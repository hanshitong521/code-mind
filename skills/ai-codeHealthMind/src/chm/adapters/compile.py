"""Compile adapter -- real ``javac`` invocation over the changed Java files.

Compilation is *evidence*, not a formality.  SpotBugs cannot run without
bytecode, and a changeset that does not compile must never be scored as if it
did, so the result of this adapter is published on the context:

``ctx.options["classes_dir"]``
    where the freshly compiled classes landed (consumed by SpotBugs); and
``ctx.options["compile_ok"]``
    ``True``/``False`` -- the gate reads this, not the finding list, to decide
    whether the Java evidence chain is trustworthy.

A compile *error* is not an adapter failure: javac did its job and told us the
code is broken.  The status is therefore ``OK`` and a ``CRITICAL`` finding is
emitted.  Only a missing/broken javac or a timeout is reported as
``UNAVAILABLE``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from ..contracts import Language, ProviderResult, ScanContext
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import Category, RawFinding, Severity
from ..util import ensure_dir, run_cmd, which
from .base import CliProvider, first_lines, parse_version, toolchain_root
from .pmd import coerce_ctx

JAVAC_ENV = "CHM_JAVAC_BIN"

#: repo-relative class output directories a build may already have produced
DEFAULT_CLASSPATH_DIRS = (
    "target/classes",
    "build/classes/java/main",
    "out/production/classes",
    "build/classes",
)

#: javac diagnostics, in English and in the localised Chinese JDK this project
#: is developed against.
_DIAG_RE = re.compile(
    r"^(?P<file>[A-Za-z]:[\\/].*?|.*?):(?P<line>\d+):\s*"
    r"(?P<kind>error|错误|warning|警告)\s*:\s*(?P<message>.*)$"
)


class CompileAdapter(CliProvider):
    """Spec §31 -- the Java evidence chain starts here."""

    name = "javac"
    executable = "javac"
    categories = (Category.ERROR_HANDLING,)

    #: without a successful compile, no Java bytecode evidence can exist
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
        return getattr(tools, "compile", None)

    def _javac(self, ctx: Optional[ScanContext] = None) -> Optional[str]:
        import os

        effective = self._eff(ctx)
        cfg = self._config(ctx)
        bin_value = getattr(cfg, "bin", None) if cfg is not None else None
        if bin_value and Path(bin_value).is_file():
            return bin_value
        env = os.environ.get(JAVAC_ENV)
        if env and Path(env).is_file():
            return env

        roots: list[Path] = []
        home = getattr(cfg, "home", None) if cfg is not None else None
        if home:
            roots.append(Path(home))
        # prefer the JDK that ``java`` came from, so javac and java always match
        from .base import java_executable

        java = java_executable()
        if java:
            roots.append(Path(java).parent)
        root = toolchain_root(effective)
        if root is not None:
            roots.append(root)
        return which("javac", roots)

    def version(self) -> Optional[str]:
        if self._version_probed:
            return self._version
        self._version_probed = True
        javac = self._javac(None)
        if javac is None:
            return None
        result = run_cmd([javac, "-version"], timeout_s=60.0)
        if not result.ok:
            return None
        self._version = parse_version(result.stdout + result.stderr)
        return self._version

    def available(self) -> tuple[bool, Optional[str]]:
        javac = self._javac(None)
        if javac is None:
            return False, "no javac found (set JAVA_HOME, CHM_JAVAC_BIN, or put javac on PATH)"
        result = run_cmd([javac, "-version"], timeout_s=60.0)
        if result.launch_error:
            return False, f"javac could not be launched: {result.launch_error}"
        if result.timed_out:
            return False, "javac -version timed out"
        if result.exit_code != 0:
            return False, f"javac -version exited {result.exit_code}: {first_lines(result.stderr)}"
        self._version = parse_version(result.stdout + result.stderr)
        self._version_probed = True
        return True, None

    # -- scope -----------------------------------------------------------

    def _sources(self, ctx: ScanContext) -> list[str]:
        sources = []
        for rel in ctx.paths(Language.JAVA):
            if (Path(ctx.repo_root) / rel).is_file():
                sources.append(rel)
        return sources

    def supports(self, ctx: ScanContext) -> bool:
        return bool(self._sources(ctx))

    def _classpath(self, ctx: ScanContext) -> Optional[str]:
        """Explicit ``-cp`` from config wins; otherwise reuse an existing build."""
        cfg = self._config(ctx)
        args = [str(a) for a in (getattr(cfg, "args", None) or [])]
        for i, arg in enumerate(args):
            if arg in ("-cp", "-classpath", "--class-path") and i + 1 < len(args):
                return args[i + 1]
            if arg.startswith("-cp=") or arg.startswith("--class-path="):
                return arg.split("=", 1)[1]
        override = ctx.options.get("classpath")
        if override:
            return str(override)
        existing = [
            str(Path(ctx.repo_root) / rel)
            for rel in DEFAULT_CLASSPATH_DIRS
            if (Path(ctx.repo_root) / rel).is_dir()
        ]
        if existing:
            import os

            return os.pathsep.join(existing)
        return None

    # -- scan -------------------------------------------------------------

    def scan(self, ctx: ScanContext) -> ProviderResult:
        self._ctx = coerce_ctx(ctx)
        cfg = self._config(ctx)
        javac = self._javac(ctx)
        if javac is None:
            ctx.options["compile_ok"] = False
            return self._unavailable(
                ToolFailureKind.MISSING.value,
                "no javac found (set JAVA_HOME, CHM_JAVAC_BIN, or put javac on PATH)",
                gap=True,
            )

        sources = self._sources(ctx)
        if not sources:
            return self._unavailable(
                ToolFailureKind.UNSUPPORTED.value,
                "no changed Java files to compile",
                gap=False,
            )

        if ctx.cache_dir is None:
            ctx.options["compile_ok"] = False
            return self._unavailable(
                ToolFailureKind.CONFIG.value,
                "no cache directory available for compiled classes",
                gap=True,
            )

        classes_dir = ensure_dir(Path(ctx.cache_dir) / "classes")
        timeout_s = float(getattr(cfg, "timeout_s", 300.0) or 300.0)

        argv = [
            javac,
            "-encoding",
            "UTF-8",
            "-source",
            "8",
            "-target",
            "8",
            "-d",
            str(classes_dir),
        ]
        classpath = self._classpath(ctx)
        if classpath:
            argv += ["-cp", classpath]
        argv += [str(a) for a in (getattr(cfg, "args", None) or [])]
        argv += [str(Path(ctx.repo_root) / rel) for rel in sources]

        result = run_cmd(argv, cwd=Path(ctx.repo_root), timeout_s=timeout_s)
        command = result.command_line
        log = self._write_artefact(
            ctx,
            "javac.log",
            (result.stdout or "") + ("\n--- stderr ---\n" + result.stderr if result.stderr else ""),
        )

        if result.timed_out or result.launch_error:
            ctx.options["compile_ok"] = False
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=self.name,
                    kind=(
                        ToolFailureKind.TIMEOUT if result.timed_out else ToolFailureKind.MISSING
                    ),
                    detail=(
                        "javac exceeded its time budget"
                        if result.timed_out
                        else f"javac could not be launched: {result.launch_error}"
                    ),
                    command=command,
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    stderr_excerpt=first_lines(result.stderr),
                    evidence_gap=True,
                ),
                duration_ms=result.duration_ms,
                command=command,
                artefact=log,
            )

        if result.exit_code == 0:
            ctx.options["classes_dir"] = str(classes_dir)
            ctx.options["compile_ok"] = True
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.OK,
                findings=[],
                duration_ms=result.duration_ms,
                command=command,
                version=self.version(),
                artefact=log,
            )

        # javac worked; the code does not compile.  That is a CRITICAL finding,
        # not a tool failure.
        ctx.options["compile_ok"] = False
        findings = self._parse_diagnostics(result.stderr, result.stdout, ctx)
        if not findings:
            findings = [
                RawFinding(
                    provider=self.name,
                    rule_id="CHM-JAVA-COMPILE-FAIL",
                    message=(
                        "javac failed without a parseable diagnostic: "
                        f"{first_lines(result.stderr or result.stdout) or 'no output'}"
                    ),
                    file=sources[0],
                    start_line=1,
                    end_line=1,
                    category=Category.ERROR_HANDLING,
                    severity=Severity.CRITICAL,
                    confidence=1.0,
                    detail="compilation failed",
                    extra={"exit_code": result.exit_code, "stderr": _clip(result.stderr)},
                )
            ]

        return ProviderResult(
            provider=self.name,
            status=ToolStatus.OK,
            findings=findings,
            error=None,
            duration_ms=result.duration_ms,
            command=command,
            version=self.version(),
            artefact=log,
        )

    def _parse_diagnostics(
        self, stderr: str, stdout: str, ctx: ScanContext
    ) -> list[RawFinding]:
        findings: list[RawFinding] = []
        seen: set[tuple[str, int, str]] = set()
        for line in (stderr or "").splitlines() + (stdout or "").splitlines():
            match = _DIAG_RE.match(line.strip())
            if match is None:
                continue
            kind = match.group("kind")
            if kind in ("warning", "警告"):
                continue
            path = match.group("file")
            try:
                lineno = int(match.group("line"))
            except (TypeError, ValueError):
                lineno = 1
            message = match.group("message").strip()
            key = (path, lineno, message)
            if key in seen:
                continue
            seen.add(key)

            findings.append(
                RawFinding(
                    provider=self.name,
                    rule_id="CHM-JAVA-COMPILE-FAIL",
                    message=f"Java compilation error: {message}",
                    file=self._relativise(path, ctx),
                    start_line=max(lineno, 1),
                    end_line=max(lineno, 1),
                    category=Category.ERROR_HANDLING,
                    severity=Severity.CRITICAL,
                    confidence=1.0,
                    detail="javac reported a compilation error",
                    extra={"exit_code": 1, "javac_message": message},
                )
            )
        return findings

    @staticmethod
    def _relativise(path: str, ctx: ScanContext) -> str:
        try:
            return Path(path).resolve().relative_to(Path(ctx.repo_root).resolve()).as_posix()
        except (ValueError, OSError):
            return Path(path).as_posix()


def _clip(text: str, limit: int = 2000) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"
