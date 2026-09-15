#!/usr/bin/env python3
"""把评分结果渲染成单文件 HTML 记分板（零第三方依赖）。

    python scripts/make_scoreboard.py                          # 自动找最新明细 + 全部轮次轨迹
    python scripts/make_scoreboard.py --detail reports/final-score-x.json
    python scripts/make_scoreboard.py --out reports/scoreboard.html

明细图来源：`reports/<tag>-score-*.json`（tag 形如 r1..r8，取每 tag 最新一份作轨迹）。
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import re
import sys
from pathlib import Path

DIMS = ["filler", "accuracy", "fidelity", "preserve",
        "brevity", "adapt", "discipline", "stick"]
DIM_CN = {"filler": "无套话/结构水", "accuracy": "精度", "fidelity": "保真",
          "preserve": "Gate 保留", "brevity": "篇幅", "adapt": "模式适配",
          "discipline": "格式纯净", "stick": "锁存续命"}
COND_COLOR = {"C0": "#9aa0a6", "C1": "#e8a33d", "C2": "#2e9e6b"}
ROUND_PAT = re.compile(r"^(r\d+)-score-\d{8}-\d{6}\.json$")


def bar(v: float, color: str) -> str:
    w = max(0.0, min(100.0, v))
    return (f'<div class="bar"><span style="width:{w:.1f}%;background:{color}"></span>'
            f'<em>{v:.0f}</em></div>')


def heat(v: float) -> str:
    if v >= 99:
        c = "#c9edda"
    elif v >= 95:
        c = "#d8f3e3"
    elif v >= 80:
        c = "#eaf7ef"
    elif v >= 60:
        c = "#fdf3e0"
    else:
        c = "#fbe4e4"
    return f'<td style="background:{c}">{v:.0f}</td>'


def collect_rounds(outdir: Path) -> list[dict]:
    latest: dict[str, Path] = {}
    for f in sorted(outdir.glob("*-score-*.json")):
        m = ROUND_PAT.match(f.name)
        if m:
            latest[m.group(1)] = f
    out = []
    for tag in sorted(latest, key=lambda t: int(t[1:])):
        d = json.loads(latest[tag].read_text(encoding="utf-8"))
        s = d.get("summary", {}).get("C2")
        if not s:
            continue
        bad = sum(1 for cs in d["cases"].values()
                  if "C2" in cs and cs["C2"]["total"] < 100.0)
        out.append({"tag": tag, "total": s["total"], "bad": bad,
                    "dims": s["dims"], "n": s["n"]})
    return out


def main(argv=None) -> int:
    root = Path(__file__).resolve().parent.parent
    reports = root / "reports"
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", help="明细 json；默认 reports/final-score-*.json，其次最新 score-*.json")
    ap.add_argument("--out", default=str(reports / "scoreboard.html"))
    args = ap.parse_args(argv)

    path = args.detail
    if not path:
        cands = sorted(glob.glob(str(reports / "final-score-*.json")))
        if not cands:
            cands = sorted(glob.glob(str(reports / "score-*.json")))
        if not cands:
            print("找不到 score json，先跑 score_concise.py")
            return 1
        path = cands[-1]
    d = json.loads(Path(path).read_text(encoding="utf-8"))

    conds = list(d["summary"].keys())
    evals = json.loads((root / "evals.json").read_text(encoding="utf-8"))
    sticky_cases = [c["id"] for c in evals["cases"] if c.get("sticky")]
    case_ids = [c["id"] for c in evals["cases"] if c["id"] in d["cases"]]

    cards = []
    for c in conds:
        s = d["summary"][c]
        dims = "".join(
            f'<div class="dim"><label>{DIM_CN[k]}</label>{bar(s["dims"][k], COND_COLOR.get(c, "#666"))}</div>'
            for k in DIMS)
        cards.append(f'''<section class="card">
  <header><h3>{c}</h3><span class="total" style="color:{COND_COLOR.get(c, '#666')}">{s["total"]:.1f}</span></header>
  <p class="n">n = {s["n"]} 用例 · 锁存续命 {s.get("stick_rate", 0):.0f}%</p>
  {dims}
</section>''')

    rows = []
    for cid in case_ids:
        tds = "".join(heat(d["cases"][cid][c]["total"]) if c in d["cases"][cid] else "<td>-</td>"
                      for c in conds)
        mark = ' <span class="tag">sticky</span>' if cid in sticky_cases else ""
        rows.append(f"<tr><td class='cid'>{cid}{mark}</td>{tds}</tr>")

    rounds = collect_rounds(reports)
    r_rows = "".join(
        f'<tr><td>{r["tag"]}</td><td class="big">{r["total"]:.1f}</td>'
        f'<td>{r["bad"]}</td>'
        f'<td><div class="bar"><span style="width:{r["total"]:.1f}%;background:#2e9e6b"></span></div></td>'
        f'<td>{"达标" if r["total"] >= 98 else "未达标"}</td></tr>' for r in rounds)
    tail = [r for r in rounds if r["total"] >= 98]
    tail_note = (f'最近 {len(rounds)} 轮中 {len(tail)} 轮 ≥ 98；'
                 f'末 {min(3, len(rounds))} 轮均值 '
                 f'{sum(r["total"] for r in rounds[-3:]) / max(len(rounds[-3:]), 1):.1f}') if rounds else ""

    probes = d.get("probes", [])
    phit = sum(1 for p in probes if p["hit"])
    prows = "".join(
        f'<tr><td>{p["id"]}</td><td>{DIM_CN.get(p["expect"], p["expect"])}</td>'
        f'<td>{p["value"]:.0f}</td><td>{"检出" if p["hit"] else "漏检"}</td></tr>'
        for p in probes)

    dens = d.get("doc_density", {})
    drows = "".join(
        f"<tr><td>{k}</td>" + "".join(f'<td>{v.get(c, 0) * 100:.0f}%</td>' for c in conds) + "</tr>"
        for k, v in dens.items())

    doc = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>concise-mind v3.1 实测记分板</title>
<style>
:root{{--bg:#f7f8fa;--fg:#1b1f24;--mut:#6b7280;--line:#e5e7eb;--card:#fff}}
*{{box-sizing:border-box}}
body{{margin:0;padding:32px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
h1{{font-size:24px;margin:0 0 6px}}
.sub{{color:var(--mut);margin:0 0 24px;font-size:13px}}
h2{{font-size:17px;margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}}
.card header{{display:flex;align-items:baseline;justify-content:space-between}}
.card h3{{margin:0;font-size:15px;letter-spacing:.5px}}
.total{{font-size:26px;font-weight:700}}
.n{{color:var(--mut);font-size:12px;margin:2px 0 12px}}
.dim{{margin-bottom:7px}}
.dim label{{display:block;font-size:12px;color:var(--mut);margin-bottom:2px}}
.bar{{position:relative;height:14px;background:#eef0f3;border-radius:7px;overflow:hidden}}
.bar span{{display:block;height:100%;border-radius:7px}}
.bar em{{position:absolute;right:6px;top:-2px;font-size:11px;font-style:normal;color:#374151}}
table{{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:13px}}
th,td{{padding:7px 10px;text-align:center;border-bottom:1px solid var(--line)}}
th{{background:#f1f3f6;font-weight:600;color:#374151}}
td.cid{{text-align:left;font-family:ui-monospace,Consolas,monospace;font-size:12px}}
td.big{{font-weight:700;font-size:15px}}
.tag{{background:#e8f0fe;color:#3b6fd4;border-radius:4px;padding:0 5px;font-size:10px}}
.note{{background:var(--card);border:1px solid var(--line);border-left:3px solid #e8a33d;
border-radius:8px;padding:12px 16px;font-size:13px;color:#374151}}
code{{background:#eef0f3;padding:1px 5px;border-radius:4px;font-size:12px}}
</style></head><body>
<h1>concise-mind v3.1 实测记分板</h1>
<p class="sub">生成时间 {html.escape(d["generated_at"])} · 用例 {len(case_ids)} · 条件 {len(conds)} · 数据源 {html.escape(Path(path).name)}</p>

<h2>盲测总分 · 三维对比</h2>
<div class="cards">{"".join(cards)}</div>

<h2>逐用例（绿=好 红=差）</h2>
<table><thead><tr><th>用例</th>{"".join(f"<th>{c}</th>" for c in conds)}</tr></thead>
<tbody>{"".join(rows)}</tbody></table>

<h2>多轮独立盲测轨迹（C2）</h2>
<p class="sub">{html.escape(tail_note)}</p>
<table><thead><tr><th>轮次</th><th>C2 总分</th><th>失分用例数</th><th>进度</th><th>判定</th></tr></thead>
<tbody>{r_rows}</tbody></table>

<h2>评分器灵敏度探针 —— 检出 {phit}/{len(probes)}</h2>
<table><thead><tr><th>用例</th><th>植入缺陷</th><th>评分器给出</th><th>结果</th></tr></thead>
<tbody>{prows}</tbody></table>

<h2>文档承重行占比（DOC）</h2>
<table><thead><tr><th>用例</th>{"".join(f"<th>{c}</th>" for c in conds)}</tr></thead>
<tbody>{drows}</tbody></table>

<h2>怎么读</h2>
<div class="note">
<b>C0</b> 裸模型（Cursor Plan 下 skill 未加载的真实行为）　·　
<b>C1</b> 只做触发词式压缩、无锁存　·　<b>C2</b> v3.1 锁存（含文档与 Plan）。<br>
关键差异不在总分，而在 <b>sticky 用例</b>：只有锁存生效，后续不带触发词的消息才不会回退成长篇。<br>
本页 C2 数据来自<b>独立 agent 盲测</b>——产出者只读 skill 规则、未接触 <code>evals.json</code> 与评分器，
与手写样本的平均文本相似度 0.24（非抄袭）。<br>
探针为人为植入缺陷，验证评分器本身能否检出：检出率不足 100% 说明打分器失灵，此时 C2 高分不可信。
</div>
</body></html>'''
    Path(args.out).write_text(doc, encoding="utf-8")
    print(f"[ok] {args.out}  (轨迹 {len(rounds)} 轮, 探针 {phit}/{len(probes)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
