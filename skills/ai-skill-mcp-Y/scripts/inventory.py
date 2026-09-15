#!/usr/bin/env python3
"""List skill roots + alwaysApply rules. No secrets, no tool schema bodies."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKIP = {".git", "node_modules", "target", ".contextmind", ".codegraph", ".agent"}


def front(text: str, key: str) -> str:
    m = re.search(rf"^---\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    block = m.group(1)
    km = re.search(rf"^{re.escape(key)}:\s*(.+)$", block, re.M)
    if not km:
        return ""
    v = km.group(1).strip().strip("\"'")
    if v == ">":
        rest = block.split(km.group(0), 1)[-1]
        lines = []
        for line in rest.splitlines()[1:]:
            if re.match(r"^[a-zA-Z0-9_-]+:", line) and not line.startswith(" "):
                break
            lines.append(line.strip())
        v = " ".join(lines)
    return re.sub(r"\s+", " ", v)[:180]


def walk(root: Path):
    for p in root.rglob("*"):
        if any(part in SKIP for part in p.parts):
            continue
        yield p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    print("=== skills ===")
    for p in sorted(walk(root)):
        if p.name != "SKILL.md":
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        n = len(t.splitlines())
        print(f"{p.relative_to(root)} | {front(t,'name')} | {n}L | {front(t,'description')}")
    print("=== alwaysApply rules ===")
    for p in sorted(walk(root)):
        if p.suffix != ".mdc":
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^alwaysApply:\s*true", t, re.M):
            continue
        print(f"{p.relative_to(root)} | {len(t.splitlines())}L | {front(t,'description')}")


if __name__ == "__main__":
    main()
