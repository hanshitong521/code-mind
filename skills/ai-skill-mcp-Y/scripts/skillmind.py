#!/usr/bin/env python3
"""skillmind.py — SkillMind 统一 CLI 调度器（spec-v2 §14.1）。

设计原则：**调度器不重写业务**。
  - `registry build` → 转发 registry_build.py
  - `route`          → 转发 router.py
  - `score`          → 转发 score.py
  - `telemetry`      → 转发 telemetry.py
  - `manifest`       → 转发 manifest_validate.py
  - `selftest`       → 转发 selftest.py
  - `registry query` / `verify` / `audit` → 本文件实现（无独立子脚本）

所有子命令都支持同名参数直连，便于脚本化与 CI。
退出码：0 = 通过；1 = 校验失败 / 存在 DRIFT / 审计有 BLOCK；2 = 用法或环境错误。

只用标准库，裸 Python 3.9 可运行。
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2

PROG = "skillmind.py"

USAGE = """\
SkillMind Ultimate V2.0 — 技能运行层统一 CLI

  registry build    [--root R] [--out P] [--json]        建注册表
  registry query    [--tag T] [--status S] [--category C] [--min-score N] [--top N] [--json]
  route             --task "..." [--project-type T] [--risk R] [--complexity L0..L3]
                    [--top N] [--method rule+tag|embedding|llm] [--confirm-risk] [--json]
  score record      --skill-id ID --metrics-json '<json>' [--baseline-json '<json>'] [--store P]
  score report      [--skill-id ID] [--store P] [--json]
  telemetry append  --event-json '<json>' [--store P] [--no-redact]
  telemetry summary [--store P] [--strict] [--json]
  manifest validate [--path P] [--schema S] [--json]
  verify            [--root R] [--installed D] [--json]   三层漂移检测（原生，无需 PyYAML）
  audit             [--scope skill|mcp|agents|all] [--root R] [--out P] [--json]
  selftest          [--json]

子脚本可独立运行，参数同名。状态目录：<repo_root>/.skillmind/
详见 README.md 与 references/spec-v2.md §14。
"""


# ────────────────────────────── 工具 ──────────────────────────────

def _mod(name: str):
    return importlib.import_module(name)


def _root_of(explicit: str | None) -> Path:
    return Path(explicit).expanduser().resolve() if explicit else C.repo_root()


def _registry_path(root: Path, explicit: str | None) -> Path:
    return Path(explicit).expanduser().resolve() if explicit else C.state_dir(root) / "registry.json"


def _load_registry(root: Path, explicit: str | None) -> tuple[dict | None, Path]:
    path = _registry_path(root, explicit)
    data = C.load_json(path, default=None)
    if isinstance(data, dict) and isinstance(data.get("skills"), list):
        return data, path
    return None, path


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


# ────────────────────────────── registry query ──────────────────────────────

def cmd_registry_query(args: list[str]) -> int:
    ap = argparse.ArgumentParser(prog=f"{PROG} registry query", description="查询 SkillMind 注册表")
    ap.add_argument("--root", default=None)
    ap.add_argument("--registry", default=None)
    ap.add_argument("--tag", action="append", default=[], help="按标签过滤（可重复；任一命中）")
    ap.add_argument("--status", default=None)
    ap.add_argument("--category", default=None)
    ap.add_argument("--min-score", type=float, default=None)
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(args)

    root = _root_of(a.root)
    data, path = _load_registry(root, a.registry)
    if data is None:
        C.eprint(f"ERROR: 注册表不可用: {path}\n  请先运行: {PROG} registry build")
        return EXIT_USAGE

    want_tags = {t.strip().lower() for t in a.tag if t.strip()}
    rows = list(data["skills"])
    if want_tags:
        rows = [r for r in rows
                if want_tags & {str(x).lower() for x in (r.get("tags") or [])}]
    if a.status:
        rows = [r for r in rows if str(r.get("status")) == a.status]
    if a.category:
        rows = [r for r in rows if str(r.get("category")) == a.category]
    if a.min_score is not None:
        rows = [r for r in rows if (_num(r.get("score")) or -1) >= a.min_score]
    if a.top > 0:
        rows = rows[:a.top]

    payload = {
        "schema_name": "skillmind-registry-query",
        "schema_version": C.SCHEMA_VERSION,
        "registry": C.relpath(path, root),
        "registry_generated_at": data.get("generated_at"),
        "filters": {"tag": sorted(want_tags), "status": a.status,
                    "category": a.category, "min_score": a.min_score, "top": a.top},
        "count": len(rows),
        "skills": [{k: r.get(k) for k in
                    ("skill_id", "name", "category", "status", "score", "load_mode",
                     "risk", "bundled", "root_lines", "tags")} for r in rows],
    }
    lines = [C.banner("SkillMind Registry Query"),
             f"registry : {payload['registry']}  count={payload['count']}"]
    for r in payload["skills"]:
        lines.append(f"  {r['skill_id']:<20} {str(r.get('category')):<11} "
                     f"{str(r.get('status')):<10} score={r.get('score')} "
                     f"tags={','.join(r.get('tags') or [])}")
    if not payload["skills"]:
        lines.append("  (无匹配)")
    C.emit(payload, as_json=a.json, human=lines)
    return EXIT_OK


# ────────────────────────────── verify（原生三层漂移） ──────────────────────────────

PASS, DRIFT, MISSING, UNTRACKED = "PASS", "DRIFT", "MISSING", "UNTRACKED"


def cmd_verify(args: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog=f"{PROG} verify",
        description="三层漂移检测（canonical → release → installed）。"
                    "与 scripts/verify_skill_drift.py 同语义，但零依赖（原生 hash_tree）。")
    ap.add_argument("--root", default=None)
    ap.add_argument("--installed", default=None, help="业务仓 .cursor/skills 目录")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(args)

    root = _root_of(a.root)
    manifest = C.try_load_yaml(root / C.CONTROL_PLANE["release_manifest"]) or {}
    exclude = C.manifest_exclude(root)
    installed = Path(a.installed).expanduser().resolve() if a.installed else None

    findings: list[dict] = []
    declared: set[str] = set()

    for name, spec in (manifest.get("skills") or {}).items():
        if not isinstance(spec, dict):
            continue
        rel = spec.get("artifact_path")
        if not rel:
            findings.append({"skill": name, "layer": "manifest", "verdict": MISSING,
                             "path": "-", "detail": "manifest 缺 artifact_path"})
            continue
        declared.add(rel)
        artifact = root / rel
        if not artifact.exists():
            findings.append({"skill": name, "layer": "release", "verdict": MISSING,
                             "path": rel, "detail": "artifact_path 不存在"})
            continue

        actual = C.hash_tree(artifact, exclude=exclude)["content_hash"]
        recorded = spec.get("content_hash")
        if spec.get("status") == "CANONICAL_LOCAL":
            if recorded is None:
                findings.append({"skill": name, "layer": "canonical_vs_release",
                                 "verdict": UNTRACKED, "path": rel,
                                 "detail": "manifest 未记录 content_hash（先跑 build_release.py）"})
            elif recorded != actual:
                findings.append({"skill": name, "layer": "canonical_vs_release",
                                 "verdict": DRIFT, "path": rel,
                                 "detail": f"记录 {recorded} != 实际 {actual}"})
            else:
                findings.append({"skill": name, "layer": "canonical_vs_release",
                                 "verdict": PASS, "path": rel, "detail": "canonical == release"})
        else:
            findings.append({"skill": name, "layer": "canonical_vs_release",
                             "verdict": PASS, "path": rel,
                             "detail": f"release hash 记录一致（{spec.get('status')}，"
                                       f"外部 canonical 比对需 --canonical-root）"
                                       if recorded == actual else
                                       f"release 记录 {recorded} != 实际 {actual}"})

        if installed:
            inst = installed / name
            if not inst.exists():
                findings.append({"skill": name, "layer": "release_vs_installed",
                                 "verdict": MISSING, "path": str(inst), "detail": "未安装"})
            else:
                ih = C.hash_tree(inst, exclude=exclude)["content_hash"]
                findings.append({"skill": name, "layer": "release_vs_installed",
                                 "verdict": PASS if ih == actual else DRIFT,
                                 "path": str(inst),
                                 "detail": "release == installed" if ih == actual
                                           else f"release {actual} != installed {ih}"})

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        for d in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            if f"skills/{d.name}" not in declared:
                findings.append({"skill": d.name, "layer": "manifest", "verdict": UNTRACKED,
                                 "path": f"skills/{d.name}",
                                 "detail": "磁盘存在但 release-manifest 未声明"})

    summary = {v: sum(1 for f in findings if f["verdict"] == v)
               for v in (PASS, DRIFT, MISSING, UNTRACKED)}
    ok = summary[DRIFT] == 0 and summary[MISSING] == 0
    payload = {"schema_name": "skillmind-verify", "schema_version": C.SCHEMA_VERSION,
               "root": str(root), "hash_semantics": "与 scripts/_release_lib.py 逐字节等价",
               "findings": findings, "summary": summary, "ok": ok}

    lines = [C.banner("SkillMind Verify — 三层漂移")]
    for f in findings:
        lines.append(f"[{f['verdict']:<9}] {f['skill']:<18} {f['layer']:<22} {f['detail']}")
    lines.append("")
    lines.append(f"PASS={summary[PASS]} DRIFT={summary[DRIFT]} "
                 f"MISSING={summary[MISSING]} UNTRACKED={summary[UNTRACKED]}")
    if not ok:
        lines.append("")
        lines.append("DRIFT/MISSING 不允许静默覆盖。可选：更新发布副本(build_release.py) / "
                     "回滚安装副本 / supersede canonical。")
    C.emit(payload, as_json=a.json, human=lines)
    return EXIT_OK if ok else EXIT_FAIL


# ────────────────────────────── audit（V1 工作流的 V2 机械化） ──────────────────────────────

ROOT_LINES_HOT = 200      # 高频常驻入口预算
ROOT_LINES_WARN = 500     # 普通根文档预算
ROOT_LINES_SPLIT = 800    # 强制审视拆分
DESC_LEN_WARN = 400       # description 写满工作流的迹象


def _audit_skill(root: Path, s: dict) -> list[dict]:
    """单技能机械检查 → findings。"""
    out: list[dict] = []
    sid = str(s.get("skill_id"))
    rel = str(s.get("path") or f"skills/{sid}/SKILL.md")
    lines = int(s.get("root_lines") or 0)
    mode = str(s.get("load_mode") or "")
    trig = s.get("triggers") if isinstance(s.get("triggers"), dict) else {}
    inc = list(trig.get("include") or [])
    exc = list(trig.get("exclude") or [])
    desc = str(s.get("description") or "")

    def add(issue: str, action: str, risk: str, verify: str) -> None:
        out.append({"skill": sid, "resource": rel, "issue": issue,
                    "action": action, "risk": risk, "verify": verify})

    if str(s.get("status")) == "blocked":
        add("status=blocked：安全/合规一票否决", "BLOCK", "high", "人工解除后才可再入池")
    if str(s.get("status")) == "deprecated":
        add("status=deprecated：已退役（低频≠可删，须确认无灾备/事故场景）",
            "DISABLE-CANDIDATE", "low", "确认无 P0 场景后 90 天再评估删除")
    if lines > ROOT_LINES_SPLIT:
        add(f"根 SKILL.md {lines} 行 > {ROOT_LINES_SPLIT}：破坏渐进式披露",
            "SPLIT", "medium", "拆 references/ 并写清命中路由；复跑 trigger 四类")
    elif lines > ROOT_LINES_WARN:
        add(f"根 SKILL.md {lines} 行 > {ROOT_LINES_WARN}：审视可否外移",
            "OPTIMIZE", "low", "外移后确认 Recall 未下降")
    if mode == "always" and lines > ROOT_LINES_HOT:
        add(f"常驻(always)且 {lines} 行 > {ROOT_LINES_HOT}：每轮都付 token",
            "LAZY-LOAD", "medium", "改 on-demand 或拆 L0 摘要；对比常驻成本")
    if len(desc) > DESC_LEN_WARN:
        add(f"description {len(desc)} 字过长：疑似写完整工作流",
            "OPTIMIZE", "medium", "压成「Use when … / Not for …」两段")
    if not inc:
        add("triggers.include 为空：Recall 风险（该用找不到）",
            "OPTIMIZE", "high", "补正向触发词后跑 4P 用例")
    if not exc:
        add("triggers.exclude 为空：Precision 风险（易误触发）",
            "OPTIMIZE", "medium", "补否定邻域后跑 3N 用例")
    if not (root / f"skills/{sid}/skill.yaml").exists():
        add("缺 skill.yaml：无统一元数据，路由/预算拿不到成本与风险声明",
            "OPTIMIZE", "medium", "按 templates/skill-skeleton/skill.yaml 补，并过 manifest validate")
    broken = [r for r in (s.get("refs") or []) if not (root / f"skills/{sid}" / r).exists()]
    if broken:
        add(f"refs 断链 {len(broken)} 条：{', '.join(broken[:3])}",
            "OPTIMIZE", "medium", "修路径或删引用（禁留死链）")
    return out


def _audit_agents(root: Path, rules: list) -> list[dict]:
    out: list[dict] = []
    total = sum(int(r.get("lines") or 0) for r in rules)
    for r in rules:
        out.append({"skill": "(agents)", "resource": r.get("path"),
                    "issue": f"alwaysApply:true 常驻规则 {r.get('lines')} 行",
                    "action": "LAZY-LOAD" if int(r.get("lines") or 0) > 50 else "KEEP",
                    "risk": "medium" if int(r.get("lines") or 0) > 50 else "low",
                    "verify": "常驻规则只留模型猜不到的事实；其余改 globs 或 skill"})
    for name in ("AGENTS.md", "CLAUDE.md", ".cursorrules"):
        p = root / name
        if not p.exists():
            continue
        text = C.read_text(p)
        n = len(text.splitlines())
        hits = re.findall(r"(每次|必读|必须先读|always read|read before)", text)
        out.append({"skill": "(agents)", "resource": name,
                    "issue": f"{name} {n} 行；命中「必读清单」措辞 {len(hits)} 处",
                    "action": "OPTIMIZE" if hits else ("LAZY-LOAD" if n > 200 else "KEEP"),
                    "risk": "medium" if hits else "low",
                    "verify": "必读清单 → 导航地图（场景→文件，否则不加载）"})
    if not rules:
        out.append({"skill": "(agents)", "resource": "-",
                    "issue": "未发现 alwaysApply:true 规则（常驻 token 成本为 0）",
                    "action": "KEEP", "risk": "low", "verify": "-"})
    return out


def _audit_mcp(root: Path, reg: dict) -> list[dict]:
    out: list[dict] = []
    mcps = reg.get("mcps") or []
    cp = C.load_control_plane(root).get("capability_registry") or {}
    budget = ((cp.get("tool_budget") or {}).get("default_max_tools_per_phase")
              if isinstance(cp, dict) else None)
    if not mcps:
        out.append({"skill": "(mcp)", "resource": "-",
                    "issue": "仓库无 MCP 清单：无法审计 tool 暴露与 standing 白名单",
                    "action": "KEEP", "risk": "low",
                    "verify": "接入 MCP 时补 shared/mcp-registry.yaml 后重跑"})
    for m in mcps:
        tools = int(m.get("tools") or 0)
        standing = bool(m.get("standing"))
        issue = f"{m.get('name')}: tools={tools} standing={standing}"
        action = "OPTIMIZE" if (standing or (budget and tools > int(budget))) else "KEEP"
        out.append({"skill": "(mcp)", "resource": str(m.get("name")), "issue": issue,
                    "action": action, "risk": "medium" if action == "OPTIMIZE" else "low",
                    "verify": f"单阶段暴露上限 capability-registry.tool_budget={budget}；"
                              f"standing 白名单写进 AGENTS/L0"})
    return out


def cmd_audit(args: list[str]) -> int:
    ap = argparse.ArgumentParser(prog=f"{PROG} audit",
                                 description="Skill/MCP/AGENTS 机械审计（V1 工作流的 V2 落地）")
    ap.add_argument("--scope", default="all", choices=("skill", "mcp", "agents", "all"))
    ap.add_argument("--root", default=None)
    ap.add_argument("--registry", default=None)
    ap.add_argument("--out", default=None, help="把 Markdown 报告写到文件")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(args)

    root = _root_of(a.root)
    reg, path = _load_registry(root, a.registry)
    if reg is None:
        C.eprint(f"ERROR: 注册表不可用: {path}\n  请先运行: {PROG} registry build")
        return EXIT_USAGE

    findings: list[dict] = []
    if a.scope in ("skill", "all"):
        for s in reg.get("skills") or []:
            findings.extend(_audit_skill(root, s))
    if a.scope in ("agents", "all"):
        findings.extend(_audit_agents(root, reg.get("rules") or []))
    if a.scope in ("mcp", "all"):
        findings.extend(_audit_mcp(root, reg))

    for o in reg.get("overlap") or []:
        if o.get("severity") == "warn":
            findings.append({"skill": f"{o['a']}~{o['b']}", "resource": "overlap",
                             "issue": f"标签高度重叠: {o.get('shared_tags')}",
                             "action": "MERGE", "risk": "medium",
                             "verify": "留一个 SSOT；输家 description 改 Deprecated 指向赢家"})

    blocked = [f for f in findings if f["action"] == "BLOCK"]
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["action"]] = counts.get(f["action"], 0) + 1
    # verdict 只由**可执行动作**决定。KEEP 是「无需动作」的结论，若当 findings 计入，
    # 审计永远报 OPTIMIZE（报警失效 = 等于没有报警）。
    actionable = [f for f in findings if f["action"] != "KEEP"]
    verdict = "BLOCK" if blocked else ("OPTIMIZE" if actionable else "PASS")

    payload = {"schema_name": "skillmind-audit", "schema_version": C.SCHEMA_VERSION,
               "generated_at": C.now_iso(), "root": str(root), "scope": a.scope,
               "verdict": verdict, "counts": counts, "findings": findings,
               "actionable": len(actionable),
               "note": "机械检查只覆盖可判定项；语义问题仍须按 references/apply.md 人工判断。"}

    md = [f"# SkillMind Audit — {a.scope}", "",
          f"Root: {C.relpath(root)} ｜ Verdict: **{verdict}** ｜ Findings: {len(findings)}", "",
          "| action | 数量 |", "|---|---:|"]
    for k in sorted(counts):
        md.append(f"| {k} | {counts[k]} |")
    md += ["", "| 资源 | 问题 | 动作 | 风险 | 验证 |", "|---|---|---|---|---|"]
    for f in findings:
        md.append(f"| {f['resource']} | {f['issue']} | {f['action']} | {f['risk']} | {f['verify']} |")
    md += ["", "Trigger: [ ]P [ ]N [ ]B [ ]C", "",
           "Rollback: 改前 git ref", "",
           "禁: 只有压缩率数字；禁: 自动删除低频高价值 Skill。"]
    report = "\n".join(md) + "\n"

    if a.out:
        C.write_text(Path(a.out).expanduser().resolve(), report)

    lines = [C.banner(f"SkillMind Audit — {a.scope}"),
             f"verdict={verdict}  findings={len(findings)}  counts={counts}"]
    for f in findings:
        lines.append(f"  [{f['action']:<18}] {f['resource']:<26} {f['issue']}")
    if a.out:
        lines.append(f"\n报告已写入: {a.out}")
    C.emit(payload, as_json=a.json, human=lines)
    return EXIT_FAIL if blocked else EXIT_OK


# ────────────────────────────── 调度 ──────────────────────────────

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(USAGE)
        return EXIT_USAGE
    if argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return EXIT_OK

    cmd, rest = argv[0], argv[1:]
    sub = rest[0] if rest and not rest[0].startswith("-") else ""

    try:
        if cmd == "registry":
            if sub == "build":
                return _mod("registry_build").main(rest[1:])
            if sub == "query":
                return cmd_registry_query(rest[1:])
            C.eprint(f"ERROR: 未知子命令 registry {sub or '(空)'}；可选 build | query")
            return EXIT_USAGE
        if cmd == "route":
            return _mod("router").main(rest)
        if cmd == "score":
            return _mod("score").main(rest)
        if cmd == "telemetry":
            return _mod("telemetry").main(rest)
        if cmd == "manifest":
            if sub == "validate":
                return _mod("manifest_validate").main(rest[1:])
            C.eprint("ERROR: 未知子命令 manifest；可选 validate")
            return EXIT_USAGE
        if cmd == "verify":
            return cmd_verify(rest)
        if cmd == "audit":
            return cmd_audit(rest)
        if cmd == "selftest":
            return _mod("selftest").main(rest)
    except ImportError as exc:
        C.eprint(f"ERROR: 子模块加载失败（{exc}）。请确认 scripts/ 完整。")
        return EXIT_USAGE
    except SystemExit as exc:  # argparse 在子模块里退出
        return int(exc.code or 0)

    C.eprint(f"ERROR: 未知命令 '{cmd}'\n\n{USAGE}")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
