"""A tiny YAML-subset parser, so the engine has **zero** third-party deps.

Scope (deliberately narrow -- it only has to read ``.codehealth.yml`` and
``accepted_risks`` blocks):

* nested mappings by indentation
* block sequences (``- item`` and ``- key: value``)
* inline sequences ``[a, b, c]`` and inline maps ``{a: 1}``
* quoted strings, booleans, ints, floats, null
* ``#`` comments and blank lines
* block scalars ``|`` / ``>``

Out of scope: anchors, aliases, tags, multi-document, complex keys.
If PyYAML happens to be importable, :func:`chm.config.load_yaml` prefers it.
Anything this parser cannot represent raises :class:`YamlSubsetError` rather
than silently guessing -- a wrong config is worse than a loud failure.
"""

from __future__ import annotations

import re
from typing import Any, Optional


class YamlSubsetError(ValueError):
    pass


_NUM_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+([eE][-+]?\d+)?$")
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.\-]*|\"[^\"]+\"|'[^']+')\s*:(?:\s+(.*))?$")

_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}
_NULL = {"null", "~", ""}


def _strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment, respecting quotes."""
    out = []
    quote: Optional[str] = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _scalar(token: str) -> Any:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        inner = token[1:-1]
        if token[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        return inner
    low = token.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    if low in _NULL:
        return None
    if _NUM_RE.match(token):
        try:
            return int(token)
        except ValueError:
            return token
    if _FLOAT_RE.match(token):
        try:
            return float(token)
        except ValueError:
            return token
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_scalar(p) for p in _split_inline(inner)]
    if token.startswith("{") and token.endswith("}"):
        inner = token[1:-1].strip()
        if not inner:
            return {}
        result: dict[str, Any] = {}
        for part in _split_inline(inner):
            if ":" not in part:
                raise YamlSubsetError(f"inline map entry without ':' -> {part!r}")
            k, _, v = part.partition(":")
            result[str(_scalar(k.strip()))] = _scalar(v)
        return result
    return token


def _split_inline(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote: Optional[str] = None
    buf = ""
    for ch in text:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf += ch
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf.strip())
            buf = ""
            continue
        buf += ch
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _prepare(text: str) -> list[tuple[int, str, int]]:
    """Return ``(indent, content, lineno)`` for significant lines."""
    rows: list[tuple[int, str, int]] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        if raw.strip() == "" :
            continue
        stripped = raw.lstrip(" \t")
        if stripped.startswith("#"):
            continue
        content = _strip_comment(raw)
        if content.strip() == "":
            continue
        indent = len(content) - len(content.lstrip(" \t"))
        rows.append((indent, content.strip(), idx))
    return rows


class _Parser:
    def __init__(self, rows: list[tuple[int, str, int]]) -> None:
        self.rows = rows
        self.pos = 0

    def parse(self) -> Any:
        if not self.rows:
            return {}
        value = self._block(self.rows[0][0])
        if self.pos != len(self.rows):
            _, content, lineno = self.rows[self.pos]
            raise YamlSubsetError(f"line {lineno}: unexpected content {content!r}")
        return value

    def _block(self, indent: int) -> Any:
        if self.pos >= len(self.rows):
            return {}
        cur_indent, content, _ = self.rows[self.pos]
        if content.startswith("- "):
            return self._sequence(indent)
        if content == "-":
            return self._sequence(indent)
        return self._mapping(indent)

    def _sequence(self, indent: int) -> list[Any]:
        items: list[Any] = []
        while self.pos < len(self.rows):
            cur_indent, content, lineno = self.rows[self.pos]
            if cur_indent < indent:
                break
            if cur_indent > indent:
                raise YamlSubsetError(f"line {lineno}: bad indentation in sequence")
            if not (content == "-" or content.startswith("- ")):
                break
            rest = content[1:].strip()
            self.pos += 1
            if rest == "":
                if self.pos < len(self.rows) and self.rows[self.pos][0] > indent:
                    items.append(self._block(self.rows[self.pos][0]))
                else:
                    items.append(None)
                continue
            # inline map start: "- key: value"
            m = _KEY_RE.match(rest)
            if m:
                item: dict[str, Any] = {}
                key = _unquote_key(m.group(1))
                value_text = (m.group(2) or "").strip()
                child_indent = indent + 2
                if value_text == "":
                    if self.pos < len(self.rows) and self.rows[self.pos][0] > indent:
                        child_indent = self.rows[self.pos][0]
                        item[key] = self._block(child_indent)
                    else:
                        item[key] = None
                elif value_text in ("|", ">"):
                    item[key] = self._block_scalar(indent, value_text)
                else:
                    item[key] = _scalar(value_text)
                # continuation keys of the same map item
                while self.pos < len(self.rows):
                    nxt_indent, nxt_content, nxt_lineno = self.rows[self.pos]
                    if nxt_indent != child_indent or nxt_content.startswith("- "):
                        break
                    mm = _KEY_RE.match(nxt_content)
                    if not mm:
                        break
                    k2 = _unquote_key(mm.group(1))
                    v2 = (mm.group(2) or "").strip()
                    self.pos += 1
                    if v2 == "":
                        if self.pos < len(self.rows) and self.rows[self.pos][0] > nxt_indent:
                            item[k2] = self._block(self.rows[self.pos][0])
                        else:
                            item[k2] = None
                    elif v2 in ("|", ">"):
                        item[k2] = self._block_scalar(nxt_indent, v2)
                    else:
                        item[k2] = _scalar(v2)
                items.append(item)
                continue
            items.append(_scalar(rest))
        return items

    def _mapping(self, indent: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while self.pos < len(self.rows):
            cur_indent, content, lineno = self.rows[self.pos]
            if cur_indent < indent:
                break
            if cur_indent > indent:
                raise YamlSubsetError(f"line {lineno}: bad indentation in mapping")
            if content.startswith("- "):
                break
            m = _KEY_RE.match(content)
            if not m:
                raise YamlSubsetError(f"line {lineno}: not a 'key: value' pair -> {content!r}")
            key = _unquote_key(m.group(1))
            value_text = (m.group(2) or "").strip()
            self.pos += 1
            if value_text == "":
                if self.pos < len(self.rows) and self.rows[self.pos][0] > indent:
                    result[key] = self._block(self.rows[self.pos][0])
                else:
                    result[key] = None
            elif value_text in ("|", ">"):
                result[key] = self._block_scalar(indent, value_text)
            else:
                result[key] = _scalar(value_text)
        return result

    def _block_scalar(self, indent: int, style: str) -> str:
        lines: list[str] = []
        base: Optional[int] = None
        while self.pos < len(self.rows):
            cur_indent, content, _ = self.rows[self.pos]
            if cur_indent <= indent:
                break
            if base is None:
                base = cur_indent
            lines.append(" " * max(0, cur_indent - base) + content)
            self.pos += 1
        if style == "|":
            return "\n".join(lines) + "\n"
        return " ".join(lines) + "\n"


def _unquote_key(key: str) -> str:
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
        return key[1:-1]
    return key


def loads(text: str) -> Any:
    """Parse a YAML-subset document."""
    return _Parser(_prepare(text)).parse()


def load(path) -> Any:
    from pathlib import Path

    return loads(Path(path).read_text(encoding="utf-8"))


def dumps(obj: Any, _indent: int = 0) -> str:
    """Emit a YAML-subset document (used for baseline / accepted-risk files)."""
    pad = "  " * _indent
    lines: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{pad}{key}:")
                lines.append(dumps(value, _indent + 1))
            elif isinstance(value, (dict, list)):
                lines.append(f"{pad}{key}: {'{}' if isinstance(value, dict) else '[]'}")
            else:
                lines.append(f"{pad}{key}: {_dump_scalar(value)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                first = True
                for key, value in item.items():
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first = False
                    if isinstance(value, (dict, list)) and value:
                        lines.append(f"{prefix}{key}:")
                        lines.append(dumps(value, _indent + 2))
                    elif isinstance(value, (dict, list)):
                        lines.append(f"{prefix}{key}: {'{}' if isinstance(value, dict) else '[]'}")
                    else:
                        lines.append(f"{prefix}{key}: {_dump_scalar(value)}")
            elif isinstance(item, list):
                lines.append(f"{pad}- {_dump_scalar(item)}")
            else:
                lines.append(f"{pad}- {_dump_scalar(item)}")
    else:
        lines.append(f"{pad}{_dump_scalar(obj)}")
    return "\n".join(lines)


def _dump_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or re.search(r"[:#\[\]{}]|^\s|\s$", text):
        return '"' + text.replace('"', '\\"') + '"'
    return text
