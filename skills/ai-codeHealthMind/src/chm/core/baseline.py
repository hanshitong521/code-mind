"""Baseline capture and diffing (spec §13).

The governing principle is one sentence: **carrying historical debt is
allowed, adding new debt is not.**  That only works if the engine can tell the
two apart, so a baseline records a stable identity for every finding it saw
and this module classifies the next run against it.

The baseline file is JSON -- never YAML -- so no parser (and no dependency)
can change its meaning between runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..schema import Category, Finding, Location, Severity
from ..util import percent, read_json, sha256_text, write_json
from .score import score_findings

BASELINE_SCHEMA_VERSION = 1

_COMPLEXITY_CATEGORIES = frozenset(
    {Category.COMPLEXITY, Category.LARGE_METHOD, Category.LARGE_CLASS}
)
_DUPLICATION_CATEGORIES = frozenset({Category.DUPLICATION, Category.BOILERPLATE})


@dataclass
class BaselineMetrics:
    """The four headline numbers plus the finding identity set."""

    complexity: int = 0
    duplication_pct: float = 0.0
    warnings: int = 0
    dead_code: int = 0
    findings: list[str] = field(default_factory=list)
    score: float = 0.0
    captured_at: Optional[str] = None
    #: Full ``Finding.to_dict()`` snapshots, sorted by id.  ``findings`` above
    #: is the identity set used for diffing; these snapshots exist so a
    #: resolved finding can be *named* (real id, rule, title) instead of being
    #: reduced to a hash.  Older baselines without this key still load.
    entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "complexity": self.complexity,
            "duplication_pct": self.duplication_pct,
            "warnings": self.warnings,
            "dead_code": self.dead_code,
            "findings": list(self.findings),
            "score": self.score,
            "captured_at": self.captured_at,
            "entries": [dict(e) for e in self.entries],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BaselineMetrics":
        data = d or {}
        return cls(
            complexity=int(data.get("complexity", 0) or 0),
            duplication_pct=float(data.get("duplication_pct", 0.0) or 0.0),
            warnings=int(data.get("warnings", 0) or 0),
            dead_code=int(data.get("dead_code", 0) or 0),
            findings=[str(x) for x in (data.get("findings") or [])],
            score=float(data.get("score", 0.0) or 0.0),
            captured_at=data.get("captured_at"),
            entries=[dict(e) for e in (data.get("entries") or [])],
        )


# --------------------------------------------------------------------------
# collection
# --------------------------------------------------------------------------


def _is_project_code(path: str, config: Any) -> bool:
    """Vendor / generated paths are not the project's debt."""
    if config is None:
        return True
    if hasattr(config, "is_excluded") and config.is_excluded(path):
        return False
    if hasattr(config, "is_generated") and config.is_generated(path):
        return False
    return True


def collect_metrics(findings: list[Finding], *, config: Any = None) -> BaselineMetrics:
    """Reduce a finding set to the comparable baseline numbers.

    ``captured_at`` is deliberately left ``None``: a timestamp here would make
    the baseline file (and anything derived from it) differ between two runs
    over identical input.  Callers that want provenance may set it explicitly.
    """
    considered = [f for f in findings if _is_project_code(f.location.file, config)]

    complexity = sum(1 for f in considered if f.category in _COMPLEXITY_CATEGORIES)
    dead_code = sum(1 for f in considered if f.category is Category.DEAD_CODE)
    duplication = sum(1 for f in considered if f.category in _DUPLICATION_CATEGORIES)
    warnings = sum(1 for f in considered if f.severity is not Severity.LOW)

    score = score_findings(considered, config=config).total

    ordered = sorted(considered, key=lambda f: f.id)
    return BaselineMetrics(
        complexity=complexity,
        duplication_pct=round(percent(duplication, max(1, len(considered))), 1),
        warnings=warnings,
        dead_code=dead_code,
        findings=sorted(f.canonical_key() for f in ordered),
        score=score,
        captured_at=None,
        entries=[f.to_dict() for f in ordered],
    )


# --------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------


def load_baseline(path: Path | str) -> Optional[BaselineMetrics]:
    """Load a baseline; a missing or unreadable file is not an error."""
    data = read_json(path, default=None)
    if not isinstance(data, dict):
        return None
    try:
        return BaselineMetrics.from_dict(data)
    except (TypeError, ValueError):
        return None


def save_baseline(path: Path | str, metrics: BaselineMetrics) -> None:
    write_json(path, metrics.to_dict())


# --------------------------------------------------------------------------
# diffing
# --------------------------------------------------------------------------


def _delta_row(before: float, after: float, digits: int) -> float:
    return round(float(after) - float(before), digits)


def compute_delta(
    baseline: Optional[BaselineMetrics], current: BaselineMetrics
) -> dict[str, Any]:
    """Spec §13 delta block: ``{"baseline": .., "current": .., "delta": ..}``."""
    current_block = {
        "complexity": current.complexity,
        "duplication_pct": round(current.duplication_pct, 1),
        "warnings": current.warnings,
        "dead_code": current.dead_code,
        "score": current.score,
        "findings": len(current.findings),
    }
    if baseline is None:
        return {"baseline": None, "current": current_block, "delta": None}

    baseline_block = {
        "complexity": baseline.complexity,
        "duplication_pct": round(baseline.duplication_pct, 1),
        "warnings": baseline.warnings,
        "dead_code": baseline.dead_code,
        "score": baseline.score,
        "findings": len(baseline.findings),
    }
    delta = {
        "complexity": int(current.complexity) - int(baseline.complexity),
        "duplication_pct": _delta_row(baseline.duplication_pct, current.duplication_pct, 1),
        "warnings": int(current.warnings) - int(baseline.warnings),
        "dead_code": int(current.dead_code) - int(baseline.dead_code),
        "score": _delta_row(baseline.score, current.score, 1),
        "findings": len(current.findings) - len(baseline.findings),
    }
    return {"baseline": baseline_block, "current": current_block, "delta": delta}


def _placeholder_finding(key: str) -> Finding:
    """Rebuild a *named* finding from a canonical key when snapshots are absent.

    Only reached for baselines written before snapshots existed.  The id is
    synthetic but deterministic, and the title says so, so a reader is never
    misled into thinking it came from a provider.
    """
    import json as _json

    try:
        parts = _json.loads(key)
    except (TypeError, ValueError):
        parts = {}
    numeric = int(sha256_text(key)[:8], 16) % 10**6
    rule_id = str(parts.get("rule_id") or "CHM-RESOLVED-001")
    if not rule_id.startswith("CHM-"):
        rule_id = "CHM-RESOLVED-001"
    return Finding(
        id=f"CHM-{numeric:06d}",
        rule_id=rule_id,
        category=Category.DEAD_CODE,
        title="resolved finding (no snapshot recorded in this baseline)",
        severity=Severity.LOW,
        confidence=0.0,
        location=Location(
            file=str(parts.get("file") or ""),
            start_line=int(parts.get("line") or 1),
            end_line=int(parts.get("line") or 1),
            symbol=parts.get("symbol"),
        ),
    )


def classify_against_baseline(
    findings: list[Finding], baseline: Optional[BaselineMetrics]
) -> tuple[list[Finding], list[Finding], list[Finding]]:
    """Split into ``(new_findings, resolved_findings, preexisting_findings)``.

    * *new* -- not in the baseline and introduced by this change;
    * *preexisting* -- already in the baseline, or untouched by this change;
    * *resolved* -- in the baseline but no longer detected.

    Every finding already in the baseline is flagged ``historical=True``.
    """
    baseline_keys: set[str] = set(baseline.findings) if baseline is not None else set()

    new_findings: list[Finding] = []
    preexisting: list[Finding] = []
    current_keys: set[str] = set()

    for finding in findings:
        key = finding.canonical_key()
        current_keys.add(key)
        if key in baseline_keys:
            finding.historical = True
            preexisting.append(finding)
        elif finding.introduced_by_current_diff:
            new_findings.append(finding)
        else:
            # Not tracked by the baseline and not touched by this diff: it is
            # debt that already lived in the repository.
            preexisting.append(finding)

    resolved: list[Finding] = []
    if baseline is not None:
        for key in sorted(baseline_keys - current_keys):
            key_parts = _key_parts(key)
            for entry in baseline.entries:
                if _entry_matches(entry, key_parts):
                    try:
                        resolved.append(Finding.from_dict(entry))
                        break
                    except (KeyError, ValueError):
                        continue
            else:
                resolved.append(_placeholder_finding(key))

    new_findings.sort(key=lambda f: (-f.severity.rank, f.location.file, f.location.start_line, f.id))
    resolved.sort(key=lambda f: (f.location.file, f.location.start_line, f.id))
    preexisting.sort(key=lambda f: (-f.severity.rank, f.location.file, f.location.start_line, f.id))
    return new_findings, resolved, preexisting


def _key_parts(key: str) -> dict[str, Any]:
    import json as _json

    try:
        parts = _json.loads(key)
    except (TypeError, ValueError):
        return {}
    return parts if isinstance(parts, dict) else {}


def _entry_matches(entry: dict[str, Any], parts: dict[str, Any]) -> bool:
    if not parts:
        return False
    location = entry.get("location") or {}
    return (
        str(entry.get("rule_id")) == str(parts.get("rule_id"))
        and str(location.get("file")) == str(parts.get("file"))
        and int(location.get("start_line", 0)) == int(parts.get("line") or 0)
        and location.get("symbol") == parts.get("symbol")
    )
