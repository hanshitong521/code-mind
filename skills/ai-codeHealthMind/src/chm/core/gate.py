"""The merge gate (spec §47).

This module owns exactly one question: *may this change be merged?*  It is the
only place allowed to answer it, and it answers from findings, compile/test
status and tool health -- never from a comfortable average.

The three outcomes that matter:

``PASS``
    Nothing above LOW severity, every tool healthy, nothing suppressed.
``WARN``
    Real but tolerable debt: new MEDIUMs within the configured budget, a
    degraded tool that did not blind us, or historical debt carried forward.
``BLOCK``
    A definite reason to stop: compile/test failure, an unaccepted
    CRITICAL/HIGH, or new MEDIUM debt over budget.
``UNKNOWN``
    We could not *see* well enough to certify the change.  A missing tool that
    would have produced HIGH/CRITICAL evidence is **never** a PASS.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..errors import ToolError
from ..schema import EXIT_CODES, EXIT_TOOL_ERROR, Finding, FindingStatus, GateVerdict, Severity

#: Finding statuses that already represent a closed decision; they can never
#: block a merge again (the decision was made and recorded).
NON_BLOCKING_STATUSES: frozenset[FindingStatus] = frozenset(
    {
        FindingStatus.ACCEPTED_RISK,
        FindingStatus.FALSE_POSITIVE,
        FindingStatus.CLOSED,
        FindingStatus.REJECTED,
        FindingStatus.FIXED,
    }
)

#: Environment variable that pins "today" for accepted-risk expiry checks.
TODAY_ENV = "CHM_TODAY"


@dataclass
class GateResult:
    verdict: GateVerdict = GateVerdict.PASS
    exit_code: int = 0
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    score: float = 0.0
    tool_degraded: bool = False
    evidence_gap: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "score": self.score,
            "tool_degraded": self.tool_degraded,
            "evidence_gap": self.evidence_gap,
        }


def exit_code_for(verdict: GateVerdict) -> int:
    return EXIT_CODES.get(verdict, EXIT_TOOL_ERROR)


def _resolve_today(today: Optional[str]) -> str:
    if today:
        return str(today)
    from_env = os.environ.get(TODAY_ENV)
    if from_env:
        return from_env
    return time.strftime("%Y-%m-%d")


def _suppression_reason(
    finding: Finding,
    *,
    config: Any,
    today: str,
    accepted_ids: frozenset[str],
) -> Optional[str]:
    """Why this finding must not block, or ``None`` if it still counts."""
    if finding.id in accepted_ids:
        return f"{finding.id} explicitly accepted by the caller"
    if finding.decision.status in NON_BLOCKING_STATUSES:
        return f"{finding.id} closed with status {finding.decision.status.value}"
    if config is not None and hasattr(config, "accepted_risk_for"):
        risk = config.accepted_risk_for(finding.id, finding.rule_id, today)
        if risk is not None:
            owner = f", owner {risk.owner}" if risk.owner else ""
            expiry = f", expires {risk.expires}" if risk.expires else ", no expiry"
            return (
                f"{finding.id} covered by accepted risk "
                f"({risk.reason or 'no reason given'}{owner}{expiry})"
            )
    return None


def evaluate_gate(
    findings: list[Finding],
    *,
    score: Any,
    config: Any,
    tool_errors: Optional[list[ToolError]] = None,
    compile_ok: Optional[bool] = None,
    test_ok: Optional[bool] = None,
    new_findings: Optional[list[Finding]] = None,
    accepted: Optional[list[Finding]] = None,
    today: Optional[str] = None,
) -> GateResult:
    """Apply the spec §47 decision matrix.

    ``new_findings`` is the baseline diff (``None`` means "derive from the
    ``introduced_by_current_diff`` flag").  Only *new* MEDIUM debt counts
    against ``gates.max_new_medium`` -- carrying historical debt is allowed,
    adding new debt is not (spec §13).
    """
    today_str = _resolve_today(today)
    gates = config.gates if config is not None else None
    accepted_ids = frozenset(f.id for f in (accepted or []))

    block_on_critical = getattr(gates, "block_on_critical", True)
    block_on_high = getattr(gates, "block_on_high", True)
    max_new_medium = int(getattr(gates, "max_new_medium", 5))
    block_on_compile_fail = getattr(gates, "block_on_compile_fail", True)
    block_on_test_fail = getattr(gates, "block_on_test_fail", True)
    block_on_tool_gap = getattr(gates, "block_on_tool_gap_for_critical", True)
    min_score = float(getattr(gates, "min_score", 0.0) or 0.0)

    reasons: list[str] = []
    blockers: list[str] = []

    live: list[Finding] = []
    for finding in findings:
        why = _suppression_reason(
            finding, config=config, today=today_str, accepted_ids=accepted_ids
        )
        if why is None:
            live.append(finding)
        else:
            reasons.append(f"not blocking: {why}")

    # ---- definite blockers -------------------------------------------------

    if compile_ok is False:
        if block_on_compile_fail:
            blockers.append("compilation failed")
        else:
            reasons.append("compilation failed but gates.block_on_compile_fail is off")

    if test_ok is False:
        if block_on_test_fail:
            blockers.append("unit tests failed")
        else:
            reasons.append("unit tests failed but gates.block_on_test_fail is off")

    criticals = sorted(
        (f for f in live if f.severity is Severity.CRITICAL), key=lambda f: f.id
    )
    if criticals and block_on_critical:
        blockers.append(
            f"{len(criticals)} CRITICAL finding(s): "
            + ", ".join(f.id for f in criticals)
        )

    highs = sorted((f for f in live if f.severity is Severity.HIGH), key=lambda f: f.id)
    if highs and block_on_high:
        blockers.append(
            f"{len(highs)} HIGH finding(s): " + ", ".join(f.id for f in highs)
        )

    # ---- new MEDIUM budget -------------------------------------------------

    if new_findings is None:
        new_mediums = [
            f
            for f in live
            if f.severity is Severity.MEDIUM and f.introduced_by_current_diff
        ]
        medium_source = "introduced_by_current_diff"
    else:
        new_mediums = []
        for finding in new_findings:
            if finding.severity is not Severity.MEDIUM:
                continue
            if _suppression_reason(
                finding, config=config, today=today_str, accepted_ids=accepted_ids
            ) is not None:
                continue
            new_mediums.append(finding)
        medium_source = "baseline diff"

    new_mediums.sort(key=lambda f: (f.location.file, f.location.start_line, f.id))
    if len(new_mediums) > max_new_medium:
        blockers.append(
            f"{len(new_mediums)} new MEDIUM finding(s) exceed "
            f"gates.max_new_medium={max_new_medium} ({medium_source})"
        )
    elif new_mediums:
        reasons.append(
            f"{len(new_mediums)} new MEDIUM finding(s) within "
            f"gates.max_new_medium={max_new_medium} -> WARN"
        )

    if min_score > 0.0:
        total = float(getattr(score, "total", 0.0))
        if total < min_score:
            blockers.append(f"score {total} below gates.min_score {min_score}")

    # ---- tool health -------------------------------------------------------

    errors = list(tool_errors or [])
    tool_degraded = bool(errors)
    evidence_gap = any(getattr(e, "evidence_gap", False) for e in errors)
    for error in errors:
        kind = getattr(getattr(error, "kind", None), "value", "UNKNOWN")
        provider = getattr(error, "provider", "unknown")
        detail = getattr(error, "detail", "") or ""
        gap = bool(getattr(error, "evidence_gap", False))
        reasons.append(
            f"tool degraded: {provider} {kind}"
            + (f" ({detail})" if detail else "")
            + (" [evidence gap: HIGH/CRITICAL verification incomplete]" if gap else "")
        )

    hard_gate = bool(getattr(score, "hard_gate", False))
    if hard_gate:
        reasons.append(
            "score hard gate tripped: "
            + "; ".join(getattr(score, "hard_gate_reasons", []) or ["(no reason recorded)"])
        )

    # ---- verdict -----------------------------------------------------------

    mediums = [f for f in live if f.severity is Severity.MEDIUM]

    if blockers:
        verdict = GateVerdict.BLOCK
    elif evidence_gap and block_on_tool_gap:
        verdict = GateVerdict.UNKNOWN
        reasons.append(
            "evidence gap affects HIGH/CRITICAL verification -> UNKNOWN "
            "(a missing tool is not evidence of absence)"
        )
    elif criticals:
        verdict = GateVerdict.WARN
        reasons.append(
            f"{len(criticals)} CRITICAL finding(s) present but "
            "gates.block_on_critical is off -> WARN"
        )
    elif highs:
        verdict = GateVerdict.WARN
        reasons.append(
            f"{len(highs)} HIGH finding(s) present but gates.block_on_high is off -> WARN"
        )
    elif tool_degraded:
        verdict = GateVerdict.WARN
        reasons.append("tool degradation without an evidence gap -> WARN")
    elif new_mediums:
        verdict = GateVerdict.WARN
    elif mediums:
        verdict = GateVerdict.WARN
        reasons.append(
            f"{len(mediums)} pre-existing MEDIUM finding(s) carried as historical debt"
        )
    else:
        verdict = GateVerdict.PASS

    if verdict is GateVerdict.PASS:
        reasons.append("no CRITICAL/HIGH/MEDIUM findings, tools healthy")

    return GateResult(
        verdict=verdict,
        exit_code=exit_code_for(verdict),
        reasons=reasons,
        blockers=blockers,
        score=float(getattr(score, "total", 0.0)),
        tool_degraded=tool_degraded,
        evidence_gap=evidence_gap,
    )
