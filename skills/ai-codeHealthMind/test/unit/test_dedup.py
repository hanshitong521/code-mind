"""Spec §17 cross-provider deduplication: three tools, one finding."""

from __future__ import annotations

import unittest

import helpers
from helpers import evidence, make_config, make_finding

from chm.core.dedup import CATEGORY_FAMILY, MAX_LINE_DELTA, deduplicate, is_same_issue
from chm.schema import Category, EvidenceKind, Severity


class SameIssueTest(unittest.TestCase):
    def test_same_file_same_line_same_category(self):
        a = make_finding("CHM-000001", file="a.java", start_line=10, category=Category.DEAD_CODE)
        b = make_finding("CHM-000002", file="a.java", start_line=10, category=Category.DEAD_CODE)
        same, reason = is_same_issue(a, b)
        self.assertTrue(same)
        self.assertIn("same file", reason)

    def test_different_file_never_merges(self):
        a = make_finding("CHM-000001", file="a.java", start_line=10, category=Category.DEAD_CODE)
        b = make_finding("CHM-000002", file="b.java", start_line=10, category=Category.DEAD_CODE)
        same, reason = is_same_issue(a, b)
        self.assertFalse(same)
        self.assertIn("different file", reason)

    def test_line_delta_over_threshold_never_merges(self):
        a = make_finding("CHM-000001", file="a.java", start_line=10, category=Category.DEAD_CODE)
        b = make_finding(
            "CHM-000002", file="a.java", start_line=10 + MAX_LINE_DELTA + 1, category=Category.DEAD_CODE
        )
        same, reason = is_same_issue(a, b)
        self.assertFalse(same)
        self.assertIn("line delta", reason)

    def test_line_delta_at_threshold_merges(self):
        a = make_finding("CHM-000001", file="a.java", start_line=10, category=Category.DEAD_CODE)
        b = make_finding(
            "CHM-000002", file="a.java", start_line=10 + MAX_LINE_DELTA, category=Category.DEAD_CODE
        )
        same, _ = is_same_issue(a, b)
        self.assertTrue(same)

    def test_shared_symbol_overrides_large_delta(self):
        a = make_finding(
            "CHM-000001", file="a.java", start_line=10, symbol="settle", category=Category.DEAD_CODE
        )
        b = make_finding(
            "CHM-000002", file="a.java", start_line=90, symbol="settle", category=Category.DEAD_CODE
        )
        same, reason = is_same_issue(a, b)
        self.assertTrue(same)
        self.assertIn("same symbol settle", reason)

    def test_unrelated_categories_never_merge(self):
        a = make_finding("CHM-000001", file="a.java", start_line=10, category=Category.DEAD_CODE)
        b = make_finding("CHM-000002", file="a.java", start_line=10, category=Category.PERFORMANCE)
        same, reason = is_same_issue(a, b)
        self.assertFalse(same)
        self.assertIn("unrelated categories", reason)

    def test_category_family_merges(self):
        a = make_finding("CHM-000001", file="a.java", start_line=10, category=Category.COMPLEXITY)
        b = make_finding("CHM-000002", file="a.java", start_line=11, category=Category.LARGE_METHOD)
        same, reason = is_same_issue(a, b)
        self.assertTrue(same)
        self.assertIn("category family", reason)

    def test_category_family_table_is_consistent(self):
        self.assertEqual(CATEGORY_FAMILY[Category.COMPLEXITY], CATEGORY_FAMILY[Category.LARGE_CLASS])
        self.assertNotEqual(CATEGORY_FAMILY[Category.DEAD_CODE], CATEGORY_FAMILY[Category.DATABASE])


class ThreeProviderMergeTest(unittest.TestCase):
    """PMD + Semgrep + LLM all reporting one problem -> exactly one Finding."""

    def _findings(self):
        return [
            make_finding(
                "CHM-000001",
                rule_id="CHM-JAVA-UNUSED-PRIVATE-METHOD",
                file="src/main/java/A.java",
                start_line=10,
                symbol="helper",
                category=Category.DEAD_CODE,
                severity=Severity.MEDIUM,
                confidence=0.9,
                evidence=[evidence("pmd", detail="UnusedPrivateMethod")],
                sources=["pmd"],
            ),
            make_finding(
                "CHM-000002",
                rule_id="CHM-SEMGREP-DEAD-001",
                file="src/main/java/A.java",
                start_line=11,
                symbol="helper",
                category=Category.DEAD_CODE,
                severity=Severity.MEDIUM,
                confidence=0.7,
                evidence=[
                    evidence("semgrep", detail="unused private method"),
                ],
                sources=["semgrep"],
            ),
            make_finding(
                "CHM-000003",
                rule_id="CHM-REVIEW-SIMPLICITY-001",
                file="src/main/java/A.java",
                start_line=10,
                symbol="helper",
                category=Category.DEAD_CODE,
                severity=Severity.MEDIUM,
                confidence=0.6,
                evidence=[
                    evidence(
                        "reviewer:simplicity",
                        kind=EvidenceKind.SEMANTIC,
                        detail="never referenced",
                    )
                ],
                sources=["reviewer:simplicity"],
            ),
        ]

    def test_merges_into_one_finding_with_three_providers(self):
        result = deduplicate(self._findings(), config=make_config())
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.merged_count, 2)
        self.assertEqual(result.original_count, 3)
        self.assertAlmostEqual(result.dedup_ratio, round(2 / 3, 4))

        kept = result.findings[0]
        providers = {e.provider for e in kept.evidence}
        self.assertEqual(providers, {"pmd", "semgrep", "reviewer:simplicity"})
        self.assertEqual(len(providers), 3)
        self.assertEqual(kept.sources, ["pmd", "reviewer:simplicity", "semgrep"])
        self.assertEqual(len(kept.sources), 3)

    def test_merge_group_records_the_reason_and_members(self):
        result = deduplicate(self._findings(), config=make_config())
        self.assertEqual(len(result.groups), 1)
        group = result.groups[0]
        self.assertEqual(group.kept_id, "CHM-000001")
        self.assertEqual(sorted(group.merged_ids), ["CHM-000002", "CHM-000003"])
        self.assertEqual(group.sources, ["pmd", "reviewer:simplicity", "semgrep"])
        self.assertIn("same file", group.reason)

    def test_kept_finding_is_the_highest_confidence_member(self):
        result = deduplicate(self._findings(), config=make_config())
        kept = result.findings[0]
        self.assertEqual(kept.id, "CHM-000001")
        self.assertEqual(kept.rule_id, "CHM-JAVA-UNUSED-PRIVATE-METHOD")
        # independent confirmation raises confidence, but never to certainty
        self.assertGreater(kept.confidence, 0.9)
        self.assertLess(kept.confidence, 1.0)
        self.assertEqual(kept.confidence, 0.95)

    def test_merge_is_recorded_in_history(self):
        result = deduplicate(self._findings(), config=make_config())
        history = result.findings[0].history
        self.assertIn("merged:CHM-000002", history)
        self.assertIn("merged:CHM-000003", history)

    def test_determinism(self):
        runs = [
            [
                (f.id, f.rule_id, f.confidence, tuple(f.sources))
                for f in deduplicate(self._findings(), config=make_config()).findings
            ]
            for _ in range(3)
        ]
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[1], runs[2])

    def test_input_list_is_not_mutated(self):
        findings = self._findings()
        before = [f.to_dict() for f in findings]
        deduplicate(findings, config=make_config())
        self.assertEqual([f.to_dict() for f in findings], before)


class NonMergeTest(unittest.TestCase):
    def test_two_files_stay_two_findings(self):
        findings = [
            make_finding("CHM-000001", file="a.java", start_line=10, category=Category.DEAD_CODE),
            make_finding("CHM-000002", file="b.java", start_line=10, category=Category.DEAD_CODE),
        ]
        result = deduplicate(findings, config=make_config())
        self.assertEqual(len(result.findings), 2)
        self.assertEqual(result.merged_count, 0)
        self.assertEqual(result.dedup_ratio, 0.0)
        self.assertEqual(result.groups, [])

    def test_far_apart_same_file_stays_two_findings(self):
        findings = [
            make_finding(
                "CHM-000001", file="a.java", start_line=10, symbol="one", category=Category.DEAD_CODE
            ),
            make_finding(
                "CHM-000002", file="a.java", start_line=40, symbol="two", category=Category.DEAD_CODE
            ),
        ]
        result = deduplicate(findings, config=make_config())
        self.assertEqual(len(result.findings), 2)
        self.assertEqual(result.merged_count, 0)

    def test_different_categories_stay_two_findings(self):
        findings = [
            make_finding("CHM-000001", file="a.java", start_line=10, category=Category.DEAD_CODE),
            make_finding("CHM-000002", file="a.java", start_line=10, category=Category.PERFORMANCE),
        ]
        result = deduplicate(findings, config=make_config())
        self.assertEqual(len(result.findings), 2)

    def test_empty_input(self):
        result = deduplicate([], config=make_config())
        self.assertEqual(result.findings, [])
        self.assertEqual(result.dedup_ratio, 0.0)
        self.assertEqual(result.original_count, 0)

    def test_output_order_is_severity_then_location(self):
        findings = [
            make_finding(
                "CHM-000001", file="b.java", start_line=1, severity=Severity.LOW, category=Category.DEAD_CODE
            ),
            make_finding(
                "CHM-000002",
                file="a.java",
                start_line=9,
                severity=Severity.CRITICAL,
                category=Category.DATABASE,
                rule_id="CHM-JAVA-TX-BOUNDARY",
            ),
            make_finding(
                "CHM-000003", file="a.java", start_line=3, severity=Severity.MEDIUM, category=Category.DEAD_CODE
            ),
        ]
        result = deduplicate(findings, config=make_config())
        self.assertEqual([f.id for f in result.findings], ["CHM-000002", "CHM-000003", "CHM-000001"])


class DedupResultShapeTest(unittest.TestCase):
    def test_to_dict_shape(self):
        findings = [
            make_finding("CHM-000001", file="a.java", start_line=10, category=Category.DEAD_CODE),
            make_finding("CHM-000002", file="a.java", start_line=10, category=Category.DEAD_CODE),
        ]
        payload = deduplicate(findings, config=make_config()).to_dict()
        self.assertEqual(payload["kept_count"], 1)
        self.assertEqual(payload["original_count"], 2)
        self.assertEqual(payload["merged_count"], 1)
        self.assertEqual(payload["dedup_ratio"], 0.5)
        self.assertEqual(len(payload["groups"]), 1)
        self.assertEqual(payload["groups"][0]["merged_count"], 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
