#!/usr/bin/env python3
"""_common.py — SkillMind 脚本共享底座。

职责（所有 scripts/ 必须复用，禁止各自实现）：
  - YAML 装载：优先 PyYAML，缺失时回落 _yaml_lite（零依赖）
  - 哈希：与仓控制面 scripts/_release_lib.py 语义完全一致
          （CRLF→LF、行尾 rstrip、同一 IGNORED_DIR_PARTS）
          否则会出现「SkillMind 算一个哈希、release-manifest 算另一个」的假 DRIFT
  - 路径：定位本 skill 根 / 仓根 / 状态目录
  - 输出：统一 --json 与人类可读双通道
  - 控制面装载：release-manifest / capability-registry / schema-versions / deploy.bundle

约定：本模块只依赖标准库（_yaml_lite 亦然），保证 scripts/ 可在裸 Python 下运行。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _yaml_lite  # noqa: E402

# ────────────────────────────── 常量 ──────────────────────────────

SKILL_DIR: Path = Path(__file__).resolve().parents[1]
SCRIPTS_DIR: Path = Path(__file__).resolve().parent
SKILL_NAME: str = SKILL_DIR.name

#: 与 scripts/_release_lib.py 保持一致，改这里等于改漂移语义。
IGNORED_DIR_PARTS: frozenset[str] = frozenset(
    {".git", "__pycache__", "node_modules", ".codehealth", "reports"}
)

#: 生成物状态目录（位于仓根，不进任何 artifact_path，故不影响 content_hash）
STATE_DIRNAME = ".skillmind"

CONTROL_PLANE: dict[str, str] = {
    "release_manifest": "shared/release-manifest.yaml",
    "capability_registry": "shared/capability-registry.yaml",
    "schema_versions": "shared/schema-versions.yaml",
    "deploy_bundle": "deploy.bundle.yaml",
}

SCHEMA_VERSION = 1


# ────────────────────────────── 路径 ──────────────────────────────

def repo_root(start: Path | None = None) -> Path:
    """从本 skill 向上找到控制面所在仓根。

    判定顺序：存在 shared/release-manifest.yaml → 存在 .git → 退化为上溯 6 层。
    """
    cur = (start or SKILL_DIR).resolve()
    for cand in [cur, *cur.parents]:
        if (cand / CONTROL_PLANE["release_manifest"]).exists():
            return cand
    for cand in [cur, *cur.parents]:
        if (cand / ".git").exists():
            return cand
    return cur.parents[3] if len(cur.parents) > 3 else cur


def state_dir(root: Path | None = None) -> Path:
    """生成物目录 <repo>/.skillmind/（自动创建）。"""
    d = (root or repo_root()) / STATE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def relpath(path: Path, base: Path | None = None) -> str:
    try:
        return path.resolve().relative_to((base or repo_root()).resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


# ────────────────────────────── YAML ──────────────────────────────

def _have_pyyaml() -> bool:
    try:
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


HAVE_PYYAML = _have_pyyaml()


def load_yaml_text(text: str) -> Any:
    if HAVE_PYYAML:
        import yaml
        return yaml.safe_load(text)
    return _yaml_lite.load(text)


def load_yaml(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"缺少文件: {p}")
    return load_yaml_text(p.read_text(encoding="utf-8", errors="replace"))


def try_load_yaml(path: str | Path) -> Any:
    """容错版：文件不存在或解析失败返回 None。"""
    try:
        return load_yaml(path)
    except Exception:
        return None


# ────────────────────────────── Frontmatter ──────────────────────────────

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """切出 SKILL.md 的 YAML frontmatter 与正文。"""
    m = _FM_RE.match(text.lstrip("\ufeff"))
    if not m:
        return {}, text
    meta = load_yaml_text(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, text[m.end():]


def parse_frontmatter(text: str) -> dict[str, Any]:
    return split_frontmatter(text)[0]


def frontmatter_scalar(text: str, key: str) -> str:
    """取 frontmatter 标量并压成单行（兼容 > 折叠块）。"""
    meta = parse_frontmatter(text)
    v = meta.get(key)
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x) for x in v)
    return re.sub(r"\s+", " ", str(v)).strip()


# ────────────────────────────── 哈希（与控制面同语义） ──────────────────────────────

def normalize_bytes(raw: bytes, exclude: list[str] | None = None, name: str = "") -> bytes:
    if exclude and name and name in exclude:
        return raw
    text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(ln.rstrip() for ln in text.split("\n")).encode("utf-8")


def hash_file(path: str | Path, exclude: list[str] | None = None) -> str:
    p = Path(path)
    return "sha256:" + hashlib.sha256(
        normalize_bytes(p.read_bytes(), exclude=exclude, name=p.name)
    ).hexdigest()


def hash_tree(root: str | Path, exclude: list[str] | None = None) -> dict[str, Any]:
    """目录（或单文件）确定性哈希；与 _release_lib.hash_tree 逐字节等价。"""
    exclude = exclude or []
    root = Path(root)
    if root.is_file():
        files, base = [root], root.parent
    else:
        files, base = sorted(p for p in root.rglob("*") if p.is_file()), root

    entries: list[tuple[str, str]] = []
    for f in files:
        rel = f.relative_to(base).as_posix()
        if rel in exclude or f.name in exclude:
            continue
        if any(part in IGNORED_DIR_PARTS for part in f.parts):
            continue
        norm = normalize_bytes(f.read_bytes(), exclude=exclude, name=f.name)
        entries.append((rel, hashlib.sha256(norm).hexdigest()))

    entries.sort(key=lambda t: t[0])
    joined = "\n".join(f"{rel}:{h}" for rel, h in entries).encode("utf-8")
    return {
        "content_hash": "sha256:" + hashlib.sha256(joined).hexdigest(),
        "file_count": len(entries),
        "files": [{"path": rel, "hash": h} for rel, h in entries],
    }


def manifest_exclude(root: Path | None = None) -> list[str]:
    """从 release-manifest 读 hash.normalize.exclude（控制面唯一真源）。"""
    m = try_load_yaml((root or repo_root()) / CONTROL_PLANE["release_manifest"]) or {}
    return ((m.get("hash") or {}).get("normalize") or {}).get("exclude") or []


# ────────────────────────────── 控制面 ──────────────────────────────

def load_control_plane(root: Path | None = None) -> dict[str, Any]:
    """一次性装载四个控制面文件（缺失的为 None，不抛）。"""
    r = root or repo_root()
    return {k: try_load_yaml(r / rel) for k, rel in CONTROL_PLANE.items()}


# ────────────────────────────── 数值 / 时间 ──────────────────────────────

def clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def round2(x: float) -> float:
    return float(f"{x:.2f}")


#: token 估算用的 CJK 字符面（CJK 标点 / 假名 / 汉字 / 全角）。
_CJK_RE = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef]")


def est_tokens(text: Any) -> int:
    """零依赖 token 估算（`references/token-loading.md` §3）：

        est_tokens(s) = ceil(ascii_chars / 4) + ceil(cjk_chars / 1.5)

    **只用于预算核验与报告填报**。禁与遥测实测值（`context_tokens_loaded` /
    `result_tokens`）混报 —— 报告里估算与实测必须分列并标 `est` / `telemetry`。
    """
    s = str(text or "")
    cjk = len(_CJK_RE.findall(s))
    ascii_n = len(s) - cjk
    return -(-ascii_n // 4) + -(-2 * cjk // 3)   # ceil(a/4) + ceil(cjk/1.5)


# ────────────────────────────── IO ──────────────────────────────

def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def write_text(path: str | Path, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def write_json(path: str | Path, payload: Any) -> Path:
    return write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def load_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return default


def iter_files(root: Path, suffixes: Iterable[str] | None = None) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in IGNORED_DIR_PARTS for part in p.parts):
            continue
        if suffixes and p.suffix not in suffixes:
            continue
        out.append(p)
    return out


# ────────────────────────────── 输出 ──────────────────────────────

def emit(payload: Any, as_json: bool = False, human: str | list[str] | None = None) -> None:
    """统一双通道输出：--json 出机器可读，否则出人类可读。"""
    if as_json or human is None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(human if isinstance(human, str) else "\n".join(human))


def eprint(*a: Any) -> None:
    print(*a, file=sys.stderr)


def banner(title: str, width: int = 68) -> str:
    return f"{'─' * width}\n{title}\n{'─' * width}"


# ────────────────────────────── 标签 ──────────────────────────────

#: description 里的否定从句标记：其后内容属于「禁触发邻域」，不进标签/触发词面。
NEGATIVE_MARKERS = ("not for", "不适用", "不用于", "禁止用于", "禁用于")
_NEG_RE = re.compile("|".join(re.escape(m) for m in NEGATIVE_MARKERS), re.I)

#: 功能词 + 无区分度的泛工程词。留在标签里只会制造假 overlap。
_STOP_TAGS = frozenset({
    # 功能词
    "use", "used", "when", "then", "than", "the", "and", "for", "not", "nor",
    "with", "without", "from", "this", "that", "these", "those", "into", "onto",
    "over", "under", "after", "before", "any", "all", "each", "both", "its",
    "their", "there", "here", "what", "which", "who", "how", "why", "where",
    "can", "could", "should", "would", "may", "might", "must", "will", "are",
    "is", "was", "were", "be", "been", "being", "has", "have", "had", "do",
    "does", "did", "but", "or", "if", "so", "no", "yes", "also", "only", "just",
    "more", "most", "less", "least", "same", "other", "others", "such", "via",
    "per", "out", "off", "up", "down", "new", "old", "first", "last", "next",
    "step", "steps", "run", "runs", "make", "makes", "made", "get", "gets",
    "got", "set", "sets", "see", "sees", "saw", "say", "says", "said", "let",
    "lets", "turn", "turns", "keep", "keeps", "need", "needs", "want", "wants",
    # 泛工程词（无区分度，任何 skill 都可能命中）
    "skill", "skills", "mcp", "mcps", "agent", "agents", "code", "codes",
    "file", "files", "doc", "docs", "readme", "md", "yaml", "yml", "json",
    "txt", "ops", "pr", "prs", "min", "max", "avg", "todo", "tbd", "etc",
    "note", "notes", "case", "cases", "item", "items", "list", "lists", "map",
    "maps", "type", "types", "name", "names", "path", "paths", "line", "lines",
    "root", "dir", "dirs", "text", "word", "words", "token", "tokens", "true",
    "false", "null", "none", "able", "using", "based", "only",
})

#: 标签取样：只取裸英文技术词；含 `/` `.` 的是路径/枚举（docs/diagram/design.md），不是标签。
_TAG_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")

#: slash 触发词只认**命令形态**（`/ai-code`）；路径段（`/shared`、`/rules`、`/spec-v2.md`）一律不认。
_SLASH_TRIGGER_RE = re.compile(r"(?<![\w/])/([a-z][a-z0-9\-]{1,})(?![\w/\-.])")

#: 路径段黑名单（兜底：万一正则漏网）。
_PATH_SEGMENTS = frozenset({
    "shared", "scripts", "references", "templates", "tests", "schemas",
    "benchmarks", "docs", "skills", "assets", "evals", "src", "lib", "bin",
    "cursor", "github", "node_modules", "target", "dist", "build",
})

#: 否定从句的短语分隔符（中英文逗号/顿号/分号/换行）。
_EXCL_SPLIT_RE = re.compile(r"[,，、;；\n]+")

#: 否定从句里的连接词与无区分度修饰语 —— 留在 exclude 只会制造死条目。
_EXCLUDE_STOP = frozenset({
    "or", "and", "but", "nor", "alone", "only", "just", "etc",
    "但", "以及", "亦", "也", "等", "等等", "之类", "之流",
})

#: exclude 短语长度上限：超长说明切分失败，宁缺勿噪。
_EXCLUDE_MAX_LEN = 32


def positive_clause(text: Any) -> str:
    """description 里「Not for …」之前的部分（正向描述）。

    否定从句里的词是「不该触发」的邻域，混进标签或触发词会把路由带偏。
    """
    return _NEG_RE.split(str(text or ""), 1)[0]


def negative_clause(text: Any) -> str:
    """description 里「Not for …」之后的部分（否定从句 / 禁触发邻域）。

    这是 precision 信号的唯一来源：Router 硬过滤（§9.2）与 audit 的
    `triggers.exclude` 检查都消费它。
    """
    parts = _NEG_RE.split(str(text or ""), 1)
    return parts[1] if len(parts) > 1 else ""


def derive_excludes(description: str) -> list[str]:
    """从否定从句派生 exclude 短语（Router 硬过滤用，spec-v2 §9.2）。

    两种形态：
      1. 命令 —— `/ai-design`（单独扫出，避免被修饰语黏住）
      2. 短语 —— `requirement freeze` / `log-only ops`（按 , 、 ; 切分）

    丢弃：连接词与修饰语（or/alone/等）、超长段、纯符号段。
    """
    neg = negative_clause(description)
    if not neg:
        return []
    out: list[str] = []

    for m in _SLASH_TRIGGER_RE.finditer(neg):
        t = "/" + m.group(1)
        if t not in out:
            out.append(t)

    for seg in _EXCL_SPLIT_RE.split(neg):
        s = re.sub(r"\s+", " ", seg).strip()
        s = re.sub(r"^(?:or|and|but|nor|但|以及)\s+", "", s, flags=re.I)
        # 已单独收录的命令前缀不再计入短语，避免 "/ai-code alone" 这种半截条目
        s = re.sub(r"^/[A-Za-z][A-Za-z0-9\-]*\s*", "", s)
        s = s.strip(" .。·-—:：").strip()
        if not s or len(s) > _EXCLUDE_MAX_LEN or s.lower() in _EXCLUDE_STOP:
            continue
        if not (re.search(r"[\u4e00-\u9fff]", s) or re.search(r"[A-Za-z]", s)):
            continue
        if s not in out:
            out.append(s)
    return out[:12]


def derive_tags(description: str, name: str = "", extra: Iterable[str] = ()) -> list[str]:
    """从 description 的**正向从句**抽英文技术词做标签（规则层，零 embedding 依赖）。

    丢弃：否定从句内容、含 `/`/`.` 的路径或枚举 token、功能词与泛工程词。
    """
    tags: set[str] = set(x.strip().lower() for x in extra if x and x.strip())
    for tok in _TAG_RE.findall(positive_clause(description)):
        t = tok.strip("_-").lower()
        if len(t) < 3 or t in _STOP_TAGS or t.isdigit():
            continue
        tags.add(t)
    if name:
        t = name.strip().lower()
        if t and t not in _STOP_TAGS:
            tags.add(t)
    return sorted(tags)


def derive_triggers(body: str, description: str = "") -> dict[str, list[str]]:
    """从 SKILL.md 与 description 抽正向触发信号 + 否定邻域。

    - `trig:` 行按 `| , ；` 分隔取词（本仓权威触发位），`prio:` 之后的内容不算触发词
    - slash 触发词只认命令形态（`/ai-code`），路径段（`/shared`）与 STOP 清单里的
      slash 一律不取 —— 后者是「禁做」信号，当成正向触发词会反向扩大触发面
    - 中文短语只取 description 的正向从句，长度 2–12 且至少含 2 个汉字
    - **exclude** 由否定从句派生（见 derive_excludes）：不派生 = precision 无护栏
    """
    include: list[str] = []
    for line in (body or "").splitlines():
        if not re.match(r"^\s*trig\s*[:：]", line):
            continue
        head = re.split(r"\bprio\s*:", line.split(":", 1)[-1])[0]
        include.extend(x.strip() for x in re.split(r"[|,，;；]", head) if x.strip())

    pos = positive_clause(description)
    for m in _SLASH_TRIGGER_RE.finditer(pos):
        if m.group(1) not in _PATH_SEGMENTS:
            include.append("/" + m.group(1))
    for seg in re.split(r"[^\u4e00-\u9fffA-Za-z0-9\-]+", pos):
        if 2 <= len(seg) <= 12 and re.search(r"[\u4e00-\u9fff]{2,}", seg):
            include.append(seg)

    seen: set[str] = set()
    uniq = [x for x in include if not (x in seen or seen.add(x))]
    return {"include": uniq[:24], "exclude": derive_excludes(description)}


def main_guard(fn) -> None:  # pragma: no cover - 便捷包装
    raise SystemExit(fn())


# ────────────────────────────── JSON Schema 子集校验（唯一实现） ──────────────────────────────
# manifest_validate 与 telemetry 都消费本实现 —— **禁各自再写一份**。
# 历史教训：两份副本已分化出 2 个缺陷（enum 不区分 True/1、pattern 无 re.error 兜底），
# 同一 schema 在两处可能得出不同结论。

JSON_TYPES = ("object", "array", "string", "number", "integer", "boolean", "null")

#: 支持的校验关键字。
SCHEMA_KEYWORDS = frozenset({
    "type", "const", "enum", "required", "properties", "items",
    "additionalProperties", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "format",
    "minItems", "maxItems", "allOf", "anyOf", "oneOf",
})

#: 注解关键字（不参与校验，出现不算「未支持」）。
SCHEMA_ANNOTATIONS = frozenset({
    "$schema", "$id", "$comment", "title", "description", "comment",
    "schema_name", "schema_version", "examples", "default", "definitions",
})

_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:?\d{2})$")


def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def type_matches(value: Any, expected: str) -> bool:
    actual = json_type_name(value)
    if expected == "number":
        return actual in ("number", "integer")
    if expected == "integer":
        return actual == "integer"
    return actual == expected


def same_value(a: Any, b: Any) -> bool:
    """enum/const 比较：区分 True/1 与 False/0。

    Python 里 `True == 1`，裸 `in` 会让 `enum:[1]` 误接受 `true`（schema 语义不允许）。
    """
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def schema_keyword_warnings(schema: Any, path: str = "$") -> list[str]:
    """递归找出 schema 里**未支持**的关键字（禁静默：schema 作者须知道它没生效）。"""
    out: list[str] = []

    def walk(node: Any, p: str) -> None:
        if not isinstance(node, dict):
            return
        for kw, val in node.items():
            if kw not in SCHEMA_KEYWORDS and kw not in SCHEMA_ANNOTATIONS:
                out.append(f"{p}: schema 关键字未支持，已忽略: {kw}")
        props = node.get("properties")
        if isinstance(props, dict):
            for k, v in props.items():
                walk(v, f"{p}.{k}")
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, f"{p}[]")
        for kw in ("allOf", "anyOf", "oneOf"):
            subs = node.get(kw)
            if isinstance(subs, list):
                for i, sub in enumerate(subs):
                    walk(sub, f"{p}.{kw}[{i}]")
        for kw in ("additionalProperties", "definitions", "$defs"):
            sub = node.get(kw)
            if isinstance(sub, dict):
                walk(sub, f"{p}.{kw}")

    walk(schema, path)
    return out


def validate_instance(
    instance: Any,
    schema: Any,
    path: str = "$",
    errors: list[str] | None = None,
) -> list[str]:
    """最小 JSON Schema 子集校验（draft-07 子集）。返回错误列表（空 = 通过）。

    支持：type / const / enum / required / properties / items /
          additionalProperties / minimum / maximum /
          exclusiveMinimum / exclusiveMaximum / minLength / maxLength /
          pattern / format(date-time) / minItems / maxItems / allOf / anyOf / oneOf
    """
    if errors is None:
        errors = []
    if not isinstance(schema, dict):
        return errors

    declared = schema.get("type")
    if declared is not None:
        allowed = declared if isinstance(declared, list) else [declared]
        if not any(type_matches(instance, t) for t in allowed):
            errors.append(f"{path}: 类型应为 {'|'.join(str(t) for t in allowed)}，"
                          f"实为 {json_type_name(instance)}")
            return errors  # 类型不符，后续关键字无意义

    # const / enum（bool 安全：True 不得匹配 1）
    if "const" in schema and not same_value(instance, schema["const"]):
        errors.append(f"{path}: 常量约束 const={schema['const']!r}，实为 {instance!r}")
    allowed_vals = schema.get("enum")
    if isinstance(allowed_vals, list) and not any(same_value(instance, a) for a in allowed_vals):
        errors.append(f"{path}: 取值须 ∈ {allowed_vals!r}，实为 {instance!r}")

    for kw in ("allOf", "anyOf", "oneOf"):
        subs = schema.get(kw)
        if not isinstance(subs, list):
            continue
        branch_errors, passed = [], 0
        for sub in subs:
            sub_err: list[str] = []
            validate_instance(instance, sub, path, sub_err)
            if not sub_err:
                passed += 1
            branch_errors.append(sub_err)
        if kw == "allOf" and passed != len(subs):
            for sub_err in branch_errors:
                errors.extend(sub_err)
        elif kw == "anyOf" and passed == 0:
            errors.append(f"{path}: 不满足 anyOf 任一分支")
        elif kw == "oneOf" and passed != 1:
            errors.append(f"{path}: oneOf 须恰好命中 1 个分支，实际命中 {passed}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: 长度 {len(instance)} < minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: 长度 {len(instance)} > maxLength {schema['maxLength']}")
        pat = schema.get("pattern")
        if isinstance(pat, str):
            try:
                hit = re.search(pat, instance)
            except re.error as exc:
                errors.append(f"{path}: pattern 非法，已跳过: {pat} ({exc})")
                hit = True
            if hit is None:
                errors.append(f"{path}: 不匹配 pattern {pat}")
        if schema.get("format") == "date-time" and not _DATETIME_RE.match(instance):
            errors.append(f"{path}: 非 ISO8601 date-time：{instance!r}")

    # 数值约束（bool 是 int 子类，需排除）
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        for kw, op, sym in (("minimum", "<", "<"), ("maximum", ">", ">"),
                            ("exclusiveMinimum", "<=", "<="),
                            ("exclusiveMaximum", ">=", ">=")):
            limit = schema.get(kw)
            if isinstance(limit, (int, float)) and not isinstance(limit, bool):
                bad = (instance < limit if op == "<" else
                       instance > limit if op == ">" else
                       instance <= limit if op == "<=" else instance >= limit)
                if bad:
                    errors.append(f"{path}: {instance} {sym} {kw} {limit}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: 元素数 {len(instance)} < minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: 元素数 {len(instance)} > maxItems {schema['maxItems']}")
        items = schema.get("items")
        if isinstance(items, dict):
            for i, v in enumerate(instance):
                validate_instance(v, items, f"{path}[{i}]", errors)

    if isinstance(instance, dict):
        for req in schema.get("required") or []:
            if req not in instance:
                errors.append(f"{path}: 缺必填字段 '{req}'")
        props = schema.get("properties") or {}
        for key, sub in props.items():
            if key in instance:
                validate_instance(instance[key], sub, f"{path}.{key}", errors)
        extra = schema.get("additionalProperties", True)
        if extra is False:
            for key in instance:
                if key not in props:
                    errors.append(f"{path}: 出现未声明字段 '{key}'")
        elif isinstance(extra, dict):
            for key, val in instance.items():
                if key not in props:
                    validate_instance(val, extra, f"{path}.{key}", errors)

    return errors


if __name__ == "__main__":  # 自检：打印环境与关键路径
    print(json.dumps({
        "skill_dir": str(SKILL_DIR),
        "repo_root": str(repo_root()),
        "state_dir": str(state_dir()),
        "pyyaml": HAVE_PYYAML,
        "python": sys.version.split()[0],
        "control_plane": {k: (repo_root() / v).exists() for k, v in CONTROL_PLANE.items()},
    }, ensure_ascii=False, indent=2))
