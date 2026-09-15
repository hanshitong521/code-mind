"""Toolchain probe -- the honest answer to "what can we actually run here?".

Every probe **executes the real tool**.  Nothing is inferred from the presence
of a file on disk, because a jar that exists but whose JVM cannot start it is
exactly the kind of false confidence this project exists to prevent (spec §29).

The probe is also the single place that knows the canonical tool order, so the
report always lists tools in the same sequence and two runs over the same host
produce the same output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..contracts import EvidenceProvider, ReviewMode, ScanContext
from .base import java_executable, toolchain_root
from .compile import CompileAdapter
from .cpd import CpdAdapter
from .knip import KnipAdapter
from .openrewrite import OpenRewriteAdapter
from .pmd import PmdAdapter
from .semgrep import SemgrepAdapter
from .spotbugs import SpotBugsAdapter
from .testrunner import TestRunnerAdapter

#: Canonical probe order, expressed in **provider names** (``EvidenceProvider.name``)
#: so the report, the orchestrator's ``PROVIDER_ORDER`` and the findings all agree.
#: The corresponding config keys are native/compile/pmd/cpd/spotbugs/semgrep/
#: knip/openrewrite/test.
PROBE_ORDER = (
    "native",
    "javac",
    "pmd",
    "cpd",
    "spotbugs",
    "semgrep",
    "knip",
    "openrewrite",
    "test-runner",
)


@dataclass
class ToolProbe:
    """One tool's real, observed availability."""

    name: str
    available: bool
    version: Optional[str] = None
    path: Optional[str] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "version": self.version,
            "path": self.path,
            "reason": self.reason,
        }


def _context_for(config: Any, ctx: Optional[ScanContext]) -> ScanContext:
    """Reuse the caller's context, or synthesise one that carries the config.

    ``available()`` takes no ctx by contract, so adapters are constructed with
    this context to keep config-driven tool locations reachable.
    """
    if ctx is not None:
        return ctx
    return ScanContext(
        repo_root=Path.cwd(),
        mode=ReviewMode.REPO,
        config=config,
    )


def _probe_via(provider: EvidenceProvider, path: Optional[str]) -> ToolProbe:
    """Run a provider's real ``available()`` and ``version()``."""
    try:
        available, reason = provider.available()
    except Exception as exc:  # a probe must never take the whole report down
        return ToolProbe(
            name=provider.name,
            available=False,
            version=None,
            path=path,
            reason=f"probe raised {type(exc).__name__}: {exc}",
        )
    version: Optional[str] = None
    if available:
        try:
            version = provider.version()
        except Exception as exc:
            version = None
            reason = f"version probe raised {type(exc).__name__}: {exc}"
    return ToolProbe(
        name=provider.name,
        available=available,
        version=version,
        path=path,
        reason=reason,
    )


def _native_probe() -> ToolProbe:
    """The built-in analyzer needs no external process -- report it honestly."""
    from .. import __version__

    return ToolProbe(
        name="native",
        available=True,
        version=__version__,
        path="chm.analyzers (in-process)",
        reason=None,
    )


def _compile_probe(ctx: ScanContext) -> ToolProbe:
    adapter = CompileAdapter(ctx)
    probe = _probe_via(adapter, adapter._javac(ctx))
    return probe


def _pmd_probe(ctx: ScanContext) -> ToolProbe:
    adapter = PmdAdapter(ctx)
    home = _pmd_home(ctx)
    probe = _probe_via(adapter, str(home) if home else None)
    if not probe.available and probe.reason and not probe.path:
        java = java_executable()
        probe.path = java
    return probe


def _cpd_probe(ctx: ScanContext) -> ToolProbe:
    adapter = CpdAdapter(ctx)
    home = _pmd_home(ctx)
    return _probe_via(adapter, str(home) if home else None)


def _pmd_home(ctx: ScanContext) -> Optional[Path]:
    from .pmd import pmd_home

    cfg = getattr(ctx.config, "tools", None)
    return pmd_home(ctx, getattr(cfg, "pmd", None))


def _spotbugs_probe(ctx: ScanContext) -> ToolProbe:
    adapter = SpotBugsAdapter(ctx)
    jar = adapter._jar(ctx)
    return _probe_via(adapter, str(jar) if jar else None)


def _semgrep_probe(ctx: ScanContext) -> ToolProbe:
    adapter = SemgrepAdapter(ctx)
    return _probe_via(adapter, adapter._binary(ctx))


def _knip_probe(ctx: ScanContext) -> ToolProbe:
    adapter = KnipAdapter(ctx)
    entry = adapter._knip_js(ctx)
    probe = _probe_via(adapter, str(entry) if entry else None)
    if not probe.available and probe.reason and not probe.path:
        probe.path = adapter._node()
    return probe


def _openrewrite_probe(ctx: ScanContext) -> ToolProbe:
    adapter = OpenRewriteAdapter(ctx)
    cli = adapter._cli(ctx)
    return _probe_via(adapter, cli or adapter._maven())


def _test_probe(ctx: ScanContext) -> ToolProbe:
    adapter = TestRunnerAdapter(ctx)
    argv = adapter._argv(ctx)
    from ..util import which

    resolved = which(argv[0]) if argv else None
    probe = _probe_via(adapter, resolved)
    if not probe.available and not probe.reason:
        probe.reason = "test runner is not enabled"
    return probe


def probe_all(ctx: Optional[ScanContext], config: Any) -> list[ToolProbe]:
    """Probe every known tool, in the canonical order, by really running it."""
    effective = _context_for(config, ctx)
    # make sure the injected context really carries the config
    if getattr(effective, "config", None) is None:
        effective.config = config

    probes: list[ToolProbe] = [
        _native_probe(),
        _compile_probe(effective),
        _pmd_probe(effective),
        _cpd_probe(effective),
        _spotbugs_probe(effective),
        _semgrep_probe(effective),
        _knip_probe(effective),
        _openrewrite_probe(effective),
        _test_probe(effective),
    ]

    # keep the declared order even if a helper ever returns out of sequence
    by_name = {p.name: p for p in probes}
    return [by_name[name] for name in PROBE_ORDER if name in by_name]


def toolchain_summary(config: Any, ctx: Optional[ScanContext] = None) -> dict[str, Any]:
    """Small helper the CLI can render: probes plus the resolved roots."""
    probes = probe_all(ctx, config)
    root = toolchain_root(_context_for(config, ctx))
    return {
        "toolchain_root": str(root) if root else None,
        "java": java_executable(),
        "env": {
            key: os.environ.get(key)
            for key in (
                "CHM_TOOLCHAIN_ROOT",
                "CHM_PMD_HOME",
                "CHM_SPOTBUGS_HOME",
                "CHM_KNIP_HOME",
                "CHM_NODE_BIN",
                "CHM_JAVAC_BIN",
                "CHM_SEMGREP_BIN",
                "CHM_OPENREWRITE_BIN",
                "CHM_MVN_BIN",
            )
            if os.environ.get(key)
        },
        "tools": [p.to_dict() for p in probes],
    }
