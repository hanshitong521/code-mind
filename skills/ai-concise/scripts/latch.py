#!/usr/bin/env python3
"""concise-mind latch — 会话锁存状态读写（零第三方依赖）。

用法:
    python scripts/latch.py on  [--mode DOC] [--level L1] [--audience manager] [--scope session|pin]
    python scripts/latch.py off
    python scripts/latch.py status [--json]
    python scripts/latch.py check            # exit 0=ACTIVE, 1=OFF  （供 hook / 自动化使用）
    python scripts/latch.py pin | unpin

文件位置优先级:
    --path 指定  >  <project>/.concise-mind.latch.json  >  ~/.concise-mind/latch.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

LATCH_NAME = ".concise-mind.latch.json"
USER_LATCH = Path.home() / ".concise-mind" / "latch.json"

OFF_WORDS = ["stop concise-mind", "normal mode", "关闭简洁", "退出简洁"]
VALID_LEVELS = ["L0", "L1", "L2", "L3"]
VALID_SCOPES = ["session", "pin"]
DEFAULT_LEVEL = "L1"


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def resolve_latch_path(explicit: str | None, project: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if project:
        return (Path(project).expanduser().resolve() / LATCH_NAME)
    cwd_file = Path.cwd() / LATCH_NAME
    if cwd_file.exists():
        return cwd_file
    return cwd_file  # 默认写项目根；不存在时创建


def read_state(path: Path) -> dict:
    if not path.exists():
        return {"active": False, "found": False, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"active": False, "found": True, "corrupt": str(exc), "path": str(path)}
    data["found"] = True
    data["path"] = str(path)
    return data


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_on(args) -> int:
    path = resolve_latch_path(args.path, args.project)
    level = (args.level or DEFAULT_LEVEL).upper()
    if level not in VALID_LEVELS:
        print(f"ERROR: level 须为 {VALID_LEVELS}")
        return 2
    scope = args.scope
    if scope not in VALID_SCOPES:
        print(f"ERROR: scope 须为 {VALID_SCOPES}")
        return 2
    state = {
        "active": True,
        "level": level,
        "mode_default": args.mode or "auto",
        "audience": args.audience,
        "scope": scope,
        "pinned": scope == "pin",
        "since": _now(),
        "off_words": OFF_WORDS,
    }
    write_state(path, state)
    print(f"concise-mind ON · {level} · mode={state['mode_default']} · scope={scope} · {path}")
    print("→ 本会话后续所有回复、文档、Plan 模式持续生效；OFF: stop concise-mind")
    return 0


def cmd_off(args) -> int:
    path = resolve_latch_path(args.path, args.project)
    state = read_state(path)
    state.update({"active": False, "pinned": False, "since": _now(),
                  "prev_level": state.get("level"), "path": str(path)})
    state.pop("found", None)
    write_state(path, state)
    print(f"concise-mind OFF · normal mode restored · {path}")
    return 0


def cmd_status(args) -> int:
    path = resolve_latch_path(args.path, args.project)
    state = read_state(path)
    if getattr(args, "json", False):
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0 if state.get("active") else 1
    if state.get("active"):
        print(f"ACTIVE · {state.get('level')} · mode={state.get('mode_default')} · "
              f"scope={state.get('scope')} · since={state.get('since')}")
        if state.get("scope") != "pin":
            print("(session scope — 新会话需重新 ON；要跨会话: latch.py pin)")
    elif state.get("corrupt"):
        print(f"OFF (状态文件损坏: {state['corrupt']}) · 沿用本会话已知状态，勿静默退出")
    else:
        print("OFF")
    return 0 if state.get("active") else 1


def cmd_pin(args) -> int:
    path = resolve_latch_path(args.path, args.project)
    state = read_state(path)
    if not state.get("active"):
        print("未 ACTIVE，先 on 再 pin")
        return 1
    state.update({"scope": "pin", "pinned": True, "path": str(path)})
    state.pop("found", None)
    write_state(path, state)
    print(f"concise-mind PINNED · 跨会话生效 · {path}")
    return 0


def cmd_unpin(args) -> int:
    path = resolve_latch_path(args.path, args.project)
    state = read_state(path)
    state.update({"scope": "session", "pinned": False, "path": str(path)})
    state.pop("found", None)
    write_state(path, state)
    print("concise-mind back to session scope")
    return 0


def cmd_show(args) -> int:
    for p in (Path.cwd() / LATCH_NAME, USER_LATCH):
        s = read_state(p)
        flag = "ACTIVE" if s.get("active") else ("missing" if not s.get("found") else "OFF")
        print(f"[{flag:7}] {p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="concise-mind session latch")
    p.add_argument("--path", help="显式指定 latch 文件路径")
    p.add_argument("--project", help="项目根目录（写 <project>/.concise-mind.latch.json）")
    sub = p.add_subparsers(dest="cmd", required=True)

    on = sub.add_parser("on")
    on.add_argument("--mode", help="默认模式: auto|CHAT|CODE|ARCH|HANDOFF|INCIDENT|DOC|PLAN")
    on.add_argument("--level", default=DEFAULT_LEVEL, help="L0|L1|L2|L3（默认 L1）")
    on.add_argument("--audience", help="Explain 受众: 5岁|15岁|manager|engineer|designer")
    on.add_argument("--scope", default="session", help="session|pin")
    on.set_defaults(func=cmd_on)

    off = sub.add_parser("off")
    off.set_defaults(func=cmd_off)

    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)

    chk = sub.add_parser("check")
    chk.add_argument("--json", action="store_true")
    chk.set_defaults(func=cmd_status)

    sub.add_parser("pin").set_defaults(func=cmd_pin)
    sub.add_parser("unpin").set_defaults(func=cmd_unpin)
    sub.add_parser("show").set_defaults(func=cmd_show)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
