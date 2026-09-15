"""Secret filtering -- spec §37.

Every byte that reaches an LLM passes through :func:`scrub` first.  A false
positive costs a slightly noisier prompt; a false negative leaks a production
credential to a third-party model.  The filter therefore errs on the side of
redacting, while keeping enough shape (``[REDACTED:kind]`` markers, first two
characters of generic values) for a reviewer to understand what was removed.

Guarantees the rest of the engine relies on:

* stdlib only (``re`` + ``fnmatch``);
* :func:`scrub` is **idempotent** -- ``scrub(scrub(x).text).text == scrub(x).text``
  for every input;
* deterministic -- the same input always yields the same text and the same
  ordered redaction list.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "Redaction",
    "ScrubResult",
    "SECRET_PATTERNS",
    "SECRET_FILENAMES",
    "SECRET_FILE_ALLOWLIST",
    "PII_KINDS",
    "scrub",
    "is_secret_file",
    "redact_report",
]


# --------------------------------------------------------------------------
# result objects
# --------------------------------------------------------------------------


@dataclass
class Redaction:
    """How many times one class of secret was removed from a text."""

    kind: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "count": self.count}


@dataclass
class ScrubResult:
    text: str
    redactions: list[Redaction] = field(default_factory=list)
    had_secret: bool = False

    @property
    def total(self) -> int:
        return sum(r.count for r in self.redactions)

    def kinds(self) -> list[str]:
        return [r.kind for r in self.redactions]

    def to_dict(self) -> dict[str, Any]:
        """Never contains ``text`` -- this dict ends up in reports."""
        return {
            "had_secret": self.had_secret,
            "total_redactions": self.total,
            "redactions": [r.to_dict() for r in self.redactions],
            "text_chars": len(self.text),
        }


# --------------------------------------------------------------------------
# patterns
# --------------------------------------------------------------------------

#: ``(kind, regex)`` -- the published surface, used by tests and docs.
SECRET_PATTERNS: list[tuple[str, str]] = [
    (
        "private_key",
        r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY(?: BLOCK)?-----"
        r".*?"
        r"-----END(?: [A-Z0-9]+)* PRIVATE KEY(?: BLOCK)?-----",
    ),
    (
        "aws_access_key",
        r"\b(?:AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|AROA|ASCA)[0-9A-Z]{16}\b",
    ),
    (
        "aws_secret_key",
        r"(?i)\baws[_\-]?(?:secret[_\-]?)?(?:access[_\-]?)?key\b"
        r"[ \t]*[=:][ \t]*[\"']?(?P<val>[A-Za-z0-9/+=]{40})",
    ),
    (
        "jwt",
        r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\b",
    ),
    (
        "github_token",
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})\b",
    ),
    (
        "slack_token",
        r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b",
    ),
    (
        "bearer_token",
        r"(?i)\bbearer[ \t]+(?P<val>[A-Za-z0-9\-._~+/]{16,}=*)",
    ),
    (
        "db_password",
        r"(?i)\b(?:jdbc:)?[a-z][a-z0-9+.\-]*://[^\s:/@]+:(?P<pw>[^\s:/@]+)@",
    ),
    (
        "generic_secret",
        r"(?i)\b(?P<key>"
        r"pass(?:word|wd)?|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|"
        r"private[_-]?key|client[_-]?secret|auth[_-]?token|bearer"
        r")[A-Za-z0-9_]*\b[\"']?[ \t]*[:=][ \t]*[\"']?"
        r"(?!\[REDACTED)(?P<val>[^\s,;\"'<>(){}]{2,})",
    ),
    (
        "id_card_cn",
        r"(?<!\d)\d{17}[\dXx](?!\d)",
    ),
    (
        "phone_cn",
        r"(?<!\d)1[3-9]\d{9}(?!\d)",
    ),
]

#: Kinds that are personal data rather than credentials -- switchable off.
PII_KINDS: frozenset[str] = frozenset({"id_card_cn", "phone_cn"})

#: Filenames whose *content* is never safe to ship to a model.
SECRET_FILENAMES: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.jks",
    "*.keystore",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "credentials",
    "credentials.*",
    "secrets.*",
    "secret.*",
    "*.pfx",
    ".npmrc",
    ".netrc",
)

#: Documented exceptions to :data:`SECRET_FILENAMES` -- these hold no secrets.
SECRET_FILE_ALLOWLIST: tuple[str, ...] = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    ".env.defaults",
)

#: Values that look like code / env lookups rather than literals.  Without this
#: the generic rule would redact ``token = get_token()`` in every codebase.
_GENERIC_SKIP = re.compile(
    r"^(?:"
    r"(?:os|sys|self|this|config|settings|conf|env|process|System|Objects|Optional|"
    r"StringUtils|Assert|Preconditions|Properties|Props|map|getenv)[ \t]*[.\[]"
    r"|(?:null|None|nil|undefined|true|false|NaN)\b"
    r"|[*xX]{3,}"
    r"|\.\.\."
    r")"
)


def _mask_value(val: str, keep: int = 2, marker: str = "[REDACTED]") -> str:
    """Keep a short prefix so reviewers can tell values apart, hide the rest."""
    if len(val) <= keep:
        return marker
    return val[:keep] + marker


def _repl_marker(marker: str, group: str = "val") -> Callable[[re.Match], str]:
    """Replace one captured group in place, leaving surrounding syntax intact."""

    def _fn(m: re.Match) -> str:
        whole = m.group(0)
        val = m.group(group)
        idx = whole.rfind(val)
        if idx < 0:
            return whole
        return whole[:idx] + marker + whole[idx + len(val):]

    return _fn


def _repl_private_key(m: re.Match) -> str:
    whole = m.group(0)
    if "\n" not in whole:
        return "[REDACTED:private_key]"
    begin = whole.split("\n", 1)[0]
    end = whole.rsplit("\n", 1)[-1]
    return f"{begin}\n[REDACTED:private_key]\n{end}"


def _repl_generic(m: re.Match) -> str:
    whole = m.group(0)
    val = m.group("val")
    if _GENERIC_SKIP.search(val):
        return whole
    # ``ab[REDACTED]`` is already masked; ``arr[0]`` is code, not a secret.
    if "[" in val and not val.endswith("[REDACTED]"):
        return whole
    new = _mask_value(val)
    if new == val:
        return whole
    idx = whole.rfind(val)
    if idx < 0:
        return whole
    return whole[:idx] + new + whole[idx + len(val):]


def _repl_dburl(m: re.Match) -> str:
    whole = m.group(0)
    pw = m.group("pw")
    idx = whole.rfind(pw)
    if idx < 0:
        return whole
    return whole[:idx] + "[REDACTED:db_password]" + whole[idx + len(pw):]


#: ``(kind, compiled, replacement)`` -- applied strictly in this order.
_RULES: list[tuple[str, "re.Pattern[str]", Any]] = [
    ("private_key", re.compile(SECRET_PATTERNS[0][1], re.S), _repl_private_key),
    ("aws_access_key", re.compile(SECRET_PATTERNS[1][1]), "[REDACTED:aws_access_key]"),
    ("aws_secret_key", re.compile(SECRET_PATTERNS[2][1]), _repl_marker("[REDACTED:aws_secret_key]")),
    ("jwt", re.compile(SECRET_PATTERNS[3][1]), "[REDACTED:jwt]"),
    ("github_token", re.compile(SECRET_PATTERNS[4][1]), "[REDACTED:github_token]"),
    ("slack_token", re.compile(SECRET_PATTERNS[5][1]), "[REDACTED:slack_token]"),
    ("bearer_token", re.compile(SECRET_PATTERNS[6][1]), _repl_marker("[REDACTED:bearer_token]")),
    ("db_password", re.compile(SECRET_PATTERNS[7][1]), _repl_dburl),
    ("generic_secret", re.compile(SECRET_PATTERNS[8][1]), _repl_generic),
    ("id_card_cn", re.compile(SECRET_PATTERNS[9][1]), "[REDACTED:id_card_cn]"),
    ("phone_cn", re.compile(SECRET_PATTERNS[10][1]), "[REDACTED:phone_cn]"),
]


# --------------------------------------------------------------------------
# api
# --------------------------------------------------------------------------


def scrub(text: str, *, pii: bool = True) -> ScrubResult:
    """Remove credentials from ``text``; never raises, never silently no-ops.

    ``pii=False`` disables the Chinese phone / ID-card rules for callers that
    legitimately need those numbers (test fixtures, sample data).
    """
    if not text:
        return ScrubResult(text=text or "", redactions=[], had_secret=False)

    out = text
    counts: dict[str, int] = {}
    for kind, rx, repl in _RULES:
        if not pii and kind in PII_KINDS:
            continue
        hits = [0]

        def _wrapped(m: "re.Match", _repl=repl, _hits=hits) -> str:
            result = _repl(m) if callable(_repl) else _repl
            if result != m.group(0):
                _hits[0] += 1
            return result

        out = rx.sub(_wrapped, out)
        if hits[0]:
            counts[kind] = counts.get(kind, 0) + hits[0]

    redactions = [Redaction(kind=k, count=counts[k]) for k in sorted(counts)]
    return ScrubResult(text=out, redactions=redactions, had_secret=bool(redactions))


def is_secret_file(rel_path: str) -> bool:
    """True when a file's whole content must stay out of model context."""
    name = Path(str(rel_path).replace("\\", "/")).name
    if not name:
        return False
    lowered = name.lower()
    if any(fnmatch.fnmatch(lowered, pat.lower()) for pat in SECRET_FILE_ALLOWLIST):
        return False
    return any(fnmatch.fnmatch(lowered, pat.lower()) for pat in SECRET_FILENAMES)


def redact_report(obj: Any) -> Any:
    """Recursively scrub every string inside an arbitrary JSON-ish structure."""
    if isinstance(obj, str):
        return scrub(obj).text
    if isinstance(obj, dict):
        return {k: redact_report(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_report(v) for v in obj]
    return obj
