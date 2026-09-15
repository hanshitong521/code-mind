#!/usr/bin/env python3
"""合并独立 agent 的盲测输出为一份 runs.json 供 score_concise.py 打分。

    python scripts/merge_blind.py --out evals/runs-blind.json

读取 evals/blind-C0.json / blind-C1.json / blind-C2.json（由独立 agent 产出，
产出者未接触 evals.json 与评分器），合并为评分器可读的 runs 格式。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

COND_DESC = {
    "C0": "盲测 · 裸模型（无任何压缩规则）—— 独立 agent 产出",
    "C1": "盲测 · 仅触发词式压缩（无锁存）—— 独立 agent 产出",
    "C2": "盲测 · concise-mind v3.1 完整规则（锁存 + 七模式 + 双 Gate）—— 独立 agent 产出",
}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(root / "evals" / "runs-blind.json"))
    ap.add_argument("--cases", default=str(root / "evals.json"))
    ap.add_argument("--suffix", default="", help="轮次后缀，如 r2 → 读 blind-r2-C2.json")
    args = ap.parse_args()

    order = [c["id"] for c in json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]]
    sfx = f"-{args.suffix}" if args.suffix else ""
    runs: list[dict] = []
    present: list[str] = []
    for cond in ("C0", "C1", "C2"):
        f = root / "evals" / f"blind{sfx}-{cond}.json"
        if not f.exists():
            print(f"[skip] {f} 不存在")
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        by_id = {r["id"]: r.get("output", "") for r in data.get("runs", [])}
        missing = [i for i in order if i not in by_id]
        if missing:
            print(f"[warn] {cond} 缺用例：{missing}")
        for cid in order:
            if cid in by_id:
                runs.append({"id": cid, "condition": cond, "output": by_id[cid]})
        present.append(cond)
        print(f"[ok] {cond}: {len(by_id)} 条")

    out = {
        "schema": "concise-mind-runs-blind",
        "version": 4,
        "note": "独立盲测样本：由未接触 evals.json / 评分器的 agent 按各自条件产出。",
        "conditions": {c: COND_DESC[c] for c in present},
        "runs": runs,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[merged] {len(runs)} 条 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
