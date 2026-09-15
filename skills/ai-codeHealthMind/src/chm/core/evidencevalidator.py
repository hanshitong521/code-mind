"""Evidence Validator (spec §17) -- the adjudicator, not a second reviewer.

The validator does exactly seven things:

1. is the finding actually established?
2. is the attached evidence sufficient?
3. is the severity inflated?
4. does counter-evidence exist?
5. is this a pre-existing problem rather than something this change introduced?
6. would deleting the code be safe?
7. does a dynamic entry point exist (reflection / IoC / RPC / MQ / XML / SPI /
   dynamic import)?

It never re-reviews the repository, and it never votes.  When two reviewers
disagree about a HIGH finding, ``validate()`` routes *both* through this
validator and records ``conflict_resolved_by="validator"`` -- majority voting is
forbidden because two impressions are still not evidence.

Outcomes are applied **in place** to the passed ``Finding`` objects, using the
legal lifecycle transitions of :mod:`chm.schema`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..config import Config
from ..contracts import ScanContext
from ..schema import (
    Category,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingStatus,
    PerfConfidence,
    RepairClass,
    Severity,
)

#: Wall clock ceiling for the validator's own dynamic-entry checks.
_MAX_SCAN_FILES = 300
_MAX_FILE_CHARS = 400_000


class Verdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    DOWNGRADED = "DOWNGRADED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class ValidationOutcome:
    finding_id: str
    verdict: Verdict
    reason: str
    original_severity: Severity
    new_severity: Severity
    evidence_added: list[EvidenceItem] = field(default_factory=list)
    dynamic_entry_kinds: list[str] = field(default_factory=list)
    conflict_resolved_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "original_severity": self.original_severity.value,
            "new_severity": self.new_severity.value,
            "evidence_added": [e.to_dict() for e in self.evidence_added],
            "dynamic_entry_kinds": list(self.dynamic_entry_kinds),
            "conflict_resolved_by": self.conflict_resolved_by,
        }


# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

_UNREFERENCED_RULE_TOKENS = ("UNUSED", "DEAD", "UNREACHABLE", "UNCALLED", "UNREFERENCED")
_UNREFERENCED_TITLE_RE = re.compile(
    r"(no\s+references?|never\s+called|not\s+called|unused|unreferenced|dead\s+code|"
    r"\u65e0\u5f15\u7528|\u672a\u4f7f\u7528|\u6b7b\u4ee3\u7801)",
    re.IGNORECASE,
)
_HISTORICAL_TITLE_RE = re.compile(
    r"(historical|pre-?existing|legacy\s+issue|baseline\s+issue|\u5386\u53f2\u95ee\u9898|\u65e7\u95ee\u9898)",
    re.IGNORECASE,
)
_QUADRATIC_RE = re.compile(
    r"(o\s*\(\s*n\s*[\^2\u00b2]\s*\)|n\s*[\^2\u00b2]|quadratic|nested\s+loop|\u5d4c\u5957\u5faa\u73af)",
    re.IGNORECASE,
)

#: Reference kinds that prove a symbol is reachable even without a visible call.
_DYNAMIC_REF_KINDS = ("xml", "reflection", "annotation", "import", "spi", "mq", "rpc", "spring")

#: The complete dynamic-entry surface a deletion decision must clear.
_ENTRY_SURFACE = ("reflection", "spring", "rpc", "mq", "xml", "dynamic_import")

_REFLECTION_RE = re.compile(
    r"(Class\.forName|getDeclaredMethod|getDeclaredField|getDeclaredConstructor|"
    r"getMethod\s*\(|\.newInstance\s*\(|\.invoke\s*\(|MethodHandles|"
    r"getClass\(\)\.getMethod)"
)
_SPRING_ENTRY_RE = re.compile(
    r"(@Component|@Service|@Repository|@Controller|@RestController|@Configuration|"
    r"@Bean|@Autowired|@Resource|@Qualifier|@PostConstruct)"
)
_RPC_ENTRY_RE = re.compile(
    r"(@FeignClient|@Reference|@DubboService|@DubboReference|@RpcService|@Remote|"
    r"@GrpcService|@ThriftService|@Spi)"
)
_MQ_ENTRY_RE = re.compile(
    r"(@RabbitListener|@KafkaListener|@RocketMQMessageListener|@JmsListener|"
    r"@StreamListener|@RabbitHandler)"
)
_XML_ENTRY_RE = re.compile(r"(<bean\b|<ref\b|ref\s*=|class\s*=\s*\"|@Component\b)", re.IGNORECASE)
_DYNAMIC_IMPORT_RE = re.compile(r"(import\s*\(\s*[`'\"]?\$|require\s*\(\s*[A-Za-z_$][\w$]*\s*\)|importlib\.import_module)")

_DOMAIN_STOPWORDS = {
    "get", "set", "is", "has", "if", "for", "while", "return", "null", "true",
    "false", "this", "self", "list", "map", "set", "string", "str", "int",
    "long", "double", "float", "boolean", "bool", "void", "new", "class",
    "public", "private", "protected", "static", "final", "abstract", "interface",
    "enum", "record", "import", "package", "extends", "implements", "throws",
    "throw", "try", "catch", "finally", "else", "switch", "case", "break",
    "continue", "default", "const", "var", "let", "function", "def", "and",
    "or", "not", "in", "of", "with", "from", "as", "the", "a", "an", "to",
    "object", "value", "values", "args", "argv", "item", "items", "result",
    "results", "data", "type", "types", "name", "names", "key", "keys", "size",
    "length", "count", "index", "idx", "i", "j", "k", "n", "x", "y", "z", "tmp",
    "temp", "obj", "object2", "arr", "array", "buffer", "builder", "util",
    "utils", "helper", "impl", "base", "abstract", "override", "super", "printf",
    "println", "system", "out", "err", "log", "logger", "debug", "info", "warn",
    "error", "trace", "java", "lang", "util2", "stringbuilder", "equals",
    "hashcode", "tostring", "serialversionuid",
}

_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")

_SMALL_LITERAL_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"Collections\.singleton(?:List|Map|Set)?\s*\("), 1),
    (re.compile(r"Collections\.empty(?:List|Map|Set)\s*\("), 0),
    (re.compile(r"\bList\.of\s*\(\s*\)"), 0),
    (re.compile(r"\bSet\.of\s*\(\s*\)"), 0),
    (re.compile(r"\bMap\.of\s*\(\s*\)"), 0),
)


# --------------------------------------------------------------------------
# validator
# --------------------------------------------------------------------------


class EvidenceValidator:
    """Adjudicates findings.  Never votes, never re-reviews the repository."""

    def __init__(self, config: Config, ctx: ScanContext, *, index: Any = None) -> None:
        self.config = config
        self.ctx = ctx
        self.index = index

    # ------------------------------------------------------------- public

    def validate(self, findings: list[Finding]) -> list[ValidationOutcome]:
        """Adjudicate every finding, marking conflicts as validator-resolved.

        Conflicting reviewer conclusions about the same location are *both* sent
        through :meth:`validate_one`; the disagreement is recorded on the
        outcome.  Nothing here counts votes.
        """
        groups: dict[tuple, list[Finding]] = {}
        for f in findings:
            groups.setdefault(self._loc_key(f), []).append(f)

        conflicted: set[tuple] = set()
        for key, group in groups.items():
            if len(group) < 2:
                continue
            severities = {f.severity for f in group}
            if len(severities) < 2:
                continue
            if max(severities, key=lambda s: s.rank).rank >= Severity.HIGH.rank:
                conflicted.add(key)

        outcomes: list[ValidationOutcome] = []
        for f in findings:
            outcome = self.validate_one(f)
            key = self._loc_key(f)
            if key in conflicted:
                outcome.conflict_resolved_by = "validator"
                outcome.reason = (
                    outcome.reason
                    + f" | conflicting reviewer conclusions at {f.location.file}:"
                    f"{f.location.start_line} resolved by evidence validation, "
                    "not by majority vote"
                )
            outcomes.append(outcome)
        return outcomes

    def validate_one(self, finding: Finding) -> ValidationOutcome:
        original = finding.severity
        added: list[EvidenceItem] = []
        notes: list[str] = []

        # 0. every provider failed -> we know nothing.  Never a silent pass.
        if self._all_evidence_failed(finding):
            return self._finalize(
                finding,
                Verdict.UNCERTAIN,
                "all evidence providers returned a ToolError; nothing can be established "
                "about this finding, so it is UNCERTAIN rather than accepted",
                original,
                added,
                [],
            )

        name = finding.location.symbol
        claims_unused = self._claims_unreferenced(finding)
        needs_entry_scan = claims_unused or finding.category is Category.DEAD_CODE

        refs: list[dict] = []
        dyn_has = False
        dyn_kinds: list[str] = []
        dyn_checked: list[str] = []
        if name and needs_entry_scan:
            refs = self._references(name, finding)
            dyn_has, dyn_kinds, dyn_checked = self._dynamic_entry_scan(name)

        # 1. dynamic entry points -- the core "never become a delete machine" guard
        if name and needs_entry_scan and dyn_has:
            # "partial" is about scan *coverage*: if some entry surface could not
            # be inspected, deletion safety is unproven and the verdict is UNCERTAIN.
            uncovered = sorted(set(_ENTRY_SURFACE) - set(dyn_checked))
            partial = bool(uncovered)
            verdict = Verdict.UNCERTAIN if partial else Verdict.REJECTED
            detail = (
                f"dynamic entry point(s) found for '{name}': {', '.join(dyn_kinds)}; "
                f"scanned {', '.join(dyn_checked) if dyn_checked else 'nothing'}"
            )
            added.append(
                EvidenceItem(
                    provider="evidence-validator",
                    result="dynamic_entry",
                    kind=EvidenceKind.DETERMINISTIC,
                    rule_id=finding.rule_id,
                    detail=detail,
                    raw={"dynamic_entry_kinds": dyn_kinds, "checked": dyn_checked},
                )
            )
            if verdict is Verdict.UNCERTAIN:
                return self._finalize(
                    finding,
                    verdict,
                    f"{detail}. Entry surface(s) {', '.join(uncovered)} could not be "
                    "inspected, so deletion cannot be declared safe.",
                    original,
                    added,
                    dyn_kinds,
                )
            return self._finalize(
                finding,
                verdict,
                f"{detail}. The code is reachable, so the dead-code claim is rejected.",
                original,
                added,
                dyn_kinds,
            )

        # 2. RV-001 -- a real reference contradicts "no references"
        if name and claims_unused and refs:
            real = [r for r in refs if not self._is_definition(r, finding)]
            if real:
                locations = ", ".join(
                    f"{r.get('file')}:{r.get('line')}({r.get('kind')})" for r in real[:8]
                )
                dynamic = [r for r in real if str(r.get("kind", "")).lower() in _DYNAMIC_REF_KINDS]
                added.append(
                    EvidenceItem(
                        provider="evidence-validator",
                        result="references_found",
                        kind=EvidenceKind.DETERMINISTIC,
                        rule_id=finding.rule_id,
                        detail=f"{len(real)} real reference(s): {locations}",
                        references=len(real),
                        raw={"references": real[:20]},
                    )
                )
                reason = (
                    f"RV-001: the finding claims '{name}' has no references, but "
                    f"{len(real)} real reference(s) exist: {locations}"
                )
                if dynamic:
                    reason += (
                        ". Dynamic reference kinds present: "
                        + ", ".join(sorted({str(r.get('kind')) for r in dynamic}))
                    )
                return self._finalize(
                    finding, Verdict.REJECTED, reason, original, added, dyn_kinds
                )

        # 3. RV-002 -- duplication across different business semantics
        if finding.category is Category.DUPLICATION:
            pair = self._duplicate_regions(finding)
            if pair is not None:
                left, right = pair
                jaccard, shared = self._noun_jaccard(left, right)
                if jaccard < 0.4:
                    added.append(
                        EvidenceItem(
                            provider="evidence-validator",
                            result="semantics_differ",
                            kind=EvidenceKind.DETERMINISTIC,
                            rule_id=finding.rule_id,
                            detail=(
                                f"domain-noun overlap {jaccard:.2f} (<0.40); shared terms: "
                                f"{sorted(shared) if shared else 'none'}"
                            ),
                            raw={"jaccard": round(jaccard, 4), "shared": sorted(shared)},
                        )
                    )
                    return self._finalize(
                        finding,
                        Verdict.DOWNGRADED,
                        f"RV-002: the two blocks share only {jaccard:.0%} of their domain nouns, "
                        "so they may encode different business rules. The finding is kept at LOW "
                        "and needs a human to confirm the business semantics before any merge.",
                        Severity.LOW,
                        added,
                        dyn_kinds,
                    )

        # 4. RV-003 -- a quadratic-looking loop over a tiny constant collection
        if finding.category is Category.PERFORMANCE and self._claims_quadratic(finding):
            bound = self._loop_bound(finding)
            if bound is not None and bound <= 10:
                finding.perf_confidence = PerfConfidence.SUSPECTED
                added.append(
                    EvidenceItem(
                        provider="evidence-validator",
                        result="bounded_collection",
                        kind=EvidenceKind.DETERMINISTIC,
                        rule_id=finding.rule_id,
                        detail=(
                            f"loop collection size is a compile-time constant of {bound} "
                            "element(s); no benchmark or profiler evidence was attached"
                        ),
                        raw={"loop_collection_size": bound},
                    )
                )
                return self._finalize(
                    finding,
                    Verdict.DOWNGRADED,
                    f"RV-003: the loop iterates a compile-time constant of {bound} element(s), "
                    "so the quadratic cost is bounded and is not an incident. Without a "
                    "benchmark the finding drops to LOW / SUSPECTED.",
                    Severity.LOW,
                    added,
                    dyn_kinds,
                )

        # 5. HIGH/CRITICAL with no deterministic evidence (spec §3.1 / §3.2)
        if (
            original.rank >= Severity.HIGH.rank
            and not finding.deterministic_evidence()
        ):
            return self._finalize(
                finding,
                Verdict.DOWNGRADED,
                "no deterministic evidence supports a HIGH/CRITICAL severity; only semantic "
                "impressions were attached, so the finding is capped at MEDIUM until a real "
                "artefact (references, coverage, benchmark, query count) is produced",
                Severity.MEDIUM,
                added,
                dyn_kinds,
            )

        # 6. "historical problem" claim contradicted by the change set
        if self._claims_historical(finding) and finding.introduced_by_current_diff:
            return self._finalize(
                finding,
                Verdict.CONFIRMED,
                "the finding claims to be a pre-existing/historical problem, but "
                "introduced_by_current_diff is True -- it is introduced by this change",
                original,
                added,
                dyn_kinds,
            )

        # 7. default: the finding stands, with the dynamic-entry scan recorded
        if needs_entry_scan and name:
            if not dyn_checked:
                return self._finalize(
                    finding,
                    Verdict.UNCERTAIN,
                    f"no dynamic entry surface could be checked for '{name}' (no symbol index "
                    "and no readable source), so deletion safety is unknown",
                    original,
                    added,
                    dyn_kinds,
                )
            notes.append("dynamic entry scan performed: " + ", ".join(dyn_checked))
        reason = "finding stands: severity is supported by the attached evidence"
        if notes:
            reason += " (" + "; ".join(notes) + ")"
        return self._finalize(finding, Verdict.CONFIRMED, reason, original, added, dyn_kinds)

    # ------------------------------------------------------------ helpers

    def _finalize(
        self,
        finding: Finding,
        verdict: Verdict,
        reason: str,
        new_severity: Severity,
        added: list[EvidenceItem],
        dyn_kinds: list[str],
    ) -> ValidationOutcome:
        original = finding.severity
        finding.severity = new_severity
        if added:
            finding.evidence.extend(added)
        finding.decision.reason = reason
        finding.validation.performed.append("evidence-validator")
        finding.validation.result = verdict.value
        if "evidence-validator" not in finding.sources:
            finding.sources.append("evidence-validator")

        if verdict is Verdict.REJECTED:
            finding.decision.block_merge = False
            self._ensure_status(finding, FindingStatus.REJECTED, reason)
        elif verdict is Verdict.UNCERTAIN:
            finding.decision.block_merge = False
            # CHM-SCHEMA-005: an UNCERTAIN finding may never be auto-fixable.
            finding.repair.auto_fixable = False
            finding.repair.repair_class = RepairClass.MANUAL_DECISION
            self._ensure_status(finding, FindingStatus.UNCERTAIN, reason)
        else:
            self._ensure_status(finding, FindingStatus.VALIDATED, reason)

        return ValidationOutcome(
            finding_id=finding.id,
            verdict=verdict,
            reason=reason,
            original_severity=original,
            new_severity=finding.severity,
            evidence_added=list(added),
            dynamic_entry_kinds=sorted(set(dyn_kinds)),
        )

    _TERMINAL = (FindingStatus.VALIDATED, FindingStatus.REJECTED, FindingStatus.UNCERTAIN)

    def _ensure_status(self, finding: Finding, target: FindingStatus, reason: str) -> None:
        """Walk the legal lifecycle path, never forcing an illegal transition."""
        current = finding.decision.status
        if current is target:
            return
        if current in self._TERMINAL:
            # Already adjudicated.  Moving between terminal states is illegal;
            # keep the recorded lifecycle and just refresh the reason.
            return
        if current is FindingStatus.DETECTED:
            finding.transition(FindingStatus.EVIDENCE_COLLECTED, "evidence validation started")
            current = finding.decision.status
        if current is FindingStatus.EVIDENCE_COLLECTED:
            finding.transition(target, reason)

    @staticmethod
    def _loc_key(finding: Finding) -> tuple:
        return (
            finding.location.file,
            finding.location.start_line,
            finding.location.symbol or "",
        )

    @staticmethod
    def _is_definition(ref: dict, finding: Finding) -> bool:
        return (
            str(ref.get("file", "")).replace("\\", "/").lstrip("./")
            == finding.location.file.replace("\\", "/").lstrip("./")
            and int(ref.get("line", -1) or -1) == finding.location.start_line
            and str(ref.get("kind", "")).lower() not in _DYNAMIC_REF_KINDS
        )

    def _all_evidence_failed(self, finding: Finding) -> bool:
        evidence = list(finding.evidence)
        if not evidence:
            return False
        for e in evidence:
            result = str(getattr(e, "result", "")).lower()
            raw = getattr(e, "raw", None) or {}
            failed = (
                result in ("error", "tool_error", "failed", "failure")
                or bool(raw.get("tool_error"))
                or bool(raw.get("error"))
            )
            if not failed:
                return False
        return True

    @staticmethod
    def _claims_unreferenced(finding: Finding) -> bool:
        rule = finding.rule_id.upper()
        if finding.category is Category.DEAD_CODE:
            return True
        if any(tok in rule for tok in _UNREFERENCED_RULE_TOKENS):
            return True
        return bool(_UNREFERENCED_TITLE_RE.search(finding.title or ""))

    @staticmethod
    def _claims_historical(finding: Finding) -> bool:
        if getattr(finding, "historical", False):
            return True
        for e in finding.evidence:
            raw = getattr(e, "raw", None) or {}
            if raw.get("historical") or raw.get("pre_existing") or raw.get("preexisting"):
                return True
        return bool(_HISTORICAL_TITLE_RE.search(finding.title or ""))

    @staticmethod
    def _claims_quadratic(finding: Finding) -> bool:
        haystack = " ".join(
            [finding.title or "", finding.rule_id or "", finding.decision.reason or ""]
            + [str(getattr(e, "detail", "") or "") for e in finding.evidence]
        )
        return bool(_QUADRATIC_RE.search(haystack))

    # -- reference / dynamic entry discovery ------------------------------

    def _references(self, name: str, finding: Finding) -> list[dict]:
        if self.index is not None:
            try:
                refs = self.index.references(name)
            except Exception:  # noqa: BLE001 - a broken index degrades to a text scan
                refs = None
            if refs is not None:
                return [dict(r) for r in refs]
        return self._text_references(name)

    def _dynamic_entry_scan(self, name: str) -> tuple[bool, list[str], list[str]]:
        """(has_entry, kinds, checked_kinds) for ``name``."""
        if self.index is not None:
            try:
                has = bool(self.index.has_dynamic_entry(name))
                kinds = [str(k) for k in (self.index.dynamic_entry_kinds(name) or [])]
            except Exception:  # noqa: BLE001 - degrade to the text scan below
                has, kinds = None, []
            else:
                checked = list(_ENTRY_SURFACE)
                if has and not kinds:
                    kinds = ["unknown"]
                return has, sorted(set(kinds)), checked

        kinds: list[str] = []
        checked: list[str] = []
        sources = self._candidate_files(want_xml=False)
        if sources:
            checked.extend(["reflection", "spring", "rpc", "mq", "dynamic_import"])
            for _path, text in sources:
                for line in _lines_near_name(text, name):
                    if _REFLECTION_RE.search(line):
                        kinds.append("reflection")
                    if _SPRING_ENTRY_RE.search(line):
                        kinds.append("spring")
                    if _RPC_ENTRY_RE.search(line):
                        kinds.append("rpc")
                    if _MQ_ENTRY_RE.search(line):
                        kinds.append("mq")
                    if _DYNAMIC_IMPORT_RE.search(line):
                        kinds.append("dynamic_import")
        xml_files = self._candidate_files(want_xml=True)
        if xml_files:
            checked.append("xml")
            for _path, text in xml_files:
                for line in _lines_near_name(text, name):
                    if _XML_ENTRY_RE.search(line):
                        kinds.append("xml")

        return bool(kinds), sorted(set(kinds)), checked

    def _text_references(self, name: str) -> list[dict]:
        out: list[dict] = []
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        for path, text in self._candidate_files(want_xml=False):
            for i, line in enumerate(text.split("\n"), start=1):
                if not pattern.search(line):
                    continue
                stripped = line.strip()
                kind = "call"
                if _REFLECTION_RE.search(line):
                    kind = "reflection"
                elif stripped.startswith("import ") or stripped.startswith("from "):
                    kind = "import"
                elif stripped.startswith("@") or re.search(r"@\w+", line):
                    kind = "annotation"
                elif _SPRING_ENTRY_RE.search(line):
                    kind = "spring"
                elif _RPC_ENTRY_RE.search(line):
                    kind = "rpc"
                elif _MQ_ENTRY_RE.search(line):
                    kind = "mq"
                out.append({"file": path, "line": i, "kind": kind})
        for path, text in self._candidate_files(want_xml=True):
            for i, line in enumerate(text.split("\n"), start=1):
                if pattern.search(line) and _XML_ENTRY_RE.search(line):
                    out.append({"file": path, "line": i, "kind": "xml"})
        return out

    def _candidate_files(self, *, want_xml: bool) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for cf in getattr(self.ctx, "changed_files", None) or []:
            if cf.is_binary or cf.is_generated:
                continue
            if _is_xml(cf.path) != want_xml:
                continue
            if cf.path in seen:
                continue
            seen.add(cf.path)
            text = self._read(cf.path)
            if text:
                out.append((cf.path, text[:_MAX_FILE_CHARS]))
        for path in getattr(self.ctx, "repo_files", None) or []:
            if len(out) >= _MAX_SCAN_FILES:
                break
            if path in seen or _is_xml(path) != want_xml:
                continue
            seen.add(path)
            text = self._read(path)
            if text:
                out.append((path, text[:_MAX_FILE_CHARS]))
        return out

    def _read(self, path: str) -> str:
        try:
            return self.ctx.read(path)
        except (OSError, ValueError):
            return ""

    # -- RV-002 / RV-003 helpers ------------------------------------------

    def _duplicate_regions(self, finding: Finding) -> Optional[tuple[str, str]]:
        """Text of the two supposedly duplicated regions, or None if unknown."""
        left = self._region_text(
            finding.location.file, finding.location.start_line, finding.location.end_line
        )
        other = self._other_region(finding)
        if other is None:
            return None
        right = self._region_text(other[0], other[1], other[2])
        if not left.strip() or not right.strip():
            return None
        return left, right

    @staticmethod
    def _other_region(finding: Finding) -> Optional[tuple[str, int, int]]:
        for e in finding.evidence:
            raw = getattr(e, "raw", None) or {}
            dup = raw.get("duplicate_of")
            if isinstance(dup, dict) and dup.get("file"):
                return (
                    str(dup["file"]),
                    int(dup.get("start_line", 1) or 1),
                    int(dup.get("end_line", dup.get("start_line", 1)) or 1),
                )
            if raw.get("other_file"):
                return (
                    str(raw["other_file"]),
                    int(raw.get("other_start_line", 1) or 1),
                    int(raw.get("other_end_line", raw.get("other_start_line", 1)) or 1),
                )
        for e in finding.evidence:
            raw = getattr(e, "raw", None) or {}
            if raw.get("file") and raw.get("start_line"):
                f = str(raw["file"])
                if f != finding.location.file or int(raw["start_line"]) != finding.location.start_line:
                    return (
                        f,
                        int(raw["start_line"]),
                        int(raw.get("end_line", raw["start_line"])),
                    )
        return None

    def _region_text(self, file: str, start: int, end: int) -> str:
        text = self._read(file)
        if not text:
            return ""
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        start = max(1, start)
        end = max(start, end)
        return "\n".join(lines[start - 1 : end])

    @staticmethod
    def _noun_jaccard(left: str, right: str) -> tuple[float, set[str]]:
        a = _domain_nouns(left)
        b = _domain_nouns(right)
        union = a | b
        if not union:
            return 0.0, set()
        shared = a & b
        return len(shared) / len(union), shared

    def _loop_bound(self, finding: Finding) -> Optional[int]:
        for e in finding.evidence:
            raw = getattr(e, "raw", None) or {}
            for key in ("loop_collection_size", "constant_size", "collection_size"):
                value = raw.get(key)
                if isinstance(value, int):
                    return value
        region = self._region_text(
            finding.location.file, finding.location.start_line, finding.location.end_line
        )
        if not region:
            return None
        for pattern, size in _SMALL_LITERAL_PATTERNS:
            if pattern.search(region):
                return size
        for m in re.finditer(r"(?:Arrays\.asList|\bList\.of|\bSet\.of|\bMap\.of)\s*\(([^;]*?)\)", region):
            args = [a for a in m.group(1).split(",") if a.strip()]
            if args and len(args) <= 10:
                return len(args)
        for m in re.finditer(r"=\s*\{([^{}]*)\}", region):
            items = [a for a in m.group(1).split(",") if a.strip()]
            if items and len(items) <= 10:
                return len(items)
        return None


def _is_xml(path: str) -> bool:
    return path.lower().endswith(".xml")


def _lines_near_name(text: str, name: str, window: int = 8) -> list[str]:
    """Lines within ``window`` lines of an occurrence of ``name``.

    Entry points are registered *next to* the symbol they expose, so scanning
    the whole file would report every annotation in the file.  A window keeps
    the heuristic honest.
    """
    lines = text.split("\n")
    hits: list[int] = []
    for i, line in enumerate(lines):
        if name in line:
            hits.append(i)
            if len(hits) >= 5:
                break
    out: list[str] = []
    for i in hits:
        out.extend(lines[max(0, i - window) : i + window + 1])
    return out


def _domain_nouns(text: str) -> set[str]:
    """Business-ish identifiers: camel/snake tokens minus generic vocabulary."""
    nouns: set[str] = set()
    for ident in _IDENT_RE.findall(text):
        for token in _CAMEL_RE.findall(ident):
            token = token.lower()
            if len(token) < 3:
                continue
            if token in _DOMAIN_STOPWORDS:
                continue
            if token.isdigit():
                continue
            nouns.add(token)
    return nouns
