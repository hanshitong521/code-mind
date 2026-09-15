"""Test runner adapter -- real execution of the project's own test command.

The command is never guessed: it comes verbatim from ``config.tools.test.args``
(``["mvn","test"]``, ``["npm","test"]``, ...).  With nothing configured the
adapter reports ``UNAVAILABLE`` / ``DISABLED`` or ``UNSUPPORTED`` and
``evidence_gap=False`` -- a project without tests is a weaker *project*, not a
tooling failure.

A red test run is a ``CRITICAL`` finding and sets ``ctx.options["test_ok"] =
False``, which the repair stage uses to refuse unverified rewrites.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..contracts import ProviderResult, ScanContext
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import Category, RawFinding, Severity
from ..util import run_cmd, which
from .base import CliProvider, first_lines
from .pmd import coerce_ctx

#: lines that usually carry the failure tally, across Maven/Gradle/npm/Jest
_SUMMARY_HINTS = (
    "Tests run:",
    "FAILED",
    "failed",
    "FAIL",
    "failing",
    "AssertionError",
)


class TestRunnerAdapter(CliProvider):
    """Spec §34 -- test evidence for the post-gate and repair stages."""

    name = "test-runner"
    executable = ""
    categories = (Category.ERROR_HANDLING,)

    #: test absence does not invalidate deterministic findings
    evidence_gap = False

    def __init__(self, ctx: Optional[ScanContext] = None) -> None:
        #: see PmdAdapter.__init__ -- lets available() see config
        self._ctx = coerce_ctx(ctx)
        self._resolved: Optional[str] = None

    # -- capability ------------------------------------------------------

    def _eff(self, ctx: Optional[ScanContext]) -> Optional[ScanContext]:
        return ctx if ctx is not None else self._ctx

    def _config(self, ctx: Optional[ScanContext] = None) -> Any:
        effective = self._eff(ctx)
        cfg = getattr(effective, "config", None) if effective is not None else None
        tools = getattr(cfg, "tools", None)
        return getattr(tools, "test", None)

    def _argv(self, ctx: Optional[ScanContext] = None) -> list[str]:
        cfg = self._config(ctx)
        return [str(a) for a in (getattr(cfg, "args", None) or [])]

    def version(self) -> Optional[str]:
        # The runner is whatever the project configured; there is no single
        # version to report, and inventing one would be dishonest.
        return None

    def available(self) -> tuple[bool, Optional[str]]:
        argv = self._argv(None)
        if not argv:
            return False, "no test command configured (config.tools.test.args is empty)"
        resolved = which(argv[0])
        if resolved is None:
            return False, f"test command '{argv[0]}' is not on PATH"
        self._resolved = resolved
        return True, None

    # -- scope -----------------------------------------------------------

    def supports(self, ctx: ScanContext) -> bool:
        cfg = self._config(ctx)
        if cfg is not None and not getattr(cfg, "enabled", True):
            return False
        return bool(self._argv(ctx))

    # -- scan -------------------------------------------------------------

    def scan(self, ctx: ScanContext) -> ProviderResult:
        self._ctx = coerce_ctx(ctx)
        cfg = self._config(ctx)
        if cfg is not None and not getattr(cfg, "enabled", True):
            return self._unavailable(
                ToolFailureKind.DISABLED.value,
                "test runner is disabled in the configuration (tools.test.enabled=false)",
                gap=False,
            )

        argv = self._argv(ctx)
        if not argv:
            return self._unavailable(
                ToolFailureKind.UNSUPPORTED.value,
                "no test command configured (config.tools.test.args is empty)",
                gap=False,
            )

        if which(argv[0]) is None:
            return self._unavailable(
                ToolFailureKind.MISSING.value,
                f"test command '{argv[0]}' is not on PATH",
                gap=False,
            )

        timeout_s = float(getattr(cfg, "timeout_s", 900.0) or 900.0)
        result = run_cmd(argv, cwd=Path(ctx.repo_root), timeout_s=timeout_s)
        command = result.command_line
        combined = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        artefact = self._write_artefact(ctx, "test-runner.log", combined) if combined.strip() else None

        if result.timed_out:
            ctx.options["test_ok"] = False
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.TIMEOUT,
                    detail=f"test command exceeded its {timeout_s:.0f}s budget",
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

        if result.launch_error:
            ctx.options["test_ok"] = False
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.MISSING,
                    detail=f"test command could not be launched: {result.launch_error}",
                    command=command,
                    duration_ms=result.duration_ms,
                    evidence_gap=False,
                ),
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )

        if result.exit_code == 0:
            ctx.options["test_ok"] = True
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.OK,
                findings=[],
                duration_ms=result.duration_ms,
                command=command,
                artefact=artefact,
            )

        ctx.options["test_ok"] = False
        summary = _failure_summary(combined)
        finding = RawFinding(
            provider=self.name,
            rule_id="CHM-TEST-FAIL",
            message=(
                f"Test suite failed (exit {result.exit_code})"
                + (f": {summary}" if summary else "")
            ),
            file=_first_touched_file(ctx),
            start_line=1,
            end_line=1,
            category=Category.ERROR_HANDLING,
            severity=Severity.CRITICAL,
            confidence=1.0,
            detail="the project's own test command reported failures",
            extra={
                "exit_code": result.exit_code,
                "command": command,
                "summary": summary,
            },
        )
        return ProviderResult(
            provider=self.name,
            status=ToolStatus.OK,
            findings=[finding],
            error=None,
            duration_ms=result.duration_ms,
            command=command,
            artefact=artefact,
        )


def _failure_summary(text: str, limit: int = 400) -> str:
    """Pull the most failure-flavoured lines out of the runner's output."""
    hits: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(hint in stripped for hint in _SUMMARY_HINTS):
            hits.append(stripped)
        if len(hits) >= 5:
            break
    summary = " | ".join(hits)
    return summary[:limit]


def _first_touched_file(ctx: ScanContext) -> str:
    for cf in ctx.changed_files:
        if not cf.is_binary:
            return cf.path
    return "(project)"
