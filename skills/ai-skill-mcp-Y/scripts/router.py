#!/usr/bin/env python3
"""router.py — SkillMind 运行时唯一权威路由（spec-v2 §3.2 / §9 / §14.3）。

定位（§9.4）：Brain / TokenMind / SkillMind / MCP 不得各做一套 Router。
本脚本是运行时唯一权威；其余层只提供输入信号。

流程：
  1. 装载 registry.json（缺则自愈：import registry_build 重建 / 提示先跑）
  2. 硬过滤（§9.2）：blocked 永不推荐；deprecated 仅无替代时推荐并标注；
     exclude 命中排除并记理由；critical+risk=high 降级为候选并告警
  3. 打分（§9.1）：
       0.45×标签/关键词命中 + 0.25×触发词命中 + 0.15×项目类型匹配
     + 0.10×历史成功率(score/100) + 0.05×上下文成本惩罚
     上下文成本惩罚 = 1 - clamp01(root_lines / 400)
     列表级过滤：score 须 ≥ 首选 score × RELATIVE_BAND(0.45)，否则降为 excluded
     （挡掉「纯 category 命中」与「单个中文二字窗口命中」这类弱信号噪声）
  4. 链装配（§9.3）：requirement → design → coding → verification，
     只依据注册表 category/phase 与 capability-registry 映射，禁硬编码 skill 名
  5. 输出 §14.3 结构

只用标准库，裸 Python 3.9 可运行。退出码：0 成功 / 1 失败 / 2 用法或环境错误。
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

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

SCHEMA_NAME = "skillmind-route-result"
SCHEMA_VERSION = 1

METHODS = ("rule+tag", "embedding", "llm")

# ── §9.1 权重（改这里 = 改算法，须同步 spec）────────────────────────────
W_TAG = 0.45
W_TRIGGER = 0.25
W_CATEGORY = 0.15
W_HISTORY = 0.10
W_CONTEXT = 0.05

#: 上下文成本预算：root_lines 达到该值即扣满 0.05。
CONTEXT_LINE_BUDGET = 400
#: 标签/关键词命中饱和点：命中 ≥ N 个即满分。
TAG_SATURATION = 2
#: 多 token 触发词的最小命中数（防「需求」这类二字子串误触发）。
TRIGGER_MIN_TOKENS = 2

#: 同量级带（§9.1 列表级过滤）：推荐项 score 必须 ≥ 首选 score × 本系数。
#:
#: 没有这条，纯 category 命中（如 governance 类技能在治理任务里只靠 category 拿 0.15）
#: 或单个中文二字窗口命中（0.45×0.5≈0.23）就会与真正的首选并列进榜 —— 这是
#: 「弱信号噪声」，会直接把 Router 准确率打下来。0.45 的依据：真实需要多技能协同的
#: 任务（如 requirement 0.73 + coding 0.61）比值约 0.84，远高于阈值；而被挡掉的都是
#: 比值 <0.45 的噪声项。
RELATIVE_BAND = 0.45

DEFAULT_TOP = 5
DEFAULT_MIN_CONFIDENCE = 0.12

PHASE_ORDER = ("requirement", "design", "coding", "verification")

#: capability-registry 的 phase 名 → 链的四阶段（§9.3 只认四阶段）。
PHASE_NORMALIZE = {
    "requirement": "requirement",
    "design": "design",
    "coding": "coding",
    "debug": "coding",
    "implementation": "coding",
    "verification": "verification",
    "test": "verification",
    "review": "verification",
}

#: 注册表 category → 链阶段（§3.1 的七类 category 全覆盖）。
CATEGORY_PHASE = {
    "backend": "coding",
    "frontend": "coding",
    "data": "coding",
    "infra": "coding",
    "test": "verification",
    "docs": "design",
    "governance": "verification",
}

#: 任务原文 → project_type 推断（按序命中，先到先得）。
PROJECT_TYPE_HINTS = (
    ("governance", ("skill", "mcp", "agents", "触发器", "误触发", "审计", "治理",
                    "governance", "瘦身", "大扫除", "token预算")),
    ("requirement", ("需求", "澄清", "冻结", "规格", "requirement", "spec", "验收标准")),
    ("test", ("测试", "回归", "用例", "junit", "pytest", "覆盖率", "test")),
    ("data", ("数仓", "etl", "报表", "指标", "埋点", "数据同步")),
    ("frontend", ("前端", "页面", "组件", "react", "vue", "css", "html", "样式")),
    ("infra", ("部署", "发布", "docker", "k8s", "运维", "服务器", "端口", "日志",
               "监控", "192.168")),
    ("docs", ("文档", "说明", "说人话", "简洁", "压缩", "画图", "架构图", "流程图",
              "时序图", "设计文档")),
    ("backend", ("java", "spring", "springboot", "mybatis", "mapper", "sql", "mysql",
                 "oracle", "接口", "服务", "dao", "bug", "修", "后端", "数据库", "报错")),
)

#: 任务原文 → 需要的工程阶段（§9.3）。
PHASE_SIGNALS = (
    ("requirement", ("需求", "澄清", "冻结", "规格", "requirement", "spec",
                     "验收标准", "追问", "评审")),
    ("design", ("设计", "方案", "架构", "流程图", "时序图", "画图", "diagram",
                "design.md", "模块划分", "接口设计")),
    ("coding", ("改", "实现", "修复", "修", "bug", "sql", "mapper", "写代码",
                "重构", "新增", "编码", "报错", "联调")),
    ("verification", ("测试", "验证", "回归", "审计", "复检", "检查", "覆盖率",
                      "verify", "test", "review", "用例", "对账", "死代码", "重复",
                      "健康", "质量门", "准出", "大扫除", "瘦身", "治理", "触发器")),
)

#: 该阶段已完成的信号：命中则不再进链（如「需求已冻结」不该再走 requirement）。
PHASE_DONE_MARKERS = {
    "requirement": ("已冻结", "已确认", "已定稿", "已评审", "已 ready", "已ready"),
    "design": ("已设计", "已定稿"),
}

_ASCII_RE = re.compile(r"[a-z][a-z0-9_.\-]*")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WS_RE = re.compile(r"\s+")


# ────────────────────────────── 文本工具 ──────────────────────────────

def norm_text(text: Any) -> str:
    return _WS_RE.sub(" ", str(text or "")).strip().lower()


def tokenize(text: Any) -> set:
    """分词：ASCII 词（小写）+ 中文二字滑窗。规则层，零依赖。

    中文按 bigram 展开，使「审计MCP」这类混排触发词能按子串命中；
    ASCII 按整词取，避免 "java/sql" 被拆成 "sql" 造成跨域误命中。
    """
    low = str(text or "").lower()
    toks = set(_ASCII_RE.findall(low))
    for run in _CJK_RE.findall(low):
        if len(run) == 1:
            toks.add(run)
            continue
        for i in range(len(run) - 1):
            toks.add(run[i:i + 2])
    return toks


def _hint_hit(text: str, hint: str) -> bool:
    """中文提示按子串；ASCII 提示按词边界。"""
    if re.search(r"[\u4e00-\u9fff]", hint):
        return hint in text
    return re.search(r"(?<![a-z0-9_])" + re.escape(hint) + r"(?![a-z0-9_])", text) is not None


def _cjk_spans(text: str, bigrams: set) -> list:
    """把命中的中文二字窗口还原成最大连续片段（清需+澄清+需求 → 澄清需求）。"""
    spans = []
    for run in _CJK_RE.findall(str(text or "").lower()):
        i, n = 0, len(run)
        while i < n - 1:
            if run[i:i + 2] not in bigrams:
                i += 1
                continue
            j = i
            while j < n - 1 and run[j:j + 2] in bigrams:
                j += 1
            spans.append(run[i:j + 1])
            i = j + 1
    return spans


def pretty_hits(task_text: str, hits: set) -> list:
    """理由可读化：中文还原成词，英文保留整词；长片段优先。"""
    spans, singles, ascii_hits = [], [], []
    bigrams = set()
    for h in hits:
        if _CJK_RE.match(h):
            if len(h) == 2:
                bigrams.add(h)
            else:
                singles.append(h)
        else:
            ascii_hits.append(h)
    spans = sorted(_cjk_spans(task_text, bigrams), key=lambda s: (-len(s), s))
    out, seen = [], set()
    for h in spans + singles + sorted(ascii_hits):
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


#: CamelCase 边界（小写/数字 → 大写）：`BrandMapper` → `Brand Mapper`。
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
#: snake_case 下划线视作词边界：`Base_Column_List` → `Base Column List`。
_IDENT_UNDERSCORE_RE = re.compile(r"_+")


def hint_text(text: Any) -> str:
    """`_hint_hit` 的检索面：先把标识符拆成词，再归一化。

    为什么需要：`_hint_hit` 对 ASCII 提示按**词边界**匹配（这是对的 —— 防 `java` 命中
    `javascript`），但标识符归一化后是一整块：`BrandMapper.xml` → `brandmapper.xml`，
    此时 `mapper` 前面是字母 `d`，`(?<![a-z0-9_])` 不成立 → `project_type` 推不出来
    → `category` 权重归零 → 总分跌破 `DEFAULT_MIN_CONFIDENCE`（0.12）
    → 该任务「未命中任何技能」。实测 18 条基准里 **7 条**因此落空。

    只在**词边界**插空格、不改变词内容，故不引入跨域误命中（反例已由 selftest 锁定）。
    """
    s = str(text or "")
    s = _CAMEL_BOUNDARY_RE.sub(" ", s)
    s = _IDENT_UNDERSCORE_RE.sub(" ", s)
    return norm_text(s)


def infer_project_type(task: str) -> str | None:
    low = hint_text(task)
    for ptype, hints in PROJECT_TYPE_HINTS:
        for h in hints:
            if _hint_hit(low, h):
                return ptype
    return None


def infer_phases(task: str) -> list:
    low = hint_text(task)
    out = []
    for phase, hints in PHASE_SIGNALS:
        if not any(_hint_hit(low, h) for h in hints):
            continue
        done = PHASE_DONE_MARKERS.get(phase) or ()
        if done and any(_hint_hit(low, d) for d in done):
            continue
        out.append(phase)
    return [p for p in PHASE_ORDER if p in out]


# ────────────────────────────── 注册表装载 ──────────────────────────────

def default_registry_path(root: Path) -> Path:
    return C.state_dir(root) / "registry.json"


def _try_builder(root: Path) -> bool:
    """自愈：复用 WS-A 的 registry_build.build_registry 重建注册表。"""
    try:
        sys.path.insert(0, str(C.SCRIPTS_DIR))
        import registry_build  # type: ignore
    except Exception:
        return False
    fn = getattr(registry_build, "build_registry", None)
    if not callable(fn):
        return False
    try:
        reg = fn(root)
    except Exception:
        return False
    if not isinstance(reg, dict) or "skills" not in reg:
        return False
    try:
        C.write_json(default_registry_path(root), reg)
    except OSError:
        return False
    return True


def load_registry(root: Path, explicit: str | None) -> tuple[dict | None, Path, str]:
    """返回 (registry, path, err)。registry 为 None 时 err 说明原因。"""
    path = Path(explicit).expanduser().resolve() if explicit else default_registry_path(root)
    data = C.load_json(path, default=None)
    if isinstance(data, dict) and isinstance(data.get("skills"), list):
        return data, path, ""
    if _try_builder(root):
        data = C.load_json(default_registry_path(root), default=None)
        if isinstance(data, dict) and isinstance(data.get("skills"), list):
            return data, default_registry_path(root), ""
    return None, path, (
        f"注册表不可用: {path}\n"
        f"  请先运行: python3 {C.SCRIPTS_DIR / 'registry_build.py'} --root {root}"
    )


def load_latest_scores(root: Path) -> dict:
    """读 .skillmind/scores.json 的最新分数（history 项在 registry.score 为 null 时的补充）。"""
    data = C.load_json(C.state_dir(root) / "scores.json", default=None)
    out: dict = {}

    def take(rec: Any) -> None:
        if not isinstance(rec, dict):
            return
        sid = rec.get("skill_id")
        val = rec.get("score")
        if sid is None or not isinstance(val, (int, float)) or isinstance(val, bool):
            return
        out[str(sid)] = float(val)  # 后写覆盖 → 取最新一条

    if isinstance(data, dict):
        recs = data.get("records")
        if isinstance(recs, list):
            for r in recs:
                take(r)
        else:
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(v.get("score"), (int, float)):
                    out[str(k)] = float(v["score"])
    elif isinstance(data, list):
        for r in data:
            take(r)
    return out


# ────────────────────────────── §9.1 打分 ──────────────────────────────

def _filtered_triggers(skill: dict) -> list:
    """触发词：剔除落在 description 否定从句里的条目（如「Not for 查日志」）。"""
    trig = skill.get("triggers") or {}
    include = list(trig.get("include") or []) if isinstance(trig, dict) else []
    neg = norm_text(C.negative_clause(skill.get("description")))
    out = []
    for t in include:
        s = norm_text(t)
        if not s or (neg and s in neg):
            continue
        if s not in out:
            out.append(str(t))
    return out


def _trigger_matches(trigger: str, task_text: str, task_tokens: set) -> bool:
    """触发词命中：完整短语优先；多 token 触发词要求 ≥2 个 token 命中。"""
    tn = norm_text(trigger)
    if not tn:
        return False
    if tn in task_text:
        return True
    tt = tokenize(tn)
    if not tt:
        return False
    inter = tt & task_tokens
    if len(tt) == 1:
        return bool(inter)
    return len(inter) >= TRIGGER_MIN_TOKENS and len(inter) * 2 >= len(tt)


def score_skill(skill: dict, task: str, task_tokens: set,
                project_type: str | None, history: dict) -> dict:
    """按 §9.1 计算单个技能的 route_score 与可解释理由。"""
    sid = str(skill.get("skill_id") or skill.get("name") or "?")
    tags = [str(t) for t in (skill.get("tags") or [])]
    tag_tokens = set(norm_text(t) for t in tags)
    # 关键词面 = 注册表 tags（整词） + name + description 正向从句
    surface = set(tag_tokens)
    surface |= tokenize(skill.get("name"))
    surface |= tokenize(C.positive_clause(skill.get("description")))

    hits = sorted(task_tokens & surface)
    tag_score = min(1.0, len(hits) / float(TAG_SATURATION)) if hits else 0.0

    reasons = []
    for h in pretty_hits(task, set(hits))[:3]:
        reasons.append(("tag:" if h in tag_tokens else "keyword:") + h)

    matched_triggers = [t for t in _filtered_triggers(skill)
                        if _trigger_matches(t, task, task_tokens)]
    trigger_score = 1.0 if matched_triggers else 0.0
    for t in matched_triggers[:2]:
        reasons.append("trigger:" + t)

    cat = str(skill.get("category") or "").strip().lower()
    category_score = 1.0 if (project_type and cat and cat == project_type) else 0.0
    if category_score:
        reasons.append("category:" + cat)

    raw_score = skill.get("score")
    if not isinstance(raw_score, (int, float)) or isinstance(raw_score, bool):
        raw_score = history.get(sid)
    if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
        history_score = C.clamp01(float(raw_score) / 100.0)
        reasons.append("history:%s" % C.round2(float(raw_score)))
    else:
        history_score = 0.0
        reasons.append("history:none")

    try:
        root_lines = int(skill.get("root_lines") or 0)
    except (TypeError, ValueError):
        root_lines = 0
    context_score = 1.0 - C.clamp01(root_lines / float(CONTEXT_LINE_BUDGET))
    reasons.append("context:root_lines=%d" % root_lines)

    total = (W_TAG * tag_score + W_TRIGGER * trigger_score
             + W_CATEGORY * category_score + W_HISTORY * history_score
             + W_CONTEXT * context_score)

    return {
        "skill_id": sid,
        "score": total,
        "reasons": reasons,
        "category": cat or None,
        "status": skill.get("status"),
        "risk": skill.get("risk"),
        "breakdown": {
            "tag": C.round2(tag_score),
            "trigger": C.round2(trigger_score),
            "category": C.round2(category_score),
            "history": C.round2(history_score),
            "context": C.round2(context_score),
        },
    }


# ────────────────────────────── §9.2 硬过滤 ──────────────────────────────

def _has_replacement(skill: dict, skills: list) -> str | None:
    """替代判定：同 category 且至少 1 个标签交集，且非 blocked。"""
    sid = str(skill.get("skill_id") or "")
    cat = str(skill.get("category") or "")
    tags = set(norm_text(t) for t in (skill.get("tags") or []))
    for other in skills:
        oid = str(other.get("skill_id") or "")
        if oid == sid or str(other.get("status") or "") == "blocked":
            continue
        if cat and str(other.get("category") or "") == cat:
            if tags & set(norm_text(t) for t in (other.get("tags") or [])):
                return oid
    return None


_EXCL_WORD_RE = re.compile(r"[a-z0-9]+")

#: 英文短语做 AND 匹配时的最小词长（短词（only/ops）无区分度，禁当判据）。
_EXCL_MIN_WORD = 4


def exclude_hit(term: str, low: str) -> bool:
    """exclude 命中判定（§9.2）。

    单 token / 中文短语：整句**子串**命中即可。
    多词英文短语：要求**所有内容词**（≥4 字母）都出现在任务里（AND 语义）——
    整句子串匹配对 `requirement freeze` 这类短语过严：任务写成 `freeze requirement`
    就漏判，等于护栏失效。
    """
    t = norm_text(term)
    if not t:
        return False
    if t in low:
        return True
    if re.search(r"[\u4e00-\u9fff]", t):
        return False  # 中文短语只认子串：分词不可靠，禁猜
    words = [w for w in _EXCL_WORD_RE.findall(t) if len(w) >= _EXCL_MIN_WORD]
    if len(words) < 2:
        return False
    return all(w in low for w in words)


def hard_filter(skills: list, task: str, risk: str, confirm_risk: bool) -> tuple[list, list, list]:
    """返回 (可打分技能, excluded, warnings)。硬过滤先于打分（§9.2）。"""
    low = norm_text(task)
    keep, excluded, warnings = [], [], []
    for s in skills:
        sid = str(s.get("skill_id") or s.get("name") or "?")
        status = str(s.get("status") or "").strip().lower()

        if status == "blocked":
            excluded.append({"skill_id": sid,
                             "reason": "status=blocked：安全/合规一票否决，永不推荐"})
            continue

        trig = s.get("triggers") if isinstance(s.get("triggers"), dict) else {}
        hit_excl = [t for t in (trig.get("exclude") or []) if exclude_hit(t, low)]
        if hit_excl:
            excluded.append({"skill_id": sid,
                             "reason": "exclude 命中：%s" % ", ".join(str(t) for t in hit_excl)})
            continue

        if status == "deprecated":
            repl = _has_replacement(s, skills)
            if repl:
                excluded.append({"skill_id": sid,
                                 "reason": "status=deprecated 且已有替代 %s" % repl})
                continue
            warnings.append("%s status=deprecated 但无替代，仍列入推荐并标注（§9.2）" % sid)

        if risk == "critical" and str(s.get("risk") or "") == "high" and not confirm_risk:
            warnings.append(
                "%s risk=high 且任务风险 critical：降级为候选，需人工确认（§9.2）" % sid)
            s = dict(s)
            s["_downgraded"] = True
        keep.append(s)
    return keep, excluded, warnings


# ────────────────────────────── §9.3 链装配 ──────────────────────────────

def build_phase_map(registry: dict, cap_reg: Any) -> dict:
    """{phase: {skill_id: {"why": str, "source": "category"|"capability"}}}。

    推导顺序（§9.3 只允许这两种来源，禁硬编码 skill 名）：
      1. 注册表 category → phase（主口径）
      2. capability-registry 的 capability.skill；无 skill 字段时才用 capability.owner
         回落到同名注册技能（如 requirement.clarify.owner=requirement-mind → ai-requirement）
    """
    out = {p: {} for p in PHASE_ORDER}
    skills = registry.get("skills") or []

    by_key = {}
    for s in skills:
        sid = str(s.get("skill_id") or s.get("name") or "")
        if not sid:
            continue
        for k in (s.get("skill_id"), s.get("name"), s.get("owner")):
            if k:
                by_key.setdefault(str(k).strip().lower(), sid)

    def bind(phase: str, why: str, ref: str, source: str) -> None:
        sid = by_key.get(ref.strip().lower())
        if sid and sid not in out[phase]:
            out[phase][sid] = {"why": why, "source": source}

    caps = {}
    phases = {}
    if isinstance(cap_reg, dict):
        caps = cap_reg.get("capabilities") if isinstance(cap_reg.get("capabilities"), dict) else {}
        phases = cap_reg.get("phases") if isinstance(cap_reg.get("phases"), dict) else {}

    def bind_capability(phase: str, cap_name: str, cap: Any) -> None:
        if not isinstance(cap, dict):
            return
        # capability 显式声明 skill 时只用 skill；否则按 owner 回落到同名技能。
        ref = cap.get("skill") or cap.get("owner")
        if ref:
            bind(phase, "capability %s → %s" % (cap_name, ref), str(ref), "capability")

    for ph, names in phases.items():
        nph = PHASE_NORMALIZE.get(str(ph).strip().lower())
        if not nph or not isinstance(names, list):
            continue
        for cn in names:
            bind_capability(nph, str(cn), caps.get(cn))

    for cn, cap in caps.items():
        if not isinstance(cap, dict):
            continue
        for ph in str(cap.get("phase") or "").split(","):
            nph = PHASE_NORMALIZE.get(ph.strip().lower())
            if nph:
                bind_capability(nph, str(cn), cap)

    for s in skills:
        sid = str(s.get("skill_id") or s.get("name") or "")
        cat = str(s.get("category") or "").strip().lower()
        nph = CATEGORY_PHASE.get(cat)
        if sid and nph:
            out[nph][sid] = {"why": "category=%s → phase %s" % (cat, nph),
                             "source": "category", "cat": cat}
    return out


def _uncovered_owners(cap_reg: Any, phase: str) -> list:
    """该阶段在 capability-registry 里出现、但仓库无对应注册技能的 owner。"""
    if not isinstance(cap_reg, dict):
        return []
    caps = cap_reg.get("capabilities") if isinstance(cap_reg.get("capabilities"), dict) else {}
    phases = cap_reg.get("phases") if isinstance(cap_reg.get("phases"), dict) else {}
    owners = []
    for cn in (phases.get(phase) or []):
        cap = caps.get(cn) if isinstance(caps.get(cn), dict) else {}
        owner = cap.get("owner")
        if owner and str(owner) not in owners:
            owners.append(str(owner))
    return owners


def build_chain(needed: list, ranked: list, phase_map: dict, cap_reg: Any,
                project_type: str | None = None) -> tuple[list, list]:
    """链只从「已过阈值」的推荐里装配；顺序即执行顺序（§9.3）。

    候选优先级：注册表 category 映射为主口径；该阶段完全没有 category 映射时
    （如 requirement），才用 capability-registry 的 skill/owner 补位。
    例外：governance 类技能只在治理域任务里承担 verification 收敛角色，
    不得为普通工程任务充当验证步骤。
    """
    chain, warnings, used = [], [], set()
    for ph in PHASE_ORDER:
        if ph not in needed:
            continue
        entries = phase_map.get(ph) or {}
        has_category = any(e.get("source") == "category" for e in entries.values())
        pool = {sid: e for sid, e in entries.items()
                if (e.get("source") == "category") == has_category}
        if ph == "verification" and project_type != "governance":
            pool = {sid: e for sid, e in pool.items() if e.get("cat") != "governance"}
        cands = [r for r in ranked if r["skill_id"] in pool]
        if not cands:
            owners = _uncovered_owners(cap_reg, ph)
            tail = ("，capability-registry 指定 owner=%s" % ", ".join(owners)) if owners else ""
            warnings.append("%s 阶段无可用注册技能%s" % (ph, tail))
            continue
        best = cands[0]
        if best["skill_id"] in used:
            continue
        used.add(best["skill_id"])
        chain.append({
            "order": len(chain) + 1,
            "phase": ph,
            "skill_id": best["skill_id"],
            "why": pool[best["skill_id"]]["why"],
        })
    return chain, warnings


# ────────────────────────────── 主流程 ──────────────────────────────

def route(task: str, registry: dict, project_type: str | None, risk: str,
          complexity: str, top: int, min_confidence: float, method: str,
          root: Path, registry_path: Path, confirm_risk: bool = False) -> dict:
    warnings: list = []
    if method != "rule+tag":
        warnings.append(
            "method=%s 未实现（§3.2 第 2/3 级需 embedding/LLM，且须满足启用条件）；"
            "已回落第 1 级 rule+tag" % method)
        method = "rule+tag"

    pt_source = "explicit" if project_type else "inferred"
    if not project_type:
        project_type = infer_project_type(task)

    skills = registry.get("skills") or []
    if not skills:
        warnings.append("注册表 skills 为空：无候选可打分，请检查 --root 是否指向仓根")
    history = load_latest_scores(root)
    task_tokens = tokenize(task)

    keep, excluded, fw = hard_filter(skills, task, risk, confirm_risk)
    warnings.extend(fw)

    scored = [score_skill(s, task, task_tokens, project_type, history) for s in keep]
    downgraded = set(str(s.get("skill_id")) for s in keep if s.get("_downgraded"))

    # 入选需同时满足：达到阈值 + 至少一条相关性信号（标签/关键词、触发词、项目类型）。
    # 只靠 history/context 两项"质量分"进榜 = 无依据推荐，一律剔除。
    def _relevant(rec: dict) -> bool:
        b = rec["breakdown"]
        return b["tag"] > 0 or b["trigger"] > 0 or b["category"] > 0

    scored = [r for r in scored if r["score"] >= min_confidence and _relevant(r)]
    scored.sort(key=lambda r: (-r["score"], r["skill_id"]))

    # §9.1 列表级过滤：与首选同量级才算推荐，弱信号一律降为 excluded（带理由）。
    banded_out: list = []
    if scored:
        band = scored[0]["score"] * RELATIVE_BAND
        banded_out = [r for r in scored if r["score"] < band]
        scored = [r for r in scored if r["score"] >= band]

    recommended = []
    for r in scored[:top]:
        reasons = list(r["reasons"])
        if r["status"] == "deprecated":
            reasons.append("status:deprecated（无替代，仅标注推荐）")
        if r["skill_id"] in downgraded:
            reasons.append("downgraded:risk=high@critical（需人工确认）")
        recommended.append({
            "skill_id": r["skill_id"],
            "confidence": C.round2(r["score"]),
            "reasons": reasons,
            "category": r["category"],
            "status": r["status"],
            "breakdown": r["breakdown"],
        })

    if not recommended:
        warnings.append(
            "未命中任何技能：无技能同时满足「相关性信号（标签/关键词·触发词·项目类型）」"
            "与阈值 %.2f（任务可能不属于本仓技能域）" % min_confidence)

    for r in recommended:
        if r["skill_id"] in downgraded:
            continue
        if str(r["status"] or "") in ("draft", "testing"):
            warnings.append(
                "首选技能 %s 状态为 %s（未 verified），建议先过 TestMind 验证再用于关键路径"
                % (r["skill_id"], r["status"]))
            break

    needed = infer_phases(task)
    if not needed:
        warnings.append("未识别工程阶段：链不装配（可能是 overlay/风格类技能，见推荐项）")
    else:
        if complexity in ("L2", "L3") and "requirement" not in needed:
            needed = ["requirement"] + needed
        if ("coding" in needed or "design" in needed) and "verification" not in needed:
            needed = needed + ["verification"]

    cap_reg = C.load_control_plane(root).get("capability_registry")
    phase_map = build_phase_map(registry, cap_reg)
    chain, cw = build_chain(needed, scored, phase_map, cap_reg, project_type)
    warnings.extend(cw)

    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at": C.now_iso(),
        "task": task,
        "method": method,
        "confidence": recommended[0]["confidence"] if recommended else 0.0,
        "recommended": recommended,
        "chain": chain,
        "excluded": sorted(
            excluded + [
                {"skill_id": r["skill_id"],
                 "reason": "低于首选同量级阈值（confidence %.2f < 首选×%.2f）：弱信号噪声"
                           % (r["score"], RELATIVE_BAND)}
                for r in banded_out
            ],
            key=lambda e: e["skill_id"],
        ),
        "warnings": warnings,
        "inputs": {
            "project_type": project_type,
            "project_type_source": pt_source,
            "risk": risk,
            "complexity": complexity,
            "top": top,
            "min_confidence": min_confidence,
            "registry": C.relpath(registry_path, root),
            "registry_generated_at": registry.get("generated_at"),
            "candidates": len(skills),
            "matched": len(recommended),
        },
    }


def render_human(res: dict) -> list:
    inp = res.get("inputs") or {}
    lines = [
        C.banner("SkillMind Router — " + str(res.get("method"))),
        "task       : %s" % res.get("task"),
        "inputs     : project_type=%s(%s) risk=%s complexity=%s top=%s min=%.2f"
        % (inp.get("project_type"), inp.get("project_type_source"), inp.get("risk"),
           inp.get("complexity"), inp.get("top"), float(inp.get("min_confidence") or 0)),
        "registry   : %s  candidates=%s matched=%s"
        % (inp.get("registry"), inp.get("candidates"), inp.get("matched")),
        "confidence : %s" % res.get("confidence"),
        "",
        "recommended:",
    ]
    if res.get("recommended"):
        for i, r in enumerate(res["recommended"], 1):
            lines.append("  %d. %-22s %-6s %s" % (i, r["skill_id"], r["confidence"],
                                                  " | ".join(r["reasons"])))
            lines.append("     breakdown: %s" % json.dumps(r.get("breakdown") or {},
                                                          ensure_ascii=False, sort_keys=True))
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("chain:")
    if res.get("chain"):
        for c in res["chain"]:
            lines.append("  %d. [%-13s] %-22s %s" % (c["order"], c["phase"], c["skill_id"], c["why"]))
    else:
        lines.append("  (未装配)")

    lines.append("")
    lines.append("excluded:")
    if res.get("excluded"):
        for e in res["excluded"]:
            lines.append("  - %-22s %s" % (e["skill_id"], e["reason"]))
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("warnings:")
    if res.get("warnings"):
        for w in res["warnings"]:
            lines.append("  - %s" % w)
    else:
        lines.append("  (none)")
    return lines


def main(argv: Any = None) -> int:
    ap = argparse.ArgumentParser(
        prog="router.py",
        description="SkillMind 运行时唯一权威路由（spec-v2 §9 / §14.3）",
    )
    ap.add_argument("--task", required=True, help="用户任务原文")
    ap.add_argument("--registry", default=None,
                    help="registry.json 路径（默认 <root>/.skillmind/registry.json）")
    ap.add_argument("--root", default=None, help="仓根（默认 _common.repo_root()）")
    ap.add_argument("--project-type", default=None, help="项目/任务域，缺省由任务推断")
    ap.add_argument("--risk", default="low", choices=("low", "medium", "high", "critical"))
    ap.add_argument("--complexity", default="L1", choices=("L0", "L1", "L2", "L3"))
    ap.add_argument("--top", type=int, default=DEFAULT_TOP, help="推荐条数上限（默认 5）")
    ap.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE,
                    help="入选阈值（默认 0.12）")
    ap.add_argument("--method", default="rule+tag", choices=METHODS,
                    help="路由级别；embedding/llm 未实现，会回落 rule+tag 并告警")
    ap.add_argument("--confirm-risk", action="store_true",
                    help="人工确认高风险技能，解除 critical/high 降级")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    if not str(args.task).strip():
        C.eprint("ERROR: --task 不能为空")
        return EXIT_USAGE
    if args.top < 1:
        C.eprint("ERROR: --top 必须 >= 1")
        return EXIT_USAGE

    try:
        root = Path(args.root).expanduser().resolve() if args.root else C.repo_root()
    except OSError as exc:
        C.eprint("ERROR: 无法解析 --root: %s" % exc)
        return EXIT_USAGE
    if not root.is_dir():
        C.eprint("ERROR: --root 不是目录: %s" % root)
        return EXIT_USAGE

    registry, reg_path, err = load_registry(root, args.registry)
    if registry is None:
        C.eprint("ERROR: " + err)
        return EXIT_USAGE

    try:
        res = route(args.task, registry, args.project_type, args.risk, args.complexity,
                    args.top, args.min_confidence, args.method, root, reg_path,
                    args.confirm_risk)
    except Exception as exc:
        C.eprint("ERROR: 路由失败: %s: %s" % (type(exc).__name__, exc))
        return EXIT_FAIL

    C.emit(res, as_json=args.json, human=render_human(res))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
