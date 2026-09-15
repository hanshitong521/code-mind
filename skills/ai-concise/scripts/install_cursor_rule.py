#!/usr/bin/env python3
"""安装 concise-mind 的 Cursor 常驻引导规则（零第三方依赖）。

    python scripts/install_cursor_rule.py --target user
    python scripts/install_cursor_rule.py --target project --project D:\\myproj
    python scripts/install_cursor_rule.py --target user --dry-run

同时检测同名 skill 冲突（~/.cursor/skills/concise-mind 若指向别的 skill，会造成加载次序不确定）。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

RULE_NAME = "concise-mind.mdc"
MARKER = "Concise-mind latch"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def stamp() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")


def rule_dest(target: str, project: str | None) -> Path:
    if target == "user":
        return Path.home() / ".cursor" / "rules" / RULE_NAME
    if not project:
        raise SystemExit("ERROR: --target project 需要 --project <路径>")
    return Path(project).expanduser().resolve() / ".cursor" / "rules" / RULE_NAME


def check_collision() -> list[str]:
    notes: list[str] = []
    for cand in (Path.home() / ".cursor" / "skills" / "concise-mind" / "SKILL.md",
                 Path.home() / ".cursor" / "skills" / "concise_mind" / "SKILL.md"):
        if not cand.exists():
            continue
        text = cand.read_text(encoding="utf-8", errors="ignore")
        if MARKER.lower() not in text.lower() and "Session-latched" not in text:
            notes.append(f"同名冲突: {cand} 内容是【另一个 skill】，与本 skill 同名 → Cursor 加载次序不确定，建议改名或归档。")
        else:
            notes.append(f"已存在同 skill: {cand}")
    if not notes:
        notes.append("未发现同名 skill 冲突。")
    return notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="install concise-mind cursor rule")
    ap.add_argument("--target", choices=["user", "project"], default="user")
    ap.add_argument("--project")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    src = repo_root() / "assets" / "cursor" / RULE_NAME
    if not src.exists():
        print(f"ERROR: 源文件不存在 {src}")
        return 1
    dest = rule_dest(args.target, args.project)

    print(f"source : {src}")
    print(f"target : {dest}")
    for n in check_collision():
        print(f"  ⚠ {n}")

    if args.dry_run:
        print("dry-run: 未写入。")
        return 0

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not args.force:
        backup = dest.with_suffix(dest.suffix + f".bak-{stamp()}")
        shutil.copy2(dest, backup)
        print(f"backup : {backup}")
    shutil.copy2(src, dest)
    print("done   : 已安装。Cursor 会每轮注入该规则，读取 latch 决定是否压缩。")
    print("next   : python scripts/latch.py on   # 开启会话锁存")
    return 0


if __name__ == "__main__":
    sys.exit(main())
