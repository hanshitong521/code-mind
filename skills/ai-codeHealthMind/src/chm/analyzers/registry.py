"""Registry of the built-in deterministic analyzers.

The orchestrator asks for ``native_analyzers()`` and appends the result to the
provider list.  Built-ins sit *beside* the external CLI adapters: they emit the
same ``RawFinding`` objects, carry the same ``EvidenceKind.DETERMINISTIC`` kind
and go through the identical dedup / evidence-validation pipeline.

Nothing here touches the filesystem or a process; ordering is fixed so that two
runs over the same change set produce byte-identical provider sequences.
"""

from __future__ import annotations

from typing import Optional

from ..contracts import EvidenceProvider
from .native_java import JavaNativeAnalyzer
from .native_vue import VueNativeAnalyzer

#: Fixed, deterministic provider order.
_NATIVE_NAMES: tuple[str, ...] = ("native-java", "native-vue")


def native_analyzers() -> list[EvidenceProvider]:
    """Return one fresh instance per built-in analyzer, in a stable order."""
    return [JavaNativeAnalyzer(), VueNativeAnalyzer()]


def all_analyzers() -> list[EvidenceProvider]:
    """Alias kept for the orchestrator (same contract as ``native_analyzers``)."""
    return native_analyzers()


def analyzer_named(name: str) -> Optional[EvidenceProvider]:
    """Look up a built-in analyzer by its provider name."""
    if name not in _NATIVE_NAMES:
        return None
    for provider in native_analyzers():
        if provider.name == name:
            return provider
    return None


__all__ = ["native_analyzers", "all_analyzers", "analyzer_named"]
