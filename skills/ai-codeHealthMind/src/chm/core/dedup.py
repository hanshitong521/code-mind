"""Deterministic cross-provider deduplication (spec §14.4).

The whole point of the engine is that *three tools reporting the same problem*
must reach the reviewer as **one** finding that carries three pieces of
evidence -- not as three findings that inflate the score damage and bury the
real issue in noise.

Merge is conservative on purpose.  Two findings are the same issue only when

* they point at the same file, **and**
* they are within :data:`MAX_LINE_DELTA` lines of each other *or* share the
  same symbol, **and**
* their categories are identical or belong to the same family.

Two similar problems in different files (or 40 lines apart) are two problems
and stay two findings.

Everything here is deterministic: the same input list always produces the same
output order, the same kept ids and the same merge groups.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Optional

from ..schema import Category, EvidenceItem, Finding, PerfConfidence

#: Two findings further apart than this are never the same issue unless they
#: share a symbol.
MAX_LINE_DELTA = 3

#: Independent providers confirming the same issue raise our confidence a
#: little -- never to certainty (spec §8 "confidence must not become a claim").
CONFIDENCE_BOOST = 0.05
CONFIDENCE_CEIL = 0.99

#: Actors that annotate a finding but are not independent *evidence* providers.
#: They must never count towards the "two independent sources" confidence
#: boost -- otherwise the validator would inflate its own confidence for free.
NON_EVIDENCE_SOURCES: frozenset[str] = frozenset(
    {"evidence-validator", "validator", "reviewer", "symbol-index", "orchestrator"}
)


# --------------------------------------------------------------------------
# category families
# --------------------------------------------------------------------------

#: Categories that describe the same underlying smell.  Kept deliberately
#: small: a family is a statement that "these two tool vocabularies are
#: talking about one problem", which is a judgement we should not overreach.
CATEGORY_FAMILIES: tuple[frozenset[Category], ...] = (
    frozenset({Category.DEAD_CODE}),
    frozenset({Category.DUPLICATION, Category.BOILERPLATE}),
    frozenset({Category.WRONG_ABSTRACTION, Category.OVER_ENGINEERING}),
    frozenset({Category.COMPLEXITY, Category.LARGE_METHOD, Category.LARGE_CLASS}),
    frozenset({Category.ERROR_HANDLING, Category.DEFENSIVE_JUNK}),
    frozenset({Category.RESOURCE_SAFETY, Category.CONCURRENCY}),
    frozenset({Category.DATABASE, Category.PERFORMANCE}),
)

CATEGORY_FAMILY: dict[Category, int] = {}
for _index, _family in enumerate(CATEGORY_FAMILIES):
    for _member in _family:
        CATEGORY_FAMILY[_member] = _index

#: A family's human name, used in merge reasons.
FAMILY_NAMES: tuple[str, ...] = tuple(
    "{" + ",".join(sorted(c.value for c in fam)) + "}" for fam in CATEGORY_FAMILIES
)

_PERF_RANK = {
    PerfConfidence.SUSPECTED: 0,
    PerfConfidence.LIKELY: 1,
    PerfConfidence.PROVEN: 2,
}


# --------------------------------------------------------------------------
# result objects
# --------------------------------------------------------------------------


@dataclass
class MergeGroup:
    """One merged cluster.  ``merged_ids`` are the findings that disappeared."""

    kept_id: str
    merged_ids: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept_id": self.kept_id,
            "merged_ids": list(self.merged_ids),
            "merged_count": len(self.merged_ids),
            "sources": list(self.sources),
            "reason": self.reason,
        }


@dataclass
class DedupResult:
    findings: list[Finding] = field(default_factory=list)
    groups: list[MergeGroup] = field(default_factory=list)
    dedup_ratio: float = 0.0
    merged_count: int = 0

    @property
    def original_count(self) -> int:
        return len(self.findings) + self.merged_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "groups": [g.to_dict() for g in self.groups],
            "dedup_ratio": self.dedup_ratio,
            "merged_count": self.merged_count,
            "kept_count": len(self.findings),
            "original_count": self.original_count,
        }


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------


def _norm_file(path: Optional[str]) -> str:
    """Posix-normalised path, used for comparison only (never for output)."""
    text = (path or "").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def is_same_issue(a: Finding, b: Finding) -> tuple[bool, str]:
    """Decide whether ``a`` and ``b`` describe one problem.

    Returns ``(True, reason)`` or ``(False, reason)``.  The reason is stable
    text so it can be embedded in the merge group and asserted in tests.
    """
    file_a = _norm_file(a.location.file)
    file_b = _norm_file(b.location.file)
    if file_a != file_b:
        return False, f"different file ({a.location.file} vs {b.location.file})"

    sym_a = a.location.symbol
    sym_b = b.location.symbol
    same_symbol = bool(sym_a) and sym_a == sym_b
    delta = abs(int(a.location.start_line) - int(b.location.start_line))
    if not same_symbol and delta > MAX_LINE_DELTA:
        return False, f"line delta {delta} > {MAX_LINE_DELTA} and no shared symbol"

    if a.category is b.category:
        semantic = f"same category {a.category.value}"
    else:
        fam_a = CATEGORY_FAMILY.get(a.category)
        fam_b = CATEGORY_FAMILY.get(b.category)
        if fam_a is None or fam_b is None or fam_a != fam_b:
            return False, (
                f"unrelated categories {a.category.value} / {b.category.value}"
            )
        semantic = f"category family {FAMILY_NAMES[fam_a]}"

    if same_symbol:
        where = f"same symbol {sym_a}"
    elif delta == 0:
        where = "same line"
    else:
        where = f"line delta {delta}"

    return True, f"same file + {where} + {semantic}"


# --------------------------------------------------------------------------
# merging
# --------------------------------------------------------------------------


def _evidence_signature(item: EvidenceItem) -> tuple[str, str, str, str]:
    return (
        item.provider,
        item.kind.value,
        item.rule_id or "",
        item.result or "",
    )


def _merge_members(members: list[Finding]) -> Finding:
    """Fold ``members`` (already ordered best-first) into one finding.

    Returns a *copy*; the caller's objects are never mutated.
    """
    kept = copy.deepcopy(members[0])
    others = members[1:]

    evidence: list[EvidenceItem] = []
    seen: set[tuple[str, str, str, str]] = set()
    providers: set[str] = set()
    for member in members:
        for item in member.evidence:
            signature = _evidence_signature(item)
            if signature in seen:
                continue
            seen.add(signature)
            evidence.append(copy.deepcopy(item))
            providers.add(item.provider)

    for member in members:
        providers.update(member.sources)

    kept.evidence = evidence
    kept.sources = sorted(providers)

    max_confidence = max(float(m.confidence) for m in members)
    independent = {
        p for p in providers if p.split(":")[0] not in NON_EVIDENCE_SOURCES
    }
    if len(independent) >= 2:
        kept.confidence = round(min(CONFIDENCE_CEIL, max_confidence + CONFIDENCE_BOOST), 4)
    else:
        kept.confidence = round(max_confidence, 4)

    # A finding that any provider attributes to this change is attributed to
    # this change; it is only "historical" when every source agrees.
    kept.introduced_by_current_diff = any(m.introduced_by_current_diff for m in members)
    kept.historical = all(m.historical for m in members)

    if kept.perf_confidence is None:
        best = None
        for member in members:
            if member.perf_confidence is None:
                continue
            if best is None or _PERF_RANK[member.perf_confidence] > _PERF_RANK[best]:
                best = member.perf_confidence
        kept.perf_confidence = best

    kept.decision.block_merge = any(m.decision.block_merge for m in members)

    if others:
        kept.history = list(kept.history) + [
            f"merged:{m.id}" for m in others
        ]

    return kept


def _output_order(finding: Finding) -> tuple[int, str, int, int, str]:
    return (
        -finding.severity.rank,
        _norm_file(finding.location.file),
        int(finding.location.start_line),
        int(finding.location.end_line),
        finding.id,
    )


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def deduplicate(findings: list[Finding], *, config: Any = None) -> DedupResult:
    """Cluster and merge ``findings``.

    ``config`` is accepted for interface symmetry; the rules here are not
    configurable because a weaker merge would silently double-count debt.
    """
    original_count = len(findings)
    if original_count == 0:
        return DedupResult(findings=[], groups=[], dedup_ratio=0.0, merged_count=0)

    # Best-first: highest severity, then highest confidence, then id.  The
    # first member of a cluster is therefore always the one we keep.
    ordered = sorted(
        findings,
        key=lambda f: (
            -f.severity.rank,
            -round(float(f.confidence), 4),
            f.id,
        ),
    )

    clusters: list[list[Finding]] = []
    cluster_reasons: list[list[str]] = []
    for finding in ordered:
        placed = False
        for index, cluster in enumerate(clusters):
            same, reason = is_same_issue(cluster[0], finding)
            if same:
                cluster.append(finding)
                cluster_reasons[index].append(f"{finding.id}: {reason}")
                placed = True
                break
        if not placed:
            clusters.append([finding])
            cluster_reasons.append([])

    kept_findings: list[Finding] = []
    groups: list[MergeGroup] = []
    merged_count = 0

    for cluster, reasons in zip(clusters, cluster_reasons):
        merged = _merge_members(cluster)
        kept_findings.append(merged)
        if len(cluster) > 1:
            merged_count += len(cluster) - 1
            groups.append(
                MergeGroup(
                    kept_id=merged.id,
                    merged_ids=[m.id for m in cluster[1:]],
                    sources=sorted(set(merged.sources)),
                    reason="; ".join(reasons),
                )
            )

    kept_findings.sort(key=_output_order)
    groups.sort(key=lambda g: g.kept_id)

    return DedupResult(
        findings=kept_findings,
        groups=groups,
        dedup_ratio=round(merged_count / max(1, original_count), 4),
        merged_count=merged_count,
    )
