"""CLI contract: init / probe / exit codes / explain / --help (real subprocesses)."""

from __future__ import annotations

import json
import unittest

import helpers
from helpers import CHMTestCase, run_cli, toolchain_available

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

COMPILE_ONLY = """\
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
    enabled: true
  test:
    enabled: false
"""

#: pmd is *enabled* here on purpose -- an enabled-but-unresolvable tool is the
#: case that must degrade to UNAVAILABLE + a MISSING evidence gap, whereas a
#: disabled tool is a different (also recorded) failure kind.
PMD_ENABLED = """\
version: 1
mode: repo
tools:
  pmd:
    enabled: true
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

UNUSED_METHOD_JAVA = """\
package p;

public class Sample {
    private void unusedHelper() {
        int x = 1;
    }

    public int add(int a, int b) {
        return a + b;
    }
}
"""

BROKEN_JAVA = """\
package p;

public class Broken {
    public int add(int a, int b) {
        return a + ;
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


def _repo_with(config: str, files: dict[str, str]) -> "helpers.CHMTestCase":
    raise NotImplementedError  # replaced by the mixin below


class CliMixin:
    """Small helpers shared by the CLI tests."""

    def make_project(self, config: str, files: dict[str, str]):
        payload = dict(files)
        payload[".codehealth.yml"] = config
        return self.temp_repo(payload)

    def review_json(self, repo, *extra):
        code, out, err = run_cli(["review", "--repo", "--format", "json", *extra], cwd=repo)
        self.assertTrue(out.strip(), f"no stdout from review (exit {code}); stderr={err[:2000]}")
        return code, json.loads(out)


class InitAndHelpTest(CHMTestCase):
    def test_init_writes_the_config_file(self):
        repo = self.temp_repo({}, commit=False)
        code, out, err = run_cli(["init"], cwd=repo)
        self.assertEqual(code, 0, err)
        target = repo / ".codehealth.yml"
        self.assertTrue(target.is_file())
        from chm.config import DEFAULT_CONFIG_TEMPLATE

        self.assertEqual(target.read_text(encoding="utf-8"), DEFAULT_CONFIG_TEMPLATE)
        self.assertIn("wrote", out)

    def test_init_is_idempotent_without_force(self):
        repo = self.temp_repo({}, commit=False)
        run_cli(["init"], cwd=repo)
        code, out, _err = run_cli(["init"], cwd=repo)
        self.assertEqual(code, 0)
        self.assertIn("already exists", out)

    def test_init_force_overwrites(self):
        repo = self.temp_repo({".codehealth.yml": "garbage: true\n"}, commit=False)
        code, _out, _err = run_cli(["init", "--force"], cwd=repo)
        self.assertEqual(code, 0)
        self.assertIn("version: 1", (repo / ".codehealth.yml").read_text(encoding="utf-8"))

    def test_help_exits_zero(self):
        code, out, err = run_cli(["--help"], cwd=helpers.repo_root())
        self.assertEqual(code, 0, err)
        self.assertIn("usage", out.lower())
        for command in ("review", "fix", "verify", "explain", "baseline", "probe", "init"):
            self.assertIn(command, out)

    def test_subcommand_help_exits_zero(self):
        for command in ("review", "probe", "explain", "init"):
            with self.subTest(command=command):
                code, out, _err = run_cli([command, "--help"], cwd=helpers.repo_root())
                self.assertEqual(code, 0)
                self.assertIn("usage", out.lower())

    def test_version_exits_zero(self):
        code, out, _err = run_cli(["--version"], cwd=helpers.repo_root())
        self.assertEqual(code, 0)
        self.assertIn("CodeHealthMind", out)

    def test_no_command_prints_help(self):
        code, out, _err = run_cli([], cwd=helpers.repo_root())
        self.assertEqual(code, 0)
        self.assertIn("usage", out.lower())


class ProbeTest(CHMTestCase):
    """``probe`` must report real, observed tool availability and versions."""

    def test_probe_reports_real_toolchain(self):
        repo = self.temp_repo({}, commit=False)
        code, out, err = run_cli(["probe", "--format", "json"], cwd=repo, timeout_s=600.0)
        self.assertEqual(code, 0, err)
        probes = {p["name"]: p for p in json.loads(out)}

        self.assertEqual(sorted(probes), sorted(
            [
                "native",
                "javac",
                "pmd",
                "cpd",
                "spotbugs",
                "semgrep",
                "knip",
                "openrewrite",
                "test-runner",
            ]
        ))

        for name in ("pmd", "cpd", "knip"):
            available, detail = toolchain_available(name)
            with self.subTest(tool=name):
                self.assertTrue(available, f"{name} should be present on this host: {detail}")
                self.assertTrue(probes[name]["available"], f"probe says {name} is unavailable: {probes[name]}")
                self.assertIsNotNone(probes[name]["version"], f"{name} reported no version")
                self.assertRegex(probes[name]["version"], r"^\d+\.\d+")

        # honest negatives on this host
        self.assertFalse(probes["semgrep"]["available"])
        self.assertIn("not installed", probes["semgrep"]["reason"] or "")
        self.assertFalse(probes["openrewrite"]["available"])
        self.assertTrue(probes["openrewrite"]["reason"])

        print("probe:", json.dumps(probes, indent=2, ensure_ascii=False)[:2000])

    def test_probe_console_format(self):
        repo = self.temp_repo({}, commit=False)
        code, out, err = run_cli(["probe"], cwd=repo, timeout_s=600.0)
        self.assertEqual(code, 0, err)
        self.assertIn("toolchain probe", out)
        self.assertIn("pmd", out)
        self.assertIn("semgrep", out)


class ExitCodeTest(CliMixin, CHMTestCase):
    """The four verdicts, observed through the real process exit code."""

    def test_clean_repo_exits_zero_with_pass(self):
        repo = self.make_project(NO_EXTERNAL_TOOLS, {"README.md": "# hello\n"})
        code, report = self.review_json(repo)
        self.assertEqual(report["summary"]["gate"], "PASS")
        self.assertEqual(code, 0)

    def test_medium_within_budget_exits_zero_with_warn(self):
        repo = self.make_project(
            NO_EXTERNAL_TOOLS, {"src/main/java/p/Sample.java": UNUSED_METHOD_JAVA}
        )
        code, report = self.review_json(repo)
        self.assertEqual(report["summary"]["gate"], "WARN")
        self.assertEqual(code, 0)
        self.assertGreater(report["summary"]["findings"], 0)

    def test_compile_failure_exits_one_with_block(self):
        repo = self.make_project(COMPILE_ONLY, {"src/main/java/p/Broken.java": BROKEN_JAVA})
        code, report = self.review_json(repo)
        self.assertEqual(report["summary"]["gate"], "BLOCK")
        self.assertEqual(code, 1)

    def test_missing_tool_exits_three_with_unknown(self):
        repo = self.make_project(PMD_ENABLED, {"src/main/java/p/Clean.java": CLEAN_JAVA})
        broken = str(self.temp_dir("chm-nope-") / "does-not-exist")
        code, out, err = run_cli(
            ["review", "--repo", "--format", "json"],
            cwd=repo,
            env={
                "CHM_PMD_HOME": broken,
                "CHM_SPOTBUGS_HOME": broken,
                "CHM_TOOLCHAIN_ROOT": "",
            },
        )
        self.assertTrue(out.strip(), f"no stdout (exit {code}); stderr={err[:2000]}")
        report = json.loads(out)
        self.assertEqual(report["summary"]["gate"], "UNKNOWN")
        self.assertEqual(code, 3)
        gaps = [e for e in report["tool_errors"] if e["evidence_gap"]]
        self.assertTrue(gaps, "an evidence gap must be recorded")
        self.assertTrue(any(e["kind"] in ("MISSING", "CONFIG") for e in gaps))
        self.assertTrue(any("pmd" == e["provider"] for e in gaps))
        # a missing tool must never be reported as a clean tool result
        pmd = [t for t in report["tools"] if t["provider"] == "pmd"]
        self.assertTrue(pmd, "pmd must still appear in the tool table")
        self.assertEqual(pmd[0]["status"], "UNAVAILABLE")

    def test_disabled_tool_is_not_probed_and_not_reported_as_missing(self):
        """A tool switched off in config must not be conflated with a missing one.

        The orchestrator filters disabled providers out of the run entirely
        (``core/orchestrator.py:468-474``), so pmd must appear neither in the
        tool table nor in ``tool_errors`` -- and its broken ``CHM_PMD_HOME``
        must therefore never be touched.
        """
        repo = self.make_project(NO_EXTERNAL_TOOLS, {"src/main/java/p/Clean.java": CLEAN_JAVA})
        broken = str(self.temp_dir("chm-nope-") / "does-not-exist")
        code, out, err = run_cli(
            ["review", "--repo", "--format", "json"],
            cwd=repo,
            env={"CHM_PMD_HOME": broken},
        )
        self.assertTrue(out.strip(), f"no stdout (exit {code}); stderr={err[:2000]}")
        report = json.loads(out)
        self.assertEqual([t for t in report["tools"] if t["provider"] == "pmd"], [])
        self.assertEqual([e for e in report["tool_errors"] if e["provider"] == "pmd"], [])
        self.assertEqual(report["summary"]["gate"], "PASS")
        self.assertEqual(code, 0)

    def test_json_summary_exit_code_matches_the_process(self):
        repo = self.make_project(
            NO_EXTERNAL_TOOLS, {"src/main/java/p/Sample.java": UNUSED_METHOD_JAVA}
        )
        code, report = self.review_json(repo)
        self.assertEqual(report["summary"]["exit_code"], code)


class ExplainTest(CliMixin, CHMTestCase):
    def test_explain_existing_finding(self):
        repo = self.make_project(
            NO_EXTERNAL_TOOLS, {"src/main/java/p/Sample.java": UNUSED_METHOD_JAVA}
        )
        _code, report = self.review_json(repo)
        self.assertTrue(report["findings"], "the fixture must produce at least one finding")
        finding = report["findings"][0]

        code, out, err = run_cli(["explain", finding["id"]], cwd=repo)
        self.assertEqual(code, 0, err)
        self.assertIn(finding["id"], out)
        self.assertIn(finding["rule_id"], out)
        self.assertIn(finding["location"]["file"], out)
        self.assertIn("confidence", out)
        self.assertIn("repair class", out)

    def test_explain_json_format(self):
        repo = self.make_project(
            NO_EXTERNAL_TOOLS, {"src/main/java/p/Sample.java": UNUSED_METHOD_JAVA}
        )
        _code, report = self.review_json(repo)
        finding = report["findings"][0]
        code, out, _err = run_cli(["explain", finding["id"], "--format", "json"], cwd=repo)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["id"], finding["id"])

    def test_explain_unknown_id_is_friendly(self):
        repo = self.make_project(
            NO_EXTERNAL_TOOLS, {"src/main/java/p/Sample.java": UNUSED_METHOD_JAVA}
        )
        self.review_json(repo)
        code, out, _err = run_cli(["explain", "CHM-999999"], cwd=repo)
        self.assertEqual(code, 0)
        self.assertIn("CHM-999999", out)
        self.assertIn("not found", out)

    def test_explain_without_a_previous_run_is_a_config_error(self):
        repo = self.make_project(NO_EXTERNAL_TOOLS, {"README.md": "# hi\n"})
        code, _out, err = run_cli(["explain", "CHM-000001"], cwd=repo)
        self.assertEqual(code, 2)
        self.assertIn("no run directory", err)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
