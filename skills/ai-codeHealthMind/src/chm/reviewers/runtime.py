"""Reviewer execution: ``off`` / ``rule`` / ``llm`` backends.

Three rules shape this module:

* **No fabricated calls.**  ``backend="llm"`` with no ``llm_command`` configured
  is a real ``CONFIG`` failure, returned as a failed call -- never a silent
  fallback to the rule backend pretending to be a model.
* **Honest labelling.**  Rule-backend findings are marked
  ``provider="reviewer:<persona>:rule"`` with ``{"backend": "rule",
  "is_llm": False}`` in ``extra``.  They are semantic *heuristics*, not an
  independent model opinion.
* **Determinism.**  The rule backend is pure Python over the input; identical
  input produces byte-identical findings (spec §41).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..config import Config
from ..contracts import Language, ScanContext
from ..errors import ToolError, ToolFailureKind
from ..schema import (
    Category,
    EvidenceKind,
    PerfConfidence,
    RawFinding,
    RepairClass,
    Severity,
)
from ..util import clamp, strip_comments_and_strings
from .personas import Persona
from .prompt import (
    assert_isolation,
    build_reviewer_prompt,
    context_payload,
    payload_fingerprint,
)

#: Fixed wall-clock ceiling for a reviewer call when the token budget cannot be
#: translated into a deadline.
_DEFAULT_TIMEOUT_S = 300.0
#: Assumed generation throughput used to turn a token budget into a deadline.
_TOKENS_PER_SECOND = 20.0

_SOURCE_SUFFIXES = (".java", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue")
_SOURCE_LANGUAGES = (
    Language.JAVA,
    Language.JAVASCRIPT,
    Language.TYPESCRIPT,
    Language.VUE,
)

_MAX_SCAN_FILES = 300
_MAX_FILE_CHARS = 400_000


def _estimate_tokens(text: str) -> int:
    """Token estimate, preferring the context layer's own estimator."""
    if not text:
        return 0
    try:
        from ..context.packer import estimate_tokens
    except ImportError:
        return max(1, len(text) // 4)
    return int(estimate_tokens(text))


def _timeout_for(config: Config) -> float:
    budget = int(getattr(config.review, "max_tokens_per_call", 6000) or 0)
    if budget <= 0:
        return _DEFAULT_TIMEOUT_S
    return float(max(30.0, min(600.0, budget / _TOKENS_PER_SECOND)))


# --------------------------------------------------------------------------
# result records
# --------------------------------------------------------------------------


@dataclass
class ReviewerCall:
    persona: str
    model: str
    prompt_chars: int
    input_tokens: int
    output_tokens: int
    duration_ms: int
    ok: bool
    error: Optional[str]
    command: Optional[str]
    context_fingerprint: str
    isolation_ok: bool
    isolation_reason: str
    # -- additions kept at the tail so the positional contract stays intact --
    backend: str = "rule"
    skipped: bool = False
    error_kind: Optional[str] = None
    estimated: bool = False

    def to_dict(self) -> dict:
        return {
            "persona": self.persona,
            "model": self.model,
            "prompt_chars": self.prompt_chars,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
            "error": self.error,
            "command": self.command,
            "context_fingerprint": self.context_fingerprint,
            "isolation_ok": self.isolation_ok,
            "isolation_reason": self.isolation_reason,
            "backend": self.backend,
            "skipped": self.skipped,
            "error_kind": self.error_kind,
            "estimated": self.estimated,
        }


@dataclass
class ReviewerOutput:
    persona: str
    model: str
    findings: list[RawFinding]
    raw_text: str
    call: ReviewerCall
    tool_error: Optional[ToolError] = None

    def to_dict(self) -> dict:
        return {
            "persona": self.persona,
            "model": self.model,
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "category": f.category.value if f.category else None,
                    "severity": f.severity.value if f.severity else None,
                    "file": f.file,
                    "start_line": f.start_line,
                    "symbol": f.symbol,
                    "provider": f.provider,
                    "kind": f.kind.value,
                    "confidence": f.confidence,
                    "extra": dict(f.extra),
                }
                for f in self.findings
            ],
            "call": self.call.to_dict(),
            "tool_error": self.tool_error.to_dict() if self.tool_error else None,
        }


# --------------------------------------------------------------------------
# source scanning helpers (shared by the rule backend)
# --------------------------------------------------------------------------

_CLASS_RE = re.compile(r"\b(class|interface|enum|record)\s+([A-Za-z_$][\w$]*)")
_METHOD_RE = re.compile(
    r"\b(public|protected|private)\s+(?:static\s+|final\s+|synchronized\s+|abstract\s+|native\s+|default\s+)*"
    r"([\w$<>\[\],\.\?\s]+?)\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?:\{|throws|;)"
)
_IMPL_RE = re.compile(r"\bimplements\s+([^{;]+)")
_METHOD_KEYWORDS = {
    "if", "for", "while", "switch", "catch", "return", "new", "synchronized",
    "try", "else", "do", "case", "throw", "assert",
}
_WRAPPER_TYPES = {
    "String", "Integer", "Long", "Boolean", "Double", "Float", "Short", "Byte",
    "Character", "Object", "int", "long", "boolean", "double", "float", "short",
    "byte", "char", "void", "BigDecimal", "BigInteger", "LocalDate", "LocalDateTime",
    "Instant", "Date",
}
_IO_CALL_RE = re.compile(
    r"(\.query\s*\(|\.queryForObject\s*\(|\.queryForList\s*\(|\.findAll\s*\(|\.findBy[\w]*\s*\(|"
    r"\.select[\w]*\s*\(|\.save\s*\(|\.insert\s*\(|\.update\s*\(|\.delete\s*\(|\.execute\s*\(|"
    r"\.executeQuery\s*\(|\.getForObject\s*\(|\.getForEntity\s*\(|\.postForObject\s*\(|"
    r"\.exchange\s*\(|\.get\s*\(|\.call\s*\()"
)
_LOOP_RE = re.compile(r"\b(for|while)\s*\(")
_REMOTE_CALL_RE = re.compile(
    r"(restTemplate|RestTemplate|WebClient|webClient|HttpClient|OkHttp|HttpURLConnection|"
    r"FeignClient|feignClient|\.getForObject\s*\(|\.postForObject\s*\(|\.exchange\s*\(|"
    r"\.execute\s*\(\s*new\s+HttpGet|\.url\s*\()"
)
_TRANSACTIONAL_RE = re.compile(r"@Transactional\b")
_NULL_GUARD_RE = re.compile(r"if\s*\(\s*([A-Za-z_$][\w$\.]*)\s*(?:!=\s*null|==\s*null)\s*\)")
_REGISTER_RE = re.compile(r"\.(register|put|add|addAll|computeIfAbsent|putIfAbsent)\s*\(")
_BOUNDARY_RE = re.compile(
    r"(Feign|Mapper|Rpc|RPC|Remote|Dubbo|Thrift|Grpc|gRPC|Spi|SPI|"
    r"@Mapper|@FeignClient|@Remote|@Rpc|@Spi)"
)


@dataclass
class _FileView:
    path: str
    text: str
    lines: list[str]
    decls: list[dict]


def _split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _scan_declarations(clean_lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for i, line in enumerate(clean_lines, start=1):
        for m in _CLASS_RE.finditer(line):
            out.append({"kind": m.group(1), "name": m.group(2), "line": i, "text": line})
        m = _METHOD_RE.search(line)
        if m and m.group(3) not in _METHOD_KEYWORDS:
            out.append(
                {
                    "kind": "method",
                    "name": m.group(3),
                    "line": i,
                    "text": line,
                    "visibility": m.group(1),
                    "params": m.group(4),
                }
            )
    return out


def _brace_span(lines: list[str], start_idx: int, limit: int = 400) -> tuple[int, int]:
    """(first_line_idx, last_line_idx) inclusive, 0-based, for a braced body."""
    depth = 0
    started = False
    end = min(len(lines) - 1, start_idx + limit)
    for j in range(start_idx, min(len(lines), start_idx + limit)):
        depth += lines[j].count("{") - lines[j].count("}")
        if "{" in lines[j]:
            started = True
        if started and depth <= 0:
            return start_idx, j
        end = j
    return start_idx, end


class ReviewerRuntime:
    """Runs reviewer personas and records exactly what happened."""

    def __init__(self, config: Config, *, ledger: Any = None) -> None:
        self.config = config
        self.ledger = ledger
        self._calls: list[ReviewerCall] = []

    # ------------------------------------------------------------- public

    def calls(self) -> list[ReviewerCall]:
        return list(self._calls)

    def token_totals(self) -> dict:
        estimated = any(c.estimated for c in self._calls)
        return {
            "input": sum(c.input_tokens for c in self._calls),
            "output": sum(c.output_tokens for c in self._calls),
            "calls": len(self._calls),
            "estimated": estimated,
        }

    def review(
        self,
        persona: Persona,
        ctx: ScanContext,
        pack: Any,
        *,
        model: Optional[str] = None,
        include_writer_rationale: bool = False,
        writer_rationale: Optional[str] = None,
    ) -> ReviewerOutput:
        backend = str(getattr(self.config.review, "backend", "rule") or "rule").lower()
        chosen_model = model or getattr(self.config.review, "model_a", "model-a")
        started = time.perf_counter()

        payload = context_payload(
            pack,
            include_writer_rationale=include_writer_rationale,
            writer_rationale=writer_rationale,
        )
        fingerprint = payload_fingerprint(payload)
        if include_writer_rationale:
            iso_ok, iso_reason = False, (
                "writer rationale included on explicit caller request; "
                "context isolation is disabled for this call"
            )
        else:
            iso_ok, iso_reason = assert_isolation(payload, writer_rationale)

        if backend == "off":
            call = ReviewerCall(
                persona=persona.key,
                model=chosen_model,
                prompt_chars=0,
                input_tokens=0,
                output_tokens=0,
                duration_ms=int((time.perf_counter() - started) * 1000),
                ok=True,
                error=None,
                command=None,
                context_fingerprint=fingerprint,
                isolation_ok=iso_ok,
                isolation_reason=iso_reason,
                backend="off",
                skipped=True,
                estimated=False,
            )
            self._calls.append(call)
            return ReviewerOutput(
                persona=persona.key, model=chosen_model, findings=[], raw_text="", call=call
            )

        if backend == "llm":
            return self._llm_review(
                persona,
                ctx,
                pack,
                model=chosen_model,
                include_writer_rationale=include_writer_rationale,
                writer_rationale=writer_rationale,
                payload=payload,
                fingerprint=fingerprint,
                iso_ok=iso_ok,
                iso_reason=iso_reason,
                started=started,
            )

        findings = self._rule_review(persona, ctx, pack)
        call = ReviewerCall(
            persona=persona.key,
            model=chosen_model,
            prompt_chars=0,
            input_tokens=0,
            output_tokens=0,
            duration_ms=int((time.perf_counter() - started) * 1000),
            ok=True,
            error=None,
            command=None,
            context_fingerprint=fingerprint,
            isolation_ok=iso_ok,
            isolation_reason=iso_reason,
            backend="rule",
            skipped=False,
            estimated=False,
        )
        self._calls.append(call)
        return ReviewerOutput(
            persona=persona.key,
            model=chosen_model,
            findings=findings,
            raw_text="",
            call=call,
        )

    # ------------------------------------------------------------ llm path

    def _llm_review(
        self,
        persona: Persona,
        ctx: ScanContext,
        pack: Any,
        *,
        model: str,
        include_writer_rationale: bool,
        writer_rationale: Optional[str],
        payload: str,
        fingerprint: str,
        iso_ok: bool,
        iso_reason: str,
        started: float,
    ) -> ReviewerOutput:
        prompt = build_reviewer_prompt(
            persona,
            pack,
            ctx,
            model=model,
            include_writer_rationale=include_writer_rationale,
            writer_rationale=writer_rationale,
        )
        template = getattr(self.config.review, "llm_command", None)
        if not template:
            err = ToolError(
                provider=f"reviewer:{persona.key}",
                kind=ToolFailureKind.CONFIG,
                detail=(
                    "review.backend='llm' but review.llm_command is not configured; "
                    "refusing to fall back to the rule backend and claim a model ran"
                ),
                evidence_gap=True,
            )
            call = ReviewerCall(
                persona=persona.key,
                model=model,
                prompt_chars=len(prompt),
                input_tokens=0,
                output_tokens=0,
                duration_ms=int((time.perf_counter() - started) * 1000),
                ok=False,
                error=f"{ToolFailureKind.CONFIG.value}: {err.detail}",
                command=None,
                context_fingerprint=fingerprint,
                isolation_ok=iso_ok,
                isolation_reason=iso_reason,
                backend="llm",
                skipped=False,
                error_kind=ToolFailureKind.CONFIG.value,
                estimated=False,
            )
            self._calls.append(call)
            return ReviewerOutput(
                persona=persona.key,
                model=model,
                findings=[],
                raw_text="",
                call=call,
                tool_error=err,
            )

        from ..util import run_cmd

        command_line = template.replace("{model}", model)
        argv = _split_command(command_line)
        if not argv:
            err = ToolError(
                provider=f"reviewer:{persona.key}",
                kind=ToolFailureKind.CONFIG,
                detail=f"review.llm_command is empty after expansion: {template!r}",
                evidence_gap=True,
            )
            call = ReviewerCall(
                persona=persona.key,
                model=model,
                prompt_chars=len(prompt),
                input_tokens=_estimate_tokens(prompt),
                output_tokens=0,
                duration_ms=int((time.perf_counter() - started) * 1000),
                ok=False,
                error=f"{ToolFailureKind.CONFIG.value}: {err.detail}",
                command=command_line,
                context_fingerprint=fingerprint,
                isolation_ok=iso_ok,
                isolation_reason=iso_reason,
                backend="llm",
                error_kind=ToolFailureKind.CONFIG.value,
                estimated=True,
            )
            self._calls.append(call)
            return ReviewerOutput(
                persona=persona.key, model=model, findings=[], raw_text="", call=call, tool_error=err
            )

        timeout_s = _timeout_for(self.config)
        result = run_cmd(
            argv,
            cwd=getattr(ctx, "repo_root", None),
            timeout_s=timeout_s,
            input_text=prompt,
        )
        input_tokens = _estimate_tokens(prompt)
        output_tokens = _estimate_tokens(result.stdout)

        if result.timed_out:
            err = ToolError(
                provider=f"reviewer:{persona.key}",
                kind=ToolFailureKind.TIMEOUT,
                detail=f"reviewer command exceeded {timeout_s:.0f}s",
                command=result.command_line,
                duration_ms=result.duration_ms,
                evidence_gap=True,
            )
            return self._failed_llm(
                persona, model, prompt, result, fingerprint, iso_ok, iso_reason,
                started, err, input_tokens, output_tokens,
            )
        if result.launch_error:
            err = ToolError(
                provider=f"reviewer:{persona.key}",
                kind=ToolFailureKind.MISSING,
                detail=f"could not launch reviewer command: {result.launch_error}",
                command=result.command_line,
                duration_ms=result.duration_ms,
                evidence_gap=True,
            )
            return self._failed_llm(
                persona, model, prompt, result, fingerprint, iso_ok, iso_reason,
                started, err, input_tokens, output_tokens,
            )
        if result.exit_code != 0:
            err = ToolError(
                provider=f"reviewer:{persona.key}",
                kind=ToolFailureKind.NONZERO_EXIT,
                detail=f"reviewer command exited {result.exit_code}",
                command=result.command_line,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                stderr_excerpt=(result.stderr or "")[:400] or None,
                evidence_gap=True,
            )
            return self._failed_llm(
                persona, model, prompt, result, fingerprint, iso_ok, iso_reason,
                started, err, input_tokens, output_tokens,
            )

        try:
            obj = _parse_json_payload(result.stdout)
            findings = self._findings_from_llm(persona, obj, ctx, model)
        except (ValueError, KeyError, TypeError) as exc:
            err = ToolError(
                provider=f"reviewer:{persona.key}",
                kind=ToolFailureKind.MALFORMED_OUTPUT,
                detail=f"reviewer output was not the agreed JSON: {type(exc).__name__}: {exc}",
                command=result.command_line,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                stderr_excerpt=(result.stdout or "")[:400] or None,
                evidence_gap=True,
            )
            return self._failed_llm(
                persona, model, prompt, result, fingerprint, iso_ok, iso_reason,
                started, err, input_tokens, output_tokens,
            )

        call = ReviewerCall(
            persona=persona.key,
            model=model,
            prompt_chars=len(prompt),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=int((time.perf_counter() - started) * 1000),
            ok=True,
            error=None,
            command=result.command_line,
            context_fingerprint=fingerprint,
            isolation_ok=iso_ok,
            isolation_reason=iso_reason,
            backend="llm",
            estimated=True,
        )
        self._calls.append(call)
        return ReviewerOutput(
            persona=persona.key,
            model=model,
            findings=findings,
            raw_text=result.stdout,
            call=call,
        )

    def _failed_llm(
        self,
        persona: Persona,
        model: str,
        prompt: str,
        result: Any,
        fingerprint: str,
        iso_ok: bool,
        iso_reason: str,
        started: float,
        err: ToolError,
        input_tokens: int,
        output_tokens: int,
    ) -> ReviewerOutput:
        call = ReviewerCall(
            persona=persona.key,
            model=model,
            prompt_chars=len(prompt),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=int((time.perf_counter() - started) * 1000),
            ok=False,
            error=f"{err.kind.value}: {err.detail}",
            command=getattr(result, "command_line", None),
            context_fingerprint=fingerprint,
            isolation_ok=iso_ok,
            isolation_reason=iso_reason,
            backend="llm",
            error_kind=err.kind.value,
            estimated=True,
        )
        self._calls.append(call)
        return ReviewerOutput(
            persona=persona.key,
            model=model,
            findings=[],
            raw_text=getattr(result, "stdout", "") or "",
            call=call,
            tool_error=err,
        )

    def _findings_from_llm(
        self, persona: Persona, obj: Any, ctx: ScanContext, model: str
    ) -> list[RawFinding]:
        if not isinstance(obj, dict):
            raise ValueError(f"expected a JSON object, got {type(obj).__name__}")
        items = obj.get("findings", [])
        if not isinstance(items, list):
            raise ValueError("'findings' must be a list")

        default_file = ""
        changed = getattr(ctx, "changed_files", None) or []
        if changed:
            default_file = changed[0].path

        out: list[RawFinding] = []
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"findings[{i}] is not an object")
            rule_id = str(item.get("rule_id") or "")
            if not _RULE_RE.match(rule_id):
                rule_id = f"CHM-REV-{persona.key.upper().replace('_', '-')}-{i:03d}"
            try:
                category = Category(str(item.get("category", "")).upper())
            except ValueError:
                category = persona.focus[0] if persona.focus else Category.BOILERPLATE
            try:
                severity = Severity(str(item.get("severity", "")).upper())
            except ValueError:
                severity = Severity.MEDIUM
            extra: dict[str, Any] = {
                "backend": "llm",
                "is_llm": True,
                "model": model,
                "evidence": [str(e) for e in (item.get("evidence") or [])],
            }
            # A semantic reviewer cannot prove HIGH/CRITICAL (spec §3.1).
            if severity.rank > Severity.MEDIUM.rank:
                extra["severity_clamped"] = f"{severity.value}->MEDIUM (semantic reviewer cannot prove it)"
                severity = Severity.MEDIUM
            rec = item.get("recommendation")
            if isinstance(rec, dict):
                extra["recommendation"] = {
                    "preferred": str(rec.get("preferred", "")),
                    "fallback": str(rec.get("fallback", "")),
                }
            if item.get("repair_class"):
                extra["repair_class"] = str(item["repair_class"])
            if category is Category.PERFORMANCE:
                extra["perf_confidence"] = PerfConfidence.SUSPECTED.value

            start_line = int(item.get("start_line", 1) or 1)
            end_line = int(item.get("end_line", start_line) or start_line)
            out.append(
                RawFinding(
                    provider=f"reviewer:{persona.key}:llm",
                    rule_id=rule_id,
                    message=str(item.get("title") or item.get("rationale") or rule_id).strip(),
                    file=str(item.get("file") or default_file).replace("\\", "/").lstrip("./"),
                    start_line=max(1, start_line),
                    end_line=max(start_line, end_line),
                    symbol=(str(item["symbol"]) if item.get("symbol") else None),
                    category=category,
                    severity=severity,
                    confidence=float(clamp(float(item.get("confidence", 0.5) or 0.5), 0.0, 1.0)),
                    kind=EvidenceKind.SEMANTIC,
                    detail=str(item.get("rationale") or "").strip() or None,
                    extra=extra,
                )
            )
        return out

    # ----------------------------------------------------------- rule path

    def _rule_review(self, persona: Persona, ctx: ScanContext, pack: Any) -> list[RawFinding]:
        """Deterministic, semantic-flavoured heuristics for one persona.

        These look at *abstraction and intent* (does this extension point have a
        second user? does this abstraction cross a real boundary?) rather than
        at syntactic patterns, which is what the native analyzers already do.
        """
        index = _index_of(ctx)
        views = _file_views(ctx)
        found: list[RawFinding] = []

        for view in views:
            if persona.key == "abstraction":
                found.extend(self._abstraction_findings(persona, ctx, index, view))
            elif persona.key == "simplicity":
                found.extend(self._simplicity_findings(persona, ctx, index, view))
            elif persona.key == "maintainability":
                found.extend(self._maintainability_findings(persona, ctx, view))
            elif persona.key == "performance":
                found.extend(self._performance_findings(persona, ctx, view))
            elif persona.key == "concurrency":
                found.extend(self._concurrency_findings(persona, ctx, view))

        found.sort(key=lambda f: (f.file, f.start_line, f.rule_id, f.symbol or ""))
        persona_tag = persona.key.upper().replace("_", "-")
        for i, raw in enumerate(found, start=1):
            raw.rule_id = f"CHM-REV-{persona_tag}-{i:03d}"
        return found

    # -- per-persona heuristics ------------------------------------------

    def _abstraction_findings(self, persona, ctx, index, view: _FileView) -> list[RawFinding]:
        out: list[RawFinding] = []
        for decl in view.decls:
            if not _is_changed(ctx, view.path, decl["line"]):
                continue
            if decl["kind"] == "interface":
                iface = decl["name"]
                if _BOUNDARY_RE.search(view.text) or _BOUNDARY_RE.search(iface):
                    continue
                impls = _count_implementations(ctx, index, iface)
                if impls <= 1:
                    out.append(
                        self._mk(
                            persona,
                            category=Category.WRONG_ABSTRACTION,
                            title=(
                                f"interface {iface} has {impls} implementation(s) and no "
                                "remote/serialization boundary"
                            ),
                            view=view,
                            decl=decl,
                            severity=Severity.MEDIUM,
                            confidence=0.6,
                            detail=(
                                "Single-implementation interface with no Feign/Mapper/RPC/SPI "
                                "boundary found in the file. Either a concrete dependency is "
                                "enough, or a real boundary exists and must be named. "
                                "Deterministic implementation count was not available from a "
                                "symbol index for every file, so this is a heuristic."
                            ),
                            preferred="直接依赖具体实现；等第二个实现出现时再引入接口",
                            fallback="补充说明该接口的真实边界（远程调用/序列化/测试替换）",
                            extra={"implementation_count": impls},
                        )
                    )
            elif decl["kind"] == "class" and decl["name"].endswith("Impl"):
                base = _implemented_interface(decl["text"])
                if not base:
                    continue
                impls = _count_implementations(ctx, index, base)
                if impls <= 1:
                    out.append(
                        self._mk(
                            persona,
                            category=Category.WRONG_ABSTRACTION,
                            title=f"{decl['name']} implements {base} but no second implementation exists",
                            view=view,
                            decl=decl,
                            severity=Severity.MEDIUM,
                            confidence=0.55,
                            detail=(
                                f"Only {impls} implementation of {base} could be found. An Impl "
                                "suffix usually implies a substitution point; with one "
                                "implementation the indirection may be speculative."
                            ),
                            preferred="删除 Impl/接口这一层，直接使用具体类",
                            fallback="若存在真实替换点（测试替身/多实现），补充证据后保留",
                            extra={"interface": base, "implementation_count": impls},
                        )
                    )
        return out

    def _simplicity_findings(self, persona, ctx, index, view: _FileView) -> list[RawFinding]:
        out: list[RawFinding] = []
        for decl in view.decls:
            if not _is_changed(ctx, view.path, decl["line"]):
                continue
            if decl["kind"] == "method" and decl.get("visibility") == "public":
                if decl["name"] in ("main",):
                    continue
                start, end = _brace_span(view.lines, decl["line"] - 1)
                body_lines = end - start + 1
                if body_lines <= 4:
                    callers = _count_callers(ctx, index, decl["name"])
                    if callers == 1:
                        out.append(
                            self._mk(
                                persona,
                                category=Category.OVER_ENGINEERING,
                                title=(
                                    f"public method {decl['name']} has one caller and a "
                                    f"{body_lines}-line body"
                                ),
                                view=view,
                                decl=decl,
                                severity=Severity.MEDIUM,
                                confidence=0.5,
                                detail=(
                                    "A public method with a single caller and a tiny body is "
                                    "usually an inline candidate. Caller count came from the "
                                    "symbol index when available, otherwise from a text scan, "
                                    "so dynamic dispatch may be undercounted."
                                ),
                                preferred=f"把 {decl['name']} 内联到唯一调用点",
                                fallback="若它是对外 API 或测试接缝，补充说明并保留",
                                extra={"caller_count": callers, "body_lines": body_lines},
                            )
                        )
            elif decl["kind"] == "class":
                name = decl["name"]
                if re.search(r"(Factory|Strategy|Provider|Registry)$", name):
                    start, end = _brace_span(view.lines, decl["line"] - 1)
                    body = "\n".join(view.lines[start : end + 1])
                    registrations = len(_REGISTER_RE.findall(body))
                    if registrations <= 1:
                        out.append(
                            self._mk(
                                persona,
                                category=Category.OVER_ENGINEERING,
                                title=f"{name} is an extension point with {registrations} registration(s)",
                                view=view,
                                decl=decl,
                                severity=Severity.MEDIUM,
                                confidence=0.5,
                                detail=(
                                    "Factory/Strategy/Provider/Registry with at most one "
                                    "registration is a speculative extension point: the "
                                    "indirection has no second participant to select between."
                                ),
                                preferred="删除注册表/工厂层，直接构造唯一实现",
                                fallback="等第二个实现真正出现时再引入选择逻辑",
                                extra={"registrations": registrations},
                            )
                        )

        out.extend(self._defensive_after_null(persona, ctx, view))
        return out

    def _defensive_after_null(self, persona, ctx, view: _FileView) -> list[RawFinding]:
        out: list[RawFinding] = []
        for decl in view.decls:
            if decl["kind"] != "method":
                continue
            start, end = _brace_span(view.lines, decl["line"] - 1)
            guards: list[tuple[int, str]] = []
            for idx in range(start, end + 1):
                m = _NULL_GUARD_RE.search(view.lines[idx])
                if m:
                    guards.append((idx, m.group(1)))
            seen: set[str] = set()
            for idx, var in guards:
                if var in seen and _is_changed(ctx, view.path, idx + 1):
                    out.append(
                        self._mk(
                            persona,
                            category=Category.DEFENSIVE_JUNK,
                            title=f"redundant null guard on '{var}' after it was already null-checked",
                            view=view,
                            decl={"kind": "line", "name": var, "line": idx + 1},
                            severity=Severity.LOW,
                            confidence=0.45,
                            detail=(
                                f"'{var}' is null-checked more than once in the same method "
                                "with no reassignment in between that this heuristic can see; "
                                "the later guard may be unreachable."
                            ),
                            preferred=f"删除对 '{var}' 的重复判空分支",
                            fallback="若中间存在重新赋值/跨线程修改，补充说明并保留",
                            extra={"variable": var},
                        )
                    )
                seen.add(var)
        return out

    def _maintainability_findings(self, persona, ctx, view: _FileView) -> list[RawFinding]:
        out: list[RawFinding] = []
        for decl in view.decls:
            if not _is_changed(ctx, view.path, decl["line"]):
                continue
            if decl["kind"] == "method" and decl.get("visibility") == "public":
                params = [p.strip() for p in (decl.get("params") or "").split(",") if p.strip()]
                if len(params) > 5 and not _has_param_object(params):
                    out.append(
                        self._mk(
                            persona,
                            category=Category.COMPLEXITY,
                            title=f"{decl['name']} takes {len(params)} primitive parameters",
                            view=view,
                            decl=decl,
                            severity=Severity.LOW,
                            confidence=0.5,
                            detail=(
                                "More than five primitive/standard parameters with no parameter "
                                "object makes call sites hard to read and easy to transpose."
                            ),
                            preferred="引入参数对象承载这组强相关参数",
                            fallback="保持签名并补充单元测试覆盖各参数组合",
                            extra={"parameter_count": len(params)},
                        )
                    )
            elif decl["kind"] == "class":
                start, end = _brace_span(view.lines, decl["line"] - 1)
                body = "\n".join(view.lines[start : end + 1])
                if "@Deprecated" in body and re.search(r"[Ll]egacy", decl["name"]):
                    out.append(
                        self._mk(
                            persona,
                            category=Category.COMPATIBILITY_JUNK,
                            title=f"{decl['name']} is both @Deprecated and legacy-named",
                            view=view,
                            decl=decl,
                            severity=Severity.LOW,
                            confidence=0.5,
                            detail=(
                                "A newly added @Deprecated legacy-named type suggests a "
                                "compatibility layer without a stated version baseline."
                            ),
                            preferred="确认版本基线后删除该兼容层",
                            fallback="补充版本基线与移除计划",
                            extra={"deprecated": True},
                        )
                    )
        return out

    def _performance_findings(self, persona, ctx, view: _FileView) -> list[RawFinding]:
        """Rule review can only ever say SUSPECTED -- there is no benchmark here."""
        out: list[RawFinding] = []
        for i, line in enumerate(view.lines):
            if not _LOOP_RE.search(line):
                continue
            if not _is_changed(ctx, view.path, i + 1):
                continue
            start, end = _brace_span(view.lines, i)
            body = "\n".join(view.lines[start : end + 1])
            m = _IO_CALL_RE.search(body)
            if not m:
                continue
            out.append(
                self._mk(
                    persona,
                    category=Category.PERFORMANCE,
                    title=f"I/O or query call inside a loop at line {i + 1}",
                    view=view,
                    decl={"kind": "loop", "name": None, "line": i + 1},
                    severity=Severity.LOW,
                    confidence=0.4,
                    detail=(
                        f"`{m.group(0).strip()}` appears inside a loop. Without a benchmark, a "
                        "profiler trace or a real query count this is a suspicion, not a "
                        "measured incident -- collection sizes are unknown."
                    ),
                    preferred="先补充 benchmark / 查询计数证据，再考虑批量查询",
                    fallback="记录当前基线并观察",
                    extra={"perf_confidence": PerfConfidence.SUSPECTED.value, "suspect_call": m.group(0).strip()},
                )
            )
        return out

    def _concurrency_findings(self, persona, ctx, view: _FileView) -> list[RawFinding]:
        out: list[RawFinding] = []
        for decl in view.decls:
            if decl["kind"] != "method":
                continue
            start, end = _brace_span(view.lines, decl["line"] - 1)
            pre = "\n".join(view.lines[max(0, decl["line"] - 4) : decl["line"] - 1])
            if not _TRANSACTIONAL_RE.search(pre):
                continue
            if not _is_changed(ctx, view.path, decl["line"]):
                continue
            body = "\n".join(view.lines[start : end + 1])
            m = _REMOTE_CALL_RE.search(body)
            if not m:
                continue
            out.append(
                self._mk(
                    persona,
                    category=Category.CONCURRENCY,
                    title=f"remote call inside @Transactional method {decl['name']}",
                    view=view,
                    decl=decl,
                    severity=Severity.MEDIUM,
                    confidence=0.6,
                    detail=(
                        f"`{m.group(0).strip()}` runs while the transaction is open. The "
                        "database lock is held for the duration of a network round trip, and "
                        "a partial commit becomes possible. The native analyzers grade the "
                        "mechanical pattern; this finding adds the transaction-boundary "
                        "semantics."
                    ),
                    preferred="把远程调用移出事务边界（先取数、再开事务写入）",
                    fallback="若必须同事务，缩短超时并补充补偿逻辑",
                    extra={"remote_call": m.group(0).strip()},
                )
            )
        return out

    # -- shared ----------------------------------------------------------

    def _mk(
        self,
        persona: Persona,
        *,
        category: Category,
        title: str,
        view: _FileView,
        decl: dict,
        severity: Severity,
        confidence: float,
        detail: str,
        preferred: str,
        fallback: str,
        extra: Optional[dict] = None,
    ) -> RawFinding:
        payload: dict[str, Any] = {
            "backend": "rule",
            "is_llm": False,
            "recommendation": {"preferred": preferred, "fallback": fallback},
        }
        if extra:
            payload.update(extra)
        line = int(decl.get("line") or 1)
        symbol = decl.get("name") if decl.get("kind") in ("class", "interface", "method", "enum", "record") else None
        return RawFinding(
            provider=f"reviewer:{persona.key}:rule",
            rule_id="",
            message=title,
            file=view.path,
            start_line=line,
            end_line=line,
            symbol=symbol,
            category=category,
            severity=severity,
            confidence=float(clamp(confidence, 0.4, 0.7)),
            kind=EvidenceKind.SEMANTIC,
            detail=detail,
            extra=payload,
        )


# --------------------------------------------------------------------------
# module-level helpers
# --------------------------------------------------------------------------


def _split_command(command_line: str) -> list[str]:
    """Split a command template into argv without invoking a shell.

    Quoted segments become single argv entries with the quotes removed, so a
    template like ``llm-run --model {model} "C:/Program Files/x.exe"`` works.
    """
    out: list[str] = []
    for part in re.findall(r'"[^"]*"|\'[^\']*\'|\S+', command_line):
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
            part = part[1:-1]
        if part:
            out.append(part)
    return out


def _parse_json_payload(text: str) -> Any:
    """Parse the reviewer's JSON, tolerating fences and surrounding noise."""
    if not text or not text.strip():
        raise ValueError("empty output")
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in output")
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc


def _index_of(ctx: ScanContext) -> Any:
    options = getattr(ctx, "options", None) or {}
    return options.get("index")


def _is_source_path(path: str) -> bool:
    lower = path.lower()
    return lower.endswith(_SOURCE_SUFFIXES)


def _file_views(ctx: ScanContext) -> list[_FileView]:
    """Changed source files, deterministic order, already comment-stripped."""
    views: list[_FileView] = []
    for cf in getattr(ctx, "changed_files", None) or []:
        if cf.is_binary or cf.is_generated:
            continue
        if cf.language not in _SOURCE_LANGUAGES and not _is_source_path(cf.path):
            continue
        text = _read(ctx, cf.path)
        if not text:
            continue
        clean = strip_comments_and_strings(text)[:_MAX_FILE_CHARS]
        lines = _split_lines(clean)
        views.append(_FileView(path=cf.path, text=text, lines=lines, decls=_scan_declarations(lines)))
    views.sort(key=lambda v: v.path)
    return views


def _read(ctx: ScanContext, path: str) -> str:
    try:
        return ctx.read(path)
    except (OSError, ValueError):
        return ""


def _is_changed(ctx: ScanContext, path: str, line: int) -> bool:
    try:
        return ctx.is_changed_line(path, line)
    except (AttributeError, ValueError):
        return True


def _candidate_paths(ctx: ScanContext) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cf in getattr(ctx, "changed_files", None) or []:
        if cf.is_binary or cf.is_generated:
            continue
        if cf.path not in seen:
            seen.add(cf.path)
            out.append(cf.path)
    for path in getattr(ctx, "repo_files", None) or []:
        if len(out) >= _MAX_SCAN_FILES:
            break
        if path in seen or not _is_source_path(path):
            continue
        seen.add(path)
        out.append(path)
    return out


def _count_implementations(ctx: ScanContext, index: Any, iface: str) -> int:
    """How many types implement ``iface``?  Symbol index first, text scan second."""
    if index is not None:
        try:
            refs = index.references(iface)
        except Exception:  # noqa: BLE001 - index failure degrades to the text scan
            refs = []
        counted = sum(
            1
            for r in refs
            if str(r.get("kind", "")).lower() in ("implements", "extends")
        )
        if counted:
            return counted
    pattern = re.compile(r"\bimplements\s+[^{;]*\b" + re.escape(iface) + r"\b")
    count = 0
    for path in _candidate_paths(ctx):
        text = _read(ctx, path)
        if text and pattern.search(text):
            count += 1
    return count


def _count_callers(ctx: ScanContext, index: Any, name: str) -> int:
    if index is not None:
        try:
            counted = int(index.reference_count(name, exclude_definition=True))
        except Exception:  # noqa: BLE001 - index failure degrades to the text scan
            counted = -1
        if counted >= 0:
            return counted
    pattern = re.compile(r"\b" + re.escape(name) + r"\s*\(")
    decl = re.compile(r"\b" + re.escape(name) + r"\s*\([^)]*\)\s*(?:\{|throws|;)")
    count = 0
    for path in _candidate_paths(ctx):
        text = _read(ctx, path)
        if not text:
            continue
        count += len(pattern.findall(text))
        count -= len(decl.findall(text))
    return max(0, count)


def _implemented_interface(class_line: str) -> Optional[str]:
    m = _IMPL_RE.search(class_line)
    if not m:
        return None
    first = m.group(1).split(",")[0].strip()
    first = re.sub(r"<.*", "", first).strip()
    return first.split(".")[-1] if first else None


def _has_param_object(params: list[str]) -> bool:
    for param in params:
        parts = param.split()
        if len(parts) < 2:
            continue
        type_name = parts[-2].split("<")[0].strip()
        if type_name and type_name[0].isupper() and type_name not in _WRAPPER_TYPES:
            return True
    return False


_RULE_RE = re.compile(r"^CHM-[A-Z0-9]+(-[A-Z0-9]+)+$")
