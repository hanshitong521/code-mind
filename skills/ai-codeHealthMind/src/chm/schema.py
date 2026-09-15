"""The Finding standard model (spec §8) and its lifecycle (spec §9).

Every provider -- external CLI, built-in analyzer, or semantic reviewer --
produces ``RawFinding`` objects.  The normalizer turns those into ``Finding``
objects which are the *only* thing the score engine, gate and reports consume.

The validation rules here are the executable form of spec §4
(CHM-SCHEMA-001 .. CHM-SCHEMA-005).  They are enforced on construction and
re-checked before a Finding may be marked ``VALIDATED``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional

from .errors import SchemaError
from .util import clamp, stable_json

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------
# enums
# --------------------------------------------------------------------------


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]

    def __lt__(self, other: "Severity") -> bool:  # type: ignore[override]
        return self.rank < other.rank


_SEVERITY_RANK = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}

#: Severities that MUST carry evidence before they can be VALIDATED (§3.1).
EVIDENCE_REQUIRED = (Severity.CRITICAL, Severity.HIGH)


class Category(str, Enum):
    """The 16 mandatory audit dimensions (spec §10) plus 4 extensions."""

    DEAD_CODE = "DEAD_CODE"
    DUPLICATION = "DUPLICATION"
    WRONG_ABSTRACTION = "WRONG_ABSTRACTION"
    OVER_ENGINEERING = "OVER_ENGINEERING"
    COMPLEXITY = "COMPLEXITY"
    LARGE_METHOD = "LARGE_METHOD"
    LARGE_CLASS = "LARGE_CLASS"
    DEPENDENCY_GROWTH = "DEPENDENCY_GROWTH"
    COMPATIBILITY_JUNK = "COMPATIBILITY_JUNK"
    DEFENSIVE_JUNK = "DEFENSIVE_JUNK"
    ERROR_HANDLING = "ERROR_HANDLING"
    CONCURRENCY = "CONCURRENCY"
    RESOURCE_SAFETY = "RESOURCE_SAFETY"
    DATABASE = "DATABASE"
    PERFORMANCE = "PERFORMANCE"
    TESTABILITY = "TESTABILITY"
    # extensions
    API_SURFACE_GROWTH = "API_SURFACE_GROWTH"
    CONFIG_INFLATION = "CONFIG_INFLATION"
    BOILERPLATE = "BOILERPLATE"
    ARCHITECTURE_DRIFT = "ARCHITECTURE_DRIFT"


MANDATORY_CATEGORIES = tuple(Category)[:16]


class FindingStatus(str, Enum):
    """Lifecycle states (spec §9). ``DETECTED -> FIXED -> PASS`` is forbidden."""

    DETECTED = "DETECTED"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"
    BLOCK = "BLOCK"
    WARN = "WARN"
    INFO = "INFO"
    FIXED = "FIXED"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    REVERIFIED = "REVERIFIED"
    CLOSED = "CLOSED"


#: Legal lifecycle transitions.  Anything else raises.
_ALLOWED_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.DETECTED: {FindingStatus.EVIDENCE_COLLECTED, FindingStatus.REJECTED},
    FindingStatus.EVIDENCE_COLLECTED: {
        FindingStatus.VALIDATED,
        FindingStatus.REJECTED,
        FindingStatus.UNCERTAIN,
    },
    FindingStatus.VALIDATED: {
        FindingStatus.BLOCK,
        FindingStatus.WARN,
        FindingStatus.INFO,
        FindingStatus.ACCEPTED_RISK,
        FindingStatus.FALSE_POSITIVE,
    },
    FindingStatus.UNCERTAIN: {
        FindingStatus.WARN,
        FindingStatus.INFO,
        FindingStatus.BLOCK,
        FindingStatus.REJECTED,
    },
    FindingStatus.BLOCK: {
        FindingStatus.FIXED,
        FindingStatus.ACCEPTED_RISK,
        FindingStatus.FALSE_POSITIVE,
    },
    FindingStatus.WARN: {
        FindingStatus.FIXED,
        FindingStatus.ACCEPTED_RISK,
        FindingStatus.FALSE_POSITIVE,
    },
    FindingStatus.INFO: {
        FindingStatus.FIXED,
        FindingStatus.ACCEPTED_RISK,
        FindingStatus.FALSE_POSITIVE,
        FindingStatus.CLOSED,
    },
    FindingStatus.FIXED: {FindingStatus.REVERIFIED},
    FindingStatus.REVERIFIED: {FindingStatus.CLOSED},
    FindingStatus.ACCEPTED_RISK: {FindingStatus.CLOSED},
    FindingStatus.FALSE_POSITIVE: {FindingStatus.CLOSED},
    FindingStatus.REJECTED: {FindingStatus.CLOSED},
    FindingStatus.CLOSED: set(),
}


class RepairClass(str, Enum):
    """Spec §23."""

    SAFE_AUTO_FIX = "SAFE_AUTO_FIX"
    WRITER_FIX = "WRITER_FIX"
    MANUAL_DECISION = "MANUAL_DECISION"
    NONE = "NONE"


class EvidenceKind(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    SEMANTIC = "SEMANTIC"


class PerfConfidence(str, Enum):
    """Performance findings must be classified (spec §19)."""

    PROVEN = "PROVEN"
    LIKELY = "LIKELY"
    SUSPECTED = "SUSPECTED"


class GateVerdict(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"


#: Exit codes are part of the public contract (spec §49).
EXIT_CODES: dict[GateVerdict, int] = {
    GateVerdict.PASS: 0,
    GateVerdict.WARN: 0,
    GateVerdict.BLOCK: 1,
    GateVerdict.UNKNOWN: 3,
}
EXIT_TOOL_ERROR = 2


# --------------------------------------------------------------------------
# value objects
# --------------------------------------------------------------------------


@dataclass
class Location:
    file: str
    start_line: int = 1
    end_line: int = 1
    symbol: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol": self.symbol,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Location":
        return cls(
            file=d["file"],
            start_line=int(d.get("start_line", 1)),
            end_line=int(d.get("end_line", d.get("start_line", 1))),
            symbol=d.get("symbol"),
        )


@dataclass
class EvidenceItem:
    """One concrete piece of evidence.  ``provider`` is mandatory."""

    provider: str
    result: str
    kind: EvidenceKind = EvidenceKind.DETERMINISTIC
    rule_id: Optional[str] = None
    detail: Optional[str] = None
    references: Optional[int] = None
    raw: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "provider": self.provider,
            "kind": self.kind.value,
            "result": self.result,
        }
        if self.rule_id:
            out["rule_id"] = self.rule_id
        if self.detail:
            out["detail"] = self.detail
        if self.references is not None:
            out["references"] = self.references
        if self.raw:
            out["raw"] = self.raw
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvidenceItem":
        return cls(
            provider=d["provider"],
            result=d.get("result", "hit"),
            kind=EvidenceKind(d.get("kind", "DETERMINISTIC")),
            rule_id=d.get("rule_id"),
            detail=d.get("detail"),
            references=d.get("references"),
            raw=d.get("raw"),
        )


@dataclass
class Uncertainty:
    """Dynamic-entry checks performed before any delete recommendation."""

    reflection_checked: bool = False
    spring_registration_checked: bool = False
    rpc_registration_checked: bool = False
    mq_registration_checked: bool = False
    xml_registration_checked: bool = False
    dynamic_import_checked: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def any_check(self) -> bool:
        return any(
            (
                self.reflection_checked,
                self.spring_registration_checked,
                self.rpc_registration_checked,
                self.mq_registration_checked,
                self.xml_registration_checked,
                self.dynamic_import_checked,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reflection_checked": self.reflection_checked,
            "spring_registration_checked": self.spring_registration_checked,
            "rpc_registration_checked": self.rpc_registration_checked,
            "mq_registration_checked": self.mq_registration_checked,
            "xml_registration_checked": self.xml_registration_checked,
            "dynamic_import_checked": self.dynamic_import_checked,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Uncertainty":
        return cls(
            reflection_checked=bool(d.get("reflection_checked")),
            spring_registration_checked=bool(d.get("spring_registration_checked")),
            rpc_registration_checked=bool(d.get("rpc_registration_checked")),
            mq_registration_checked=bool(d.get("mq_registration_checked")),
            xml_registration_checked=bool(d.get("xml_registration_checked")),
            dynamic_import_checked=bool(d.get("dynamic_import_checked")),
            notes=list(d.get("notes", [])),
        )


@dataclass
class Decision:
    status: FindingStatus = FindingStatus.DETECTED
    block_merge: bool = False
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "block_merge": self.block_merge, "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Decision":
        return cls(
            status=FindingStatus(d.get("status", "DETECTED")),
            block_merge=bool(d.get("block_merge")),
            reason=d.get("reason"),
        )


@dataclass
class Recommendation:
    preferred: str = ""
    fallback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"preferred": self.preferred, "fallback": self.fallback}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Recommendation":
        return cls(preferred=d.get("preferred", ""), fallback=d.get("fallback", ""))


@dataclass
class Repair:
    auto_fixable: bool = False
    repair_class: RepairClass = RepairClass.NONE
    recipe: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_fixable": self.auto_fixable,
            "repair_class": self.repair_class.value,
            "recipe": self.recipe,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Repair":
        return cls(
            auto_fixable=bool(d.get("auto_fixable")),
            repair_class=RepairClass(d.get("repair_class", "NONE")),
            recipe=d.get("recipe"),
        )


@dataclass
class Validation:
    required: list[str] = field(default_factory=list)
    performed: list[str] = field(default_factory=list)
    result: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": list(self.required),
            "performed": list(self.performed),
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Validation":
        return cls(
            required=list(d.get("required", [])),
            performed=list(d.get("performed", [])),
            result=d.get("result"),
        )


# --------------------------------------------------------------------------
# raw finding (provider output, pre-normalisation)
# --------------------------------------------------------------------------


@dataclass
class RawFinding:
    """What a provider emits.  Deliberately loose -- normalisation tightens it."""

    provider: str
    rule_id: str
    message: str
    file: str
    start_line: int = 1
    end_line: int = 1
    symbol: Optional[str] = None
    category: Optional[Category] = None
    severity: Optional[Severity] = None
    confidence: float = 0.5
    kind: EvidenceKind = EvidenceKind.DETERMINISTIC
    detail: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return f"{self.rule_id}|{self.file}|{self.start_line}|{self.symbol or ''}"


# --------------------------------------------------------------------------
# Finding
# --------------------------------------------------------------------------

_ID_RE = re.compile(r"^CHM-[0-9]{6,}$")
_RULE_RE = re.compile(r"^CHM-[A-Z0-9]+(-[A-Z0-9]+)+$")


@dataclass
class Finding:
    """The standard model of spec §8."""

    id: str
    rule_id: str
    category: Category
    title: str
    severity: Severity
    confidence: float
    location: Location
    introduced_by_current_diff: bool = False

    evidence: list[EvidenceItem] = field(default_factory=list)
    uncertainty: Uncertainty = field(default_factory=Uncertainty)
    decision: Decision = field(default_factory=Decision)
    recommendation: Recommendation = field(default_factory=Recommendation)
    repair: Repair = field(default_factory=Repair)
    validation: Validation = field(default_factory=Validation)

    #: performance classification (spec §19); None for non-performance findings
    perf_confidence: Optional[PerfConfidence] = None
    #: free-form provenance used by the deduplicator
    sources: list[str] = field(default_factory=list)
    #: lifecycle trace, newest last
    history: list[str] = field(default_factory=list)
    #: baseline bookkeeping
    historical: bool = False
    score_weight: float = 1.0

    # ---------------------------------------------------------------- checks

    def deterministic_evidence(self) -> list[EvidenceItem]:
        return [e for e in self.evidence if e.kind is EvidenceKind.DETERMINISTIC]

    def semantic_evidence(self) -> list[EvidenceItem]:
        return [e for e in self.evidence if e.kind is EvidenceKind.SEMANTIC]

    def validate_schema(self) -> None:
        """CHM-SCHEMA-001/002/003 -- structural validation."""
        problems: list[str] = []

        # CHM-SCHEMA-001 -- required fields
        if not self.id or not _ID_RE.match(self.id):
            problems.append(f"CHM-SCHEMA-001: id '{self.id}' must match CHM-NNNNNN")
        if not self.rule_id or not _RULE_RE.match(self.rule_id):
            problems.append(f"CHM-SCHEMA-001: rule_id '{self.rule_id}' malformed")
        if not self.title:
            problems.append("CHM-SCHEMA-001: title is required")
        if not self.location or not self.location.file:
            problems.append("CHM-SCHEMA-001: location.file is required")

        # CHM-SCHEMA-002 -- severity enum
        if not isinstance(self.severity, Severity):
            problems.append(f"CHM-SCHEMA-002: severity '{self.severity}' is not a Severity")

        # CHM-SCHEMA-003 -- confidence range
        if not isinstance(self.confidence, (int, float)):
            problems.append("CHM-SCHEMA-003: confidence must be numeric")
        elif not (0.0 <= float(self.confidence) <= 1.0):
            problems.append(f"CHM-SCHEMA-003: confidence {self.confidence} outside 0..1")

        if not isinstance(self.category, Category):
            problems.append(f"CHM-SCHEMA-002: category '{self.category}' is not a Category")

        if problems:
            raise SchemaError("; ".join(problems), finding_id=self.id)

    def validate_evidence(self) -> None:
        """CHM-SCHEMA-004 -- HIGH/CRITICAL need evidence to be VALIDATED."""
        if self.severity in EVIDENCE_REQUIRED and not self.evidence:
            raise SchemaError(
                "CHM-SCHEMA-004: HIGH/CRITICAL finding has no evidence",
                finding_id=self.id,
                severity=self.severity.value,
            )

    def validate_uncertain_safety(self) -> None:
        """CHM-SCHEMA-005 -- UNCERTAIN findings may never be auto-deleted."""
        if self.decision.status is FindingStatus.UNCERTAIN:
            if self.repair.auto_fixable or self.repair.repair_class is RepairClass.SAFE_AUTO_FIX:
                raise SchemaError(
                    "CHM-SCHEMA-005: UNCERTAIN finding must not be auto-fixable",
                    finding_id=self.id,
                )

    def validate_all(self) -> None:
        self.validate_schema()
        self.validate_uncertain_safety()

    # ------------------------------------------------------------ lifecycle

    def transition(self, new_status: FindingStatus, reason: Optional[str] = None) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(self.decision.status, set())
        if new_status not in allowed:
            raise SchemaError(
                f"illegal lifecycle transition {self.decision.status.value} -> {new_status.value}",
                finding_id=self.id,
            )
        if new_status is FindingStatus.VALIDATED:
            self.validate_evidence()
        self.decision.status = new_status
        if reason:
            self.decision.reason = reason
        self.history.append(new_status.value)

    def clamp_confidence(self) -> None:
        self.confidence = round(clamp(float(self.confidence), 0.0, 1.0), 4)

    # ------------------------------------------------------------------ io

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "rule_id": self.rule_id,
            "category": self.category.value,
            "title": self.title,
            "severity": self.severity.value,
            "confidence": round(float(self.confidence), 4),
            "location": self.location.to_dict(),
            "change_scope": {"introduced_by_current_diff": self.introduced_by_current_diff},
            "evidence": {
                "deterministic": [e.to_dict() for e in self.deterministic_evidence()],
                "semantic": [e.to_dict() for e in self.semantic_evidence()],
            },
            "uncertainty": self.uncertainty.to_dict(),
            "decision": self.decision.to_dict(),
            "recommendation": self.recommendation.to_dict(),
            "repair": self.repair.to_dict(),
            "validation": self.validation.to_dict(),
            "sources": sorted(set(self.sources)),
            "historical": self.historical,
            "history": list(self.history),
        }
        if self.perf_confidence is not None:
            out["perf_confidence"] = self.perf_confidence.value
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        ev = d.get("evidence", {})
        evidence = [EvidenceItem.from_dict(x) for x in ev.get("deterministic", [])]
        evidence += [EvidenceItem.from_dict(x) for x in ev.get("semantic", [])]
        perf = d.get("perf_confidence")
        return cls(
            id=d["id"],
            rule_id=d["rule_id"],
            category=Category(d["category"]),
            title=d["title"],
            severity=Severity(d["severity"]),
            confidence=float(d["confidence"]),
            location=Location.from_dict(d["location"]),
            introduced_by_current_diff=bool(
                d.get("change_scope", {}).get("introduced_by_current_diff")
            ),
            evidence=evidence,
            uncertainty=Uncertainty.from_dict(d.get("uncertainty", {})),
            decision=Decision.from_dict(d.get("decision", {})),
            recommendation=Recommendation.from_dict(d.get("recommendation", {})),
            repair=Repair.from_dict(d.get("repair", {})),
            validation=Validation.from_dict(d.get("validation", {})),
            perf_confidence=PerfConfidence(perf) if perf else None,
            sources=list(d.get("sources", [])),
            historical=bool(d.get("historical")),
            history=list(d.get("history", [])),
        )

    def canonical_key(self) -> str:
        """Stable identity used by the deduplicator and by baseline diffing."""
        return stable_json(
            {
                "rule_id": self.rule_id,
                "file": self.location.file,
                "line": self.location.start_line,
                "symbol": self.location.symbol,
            }
        )


# --------------------------------------------------------------------------
# aggregation helpers
# --------------------------------------------------------------------------


def severity_counts(findings: Iterable[Finding]) -> dict[str, int]:
    counts = {s.value: 0 for s in Severity}
    for f in findings:
        counts[f.severity.value] += 1
    return counts


def worst_severity(findings: Iterable[Finding]) -> Optional[Severity]:
    worst: Optional[Severity] = None
    for f in findings:
        if worst is None or f.severity.rank > worst.rank:
            worst = f.severity
    return worst
