#!/usr/bin/env python3
"""manifest_validate.py — skill.yaml 的零依赖校验器（spec-v2 §8 / §17）。

校验器**复用 _common.validate_instance**（唯一实现，与 telemetry 同源），
不引入 jsonschema 包。支持的关键字与注解见 _common.SCHEMA_KEYWORDS /
SCHEMA_ANNOTATIONS；未支持的关键字 → warnings（提示 schema 作者该关键字未生效，禁静默）。

用法：
  python3 scripts/manifest_validate.py --path skills/ai-skill-mcp-Y/skill.yaml [--schema P] [--json]

退出码：0 = 校验通过；1 = 校验失败；2 = 用法或环境错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SCHEMA_NAME = "skillmind-manifest-validation"
DEFAULT_SCHEMA = C.SKILL_DIR / "schemas" / "skill-manifest.schema.json"


def _split(line: str) -> dict:
    """`"$.path: message"` → `{"path": "$.path", "message": "message"}`。

    _common 的校验器按 `path: message` 出串（与 telemetry 同口径）；本命令的对外
    payload 保留结构化 {path, message}，故在此拆一次。path 段不含 ": "，拆分安全。
    """
    path, _, message = str(line).partition(": ")
    return {"path": path, "message": message}


def load_document(path: Path) -> Any:
    """按后缀装载：.json 走 json，其余走 _common（优先 PyYAML，缺失回落 _yaml_lite）。"""
    if path.suffix == ".json":
        return C.load_json(path, default=None)
    return C.load_yaml(path)


def render_human(payload: dict) -> list:
    lines = [
        C.banner("SkillMind Manifest Validate"),
        f"path     : {payload['path']}",
        f"schema   : {payload['schema']}",
        f"result   : {'PASS' if payload['ok'] else 'FAIL'}",
        f"errors   : {len(payload['errors'])}",
        f"warnings : {len(payload['warnings'])}",
    ]
    for e in payload["errors"]:
        lines.append(f"  ERROR {e['path']}: {e['message']}")
    for w in payload["warnings"]:
        lines.append(f"  WARN  {w['path']}: {w['message']}")
    return lines


def main(argv: Any = None) -> int:
    ap = argparse.ArgumentParser(
        prog="manifest_validate.py",
        description="校验 skill.yaml 是否符合 skill-manifest.schema.json（零依赖）",
    )
    ap.add_argument("--path", required=True, help="待校验的 skill.yaml（或 .json）")
    ap.add_argument("--schema", default=None, help=f"schema 路径（默认 {DEFAULT_SCHEMA}）")
    ap.add_argument("--json", action="store_true", help="以 JSON 打印到 stdout")
    args = ap.parse_args(argv)

    doc_path = Path(args.path).expanduser()
    schema_path = Path(args.schema).expanduser() if args.schema else DEFAULT_SCHEMA
    if not doc_path.is_file():
        C.eprint(f"ERROR: 待校验文件不存在: {doc_path}")
        return 2
    if not schema_path.is_file():
        C.eprint(f"ERROR: schema 文件不存在: {schema_path}")
        return 2

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        C.eprint(f"ERROR: schema 不是合法 JSON: {schema_path} ({exc})")
        return 2
    if not isinstance(schema, dict):
        C.eprint(f"ERROR: schema 顶层必须是对象: {schema_path}")
        return 2

    try:
        document = load_document(doc_path)
    except Exception as exc:
        C.eprint(f"ERROR: 无法解析 {doc_path}: {type(exc).__name__}: {exc}")
        return 2
    if document is None:
        C.eprint(f"ERROR: 文档为空或解析失败: {doc_path}")
        return 2

    errors = [_split(e) for e in C.validate_instance(document, schema)]
    warnings = [_split(w) for w in C.schema_keyword_warnings(schema)]

    payload = {
        "schema_name": SCHEMA_NAME,
        "schema_version": C.SCHEMA_VERSION,
        "path": doc_path.as_posix(),
        "schema": schema_path.as_posix(),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    C.emit(payload, as_json=args.json, human=render_human(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
