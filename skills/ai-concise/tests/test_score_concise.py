#!/usr/bin/env python3
"""concise-mind 评测资产自检（零依赖，stdlib unittest）。

    python -m unittest discover -s tests -v
    # 或
    python tests/test_score_concise.py

守的是三件事：
  1. 契约不烂 —— evals.json / runs.json 结构合法、id 唯一、check key 都被打分器认识；
  2. 不打自己 —— C2 黄金样本在新黑名单下不得被误伤（防「加规则 → 误杀好输出」）；
  3. 探针还灵 —— 每条植入缺陷样本必须被对应维度检出（防「打分器变哑巴」）。
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import score_concise as S  # noqa: E402

MODES = {"CHAT", "CODE", "ARCH", "HANDOFF", "INCIDENT", "DOC", "PLAN"}
KNOWN_KEYS = {
    "max_chars", "max_lines", "max_sentences", "max_list_items",
    "must_regex", "forbidden_regex", "forbidden_shapes", "require_fields",
    "must_keep", "min_chars", "must_numbers", "must_paths", "min_density",
    "first_line_forbid_regex", "last_line_regex", "why",
}


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


EVALS = load("evals.json")
RUNS = load("evals/runs.json")
CASES = {c["id"]: c for c in EVALS["cases"]}
GFORB = S.load_global_forbidden(ROOT / "references" / "filler-blacklist.md")


class TestContract(unittest.TestCase):
    def test_case_ids_unique(self):
        ids = [c["id"] for c in EVALS["cases"]]
        self.assertEqual(len(ids), len(set(ids)), "evals.json 存在重复 id")

    def test_every_case_has_known_mode_and_keys(self):
        for c in EVALS["cases"]:
            self.assertIn(c["mode"], MODES, f"{c['id']}: 未知 mode")
            unknown = set(c["check"]) - KNOWN_KEYS
            self.assertFalse(unknown, f"{c['id']}: 打分器不认识的 check key {unknown}")
            for f in c["check"].get("require_fields", []):
                self.assertIn(f, S.FIELDS, f"{c['id']}: 未知 Gate 字段 {f}")

    def test_every_case_has_runs(self):
        seen = {r["id"] for r in RUNS["runs"]}
        missing = [c["id"] for c in EVALS["cases"] if c["id"] not in seen]
        self.assertFalse(missing, f"以下用例没有任何样本：{missing}")

    def test_every_case_has_c0_c1_c2(self):
        by = {}
        for r in RUNS["runs"]:
            if r["condition"] != "PROBE":
                by.setdefault(r["id"], set()).add(r["condition"])
        for c in EVALS["cases"]:
            self.assertEqual(by.get(c["id"], set()), {"C0", "C1", "C2"},
                             f"{c['id']}: 条件样本不全（三条件必须同题可比）")

    def test_blacklist_regex_all_compile(self):
        for kind in ("phrases", "shapes"):
            self.assertTrue(GFORB[kind], f"黑名单 {kind} 为空 —— SSOT 可能被改坏")
            for p in GFORB[kind]:
                try:
                    re.compile(p)
                except re.error as e:  # pragma: no cover
                    self.fail(f"黑名单 {kind} 正则无法编译: {p} ({e})")


class TestNoSelfHarm(unittest.TestCase):
    """C2 黄金样本必须满分 —— 加规则不得误杀达标输出。"""

    def test_c2_golden_is_clean(self):
        for r in RUNS["runs"]:
            if r["condition"] != "C2":
                continue
            res = S.score_one(CASES[r["id"]], r["output"], GFORB)
            d = res["dims"]
            self.assertEqual(d["filler"], 100.0,
                             f"{r['id']}/C2 被套话规则误伤: {res['detail']['filler_hits']}")
            self.assertEqual(d["accuracy"], 100.0,
                             f"{r['id']}/C2 精度扣分: {res['detail'].get('accuracy_forbidden')}"
                             f" must={res['detail'].get('must_regex')}")
            self.assertEqual(d["discipline"], 100.0,
                             f"{r['id']}/C2 形状门扣分: {res['detail']['discipline_bad']}")
            self.assertEqual(d["brevity"], 100.0,
                             f"{r['id']}/C2 超预算: {res['detail'].get('list_over')}"
                             f" {res['detail'].get('chars')}")


class TestProbes(unittest.TestCase):
    """探针必须全部检出 —— 打分器不得变哑巴。"""

    def test_all_probes_detected(self):
        probes = [r for r in RUNS["runs"] if r["condition"] == "PROBE"]
        self.assertGreaterEqual(len(probes), 8, "探针太少，覆盖不住各维度")
        for r in probes:
            exp = r["probe_expect"]
            got = S.score_one(CASES[r["id"]], r["output"], GFORB)["dims"][exp]
            self.assertLess(got, 100.0,
                            f"{r['id']} 探针漏检：植入 {exp} 缺陷但该维度仍 {got}")

    def test_probes_cover_core_dims(self):
        covered = {r["probe_expect"] for r in RUNS["runs"] if r["condition"] == "PROBE"}
        for dim in ("filler", "accuracy", "fidelity", "preserve", "brevity",
                    "adapt", "discipline", "stick"):
            self.assertIn(dim, covered, f"维度 {dim} 没有探针")


class TestShapeGate(unittest.TestCase):
    """v5 形状门的正负例（见 references/reader-first.md）。"""

    def test_first_line_forbid_catches_announcement(self):
        chk = {"first_line_forbid_regex": ["^\\s*(?:让我|我来|接下来)"]}
        bad = S.discipline_score("让我先看看代码。\n\n原因是 X。", chk)
        good = S.discipline_score("原因是 X。\n\n下一步：看日志。", chk)
        self.assertIn("first_line_announce", bad[1])
        self.assertNotIn("first_line_announce", good[1])

    def test_last_line_requires_next_action(self):
        chk = {"last_line_regex": ["下一步|验证："]}
        bad = S.discipline_score("原因是 X。\n\n希望这能帮到你。", chk)
        good = S.discipline_score("原因是 X。\n\n下一步：看日志。", chk)
        self.assertIn("last_line_next", bad[1])
        self.assertNotIn("last_line_next", good[1])

    def test_list_cap_counts_bullets(self):
        self.assertEqual(S.count_list_items("1. a\n2. b\n- c\n\n正文"), 3)
        self.assertEqual(S.count_list_items("| a | b |\n|---|---|"), 0)
        chk = {"max_list_items": 5}
        nine = "\n".join(f"{i}. x" for i in range(1, 10))
        res = S.score_one({"id": "t", "check": chk}, nine, GFORB)
        self.assertLess(res["dims"]["brevity"], 100.0)
        self.assertEqual(res["detail"]["list_over"], 9)

    def test_shape_gate_is_opt_in(self):
        """未声明形状门的用例分母不得变化（旧用例可比性）。"""
        plain = S.discipline_score("让我先看看。\n\n随便写点。", {})
        self.assertEqual(plain[0], 100.0)
        self.assertEqual(len(plain[1]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
