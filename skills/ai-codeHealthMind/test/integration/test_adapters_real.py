"""Spec §16: every adapter must really invoke its tool, and report honestly.

Nothing here is mocked.  When a tool is absent on this host the test asserts the
*correct* behaviour for absence (``UNAVAILABLE`` + typed ``ToolError``), which is
the whole point of the exercise -- a missing tool must never look like a pass.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
from pathlib import Path

import helpers
from helpers import CHMTestCase, toolchain_available, write_bytes, write_files

from chm.adapters.compile import CompileAdapter
from chm.adapters.cpd import CpdAdapter
from chm.adapters.knip import KnipAdapter
from chm.adapters.openrewrite import OpenRewriteAdapter
from chm.adapters.pmd import PmdAdapter
from chm.adapters.semgrep import SemgrepAdapter
from chm.adapters.spotbugs import SpotBugsAdapter
from chm.config import Config
from chm.contracts import ChangedFile, ReviewMode, ScanContext, language_of
from chm.errors import ToolFailureKind, ToolStatus

JDK = Path("E:/jdk")


def setUpModule() -> None:  # pragma: no cover - environment wiring
    """Pin the real tool locations for this host, then print what was found."""
    root = helpers.TOOLCHAIN_ROOT
    if root is not None:
        os.environ["CHM_TOOLCHAIN_ROOT"] = str(root)
        pmd = sorted(p for p in root.glob("pmd-bin-*") if (p / "lib").is_dir())
        if pmd:
            os.environ["CHM_PMD_HOME"] = str(pmd[-1])
        sb = sorted(p for p in root.glob("spotbugs-*") if (p / "lib").is_dir())
        if sb:
            os.environ["CHM_SPOTBUGS_HOME"] = str(sb[-1])
        if (root / "knip" / "node_modules" / "knip" / "bin" / "knip.js").is_file():
            os.environ["CHM_KNIP_HOME"] = str(root / "knip")
    if (JDK / "bin" / "javac.exe").is_file():
        os.environ["CHM_JAVA_HOME"] = str(JDK)
        os.environ["JAVA_HOME"] = str(JDK)
    os.environ.pop("CHM_SEMGREP_BIN", None)
    os.environ.pop("CHM_OPENREWRITE_BIN", None)
    os.environ.pop("CHM_MVN_BIN", None)

    print("\n[adapters_real] toolchain root :", root)
    for name in ("pmd", "cpd", "spotbugs", "knip", "javac", "node", "semgrep", "mvn"):
        available, detail = toolchain_available(name)
        print(f"[adapters_real] {name:10s} available={available!s:5s} {detail}")


UNUSED_METHOD = """\
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

_dup_lines = "".join(f"        total += v * {i};\n" for i in range(2, 23))
DUPLICATED = (
    "package p;\n\npublic class Dup {\n    public int a1(int v) {\n        int total = 0;\n"
    + _dup_lines
    + "        return total;\n    }\n\n    public int a2(int v) {\n        int total = 0;\n"
    + _dup_lines
    + "        return total;\n    }\n}\n"
)

UNCLOSED_STREAM = """\
package p;

import java.io.FileInputStream;
import java.io.IOException;

public class Leak {
    public int read(String name) throws IOException {
        FileInputStream in = new FileInputStream(name);
        return in.read();
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


class AdapterCase(CHMTestCase):
    def project(self, files: dict[str, str], *, config: Config | None = None) -> ScanContext:
        repo = self.temp_dir("chm-adapters-")
        write_files(repo, files)
        cache = repo / ".cache"
        cache.mkdir(parents=True, exist_ok=True)
        changed = [
            ChangedFile(
                path=rel,
                language=language_of(rel),
                hunks=[],
                size_bytes=(repo / rel).stat().st_size,
            )
            for rel in files
        ]
        return ScanContext(
            repo_root=repo,
            mode=ReviewMode.REPO,
            changed_files=changed,
            config=config or Config(),
            cache_dir=cache,
            options={"whole_file": True},
        )


class JavacTest(AdapterCase):
    def test_compiles_a_valid_file(self):
        ctx = self.project({"src/main/java/p/Clean.java": CLEAN_JAVA})
        adapter = CompileAdapter(ctx)
        available, reason = adapter.available()
        self.assertTrue(available, reason)

        result = adapter.scan(ctx)
        print("javac command:", result.command)
        self.assertEqual(result.status, ToolStatus.OK)
        self.assertIsNone(result.error)
        self.assertTrue(ctx.options.get("compile_ok"))
        classes = Path(ctx.options["classes_dir"])
        produced = sorted(p.name for p in classes.rglob("*.class"))
        self.assertIn("Clean.class", produced)
        self.assertIn("javac", result.command)
        self.assertRegex(result.version or "", r"^\d+")

    def test_reports_a_real_compile_failure(self):
        ctx = self.project({"src/main/java/p/Broken.java": BROKEN_JAVA})
        result = CompileAdapter(ctx).scan(ctx)
        print("javac failure command:", result.command)
        self.assertFalse(ctx.options.get("compile_ok"))
        # the tool worked; the *code* is broken -- that is a finding, not a tool error
        self.assertEqual(result.status, ToolStatus.OK)
        self.assertIsNone(result.error)
        self.assertTrue(result.findings, "a compile failure must produce a finding")
        self.assertTrue(
            any("COMPILE" in f.rule_id or "ERROR" in f.rule_id for f in result.findings),
            [f.rule_id for f in result.findings],
        )
        self.assertEqual(result.findings[0].file, "src/main/java/p/Broken.java")


class PmdTest(AdapterCase):
    def test_real_pmd_run_finds_the_unused_method(self):
        ctx = self.project({"src/main/java/p/Sample.java": UNUSED_METHOD})
        adapter = PmdAdapter(ctx)
        available, reason = adapter.available()
        self.assertTrue(available, f"PMD must be usable on this host: {reason}")
        version = adapter.version()
        print("pmd version:", version)

        result = adapter.scan(ctx)
        print("pmd command:", result.command)
        for finding in result.findings:
            print(f"  pmd hit: {finding.rule_id} {finding.file}:{finding.start_line}")

        self.assertEqual(result.status, ToolStatus.OK)
        self.assertIsNone(result.error)
        self.assertTrue(result.findings, "PMD must report the unused private method")
        self.assertIn("java", result.command)
        self.assertIn("-cp", result.command)
        self.assertIn("net.sourceforge.pmd.PMD", result.command)
        self.assertTrue(all(f.provider == "pmd" for f in result.findings))
        self.assertTrue(any("UnusedPrivateMethod" in f.rule_id or "UNUSED" in f.rule_id.upper()
                            for f in result.findings), [f.rule_id for f in result.findings])

    def test_pmd_skips_a_changeset_with_no_java(self):
        ctx = self.project({"docs/note.md": "# hi\n"})
        result = PmdAdapter(ctx).scan(ctx)
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertEqual(result.error.kind, ToolFailureKind.UNSUPPORTED)
        self.assertFalse(result.error.evidence_gap)

    def test_pmd_missing_distribution_is_an_evidence_gap(self):
        ctx = self.project({"src/main/java/p/Sample.java": UNUSED_METHOD})
        broken = str(self.temp_dir("chm-nope-") / "absent")
        saved = os.environ.get("CHM_PMD_HOME")
        saved_root = os.environ.get("CHM_TOOLCHAIN_ROOT")
        os.environ["CHM_PMD_HOME"] = broken
        os.environ.pop("CHM_TOOLCHAIN_ROOT", None)
        try:
            result = PmdAdapter(ctx).scan(ctx)
        finally:
            if saved is not None:
                os.environ["CHM_PMD_HOME"] = saved
            if saved_root is not None:
                os.environ["CHM_TOOLCHAIN_ROOT"] = saved_root
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertIn(result.error.kind, (ToolFailureKind.MISSING, ToolFailureKind.CONFIG))
        self.assertTrue(result.error.evidence_gap)


class CpdTest(AdapterCase):
    def test_real_cpd_run_finds_the_duplication(self):
        ctx = self.project({"src/main/java/p/Dup.java": DUPLICATED})
        adapter = CpdAdapter(ctx)
        available, reason = adapter.available()
        self.assertTrue(available, f"CPD must be usable on this host: {reason}")
        print("cpd version:", adapter.version())

        result = adapter.scan(ctx)
        print("cpd command:", result.command)
        for finding in result.findings:
            print(f"  cpd hit: {finding.rule_id} {finding.file}:{finding.start_line}")

        self.assertEqual(result.status, ToolStatus.OK)
        self.assertTrue(result.findings, "CPD must report the duplicated block")
        self.assertIn("net.sourceforge.pmd.cpd.CPD", result.command)
        self.assertIn("--minimum-tokens", result.command)
        self.assertIn("100", result.command)

    def test_cpd_skips_vue(self):
        ctx = self.project({"src/App.vue": "<template><div/></template>\n"})
        result = CpdAdapter(ctx).scan(ctx)
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertEqual(result.error.kind, ToolFailureKind.UNSUPPORTED)


class SpotBugsTest(AdapterCase):
    def test_compile_then_scan_finds_the_unclosed_stream(self):
        ctx = self.project({"src/main/java/p/Leak.java": UNCLOSED_STREAM})
        adapter = SpotBugsAdapter(ctx)
        available, reason = adapter.available()
        self.assertTrue(available, f"SpotBugs must be usable on this host: {reason}")
        print("spotbugs version:", adapter.version())

        compile_result = CompileAdapter(ctx).scan(ctx)
        self.assertEqual(compile_result.status, ToolStatus.OK, compile_result.error)
        self.assertTrue(ctx.options.get("compile_ok"))

        result = adapter.scan(ctx)
        print("spotbugs command:", result.command)
        for finding in result.findings:
            print(f"  spotbugs hit: {finding.rule_id} {finding.file}:{finding.start_line}")

        self.assertEqual(result.status, ToolStatus.OK, result.error)
        self.assertTrue(result.findings, "SpotBugs must report the resource leak")
        self.assertTrue(
            any("OS_OPEN_STREAM" in f.rule_id for f in result.findings),
            [f.rule_id for f in result.findings],
        )

    def test_spotbugs_without_classes_is_unsupported(self):
        ctx = self.project({"src/main/java/p/Leak.java": UNCLOSED_STREAM})
        ctx.options.pop("classes_dir", None)
        result = SpotBugsAdapter(ctx).scan(ctx)
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertEqual(result.error.kind, ToolFailureKind.UNSUPPORTED)


class KnipTest(AdapterCase):
    def test_real_knip_run_finds_the_unused_dependency(self):
        repo = self.temp_dir("chm-knip-")
        (repo / "package.json").write_text(
            json.dumps(
                {
                    "name": "knip-probe",
                    "version": "1.0.0",
                    "main": "index.js",
                    "dependencies": {"left-pad": "^1.3.0"},
                }
            ),
            encoding="utf-8",
        )
        (repo / "index.js").write_text("console.log('hi');\n", encoding="utf-8")
        cache = repo / ".cache"
        cache.mkdir(exist_ok=True)
        ctx = ScanContext(
            repo_root=repo,
            mode=ReviewMode.REPO,
            changed_files=[ChangedFile(path="index.js", language=language_of("index.js"))],
            config=Config(),
            cache_dir=cache,
            options={"whole_file": True},
        )

        adapter = KnipAdapter(ctx)
        available, reason = adapter.available()
        self.assertTrue(available, f"knip must be usable on this host: {reason}")
        print("knip version:", adapter.version())

        result = adapter.scan(ctx)
        print("knip command:", result.command)
        for finding in result.findings:
            print(f"  knip hit: {finding.rule_id} {finding.file}:{finding.start_line}")

        self.assertEqual(result.status, ToolStatus.OK, result.error)
        self.assertTrue(result.findings, "knip must report the unused dependency")
        self.assertTrue(
            any("UNUSED-DEPENDENCY" in f.rule_id for f in result.findings),
            [f.rule_id for f in result.findings],
        )
        self.assertTrue(any("left-pad" in f.message for f in result.findings))


class SemgrepTest(AdapterCase):
    """Semgrep is genuinely not installed on this host -- assert the honest answer."""

    def test_semgrep_is_unavailable_with_a_missing_tool_error(self):
        ctx = self.project({"src/main/java/p/Sample.java": UNUSED_METHOD})
        adapter = SemgrepAdapter(ctx)
        available, reason = adapter.available()
        self.assertFalse(available, "semgrep is expected to be absent on this host")
        print("semgrep availability reason:", reason)

        result = adapter.scan(ctx)
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.kind, ToolFailureKind.MISSING)
        self.assertTrue(result.error.evidence_gap)
        self.assertEqual(result.error.provider, "semgrep")
        self.assertEqual(result.findings, [])


class OpenRewriteTest(AdapterCase):
    """The adapter must name the *real* reason it cannot run a recipe.

    On this host Maven is present and healthy (``mvn -v`` succeeds,
    ``E:\\apache-maven-3.9.14``), but the ``rewrite-maven-plugin`` has never
    been resolved into ``~/.m2/repository``.  So the honest answer is not
    "no Maven" -- it is "Maven runs, the plugin would have to be downloaded
    first", and the adapter is expected to say exactly that.
    """

    def test_openrewrite_is_unavailable_with_a_real_reason(self):
        ctx = self.project({"pom.xml": "<project/>\n"})
        adapter = OpenRewriteAdapter(ctx)
        available, reason = adapter.available()
        self.assertFalse(available, "OpenRewrite is expected to be unusable on this host")
        print("openrewrite availability reason:", reason)
        self.assertTrue(reason)

        result = adapter.scan(ctx)
        self.assertEqual(result.status, ToolStatus.UNAVAILABLE)
        self.assertIsNotNone(result.error)
        self.assertIn(
            result.error.kind,
            (ToolFailureKind.MISSING, ToolFailureKind.DISABLED, ToolFailureKind.CONFIG),
        )
        detail = (result.error.detail or "") + " " + (reason or "")
        self.assertTrue(
            "Maven" in detail or "mvn" in detail or "plugin" in detail,
            f"the reason must name the real cause, got: {detail!r}",
        )
        self.assertEqual(result.findings, [])

    def test_maven_itself_is_healthy_so_the_reason_must_be_the_plugin(self):
        """Guard against the adapter blaming Maven for a plugin problem."""
        ctx = self.project({"pom.xml": "<project/>\n"})
        adapter = OpenRewriteAdapter(ctx)
        maven_ok, maven_reason = adapter._maven_probe()
        if not maven_ok:
            self.skipTest(f"Maven is genuinely unusable on this host: {maven_reason}")

        available, reason = adapter.available()
        self.assertFalse(available)
        self.assertIn("plugin", (reason or "").lower())
        self.assertNotIn("could not be launched", (reason or "").lower())
        print(f"maven version probed as {adapter.version()!r}; openrewrite reason: {reason}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
