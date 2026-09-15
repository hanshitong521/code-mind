"""Spec §38: the six review modes against a real git repository, plus edge cases."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

import helpers
from helpers import CHMTestCase, commit_all, write_bytes, write_files

from chm.config import Config
from chm.context.gitctx import (
    parse_unified_diff,
    probe_repo,
    resolve_changed_files,
    resolve_context,
)
from chm.contracts import ChangeKind, ReviewMode
from chm.errors import ContextError, GitError

KEEP_V1 = """\
package p;

public class Keep {
    public int add(int a, int b) {
        return a + b;
    }
}
"""

KEEP_V2 = """\
package p;

public class Keep {
    public int add(int a, int b) {
        return a + b;
    }

    public int sub(int a, int b) {
        return a - b;
    }
}
"""

GONE = """\
package p;

public class Gone {
}
"""

FRESH = """\
package p;

public class Fresh {
}
"""

NAME = """\
package old;

public class Name {
    public void hello() {
    }
}
"""


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


class GitModesBase(CHMTestCase):
    def base_repo(self) -> tuple[Path, str]:
        repo = self.temp_repo(
            {
                "src/main/java/p/Keep.java": KEEP_V1,
                "src/main/java/p/Gone.java": GONE,
                "old/Name.java": NAME,
                "docs/note.md": "# note\n",
                "crlf/File.java": "package c;\r\n\r\npublic class File {\r\n}\r\n",
                "big/Big.java": "package b;\n\npublic class Big {\n"
                + "".join(f"    int f{i} = {i};\n" for i in range(400))
                + "}\n",
            },
            commit=False,
        )
        write_bytes(repo, "bin/data.bin", bytes(range(256)) * 8)
        base = commit_all(repo, "base")
        return repo, base

    def apply_scenario(self, repo: Path) -> None:
        """modify / add / delete / rename / binary / crlf, all at once."""
        write_files(repo, {"src/main/java/p/Keep.java": KEEP_V2})
        write_files(repo, {"src/main/java/p/Fresh.java": FRESH})
        (repo / "src/main/java/p/Gone.java").unlink()
        res = git(repo, "mv", "old/Name.java", "new/Renamed.java")
        self.assertEqual(res.returncode, 0, res.stderr)
        write_bytes(repo, "bin/data.bin", bytes(range(255, -1, -1)) * 8)
        write_files(
            repo,
            {"crlf/File.java": "package c;\r\n\r\npublic class File {\r\n    int x = 1;\r\n}\r\n"},
        )

    def by_path(self, ctx) -> dict:
        return {cf.path: cf for cf in ctx.changed_files}

    def head(self, repo: Path) -> str:
        return git(repo, "rev-parse", "HEAD").stdout.strip()


class DiffModeTest(GitModesBase):
    def test_diff_reports_every_change_kind(self):
        repo, _base = self.base_repo()
        self.apply_scenario(repo)

        ctx = resolve_context(repo, mode=ReviewMode.DIFF, config=helpers.make_config())
        files = self.by_path(ctx)

        keep = files["src/main/java/p/Keep.java"]
        self.assertEqual(keep.change_kind, ChangeKind.MODIFIED)
        self.assertGreaterEqual(keep.added_lines, 4)
        self.assertEqual(keep.removed_lines, 0)
        self.assertGreaterEqual(len(keep.hunks), 1)
        self.assertIsNone(keep.old_path)

        fresh = files["src/main/java/p/Fresh.java"]
        self.assertEqual(fresh.change_kind, ChangeKind.ADDED)
        self.assertGreater(fresh.added_lines, 0)
        self.assertIsNone(fresh.old_path)

        gone = files["src/main/java/p/Gone.java"]
        self.assertEqual(gone.change_kind, ChangeKind.DELETED)
        self.assertGreater(gone.removed_lines, 0)
        self.assertEqual(gone.added_lines, 0)

        renamed = files["new/Renamed.java"]
        self.assertEqual(renamed.change_kind, ChangeKind.RENAMED)
        self.assertEqual(renamed.old_path, "old/Name.java")

        binary = files["bin/data.bin"]
        self.assertTrue(binary.is_binary)
        self.assertEqual(binary.change_kind, ChangeKind.MODIFIED)
        self.assertEqual(binary.hunks, [])

        crlf = files["crlf/File.java"]
        self.assertEqual(crlf.change_kind, ChangeKind.MODIFIED)
        self.assertGreaterEqual(crlf.added_lines, 1)
        self.assertEqual(crlf.hunks[0].lines[-1][:1], "+")
        self.assertNotIn("\r", "".join(crlf.hunks[0].lines))

    def test_diff_is_sorted_and_deterministic(self):
        repo, _base = self.base_repo()
        self.apply_scenario(repo)
        cfg = helpers.make_config()
        runs = []
        for _ in range(3):
            ctx = resolve_context(repo, mode=ReviewMode.DIFF, config=cfg)
            runs.append([(cf.path, cf.change_kind.value, cf.added_lines, cf.removed_lines)
                         for cf in ctx.changed_files])
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[1], runs[2])
        self.assertEqual([r[0] for r in runs[0]], sorted(r[0] for r in runs[0]))

    def test_changed_line_numbers_come_from_the_hunks(self):
        repo, _base = self.base_repo()
        write_files(repo, {"src/main/java/p/Keep.java": KEEP_V2})
        ctx = resolve_context(repo, mode=ReviewMode.DIFF, config=helpers.make_config())
        cf = self.by_path(ctx)["src/main/java/p/Keep.java"]
        lines = cf.changed_line_numbers
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(ctx.is_changed_line(cf.path, line))
        self.assertFalse(ctx.is_changed_line(cf.path, 1))

    def test_large_file_size_is_reported(self):
        repo, _base = self.base_repo()
        write_files(repo, {"big/Big.java": (repo / "big/Big.java").read_text(encoding="utf-8") + "// touched\n"})
        ctx = resolve_context(repo, mode=ReviewMode.DIFF, config=helpers.make_config())
        cf = self.by_path(ctx)["big/Big.java"]
        self.assertEqual(cf.size_bytes, (repo / "big/Big.java").stat().st_size)
        self.assertGreater(cf.size_bytes, 4000)
        self.assertFalse(cf.is_binary)


class StagedModeTest(GitModesBase):
    def test_staged_sees_only_the_index(self):
        repo, _base = self.base_repo()
        write_files(repo, {"src/main/java/p/Keep.java": KEEP_V2})
        git(repo, "add", "src/main/java/p/Keep.java")
        # a further unstaged edit must NOT appear in --staged
        write_files(repo, {"docs/note.md": "# changed after staging\n"})

        ctx = resolve_context(repo, mode=ReviewMode.STAGED, config=helpers.make_config())
        paths = {cf.path for cf in ctx.changed_files}
        self.assertEqual(paths, {"src/main/java/p/Keep.java"})
        cf = self.by_path(ctx)["src/main/java/p/Keep.java"]
        self.assertEqual(cf.change_kind, ChangeKind.MODIFIED)
        self.assertGreaterEqual(cf.added_lines, 4)

    def test_staged_rename_and_delete(self):
        repo, _base = self.base_repo()
        git(repo, "mv", "old/Name.java", "new/Renamed.java")
        git(repo, "rm", "-q", "src/main/java/p/Gone.java")
        ctx = resolve_context(repo, mode=ReviewMode.STAGED, config=helpers.make_config())
        files = self.by_path(ctx)
        self.assertEqual(files["new/Renamed.java"].change_kind, ChangeKind.RENAMED)
        self.assertEqual(files["new/Renamed.java"].old_path, "old/Name.java")
        self.assertEqual(files["src/main/java/p/Gone.java"].change_kind, ChangeKind.DELETED)


class CommitModeTest(GitModesBase):
    def test_commit_reviews_exactly_one_commit(self):
        repo, base = self.base_repo()
        write_files(repo, {"src/main/java/p/Keep.java": KEEP_V2})
        write_files(repo, {"src/main/java/p/Fresh.java": FRESH})
        sha = commit_all(repo, "feature")

        ctx = resolve_context(repo, mode=ReviewMode.COMMIT, config=helpers.make_config(), commit=sha)
        files = self.by_path(ctx)
        self.assertEqual(set(files), {"src/main/java/p/Keep.java", "src/main/java/p/Fresh.java"})
        self.assertEqual(files["src/main/java/p/Fresh.java"].change_kind, ChangeKind.ADDED)
        self.assertEqual(files["src/main/java/p/Keep.java"].change_kind, ChangeKind.MODIFIED)

    def test_commit_requires_a_sha(self):
        repo, _base = self.base_repo()
        with self.assertRaises(ContextError):
            resolve_changed_files(
                probe_repo(repo), mode=ReviewMode.COMMIT, config=helpers.make_config()
            )

    def test_commit_with_a_bad_sha_raises_git_error(self):
        repo, _base = self.base_repo()
        with self.assertRaises(GitError):
            resolve_changed_files(
                probe_repo(repo),
                mode=ReviewMode.COMMIT,
                commit="0" * 40,
                config=helpers.make_config(),
            )


class RangeModeTest(GitModesBase):
    def test_range_covers_every_commit_in_between(self):
        repo, base = self.base_repo()
        write_files(repo, {"src/main/java/p/Keep.java": KEEP_V2})
        first = commit_all(repo, "one")
        write_files(repo, {"src/main/java/p/Fresh.java": FRESH})
        second = commit_all(repo, "two")

        ctx = resolve_context(
            repo,
            mode=ReviewMode.RANGE,
            config=helpers.make_config(),
            base_ref=base,
            head_ref=second,
        )
        files = self.by_path(ctx)
        self.assertEqual(set(files), {"src/main/java/p/Keep.java", "src/main/java/p/Fresh.java"})

    def test_range_requires_both_ends(self):
        repo, _base = self.base_repo()
        with self.assertRaises(ContextError):
            resolve_changed_files(
                probe_repo(repo),
                mode=ReviewMode.RANGE,
                base_ref="HEAD",
                config=helpers.make_config(),
            )

    def test_range_accepts_head_relative_refs(self):
        repo, _base = self.base_repo()
        write_files(repo, {"src/main/java/p/Keep.java": KEEP_V2})
        commit_all(repo, "one")
        ctx = resolve_context(
            repo,
            mode=ReviewMode.RANGE,
            config=helpers.make_config(),
            base_ref="HEAD~1",
            head_ref="HEAD",
        )
        self.assertEqual([cf.path for cf in ctx.changed_files], ["src/main/java/p/Keep.java"])


class FileModeTest(GitModesBase):
    def test_file_mode_limits_the_change_set(self):
        repo, _base = self.base_repo()
        write_files(repo, {"src/main/java/p/Keep.java": KEEP_V2})
        write_files(repo, {"docs/note.md": "# other\n"})
        ctx = resolve_context(
            repo,
            mode=ReviewMode.FILE,
            config=helpers.make_config(),
            file_arg="src/main/java/p/Keep.java",
        )
        self.assertEqual([cf.path for cf in ctx.changed_files], ["src/main/java/p/Keep.java"])

    def test_file_mode_on_an_unchanged_file_reviews_it_in_full(self):
        repo, _base = self.base_repo()
        ctx = resolve_context(
            repo,
            mode=ReviewMode.FILE,
            config=helpers.make_config(),
            file_arg="src/main/java/p/Gone.java",
        )
        self.assertEqual(len(ctx.changed_files), 1)
        self.assertEqual(ctx.changed_files[0].change_kind, ChangeKind.MODIFIED)
        self.assertIn("unchanged against HEAD", " ".join(ctx.options["git"]["warnings"]))

    def test_file_mode_rejects_paths_outside_the_repo(self):
        repo, _base = self.base_repo()
        outside = self.temp_dir() / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaises(ContextError):
            resolve_changed_files(
                probe_repo(repo),
                mode=ReviewMode.FILE,
                file_arg=str(outside),
                config=helpers.make_config(),
            )


class RepoModeTest(GitModesBase):
    def test_repo_mode_lists_every_tracked_file(self):
        repo, _base = self.base_repo()
        ctx = resolve_context(repo, mode=ReviewMode.REPO, config=helpers.make_config())
        paths = {cf.path for cf in ctx.changed_files}
        self.assertIn("src/main/java/p/Keep.java", paths)
        self.assertIn("docs/note.md", paths)
        self.assertIn("bin/data.bin", paths)
        self.assertIn("old/Name.java", paths)
        for cf in ctx.changed_files:
            self.assertEqual(cf.change_kind, ChangeKind.MODIFIED)
            self.assertEqual(cf.hunks, [])
        self.assertEqual(ctx.repo_files, sorted(ctx.repo_files))
        self.assertIn("src/main/java/p/Keep.java", ctx.repo_files)

    def test_repo_mode_marks_binary_files(self):
        repo, _base = self.base_repo()
        ctx = resolve_context(repo, mode=ReviewMode.REPO, config=helpers.make_config())
        self.assertTrue(self.by_path(ctx)["bin/data.bin"].is_binary)


class NonGitDirectoryTest(CHMTestCase):
    def test_diff_outside_a_repository_raises_a_clear_error(self):
        plain = self.temp_dir("chm-plain-")
        (plain / "a.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ContextError) as ctx:
            resolve_context(plain, mode=ReviewMode.DIFF, config=helpers.make_config())
        message = str(ctx.exception)
        self.assertIn("requires a git repository", message)
        self.assertIn("CHM_GIT_ERROR" if isinstance(ctx.exception, GitError) else "CHM_CONTEXT_ERROR", ctx.exception.code)

    def test_repo_mode_still_works_without_git(self):
        plain = self.temp_dir("chm-plain-")
        (plain / "src").mkdir()
        (plain / "src" / "A.java").write_text("class A {}\n", encoding="utf-8")
        (plain / "src" / "note.txt").write_text("hi\n", encoding="utf-8")
        ctx = resolve_context(plain, mode=ReviewMode.REPO, config=helpers.make_config())
        paths = {cf.path for cf in ctx.changed_files}
        self.assertIn("src/A.java", paths)
        self.assertNotIn("src/note.txt", paths)  # not a known source suffix
        self.assertIn("fell back to filesystem walk", " ".join(ctx.options["git"]["warnings"]))

    def test_probe_repo_reports_is_git_false(self):
        plain = self.temp_dir("chm-plain-")
        info = probe_repo(plain)
        self.assertFalse(info.is_git)
        self.assertEqual(info.head_sha, "")


class SpecialEntryTest(GitModesBase):
    """symlink (mode 120000) and submodule (mode 160000) entries."""

    def _add_special_index_entry(self, repo: Path, mode: str, target: str, path: str) -> None:
        tmp = repo / ".chm-special"
        tmp.write_text(target, encoding="utf-8")
        blob = git(repo, "hash-object", "-w", str(tmp))
        self.assertEqual(blob.returncode, 0, blob.stderr)
        sha = blob.stdout.strip()
        res = git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{sha},{path}")
        self.assertEqual(res.returncode, 0, res.stderr)
        tmp.unlink()

    def test_symlink_entry_is_parsed(self):
        repo, _base = self.base_repo()
        self._add_special_index_entry(repo, "120000", "src/main/java/p/Keep.java", "link/KeepLink.java")
        ctx = resolve_context(repo, mode=ReviewMode.STAGED, config=helpers.make_config())
        files = self.by_path(ctx)
        self.assertIn("link/KeepLink.java", files)
        self.assertEqual(files["link/KeepLink.java"].change_kind, ChangeKind.ADDED)

    def test_submodule_entry_is_parsed(self):
        repo, base = self.base_repo()
        self._add_special_index_entry(repo, "160000", base, "vendor/sub")
        ctx = resolve_context(repo, mode=ReviewMode.STAGED, config=helpers.make_config())
        files = self.by_path(ctx)
        self.assertIn("vendor/sub", files)
        self.assertEqual(files["vendor/sub"].change_kind, ChangeKind.ADDED)
        # a gitlink is a directory, never a readable blob
        self.assertFalse(files["vendor/sub"].is_binary)

    def test_gitlinks_survive_repo_mode(self):
        repo, base = self.base_repo()
        self._add_special_index_entry(repo, "160000", base, "vendor/sub")
        ctx = resolve_context(repo, mode=ReviewMode.REPO, config=helpers.make_config())
        self.assertIn("vendor/sub", {cf.path for cf in ctx.changed_files})


class DiffParserTest(unittest.TestCase):
    """Direct parser coverage for shapes git emits but a fixture cannot force."""

    def test_mode_change_only(self):
        diff = (
            "diff --git a/run.sh b/run.sh\n"
            "old mode 100644\n"
            "new mode 100755\n"
        )
        files = parse_unified_diff(diff, repo_root=helpers.repo_root(), config=Config())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].change_kind, ChangeKind.MODIFIED)
        self.assertEqual(files[0].hunks, [])

    def test_no_newline_marker_is_kept(self):
        diff = (
            "diff --git a/a.txt b/a.txt\n"
            "--- a/a.txt\n"
            "+++ b/a.txt\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "\\ No newline at end of file\n"
            "+new\n"
            "\\ No newline at end of file\n"
        )
        files = parse_unified_diff(diff, repo_root=helpers.repo_root(), config=Config())
        self.assertEqual(files[0].added_lines, 1)
        self.assertEqual(files[0].removed_lines, 1)
        self.assertEqual(len(files[0].hunks), 1)

    def test_excluded_paths_are_dropped(self):
        diff = (
            "diff --git a/node_modules/x.js b/node_modules/x.js\n"
            "--- a/node_modules/x.js\n"
            "+++ b/node_modules/x.js\n"
            "@@ -1 +1 @@\n"
            "-a\n"
            "+b\n"
        )
        self.assertEqual(parse_unified_diff(diff, repo_root=helpers.repo_root(), config=Config()), [])

    def test_malformed_hunk_header_raises(self):
        diff = (
            "diff --git a/a.txt b/a.txt\n"
            "--- a/a.txt\n"
            "+++ b/a.txt\n"
            "@@ not a hunk @@\n"
            "-a\n"
            "+b\n"
        )
        with self.assertRaises(ContextError):
            parse_unified_diff(diff, repo_root=helpers.repo_root(), config=Config())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
