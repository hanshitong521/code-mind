"""RawFinding -> Finding normalisation: determinism, diff scoping, downgrades, repair routing."""

from __future__ import annotations

import unittest

import helpers
from helpers import changed_file, hunk, make_config, make_ctx

from chm.core.normalizer import normalize_all, normalize_one
from chm.schema import (
    Category,
    EvidenceKind,
    PerfConfidence,
    RawFinding,
    RepairClass,
    Severity,
)


def raw(
    *,
    provider: str = "native-java",
    rule_id: str = "CHM-JAVA-DEAD-001",
    message: str = "unused private method",
    file: str = "src/main/java/A.java",
    start_line: int = 10,
    end_line: int | None = None,
    symbol: str | None = None,
    category: Category | None = None,
    severity: Severity | None = None,
    confidence: float = 0.8,
    kind: EvidenceKind = EvidenceKind.DETERMINISTIC,
    extra: dict | None = None,
) -> RawFinding:
    return RawFinding(
        provider=provider,
        rule_id=rule_id,
        message=message,
        file=file,
        start_line=start_line,
        end_line=end_line if end_line is not None else start_line,
        symbol=symbol,
        category=category,
        severity=severity,
        confidence=confidence,
        kind=kind,
        extra=dict(extra or {}),
    )


class DeterminismTest(unittest.TestCase):
    """Spec §41 -- identical input must produce identical ids and ordering."""

    def test_three_runs_are_identical(self):
        raws = [
            raw(file="src/z/Z.java", start_line=30, rule_id="CHM-JAVA-DEAD-002"),
            raw(file="src/a/A.java", start_line=5, rule_id="CHM-JAVA-DEAD-001"),
            raw(file="src/a/A.java", start_line=5, rule_id="CHM-JAVA-DEAD-001", symbol="m2"),
            raw(file="src/a/A.java", start_line=5, rule_id="CHM-JAVA-COMPLEXITY-001"),
            raw(file="src/m/M.java", start_line=1, rule_id="CHM-JAVA-DEAD-003"),
        ]
        cfg = helpers.make_config()
        runs = []
        for _ in range(3):
            findings, stats = normalize_all(raws, config=cfg, ctx=None)
            runs.append(
                (
                    [f.id for f in findings],
                    [f.rule_id for f in findings],
                    [(f.location.file, f.location.start_line) for f in findings],
                    stats.to_dict(),
                )
            )
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[1], runs[2])
        self.assertEqual(runs[0][0], ["CHM-000001", "CHM-000002", "CHM-000003", "CHM-000004", "CHM-000005"])
        # sorted by file then line
        self.assertEqual(runs[0][2][0][0], "src/a/A.java")

    def test_ids_are_sequential_and_legal(self):
        findings, _ = normalize_all(
            [raw(file="b.java"), raw(file="a.java")], config=helpers.make_config(), ctx=None
        )
        self.assertEqual([f.id for f in findings], ["CHM-000001", "CHM-000002"])
        for f in findings:
            f.validate_schema()

    def test_normalize_one_is_pure_wrt_index(self):
        cfg = helpers.make_config()
        a = normalize_one(raw(), index=7, config=cfg)
        b = normalize_one(raw(), index=7, config=cfg)
        self.assertEqual(a.to_dict(), b.to_dict())


class DiffScopeTest(unittest.TestCase):
    """Findings outside the change set are noise by default (spec §13)."""

    def setUp(self):
        self.cfg = helpers.make_config()
        self.ctx = make_ctx(
            helpers.repo_root(),
            changed=[changed_file("src/a/A.java", hunks=[hunk(5, 1)], added_lines=1)],
        )

    def test_outside_diff_counter(self):
        raws = [
            raw(file="src/a/A.java", start_line=5),          # inside the hunk
            raw(file="src/a/A.java", start_line=99),         # same file, untouched line
            raw(file="src/b/B.java", start_line=1),          # untouched file
            raw(file="src/b/B.java", start_line=2),          # untouched file
        ]
        findings, stats = normalize_all(raws, config=self.cfg, ctx=self.ctx)
        self.assertEqual(stats.total, 4)
        self.assertEqual(stats.outside_diff, 3)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].location.start_line, 5)
        self.assertTrue(findings[0].introduced_by_current_diff)

    def test_whole_file_escape_hatch(self):
        raws = [raw(file="src/b/B.java", start_line=1, extra={"whole_file": True})]
        findings, stats = normalize_all(raws, config=self.cfg, ctx=self.ctx)
        self.assertEqual(stats.outside_diff, 0)
        self.assertEqual(len(findings), 1)

    def test_report_unchanged_escape_hatch(self):
        raws = [raw(file="src/b/B.java", start_line=1, extra={"report_unchanged": True})]
        findings, stats = normalize_all(raws, config=self.cfg, ctx=self.ctx)
        self.assertEqual(stats.outside_diff, 0)
        self.assertEqual(len(findings), 1)
        self.assertFalse(findings[0].introduced_by_current_diff)

    def test_excluded_path_is_dropped_before_scoping(self):
        raws = [raw(file="node_modules/x/a.js", start_line=1, extra={"whole_file": True})]
        findings, stats = normalize_all(raws, config=self.cfg, ctx=self.ctx)
        self.assertEqual(stats.excluded, 1)
        self.assertEqual(findings, [])

    def test_no_ctx_means_no_scoping(self):
        raws = [raw(file="anything/Any.java", start_line=1)]
        findings, stats = normalize_all(raws, config=self.cfg, ctx=None)
        self.assertEqual(stats.outside_diff, 0)
        self.assertEqual(len(findings), 1)


class SeverityDowngradeTest(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.make_config()

    def test_semantic_only_high_becomes_medium(self):
        raws = [
            raw(
                provider="reviewer:correctness",
                rule_id="CHM-REVIEW-CORRECTNESS-001",
                severity=Severity.HIGH,
                kind=EvidenceKind.SEMANTIC,
                confidence=0.9,
                category=Category.ERROR_HANDLING,
            )
        ]
        findings, _ = normalize_all(raws, config=self.cfg, ctx=None)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, Severity.MEDIUM)
        self.assertLessEqual(findings[0].confidence, 0.6)

    def test_semantic_only_critical_becomes_medium(self):
        raws = [
            raw(
                provider="reviewer:correctness",
                rule_id="CHM-REVIEW-CORRECTNESS-002",
                severity=Severity.CRITICAL,
                kind=EvidenceKind.SEMANTIC,
                category=Category.ERROR_HANDLING,
            )
        ]
        findings, _ = normalize_all(raws, config=self.cfg, ctx=None)
        self.assertEqual(findings[0].severity, Severity.MEDIUM)

    def test_deterministic_high_is_kept(self):
        raws = [raw(severity=Severity.HIGH, category=Category.RESOURCE_SAFETY)]
        findings, _ = normalize_all(raws, config=self.cfg, ctx=None)
        self.assertEqual(findings[0].severity, Severity.HIGH)

    def test_performance_without_proof_capped_at_medium(self):
        raws = [
            raw(
                rule_id="CHM-JAVA-PERF-NPLUS1",
                severity=Severity.HIGH,
                category=Category.PERFORMANCE,
                extra={},
            )
        ]
        findings, _ = normalize_all(raws, config=self.cfg, ctx=None)
        self.assertEqual(findings[0].severity, Severity.MEDIUM)
        self.assertEqual(findings[0].perf_confidence, PerfConfidence.SUSPECTED)

    def test_performance_proven_keeps_high(self):
        raws = [
            raw(
                rule_id="CHM-JAVA-PERF-NPLUS1",
                severity=Severity.HIGH,
                category=Category.PERFORMANCE,
                extra={"perf_confidence": "PROVEN"},
            )
        ]
        findings, _ = normalize_all(raws, config=self.cfg, ctx=None)
        self.assertEqual(findings[0].severity, Severity.HIGH)
        self.assertEqual(findings[0].perf_confidence, PerfConfidence.PROVEN)

    def test_performance_likely_is_still_capped(self):
        raws = [
            raw(
                rule_id="CHM-JAVA-PERF-NPLUS1",
                severity=Severity.CRITICAL,
                category=Category.PERFORMANCE,
                extra={"perf_confidence": "LIKELY"},
            )
        ]
        findings, _ = normalize_all(raws, config=self.cfg, ctx=None)
        self.assertEqual(findings[0].severity, Severity.MEDIUM)
        self.assertEqual(findings[0].perf_confidence, PerfConfidence.LIKELY)

    def test_bogus_perf_confidence_falls_back_to_suspected(self):
        raws = [
            raw(
                rule_id="CHM-JAVA-PERF-NPLUS1",
                severity=Severity.HIGH,
                category=Category.PERFORMANCE,
                extra={"perf_confidence": "definitely"},
            )
        ]
        findings, _ = normalize_all(raws, config=self.cfg, ctx=None)
        self.assertEqual(findings[0].perf_confidence, PerfConfidence.SUSPECTED)


class RepairRoutingTest(unittest.TestCase):
    """Spec §23 -- only provably mechanical work may be auto-fixed."""

    def _route(self, raws, **overrides):
        cfg = make_config(**overrides)
        findings, _ = normalize_all(raws, config=cfg, ctx=None)
        return findings[0]

    def test_dead_code_not_auto_deletable_by_default(self):
        f = self._route([raw(rule_id="CHM-JAVA-UNUSED-PRIVATE-METHOD")])
        self.assertFalse(f.repair.auto_fixable)
        self.assertIsNot(f.repair.repair_class, RepairClass.SAFE_AUTO_FIX)
        self.assertEqual(f.repair.repair_class, RepairClass.MANUAL_DECISION)

    def test_unused_import_is_safe_auto_fix_when_allowed(self):
        f = self._route(
            [raw(rule_id="CHM-JAVA-UNUSED-IMPORT", message="unused import java.util.List")],
            **{"dead_code.allow_auto_delete": True},
        )
        self.assertTrue(f.repair.auto_fixable)
        self.assertEqual(f.repair.repair_class, RepairClass.SAFE_AUTO_FIX)

    def test_unused_import_still_blocked_when_auto_delete_disallowed(self):
        f = self._route([raw(rule_id="CHM-JAVA-UNUSED-IMPORT")])
        self.assertFalse(f.repair.auto_fixable)
        self.assertEqual(f.repair.repair_class, RepairClass.MANUAL_DECISION)

    def test_other_dead_code_stays_manual_even_when_allowed(self):
        f = self._route(
            [raw(rule_id="CHM-JAVA-UNUSED-PRIVATE-METHOD")],
            **{"dead_code.allow_auto_delete": True},
        )
        self.assertFalse(f.repair.auto_fixable)
        self.assertEqual(f.repair.repair_class, RepairClass.MANUAL_DECISION)

    def test_concurrency_is_writer_fix(self):
        f = self._route([raw(rule_id="CHM-JAVA-LOCK-ORDER", severity=Severity.MEDIUM)])
        self.assertEqual(f.category, Category.CONCURRENCY)
        self.assertIn(f.repair.repair_class, (RepairClass.WRITER_FIX, RepairClass.MANUAL_DECISION))
        self.assertIsNot(f.repair.repair_class, RepairClass.SAFE_AUTO_FIX)

    def test_database_transaction_is_writer_fix(self):
        f = self._route([raw(rule_id="CHM-JAVA-TX-BOUNDARY", severity=Severity.MEDIUM)])
        self.assertEqual(f.category, Category.DATABASE)
        self.assertEqual(f.repair.repair_class, RepairClass.WRITER_FIX)

    def test_architecture_drift_is_never_auto_fixable(self):
        f = self._route([raw(rule_id="CHM-ARCH-DRIFT-001", severity=Severity.MEDIUM)])
        self.assertEqual(f.category, Category.ARCHITECTURE_DRIFT)
        self.assertIsNot(f.repair.repair_class, RepairClass.SAFE_AUTO_FIX)
        self.assertFalse(f.repair.auto_fixable)

    def test_semantic_finding_is_manual_decision(self):
        f = self._route(
            [
                raw(
                    provider="reviewer:simplicity",
                    rule_id="CHM-REVIEW-SIMPLICITY-001",
                    kind=EvidenceKind.SEMANTIC,
                    category=Category.OVER_ENGINEERING,
                )
            ]
        )
        self.assertEqual(f.repair.repair_class, RepairClass.MANUAL_DECISION)
        self.assertFalse(f.repair.auto_fixable)

    def test_config_inflation_is_manual_decision(self):
        f = self._route([raw(rule_id="CHM-JAVA-UNUSED-CONFIG")])
        self.assertEqual(f.category, Category.CONFIG_INFLATION)
        self.assertEqual(f.repair.repair_class, RepairClass.MANUAL_DECISION)


class CategoryInferenceTest(unittest.TestCase):
    def test_rule_token_inference(self):
        cases = {
            "CHM-JAVA-UNUSED-IMPORT": Category.DEAD_CODE,
            "CHM-JAVA-CPD-DUPLICATE": Category.DUPLICATION,
            "CHM-JAVA-TX-BOUNDARY": Category.DATABASE,
            "CHM-JAVA-RESOURCE-LEAK": Category.RESOURCE_SAFETY,
            "CHM-JAVA-EMPTY-CATCH": Category.ERROR_HANDLING,
            "CHM-ARCH-DRIFT-001": Category.ARCHITECTURE_DRIFT,
        }
        cfg = helpers.make_config()
        for rule_id, expected in cases.items():
            with self.subTest(rule_id=rule_id):
                findings, _ = normalize_all([raw(rule_id=rule_id)], config=cfg, ctx=None)
                self.assertEqual(findings[0].category, expected)

    def test_explicit_category_wins(self):
        findings, _ = normalize_all(
            [raw(rule_id="CHM-JAVA-UNUSED-IMPORT", category=Category.PERFORMANCE)],
            config=helpers.make_config(),
            ctx=None,
        )
        self.assertEqual(findings[0].category, Category.PERFORMANCE)

    def test_unknown_rule_falls_back_to_boilerplate(self):
        findings, _ = normalize_all(
            [raw(rule_id="CHM-XYZ-001", message="something odd")],
            config=helpers.make_config(),
            ctx=None,
        )
        self.assertEqual(findings[0].category, Category.BOILERPLATE)


class EvidenceAttachmentTest(unittest.TestCase):
    def test_provider_hit_becomes_structured_evidence(self):
        findings, _ = normalize_all(
            [raw(provider="pmd", rule_id="CHM-JAVA-DEAD-001")],
            config=helpers.make_config(),
            ctx=None,
        )
        f = findings[0]
        self.assertEqual(len(f.evidence), 1)
        self.assertEqual(f.evidence[0].provider, "pmd")
        self.assertEqual(f.evidence[0].kind, EvidenceKind.DETERMINISTIC)
        self.assertEqual(f.sources, ["pmd"])

    def test_uncertainty_flags_are_extracted(self):
        findings, _ = normalize_all(
            [raw(extra={"reflection_checked": True, "uncertainty_notes": ["checked by hand"]})],
            config=helpers.make_config(),
            ctx=None,
        )
        f = findings[0]
        self.assertTrue(f.uncertainty.reflection_checked)
        self.assertIn("checked by hand", f.uncertainty.notes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
