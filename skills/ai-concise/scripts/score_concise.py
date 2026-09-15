#!/usr/bin/env python3
"""concise-mind 评测打分器 v4（零第三方依赖）。

    python scripts/score_concise.py --runs evals/runs.json
    python scripts/score_concise.py --runs evals/runs.json --evals evals.json --out reports

判分口径（SSOT）：
  - 全局禁词/禁形：references/filler-blacklist.md 中的 ```regex``` 块
  - 用例断言：evals.json 的 check 段
  - Preservation Gate 字段字典：本文件 FIELDS（与 schemas/must-preserve.yaml 对齐）

维度（v4）：filler / accuracy / fidelity / preserve / brevity / adapt / discipline / stick
  - accuracy 权重最高：宁可不简洁，不可不准确
  - fidelity = 承重事实保真（must_keep 覆盖 ∧ 反压门），与 preserve（字段在不在）互补
  - discipline = 格式纯净度（空段/重复行/标题跳级/行尾空白/尾随装饰/首行铺垫/末行缺下一步）
  - brevity 追加 max_list_items（可见列表 ≤5，见 references/reader-first.md）

v5 新增 check key（用例不声明则不计入，旧用例分母不变）：
  first_line_forbid_regex → discipline · last_line_regex → discipline · max_list_items → brevity
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WEIGHTS = {"filler": 2.0, "accuracy": 2.5, "fidelity": 2.0,
           "preserve": 1.5, "brevity": 1.5, "adapt": 1.5,
           "discipline": 1.0, "stick": 1.5}
DIMS = list(WEIGHTS)

# 可识别的文件扩展名（must_paths / 承重行判定共用，保持一处定义）
FILE_EXT = (r"(java|kt|cs|cpp|c|h|go|rs|rb|php|py|ts|tsx|js|jsx|vue|mjs|json|"
            r"ya?ml|md|xml|sql|sh|ps1|bat|txt|log|conf|ini|toml|properties|gradle|jar)")

FIELDS = {
    "decision": r"decision|决策|决定|结论|方案是|选中|采用|改用|改为|换成|改成|做法|改法|建议|按.{0,8}(做|走)",
    "constraint": r"constraint|约束|限制|前提|不能|不可行|需先|必须|仅当|只在",
    "evidence": r"evidence|证据|依据|实测|跑了|跑出|日志|输出|截图|命令|复现|显示",
    "risk": r"risk|风险|回滚|可能失败|隐患|影响面|代价|副作用",
    "verification": r"verification|验证|已验证|未验证|待验证|自测|测试|复跑|怎么验",
}


# ── 读取黑名单 SSOT ────────────────────────────────────────────────
def load_global_forbidden(blacklist_md: Path) -> dict[str, list[str]]:
    text = blacklist_md.read_text(encoding="utf-8") if blacklist_md.exists() else ""
    blocks = re.findall(r"```regex\n(.*?)```", text, flags=re.S)
    phrases = [ln.strip() for ln in (blocks[0] if len(blocks) > 0 else "").splitlines() if ln.strip()]
    shapes = [ln.strip() for ln in (blocks[1] if len(blocks) > 1 else "").splitlines() if ln.strip()]
    return {"phrases": phrases, "shapes": shapes}


def re_hits(patterns: list[str], text: str) -> list[str]:
    hits = []
    for p in patterns:
        try:
            if re.search(p, text, flags=re.M):
                hits.append(p)
        except re.error:
            hits.append(f"<bad-regex:{p}>")
    return hits


def re_found(patterns: list[str], text: str) -> tuple[int, int]:
    if not patterns:
        return 0, 0
    got = sum(1 for p in patterns if re.search(p, text, flags=re.M))
    return got, len(patterns)


def fact_density(text: str) -> float:
    """DOC 用：承重行占比（含数字/路径/命令/表格/文件名的行）。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0.0
    factual = sum(1 for ln in lines
                  if re.search(r"\d|/|`|\||\." + FILE_EXT, ln))
    return factual / len(lines)


def count_lines(text: str) -> int:
    return len([ln for ln in text.splitlines() if ln.strip()])


LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")


def count_list_items(text: str) -> int:
    """可见列表项数（`- x` / `1. x`）。表格与代码块不计。"""
    return sum(1 for ln in text.splitlines() if LIST_ITEM.match(ln))


def first_line(text: str) -> str:
    ls = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return ls[0] if ls else ""


def last_line(text: str) -> str:
    ls = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return ls[-1] if ls else ""


LABEL_LINE = re.compile(r"^(决策|目标|约束|证据|风险|验证|回滚|判据|涉及文件|步骤)[:：]")


def count_sentences(text: str) -> int:
    """中文分号「；」是分句不是句末，不计句数。

    标签行（`决策：`/`风险：` 等）是格式约定，各算一行，其内部句号不计入句数 —— 
    否则「3 行标签短答」会被误判成 4 句超预算。
    """
    body = "\n".join(ln.strip() for ln in text.splitlines()
                     if ln.strip() and not LABEL_LINE.match(ln.strip()))
    punct = len(re.findall(r"[。！？!?]|\.\s", body))
    return max(punct, count_lines(text))


# ── discipline：格式纯净度 ─────────────────────────────────────────
DISC_LABEL = {
    "blank_run": "连续空段", "dup_line": "重复行", "heading_skip": "标题跳级",
    "trailing_ws": "行尾空白", "tail_decoration": "尾随装饰",
    "first_line_announce": "首行铺垫", "last_line_next": "末行缺下一步",
}


def discipline_score(text: str, chk: dict | None = None) -> tuple[float, list[str]]:
    """基础五个 0/1 检查 + 用例声明的 v5 形状门，取平均。返回 (分数, 违规列表)。"""
    checks: list[tuple[str, bool]] = []

    # 1) 无连续空段（3+ 行）
    checks.append(("blank_run", not re.search(r"\n[ \t]*\n[ \t]*\n", text)))

    # 2) 无重复非空行（>=12 字符完全相同）—— 同义反复的信号
    seen, dup = set(), False
    for ln in text.splitlines():
        s = ln.strip()
        if len(s) >= 12:
            if s in seen:
                dup = True
            seen.add(s)
    checks.append(("dup_line", not dup))

    # 3) 标题层级不跳级（h1 → h3 算跳）
    levels = [len(m.group(1)) for m in re.finditer(r"^(#{1,6})\s", text, flags=re.M)]
    ok = True
    for a, b in zip(levels, levels[1:]):
        if b > a + 1:
            ok = False
    checks.append(("heading_skip", ok))

    # 4) 无行尾空白
    checks.append(("trailing_ws", not re.search(r"[ \t]+$", text, flags=re.M)))

    # 5) 无尾随装饰行（正文以水平线结尾）
    tail = [ln for ln in text.splitlines() if ln.strip()]
    checks.append(("tail_decoration", not (tail and re.match(r"^\s*[-—=*_]{3,}\s*$", tail[-1]))))

    # 6/7) v5 形状门 —— 仅用例声明时计入，旧用例分母不变（见 references/reader-first.md）
    chk = chk or {}
    fl_forbid = chk.get("first_line_forbid_regex", [])
    if fl_forbid:
        checks.append(("first_line_announce", not re_hits(fl_forbid, first_line(text))))
    ll_need = chk.get("last_line_regex", [])
    if ll_need:
        checks.append(("last_line_next", bool(re_hits(ll_need, last_line(text)))))

    bad = [name for name, passed in checks if not passed]
    return (100.0 * (len(checks) - len(bad)) / len(checks), bad)


# ── 单条评分 ───────────────────────────────────────────────────────
def score_one(case: dict, output: str, gforb: dict) -> dict:
    chk = case.get("check", {}) or {}
    det: dict[str, object] = {}

    # 1) filler —— 命中一次即 0（套话 + 结构性水是最贵的失败）
    f_hits = re_hits(gforb["phrases"], output) + re_hits(gforb["shapes"], output)
    f_hits += re_hits(chk.get("forbidden_shapes", []), output)
    det["filler_hits"] = f_hits
    filler = 0.0 if f_hits else 100.0

    # 2) brevity —— 上限预算
    ratios = []
    if "max_chars" in chk:
        n = len(output)
        det["chars"] = n
        ratios.append(1.0 if n <= chk["max_chars"] else chk["max_chars"] / max(n, 1))
    if "max_lines" in chk:
        n = count_lines(output)
        det["lines"] = n
        ratios.append(1.0 if n <= chk["max_lines"] else chk["max_lines"] / max(n, 1))
    if "max_sentences" in chk:
        n = count_sentences(output)
        det["sentences"] = n
        ratios.append(1.0 if n <= chk["max_sentences"] else chk["max_sentences"] / max(n, 1))
    if "max_list_items" in chk:
        n = count_list_items(output)
        det["list_items"] = n
        over = n > chk["max_list_items"]
        if over:
            det["list_over"] = n
        ratios.append(1.0 if not over else chk["max_list_items"] / max(n, 1))
    brevity = 100.0 * min(ratios) if ratios else 100.0

    # 3) preserve —— Gate 字段
    req = chk.get("require_fields", [])
    got_fields = [f for f in req if re.search(FIELDS[f], output)]
    det["fields_missing"] = [f for f in req if f not in got_fields]
    preserve = 100.0 * len(got_fields) / len(req) if req else 100.0

    # 4) accuracy —— 硬禁 + 关键点覆盖（权重最高）
    a_forb = re_hits(chk.get("forbidden_regex", []), output)
    det["accuracy_forbidden"] = a_forb
    got, total = re_found(chk.get("must_regex", []), output)
    det["must_regex"] = f"{got}/{total}" if total else "n/a"
    cover = (got / total * 100.0) if total else 100.0
    accuracy = 0.0 if a_forb else cover

    # 5) fidelity —— 承重事实保真（must_keep 覆盖 ∧ 反压门）
    fid_parts: list[float] = []
    keep = chk.get("must_keep", [])
    kgot, ktot = re_found(keep, output)
    if ktot:
        det["must_keep"] = f"{kgot}/{ktot}"
        missing = [p for p in keep if not re.search(p, output, flags=re.M)]
        det["must_keep_missing"] = missing
        fid_parts.append(kgot / ktot)
    if "min_chars" in chk:
        floor = chk["min_chars"] * 0.6
        n = len(output)
        det["fidelity_floor"] = int(floor)
        fid_parts.append(1.0 if n >= floor else n / floor)
    fidelity = 100.0 * min(fid_parts) if fid_parts else 100.0

    # 6) adapt —— 模式该保留的形状
    shape_checks = []
    if "min_chars" in chk:
        n = len(output)
        det["chars"] = n
        shape_checks.append(1.0 if n >= chk["min_chars"] else n / max(chk["min_chars"], 1))
    if chk.get("must_numbers"):
        shape_checks.append(1.0 if re.search(r"\d", output) else 0.0)
    if chk.get("must_paths"):
        shape_checks.append(1.0 if re.search(r"[\w./\\-]+\." + FILE_EXT, output) else 0.0)
    if "min_density" in chk:
        d = fact_density(output)
        det["density"] = round(d, 3)
        shape_checks.append(1.0 if d >= chk["min_density"] else d / max(chk["min_density"], 0.001))
    adapt = 100.0 * (sum(shape_checks) / len(shape_checks)) if shape_checks else 100.0

    # 7) discipline —— 格式纯净度
    disc, disc_bad = discipline_score(output, chk)
    det["discipline_bad"] = disc_bad
    discipline = disc

    # 8) stick —— 无触发词也必须仍是「模式正确 + 压缩 + 保真」的产出
    if case.get("sticky"):
        stick = 100.0 if (filler == 100.0 and accuracy >= 80.0 and adapt >= 80.0
                          and preserve >= 60.0 and fidelity >= 80.0) else 0.0
    else:
        stick = 100.0
    det["stick_basis"] = "sticky-case" if case.get("sticky") else "n/a"
    det["sticky_case"] = bool(case.get("sticky"))

    dims = {"filler": filler, "accuracy": accuracy, "fidelity": fidelity,
            "preserve": preserve, "brevity": brevity, "adapt": adapt,
            "discipline": discipline, "stick": stick}
    total = sum(dims[d] * WEIGHTS[d] for d in DIMS) / sum(WEIGHTS.values())
    return {"dims": dims, "total": round(total, 1), "detail": det}


# ── 报告 ───────────────────────────────────────────────────────────
def render_md(evals: dict, runs: dict, result: dict) -> str:
    cases = {c["id"]: c for c in evals["cases"]}
    conds = [c for c in runs["conditions"].keys() if c != "PROBE"]
    L = []
    L.append("# Concise-mind 实测打分\n")
    L.append(f"生成时间：{result['generated_at']}　·　用例数：{len(cases)}　·　条件数：{len(conds)}　·　评分器 v5\n")
    L.append("## 条件说明\n")
    for k, v in runs["conditions"].items():
        L.append(f"- **{k}** — {v}")
    L.append("")

    L.append("## 总分\n")
    L.append("| 条件 | 总分 | " + " | ".join(DIMS) + " |")
    L.append("|---" * (2 + len(DIMS)) + "|")
    for c in conds:
        s = result["summary"][c]
        L.append(f"| {c} | **{s['total']}** | " + " | ".join(f"{s['dims'][d]:.0f}" for d in DIMS) + " |")
    L.append("")

    L.append("## 逐用例\n")
    L.append("| 用例 | Mode | sticky | " + " | ".join(conds) + " |")
    L.append("|---" * (3 + len(conds)) + "|")
    for cid, case in cases.items():
        row = [cid, case["mode"], "✓" if case.get("sticky") else ""]
        for c in conds:
            r = result["cases"].get(cid, {}).get(c)
            row.append(f"{r['total']:.0f}" if r else "-")
        L.append("| " + " | ".join(str(x) for x in row) + " |")
    L.append("")

    L.append("## 失败明细\n")
    any_fail = False
    for cid, case in cases.items():
        for c in conds:
            r = result["cases"].get(cid, {}).get(c)
            if not r:
                continue
            bad = []
            if r["dims"]["filler"] == 0:
                bad.append(f"套话/结构水命中 {r['detail']['filler_hits'][:3]}")
            if r["detail"].get("fields_missing"):
                bad.append(f"缺字段 {r['detail']['fields_missing']}")
            if r["detail"].get("accuracy_forbidden"):
                best = r["detail"]["accuracy_forbidden"][:2]
                bad.append(f"精度违规 {best}")
            if r["detail"].get("must_keep_missing"):
                bad.append(f"承重事实丢失 {r['detail']['must_keep_missing']}")
            if r["dims"]["fidelity"] < 80:
                bad.append(f"保真不足 {r['dims']['fidelity']:.0f}")
            if r["detail"].get("discipline_bad"):
                bad.append("格式 " + "/".join(DISC_LABEL.get(n, n) for n in r["detail"]["discipline_bad"]))
            if r["detail"].get("list_over"):
                bad.append(f"列表超上限（{r['detail']['list_over']} 项）")
            if r["dims"]["brevity"] < 80:
                bad.append(f"超预算 {r['detail'].get('chars') or r['detail'].get('lines') or r['detail'].get('sentences')}")
            if r["dims"]["stick"] == 0:
                bad.append("锁存失效（无触发词即放弃压缩，或保真不达标）")
            if bad:
                any_fail = True
                L.append(f"- **{cid} / {c}** — " + "；".join(bad))
    if not any_fail:
        L.append("- 无")
    L.append("")

    if result.get("doc_density"):
        L.append("## 文档承重行占比（DOC 模式）\n")
        L.append("含数字/路径/命令/表格的行 ÷ 非空行。越高说明文档里的事实密度越大。\n")
        L.append("| 用例 | " + " | ".join(conds) + " |")
        L.append("|---" * (1 + len(conds)) + "|")
        for cid, v in result["doc_density"].items():
            L.append(f"| {cid} | " + " | ".join(f"{v.get(c, 0) * 100:.0f}%" for c in conds) + " |")
        L.append("")

    L.append("## 锁存续命率（sticky 用例）\n")
    L.append("无触发词的后续消息里仍保持「压缩 + 保真」态的比例 —— 这是 v3 相对 v2 的核心差异。\n")
    L.append("| 条件 | 续命率 |")
    L.append("|---|---|")
    for c in conds:
        r = result["summary"][c].get("stick_rate")
        L.append(f"| {c} | {r:.0f}% |" if r is not None else f"| {c} | n/a |")
    L.append("")

    L.append("## 保真度（Fidelity Gate）\n")
    L.append("承重事实（命令/版本/端口/路径/前置条件）保留率 —— 防「为省字丢事实」。\n")
    L.append("| 条件 | 保真度 |")
    L.append("|---|---|")
    for c in conds:
        L.append(f"| {c} | {result['summary'][c]['dims']['fidelity']:.0f} |")
    L.append("")

    probes = result.get("probes", [])
    if probes:
        hit = sum(1 for p in probes if p["hit"])
        L.append("## 评分器灵敏度探针\n")
        L.append(f"人为植入缺陷输出，验证打分器能否检出。**检出率 {hit}/{len(probes)} = "
                 f"{hit / len(probes) * 100:.0f}%**\n")
        L.append("| 用例 | 植入缺陷维度 | 打分器给出 | 是否检出 |")
        L.append("|---|---|---|---|")
        for p in probes:
            L.append(f"| {p['id']} | {p['expect']} | {p['value']} | {'✓' if p['hit'] else '✗ 漏检'} |")
        L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--evals", default=str(root / "evals.json"))
    ap.add_argument("--runs", default=str(root / "evals" / "runs.json"))
    ap.add_argument("--blacklist", default=str(root / "references" / "filler-blacklist.md"))
    ap.add_argument("--out", default=str(root / "reports"))
    ap.add_argument("--tag", default="", help="输出文件名前缀，便于对比不同轮次")
    ap.add_argument("--extra-runs", nargs="*", default=[],
                    help="额外 runs 文件，仅取其 PROBE 探针段（用于主样本为盲测时补充灵敏度检验）")
    args = ap.parse_args(argv)

    evals = json.loads(Path(args.evals).read_text(encoding="utf-8"))
    runs = json.loads(Path(args.runs).read_text(encoding="utf-8"))
    gforb = load_global_forbidden(Path(args.blacklist))

    cases = {c["id"]: c for c in evals["cases"]}
    conds = [c for c in runs["conditions"].keys() if c != "PROBE"]

    result = {"cases": {}, "summary": {}, "doc_density": {}, "probes": [],
              "generated_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")}

    by_cond: dict[str, list] = {c: [] for c in conds}
    for run in runs["runs"]:
        cid, cond = run["id"], run["condition"]
        case = cases.get(cid)
        if not case:
            continue
        if cond == "PROBE":
            r = score_one(case, run.get("output", ""), gforb)
            exp = run.get("probe_expect", "")
            result["probes"].append({
                "id": cid, "expect": exp,
                "value": round(r["dims"].get(exp, -1), 1),
                "hit": r["dims"].get(exp, 100.0) < 100.0,
            })
            continue
        if cond not in by_cond:
            continue
        r = score_one(case, run.get("output", ""), gforb)
        r["chars"] = len(run.get("output", ""))
        result["cases"].setdefault(cid, {})[cond] = r
        by_cond[cond].append(r)

    for c in conds:
        rs = by_cond[c]
        if not rs:
            continue
        sticky_rs = [r for r in rs if r["detail"].get("sticky_case")]
        result["summary"][c] = {
            "total": round(sum(r["total"] for r in rs) / len(rs), 1),
            "dims": {d: round(sum(r["dims"][d] for r in rs) / len(rs), 1) for d in DIMS},
            "stick_rate": round(sum(r["dims"]["stick"] for r in sticky_rs) / max(len(sticky_rs), 1), 1),
            "n": len(rs),
        }

    for cid, case in cases.items():
        if case["mode"] != "DOC":
            continue
        entry = {}
        for c in conds:
            for run in runs["runs"]:
                if run["id"] == cid and run["condition"] == c:
                    entry[c] = round(fact_density(run.get("output", "")), 3)
        if entry:
            result["doc_density"][cid] = entry

    # 外挂探针：主样本（如盲测）不含 PROBE 时，从指定文件补入灵敏度检验
    for extra in args.extra_runs:
        ed = json.loads(Path(extra).read_text(encoding="utf-8"))
        for run in ed.get("runs", []):
            if run.get("condition") != "PROBE":
                continue
            case = cases.get(run["id"])
            if not case:
                continue
            r = score_one(case, run.get("output", ""), gforb)
            exp = run.get("probe_expect", "")
            result["probes"].append({
                "id": run["id"], "expect": exp,
                "value": round(r["dims"].get(exp, -1), 1),
                "hit": r["dims"].get(exp, 100.0) < 100.0,
            })

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = f"{args.tag}-" if args.tag else ""
    (outdir / f"{prefix}score-{stamp}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_md(evals, runs, result)
    (outdir / f"{prefix}score-{stamp}.md").write_text(md, encoding="utf-8")
    (outdir / f"{prefix}latest.md").write_text(md, encoding="utf-8")

    print(md)
    print(f"\n[saved] {outdir / f'{prefix}score-{stamp}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
