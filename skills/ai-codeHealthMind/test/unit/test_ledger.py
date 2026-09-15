"""Spec §30 run ledger: full field set, percentiles, aggregation."""

from __future__ import annotations

import json
import unittest

import helpers

from chm.core.ledger import RunLedger, new_run_id, percentile, summarize_ledgers


class LedgerShapeTest(unittest.TestCase):
    REQUIRED = (
        "run_id",
        "repo",
        "commit",
        "base",
        "mode",
        "duration_ms",
        "tool_duration",
        "llm_calls",
        "input_tokens",
        "output_tokens",
        "cache_hit",
        "findings",
        "dedup_ratio",
        "gate",
    )

    def test_to_dict_contains_every_required_field(self):
        payload = RunLedger().to_dict()
        for key in self.REQUIRED:
            with self.subTest(key=key):
                self.assertIn(key, payload)

    def test_to_dict_extra_fields(self):
        payload = RunLedger().to_dict()
        self.assertIn("started_at", payload)
        self.assertIn("errors", payload)
        self.assertIn("error_count", payload)

    def test_add_tool_records_real_timings(self):
        ledger = RunLedger()
        ledger.add_tool("pmd", 1234, "OK")
        ledger.add_tool("semgrep", 5, "UNAVAILABLE")
        payload = ledger.to_dict()
        self.assertEqual(len(payload["tool_duration"]), 2)
        self.assertEqual(payload["tool_duration"][0], {"provider": "pmd", "duration_ms": 1234, "status": "OK"})
        self.assertEqual(payload["tool_duration"][1]["status"], "UNAVAILABLE")

    def test_add_llm_accumulates(self):
        ledger = RunLedger()
        ledger.add_llm(2, 100, 40)
        ledger.add_llm(1, 50, 20)
        self.assertEqual(ledger.llm_calls, 3)
        self.assertEqual(ledger.input_tokens, 150)
        self.assertEqual(ledger.output_tokens, 60)
        self.assertEqual(ledger.to_dict()["llm_calls"], 3)

    def test_error_count_is_derived(self):
        ledger = RunLedger(errors=[{"provider": "pmd"}, {"provider": "knip"}])
        self.assertEqual(ledger.to_dict()["error_count"], 2)

    def test_run_id_is_unique_but_sortable(self):
        a = new_run_id("E:/repo", mode="diff", commit="abc")
        b = new_run_id("E:/repo", mode="diff", commit="abc")
        self.assertNotEqual(a, b)
        self.assertEqual(len(a.split("-")[0]), 15)  # YYYYmmddTHHMMSS
        self.assertEqual(a[:8], b[:8])

    def test_write_produces_real_json(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            RunLedger(run_id="r1", gate="WARN", findings=3).write(path)
            self.assertTrue(path.is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["run_id"], "r1")
            self.assertEqual(data["gate"], "WARN")
            self.assertEqual(data["findings"], 3)


class PercentileTest(unittest.TestCase):
    def test_empty_is_zero(self):
        self.assertEqual(percentile([], 50), 0.0)
        self.assertEqual(percentile([], 95), 0.0)

    def test_single_value(self):
        self.assertEqual(percentile([7.0], 50), 7.0)
        self.assertEqual(percentile([7.0], 95), 7.0)

    def test_p50_of_one_to_four(self):
        # position = (4-1)*0.5 = 1.5 -> 2 + (3-2)*0.5 = 2.5
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)

    def test_p95_of_one_to_four(self):
        # position = 3*0.95 = 2.85 -> 3 + (4-3)*0.85 = 3.85
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 95), 3.85, places=6)

    def test_boundaries(self):
        self.assertEqual(percentile([1, 2, 3], 0), 1)
        self.assertEqual(percentile([1, 2, 3], 100), 3)

    def test_input_is_sorted_internally(self):
        self.assertEqual(percentile([4, 1, 3, 2], 50), percentile([1, 2, 3, 4], 50))


class SummarizeTest(helpers.CHMTestCase):
    def _write_ledger(self, directory, run_id, **fields):
        ledger = RunLedger(run_id=run_id, **fields)
        path = directory / run_id / "ledger.json"
        ledger.write(path)
        return path

    def test_aggregates_multiple_ledgers(self):
        runs = self.temp_dir("chm-runs-")
        r1 = RunLedger(
            run_id="r1",
            duration_ms=100,
            input_tokens=1000,
            output_tokens=100,
            cache_hit=0.5,
            findings=2,
            gate="WARN",
        )
        r1.write(runs / "r1" / "ledger.json")

        r2 = RunLedger(
            run_id="r2",
            duration_ms=300,
            input_tokens=3000,
            output_tokens=300,
            cache_hit=1.0,
            findings=4,
            gate="BLOCK",
        )
        r2.add_tool("pmd", 200, "OK")
        r2.write(runs / "r2" / "ledger.json")

        summary = summarize_ledgers(runs)
        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(summary["avg_input_tokens"], 2000.0)
        self.assertEqual(summary["avg_output_tokens"], 200.0)
        self.assertEqual(summary["p50_ms"], 200.0)
        self.assertEqual(summary["cache_hit_ratio"], 0.75)
        self.assertEqual(summary["gate_histogram"], {"BLOCK": 1, "WARN": 1})
        self.assertEqual(summary["tool_duration"]["pmd"]["avg_ms"], 200.0)
        self.assertEqual(summary["tool_duration"]["pmd"]["runs"], 1)
        self.assertEqual(summary["new_debt_per_run"]["total"], 6)
        self.assertEqual(summary["new_debt_per_run"]["avg"], 3.0)

    def test_malformed_ledger_is_counted_not_swallowed(self):
        runs = self.temp_dir("chm-runs-")
        self._write_ledger(runs, "good", duration_ms=10, gate="PASS")
        bad = runs / "bad" / "ledger.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{not json", encoding="utf-8")

        summary = summarize_ledgers(runs)
        self.assertEqual(summary["runs"], 1)
        self.assertEqual(summary["skipped"], 1)

    def test_empty_directory_degrades_honestly(self):
        summary = summarize_ledgers(self.temp_dir("chm-runs-"))
        self.assertEqual(summary["runs"], 0)
        self.assertEqual(summary["p50_ms"], 0.0)
        self.assertEqual(summary["gate_histogram"], {})

    def test_missing_directory_is_not_an_error(self):
        summary = summarize_ledgers(self.temp_dir("chm-runs-") / "absent")
        self.assertEqual(summary["runs"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
