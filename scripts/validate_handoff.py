#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_handoff.py — Handoff 结构化契约校验器

校验 Handoff 实例（YAML/键值块）是否符合 shared/handoff-schema.yaml 定义的字段契约。
零外部依赖（仅 Python 标准库）。

用法:
  python scripts/validate_handoff.py                          # 校验 handoff-template.md 中的示例
  python scripts/validate_handoff.py path/to/handoff.yaml     # 校验独立 YAML 文件
  python scripts/validate_handoff.py path/to/markdown.md      # 校验 markdown 中的 ```yaml 块

退出码: 0=全部通过, 1=有失败
"""
import os
import re
import sys
from pathlib import Path

# ── Schema 定义（与 shared/handoff-schema.yaml 同步；本处为机器可执行权威源）──
# 修改时须同步更新 shared/handoff-schema.yaml
SCHEMA = {
    "design_to_code": {
        "required": ["变更面", "plan路径", "范围", "验收", "验证档位", "建议下一步"],
        "enum_fields": {
            "验证档位": ["micro-fix", "local-fix", "surface", "pr-ready", "release"],
            "建议下一步": ["/ai-design", "/ai-code", "/ai-debug", "无"],
        },
    },
    "design_to_test": {
        "required": ["plan路径", "只验SQL或含API", "测试库写操作", "建议下一步"],
        "enum_fields": {
            "只验SQL或含API": ["只验SQL", "含API"],
            "建议下一步": ["/ai-design", "/ai-code", "/ai-debug", "无"],
        },
    },
    "code_to_test": {
        "required": ["变更面", "plan引用", "已跑验证", "未跑验证", "建议下一步"],
        "enum_fields": {
            "建议下一步": ["/ai-design", "/ai-code", "/ai-debug", "无"],
        },
    },
    "test_to_design": {
        "required": ["结论", "证据", "建议", "建议下一步"],
        "enum_fields": {
            "结论": ["SQL证伪", "SQL证实Bug", "全部PASS"],
            "建议下一步": ["/ai-design", "/ai-code", "/ai-debug", "无"],
        },
    },
}

# Handoff 类型识别关键词（出现在 ```yaml 块首行或文件首部）
TYPE_MARKERS = {
    "design_to_code": ["设计 Handoff → 编码", "设计 Handoff → 代码", "design_to_code"],
    "design_to_test": ["设计 Handoff → 测试", "design_to_test"],
    "code_to_test": ["编码 Handoff", "code_to_test"],
    "test_to_design": ["测试 Handoff → 设计", "test_to_design"],
}


def parse_kv_block(text):
    """从文本中解析 'key: value' 形式的键值对（兼容简单 YAML 子集）。"""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^([^:：]+)[：:]\s*(.*)$', line)
        if m:
            key = m.group(1).strip()
            val = m.group(2)
            # 剥离行内注释（ # ...），但保留引号内的 #
            if ' #' in val and not (val.strip().startswith('"') or val.strip().startswith("'")):
                val = re.split(r'\s+#', val, maxsplit=1)[0]
            elif ' #' in val:
                # 引号包裹的值，仅当 # 在引号外才剥离（简单处理）
                val = re.split(r'(?<!\\)\s+#', val, maxsplit=1)[0]
            val = val.strip().strip('"').strip("'")
            if key:
                result[key] = val
    return result


def detect_handoff_type(text):
    """根据文本特征判断 Handoff 类型。"""
    for htype, markers in TYPE_MARKERS.items():
        for marker in markers:
            if marker in text:
                return htype
    # 兜底：按字段推断
    keys = set(parse_kv_block(text).keys())
    if {"变更面", "plan路径", "验收"} <= keys:
        return "design_to_code"
    if {"plan路径", "只验SQL或含API"} <= keys:
        return "design_to_test"
    if {"plan引用", "已跑验证", "未跑验证"} <= keys:
        return "code_to_test"
    if {"结论", "证据", "建议"} <= keys and "SQL" in text:
        return "test_to_design"
    return None


def extract_yaml_blocks(markdown_text):
    """从 markdown 中提取 ```yaml 或 ``` 代码块。"""
    blocks = []
    pattern = re.compile(r'```(?:ya?ml)?\s*\n(.*?)```', re.DOTALL)
    for m in pattern.finditer(markdown_text):
        block_text = m.group(1)
        # 只保留看起来像 Handoff 的块（含至少 2 个 key: value 行）
        kv = parse_kv_block(block_text)
        if len(kv) >= 2:
            blocks.append(block_text)
    return blocks


def validate_one(handoff_text, source_label=""):
    """校验单个 Handoff 文本块。返回 (passed, issues)。"""
    issues = []
    htype = detect_handoff_type(handoff_text)
    if htype is None:
        issues.append(f"[{source_label}] 无法识别 Handoff 类型（缺类型标记且字段不匹配任何 schema）")
        return False, issues

    kv = parse_kv_block(handoff_text)
    schema = SCHEMA[htype]

    # 必填字段检查
    for field in schema["required"]:
        if field not in kv or not kv[field]:
            issues.append(f"[{source_label}] {htype}: 缺必填字段「{field}」")

    # 枚举值检查
    for field, allowed in schema["enum_fields"].items():
        if field in kv and kv[field] and kv[field] not in allowed:
            issues.append(
                f"[{source_label}] {htype}: 字段「{field}」值「{kv[field]}」不在允许枚举 {allowed} 中"
            )

    # 通用约束：建议下一步 必须在枚举内（已在 enum_fields 覆盖）
    return len(issues) == 0, issues


def _extract_yaml_from_md(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"```ya?ml\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not blocks:
        raise ValueError("no yaml block in markdown")
    return blocks[0]


def _infer_allow_globs(范围: str, 变更面: str) -> list[str]:
    globs: list[str] = []
    blob = f"{范围} {变更面}".lower()
    if "shejiu-product" in blob or "product" in blob:
        globs.append("shejiu-modules/shejiu-product/**")
    if "shejiu-order" in blob or "order" in blob:
        globs.append("shejiu-modules/shejiu-order/**")
    if "shejiu-auth" in blob:
        globs.append("shejiu-modules/shejiu-auth/**")
    return globs


def handoff_to_bundle(kv: dict) -> dict:
    goal = kv.get("假设") or kv.get("范围") or "Implement handoff scope"
    bundle = {
        "version": 1,
        "intent": {
            "goal": goal[:500],
            "background": (kv.get("变更面") or "")[:800],
            "success": (kv.get("验收") or "")[:800],
        },
        "spec": {
            "allow_globs": _infer_allow_globs(kv.get("范围", ""), kv.get("变更面", "")),
            "deny_globs": [],
            "forbidden_actions": [],
        },
        "plan": {"steps": [], "plan_ref": kv.get("plan路径") or kv.get("plan引用") or ""},
        "eval": {"commands": [], "acceptance": (kv.get("验收") or "")[:800]},
        "meta": {"source": "handoff", "handoff_type": "design_to_code"},
    }
    if kv.get("规则演进") and kv.get("规则演进") != "无":
        bundle["spec"]["forbidden_actions"].append(f"Policy gap noted: {kv['规则演进'][:200]}")
    return bundle


def cmd_to_bundle(argv: list[str]) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="validate_handoff.py to-bundle")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path(".contextmind/task.active.json"))
    args = ap.parse_args(argv)
    src = args.input
    if not src.exists():
        print(f"missing {src}", file=sys.stderr)
        return 1
    yaml_text = _extract_yaml_from_md(src) if src.suffix.lower() in (".md", ".markdown") else src.read_text(encoding="utf-8")
    kv = parse_kv_block(yaml_text)
    bundle = handoff_to_bundle(kv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "to-bundle":
        return cmd_to_bundle(sys.argv[2:])

    root = Path(__file__).resolve().parent.parent
    all_issues = []
    total = 0
    passed = 0

    if len(sys.argv) > 1:
        # 校验指定文件
        for target in sys.argv[1:]:
            tpath = Path(target)
            if not tpath.is_absolute():
                tpath = root / target
            if not tpath.exists():
                all_issues.append(f"[{target}] 文件不存在")
                total += 1
                continue
            text = tpath.read_text(encoding="utf-8")
            if tpath.suffix in (".md",):
                blocks = extract_yaml_blocks(text)
                if not blocks:
                    all_issues.append(f"[{target}] 未找到 YAML 代码块")
                    total += 1
                    continue
                for i, blk in enumerate(blocks):
                    total += 1
                    ok, iss = validate_one(blk, f"{target}#block{i+1}")
                    if ok:
                        passed += 1
                    else:
                        all_issues.extend(iss)
            else:
                total += 1
                ok, iss = validate_one(text, target)
                if ok:
                    passed += 1
                else:
                    all_issues.extend(iss)
    else:
        # 默认校验 handoff-template.md
        template = root / "skills" / "ai-design" / "references" / "handoff-template.md"
        if template.exists():
            text = template.read_text(encoding="utf-8")
            blocks = extract_yaml_blocks(text)
            for i, blk in enumerate(blocks):
                total += 1
                ok, iss = validate_one(blk, f"handoff-template.md#block{i+1}")
                if ok:
                    passed += 1
                else:
                    all_issues.extend(iss)
        # 也校验 schema 自身示例不存在时跳过

    print(f"[validate_handoff] 校验 {total} 个 Handoff 实例，{passed} 通过，{total - passed} 失败")
    if all_issues:
        for iss in all_issues:
            print(f"  FAIL: {iss}")
        return 1
    print("  全部通过 [OK]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
