"""Risk-scaled context packing -- spec §14.2.

The gate must never hand a whole repository to a model.  It starts from the
diff, then *buys* extra context only when the risk level justifies it:

===========  ==========================================================
LOW          diff + the changed files themselves
MEDIUM       + direct references (callers / callees of changed symbols)
HIGH         + call graph, tests, configuration, business rules
CRITICAL     + full related slices and everything multi-model review needs
===========  ==========================================================

Two invariants matter for the review protocol:

* every byte in :class:`ContextFile.content` has already been through
  :func:`~chm.context.secretfilter.scrub`;
* the writer's own rationale is **absent** unless
  ``include_writer_rationale=True``, which is what makes
  :meth:`ContextPack.fingerprint` usable as evidence that reviewer A and
  reviewer B saw genuinely different contexts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..config import Config
from ..contracts import ScanContext
from ..util import read_text, sha256_text, stable_json
from .secretfilter import is_secret_file, scrub
from .symbols import SymbolIndex

__all__ = ["ContextFile", "ContextPack", "estimate_tokens", "build_context_pack"]

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

#: per-risk budget of *extra* material
_CAPS: dict[str, dict[str, int]] = {
    "LOW": {"refs": 0, "callees": 0, "tests": 0, "config": 0, "rules": 0},
    "MEDIUM": {"refs": 40, "callees": 20, "tests": 0, "config": 0, "rules": 0},
    "HIGH": {"refs": 60, "callees": 30, "tests": 4, "config": 4, "rules": 3},
    "CRITICAL": {"refs": 80, "callees": 40, "tests": 6, "config": 6, "rules": 5},
}

#: how many symbols of a changed file we are willing to chase references for
MAX_SYMS_PER_FILE = 40
#: reference hits considered per symbol
MAX_REFS_PER_SYMBOL = 12

#: lines of context kept around a change when a file must be truncated
WINDOW_RADIUS = 80
#: lines kept from the head of a large file that has no change coordinates
HEAD_LINES = 200
#: files above this size are never read into the pack at all
MAX_PACK_READ_BYTES = 16 * 1024 * 1024

_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

_TEST_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs)(/|$)"
    r"|(^|/)[\w.\-]+(?:\.|-)(?:test|spec)\.(?:java|js|jsx|ts|tsx|vue|py)$"
    r"|(^|/)(?:Test|IT)[\w]*\.java$",
    re.I,
)
_CONFIG_RE = re.compile(
    r"(^|/)(pom\.xml|build\.gradle(?:\.kts)?|settings\.gradle|gradle\.properties|"
    r"package\.json|tsconfig[\w.\-]*\.json|application[\w.\-]*\.(?:ya?ml|properties)|"
    r"bootstrap[\w.\-]*\.(?:ya?ml|properties)|[\w.\-]+\.config\.(?:js|ts|mjs|cjs)|"
    r"webpack\.[\w.\-]+\.js|vite\.config\.[\w]+|\.env[\w.\-]*|"
    r"mybatis[\w.\-]*\.xml|logback[\w.\-]*\.xml)$",
    re.I,
)
_RULE_RE = re.compile(
    r"(^|/)(rules|docs|requirements|specs)/"
    r"|\.feature$"
    r"|(^|/)(README|REQUIREMENTS|SPEC|AGENTS|CONTRIBUTING)\.md$",
    re.I,
)


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------


@dataclass
class ContextFile:
    path: str
    reason: str
    content: str
    truncated: bool = False
    bytes: int = 0
    #: selection rank; not serialised (it is an implementation detail)
    priority: int = field(default=99, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reason": self.reason,
            "content": self.content,
            "truncated": self.truncated,
            "bytes": self.bytes,
        }


@dataclass
class ContextPack:
    risk: str
    files: list[ContextFile] = field(default_factory=list)
    requirement_context: str = ""
    test_evidence: str = ""
    total_bytes: int = 0
    total_tokens_estimate: int = 0
    truncated: bool = False
    expansion_reason: str = ""
    #: populated only when the caller explicitly opts in
    writer_rationale: str = ""
    writer_rationale_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk": self.risk,
            "files": [f.to_dict() for f in self.files],
            "requirement_context": self.requirement_context,
            "test_evidence": self.test_evidence,
            "total_bytes": self.total_bytes,
            "total_tokens_estimate": self.total_tokens_estimate,
            "truncated": self.truncated,
            "expansion_reason": self.expansion_reason,
            "writer_rationale": self.writer_rationale,
            "writer_rationale_included": self.writer_rationale_included,
        }

    def fingerprint(self) -> str:
        """Content hash of the pack -- proves which context a reviewer saw."""
        return sha256_text(stable_json(self.to_dict()))

    def paths(self) -> list[str]:
        return [f.path for f in self.files]


def estimate_tokens(text: str) -> int:
    """Deterministic, backend-agnostic token estimate.

    ~4 characters per token for ASCII and ~1 token per CJK character.  It is
    only used for budgeting, never for billing.
    """
    if not text:
        return 0
    ascii_chars = len(text.encode("ascii", "ignore"))
    other = len(text) - ascii_chars
    return int(math.ceil(ascii_chars / 4.0 + other))


# --------------------------------------------------------------------------
# truncation
# --------------------------------------------------------------------------


def _expand_merge(ranges: list[tuple[int, int]], radius: int, total: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for start, end in ranges:
        a = max(1, start - radius)
        b = min(total, end + radius)
        if a > b:
            continue
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _window_text(text: str, ranges: list[tuple[int, int]], limit_bytes: int) -> str:
    lines = text.split("\n")
    total = len(lines)
    keep = _expand_merge(ranges, WINDOW_RADIUS, total) if ranges else [(1, min(total, HEAD_LINES))]
    parts: list[str] = []
    prev_end = 0
    for a, b in keep:
        if a > prev_end + 1:
            parts.append(f"... [{a - prev_end - 1} lines elided] ...")
        parts.extend(lines[a - 1:b])
        prev_end = b
    if prev_end < total:
        parts.append(f"... [{total - prev_end} lines elided] ...")
    windowed = "\n".join(parts)

    if len(windowed.encode("utf-8")) <= limit_bytes:
        return windowed

    # still too big: hard cut on a line boundary
    out: list[str] = []
    used = 0
    for line in windowed.split("\n"):
        size = len(line.encode("utf-8")) + 1
        if used + size > limit_bytes:
            out.append(f"... [truncated at {limit_bytes} bytes] ...")
            break
        out.append(line)
        used += size
    return "\n".join(out)


def _change_ranges(cf: Any) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for h in cf.hunks:
        if h.new_count <= 0:
            continue
        ranges.append((h.new_start, h.new_start + h.new_count - 1))
    return ranges


# --------------------------------------------------------------------------
# packing
# --------------------------------------------------------------------------


def build_context_pack(
    ctx: ScanContext,
    findings: Optional[list[Any]] = None,
    *,
    risk: str,
    config: Config,
    index: Optional[SymbolIndex] = None,
    writer_rationale: Optional[str] = None,
    include_writer_rationale: bool = False,
) -> ContextPack:
    """Assemble the LLM context for one review at the requested risk level."""
    level = (risk or "LOW").upper()
    if level not in RISK_LEVELS:
        level = "LOW"
    caps = _CAPS[level]
    budget = max(1, int(config.token.max_file_bytes_for_llm))
    max_files = int(config.token.max_context_files)

    candidates: dict[str, tuple[int, str]] = {}
    notes: list[str] = []

    def add(path: str, priority: int, reason: str) -> None:
        rel = str(path).replace("\\", "/").lstrip("./")
        if not rel or config.is_excluded(rel):
            return
        if is_secret_file(rel):
            notes.append(f"secret-bearing file withheld from model context: {rel}")
            return
        current = candidates.get(rel)
        if current is None or priority < current[0]:
            candidates[rel] = (priority, reason)

    changed = [cf for cf in ctx.changed_files]
    changed_paths = {cf.path for cf in changed}

    # ---- always: the diff itself ---------------------------------------
    for cf in changed:
        if cf.is_binary:
            notes.append(f"binary changed file skipped: {cf.path}")
            continue
        add(cf.path, 0, "changed file")

    # ---- findings' own locations ---------------------------------------
    for finding in findings or []:
        loc = getattr(finding, "location", None)
        if loc is None:
            continue
        add(getattr(loc, "file", "") or "", 1, "finding location")

    # ---- MEDIUM+: direct references and callees ------------------------
    if caps["refs"] or caps["callees"]:
        if index is None:
            notes.append("no symbol index available; reference expansion skipped")
        else:
            ref_budget = caps["refs"]
            for cf in changed:
                for sym in index.symbols(cf.path)[:MAX_SYMS_PER_FILE]:
                    if ref_budget <= 0:
                        break
                    if len(sym.name) < 3:
                        continue
                    for ref in index.references(sym.name)[:MAX_REFS_PER_SYMBOL]:
                        if ref_budget <= 0:
                            break
                        if ref["file"] in changed_paths:
                            continue
                        add(ref["file"], 1, f"references {sym.name}")
                        ref_budget -= 1

            callee_budget = caps["callees"]
            for cf in changed:
                if callee_budget <= 0:
                    break
                text = index.file_text(cf.path)
                if not text:
                    continue
                local = {s.name for s in index.symbols(cf.path)}
                for token in sorted(set(_IDENT_RE.findall(text))):
                    if callee_budget <= 0:
                        break
                    if token in local or len(token) < 4:
                        continue
                    for sym in index.definitions(token)[:1]:
                        if sym.file in changed_paths:
                            continue
                        add(sym.file, 2, f"defines {token}, used by {cf.path}")
                        callee_budget -= 1

    # ---- HIGH+: tests, configuration, business rules -------------------
    if caps["tests"] or caps["config"] or caps["rules"]:
        names = {s.name for cf in changed for s in (index.symbols(cf.path) if index else [])}
        names |= {Path(cf.path).stem for cf in changed}

        def _mentions(path: str) -> bool:
            if index is None:
                return False
            text = index.file_text(path)
            return bool(text) and any(n and n in text for n in names)

        test_budget, config_budget, rule_budget = caps["tests"], caps["config"], caps["rules"]
        for rel in ctx.repo_files:
            if test_budget <= 0 and config_budget <= 0 and rule_budget <= 0:
                break
            if test_budget > 0 and _TEST_RE.search(rel) and _mentions(rel):
                add(rel, 3, "test evidence for changed symbols")
                test_budget -= 1
                continue
            if config_budget > 0 and _CONFIG_RE.search(rel):
                add(rel, 4, "build/runtime configuration")
                config_budget -= 1
                continue
            if rule_budget > 0 and _RULE_RE.search(rel) and _mentions(rel):
                add(rel, 5, "business rule / requirement document")
                rule_budget -= 1

    # ---- select, truncate to budget ------------------------------------
    ordered = sorted(candidates.items(), key=lambda kv: (kv[1][0], kv[0]))
    selected = ordered
    dropped: list[str] = []
    if max_files > 0 and len(ordered) > max_files:
        selected = ordered[:max_files]
        dropped = [p for p, _ in ordered[max_files:]]

    files: list[ContextFile] = []
    for path, (priority, reason) in selected:
        full = ctx.repo_root / path
        if not full.is_file():
            content = f"[{reason}: file is absent from the worktree (deleted or renamed)]"
            files.append(
                ContextFile(path=path, reason=reason, content=content, truncated=False,
                            bytes=len(content.encode("utf-8")), priority=priority)
            )
            continue

        if config.is_generated(path) and config.token.exclude_generated_from_llm:
            try:
                size = full.stat().st_size
            except OSError:
                size = 0
            content = f"[generated file omitted from LLM context: {path} ({size} bytes)]"
            files.append(
                ContextFile(path=path, reason=reason, content=content, truncated=False,
                            bytes=len(content.encode("utf-8")), priority=priority)
            )
            continue

        try:
            size = full.stat().st_size
        except OSError:
            size = 0

        if size > MAX_PACK_READ_BYTES:
            content = (
                f"[file too large for LLM context: {path} ({size} bytes, "
                f"read limit {MAX_PACK_READ_BYTES})]"
            )
            files.append(
                ContextFile(path=path, reason=reason, content=content, truncated=True,
                            bytes=len(content.encode("utf-8")), priority=priority)
            )
            continue

        raw = read_text(full, max_bytes=size + 1)
        # LF-normalise so a Windows and a Linux checkout of the same commit
        # produce the same pack (and therefore the same fingerprint).
        if "\r" in raw:
            raw = raw.replace("\r\n", "\n").replace("\r", "\n")
        truncated = False
        if size > budget:
            ranges: list[tuple[int, int]] = []
            cf = ctx.changed_file(path)
            if cf is not None:
                ranges = _change_ranges(cf)
            raw = _window_text(raw, ranges, budget)
            truncated = True

        scrubbed = scrub(raw)
        content = scrubbed.text
        if len(content.encode("utf-8")) > budget:
            content = _window_text(content, [], budget)
            truncated = True

        files.append(
            ContextFile(
                path=path,
                reason=reason,
                content=content,
                truncated=truncated,
                bytes=len(content.encode("utf-8")),
                priority=priority,
            )
        )

    # ---- requirement / test evidence -----------------------------------
    req = scrub(ctx.requirement_context or "").text
    tests = scrub(ctx.test_evidence or "").text

    # ---- writer rationale: opt-in only ---------------------------------
    rationale = ""
    if include_writer_rationale and writer_rationale:
        rationale = scrub(writer_rationale).text

    total_bytes = (
        sum(f.bytes for f in files)
        + len(req.encode("utf-8"))
        + len(tests.encode("utf-8"))
        + len(rationale.encode("utf-8"))
    )
    total_tokens = (
        sum(estimate_tokens(f.content) for f in files)
        + estimate_tokens(req)
        + estimate_tokens(tests)
        + estimate_tokens(rationale)
    )

    buckets: dict[int, int] = {}
    for f in files:
        buckets[f.priority] = buckets.get(f.priority, 0) + 1
    labels = {0: "changed", 1: "references", 2: "callees", 3: "tests", 4: "config", 5: "rules"}
    summary = ", ".join(f"{labels.get(k, str(k))}={buckets[k]}" for k in sorted(buckets)) or "none"

    reason_parts = [
        f"risk={level}",
        f"files={len(files)}/{len(ordered)} ({summary})",
        f"budget_files={max_files}",
        f"budget_bytes_per_file={budget}",
    ]
    if dropped:
        reason_parts.append(
            f"dropped {len(dropped)} lower-priority file(s): {', '.join(dropped[:8])}"
            + (" ..." if len(dropped) > 8 else "")
        )
    if any(f.truncated for f in files):
        reason_parts.append(
            "truncated: " + ", ".join(f.path for f in files if f.truncated)[:400]
        )
    if notes:
        reason_parts.append("notes: " + "; ".join(notes[:6]))
    if include_writer_rationale and rationale:
        reason_parts.append("writer rationale included")

    return ContextPack(
        risk=level,
        files=files,
        requirement_context=req,
        test_evidence=tests,
        total_bytes=total_bytes,
        total_tokens_estimate=total_tokens,
        truncated=bool(dropped) or any(f.truncated for f in files),
        expansion_reason="; ".join(reason_parts),
        writer_rationale=rationale,
        writer_rationale_included=bool(rationale),
    )
