#!/usr/bin/env python3
"""telemetry.py — SkillMind 遥测落盘与聚合（spec-v2 §14.5 / §23）。

职责：
  append  校验事件 → 脱敏 → 追加一行 JSON 到 <repo>/.skillmind/telemetry.jsonl
  summary 聚合 telemetry.jsonl → 调用数/成功率/token/重复调用/缓存命中/延迟/
          P0 证据丢失/返工/error_class 分布 + 阈值告警

设计约束：
  - 只依赖标准库，可在裸 Python 3.9 下运行（无 PyYAML、无 jsonschema）；
  - JSON Schema 校验复用 _common.validate_instance（draft-07 最小子集，唯一实现）；
  - 脱敏默认开启：键名规则可用 --no-redact 关闭（排障），
    **值形态规则恒开**——禁止原始敏感值落盘是硬约束，无关闭开关；
  - 复用 scripts/_common.py 的路径/输出底座。

退出码：0=通过；1=校验失败（事件不合 schema）；2=用法或环境错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # 中文输出在 Windows 控制台不炸
    sys.stdout.reconfigure(encoding="utf-8")

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2

SCHEMA_REL = "schemas/telemetry-event.schema.json"
DEFAULT_STORE_NAME = "telemetry.jsonl"
MASK = "***"

# ────────────────────────── 脱敏规则 ──────────────────────────
#: 键名命中即整值打码（大小写不敏感，子串匹配）。
SENSITIVE_KEY_RE = re.compile(
    r"token|key|secret|password|passwd|authorization|cookie|credential", re.I
)

#: 契约字段豁免表：这些 §14.5 字段名里含 "token" 字样，但值是**计数指标**而非凭证。
#: 不豁免会把 integer 打成 "***"，直接破坏 telemetry-event schema（假 P0 告警的根源）。
SAFE_KEY_ALLOWLIST = frozenset({"context_tokens_loaded", "result_tokens"})

#: 值形态命中即打码。long_b64 另有启发式二次判定，避免把 sha256 十六进制误伤。
SECRET_VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}")),
    ("github_pat_v2", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("aws_akid", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}")),
    ("long_b64", re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")),
]

_B64_HAS_UPPER = re.compile(r"[A-Z]")
_B64_HAS_LOWER = re.compile(r"[a-z]")
_B64_HAS_DIGIT = re.compile(r"[0-9+/=]")


def _looks_like_b64_secret(s: str) -> bool:
    """长 base64 启发式：同时含大小写 + 数字/符号才算疑似 secret。

    纯小写十六进制（sha256 摘要、git hash）不算 secret，避免误伤哈希证据。
    """
    return bool(
        _B64_HAS_UPPER.search(s)
        and _B64_HAS_LOWER.search(s)
        and _B64_HAS_DIGIT.search(s)
    )


def _redact_string(value: str) -> tuple[str, list[str]]:
    hits: list[str] = []

    def _sub(match: "re.Match[str]", name: str = "") -> str:
        text = match.group(0)
        if name == "long_b64" and not _looks_like_b64_secret(text):
            return text
        hits.append(name)
        return MASK

    out = value
    for name, pat in SECRET_VALUE_PATTERNS:
        out = pat.sub(lambda m, n=name: _sub(m, n), out)
    return out, hits


def redact_event(obj: Any, path: str = "$", key_redaction: bool = True) -> tuple[Any, list[str]]:
    """递归脱敏。返回 (脱敏后对象, 命中的字段路径列表)。

    ``key_redaction`` 只控制**键名规则**（可关，供排障时看清字段名）。
    **值形态规则永远生效**——`sk-` / `ghp_` / `Bearer` / 私钥头 / 长 base64
    一律打码，因为「禁止原始敏感值落盘」是硬约束，不提供关闭开关。
    """
    redacted: list[str] = []

    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)
            if key_redaction and key not in SAFE_KEY_ALLOWLIST and SENSITIVE_KEY_RE.search(key):
                out[key] = MASK
                redacted.append(f"{path}.{key}")
                continue
            nv, sub = redact_event(v, f"{path}.{key}", key_redaction)
            out[key] = nv
            redacted.extend(sub)
        return out, redacted

    if isinstance(obj, list):
        items = []
        for i, v in enumerate(obj):
            nv, sub = redact_event(v, f"{path}[{i}]", key_redaction)
            items.append(nv)
            redacted.extend(sub)
        return items, redacted

    if isinstance(obj, str):
        nv, hits = _redact_string(obj)
        for h in hits:
            redacted.append(f"{path}<{h}>")
        return nv, redacted

    return obj, redacted


# ────────────────────────── JSON Schema 最小子集 ──────────────────────────
# 唯一实现已收敛到 _common.validate_instance（manifest_validate 与本文件共用）。
# 这里只做名字转发：保留既有调用点与公开名（selftest 直接调用 validate_instance）。
validate_instance = _common.validate_instance
json_type_name = _common.json_type_name
type_matches = _common.type_matches
same_value = _common.same_value


# ────────────────────────── 路径与装载 ──────────────────────────


def schema_path() -> Path:
    return _common.SKILL_DIR / SCHEMA_REL


def load_schema() -> dict[str, Any] | None:
    """装载事件 schema；缺失或非法返回 None（调用方按环境错误处理）。"""
    p = schema_path()
    if not p.exists():
        _common.eprint(f"[ENV] 缺少事件 schema：{p}")
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        _common.eprint(f"[ENV] 事件 schema 解析失败：{e}")
        return None
    if not isinstance(doc, dict):
        _common.eprint("[ENV] 事件 schema 顶层须为 object")
        return None
    return doc


def resolve_store(store: str | None) -> Path:
    """--store 可传目录或 .jsonl 文件；缺省 <repo>/.skillmind/telemetry.jsonl。"""
    if not store:
        return _common.state_dir() / DEFAULT_STORE_NAME
    p = Path(store).expanduser()
    if p.is_dir() or p.suffix.lower() not in (".jsonl", ".json", ".ndjson"):
        return p / DEFAULT_STORE_NAME
    return p


def _iter_lines(path: Path) -> tuple[list[dict[str, Any]], int, list[str]]:
    """读 jsonl；返回 (事件列表, 坏行数, 坏行描述)。"""
    events: list[dict[str, Any]] = []
    bad = 0
    notes: list[str] = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except ValueError as e:
            bad += 1
            notes.append(f"line {i}: JSON 解析失败 {e}")
            continue
        if not isinstance(obj, dict):
            bad += 1
            notes.append(f"line {i}: 非 object")
            continue
        events.append(obj)
    return events, bad, notes


# ────────────────────────── 聚合 ──────────────────────────

#: 告警阈值（observability.md 与之一致，改这里等于改告警口径）。
ALERT_THRESHOLDS = {
    "success_rate_warn": 0.90,
    "duplicate_ratio_warn": 0.20,
    "calls_per_event_warn": 3.0,
    "avg_latency_ms_warn": 5000,
    #: 比例类告警的最小样本量：2 条事件里 1 条重复算出 50%，是噪声不是信号。
    "min_sample_for_ratio": 5,
}


def _group(events: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for ev in events:
        k = str(ev.get(key) or "")
        if not k:
            k = "(empty)"
        slot = out.setdefault(k, {"calls": 0, "success": 0, "success_rate": 0.0})
        slot["calls"] += 1
        if ev.get("success") is True:
            slot["success"] += 1
    for slot in out.values():
        slot["success_rate"] = _common.round2(slot["success"] / slot["calls"]) if slot["calls"] else 0.0
    return out


def _num(ev: dict[str, Any], key: str) -> int:
    v = ev.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0
    return int(v)


def build_summary(events: list[dict[str, Any]], store: Path, bad: int, notes: list[str]) -> dict[str, Any]:
    total = len(events)
    success = sum(1 for e in events if e.get("success") is True)
    context_tokens = sum(_num(e, "context_tokens_loaded") for e in events)
    result_tokens = sum(_num(e, "result_tokens") for e in events)
    call_total = sum(_num(e, "call_count") for e in events)
    rework_total = sum(_num(e, "rework") for e in events)
    latency_vals = [_num(e, "latency_ms") for e in events if "latency_ms" in e]
    cache_hits = sum(1 for e in events if e.get("cache_hit") is True)

    # 重复调用：同一 (session, agent, skill, tool) 再次出现即算一次重复
    seen: set[tuple[str, str, str, str]] = set()
    duplicates = 0
    duplicate_detail: list[dict[str, Any]] = []
    for i, e in enumerate(events, 1):
        sig = (
            str(e.get("session_id") or ""),
            str(e.get("agent_id") or ""),
            str(e.get("skill_id") or ""),
            str(e.get("tool_id") or ""),
        )
        if sig in seen:
            duplicates += 1
            duplicate_detail.append({"line": i, "skill_id": sig[2], "tool_id": sig[3]})
        else:
            seen.add(sig)

    # P0 证据丢失：Hard Gate 级，必须逐条列出
    p0_lost = [
        {
            "line": i,
            "ts": e.get("ts"),
            "session_id": e.get("session_id"),
            "agent_id": e.get("agent_id"),
            "skill_id": e.get("skill_id"),
            "error_class": e.get("error_class"),
        }
        for i, e in enumerate(events, 1)
        if e.get("p0_evidence_retained") is False
    ]

    error_class: dict[str, int] = {}
    for e in events:
        ec = e.get("error_class")
        if ec in (None, "", False):
            continue
        error_class[str(ec)] = error_class.get(str(ec), 0) + 1

    success_rate = _common.round2(success / total) if total else 0.0
    cache_hit_rate = _common.round2(cache_hits / total) if total else 0.0
    dup_ratio = _common.round2(duplicates / total) if total else 0.0
    avg_latency = _common.round2(sum(latency_vals) / len(latency_vals)) if latency_vals else 0.0
    calls_per_event = _common.round2(call_total / total) if total else 0.0

    alerts: list[dict[str, Any]] = []
    if p0_lost:
        alerts.append({
            "code": "P0_EVIDENCE_LOST", "level": "critical", "value": len(p0_lost), "threshold": 0,
            "message": f"P0 证据丢失 {len(p0_lost)} 条（Hard Gate FAIL：压缩不得删错误证据，V1 §13.3）",
        })
    if total and success_rate < ALERT_THRESHOLDS["success_rate_warn"]:
        alerts.append({
            "code": "SUCCESS_RATE_DROP", "level": "high", "value": success_rate,
            "threshold": ALERT_THRESHOLDS["success_rate_warn"],
            "message": f"成功率 {success_rate} 低于 {ALERT_THRESHOLDS['success_rate_warn']}",
        })
    if calls_per_event > ALERT_THRESHOLDS["calls_per_event_warn"]:
        alerts.append({
            "code": "RETRY_STORM", "level": "high", "value": calls_per_event,
            "threshold": ALERT_THRESHOLDS["calls_per_event_warn"],
            "message": f"平均 call_count {calls_per_event} 超上限，疑似重试风暴（5 Agent × 3 retry）",
        })
    if total >= ALERT_THRESHOLDS["min_sample_for_ratio"] and dup_ratio > ALERT_THRESHOLDS["duplicate_ratio_warn"]:
        alerts.append({
            "code": "DUPLICATE_CALLS", "level": "warn", "value": dup_ratio,
            "threshold": ALERT_THRESHOLDS["duplicate_ratio_warn"],
            "message": f"重复调用占比 {dup_ratio} 超阈值，检查缓存与触发去重",
        })
    if avg_latency > ALERT_THRESHOLDS["avg_latency_ms_warn"]:
        alerts.append({
            "code": "LATENCY_HIGH", "level": "warn", "value": avg_latency,
            "threshold": ALERT_THRESHOLDS["avg_latency_ms_warn"],
            "message": f"平均延迟 {avg_latency}ms 超阈值",
        })
    if bad:
        alerts.append({
            "code": "MALFORMED_LINES", "level": "warn", "value": bad, "threshold": 0,
            "message": f"telemetry.jsonl 有 {bad} 行无法解析",
        })

    return {
        "schema_name": "skillmind-telemetry-summary",
        "schema_version": 1,
        "generated_at": _common.now_iso(),
        "store": str(store),
        "total_events": total,
        "malformed_lines": bad,
        "malformed_notes": notes[:20],
        "by_agent": _group(events, "agent_id"),
        "by_project": _group(events, "project_id"),
        "by_skill": _group(events, "skill_id"),
        "success_count": success,
        "success_rate": success_rate,
        "context_tokens_loaded": context_tokens,
        "result_tokens": result_tokens,
        "call_count": call_total,
        "calls_per_event": calls_per_event,
        "duplicate_calls": duplicates,
        "duplicate_calls_detail": duplicate_detail[:20],
        "cache_hit_count": cache_hits,
        "cache_hit_rate": cache_hit_rate,
        "avg_latency_ms": avg_latency,
        "latency_samples": len(latency_vals),
        "p0_evidence_lost": len(p0_lost),
        "p0_evidence_lost_events": p0_lost,
        "rework": rework_total,
        "error_class": error_class,
        "alerts": alerts,
    }


def _human_summary(p: dict[str, Any]) -> list[str]:
    lines = [
        _common.banner("SkillMind Telemetry Summary"),
        f"store                : {p['store']}",
        f"总事件数             : {p['total_events']}（坏行 {p['malformed_lines']}）",
        f"成功率               : {p['success_rate']}（{p['success_count']}/{p['total_events']}）",
        f"context_tokens_loaded: {p['context_tokens_loaded']}",
        f"result_tokens        : {p['result_tokens']}",
        f"call_count 合计      : {p['call_count']}（每次 {p['calls_per_event']}）",
        f"重复调用数           : {p['duplicate_calls']}",
        f"cache_hit 命中率     : {p['cache_hit_rate']}（{p['cache_hit_count']}）",
        f"平均延迟             : {p['avg_latency_ms']}ms（样本 {p['latency_samples']}）",
        f"rework 合计          : {p['rework']}",
        f"P0 证据丢失          : {p['p0_evidence_lost']}  <- false 即 Hard Gate FAIL",
    ]
    for ev in p["p0_evidence_lost_events"]:
        lines.append(
            f"  ! line {ev['line']} ts={ev['ts']} skill={ev['skill_id']} "
            f"session={ev['session_id']} error_class={ev['error_class']}"
        )
    for name, key in (("agent", "by_agent"), ("project", "by_project"), ("skill", "by_skill")):
        lines.append(f"── by_{name} ──")
        for k, v in sorted(p[key].items()):
            lines.append(f"  {k}: calls={v['calls']} success_rate={v['success_rate']}")
    lines.append("── error_class ──")
    if p["error_class"]:
        for k, v in sorted(p["error_class"].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {k}: {v}")
    else:
        lines.append("  (none)")
    lines.append("── alerts ──")
    if p["alerts"]:
        for a in p["alerts"]:
            lines.append(f"  [{a['level'].upper()}] {a['code']}: {a['message']}")
    else:
        lines.append("  (none)")
    return lines


# ────────────────────────── 子命令 ──────────────────────────


def cmd_append(args: argparse.Namespace) -> int:
    try:
        event = json.loads(args.event_json)
    except ValueError as e:
        _common.eprint(f"[USAGE] --event-json 不是合法 JSON：{e}")
        return EXIT_USAGE
    if not isinstance(event, dict):
        _common.eprint("[USAGE] --event-json 顶层须为 JSON object")
        return EXIT_USAGE

    schema = load_schema()
    if schema is None:
        return EXIT_USAGE

    errors = validate_instance(event, schema)
    if errors:
        payload = {
            "schema_name": "skillmind-telemetry-append",
            "ok": False,
            "store": str(resolve_store(args.store)),
            "errors": errors,
        }
        _common.emit(payload, args.json, [
            _common.banner("Telemetry Append — SCHEMA FAIL"),
            *[f"  [FAIL] {e}" for e in errors],
            f"共 {len(errors)} 项不合 {SCHEMA_REL}；未落盘。",
        ])
        return EXIT_INVALID

    # 值形态脱敏恒开；--no-redact 只关键名规则
    stored, redacted = redact_event(event, key_redaction=bool(args.redact))
    post_errors = validate_instance(stored, schema)

    store = resolve_store(args.store)
    store.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(stored, ensure_ascii=False)
    with store.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    payload = {
        "schema_name": "skillmind-telemetry-append",
        "ok": True,
        "store": str(store),
        "redact": bool(args.redact),
        "value_patterns_always_on": True,
        "redacted": sorted(set(redacted)),
        "redacted_count": len(redacted),
        "post_redact_schema_ok": not post_errors,
        "post_redact_errors": post_errors,
    }
    _common.emit(payload, args.json, [
        _common.banner("Telemetry Append — OK"),
        f"store    : {store}",
        f"redact   : 键名={payload['redact']} 值形态=True（恒开，不可关闭）",
        f"打码字段 : {', '.join(payload['redacted']) if payload['redacted'] else '(none)'}",
    ])
    return EXIT_OK


def cmd_summary(args: argparse.Namespace) -> int:
    store = resolve_store(args.store)
    if not store.exists():
        if args.store:
            _common.eprint(f"[USAGE] --store 指向的遥测文件不存在：{store}")
            return EXIT_USAGE
        events, bad, notes = [], 0, []
    else:
        events, bad, notes = _iter_lines(store)

    payload = build_summary(events, store, bad, notes)
    _common.emit(payload, args.json, _human_summary(payload))

    if args.strict and any(a["level"] == "critical" for a in payload["alerts"]):
        return EXIT_INVALID
    return EXIT_OK


# ────────────────────────── CLI ──────────────────────────


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="telemetry.py",
        description="SkillMind 遥测落盘与聚合（spec-v2 §14.5 / §23）",
    )
    sub = ap.add_subparsers(dest="cmd")

    p_append = sub.add_parser("append", help="校验并追加一条遥测事件")
    p_append.add_argument("--event-json", required=True, help="事件 JSON 字符串")
    p_append.add_argument("--store", default=None, help="存储路径或目录；默认 <repo>/.skillmind/telemetry.jsonl")
    p_append.add_argument(
        "--no-redact",
        dest="redact",
        action="store_false",
        help="关闭键名脱敏（仅排障看字段名用，禁进 CI）；值形态脱敏不可关闭",
    )
    p_append.add_argument("--json", action="store_true")
    p_append.set_defaults(redact=True, func=cmd_append)

    p_sum = sub.add_parser("summary", help="聚合遥测指标")
    p_sum.add_argument("--store", default=None, help="存储路径或目录；默认 <repo>/.skillmind/telemetry.jsonl")
    p_sum.add_argument("--strict", action="store_true", help="存在 critical 告警时退出码 1（CI 用）")
    p_sum.add_argument("--json", action="store_true")
    p_sum.set_defaults(func=cmd_summary)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        return args.func(args)
    except FileNotFoundError as e:
        _common.eprint(f"[ENV] {e}")
        return EXIT_USAGE
    except OSError as e:
        _common.eprint(f"[ENV] IO 失败：{e}")
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
