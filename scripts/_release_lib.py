#!/usr/bin/env python3
"""P0 发布控制面 —— 共享底层：哈希、清单装载、YAML 读写。

所有 P0 脚本必须共用本模块，禁止各自实现哈希/归一化逻辑，
否则会出现「build 算一个哈希、verify 算另一个」的假 drift。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

MANIFEST_REL = "shared/release-manifest.yaml"
SCHEMA_VERSIONS_REL = "shared/schema-versions.yaml"
CAPABILITY_REGISTRY_REL = "shared/capability-registry.yaml"
BUNDLE_REL = "deploy.bundle.yaml"

#: 不参与 content_hash 的目录名。
#:
#: 前三个是 VCS / 解释器缓存 / 依赖目录。
#: 后两个是**生成物**目录：`.codehealth/` 是 CodeHealthMind 的运行产物（报告、ledger、
#: 缓存），`reports/` 是验收脚本的输出。它们每次运行都会变，算进哈希只会让 CI 里的
#: `--check` 反复报假 DRIFT。content_hash 描述源码，不描述「上一次跑出来的报告」。
IGNORED_DIR_PARTS: frozenset[str] = frozenset(
    {".git", "__pycache__", "node_modules", ".codehealth", "reports"}
)


def repo_root() -> Path:
    """本仓根 = scripts/ 的父目录。"""
    return Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"缺少文件: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def dump_yaml(path: Path, data: dict) -> None:
    """回写 YAML，保留 UTF-8 且不转义中文。"""
    text = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100
    )
    path.write_text(text, encoding="utf-8")


def normalize_bytes(raw: bytes, exclude: list[str] | None = None, name: str = "") -> bytes:
    """哈希归一化：CRLF→LF、去行尾空白。

    目的：同一份内容在 Windows(CRLF) 与 Linux(LF) 下算出同一哈希，
    避免跨平台假 drift。
    """
    if exclude and name and name in exclude:
        return raw
    text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    return "\n".join(lines).encode("utf-8")


def hash_tree(root: Path, exclude: list[str] | None = None) -> dict[str, Any]:
    """对目录（或单文件）计算确定性哈希。

    目录哈希 = 对「相对路径排序后的 file:hash 行」再做一次 sha256，
    保证文件顺序变化不影响结果。

    生成物目录（见 ``GENERATED_DIR_PARTS``）不参与哈希：它们是**每次运行都会变**的
    输出，把它们算进 content_hash 只会让 CI 里的 ``--check`` 反复报假 DRIFT。
    内容哈希应该描述「源码」，不是「上一次跑出来的报告」。
    """
    exclude = exclude or []
    entries: list[tuple[str, str]] = []

    if root.is_file():
        files = [root]
        base = root.parent
    else:
        files = sorted(p for p in root.rglob("*") if p.is_file())
        base = root

    for f in files:
        rel = f.relative_to(base).as_posix()
        if rel in exclude or f.name in exclude:
            continue
        # 跳过 VCS / 缓存 / 生成物目录
        if any(part in IGNORED_DIR_PARTS for part in f.parts):
            continue
        raw = f.read_bytes()
        norm = normalize_bytes(raw, exclude=exclude, name=f.name)
        entries.append((rel, hashlib.sha256(norm).hexdigest()))

    entries.sort(key=lambda t: t[0])
    joined = "\n".join(f"{rel}:{h}" for rel, h in entries).encode("utf-8")
    return {
        "content_hash": "sha256:" + hashlib.sha256(joined).hexdigest(),
        "file_count": len(entries),
        "files": [{"path": rel, "hash": h} for rel, h in entries],
    }


def hash_file(path: Path, exclude: list[str] | None = None) -> str:
    raw = path.read_bytes()
    norm = normalize_bytes(raw, exclude=exclude, name=path.name)
    return "sha256:" + hashlib.sha256(norm).hexdigest()


def find_installed_skill_dirs(target_dir: Path, skill: str) -> list[Path]:
    """在业务仓 .cursor/skills/ 下定位安装副本（可能是 junction 或实体目录）。"""
    cand = target_dir / skill
    return [cand] if cand.exists() else []
