"""SpotBugs adapter -- real ``java -jar spotbugs.jar -textui`` invocation.

SpotBugs is a *bytecode* analyzer: it cannot say anything at all about source it
has not seen compiled.  The adapter therefore refuses to pretend: with no
compiled classes available it reports ``UNAVAILABLE`` / ``UNSUPPORTED`` with
``evidence_gap=False`` and tells the caller to run the compile step first.  That
is a truthful "not applicable", not a silent pass.

The original SpotBugs rule id is preserved verbatim in ``rule_id``
(``CHM-JAVA-SB-<type>``) and duplicated into ``extra["spotbugs_type"]`` so the
report can always be traced back to the upstream detector.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

from ..contracts import ProviderResult, ScanContext
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import Category, RawFinding, Severity
from ..util import run_cmd
from .base import CliProvider, classify_cmd_failure, first_lines, parse_version, toolchain_root
from .pmd import coerce_ctx, config_path_failure, explicit_path_error, local_name, parse_xml

SPOTBUGS_HOME_ENV = "CHM_SPOTBUGS_HOME"

#: repo-relative directories a build usually leaves classes in
DEFAULT_CLASS_DIRS = (
    "target/classes",
    "build/classes/java/main",
    "build/classes",
    "out/production/classes",
    "bin",
    "classes",
)

#: SpotBugs priority -> our Severity (1 is the most severe)
PRIORITY_SEVERITY: dict[str, Severity] = {
    "1": Severity.HIGH,
    "2": Severity.MEDIUM,
    "3": Severity.LOW,
}

#: Exact bug pattern -> Category
TYPE_CATEGORY: dict[str, Category] = {
    "IS2_INCONSISTENT_SYNC": Category.CONCURRENCY,
    "UG_SYNC_SET_UNSYNC_GET": Category.CONCURRENCY,
    "SC_START_IN_CTOR": Category.CONCURRENCY,
    "DC_DOUBLECHECK": Category.CONCURRENCY,
    "DLS_DEAD_LOCAL_STORE": Category.DEAD_CODE,
    "UPM_UNCALLED_PRIVATE_METHOD": Category.DEAD_CODE,
    "URF_UNREAD_FIELD": Category.DEAD_CODE,
    "UUF_UNUSED_FIELD": Category.DEAD_CODE,
    "UWF_UNWRITTEN_FIELD": Category.DEAD_CODE,
    "SIC_INNER_SHOULD_BE_STATIC": Category.DEAD_CODE,
    "REC_CATCH_EXCEPTION": Category.ERROR_HANDLING,
    "DE_MIGHT_IGNORE": Category.ERROR_HANDLING,
    "DE_MIGHT_DROP": Category.ERROR_HANDLING,
    "RV_RETURN_VALUE_IGNORED": Category.ERROR_HANDLING,
}

#: Prefix rules, checked in order (longest-first by construction below).
TYPE_PREFIX_CATEGORY: tuple[tuple[str, Category], ...] = (
    ("NP_NULL_ON_SOME_PATH", Category.ERROR_HANDLING),
    ("RCN_REDUNDANT_NULLCHECK", Category.ERROR_HANDLING),
    ("OS_OPEN_STREAM", Category.RESOURCE_SAFETY),
    ("OBL_UNSATISFIED_OBLIGATION", Category.RESOURCE_SAFETY),
    ("LI_LAZY_INIT", Category.CONCURRENCY),
    ("SQL_", Category.DATABASE),
    ("DMI_", Category.ERROR_HANDLING),
    ("RV_", Category.ERROR_HANDLING),
)

#: SpotBugs' own category attribute as the fallback signal.
CATEGORY_ATTR_MAP: dict[str, Category] = {
    "PERFORMANCE": Category.PERFORMANCE,
    "MT_CORRECTNESS": Category.CONCURRENCY,
    "CORRECTNESS": Category.ERROR_HANDLING,
}


def category_for(bug_type: str, category_attr: str) -> Optional[Category]:
    """Map a SpotBugs detector onto a CHM dimension; ``None`` defers."""
    if bug_type in TYPE_CATEGORY:
        return TYPE_CATEGORY[bug_type]
    for prefix, cat in TYPE_PREFIX_CATEGORY:
        if bug_type.startswith(prefix):
            return cat
    return CATEGORY_ATTR_MAP.get((category_attr or "").strip().upper())


class SpotBugsAdapter(CliProvider):
    """Spec §10 correctness/resource/concurrency evidence via SpotBugs."""

    name = "spotbugs"
    executable = "java"
    categories = (
        Category.DEAD_CODE,
        Category.ERROR_HANDLING,
        Category.RESOURCE_SAFETY,
        Category.CONCURRENCY,
        Category.DATABASE,
        Category.PERFORMANCE,
    )

    #: Missing SpotBugs does block HIGH/CRITICAL correctness conclusions.
    evidence_gap = True

    def __init__(self, ctx: Optional[ScanContext] = None) -> None:
        #: see PmdAdapter.__init__ -- lets available()/version() see config
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
        return getattr(tools, "spotbugs", None)

    def _jar(self, ctx: Optional[ScanContext] = None) -> Optional[Path]:
        effective = self._eff(ctx)
        cfg = self._config(ctx)
        candidates: list[Path] = []
        bin_value = getattr(cfg, "bin", None) if cfg is not None else None
        if bin_value and Path(bin_value).suffix.lower() == ".jar":
            candidates.append(Path(bin_value))
        home_value = getattr(cfg, "home", None) if cfg is not None else None
        if home_value:
            candidates.append(Path(home_value))
        import os

        env = os.environ.get(SPOTBUGS_HOME_ENV)
        if env:
            candidates.append(Path(env))
        root = toolchain_root(effective)
        if root is not None and root.is_dir():
            for cand in sorted(root.glob("spotbugs-*")):
                if cand.is_dir():
                    candidates.append(cand)
            candidates.append(root)

        for cand in candidates:
            if cand.is_file() and cand.suffix.lower() == ".jar":
                return cand
            jar = cand / "lib" / "spotbugs.jar"
            if jar.is_file():
                return jar
        return None

    def version(self) -> Optional[str]:
        if self._version_probed:
            return self._version
        self._version_probed = True
        self._version = self._probe_version()
        return self._version

    def _probe_version(self) -> Optional[str]:
        """SpotBugs 4.5.3 prints nothing for ``-version``; ``-help`` carries the banner."""
        from .base import java_executable

        java = java_executable()
        jar = self._jar(None)
        if java is None or jar is None:
            return None
        for flag in ("-version", "-help"):
            result = run_cmd([java, "-jar", str(jar), flag], timeout_s=60.0)
            if result.launch_error or result.timed_out:
                continue
            parsed = parse_version(result.stdout + result.stderr)
            if parsed:
                return parsed
        return None

    def available(self) -> tuple[bool, Optional[str]]:
        from .base import java_executable

        configured_error = explicit_path_error(self._config(None), "spotbugs")
        if configured_error:
            return False, configured_error
        java = java_executable()
        if java is None:
            return False, "no Java runtime found (set JAVA_HOME or put java on PATH)"
        jar = self._jar(None)
        if jar is None:
            return False, (
                "SpotBugs distribution not found (no spotbugs.jar under the configured "
                f"home, ${SPOTBUGS_HOME_ENV}, or a 'spotbugs-*' directory in the pinned toolchain)"
            )
        result = run_cmd([java, "-jar", str(jar), "-help"], timeout_s=60.0)
        if result.launch_error:
            return False, f"java could not be launched: {result.launch_error}"
        if result.timed_out:
            return False, "SpotBugs -help timed out"
        text = result.stdout + result.stderr
        if result.exit_code != 0 and "SpotBugs" not in text:
            return False, f"SpotBugs -help exited {result.exit_code}: {first_lines(text)}"
        self._version = parse_version(text) or self._probe_version()
        self._version_probed = True
        return True, None

    # -- scope -----------------------------------------------------------

    def _classes(self, ctx: ScanContext) -> Optional[Path]:
        override = ctx.options.get("classes_dir")
        if override:
            p = Path(override)
            if p.is_dir():
                return p
        for rel in DEFAULT_CLASS_DIRS:
            p = Path(ctx.repo_root) / rel
            if p.is_dir():
                return p
        return None

    def supports(self, ctx: ScanContext) -> bool:
        return self._classes(ctx) is not None

    # -- scan -------------------------------------------------------------

    def scan(self, ctx: ScanContext) -> ProviderResult:
        self._ctx = coerce_ctx(ctx)
        cfg = self._config(ctx)
        config_failure = config_path_failure(self.name, cfg, "spotbugs")
        if config_failure is not None:
            return config_failure
        from .base import java_executable

        java = java_executable()
        if java is None:
            return self._unavailable(
                ToolFailureKind.MISSING.value,
                "no Java runtime found (set JAVA_HOME or put java on PATH)",
                gap=True,
            )
        jar = self._jar(ctx)
        if jar is None:
            return self._unavailable(
                ToolFailureKind.MISSING.value,
                "SpotBugs distribution not found; run the toolchain bootstrap first",
                gap=True,
            )

        classes = self._classes(ctx)
        if classes is None:
            return self._unavailable(
                ToolFailureKind.UNSUPPORTED.value,
                "no compiled classes; run compile step first",
                gap=False,
            )

        timeout_s = float(getattr(cfg, "timeout_s", 300.0) or 300.0)
        cache_dir = Path(ctx.cache_dir) if ctx.cache_dir is not None else None
        out_dir = cache_dir / "tmp" if cache_dir is not None else None
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
        report_path = (out_dir / "spotbugs.xml") if out_dir is not None else None

        argv = [
            java,
            "-jar",
            str(jar),
            "-textui",
            "-xml:withMessages",
        ]
        if report_path is not None:
            argv += ["-output", str(report_path)]
        argv += ["-effort:default", "-low"]
        aux = ctx.options.get("aux_classpath") or ctx.options.get("classpath")
        if aux:
            argv += ["-auxclasspath", str(aux)]
        argv.append(str(classes))
        argv += [str(a) for a in (getattr(cfg, "args", None) or [])]

        result = run_cmd(argv, cwd=Path(ctx.repo_root), timeout_s=timeout_s)
        command = result.command_line

        raw = ""
        if report_path is not None and report_path.is_file():
            from ..util import read_text

            raw = read_text(report_path)
        if not raw:
            raw = result.stdout
        artefact = self._write_artefact(ctx, "spotbugs.xml", raw) if raw else None

        if result.timed_out or result.launch_error:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=classify_cmd_failure(self.name, result, evidence_gap=True, what="SpotBugs"),
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )

        root, parse_error = parse_xml(raw)
        if root is None:
            # SpotBugs exits non-zero when it finds bugs; only treat it as a real
            # failure if we also failed to get a report out of it.
            if result.exit_code != 0:
                return ProviderResult(
                    provider=self.name,
                    status=ToolStatus.UNAVAILABLE,
                    error=classify_cmd_failure(
                        self.name, result, evidence_gap=True, what="SpotBugs"
                    ),
                    duration_ms=result.duration_ms,
                    command=command,
                    artefact=artefact,
                )
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.DEGRADED,
                error=ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.MALFORMED_OUTPUT,
                    detail=f"SpotBugs report could not be parsed ({parse_error})",
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

        findings, skipped = self._parse_bugs(root, ctx)
        error: Optional[ToolError] = None
        status = ToolStatus.OK
        if skipped:
            status = ToolStatus.DEGRADED
            error = ToolError(
                provider=self.name,
                kind=ToolFailureKind.PARTIAL_OUTPUT,
                detail=f"{skipped} SpotBugs BugInstance element(s) could not be interpreted",
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

    def _parse_bugs(self, root: ET.Element, ctx: ScanContext) -> tuple[list[RawFinding], int]:
        findings: list[RawFinding] = []
        skipped = 0
        for bug in root.iter():
            if local_name(bug.tag) != "BugInstance":
                continue
            bug_type = bug.get("type") or ""
            if not bug_type:
                skipped += 1
                continue
            category_attr = bug.get("category") or ""
            priority = bug.get("priority") or "2"

            source_file = ""
            start = end = 1
            class_name: Optional[str] = None
            method_name: Optional[str] = None
            message = ""
            for child in bug.iter():
                tag = local_name(child.tag)
                if tag == "SourceLine":
                    source_file = source_file or (child.get("sourcepath") or "")
                    try:
                        start = int(child.get("start") or start)
                        end = int(child.get("end") or start)
                    except (TypeError, ValueError):
                        pass
                elif tag == "Class":
                    class_name = class_name or child.get("classname")
                elif tag == "Method":
                    method_name = method_name or child.get("name")
                elif tag == "ShortMessage" and not message:
                    message = (child.text or "").strip()
                elif tag == "LongMessage" and not message:
                    message = (child.text or "").strip()

            if not source_file:
                # fall back to the class name as a dotted path
                source_file = (class_name or "unknown").replace(".", "/") + ".java"
                skipped += 1

            rel = self._resolve_source(source_file, ctx)
            findings.append(
                RawFinding(
                    provider=self.name,
                    rule_id="CHM-JAVA-SB-" + bug_type,
                    message=message or f"{bug_type} detected by SpotBugs",
                    file=rel,
                    start_line=max(start, 1),
                    end_line=max(end, 1),
                    symbol=method_name or class_name,
                    category=category_for(bug_type, category_attr),
                    severity=PRIORITY_SEVERITY.get(str(priority), Severity.MEDIUM),
                    confidence=0.9,
                    detail=f"SpotBugs {category_attr or 'UNKNOWN'} / {bug_type} (priority {priority})",
                    extra={
                        "spotbugs_type": bug_type,
                        "spotbugs_category": category_attr,
                        "priority": priority,
                        "classname": class_name,
                        "method": method_name,
                    },
                )
            )
        return findings, skipped

    @staticmethod
    def _resolve_source(sourcepath: str, ctx: ScanContext) -> str:
        """Turn SpotBugs' ``sourcepath`` into a repo-relative path.

        SpotBugs reports source paths relative to the *source root* it was
        pointed at (e.g. ``demo/Buggy.java`` for ``src/demo/Buggy.java``), so a
        naive join would produce a path the gate can never match against the
        changeset.  Resolve against the changed files, then the configured
        source roots, before giving up.
        """
        if not sourcepath:
            return sourcepath
        norm = sourcepath.replace("\\", "/").lstrip("./")

        # 1. already repo-relative and real
        if (Path(ctx.repo_root) / norm).is_file():
            return norm

        # 2. it is one of the files we are actually reviewing
        for cf in ctx.changed_files:
            if cf.path == norm or cf.path.endswith("/" + norm):
                return cf.path

        # 3. try each configured source root
        config = getattr(ctx, "config", None)
        roots = list(getattr(config, "source_roots", None) or ["src", "app", "lib"])
        roots.append("")
        for root_rel in roots:
            base = (Path(ctx.repo_root) / root_rel) if root_rel else Path(ctx.repo_root)
            candidate = base / norm
            if candidate.is_file():
                try:
                    return candidate.resolve().relative_to(Path(ctx.repo_root).resolve()).as_posix()
                except (ValueError, OSError):
                    return candidate.as_posix()

        # 4. bounded suffix search, so the report still points somewhere real
        tail = Path(norm).name
        for found in sorted(Path(ctx.repo_root).rglob(tail)):
            if found.is_file():
                try:
                    return found.resolve().relative_to(Path(ctx.repo_root).resolve()).as_posix()
                except (ValueError, OSError):
                    return found.as_posix()
        return norm


#: The orchestrator looks this class up as ``SpotbugsAdapter``; keep both
#: spellings working so neither the adapter map nor callers can miss it.
SpotbugsAdapter = SpotBugsAdapter
