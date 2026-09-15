"""SARIF 2.1.0 output, so existing consumers can read our findings.

The report is a CodeHealthMind artefact; SARIF is how it reaches GitHub code
scanning, IDE problem panels and other standard tooling.  That means the
document has to be *actually* conformant, not approximately:

* every ``ruleId`` in a result must exist in ``tool.driver.rules``;
* every artifact location must be a **relative**, ``/``-separated URI;
* every region must satisfy ``1 <= startLine <= endLine``;
* the severity mapping must be the documented one (CRITICAL/HIGH -> ``error``).

:func:`validate_sarif` is a self-check for exactly those invariants, and it is
used by the test suite rather than trusted.
"""

from __future__ import annotations

import re
from typing import Any

from .json_report import evidence_items, relative_uri, report_findings

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

#: Placeholder until the project publishes a canonical URL.  SARIF requires the
#: field to be present and to be a URI.
#: Real location of this implementation.  Do not point this at a domain that
#: does not resolve -- SARIF consumers surface it to humans.
INFORMATION_URI = "https://github.com/hanshitong521/code-mind/tree/master/skills/ai-codeHealthMind"

_LEVELS = ("error", "warning", "note", "none")

#: Severity -> SARIF result level.
SEVERITY_LEVEL = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
}


def level_for(severity: str) -> str:
    return SEVERITY_LEVEL.get(str(severity), "warning")


def _rule_for(finding: dict[str, Any]) -> dict[str, Any]:
    severity = str(finding.get("severity", ""))
    category = str(finding.get("category", ""))
    return {
        "id": str(finding.get("rule_id", "")),
        "name": str(finding.get("rule_id", "")),
        "shortDescription": {"text": str(finding.get("title", ""))},
        "fullDescription": {
            "text": f"{category} finding detected by CodeHealthMind: {finding.get('title', '')}"
        },
        "defaultConfiguration": {"level": level_for(severity)},
        "properties": {
            "tags": [category, severity],
            "category": category,
            "severity": severity,
        },
    }


def _result_for(finding: dict[str, Any], rule_index: int, repo: str | None) -> dict[str, Any]:
    location = finding.get("location") or {}
    start_line = int(location.get("start_line", 1) or 1)
    end_line = int(location.get("end_line", start_line) or start_line)
    if start_line < 1:
        start_line = 1
    if end_line < start_line:
        end_line = start_line

    providers = sorted(
        {str(item.get("provider", "")) for item in evidence_items(finding)} - {""}
    )

    return {
        "ruleId": str(finding.get("rule_id", "")),
        "ruleIndex": rule_index,
        "level": level_for(str(finding.get("severity", ""))),
        "message": {"text": str(finding.get("title", ""))},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": relative_uri(str(location.get("file", "")), repo)
                    },
                    "region": {"startLine": start_line, "endLine": end_line},
                }
            }
        ],
        "properties": {
            "severity": str(finding.get("severity", "")),
            "category": str(finding.get("category", "")),
            "confidence": finding.get("confidence", 0.0),
            "gate": None,  # filled in by render_sarif (one verdict per run)
            "evidenceProviders": providers,
            "findingId": str(finding.get("id", "")),
            "repairClass": ((finding.get("repair") or {}).get("repair_class") or "NONE"),
        },
    }


def render_sarif(report: dict[str, Any]) -> dict[str, Any]:
    """Build a SARIF 2.1.0 document from a CodeHealthMind report."""
    tool = report.get("tool") or {}
    run = report.get("run") or {}
    gate = report.get("gate") or {}
    summary = report.get("summary") or {}
    repo = run.get("repo")
    findings = report_findings(report)

    rules: list[dict[str, Any]] = []
    rule_index: dict[str, int] = {}
    for finding in findings:
        rule_id = str(finding.get("rule_id", ""))
        if not rule_id or rule_id in rule_index:
            continue
        rule_index[rule_id] = len(rules)
        rules.append(_rule_for(finding))

    results: list[dict[str, Any]] = []
    for finding in findings:
        rule_id = str(finding.get("rule_id", ""))
        index = rule_index.get(rule_id, -1)
        result = _result_for(finding, index, repo)
        result["properties"]["gate"] = gate.get("verdict")
        results.append(result)

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool.get("name", "CodeHealthMind"),
                        "version": tool.get("version", "1.0.0"),
                        "informationUri": INFORMATION_URI,
                        "rules": rules,
                    }
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": gate.get("verdict") != "UNKNOWN",
                        "exitCode": int(gate.get("exit_code", 0) or 0),
                        "toolExecutionNotifications": [
                            {
                                "level": "error" if error.get("evidence_gap") else "warning",
                                "message": {
                                    "text": (
                                        f"{error.get('provider')}: {error.get('kind')} -- "
                                        f"{error.get('detail')}"
                                    )
                                },
                                "properties": {
                                    "evidenceGap": bool(error.get("evidence_gap")),
                                },
                            }
                            for error in (report.get("tool_errors") or [])
                        ],
                    }
                ],
                "properties": {
                    "gate": gate.get("verdict"),
                    "score": summary.get("score", 0.0),
                    "runId": run.get("run_id"),
                    "schemaVersion": report.get("schema_version"),
                },
            }
        ],
    }


# --------------------------------------------------------------------------
# self-check
# --------------------------------------------------------------------------

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def validate_sarif(doc: dict[str, Any]) -> list[str]:
    """Return a list of conformance problems; empty means valid."""
    problems: list[str] = []

    if not isinstance(doc, dict):
        return ["document is not an object"]
    if doc.get("version") != SARIF_VERSION:
        problems.append(f"version must be {SARIF_VERSION}, got {doc.get('version')!r}")
    if not doc.get("$schema"):
        problems.append("$schema is required")

    runs = doc.get("runs")
    if not isinstance(runs, list) or not runs:
        problems.append("runs must be a non-empty array")
        return problems

    run = runs[0]
    if not isinstance(run, dict):
        return problems + ["runs[0] must be an object"]

    driver = ((run.get("tool") or {}).get("driver")) if isinstance(run.get("tool"), dict) else None
    if not isinstance(driver, dict):
        problems.append("runs[0].tool.driver is required")
        driver = {}
    for field in ("name", "version", "informationUri"):
        if not driver.get(field):
            problems.append(f"runs[0].tool.driver.{field} is required")
    if driver.get("name") != "CodeHealthMind":
        problems.append(f"runs[0].tool.driver.name must be 'CodeHealthMind', got {driver.get('name')!r}")

    rules = driver.get("rules")
    if not isinstance(rules, list):
        problems.append("runs[0].tool.driver.rules must be an array")
        rules = []
    known_rules: set[str] = set()
    for index, rule in enumerate(rules):
        where = f"runs[0].tool.driver.rules[{index}]"
        if not isinstance(rule, dict):
            problems.append(f"{where} must be an object")
            continue
        rule_id = rule.get("id")
        if not rule_id:
            problems.append(f"{where}.id is required")
        elif rule_id in known_rules:
            problems.append(f"{where}.id {rule_id!r} is duplicated")
        else:
            known_rules.add(str(rule_id))
        if not rule.get("name"):
            problems.append(f"{where}.name is required")
        short = rule.get("shortDescription")
        if not isinstance(short, dict) or not short.get("text"):
            problems.append(f"{where}.shortDescription.text is required")
        level = ((rule.get("defaultConfiguration") or {}).get("level")) if isinstance(
            rule.get("defaultConfiguration"), dict
        ) else None
        if level not in _LEVELS:
            problems.append(f"{where}.defaultConfiguration.level {level!r} is not a SARIF level")
        tags = ((rule.get("properties") or {}).get("tags")) if isinstance(
            rule.get("properties"), dict
        ) else None
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            problems.append(f"{where}.properties.tags must be an array of strings")

    results = run.get("results")
    if not isinstance(results, list):
        problems.append("runs[0].results must be an array")
        return problems

    for index, result in enumerate(results):
        where = f"runs[0].results[{index}]"
        if not isinstance(result, dict):
            problems.append(f"{where} must be an object")
            continue

        rule_id = result.get("ruleId")
        if not rule_id:
            problems.append(f"{where}.ruleId is required")
        elif str(rule_id) not in known_rules:
            problems.append(f"{where}.ruleId {rule_id!r} has no matching rule")

        if result.get("level") not in _LEVELS:
            problems.append(f"{where}.level {result.get('level')!r} is not a SARIF level")

        message = result.get("message")
        if not isinstance(message, dict) or not message.get("text"):
            problems.append(f"{where}.message.text is required")

        locations = result.get("locations")
        if not isinstance(locations, list) or not locations:
            problems.append(f"{where}.locations must be a non-empty array")
            continue

        physical = ((locations[0] or {}).get("physicalLocation")) if isinstance(locations[0], dict) else None
        if not isinstance(physical, dict):
            problems.append(f"{where}.locations[0].physicalLocation is required")
            continue

        artifact = physical.get("artifactLocation")
        if not isinstance(artifact, dict) or not artifact.get("uri"):
            problems.append(f"{where}.locations[0].physicalLocation.artifactLocation.uri is required")
        else:
            uri = str(artifact["uri"])
            if "\\" in uri:
                problems.append(f"{where}: uri {uri!r} must use forward slashes")
            if uri.startswith("/"):
                problems.append(f"{where}: uri {uri!r} must be relative")
            if _DRIVE_RE.match(uri):
                problems.append(f"{where}: uri {uri!r} must not contain a drive letter")

        region = physical.get("region")
        if not isinstance(region, dict):
            problems.append(f"{where}.locations[0].physicalLocation.region is required")
            continue
        start = region.get("startLine")
        end = region.get("endLine")
        if not isinstance(start, int) or start < 1:
            problems.append(f"{where}: region.startLine must be an int >= 1, got {start!r}")
            continue
        if not isinstance(end, int) or end < start:
            problems.append(f"{where}: region.endLine must be an int >= startLine, got {end!r}")

    return problems
