"""Spec §12 scoring: literal weights, hard gate, explainable deductions."""

from __future__ import annotations

import unittest

import helpers
from helpers import make_config, make_finding

from chm.core.score import (
    CATEGORY_DIMENSION,
    DIMENSIONS,
    SEVERITY_FRACTION,
    dimension_for,
    score_findings,
)
from chm.errors import ToolError, ToolFailureKind
from chm.schema import Category, Severity

#: spec §12, transcribed by hand -- this is the point of the test.
SPEC_WEIGHTS = {
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


class WeightTest(unittest.TestCase):
    def test_weights_match_spec_verbatim(self):
        self.assertEqual(DIMENSIONS, SPEC_WEIGHTS)

    def test_weights_sum_to_one_hundred(self):
        self.assertEqual(sum(DIMENSIONS.values()), 100.0)

    def test_ten_dimensions(self):
        self.assertEqual(len(DIMENSIONS), 10)

    def test_score_reports_the_same_weights(self):
        breakdown = score_findings([], config=make_config())
        self.assertEqual(breakdown.weights, SPEC_WEIGHTS)

    def test_every_category_maps_to_a_known_dimension(self):
        for category in Category:
            with self.subTest(category=category):
                self.assertIn(dimension_for(category), DIMENSIONS)

    def test_category_dimension_table_covers_all_categories(self):
        self.assertEqual(set(CATEGORY_DIMENSION), set(Category))

    def test_severity_fractions(self):
        self.assertEqual(SEVERITY_FRACTION[Severity.CRITICAL], 1.0)
        self.assertEqual(SEVERITY_FRACTION[Severity.HIGH], 0.6)
        self.assertEqual(SEVERITY_FRACTION[Severity.MEDIUM], 0.3)
        self.assertEqual(SEVERITY_FRACTION[Severity.LOW], 0.1)


class TotalTest(unittest.TestCase):
    def test_clean_run_scores_one_hundred(self):
        breakdown = score_findings([], config=make_config())
        self.assertEqual(breakdown.total, 100.0)
        self.assertFalse(breakdown.hard_gate)
        self.assertEqual(breakdown.deductions, [])

    def test_critical_dead_code_costs_the_whole_dead_code_budget(self):
        finding = make_finding(
            "CHM-000001", category=Category.DEAD_CODE, severity=Severity.CRITICAL
        )
        breakdown = score_findings([finding], config=make_config())
        self.assertEqual(breakdown.dimensions["Dead Code"], 0.0)
        self.assertEqual(breakdown.total, 90.0)
        self.assertEqual(breakdown.deductions[0]["amount"], 10.0)
        self.assertEqual(breakdown.deductions[0]["dimension"], "Dead Code")

    def test_low_severity_costs_a_tenth(self):
        finding = make_finding("CHM-000001", category=Category.DEAD_CODE, severity=Severity.LOW)
        breakdown = score_findings([finding], config=make_config())
        self.assertEqual(breakdown.deductions[0]["amount"], 1.0)
        self.assertEqual(breakdown.dimensions["Dead Code"], 9.0)
        self.assertEqual(breakdown.total, 99.0)

    def test_dimension_floor_is_zero(self):
        findings = [
            make_finding(f"CHM-{i:06d}", category=Category.PERFORMANCE, severity=Severity.CRITICAL)
            for i in range(1, 5)
        ]
        breakdown = score_findings(findings, config=make_config())
        self.assertEqual(breakdown.dimensions["Performance"], 0.0)
        self.assertGreaterEqual(breakdown.total, 0.0)

    def test_score_weight_scales_the_deduction(self):
        finding = make_finding(
            "CHM-000001", category=Category.DEAD_CODE, severity=Severity.CRITICAL, score_weight=0.5
        )
        breakdown = score_findings([finding], config=make_config())
        self.assertEqual(breakdown.deductions[0]["amount"], 5.0)

    def test_deterministic_ordering_of_deductions(self):
        findings = [
            make_finding("CHM-000003", file="z.java", category=Category.DEAD_CODE, severity=Severity.LOW),
            make_finding("CHM-000001", file="a.java", category=Category.DEAD_CODE, severity=Severity.HIGH),
            make_finding("CHM-000002", file="a.java", category=Category.DEAD_CODE, severity=Severity.LOW),
        ]
        runs = [
            [d["finding_id"] for d in score_findings(findings, config=make_config()).deductions]
            for _ in range(3)
        ]
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[1], runs[2])
        self.assertEqual(runs[0], ["CHM-000001", "CHM-000002", "CHM-000003"])


class HardGateTest(unittest.TestCase):
    def test_critical_trips_the_hard_gate(self):
        finding = make_finding("CHM-000001", severity=Severity.CRITICAL, category=Category.DATABASE)
        breakdown = score_findings([finding], config=make_config())
        self.assertTrue(breakdown.hard_gate)
        self.assertTrue(any("CRITICAL" in r for r in breakdown.hard_gate_reasons))

    def test_high_trips_the_hard_gate(self):
        finding = make_finding("CHM-000001", severity=Severity.HIGH, category=Category.RESOURCE_SAFETY)
        breakdown = score_findings([finding], config=make_config())
        self.assertTrue(breakdown.hard_gate)
        self.assertTrue(any("HIGH" in r for r in breakdown.hard_gate_reasons))

    def test_compile_failure_trips_the_hard_gate(self):
        breakdown = score_findings([], config=make_config(), compile_ok=False)
        self.assertTrue(breakdown.hard_gate)
        self.assertIn("compilation failed (compile_ok=False)", breakdown.hard_gate_reasons)

    def test_test_failure_trips_the_hard_gate(self):
        breakdown = score_findings([], config=make_config(), test_ok=False)
        self.assertTrue(breakdown.hard_gate)
        self.assertIn("tests failed (test_ok=False)", breakdown.hard_gate_reasons)

    def test_compile_success_does_not_trip_it(self):
        breakdown = score_findings([], config=make_config(), compile_ok=True, test_ok=True)
        self.assertFalse(breakdown.hard_gate)

    def test_evidence_gap_trips_the_hard_gate(self):
        err = ToolError(
            provider="pmd",
            kind=ToolFailureKind.MISSING,
            detail="pmd not found",
            evidence_gap=True,
        )
        breakdown = score_findings([], config=make_config(), tool_errors=[err])
        self.assertTrue(breakdown.hard_gate)
        self.assertTrue(any("evidence gap" in r for r in breakdown.hard_gate_reasons))

    def test_degraded_tool_without_gap_does_not_trip_it(self):
        err = ToolError(
            provider="pmd",
            kind=ToolFailureKind.NONZERO_EXIT,
            detail="pmd exited 4",
            evidence_gap=False,
        )
        breakdown = score_findings([], config=make_config(), tool_errors=[err])
        self.assertFalse(breakdown.hard_gate)

    def test_medium_alone_does_not_trip_it(self):
        finding = make_finding("CHM-000001", severity=Severity.MEDIUM)
        breakdown = score_findings([finding], config=make_config())
        self.assertFalse(breakdown.hard_gate)


class ExplainabilityTest(unittest.TestCase):
    def test_every_deduction_names_its_source_finding(self):
        findings = helpers.sample_findings()
        breakdown = score_findings(findings, config=make_config())
        self.assertTrue(breakdown.deductions)
        for deduction in breakdown.deductions:
            self.assertIn("finding_id", deduction)
            self.assertTrue(deduction["finding_id"], f"missing source: {deduction}")
            self.assertTrue(deduction["reason"])
            self.assertIn("dimension", deduction)
            self.assertIn("amount", deduction)

    def test_deduction_ids_are_all_real_findings(self):
        findings = helpers.sample_findings()
        breakdown = score_findings(findings, config=make_config())
        ids = {f.id for f in findings}
        for deduction in breakdown.deductions:
            self.assertIn(deduction["finding_id"], ids)

    def test_deductions_sum_to_the_loss(self):
        findings = helpers.sample_findings()
        breakdown = score_findings(findings, config=make_config())
        loss = sum(d["amount"] for d in breakdown.deductions if d["finding_id"])
        self.assertAlmostEqual(round(100.0 - breakdown.total, 1), round(loss, 1), places=1)

    def test_round_trip_through_dict(self):
        from chm.core.score import score_from_dict

        findings = helpers.sample_findings()
        breakdown = score_findings(findings, config=make_config())
        restored = score_from_dict(breakdown.to_dict())
        self.assertEqual(restored.to_dict(), breakdown.to_dict())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
