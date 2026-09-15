#!/usr/bin/env python3
"""_yaml_lite.py — 零依赖 YAML 子集解析器（PyYAML 缺失时的兜底）。

覆盖范围（本仓控制面 + skill.yaml 实际用到的语法）：
  - 注释：整行 / 行尾（引号内的 # 不算注释）
  - 缩进嵌套 mapping
  - 序列：`- item` / `- key: val`（含后续同级 key 续行）
  - 行内流式：`[a, b]` / `{k: v}`
  - 单/双引号字符串（双引号支持 \\n \\t \\" 转义）
  - 块标量：`>` `>-` `>+` `|` `|-` `|+`
  - 标量类型：int / float / bool(true|yes|on|false|no|off) / null(~|null|空)
  - 文档分隔：`---` / `...`（取第一份文档）

不支持（本仓不需要）：锚点/别名、显式标签、多行 flow、复杂嵌套 flow。

调用约定：优先 PyYAML，仅在 ImportError 时兜底 —— 见 _common.load_yaml()。
本模块自身不 import 任何第三方包，保证 scripts/ 可在裸 Python 下运行。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = ["load", "load_file"]

_TRUE = frozenset({"true", "yes", "on"})
_FALSE = frozenset({"false", "no", "off"})
_NULL = frozenset({"null", "~", ""})
_BLOCK_INDICATORS = frozenset({">", ">-", ">+", "|", "|-", "|+", ">2", "|2"})
_INT_RE = re.compile(r"[-+]?\d+$")
_FLOAT_RE = re.compile(r"[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")


# ────────────────────────────── 词法层 ──────────────────────────────

def _strip_comment(line: str) -> str:
    """去掉行尾注释，尊重引号；返回保留缩进的原文。"""
    out: list[str] = []
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"' and i + 1 < n:
                out.append(line[i + 1])
                i += 1
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _split_key(s: str) -> tuple[str, str, str]:
    """按「第一个深度 0 且后跟空白/EOL 的冒号」切 key/value。"""
    quote: str | None = None
    depth = 0
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            continue
        if ch in "[{":
            depth += 1
            continue
        if ch in "]}":
            depth -= 1
            continue
        if ch == ":" and depth == 0:
            if i + 1 >= len(s) or s[i + 1] in " \t":
                return s[:i].strip(), ":", s[i + 1:].strip()
    return s.strip(), "", ""


def _split_flow(inner: str) -> list[str]:
    """按深度 0 的逗号切分行内 flow。"""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    depth = 0
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] == tok[-1] == '"':
        body = tok[1:-1]
        return (body.replace('\\"', '"').replace("\\n", "\n")
                    .replace("\\t", "\t").replace("\\\\", "\\"))
    if len(tok) >= 2 and tok[0] == tok[-1] == "'":
        return tok[1:-1].replace("''", "'")
    return tok


def _scalar(tok: str) -> Any:
    tok = tok.strip()
    if tok == "":
        return None
    if tok[0] in "\"'" and len(tok) >= 2 and tok[-1] == tok[0]:
        return _unquote(tok)
    if tok.startswith("[") and tok.endswith("]"):
        inner = tok[1:-1].strip()
        return [] if not inner else [_scalar(x) for x in _split_flow(inner)]
    if tok.startswith("{") and tok.endswith("}"):
        inner = tok[1:-1].strip()
        obj: dict[str, Any] = {}
        if inner:
            for part in _split_flow(inner):
                k, sep, v = _split_key(part)
                if sep:
                    obj[k] = _scalar(v)
        return obj
    low = tok.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    if low in _NULL:
        return None
    if _INT_RE.match(tok):
        return int(tok)
    if _FLOAT_RE.match(tok) and ("." in tok or "e" in tok.lower()):
        return float(tok)
    return tok


# ────────────────────────────── 语法层 ──────────────────────────────

class _Parser:
    def __init__(self, text: str) -> None:
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.n = len(self.lines)
        self.i = 0

    # —— 基础工具 ——
    def _content(self, i: int) -> tuple[int | None, str]:
        raw = self.lines[i]
        s = _strip_comment(raw)
        if s.strip() == "":
            return None, ""
        indent = len(s) - len(s.lstrip(" "))
        return indent, s.strip()

    def _peek(self) -> tuple[int, str] | None:
        j = self.i
        while j < self.n:
            ind, content = self._content(j)
            if ind is None or content in ("---", "..."):
                j += 1
                continue
            return ind, content
        return None

    def _skip_noise(self) -> None:
        while self.i < self.n:
            ind, content = self._content(self.i)
            if ind is None or content in ("---", "..."):
                self.i += 1
                continue
            return

    # —— 入口 ——
    def parse(self) -> Any:
        self._skip_noise()
        if self.i >= self.n:
            return None
        ind, _ = self._content(self.i)  # type: ignore[misc]
        value, _ = self._parse_block(ind)  # type: ignore[arg-type]
        return value

    def _parse_block(self, indent: int) -> tuple[Any, int]:
        peek = self._peek()
        if peek is None or peek[0] < indent:
            return None, self.i
        _, content = peek
        if content == "-" or content.startswith("- "):
            return self._parse_seq(indent), self.i
        return self._parse_map(indent), self.i

    def _parse_child(self, parent_indent: int) -> Any:
        peek = self._peek()
        if peek is None:
            return None
        if peek[0] > parent_indent:
            value, _ = self._parse_block(peek[0])
            return value
        if peek[0] == parent_indent and (peek[1] == "-" or peek[1].startswith("- ")):
            return self._parse_seq(parent_indent)
        return None

    def _parse_seq(self, indent: int) -> list[Any]:
        items: list[Any] = []
        while self.i < self.n:
            ind, content = self._content(self.i)
            if ind is None:
                self.i += 1
                continue
            if ind != indent or not (content == "-" or content.startswith("- ")):
                break
            rest = content[2:].strip() if content.startswith("- ") else ""
            if rest == "":
                self.i += 1
                items.append(self._parse_child(indent))
                continue
            if rest in _BLOCK_INDICATORS:
                self.i += 1
                items.append(self._read_block_scalar(indent, rest))
                continue
            if _split_key(rest)[1]:
                # `- key: val` → 改写为同级缩进后按 mapping 解析，后续同级 key 自动续入
                self.lines[self.i] = " " * (indent + 2) + rest
                value, _ = self._parse_block(indent + 2)
                items.append(value)
                continue
            self.i += 1
            items.append(_scalar(rest))
        return items

    def _parse_map(self, indent: int) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        while self.i < self.n:
            ind, content = self._content(self.i)
            if ind is None:
                self.i += 1
                continue
            if ind != indent:
                break
            if content == "-" or content.startswith("- "):
                break
            key, sep, val = _split_key(content)
            if not sep:
                break
            self.i += 1
            if val == "":
                mapping[key] = self._parse_child(indent)
            elif val in _BLOCK_INDICATORS:
                mapping[key] = self._read_block_scalar(indent, val)
            else:
                mapping[key] = _scalar(val)
        return mapping

    def _read_block_scalar(self, parent_indent: int, indicator: str) -> str:
        literal = indicator[0] == "|"
        chomp = indicator[1:2]
        raw_lines: list[str] = []
        block_indent: int | None = None
        while self.i < self.n:
            raw = self.lines[self.i]
            if raw.strip() == "":
                raw_lines.append("")
                self.i += 1
                continue
            ind = len(raw) - len(raw.lstrip(" "))
            if ind <= parent_indent:
                break
            if block_indent is None:
                block_indent = ind
            raw_lines.append(raw[block_indent:])
            self.i += 1
        while raw_lines and raw_lines[-1] == "":
            raw_lines.pop()
        if literal:
            text = "\n".join(raw_lines)
        else:
            parts: list[str] = []
            buf: list[str] = []
            for ln in raw_lines:
                if ln.strip() == "":
                    if buf:
                        parts.append(" ".join(buf))
                        buf = []
                    parts.append("\n")
                else:
                    buf.append(ln.strip())
            if buf:
                parts.append(" ".join(buf))
            text = "".join(parts)
        # chomping：- 去掉全部尾换行；+ 保留；默认(clip) 保留一个尾换行
        if chomp == "-":
            text = text.rstrip("\n")
        elif chomp == "+":
            pass
        else:
            text = text.rstrip("\n")
            if text:
                text += "\n"
        return text


# ────────────────────────────── 对外接口 ──────────────────────────────

def load(text: str) -> Any:
    """解析 YAML 文本（子集）。空文档返回 None。

    兼容「.yaml 文件里其实装的是 JSON」——本仓存在这种 fixture，
    先尝试 json.loads，失败再走 YAML 子集解析。
    """
    if text is None:
        return None
    head = text.lstrip("\ufeff \t\r\n")
    if head[:1] in ("{", "["):
        try:
            return json.loads(head)
        except ValueError:
            pass
    return _Parser(text).parse()


def load_file(path: str | Path) -> Any:
    return load(Path(path).read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":  # 手动冒烟：python _yaml_lite.py <file.yaml>
    import json
    import sys

    for arg in sys.argv[1:]:
        print(json.dumps(load_file(arg), ensure_ascii=False, indent=2))
