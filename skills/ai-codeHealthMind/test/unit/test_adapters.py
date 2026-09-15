"""Spec §16/§28/§29: the adapter layer must really run its tool and report honestly.

Every test here drives the **genuine** CLI on this host.  Nothing is mocked and
nothing is skipped into a green: when a tool is genuinely absent the test asserts
the *correct* absence behaviour (``UNAVAILABLE`` + typed ``ToolError``), which is
the whole point -- a missing tool must never be able to look like a pass.

The tests are deliberately tolerant about *what* the tools report (that depends
on the pinned versions) but strict about *how* the adapters report it:
the real command line must be recorded, failures must be typed, and partial
output must be exposed rather than swallowed.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src/ and test/ on sys.path)

from chm.adapters.compile import CompileAdapter
from chm.adapters.cpd import CpdAdapter
from chm.adapters.knip import KnipAdapter
from chm.adapters.openrewrite import OpenRewriteAdapter
from chm.adapters.pmd import PmdAdapter
from chm.adapters.probe import probe_all
from chm.adapters.semgrep import SemgrepAdapter
from chm.adapters.spotbugs import SpotBugsAdapter
from chm.adapters.testrunner import TestRunnerAdapter
from chm.config import Config
from chm.contracts import ChangeKind, ChangedFile, Language, ReviewMode, ScanContext
from chm.errors import ToolFailureKind, ToolStatus

JDK = Path("E:/jdk")
TOOLCHAIN = helpers.TOOLCHAIN_ROOT


def setUpModule() -> None:  # pragma: no cover - environment wiring
    """Pin the real tool locations for this host before anything runs."""
    if TOOLCHAIN is not None:
        os.environ["CHM_TOOLCHAIN_ROOT"] = str(TOOLCHAIN)
        pmd = sorted(p for p in TOOLCHAIN.glob("pmd-bin-*") if (p / "lib").is_dir())
        if pmd:
            os.environ["CHM_PMD_HOME"] = str(pmd[-1])
        sb = sorted(p for p in TOOLCHAIN.glob("spotbugs-*") if (p / "lib").is_dir())
        if sb:
            os.environ["CHM_SPOTBUGS_HOME"] = str(sb[-1])
        if (TOOLCHAIN / "knip" / "node_modules" / "knip" / "bin" / "knip.js").is_file():
            os.environ["CHM_KNIP_HOME"] = str(TOOLCHAIN / "knip")
    if (JDK / "bin" / "javac.exe").is_file():
        os.environ["CHM_JAVA_HOME"] = str(JDK)
        os.environ["JAVA_HOME"] = str(JDK)


# --------------------------------------------------------------------------
# shared fixtures
# --------------------------------------------------------------------------


def _make_ctx(
    root: Path,
    files: list[tuple[str, Language]],
    *,
    config: Config | None = None,
    cache: Path | None = None,
    options: dict | None = None,
) -> ScanContext:
    """A real ``ScanContext`` with a real cache directory for artefacts."""
    cache_dir = cache if cache is not None else (root / ".chm-cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return ScanContext(
        repo_root=Path(root),
        mode=ReviewMode.DIFF,
        changed_files=[
            ChangedFile(path=p, change_kind=ChangeKind.ADDED, language=lang)
            for p, lang in files
        ],
        config=config if config is not None else Config(),
        cache_dir=cache_dir,
        options=dict(options or {}),
    )


SMELLY_JAVA = """\
package demo;

import java.io.FileInputStream;
import java.io.IOException;

public class Smelly {
    private int unusedField = 42;

    public void emptyCatch() {
        try {
            FileInputStream in = new FileInputStream("x");
        } catch (Exception e) {
        }
    }

    private void unusedPrivateMethod() {
        int dead = 1;
    }
}
"""

BUGGY_JAVA = """\
package demo;

public class Buggy {
    private String unusedField;

    public String pick(boolean flag) {
        String s = flag ? "a" : null;
        return s.trim();
    }
}
"""


def _duplicate_js_body() -> str:
    """A block comfortably over the default 100-token CPD threshold."""
    lines = [f"  const v{i} = base + {i} * factor - offset;" for i in range(30)]
    lines += [
        "  if (v0 > threshold) {",
        "    accumulator += v0 * weight + v1 - v2;",
        "  } else if (v3 < floor) {",
        "    accumulator -= v4 / divisor + v5 % modulus;",
        "  } else {",
        "    accumulator = (accumulator ^ v6) | (v7 & mask);",
        "  }",
    ]
    return "\n".join(lines)


def _js_module(name: str) -> str:
    return (
        f"export function compute{name}(base, factor, offset, threshold, weight,\n"
        "                                floor, divisor, modulus, mask) {\n"
        "  let accumulator = 0;\n"
        f"{_duplicate_js_body()}\n"
        "  return accumulator;\n"
        "}\n"
    )


# --------------------------------------------------------------------------
# probe
# --------------------------------------------------------------------------


class TestProbeAll(unittest.TestCase):
    """``probe_all`` must really execute each tool and never guess."""

    @classmethod
    def setUpClass(cls):
        cls.probes = {p.name: p for p in probe_all(None, Config())}

    def test_probe_order_is_canonical(self):
        names = [p.name for p in probe_all(None, Config())]
        self.assertEqual(
            names,
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
            ],
        )

    def test_probed_tools_report_real_versions(self):
        """pmd/cpd/spotbugs/knip are pinned on this host: available + versioned."""
        for name in ("pmd", "cpd", "spotbugs", "knip"):
            probe = self.probes[name]
            with self.subTest(tool=name):
                self.assertTrue(probe.available, f"{name} should be available: {probe.reason}")
                self.assertTrue(probe.version, f"{name} reported no version")
                self.assertRegex(probe.version, r"\d+\.\d+")

    def test_absent_tools_carry_a_real_reason(self):
        for name in ("semgrep", "openrewrite", "test-runner"):
            probe = self.probes[name]
            with self.subTest(tool=name):
                self.assertFalse(probe.available)
                self.assertTrue(probe.reason, f"{name} must explain why it is unavailable")

    def test_to_dict_shape(self):
        payload = self.probes["pmd"].to_dict()
        self.assertEqual(
            set(payload), {"name", "available", "version", "path", "reason"}
        )


# --------------------------------------------------------------------------
# PMD
# --------------------------------------------------------------------------


class TestPmdAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.temp_dir("chm-pmd-")
        src = self.tmp / "src" / "demo"
        src.mkdir(parents=True)
        (src / "Smelly.java").write_text(SMELLY_JAVA, encoding="utf-8")
        self.ctx = _make_ctx(self.tmp, [("src/demo/Smelly.java", Language.JAVA)])

    def tearDown(self):
        helpers.cleanup_temp_dirs()

    def test_available_on_this_host(self):
        available, reason = PmdAdapter(self.ctx).available()
        self.assertTrue(available, reason)

    def test_scan_runs_real_pmd_and_records_command(self):
        adapter = PmdAdapter(self.ctx)
        result = adapter.scan(self.ctx)

        self.assertIs(result.status, ToolStatus.OK, result.error)
        self.assertGreater(len(result.findings), 0, "PMD found nothing in a deliberately smelly file")
        self.assertIsNotNone(result.command)
        self.assertIn("net.sourceforge.pmd.PMD", result.command)
        self.assertIn("-filelist", result.command)
        self.assertTrue(result.artefact and Path(result.artefact).is_file())

    def test_findings_are_attributed_to_pmd_with_a_chm_rule_id(self):
        result = PmdAdapter(self.ctx).scan(self.ctx)
        for finding in result.findings:
            self.assertEqual(finding.provider, "pmd")
            self.assertTrue(finding.rule_id.startswith("CHM-JAVA-PMD-"))
            self.assertNotEqual(finding.file, "")
            self.assertGreaterEqual(finding.start_line, 1)

    def test_dead_code_rules_map_to_dead_code_category(self):
        from chm.schema import Category

        result = PmdAdapter(self.ctx).scan(self.ctx)
        by_rule = {f.extra.get("pmd_rule"): f for f in result.findings}
        self.assertIn("UnusedPrivateField", by_rule)
        self.assertIs(by_rule["UnusedPrivateField"].category, Category.DEAD_CODE)
        self.assertIn("EmptyCatchBlock", by_rule)
        self.assertIs(by_rule["EmptyCatchBlock"].category, Category.ERROR_HANDLING)

    def test_bad_ruleset_is_a_typed_failure_not_a_crash(self):
        cfg = Config()
        cfg.tools.pmd.ruleset = "rulesets/java/definitely-not-real.xml"
        ctx = _make_ctx(
            self.tmp, [("src/demo/Smelly.java", Language.JAVA)], config=cfg
        )
        result = PmdAdapter(ctx).scan(ctx)
        self.assertIs(result.status, ToolStatus.UNAVAILABLE)
        self.assertIsNotNone(result.error)
        self.assertIs(result.error.kind, ToolFailureKind.NONZERO_EXIT)
        self.assertIsNotNone(result.error.exit_code)


# --------------------------------------------------------------------------
# CPD
# --------------------------------------------------------------------------


class TestCpdAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.temp_dir("chm-cpd-")
        dup = self.tmp / "src" / "dup"
        dup.mkdir(parents=True)
        for name in ("Alpha", "Beta"):
            (dup / f"{name}.js").write_text(_js_module(name), encoding="utf-8")
        self.ctx = _make_ctx(
            self.tmp,
            [("src/dup/Alpha.js", Language.JAVASCRIPT), ("src/dup/Beta.js", Language.JAVASCRIPT)],
        )

    def tearDown(self):
        helpers.cleanup_temp_dirs()

    def test_scan_reports_real_duplication(self):
        result = CpdAdapter(self.ctx).scan(self.ctx)

        self.assertIs(result.status, ToolStatus.OK, result.error)
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.category.value, "DUPLICATION")
        self.assertEqual(finding.rule_id, "CHM-JS-CPD-DUP")
        self.assertGreaterEqual(finding.extra["tokens"], 100)
        self.assertEqual(len(finding.extra["occurrences"]), 2)
        self.assertIn("net.sourceforge.pmd.cpd.CPD", result.command)
        self.assertIn("--minimum-tokens", result.command)

    def test_uses_utf8_encoding_and_skip_lexical_errors(self):
        """Regression: CPD's GBK default mangled UTF-8 sources and aborted runs."""
        result = CpdAdapter(self.ctx).scan(self.ctx)
        self.assertIn("--encoding", result.command)
        self.assertIn("UTF-8", result.command)
        self.assertIn("--skip-lexical-errors", result.command)
        # an explicit file set must go through --files, not the encoding-fragile
        # --filelist (CPD reads that with the JVM charset, not --encoding)
        self.assertIn("--files", result.command)
        self.assertNotIn("--filelist", result.command)

    def test_unlexable_file_does_not_abort_the_scan(self):
        """Regression: one bad file used to fail the whole CPD run."""
        bad = self.tmp / "src" / "dup" / "bad.js"
        bad.write_text("#!/usr/bin/env node\nconsole.log('shebang breaks the ecmascript lexer');\n", encoding="utf-8")

        ctx = _make_ctx(
            self.tmp,
            [
                ("src/dup/Alpha.js", Language.JAVASCRIPT),
                ("src/dup/Beta.js", Language.JAVASCRIPT),
                ("src/dup/bad.js", Language.JAVASCRIPT),
            ],
        )
        result = CpdAdapter(ctx).scan(ctx)

        self.assertNotEqual(
            result.status,
            ToolStatus.UNAVAILABLE,
            f"a single unlexable file must not fail the scan: {result.error}",
        )
        self.assertGreaterEqual(len(result.findings), 1, "real duplications were lost")
        self.assertIsNotNone(result.error)
        self.assertIs(result.error.kind, ToolFailureKind.PARTIAL_OUTPUT)
        self.assertFalse(result.error.evidence_gap)
        self.assertIn("skipped", result.error.detail)
        self.assertIn("bad.js", result.error.detail)


# --------------------------------------------------------------------------
# javac / SpotBugs
# --------------------------------------------------------------------------


class TestCompileAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.temp_dir("chm-javac-")

    def tearDown(self):
        helpers.cleanup_temp_dirs()

    def _write(self, rel: str, body: str) -> ScanContext:
        target = self.tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return _make_ctx(self.tmp, [(rel, Language.JAVA)])

    def test_successful_compile_publishes_classes_dir(self):
        ctx = self._write("src/demo/Good.java", "package demo;\npublic class Good {}\n")
        result = CompileAdapter(ctx).scan(ctx)

        self.assertIs(result.status, ToolStatus.OK)
        self.assertEqual(result.findings, [])
        self.assertIn("javac", (result.command or "").lower())
        self.assertTrue(ctx.options.get("compile_ok"))
        classes = Path(ctx.options["classes_dir"])
        self.assertTrue(classes.is_dir())
        self.assertTrue(any(classes.rglob("Good.class")))

    def test_compile_failure_is_critical_but_not_a_tool_failure(self):
        ctx = self._write(
            "src/demo/Broken.java",
            "package demo;\npublic class Broken { public void x() { int a = ; } }\n",
        )
        result = CompileAdapter(ctx).scan(ctx)

        # javac worked; the *code* is broken.  That is a CRITICAL finding.
        self.assertIs(result.status, ToolStatus.OK)
        self.assertIsNone(result.error)
        self.assertFalse(ctx.options.get("compile_ok"))
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.rule_id, "CHM-JAVA-COMPILE-FAIL")
        self.assertEqual(finding.severity.value, "CRITICAL")
        self.assertEqual(finding.category.value, "ERROR_HANDLING")
        self.assertGreaterEqual(finding.start_line, 1)

    def test_no_java_files_is_unsupported(self):
        ctx = _make_ctx(self.tmp, [])
        self.assertFalse(CompileAdapter(ctx).supports(ctx))


class TestSpotBugsAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.temp_dir("chm-sb-")
        src = self.tmp / "src" / "demo"
        src.mkdir(parents=True)
        (src / "Buggy.java").write_text(BUGGY_JAVA, encoding="utf-8")
        self.ctx = _make_ctx(self.tmp, [("src/demo/Buggy.java", Language.JAVA)])

    def tearDown(self):
        helpers.cleanup_temp_dirs()

    def test_without_compiled_classes_it_refuses_rather_than_guesses(self):
        result = SpotBugsAdapter(self.ctx).scan(self.ctx)

        self.assertIs(result.status, ToolStatus.UNAVAILABLE)
        self.assertIs(result.error.kind, ToolFailureKind.UNSUPPORTED)
        self.assertFalse(result.error.evidence_gap)
        self.assertIn("compiled classes", result.error.detail)
        self.assertEqual(result.findings, [])

    def test_after_compiling_it_finds_real_bugs_with_resolvable_paths(self):
        CompileAdapter(self.ctx).scan(self.ctx)
        self.assertTrue(self.ctx.options.get("compile_ok"))

        result = SpotBugsAdapter(self.ctx).scan(self.ctx)

        self.assertIs(result.status, ToolStatus.OK, result.error)
        self.assertIn("spotbugs.jar", result.command)
        self.assertGreater(len(result.findings), 0)
        for finding in result.findings:
            self.assertTrue(finding.rule_id.startswith("CHM-JAVA-SB-"))
            # SpotBugs reports paths relative to the *source root*; the adapter
            # must map them back onto a file that really exists in the repo.
            self.assertTrue(
                (self.tmp / finding.file).is_file(),
                f"unresolvable source path: {finding.file}",
            )
            self.assertEqual(finding.extra["spotbugs_type"], finding.rule_id[len("CHM-JAVA-SB-"):])


# --------------------------------------------------------------------------
# knip
# --------------------------------------------------------------------------


class TestKnipAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.temp_dir("chm-knip-")
        (self.tmp / "src").mkdir(parents=True)
        (self.tmp / "package.json").write_text(
            '{\n  "name": "knip-demo",\n  "version": "1.0.0",\n  "type": "module",\n'
            '  "main": "src/index.js",\n  "dependencies": {\n'
            '    "lodash": "^4.17.21",\n    "left-pad": "^1.3.0"\n  }\n}\n',
            encoding="utf-8",
        )
        (self.tmp / "src" / "index.js").write_text(
            "import { used } from './used.js';\nexport function main() { return used(); }\n",
            encoding="utf-8",
        )
        (self.tmp / "src" / "used.js").write_text(
            "export function used() { return 1; }\nexport function unusedExport() { return 3; }\n",
            encoding="utf-8",
        )
        (self.tmp / "src" / "orphan.js").write_text(
            "export function neverImported() { return 2; }\n", encoding="utf-8"
        )
        self.ctx = _make_ctx(self.tmp, [("src/index.js", Language.JAVASCRIPT)])

    def tearDown(self):
        helpers.cleanup_temp_dirs()

    def test_scan_runs_real_knip(self):
        adapter = KnipAdapter(self.ctx)
        available, reason = adapter.available()
        if not available:
            self.skipTest(f"knip unavailable on this host: {reason}")

        result = adapter.scan(self.ctx)
        self.assertIs(result.status, ToolStatus.OK, result.error)
        self.assertIn("knip", result.command)
        self.assertIn("--reporter", result.command)
        self.assertIn("json", result.command)

        rules = {f.rule_id for f in result.findings}
        self.assertIn("CHM-JS-KNIP-UNUSED-FILE", rules)
        self.assertIn("CHM-JS-KNIP-UNUSED-DEPENDENCY", rules)
        self.assertIn("CHM-JS-KNIP-UNUSED-EXPORT", rules)

    def test_knip_absence_is_not_an_evidence_gap(self):
        """Knip only ever yields MEDIUM/LOW, so it never blocks a HIGH verdict."""
        self.assertFalse(KnipAdapter.evidence_gap)

    def test_without_package_json_it_is_unsupported(self):
        bare = helpers.temp_dir("chm-knip-bare-")
        ctx = _make_ctx(bare, [("src/a.js", Language.JAVASCRIPT)])
        self.assertFalse(KnipAdapter(ctx).supports(ctx))


# --------------------------------------------------------------------------
# genuinely absent tools
# --------------------------------------------------------------------------


class TestAbsentTools(unittest.TestCase):
    """Each of these must produce a typed ToolError -- never an empty success."""

    def setUp(self):
        self.tmp = helpers.temp_dir("chm-absent-")
        (self.tmp / "src").mkdir(parents=True)
        (self.tmp / "src" / "Foo.java").write_text("package p;\npublic class Foo {}\n", encoding="utf-8")
        self.ctx = _make_ctx(self.tmp, [("src/Foo.java", Language.JAVA)])

    def tearDown(self):
        helpers.cleanup_temp_dirs()

    def _assert_typed_unavailable(self, adapter, expected_kind, gap):
        result = adapter.scan(self.ctx)
        self.assertIs(result.status, ToolStatus.UNAVAILABLE)
        self.assertEqual(result.findings, [])
        self.assertIsNotNone(result.error, "an unavailable tool must carry a ToolError")
        self.assertIs(result.error.kind, expected_kind)
        self.assertEqual(result.error.evidence_gap, gap)
        self.assertTrue(result.error.detail.strip(), "the reason must not be empty")
        return result

    def test_semgrep_is_missing_on_this_host(self):
        adapter = SemgrepAdapter(self.ctx)
        available, reason = adapter.available()
        if available:
            self.skipTest("semgrep is installed on this host; absence path not exercisable")
        self.assertIn("semgrep", reason)
        result = self._assert_typed_unavailable(adapter, ToolFailureKind.MISSING, True)
        self.assertIn("semgrep", result.error.detail)

    def test_openrewrite_is_unavailable_on_this_host(self):
        adapter = OpenRewriteAdapter(self.ctx)
        available, reason = adapter.available()
        if available:
            self.skipTest("OpenRewrite is usable on this host; absence path not exercisable")
        self.assertTrue(reason)
        self._assert_typed_unavailable(adapter, ToolFailureKind.MISSING, False)

    def test_test_runner_without_configuration_is_unsupported(self):
        result = self._assert_typed_unavailable(
            TestRunnerAdapter(self.ctx), ToolFailureKind.DISABLED, False
        )
        self.assertIn("disabled", result.error.detail)

    def test_test_runner_without_a_command_is_unsupported(self):
        cfg = Config()
        cfg.tools.test.enabled = True
        cfg.tools.test.args = []
        ctx = _make_ctx(self.tmp, [("src/Foo.java", Language.JAVA)], config=cfg)
        result = TestRunnerAdapter(ctx).scan(ctx)
        self.assertIs(result.status, ToolStatus.UNAVAILABLE)
        self.assertIs(result.error.kind, ToolFailureKind.UNSUPPORTED)
        self.assertFalse(result.error.evidence_gap)


# --------------------------------------------------------------------------
# explicit configuration pointing nowhere
# --------------------------------------------------------------------------


class TestExplicitConfigPathMissing(unittest.TestCase):
    """A configured path that does not exist must be a CONFIG error.

    Silently falling back to a *different* toolchain would mean the user believes
    they selected one tool while another actually ran -- the exact false-green
    this project exists to prevent (spec §29).
    """

    def setUp(self):
        self.tmp = helpers.temp_dir("chm-cfg-")
        (self.tmp / "src").mkdir(parents=True)
        (self.tmp / "src" / "Foo.java").write_text("package p;\npublic class Foo {}\n", encoding="utf-8")
        self.missing = str(self.tmp / "no-such-tool-home")

    def tearDown(self):
        helpers.cleanup_temp_dirs()

    def _ctx_for(self, tool_key: str, **fields) -> ScanContext:
        cfg = Config()
        target = getattr(cfg.tools, tool_key)
        for name, value in fields.items():
            setattr(target, name, value)
        return _make_ctx(self.tmp, [("src/Foo.java", Language.JAVA)], config=cfg)

    def test_all_six_adapters_report_config_error(self):
        cases = [
            ("pmd", PmdAdapter, {"home": self.missing}),
            ("cpd", CpdAdapter, {"home": self.missing}),
            ("spotbugs", SpotBugsAdapter, {"home": self.missing}),
            ("semgrep", SemgrepAdapter, {"bin": self.missing + "/semgrep.exe"}),
            ("knip", KnipAdapter, {"home": self.missing}),
            ("openrewrite", OpenRewriteAdapter, {"bin": self.missing + "/mod.exe"}),
        ]
        for tool_key, cls, fields in cases:
            with self.subTest(tool=tool_key):
                ctx = self._ctx_for(tool_key, **fields)
                adapter = cls(ctx)

                available, reason = adapter.available()
                self.assertFalse(available, f"{tool_key} must not claim availability")
                self.assertIn("does not exist", reason or "")

                result = adapter.scan(ctx)
                self.assertIs(result.status, ToolStatus.UNAVAILABLE)
                self.assertIs(result.error.kind, ToolFailureKind.CONFIG)
                self.assertEqual(result.findings, [])
                self.assertIn("does not exist", result.error.detail)

    def test_bare_command_name_is_not_treated_as_a_missing_path(self):
        """``bin: semgrep`` names a PATH command; it is not a broken path."""
        cfg = Config()
        cfg.tools.semgrep.bin = "semgrep-not-a-real-command"
        ctx = _make_ctx(self.tmp, [("src/Foo.java", Language.JAVA)], config=cfg)
        available, reason = SemgrepAdapter(ctx).available()
        self.assertFalse(available)
        self.assertNotIn("does not exist", reason or "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
