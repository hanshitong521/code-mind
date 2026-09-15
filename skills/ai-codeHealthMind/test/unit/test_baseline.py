"""Spec §30 baseline capture and diffing: historical debt vs new debt."""

from __future__ import annotations

import unittest

import helpers
from helpers import make_config, make_finding

from chm.core.baseline import (
    BASELINE_SCHEMA_VERSION,
    BaselineMetrics,
    classify_against_baseline,
    collect_metrics,
    compute_delta,
    load_baseline,
    save_baseline,
)
from chm.core.gate import evaluate_gate
from chm.core.score import score_findings
from chm.schema import Category, GateVerdict, Severity


def _medium_debt(count: int, *, prefix: str = "src/main/java/Debt") -> list:
    """``count`` distinct MEDIUM findings (distinct canonical keys)."""
    return [
        make_finding(
            f"CHM-{i:06d}",
            rule_id="CHM-JAVA-COMPLEXITY-001",
            category=Category.COMPLEXITY,
            severity=Severity.MEDIUM,
            file=f"{prefix}{i}.java",
            start_line=10 + i,
            introduced=False,
        )
        for i in range(1, count + 1)
    ]


class BaselineMetricsTest(unittest.TestCase):
    def test_collect_counts_by_category_and_severity(self):
        findings = helpers.sample_findings()
        metrics = collect_metrics(findings, config=make_config())
        # sample: 1 DATABASE(critical) 1 RESOURCE(high) 1 COMPLEXITY(medium) 1 DUP(low) 1 DEAD(low)
        self.assertEqual(metrics.warnings, 3)  # every severity except LOW
        self.assertEqual(metrics.dead_code, 1)
        self.assertEqual(metrics.complexity, 1)
        self.assertEqual(len(metrics.findings), 5)

    def test_captured_at_is_none_for_determinism(self):
        metrics = collect_metrics(helpers.sample_findings(), config=make_config())
        self.assertIsNone(metrics.captured_at)

    def test_finding_identities_are_sorted(self):
        metrics = collect_metrics(helpers.sample_findings(), config=make_config())
        self.assertEqual(metrics.findings, sorted(metrics.findings))

    def test_snapshots_are_stored_for_naming_resolved_findings(self):
        metrics = collect_metrics(helpers.sample_findings(), config=make_config())
        self.assertEqual(len(metrics.entries), 5)
        self.assertTrue(all("location" in e for e in metrics.entries))

    def test_excluded_and_generated_paths_are_not_project_debt(self):
        findings = [
            make_finding("CHM-000001", file="node_modules/lib/x.js", severity=Severity.MEDIUM),
            make_finding("CHM-000002", file="src/app/app.min.js", severity=Severity.MEDIUM),
            make_finding("CHM-000003", file="src/main/java/A.java", severity=Severity.MEDIUM),
        ]
        metrics = collect_metrics(findings, config=make_config())
        self.assertEqual(len(metrics.findings), 1)
        self.assertEqual(metrics.warnings, 1)

    def test_to_dict_round_trip(self):
        metrics = collect_metrics(helpers.sample_findings(), config=make_config())
        restored = BaselineMetrics.from_dict(metrics.to_dict())
        self.assertEqual(restored.to_dict(), metrics.to_dict())
        self.assertEqual(restored.to_dict()["schema_version"], BASELINE_SCHEMA_VERSION)

    def test_legacy_baseline_without_entries_still_loads(self):
        legacy = {
            "complexity": 3,
            "duplication_pct": 12.5,
            "warnings": 7,
            "dead_code": 1,
            "findings": ["{}"],
            "score": 88.0,
        }
        restored = BaselineMetrics.from_dict(legacy)
        self.assertEqual(restored.complexity, 3)
        self.assertEqual(restored.entries, [])


class PersistenceTest(helpers.CHMTestCase):
    def test_save_and_load_round_trip(self):
        path = self.temp_dir() / "baseline.json"
        metrics = collect_metrics(helpers.sample_findings(), config=make_config())
        save_baseline(path, metrics)
        self.assertTrue(path.is_file())
        loaded = load_baseline(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.to_dict(), metrics.to_dict())

    def test_missing_baseline_is_not_an_error(self):
        self.assertIsNone(load_baseline(self.temp_dir() / "nope.json"))

    def test_malformed_baseline_is_not_an_error(self):
        path = self.temp_dir() / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(load_baseline(path))


class ClassifyTest(unittest.TestCase):
    def test_preexisting_findings_are_marked_historical(self):
        baseline_findings = _medium_debt(3)
        baseline = collect_metrics(baseline_findings, config=make_config())

        current = _medium_debt(3)
        new, resolved, preexisting = classify_against_baseline(current, baseline)

        self.assertEqual(new, [])
        self.assertEqual(len(preexisting), 3)
        self.assertTrue(all(f.historical for f in preexisting))
        self.assertEqual(resolved, [])

    def test_new_findings_are_separated(self):
        baseline = collect_metrics(_medium_debt(3), config=make_config())
        current = _medium_debt(3) + [
            make_finding(
                "CHM-900001",
                rule_id="CHM-JAVA-RESOURCE-LEAK",
                category=Category.RESOURCE_SAFETY,
                severity=Severity.HIGH,
                file="src/main/java/New.java",
                start_line=5,
                introduced=True,
            )
        ]
        new, resolved, preexisting = classify_against_baseline(current, baseline)
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0].id, "CHM-900001")
        self.assertEqual(len(preexisting), 3)

    def test_resolved_findings_are_named_from_snapshots(self):
        baseline = collect_metrics(_medium_debt(3), config=make_config())
        current = _medium_debt(3)[:2]
        new, resolved, preexisting = classify_against_baseline(current, baseline)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].rule_id, "CHM-JAVA-COMPLEXITY-001")
        self.assertNotIn("no snapshot recorded", resolved[0].title)

    def test_untracked_and_untouched_finding_is_preexisting(self):
        baseline = collect_metrics([], config=make_config())
        current = _medium_debt(1)  # introduced=False, not in baseline
        new, _, preexisting = classify_against_baseline(current, baseline)
        self.assertEqual(new, [])
        self.assertEqual(len(preexisting), 1)

    def test_no_baseline_means_everything_is_new_if_introduced(self):
        current = [
            make_finding("CHM-000001", severity=Severity.HIGH, introduced=True),
        ]
        new, resolved, preexisting = classify_against_baseline(current, None)
        self.assertEqual(len(new), 1)
        self.assertEqual(resolved, [])
        self.assertEqual(preexisting, [])


class DeltaStructureTest(unittest.TestCase):
    def test_no_baseline_yields_null_delta(self):
        current = collect_metrics(_medium_debt(2), config=make_config())
        delta = compute_delta(None, current)
        self.assertIsNone(delta["baseline"])
        self.assertIsNone(delta["delta"])
        self.assertEqual(delta["current"]["warnings"], 2)

    def test_delta_block_shape(self):
        baseline = collect_metrics(_medium_debt(5), config=make_config())
        current = collect_metrics(_medium_debt(3), config=make_config())
        delta = compute_delta(baseline, current)
        self.assertEqual(
            sorted(delta),
            ["baseline", "current", "delta"],
        )
        for block in ("baseline", "current"):
            self.assertEqual(
                sorted(delta[block]),
                ["complexity", "dead_code", "duplication_pct", "findings", "score", "warnings"],
            )
        self.assertEqual(
            sorted(delta["delta"]),
            ["complexity", "dead_code", "duplication_pct", "findings", "score", "warnings"],
        )
        self.assertEqual(delta["delta"]["findings"], -2)
        self.assertEqual(delta["delta"]["warnings"], -2)


class AcceptanceScenarioTest(unittest.TestCase):
    """BL-001 / BL-002 / BL-003 from spec §30."""

    def _gate(self, findings, baseline_metrics):
        new, _resolved, _preexisting = classify_against_baseline(findings, baseline_metrics)
        score = score_findings(findings, config=make_config())
        return evaluate_gate(
            findings,
            score=score,
            config=make_config(),
            new_findings=new,
            today="2026-09-15",
        )

    def test_bl_001_existing_warnings_without_new_debt_warns(self):
        baseline_findings = _medium_debt(100)
        baseline = collect_metrics(baseline_findings, config=make_config())
        self.assertEqual(baseline.warnings, 100)

        current = _medium_debt(100)
        result = self._gate(current, baseline)
        self.assertEqual(result.verdict, GateVerdict.WARN)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.blockers, [])

    def test_bl_002_two_new_high_findings_block(self):
        baseline = collect_metrics(_medium_debt(100), config=make_config())
        current = _medium_debt(100) + [
            make_finding(
                "CHM-800001",
                rule_id="CHM-JAVA-RESOURCE-LEAK",
                category=Category.RESOURCE_SAFETY,
                severity=Severity.HIGH,
                file="src/main/java/New1.java",
                start_line=5,
                introduced=True,
            ),
            make_finding(
                "CHM-800002",
                rule_id="CHM-JAVA-RESOURCE-LEAK",
                category=Category.RESOURCE_SAFETY,
                severity=Severity.HIGH,
                file="src/main/java/New2.java",
                start_line=9,
                introduced=True,
            ),
        ]
        result = self._gate(current, baseline)
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.exit_code, 1)
        self.assertTrue(any("HIGH" in b for b in result.blockers))

    def test_bl_003_clearing_debt_improves_the_score(self):
        baseline_metrics = collect_metrics(_medium_debt(10), config=make_config())
        current_metrics = collect_metrics(_medium_debt(3), config=make_config())

        delta = compute_delta(baseline_metrics, current_metrics)
        self.assertGreater(delta["delta"]["score"], 0.0)
        self.assertGreater(current_metrics.score, baseline_metrics.score)
        # 10 MEDIUM COMPLEXITY findings saturate the 10-point Complexity budget
        # (10 x 0.3 = 3.0 each) -> the dimension floors at 0 and the total is 90.
        self.assertEqual(baseline_metrics.score, 90.0)
        # 3 of them cost 9.0 -> the dimension keeps 1.0 -> total 91.
        self.assertEqual(current_metrics.score, 91.0)
        self.assertEqual(delta["delta"]["score"], 1.0)
        self.assertEqual(delta["delta"]["findings"], -7)

    def test_bl_003_resolved_findings_are_named(self):
        baseline = collect_metrics(_medium_debt(10), config=make_config())
        current = _medium_debt(3)
        _new, resolved, _pre = classify_against_baseline(current, baseline)
        self.assertEqual(len(resolved), 7)
        for finding in resolved:
            self.assertTrue(finding.id.startswith("CHM-"))
            self.assertEqual(finding.rule_id, "CHM-JAVA-COMPLEXITY-001")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
