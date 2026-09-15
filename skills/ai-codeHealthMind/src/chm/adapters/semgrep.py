"""Semgrep adapter -- real ``semgrep --config <local rules> --json`` invocation.

Only the genuine CLI is used.  ``--config auto`` is deliberately *not* an
option: the gate must be reproducible and offline, so the ruleset always comes
from ``config.tools.semgrep.ruleset`` or from the repository's own ``rules/``
tree.

On hosts without semgrep (including the Windows dev box this was written on)
the adapter reports ``UNAVAILABLE`` / ``MISSING`` with ``evidence_gap=True``.
That is the honest answer: several HIGH findings simply cannot be substantiated
without it.  It never fabricates a clean result.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from ..contracts import Language, ProviderResult, ScanContext, severity_from_tool
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import Category, EvidenceKind, RawFinding, Severity
from ..util import run_cmd, which
from .base import CliProvider, classify_cmd_failure, first_lines, parse_version, toolchain_root
from .pmd import coerce_ctx, config_path_failure, explicit_path_error

SEMGREP_ENV = "CHM_SEMGREP_BIN"

#: repository rule directories per language (spec §12)
RULE_DIR_BY_LANGUAGE: dict[Language, tuple[str, ...]] = {
    Language.JAVA: ("rules/common", "rules/java", "rules/shejiu"),
    Language.JAVASCRIPT: ("rules/common", "rules/javascript"),
    Language.TYPESCRIPT: ("rules/common", "rules/typescript"),
    Language.VUE: ("rules/common", "rules/vue2"),
}

#: check_id namespace prefixes stripped before building our rule id
_ID_PREFIXES = (
    "rules.common.",
    "rules.java.",
    "rules.javascript.",
    "rules.typescript.",
    "rules.vue2.",
    "rules.shejiu.",
)

#: semgrep severity vocabulary -> our Category is unknowable from the CLI alone,
#: so we leave ``category`` for the normalizer and only fix the severity here.
_SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "info": Severity.LOW,
}


class SemgrepAdapter(CliProvider):
    """Spec §10 pattern-based evidence for Java/JS/TS/Vue."""

    name = "semgrep"
    executable = "semgrep"
    categories = (
        Category.ERROR_HANDLING,
        Category.RESOURCE_SAFETY,
        Category.CONCURRENCY,
        Category.DATABASE,
        Category.PERFORMANCE,
    )

    #: semgrep absence blocks HIGH/CRITICAL pattern conclusions.
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
        return getattr(tools, "semgrep", None)

    def _binary(self, ctx: Optional[ScanContext] = None) -> Optional[str]:
        import os

        effective = self._eff(ctx)
        cfg = self._config(ctx)
        bin_value = getattr(cfg, "bin", None) if cfg is not None else None
        if bin_value and Path(bin_value).is_file():
            return bin_value
        env = os.environ.get(SEMGREP_ENV)
        if env and Path(env).is_file():
            return env
        roots: list[Path] = []
        home = getattr(cfg, "home", None) if cfg is not None else None
        if home:
            roots.append(Path(home))
        root = toolchain_root(effective)
        if root is not None:
            roots.append(root)
        return which(self.executable, roots)

    def version(self) -> Optional[str]:
        if self._version_probed:
            return self._version
        self._version_probed = True
        binary = self._binary(None)
        if binary is None:
            return None
        result = run_cmd([binary, "--version"], timeout_s=60.0)
        if not result.ok:
            return None
        self._version = parse_version(result.stdout + result.stderr)
        return self._version

    def available(self) -> tuple[bool, Optional[str]]:
        configured_error = explicit_path_error(self._config(None), "semgrep")
        if configured_error:
            return False, configured_error
        binary = self._binary(None)
        if binary is None:
            return False, (
                "semgrep is not installed on this host (not in config, not on PATH)"
            )
        result = run_cmd([binary, "--version"], timeout_s=60.0)
        if result.launch_error:
            return False, f"semgrep could not be launched: {result.launch_error}"
        if result.timed_out:
            return False, "semgrep --version timed out"
        if result.exit_code != 0:
            return False, f"semgrep --version exited {result.exit_code}: {first_lines(result.stderr)}"
        self._version = parse_version(result.stdout + result.stderr)
        self._version_probed = True
        return True, None

    # -- scope -----------------------------------------------------------

    def _rulesets(self, ctx: ScanContext) -> list[str]:
        cfg = self._config(ctx)
        configured = getattr(cfg, "ruleset", None) if cfg is not None else None
        if configured:
            candidate = Path(ctx.repo_root) / configured
            if candidate.exists():
                return [str(candidate)]
            return [configured]

        dirs: list[str] = []
        for language in sorted(ctx.language_set(), key=lambda l: l.value):
            for rel in RULE_DIR_BY_LANGUAGE.get(language, ()):
                candidate = Path(ctx.repo_root) / rel
                if candidate.is_dir() and str(candidate) not in dirs:
                    dirs.append(str(candidate))
        return dirs

    def _paths(self, ctx: ScanContext) -> list[str]:
        wanted = {Language.JAVA, Language.JAVASCRIPT, Language.TYPESCRIPT, Language.VUE}
        return [
            cf.path
            for cf in ctx.changed_files
            if not cf.is_binary and cf.language in wanted
        ]

    def supports(self, ctx: ScanContext) -> bool:
        return bool(self._paths(ctx)) and bool(self._rulesets(ctx))

    # -- scan -------------------------------------------------------------

    def scan(self, ctx: ScanContext) -> ProviderResult:
        self._ctx = coerce_ctx(ctx)
        cfg = self._config(ctx)
        config_failure = config_path_failure(self.name, cfg, "semgrep")
        if config_failure is not None:
            return config_failure
        binary = self._binary(ctx)
        if binary is None:
            return self._unavailable(
                ToolFailureKind.MISSING.value,
                "semgrep is not installed on this host (not in config, not on PATH)",
                gap=True,
            )

        rulesets = self._rulesets(ctx)
        if not rulesets:
            return self._unavailable(
                ToolFailureKind.UNSUPPORTED.value,
                "no semgrep ruleset configured and no matching rules/ directory in the repository",
                gap=False,
            )

        paths = self._paths(ctx)
        if not paths:
            return self._unavailable(
                ToolFailureKind.UNSUPPORTED.value,
                "no Java/JS/TS/Vue files in this changeset",
                gap=False,
            )

        timeout_s = float(getattr(cfg, "timeout_s", 300.0) or 300.0)
        argv = [binary, "--json", "--quiet", "--no-git-ignore"]
        for ruleset in rulesets:
            argv += ["--config", ruleset]
        argv += [str(a) for a in (getattr(cfg, "args", None) or [])]
        argv += paths

        result = run_cmd(argv, cwd=Path(ctx.repo_root), timeout_s=timeout_s)
        command = result.command_line
        artefact = self._write_artefact(ctx, "semgrep.json", result.stdout) if result.stdout else None

        if result.timed_out or result.launch_error:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=classify_cmd_failure(self.name, result, evidence_gap=True, what="semgrep"),
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )

        payload, parse_error = self._load_json(result.stdout)
        if payload is None:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.DEGRADED if result.exit_code == 0 else ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=self.name,
                    kind=(
                        ToolFailureKind.MALFORMED_OUTPUT
                        if result.exit_code == 0
                        else ToolFailureKind.NONZERO_EXIT
                    ),
                    detail=(
                        f"semgrep output could not be parsed ({parse_error})"
                        if result.exit_code == 0
                        else f"semgrep exited {result.exit_code}: {first_lines(result.stderr)}"
                    ),
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

        findings, skipped = self._parse_results(payload, ctx)
        error: Optional[ToolError] = None
        status = ToolStatus.OK
        if result.exit_code not in (0, 1):  # semgrep uses 1 for "findings present"
            status = ToolStatus.DEGRADED
            error = ToolError(
                provider=self.name,
                kind=ToolFailureKind.NONZERO_EXIT,
                detail=f"semgrep exited {result.exit_code} but produced a parseable report",
                command=command,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                stderr_excerpt=first_lines(result.stderr),
                evidence_gap=False,
            )
        elif skipped:
            status = ToolStatus.DEGRADED
            error = ToolError(
                provider=self.name,
                kind=ToolFailureKind.PARTIAL_OUTPUT,
                detail=f"{skipped} semgrep result(s) lacked a usable path/rule",
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

    @staticmethod
    def _load_json(text: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        if not text or not text.strip():
            return None, "empty output"
        # semgrep may print progress lines before the JSON document
        start = text.find("{")
        if start < 0:
            return None, "no JSON object found"
        payload_text = text[start:]
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            return None, str(exc)
        if not isinstance(payload, dict):
            return None, "top-level JSON value is not an object"
        return payload, None

    def _parse_results(
        self, payload: dict[str, Any], ctx: ScanContext
    ) -> tuple[list[RawFinding], int]:
        results = payload.get("results")
        if not isinstance(results, list):
            return [], 0

        findings: list[RawFinding] = []
        skipped = 0
        for item in results:
            if not isinstance(item, dict):
                skipped += 1
                continue
            check_id = str(item.get("check_id") or "")
            path = str(item.get("path") or "")
            if not check_id or not path:
                skipped += 1
                continue

            start_obj = item.get("start") or {}
            end_obj = item.get("end") or {}
            try:
                start_line = int(start_obj.get("line") or 1)
            except (TypeError, ValueError):
                start_line = 1
            try:
                end_line = int(end_obj.get("line") or start_line)
            except (TypeError, ValueError):
                end_line = start_line

            extra = item.get("extra") or {}
            message = str(extra.get("message") or check_id)
            severity_text = str(extra.get("severity") or "").lower()
            metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
            if metadata is None:
                metadata = {}

            raw_severity = severity_text
            # semgrep's own vocabulary is ERROR/WARNING/INFO; fall back to the
            # shared mapper for anything else (e.g. a rule that already speaks
            # CHM's CRITICAL/HIGH/MEDIUM/LOW).
            severity = _SEVERITY_MAP.get(severity_text) or severity_from_tool(raw_severity)
            if raw_severity.upper() in Severity.__members__:
                severity = Severity[raw_severity.upper()]

            category = self._category_from_metadata(metadata)

            findings.append(
                RawFinding(
                    provider=self.name,
                    rule_id="CHM-" + normalise_check_id(check_id),
                    message=message,
                    file=self._relativise(path, ctx),
                    start_line=start_line,
                    end_line=end_line,
                    category=category,
                    severity=severity,
                    confidence=0.85,
                    kind=EvidenceKind.DETERMINISTIC,
                    detail=str(metadata.get("message") or check_id),
                    extra={
                        "semgrep_check_id": check_id,
                        "semgrep_severity": extra.get("severity"),
                        "metadata": metadata,
                    },
                )
            )
        return findings, skipped

    @staticmethod
    def _category_from_metadata(metadata: dict[str, Any]) -> Optional[Category]:
        for key in ("chm_category", "category"):
            value = metadata.get(key)
            if isinstance(value, str):
                token = value.strip().upper().replace("-", "_")
                if token in Category.__members__:
                    return Category[token]
        return None

    @staticmethod
    def _relativise(path: str, ctx: ScanContext) -> str:
        try:
            return Path(path).resolve().relative_to(Path(ctx.repo_root).resolve()).as_posix()
        except (ValueError, OSError):
            return Path(path).as_posix()


def normalise_check_id(check_id: str) -> str:
    """``rules.java.foo.bar-baz`` -> ``JAVA-FOO-BAR-BAZ``."""
    token = check_id
    for prefix in _ID_PREFIXES:
        if token.startswith(prefix):
            token = token[len(prefix) :]
            break
    token = re.sub(r"[^A-Za-z0-9]+", "-", token).strip("-").upper()
    return token or "UNKNOWN"
