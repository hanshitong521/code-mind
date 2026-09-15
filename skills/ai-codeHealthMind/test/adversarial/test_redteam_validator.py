"""Adversarial suite C: red-team the EvidenceValidator (spec §21).

The three specification cases are exercised against the **real**
``chm.core.evidencevalidator.EvidenceValidator`` -- no mock, no stub:

* **RV-001** a finding that claims "this method has no references" while the
  method is in fact reachable (MyBatis mapper XML, a Java call site, a Spring
  entry point) must be **rejected**;
* **RV-002** a "duplicated code, abstract it" finding whose two regions encode
  *different* business rules must be **downgraded** (never kept at MEDIUM+);
* **RV-003** an "O(n^2) performance incident" finding whose collection is a
  compile-time constant of <= 5 elements must be **downgraded**.

A negative control is included for each family: a genuinely unreferenced
symbol, a genuinely equivalent duplication and a genuinely unbounded loop must
NOT be rejected, otherwise the validator would be a rubber stamp.

Every verdict is printed.  Where the implementation does not meet the
specification the test records ``REDTEAM_GAP`` with the real verdict instead of
pretending it passed.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "golden"))

from _chm import golden_config  # noqa: E402

from chm.contracts import ChangeKind, ChangedFile, ReviewMode, ScanContext, language_of  # noqa: E402
from chm.core.evidencevalidator import EvidenceValidator, Verdict  # noqa: E402
from chm.schema import (  # noqa: E402
    Category,
    EvidenceItem,
    EvidenceKind,
    Finding,
    Location,
    Severity,
)

#: Cases where the specification demands a rejection/downgrade but the
#: implementation returns something else.  Filled in by ``setUpClass``.
REDTEAM_GAPS: list[str] = []


def _finding(
    *,
    fid: str,
    rule_id: str,
    category: Category,
    severity: Severity,
    file: str,
    line: int = 1,
    end_line: int = 1,
    symbol: str | None = None,
    title: str = "",
    detail: str = "",
    raw: dict | None = None,
) -> Finding:
    return Finding(
        id=fid,
        rule_id=rule_id,
        category=category,
        title=title or rule_id,
        severity=severity,
        confidence=0.8,
        location=Location(file=file, start_line=line, end_line=end_line, symbol=symbol),
        evidence=[
            EvidenceItem(
                provider="native-java",
                result="hit",
                kind=EvidenceKind.DETERMINISTIC,
                rule_id=rule_id,
                detail=detail or title or rule_id,
                raw=raw or {},
            )
        ],
    )


#: A variant of ``Perf.java`` whose five-element literal lives *inside* the
#: loop body, i.e. inside the region the finding points at.
PERF2_JAVA = """package demo.rv;

import java.util.Arrays;
import java.util.List;

public class Perf2 {
    public boolean check(List<String> values) {
        List<String> regions = Arrays.asList("eu", "us", "apac", "latam", "mea");
        for (String a : values) {
            for (String b : values) {
                if (regions.contains(b)) {
                    return true;
                }
            }
        }
        return false;
    }
}
"""


class _Base(unittest.TestCase):
    """Builds a real ScanContext over a temp tree, then runs the validator."""

    files: dict[str, str] = {}

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="chm-redteam-"))
        for rel, text in self.files.items():
            p = self.tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        self.cfg = golden_config()
        self.ctx = ScanContext(
            repo_root=self.tmp,
            mode=ReviewMode.REPO,
            changed_files=[
                ChangedFile(
                    path=rel,
                    change_kind=ChangeKind.MODIFIED,
                    language=language_of(rel),
                )
                for rel in sorted(self.files)
            ],
            repo_files=sorted(self.files),
            config=self.cfg,
        )
        self.validator = EvidenceValidator(self.cfg, self.ctx)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def verdict(self, finding: Finding) -> tuple[Verdict, Severity, str]:
        outcome = self.validator.validate_one(finding)
        return outcome.verdict, outcome.new_severity, outcome.reason


# ---------------------------------------------------------------------------
# RV-001
# ---------------------------------------------------------------------------


class RV001Test(_Base):
    files = {
        "src/main/java/demo/rv/Mapper.java": (
            "package demo.rv;\n\n"
            "import java.util.List;\n"
            "import org.apache.ibatis.annotations.Mapper;\n\n"
            "@Mapper\n"
            "public interface Mapper {\n"
            "    List<String> selectByStatus(String status);\n"
            "}\n"
        ),
        "src/main/resources/mapper/Mapper.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<mapper namespace="demo.rv.Mapper">\n'
            '    <select id="selectByStatus" resultType="java.lang.String">\n'
            "        SELECT name FROM rows WHERE status = #{status}\n"
            "    </select>\n"
            "</mapper>\n"
        ),
        "src/main/java/demo/rv/Support.java": (
            "package demo.rv;\n\n"
            "import java.util.List;\n"
            "import org.springframework.stereotype.Component;\n\n"
            "@Component\n"
            "public class Support {\n"
            "    private List<String> selectByStatus(String status) {\n"
            "        return List.of();\n"
            "    }\n"
            "}\n"
        ),
        "src/main/java/demo/rv/Caller.java": (
            "package demo.rv;\n\n"
            "public class Caller {\n"
            "    public String call(Mapper mapper) {\n"
            "        return mapper.selectByStatus(\"ACTIVE\").toString();\n"
            "    }\n"
            "}\n"
        ),
        "src/main/java/demo/rv/TrulyUnused.java": (
            "package demo.rv;\n\n"
            "public class TrulyUnused {\n"
            "    private String neverReferencedAnywhere() {\n"
            "        return \"x\";\n"
            "    }\n"
            "}\n"
        ),
    }

    def test_rv001_mapper_xml_reference_is_rejected(self) -> None:
        """A method reached only from MyBatis mapper XML must not be called dead."""
        f = _finding(
            fid="CHM-000001",
            rule_id="CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD",
            category=Category.DEAD_CODE,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/Support.java",
            line=8,
            symbol="selectByStatus",
            title="Private method 'selectByStatus' is never referenced",
        )
        verdict, sev, reason = self.verdict(f)
        print(f"\n  RV-001 (mapper XML only) -> {verdict.value} ({sev.value}): {reason[:200]}")
        self.assertIn(
            verdict,
            (Verdict.REJECTED, Verdict.UNCERTAIN),
            "a mapper-XML-reachable method must not be accepted as dead code",
        )
        if verdict is Verdict.UNCERTAIN:
            REDTEAM_GAPS.append(
                "RV-001 mapper-XML case returned UNCERTAIN instead of REJECTED"
            )

    def test_rv001_java_call_site_is_rejected(self) -> None:
        f = _finding(
            fid="CHM-000002",
            rule_id="CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD",
            category=Category.DEAD_CODE,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/Support.java",
            line=8,
            symbol="selectByStatus",
            title="Private method 'selectByStatus' is never referenced",
        )
        verdict, sev, reason = self.verdict(f)
        print(f"  RV-001 (java call site) -> {verdict.value} ({sev.value}): {reason[:160]}")
        self.assertIs(verdict, Verdict.REJECTED)

    def test_rv001_spring_entry_point_is_rejected(self) -> None:
        """`@Component`-adjacent symbol: the dynamic-entry scan must catch it."""
        files = dict(self.files)
        files["src/main/java/demo/rv/SpringEntry.java"] = (
            "package demo.rv;\n\n"
            "import org.springframework.stereotype.Component;\n\n"
            "@Component\n"
            "public class SpringEntry {\n"
            "    private String scheduledHandler() {\n"
            "        return \"x\";\n"
            "    }\n"
            "}\n"
        )
        self.files = files
        self.setUp()
        try:
            f = _finding(
                fid="CHM-000003",
                rule_id="CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD",
                category=Category.DEAD_CODE,
                severity=Severity.MEDIUM,
                file="src/main/java/demo/rv/SpringEntry.java",
                line=8,
                symbol="scheduledHandler",
                title="Private method 'scheduledHandler' is never referenced",
            )
            verdict, sev, reason = self.verdict(f)
            print(
                f"  RV-001 (spring entry) -> {verdict.value} ({sev.value}): {reason[:160]}"
            )
            self.assertIn(verdict, (Verdict.REJECTED, Verdict.UNCERTAIN))
        finally:
            self.tearDown()

    def test_rv001_negative_control_is_not_rejected(self) -> None:
        """A genuinely unreferenced symbol must still be accepted."""
        f = _finding(
            fid="CHM-000004",
            rule_id="CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD",
            category=Category.DEAD_CODE,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/TrulyUnused.java",
            line=4,
            symbol="neverReferencedAnywhere",
            title="Private method 'neverReferencedAnywhere' is never referenced",
        )
        verdict, sev, reason = self.verdict(f)
        print(f"  RV-001 (negative control) -> {verdict.value} ({sev.value}): {reason[:160]}")
        self.assertNotIn(
            verdict,
            (Verdict.REJECTED,),
            "the validator must not reject everything",
        )


# ---------------------------------------------------------------------------
# RV-002
# ---------------------------------------------------------------------------


class RV002Test(_Base):
    files = {
        "src/main/java/demo/rv/Duplication.java": (
            "package demo.rv;\n\n"
            "import java.math.BigDecimal;\n\n"
            "public class Duplication {\n"
            "    public BigDecimal refund(String code, BigDecimal paid, int days) {\n"
            "        switch (code) {\n"
            "            case \"DAMAGED\":\n"
            "                return paid;\n"
            "            default:\n"
            "                return BigDecimal.ZERO;\n"
            "        }\n"
            "    }\n\n"
            "    public BigDecimal coupon(String code, BigDecimal paid) {\n"
            "        if (code == null || code.isEmpty()) {\n"
            "            return BigDecimal.ZERO;\n"
            "        }\n"
            "        return BigDecimal.valueOf(code.length()).min(paid);\n"
            "    }\n"
            "}\n"
        ),
    }

    def test_rv002_known_gap_jdk_type_names_inflate_overlap(self) -> None:
        """KNOWN GAP -- RV-002 does not fire on the realistic refund/coupon pair.

        ``_domain_nouns`` splits ``BigDecimal`` into the tokens ``big`` and
        ``decimal``.  Neither is in ``_DOMAIN_STOPWORDS``, so two methods that
        merely share a *type* accumulate shared "domain nouns".  The measured
        overlap for refund vs coupon is 0.4167, just above the 0.40 threshold,
        so the finding stays CONFIRMED at MEDIUM even though the two methods
        encode genuinely different business rules.

        This test asserts the *real* behaviour and records the gap.  If the
        validator is fixed the assertion fails, which is the signal to delete
        the gap entry.
        """
        f = _finding(
            fid="CHM-000010",
            rule_id="CHM-JAVA-NAT-DUPLICATE-BLOCK",
            category=Category.DUPLICATION,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/Duplication.java",
            line=5,
            end_line=13,
            title="Duplicated block: refund and coupon share the same shape",
            detail="identical normalized token block found elsewhere",
            raw={
                "duplicate_of": {
                    "file": "src/main/java/demo/rv/Duplication.java",
                    "start_line": 15,
                    "end_line": 21,
                }
            },
        )
        pair = self.validator._duplicate_regions(f)
        self.assertIsNotNone(
            pair, "the two regions must be readable for this gap to be meaningful"
        )
        jaccard, shared = self.validator._noun_jaccard(*pair)
        verdict, sev, reason = self.verdict(f)
        print(
            f"\n  RV-002 (refund/coupon, KNOWN GAP) -> {verdict.value} ({sev.value}) "
            f"jaccard={jaccard:.4f} shared={sorted(shared)}"
        )
        if verdict is Verdict.CONFIRMED and sev.rank > Severity.LOW.rank:
            REDTEAM_GAPS.append(
                "RV-002: refund-vs-coupon duplication stays "
                f"{verdict.value}/{sev.value} because JDK type names inflate the "
                f"domain-noun overlap to {jaccard:.4f} (threshold 0.40); shared="
                f"{sorted(shared)}. Spec 21 expects DOWNGRADED/REJECTED."
            )
        else:
            self.fail(
                "RV-002 gap appears to be FIXED (verdict=%s sev=%s) -- remove the "
                "KNOWN GAP entry from test_redteam_validator.py"
                % (verdict.value, sev.value)
            )

    def test_rv002_negative_control_same_region_stays(self) -> None:
        """Pointing at the *same* region must not be treated as different semantics."""
        f = _finding(
            fid="CHM-000011",
            rule_id="CHM-JAVA-NAT-DUPLICATE-BLOCK",
            category=Category.DUPLICATION,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/Duplication.java",
            line=5,
            end_line=13,
            title="Duplicated block",
            raw={
                "duplicate_of": {
                    "file": "src/main/java/demo/rv/Duplication.java",
                    "start_line": 5,
                    "end_line": 13,
                }
            },
        )
        verdict, sev, reason = self.verdict(f)
        print(f"  RV-002 (negative control) -> {verdict.value} ({sev.value}): {reason[:140]}")
        self.assertNotIn(verdict, (Verdict.REJECTED,))


class RV002SemanticsTest(_Base):
    """The RV-002 guard must fire when two regions share no domain vocabulary."""

    files = {
        "src/main/java/demo/rv/Semantics.java": (
            """package demo.rv;

import java.math.BigDecimal;

public class Semantics {
    public void sendInvoiceEmail(String customerEmail, String invoiceNo) {
        if (customerEmail == null) {
            return;
        }
        mailer.send(customerEmail, invoiceNo);
    }

    public BigDecimal calculateTaxRate(String regionCode, BigDecimal grossAmount) {
        if (regionCode == null) {
            return BigDecimal.ZERO;
        }
        return grossAmount.multiply(taxRate(regionCode));
    }
}
"""
        ),
    }

    def test_rv002_different_domain_semantics_is_downgraded(self) -> None:
        f = _finding(
            fid="CHM-000013",
            rule_id="CHM-JAVA-NAT-DUPLICATE-BLOCK",
            category=Category.DUPLICATION,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/Semantics.java",
            line=6,
            end_line=11,
            title="Duplicated block: sendInvoiceEmail and calculateTaxRate share a shape",
            detail="identical normalized token block found elsewhere",
            raw={
                "duplicate_of": {
                    "file": "src/main/java/demo/rv/Semantics.java",
                    "start_line": 13,
                    "end_line": 18,
                }
            },
        )
        verdict, sev, reason = self.verdict(f)
        print(
            f"\n  RV-002 (disjoint semantics) -> {verdict.value} ({sev.value}): {reason[:200]}"
        )
        self.assertIn(
            verdict,
            (Verdict.DOWNGRADED, Verdict.REJECTED),
            "two blocks with unrelated business vocabulary must not stay MEDIUM+",
        )
        self.assertLessEqual(sev.rank, Severity.LOW.rank)


# ---------------------------------------------------------------------------
# RV-003
# ---------------------------------------------------------------------------


class RV003Test(_Base):
    files = {
        "src/main/java/demo/rv/Perf.java": (
            "package demo.rv;\n\n"
            "import java.util.Arrays;\n"
            "import java.util.List;\n\n"
            "public class Perf {\n"
            "    private static final List<String> REGIONS = Arrays.asList(\"eu\", \"us\", \"apac\", \"latam\", \"mea\");\n\n"
            "    public boolean check(List<String> values) {\n"
            "        for (String a : values) {\n"
            "            for (String b : values) {\n"
            "                if (REGIONS.contains(b)) {\n"
            "                    return true;\n"
            "                }\n"
            "            }\n"
            "        }\n"
            "        return false;\n"
            "    }\n"
            "}\n"
        ),
    }

    def test_rv003_known_gap_constant_declared_outside_region(self) -> None:
        """KNOWN GAP -- the constant is declared outside the finding region.

        ``_loop_bound`` only inspects the text of the reported region (plus the
        ``raw`` evidence keys, which no producer in ``src/`` ever sets).  In the
        realistic shape -- ``private static final List<String> REGIONS =
        Arrays.asList(...)`` at field level, the loop in a method below -- the
        five-element literal is never seen, so the O(n^2) finding stays
        CONFIRMED at MEDIUM.

        This test asserts the *real* behaviour and records the gap.  If the
        validator is fixed the assertion fails, which is the signal to delete
        the gap entry.
        """
        f = _finding(
            fid="CHM-000020",
            rule_id="CHM-JAVA-NAT-ON2",
            category=Category.PERFORMANCE,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/Perf.java",
            line=10,
            end_line=15,
            title="Nested loop over REGIONS is O(n^2)",
            detail="quadratic membership test",
        )
        bound = self.validator._loop_bound(f)
        verdict, sev, reason = self.verdict(f)
        print(
            f"\n  RV-003 (constant declared outside region, KNOWN GAP) -> "
            f"{verdict.value} ({sev.value}) resolved_bound={bound}"
        )
        if verdict is Verdict.CONFIRMED and sev.rank > Severity.LOW.rank:
            REDTEAM_GAPS.append(
                "RV-003: a nested loop over a 5-element field-level constant stays "
                f"{verdict.value}/{sev.value} because _loop_bound only reads the "
                "finding's own region (resolved bound=None) and no producer ever "
                "attaches a loop_collection_size evidence key. Spec 21 expects "
                "DOWNGRADED."
            )
        else:
            self.fail(
                "RV-003 gap appears to be FIXED (verdict=%s sev=%s bound=%s) -- remove "
                "the KNOWN GAP entry from test_redteam_validator.py"
                % (verdict.value, sev.value, bound)
            )

    def test_rv003_in_region_constant_is_downgraded(self) -> None:
        """The literal lives inside the reported region -> the guard must fire."""
        rel = "src/main/java/demo/rv/Perf2.java"
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(PERF2_JAVA, encoding="utf-8")
        f = _finding(
            fid="CHM-000023",
            rule_id="CHM-JAVA-NAT-ON2",
            category=Category.PERFORMANCE,
            severity=Severity.MEDIUM,
            file=rel,
            line=8,
            end_line=16,
            title="Nested loop over a literal region list is O(n^2)",
            detail="quadratic membership test",
        )
        verdict, sev, reason = self.verdict(f)
        print(
            f"\n  RV-003 (in-region constant) -> {verdict.value} ({sev.value}): {reason[:200]}"
        )
        self.assertIs(verdict, Verdict.DOWNGRADED)
        self.assertLessEqual(sev.rank, Severity.LOW.rank)

    def test_rv003_explicit_loop_bound_evidence_is_downgraded(self) -> None:
        f = _finding(
            fid="CHM-000021",
            rule_id="CHM-JAVA-NAT-ON2",
            category=Category.PERFORMANCE,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/Perf.java",
            line=10,
            title="Nested loop is O(n^2)",
            raw={"loop_collection_size": 4},
        )
        verdict, sev, reason = self.verdict(f)
        print(f"  RV-003 (explicit bound=4) -> {verdict.value} ({sev.value}): {reason[:180]}")
        self.assertIs(verdict, Verdict.DOWNGRADED)
        self.assertIs(f.perf_confidence.value, "SUSPECTED")

    def test_rv003_negative_control_unbounded_is_not_downgraded(self) -> None:
        """An unbounded nested loop with no bound evidence must not be softened."""
        f = _finding(
            fid="CHM-000022",
            rule_id="CHM-JAVA-NAT-ON2",
            category=Category.PERFORMANCE,
            severity=Severity.MEDIUM,
            file="src/main/java/demo/rv/Perf.java",
            line=10,
            end_line=15,
            title="Nested loop over a request-scoped collection is O(n^2)",
            detail="quadratic membership test on a bulk-loaded list",
        )
        verdict, sev, reason = self.verdict(f)
        print(f"  RV-003 (negative control) -> {verdict.value} ({sev.value}): {reason[:180]}")
        self.assertNotEqual(verdict, Verdict.DOWNGRADED)

    def test_high_without_deterministic_evidence_is_capped(self) -> None:
        """Spec §3.1: HIGH with only semantic evidence cannot stand."""
        f = Finding(
            id="CHM-000030",
            rule_id="CHM-REV-SEM-0001",
            category=Category.OVER_ENGINEERING,
            title="This abstraction looks unnecessary",
            severity=Severity.HIGH,
            confidence=0.5,
            location=Location(file="src/main/java/demo/rv/Perf.java", start_line=5),
            evidence=[
                EvidenceItem(
                    provider="reviewer:simplicity",
                    result="impression",
                    kind=EvidenceKind.SEMANTIC,
                    detail="looks over-engineered",
                )
            ],
        )
        verdict, sev, reason = self.verdict(f)
        print(f"\n  §3.1 (semantic-only HIGH) -> {verdict.value} ({sev.value}): {reason[:180]}")
        self.assertIs(verdict, Verdict.DOWNGRADED)
        self.assertLessEqual(sev.rank, Severity.MEDIUM.rank)

    def test_all_providers_failed_yields_uncertain(self) -> None:
        f = Finding(
            id="CHM-000031",
            rule_id="CHM-PMD-UNUSED-0001",
            category=Category.DEAD_CODE,
            title="Unused private method",
            severity=Severity.MEDIUM,
            confidence=0.5,
            location=Location(
                file="src/main/java/demo/rv/Perf.java", start_line=5, symbol="check"
            ),
            evidence=[
                EvidenceItem(
                    provider="pmd",
                    result="error",
                    kind=EvidenceKind.DETERMINISTIC,
                    detail="tool unavailable",
                    raw={"tool_error": True},
                )
            ],
        )
        verdict, _sev, reason = self.verdict(f)
        print(f"  all-providers-failed -> {verdict.value}: {reason[:160]}")
        self.assertIs(verdict, Verdict.UNCERTAIN)
        self.assertFalse(f.repair.auto_fixable)
        self.assertEqual(f.repair.repair_class.value, "MANUAL_DECISION")


class RedTeamSummary(unittest.TestCase):
    def test_redteam_gaps_are_reported(self) -> None:
        if REDTEAM_GAPS:
            print("\n  REDTEAM_GAP:")
            for gap in REDTEAM_GAPS:
                print("    - " + gap)
        else:
            print("\n  red-team: no gaps recorded")
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
