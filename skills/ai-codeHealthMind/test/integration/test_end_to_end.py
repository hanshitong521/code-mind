"""Full-chain end-to-end runs through the real :class:`Orchestrator`."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

import helpers
from helpers import CHMTestCase, toolchain_available, write_files

from chm.config import Config, load_config
from chm.contracts import ReviewMode
from chm.core.orchestrator import Orchestrator, rerun_gate
from chm.reports.sarif import validate_sarif

NO_EXTERNAL_TOOLS = """\
version: 1
mode: repo
tools:
  pmd:
    enabled: false
  cpd:
    enabled: false
  spotbugs:
    enabled: false
  semgrep:
    enabled: false
  knip:
    enabled: false
  openrewrite:
    enabled: false
  compile:
    enabled: false
  test:
    enabled: false
"""

REAL_TOOLS = """\
version: 1
mode: repo
tools:
  pmd:
    enabled: true
  cpd:
    enabled: true
  spotbugs:
    enabled: true
  semgrep:
    enabled: false
  knip:
    enabled: true
  openrewrite:
    enabled: false
  compile:
    enabled: true
  test:
    enabled: false
"""

SQL_NO_WHERE = """\
package p;

public class Repo {
    public void deactivateAll() {
        String sql = "UPDATE users SET active = 0";
        execute(sql);
    }

    private void execute(String sql) {
    }
}
"""

SQL_WITH_WHERE = """\
package p;

public class Repo {
    public void deactivateAll() {
        String sql = "UPDATE users SET active = 0 WHERE id = ?";
        execute(sql);
    }

    private void execute(String sql) {
    }
}
"""

CLEAN_JAVA = """\
package p;

public class Clean {
    public int add(int a, int b) {
        return a + b;
    }
}
"""

LEAKY_JAVA = """\
package p;

import java.io.FileInputStream;
import java.io.IOException;

public class Leaky {
    private void unusedHelper() {
        int x = 1;
    }

    public int read(String name) throws IOException {
        FileInputStream in = new FileInputStream(name);
        return in.read();
    }
}
"""


class EndToEndBase(CHMTestCase):
    def orchestrator(self, repo: Path, config_file: str = NO_EXTERNAL_TOOLS, **kwargs) -> Orchestrator:
        write_files(repo, {".codehealth.yml": config_file})
        cfg = load_config(repo / ".codehealth.yml", repo_root=repo)
        return Orchestrator(
            repo_root=repo,
            config=cfg,
            mode=ReviewMode.REPO,
            options={"whole_file": True, "pmd_scope": "repo"},
            **kwargs,
        )

    def artefacts(self, run_dir: Path) -> dict[str, Path]:
        return {
            "report.json": run_dir / "report.json",
            "report.md": run_dir / "report.md",
            "report.sarif": run_dir / "report.sarif",
            "ledger.json": run_dir / "ledger.json",
            "scan.json": run_dir / "context" / "scan.json",
        }


class CleanRunTest(EndToEndBase):
    def test_a_clean_change_set_is_not_blocked(self):
        repo = self.temp_repo({"src/main/java/p/Clean.java": CLEAN_JAVA})
        result = self.orchestrator(repo).run()
        self.assertIn(result.gate, ("PASS", "WARN"))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            [f for f in result.findings if f.severity.value in ("CRITICAL", "HIGH")], []
        )

    def test_a_documentation_only_change_is_clean(self):
        repo = self.temp_repo({"docs/guide.md": "# guide\n"})
        result = self.orchestrator(repo).run()
        self.assertEqual(result.gate, "PASS")
        self.assertEqual(result.exit_code, 0)


class CriticalInjectionTest(EndToEndBase):
    def test_update_without_where_blocks_the_merge(self):
        repo = self.temp_repo({"src/main/java/p/Repo.java": SQL_NO_WHERE})
        result = self.orchestrator(repo).run()

        self.assertEqual(result.gate, "BLOCK")
        self.assertEqual(result.exit_code, 1)
        criticals = [f for f in result.findings if f.severity.value == "CRITICAL"]
        self.assertTrue(criticals, [f.rule_id for f in result.findings])
        self.assertTrue(
            any(f.rule_id == "CHM-JAVA-NAT-UPDATE-NO-WHERE" for f in criticals),
            [f.rule_id for f in criticals],
        )
        self.assertIn("CRITICAL", json.dumps(result.report["gate"]["blockers"]))

    def test_high_total_score_cannot_rescue_the_block(self):
        repo = self.temp_repo({"src/main/java/p/Repo.java": SQL_NO_WHERE})
        result = self.orchestrator(repo).run()
        self.assertGreater(result.report["score"]["total"], 0.0)
        self.assertEqual(result.gate, "BLOCK")
        self.assertTrue(result.report["score"]["hard_gate"])


class RerunGateTest(EndToEndBase):
    def test_fixing_the_sql_closes_the_finding(self):
        repo = self.temp_repo({"src/main/java/p/Repo.java": SQL_NO_WHERE})
        first = self.orchestrator(repo).run()
        self.assertEqual(first.gate, "BLOCK")
        blocked_ids = [f.id for f in first.findings if f.severity.value == "CRITICAL"]
        self.assertTrue(blocked_ids)

        write_files(repo, {"src/main/java/p/Repo.java": SQL_WITH_WHERE})
        cfg = load_config(repo / ".codehealth.yml", repo_root=repo)
        rerun = rerun_gate(
            repo_root=repo,
            config=cfg,
            previous_report=first.report,
            mode=ReviewMode.REPO,
            options={"whole_file": True, "pmd_scope": "repo"},
        )

        self.assertIn(blocked_ids[0], rerun["closed"])
        self.assertEqual(rerun["new_high_or_critical"], [])
        self.assertFalse(rerun["regression"])
        self.assertNotEqual(rerun["gate"], "BLOCK")

    def test_a_new_high_after_the_fix_is_a_regression(self):
        repo = self.temp_repo({"src/main/java/p/Clean.java": CLEAN_JAVA})
        first = self.orchestrator(repo).run()
        self.assertIn(first.gate, ("PASS", "WARN"))

        write_files(repo, {"src/main/java/p/Repo.java": SQL_NO_WHERE})
        cfg = load_config(repo / ".codehealth.yml", repo_root=repo)
        rerun = rerun_gate(
            repo_root=repo,
            config=cfg,
            previous_report=first.report,
            mode=ReviewMode.REPO,
            options={"whole_file": True, "pmd_scope": "repo"},
        )
        self.assertTrue(rerun["new_high_or_critical"])
        self.assertTrue(rerun["regression"])
        self.assertEqual(rerun["gate"], "BLOCK")


class ArtefactTest(EndToEndBase):
    def test_every_artefact_lands_on_disk(self):
        repo = self.temp_repo({"src/main/java/p/Repo.java": SQL_NO_WHERE})
        result = self.orchestrator(repo).run()

        for name, path in self.artefacts(result.run_dir).items():
            with self.subTest(artefact=name):
                self.assertTrue(path.is_file(), f"{name} was not written")
                self.assertGreater(path.stat().st_size, 0)

        report = json.loads((result.run_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["gate"], "BLOCK")
        self.assertEqual(report["run"]["run_id"], result.report["run"]["run_id"])
        self.assertIn("findings", report)
        self.assertIn("dedup", report)
        self.assertIn("baseline", report)

        sarif = json.loads((result.run_dir / "report.sarif").read_text(encoding="utf-8"))
        self.assertEqual(validate_sarif(sarif), [])

        ledger = json.loads((result.run_dir / "ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["run_id"], report["run"]["run_id"])
        self.assertEqual(ledger["gate"], "BLOCK")

        scan = json.loads((result.run_dir / "context" / "scan.json").read_text(encoding="utf-8"))
        self.assertEqual(scan["mode"], "repo")
        self.assertTrue(scan["changed_files"])

    def test_latest_pointer_is_updated(self):
        repo = self.temp_repo({"src/main/java/p/Clean.java": CLEAN_JAVA})
        result = self.orchestrator(repo).run()
        latest = json.loads((repo / ".codehealth" / "runs" / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(latest["run_id"], result.report["run"]["run_id"])

    def test_markdown_report_is_readable(self):
        repo = self.temp_repo({"src/main/java/p/Repo.java": SQL_NO_WHERE})
        result = self.orchestrator(repo).run()
        text = (result.run_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("# CodeHealthMind report", text)
        self.assertIn("## Gate", text)
        self.assertIn("CHM-JAVA-NAT-UPDATE-NO-WHERE", text)


class DeterminismTest(EndToEndBase):
    """Spec §41: two runs over identical input must produce identical bytes."""

    def test_report_json_is_byte_identical_across_two_runs(self):
        repo = self.temp_repo({"src/main/java/p/Repo.java": SQL_NO_WHERE})
        first = self.orchestrator(repo).run()
        second = self.orchestrator(repo).run()

        first_bytes = (first.run_dir / "report.json").read_bytes()
        second_bytes = (second.run_dir / "report.json").read_bytes()
        self.assertNotEqual(first.run_dir, second.run_dir)
        self.assertEqual(
            first_bytes,
            second_bytes,
            "report.json must be byte-identical for identical input (spec §41)",
        )

    def test_the_deterministic_blocks_are_identical(self):
        repo = self.temp_repo({"src/main/java/p/Repo.java": SQL_NO_WHERE})
        first = self.orchestrator(repo).run().report
        second = self.orchestrator(repo).run().report
        for key in ("findings", "score", "gate", "dedup", "summary", "baseline"):
            with self.subTest(block=key):
                self.assertEqual(
                    json.dumps(first[key], sort_keys=True),
                    json.dumps(second[key], sort_keys=True),
                )

    def test_finding_ids_are_stable(self):
        repo = self.temp_repo({"src/main/java/p/Repo.java": SQL_NO_WHERE})
        first = [f.id for f in self.orchestrator(repo).run().findings]
        second = [f.id for f in self.orchestrator(repo).run().findings]
        self.assertEqual(first, second)


class RealToolChainTest(EndToEndBase):
    """The key path, executed once with the genuine external tools."""

    def test_full_chain_with_real_pmd_cpd_spotbugs_knip_and_javac(self):
        available = {name: toolchain_available(name) for name in ("pmd", "cpd", "spotbugs", "knip", "javac")}
        for name, (ok, detail) in available.items():
            with self.subTest(tool=name):
                self.assertTrue(ok, f"{name} must be usable for this test: {detail}")

        repo = self.temp_repo(
            {
                "src/main/java/p/Leaky.java": LEAKY_JAVA,
                "package.json": json.dumps(
                    {
                        "name": "chain-probe",
                        "version": "1.0.0",
                        "main": "index.js",
                        "dependencies": {"left-pad": "^1.3.0"},
                    }
                ),
                "index.js": "console.log('hi');\n",
            }
        )
        result = self.orchestrator(repo, REAL_TOOLS).run()

        tools = {t["provider"]: t for t in result.report["tools"]}
        print("real tool results:")
        for name, info in sorted(tools.items()):
            print(f"  {name:12s} status={info['status']:12s} version={info['version']} "
                  f"findings={info['finding_count']}")
            print(f"      cmd={info['command']}")

        for name in ("javac", "pmd", "cpd", "spotbugs", "knip"):
            with self.subTest(tool=name):
                self.assertIn(name, tools)
                self.assertEqual(tools[name]["status"], "OK", tools[name].get("error"))
                self.assertIsNotNone(tools[name]["version"], f"{name} reported no real version")
                self.assertIsNotNone(tools[name]["command"], f"{name} recorded no real command")

        self.assertTrue(result.findings, "the fixture must produce real findings")
        providers = {p for f in result.findings for p in f.sources}
        print("finding sources:", sorted(providers))
        self.assertIn("pmd", providers)
        self.assertIn("knip", providers)
        if "spotbugs" in tools and tools["spotbugs"]["status"] == "OK":
            self.assertIn("spotbugs", providers)
        self.assertNotEqual(result.gate, "PASS")
        self.assertIn(result.exit_code, (0, 1, 3))

    def test_unavailable_semgrep_produces_an_evidence_gap(self):
        repo = self.temp_repo(
            {
                "src/main/java/p/Clean.java": CLEAN_JAVA,
                "rules/java/smoke.yml": (
                    "rules:\n"
                    "  - id: smoke\n"
                    "    pattern: $X\n"
                    "    message: smoke\n"
                    "    severity: INFO\n"
                ),
            }
        )
        cfg_text = NO_EXTERNAL_TOOLS.replace(
            "  semgrep:\n    enabled: false", "  semgrep:\n    enabled: true"
        )
        absent = str(self.temp_dir("chm-nosemgrep-") / "nope")
        saved = {
            k: os.environ.get(k)
            for k in ("CHM_SEMGREP_BIN", "CHM_TOOLCHAIN_ROOT")
        }
        os.environ["CHM_SEMGREP_BIN"] = absent
        os.environ.pop("CHM_TOOLCHAIN_ROOT", None)
        try:
            result = self.orchestrator(repo, cfg_text).run()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        gaps = [e for e in result.tool_errors if e.evidence_gap]
        self.assertTrue(gaps, "a missing semgrep must be recorded as an evidence gap")
        self.assertEqual(result.gate, "UNKNOWN")
        self.assertEqual(result.exit_code, 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
