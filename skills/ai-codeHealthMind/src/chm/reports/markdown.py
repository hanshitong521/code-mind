"""The reviewable report (spec §53).

A report is read by a human who has to decide something, so it is organised by
*decision*, not by data source:

1. what is the verdict,
2. what did **this change** introduce,
3. what was already there,
4. what did we fix,
5. how was the score built,
6. what did the tools actually do.

Multi-source findings are collapsed to a single row -- the same problem is
never listed three times just because three tools found it.
"""

from __future__ import annotations

from typing import Any

from .json_report import (
    evidence_items,
    finding_location,
    finding_providers,
    report_findings,
)

_SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip()


def _severity_sort(finding: dict[str, Any]) -> tuple[int, str, int, str]:
    rank = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
    location = finding.get("location") or {}
    return (
        -rank.get(str(finding.get("severity")), 0),
        str(location.get("file") or ""),
        int(location.get("start_line", 1) or 1),
        str(finding.get("id") or ""),
    )


def _split_groups(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(introduced_by_this_change, preexisting)``.

    ``new_findings`` from the baseline diff is authoritative when present;
    otherwise the finding's own ``introduced_by_current_diff`` flag is used.
    """
    findings = report_findings(report)
    new_ids = report.get("new_findings")
    if isinstance(new_ids, list):
        new_set = {str(x) for x in new_ids}
        introduced = [f for f in findings if str(f.get("id")) in new_set]
        preexisting = [f for f in findings if str(f.get("id")) not in new_set]
    else:
        introduced = [
            f
            for f in findings
            if (f.get("change_scope") or {}).get("introduced_by_current_diff")
        ]
        preexisting = [
            f
            for f in findings
            if not (f.get("change_scope") or {}).get("introduced_by_current_diff")
        ]
    introduced.sort(key=_severity_sort)
    preexisting.sort(key=_severity_sort)
    return introduced, preexisting


def _findings_table(findings: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| ID | Severity | Category | Location | Title | Sources | Repair class |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for finding in findings:
        providers = finding_providers(finding)
        repair = finding.get("repair") or {}
        lines.append(
            "| {id} | {sev} | {cat} | {loc} | {title} | {src} | {repair} |".format(
                id=_cell(finding.get("id")),
                sev=_cell(finding.get("severity")),
                cat=_cell(finding.get("category")),
                loc=_cell(finding_location(finding)),
                title=_cell(finding.get("title")),
                src=_cell(", ".join(providers) if providers else "none"),
                repair=_cell(repair.get("repair_class", "NONE")),
            )
        )
    return lines


def _evidence_block(findings: list[dict[str, Any]]) -> list[str]:
    """Per-finding evidence detail -- one block per finding, never per source."""
    lines: list[str] = []
    for finding in findings:
        items = evidence_items(finding)
        providers = finding_providers(finding)
        lines.append(f"#### {_cell(finding.get('id'))} -- {_cell(finding.get('title'))}")
        lines.append("")
        lines.append(f"- **Location:** `{_cell(finding_location(finding))}`")
        lines.append(f"- **Severity / category:** {_cell(finding.get('severity'))} / {_cell(finding.get('category'))}")
        lines.append(f"- **Confidence:** {finding.get('confidence', 0.0)}")
        lines.append(
            "- **Evidence sources:** "
            + (", ".join(providers) if providers else "none")
        )
        if items:
            for item in items:
                provider = _cell(item.get("provider"))
                kind = _cell(item.get("kind"))
                result = _cell(item.get("result"))
                detail = _cell(item.get("detail"))
                suffix = f" -- {detail}" if detail else ""
                lines.append(f"  - `{provider}` ({kind}): {result}{suffix}")
        uncertainty = finding.get("uncertainty") or {}
        notes = uncertainty.get("notes") or []
        if notes:
            lines.append("- **Uncertainty notes:** " + "; ".join(_cell(n) for n in notes))
        lines.append("")

    recommendations = [
        f for f in findings if (f.get("recommendation") or {}).get("preferred")
    ]
    if recommendations:
        lines.append("#### Recommendations")
        lines.append("")
        for finding in recommendations:
            recommendation = finding.get("recommendation") or {}
            lines.append(
                f"- **{_cell(finding.get('id'))}** -- preferred: "
                f"{_cell(recommendation.get('preferred'))}"
            )
            if recommendation.get("fallback"):
                lines.append(f"  - fallback: {_cell(recommendation['fallback'])}")
        lines.append("")

    return lines


def _tool_tables(report: dict[str, Any]) -> list[str]:
    lines = ["| Provider | Status | Version | Duration (ms) | Findings | Error kind |", "| --- | --- | --- | --- | --- | --- |"]
    tools = report.get("tools") or []
    if not tools:
        lines.append("| _(none)_ | - | - | - | - | - |")
    for tool_result in tools:
        error = tool_result.get("error") or {}
        lines.append(
            "| {p} | {s} | {v} | {d} | {n} | {e} |".format(
                p=_cell(tool_result.get("provider")),
                s=_cell(tool_result.get("status")),
                v=_cell(tool_result.get("version") or "-"),
                d=_cell(tool_result.get("duration_ms", 0)),
                n=_cell(tool_result.get("finding_count", 0)),
                e=_cell(error.get("kind") or "-"),
            )
        )
    return lines


def _baseline_table(report: dict[str, Any]) -> list[str]:
    baseline = report.get("baseline")
    if not isinstance(baseline, dict) or baseline.get("current") is None:
        return ["_No baseline recorded for this run._"]

    before = baseline.get("baseline")
    current = baseline.get("current") or {}
    delta = baseline.get("delta")
    if before is None or not isinstance(delta, dict):
        rows = "\n".join(
            f"| {_cell(k)} | - | {_cell(v)} | - |" for k, v in current.items()
        )
        return [
            "_No previous baseline: these values become the new baseline._",
            "",
            "| Metric | Baseline | Current | Delta |",
            "| --- | --- | --- | --- |",
            rows,
        ]

    lines = ["| Metric | Baseline | Current | Delta |", "| --- | --- | --- | --- |"]
    for key in ("complexity", "duplication_pct", "warnings", "dead_code", "score", "findings"):
        change = delta.get(key, 0)
        marker = f"+{change}" if isinstance(change, (int, float)) and change > 0 else str(change)
        lines.append(
            f"| {_cell(key)} | {_cell(before.get(key))} | {_cell(current.get(key))} | {_cell(marker)} |"
        )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    tool = report.get("tool") or {}
    summary = report.get("summary") or {}
    gate = report.get("gate") or {}
    score = report.get("score") or {}
    severity = summary.get("severity") or {}
    findings = report_findings(report)
    introduced, preexisting = _split_groups(report)

    lines: list[str] = []
    lines.append(f"# {tool.get('name', 'CodeHealthMind')} {tool.get('version', '1.0.0')} -- code health report")
    lines.append("")
    lines.append(f"**Gate:** {gate.get('verdict', 'UNKNOWN')} (exit code {gate.get('exit_code', 0)})")
    lines.append(f"**Score:** {score.get('total', 0.0)}")
    lines.append(f"**Changed files:** {int(summary.get('changed_files', 0) or 0)}")
    lines.append(
        "**Findings:** {n} -- CRITICAL {c} / HIGH {h} / MEDIUM {m} / LOW {l}".format(
            n=int(summary.get("findings", len(findings)) or 0),
            c=int(severity.get("CRITICAL", 0) or 0),
            h=int(severity.get("HIGH", 0) or 0),
            m=int(severity.get("MEDIUM", 0) or 0),
            l=int(severity.get("LOW", 0) or 0),
        )
    )
    lines.append("")

    # ---- gate -----------------------------------------------------------
    lines.append("## Gate")
    lines.append("")
    lines.append(
        f"Tool degraded: **{'yes' if gate.get('tool_degraded') else 'no'}** / "
        f"evidence gap: **{'yes' if gate.get('evidence_gap') else 'no'}**"
    )
    lines.append("")
    blockers = gate.get("blockers") or []
    if blockers:
        lines.append("### Blockers")
        lines.append("")
        for blocker in blockers:
            lines.append(f"- {_cell(blocker)}")
        lines.append("")
    reasons = gate.get("reasons") or []
    if reasons:
        lines.append("### Reasons")
        lines.append("")
        for reason in reasons:
            lines.append(f"- {_cell(reason)}")
        lines.append("")

    # ---- findings -------------------------------------------------------
    lines.append("## Findings introduced by this change")
    lines.append("")
    if introduced:
        lines.extend(_findings_table(introduced))
        lines.append("")
        lines.extend(_evidence_block(introduced))
    else:
        lines.append("_None._")
        lines.append("")

    lines.append("## Pre-existing / historical debt")
    lines.append("")
    if preexisting:
        lines.extend(_findings_table(preexisting))
        lines.append("")
        lines.extend(_evidence_block(preexisting))
    else:
        lines.append("_None._")
        lines.append("")

    resolved_ids = report.get("resolved_findings")
    if isinstance(resolved_ids, list) and resolved_ids:
        lines.append("## Resolved since baseline")
        lines.append("")
        for finding_id in sorted(str(x) for x in resolved_ids):
            lines.append(f"- {_cell(finding_id)}")
        lines.append("")

    # ---- score ----------------------------------------------------------
    lines.append("## Score")
    lines.append("")
    weights = score.get("weights") or {}
    dimensions = score.get("dimensions") or {}
    lines.append("| Dimension | Score | Weight |")
    lines.append("| --- | --- | --- |")
    for name in weights:
        lines.append(
            f"| {_cell(name)} | {dimensions.get(name, 0.0)} | {weights.get(name, 0.0):g} |"
        )
    lines.append(f"| **Total** | **{score.get('total', 0.0)}** | **100** |")
    lines.append("")
    if score.get("hard_gate"):
        lines.append("**Hard gate tripped** -- the numeric total must not be used to argue for a merge:")
        lines.append("")
        for reason in score.get("hard_gate_reasons") or []:
            lines.append(f"- {_cell(reason)}")
        lines.append("")

    deductions = score.get("deductions") or []
    if deductions:
        lines.append("### Deductions")
        lines.append("")
        lines.append("| Finding | Dimension | Points | Reason |")
        lines.append("| --- | --- | --- | --- |")
        for item in deductions:
            lines.append(
                "| {f} | {d} | {a} | {r} |".format(
                    f=_cell(item.get("finding_id") or "-"),
                    d=_cell(item.get("dimension") or "-"),
                    a=_cell(item.get("amount", 0.0)),
                    r=_cell(item.get("reason")),
                )
            )
        lines.append("")

    # ---- tools ----------------------------------------------------------
    lines.append("## Tools")
    lines.append("")
    lines.extend(_tool_tables(report))
    lines.append("")

    errors = report.get("tool_errors") or []
    lines.append("## Tool errors")
    lines.append("")
    if not errors:
        lines.append("_None._")
    else:
        lines.append("| Provider | Kind | Evidence gap | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for error in errors:
            lines.append(
                "| {p} | {k} | {g} | {d} |".format(
                    p=_cell(error.get("provider")),
                    k=_cell(error.get("kind")),
                    g="yes" if error.get("evidence_gap") else "no",
                    d=_cell(error.get("detail")),
                )
            )
    lines.append("")

    # ---- baseline -------------------------------------------------------
    lines.append("## Baseline delta")
    lines.append("")
    lines.extend(_baseline_table(report))
    lines.append("")

    # ---- dedup ----------------------------------------------------------
    dedup = report.get("dedup") or {}
    lines.append("## Deduplication")
    lines.append("")
    lines.append(
        "{orig} finding(s) from all providers collapsed to {kept} "
        "(merged {merged}, ratio {ratio}).".format(
            orig=int(dedup.get("original_count", len(findings)) or 0),
            kept=int(dedup.get("kept_count", len(findings)) or 0),
            merged=int(dedup.get("merged_count", 0) or 0),
            ratio=dedup.get("dedup_ratio", 0.0),
        )
    )
    groups = dedup.get("groups") or []
    if groups:
        lines.append("")
        lines.append("| Kept | Merged in | Sources | Reason |")
        lines.append("| --- | --- | --- | --- |")
        for group in groups:
            lines.append(
                "| {k} | {m} | {s} | {r} |".format(
                    k=_cell(group.get("kept_id")),
                    m=_cell(", ".join(group.get("merged_ids") or [])),
                    s=_cell(", ".join(group.get("sources") or [])),
                    r=_cell(group.get("reason")),
                )
            )
    lines.append("")

    return "\n".join(lines)
