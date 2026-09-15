"""Spec §47 gate decision matrix -- asserted row by row."""

from __future__ import annotations

import unittest

import helpers
from helpers import make_config, make_finding

from chm.core.gate import TODAY_ENV, evaluate_gate, exit_code_for
from chm.core.score import score_findings
from chm.errors import ToolError, ToolFailureKind
from chm.schema import Category, EXIT_CODES, FindingStatus, GateVerdict, Severity


def _gate(findings, *, config=None, score=None, **kwargs):
    cfg = config if config is not None else make_config()
    if score is None:
        score = score_findings(findings, config=cfg)
    return evaluate_gate(findings, score=score, config=cfg, **kwargs)


class MatrixTest(unittest.TestCase):
    """The published verdict matrix, one test per row."""

    def test_compile_fail_blocks(self):
        result = _gate([], compile_ok=False)
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("compilation failed", result.blockers)

    def test_unit_fail_blocks(self):
        result = _gate([], test_ok=False)
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("unit tests failed", result.blockers)

    def test_critical_finding_blocks(self):
        finding = make_finding("CHM-000001", severity=Severity.CRITICAL, category=Category.DATABASE)
        result = _gate([finding])
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.exit_code, 1)
        self.assertTrue(any("CRITICAL" in b for b in result.blockers))

    def test_high_finding_blocks(self):
        finding = make_finding("CHM-000001", severity=Severity.HIGH, category=Category.RESOURCE_SAFETY)
        result = _gate([finding])
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.exit_code, 1)

    def test_medium_within_threshold_warns(self):
        findings = [
            make_finding(
                f"CHM-{i:06d}", severity=Severity.MEDIUM, introduced=True, category=Category.COMPLEXITY
            )
            for i in range(1, 6)  # 5 == gates.max_new_medium
        ]
        result = _gate(findings)
        self.assertEqual(result.verdict, GateVerdict.WARN)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.blockers, [])

    def test_medium_over_threshold_blocks(self):
        findings = [
            make_finding(
                f"CHM-{i:06d}", severity=Severity.MEDIUM, introduced=True, category=Category.COMPLEXITY
            )
            for i in range(1, 7)  # 6 > 5
        ]
        result = _gate(findings)
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.exit_code, 1)
        self.assertTrue(any("max_new_medium=5" in b for b in result.blockers))

    def test_only_low_passes(self):
        finding = make_finding("CHM-000001", severity=Severity.LOW, introduced=True)
        result = _gate([finding])
        self.assertEqual(result.verdict, GateVerdict.PASS)
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.tool_degraded)

    def test_tool_degraded_without_gap_warns(self):
        err = ToolError(
            provider="pmd",
            kind=ToolFailureKind.NONZERO_EXIT,
            detail="pmd exited 4",
            evidence_gap=False,
        )
        result = _gate([], tool_errors=[err])
        self.assertEqual(result.verdict, GateVerdict.WARN)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.tool_degraded)
        self.assertFalse(result.evidence_gap)

    def test_tool_gap_affecting_high_critical_is_unknown(self):
        err = ToolError(
            provider="pmd",
            kind=ToolFailureKind.MISSING,
            detail="pmd distribution not found",
            evidence_gap=True,
        )
        result = _gate([], tool_errors=[err])
        self.assertEqual(result.verdict, GateVerdict.UNKNOWN)
        self.assertEqual(result.exit_code, 3)
        self.assertTrue(result.evidence_gap)
        self.assertTrue(any("not evidence of absence" in r for r in result.reasons))

    def test_exit_codes_match_the_published_table(self):
        self.assertEqual(EXIT_CODES[GateVerdict.PASS], 0)
        self.assertEqual(EXIT_CODES[GateVerdict.WARN], 0)
        self.assertEqual(EXIT_CODES[GateVerdict.BLOCK], 1)
        self.assertEqual(EXIT_CODES[GateVerdict.UNKNOWN], 3)
        self.assertEqual(exit_code_for(GateVerdict.PASS), 0)
        self.assertEqual(exit_code_for(GateVerdict.UNKNOWN), 3)


class ScoreCannotRescueTest(unittest.TestCase):
    def test_high_total_does_not_cancel_a_critical(self):
        finding = make_finding("CHM-000001", severity=Severity.CRITICAL, category=Category.DATABASE)
        perfect_score = score_findings([], config=make_config())
        self.assertEqual(perfect_score.total, 100.0)
        result = _gate([finding], score=perfect_score)
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.exit_code, 1)

    def test_low_never_blocks(self):
        findings = [
            make_finding(f"CHM-{i:06d}", severity=Severity.LOW, introduced=True)
            for i in range(1, 30)
        ]
        result = _gate(findings)
        self.assertEqual(result.verdict, GateVerdict.PASS)

    def test_medium_budget_override_is_honoured(self):
        findings = [
            make_finding(f"CHM-{i:06d}", severity=Severity.MEDIUM, introduced=True)
            for i in range(1, 4)
        ]
        cfg = make_config(**{"gates.max_new_medium": 1})
        result = _gate(findings, config=cfg)
        self.assertEqual(result.verdict, GateVerdict.BLOCK)

    def test_min_score_gate(self):
        # one MEDIUM COMPLEXITY costs 10 x 0.3 = 3.0 -> total 97.0
        cfg = make_config(**{"gates.min_score": 99.0})
        finding = make_finding("CHM-000001", severity=Severity.MEDIUM, category=Category.COMPLEXITY)
        result = _gate([finding], config=cfg)
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertTrue(any("min_score" in b for b in result.blockers))

    def test_min_score_not_triggered_when_above(self):
        cfg = make_config(**{"gates.min_score": 90.0})
        finding = make_finding("CHM-000001", severity=Severity.MEDIUM, category=Category.COMPLEXITY)
        result = _gate([finding], config=cfg)
        self.assertEqual(result.verdict, GateVerdict.WARN)


class AcceptedRiskTest(unittest.TestCase):
    def test_live_risk_suppresses_the_blocker(self):
        finding = make_finding("CHM-000001", severity=Severity.HIGH, category=Category.RESOURCE_SAFETY)
        cfg = make_config()
        from chm.config import AcceptedRisk

        cfg.accepted_risks = [
            AcceptedRisk(finding_id="CHM-000001", reason="legacy", owner="team", expires="2030-01-01")
        ]
        result = _gate([finding], config=cfg, today="2026-09-15")
        self.assertNotEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.verdict, GateVerdict.PASS)

    def test_expired_risk_becomes_a_blocker_again(self):
        finding = make_finding("CHM-000001", severity=Severity.HIGH, category=Category.RESOURCE_SAFETY)
        cfg = make_config()
        from chm.config import AcceptedRisk

        cfg.accepted_risks = [
            AcceptedRisk(finding_id="CHM-000001", reason="legacy", expires="2020-01-01")
        ]
        result = _gate([finding], config=cfg, today="2026-09-15")
        self.assertEqual(result.verdict, GateVerdict.BLOCK)
        self.assertEqual(result.exit_code, 1)
        self.assertTrue(any("HIGH" in b for b in result.blockers))

    def test_today_env_var_is_respected(self):
        finding = make_finding("CHM-000001", severity=Severity.HIGH)
        cfg = make_config()
        from chm.config import AcceptedRisk

        cfg.accepted_risks = [AcceptedRisk(finding_id="CHM-000001", expires="2026-01-01")]
        import os

        os.environ[TODAY_ENV] = "2025-01-01"
        try:
            result = _gate([finding], config=cfg)
            self.assertNotEqual(result.verdict, GateVerdict.BLOCK)
        finally:
            os.environ.pop(TODAY_ENV, None)

    def test_closed_finding_does_not_block(self):
        finding = make_finding(
            "CHM-000001", severity=Severity.CRITICAL, status=FindingStatus.FALSE_POSITIVE
        )
        result = _gate([finding])
        self.assertEqual(result.verdict, GateVerdict.PASS)

    def test_explicitly_accepted_list_does_not_block(self):
        finding = make_finding("CHM-000001", severity=Severity.HIGH)
        result = _gate([finding], accepted=[finding])
        self.assertEqual(result.verdict, GateVerdict.PASS)


class BaselineBudgetTest(unittest.TestCase):
    def test_historical_medium_debt_warns_but_does_not_block(self):
        findings = [
            make_finding(f"CHM-{i:06d}", severity=Severity.MEDIUM, introduced=False)
            for i in range(1, 50)
        ]
        result = _gate(findings, new_findings=[])
        self.assertEqual(result.verdict, GateVerdict.WARN)
        self.assertEqual(result.exit_code, 0)

    def test_explicit_new_findings_drive_the_budget(self):
        historical = make_finding("CHM-000001", severity=Severity.MEDIUM, introduced=False)
        new = make_finding("CHM-000002", severity=Severity.MEDIUM, introduced=True)
        result = _gate([historical, new], new_findings=[new])
        self.assertEqual(result.verdict, GateVerdict.WARN)

    def test_too_many_explicit_new_findings_blocks(self):
        historical = [make_finding(f"CHM-{i:06d}", severity=Severity.MEDIUM) for i in range(1, 3)]
        new = [make_finding(f"CHM-{i:06d}", severity=Severity.MEDIUM) for i in range(3, 10)]
        result = _gate(historical + new, new_findings=new)
        self.assertEqual(result.verdict, GateVerdict.BLOCK)


class GateResultShapeTest(unittest.TestCase):
    def test_to_dict_has_the_contract_fields(self):
        payload = _gate([]).to_dict()
        for key in (
            "verdict",
            "exit_code",
            "reasons",
            "blockers",
            "score",
            "tool_degraded",
            "evidence_gap",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["verdict"], "PASS")

    def test_verdict_value_is_serialised_as_string(self):
        finding = make_finding("CHM-000001", severity=Severity.CRITICAL)
        self.assertEqual(_gate([finding]).to_dict()["verdict"], "BLOCK")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
