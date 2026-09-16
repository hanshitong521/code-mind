"""Spec §31/§32 fault injection.

Every scenario here is *real*: a real missing directory, a real process that
really exits 127, a real process that really sleeps past its deadline.  The
assertions encode the red line -- **no tool failure may ever produce PASS**.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

import helpers
from helpers import CHMTestCase, toolchain_available, write_files

from chm.adapters.base import classify_cmd_failure
from chm.adapters.pmd import PmdAdapter, parse_xml, strip_to_xml
from chm.adapters.semgrep import SemgrepAdapter
from chm.config import Config, load_config
from chm.contracts import ChangedFile, ProviderResult, ReviewMode, ScanContext, language_of
from chm.core.gate import evaluate_gate
from chm.core.orchestrator import Orchestrator
from chm.core.score import score_findings
from chm.errors import ToolError, ToolFailureKind, ToolStatus
from chm.schema import GateVerdict
from chm.util import run_cmd

SAMPLE_JAVA = """\
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


class AdapterCase(CHMTestCase):
    def project(self, files: dict[str, str], *, config: Config | None = None) -> ScanContext:
        repo = self.temp_dir("chm-fault-")
        write_files(repo, files)
        cache = repo / ".cache"
        cache.mkdir(parents=True, exist_ok=True)
        return ScanContext(
            repo_root=repo,
            mode=ReviewMode.REPO,
            changed_files=[
                ChangedFile(path=rel, language=language_of(rel), hunks=[], size_bytes=0)
                for rel in files
            ],
            config=config or Config(),
            cache_dir=cache,
            options={"whole_file": True},
        )


class MissingToolTest(AdapterCase):
    def test_missing_distribution_yields_unavailable_and_tool_error(self):
        ctx = self.project({"src/main/java/p/Sample.java": SAMPLE_JAVA})
        absent = str(self.temp_dir("chm-absent-") / "nope")
        saved = {k: os.environ.get(k) for k in ("CHM_PMD_HOME", "CHM_TOOLCHAIN_ROOT")}
        os.environ["CHM_PMD_HOME"] = absent
        os.environ.pop("CHM_TOOLCHAIN_ROOT", None)
        try:
            result = PmdAdapter(ctx).scan(ctx)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertIsInstance(result.error, ToolError)
        self.assertIn(result.error.kind, (ToolFailureKind.MISSING, ToolFailureKind.CONFIG))
        self.assertTrue(result.error.evidence_gap)
        self.assertEqual(result.findings, [])

    def test_missing_tool_does_not_crash_the_orchestrator(self):
        repo = self.temp_repo(
            {
                ".codehealth.yml": NO_EXTERNAL_TOOLS.replace(
                    "  pmd:\n    enabled: false", "  pmd:\n    enabled: true"
                ),
                "src/main/java/p/Sample.java": SAMPLE_JAVA,
            }
        )
        absent = str(self.temp_dir("chm-absent-") / "nope")
        saved = {k: os.environ.get(k) for k in ("CHM_PMD_HOME", "CHM_TOOLCHAIN_ROOT")}
        os.environ["CHM_PMD_HOME"] = absent
        os.environ.pop("CHM_TOOLCHAIN_ROOT", None)
        try:
            cfg = load_config(repo / ".codehealth.yml", repo_root=repo)
            result = Orchestrator(
                repo_root=repo,
                config=cfg,
                mode=ReviewMode.REPO,
                options={"whole_file": True},
            ).run()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertNotEqual(result.gate, GateVerdict.PASS.value)
        self.assertEqual(result.gate, GateVerdict.UNKNOWN.value)
        self.assertEqual(result.exit_code, 3)
        pmd_errors = [e for e in result.tool_errors if e.provider == "pmd"]
        self.assertEqual(len(pmd_errors), 1)
        self.assertIn(pmd_errors[0].kind, (ToolFailureKind.MISSING, ToolFailureKind.CONFIG))
        self.assertTrue(pmd_errors[0].evidence_gap)


class NonzeroExitTest(unittest.TestCase):
    def test_a_real_process_exiting_127_is_classified_as_nonzero_exit(self):
        started = time.perf_counter()
        result = run_cmd([sys.executable, "-c", "import sys; sys.exit(127)"], timeout_s=60.0)
        elapsed = time.perf_counter() - started

        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 127)
        self.assertFalse(result.timed_out)
        self.assertIsNone(result.launch_error)

        error = classify_cmd_failure("faketool", result, what="faketool")
        self.assertEqual(error.kind, ToolFailureKind.NONZERO_EXIT)
        self.assertEqual(error.exit_code, 127)
        self.assertFalse(error.evidence_gap)
        self.assertIn("127", error.detail)
        print(f"exit-127 process took {elapsed:.2f}s")

    def test_launch_failure_is_classified_as_missing(self):
        result = run_cmd(["definitely-not-a-real-binary-xyz"], timeout_s=10.0)
        self.assertIsNotNone(result.launch_error)
        error = classify_cmd_failure("faketool", result, what="faketool")
        self.assertEqual(error.kind, ToolFailureKind.MISSING)
        self.assertTrue(error.evidence_gap)


class TimeoutTest(AdapterCase):
    def test_a_real_hung_process_is_killed_and_classified(self):
        script = "import time; time.sleep(60)"
        started = time.perf_counter()
        result = run_cmd([sys.executable, "-c", script], timeout_s=2.0)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        self.assertTrue(result.timed_out)
        self.assertLess(elapsed_ms, 15_000, "the timeout must really kill the process tree")
        print(f"timeout fired after {elapsed_ms} ms")

        error = classify_cmd_failure("faketool", result, what="faketool")
        self.assertEqual(error.kind, ToolFailureKind.TIMEOUT)
        self.assertTrue(error.evidence_gap)
        self.assertIn("time budget", error.detail)

    def test_adapter_timeout_becomes_a_tool_error_not_an_exception(self):
        """A real PMD run killed by a 50 ms budget must degrade, not raise."""
        ok, detail = toolchain_available("pmd")
        if not ok:
            self.skipTest(f"PMD not available on this host: {detail}")
        ctx = self.project({"src/main/java/p/Sample.java": SAMPLE_JAVA})
        ctx.config.tools.pmd.timeout_s = 0.05
        started = time.perf_counter()
        result = PmdAdapter(ctx).scan(ctx)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        self.assertLess(elapsed_ms, 15_000)
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertIsNotNone(result.error)
        self.assertIn(
            result.error.kind,
            (ToolFailureKind.TIMEOUT, ToolFailureKind.NONZERO_EXIT),
        )
        self.assertTrue(result.error.evidence_gap)
        self.assertEqual(result.findings, [])
        print(f"PMD killed by a 50 ms budget after {elapsed_ms} ms: {result.error.kind.value}")


class MalformedOutputTest(AdapterCase):
    def test_parse_xml_reports_garbage_without_raising(self):
        for garbage in ("", "not xml at all", "<pmd><unclosed>", "{\"json\": true}", "\x00\x01\x02"):
            with self.subTest(garbage=garbage[:20]):
                root, reason = parse_xml(garbage)
                self.assertIsNone(root)
                self.assertTrue(reason)

    def test_strip_to_xml_survives_log_noise(self):
        noisy = "SLF4J: something\nINFO: starting\n<?xml version=\"1.0\"?><pmd/>"
        self.assertTrue(strip_to_xml(noisy).startswith("<?xml"))

    def test_malformed_pmd_report_degrades_instead_of_raising(self):
        ctx = self.project({"src/main/java/p/Sample.java": SAMPLE_JAVA})
        ctx.config.tools.pmd.ruleset = "does/not/exist-ruleset.xml"
        result = PmdAdapter(ctx).scan(ctx)
        # must not raise, and must not claim success
        self.assertNotEqual(result.status, ToolStatus.OK)
        self.assertIsNotNone(result.error)
        self.assertIn(
            result.error.kind,
            (
                ToolFailureKind.MALFORMED_OUTPUT,
                ToolFailureKind.NONZERO_EXIT,
                ToolFailureKind.MISSING,
                ToolFailureKind.CONFIG,
            ),
        )
        self.assertEqual(result.findings, [])
        print("broken-ruleset result:", result.status.value, result.error.kind.value,
              result.error.detail[:160])

    def test_garbage_semgrep_output_is_a_missing_tool_here(self):
        ctx = self.project({"src/main/java/p/Sample.java": SAMPLE_JAVA})
        os.environ.pop("CHM_SEMGREP_BIN", None)
        result = SemgrepAdapter(ctx).scan(ctx)
        self.assertNotEqual(result.status, ToolStatus.OK)
        self.assertIsNotNone(result.error)


class NoPassOnFailureTest(unittest.TestCase):
    """The red line: a tool failure must never be reported as a clean PASS."""

    KINDS = (
        ToolFailureKind.MISSING,
        ToolFailureKind.TIMEOUT,
        ToolFailureKind.NONZERO_EXIT,
        ToolFailureKind.MALFORMED_OUTPUT,
        ToolFailureKind.PARTIAL_OUTPUT,
        ToolFailureKind.CRASHED,
        ToolFailureKind.UNSUPPORTED,
        ToolFailureKind.DISABLED,
        ToolFailureKind.CONFIG,
    )

    def test_evidence_gap_never_passes(self):
        cfg = Config()
        score = score_findings([], config=cfg)
        for kind in self.KINDS:
            with self.subTest(kind=kind):
                error = ToolError(
                    provider="pmd",
                    kind=kind,
                    detail=f"injected {kind.value}",
                    evidence_gap=True,
                )
                gate = evaluate_gate([], score=score, config=cfg, tool_errors=[error])
                self.assertNotEqual(gate.verdict, GateVerdict.PASS)
                self.assertEqual(gate.verdict, GateVerdict.UNKNOWN)
                self.assertEqual(gate.exit_code, 3)

    def test_degradation_without_gap_warns_not_passes(self):
        cfg = Config()
        score = score_findings([], config=cfg)
        for kind in self.KINDS:
            with self.subTest(kind=kind):
                error = ToolError(
                    provider="pmd",
                    kind=kind,
                    detail=f"injected {kind.value}",
                    evidence_gap=False,
                )
                gate = evaluate_gate([], score=score, config=cfg, tool_errors=[error])
                self.assertNotEqual(gate.verdict, GateVerdict.PASS)
                self.assertEqual(gate.verdict, GateVerdict.WARN)
                self.assertEqual(gate.exit_code, 0)

    def test_a_provider_result_with_an_error_is_never_ok(self):
        result = ProviderResult(
            provider="pmd",
            status=ToolStatus.UNAVAILABLE,
            error=ToolError(provider="pmd", kind=ToolFailureKind.MISSING, detail="gone"),
        )
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.to_dict()["error"]["kind"], "MISSING")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
