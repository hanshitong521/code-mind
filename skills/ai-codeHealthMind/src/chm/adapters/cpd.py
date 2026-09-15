"""CPD adapter -- PMD's copy/paste detector, run as a real CLI.

CPD 6.55 ships inside the PMD distribution (``net.sourceforge.pmd.cpd.CPD``).
Two facts learned from the genuine ``--help`` output, both of which shaped this
adapter:

* there is **no** ``-r``/report-file option -- the XML goes to *stdout*; and
* there is **no** ``--version`` option, so availability is proven by a real
  ``--help`` invocation and the version string is taken from the PMD
  distribution that contains CPD.

Supported languages are taken from CPD's own list; ``vue`` is *not* one of
them, so Vue files are honestly reported as unsupported rather than silently
dropped.
"""

from __future__ import annotations

import locale
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

from ..contracts import Language, ProviderResult, ScanContext
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import Category, RawFinding, Severity
from ..util import run_cmd
from .base import CliProvider, classify_cmd_failure, first_lines, parse_version
from .pmd import (
    CPD_MAIN,
    coerce_ctx,
    config_path_failure,
    explicit_path_error,
    java_classpath_prefix,
    local_name,
    parse_xml,
)

#: CPD language token per CHM language, from CPD's real ``--help`` output.
CPD_LANGUAGE: dict[Language, str] = {
    Language.JAVA: "java",
    Language.JAVASCRIPT: "ecmascript",
    Language.TYPESCRIPT: "ecmascript",
}

#: rule-id language segment
LANG_TOKEN: dict[Language, str] = {
    Language.JAVA: "JAVA",
    Language.JAVASCRIPT: "JS",
    Language.TYPESCRIPT: "TS",
    Language.VUE: "VUE",
}

#: duplication above this token count is worth blocking on
HIGH_TOKEN_THRESHOLD = 300

#: ``--skip-lexical-errors`` makes CPD log one of these per unreadable file:
#: ``Skipping <path>. Reason: Lexical error in file <path> at line 1, column 1 ...``
_LEXICAL_SKIP_RE = re.compile(r"Skipping\s+(?P<path>.+?)\.\s+Reason:\s*(?P<reason>.*)")


_JVM_ENCODING_CACHE: dict[str, str] = {}


def filelist_encoding(java: Optional[str] = None) -> str:
    """Charset CPD uses when reading ``--filelist``.

    CPD reads the list with the **JVM's** default charset, not with
    ``--encoding`` (which only applies to source files).  On a zh_CN Windows
    host that is GBK, so a UTF-8 file list aborts the run at
    ``addFilesFromFilelist`` on the first non-ASCII path.  Python's own locale
    is not a reliable proxy for the JVM's charset, so we ask the JVM itself and
    cache the answer.
    """
    if java is None:
        from .base import java_executable

        java = java_executable()
    if java is None:
        return locale.getpreferredencoding(False) or "utf-8"
    cached = _JVM_ENCODING_CACHE.get(java)
    if cached is not None:
        return cached

    encoding = locale.getpreferredencoding(False) or "utf-8"
    result = run_cmd([java, "-XshowSettings:properties", "-version"], timeout_s=60.0)
    if not result.launch_error and not result.timed_out:
        match = re.search(
            r"file\.encoding\s*=\s*(\S+)", (result.stdout or "") + (result.stderr or "")
        )
        if match:
            encoding = match.group(1).strip()
    _JVM_ENCODING_CACHE[java] = encoding
    return encoding


def _parse_lexical_skips(stderr: str) -> list[str]:
    """Names of files CPD could not tokenise and therefore skipped.

    CPD writes these to stderr with the *console* encoding, so on a GBK console
    the path may contain replacement characters.  We therefore keep the raw text
    rather than pretending it is a clean path, and callers only report counts
    plus a best-effort excerpt.
    """
    skips: list[str] = []
    for line in (stderr or "").splitlines():
        match = _LEXICAL_SKIP_RE.search(line.strip())
        if match is None:
            continue
        path = match.group("path").strip()
        if path and path not in skips:
            skips.append(path)
    return skips


class CpdAdapter(CliProvider):
    """Spec §10 DUPLICATION evidence, backed by the real CPD CLI."""

    name = "cpd"
    executable = "java"
    categories = (Category.DUPLICATION,)

    #: Duplication findings we emit are MEDIUM/HIGH; CPD absence is a real gap
    #: for the HIGH (>= 300 token) duplication conclusion.
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
        return getattr(tools, "cpd", None)

    def _prefix(self, ctx: Optional[ScanContext] = None) -> tuple[Optional[list[str]], Optional[str]]:
        return java_classpath_prefix(self._eff(ctx), self._config(ctx), CPD_MAIN)

    def _probe_help(self, ctx: Optional[ScanContext] = None):
        prefix, reason = self._prefix(ctx)
        if prefix is None:
            return None, reason
        # CPD 6.55 has no --version flag; --help is the real, working probe.
        result = run_cmd([*prefix, "--help"], timeout_s=60.0)
        return result, None

    def version(self) -> Optional[str]:
        if self._version_probed:
            return self._version
        self._version_probed = True
        from .pmd import PMD_MAIN

        prefix, _ = java_classpath_prefix(None, self._config(None), PMD_MAIN)
        if prefix is None:
            return None
        result = run_cmd([*prefix, "--version"], timeout_s=60.0)
        if not result.ok:
            return None
        self._version = parse_version(result.stdout + result.stderr)
        return self._version

    def available(self) -> tuple[bool, Optional[str]]:
        configured_error = explicit_path_error(self._config(None), "cpd")
        if configured_error:
            return False, configured_error
        result, reason = self._probe_help(None)
        if result is None:
            return False, reason
        if result.launch_error:
            return False, f"java could not be launched: {result.launch_error}"
        if result.timed_out:
            return False, "CPD --help timed out"
        # jcommander prints usage to stdout/stderr and exits 0 for --help.
        if result.exit_code != 0 or "Usage: cpd" not in (result.stdout + result.stderr):
            return False, (
                f"CPD did not respond to --help (exit {result.exit_code}): "
                f"{first_lines(result.stderr or result.stdout)}"
            )
        self._version = self.version()
        return True, None

    # -- scope -----------------------------------------------------------

    def _targets(self, ctx: ScanContext) -> tuple[dict[str, list[str]], list[Language]]:
        """Group files by the CPD language token that can handle them.

        In repo scope the groups only record *which* languages are present; the
        actual scan is driven by ``--dir <repo_root>``.
        """
        grouped: dict[str, list[str]] = {}
        skipped: list[Language] = []
        repo_scope = str(ctx.options.get("cpd_scope", "")).lower() == "repo"

        if repo_scope:
            for cf in ctx.changed_files:
                token = CPD_LANGUAGE.get(cf.language)
                if token is None:
                    continue
                grouped.setdefault(token, [])
            return grouped, skipped

        for cf in ctx.changed_files:
            if cf.is_binary or cf.is_generated:
                continue
            token = CPD_LANGUAGE.get(cf.language)
            if token is None:
                if cf.language in (Language.VUE, Language.TYPESCRIPT):
                    skipped.append(cf.language)
                continue
            p = Path(ctx.repo_root) / cf.path
            if p.is_file():
                grouped.setdefault(token, []).append(str(p))
        return grouped, skipped

    def supports(self, ctx: ScanContext) -> bool:
        grouped, _ = self._targets(ctx)
        return any(grouped.values())

    #: Windows caps a process command line at 32767 chars; stay well clear.
    MAX_ARGV_PATH_CHARS = 20000

    def _file_targets(
        self, paths: list[str], token: str, out_dir: Optional[Path]
    ) -> tuple[list[str], Optional[ToolError]]:
        """Decide how to hand an explicit file set to CPD.

        ``--files`` is deprecated in 6.55 but is the only form that survives
        non-ASCII paths: CPD reads ``--filelist`` with the *JVM* default charset
        (GBK here) rather than with ``--encoding``, so a UTF-8 file list aborts
        the entire run at ``addFilesFromFilelist``.  We therefore prefer
        ``--files`` and fall back to ``--filelist`` -- written in the platform
        encoding -- only when the command line would become too long.
        """
        budget = sum(len(p) + 1 for p in paths)
        if budget <= self.MAX_ARGV_PATH_CHARS:
            return ["--files", *paths], None

        if out_dir is None:
            return [], ToolError(
                provider=self.name,
                kind=ToolFailureKind.CONFIG,
                detail=(
                    f"no cache directory available to stage the CPD file list for {token}: "
                    f"{len(paths)} files exceed the command-line budget"
                ),
                evidence_gap=True,
            )
        filelist = out_dir / f"cpd-filelist-{token}.txt"
        try:
            filelist.write_text("\n".join(paths), encoding=filelist_encoding())
        except (OSError, UnicodeEncodeError) as exc:
            return [], ToolError(
                provider=self.name,
                kind=ToolFailureKind.CONFIG,
                detail=f"could not write CPD file list for {token}: {exc}",
                evidence_gap=True,
            )
        return ["--filelist", str(filelist)], None

    # -- scan -------------------------------------------------------------

    def scan(self, ctx: ScanContext) -> ProviderResult:
        self._ctx = coerce_ctx(ctx)
        cfg = self._config(ctx)
        config_failure = config_path_failure(self.name, cfg, "cpd")
        if config_failure is not None:
            return config_failure
        prefix, reason = self._prefix(ctx)
        if prefix is None:
            return self._unavailable(
                ToolFailureKind.MISSING.value, reason or "CPD not found", gap=True
            )

        grouped, skipped_languages = self._targets(ctx)
        if not grouped:
            detail = "no CPD-supported source files in this changeset"
            if skipped_languages:
                names = ", ".join(sorted({lang.value for lang in skipped_languages}))
                detail += f" (CPD 6.55 has no tokenizer for: {names})"
            return self._unavailable(ToolFailureKind.UNSUPPORTED.value, detail, gap=False)

        timeout_s = float(getattr(cfg, "timeout_s", 300.0) or 300.0)
        min_tokens = int(getattr(getattr(ctx, "config", None), "duplication_min_tokens", 100) or 100)

        cache_dir = Path(ctx.cache_dir) if ctx.cache_dir is not None else None
        out_dir = (cache_dir / "tmp") if cache_dir is not None else None
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)

        all_findings: list[RawFinding] = []
        commands: list[str] = []
        artefacts: list[str] = []
        failures: list[ToolError] = []
        worst_status = ToolStatus.OK
        total_ms = 0
        repo_scope = str(ctx.options.get("cpd_scope", "")).lower() == "repo"

        for token, paths in sorted(grouped.items()):
            argv = [
                *prefix,
                "--minimum-tokens",
                str(min_tokens),
                "--language",
                token,
                "--format",
                "xml",
                "--fail-on-violation",
                "false",
                # CPD's default encoding on this host is GBK, which mangles UTF-8
                # sources into replacement characters and aborts the run.
                "--encoding",
                "UTF-8",
                # One undecodable/unlexable file must never take down the whole
                # scan; skipped files are surfaced as PARTIAL_OUTPUT below.
                "--skip-lexical-errors",
            ]
            if repo_scope:
                argv += ["--dir", str(Path(ctx.repo_root))]
            else:
                target_argv, target_error = self._file_targets(paths, token, out_dir)
                if target_error is not None:
                    failures.append(target_error)
                    continue
                argv += target_argv
            argv += [str(a) for a in (getattr(cfg, "args", None) or [])]

            result = run_cmd(argv, cwd=Path(ctx.repo_root), timeout_s=timeout_s)
            total_ms += result.duration_ms
            commands.append(result.command_line)

            xml_text = result.stdout
            if xml_text.strip():
                artefacts.append(self._write_artefact(ctx, f"cpd-{token}.xml", xml_text) or "")

            # Files CPD skipped because it could not tokenise them.  These are a
            # partial-output condition, never a silent omission (spec §16).
            lexical_skips = _parse_lexical_skips(result.stderr)
            if lexical_skips:
                failures.append(
                    ToolError(
                        provider=self.name,
                        kind=ToolFailureKind.PARTIAL_OUTPUT,
                        detail=(
                            f"CPD ({token}) skipped {len(lexical_skips)} file(s) that could "
                            "not be tokenised: "
                            + "; ".join(lexical_skips[:5])
                            + (" ..." if len(lexical_skips) > 5 else "")
                        ),
                        command=result.command_line,
                        exit_code=result.exit_code,
                        duration_ms=result.duration_ms,
                        evidence_gap=False,
                    )
                )
                if worst_status is ToolStatus.OK:
                    worst_status = ToolStatus.DEGRADED

            if result.timed_out or result.launch_error or result.exit_code not in (0, 4):
                failures.append(
                    classify_cmd_failure(
                        self.name, result, evidence_gap=True, what=f"CPD ({token})"
                    )
                )
                worst_status = ToolStatus.UNAVAILABLE
                continue

            root, parse_error = parse_xml(xml_text)
            if root is None:
                failures.append(
                    ToolError(
                        provider=self.name,
                        kind=ToolFailureKind.MALFORMED_OUTPUT,
                        detail=f"CPD report for {token} could not be parsed ({parse_error})",
                        command=result.command_line,
                        exit_code=result.exit_code,
                        duration_ms=result.duration_ms,
                        stderr_excerpt=first_lines(result.stderr),
                        evidence_gap=True,
                    )
                )
                if worst_status is ToolStatus.OK:
                    worst_status = ToolStatus.DEGRADED
                continue

            found, unreadable = self._parse_duplications(root, ctx, token)
            all_findings.extend(found)
            if unreadable:
                failures.append(
                    ToolError(
                        provider=self.name,
                        kind=ToolFailureKind.PARTIAL_OUTPUT,
                        detail=(
                            f"{unreadable} CPD duplication element(s) for {token} "
                            "were unreadable"
                        ),
                        evidence_gap=False,
                    )
                )
                if worst_status is ToolStatus.OK:
                    worst_status = ToolStatus.DEGRADED

        if not all_findings and worst_status is ToolStatus.UNAVAILABLE and failures:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=failures[0],
                duration_ms=total_ms,
                command=" && ".join(commands) or None,
                version=self.version(),
                artefact=artefacts[0] if artefacts else None,
            )

        error = failures[0] if failures else None
        return ProviderResult(
            provider=self.name,
            status=worst_status,
            findings=all_findings,
            error=error,
            duration_ms=total_ms,
            command=" && ".join(commands) or None,
            version=self.version(),
            artefact=next((a for a in artefacts if a), None),
        )

    def _parse_duplications(
        self, root: ET.Element, ctx: ScanContext, token: str
    ) -> tuple[list[RawFinding], int]:
        findings: list[RawFinding] = []
        skipped = 0
        lang = next((k for k, v in CPD_LANGUAGE.items() if v == token), Language.OTHER)
        lang_token = LANG_TOKEN.get(lang, "GEN")

        for dup in root:
            if local_name(dup.tag) != "duplication":
                continue
            try:
                tokens = int(dup.get("tokens") or 0)
                lines = int(dup.get("lines") or 0)
            except (TypeError, ValueError):
                tokens, lines = 0, 0

            occurrences: list[dict[str, Any]] = []
            for child in dup:
                if local_name(child.tag) != "file":
                    continue
                path = child.get("path") or ""
                if not path:
                    continue
                try:
                    line = int(child.get("line") or 1)
                except (TypeError, ValueError):
                    line = 1
                occurrences.append({"file": self._relativise(path, ctx), "line": line})

            if not occurrences:
                skipped += 1
                continue

            severity = Severity.HIGH if tokens >= HIGH_TOKEN_THRESHOLD else Severity.MEDIUM
            first = occurrences[0]
            others = ", ".join(f"{o['file']}:{o['line']}" for o in occurrences[1:])
            findings.append(
                RawFinding(
                    provider=self.name,
                    rule_id=f"CHM-{lang_token}-CPD-DUP",
                    message=(
                        f"Duplicated block of {tokens} tokens / {lines} lines "
                        f"also appears in {others or 'no other file'}"
                    ),
                    file=first["file"],
                    start_line=first["line"],
                    end_line=first["line"] + max(lines - 1, 0),
                    category=Category.DUPLICATION,
                    severity=severity,
                    confidence=0.95,
                    detail=f"CPD {token} duplication, {len(occurrences)} occurrence(s)",
                    extra={
                        "tokens": tokens,
                        "lines": lines,
                        "occurrences": occurrences,
                        "cpd_language": token,
                    },
                )
            )
        return findings, skipped

    @staticmethod
    def _relativise(path: str, ctx: ScanContext) -> str:
        try:
            return Path(path).resolve().relative_to(Path(ctx.repo_root).resolve()).as_posix()
        except (ValueError, OSError):
            return Path(path).as_posix()
