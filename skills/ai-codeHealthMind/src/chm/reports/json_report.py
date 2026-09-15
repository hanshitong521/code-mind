"""The machine-readable report (the contract every consumer reads).

``build_report`` assembles the single JSON document that the CLI, the SARIF
emitter and the Markdown emitter all consume, so there is exactly one place
where the report shape is defined.

``render_json`` goes through :func:`chm.util.stable_json`, which sorts keys and
pins separators.  Two runs over identical input therefore produce byte-identical
bytes -- no timestamps, no set iteration, no dictionary-order accidents.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from ..schema import severity_counts
from ..util import stable_json

REPORT_SCHEMA_VERSION = 1
TOOL_NAME = "CodeHealthMind"

try:  # single source of truth for the version string
    from .. import __version__ as TOOL_VERSION
except Exception:  # pragma: no cover - defensive
    TOOL_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# small shared accessors (used by every renderer)
# --------------------------------------------------------------------------


def as_dict(obj: Any) -> Any:
    """``to_dict()`` when available, plain ``dict`` otherwise."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return obj


def report_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings = report.get("findings") or []
    return [f for f in findings if isinstance(f, dict)]


def finding_location(finding: dict[str, Any]) -> str:
    location = finding.get("location") or {}
    path = str(location.get("file") or "?")
    line = int(location.get("start_line", 1) or 1)
    return f"{path}:{line}"


def evidence_items(finding: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = finding.get("evidence") or {}
    items: list[dict[str, Any]] = []
    for bucket in ("deterministic", "semantic"):
        for item in evidence.get(bucket) or []:
            if isinstance(item, dict):
                items.append(item)
    return items


def finding_providers(finding: dict[str, Any]) -> list[str]:
    """Merged evidence sources, de-duplicated and sorted."""
    providers = {str(i.get("provider", "")) for i in evidence_items(finding)}
    providers |= {str(s) for s in (finding.get("sources") or [])}
    providers.discard("")
    return sorted(providers)


def evidence_labels(finding: dict[str, Any]) -> list[str]:
    """Human labels for the merged evidence, in a stable order."""
    labels: list[str] = []
    for item in evidence_items(finding):
        label = str(item.get("detail") or item.get("result") or item.get("provider") or "")
        if label and label not in labels:
            labels.append(label)
    if not labels:
        labels = finding_providers(finding)
    return labels


_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def relative_uri(path: str, repo: Optional[str] = None) -> str:
    """Repo-relative, posix-separated URI (SARIF requires relative paths)."""
    text = str(path or "").replace("\\", "/")
    if text.startswith("file://"):
        text = text[7:]
    if repo:
        root = str(repo).replace("\\", "/").rstrip("/")
        if root and text.lower().startswith(root.lower() + "/"):
            text = text[len(root) + 1 :]
    if _DRIVE_RE.match(text):
        text = text[2:]
    text = text.lstrip("/")
    while text.startswith("./"):
        text = text[2:]
    return text


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def build_report(
    *,
    run_id: str,
    mode: str,
    ctx_dict: dict[str, Any],
    findings: Iterable[Any],
    score: Any,
    gate: Any,
    dedup: Any,
    tool_results: Iterable[Any],
    tool_errors: Iterable[Any],
    ledger: Any,
    baseline_delta: Optional[dict[str, Any]] = None,
    index_stats: Optional[dict[str, Any]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    ctx = dict(ctx_dict or {})
    finding_list = list(findings or [])
    finding_dicts = [as_dict(f) for f in finding_list]

    score_dict = as_dict(score) or {}
    gate_dict = as_dict(gate) or {}
    ledger_dict = as_dict(ledger) or {}

    changed_files = len(ctx.get("changed_files") or [])
    counts = severity_counts(finding_list)
    severity_block = {name: int(counts.get(name, 0)) for name in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "run": {
            "run_id": run_id,
            "mode": mode,
            "repo": ctx.get("repo_root"),
            "commit": ctx.get("commit") or ctx.get("head_ref"),
            "base": ctx.get("base_ref"),
            "duration_ms": int(ledger_dict.get("duration_ms", 0) or 0),
        },
        "summary": {
            "changed_files": changed_files,
            "findings": len(finding_dicts),
            "severity": severity_block,
            "gate": gate_dict.get("verdict"),
            "exit_code": gate_dict.get("exit_code"),
            "score": score_dict.get("total", 0.0),
        },
        "score": score_dict,
        "gate": gate_dict,
        "dedup": as_dict(dedup) or {},
        "findings": finding_dicts,
        "tools": [as_dict(t) for t in (tool_results or [])],
        "tool_errors": [as_dict(e) for e in (tool_errors or [])],
        "ledger": ledger_dict,
        "baseline": baseline_delta,
        "index": index_stats,
    }

    # Caller-supplied blocks (repair plan, reviewer calls, ...).  Core keys are
    # never overwritten: a report renderer must not be able to clobber the
    # verdict.
    for key, value in (extra or {}).items():
        if key not in report:
            report[key] = value

    return report


def render_json(report: dict[str, Any]) -> str:
    """Deterministic JSON.  Byte-identical for identical input."""
    return stable_json(report)
