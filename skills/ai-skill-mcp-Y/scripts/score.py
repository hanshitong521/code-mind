#!/usr/bin/env python3
"""score.py — SkillMind 评分引擎（spec-v2 §3.3 / §14.4）。

公式（权重不可私改，改即改 spec）：

    Score = 成功率×40% + 准确率×30% + Token效率×15% + 速度×10% + 稳定性×5%

分项归一：
    success_rate     = clamp01(metrics.success_rate) × 100
    accuracy         = clamp01(metrics.accuracy) × 100
    token_efficiency = clamp01(baseline.token_avg / metrics.token_avg) × 100
    speed            = clamp01(baseline.time_avg  / metrics.time_avg)  × 100
    stability        = clamp01(metrics.stability) × 100

铁律（§3.3 / §15）：原始指标必须与分数同时输出，禁止只存分数。
未提供 baseline 时用默认 {token_avg: 3000, time_avg: 20} 并标注 baseline_defaulted=true。

子命令：
    record --skill-id ID --metrics-json '<json>' [--baseline-json '<json>'] [--store P]
    report [--skill-id ID] [--store P]

只用标准库，裸 Python 3.9 可运行。退出码：0 成功 / 1 失败 / 2 用法或环境错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

SCHEMA_NAME = "skillmind-score-record"
SCHEMA_VERSION = 1

#: §3.3 权重（固定，禁止私改）。
WEIGHTS = {
    "success_rate": 0.40,
    "accuracy": 0.30,
    "token_efficiency": 0.15,
    "speed": 0.10,
    "stability": 0.05,
}

#: §14.4 默认基线。
DEFAULT_BASELINE = {"token_avg": 3000.0, "time_avg": 20.0}

#: §3.3 分档（下界, grade, 中文档位）。
GRADE_BANDS = (
    (95.0, "Production Grade", "生产级"),
    (90.0, "Strong", "强"),
    (80.0, "Usable", "可用待优化"),
    (70.0, "Review Before Release", "上线前复查"),
    (0.0, "Redesign or Disable", "重设计或禁用"),
)

#: 未参与打分但必须随原始指标一起保留的字段（§7 禁只报压缩率）。
RAW_PASSTHROUGH = ("bug_escape", "tool_calls", "duplicate_calls", "latency_ms",
                   "rework", "evidence_retention", "input_tokens", "output_tokens")

_REQUIRED_SCORED = ("success_rate", "accuracy", "token_avg", "time_avg", "stability")


# ────────────────────────────── 数值工具 ──────────────────────────────

def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def grade_of(score: float) -> tuple:
    """返回 (grade, grade_cn)。"""
    for low, grade, cn in GRADE_BANDS:
        if score >= low:
            return grade, cn
    return GRADE_BANDS[-1][1], GRADE_BANDS[-1][2]


# ────────────────────────────── 核心计算 ──────────────────────────────

def compute(metrics: dict, baseline: dict | None) -> dict:
    """按 §3.3 计算 subscores / score / grade，并保留全部原始指标。"""
    warnings: list = []

    raw_metrics: dict = {}
    for k, v in (metrics or {}).items():
        raw_metrics[str(k)] = v
    for k in _REQUIRED_SCORED:
        if k not in raw_metrics:
            warnings.append("metrics 缺少 %s：按缺省处理（比例类记 0，均值类记 1.0 倍基线）" % k)

    baseline_defaulted = not baseline
    base = {}
    src = baseline if baseline else DEFAULT_BASELINE
    for k in ("token_avg", "time_avg"):
        v = _num(src.get(k))
        if v is None or v <= 0:
            v = DEFAULT_BASELINE[k]
            if baseline:
                warnings.append("baseline.%s 非法，回落默认 %s" % (k, v))
        base[k] = v
    if baseline_defaulted:
        warnings.append("未提供 baseline，使用默认基线 token_avg=%s time_avg=%s（§14.4）"
                        % (base["token_avg"], base["time_avg"]))

    def ratio(metric_key: str) -> float:
        v = _num(raw_metrics.get(metric_key))
        if v is None or v <= 0:
            return 1.0
        return C.clamp01(base[metric_key] / v)

    def unit(key: str) -> float:
        v = _num(raw_metrics.get(key))
        return C.clamp01(v) if v is not None else 0.0

    subscores = {
        "success_rate": C.round2(unit("success_rate") * 100.0),
        "accuracy": C.round2(unit("accuracy") * 100.0),
        "token_efficiency": C.round2(ratio("token_avg") * 100.0),
        "speed": C.round2(ratio("time_avg") * 100.0),
        "stability": C.round2(unit("stability") * 100.0),
    }
    score = C.round2(sum(subscores[k] * WEIGHTS[k] for k in WEIGHTS))
    grade, grade_cn = grade_of(score)

    kept = {k: raw_metrics[k] for k in RAW_PASSTHROUGH if k in raw_metrics}
    kept.update({k: v for k, v in raw_metrics.items() if k not in kept})

    return {
        "metrics": kept,
        "baseline": base,
        "baseline_defaulted": baseline_defaulted,
        "subscores": subscores,
        "weights": dict(WEIGHTS),
        "score": score,
        "grade": grade,
        "grade_cn": grade_cn,
        "warnings": warnings,
    }


# ────────────────────────────── 存储 ──────────────────────────────

def store_path(root: Path, explicit: str | None) -> Path:
    if not explicit:
        return C.state_dir(root) / "scores.json"
    p = Path(explicit).expanduser()
    if p.is_dir():
        return p / "scores.json"
    return p


def load_store(path: Path) -> list:
    """读 scores.json；容忍 list / {"records": [...]} / {skill_id: {...}} 三种外层。"""
    data = C.load_json(path, default=None)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        recs = data.get("records")
        if isinstance(recs, list):
            return [r for r in recs if isinstance(r, dict)]
        out = []
        for k, v in data.items():
            if isinstance(v, dict) and "score" in v:
                rec = dict(v)
                rec.setdefault("skill_id", k)
                out.append(rec)
        return out
    return []


def save_store(path: Path, records: list) -> None:
    C.write_json(path, {
        "schema_name": "skillmind-scores",
        "schema_version": SCHEMA_VERSION,
        "updated_at": C.now_iso(),
        "records": records,
    })


# ────────────────────────────── 子命令 ──────────────────────────────

def _parse_json_arg(raw: str, name: str) -> tuple[dict | None, str]:
    try:
        val = json.loads(raw)
    except ValueError as exc:
        return None, "%s 不是合法 JSON: %s" % (name, exc)
    if not isinstance(val, dict):
        return None, "%s 必须是 JSON 对象" % name
    return val, ""


def cmd_record(args: Any, root: Path) -> int:
    metrics, err = _parse_json_arg(args.metrics_json, "--metrics-json")
    if metrics is None:
        C.eprint("ERROR: " + err)
        return EXIT_USAGE
    baseline = None
    if args.baseline_json:
        baseline, err = _parse_json_arg(args.baseline_json, "--baseline-json")
        if baseline is None:
            C.eprint("ERROR: " + err)
            return EXIT_USAGE
    elif isinstance(metrics.get("baseline"), dict):
        baseline = metrics["baseline"]

    calc = compute(metrics, baseline)
    record = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "skill_id": args.skill_id,
        "recorded_at": C.now_iso(),
        "metrics": calc["metrics"],
        "baseline": calc["baseline"],
        "baseline_defaulted": calc["baseline_defaulted"],
        "subscores": calc["subscores"],
        "weights": calc["weights"],
        "score": calc["score"],
        "grade": calc["grade"],
        "warnings": calc["warnings"],
    }

    path = store_path(root, args.store)
    records = load_store(path)
    records.append(record)
    try:
        save_store(path, records)
    except OSError as exc:
        C.eprint("ERROR: 写入 %s 失败: %s" % (path, exc))
        return EXIT_FAIL

    human = [
        C.banner("SkillMind Score — record"),
        "skill_id  : %s" % record["skill_id"],
        "store     : %s  (累计 %d 条)" % (C.relpath(path, root), len(records)),
        "score     : %s  [%s / %s]" % (record["score"], record["grade"], calc["grade_cn"]),
        "baseline  : token_avg=%s time_avg=%s%s"
        % (record["baseline"]["token_avg"], record["baseline"]["time_avg"],
           "  (defaulted)" if record["baseline_defaulted"] else ""),
        "",
        "原始指标（必须与分数同报）:",
    ]
    for k in sorted(record["metrics"]):
        human.append("  %-22s %s" % (k, record["metrics"][k]))
    human.append("")
    human.append("subscores:")
    for k in ("success_rate", "accuracy", "token_efficiency", "speed", "stability"):
        human.append("  %-18s %8.2f  × %.2f" % (k, record["subscores"][k], WEIGHTS[k]))
    human.append("  %-18s %8.2f" % ("score", record["score"]))
    if record["warnings"]:
        human.append("")
        human.append("warnings:")
        human.extend("  - %s" % w for w in record["warnings"])

    C.emit(record, as_json=args.json, human=human)
    return EXIT_OK


def cmd_report(args: Any, root: Path) -> int:
    path = store_path(root, args.store)
    records = load_store(path)
    if args.skill_id:
        records = [r for r in records if str(r.get("skill_id")) == args.skill_id]
    if args.skill_id and not records:
        C.eprint("ERROR: scores.json 中无 %s 的记录: %s" % (args.skill_id, path))
        return EXIT_FAIL

    by_skill: dict = {}
    for r in records:
        by_skill.setdefault(str(r.get("skill_id") or "?"), []).append(r)

    skills = []
    for sid in sorted(by_skill):
        recs = by_skill[sid]
        scores = [float(r["score"]) for r in recs if isinstance(r.get("score"), (int, float))]
        latest = recs[-1]
        grade, grade_cn = grade_of(float(latest.get("score") or 0.0))
        skills.append({
            "skill_id": sid,
            "records": len(recs),
            "latest": latest,
            "latest_score": latest.get("score"),
            "grade": grade,
            "grade_cn": grade_cn,
            "avg_score": C.round2(sum(scores) / len(scores)) if scores else None,
            "best_score": C.round2(max(scores)) if scores else None,
            "worst_score": C.round2(min(scores)) if scores else None,
            "trend": [C.round2(s) for s in scores],
        })

    all_scores = [float(r["score"]) for r in records if isinstance(r.get("score"), (int, float))]
    summary = {
        "records": len(records),
        "skills": len(skills),
        "avg_score": C.round2(sum(all_scores) / len(all_scores)) if all_scores else None,
        "best_score": C.round2(max(all_scores)) if all_scores else None,
        "worst_score": C.round2(min(all_scores)) if all_scores else None,
    }

    payload = {
        "schema_name": "skillmind-score-report",
        "schema_version": SCHEMA_VERSION,
        "generated_at": C.now_iso(),
        "store": C.relpath(path, root),
        "baseline_default": dict(DEFAULT_BASELINE),
        "weights": dict(WEIGHTS),
        "grade_bands": [
            {"min": low,
             "max": (100.0 if i == 0 else GRADE_BANDS[i - 1][0]),
             "grade": grade, "grade_cn": cn}
            for i, (low, grade, cn) in enumerate(GRADE_BANDS)
        ],
        "summary": summary,
        "skills": skills,
    }

    human = [
        C.banner("SkillMind Score — report"),
        "store     : %s" % payload["store"],
        "summary   : records=%s skills=%s avg=%s best=%s worst=%s"
        % (summary["records"], summary["skills"], summary["avg_score"],
           summary["best_score"], summary["worst_score"]),
        "",
        "分档: 95-100 生产级 | 90-94 强 | 80-89 可用待优化 | 70-79 上线前复查 | <70 重设计或禁用",
        "",
        "%-22s %6s %6s %6s %6s  %s" % ("skill_id", "n", "latest", "avg", "best", "grade"),
    ]
    for s in skills:
        human.append("%-22s %6d %6s %6s %6s  %s"
                     % (s["skill_id"], s["records"], s["latest_score"],
                        s["avg_score"], s["best_score"], s["grade_cn"]))
    if not skills:
        human.append("(无记录)")
    human.append("")
    human.append("最新记录的原始指标（禁只报分数）:")
    for s in skills:
        latest = s["latest"]
        human.append("  %s @ %s  score=%s" % (s["skill_id"], latest.get("recorded_at"),
                                             latest.get("score")))
        human.append("    metrics : %s" % json.dumps(latest.get("metrics") or {},
                                                    ensure_ascii=False, sort_keys=True))
        human.append("    baseline: %s  subscores: %s"
                     % (json.dumps(latest.get("baseline") or {}, ensure_ascii=False, sort_keys=True),
                        json.dumps(latest.get("subscores") or {}, ensure_ascii=False, sort_keys=True)))

    C.emit(payload, as_json=args.json, human=human)
    return EXIT_OK


# ────────────────────────────── CLI ──────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="score.py",
        description="SkillMind 评分引擎（spec-v2 §3.3 / §14.4）",
    )
    ap.add_argument("--root", default=None, help="仓根（默认 _common.repo_root()）")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="记录一次评分（追加到 scores.json）")
    rec.add_argument("--skill-id", required=True)
    rec.add_argument("--metrics-json", required=True, help="原始指标 JSON 对象")
    rec.add_argument("--baseline-json", default=None, help="对比基线 JSON 对象")
    rec.add_argument("--store", default=None, help="scores.json 路径（默认 <root>/.skillmind/scores.json）")
    rec.add_argument("--json", action="store_true")

    rep = sub.add_parser("report", help="汇总评分记录")
    rep.add_argument("--skill-id", default=None)
    rep.add_argument("--store", default=None)
    rep.add_argument("--json", action="store_true")
    return ap


def main(argv: Any = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help(sys.stderr)
        return EXIT_USAGE

    try:
        root = Path(args.root).expanduser().resolve() if args.root else C.repo_root()
    except OSError as exc:
        C.eprint("ERROR: 无法解析 --root: %s" % exc)
        return EXIT_USAGE

    try:
        if args.cmd == "record":
            return cmd_record(args, root)
        if args.cmd == "report":
            return cmd_report(args, root)
    except OSError as exc:
        C.eprint("ERROR: %s: %s" % (type(exc).__name__, exc))
        return EXIT_FAIL
    ap.print_help(sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
