"""CodeHealthMind error taxonomy.

Design rule (spec §29 / §35.12): **every** failure is classified, surfaced and
recorded.  A missing or broken tool must never collapse into a silent PASS.
The only two honest outcomes when evidence is incomplete are:

* ``TOOL_DEGRADED`` -- other providers still produced enough evidence; and
* ``UNKNOWN``      -- a HIGH/CRITICAL conclusion depended on the missing tool.

Nothing in this package is allowed to ``except: pass``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ToolFailureKind(str, Enum):
    """How an evidence provider failed.

    The names are stable strings because they are serialised into reports and
    asserted by tests.
    """

    MISSING = "MISSING"                      # binary/jar not found on this host
    DISABLED = "DISABLED"                    # switched off in .codehealth.yml
    UNSUPPORTED = "UNSUPPORTED"              # tool exists but cannot handle input
    TIMEOUT = "TIMEOUT"                      # exceeded configured deadline
    NONZERO_EXIT = "NONZERO_EXIT"            # ran, exited non-zero
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"    # ran, output not parseable
    PARTIAL_OUTPUT = "PARTIAL_OUTPUT"        # parsed some, truncated some
    CRASHED = "CRASHED"                      # interpreter/OS level failure
    CONFIG = "CONFIG"                        # bad adapter configuration


class ToolStatus(str, Enum):
    """Provider-level health, independent of findings."""

    OK = "OK"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class CHMError(Exception):
    """Base class for every CodeHealthMind failure."""

    code = "CHM_ERROR"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


class ConfigError(CHMError):
    code = "CHM_CONFIG_ERROR"


class SchemaError(CHMError):
    """A Finding violated the published schema (spec §4 CHM-SCHEMA-*)."""

    code = "CHM_SCHEMA_ERROR"


class ContextError(CHMError):
    code = "CHM_CONTEXT_ERROR"


class GitError(ContextError):
    code = "CHM_GIT_ERROR"


class GateError(CHMError):
    code = "CHM_GATE_ERROR"


@dataclass
class ToolError:
    """Structured, serialisable record of a provider failure.

    Deliberately a dataclass rather than an exception: adapters *return* tool
    errors so the orchestrator can keep running the remaining providers
    (spec §28 "工具失败不能让整个系统崩").
    """

    provider: str
    kind: ToolFailureKind
    detail: str
    command: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    stderr_excerpt: Optional[str] = None

    #: True when the failure means we could not gather evidence that a
    #: HIGH/CRITICAL verdict would depend on.  Drives UNKNOWN vs DEGRADED.
    evidence_gap: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "kind": self.kind.value,
            "detail": self.detail,
            "command": self.command,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stderr_excerpt": self.stderr_excerpt,
            "evidence_gap": self.evidence_gap,
        }

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"[{self.provider}:{self.kind.value}] {self.detail}"


@dataclass
class ErrorLedger:
    """Accumulates tool errors for a single run."""

    errors: list[ToolError] = field(default_factory=list)

    def add(self, err: ToolError) -> None:
        self.errors.append(err)

    def extend(self, errs: list[ToolError]) -> None:
        self.errors.extend(errs)

    def of(self, provider: str) -> list[ToolError]:
        return [e for e in self.errors if e.provider == provider]

    @property
    def has_evidence_gap(self) -> bool:
        return any(e.evidence_gap for e in self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.errors),
            "has_evidence_gap": self.has_evidence_gap,
            "errors": [e.to_dict() for e in self.errors],
        }
