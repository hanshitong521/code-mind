"""Spec §4 executable schema rules (CHM-SCHEMA-001 .. 005) + lifecycle + IO."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401  (puts src/ on sys.path)

from chm.errors import SchemaError
from chm.schema import (
    Category,
    Decision,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingStatus,
    Location,
    Repair,
    RepairClass,
    Severity,
)


def _legal_finding(**overrides) -> Finding:
    base = dict(
        id="CHM-000123",
        rule_id="CHM-JAVA-DEAD-001",
        category=Category.DEAD_CODE,
        title="unused private method",
        severity=Severity.MEDIUM,
        confidence=0.75,
        location=Location(file="src/main/java/A.java", start_line=10, end_line=12, symbol="m"),
    )
    base.update(overrides)
    return Finding(**base)


class SchemaRequiredFieldsTest(unittest.TestCase):
    """CHM-SCHEMA-001 -- id / rule_id / title / location.file are mandatory."""

    def test_valid_finding_passes(self):
        _legal_finding().validate_schema()  # must not raise

    def test_missing_id_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(id="").validate_schema()
        self.assertIn("CHM-SCHEMA-001", str(ctx.exception))
        self.assertIn("id", str(ctx.exception))

    def test_malformed_id_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(id="FINDING-1").validate_schema()
        self.assertIn("CHM-SCHEMA-001", str(ctx.exception))

    def test_missing_rule_id_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(rule_id="").validate_schema()
        self.assertIn("rule_id", str(ctx.exception))

    def test_malformed_rule_id_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(rule_id="CHM").validate_schema()
        self.assertIn("rule_id", str(ctx.exception))

    def test_missing_title_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(title="").validate_schema()
        self.assertIn("title", str(ctx.exception))

    def test_missing_location_file_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(location=Location(file="")).validate_schema()
        self.assertIn("location.file", str(ctx.exception))

    def test_error_carries_finding_id_context(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(title="").validate_schema()
        self.assertEqual(ctx.exception.context.get("finding_id"), "CHM-000123")
        self.assertEqual(ctx.exception.code, "CHM_SCHEMA_ERROR")


class SchemaEnumTest(unittest.TestCase):
    """CHM-SCHEMA-002 -- severity and category must be real enum members."""

    def test_severity_must_be_severity_enum(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(severity="HIGH").validate_schema()
        self.assertIn("CHM-SCHEMA-002", str(ctx.exception))
        self.assertIn("severity", str(ctx.exception))

    def test_bogus_severity_string_rejected(self):
        with self.assertRaises(SchemaError):
            _legal_finding(severity="BLOCKER").validate_schema()

    def test_category_must_be_category_enum(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(category="DEAD_CODE").validate_schema()
        self.assertIn("CHM-SCHEMA-002", str(ctx.exception))
        self.assertIn("category", str(ctx.exception))

    def test_all_severities_accepted(self):
        for sev in Severity:
            _legal_finding(severity=sev).validate_schema()

    def test_all_categories_accepted(self):
        for cat in Category:
            _legal_finding(category=cat).validate_schema()


class SchemaConfidenceTest(unittest.TestCase):
    """CHM-SCHEMA-003 -- confidence lives in the closed interval [0, 1]."""

    def test_boundaries_accepted(self):
        _legal_finding(confidence=0.0).validate_schema()
        _legal_finding(confidence=1.0).validate_schema()

    def test_above_one_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(confidence=1.0001).validate_schema()
        self.assertIn("CHM-SCHEMA-003", str(ctx.exception))

    def test_below_zero_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(confidence=-0.2).validate_schema()
        self.assertIn("CHM-SCHEMA-003", str(ctx.exception))

    def test_non_numeric_rejected(self):
        with self.assertRaises(SchemaError) as ctx:
            _legal_finding(confidence="high").validate_schema()
        self.assertIn("must be numeric", str(ctx.exception))

    def test_clamp_confidence_pulls_into_range(self):
        f = _legal_finding(confidence=1.8)
        f.clamp_confidence()
        self.assertEqual(f.confidence, 1.0)
        f.validate_schema()


class SchemaEvidenceGateTest(unittest.TestCase):
    """CHM-SCHEMA-004 -- HIGH/CRITICAL cannot become VALIDATED without evidence."""

    def _at_evidence_collected(self, severity: Severity, evidence: list[EvidenceItem]):
        f = _legal_finding(severity=severity, evidence=evidence)
        f.decision = Decision(status=FindingStatus.EVIDENCE_COLLECTED)
        return f

    def test_high_without_evidence_cannot_validate(self):
        f = self._at_evidence_collected(Severity.HIGH, [])
        with self.assertRaises(SchemaError) as ctx:
            f.transition(FindingStatus.VALIDATED)
        self.assertIn("CHM-SCHEMA-004", str(ctx.exception))
        self.assertEqual(f.decision.status, FindingStatus.EVIDENCE_COLLECTED)

    def test_critical_without_evidence_cannot_validate(self):
        f = self._at_evidence_collected(Severity.CRITICAL, [])
        with self.assertRaises(SchemaError) as ctx:
            f.transition(FindingStatus.VALIDATED)
        self.assertIn("CHM-SCHEMA-004", str(ctx.exception))

    def test_high_with_evidence_validates(self):
        f = self._at_evidence_collected(
            Severity.HIGH,
            [EvidenceItem(provider="pmd", result="hit", kind=EvidenceKind.DETERMINISTIC)],
        )
        f.transition(FindingStatus.VALIDATED)
        self.assertEqual(f.decision.status, FindingStatus.VALIDATED)

    def test_medium_without_evidence_may_validate(self):
        f = self._at_evidence_collected(Severity.MEDIUM, [])
        f.transition(FindingStatus.VALIDATED)
        self.assertEqual(f.decision.status, FindingStatus.VALIDATED)

    def test_validate_evidence_raises_directly(self):
        f = _legal_finding(severity=Severity.CRITICAL, evidence=[])
        with self.assertRaises(SchemaError):
            f.validate_evidence()

    def test_evidence_requires_provider(self):
        with self.assertRaises(TypeError):
            EvidenceItem(result="hit")  # provider is a required field


class SchemaUncertainSafetyTest(unittest.TestCase):
    """CHM-SCHEMA-005 -- an UNCERTAIN finding is never auto-fixable."""

    def test_uncertain_auto_fixable_rejected(self):
        f = _legal_finding(
            decision=Decision(status=FindingStatus.UNCERTAIN),
            repair=Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX),
        )
        with self.assertRaises(SchemaError) as ctx:
            f.validate_uncertain_safety()
        self.assertIn("CHM-SCHEMA-005", str(ctx.exception))

    def test_uncertain_safe_auto_fix_class_rejected_even_if_flag_false(self):
        f = _legal_finding(
            decision=Decision(status=FindingStatus.UNCERTAIN),
            repair=Repair(auto_fixable=False, repair_class=RepairClass.SAFE_AUTO_FIX),
        )
        with self.assertRaises(SchemaError):
            f.validate_uncertain_safety()

    def test_uncertain_manual_decision_is_allowed(self):
        f = _legal_finding(
            decision=Decision(status=FindingStatus.UNCERTAIN),
            repair=Repair(auto_fixable=False, repair_class=RepairClass.MANUAL_DECISION),
        )
        f.validate_uncertain_safety()  # must not raise

    def test_validate_all_covers_both_checks(self):
        f = _legal_finding(
            decision=Decision(status=FindingStatus.UNCERTAIN),
            repair=Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX),
        )
        with self.assertRaises(SchemaError):
            f.validate_all()

    def test_non_uncertain_auto_fixable_is_allowed(self):
        f = _legal_finding(
            decision=Decision(status=FindingStatus.DETECTED),
            repair=Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX),
        )
        f.validate_uncertain_safety()  # must not raise


class LifecycleTest(unittest.TestCase):
    """Spec §9 -- only the documented transitions are legal."""

    def test_detected_to_fixed_is_illegal(self):
        f = _legal_finding()
        with self.assertRaises(SchemaError) as ctx:
            f.transition(FindingStatus.FIXED)
        self.assertIn("illegal lifecycle transition", str(ctx.exception))
        self.assertIn("DETECTED -> FIXED", str(ctx.exception))

    def test_detected_to_validated_is_illegal(self):
        f = _legal_finding()
        with self.assertRaises(SchemaError):
            f.transition(FindingStatus.VALIDATED)

    def test_legal_path_is_recorded_in_history(self):
        f = _legal_finding(
            evidence=[EvidenceItem(provider="pmd", result="hit", kind=EvidenceKind.DETERMINISTIC)]
        )
        f.history.append(FindingStatus.DETECTED.value)
        f.transition(FindingStatus.EVIDENCE_COLLECTED)
        f.transition(FindingStatus.VALIDATED)
        f.transition(FindingStatus.BLOCK, reason="critical path")
        f.transition(FindingStatus.FIXED)
        f.transition(FindingStatus.REVERIFIED)
        f.transition(FindingStatus.CLOSED)
        self.assertEqual(
            f.history,
            [
                "DETECTED",
                "EVIDENCE_COLLECTED",
                "VALIDATED",
                "BLOCK",
                "FIXED",
                "REVERIFIED",
                "CLOSED",
            ],
        )
        self.assertEqual(f.decision.status, FindingStatus.CLOSED)
        self.assertEqual(f.decision.reason, "critical path")

    def test_closed_is_terminal(self):
        f = _legal_finding(decision=Decision(status=FindingStatus.CLOSED))
        with self.assertRaises(SchemaError):
            f.transition(FindingStatus.WARN)

    def test_validated_to_fixed_is_illegal(self):
        f = _legal_finding(
            decision=Decision(status=FindingStatus.VALIDATED),
            evidence=[EvidenceItem(provider="pmd", result="hit")],
        )
        with self.assertRaises(SchemaError):
            f.transition(FindingStatus.FIXED)


class RoundTripTest(unittest.TestCase):
    """``to_dict`` / ``from_dict`` must be lossless for the modelled fields."""

    def test_round_trip_preserves_payload(self):
        original = _legal_finding(
            severity=Severity.HIGH,
            confidence=0.8123,
            introduced_by_current_diff=True,
            evidence=[
                EvidenceItem(
                    provider="pmd",
                    result="hit",
                    kind=EvidenceKind.DETERMINISTIC,
                    rule_id="CHM-JAVA-DEAD-001",
                    detail="UnusedPrivateMethod",
                    references=0,
                ),
                EvidenceItem(
                    provider="reviewer:simplicity",
                    result="flagged",
                    kind=EvidenceKind.SEMANTIC,
                    detail="single implementation abstraction",
                ),
            ],
            decision=Decision(status=FindingStatus.WARN, block_merge=False, reason="budget"),
            repair=Repair(auto_fixable=False, repair_class=RepairClass.WRITER_FIX, recipe=None),
            sources=["pmd", "reviewer:simplicity", "pmd"],
            historical=False,
        )
        original.history.extend(["DETECTED", "EVIDENCE_COLLECTED", "VALIDATED", "WARN"])

        restored = Finding.from_dict(original.to_dict())
        self.assertEqual(restored.to_dict(), original.to_dict())
        self.assertEqual(restored.sources, ["pmd", "reviewer:simplicity"])
        self.assertEqual(len(restored.evidence), 2)
        self.assertEqual(restored.evidence[0].kind, EvidenceKind.DETERMINISTIC)
        self.assertEqual(restored.evidence[1].kind, EvidenceKind.SEMANTIC)
        self.assertEqual(restored.decision.status, FindingStatus.WARN)

    def test_round_trip_is_stable_twice(self):
        original = _legal_finding(severity=Severity.CRITICAL)
        once = Finding.from_dict(original.to_dict())
        twice = Finding.from_dict(once.to_dict())
        self.assertEqual(once.to_dict(), twice.to_dict())

    def test_canonical_key_is_identity_without_id(self):
        a = _legal_finding(id="CHM-000001")
        b = _legal_finding(id="CHM-999999")
        self.assertEqual(a.canonical_key(), b.canonical_key())
        c = _legal_finding(id="CHM-000001", location=Location(file="other.java"))
        self.assertNotEqual(a.canonical_key(), c.canonical_key())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
