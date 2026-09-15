"""The terminal report (spec §24).

Default output is *short on purpose*: a developer reading a failing build log
needs the verdict, the shape of the damage and the single worst issue -- not a
wall of text.  Everything else is behind ``verbose=True``.

``color`` defaults to ``False`` so the output is byte-assertable in tests and
readable in a dumb CI log.
"""

from __future__ import annotations

from typing import Any, Optional

from .json_report import (
    evidence_labels,
    finding_location,
    finding_providers,
    report_findings,
)

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
CYAN = "\033[36m"

_SEVERITY_COLOR = {
    "CRITICAL": RED,
    "HIGH": RED,
    "MEDIUM": YELLOW,
    "LOW": CYAN,
}

_VERDICT_COLOR = {
    "PASS": GREEN,
    "WARN": YELLOW,
    "BLOCK": RED,
    "UNKNOWN": YELLOW,
}

_SEVERITY_TITLE = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
}

#: Display order for the short summary.
_SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def _paint(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{color}{text}{RESET}"


def _worst(finding_dicts: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    rank = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
    if not finding_dicts:
        return None
    return min(
        finding_dicts,
        key=lambda f: (
            -rank.get(str(f.get("severity")), 0),
            -float(f.get("confidence", 0.0) or 0.0),
            str(f.get("id", "")),
        ),
    )


def render_console(
    report: dict[str, Any], *, verbose: bool = False, color: bool = False
) -> str:
    tool = report.get("tool") or {}
    summary = report.get("summary") or {}
    gate = report.get("gate") or {}
    score = report.get("score") or {}
    severity = summary.get("severity") or {}
    findings = report_findings(report)

    lines: list[str] = []
    lines.append(f"{tool.get('name', 'CodeHealthMind')} {tool.get('version', '1.0.0')}")
    lines.append("")
    lines.append(f"Changed files: {int(summary.get('changed_files', 0) or 0)}")
    lines.append(f"Findings: {int(summary.get('findings', len(findings)) or 0)}")
    for name in _SEVERITY_ORDER:
        label = _SEVERITY_TITLE[name]
        count = int(severity.get(name, 0) or 0)
        text = f"  {label}: {count}"
        lines.append(_paint(text, _SEVERITY_COLOR[name], color))
    lines.append("")

    verdict = str(gate.get("verdict") or "UNKNOWN")
    lines.append(_paint(f"Gate: {verdict}", _VERDICT_COLOR.get(verdict, ""), color))
    lines.append("")

    lines.append("Top issue:")
    top = _worst(findings)
    if top is None:
        lines.append("none")
    else:
        sev = str(top.get("severity", ""))
        lines.append(_paint(f"{top.get('id', '?')} {sev}", _SEVERITY_COLOR.get(sev, ""), color))
        lines.append(finding_location(top))
        lines.append(str(top.get("title", "")))
        labels = evidence_labels(top)
        lines.append("Evidence: " + (" + ".join(labels) if labels else "none"))

    # A non-PASS verdict must explain itself.  "Gate: UNKNOWN / Top issue: none"
    # is the least useful possible output, and it is exactly what a degraded
    # toolchain produces.
    reasons = [str(r) for r in (gate.get("reasons") or [])]
    tool_errors = report.get("tool_errors") or []
    if verdict != "PASS" and (reasons or tool_errors):
        lines.append("")
        lines.append("Why this verdict:")
        for reason in reasons[:8]:
            lines.append(f"  - {reason}")
        for err in tool_errors[:8]:
            lines.append(
                f"  - tool {err.get('provider')}: {err.get('kind')} -- {err.get('detail')}"
            )
        if verdict == "UNKNOWN":
            lines.append(
                "  UNKNOWN is not a pass. Fix the toolchain above, then re-run."
            )

    if verbose:
        lines.extend(_verbose_blocks(report, findings, score, gate, color))

    return "\n".join(lines) + "\n"


def _verbose_blocks(
    report: dict[str, Any],
    findings: list[dict[str, Any]],
    score: dict[str, Any],
    gate: dict[str, Any],
    color: bool,
) -> list[str]:
    lines: list[str] = []

    # ---- score ----------------------------------------------------------
    lines.append("")
    lines.append("Score:")
    lines.append(f"  Total: {score.get('total', 0.0)}")
    weights = score.get("weights") or {}
    dimensions = score.get("dimensions") or {}
    for name in weights:
        lines.append(
            f"  {name}: {dimensions.get(name, 0.0)}/{weights.get(name, 0.0):g}"
        )
    lines.append(f"  Hard gate: {'yes' if score.get('hard_gate') else 'no'}")
    for reason in score.get("hard_gate_reasons") or []:
        lines.append(f"    - {reason}")

    # ---- gate -----------------------------------------------------------
    lines.append("")
    lines.append("Gate detail:")
    lines.append(f"  Exit code: {gate.get('exit_code', 0)}")
    lines.append(f"  Tool degraded: {'yes' if gate.get('tool_degraded') else 'no'}")
    lines.append(f"  Evidence gap: {'yes' if gate.get('evidence_gap') else 'no'}")
    for reason in gate.get("blockers") or []:
        lines.append(_paint(f"  BLOCK: {reason}", RED, color))
    for reason in gate.get("reasons") or []:
        lines.append(f"  {reason}")

    # ---- every finding --------------------------------------------------
    lines.append("")
    lines.append(f"Findings ({len(findings)}):")
    for finding in findings:
        sev = str(finding.get("severity", ""))
        head = (
            f"  {finding.get('id', '?')} {sev} {finding.get('category', '')} "
            f"{finding_location(finding)}"
        )
        lines.append(_paint(head, _SEVERITY_COLOR.get(sev, ""), color))
        lines.append(f"    {finding.get('title', '')}")
        lines.append(f"    confidence: {finding.get('confidence', 0.0)}")
        providers = finding_providers(finding)
        lines.append("    providers: " + (", ".join(providers) if providers else "none"))
        recommendation = finding.get("recommendation") or {}
        if recommendation.get("preferred"):
            lines.append(f"    preferred: {recommendation['preferred']}")
        if recommendation.get("fallback"):
            lines.append(f"    fallback: {recommendation['fallback']}")
        repair = finding.get("repair") or {}
        lines.append(f"    repair_class: {repair.get('repair_class', 'NONE')}")

    # ---- dedup ----------------------------------------------------------
    dedup = report.get("dedup") or {}
    if dedup:
        lines.append("")
        lines.append("Dedup:")
        lines.append(f"  original: {dedup.get('original_count', 0)}")
        lines.append(f"  kept: {dedup.get('kept_count', 0)}")
        lines.append(f"  merged: {dedup.get('merged_count', 0)}")
        lines.append(f"  ratio: {dedup.get('dedup_ratio', 0.0)}")
        for group in dedup.get("groups") or []:
            lines.append(
                f"  {group.get('kept_id')} <- {', '.join(group.get('merged_ids') or [])}"
            )
            lines.append(f"    sources: {', '.join(group.get('sources') or [])}")
            lines.append(f"    reason: {group.get('reason')}")

    # ---- tools ----------------------------------------------------------
    lines.append("")
    lines.append("Tools:")
    tools = report.get("tools") or []
    if not tools:
        lines.append("  (none)")
    for tool_result in tools:
        lines.append(
            f"  {tool_result.get('provider')}: {tool_result.get('status')} "
            f"{tool_result.get('version') or '?'} ({tool_result.get('duration_ms', 0)}ms, "
            f"{tool_result.get('finding_count', 0)} findings)"
        )

    errors = report.get("tool_errors") or []
    lines.append("")
    lines.append(f"Tool errors ({len(errors)}):")
    if not errors:
        lines.append("  (none)")
    for error in errors:
        gap = " [evidence gap]" if error.get("evidence_gap") else ""
        lines.append(
            _paint(
                f"  {error.get('provider')} {error.get('kind')}: {error.get('detail')}{gap}",
                RED if error.get("evidence_gap") else YELLOW,
                color,
            )
        )

    return lines
