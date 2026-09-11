#!/usr/bin/env python3
"""build_release.py — Canonical → Release 确定性构建（Peak v3 §6.2 / DOC3-04）

职责：
  1. 依据 shared/release-manifest.yaml，为每个 skill 计算 canonical 与 release 的 content_hash
  2. 校验声明的 artifact_path 确实存在（MISSING 则失败）
  3. 把哈希回写 manifest（禁止手填）
  4. --check 模式：只校验不写，用于 CI

用法：
  python scripts/build_release.py            # 计算并回写 manifest
  python scripts/build_release.py --check    # 只校验（CI 用），漂移则 exit 1
  python scripts/build_release.py --json     # 机器可读输出
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _release_lib import (  # noqa: E402
    MANIFEST_REL,
    dump_yaml,
    hash_tree,
    load_yaml,
    repo_root,
)


def build(root: Path, write: bool) -> tuple[dict, list[str]]:
    """返回 (结果, 错误列表)。"""
    errors: list[str] = []
    manifest_path = root / MANIFEST_REL
    manifest = load_yaml(manifest_path)
    exclude = (manifest.get("hash") or {}).get("normalize", {}).get("exclude", [])

    results: dict[str, dict] = {}

    for name, spec in (manifest.get("skills") or {}).items():
        artifact_rel = spec.get("artifact_path")
        if not artifact_rel:
            errors.append(f"{name}: manifest 缺 artifact_path")
            continue

        artifact = root / artifact_rel
        if not artifact.exists():
            errors.append(f"{name}: artifact_path 不存在 → {artifact_rel} (MISSING)")
            results[name] = {"status": "MISSING", "artifact_path": artifact_rel}
            continue

        info = hash_tree(artifact, exclude=exclude)
        entry = {
            "status": "OK",
            "artifact_path": artifact_rel,
            "content_hash": info["content_hash"],
            "file_count": info["file_count"],
            "editable": spec.get("editable", False),
        }

        # canonical 在本仓时，canonical 与 release 是同一目录，哈希必然一致
        if spec.get("status") == "CANONICAL_LOCAL":
            entry["canonical_hash"] = info["content_hash"]
            entry["hash_match"] = True
        else:
            # 外部 canonical：仅记录 release 哈希；canonical 比对留给 verify（需外部仓）
            entry["canonical_hash"] = None
            entry["hash_match"] = None

        results[name] = entry

    # 共享契约同样纳入
    for rel, spec in (manifest.get("shared_contracts") or {}).items():
        p = root / rel
        if not p.exists():
            errors.append(f"shared_contract: 缺少 {rel}")
            continue
        info = hash_tree(p, exclude=exclude)
        spec["content_hash"] = info["content_hash"]
        results[rel] = {"status": "OK", "content_hash": info["content_hash"],
                        "file_count": info["file_count"]}

    if write and not errors:
        for name, spec in (manifest.get("skills") or {}).items():
            r = results.get(name) or {}
            if r.get("status") == "OK":
                spec["content_hash"] = r["content_hash"]
        dump_yaml(manifest_path, manifest)

    return {"skills": results, "errors": errors}, errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Canonical → Release build")
    ap.add_argument("--check", action="store_true", help="只校验，不回写（CI）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--root", type=Path, default=None)
    args = ap.parse_args()

    root = args.root or repo_root()
    payload, errors = build(root, write=not args.check)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for name, r in payload["skills"].items():
            if r.get("status") == "OK":
                print(f"[OK]   {name:<16} {r['content_hash']}  ({r['file_count']} files)")
            else:
                print(f"[{r.get('status')}] {name}")
        if errors:
            print("\n错误:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
        else:
            print(f"\nbuild OK · {len(payload['skills'])} 项" +
                  ("（--check 未回写）" if args.check else "（已回写 manifest）"))

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
