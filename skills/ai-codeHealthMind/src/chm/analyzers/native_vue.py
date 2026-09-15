"""Built-in deterministic analyzer for Vue SFC / JS / TS change sets.

Pure standard library, no process, no LLM.  Every rule is a *pattern* rule with
an explicit counter-example suppression: when the suppression signal is present
the rule must stay silent.  Low precision is worse than low recall here
(spec: MEDIUM+ false positives <= 8%, HIGH+ <= 3%).

------------------------------------------------------------------------------
Rule -> suppression summary
------------------------------------------------------------------------------
CHM-JS-NAT-UNUSED-COMPONENT
    hit   : a name registered in ``components: { X }`` never appears as a tag
            ``<x``/``<X`` in the same file's ``<template>``.
    known counter-examples: ``<component :is="X">`` dynamic usage; the name
            appearing anywhere as a quoted string in the template; global
            registration via ``Vue.component('x', ...)``; ``defineComponent``
            with ``components`` inside ``setup``.  All suppressed.

CHM-JS-NAT-UNUSED-EXPORT
    hit   : ``export function X`` / ``export const X`` with zero cross-file
            ``import ... X`` and not an entry file.
    known counter-examples: dynamic ``import()`` of the module; the module
            referenced from a router lazy-load; ``index.js``/``main.js``
            barrels; test files.  All suppressed.

CHM-JS-NAT-DUP-COMPUTED
    hit   : two computed properties in one SFC with byte-identical normalized
            bodies of >= 3 lines.
    known counter-examples: <= 2 line bodies (plain field access).  Suppressed.

CHM-JS-NAT-HUGE-COMPONENT
    hit   : SFC > 800 lines, or ``data()`` returning > 30 fields, or
            ``methods`` with > 30 members.  LOW only.

CHM-JS-NAT-API-WRAPPER-PASSTHRU
    hit   : ``src/api/*.js`` function whose whole body is ``return request({...})``
            and which has a single caller.
    known counter-examples: ``then``/``catch`` normalisation, parameter
            transformation, retry, abort-controller.  Suppressed.

CHM-JS-NAT-EMPTY-CATCH
    hit   : a ``try { ... } catch (x) { }`` whose catch body has no statement.
    known counter-examples (-> LOW + ``extra["note"]``, never suppressed):
            * the catch binding is deliberately unused (``_``/``_e``/``_err``/
              ``ignored``/``unused``);
            * the try body only *probes* an optional thing (``execSync``/
              ``spawnSync``/``require(``/``import(``/``fs.existsSync``/
              ``fs.statSync``/``fs.accessSync``), *parses with a default*
              (``JSON.parse``/``parseInt``/``parseFloat``/
              ``decodeURIComponent``), *cleans up* (``fs.unlinkSync``/
              ``fs.rmSync``/``fs.rmdirSync``) or touches *optional storage*
              (``process.kill``/``localStorage``/``sessionStorage``);
            * the catch block carries a comment (the author stated intent);
            * the binding is unused *and* the try/catch is the last statement
              of its enclosing block.
            ``catch (Exception e) {}`` with no comment, no probe and no
            deliberately-unused binding stays HIGH (spec CHM-ERR-001).

CHM-JS-NAT-DEBUG-RESIDUE
    hit   : ``console.log/debug/info`` outside tests.
    known counter-examples: ``test``/``tests``/``__tests__``/``spec``/``e2e``
            /``dev`` paths; CLI tooling paths ``benchmarks``/``scripts``/
            ``tools``/``bin`` where stdout *is* the product.  Suppressed.

CHM-JS-NAT-TODO-MARKER
    direct textual rule.

CHM-JS-NAT-UNUSED-DEPENDENCY-DECL
    hit   : a dependency in ``package.json`` with zero ``import``/``require``
            in the sources.
    known counter-examples: build-only tooling declared in ``devDependencies``
            (not scanned), packages referenced only by string in scripts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..contracts import (
    ChangeKind,
    EvidenceProvider,
    Language,
    ProviderResult,
    ScanContext,
)
from ..errors import ToolFailureKind, ToolError, ToolStatus
from ..schema import Category, EvidenceKind, RawFinding, Severity
from ..util import iter_files, read_text, strip_comments_and_strings

PROVIDER_NAME = "native-vue"

VUE_LANGS = frozenset(
    {Language.VUE, Language.JAVASCRIPT, Language.TYPESCRIPT}
)
VUE_SUFFIXES = (".vue", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

_SFC_LIMIT_LINES = 800
_SFC_LIMIT_DATA_FIELDS = 30
_SFC_LIMIT_METHODS = 30

MAX_FILE_BYTES = 2 * 1024 * 1024

# --------------------------------------------------------------------------
# compiled patterns (module level: compiled once, never per call)
# --------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_STRING_RE = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`", re.S)

_COMPONENTS_BLOCK_RE = re.compile(r"\bcomponents\s*:\s*\{", re.S)
_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")

_TEMPLATE_RE = re.compile(r"<template\b[^>]*>(.*?)</template>", re.S | re.I)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
_TAG_RE = re.compile(r"<\s*([A-Za-z][\w.-]*)")
_KEBAB_RE = re.compile(r"[A-Z]")

_EXPORT_FN_RE = re.compile(
    r"\bexport\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"
    r"|\bexport\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)"
)
_DYNAMIC_IMPORT_RE = re.compile(r"\bimport\s*\(")
_ENTRY_BASENAMES = frozenset(
    {"main.js", "main.ts", "index.js", "index.ts", "app.js", "app.ts", "main.mjs"}
)

_COMPUTED_BLOCK_RE = re.compile(r"\bcomputed\s*:\s*\{", re.S)
_METHODS_BLOCK_RE = re.compile(r"\bmethods\s*:\s*\{", re.S)
_DATA_BLOCK_RE = re.compile(r"\bdata\s*(?:\(\s*\))?\s*(?::\s*[^=]+)?\{", re.S)
_DATA_RETURN_RE = re.compile(r"\breturn\s*\{", re.S)

_CATCH_RE = re.compile(r"\bcatch\b\s*(?:\(\s*(?P<bind>[^)]*?)\s*\))?\s*(?P<brace>\{)")
_CONSOLE_RE = re.compile(r"\bconsole\s*\.\s*(log|debug|info)\s*\(")
_TODO_RE = re.compile(r"(?://|/\*|\*)[^\n]*\b(TODO|FIXME|XXX|HACK)\b")

#: catch bindings whose *name* says "I deliberately do not use this error".
_UNUSED_BINDING_RE = re.compile(
    r"^(?:_+|_(?:e|err|ex|error|exception|ignored|unused|t|x)"
    r"|ignored|ignore|unused)$",
    re.I,
)

#: Calls whose failure is idiomatic to ignore: probing for something optional,
#: parsing a value that has a fallback, or best-effort cleanup.  A swallowed
#: error around one of these is downgraded, never suppressed.
_PROBE_CALL_RE = re.compile(
    r"(?:"
    r"\b(?:execSync|execFileSync|spawnSync|execFile|spawn|exec)\s*\("
    r"|\b(?:require|import)\s*\("
    r"|\bJSON\s*\.\s*parse\s*\("
    r"|\b(?:parseInt|parseFloat|decodeURIComponent|decodeURI)\s*\("
    r"|\bfs\s*\.\s*(?:statSync|lstatSync|accessSync|existsSync|realpathSync"
    r"|unlinkSync|rmSync|rmdirSync)\s*\("
    r"|\bprocess\s*\.\s*kill\s*\("
    r"|\b(?:localStorage|sessionStorage)\s*\."
    r")"
)

#: Block owners whose body runs repeatedly -- the "try each candidate" shape.
_LOOP_OWNERS = frozenset(
    {
        "for",
        "while",
        "do",
        "forEach",
        "map",
        "filter",
        "some",
        "every",
        "reduce",
        "reduceRight",
        "find",
        "findIndex",
        "flatMap",
        "sort",
    }
)

#: Directories whose JS files *are* command line tools: stdout is the product,
#: so ``console.log`` there is not debug residue.
_TOOLING_PATH_RE = re.compile(
    r"(?:^|/)(?:benchmarks?|scripts?|tools?|bin)(?:/|$)", re.I
)

_API_PASSTHRU_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{"
    r"\s*return\s+request\s*\(",
    re.S,
)

_TEST_PATH_RE = re.compile(r"(?:^|/)(?:test|tests|__tests__|spec|e2e|dev)(?:/|$)", re.I)


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub(lambda m: " " * (m.end() - m.start()), text)


def _aligned_skeleton(code: str) -> str:
    """Comments + string literals blanked, **every offset preserved**.

    ``util.strip_comments_and_strings`` drops the two delimiter characters of
    every comment, so a skeleton offset does not index the original source.
    Rules that must read the raw text through a skeleton offset (the empty
    catch rule needs the real body to tell "no statement" from "comment")
    use this instead.  Length and newline positions are identical to ``code``.
    """
    out = list(code)
    i = 0
    n = len(code)
    quote: Optional[str] = None
    while i < n:
        ch = code[i]
        if quote is not None:
            if ch == "\\":
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
                continue
            if ch == quote:
                quote = None
            if ch != "\n":
                out[i] = " "
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out[i] = " "
            i += 1
            continue
        if ch == "/" and i + 1 < n and code[i + 1] == "/":
            while i < n and code[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if ch == "/" and i + 1 < n and code[i + 1] == "*":
            out[i] = " "
            out[i + 1] = " "
            i += 2
            while i < n:
                if code[i] == "*" and i + 1 < n and code[i + 1] == "/":
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    break
                if code[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


def _normalize_body(body: str) -> str:
    """Whitespace-insensitive, literal-insensitive body fingerprint."""
    body = _STRING_RE.sub("STR", body)
    body = re.sub(r"\b\d+(?:\.\d+)?\b", "NUM", body)
    return re.sub(r"\s+", " ", body).strip()


def _kebab(name: str) -> str:
    return _KEBAB_RE.sub(lambda m: "-" + m.group(0).lower(), name).lstrip("-").lower()


def _block_of(text: str, open_brace_idx: int) -> Optional[str]:
    """Return the text inside the brace opened at ``open_brace_idx``."""
    depth = 0
    for i in range(open_brace_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_idx + 1 : i]
    return None


def _brace_pairs(text: str) -> tuple[dict[int, int], dict[int, int]]:
    """One O(n) pass: (open->close, close->open) brace index maps.

    ``strip_comments_and_strings`` preserves length, so these offsets also
    index the original source.
    """
    stack: list[int] = []
    forward: dict[int, int] = {}
    backward: dict[int, int] = {}
    for i, ch in enumerate(text):
        if ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            open_idx = stack.pop()
            forward[open_idx] = i
            backward[i] = open_idx
    return forward, backward


def _block_owner(skel: str, close_brace_idx: int, close_to_open: dict[int, int]) -> str:
    """Keyword/identifier that introduces the block closed at ``close_brace_idx``.

    ``for (...) {`` -> ``"for"``, ``function f() {`` -> ``"f"``, ``else {`` ->
    ``"else"``.  Empty when the shape is not recognisable.
    """
    open_idx = close_to_open.get(close_brace_idx)
    if open_idx is None:
        return ""
    j = open_idx - 1
    while j >= 0 and skel[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return ""
    if skel[j] == ")":
        depth = 0
        k = j
        while k >= 0:
            if skel[k] == ")":
                depth += 1
            elif skel[k] == "(":
                depth -= 1
                if depth == 0:
                    break
            k -= 1
        if k < 0:
            return ""
        j = k - 1
        while j >= 0 and skel[j] in " \t\r\n":
            j -= 1
    end = j
    while j >= 0 and (skel[j].isalnum() or skel[j] in "_$."):
        j -= 1
    return skel[j + 1 : end + 1]


def _is_last_in_block(skel: str, idx: int) -> bool:
    """True when only whitespace/``;`` separates ``idx`` from the closing ``}``."""
    i = idx + 1
    while i < len(skel) and skel[i] in " \t\r\n;":
        i += 1
    return i < len(skel) and skel[i] == "}"


def _enclosing_try(
    skel: str, catch_start: int, close_to_open: dict[int, int]
) -> Optional[tuple[int, int]]:
    """``(try_open_brace, try_close_brace)`` for the ``try`` owning this catch."""
    i = catch_start - 1
    while i >= 0 and skel[i] in " \t\r\n":
        i -= 1
    if i < 0 or skel[i] != "}":
        return None
    open_idx = close_to_open.get(i)
    if open_idx is None:
        return None
    j = open_idx - 1
    while j >= 0 and skel[j] in " \t\r\n":
        j -= 1
    end = j + 1
    while j >= 0 and (skel[j].isalnum() or skel[j] in "_$"):
        j -= 1
    if skel[j + 1 : end] != "try":
        return None
    return open_idx, i


def _comment_only(blob: str) -> bool:
    """True when a raw source region holds nothing but whitespace/comments."""
    return not _COMMENT_RE.sub(" ", blob).strip()


def _top_level_members(block: str) -> list[str]:
    """Split an object-literal body into top-level member keys (deterministic)."""
    keys: list[str] = []
    depth = 0
    i = 0
    n = len(block)
    current_start = 0
    while i < n:
        ch = block[i]
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif ch == "," and depth == 0:
            chunk = block[current_start:i]
            keys.append(chunk)
            current_start = i + 1
        i += 1
    keys.append(block[current_start:])
    out: list[str] = []
    for chunk in keys:
        m = re.match(
            r"\s*(?:async\s+)?(?:get\s+|set\s+)?([A-Za-z_$][\w$]*)\s*(?:[(:=]|$)", chunk
        )
        if m:
            out.append(m.group(1))
    return out


@dataclass
class _JsFile:
    path: str
    text: str
    lines: list[str]
    noc: str  # comments stripped, strings kept
    skel: str  # comments + strings stripped


def _load(path: Path, rel: str) -> Optional[_JsFile]:
    text = read_text(path, max_bytes=MAX_FILE_BYTES)
    if not text:
        return None
    return _JsFile(
        path=rel,
        text=text,
        lines=text.replace("\r\n", "\n").replace("\r", "\n").split("\n"),
        noc=_strip_comments(text),
        skel=strip_comments_and_strings(text),
    )


class VueNativeAnalyzer(EvidenceProvider):
    """Deterministic JS/TS/Vue pattern analyzer."""

    name = PROVIDER_NAME
    kind = EvidenceKind.DETERMINISTIC
    categories = (
        Category.DEAD_CODE,
        Category.DUPLICATION,
        Category.LARGE_CLASS,
        Category.OVER_ENGINEERING,
        Category.ERROR_HANDLING,
        Category.DEPENDENCY_GROWTH,
        Category.API_SURFACE_GROWTH,
    )

    # ------------------------------------------------------------ contract

    def version(self) -> Optional[str]:
        return "native-vue/1"

    def available(self) -> tuple[bool, Optional[str]]:
        return True, None

    def supports(self, ctx: ScanContext) -> bool:
        for cf in ctx.changed_files:
            if cf.is_binary or cf.change_kind is ChangeKind.DELETED:
                continue
            if cf.language in VUE_LANGS or cf.path.lower().endswith(VUE_SUFFIXES):
                return True
        return False

    def scan(self, ctx: ScanContext) -> ProviderResult:
        timer = self.timer()
        with timer:
            try:
                findings = self._scan(ctx)
            except Exception as exc:  # noqa: BLE001 - providers must never raise
                err = ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.CRASHED,
                    detail=f"{type(exc).__name__}: {exc}",
                    evidence_gap=False,
                )
                return ProviderResult(
                    provider=self.name,
                    status=ToolStatus.DEGRADED,
                    error=err,
                    duration_ms=timer.duration_ms,
                    version=self.version(),
                )
        return ProviderResult(
            provider=self.name,
            status=ToolStatus.OK,
            findings=findings,
            duration_ms=timer.duration_ms,
            version=self.version(),
        )

    # ---------------------------------------------------------------- scan

    def _scan(self, ctx: ScanContext) -> list[RawFinding]:
        whole = bool(ctx.options.get("whole_file"))
        changed = [
            cf
            for cf in ctx.changed_files
            if not cf.is_binary
            and cf.change_kind is not ChangeKind.DELETED
            and (
                cf.language in VUE_LANGS
                or cf.path.lower().endswith(VUE_SUFFIXES)
                or Path(cf.path).name.lower() == "package.json"
            )
        ]
        if not changed:
            return []

        files: dict[str, _JsFile] = {}
        for cf in sorted(changed, key=lambda c: c.path):
            loaded = _load(ctx.repo_root / cf.path, cf.path)
            if loaded is not None:
                files[cf.path] = loaded

        repo = _RepoJs(ctx)
        out: list[RawFinding] = []

        for path in sorted(files):
            f = files[path]
            if path.lower().endswith(".vue"):
                self._rule_unused_component(ctx, f, out, whole)
                self._rule_dup_computed(ctx, f, out, whole)
                self._rule_huge_component(ctx, f, out, whole)
            self._rule_unused_export(ctx, f, repo, out, whole)
            self._rule_api_passthru(ctx, f, repo, out, whole)
            self._rule_empty_catch(ctx, f, out, whole)
            self._rule_debug_residue(ctx, f, out, whole)
            self._rule_todo_marker(ctx, f, out, whole)
            self._rule_unused_dependency(ctx, f, repo, out, whole)

        out.sort(key=lambda r: (r.file, r.start_line, r.rule_id))
        return out

    # ------------------------------------------------------------- helpers

    def _emit(
        self,
        ctx: ScanContext,
        out: list[RawFinding],
        path: str,
        rule_id: str,
        message: str,
        start: int,
        end: int,
        symbol: Optional[str],
        category: Category,
        severity: Severity,
        confidence: float,
        detail: str,
        extra: dict[str, Any],
        whole: bool,
    ) -> None:
        if not whole:
            line = None
            for ln in range(start, end + 1):
                if ctx.is_changed_line(path, ln):
                    line = ln
                    break
            if line is None:
                return
        else:
            line = start
        out.append(
            RawFinding(
                provider=self.name,
                rule_id=rule_id,
                message=message,
                file=path,
                start_line=line,
                end_line=max(line, end),
                symbol=symbol,
                category=category,
                severity=severity,
                confidence=confidence,
                kind=EvidenceKind.DETERMINISTIC,
                detail=detail,
                extra=extra,
            )
        )

    # ------------------------------------------------------- dead / stale

    def _rule_unused_component(
        self, ctx: ScanContext, f: _JsFile, out: list[RawFinding], whole: bool
    ) -> None:
        script_m = _SCRIPT_RE.search(f.skel)
        if script_m is None:
            return
        script = script_m.group(1)
        offset = f.skel[: script_m.start(1)].count("\n")

        block_m = _COMPONENTS_BLOCK_RE.search(script)
        if block_m is None:
            return
        body = _block_of(script, block_m.end() - 1)
        if body is None:
            return
        names = [n for n in _top_level_members(body) if _IDENT_RE.match(n)]
        if not names:
            return

        tmpl_m = _TEMPLATE_RE.search(f.skel)
        template = tmpl_m.group(1) if tmpl_m else ""
        tags = {t.lower() for t in _TAG_RE.findall(template)}
        dynamic = ":is" in template or "v-bind:is" in template

        for name in names:
            kebab = _kebab(name)
            if dynamic:
                continue
            if kebab in tags or name.lower() in tags:
                continue
            # string reference anywhere in the SFC (e.g. render functions, :is="'x'")
            if re.search(r"['\"]" + re.escape(name) + r"['\"]", f.noc):
                continue
            if re.search(r"Vue\s*\.\s*component\s*\(\s*['\"]" + re.escape(kebab), f.noc):
                continue
            line = offset + script[: block_m.start()].count("\n") + 1
            self._emit(
                ctx,
                out,
                f.path,
                "CHM-JS-NAT-UNUSED-COMPONENT",
                f"Component '{name}' is registered but never used in the template",
                line,
                line,
                name,
                Category.DEAD_CODE,
                Severity.MEDIUM,
                0.8,
                "registered in `components` but no <tag> match in <template>",
                {
                    "matched_snippet": f"components: {{ {name} }}",
                    "line": line,
                    "reason": "no template tag, no dynamic :is, no string reference",
                    "component": name,
                },
                whole,
            )

    def _rule_unused_export(
        self,
        ctx: ScanContext,
        f: _JsFile,
        repo: "_RepoJs",
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        if _TEST_PATH_RE.search(f.path):
            return
        basename = Path(f.path).name.lower()
        if basename in _ENTRY_BASENAMES:
            return
        if _DYNAMIC_IMPORT_RE.search(f.noc):
            # the module may be reached through a computed specifier
            return

        for m in _EXPORT_FN_RE.finditer(f.noc):
            name = m.group(1) or m.group(2)
            if not name:
                continue
            line = f.noc[: m.start()].count("\n") + 1
            if repo.name_imported_elsewhere(name, f.path):
                continue
            self._emit(
                ctx,
                out,
                f.path,
                "CHM-JS-NAT-UNUSED-EXPORT",
                f"Exported symbol '{name}' has no importer in this repository",
                line,
                line,
                name,
                Category.DEAD_CODE,
                Severity.LOW,
                0.7,
                "no `import ... name` outside the declaring file",
                {
                    "matched_snippet": f.lines[line - 1].strip()[:200],
                    "line": line,
                    "reason": "zero cross-file importers, not an entry file",
                    "symbol": name,
                },
                whole,
            )

    # -------------------------------------------------------- duplication

    def _rule_dup_computed(
        self, ctx: ScanContext, f: _JsFile, out: list[RawFinding], whole: bool
    ) -> None:
        script_m = _SCRIPT_RE.search(f.skel)
        if script_m is None:
            return
        script = script_m.group(1)
        offset = f.skel[: script_m.start(1)].count("\n")
        block_m = _COMPUTED_BLOCK_RE.search(script)
        if block_m is None:
            return
        body = _block_of(script, block_m.end() - 1)
        if body is None:
            return

        seen: dict[str, str] = {}
        for chunk in _split_top_level(body):
            name_m = re.match(r"\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*[(:]", chunk)
            if not name_m:
                continue
            name = name_m.group(1)
            brace = chunk.find("{")
            if brace < 0:
                continue
            fn_body = _block_of(chunk, brace)
            if fn_body is None:
                continue
            norm = _normalize_body(fn_body)
            effective_lines = [ln for ln in fn_body.split("\n") if ln.strip()]
            if len(effective_lines) < 3:
                # <= 2 effective lines -> plain field access, not duplication
                continue
            line = offset + script[: block_m.start()].count("\n") + 1
            prev = seen.get(norm)
            if prev is not None:
                self._emit(
                    ctx,
                    out,
                    f.path,
                    "CHM-JS-NAT-DUP-COMPUTED",
                    f"Computed '{name}' duplicates computed '{prev}'",
                    line,
                    line,
                    name,
                    Category.DUPLICATION,
                    Severity.MEDIUM,
                    0.8,
                    "normalized computed bodies are identical",
                    {
                        "matched_snippet": norm[:200],
                        "line": line,
                        "reason": "two computed properties share the same normalized body",
                        "duplicate_of": prev,
                    },
                    whole,
                )
            else:
                seen[norm] = name

    def _rule_huge_component(
        self, ctx: ScanContext, f: _JsFile, out: list[RawFinding], whole: bool
    ) -> None:
        n_lines = len(f.lines)
        reasons: list[str] = []
        if n_lines > _SFC_LIMIT_LINES:
            reasons.append(f"{n_lines} lines > {_SFC_LIMIT_LINES}")

        script_m = _SCRIPT_RE.search(f.skel)
        script = script_m.group(1) if script_m else ""
        offset = f.skel[: script_m.start(1)].count("\n") if script_m else 0

        data_m = _DATA_BLOCK_RE.search(script)
        if data_m is not None:
            data_body = _block_of(script, data_m.end() - 1)
            if data_body is not None:
                ret_m = _DATA_RETURN_RE.search(data_body)
                if ret_m is not None:
                    obj = _block_of(data_body, ret_m.end() - 1)
                    if obj is not None:
                        fields = [x for x in _top_level_members(obj) if _IDENT_RE.match(x)]
                        if len(fields) > _SFC_LIMIT_DATA_FIELDS:
                            reasons.append(f"data() returns {len(fields)} fields")

        meth_m = _METHODS_BLOCK_RE.search(script)
        if meth_m is not None:
            meth_body = _block_of(script, meth_m.end() - 1)
            if meth_body is not None:
                methods = [x for x in _top_level_members(meth_body) if _IDENT_RE.match(x)]
                if len(methods) > _SFC_LIMIT_METHODS:
                    reasons.append(f"methods has {len(methods)} members")

        if not reasons:
            return
        line = 1
        for ln in range(1, n_lines + 1):
            if ctx.is_changed_line(f.path, ln) or whole:
                line = ln
                break
        self._emit(
            ctx,
            out,
            f.path,
            "CHM-JS-NAT-HUGE-COMPONENT",
            "Vue SFC is oversized",
            line,
            min(n_lines, line + 1),
            None,
            Category.LARGE_CLASS,
            Severity.LOW,
            0.75,
            "; ".join(reasons),
            {
                "matched_snippet": f.lines[line - 1].strip()[:200] if line <= n_lines else "",
                "line": line,
                "reason": "; ".join(reasons),
                "line_count": n_lines,
                "script_offset": offset,
            },
            whole,
        )

    # ------------------------------------------------------------ quality

    def _rule_api_passthru(
        self,
        ctx: ScanContext,
        f: _JsFile,
        repo: "_RepoJs",
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        if not re.search(r"(?:^|/)api/", f.path.replace("\\", "/")):
            return
        for m in _API_PASSTHRU_RE.finditer(f.skel):
            name = m.group(1)
            line = f.skel[: m.start()].count("\n") + 1
            if repo.count_references(name, f.path) > 1:
                # more than one call site -> the wrapper is carrying its weight
                continue
            # suppression: the function normalises errors / rewrites params
            window = "\n".join(f.lines[max(0, line - 2) : line + 12])
            if re.search(r"\.then\s*\(|\.catch\s*\(|try\s*\{|throw\s|interceptor|retry|signal", window):
                continue
            self._emit(
                ctx,
                out,
                f.path,
                "CHM-JS-NAT-API-WRAPPER-PASSTHRU",
                f"API wrapper '{name}' only forwards to request() and has one caller",
                line,
                line,
                name,
                Category.OVER_ENGINEERING,
                Severity.LOW,
                0.6,
                "pure pass-through wrapper with a single call site",
                {
                    "matched_snippet": f.lines[line - 1].strip()[:200],
                    "line": line,
                    "reason": "single caller, no error/param transformation",
                    "symbol": name,
                },
                whole,
            )

    def _rule_empty_catch(
        self, ctx: ScanContext, f: _JsFile, out: list[RawFinding], whole: bool
    ) -> None:
        # ``f.skel`` drops the comment delimiters, so its offsets do not index
        # ``f.text``; this rule needs the real body text.
        skel = _aligned_skeleton(f.text)
        open_to_close, close_to_open = _brace_pairs(skel)
        for cm in _CATCH_RE.finditer(skel):
            brace = cm.start("brace")
            close = open_to_close.get(brace)
            if close is None:
                continue
            if skel[brace + 1 : close].strip():
                continue
            try_pair = _enclosing_try(skel, cm.start(), close_to_open)
            if try_pair is None:
                continue
            try_open, try_close = try_pair
            raw_body = f.text[brace + 1 : close]
            if not _comment_only(raw_body):
                # the skeleton blanked a statement (e.g. a bare string literal)
                continue
            if re.search(
                r"(?:ignore|noop|no-op|intentionally|expected|swallow)", raw_body, re.I
            ):
                continue

            binding = (cm.group("bind") or "").strip()
            unused_binding = bool(_UNUSED_BINDING_RE.match(binding))
            probe = bool(_PROBE_CALL_RE.search(skel[try_open + 1 : try_close]))
            has_comment = bool(re.search(r"//|/\*", raw_body))
            tail = _is_last_in_block(skel, close)
            tail_loop = tail and _block_owner(skel, close, close_to_open) in _LOOP_OWNERS

            signals: list[str] = []
            if unused_binding:
                signals.append("catch binding is deliberately unused")
            if probe:
                signals.append("try body only probes / parses / cleans up")
            if tail_loop:
                signals.append("try/catch is the last statement of a loop body")
            elif tail:
                signals.append("try/catch is the last statement of its enclosing block")
            if has_comment:
                signals.append("catch block carries a comment")

            # Downgrade (never suppress) when the shape says "intentional":
            #   * the author annotated the catch, or
            #   * the try body is a probe/parse/cleanup, or
            #   * the binding is deliberately unused AND nothing follows.
            # ``catch (Exception e) {}`` with none of these stays HIGH
            # (spec CHM-ERR-001).
            downgrade = has_comment or probe or (unused_binding and tail)
            line = skel[: cm.start()].count("\n") + 1
            detail = (
                "catch block is empty; " + "; ".join(signals) + " - needs confirmation"
                if downgrade
                else "catch block contains no statements at all"
            )
            self._emit(
                ctx,
                out,
                f.path,
                "CHM-JS-NAT-EMPTY-CATCH",
                "Empty catch block swallows the error",
                line,
                line,
                binding or None,
                Category.ERROR_HANDLING,
                Severity.LOW if downgrade else Severity.HIGH,
                0.5 if downgrade else 0.9,
                detail,
                {
                    "matched_snippet": f.lines[line - 1].strip()[:200],
                    "line": line,
                    "reason": detail,
                    "catch_binding": binding,
                    "signals": signals,
                    "note": (
                        "looks like an intentional probe/cleanup; confirm"
                        if downgrade
                        else ""
                    ),
                },
                whole,
            )

    def _rule_debug_residue(
        self, ctx: ScanContext, f: _JsFile, out: list[RawFinding], whole: bool
    ) -> None:
        if _TEST_PATH_RE.search(f.path) or _TOOLING_PATH_RE.search(f.path):
            # test code and CLI tooling: stdout is the product, not residue
            return
        for m in _CONSOLE_RE.finditer(f.skel):
            line = f.skel[: m.start()].count("\n") + 1
            self._emit(
                ctx,
                out,
                f.path,
                "CHM-JS-NAT-DEBUG-RESIDUE",
                f"console.{m.group(1)} left in production code",
                line,
                line,
                None,
                Category.DEAD_CODE,
                Severity.LOW,
                0.9,
                "debug print in a non-test path",
                {
                    "matched_snippet": f.lines[line - 1].strip()[:200],
                    "line": line,
                    "reason": "console debug statement",
                },
                whole,
            )

    def _rule_todo_marker(
        self, ctx: ScanContext, f: _JsFile, out: list[RawFinding], whole: bool
    ) -> None:
        for i, raw in enumerate(f.lines):
            m = _TODO_RE.search(raw)
            if m is None:
                continue
            line = i + 1
            self._emit(
                ctx,
                out,
                f.path,
                "CHM-JS-NAT-TODO-MARKER",
                f"{m.group(1)} marker left in code",
                line,
                line,
                None,
                Category.DEAD_CODE,
                Severity.LOW,
                0.9,
                "TODO/FIXME marker in a comment",
                {
                    "matched_snippet": raw.strip()[:200],
                    "line": line,
                    "reason": "unresolved marker",
                },
                whole,
            )

    def _rule_unused_dependency(
        self,
        ctx: ScanContext,
        f: _JsFile,
        repo: "_RepoJs",
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        if Path(f.path).name.lower() != "package.json":
            return
        data = _load_package_json(f.text)
        if data is None:
            return
        deps = data.get("dependencies")
        if not isinstance(deps, dict):
            return
        for pkg in sorted(deps):
            if not isinstance(pkg, str):
                continue
            if repo.package_referenced(pkg):
                continue
            line = _find_line(f.lines, pkg)
            self._emit(
                ctx,
                out,
                f.path,
                "CHM-JS-NAT-UNUSED-DEPENDENCY-DECL",
                f"Dependency '{pkg}' is declared but never imported",
                line,
                line,
                pkg,
                Category.DEPENDENCY_GROWTH,
                Severity.MEDIUM,
                0.7,
                "no import/require of this package anywhere in the sources",
                {
                    "matched_snippet": f.lines[line - 1].strip()[:200] if line <= len(f.lines) else pkg,
                    "line": line,
                    "reason": "zero source references",
                    "package": pkg,
                },
                whole,
            )


# --------------------------------------------------------------------------
# repository level helper
# --------------------------------------------------------------------------


def _split_top_level(block: str) -> list[str]:
    out: list[str] = []
    depth = 0
    start = 0
    i = 0
    n = len(block)
    while i < n:
        ch = block[i]
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(block[start:i])
            start = i + 1
        i += 1
    out.append(block[start:])
    return out


def _load_package_json(text: str) -> Optional[dict[str, Any]]:
    import json

    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _find_line(lines: list[str], needle: str) -> int:
    for i, ln in enumerate(lines):
        if '"' + needle + '"' in ln:
            return i + 1
    return 1


class _RepoJs:
    """Lazy, deterministic repo-wide text index for JS/TS rules."""

    def __init__(self, ctx: ScanContext) -> None:
        self._ctx = ctx
        self._texts: Optional[dict[str, str]] = None

    def _load(self) -> dict[str, str]:
        if self._texts is not None:
            return self._texts
        ctx = self._ctx
        root = Path(ctx.repo_root)
        excludes = list(getattr(ctx.config, "excludes", None) or ())
        if ctx.repo_files:
            rels = sorted({p.replace("\\", "/") for p in ctx.repo_files})
            paths = [root / r for r in rels if r.lower().endswith(VUE_SUFFIXES)]
        else:
            paths = sorted(iter_files(root, suffixes=list(VUE_SUFFIXES), excludes=excludes))
        texts: dict[str, str] = {}
        for p in paths[:2000]:
            try:
                rel = p.resolve().relative_to(root.resolve()).as_posix()
            except (ValueError, OSError):
                rel = p.as_posix()
            texts[rel] = read_text(p, max_bytes=MAX_FILE_BYTES)
        self._texts = texts
        return texts

    def name_imported_elsewhere(self, name: str, own_path: str) -> bool:
        pat = re.compile(r"\b" + re.escape(name) + r"\b")
        for rel in sorted(self._load()):
            if rel == own_path:
                continue
            text = self._load()[rel]
            if not text:
                continue
            for m in pat.finditer(text):
                head = text[max(0, m.start() - 120) : m.start()]
                if "import" in head or "require(" in head:
                    return True
        return False

    def count_references(self, name: str, own_path: str) -> int:
        """Call sites of ``name`` outside the declaring file (imports excluded)."""
        pat = re.compile(r"\b" + re.escape(name) + r"\s*\(")
        total = 0
        for rel in sorted(self._load()):
            if rel == own_path:
                continue
            total += len(pat.findall(self._load()[rel]))
        return total

    def package_referenced(self, pkg: str) -> bool:
        escaped = re.escape(pkg)
        pats = (
            re.compile(r"""from\s*['"]""" + escaped + r"""['"]"""),
            re.compile(r"""require\s*\(\s*['"]""" + escaped + r"""['"]"""),
            re.compile(r"""import\s*\(\s*['"]""" + escaped + r"""['"]"""),
            re.compile(r"""import\s*['"]""" + escaped + r"""['"]"""),
        )
        for rel in sorted(self._load()):
            text = self._load()[rel]
            if not text:
                continue
            for p in pats:
                if p.search(text):
                    return True
        return False


__all__ = ["VueNativeAnalyzer", "PROVIDER_NAME"]
