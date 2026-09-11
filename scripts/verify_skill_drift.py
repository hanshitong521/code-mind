#!/usr/bin/env python3
"""verify_skill_drift.py — 三层漂移检测（Peak v3 §6.2 Drift Check / DOC3-03）

检测链：
    canonical  →  release copy  →  installed copy

输出四种结论（§6.2）：
    PASS       三层哈希一致
    DRIFT      哈希不一致（禁止静默覆盖）
    MISSING    声明存在但磁盘缺失
    UNTRACKED  磁盘存在但 manifest 未声明

用法：
  python scripts/verify_skill_drift.py                          # 只查 canonical vs release
  python scripts/verify_skill_drift.py --installed <dir>        # 再查 release vs installed
  python scripts/verify_skill_drift.py --json
  python scripts/verify_skill_drift.py --canonical-root <外部canonical仓路径>

退出码：0=全 PASS；1=存在 DRIFT/MISSING/UNTRACKED。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _release_lib import (  # noqa: E402
    MANIFEST_REL,
    hash_file,
    hash_tree,
    load_yaml,
    repo_root,
)

PASS, DRIFT, MISSING, UNTRACKED = "PASS", "DRIFT", "MISSING", "UNTRACKED"


def _resolve_external_canonical(
    canonical_root: Path, spec: dict, external_sources: dict
) -> Path:
    """把外部 canonical 定位到具体路径。

    manifest 中 source_path 是「相对 canonical 仓根」的路径，而 source_repo 是
    `owner/name` 形式的仓标识。因此需要先落到仓目录，再拼 source_path：

        <canonical_root>/<repo-dir>/<source_path>

    仓目录名的优先级：
      1. external_sources[key].local_path （显式声明，最稳）
      2. source_repo 的最后一段（owner/name -> name）
      3. 空（退回 canonical_root 本身）
    """
    src_repo = spec.get("source_repo") or ""

    repo_dir = ""
    for _, es in (external_sources or {}).items():
        if es.get("repo") == src_repo:
            repo_dir = es.get("local_path") or ""
            break
    if not repo_dir and src_repo:
        repo_dir = src_repo.rsplit("/", 1)[-1]

    src_path = spec.get("source_path") or ""
    if repo_dir:
        return canonical_root / repo_dir / src_path
    return canonical_root / src_path


def verify(root: Path, installed: Path | None, canonical_root: Path | None) -> dict:
    manifest = load_yaml(root / MANIFEST_REL)
    external_sources = manifest.get("external_sources") or {}
    exclude = (manifest.get("hash") or {}).get("normalize", {}).get("exclude", [])
    findings: list[dict] = []

    declared_artifacts: set[str] = set()

    for name, spec in (manifest.get("skills") or {}).items():
        artifact_rel = spec.get("artifact_path")
        declared_artifacts.add(artifact_rel)
        artifact = root / artifact_rel

        # ── 层 1：release 是否存在 ──
        if not artifact.exists():
            findings.append({
                "skill": name, "layer": "release", "verdict": MISSING,
                "path": artifact_rel, "detail": "artifact_path 不存在",
            })
            continue

        rel_hash = hash_tree(artifact, exclude=exclude)["content_hash"]
        recorded = spec.get("content_hash")

        # ── 层 2：canonical vs release ──
        if spec.get("status") == "CANONICAL_LOCAL":
            # canonical 即本仓该目录 → 与 manifest 记录比对
            if recorded is None:
                findings.append({
                    "skill": name, "layer": "canonical_vs_release", "verdict": UNTRACKED,
                    "path": artifact_rel,
                    "detail": "manifest 未记录 content_hash（先跑 build_release.py）",
                })
            elif recorded != rel_hash:
                findings.append({
                    "skill": name, "layer": "canonical_vs_release", "verdict": DRIFT,
                    "path": artifact_rel,
                    "detail": f"记录 {recorded} != 实际 {rel_hash}",
                })
            else:
                findings.append({
                    "skill": name, "layer": "canonical_vs_release", "verdict": PASS,
                    "path": artifact_rel, "detail": "canonical == release",
                })

        elif spec.get("status") == "VENDORED_RELEASE_COPY":
            src_repo = spec.get("source_repo")
            if canonical_root:
                cand = _resolve_external_canonical(
                    canonical_root, spec, external_sources
                )
                # compare 语义：默认整目录；single_file 时只比一个文件
                cmp_spec = spec.get("compare") or {}
                cmp_mode = cmp_spec.get("mode", "tree")

                if cmp_mode == "single_file":
                    can_file = cmp_spec.get("canonical_file") or spec.get("source_path") or "SKILL.md"
                    rel_file = cmp_spec.get("release_file") or "SKILL.md"
                    cand = cand / can_file if cand.is_dir() else cand
                    rel_target = artifact / rel_file
                    if not cand.exists() or not rel_target.exists():
                        miss = cand if not cand.exists() else rel_target
                        findings.append({
                            "skill": name, "layer": "canonical_vs_release", "verdict": MISSING,
                            "path": str(miss), "detail": "single_file 比对路径不存在",
                        })
                        continue
                    can_hash = hash_file(cand, exclude=exclude)
                    rel_hash_cmp = hash_file(rel_target, exclude=exclude)
                    if can_hash != rel_hash_cmp:
                        findings.append({
                            "skill": name, "layer": "canonical_vs_release", "verdict": DRIFT,
                            "path": rel_file,
                            "detail": f"canonical({src_repo}) {can_hash} != release {rel_hash_cmp} [{rel_file}]",
                        })
                    else:
                        findings.append({
                            "skill": name, "layer": "canonical_vs_release", "verdict": PASS,
                            "path": rel_file, "detail": f"canonical == release [{rel_file}]",
                        })
                    continue

                if cand.exists():
                    can_hash = hash_tree(cand, exclude=exclude)["content_hash"]
                    if can_hash != rel_hash:
                        findings.append({
                            "skill": name, "layer": "canonical_vs_release", "verdict": DRIFT,
                            "path": artifact_rel,
                            "detail": f"canonical({src_repo}) {can_hash} != release {rel_hash}",
                        })
                    else:
                        findings.append({
                            "skill": name, "layer": "canonical_vs_release", "verdict": PASS,
                            "path": artifact_rel, "detail": "canonical == release",
                        })
                else:
                    findings.append({
                        "skill": name, "layer": "canonical_vs_release", "verdict": MISSING,
                        "path": str(cand), "detail": "canonical 路径不存在",
                    })
            else:
                findings.append({
                    "skill": name, "layer": "canonical_vs_release", "verdict": UNTRACKED,
                    "path": artifact_rel,
                    "detail": f"外部 canonical({src_repo}) 未提供 --canonical-root，跳过比对",
                })

        # ── 层 3：release vs installed ──
        if installed:
            inst = installed / name
            if not inst.exists():
                findings.append({
                    "skill": name, "layer": "release_vs_installed", "verdict": MISSING,
                    "path": str(inst), "detail": "未安装",
                })
            else:
                inst_hash = hash_tree(inst, exclude=exclude)["content_hash"]
                if inst_hash != rel_hash:
                    findings.append({
                        "skill": name, "layer": "release_vs_installed", "verdict": DRIFT,
                        "path": str(inst),
                        "detail": f"release {rel_hash} != installed {inst_hash}",
                    })
                else:
                    findings.append({
                        "skill": name, "layer": "release_vs_installed", "verdict": PASS,
                        "path": str(inst), "detail": "release == installed",
                    })

    # ── UNTRACKED：磁盘有但 manifest 没声明 ──
    skills_dir = root / "skills"
    if skills_dir.exists():
        for d in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            rel = f"skills/{d.name}"
            if rel not in declared_artifacts:
                findings.append({
                    "skill": d.name, "layer": "manifest", "verdict": UNTRACKED,
                    "path": rel, "detail": "磁盘存在但 release-manifest 未声明",
                })

    summary = {v: sum(1 for f in findings if f["verdict"] == v)
               for v in (PASS, DRIFT, MISSING, UNTRACKED)}
    return {"findings": findings, "summary": summary,
            "ok": summary[DRIFT] == 0 and summary[MISSING] == 0}


def main() -> int:
    ap = argparse.ArgumentParser(description="Skill 三层漂移检测")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--installed", type=Path, default=None,
                    help="业务仓 .cursor/skills 目录（启用 installed 层比对）")
    ap.add_argument("--canonical-root", type=Path, default=None,
                    help="外部 canonical 仓路径（启用跨仓比对）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = args.root or repo_root()
    payload = verify(root, args.installed, args.canonical_root)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for f in payload["findings"]:
            print(f"[{f['verdict']:<9}] {f['skill']:<16} {f['layer']:<22} {f['detail']}")
        s = payload["summary"]
        print(f"\nPASS={s[PASS]} DRIFT={s[DRIFT]} MISSING={s[MISSING]} UNTRACKED={s[UNTRACKED]}")
        if s[DRIFT]:
            print("\n⚠ DRIFT 不允许静默覆盖。请显式选择其一：", file=sys.stderr)
            print("  - 更新发布副本 (build_release.py)", file=sys.stderr)
            print("  - 回滚安装副本 (install.ps1 -Rollback)", file=sys.stderr)
            print("  - supersede canonical (改 canonical 后重跑)", file=sys.stderr)

    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
