"""Adapter base utilities.

Adapters are thin, honest wrappers around real external tools.  They are the
*only* place in the codebase allowed to talk to a process outside Python, and
they never invent results: if the tool is absent, timed out or produced
garbage, they say so (spec §28, §29, §31).
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from ..contracts import EvidenceProvider, ProviderResult, ScanContext
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import RawFinding
from ..util import CmdResult, which

#: Where the repo keeps its pinned toolchain (`.tools/codehealth/...`).
TOOLCHAIN_ROOT_ENV = "CHM_TOOLCHAIN_ROOT"
DEFAULT_TOOLCHAIN_RELATIVE = Path(".tools") / "codehealth"


def toolchain_root(ctx: Optional[ScanContext] = None) -> Optional[Path]:
    """Locate the pinned toolchain directory, if it exists."""
    env = os.environ.get(TOOLCHAIN_ROOT_ENV)
    if env and Path(env).is_dir():
        return Path(env)
    roots: list[Path] = []
    if ctx is not None:
        roots.append(Path(ctx.repo_root))
    roots.append(Path.cwd())
    for root in roots:
        for candidate in (root, *root.parents):
            probe = candidate / DEFAULT_TOOLCHAIN_RELATIVE
            if probe.is_dir():
                return probe
    return None


def java_home() -> Optional[Path]:
    for key in ("CHM_JAVA_HOME", "JAVA_HOME"):
        val = os.environ.get(key)
        if val and Path(val).is_dir():
            return Path(val)
    # fall back to a java on PATH
    java = which("java")
    if java:
        return Path(java).parent.parent
    return None


def java_executable() -> Optional[str]:
    home = java_home()
    if home:
        for name in ("java.exe", "java"):
            cand = home / "bin" / name
            if cand.is_file():
                return str(cand)
    return which("java")


@dataclass
class CommandPlan:
    """A fully-resolved command that is about to be executed.

    Keeping this explicit lets the observability ledger record the *real*
    command line, which is what the spec demands in reports.
    """

    argv: list[str]
    cwd: Optional[Path] = None
    env: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.env is None:
            self.env = {}

    @property
    def command_line(self) -> str:
        from ..util import _quote

        return " ".join(_quote(a) for a in self.argv)


def classpath_from_dir(lib_dir: Path) -> Optional[str]:
    """Build a ``;``/``:`` separated classpath from a directory of jars."""
    if not lib_dir.is_dir():
        return None
    jars = sorted(str(p) for p in lib_dir.glob("*.jar"))
    if not jars:
        return None
    return os.pathsep.join(jars)


def classify_cmd_failure(
    provider: str,
    result: CmdResult,
    *,
    evidence_gap: bool = False,
    what: str = "tool",
) -> ToolError:
    """Translate a failed :class:`CmdResult` into a typed ToolError."""
    if result.launch_error:
        kind = ToolFailureKind.MISSING
        detail = f"{what} could not be launched: {result.launch_error}"
        gap = True
    elif result.timed_out:
        kind = ToolFailureKind.TIMEOUT
        detail = f"{what} exceeded its time budget"
        gap = True
    else:
        kind = ToolFailureKind.NONZERO_EXIT
        detail = f"{what} exited with code {result.exit_code}"
        gap = evidence_gap
    return ToolError(
        provider=provider,
        kind=kind,
        detail=detail,
        command=result.command_line,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        stderr_excerpt=_excerpt(result.stderr),
        evidence_gap=gap,
    )


def _excerpt(text: str, limit: int = 800) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [{len(text) - limit} more chars]"


def first_lines(text: str, n: int = 3) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return " / ".join(lines[:n])


def parse_version(text: str) -> Optional[str]:
    """Pull the first ``X.Y[.Z]`` looking token out of a version banner."""
    m = re.search(r"(\d+\.\d+(?:\.\d+)?(?:[-.\w]+)?)", text or "")
    return m.group(1) if m else None


class CliProvider(EvidenceProvider):
    """Common plumbing for adapters that shell out to a real executable."""

    #: executable name looked up on PATH
    executable: str = ""
    #: extra search roots (toolchain home / bin) resolved per-run
    executable_roots: Sequence[str] = ()

    def resolve_executable(self, ctx: Optional[ScanContext] = None) -> Optional[str]:
        candidates: list[Path] = []
        root = toolchain_root(ctx)
        if root is not None:
            for rel in self.executable_roots:
                candidates.append(root / rel)
        found = which(self.executable, candidates)
        return found

    def _tool_missing(self, detail: str) -> ProviderResult:
        return ProviderResult(
            provider=self.name,
            status=ToolStatus.UNAVAILABLE,
            error=ToolError(
                provider=self.name,
                kind=ToolFailureKind.MISSING,
                detail=detail,
                evidence_gap=True,
            ),
        )

    def _write_artefact(self, ctx: ScanContext, filename: str, content: str) -> Optional[str]:
        if ctx.cache_dir is None:
            return None
        from ..util import ensure_dir

        target = ensure_dir(Path(ctx.cache_dir) / "artefacts") / filename
        try:
            target.write_text(content, encoding="utf-8")
        except OSError:
            return None
        return str(target)

    def _paths_for(self, ctx: ScanContext, languages: Iterable[str]) -> list[str]:
        wanted = {str(x).lower() for x in languages}
        return [
            cf.path
            for cf in ctx.changed_files
            if not cf.is_binary and cf.language.value in wanted
        ]
