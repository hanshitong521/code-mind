#!/usr/bin/env python3
"""把 runs-blind.json 匿名化成盲评包（A/B/C 标签）+ 密封对照表。

    python scripts/make_judge_bundle.py --runs evals/runs-blind.json \
        --out evals/judge/bundle.json --key evals/judge/key.json --round r9

产出两份文件：
  - bundle.json —— 发给盲评者的匿名包（每条含 case_id / prompt / 三份回复 A B C + 判据正文）
  - key.json    —— 密封对照表（label -> condition），盲评结束后才允许读取

设计：label 用 (round, case_id) 做种子的确定性洗牌，保证同一轮可复现，
但不随条件固定 —— 避免盲评者从"A 总是最短"这种规律猜出条件。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

LABELS = ("A", "B", "C")


def load_rubric(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"<!-- judge:begin -->(.*?)<!-- judge:end -->", text, flags=re.S)
    if not m:
        raise SystemExit(f"rubric 缺少 judge:begin/judge:end 块: {path}")
    return m.group(1).strip()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(root / "evals" / "runs-blind.json"))
    ap.add_argument("--evals", default=str(root / "evals.json"))
    ap.add_argument("--rubric", default=str(root / "evals" / "judge" / "rubric.md"))
    ap.add_argument("--out", default=str(root / "evals" / "judge" / "bundle.json"))
    ap.add_argument("--key", default=str(root / "evals" / "judge" / "key.json"))
    ap.add_argument("--round", default="r1")
    args = ap.parse_args()

    runs = json.loads(Path(args.runs).read_text(encoding="utf-8"))
    evals = json.loads(Path(args.evals).read_text(encoding="utf-8"))
    prompts = {c["id"]: c["prompt"] for c in evals["cases"]}

    by_case: dict[str, dict[str, str]] = {}
    for r in runs["runs"]:
        by_case.setdefault(r["id"], {})[r["condition"]] = r["output"]

    conds = sorted({r["condition"] for r in runs["runs"] if r["condition"] != "PROBE"})
    items, key = [], {}
    for cid, outs in by_case.items():
        missing = [c for c in conds if c not in outs]
        if missing:
            print(f"[skip] {cid}: 缺条件 {missing}（盲评必须同题同条件，否则不可比）")
            continue
        seed = int(hashlib.sha256(f"{args.round}:{cid}".encode()).hexdigest()[:8], 16)
        order = list(conds)
        random.Random(seed).shuffle(order)
        mapping = dict(zip(LABELS, order))
        key[cid] = mapping
        items.append({
            "case_id": cid,
            "prompt": prompts.get(cid, ""),
            "responses": {lab: outs[cond] for lab, cond in mapping.items()},
        })

    bundle = {
        "round": args.round,
        "labels": list(LABELS),
        "rubric": load_rubric(Path(args.rubric)),
        "items": items,
        "instructions": (
            "对每条 item 的三份回复 A/B/C 打分。只输出 JSONL，每行一个对象，字段："
            '{"case_id": str, "label": "A"|"B"|"C", "correctness": 1-5, "actionability": 1-5,'
            ' "concision": 1-5, "autonomy": 1-5, "safety": 1-5, "blocker": bool, "notes": str}。'
            "不要输出解释性前言或结尾。"
        ),
    }
    out, kp = Path(args.out), Path(args.key)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kp.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[bundle] {out}  用例 {len(items)} 条 × {len(LABELS)} 份 = {len(items) * 3} 份回复")
    print(f"[key]    {kp}  （盲评期间禁止读取）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
