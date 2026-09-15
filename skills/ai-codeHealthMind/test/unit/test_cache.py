"""Spec §33 cache behaviour and the five §14.3 key elements."""

from __future__ import annotations

import json
import unittest

import helpers

from chm.core.cache import KEY_ELEMENTS, RunCache, cache_key, repo_cache_dir
from chm.util import sha256_text


def _parts(file_hash: str, *, tool: str = "pmd-6.55.0", head: str = "abc123") -> dict[str, str]:
    return {
        "tool-version": tool,
        "repo-head": head,
        "file-hash": file_hash,
        "rule-version": "ruleset-v1",
        "config-hash": "cfg-1",
    }


class KeyElementTest(unittest.TestCase):
    def test_key_elements_match_spec_14_3(self):
        self.assertEqual(
            KEY_ELEMENTS,
            ("tool-version", "repo-head", "file-hash", "rule-version", "config-hash"),
        )

    def test_five_elements(self):
        self.assertEqual(len(KEY_ELEMENTS), 5)

    def test_cache_key_is_sha256_and_deterministic(self):
        key = cache_key("a", "b", "c")
        self.assertEqual(len(key), 64)
        self.assertEqual(key, cache_key("a", "b", "c"))
        self.assertEqual(key, sha256_text("a\x00b\x00c"))

    def test_changing_any_element_changes_the_key(self):
        base = _parts("h1")
        baseline = cache_key(*[f"{name}={base[name]}" for name in KEY_ELEMENTS])
        for name in KEY_ELEMENTS:
            with self.subTest(element=name):
                changed = dict(base)
                changed[name] = "different"
                other = cache_key(*[f"{n}={changed[n]}" for n in KEY_ELEMENTS])
                self.assertNotEqual(baseline, other)


class CacheBehaviourTest(helpers.CHMTestCase):
    """miss -> hit -> (one file edited) miss, with real CacheStats printed."""

    def test_miss_then_hit_then_invalidated_scope(self):
        cache_dir = self.temp_dir("chm-cache-")
        value = {"findings": [{"rule_id": "CHM-JAVA-DEAD-001"}]}

        first = RunCache(cache_dir, key_parts=_parts("hash-A"))
        self.assertIsNone(first.get("pmd", "src/a.java"))
        first.put("pmd", "src/a.java", value)
        self.assertEqual(first.get("pmd", "src/a.java"), value)
        stats_first = first.stats()
        print("CacheStats[run1] =", json.dumps(stats_first.to_dict(), sort_keys=True))
        self.assertEqual(stats_first.hits, 1)
        self.assertEqual(stats_first.misses, 1)
        self.assertEqual(stats_first.writes, 1)
        self.assertEqual(stats_first.ratio, 0.5)

        # second run, nothing changed -> the same key still resolves
        second = RunCache(cache_dir, key_parts=_parts("hash-A"))
        self.assertEqual(second.get("pmd", "src/a.java"), value)
        stats_second = second.stats()
        print("CacheStats[run2] =", json.dumps(stats_second.to_dict(), sort_keys=True))
        self.assertEqual(stats_second.hits, 1)
        self.assertEqual(stats_second.misses, 0)
        self.assertEqual(stats_second.ratio, 1.0)

        # third run, one file edited -> only the keys that mention it miss
        third = RunCache(cache_dir, key_parts=_parts("hash-B"))
        self.assertIsNone(third.get("pmd", "src/a.java"))
        stats_third = third.stats()
        print("CacheStats[run3] =", json.dumps(stats_third.to_dict(), sort_keys=True))
        self.assertEqual(stats_third.hits, 0)
        self.assertEqual(stats_third.misses, 1)
        self.assertEqual(stats_third.ratio, 0.0)

    def test_other_key_elements_also_invalidate(self):
        cache_dir = self.temp_dir("chm-cache-")
        RunCache(cache_dir, key_parts=_parts("h")).put("pmd", "k", 1)
        for name in ("tool-version", "repo-head", "rule-version", "config-hash"):
            with self.subTest(element=name):
                parts = _parts("h")
                parts[name] = "changed"
                self.assertIsNone(RunCache(cache_dir, key_parts=parts).get("pmd", "k"))

    def test_namespaces_are_isolated(self):
        cache_dir = self.temp_dir("chm-cache-")
        cache = RunCache(cache_dir, key_parts=_parts("h"))
        cache.put("pmd", "k", "pmd-value")
        cache.put("cpd", "k", "cpd-value")
        self.assertEqual(cache.get("pmd", "k"), "pmd-value")
        self.assertEqual(cache.get("cpd", "k"), "cpd-value")

    def test_invalidate_one_namespace(self):
        cache_dir = self.temp_dir("chm-cache-")
        cache = RunCache(cache_dir, key_parts=_parts("h"))
        cache.put("pmd", "k", "v")
        cache.put("cpd", "k", "v")
        cache.invalidate("pmd")
        self.assertIsNone(RunCache(cache_dir, key_parts=_parts("h")).get("pmd", "k"))
        self.assertEqual(RunCache(cache_dir, key_parts=_parts("h")).get("cpd", "k"), "v")

    def test_invalidate_everything(self):
        cache_dir = self.temp_dir("chm-cache-")
        cache = RunCache(cache_dir, key_parts=_parts("h"))
        cache.put("pmd", "k", "v")
        cache.invalidate()
        self.assertEqual(list(cache_dir.glob("*.json")), [])

    def test_entry_key_is_stored_not_the_raw_key(self):
        cache_dir = self.temp_dir("chm-cache-")
        RunCache(cache_dir, key_parts=_parts("h")).put("pmd", "src/a.java", 42)
        payload = json.loads((cache_dir / "pmd.json").read_text(encoding="utf-8"))
        self.assertNotEqual(payload["key"], "src/a.java")
        self.assertEqual(len(payload["key"]), 64)
        self.assertEqual(payload["value"], 42)

    def test_ratio_is_zero_before_any_lookup(self):
        stats = RunCache(self.temp_dir("chm-cache-"), key_parts=_parts("h")).stats()
        self.assertEqual(stats.to_dict(), {"hits": 0, "misses": 0, "writes": 0, "ratio": 0.0})


class CacheDirTest(helpers.CHMTestCase):
    def test_repo_cache_dir_follows_run_dir(self):
        repo = self.temp_dir("chm-repo-")
        cfg = helpers.make_config(**{"run_dir": ".codehealth/runs"})
        path = repo_cache_dir(repo, cfg, head_sha="deadbeef")
        self.assertEqual(path, repo / ".codehealth" / "runs" / "cache")
        # repo_cache_dir() is a pure path computation -- it must not create
        # anything on disk; the directory appears only when a RunCache is built.
        self.assertFalse(path.exists())

    def test_creating_a_cache_materialises_the_directory(self):
        repo = self.temp_dir("chm-repo-")
        cfg = helpers.make_config(**{"run_dir": ".codehealth/runs"})
        path = repo_cache_dir(repo, cfg, head_sha="deadbeef")
        RunCache(path, key_parts=_parts("f0"))
        self.assertTrue(path.is_dir())
        self.assertEqual(path, repo / ".codehealth" / "runs" / "cache")

    def test_head_sha_does_not_change_the_directory_layout(self):
        """§14.3 isolation lives in the key, not in the path."""
        repo = self.temp_dir("chm-repo-")
        cfg = helpers.make_config(**{"run_dir": ".codehealth/runs"})
        self.assertEqual(
            repo_cache_dir(repo, cfg, head_sha="aaaaaa"),
            repo_cache_dir(repo, cfg, head_sha="bbbbbb"),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
