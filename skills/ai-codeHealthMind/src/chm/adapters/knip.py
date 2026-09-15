"""Knip adapter -- real ``node <knip>/bin/knip.js --reporter json`` invocation.

Knip's published ``node_modules/.bin/knip`` entry point is a *shell* shim on
POSIX and a ``.cmd`` wrapper on Windows, neither of which can be executed
without a shell.  This adapter therefore invokes the real JavaScript entry point
(``node_modules/knip/bin/knip.js``) with the resolved ``node`` binary -- that is
the form verified to work on Windows.

Knip only covers JS/TS dependency and export hygiene, which is a MEDIUM/LOW
concern; its absence therefore does **not** open an evidence gap for any
HIGH/CRITICAL conclusion.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from ..contracts import ProviderResult, ScanContext
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import Category, RawFinding, Severity
from ..util import run_cmd, which
from .base import CliProvider, classify_cmd_failure, first_lines, parse_version, toolchain_root
from .pmd import coerce_ctx, config_path_failure, explicit_path_error

KNIP_HOME_ENV = "CHM_KNIP_HOME"
NODE_BIN_ENV = "CHM_NODE_BIN"

#: (issue bucket, rule tail, category, severity)
ISSUE_BUCKETS: tuple[tuple[str, str, Category, Severity], ...] = (
    ("dependencies", "UNUSED-DEPENDENCY", Category.DEAD_CODE, Severity.MEDIUM),
    ("devDependencies", "UNUSED-DEV-DEPENDENCY", Category.DEAD_CODE, Severity.MEDIUM),
    ("optionalPeerDependencies", "UNUSED-OPTIONAL-PEER", Category.DEAD_CODE, Severity.LOW),
    ("exports", "UNUSED-EXPORT", Category.DEAD_CODE, Severity.LOW),
    ("types", "UNUSED-TYPE", Category.DEAD_CODE, Severity.LOW),
    ("duplicates", "DUPLICATE-EXPORT", Category.DEAD_CODE, Severity.LOW),
    ("binaries", "UNUSED-BINARY", Category.DEAD_CODE, Severity.LOW),
    ("unlisted", "UNLISTED-DEPENDENCY", Category.DEPENDENCY_GROWTH, Severity.MEDIUM),
    ("unresolved", "UNRESOLVED-IMPORT", Category.DEPENDENCY_GROWTH, Severity.MEDIUM),
    ("catalog", "UNUSED-CATALOG-ENTRY", Category.DEAD_CODE, Severity.LOW),
)


class KnipAdapter(CliProvider):
    """Spec §10 dependency/export hygiene evidence for JS/TS."""

    name = "knip"
    executable = "knip"
    categories = (Category.DEAD_CODE, Category.DEPENDENCY_GROWTH)

    #: Knip only ever produces MEDIUM/LOW -> no HIGH/CRITICAL gap.
    evidence_gap = False

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
        return getattr(tools, "knip", None)

    def _node(self) -> Optional[str]:
        env = os.environ.get(NODE_BIN_ENV)
        if env and Path(env).is_file():
            return env
        return which("node")

    def _knip_js(self, ctx: Optional[ScanContext] = None) -> Optional[Path]:
        effective = self._eff(ctx)
        cfg = self._config(ctx)
        candidates: list[Path] = []
        bin_value = getattr(cfg, "bin", None) if cfg is not None else None
        if bin_value:
            candidates.append(Path(bin_value))
        home_value = getattr(cfg, "home", None) if cfg is not None else None
        if home_value:
            candidates.append(Path(home_value))
        env = os.environ.get(KNIP_HOME_ENV)
        if env:
            candidates.append(Path(env))
        root = toolchain_root(effective)
        if root is not None:
            candidates.append(root / "knip")
            candidates.append(root)

        for cand in candidates:
            for probe in _knip_js_candidates(cand):
                # spawn via `node`, so the entry point must really be JavaScript
                if probe.is_file() and probe.suffix.lower() in (".js", ".mjs", ".cjs"):
                    return probe
        return None

    def _argv_prefix(self, ctx: Optional[ScanContext] = None) -> tuple[Optional[list[str]], Optional[str]]:
        node = self._node()
        if node is None:
            return None, "no 'node' executable found on PATH (set CHM_NODE_BIN to override)"
        knip_js = self._knip_js(ctx)
        if knip_js is None:
            return None, (
                "knip entry point not found (expected "
                "<home>/node_modules/knip/bin/knip.js under config.home, "
                f"${KNIP_HOME_ENV}, or the pinned toolchain)"
            )
        return [node, str(knip_js)], None

    def version(self) -> Optional[str]:
        if self._version_probed:
            return self._version
        self._version_probed = True
        prefix, _ = self._argv_prefix(None)
        if prefix is None:
            return None
        result = run_cmd([*prefix, "--version"], timeout_s=60.0)
        if not result.ok:
            return None
        self._version = parse_version(result.stdout + result.stderr)
        return self._version

    def available(self) -> tuple[bool, Optional[str]]:
        configured_error = explicit_path_error(self._config(None), "knip")
        if configured_error:
            return False, configured_error
        prefix, reason = self._argv_prefix(None)
        if prefix is None:
            return False, reason
        result = run_cmd([*prefix, "--version"], timeout_s=60.0)
        if result.launch_error:
            return False, f"node could not be launched: {result.launch_error}"
        if result.timed_out:
            return False, "knip --version timed out"
        if result.exit_code != 0:
            return False, f"knip --version exited {result.exit_code}: {first_lines(result.stderr)}"
        self._version = parse_version(result.stdout + result.stderr)
        self._version_probed = True
        return True, None

    # -- scope -----------------------------------------------------------

    def _project_root(self, ctx: ScanContext) -> Optional[Path]:
        override = ctx.options.get("knip_dir")
        if override and Path(override).is_dir():
            return Path(override)
        root = Path(ctx.repo_root)
        if (root / "package.json").is_file():
            return root
        # fall back to the shallowest package.json that owns a changed file
        best: Optional[Path] = None
        for cf in ctx.changed_files:
            cur = (root / cf.path).parent
            while cur != root.parent:
                if (cur / "package.json").is_file():
                    if best is None or len(cur.parts) < len(best.parts):
                        best = cur
                    break
                if cur == root:
                    break
                cur = cur.parent
        return best

    def supports(self, ctx: ScanContext) -> bool:
        return self._project_root(ctx) is not None

    # -- scan -------------------------------------------------------------

    def scan(self, ctx: ScanContext) -> ProviderResult:
        self._ctx = coerce_ctx(ctx)
        cfg = self._config(ctx)
        config_failure = config_path_failure(self.name, cfg, "knip")
        if config_failure is not None:
            return config_failure
        prefix, reason = self._argv_prefix(ctx)
        if prefix is None:
            return self._unavailable(
                ToolFailureKind.MISSING.value, reason or "knip not found", gap=False
            )

        project = self._project_root(ctx)
        if project is None:
            return self._unavailable(
                ToolFailureKind.UNSUPPORTED.value,
                "no package.json found; knip only applies to Node projects",
                gap=False,
            )

        timeout_s = float(getattr(cfg, "timeout_s", 300.0) or 300.0)
        argv = [
            *prefix,
            "--reporter",
            "json",
            "--no-progress",
            "--directory",
            str(project),
        ]
        argv += [str(a) for a in (getattr(cfg, "args", None) or [])]

        result = run_cmd(argv, cwd=project, timeout_s=timeout_s)
        command = result.command_line
        artefact = self._write_artefact(ctx, "knip.json", result.stdout) if result.stdout else None

        if result.timed_out or result.launch_error:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=classify_cmd_failure(self.name, result, evidence_gap=False, what="knip"),
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )

        payload, parse_error = self._load_json(result.stdout)
        if payload is None:
            # knip exits 1 when it finds issues in some configurations, and 2 on
            # a real error; only the latter is a tool failure.
            if result.exit_code not in (0, 1):
                return ProviderResult(
                    provider=self.name,
                    status=ToolStatus.UNAVAILABLE,
                    error=classify_cmd_failure(self.name, result, evidence_gap=False, what="knip"),
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
                    detail=f"knip JSON reporter output could not be parsed ({parse_error})",
                    command=command,
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    stderr_excerpt=first_lines(result.stderr),
                    evidence_gap=False,
                ),
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )

        findings, skipped = self._parse_report(payload, ctx, project)
        error: Optional[ToolError] = None
        status = ToolStatus.OK
        if skipped:
            status = ToolStatus.DEGRADED
            error = ToolError(
                provider=self.name,
                kind=ToolFailureKind.PARTIAL_OUTPUT,
                detail=f"{skipped} knip issue entry/entries had an unexpected shape",
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
        start = text.find("{")
        if start < 0:
            return None, "no JSON object found"
        try:
            payload = json.loads(text[start:])
        except json.JSONDecodeError as exc:
            return None, str(exc)
        if not isinstance(payload, dict):
            return None, "top-level JSON value is not an object"
        return payload, None

    def _parse_report(
        self, payload: dict[str, Any], ctx: ScanContext, project: Path
    ) -> tuple[list[RawFinding], int]:
        findings: list[RawFinding] = []
        skipped = 0

        unused_files = payload.get("files")
        if isinstance(unused_files, list):
            for entry in unused_files:
                if not isinstance(entry, str):
                    skipped += 1
                    continue
                findings.append(
                    RawFinding(
                        provider=self.name,
                        rule_id="CHM-JS-KNIP-UNUSED-FILE",
                        message=f"Unused file '{entry}' is not referenced by any entry point",
                        file=self._relativise(entry, project, ctx),
                        start_line=1,
                        end_line=1,
                        category=Category.DEAD_CODE,
                        severity=Severity.LOW,
                        confidence=0.8,
                        detail="knip reported this file as unreferenced",
                        extra={"knip_bucket": "files", "knip_value": entry},
                    )
                )
        elif unused_files is not None:
            skipped += 1

        issues = payload.get("issues")
        if not isinstance(issues, list):
            return findings, skipped

        for issue in issues:
            if not isinstance(issue, dict):
                skipped += 1
                continue
            issue_file = str(issue.get("file") or "")
            for bucket, rule_tail, category, severity in ISSUE_BUCKETS:
                items = issue.get(bucket)
                if items is None:
                    continue
                if not isinstance(items, list):
                    skipped += 1
                    continue
                for item in items:
                    finding = self._make_finding(
                        issue_file, bucket, rule_tail, category, severity, item, project, ctx
                    )
                    if finding is None:
                        skipped += 1
                    else:
                        findings.append(finding)

            enum_members = issue.get("enumMembers")
            if isinstance(enum_members, dict):
                for enum_name, members in enum_members.items():
                    if not isinstance(members, list):
                        skipped += 1
                        continue
                    for item in members:
                        finding = self._make_finding(
                            issue_file,
                            "enumMembers",
                            "UNUSED-ENUM-MEMBER",
                            Category.DEAD_CODE,
                            Severity.LOW,
                            item,
                            project,
                            ctx,
                            symbol_prefix=str(enum_name),
                        )
                        if finding is None:
                            skipped += 1
                        else:
                            findings.append(finding)
            elif enum_members is not None:
                skipped += 1

        return findings, skipped

    def _make_finding(
        self,
        issue_file: str,
        bucket: str,
        rule_tail: str,
        category: Category,
        severity: Severity,
        item: Any,
        project: Path,
        ctx: ScanContext,
        *,
        symbol_prefix: str = "",
    ) -> Optional[RawFinding]:
        """Knip entries are ``{"name", "line", "col", "pos"}``; be defensive."""
        if isinstance(item, str):
            name, line = item, 1
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("file") or "")
            try:
                line = int(item.get("line") or 1)
            except (TypeError, ValueError):
                line = 1
        else:
            return None

        if not issue_file:
            return None
        symbol = f"{symbol_prefix}.{name}" if symbol_prefix and name else (name or None)
        target = self._relativise(issue_file, project, ctx)
        return RawFinding(
            provider=self.name,
            rule_id=f"CHM-JS-KNIP-{rule_tail}",
            message=f"{_HUMAN.get(rule_tail, rule_tail)}: {name or issue_file}",
            file=target,
            start_line=max(line, 1),
            end_line=max(line, 1),
            symbol=symbol,
            category=category,
            severity=severity,
            confidence=0.8,
            detail=f"knip bucket '{bucket}'",
            extra={"knip_bucket": bucket, "knip_value": name},
        )

    @staticmethod
    def _relativise(path: str, project: Path, ctx: ScanContext) -> str:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = project / candidate
        for root in (ctx.repo_root, project):
            try:
                return candidate.resolve().relative_to(Path(root).resolve()).as_posix()
            except (ValueError, OSError):
                continue
        return candidate.as_posix()


_HUMAN = {
    "UNUSED-DEPENDENCY": "Unused dependency",
    "UNUSED-DEV-DEPENDENCY": "Unused devDependency",
    "UNUSED-OPTIONAL-PEER": "Unused optional peer dependency",
    "UNUSED-EXPORT": "Unused export",
    "UNUSED-TYPE": "Unused exported type",
    "DUPLICATE-EXPORT": "Duplicate export",
    "UNUSED-BINARY": "Unused binary",
    "UNLISTED-DEPENDENCY": "Unlisted dependency (imported but not declared)",
    "UNRESOLVED-IMPORT": "Unresolved import",
    "UNUSED-CATALOG-ENTRY": "Unused catalog entry",
    "UNUSED-ENUM-MEMBER": "Unused enum member",
}


def _knip_js_candidates(cand: Path) -> tuple[Path, ...]:
    """Every layout a knip install may plausibly use.

    Only ``.js`` entry points are returned.  ``node_modules/.bin/knip`` is a
    ``/bin/sh`` wrapper (verified on this host) which cannot be spawned without
    a shell, so it is explicitly *not* a candidate.
    """
    pkg_dir = cand / "node_modules" / "knip"
    return (
        cand,
        _bin_from_package_json(pkg_dir),
        pkg_dir / "bin" / "knip.js",
        cand / "knip" / "bin" / "knip.js",
        cand / "bin" / "knip.js",
        cand.parent / "node_modules" / "knip" / "bin" / "knip.js",
    )


def _bin_from_package_json(pkg_dir: Path) -> Path:
    """Honour knip's own ``package.json`` ``bin`` mapping when present."""
    manifest = pkg_dir / "package.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return pkg_dir / "bin" / "knip.js"
    bin_field = data.get("bin")
    if isinstance(bin_field, dict):
        entry = bin_field.get("knip")
        if isinstance(entry, str):
            return pkg_dir / entry
    if isinstance(bin_field, str):
        return pkg_dir / bin_field
    return pkg_dir / "bin" / "knip.js"
