#!/usr/bin/env python3
"""validate_bundle.py — 发布包一致性校验（Peak v3 DOC3-03 配套）

校验项：
  1. deploy.bundle.yaml 的 skills 列表 ⊆ release-manifest 声明的 skills
  2. 每个 bundle skill 的目录与 SKILL.md 存在
  3. release-manifest 声明的 artifact_path 全部存在
  4. capability-registry 的 owner 合法、phase 合法、skill 引用存在
  5. schema-versions 引用的文件存在，且契约文件里 schema_name 对得上
  6. deploy.bundle.yaml 的 release 段指针文件存在
  7. legacy_skill_names 与 skills 不重叠（重叠会导致装完即被当成 legacy 清掉）

用法：
  python scripts/validate_bundle.py [--json] [--root <path>]
退出码：0=全通过；1=有错误（WARN 不影响退出码）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _release_lib import (  # noqa: E402
    BUNDLE_REL,
    CAPABILITY_REGISTRY_REL,
    MANIFEST_REL,
    SCHEMA_VERSIONS_REL,
    load_yaml,
    repo_root,
)

VALID_OWNERS = {
    "requirement-mind", "project-brain-agent", "token-mind",
    "test-mind", "concise-mind", "ai-programming-docs", "git",
}
VALID_PHASES = {"requirement", "design", "coding", "debug", "verification",
                "review", "all"}


def validate(root: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    # ── 装载 ──
    bundle = load_yaml(root / BUNDLE_REL)
    manifest = load_yaml(root / MANIFEST_REL)
    registry = load_yaml(root / CAPABILITY_REGISTRY_REL)
    schema_versions = load_yaml(root / SCHEMA_VERSIONS_REL)

    bundle_skills = list(bundle.get("skills") or [])
    manifest_skills = dict(manifest.get("skills") or {})

    # ── 1. bundle ⊆ manifest ──
    for s in bundle_skills:
        if s not in manifest_skills:
            errors.append(f"[bundle] skill '{s}' 在 deploy.bundle.yaml 中但 release-manifest 未声明")
    for s in manifest_skills:
        if s not in bundle_skills:
            warnings.append(f"[manifest] skill '{s}' 已声明但未进 deploy.bundle.yaml（不会分发）")

    # ── 2. skill 目录与 SKILL.md ──
    for s in bundle_skills:
        d = root / "skills" / s
        if not d.exists():
            errors.append(f"[dir] skills/{s} 不存在")
        elif not (d / "SKILL.md").exists():
            errors.append(f"[file] skills/{s}/SKILL.md 不存在")

    # ── 3. artifact_path 存在 ──
    for name, spec in manifest_skills.items():
        ap = spec.get("artifact_path")
        if ap and not (root / ap).exists():
            errors.append(f"[artifact] {name}: artifact_path '{ap}' 不存在")

    # ── 4. capability-registry ──
    caps = registry.get("capabilities") or {}
    if not caps:
        errors.append("[registry] capabilities 为空")
    for cap, spec in caps.items():
        owner = spec.get("owner")
        if owner not in VALID_OWNERS:
            errors.append(f"[registry] {cap}: 非法 owner '{owner}'")
        phase = spec.get("phase", "")
        for ph in str(phase).split(","):
            if ph.strip() and ph.strip() not in VALID_PHASES:
                errors.append(f"[registry] {cap}: 非法 phase '{ph.strip()}'")
        sk = spec.get("skill")
        if sk and sk not in bundle_skills:
            errors.append(f"[registry] {cap}: 引用 skill '{sk}' 不在 bundle 中")

    for ph, cap_list in (registry.get("phases") or {}).items():
        if ph not in VALID_PHASES:
            errors.append(f"[registry] phases 段出现非法阶段 '{ph}'")
        for c in cap_list:
            if c not in caps:
                errors.append(f"[registry] phases.{ph} 引用了未定义能力 '{c}'")

    # ── 5. schema-versions ──
    for cname, spec in (schema_versions.get("contracts") or {}).items():
        f = spec.get("file")
        if not f:
            errors.append(f"[schema-versions] {cname}: 缺 file")
            continue
        p = root / f
        if not p.exists():
            errors.append(f"[schema-versions] {cname}: 文件 '{f}' 不存在")
            continue
        # 契约文件里的 schema_name 必须与注册表 key / 声明一致
        try:
            doc = load_yaml(p)
            declared = doc.get("schema_name")
            if declared and declared != cname:
                errors.append(f"[schema-versions] {cname}: 文件内 schema_name='{declared}' 不一致")
            if not declared and p.suffix in (".yaml", ".yml"):
                warnings.append(f"[schema-versions] {cname}: 文件 '{f}' 未声明 schema_name（§30 要求）")
        except Exception as e:  # yaml 解析失败
            errors.append(f"[schema-versions] {cname}: 解析 '{f}' 失败 - {e}")

    # ── 6. bundle release 指针 ──
    rel = bundle.get("release") or {}
    for key in ("manifest", "capability_registry", "schema_versions"):
        v = rel.get(key)
        if v and not (root / v).exists():
            errors.append(f"[bundle.release] {key}='{v}' 不存在")

    # ── 7. legacy 与 skills 重叠 ──
    legacy = set(bundle.get("legacy_skill_names") or [])
    overlap = legacy & set(bundle_skills)
    for s in sorted(overlap):
        errors.append(f"[bundle] '{s}' 同时出现在 skills 与 legacy_skill_names（装完即被清）")

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "stats": {"bundle_skills": len(bundle_skills),
                      "manifest_skills": len(manifest_skills),
                      "capabilities": len(caps),
                      "contracts": len(schema_versions.get("contracts") or {})}}


def main() -> int:
    ap = argparse.ArgumentParser(description="发布包一致性校验")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = args.root or repo_root()
    payload = validate(root)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        st = payload["stats"]
        print(f"bundle_skills={st['bundle_skills']} manifest_skills={st['manifest_skills']} "
              f"capabilities={st['capabilities']} contracts={st['contracts']}")
        for w in payload["warnings"]:
            print(f"[WARN] {w}")
        for e in payload["errors"]:
            print(f"[FAIL] {e}", file=sys.stderr)
        print("\nvalidate_bundle: " + ("PASS" if payload["ok"] else f"FAIL ({len(payload['errors'])})"))

    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
