"""Deterministic, dependency-free symbol extraction -- spec §14 / §22.

No tree-sitter, no JVM, no network: the index is built from regexes plus real
brace matching over a comment/string-aware token stream.  It is deliberately
conservative -- it would rather miss a symbol than invent one, because the
dead-code rules treat "definition found, zero references" as a deletable
finding.

The safety-critical half of this module is *dynamic entry detection*: a class
that is only reachable through ``Class.forName``, Spring annotations, a MyBatis
``<select id=...>`` or a Vue ``components:`` registration must never be
reported as dead.  :meth:`SymbolIndex.has_dynamic_entry` returns ``True`` only
when a real entry point was actually found in the repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..config import Config
from ..contracts import Language, ScanContext, language_of
from ..util import is_binary_file, iter_files, read_text

__all__ = ["Symbol", "SymbolIndex", "extract_symbols", "build_symbol_index", "language_of"]

#: Files larger than this are not indexed (they are almost always generated).
MAX_INDEX_FILE_BYTES = 2 * 1024 * 1024

#: Hard ceiling so a runaway monorepo cannot exhaust memory.
MAX_INDEX_FILES = 20_000

_INDEXABLE = frozenset(
    {Language.JAVA, Language.JAVASCRIPT, Language.TYPESCRIPT, Language.VUE, Language.XML}
)

SOURCE_SUFFIXES = (
    ".java",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".vue",
    ".xml",
)

#: Conventional resource roots probed for ``META-INF/services`` / factories.
_RESOURCE_ROOTS = (
    "src/main/resources",
    "src/test/resources",
    "src/main",
    "resources",
    "src",
    "",
)

_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

#: Strings / comments / braces -- lets us count braces without a char loop.
_BRACE_TOKENS = re.compile(
    r"//[^\n]*"
    r"|/\*.*?\*/"
    r"|\"(?:\\.|[^\"\\])*\""
    r"|'(?:\\.|[^'\\])*'"
    r"|`(?:\\.|[^`\\])*`"
    r"|\{|\}",
    re.S,
)

_VISIBILITIES = ("public", "protected", "private")
_MODIFIERS = (
    "static",
    "final",
    "abstract",
    "synchronized",
    "native",
    "default",
    "transient",
    "volatile",
    "strictfp",
    "sealed",
    "async",
)
_JAVA_KEYWORDS = frozenset(
    {
        "if", "else", "for", "while", "switch", "case", "catch", "try", "do",
        "return", "throw", "throws", "new", "assert", "instanceof", "super",
        "this", "break", "continue", "synchronized", "yield", "record",
    }
)
_JS_KEYWORDS = frozenset(
    {
        "if", "else", "for", "while", "switch", "case", "catch", "try", "do",
        "return", "throw", "new", "typeof", "delete", "void", "in", "of",
        "function", "class", "const", "let", "var", "await", "yield", "else",
    }
)

_ANNO_RE = re.compile(r"@([\w.]+)")


# --------------------------------------------------------------------------
# symbol model
# --------------------------------------------------------------------------


@dataclass
class Symbol:
    name: str
    kind: str  # class|interface|enum|method|field|function|component|export|const
    file: str
    start_line: int
    end_line: int
    visibility: Optional[str] = None
    modifiers: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    owner: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "visibility": self.visibility,
            "modifiers": list(self.modifiers),
            "annotations": list(self.annotations),
            "owner": self.owner,
        }


# --------------------------------------------------------------------------
# low level helpers
# --------------------------------------------------------------------------


def _match_brace(text: str, open_idx: int) -> int:
    """Index of the ``}`` matching the ``{`` at ``open_idx`` (-1 if unbalanced)."""
    depth = 0
    for m in _BRACE_TOKENS.finditer(text, open_idx):
        tok = m.group(0)
        if tok == "{":
            depth += 1
        elif tok == "}":
            depth -= 1
            if depth == 0:
                return m.start()
    return -1


def _line_starts(text: str) -> list[int]:
    starts = [0]
    idx = text.find("\n")
    while idx != -1:
        starts.append(idx + 1)
        idx = text.find("\n", idx + 1)
    return starts


def _line_of(starts: list[int], index: int) -> int:
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= index:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _split_mods(mods: str) -> tuple[Optional[str], list[str]]:
    visibility: Optional[str] = None
    others: list[str] = []
    for token in mods.split():
        if token in _VISIBILITIES:
            visibility = token
        elif token in _MODIFIERS:
            others.append(token)
    return visibility, others


def _annos_of(text: str) -> list[str]:
    return [a for a in _ANNO_RE.findall(text)]


def _normalise_newlines(text: str) -> str:
    """CRLF and lone CR both become LF so anchors and ``$`` behave on Windows."""
    if "\r" not in text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _preceding_annotations(lines: list[str], index: int, limit: int = 6) -> list[str]:
    """Annotations written on their own lines directly above ``index``."""
    out: list[str] = []
    i = index - 1
    steps = 0
    while i >= 0 and steps < limit:
        stripped = lines[i].strip()
        if not stripped:
            break
        if not stripped.startswith("@"):
            break
        out.append(stripped.split("(")[0].strip()[1:])
        i -= 1
        steps += 1
    out.reverse()
    return out


def _make_symbol(
    *,
    name: str,
    kind: str,
    rel_path: str,
    line_no: int,
    end_line: int,
    visibility: Optional[str] = None,
    modifiers: Optional[list[str]] = None,
    annotations: Optional[list[str]] = None,
    owner: Optional[str] = None,
) -> Symbol:
    return Symbol(
        name=name,
        kind=kind,
        file=rel_path,
        start_line=line_no,
        end_line=max(end_line, line_no),
        visibility=visibility,
        modifiers=list(modifiers or []),
        annotations=list(annotations or []),
        owner=owner,
    )


# --------------------------------------------------------------------------
# java
# --------------------------------------------------------------------------

_JAVA_TYPE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<annos>(?:@[\w.]+(?:\([^)]*\))?[ \t]*)*)"
    r"(?P<mods>(?:(?:public|protected|private|static|final|abstract|sealed|"
    r"non-sealed|strictfp)[ \t]+)*)"
    r"(?P<kind>class|interface|enum|record)[ \t]+(?P<name>\w+)"
)

_JAVA_METHOD_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<annos>(?:@[\w.]+(?:\([^)]*\))?[ \t]*)*)"
    r"(?P<mods>(?:(?:public|protected|private|static|final|abstract|synchronized|"
    r"native|default|strictfp)[ \t]+)*)"
    r"(?P<ret>[\w$.<>\[\],?]+(?:[ \t]+[\w$.<>\[\],?]+)*?)[ \t]+(?P<name>\w+)[ \t]*"
    r"\((?P<args>[^)]*)\)[ \t]*(?:throws[ \t]+[\w$.,<>\[\] \t]+)?(?P<end>[{;])"
)

_JAVA_FIELD_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<annos>(?:@[\w.]+(?:\([^)]*\))?[ \t]*)*)"
    r"(?P<mods>(?:(?:public|protected|private|static|final|transient|volatile)[ \t]+)+)"
    r"(?P<type>[\w$.<>\[\],?]+(?:[ \t]+[\w$.<>\[\],?]+)*?)[ \t]+(?P<name>\w+)[ \t]*"
    r"(?:=[^;]*)?;[ \t]*$"
)

_JAVA_CTOR_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<annos>(?:@[\w.]+(?:\([^)]*\))?[ \t]*)*)"
    r"(?P<mods>(?:(?:public|protected|private)[ \t]+)*)"
    r"(?P<name>\w+)[ \t]*\((?P<args>[^)]*)\)[ \t]*"
    r"(?:throws[ \t]+[\w$.,<>\[\] \t]+)?(?P<end>[{;])"
)


def _extract_java(rel_path: str, text: str) -> list[Symbol]:
    lines = text.split("\n")
    starts = _line_starts(text)
    out: list[Symbol] = []
    class_stack: list[tuple[str, int]] = []  # (name, end_line)

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        while class_stack and idx + 1 > class_stack[-1][1]:
            class_stack.pop()
        owner = class_stack[-1][0] if class_stack else None

        m = _JAVA_TYPE_RE.match(line)
        if m:
            visibility, mods = _split_mods(m.group("mods"))
            open_idx = text.find("{", starts[idx] + m.end())
            close_idx = _match_brace(text, open_idx) if open_idx != -1 else -1
            end_line = _line_of(starts, close_idx) if close_idx != -1 else idx + 1
            kind = m.group("kind")
            if kind == "record":
                kind = "class"
            annos = _annos_of(m.group("annos")) + _preceding_annotations(lines, idx)
            out.append(
                _make_symbol(
                    name=m.group("name"),
                    kind=kind,
                    rel_path=rel_path,
                    line_no=idx + 1,
                    end_line=end_line,
                    visibility=visibility,
                    modifiers=mods,
                    annotations=annos,
                    owner=owner,
                )
            )
            class_stack.append((m.group("name"), end_line))
            continue

        m = _JAVA_METHOD_RE.match(line)
        if m:
            first = m.group("ret").split()[0] if m.group("ret").split() else ""
            # reject control flow that merely looks like `Type name(...)`
            if first not in _JAVA_KEYWORDS and m.group("name") not in _JAVA_KEYWORDS:
                visibility, mods = _split_mods(m.group("mods"))
                annos = _annos_of(m.group("annos")) + _preceding_annotations(lines, idx)
                if m.group("end") == "{":
                    open_idx = text.find("{", starts[idx] + m.end() - 1)
                    close_idx = _match_brace(text, open_idx) if open_idx != -1 else -1
                    end_line = _line_of(starts, close_idx) if close_idx != -1 else idx + 1
                else:
                    end_line = idx + 1
                out.append(
                    _make_symbol(
                        name=m.group("name"),
                        kind="method",
                        rel_path=rel_path,
                        line_no=idx + 1,
                        end_line=end_line,
                        visibility=visibility,
                        modifiers=mods,
                        annotations=annos,
                        owner=owner,
                    )
                )
                continue

        m = _JAVA_CTOR_RE.match(line)
        if m and owner and m.group("name") == owner:
            visibility, mods = _split_mods(m.group("mods"))
            annos = _annos_of(m.group("annos")) + _preceding_annotations(lines, idx)
            if m.group("end") == "{":
                open_idx = text.find("{", starts[idx] + m.end() - 1)
                close_idx = _match_brace(text, open_idx) if open_idx != -1 else -1
                end_line = _line_of(starts, close_idx) if close_idx != -1 else idx + 1
            else:
                end_line = idx + 1
            out.append(
                _make_symbol(
                    name=m.group("name"),
                    kind="method",
                    rel_path=rel_path,
                    line_no=idx + 1,
                    end_line=end_line,
                    visibility=visibility,
                    modifiers=mods,
                    annotations=annos,
                    owner=owner,
                )
            )
            continue

        m = _JAVA_FIELD_RE.match(line)
        if m:
            visibility, mods = _split_mods(m.group("mods"))
            annos = _annos_of(m.group("annos")) + _preceding_annotations(lines, idx)
            out.append(
                _make_symbol(
                    name=m.group("name"),
                    kind="field",
                    rel_path=rel_path,
                    line_no=idx + 1,
                    end_line=idx + 1,
                    visibility=visibility,
                    modifiers=mods,
                    annotations=annos,
                    owner=owner,
                )
            )

    return out


# --------------------------------------------------------------------------
# javascript / typescript / vue
# --------------------------------------------------------------------------

_JS_PATTERNS: list[tuple[str, "re.Pattern[str]", str]] = [
    ("class", re.compile(r"^(?P<indent>[ \t]*)(?:export[ \t]+(?:default[ \t]+)?)?(?:abstract[ \t]+)?class[ \t]+(?P<name>[\w$]+)"), "class"),
    ("function", re.compile(r"^(?P<indent>[ \t]*)(?:export[ \t]+(?:default[ \t]+)?)?(?:async[ \t]+)?function[ \t]*\*?[ \t]*(?P<name>[\w$]+)"), "function"),
    ("interface", re.compile(r"^(?P<indent>[ \t]*)(?:export[ \t]+)?interface[ \t]+(?P<name>[\w$]+)"), "interface"),
    ("enum", re.compile(r"^(?P<indent>[ \t]*)(?:export[ \t]+)?(?:const[ \t]+)?enum[ \t]+(?P<name>[\w$]+)"), "enum"),
    ("type", re.compile(r"^(?P<indent>[ \t]*)(?:export[ \t]+)?type[ \t]+(?P<name>[\w$]+)[ \t]*[=<]"), "const"),
    ("const_arrow", re.compile(r"^(?P<indent>[ \t]*)(?:export[ \t]+)?(?:const|let|var)[ \t]+(?P<name>[\w$]+)[ \t]*=[ \t]*(?:async[ \t]*)?(?:\([^)]*\)|[\w$]+)[ \t]*=>"), "function"),
    ("const_fn", re.compile(r"^(?P<indent>[ \t]*)(?:export[ \t]+)?(?:const|let|var)[ \t]+(?P<name>[\w$]+)[ \t]*=[ \t]*(?:async[ \t]*)?function\b"), "function"),
    ("vue_component", re.compile(r"^(?P<indent>[ \t]*)(?:Vue|app)[ \t]*\.[ \t]*component[ \t]*\([ \t]*['\"](?P<name>[\w\-.]+)['\"]"), "component"),
    ("export_default", re.compile(r"^(?P<indent>[ \t]*)export[ \t]+default[ \t]+(?P<name>[\w$]+)[ \t]*[{;]?[ \t]*$"), "export"),
    ("member", re.compile(r"^(?P<indent>[ \t]{2,})(?P<mods>(?:(?:async|static|get|set)[ \t]+)*)(?P<name>[\w$]+)[ \t]*\((?P<args>[^)]*)\)[ \t]*\{"), "method"),
]


def _extract_js(rel_path: str, text: str, *, line_offset: int = 0) -> list[Symbol]:
    lines = text.split("\n")
    starts = _line_starts(text)
    out: list[Symbol] = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        for _tag, rx, kind in _JS_PATTERNS:
            m = rx.match(line)
            if not m:
                continue
            name = m.group("name")
            if kind == "method" and name in _JS_KEYWORDS:
                break
            visibility, mods = _split_mods(m.groupdict().get("mods") or "")
            annos = _preceding_annotations(lines, idx)
            if line.rstrip().endswith("{"):
                open_idx = starts[idx] + line.rstrip().rfind("{")
            else:
                open_idx = text.find("{", starts[idx] + m.end())
                stop = text.find(";", starts[idx] + m.end())
                if stop != -1 and (open_idx == -1 or stop < open_idx):
                    open_idx = -1
            close_idx = _match_brace(text, open_idx) if open_idx != -1 else -1
            end_line = _line_of(starts, close_idx) if close_idx != -1 else idx + 1
            out.append(
                _make_symbol(
                    name=name,
                    kind=kind,
                    rel_path=rel_path,
                    line_no=idx + 1 + line_offset,
                    end_line=end_line + line_offset,
                    visibility=visibility,
                    modifiers=mods,
                    annotations=annos,
                )
            )
            break

    return out


_SCRIPT_OPEN = re.compile(r"<script[^>]*>", re.I)


def _extract_vue(rel_path: str, text: str) -> list[Symbol]:
    out: list[Symbol] = []
    base = Path(rel_path).stem
    out.append(
        _make_symbol(
            name=base,
            kind="component",
            rel_path=rel_path,
            line_no=1,
            end_line=max(1, len(text.split("\n"))),
        )
    )
    m = _SCRIPT_OPEN.search(text)
    if m:
        end = text.find("</script>", m.end())
        body = text[m.end(): end if end != -1 else len(text)]
        offset = text.count("\n", 0, m.end())
        out.extend(_extract_js(rel_path, body, line_offset=offset))
    return out


# --------------------------------------------------------------------------
# xml (mybatis / spring)
# --------------------------------------------------------------------------

_XML_STMT_RE = re.compile(
    r"<(?P<tag>select|insert|update|delete|sql)[ \t][^>]*\bid[ \t]*=[ \t]*[\"'](?P<name>[^\"']+)[\"']",
    re.I,
)
_XML_MAPPER_RE = re.compile(
    r"<mapper[ \t][^>]*\bnamespace[ \t]*=[ \t]*[\"'](?P<name>[^\"']+)[\"']", re.I
)


def _extract_xml(rel_path: str, text: str) -> list[Symbol]:
    out: list[Symbol] = []
    starts = _line_starts(text)
    namespace = ""
    m = _XML_MAPPER_RE.search(text)
    if m:
        namespace = m.group("name")
        out.append(
            _make_symbol(
                name=namespace.rsplit(".", 1)[-1],
                kind="class",
                rel_path=rel_path,
                line_no=_line_of(starts, m.start()),
                end_line=_line_of(starts, m.start()),
                annotations=[namespace],
            )
        )
    for m in _XML_STMT_RE.finditer(text):
        line_no = _line_of(starts, m.start())
        out.append(
            _make_symbol(
                name=m.group("name"),
                kind="method",
                rel_path=rel_path,
                line_no=line_no,
                end_line=line_no,
                owner=namespace or None,
            )
        )
    return out


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------


def extract_symbols(rel_path: str, text: str, language: Language) -> list[Symbol]:
    """Extract symbols from one file.  Pure, deterministic, never raises."""
    if not text:
        return []
    rel = str(rel_path).replace("\\", "/")
    if language is Language.JAVA:
        out = _extract_java(rel, text)
    elif language in (Language.JAVASCRIPT, Language.TYPESCRIPT):
        out = _extract_js(rel, text)
    elif language is Language.VUE:
        out = _extract_vue(rel, text)
    elif language is Language.XML:
        out = _extract_xml(rel, text)
    else:
        return []
    out.sort(key=lambda s: (s.start_line, s.end_line, s.kind, s.name))
    return out


# --------------------------------------------------------------------------
# dynamic entry detection
# --------------------------------------------------------------------------

_JAVA_FORNAME = re.compile(r"Class[ \t]*\.[ \t]*forName[ \t]*\([ \t]*\"([^\"]+)\"")
_JAVA_GETMETHOD = re.compile(r"\.get(?:Declared)?Method[ \t]*\([ \t]*\"([^\"]+)\"")
_JAVA_METHODHANDLES = re.compile(
    r"find(?:Virtual|Static|Special|Constructor)[ \t]*\([^)]*?\"([^\"]+)\"", re.S
)
_JAVA_SERVICELOADER = re.compile(r"ServiceLoader[ \t]*\.[ \t]*load[ \t]*\([ \t]*([\w$.]+)")
_JAVA_GETBEAN = re.compile(r"getBean[ \t]*\([ \t]*\"([^\"]+)\"")

_JS_DYN_IMPORT = re.compile(r"import[ \t]*\([^)]*\)", re.S)
_JS_DYN_REQUIRE = re.compile(r"require[ \t]*\([ \t]*(?![\"'])[^)]*\)", re.S)
_JS_VUE_COMPONENT = re.compile(r"(?:Vue|app)[ \t]*\.[ \t]*component[ \t]*\([ \t]*[\"']([^\"']+)[\"']")
_JS_VUE_USE = re.compile(r"(?:Vue|app|vm)[ \t]*\.[ \t]*use[ \t]*\([ \t]*([\w$.]+)")
_JS_COMPONENTS = re.compile(r"\bcomponents[ \t]*:[ \t]*\{([^}]*)\}", re.S)
_JS_ROUTER_COMPONENT = re.compile(
    r"\bcomponent[ \t]*:[ \t]*\([ \t]*\)[ \t]*=>[ \t]*import[ \t]*\([ \t]*[\"']([^\"']+)[\"']"
)
_JS_FILTERS = re.compile(r"\bfilters[ \t]*:[ \t]*\{([^}]*)\}", re.S)
_JS_MIXINS = re.compile(r"\bmixins[ \t]*:[ \t]*\[([^\]]*)\]", re.S)
_JS_REQUIRE_CONTEXT = re.compile(r"require[ \t]*\.[ \t]*context[ \t]*\(")

_XML_ANY_ID = re.compile(
    r"<(?P<tag>[A-Za-z_][\w.\-]*)[ \t][^>]*\b(?:id|ref|bean|class)[ \t]*=[ \t]*[\"'](?P<name>[^\"']+)[\"']",
    re.I,
)

#: annotation -> dynamic entry kind.  Longest names first so ``@Service`` is not
#: shadowed by a shorter prefix.
_ANNOTATION_KINDS: dict[str, str] = {
    "Component": "spring:bean",
    "Service": "spring:bean",
    "Controller": "spring:bean",
    "RestController": "spring:bean",
    "Repository": "spring:bean",
    "Configuration": "spring:bean",
    "Bean": "spring:bean",
    "Mapper": "spring:bean",
    "MapperScan": "mybatis:mapper_scan",
    "ComponentScan": "spring:component_scan",
    "Scheduled": "spring:scheduled",
    "EventListener": "spring:event_listener",
    "PostConstruct": "spring:lifecycle",
    "Async": "spring:lifecycle",
    "KafkaListener": "mq:listener",
    "RabbitListener": "mq:listener",
    "JmsListener": "mq:listener",
    "RocketMQMessageListener": "mq:listener",
    "XxlJob": "scheduler:xxl_job",
    "FeignClient": "rpc:feign",
    "DubboService": "rpc:dubbo",
    "DubboReference": "rpc:dubbo",
    "Reference": "rpc:dubbo",
    "RequestMapping": "http:endpoint",
    "GetMapping": "http:endpoint",
    "PostMapping": "http:endpoint",
    "PutMapping": "http:endpoint",
    "DeleteMapping": "http:endpoint",
    "PatchMapping": "http:endpoint",
    "Path": "http:endpoint",
}

_SPRING_ANNOTATIONS = frozenset(
    n for n, k in _ANNOTATION_KINDS.items() if k.startswith("spring:") or k.startswith("http:")
)


def _word_in(name: str, blob: str) -> bool:
    if not name or not blob:
        return False
    return bool(re.search(r"\b" + re.escape(name) + r"\b", blob)) or (
        f"'{name}'" in blob or f'"{name}"' in blob
    )


def _classify_ref(rel_path: str, language: Language, line: str, name: str) -> str:
    escaped = re.escape(name)
    if language is Language.XML:
        if re.search(r"\b(?:id|ref|bean|class|namespace)[ \t]*=[ \t]*[\"'][^\"']*" + escaped, line):
            return "xml"
        return "text"
    if re.match(r"^[ \t]*@\w*" + escaped + r"\b", line):
        return "annotation"
    if re.match(r"^[ \t]*(?:import|export|from|require|using|package)\b", line):
        return "import"
    if re.search(
        r"\b(?:forName|getMethod|getDeclaredMethod|findVirtual|findStatic|findSpecial|"
        r"loadClass|getBean|ServiceLoader|import|require|context)\b",
        line,
    ):
        return "reflection"
    if re.search(r"\b" + escaped + r"[ \t]*\(", line):
        return "call"
    return "text"


# --------------------------------------------------------------------------
# index
# --------------------------------------------------------------------------


class SymbolIndex:
    """Repo-wide symbol + reference index.

    Built once per run from the files the context layer already knows about;
    :meth:`references` is computed lazily and memoised so a scan that asks
    about ten dead-code candidates never tokenises the repo ten times.
    """

    def __init__(self, ctx: ScanContext, config: Config) -> None:
        self.ctx = ctx
        self.config = config
        self._by_file: dict[str, list[Symbol]] = {}
        self._all: list[Symbol] = []
        self._defs: dict[str, list[Symbol]] = {}
        self._texts: dict[str, str] = {}
        self._token_files: dict[str, list[str]] = {}
        self._spi: dict[str, str] = {}
        self._ref_cache: dict[str, list[dict[str, Any]]] = {}
        self._unreadable: list[str] = []
        self._built = False

    # -- construction ----------------------------------------------------

    def build(self) -> "SymbolIndex":
        files = self._source_files()
        for rel in files:
            text = self._read_source(rel)
            if text is None:
                continue
            syms = extract_symbols(rel, text, language_of(rel))
            if syms:
                self._by_file[rel] = syms
                self._all.extend(syms)

        self._all.sort(key=lambda s: (s.file, s.start_line, s.end_line, s.kind, s.name))
        for sym in self._all:
            self._defs.setdefault(sym.name, []).append(sym)

        names = set(self._defs)
        for rel in sorted(self._texts):
            tokens = set(_IDENT.findall(self._texts[rel]))
            for token in tokens & names:
                self._token_files.setdefault(token, []).append(rel)
        for token in self._token_files:
            self._token_files[token].sort()

        self._collect_spi()
        self._built = True
        return self

    def _source_files(self) -> list[str]:
        candidates: list[str] = []
        for rel in self.ctx.repo_files:
            if language_of(rel) in _INDEXABLE and not self.config.is_excluded(rel):
                candidates.append(rel)
        if not candidates:
            roots = [self.ctx.repo_root / r for r in self.config.source_roots]
            roots = [r for r in roots if r.is_dir()] or [self.ctx.repo_root]
            found: set[str] = set()
            for base in roots:
                for path in iter_files(base, suffixes=SOURCE_SUFFIXES, excludes=self.config.excludes):
                    try:
                        rel = path.resolve().relative_to(self.ctx.repo_root.resolve()).as_posix()
                    except (ValueError, OSError):
                        continue
                    if language_of(rel) in _INDEXABLE and not self.config.is_excluded(rel):
                        found.add(rel)
            candidates = sorted(found)
        return candidates[:MAX_INDEX_FILES]

    def _read_source(self, rel: str, *, force: bool = False) -> Optional[str]:
        cached = self._texts.get(rel)
        if cached is not None:
            return cached
        if not force and language_of(rel) not in _INDEXABLE:
            return None
        full = self.ctx.repo_root / rel
        if not full.is_file():
            return None
        try:
            if full.stat().st_size > MAX_INDEX_FILE_BYTES:
                self._unreadable.append(rel)
                return None
        except OSError:
            self._unreadable.append(rel)
            return None
        if is_binary_file(full):
            return None
        text = read_text(full, max_bytes=MAX_INDEX_FILE_BYTES)
        text = _normalise_newlines(text)
        self._texts[rel] = text
        return text

    def _collect_spi(self) -> None:
        """``META-INF/services/*`` and ``spring.factories`` are real entry points.

        Taken from the repo file list when available (git mode), otherwise
        probed at the conventional resource locations -- ``_scan_tree`` only
        walks known source suffixes and would miss them entirely.
        """
        candidates: set[str] = set()
        for rel in self.ctx.repo_files:
            normalised = "/" + rel.replace("\\", "/")
            if "/META-INF/services/" in normalised or rel.rsplit("/", 1)[-1] == "spring.factories":
                candidates.add(rel.replace("\\", "/"))
        if not candidates:
            for base in _RESOURCE_ROOTS:
                root = self.ctx.repo_root / base if base else self.ctx.repo_root
                for sub in ("META-INF/services", "META-INF"):
                    directory = root / sub
                    if not directory.is_dir():
                        continue
                    for entry in sorted(directory.iterdir()):
                        if not entry.is_file():
                            continue
                        if sub.endswith("services"):
                            candidates.add(entry.relative_to(self.ctx.repo_root).as_posix())
                        elif entry.name == "spring.factories":
                            candidates.add(entry.relative_to(self.ctx.repo_root).as_posix())
        for rel in sorted(candidates):
            if self.config.is_excluded(rel):
                continue
            text = self._read_source(rel, force=True)
            if text:
                self._spi[rel] = text

    # -- lookups ---------------------------------------------------------

    def symbols(self, rel_path: str) -> list[Symbol]:
        return list(self._by_file.get(str(rel_path).replace("\\", "/"), []))

    def all_symbols(self) -> list[Symbol]:
        return list(self._all)

    def definitions(self, name: str) -> list[Symbol]:
        return list(self._defs.get(name, []))

    def file_text(self, rel_path: str) -> str:
        rel = str(rel_path).replace("\\", "/")
        cached = self._texts.get(rel)
        if cached is not None:
            return cached
        return _normalise_newlines(read_text(self.ctx.repo_root / rel, max_bytes=MAX_INDEX_FILE_BYTES))

    def files_containing(self, name: str) -> list[str]:
        """Files that mention ``name``.

        The inverted token index is a fast path; it only covers names that are
        *defined* somewhere.  Names that are only ever referenced (a plugin
        registered via ``Vue.use``, a class named in ``Class.forName``) fall
        back to a full scan, so :meth:`has_dynamic_entry` stays truthful.
        """
        if not name:
            return []
        hits = self._token_files.get(name)
        if hits is not None:
            return list(hits)
        return sorted(rel for rel, text in self._texts.items() if name in text)

    def references(self, name: str) -> list[dict[str, Any]]:
        if not name:
            return []
        cached = self._ref_cache.get(name)
        if cached is not None:
            return list(cached)
        out: list[dict[str, Any]] = []
        for rel in self.files_containing(name):
            text = self.file_text(rel)
            if not text:
                continue
            lang = language_of(rel)
            for lineno, line in enumerate(text.split("\n"), 1):
                if name not in line:
                    continue
                out.append({"file": rel, "line": lineno, "kind": _classify_ref(rel, lang, line, name)})
        out.sort(key=lambda d: (d["file"], d["line"], d["kind"]))
        self._ref_cache[name] = out
        return list(out)

    def reference_count(self, name: str, *, exclude_definition: bool = True) -> int:
        refs = self.references(name)
        if not exclude_definition:
            return len(refs)
        defs = {(s.file, s.start_line) for s in self._defs.get(name, [])}
        return sum(1 for r in refs if (r["file"], r["line"]) not in defs)

    # -- dynamic entry points --------------------------------------------

    def dynamic_entry_kinds(self, name: str) -> list[str]:
        """Real, evidence-backed dynamic entry kinds for ``name`` (may be empty)."""
        if not name:
            return []
        kinds: set[str] = set()
        for rel in self.files_containing(name):
            text = self.file_text(rel)
            if not text:
                continue
            lang = language_of(rel)
            if lang is Language.JAVA:
                self._java_dynamic(text, name, kinds)
            elif lang in (Language.JAVASCRIPT, Language.TYPESCRIPT, Language.VUE):
                self._js_dynamic(text, name, kinds)
            elif lang is Language.XML:
                self._xml_dynamic(text, name, kinds)
        for rel, text in sorted(self._spi.items()):
            if name in text or name in rel:
                kinds.add("spi:meta_inf_services")
        for sym in self._defs.get(name, []):
            for anno in sym.annotations:
                short = anno.rsplit(".", 1)[-1]
                kind = _ANNOTATION_KINDS.get(short)
                if kind:
                    kinds.add(kind)
        return sorted(kinds)

    def has_dynamic_entry(self, name: str) -> bool:
        """``True`` only when a genuine dynamic entry point was found."""
        return bool(self.dynamic_entry_kinds(name))

    @staticmethod
    def _java_dynamic(text: str, name: str, kinds: set[str]) -> None:
        for m in _JAVA_FORNAME.finditer(text):
            fq = m.group(1)
            if fq == name or fq.rsplit(".", 1)[-1] == name or fq.endswith("." + name):
                kinds.add("reflection:class_for_name")
        for m in _JAVA_GETMETHOD.finditer(text):
            if m.group(1) == name:
                kinds.add("reflection:get_method")
        for m in _JAVA_METHODHANDLES.finditer(text):
            if m.group(1) == name:
                kinds.add("reflection:method_handles")
        for m in _JAVA_SERVICELOADER.finditer(text):
            if m.group(1).rsplit(".", 1)[-1] == name:
                kinds.add("spi:service_loader")
        for m in _JAVA_GETBEAN.finditer(text):
            if m.group(1) == name:
                kinds.add("spring:get_bean")

    @staticmethod
    def _js_dynamic(text: str, name: str, kinds: set[str]) -> None:
        if any(name in m.group(0) for m in _JS_DYN_IMPORT.finditer(text)):
            kinds.add("js:dynamic_import")
        if any(name in m.group(0) for m in _JS_DYN_REQUIRE.finditer(text)):
            kinds.add("js:dynamic_require")
        if any(m.group(1) == name for m in _JS_VUE_COMPONENT.finditer(text)):
            kinds.add("vue:global_component")
        if any(_word_in(name, m.group(1)) for m in _JS_COMPONENTS.finditer(text)):
            kinds.add("vue:component_registration")
        if any(name in m.group(1) for m in _JS_ROUTER_COMPONENT.finditer(text)):
            kinds.add("vue:router_component")
        if any(m.group(1).rsplit(".", 1)[-1] == name for m in _JS_VUE_USE.finditer(text)):
            kinds.add("vue:plugin")
        if any(_word_in(name, m.group(1)) for m in _JS_FILTERS.finditer(text)):
            kinds.add("vue:filter")
        if any(_word_in(name, m.group(1)) for m in _JS_MIXINS.finditer(text)):
            kinds.add("vue:mixin")
        if _JS_REQUIRE_CONTEXT.search(text) and name in text:
            kinds.add("webpack:require_context")

    @staticmethod
    def _xml_dynamic(text: str, name: str, kinds: set[str]) -> None:
        for m in _XML_ANY_ID.finditer(text):
            value = m.group("name")
            tag = m.group("tag").lower()
            if value == name or value.rsplit(".", 1)[-1] == name:
                if tag in ("select", "insert", "update", "delete", "sql"):
                    kinds.add("mybatis:xml_statement")
                elif tag == "mapper":
                    kinds.add("mybatis:mapper_namespace")
                elif tag == "bean":
                    kinds.add("spring:xml_bean")
                else:
                    kinds.add("xml:reference")

    def find_spring_annotated(self) -> dict[str, list[str]]:
        """``{class_name: [annotation, ...]}`` for Spring/HTTP annotated types."""
        out: dict[str, list[str]] = {}
        for sym in self._all:
            if sym.kind not in ("class", "interface", "enum"):
                continue
            if language_of(sym.file) is not Language.JAVA:
                continue
            annos = [a.rsplit(".", 1)[-1] for a in sym.annotations]
            hits = [a for a in annos if a in _SPRING_ANNOTATIONS]
            if hits:
                out.setdefault(sym.name, [])
                for h in sorted(set(hits)):
                    if h not in out[sym.name]:
                        out[sym.name].append(h)
        return {k: sorted(v) for k, v in sorted(out.items())}

    # -- reporting -------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        by_language: dict[str, int] = {}
        for sym in self._all:
            by_kind[sym.kind] = by_kind.get(sym.kind, 0) + 1
            lang = language_of(sym.file).value
            by_language[lang] = by_language.get(lang, 0) + 1
        return {
            "files_indexed": len(self._by_file),
            "files_with_symbols": len(self._by_file),
            "symbols": len(self._all),
            "unique_names": len(self._defs),
            "by_kind": {k: by_kind[k] for k in sorted(by_kind)},
            "by_language": {k: by_language[k] for k in sorted(by_language)},
            "spi_files": len(self._spi),
            "references_cached": len(self._ref_cache),
            "unreadable": sorted(self._unreadable),
        }


def build_symbol_index(ctx: ScanContext, config: Config) -> SymbolIndex:
    """Convenience entry point: build a ready-to-query :class:`SymbolIndex`."""
    return SymbolIndex(ctx, config).build()
