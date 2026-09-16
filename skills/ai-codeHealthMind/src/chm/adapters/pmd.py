"""PMD 6.x adapter -- real ``java -cp ... net.sourceforge.pmd.PMD`` invocation.

PMD is our primary Java *dead code* / *complexity* evidence source, so its
absence is an evidence gap: a HIGH/CRITICAL "unused private method" conclusion
cannot be substantiated without it (spec §29).

The XML report PMD writes is parsed defensively.  PMD 6 is a Java program that
prints JUL log lines (``[main] WARN ...`` / localised ``警告:`` lines) to
*stderr*; when a caller captures stdout instead, those lines can end up glued to
the XML.  :func:`strip_to_xml` therefore trims everything before the first
``<?xml`` / ``<pmd`` marker before handing the payload to the parser.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

from ..contracts import Language, ProviderResult, ReviewMode, ScanContext, severity_from_tool
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import Category, RawFinding
from ..util import ensure_dir, run_cmd
from .base import (
    CliProvider,
    classpath_from_dir,
    classify_cmd_failure,
    first_lines,
    java_executable,
    parse_version,
    toolchain_root,
)

#: main classes inside the PMD distribution
PMD_MAIN = "net.sourceforge.pmd.PMD"
CPD_MAIN = "net.sourceforge.pmd.cpd.CPD"

#: environment override for the pinned PMD distribution
PMD_HOME_ENV = "CHM_PMD_HOME"

#: built-in fallback ruleset shipped inside the PMD jars
FALLBACK_RULESET = "rulesets/java/quickstart.xml"

#: repository-relative preferred ruleset
REPO_RULESET_REL = ("rules/java/pmd-ruleset.xml",)

#: how PMD's 1..5 priority vocabulary maps onto our Severity (1 = worst).
#: Delegated to :func:`severity_from_tool` so the whole codebase agrees.


# --------------------------------------------------------------------------
# tool resolution (shared with cpd.py)
# --------------------------------------------------------------------------


def coerce_ctx(value: Any) -> Optional[ScanContext]:
    """Normalise whatever an adapter is constructed with.

    The orchestrator builds providers as ``Cls(self.config)`` (a bare
    :class:`~chm.config.Config`), while the probe builds them as
    ``Cls(scan_context)``.  Both call styles must work, and neither may be
    silently ignored -- dropping the config would break the documented tool
    discovery order (``tools.X.bin`` -> ``tools.X.home`` -> env -> PATH).
    """
    if value is None:
        return None
    if isinstance(value, ScanContext):
        return value
    if hasattr(value, "tools"):
        return ScanContext(repo_root=Path.cwd(), mode=ReviewMode.REPO, config=value)
    return None


def _looks_like_path(value: str) -> bool:
    """Distinguish ``./tools/pmd`` from a bare command name like ``pmd``.

    Only path-looking values are validated: ``bin: semgrep`` is a legitimate way
    to name a command to be resolved on PATH, and must not be reported as a
    missing file.
    """
    return any(sep in value for sep in ("/", "\\", ":")) or value.startswith(".")


def explicit_path_error(cfg: Any, tool_key: str) -> Optional[str]:
    """Describe an explicitly configured ``home``/``bin`` that does not exist.

    Returns ``None`` when nothing was configured, or when what was configured is
    a bare command name rather than a path.  A non-``None`` result means the
    adapter MUST fail with ``ToolFailureKind.CONFIG`` instead of quietly falling
    back to the pinned toolchain -- otherwise the user believes they selected a
    tool while a different one actually ran, which is exactly the "never a false
    green" failure this project exists to prevent (spec §29).
    """
    if cfg is None:
        return None
    problems: list[str] = []
    for field in ("bin", "home"):
        value = getattr(cfg, field, None)
        if not value or not isinstance(value, str):
            continue
        if not _looks_like_path(value):
            continue
        if not Path(value).exists():
            problems.append(f"tools.{tool_key}.{field} = '{value}' does not exist")
    if not problems:
        return None
    return "; ".join(problems) + " (explicitly configured paths are never silently ignored)"


def config_path_failure(
    provider: str, cfg: Any, tool_key: str
) -> Optional[ProviderResult]:
    """A ready-made ``UNAVAILABLE``/``CONFIG`` result, or ``None`` if config is sane."""
    detail = explicit_path_error(cfg, tool_key)
    if detail is None:
        return None
    return ProviderResult(
        provider=provider,
        status=ToolStatus.UNAVAILABLE,
        error=ToolError(
            provider=provider,
            kind=ToolFailureKind.CONFIG,
            detail=detail,
            evidence_gap=True,
        ),
    )


def _glob_distribution(root: Path, prefix: str) -> Optional[Path]:
    if not root.is_dir():
        return None
    matches = sorted(p for p in root.glob(prefix + "*") if p.is_dir() and (p / "lib").is_dir())
    return matches[-1] if matches else None


def pmd_home(ctx: Optional[ScanContext] = None, cfg: Any = None) -> Optional[Path]:
    """Resolve the PMD distribution root.

    Discovery order (spec §28): ``config.tools.pmd.home`` -> ``bin`` ->
    ``CHM_PMD_HOME`` -> pinned toolchain -> PATH.
    """
    candidates: list[Path] = []
    if cfg is not None:
        for value in (getattr(cfg, "home", None), getattr(cfg, "bin", None)):
            if not value:
                continue
            p = Path(value)
            # ``bin`` may point at the pmd launcher script inside ``<home>/bin``
            if p.is_file() and p.parent.name == "bin":
                candidates.append(p.parent.parent)
            else:
                candidates.append(p)
    env = os.environ.get(PMD_HOME_ENV)
    if env:
        candidates.append(Path(env))
    else:
        root = toolchain_root(ctx)
        if root is not None:
            found = _glob_distribution(root, "pmd-bin-")
            if found is not None:
                candidates.append(found)

    for cand in candidates:
        if (cand / "lib").is_dir():
            return cand
    return None


def pmd_lib_classpath(home: Optional[Path], cfg: Any = None) -> Optional[str]:
    """``;``/``:`` separated classpath of every jar in ``<home>/lib``."""
    if cfg is not None and getattr(cfg, "bin", None):
        bin_path = Path(cfg.bin)
        if bin_path.suffix.lower() == ".jar" and bin_path.is_file():
            extra = classpath_from_dir(home / "lib") if home else None
            return os.pathsep.join([str(bin_path), extra] if extra else [str(bin_path)])
    if home is None:
        return None
    return classpath_from_dir(home / "lib")


def java_classpath_prefix(
    ctx: Optional[ScanContext],
    cfg: Any,
    main_class: str,
    *,
    dist_prefix: str = "pmd-bin-",
) -> tuple[Optional[list[str]], Optional[str]]:
    """Build ``[java, -cp, <classpath>, <main_class>]`` or explain why not."""
    java = java_executable()
    if not java:
        return None, "no Java runtime found (set JAVA_HOME or put java on PATH)"
    home = pmd_home(ctx, cfg)
    classpath = pmd_lib_classpath(home, cfg)
    if not classpath:
        return None, (
            f"PMD distribution not found (looked for a '{dist_prefix}*' directory "
            f"with a lib/ folder in the pinned toolchain and ${PMD_HOME_ENV})"
        )
    return [java, "-cp", classpath, main_class], None


# --------------------------------------------------------------------------
# output handling
# --------------------------------------------------------------------------


def strip_to_xml(text: str) -> str:
    """Drop log noise glued in front of an XML payload."""
    if not text:
        return ""
    for marker in ("<?xml", "<pmd", "<pmd-cpd"):
        idx = text.find(marker)
        if idx >= 0:
            return text[idx:]
    return text.strip()


def local_name(tag: str) -> str:
    """``{ns}violation`` -> ``violation`` (PMD 6 emits a default namespace)."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_xml(text: str) -> tuple[Optional[ET.Element], Optional[str]]:
    """Parse XML defensively; returns ``(root, error_detail)``."""
    payload = strip_to_xml(text)
    if not payload:
        return None, "empty report"
    try:
        return ET.fromstring(payload), None
    except ET.ParseError as exc:
        return None, f"XML parse error: {exc}"


# --------------------------------------------------------------------------
# rule -> Category mapping
# --------------------------------------------------------------------------

#: Explicit, hand-curated map for the rules we actually rely on.
RULE_CATEGORY: dict[str, Category] = {
    # ---- dead code ----------------------------------------------------
    "UnusedPrivateMethod": Category.DEAD_CODE,
    "UnusedPrivateField": Category.DEAD_CODE,
    "UnusedPrivateConstructor": Category.DEAD_CODE,
    "UnusedLocalVariable": Category.DEAD_CODE,
    "UnusedFormalParameter": Category.DEAD_CODE,
    "UnusedAssignment": Category.DEAD_CODE,
    "UnusedImports": Category.DEAD_CODE,
    "UnnecessaryImport": Category.DEAD_CODE,
    "SingularField": Category.DEAD_CODE,
    "UnusedNullCheckInEquals": Category.DEAD_CODE,
    "UselessOperationOnImmutable": Category.DEAD_CODE,
    # ---- complexity / size --------------------------------------------
    "CyclomaticComplexity": Category.COMPLEXITY,
    "NPathComplexity": Category.COMPLEXITY,
    "CognitiveComplexity": Category.COMPLEXITY,
    "ExcessiveParameterList": Category.COMPLEXITY,
    "CouplingBetweenObjects": Category.COMPLEXITY,
    "ExcessiveImports": Category.COMPLEXITY,
    "ExcessiveMethodLength": Category.LARGE_METHOD,
    "ExcessiveClassLength": Category.LARGE_CLASS,
    "ExcessivePublicCount": Category.LARGE_CLASS,
    "TooManyMethods": Category.LARGE_CLASS,
    "TooManyFields": Category.LARGE_CLASS,
    "GodClass": Category.LARGE_CLASS,
    "TooManyStaticImports": Category.CONFIG_INFLATION,
    # ---- error handling ------------------------------------------------
    "EmptyCatchBlock": Category.ERROR_HANDLING,
    "AvoidCatchingGenericException": Category.ERROR_HANDLING,
    "AvoidCatchingNPE": Category.ERROR_HANDLING,
    "AvoidCatchingThrowable": Category.ERROR_HANDLING,
    "AvoidThrowingRawExceptionTypes": Category.ERROR_HANDLING,
    "AvoidThrowingNullPointerException": Category.ERROR_HANDLING,
    "AvoidRethrowingException": Category.ERROR_HANDLING,
    "PreserveStackTrace": Category.ERROR_HANDLING,
    "DoNotThrowExceptionInFinally": Category.ERROR_HANDLING,
    "ReturnFromFinallyBlock": Category.ERROR_HANDLING,
    # ---- resource safety ----------------------------------------------
    "CloseResource": Category.RESOURCE_SAFETY,
    "UseTryWithResources": Category.RESOURCE_SAFETY,
    "AvoidFileStream": Category.RESOURCE_SAFETY,
    # ---- concurrency ---------------------------------------------------
    "AvoidSynchronizedAtMethodLevel": Category.CONCURRENCY,
    "UnsynchronizedStaticFormatter": Category.CONCURRENCY,
    "DoNotUseThreads": Category.CONCURRENCY,
    "AvoidThreadGroup": Category.CONCURRENCY,
    "NonThreadSafeSingleton": Category.CONCURRENCY,
    "AvoidUsingVolatile": Category.CONCURRENCY,
    "UnsynchronizedStaticDateFormatter": Category.CONCURRENCY,
    # ---- defensive junk -------------------------------------------------
    "UnnecessaryNullCheck": Category.DEFENSIVE_JUNK,
    "UnnecessaryNullCheckBeforeInstanceOf": Category.DEFENSIVE_JUNK,
    "AvoidDuplicateLiterals": Category.BOILERPLATE,
    "AvoidLiteralsInIfCondition": Category.DEFENSIVE_JUNK,
    "EmptyIfStmt": Category.DEFENSIVE_JUNK,
    "EmptyWhileStmt": Category.DEFENSIVE_JUNK,
    "EmptyTryBlock": Category.DEFENSIVE_JUNK,
    # ---- performance ----------------------------------------------------
    "AvoidInstantiatingObjectsInLoops": Category.PERFORMANCE,
    "InefficientStringBuffering": Category.PERFORMANCE,
    "StringInstantiation": Category.PERFORMANCE,
    "ConsecutiveLiteralAppends": Category.PERFORMANCE,
    "UseStringBufferForStringAppends": Category.PERFORMANCE,
    "InefficientEmptyStringCheck": Category.PERFORMANCE,
    # ---- database --------------------------------------------------------
    "AvoidResultSetMethodCalls": Category.DATABASE,
    "CloseResource.Db": Category.DATABASE,
    # ---- the rest of the shipped ruleset --------------------------------
    # Every rule referenced by rules/java/pmd-ruleset.xml must appear above,
    # otherwise an unknown rule silently falls back to its *ruleset* name and
    # ends up in a nonsense dimension (e.g. LooseCoupling -> DEAD_CODE).
    "LooseCoupling": Category.COMPLEXITY,
    "AvoidReassigningParameters": Category.COMPLEXITY,
    "AvoidDeeplyNestedIfStmts": Category.COMPLEXITY,
    "CollapsibleIfStatements": Category.COMPLEXITY,
    "SimplifyBooleanReturns": Category.COMPLEXITY,
    "SimplifyBooleanExpressions": Category.COMPLEXITY,
    "SimplifyConditional": Category.COMPLEXITY,
    "SwitchDensity": Category.COMPLEXITY,
    "TooFewBranchesForASwitchStatement": Category.COMPLEXITY,
    "DefaultLabelNotLastInSwitchStmt": Category.COMPLEXITY,
    "NcssCount": Category.COMPLEXITY,
    "LawOfDemeter": Category.COMPLEXITY,
    "MethodReturnsInternalArray": Category.CONCURRENCY,
    "ArrayIsStoredDirectly": Category.CONCURRENCY,
    "AssignmentToNonFinalStatic": Category.CONCURRENCY,
    "DoNotTerminateVM": Category.ERROR_HANDLING,
    "AvoidLosingExceptionInformation": Category.ERROR_HANDLING,
    "BrokenNullCheck": Category.ERROR_HANDLING,
    "ExceptionAsFlowControl": Category.ERROR_HANDLING,
    "AvoidPrintStackTrace": Category.ERROR_HANDLING,
    "CheckResultSet": Category.ERROR_HANDLING,
    "GuardLogStatement": Category.PERFORMANCE,
    "ConsecutiveAppendsShouldReuse": Category.PERFORMANCE,
    "InsufficientStringBufferDeclaration": Category.PERFORMANCE,
    "UseStringBufferLength": Category.PERFORMANCE,
    "StringToString": Category.PERFORMANCE,
    "UseIndexOfChar": Category.PERFORMANCE,
    "RedundantFieldInitializer": Category.PERFORMANCE,
    "OptimizableToArrayCall": Category.PERFORMANCE,
    "UnnecessaryWrapperObjectCreation": Category.PERFORMANCE,
    "SystemPrintln": Category.DEAD_CODE,
    "UnnecessaryLocalBeforeReturn": Category.DEAD_CODE,
    "UselessOverridingMethod": Category.DEAD_CODE,
    "UnnecessaryModifier": Category.BOILERPLATE,
    "UnnecessaryReturn": Category.BOILERPLATE,
    "AccessorClassGeneration": Category.BOILERPLATE,
    "OneDeclarationPerLine": Category.BOILERPLATE,
    "MissingOverride": Category.BOILERPLATE,
    "ImmutableField": Category.BOILERPLATE,
    "ClassWithOnlyPrivateConstructorsShouldBeFinal": Category.BOILERPLATE,
    "AbstractClassWithoutAnyMethod": Category.WRONG_ABSTRACTION,
    "EmptyControlStatement": Category.DEFENSIVE_JUNK,
}

#: When a rule is unknown, its PMD ruleset name is the next best signal.
#:
#: ``best practices`` deliberately maps to ``None``: that ruleset mixes dead
#: code, coupling, resource and logging rules, so guessing a dimension from it
#: is worse than letting the normalizer infer one from the rule id.
RULESET_CATEGORY: dict[str, Category] = {
    "error prone": Category.ERROR_HANDLING,
    "multithreading": Category.CONCURRENCY,
    "performance": Category.PERFORMANCE,
    "design": Category.COMPLEXITY,
}


def category_for(rule: str, ruleset: str) -> Optional[Category]:
    """Best-effort rule -> dimension mapping; ``None`` defers to the normalizer."""
    if rule in RULE_CATEGORY:
        return RULE_CATEGORY[rule]
    return RULESET_CATEGORY.get((ruleset or "").strip().lower())


# --------------------------------------------------------------------------
# adapter
# --------------------------------------------------------------------------


class PmdAdapter(CliProvider):
    """Spec §28 evidence provider backed by the genuine PMD CLI."""

    name = "pmd"
    executable = "java"
    categories = (
        Category.DEAD_CODE,
        Category.COMPLEXITY,
        Category.LARGE_METHOD,
        Category.LARGE_CLASS,
        Category.ERROR_HANDLING,
        Category.RESOURCE_SAFETY,
        Category.CONCURRENCY,
        Category.PERFORMANCE,
    )

    #: PMD absence blocks HIGH/CRITICAL Java conclusions -> evidence gap.
    evidence_gap = True

    def __init__(self, ctx: Optional[ScanContext] = None) -> None:
        #: Context injected at construction.  ``available()``/``version()`` take
        #: no ctx argument by contract, so this is how config-driven tool
        #: locations (``tools.pmd.bin``/``home``) stay reachable from them.
        #: The orchestrator passes a bare ``Config``; ``coerce_ctx`` wraps it.
        self._ctx = coerce_ctx(ctx)
        self._version: Optional[str] = None
        self._version_probed = False

    # -- capability ------------------------------------------------------

    def _eff(self, ctx: Optional[ScanContext]) -> Optional[ScanContext]:
        return ctx if ctx is not None else self._ctx

    def _config(self, ctx: Optional[ScanContext] = None) -> Any:
        effective = self._eff(ctx)
        cfg = getattr(effective, "config", None) if effective is not None else None
        tools = getattr(cfg, "tools", None)
        return getattr(tools, "pmd", None)

    def _prefix(self, ctx: Optional[ScanContext] = None) -> tuple[Optional[list[str]], Optional[str]]:
        return java_classpath_prefix(self._eff(ctx), self._config(ctx), PMD_MAIN)

    def version(self) -> Optional[str]:
        if self._version_probed:
            return self._version
        self._version_probed = True
        prefix, _ = self._prefix(None)
        if prefix is None:
            return None
        result = run_cmd([*prefix, "--version"], timeout_s=60.0)
        if not result.ok:
            return None
        self._version = parse_version(result.stdout + result.stderr)
        return self._version

    def available(self) -> tuple[bool, Optional[str]]:
        # An explicitly configured path that does not exist is a configuration
        # error, never a reason to quietly use a different toolchain.
        configured_error = explicit_path_error(self._config(None), "pmd")
        if configured_error:
            return False, configured_error
        prefix, reason = self._prefix(None)
        if prefix is None:
            return False, reason
        result = run_cmd([*prefix, "--version"], timeout_s=60.0)
        if result.launch_error:
            return False, f"java could not be launched: {result.launch_error}"
        if result.timed_out:
            return False, "PMD --version timed out"
        if result.exit_code != 0:
            return False, f"PMD --version exited {result.exit_code}: {first_lines(result.stderr)}"
        self._version = parse_version(result.stdout + result.stderr)
        self._version_probed = True
        return True, None

    # -- scope -----------------------------------------------------------

    def supports(self, ctx: ScanContext) -> bool:
        if str(ctx.options.get("pmd_scope", "")).lower() == "repo":
            return True
        return bool(ctx.paths(Language.JAVA))

    def _targets(self, ctx: ScanContext) -> tuple[bool, list[str]]:
        """Return ``(scan_whole_repo, absolute_java_paths)``.

        Scanning the repo root is the honest default only when explicitly asked
        for: ``ctx.options["pmd_scope"] == "repo"``.  Otherwise we analyse just
        the changed files, which is what the gate actually cares about.
        """
        if str(ctx.options.get("pmd_scope", "")).lower() == "repo":
            return True, []
        abs_paths = []
        for rel in ctx.paths(Language.JAVA):
            p = Path(ctx.repo_root) / rel
            if p.is_file():
                abs_paths.append(str(p))
        return False, abs_paths

    def _ruleset(self, ctx: ScanContext) -> str:
        cfg = self._config(ctx)
        configured = getattr(cfg, "ruleset", None) if cfg is not None else None
        if configured:
            candidate = Path(ctx.repo_root) / configured
            if candidate.is_file():
                return str(candidate)
            return configured
        for rel in REPO_RULESET_REL:
            candidate = Path(ctx.repo_root) / rel
            if candidate.is_file():
                return str(candidate)
        return FALLBACK_RULESET

    # -- scan -------------------------------------------------------------

    def scan(self, ctx: ScanContext) -> ProviderResult:
        self._ctx = ctx
        cfg = self._config(ctx)
        config_failure = config_path_failure(self.name, cfg, "pmd")
        if config_failure is not None:
            return config_failure
        prefix, reason = self._prefix(ctx)
        if prefix is None:
            return self._unavailable(ToolFailureKind.MISSING.value, reason or "PMD not found", gap=True)

        timeout_s = float(getattr(cfg, "timeout_s", 300.0) or 300.0)
        repo_scope, abs_paths = self._targets(ctx)
        if not repo_scope and not abs_paths:
            return self._unavailable(
                ToolFailureKind.UNSUPPORTED.value,
                "no Java files to analyse in this changeset",
                gap=False,
            )

        cache_dir = Path(ctx.cache_dir) if ctx.cache_dir is not None else None
        out_dir = ensure_dir(cache_dir / "tmp") if cache_dir is not None else None
        if repo_scope:
            targets_argv = ["-d", str(Path(ctx.repo_root))]
        else:
            if out_dir is None:
                return self._unavailable(
                    ToolFailureKind.CONFIG.value,
                    "no cache directory available to stage the PMD file list",
                    gap=True,
                )
            filelist_path = out_dir / "pmd-filelist.txt"
            try:
                filelist_path.write_text("\n".join(abs_paths), encoding="utf-8")
            except OSError as exc:
                return ProviderResult(
                    provider=self.name,
                    status=ToolStatus.UNAVAILABLE,
                    error=ToolError(
                        provider=self.name,
                        kind=ToolFailureKind.CONFIG,
                        detail=f"could not write PMD file list: {exc}",
                        evidence_gap=True,
                    ),
                )
            targets_argv = ["-filelist", str(filelist_path)]

        report_path: Optional[Path] = None
        if out_dir is not None:
            report_path = out_dir / "pmd-report.xml"

        argv = [
            *prefix,
            *targets_argv,
            "-R",
            self._ruleset(ctx),
            "-f",
            "xml",
            "--no-cache",
            "--fail-on-violation",
            "false",
        ]
        if report_path is not None:
            argv += ["-r", str(report_path)]
        argv += [str(a) for a in (getattr(cfg, "args", None) or [])]

        result = run_cmd(argv, cwd=Path(ctx.repo_root), timeout_s=timeout_s)

        raw_report = ""
        if report_path is not None and report_path.is_file():
            from ..util import read_text

            raw_report = read_text(report_path)
        if not raw_report:
            raw_report = result.stdout

        artefact = self._write_artefact(ctx, "pmd.xml", raw_report) if raw_report else None
        command = result.command_line

        # PMD exits 4 when violations are found unless fail-on-violation is off;
        # any other non-zero exit is a genuine tool failure.
        if result.timed_out:
            err = classify_cmd_failure(self.name, result, evidence_gap=True, what="PMD")
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=err,
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )
        if result.launch_error:
            err = classify_cmd_failure(self.name, result, evidence_gap=True, what="PMD")
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=err,
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )
        if result.exit_code not in (0, 4) and not raw_report:
            err = classify_cmd_failure(self.name, result, evidence_gap=True, what="PMD")
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=err,
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )

        root, parse_error = parse_xml(raw_report)
        if root is None:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.DEGRADED,
                error=ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.MALFORMED_OUTPUT,
                    detail=f"PMD report could not be parsed ({parse_error})",
                    command=command,
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    stderr_excerpt=first_lines(result.stderr),
                    evidence_gap=True,
                ),
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )

        findings, skipped = self._parse_violations(root, ctx)
        error: Optional[ToolError] = None
        status = ToolStatus.OK
        if skipped:
            status = ToolStatus.DEGRADED
            error = ToolError(
                provider=self.name,
                kind=ToolFailureKind.PARTIAL_OUTPUT,
                detail=f"{skipped} PMD violation element(s) could not be interpreted",
                command=command,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                evidence_gap=False,
            )

        return ProviderResult(
            provider=self.name,
            status=status,
            findings=findings,
            error=error,
            duration_ms=result.duration_ms,
            command=command,
            version=self.version(),
            artefact=artefact,
        )

    def _parse_violations(
        self, root: ET.Element, ctx: ScanContext
    ) -> tuple[list[RawFinding], int]:
        findings: list[RawFinding] = []
        skipped = 0
        for file_el in root:
            if local_name(file_el.tag) != "file":
                continue
            file_path = file_el.get("name") or ""
            rel = self._relativise(file_path, ctx)
            for violation in file_el:
                if local_name(violation.tag) != "violation":
                    continue
                rule = violation.get("rule") or ""
                if not rule:
                    skipped += 1
                    continue
                try:
                    start = int(violation.get("beginline") or 1)
                    end = int(violation.get("endline") or start)
                except (TypeError, ValueError):
                    start, end = 1, 1
                    skipped += 1
                priority = violation.get("priority")
                ruleset = violation.get("ruleset") or ""
                message = (violation.text or "").strip() or rule
                severity = severity_from_tool(str(priority or ""))

                extra: dict[str, Any] = {
                    "pmd_rule": rule,
                    "priority": priority,
                    "ruleset": ruleset,
                }
                for attr in ("package", "class", "method", "variable"):
                    value = violation.get(attr)
                    if value:
                        extra[attr] = value

                findings.append(
                    RawFinding(
                        provider=self.name,
                        rule_id="CHM-JAVA-PMD-" + _rule_token(rule),
                        message=message,
                        file=rel,
                        start_line=start,
                        end_line=end,
                        symbol=violation.get("method") or violation.get("variable") or violation.get("class"),
                        category=category_for(rule, ruleset),
                        severity=severity,
                        confidence=0.9,
                        detail=f"{ruleset} / {rule} (priority {priority})",
                        extra=extra,
                    )
                )
        return findings, skipped

    @staticmethod
    def _relativise(path: str, ctx: ScanContext) -> str:
        if not path:
            return path
        try:
            return Path(path).resolve().relative_to(Path(ctx.repo_root).resolve()).as_posix()
        except (ValueError, OSError):
            return Path(path).as_posix()


def _rule_token(rule: str) -> str:
    """``UnusedPrivateField`` -> ``UNUSED-PRIVATE-FIELD`` (stable rule-id tail)."""
    token = re.sub(r"[^A-Za-z0-9]+", "-", rule).strip("-").upper()
    return token or "UNKNOWN"
