"""Spec §4.3 / §18 risk router: scrutiny scales with risk, honestly."""

from __future__ import annotations

import unittest

import helpers
from helpers import changed_file, make_config, make_ctx, make_finding

from chm.core.riskrouter import RoutePlan, initial_risk, plan_route, risk_of
from chm.schema import Category, Severity


def _finding(severity: Severity, *, category: Category = Category.COMPLEXITY, ident: str = "CHM-000001"):
    return make_finding(ident, severity=severity, category=category)


class RiskOfTest(unittest.TestCase):
    def test_empty_is_low(self):
        self.assertEqual(risk_of([]), "LOW")

    def test_worst_severity_wins(self):
        findings = [
            _finding(Severity.LOW, ident="CHM-000001"),
            _finding(Severity.CRITICAL, category=Category.DATABASE, ident="CHM-000002"),
            _finding(Severity.MEDIUM, ident="CHM-000003"),
        ]
        self.assertEqual(risk_of(findings), "CRITICAL")

    def test_each_level(self):
        for severity, expected in (
            (Severity.LOW, "LOW"),
            (Severity.MEDIUM, "MEDIUM"),
            (Severity.HIGH, "HIGH"),
            (Severity.CRITICAL, "CRITICAL"),
        ):
            with self.subTest(severity=severity):
                self.assertEqual(risk_of([_finding(severity)]), expected)


class ReviewerCountTest(unittest.TestCase):
    def _plan(self, severity, **overrides):
        cfg = make_config(**overrides)
        ctx = make_ctx(helpers.repo_root())
        return plan_route([_finding(severity)], ctx, cfg)

    def test_low_gets_one_reviewer(self):
        plan = self._plan(Severity.LOW)
        self.assertEqual(plan.risk, "LOW")
        self.assertEqual(plan.reviewers, 1)
        self.assertFalse(plan.validator)
        self.assertTrue(plan.deterministic_only)

    def test_medium_gets_one_reviewer(self):
        plan = self._plan(Severity.MEDIUM)
        self.assertEqual(plan.risk, "MEDIUM")
        self.assertEqual(plan.reviewers, 1)
        self.assertFalse(plan.validator)

    def test_high_gets_two_reviewers_and_a_validator(self):
        plan = self._plan(Severity.HIGH)
        self.assertEqual(plan.risk, "HIGH")
        self.assertEqual(plan.reviewers, 2)
        self.assertTrue(plan.validator)
        self.assertFalse(plan.deterministic_only)

    def test_critical_gets_two_reviewers_and_a_validator(self):
        plan = self._plan(Severity.CRITICAL)
        self.assertEqual(plan.risk, "CRITICAL")
        self.assertEqual(plan.reviewers, 2)
        self.assertTrue(plan.validator)
        self.assertEqual(plan.expansion, "full_slice")

    def test_counts_follow_config(self):
        plan = self._plan(
            Severity.HIGH,
            **{"review.reviewers_high": 3, "review.validator_on_high": False},
        )
        self.assertEqual(plan.reviewers, 3)
        self.assertFalse(plan.validator)


class ModelTest(unittest.TestCase):
    def _plan(self, severity, **overrides):
        cfg = make_config(**overrides)
        ctx = make_ctx(helpers.repo_root())
        return plan_route([_finding(severity)], ctx, cfg)

    def test_rule_backend_uses_one_model_for_high(self):
        plan = self._plan(Severity.HIGH, **{"review.backend": "rule"})
        self.assertEqual(plan.models, ["model-a"])

    def test_llm_backend_uses_two_models_for_high(self):
        plan = self._plan(Severity.HIGH, **{"review.backend": "llm"})
        self.assertEqual(plan.models, ["model-a", "model-b"])

    def test_llm_backend_uses_two_models_for_critical(self):
        plan = self._plan(Severity.CRITICAL, **{"review.backend": "llm"})
        self.assertEqual(len(plan.models), 2)

    def test_rule_backend_never_claims_cross_model(self):
        plan = self._plan(Severity.HIGH, **{"review.backend": "rule"})
        self.assertIn("cross-model review not applicable", plan.reason)
        self.assertNotIn("cross-model review with", plan.reason)

    def test_llm_backend_does_claim_cross_model(self):
        plan = self._plan(Severity.HIGH, **{"review.backend": "llm"})
        self.assertIn("cross-model review with", plan.reason)

    def test_multi_model_off_keeps_one_model(self):
        plan = self._plan(
            Severity.HIGH, **{"review.backend": "llm", "review.multi_model_on_high": False}
        )
        self.assertEqual(plan.models, ["model-a"])

    def test_low_risk_does_not_expand_models(self):
        plan = self._plan(Severity.LOW, **{"review.backend": "llm"})
        self.assertEqual(plan.models, ["model-a"])


class BackendOffTest(unittest.TestCase):
    def test_backend_off_runs_zero_reviewers_and_says_so(self):
        cfg = make_config(**{"review.backend": "off"})
        ctx = make_ctx(helpers.repo_root())
        plan = plan_route([_finding(Severity.HIGH)], ctx, cfg)
        self.assertEqual(plan.reviewers, 0)
        self.assertIn("review backend is 'off'", plan.reason)
        self.assertIn("NOT evidence", plan.reason)

    def test_rule_backend_labels_itself_honestly(self):
        cfg = make_config(**{"review.backend": "rule"})
        ctx = make_ctx(helpers.repo_root())
        plan = plan_route([_finding(Severity.HIGH)], ctx, cfg)
        self.assertIn("not an independent model opinion", plan.reason)


class InitialRiskTest(helpers.CHMTestCase):
    def test_empty_change_set_is_low(self):
        ctx = make_ctx(helpers.repo_root(), changed=[])
        risk, why = initial_risk(ctx)
        self.assertEqual(risk, "LOW")
        self.assertIn("empty change set", why)

    def test_docs_only_change_is_low(self):
        ctx = make_ctx(
            helpers.repo_root(),
            changed=[changed_file("docs/guide.md"), changed_file("src/test/A.java")],
        )
        risk, why = initial_risk(ctx)
        self.assertEqual(risk, "LOW")
        self.assertIn("documentation/test-only", why)

    def test_sensitive_keyword_raises_to_high(self):
        repo = self.temp_repo(
            {"src/main/java/pay/Checkout.java": "class Checkout { int paymentAmount; }"},
            commit=False,
        )
        ctx = make_ctx(repo, changed=[changed_file("src/main/java/pay/Checkout.java")])
        risk, why = initial_risk(ctx)
        self.assertEqual(risk, "HIGH")
        self.assertIn("sensitive-domain keyword", why)

    def test_ordinary_change_is_medium(self):
        repo = self.temp_repo({"src/main/java/A.java": "class A { void m() {} }"}, commit=False)
        ctx = make_ctx(repo, changed=[changed_file("src/main/java/A.java")])
        risk, why = initial_risk(ctx)
        self.assertEqual(risk, "MEDIUM")
        self.assertIn("ordinary source change", why)


class PlanShapeTest(helpers.CHMTestCase):
    def test_to_dict_has_the_contract_fields(self):
        cfg = make_config()
        ctx = make_ctx(helpers.repo_root())
        plan = plan_route([_finding(Severity.HIGH)], ctx, cfg)
        payload = plan.to_dict()
        for key in (
            "risk",
            "reviewers",
            "validator",
            "deterministic_only",
            "expansion",
            "models",
            "reason",
        ):
            self.assertIn(key, payload)
        self.assertIsInstance(plan, RoutePlan)
        self.assertEqual(payload["risk"], "HIGH")

    def test_reason_records_the_basis_and_the_tier(self):
        cfg = make_config()
        ctx = make_ctx(helpers.repo_root())
        plan = plan_route([_finding(Severity.CRITICAL)], ctx, cfg)
        self.assertIn("risk=CRITICAL from 1 existing finding(s)", plan.reason)
        self.assertIn("CRITICAL -> 2 reviewer(s) + validator + full gate", plan.reason)
        self.assertIn("expansion=full_slice", plan.reason)

    def test_pre_review_plan_when_there_are_no_findings_yet(self):
        repo = self.temp_repo({"src/main/java/A.java": "class A {}"}, commit=False)
        ctx = make_ctx(repo, changed=[changed_file("src/main/java/A.java")])
        plan = plan_route([], ctx, make_config())
        self.assertEqual(plan.risk, "MEDIUM")
        self.assertIn("pre-review", plan.reason)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
