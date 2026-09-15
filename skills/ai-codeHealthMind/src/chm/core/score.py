"""Explainable scoring (spec §12) and hard-gate detection.

Two rules drive this module:

1. **Every point of damage has a source.**  ``ScoreBreakdown.deductions`` lists
   one entry per finding that cost points, so a reviewer can always answer
   "why is this 72.5 and not 100?" (spec §46 explainability).
2. **Averages must never bury a fatal problem.**  When a CRITICAL finding
   exists, when compilation failed, or when tests failed, ``hard_gate`` is set
   and the numeric total stops being an argument (spec §46).  The real total is
   still reported -- it is honest data -- but the gate is forbidden from using
   it as a defence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..errors import ToolError
from ..schema import Category, Finding, Severity
from ..util import clamp

#: Spec §12 dimension weights.  They sum to exactly 100.
DIMENSIONS: dict[str, float] = {
    "Correctness": 20.0,
    "Simplicity": 15.0,
    "Maintainability": 15.0,
    "Duplication": 10.0,
    "Complexity": 10.0,
    "Dead Code": 10.0,
    "Performance": 5.0,
    "Concurrency": 5.0,
    "Resource Safety": 5.0,
    "Testability": 5.0,
}

#: Every Category maps to exactly one dimension.  The partition below covers
#: all 20 categories in :class:`chm.schema.Category`.
CATEGORY_DIMENSION: dict[Category, str] = {
    Category.ERROR_HANDLING: "Correctness",
    Category.DATABASE: "Correctness",
    Category.CONFIG_INFLATION: "Correctness",
    Category.OVER_ENGINEERING: "Simplicity",
    Category.WRONG_ABSTRACTION: "Simplicity",
    Category.DEFENSIVE_JUNK: "Simplicity",
    Category.COMPATIBILITY_JUNK: "Simplicity",
    Category.DEPENDENCY_GROWTH: "Maintainability",
    Category.API_SURFACE_GROWTH: "Maintainability",
    Category.ARCHITECTURE_DRIFT: "Maintainability",
    Category.DUPLICATION: "Duplication",
    Category.BOILERPLATE: "Duplication",
    Category.COMPLEXITY: "Complexity",
    Category.LARGE_METHOD: "Complexity",
    Category.LARGE_CLASS: "Complexity",
    Category.DEAD_CODE: "Dead Code",
    Category.PERFORMANCE: "Performance",
    Category.CONCURRENCY: "Concurrency",
    Category.RESOURCE_SAFETY: "Resource Safety",
    Category.TESTABILITY: "Testability",
}

#: Fraction of a dimension's weight a finding of that severity costs.
SEVERITY_FRACTION: dict[Severity, float] = {
    Severity.CRITICAL: 1.0,
    Severity.HIGH: 0.6,
    Severity.MEDIUM: 0.3,
    Severity.LOW: 0.1,
}

#: Used only if a future Category is added without a mapping.  Maintainability
#: is the least flattering default, so an unmapped category is never cheap.
_FALLBACK_DIMENSION = "Maintainability"


def dimension_for(category: Category) -> str:
    return CATEGORY_DIMENSION.get(category, _FALLBACK_DIMENSION)


# --------------------------------------------------------------------------
# result object
# --------------------------------------------------------------------------


@dataclass
class ScoreBreakdown:
    total: float = 0.0
    dimensions: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    deductions: list[dict[str, Any]] = field(default_factory=list)
    hard_gate: bool = False
    hard_gate_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "dimensions": dict(self.dimensions),
            "weights": dict(self.weights),
            "deductions": [dict(d) for d in self.deductions],
            "hard_gate": self.hard_gate,
            "hard_gate_reasons": list(self.hard_gate_reasons),
        }


def score_from_dict(d: dict[str, Any]) -> ScoreBreakdown:
    """Inverse of :meth:`ScoreBreakdown.to_dict` (used by report consumers)."""
    data = d or {}
    return ScoreBreakdown(
        total=float(data.get("total", 0.0)),
        dimensions={str(k): float(v) for k, v in (data.get("dimensions") or {}).items()},
        weights={str(k): float(v) for k, v in (data.get("weights") or {}).items()},
        deductions=[dict(x) for x in (data.get("deductions") or [])],
        hard_gate=bool(data.get("hard_gate", False)),
        hard_gate_reasons=[str(x) for x in (data.get("hard_gate_reasons") or [])],
    )


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def _ordered(findings: list[Finding]) -> list[Finding]:
    """Stable order so ``deductions`` is byte-identical between runs."""
    return sorted(
        findings,
        key=lambda f: (
            -f.severity.rank,
            (f.location.file or "").replace("\\", "/"),
            int(f.location.start_line),
            f.id,
        ),
    )


def score_findings(
    findings: list[Finding],
    *,
    config: Any = None,
    tool_errors: Optional[list[ToolError]] = None,
    compile_ok: Optional[bool] = None,
    test_ok: Optional[bool] = None,
) -> ScoreBreakdown:
    """Score a finding set and decide whether the hard gate tripped.

    ``config`` is accepted for interface symmetry; weights are fixed by spec
    §12 and deliberately not tunable (a tunable gate is not a gate).
    """
    used: dict[str, float] = {name: 0.0 for name in DIMENSIONS}
    deductions: list[dict[str, Any]] = []

    for finding in _ordered(findings):
        dimension = dimension_for(finding.category)
        weight = DIMENSIONS.get(dimension, 0.0)
        fraction = SEVERITY_FRACTION.get(finding.severity, 0.0)
        finding_weight = clamp(float(finding.score_weight or 0.0), 0.0, 1.0)
        amount = round(weight * fraction * finding_weight, 4)
        deductions.append(
            {
                "finding_id": finding.id,
                "dimension": dimension,
                "amount": amount,
                "reason": (
                    f"{finding.severity.value} {finding.category.value} finding "
                    f"costs {fraction:.0%} of the {dimension} budget "
                    f"({weight:g} x {fraction:.2f})"
                ),
            }
        )
        used[dimension] = used[dimension] + amount

    dimensions = {
        name: round(max(0.0, DIMENSIONS[name] - used[name]), 2) for name in DIMENSIONS
    }
    total = round(sum(dimensions.values()), 1)

    hard_gate_reasons: list[str] = []

    criticals = sorted(f.id for f in findings if f.severity is Severity.CRITICAL)
    if criticals:
        hard_gate_reasons.append(
            "CRITICAL finding present: " + ", ".join(criticals)
        )

    highs = sorted(f.id for f in findings if f.severity is Severity.HIGH)
    if highs:
        # score.py has no accepted-risk view; gate.py is the layer that knows
        # which HIGH findings are explained.  Until then every HIGH counts.
        hard_gate_reasons.append(
            "unexplained HIGH finding present: " + ", ".join(highs)
        )

    if compile_ok is False:
        hard_gate_reasons.append("compilation failed (compile_ok=False)")
    if test_ok is False:
        hard_gate_reasons.append("tests failed (test_ok=False)")

    for error in tool_errors or []:
        if not getattr(error, "evidence_gap", False):
            continue
        kind = getattr(getattr(error, "kind", None), "value", "UNKNOWN")
        provider = getattr(error, "provider", "unknown")
        detail = getattr(error, "detail", "") or ""
        deductions.append(
            {
                "finding_id": "",
                "dimension": "",
                "amount": 0.0,
                "reason": (
                    f"evidence gap: provider {provider} failed with {kind}"
                    + (f" ({detail})" if detail else "")
                    + " -- HIGH/CRITICAL verification incomplete"
                ),
            }
        )
        hard_gate_reasons.append(
            f"evidence gap from {provider} ({kind}) -- "
            "HIGH/CRITICAL verification incomplete; the gate may not claim a clean result"
        )

    return ScoreBreakdown(
        total=total,
        dimensions=dimensions,
        weights=dict(DIMENSIONS),
        deductions=deductions,
        hard_gate=bool(hard_gate_reasons),
        hard_gate_reasons=hard_gate_reasons,
    )
