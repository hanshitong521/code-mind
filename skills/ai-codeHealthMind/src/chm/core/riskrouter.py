"""Risk Router (spec §4.3).

Cheap review for cheap changes, expensive review for dangerous ones.  The
router answers one question: *how much scrutiny does this change set deserve?*

    LOW       -> 1 reviewer, deterministic evidence only
    MEDIUM    -> 1 reviewer + deterministic evidence
    HIGH      -> 2 reviewers (cross-model when a real LLM backend is configured)
    CRITICAL  -> 2 reviewers + Evidence Validator + full gate

Two honesty rules are enforced here:

* ``multi_model_on_high`` only produces two *different* models when
  ``review.backend == "llm"``.  With the rule backend the reason string says so
  explicitly -- we never claim a cross-model review that did not happen.
* ``backend == "off"`` means **zero** reviewers run, and the plan says that
  rather than pretending the semantic layer approved anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..config import Config
from ..contracts import ScanContext
from ..schema import Finding, Severity

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CRITICAL = "CRITICAL"

RISK_ORDER: tuple[str, ...] = (LOW, MEDIUM, HIGH, CRITICAL)

#: Domains where a small-looking change can still lose money or corrupt state.
SENSITIVE_KEYWORDS: tuple[str, ...] = (
    "payment",
    "refund",
    "amount",
    "coupon",
    "order",
    "transaction",
    "auth",
    "permission",
    "lock",
)

_DOC_SUFFIXES = (".md", ".txt", ".rst", ".adoc", ".adr")
_TEST_RE = re.compile(
    r"(^|/)(test|tests|__tests__|spec|specs|testing)(/|$)"
    r"|(Test|Tests|Spec|IT)\.(java|js|jsx|ts|tsx|vue)$"
    r"|\.(test|spec)\.(js|jsx|ts|tsx|vue)$",
    re.IGNORECASE,
)

_MAX_KEYWORD_SCAN_CHARS = 200_000


@dataclass
class RoutePlan:
    risk: str
    reviewers: int
    validator: bool
    deterministic_only: bool
    expansion: str
    models: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "risk": self.risk,
            "reviewers": self.reviewers,
            "validator": self.validator,
            "deterministic_only": self.deterministic_only,
            "expansion": self.expansion,
            "models": list(self.models),
            "reason": self.reason,
        }


def risk_of(findings: Iterable[Finding]) -> str:
    """Risk implied by the findings we already have.  Empty -> LOW."""
    worst: Optional[Severity] = None
    for f in findings:
        sev = getattr(f, "severity", None)
        if sev is None:
            continue
        if worst is None or sev.rank > worst.rank:
            worst = sev
    if worst is None:
        return LOW
    return {
        Severity.LOW: LOW,
        Severity.MEDIUM: MEDIUM,
        Severity.HIGH: HIGH,
        Severity.CRITICAL: CRITICAL,
    }[worst]


def _is_doc_or_test(path: str) -> bool:
    lower = path.lower()
    if lower.endswith(_DOC_SUFFIXES):
        return True
    return bool(_TEST_RE.search(path.replace("\\", "/")))


def _sensitive_hit(ctx: ScanContext, cf) -> Optional[str]:
    """First sensitive keyword found in the path or the file body, if any."""
    lower_path = cf.path.lower()
    for kw in SENSITIVE_KEYWORDS:
        if kw in lower_path:
            return kw
    text = ""
    try:
        text = ctx.read(cf.path)[:_MAX_KEYWORD_SCAN_CHARS]
    except (OSError, ValueError):
        text = ""
    if not text:
        return None
    haystack = text.lower()
    for kw in SENSITIVE_KEYWORDS:
        if kw in haystack:
            return kw
    return None


def initial_risk(ctx: ScanContext) -> tuple[str, str]:
    """Risk of a change set *before* any finding exists.

    Documentation/test-only changes are LOW; anything touching money, orders,
    authentication, permissions or locking starts at HIGH; everything else is
    MEDIUM.
    """
    files = list(getattr(ctx, "changed_files", None) or [])
    if not files:
        return LOW, "empty change set"

    if all(_is_doc_or_test(cf.path) for cf in files):
        return LOW, f"documentation/test-only change set ({len(files)} file(s))"

    for cf in files:
        if cf.is_generated:
            continue
        kw = _sensitive_hit(ctx, cf)
        if kw is not None:
            return (
                HIGH,
                f"sensitive-domain keyword '{kw}' in {cf.path} "
                f"({len(files)} file(s) in the change set)",
            )

    return MEDIUM, f"ordinary source change, {len(files)} file(s), no sensitive-domain keyword"


def plan_route(findings: list[Finding], ctx: ScanContext, config: Config) -> RoutePlan:
    """Decide how much scrutiny this change set gets, and say why."""
    review = config.review

    if findings:
        risk = risk_of(findings)
        basis = f"risk={risk} from {len(findings)} existing finding(s)"
    else:
        risk, why = initial_risk(ctx)
        basis = f"risk={risk} (pre-review) because {why}"

    if risk == LOW:
        reviewers = int(review.reviewers_low)
        validator = False
        deterministic_only = True
        expansion = "none"
        tier = f"LOW -> {reviewers} reviewer(s), deterministic evidence only"
    elif risk == MEDIUM:
        reviewers = int(review.reviewers_medium)
        validator = False
        deterministic_only = True
        expansion = "direct_refs"
        tier = f"MEDIUM -> {reviewers} reviewer(s) + deterministic evidence"
    elif risk == HIGH:
        reviewers = int(review.reviewers_high)
        validator = bool(review.validator_on_high)
        deterministic_only = False
        expansion = "callgraph_tests_config"
        tier = f"HIGH -> {reviewers} reviewer(s), validator={'on' if validator else 'off'}"
    else:
        reviewers = int(review.reviewers_critical)
        validator = bool(review.validator_on_critical)
        deterministic_only = False
        expansion = "full_slice"
        tier = f"CRITICAL -> {reviewers} reviewer(s) + validator + full gate"

    backend = str(getattr(review, "backend", "rule") or "rule").lower()
    models = [review.model_a]
    notes: list[str] = []

    if risk in (HIGH, CRITICAL) and review.multi_model_on_high:
        if backend == "llm":
            models = [review.model_a, review.model_b]
            notes.append(f"llm backend: cross-model review with {models}")
        else:
            notes.append(f"{backend} backend: cross-model review not applicable")

    if backend == "off":
        reviewers = 0
        notes.append(
            "review backend is 'off': no semantic reviewer runs; "
            "this is NOT evidence that the semantic layer approved the change"
        )
    elif backend == "rule":
        notes.append(
            "rule backend: findings are deterministic Python heuristics labelled "
            "reviewer:<persona>:rule, not an independent model opinion"
        )

    if validator and risk in (HIGH, CRITICAL) and backend == "off":
        notes.append("validator still runs on deterministic findings")

    reason = "; ".join([basis, tier, f"expansion={expansion}", *notes])
    return RoutePlan(
        risk=risk,
        reviewers=reviewers,
        validator=validator,
        deterministic_only=deterministic_only,
        expansion=expansion,
        models=models,
        reason=reason,
    )
