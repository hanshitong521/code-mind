"""Prompt construction for the semantic reviewers and the evidence validator.

Two invariants live here (spec §3.5 / §15):

1. **Context isolation.**  ``context_payload`` never emits the writer's own
   rationale unless the caller *explicitly* opts in.  ``assert_isolation`` is a
   real, testable check -- it looks for verbatim sentences of the rationale
   inside the payload and reports the leak instead of trusting the caller.
2. **Strict output contract.**  The reviewer is asked for exactly one JSON
   object; anything else is a parse failure, not a silent empty result.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Sequence

from ..util import sha256_text

#: Optional project/team rule pack, appended to every reviewer prompt.
#: Editing `prompts/team-rules.md` is the supported way to teach the reviewer
#: something organisation-specific -- without forking the code.
TEAM_RULES_PATH = Path(__file__).resolve().parents[2] / "prompts" / "team-rules.md"

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def load_team_rules(path: Optional[Path | str] = None) -> str:
    """Return the team rule pack, or ``''`` when absent/empty.

    The HTML comment header of the template is stripped so authors can keep
    instructions to themselves in the file.
    """
    target = Path(path) if path else TEAM_RULES_PATH
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return ""
    return _HTML_COMMENT.sub("", text).strip()


# --------------------------------------------------------------------------
# system rules (spec §15) -- the eight rules every reviewer call carries
# --------------------------------------------------------------------------

#: Spec §15 verbatim (Chinese original preserved so the contract can be audited
#: against the specification without translation drift).
SPEC_SECTION_15_RULES: list[str] = [
    "不因为代码能运行就判定健康。 (Do not call code healthy just because it runs.)",
    "不因为出现重复就自动要求抽象。 (Do not demand an abstraction just because "
    "duplication exists.)",
    "不因为未来可能扩展就接受抽象。 (Do not accept an abstraction because it "
    "might be useful later.)",
    "每个 HIGH 结论必须引用证据。 (Every HIGH conclusion must cite evidence.)",
    "无证据时降级 confidence。 (Lower confidence when there is no evidence.)",
    "优先提出删除/简化方案。 (Prefer deletion/simplification over addition.)",
    "不直接修改代码。 (Do not modify code directly.)",
    "输出结构化 Finding。 (Emit structured findings only.)",
]

#: Additional invariants that make the eight rules above mechanically
#: enforceable (AI != evidence, context isolation, no majority vote).
REVIEWER_SYSTEM_RULES: list[str] = [
    "You are a SEMANTIC reviewer, not an evidence source. You may explain code, "
    "judge business intent, identify wrong abstractions, reason about complexity, "
    "cluster findings, grade risk and propose repairs. You may NOT prove anything.",
    "AI is not evidence. A claim that code is dead, unused, uncalled, slow or "
    "unreachable is only a hypothesis. Deterministic artefacts (symbol "
    "references, compiler output, coverage, profiler, benchmark, query count) "
    "are the only proof, and you do not produce them.",
    "Context isolation. You do not see, and must not ask for, the author's own "
    "explanation of their change. Judge the code in front of you; never argue "
    "from stated intent ('this is for extensibility', 'we plan to use it later').",
    "Never claim a HIGH or CRITICAL severity without deterministic evidence. "
    "When you have no evidence, lower `confidence` to at most 0.5 and record the "
    "missing artefact in `rationale`.",
    "Performance findings need a benchmark, a profiler trace or a real query "
    "count. Without one, classify the finding as SUSPECTED and never grade it "
    "above LOW.",
    "Deleting code is a last resort. Before recommending any deletion, consider "
    "reflection, dependency injection, XML/annotation registration, RPC, MQ, SPI "
    "and dynamic import entry points; if any might exist, say so explicitly.",
    "Duplication alone is not a defect. Do not demand an abstraction merely "
    "because two blocks look alike -- name the single business concept they "
    "share, or ask a human to confirm the semantics.",
    "When two reviewers disagree about a HIGH or CRITICAL finding, the Evidence "
    "Validator decides. Never resolve a disagreement by majority vote, and never "
    "repeat another reviewer's conclusion as if it were your own evidence.",
]

#: The exact JSON shape the reviewer must return.
OUTPUT_CONTRACT: str = (
    '{"findings":[{"rule_id":"CHM-REV-<PERSONA>-<NNN>",'
    '"category":"WRONG_ABSTRACTION",'
    '"title":"one sentence, concrete",'
    '"file":"a/b.java","start_line":10,"end_line":20,"symbol":"foo",'
    '"severity":"MEDIUM","confidence":0.7,'
    '"rationale":"why, and which evidence is missing",'
    '"evidence":["symbol index: 0 references","no benchmark"],'
    '"recommendation":{"preferred":"...","fallback":"..."},'
    '"repair_class":"MANUAL_DECISION"}]}'
)

_RATIONALE_SENTENCE_MIN = 20
_SENTENCE_SPLIT = re.compile(r"[.!?\u3002\uff01\uff1f;\n\r]+")
_WS = re.compile(r"\s+")


# --------------------------------------------------------------------------
# context payload
# --------------------------------------------------------------------------


def _file_block(entry: Any) -> str:
    path = getattr(entry, "path", None) or (entry.get("path") if isinstance(entry, dict) else "")
    reason = getattr(entry, "reason", None) or (entry.get("reason") if isinstance(entry, dict) else "")
    truncated = getattr(entry, "truncated", None)
    if truncated is None and isinstance(entry, dict):
        truncated = entry.get("truncated", False)
    size = getattr(entry, "bytes", None)
    if size is None and isinstance(entry, dict):
        size = entry.get("bytes", 0)
    content = getattr(entry, "content", None)
    if content is None and isinstance(entry, dict):
        content = entry.get("content", "")
    header = f"--- file: {path} (reason: {reason}, bytes: {size}, truncated: {bool(truncated)})"
    return f"{header}\n{content}"


def context_payload(
    pack: Any,
    *,
    include_writer_rationale: bool,
    writer_rationale: Optional[str],
) -> str:
    """Render the review context as deterministic text.

    The writer's rationale is appended **only** when the caller opted in.
    Everything else comes from the context pack (files, requirement excerpt,
    test evidence) which is itself already secret-filtered.
    """
    lines: list[str] = []
    risk = getattr(pack, "risk", None) if pack is not None else None
    lines.append("[CONTEXT]")
    lines.append(f"risk: {risk if risk else 'UNKNOWN'}")

    if pack is None:
        lines.append("pack: UNAVAILABLE (context layer degraded)")
    else:
        degraded = bool(getattr(pack, "degraded", False))
        if degraded:
            lines.append("pack: DEGRADED (context layer fell back to a minimal pack)")
        expansion = getattr(pack, "expansion_reason", "") or ""
        if expansion:
            lines.append(f"expansion_reason: {expansion}")
        req = getattr(pack, "requirement_context", "") or ""
        lines.append("[REQUIREMENT]")
        lines.append(req if req else "(none provided)")
        tests = getattr(pack, "test_evidence", "") or ""
        lines.append("[TEST EVIDENCE]")
        lines.append(tests if tests else "(none provided)")
        files = list(getattr(pack, "files", None) or [])
        lines.append(f"[CHANGED CONTEXT FILES] count={len(files)}")
        for entry in files:
            lines.append(_file_block(entry))

    if include_writer_rationale:
        lines.append("[AUTHOR RATIONALE -- explicitly supplied by the caller]")
        lines.append(writer_rationale or "(empty)")
    else:
        lines.append(
            "[AUTHOR RATIONALE] withheld by context isolation -- do not speculate about intent"
        )

    return "\n".join(lines) + "\n"


def payload_fingerprint(payload: str) -> str:
    """Stable sha256 of a payload, used to prove two payloads differ."""
    return sha256_text(payload)


def assert_isolation(payload: str, writer_rationale: Optional[str]) -> tuple[bool, str]:
    """Verify no substantive fragment of ``writer_rationale`` leaked into ``payload``.

    Returns ``(ok, reason)``.  A "substantive fragment" is any sentence of the
    rationale with at least ``_RATIONALE_SENTENCE_MIN`` characters, compared as
    a substring both verbatim and with whitespace normalised.
    """
    if not writer_rationale or not writer_rationale.strip():
        return True, "no writer rationale supplied"

    fragments = [
        s.strip()
        for s in _SENTENCE_SPLIT.split(writer_rationale)
        if len(s.strip()) >= _RATIONALE_SENTENCE_MIN
    ]
    if not fragments:
        stripped = writer_rationale.strip()
        if len(stripped) < _RATIONALE_SENTENCE_MIN:
            return True, "writer rationale too short to be a substantive fragment"
        fragments = [stripped]

    payload_norm = _WS.sub(" ", payload)
    leaks: list[str] = []
    for frag in fragments:
        if frag in payload:
            leaks.append(frag)
            continue
        frag_norm = _WS.sub(" ", frag)
        if frag_norm and frag_norm in payload_norm:
            leaks.append(frag)

    if leaks:
        preview = leaks[0][:80]
        return False, f"writer rationale leaked into payload: {len(leaks)} fragment(s), e.g. {preview!r}"
    return True, f"checked {len(fragments)} rationale fragment(s); none present in payload"


# --------------------------------------------------------------------------
# reviewer prompt
# --------------------------------------------------------------------------


def _persona_header(persona: Any) -> tuple[str, str, list[str], list[str]]:
    if persona is None:
        return (
            "reviewer",
            "Review the change set for semantic code-health problems.",
            [],
            [],
        )
    key = getattr(persona, "key", "reviewer")
    title = getattr(persona, "title", key)
    goal = getattr(persona, "goal", "")
    rules = [str(r) for r in (getattr(persona, "rules", ()) or ())]
    focus = [getattr(c, "value", str(c)) for c in (getattr(persona, "focus", ()) or ())]
    return key, f"{title}\n{goal}".strip(), rules, focus


def build_reviewer_prompt(
    persona: Any,
    pack: Any,
    ctx: Any,
    *,
    model: Optional[str] = None,
    include_writer_rationale: bool = False,
    writer_rationale: Optional[str] = None,
) -> str:
    """Build the full reviewer prompt: Role / Goal / Rules / Context / Output."""
    key, goal, persona_rules, focus = _persona_header(persona)
    persona_upper = key.upper().replace("_", "-")

    lines: list[str] = []
    lines.append("=== ROLE ===")
    lines.append(
        f"You are the {key} reviewer inside CodeHealthMind, a mandatory code-health "
        "gate that runs after an AI agent writes code."
    )
    if model:
        lines.append(f"model: {model}")
    lines.append(f"repository: {getattr(ctx, 'repo_root', 'unknown')}")
    mode = getattr(ctx, "mode", None)
    lines.append(f"review mode: {getattr(mode, 'value', mode)}")

    lines.append("")
    lines.append("=== GOAL ===")
    lines.append(goal or "Review the change set for semantic code-health problems.")
    if focus:
        lines.append("focus categories: " + ", ".join(focus))

    lines.append("")
    lines.append("=== RULES (spec section 15, non-negotiable) ===")
    for i, rule in enumerate(SPEC_SECTION_15_RULES, start=1):
        lines.append(f"{i}. {rule}")
    lines.append("")
    lines.append("=== ENFORCEMENT INVARIANTS ===")
    for i, rule in enumerate(REVIEWER_SYSTEM_RULES, start=1):
        lines.append(f"{i}. {rule}")
    if persona_rules:
        lines.append("")
        lines.append(f"=== {key.upper()} REVIEWER RULES ===")
        for i, rule in enumerate(persona_rules, start=1):
            lines.append(f"{i}. {rule}")

    team_rules = load_team_rules()
    if team_rules:
        lines.append("")
        lines.append("=== TEAM RULES ===")
        lines.append(team_rules)

    lines.append("")
    lines.append("=== CONTEXT ===")
    lines.append(
        context_payload(
            pack,
            include_writer_rationale=include_writer_rationale,
            writer_rationale=writer_rationale,
        )
    )

    lines.append("=== OUTPUT ===")
    lines.append(
        "Return exactly one JSON object and nothing else -- no markdown fence, no "
        "commentary. Shape:"
    )
    lines.append(OUTPUT_CONTRACT)
    lines.append("")
    lines.append(
        f"`rule_id` must be CHM-REV-{persona_upper}-NNN with NNN starting at 001. "
        "`category` must be one of the CHM categories. `severity` must be one of "
        "LOW/MEDIUM/HIGH/CRITICAL. `confidence` is a float in 0..1. `repair_class` "
        "must be one of SAFE_AUTO_FIX/WRITER_FIX/MANUAL_DECISION/NONE. "
        "Use an empty findings array when you found nothing."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# validator prompt
# --------------------------------------------------------------------------


def _finding_digest(finding: Any, index: int) -> str:
    loc = getattr(finding, "location", None)
    file = getattr(loc, "file", "?") if loc is not None else "?"
    line = getattr(loc, "start_line", 0) if loc is not None else 0
    symbol = getattr(loc, "symbol", None) if loc is not None else None
    severity = getattr(finding, "severity", None)
    sev = getattr(severity, "value", severity)
    category = getattr(finding, "category", None)
    cat = getattr(category, "value", category)
    evidence = list(getattr(finding, "evidence", None) or [])
    kinds = sorted({getattr(getattr(e, "kind", None), "value", "?") for e in evidence})
    providers = sorted({str(getattr(e, "provider", "?")) for e in evidence})
    return (
        f"{index}. id={getattr(finding, 'id', '?')} rule={getattr(finding, 'rule_id', '?')} "
        f"category={cat} severity={sev} at {file}:{line} symbol={symbol} "
        f"evidence={len(evidence)} kinds={kinds} providers={providers} "
        f"introduced_by_current_diff={getattr(finding, 'introduced_by_current_diff', None)}"
    )


def build_validator_prompt(findings: Sequence[Any], ctx: Any, *, index: Any = None) -> str:
    """Prompt for the Evidence Validator.

    The validator adjudicates findings -- it does not re-review the code base.
    """
    lines: list[str] = []
    lines.append("=== ROLE ===")
    lines.append(
        "You are the Evidence Validator inside CodeHealthMind. You adjudicate "
        "findings produced by reviewers and deterministic tools. You do not "
        "re-review the repository."
    )
    lines.append(f"repository: {getattr(ctx, 'repo_root', 'unknown')}")

    lines.append("")
    lines.append("=== YOU MAY ONLY DECIDE THESE SEVEN THINGS ===")
    for i, item in enumerate(
        (
            "whether the finding is actually established;",
            "whether the evidence attached to it is sufficient;",
            "whether its severity is inflated;",
            "whether counter-evidence exists;",
            "whether it is a pre-existing problem rather than introduced by this change;",
            "whether deleting the code would be safe;",
            "whether a dynamic entry point (reflection / IoC / RPC / MQ / XML / SPI / dynamic import) exists.",
        ),
        start=1,
    ):
        lines.append(f"{i}. {item}")

    lines.append("")
    lines.append("=== RULES ===")
    lines.append(
        "A HIGH or CRITICAL finding with no deterministic evidence must be "
        "downgraded -- semantic impressions can never carry that severity."
    )
    lines.append(
        "Conflicting reviewer conclusions about the same location are resolved "
        "here, by evidence. Majority vote is forbidden and is never evidence."
    )
    lines.append(
        "If every evidence provider failed, the verdict is UNCERTAIN -- never a "
        "silent pass."
    )

    lines.append("")
    lines.append("=== FINDINGS TO ADJUDICATE ===")
    if not findings:
        lines.append("(none)")
    else:
        for i, f in enumerate(findings, start=1):
            lines.append(_finding_digest(f, i))

    if index is not None:
        stats = None
        try:
            stats = index.stats()
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            lines.append(f"symbol index stats unavailable: {type(exc).__name__}: {exc}")
        if stats:
            lines.append(f"symbol index: {stats}")
    else:
        lines.append("symbol index: UNAVAILABLE -- dynamic entry checks are text-based only")

    lines.append("")
    lines.append("=== OUTPUT ===")
    lines.append(
        'Return one JSON object: {"verdicts":[{"finding_id":"CHM-000001",'
        '"verdict":"CONFIRMED|DOWNGRADED|REJECTED|UNCERTAIN","reason":"...",'
        '"new_severity":"LOW|MEDIUM|HIGH|CRITICAL"}]}. '
        "Every input finding must appear exactly once. No commentary outside the JSON."
    )
    return "\n".join(lines)
