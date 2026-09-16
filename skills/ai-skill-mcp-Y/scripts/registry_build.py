#!/usr/bin/env python3
"""registry_build.py — 机械生成 SkillMind 注册表（spec-v2 §3.1 / §11 / §14.2）。

职责：
  - 扫描 <root>/skills/*/SKILL.md，解析 frontmatter（name/description/version/
    disable-model-invocation），统计 root_lines / root_words，列 references/ 为 refs
  - 复用 _common.derive_tags / derive_triggers 生成 tags / triggers
  - 复用 _common.hash_tree（+ manifest_exclude）计算 hash，与仓控制面逐字节等价
  - 只读消费控制面：release-manifest / capability-registry / deploy.bundle /
    schema-versions（禁反向改写）
  - 扫描 .cursor/rules/**/*.mdc 的 alwaysApply:true 常驻规则
  - 计算 skill 间 overlap（标签交集 ≥2 或 description 关键词交叉）

用法：
  python3 scripts/registry_build.py [--root R] [--out P] [--json]

退出码：0 = 生成成功；2 = 用法或环境错误。
状态目录：默认 <root>/.skillmind/registry.json。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCHEMA_NAME = "skillmind-registry"

#: 目录名 → category 推断表（spec-v2 §3.1）；未知一律 governance。
CATEGORY_BY_SKILL = {
    "ai-code": "backend",
    "ai-design": "docs",
    "ai-requirement": "governance",
    "ai-concise": "docs",
    "ai-codeHealthMind": "test",
    "ai-skill-mcp-Y": "governance",
}
DEFAULT_CATEGORY = "governance"
VALID_CATEGORIES = ("backend", "frontend", "data", "infra", "governance", "docs", "test")
VALID_LOAD_MODES = ("always", "on-demand", "deep")
VALID_RISK = ("low", "medium", "high", "critical")
VALID_STATUS = ("draft", "testing", "verified", "deprecated", "blocked")

#: 仓库 MCP 清单候选路径（都缺 → mcps = []，禁臆造）。
MCP_MANIFEST_CANDIDATES = (
    "shared/mcp-registry.yaml",
    "shared/mcp-manifest.yaml",
    ".skillmind/mcps.yaml",
    ".skillmind/mcps.json",
)

_WORD_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_'\-.]*|[\u4e00-\u9fff]")


# ────────────────────────────── 标量归一 ──────────────────────────────

def _as_str(v: Any, default: str = "") -> str:
    """把任意 YAML 标量压成单行字符串（兼容折叠块与列表）。"""
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x) for x in v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return re.sub(r"\s+", " ", str(v)).strip()


def _as_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "on", "1"):
            return True
        if s in ("false", "no", "off", "0"):
            return False
    return default


def _pick(*candidates: Any) -> str:
    """返回第一个非空字符串候选。"""
    for c in candidates:
        s = _as_str(c)
        if s:
            return s
    return ""


def _one_of(value: str, allowed: tuple, default: str) -> str:
    return value if value in allowed else default


def _as_number(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _normalize_owner(value: Any) -> str:
    """把 `owner/name` 形态的仓标识压成 owner 名。

    release-manifest 的 `source_repo` 形如 `hanshitong521/concise-mind`，
    直接当 owner 用会与 capability-registry 的 `exclusive_owners` 对不上
    （`concise-mind`）。这里只取仓名，非法字符形态返回空串。
    """
    s = _as_str(value)
    if not s:
        return ""
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    return s if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]*", s) else ""


def count_words(text: str) -> int:
    """root_words 口径：拉丁词 + 单个中日韩字符（中文无空格，故按字计）。"""
    return len(_WORD_RE.findall(text or ""))


# ────────────────────────────── 控制面消费 ──────────────────────────────

def _record_map(raw: Any) -> dict:
    """release-manifest.skills 既可能是 mapping 也可能是 list。"""
    out: dict = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                out[str(k)] = v
    elif isinstance(raw, list):
        for v in raw:
            if isinstance(v, dict):
                key = _pick(v.get("id"), v.get("skill_id"), v.get("name"))
                if key:
                    out[key] = v
    return out


def _id_list(raw: Any) -> list:
    """deploy.bundle.skills 既可能是 list[str] 也可能是 list[dict]。"""
    out: list = []
    if isinstance(raw, list):
        for v in raw:
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
            elif isinstance(v, dict):
                key = _pick(v.get("id"), v.get("skill_id"), v.get("name"))
                if key:
                    out.append(key)
    elif isinstance(raw, dict):
        out = [str(k) for k in raw]
    return out


def _owner_from_capabilities(caps: Any) -> dict:
    out: dict = {}
    if not isinstance(caps, dict):
        return out
    for _cap, rec in caps.items():
        if not isinstance(rec, dict):
            continue
        skill = _as_str(rec.get("skill"))
        if skill and skill not in out:
            owner = _as_str(rec.get("owner"))
            if owner:
                out[skill] = owner
    return out


def load_scores(root: Path) -> dict:
    """读 .skillmind/scores.json（score.py 产物）；容忍多种外层结构。"""
    data = C.load_json(C.state_dir(root) / "scores.json", default=None)
    out: dict = {}

    def _take(rec: Any, key: Any) -> None:
        if not isinstance(rec, dict) or key is None:
            return
        num = _as_number(rec.get("score"))
        if num is not None:
            out[str(key)] = num

    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict) and "score" in v:
                _take(v, k)
            else:
                num = _as_number(v)
                if num is not None:
                    out[str(k)] = num
        for bucket in ("records", "scores", "entries"):
            recs = data.get(bucket)
            if isinstance(recs, list):
                for r in recs:
                    _take(r, r.get("skill_id") if isinstance(r, dict) else None)
    elif isinstance(data, list):
        for r in data:
            _take(r, r.get("skill_id") if isinstance(r, dict) else None)
    return out


def load_status_overrides(root: Path) -> dict:
    """读 .skillmind/status-overrides.json：人工状态裁决（blocked 一票否决）。"""
    data = C.load_json(C.state_dir(root) / "status-overrides.json", default=None)
    if not isinstance(data, dict):
        return {}
    return {str(k): _as_str(v) for k, v in data.items() if _as_str(v) in VALID_STATUS}


def load_context(root: Path) -> dict:
    """一次性装载控制面 + 生成物，产出构建上下文。"""
    cp = C.load_control_plane(root)
    rm = cp.get("release_manifest") or {}
    if not isinstance(rm, dict):
        rm = {}
    db = cp.get("deploy_bundle") or {}
    if not isinstance(db, dict):
        db = {}
    cr = cp.get("capability_registry") or {}
    if not isinstance(cr, dict):
        cr = {}
    return {
        "release_records": _record_map(rm.get("skills")),
        "bundled_ids": set(_id_list(db.get("skills"))),
        "owner_by_skill": _owner_from_capabilities(cr.get("capabilities")),
        "overrides": load_status_overrides(root),
        "scores": load_scores(root),
        "exclude": C.manifest_exclude(root),
        "sources": [rel for rel in C.CONTROL_PLANE.values() if (root / rel).exists()],
    }


# ────────────────────────────── skill 条目 ──────────────────────────────

def _collect_refs(skill_dir: Path) -> list:
    ref_dir = skill_dir / "references"
    if not ref_dir.is_dir():
        return []
    out = []
    for p in C.iter_files(ref_dir):
        out.append(p.relative_to(skill_dir).as_posix())
    return sorted(out)


def _manifest_of(skill_dir: Path) -> dict:
    data = C.try_load_yaml(skill_dir / "skill.yaml")
    return data if isinstance(data, dict) else {}


def build_entry(root: Path, skill_dir: Path, ctx: dict) -> dict:
    skill_id = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    text = C.read_text(skill_md)
    meta = C.parse_frontmatter(text)
    _fm, body = C.split_frontmatter(text)
    manifest = _manifest_of(skill_dir)

    rec = ctx["release_records"].get(skill_id) or {}
    bundled = bool(rec) or skill_id in ctx["bundled_ids"]

    name = _pick(meta.get("name"), manifest.get("name")) or skill_id
    description = _pick(meta.get("description"), manifest.get("description"))

    version = _pick(meta.get("version"), manifest.get("version"), rec.get("version")) or None

    risk_meta = manifest.get("risk") if isinstance(manifest.get("risk"), dict) else {}
    risk = _one_of(
        _pick(meta.get("risk"), risk_meta.get("level")).lower(), VALID_RISK, "low"
    )
    destructive = _as_bool(
        meta.get("destructive") if meta.get("destructive") is not None
        else risk_meta.get("destructive"),
        default=False,
    )

    loading = manifest.get("loading") if isinstance(manifest.get("loading"), dict) else {}
    declared_mode = _pick(loading.get("mode")).lower()
    if declared_mode in VALID_LOAD_MODES:
        load_mode, load_mode_source = declared_mode, "declared"
    elif _as_bool(meta.get("disable-model-invocation"), False):
        # frontmatter 显式关闭模型自动调用 —— 也是作者显式选择，不是默认回落。
        load_mode, load_mode_source = "on-demand", "declared"
    else:
        # 既无 skill.yaml.loading.mode，也无 disable-model-invocation → 落到默认常驻。
        # 这是**未声明**，不是设计选择：V5.1 前 ai-requirement 即此情形，白付 3502 tok/轮。
        # 审计据此区分「故意常驻」（latch 型，如 ai-concise）与「忘了声明」。
        load_mode, load_mode_source = "always", "default"

    category = _one_of(
        _pick(meta.get("category"), manifest.get("category")).lower(),
        VALID_CATEGORIES,
        CATEGORY_BY_SKILL.get(skill_id, DEFAULT_CATEGORY),
    )

    m_triggers = manifest.get("triggers") if isinstance(manifest.get("triggers"), dict) else {}
    derived = C.derive_triggers(body, description)
    include = []
    for t in list(m_triggers.get("include") or []) + list(derived.get("include") or []):
        s = _as_str(t)
        # 触发词必须是无空白单 token：丢弃 `trig:` 行尾说明文字（如 "prio:rules>this"）。
        if s and not re.search(r"\s", s) and s not in include:
            include.append(s)
    exclude = []
    for t in list(m_triggers.get("exclude") or []) + list(derived.get("exclude") or []):
        s = _as_str(t)
        # exclude 允许**短语**形态（"requirement freeze"）——否定从句本就是短语。
        # 与 include 不同：include 禁空白是为了丢 `trig:` 行尾的 prio 说明；
        # exclude 若照搬该守卫，多词否定短语会被静默丢弃（precision 护栏失效）。
        if s and len(s) <= 32 and not re.search(r"[\r\n]", s) and s not in exclude:
            exclude.append(s)

    tags = C.derive_tags(description, name)
    for t in manifest.get("tags") or []:
        s = _as_str(t).lower()
        if s and s not in tags:
            tags.append(s)
    tags = sorted(set(tags))

    # owner 优先级：capability-registry（SSOT） → skill.yaml 显式声明 → source_repo 归一
    owner = _pick(
        ctx["owner_by_skill"].get(skill_id),
        manifest.get("owner"),
        _normalize_owner(rec.get("source_repo")),
    ) or None

    override = ctx["overrides"].get(skill_id)
    if override:
        status = override
    elif rec and bundled:
        status = "verified"
    else:
        status = "testing"

    return {
        "skill_id": skill_id,
        "name": name,
        "path": (skill_dir / "SKILL.md").relative_to(root).as_posix(),
        "dir": skill_dir.relative_to(root).as_posix(),
        "description": description,
        "category": category,
        "tags": tags,
        "version": version,
        "status": status,
        "score": ctx["scores"].get(skill_id),
        "owner": owner,
        "load_mode": load_mode,
        "load_mode_source": load_mode_source,
        "risk": risk,
        "destructive": destructive,
        "always_apply": load_mode == "always",
        "root_lines": len(text.splitlines()),
        "root_words": count_words(text),
        "refs": _collect_refs(skill_dir),
        "triggers": {"include": include[:24], "exclude": exclude},
        "bundled": bundled,
        "hash": C.hash_tree(skill_dir, ctx["exclude"])["content_hash"],
        "source": "release-manifest" if rec else "filesystem",
    }


# ────────────────────────────── rules / mcps ──────────────────────────────

def scan_rules(root: Path) -> list:
    """扫 .cursor/rules/**/*.mdc，只收 alwaysApply: true（常驻 token 成本来源）。"""
    base = root / ".cursor" / "rules"
    out: list = []
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*.mdc")):
        if any(part in C.IGNORED_DIR_PARTS for part in p.parts):
            continue
        text = C.read_text(p)
        meta = C.parse_frontmatter(text)
        if meta.get("alwaysApply") is not None:
            always = _as_bool(meta.get("alwaysApply"), False)
        else:
            always = bool(re.search(r"^\s*alwaysApply\s*:\s*true\s*$", text, re.M))
        if not always:
            continue
        out.append({
            "path": p.relative_to(root).as_posix(),
            "always_apply": True,
            "lines": len(text.splitlines()),
        })
    return out


def _tool_items(tools: list) -> list:
    """逐工具估算 schema token 成本（口径 `references/token-loading.md` §3）。

    估算面 = 工具名 + description + 参数名/类型 —— 这三项就是模型实际看到的 schema。
    显式 `schema_tokens` 优先（调用方有实测值时用实测）。
    """
    out: list = []
    for t in tools:
        if isinstance(t, str):
            out.append({"name": t, "tokens": C.est_tokens(t),
                        "destructive": False, "description_len": 0})
            continue
        if not isinstance(t, dict):
            continue
        tn = _pick(t.get("name"), t.get("id"))
        if not tn:
            continue
        desc = str(t.get("description") or "")
        params = t.get("params") if isinstance(t.get("params"), dict) else {}
        declared = t.get("schema_tokens")
        if declared is not None:
            tokens = int(_as_number(declared) or 0)
        else:
            surface = " ".join([tn, desc] + [f"{k}:{v}" for k, v in params.items()])
            tokens = C.est_tokens(surface)
        out.append({"name": tn, "tokens": tokens,
                    "destructive": _as_bool(t.get("destructive"), False),
                    "description_len": len(desc)})
    return out


def _mcp_entries(raw: Any) -> list:
    if isinstance(raw, dict):
        for bucket in ("servers", "mcps", "mcp_servers"):
            if isinstance(raw.get(bucket), list):
                raw = raw[bucket]
                break
        else:
            raw = [dict({"name": k}, **(v if isinstance(v, dict) else {})) for k, v in raw.items()]
    if not isinstance(raw, list):
        return []
    out: list = []
    for rec in raw:
        if isinstance(rec, str):
            out.append({"name": rec, "tools": 0, "standing": False,
                        "tool_items": [], "tool_tokens": 0, "destructive": False,
                        "transport": "", "owner": ""})
            continue
        if not isinstance(rec, dict):
            continue
        name = _pick(rec.get("name"), rec.get("id"), rec.get("server"))
        if not name:
            continue
        tools = rec.get("tools")
        items = _tool_items(tools) if isinstance(tools, list) else []
        count = len(items) if items else int(_as_number(rec.get("tool_count")) or 0)
        out.append({
            "name": name,
            # tools 保持为**个数**（向后兼容既有消费者）；明细在 tool_items。
            "tools": count,
            "standing": _as_bool(rec.get("standing"), False),
            # 工具定义是**每轮都进上下文**的常驻成本（等价于 always skill 的 root_words）。
            # 只数个数 = 把成本藏起来 —— 与 D8「root_words 无消费」同类缺陷。
            "tool_items": items,
            "tool_tokens": sum(int(i.get("tokens") or 0) for i in items),
            "destructive": any(bool(i.get("destructive")) for i in items),
            "transport": _pick(rec.get("transport"), rec.get("type")) or "",
            "owner": _pick(rec.get("owner")) or "",
        })
    return out


def scan_mcps(root: Path) -> list:
    """仓库无 MCP 清单 → []（不臆造）。"""
    for rel in MCP_MANIFEST_CANDIDATES:
        p = root / rel
        if not p.exists():
            continue
        data = C.load_json(p, default=None) if p.suffix == ".json" else C.try_load_yaml(p)
        entries = _mcp_entries(data)
        if entries:
            return sorted(entries, key=lambda e: e["name"])
    return []


# ────────────────────────────── overlap ──────────────────────────────

def _keywords(description: str) -> set:
    """description 关键词集：拉丁词(≥4) + 中文二字滑窗（规则层，无 embedding）。"""
    kws: set = set()
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{3,}", description or ""):
        low = tok.lower()
        if low not in C._STOP_TAGS:
            kws.add(low)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", description or ""):
        for i in range(len(run) - 1):
            kws.add(run[i:i + 2])
    return kws


def compute_overlap(skills: list) -> list:
    """标签交集 ≥2 或 description 关键词交叉 ≥3 → 一条记录。"""
    kw = {s["skill_id"]: _keywords(s["description"]) for s in skills}
    out: list = []
    for i, a in enumerate(skills):
        for b in skills[i + 1:]:
            ta, tb = set(a["tags"]), set(b["tags"])
            shared = sorted(ta & tb)
            shared_kw = kw[a["skill_id"]] & kw[b["skill_id"]]
            if len(shared) < 2 and len(shared_kw) < 3:
                continue
            out.append({
                "a": a["skill_id"],
                "b": b["skill_id"],
                "shared_tags": shared,
                "severity": "warn" if len(shared) >= 3 else "info",
            })
    out.sort(key=lambda r: (r["a"], r["b"]))
    return out


# ────────────────────────────── 主流程 ──────────────────────────────

def build_registry(root: Path) -> dict:
    ctx = load_context(root)
    skills = [build_entry(root, p.parent, ctx)
              for p in sorted((root / "skills").glob("*/SKILL.md"))]
    skills.sort(key=lambda s: s["skill_id"])
    rules = scan_rules(root)
    mcps = scan_mcps(root)
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": C.SCHEMA_VERSION,
        "generated_at": C.now_iso(),
        "root": str(root),
        "sources": ctx["sources"],
        "skills": skills,
        "rules": rules,
        "mcps": mcps,
        "overlap": compute_overlap(skills),
        "stats": {
            "skills": len(skills),
            "verified": sum(1 for s in skills if s["status"] == "verified"),
            "always_apply_rules": len(rules),
            "bundled": sum(1 for s in skills if s["bundled"]),
        },
    }


def render_human(reg: dict, out_path: Path) -> list:
    st = reg["stats"]
    lines = [
        C.banner("SkillMind Registry"),
        f"out     : {out_path}",
        f"sources : {', '.join(reg['sources']) or '(none)'}",
        f"stats   : skills={st['skills']} verified={st['verified']} "
        f"bundled={st['bundled']} always_apply_rules={st['always_apply_rules']} "
        f"mcps={len(reg['mcps'])} overlap={len(reg['overlap'])}",
        "",
        f"{'skill_id':<20} {'category':<11} {'status':<10} {'load_mode':<10} "
        f"{'risk':<8} {'lines':>5} {'refs':>4} {'bundled':>7}",
    ]
    for s in reg["skills"]:
        lines.append(
            f"{s['skill_id']:<20} {s['category']:<11} {s['status']:<10} "
            f"{s['load_mode']:<10} {s['risk']:<8} {s['root_lines']:>5} "
            f"{len(s['refs']):>4} {'yes' if s['bundled'] else 'no':>7}"
        )
    if reg["overlap"]:
        lines.append("")
        lines.append("overlap:")
        for o in reg["overlap"]:
            lines.append(f"  {o['a']} ~ {o['b']} [{o['severity']}] tags={o['shared_tags']}")
    if reg["rules"]:
        lines.append("")
        lines.append("alwaysApply rules:")
        for r in reg["rules"]:
            lines.append(f"  {r['path']} ({r['lines']}L)")
    if not reg["mcps"]:
        lines.append("")
        lines.append("mcps: (仓库无 MCP 清单，输出空数组)")
    return lines


def main(argv: Any = None) -> int:
    ap = argparse.ArgumentParser(
        prog="registry_build.py",
        description="生成 SkillMind 注册表（spec-v2 §14.2）",
    )
    ap.add_argument("--root", default=None, help="扫描根（默认 _common.repo_root()）")
    ap.add_argument("--out", default=None, help="输出路径（默认 <root>/.skillmind/registry.json）")
    ap.add_argument("--json", action="store_true", help="以 JSON 打印到 stdout")
    args = ap.parse_args(argv)

    try:
        root = Path(args.root).expanduser().resolve() if args.root else C.repo_root()
    except OSError as exc:
        C.eprint(f"ERROR: 无法解析 --root: {exc}")
        return 2
    if not root.is_dir():
        C.eprint(f"ERROR: --root 不是目录: {root}")
        return 2
    if not (root / "skills").is_dir():
        C.eprint(f"ERROR: 缺少 skills/ 目录: {root / 'skills'}")
        return 2

    out_path = Path(args.out).expanduser().resolve() if args.out else C.state_dir(root) / "registry.json"

    try:
        reg = build_registry(root)
    except Exception as exc:  # 环境/解析错误 → 2
        C.eprint(f"ERROR: 生成注册表失败: {type(exc).__name__}: {exc}")
        return 2

    C.write_json(out_path, reg)
    C.emit(reg, as_json=args.json, human=render_human(reg, out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
