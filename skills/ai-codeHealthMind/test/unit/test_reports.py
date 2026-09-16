"""Reports: byte-level determinism, console fields, SARIF conformance, MD grouping."""

from __future__ import annotations

import unittest

import helpers
from helpers import evidence, make_config, make_finding

from chm.core.dedup import deduplicate
from chm.core.gate import evaluate_gate
from chm.core.ledger import RunLedger
from chm.core.score import score_findings
from chm.errors import ToolError, ToolFailureKind, ToolStatus
from chm.contracts import ProviderResult
from chm.reports.console import render_console
from chm.reports.json_report import build_report, relative_uri, render_json
from chm.reports.markdown import render_markdown
from chm.reports.sarif import SEVERITY_LEVEL, level_for, render_sarif, validate_sarif
from chm.schema import Category, Severity

REPO = "E:/workA/A-skill/A-github-skill-mcp/code-mind/skills/ai-codeHealthMind"


def _build() -> dict:
    findings = [
        make_finding(
            "CHM-000001",
            rule_id="CHM-JAVA-TX-NO-WHERE",
            category=Category.DATABASE,
            severity=Severity.CRITICAL,
            title="UPDATE without WHERE",
            file="src/main/java/db/Repo.java",
            start_line=42,
            introduced=True,
            evidence=[evidence("native-java"), evidence("pmd")],
        ),
        make_finding(
            "CHM-000002",
            rule_id="CHM-JAVA-RESOURCE-LEAK",
            category=Category.RESOURCE_SAFETY,
            severity=Severity.HIGH,
            title="stream never closed",
            file="src/main/java/io/Reader.java",
            start_line=18,
            introduced=True,
            evidence=[evidence("spotbugs")],
        ),
        make_finding(
            "CHM-000003",
            rule_id="CHM-JAVA-COMPLEXITY-001",
            category=Category.COMPLEXITY,
            severity=Severity.MEDIUM,
            title="cyclomatic complexity 24",
            file="src/main/java/svc/Order.java",
            start_line=77,
            introduced=False,
            historical=True,
        ),
        make_finding(
            "CHM-000004",
            rule_id="CHM-JAVA-DUP-001",
            category=Category.DUPLICATION,
            severity=Severity.LOW,
            title="42 duplicated tokens",
            file="src/main/java/svc/Copy.java",
            start_line=5,
            introduced=False,
            historical=True,
            evidence=[evidence("cpd")],
        ),
    ]
    cfg = make_config()
    dedup = deduplicate(findings, config=cfg)
    score = score_findings(findings, config=cfg)
    gate = evaluate_gate(findings, score=score, config=cfg)
    ledger = RunLedger(
        run_id="20260915T120000-abcdef",
        repo=REPO,
        commit="deadbeef",
        base="HEAD~1",
        mode="diff",
        duration_ms=1234,
        findings=len(findings),
        dedup_ratio=dedup.dedup_ratio,
        gate=gate.verdict.value,
    )
    ledger.add_tool("pmd", 900, "OK")
    tool_results = [
        ProviderResult(
            provider="pmd",
            status=ToolStatus.OK,
            duration_ms=900,
            command="java -cp pmd.jar net.sourceforge.pmd.PMD -R rules",
            version="6.55.0",
        ),
        ProviderResult(
            provider="semgrep",
            status=ToolStatus.UNAVAILABLE,
            error=ToolError(
                provider="semgrep",
                kind=ToolFailureKind.MISSING,
                detail="semgrep is not installed on this host",
                evidence_gap=True,
            ),
        ),
    ]
    return build_report(
        run_id=ledger.run_id,
        mode="diff",
        ctx_dict={"repo_root": REPO, "changed_files": [{"path": "a"}, {"path": "b"}]},
        findings=findings,
        score=score,
        gate=gate,
        dedup=dedup,
        tool_results=tool_results,
        tool_errors=[tool_results[1].error],
        ledger=ledger,
        baseline_delta={
            "baseline": {"score": 80.0},
            "current": {"score": score.total},
            "delta": {"score": round(score.total - 80.0, 1)},
        },
        extra={
            "new_findings": ["CHM-000001", "CHM-000002"],
            "resolved_findings": ["CHM-000009"],
            "preexisting_findings": ["CHM-000003", "CHM-000004"],
        },
    )


class DeterminismTest(unittest.TestCase):
    def test_render_json_is_byte_identical_across_three_runs(self):
        report = _build()
        outputs = {render_json(report) for _ in range(3)}
        self.assertEqual(len(outputs), 1)

    def test_render_markdown_is_byte_identical_across_three_runs(self):
        report = _build()
        outputs = {render_markdown(report) for _ in range(3)}
        self.assertEqual(len(outputs), 1)

    def test_render_sarif_is_byte_identical_across_three_runs(self):
        import json

        report = _build()
        outputs = {json.dumps(render_sarif(report), sort_keys=True) for _ in range(3)}
        self.assertEqual(len(outputs), 1)

    def test_no_timestamp_in_the_decision_blocks(self):
        import json

        payload = json.loads(render_json(_build()))
        for key in ("score", "gate", "dedup", "findings", "summary", "baseline", "tools"):
            with self.subTest(block=key):
                block = json.dumps(payload[key])
                self.assertNotIn("started_at", block)
                self.assertNotIn("duration_ms", block)

    def test_volatile_fields_are_confined_to_run_and_ledger(self):
        """Documents *where* the non-deterministic data lives (see spec §41)."""
        import json

        payload = json.loads(render_json(_build()))
        self.assertIn("run_id", payload["run"])
        self.assertNotIn("duration_ms", payload["run"])
        self.assertNotIn("started_at", payload["ledger"])
        self.assertNotIn("duration_ms", payload["ledger"])

    def test_two_independent_builds_of_the_same_input_match(self):
        self.assertEqual(render_json(_build()), render_json(_build()))


class ConsoleTest(unittest.TestCase):
    def setUp(self):
        self.text = render_console(_build(), color=False)

    def test_required_field_names_are_present(self):
        for field in (
            "Changed files:",
            "Findings:",
            "Critical:",
            "High:",
            "Medium:",
            "Low:",
            "Gate:",
            "Top issue:",
        ):
            with self.subTest(field=field):
                self.assertIn(field, self.text)

    def test_counts_are_real(self):
        self.assertIn("Changed files: 2", self.text)
        self.assertIn("Findings: 4", self.text)
        self.assertIn("Critical: 1", self.text)
        self.assertIn("High: 1", self.text)
        self.assertIn("Medium: 1", self.text)
        self.assertIn("Low: 1", self.text)

    def test_verdict_is_shown(self):
        self.assertIn("Gate: BLOCK", self.text)

    def test_top_issue_is_the_worst_one(self):
        self.assertIn("CHM-000001", self.text)

    def test_no_ansi_escapes_when_color_is_off(self):
        self.assertNotIn("\033[", self.text)

    def test_color_adds_escapes(self):
        colored = render_console(_build(), color=True)
        self.assertIn("\033[", colored)

    def test_verbose_shows_score_and_tools(self):
        verbose = render_console(_build(), verbose=True, color=False)
        for field in ("Score:", "Total:", "Gate detail:", "Dedup:", "Tools:", "Tool errors:"):
            with self.subTest(field=field):
                self.assertIn(field, verbose)
        self.assertIn("semgrep", verbose)


class SarifTest(unittest.TestCase):
    def setUp(self):
        self.report = _build()
        self.doc = render_sarif(self.report)

    def test_validates_clean(self):
        self.assertEqual(validate_sarif(self.doc), [])

    def test_version_and_schema(self):
        self.assertEqual(self.doc["version"], "2.1.0")
        self.assertIn("sarif", self.doc["$schema"])

    def test_level_mapping(self):
        self.assertEqual(level_for("CRITICAL"), "error")
        self.assertEqual(level_for("HIGH"), "error")
        self.assertEqual(level_for("MEDIUM"), "warning")
        self.assertEqual(level_for("LOW"), "note")
        self.assertEqual(
            SEVERITY_LEVEL,
            {"CRITICAL": "error", "HIGH": "error", "MEDIUM": "warning", "LOW": "note"},
        )

    def test_results_carry_the_mapped_levels(self):
        by_id = {r["properties"]["findingId"]: r for r in self.doc["runs"][0]["results"]}
        self.assertEqual(by_id["CHM-000001"]["level"], "error")
        self.assertEqual(by_id["CHM-000002"]["level"], "error")
        self.assertEqual(by_id["CHM-000003"]["level"], "warning")
        self.assertEqual(by_id["CHM-000004"]["level"], "note")

    def test_every_result_has_a_matching_rule(self):
        rules = {r["id"] for r in self.doc["runs"][0]["tool"]["driver"]["rules"]}
        for result in self.doc["runs"][0]["results"]:
            self.assertIn(result["ruleId"], rules)

    def test_uris_are_relative_and_posix(self):
        for result in self.doc["runs"][0]["results"]:
            uri = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            self.assertNotIn("\\", uri)
            self.assertFalse(uri.startswith("/"))
            self.assertNotIn(":", uri)

    def test_region_bounds_are_valid(self):
        for result in self.doc["runs"][0]["results"]:
            region = result["locations"][0]["physicalLocation"]["region"]
            self.assertGreaterEqual(region["startLine"], 1)
            self.assertGreaterEqual(region["endLine"], region["startLine"])

    def test_evidence_gap_becomes_a_notification(self):
        notifications = self.doc["runs"][0]["invocations"][0]["toolExecutionNotifications"]
        self.assertEqual(len(notifications), 1)
        self.assertTrue(notifications[0]["properties"]["evidenceGap"])
        self.assertEqual(notifications[0]["level"], "error")

    def test_validator_catches_a_broken_uri(self):
        broken = render_sarif(self.report)
        broken["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"][
            "uri"
        ] = "C:\\abs\\path.java"
        problems = validate_sarif(broken)
        self.assertTrue(any("forward slashes" in p or "drive letter" in p or "relative" in p for p in problems))

    def test_validator_catches_an_unknown_rule_id(self):
        broken = render_sarif(self.report)
        broken["runs"][0]["results"][0]["ruleId"] = "CHM-NOT-DECLARED"
        problems = validate_sarif(broken)
        self.assertTrue(any("no matching rule" in p for p in problems))

    def test_relative_uri_strips_repo_prefix_and_drive(self):
        self.assertEqual(relative_uri("E:\\proj\\src\\A.java", "E:\\proj"), "src/A.java")
        self.assertEqual(relative_uri("src/main/java/A.java", REPO), "src/main/java/A.java")
        self.assertEqual(relative_uri("./src/A.java"), "src/A.java")


class MarkdownTest(unittest.TestCase):
    def setUp(self):
        self.text = render_markdown(_build())

    def test_has_both_grouping_sections(self):
        self.assertIn("## Findings introduced by this change", self.text)
        self.assertIn("## Pre-existing / historical debt", self.text)

    def test_introduced_and_historical_are_separated(self):
        introduced_block = self.text.split("## Findings introduced by this change", 1)[1]
        introduced_block = introduced_block.split("## Pre-existing / historical debt", 1)[0]
        # bound the historical block at the next section so the score deductions
        # table (which names every finding) cannot leak into it
        historical_block = self.text.split("## Pre-existing / historical debt", 1)[1]
        historical_block = historical_block.split("## Resolved since baseline", 1)[0]

        self.assertIn("CHM-000001", introduced_block)
        self.assertIn("CHM-000002", introduced_block)
        self.assertNotIn("CHM-000003", introduced_block)
        self.assertNotIn("CHM-000004", introduced_block)

        self.assertIn("CHM-000003", historical_block)
        self.assertIn("CHM-000004", historical_block)
        self.assertNotIn("CHM-000001", historical_block)
        self.assertNotIn("CHM-000002", historical_block)

    def test_core_sections_exist(self):
        for heading in (
            "## Gate",
            "## Score",
            "## Tools",
            "## Tool errors",
            "## Baseline delta",
            "## Deduplication",
            "## Resolved since baseline",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.text)

    def test_hard_gate_warning_is_present(self):
        self.assertIn("**Hard gate tripped**", self.text)

    def test_score_table_lists_every_dimension(self):
        for dimension in (
            "Correctness",
            "Simplicity",
            "Maintainability",
            "Duplication",
            "Complexity",
            "Dead Code",
            "Performance",
            "Concurrency",
            "Resource Safety",
            "Testability",
        ):
            with self.subTest(dimension=dimension):
                self.assertIn(f"| {dimension} |", self.text)

    def test_tool_error_is_reported_with_its_gap(self):
        self.assertIn("semgrep", self.text)
        self.assertIn("| yes |", self.text)

    def test_pipes_in_titles_are_escaped(self):
        report = _build()
        report["findings"][0]["title"] = "a | b"
        text = render_markdown(report)
        self.assertIn("a \\| b", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
