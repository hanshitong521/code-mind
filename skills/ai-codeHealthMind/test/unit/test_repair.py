"""Spec §23 safe repairs: only provably mechanical edits, verified before editing."""

from __future__ import annotations

import unittest

import helpers
from helpers import make_config, make_finding

from chm.core.repair import apply_safe_fixes, is_applicable
from chm.schema import Category, Repair, RepairClass, Severity

SOURCE = (
    "package p;\n"
    "\n"
    "import java.util.List;\n"
    "import java.util.Map;\n"
    "\n"
    "public class A {\n"
    "    void m() {\n"
    '        System.out.println("debug");\n'
    "    }\n"
    "}\n"
)

EXPECTED_AFTER = (
    "package p;\n"
    "\n"
    "\n"
    "public class A {\n"
    "    void m() {\n"
    "    }\n"
    "}\n"
)


def _safe(rule_id: str, line: int, *, category: Category = Category.DEAD_CODE):
    return make_finding(
        f"CHM-{line:06d}",
        rule_id=rule_id,
        category=category,
        severity=Severity.LOW,
        file="src/A.java",
        start_line=line,
        repair=Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX),
    )


class ApplicabilityTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_config(**{"dead_code.allow_auto_delete": True})

    def test_safe_auto_fix_unused_import_is_applicable(self):
        ok, reason = is_applicable(_safe("CHM-JAVA-UNUSED-IMPORT", 3), self.cfg)
        self.assertTrue(ok, reason)

    def test_writer_fix_is_never_applicable(self):
        finding = make_finding(
            "CHM-000001",
            rule_id="CHM-JAVA-UNUSED-IMPORT",
            category=Category.DEAD_CODE,
            repair=Repair(auto_fixable=False, repair_class=RepairClass.WRITER_FIX),
        )
        ok, reason = is_applicable(finding, self.cfg)
        self.assertFalse(ok)
        self.assertIn("WRITER_FIX", reason)

    def test_manual_decision_is_never_applicable(self):
        finding = make_finding(
            "CHM-000001",
            rule_id="CHM-JAVA-UNUSED-IMPORT",
            repair=Repair(auto_fixable=False, repair_class=RepairClass.MANUAL_DECISION),
        )
        self.assertFalse(is_applicable(finding, self.cfg)[0])

    def test_rule_outside_the_allowlist_is_refused(self):
        finding = make_finding(
            "CHM-000001",
            rule_id="CHM-JAVA-UNUSED-PRIVATE-METHOD",
            category=Category.DEAD_CODE,
            repair=Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX),
        )
        ok, reason = is_applicable(finding, self.cfg)
        self.assertFalse(ok)
        self.assertIn("allowlist", reason)

    def test_dead_code_blocked_when_auto_delete_is_off(self):
        cfg = make_config(**{"dead_code.allow_auto_delete": False})
        ok, reason = is_applicable(_safe("CHM-JAVA-UNUSED-IMPORT", 3), cfg)
        self.assertFalse(ok)
        self.assertIn("allow_auto_delete", reason)

    def test_uncertain_dynamic_entry_is_refused(self):
        finding = _safe("CHM-JAVA-UNUSED-IMPORT", 3)
        finding.uncertainty.notes = ["possible reflection use"]
        ok, reason = is_applicable(finding, self.cfg)
        self.assertFalse(ok)
        self.assertIn("uncertain", reason)


class ApplyTest(helpers.CHMTestCase):
    def setUp(self):
        self.repo = self.temp_repo({"src/A.java": SOURCE}, commit=False)
        self.cfg = make_config(**{"dead_code.allow_auto_delete": True})
        self.target = self.repo / "src" / "A.java"

    def test_applies_the_safe_subset_only(self):
        findings = [
            _safe("CHM-JAVA-UNUSED-IMPORT", 3),
            _safe("CHM-JAVA-UNUSED-IMPORT", 4),
            _safe("CHM-JAVA-DEBUG-RESIDUE", 8),
            make_finding(
                "CHM-000099",
                rule_id="CHM-JAVA-RESOURCE-LEAK",
                category=Category.RESOURCE_SAFETY,
                severity=Severity.HIGH,
                file="src/A.java",
                start_line=8,
                repair=Repair(auto_fixable=False, repair_class=RepairClass.WRITER_FIX),
            ),
        ]
        applied, refused = apply_safe_fixes(self.repo, findings, self.cfg)

        self.assertEqual(len(applied), 3)
        self.assertEqual(
            applied,
            [
                "src/A.java:3 CHM-JAVA-UNUSED-IMPORT",
                "src/A.java:4 CHM-JAVA-UNUSED-IMPORT",
                "src/A.java:8 CHM-JAVA-DEBUG-RESIDUE",
            ],
        )
        self.assertEqual(refused, [])
        self.assertEqual(self.target.read_text(encoding="utf-8"), EXPECTED_AFTER)

    def test_every_other_line_is_untouched(self):
        before = self.target.read_text(encoding="utf-8").split("\n")
        apply_safe_fixes(self.repo, [_safe("CHM-JAVA-UNUSED-IMPORT", 3)], self.cfg)
        after = self.target.read_text(encoding="utf-8").split("\n")
        self.assertEqual(len(after), len(before) - 1)
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1], before[1])
        self.assertEqual(after[2:], before[3:])

    def test_line_content_mismatch_is_refused(self):
        # line 6 is "public class A {", not an import
        findings = [_safe("CHM-JAVA-UNUSED-IMPORT", 6)]
        applied, refused = apply_safe_fixes(self.repo, findings, self.cfg)
        self.assertEqual(applied, [])
        self.assertEqual(len(refused), 1)
        self.assertIn("content changed, refusing", refused[0])
        self.assertEqual(self.target.read_text(encoding="utf-8"), SOURCE)

    def test_out_of_range_line_is_refused(self):
        findings = [_safe("CHM-JAVA-UNUSED-IMPORT", 9999)]
        applied, refused = apply_safe_fixes(self.repo, findings, self.cfg)
        self.assertEqual(applied, [])
        self.assertEqual(len(refused), 1)
        self.assertIn("line out of range", refused[0])

    def test_missing_file_is_refused(self):
        finding = make_finding(
            "CHM-000001",
            rule_id="CHM-JAVA-UNUSED-IMPORT",
            category=Category.DEAD_CODE,
            file="src/Gone.java",
            start_line=1,
            repair=Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX),
        )
        applied, refused = apply_safe_fixes(self.repo, [finding], self.cfg)
        self.assertEqual(applied, [])
        self.assertTrue(any("no longer exists" in r for r in refused))

    def test_multiple_findings_in_one_file_are_applied_bottom_up(self):
        findings = [
            _safe("CHM-JAVA-UNUSED-IMPORT", 3),
            _safe("CHM-JAVA-UNUSED-IMPORT", 4),
        ]
        applied, refused = apply_safe_fixes(self.repo, findings, self.cfg)
        self.assertEqual(len(applied), 2)
        self.assertEqual(refused, [])
        text = self.target.read_text(encoding="utf-8")
        self.assertNotIn("import java.util.List;", text)
        self.assertNotIn("import java.util.Map;", text)

    def test_crlf_line_endings_are_preserved(self):
        crlf = SOURCE.replace("\n", "\r\n")
        repo = self.temp_repo({"src/B.java": crlf}, commit=False)
        finding = make_finding(
            "CHM-000003",
            rule_id="CHM-JAVA-UNUSED-IMPORT",
            category=Category.DEAD_CODE,
            file="src/B.java",
            start_line=3,
            repair=Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX),
        )
        applied, refused = apply_safe_fixes(repo, [finding], self.cfg)
        self.assertEqual(len(applied), 1)
        self.assertEqual(refused, [])
        raw = (repo / "src" / "B.java").read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"import java.util.List;", raw)

    def test_no_findings_is_a_no_op(self):
        applied, refused = apply_safe_fixes(self.repo, [], self.cfg)
        self.assertEqual((applied, refused), ([], []))
        self.assertEqual(self.target.read_text(encoding="utf-8"), SOURCE)


class RefusalReportingTest(helpers.CHMTestCase):
    """The requested contract: anything not applied must be visible as refused."""

    def setUp(self):
        self.repo = self.temp_repo({"src/A.java": SOURCE}, commit=False)
        self.cfg = make_config(**{"dead_code.allow_auto_delete": True})

    def test_non_safe_auto_fix_findings_are_reported_as_refused(self):
        unsafe = make_finding(
            "CHM-000077",
            rule_id="CHM-JAVA-RESOURCE-LEAK",
            category=Category.RESOURCE_SAFETY,
            severity=Severity.HIGH,
            file="src/A.java",
            start_line=8,
            repair=Repair(auto_fixable=False, repair_class=RepairClass.WRITER_FIX),
        )
        _applied, refused = apply_safe_fixes(self.repo, [unsafe], self.cfg)
        self.assertTrue(
            any("CHM-000077" in r for r in refused),
            "a finding that was not applied must be reported in `refused`, got: " + repr(refused),
        )

    def test_unsafe_finding_never_touches_the_file(self):
        unsafe = make_finding(
            "CHM-000077",
            rule_id="CHM-JAVA-RESOURCE-LEAK",
            category=Category.RESOURCE_SAFETY,
            severity=Severity.HIGH,
            file="src/A.java",
            start_line=8,
            repair=Repair(auto_fixable=False, repair_class=RepairClass.WRITER_FIX),
        )
        applied, _refused = apply_safe_fixes(self.repo, [unsafe], self.cfg)
        self.assertEqual(applied, [])
        self.assertEqual((self.repo / "src" / "A.java").read_text(encoding="utf-8"), SOURCE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
