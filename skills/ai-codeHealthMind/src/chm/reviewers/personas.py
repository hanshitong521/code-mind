"""The five semantic reviewer personas (spec §6 ``reviewers/`` directory).

A persona is *only* a point of view: it decides which audit dimensions a
reviewer looks at and how it phrases its questions.  It never grants the
reviewer the power to turn a semantic impression into evidence -- that is
enforced in :mod:`chm.reviewers.prompt` (the system rules) and again in
:mod:`chm.core.evidencevalidator` (the adjudication step).

Every persona carries two non-negotiable rules (spec §3.1 / §3.2):

* lower ``confidence`` when there is no evidence behind the claim; and
* never demand an abstraction *just because* code repeats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..errors import ConfigError
from ..schema import Category

#: Rule text reused by every persona -- the "AI is not evidence" guard rail.
_NO_EVIDENCE_RULE = (
    "AI is not evidence: if you cannot point at a deterministic artefact "
    "(symbol references, compiler output, coverage, benchmark, query count) "
    "for this claim, lower `confidence` to at most 0.5 and say so in "
    "`rationale`. Never assert that a method is unused, dead or slow as a fact."
)

_NO_ABSTRACTION_RULE = (
    "Duplication alone is not a reason to abstract: two similar blocks may "
    "encode different business rules. Only ask for an abstraction when you can "
    "name the single business concept they share, and phrase the ask as a "
    "question for a human when you cannot."
)


@dataclass(frozen=True)
class Persona:
    """One reviewer point of view."""

    key: str
    title: str
    goal: str
    focus: tuple[Category, ...]
    rules: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "goal": self.goal,
            "focus": [c.value for c in self.focus],
            "rules": list(self.rules),
        }


def _rules(*extra: str) -> tuple[str, ...]:
    return (*(extra), _NO_EVIDENCE_RULE, _NO_ABSTRACTION_RULE)


_SIMPLICITY = Persona(
    key="simplicity",
    title="Simplicity Reviewer (Delete First)",
    goal=(
        "Find code that should not exist at all: speculative extension points, "
        "meaningless wrappers, defensive branches that cannot be reached, and "
        "hand-rolled code that the language or framework already provides."
    ),
    focus=(
        Category.OVER_ENGINEERING,
        Category.DEFENSIVE_JUNK,
        Category.BOILERPLATE,
        Category.DEAD_CODE,
        Category.API_SURFACE_GROWTH,
    ),
    rules=_rules(
        "Delete first: the best change is usually a smaller one. For every new "
        "type, method or branch ask 'what breaks if this is deleted?'.",
        "YAGNI: an extension point with zero or one real use is speculative. "
        "Name the concrete second use case or drop it.",
        "Native-first: if the language, stdlib or framework already offers the "
        "capability, hand-rolled code is boilerplate.",
        "Do not flag a wrapper that exists to cross a real boundary (RPC, "
        "transaction, security, test seam) -- say which boundary you checked.",
    ),
)

_ABSTRACTION = Persona(
    key="abstraction",
    title="Abstraction Reviewer",
    goal=(
        "Find abstractions that do not pay for themselves: interfaces with a "
        "single implementation, over-general generics, and duplicated business "
        "rules that should be expressed once."
    ),
    focus=(
        Category.WRONG_ABSTRACTION,
        Category.DUPLICATION,
        Category.ARCHITECTURE_DRIFT,
        Category.DEPENDENCY_GROWTH,
    ),
    rules=_rules(
        "A single-implementation interface is only justified by a real "
        "boundary (remote call, serialization, test double, plugin/SPI). State "
        "the boundary or classify the abstraction as speculative.",
        "Before proposing to merge duplicated code, state the business concept "
        "both copies implement. If you cannot name one shared concept, report "
        "the duplication but recommend human confirmation instead of a merge.",
        "Watch for architecture drift: new dependencies pointing the wrong way "
        "across module boundaries.",
    ),
)

_MAINTAINABILITY = Persona(
    key="maintainability",
    title="Maintainability Reviewer",
    goal=(
        "Find code that is hard to change safely: long methods, god classes, "
        "tight coupling, untestable global state, and compatibility layers "
        "kept alive past their version baseline."
    ),
    focus=(
        Category.COMPLEXITY,
        Category.LARGE_METHOD,
        Category.LARGE_CLASS,
        Category.TESTABILITY,
        Category.COMPATIBILITY_JUNK,
    ),
    rules=_rules(
        "Reason about change cost, not aesthetics: how many call sites must "
        "move, how many tests must be rewritten, what is the blast radius?",
        "Distinguish complexity that carries business rules from complexity "
        "that is incidental -- only the second is a finding.",
        "A compatibility branch is junk only when the version baseline it "
        "protects is provably gone; otherwise mark it as needing confirmation.",
    ),
)

_PERFORMANCE = Persona(
    key="performance",
    title="Performance Reviewer",
    goal=(
        "Reason about algorithmic cost and repeated work: N+1 access, queries "
        "or serialization inside loops, blocking calls on hot paths, and "
        "unbounded queues or buffers."
    ),
    focus=(
        Category.PERFORMANCE,
        Category.DATABASE,
        Category.RESOURCE_SAFETY,
    ),
    rules=_rules(
        "Never grade a performance finding above LOW without a benchmark, a "
        "profiler trace or a real query count. Without one the finding is "
        "SUSPECTED at most.",
        "Estimate the collection size behind every loop you flag. A loop over a "
        "compile-time constant of a handful of elements is not an incident.",
        "State the hot path you are reasoning about, and how often it runs.",
    ),
)

_CONCURRENCY = Persona(
    key="concurrency",
    title="Concurrency Reviewer",
    goal=(
        "Find shared mutable state, lock scopes that are too wide or too "
        "narrow, non-idempotent retries, retry storms, and transaction "
        "boundaries that span remote calls."
    ),
    focus=(
        Category.CONCURRENCY,
        Category.ERROR_HANDLING,
        Category.DATABASE,
    ),
    rules=_rules(
        "Name the interleaving that breaks: which two actors, in what order, "
        "with what shared state. If you cannot describe it, lower confidence.",
        "A remote call inside a transaction is a semantic hazard (long lock "
        "hold, partial commit); say what should move outside the boundary.",
        "Retries without an idempotency key are a retry storm risk -- describe "
        "the duplicate side effect, not just the loop.",
    ),
)


PERSONAS: dict[str, Persona] = {
    p.key: p
    for p in (_SIMPLICITY, _ABSTRACTION, _MAINTAINABILITY, _PERFORMANCE, _CONCURRENCY)
}


def get_persona(key: str) -> Persona:
    """Look up a persona by key, or fail loudly."""
    try:
        return PERSONAS[key]
    except KeyError as exc:
        raise ConfigError(
            f"unknown reviewer persona '{key}'",
            known=sorted(PERSONAS),
        ) from exc


def personas_for(categories: Iterable[Category]) -> list[Persona]:
    """Personas relevant to the given categories, in a fixed deterministic order.

    Order follows ``PERSONAS`` declaration order so that two runs over the same
    input pick the same reviewer for the same slot (spec §41 Determinism).
    """
    wanted = set(categories)
    return [p for p in PERSONAS.values() if wanted & set(p.focus)]
