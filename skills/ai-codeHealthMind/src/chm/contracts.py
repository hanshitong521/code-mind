"""Shared contracts between the orchestrator, context layer and providers.

Kept in one module so that adapters, analyzers and reviewers can all import
their interfaces without pulling in the engine (avoids import cycles).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .errors import ToolError, ToolStatus
from .schema import Category, EvidenceKind, RawFinding, Severity
from .util import Timer, file_hash


class ReviewMode(str, Enum):
    """Spec §7 -- the review targets the CLI must support."""

    DIFF = "diff"
    STAGED = "staged"
    COMMIT = "commit"
    RANGE = "range"
    FILE = "file"
    REPO = "repo"


class ChangeKind(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"
    COPIED = "COPIED"
    BINARY = "BINARY"
    UNKNOWN = "UNKNOWN"


class Language(str, Enum):
    # -- languages an evidence provider actually covers ----------------------
    JAVA = "java"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    VUE = "vue"
    # -- recognised but not yet covered --------------------------------------
    # These exist so the engine can *say* it does not cover them.  Reviewing a
    # Python-only change set and reporting PASS would be a false green, which
    # the specification forbids, so the orchestrator raises a coverage gap for
    # any change set made only of these.
    PYTHON = "python"
    KOTLIN = "kotlin"
    SCALA = "scala"
    GO = "go"
    RUST = "rust"
    CSHARP = "csharp"
    PHP = "php"
    RUBY = "ruby"
    CPP = "cpp"
    C = "c"
    SHELL = "shell"
    # -- non-source ----------------------------------------------------------
    JSON = "json"
    YAML = "yaml"
    XML = "xml"
    SQL = "sql"
    MARKDOWN = "markdown"
    OTHER = "other"


#: Languages with at least one real evidence provider behind them.
SUPPORTED_LANGUAGES: frozenset["Language"] = frozenset(
    {Language.JAVA, Language.JAVASCRIPT, Language.TYPESCRIPT, Language.VUE}
)

#: Languages that are source code (as opposed to config/prose/data).
SOURCE_LANGUAGES: frozenset["Language"] = frozenset(
    {
        Language.JAVA,
        Language.JAVASCRIPT,
        Language.TYPESCRIPT,
        Language.VUE,
        Language.PYTHON,
        Language.KOTLIN,
        Language.SCALA,
        Language.GO,
        Language.RUST,
        Language.CSHARP,
        Language.PHP,
        Language.RUBY,
        Language.CPP,
        Language.C,
        Language.SHELL,
    }
)


_EXT_LANG: dict[str, Language] = {
    ".java": Language.JAVA,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".vue": Language.VUE,
    ".py": Language.PYTHON,
    ".pyi": Language.PYTHON,
    ".kt": Language.KOTLIN,
    ".kts": Language.KOTLIN,
    ".scala": Language.SCALA,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".cs": Language.CSHARP,
    ".php": Language.PHP,
    ".rb": Language.RUBY,
    ".cc": Language.CPP,
    ".cpp": Language.CPP,
    ".cxx": Language.CPP,
    ".hpp": Language.CPP,
    ".h": Language.C,
    ".c": Language.C,
    ".sh": Language.SHELL,
    ".bash": Language.SHELL,
    ".zsh": Language.SHELL,
    ".json": Language.JSON,
    ".yml": Language.YAML,
    ".yaml": Language.YAML,
    ".xml": Language.XML,
    ".sql": Language.SQL,
    ".md": Language.MARKDOWN,
}


def language_of(path: str) -> Language:
    return _EXT_LANG.get(Path(path).suffix.lower(), Language.OTHER)


@dataclass
class ChangedFile:
    """One entry of the change set, already resolved against git."""

    path: str                      # repo-relative, posix separators
    change_kind: ChangeKind = ChangeKind.MODIFIED
    old_path: Optional[str] = None
    language: Language = Language.OTHER
    added_lines: int = 0
    removed_lines: int = 0
    is_binary: bool = False
    is_generated: bool = False
    size_bytes: int = 0
    content_hash: str = ""
    #: unified diff hunks for this file (new-file coordinates)
    hunks: list["Hunk"] = field(default_factory=list)

    @property
    def changed_line_numbers(self) -> set[int]:
        out: set[int] = set()
        for h in self.hunks:
            out.update(range(h.new_start, h.new_start + h.new_count))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_kind": self.change_kind.value,
            "old_path": self.old_path,
            "language": self.language.value,
            "added_lines": self.added_lines,
            "removed_lines": self.removed_lines,
            "is_binary": self.is_binary,
            "is_generated": self.is_generated,
            "size_bytes": self.size_bytes,
            "content_hash": self.content_hash,
            "hunks": [h.to_dict() for h in self.hunks],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ChangedFile":
        return cls(
            path=d["path"],
            change_kind=ChangeKind(d.get("change_kind", "MODIFIED")),
            old_path=d.get("old_path"),
            language=Language(d.get("language", "other")),
            added_lines=int(d.get("added_lines", 0)),
            removed_lines=int(d.get("removed_lines", 0)),
            is_binary=bool(d.get("is_binary")),
            is_generated=bool(d.get("is_generated")),
            size_bytes=int(d.get("size_bytes", 0)),
            content_hash=d.get("content_hash", ""),
            hunks=[Hunk.from_dict(h) for h in d.get("hunks", [])],
        )


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str = ""
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_start": self.old_start,
            "old_count": self.old_count,
            "new_start": self.new_start,
            "new_count": self.new_count,
            "header": self.header,
            "lines": list(self.lines),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Hunk":
        return cls(
            old_start=int(d["old_start"]),
            old_count=int(d["old_count"]),
            new_start=int(d["new_start"]),
            new_count=int(d["new_count"]),
            header=d.get("header", ""),
            lines=list(d.get("lines", [])),
        )


@dataclass
class ScanContext:
    """Everything a provider is allowed to know about the run.

    Providers receive *this* and nothing else.  In particular the semantic
    reviewer never sees the writer's rationale (spec §3.5 Context Isolation).
    """

    repo_root: Path
    mode: ReviewMode
    changed_files: list[ChangedFile] = field(default_factory=list)
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    commit: Optional[str] = None
    file_arg: Optional[str] = None

    #: repo-wide file index, populated lazily / on demand by the context layer
    repo_files: list[str] = field(default_factory=list)
    #: requirement / design excerpt, already secret-filtered
    requirement_context: str = ""
    #: test evidence text (POST-GATE), already secret-filtered
    test_evidence: str = ""
    #: config object (chm.config.Config) -- typed loosely to avoid a cycle
    config: Any = None
    #: cache directory for this run
    cache_dir: Optional[Path] = None
    #: extra provider options coming from CLI flags
    options: dict[str, Any] = field(default_factory=dict)

    def language_set(self) -> set[Language]:
        return {cf.language for cf in self.changed_files}

    def paths(self, *languages: Language) -> list[str]:
        wanted = set(languages) or None
        return [
            cf.path
            for cf in self.changed_files
            if not cf.is_binary and (wanted is None or cf.language in wanted)
        ]

    def changed_file(self, path: str) -> Optional[ChangedFile]:
        norm = path.replace("\\", "/").lstrip("./")
        for cf in self.changed_files:
            if cf.path == norm or cf.path.endswith("/" + norm):
                return cf
        return None

    def is_changed_line(self, path: str, line: int) -> bool:
        cf = self.changed_file(path)
        if cf is None:
            return False
        if not cf.hunks:
            return True
        return line in cf.changed_line_numbers

    def read(self, rel_path: str, *, max_bytes: int = 8 * 1024 * 1024) -> str:
        from .util import read_text

        return read_text(self.repo_root / rel_path, max_bytes=max_bytes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": str(self.repo_root),
            "mode": self.mode.value,
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "commit": self.commit,
            "file_arg": self.file_arg,
            "changed_files": [cf.to_dict() for cf in self.changed_files],
            "repo_file_count": len(self.repo_files),
        }


# --------------------------------------------------------------------------
# provider contract
# --------------------------------------------------------------------------


@dataclass
class ProviderResult:
    """What every evidence provider returns.  Never raises, never silent."""

    provider: str
    status: ToolStatus
    findings: list[RawFinding] = field(default_factory=list)
    error: Optional[ToolError] = None
    duration_ms: int = 0
    command: Optional[str] = None
    version: Optional[str] = None
    #: raw artefact written to the run directory (xml/sarif/json), if any
    artefact: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is ToolStatus.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "finding_count": len(self.findings),
            "duration_ms": self.duration_ms,
            "command": self.command,
            "version": self.version,
            "artefact": self.artefact,
            "error": self.error.to_dict() if self.error else None,
        }


class EvidenceProvider(ABC):
    """Spec §28 -- the single adapter interface.

    Implementations must:
      * call the real tool (never fabricate results);
      * never raise on tool failure -- return ``ProviderResult`` with a
        ``ToolError`` and ``status`` in {DEGRADED, UNAVAILABLE};
      * declare ``supports()`` truthfully so the orchestrator can skip them.
    """

    #: human name, also used as ``EvidenceItem.provider``
    name: str = "unnamed"
    #: categories this provider can contribute to
    categories: tuple[Category, ...] = ()
    #: evidence kind produced
    kind: EvidenceKind = EvidenceKind.DETERMINISTIC

    @abstractmethod
    def version(self) -> Optional[str]:
        """Real version string of the underlying tool, or None if unavailable."""

    @abstractmethod
    def available(self) -> tuple[bool, Optional[str]]:
        """(is_available, reason_if_not)."""

    @abstractmethod
    def supports(self, ctx: ScanContext) -> bool:
        """Cheap check: would this provider contribute anything for this ctx?"""

    @abstractmethod
    def scan(self, ctx: ScanContext) -> ProviderResult:
        """Run the real tool and translate its output into RawFindings."""

    # -- shared helpers ---------------------------------------------------

    def _unavailable(self, kind: str, detail: str, *, gap: bool = False) -> ProviderResult:
        from .errors import ToolFailureKind

        err = ToolError(
            provider=self.name,
            kind=ToolFailureKind(kind),
            detail=detail,
            evidence_gap=gap,
        )
        return ProviderResult(provider=self.name, status=ToolStatus.UNAVAILABLE, error=err)

    def timer(self) -> Timer:
        return Timer()


def severity_from_tool(text: str, default: Severity = Severity.MEDIUM) -> Severity:
    """Map a tool's own priority vocabulary onto our Severity."""
    t = (text or "").strip().lower()
    if t in ("1", "critical", "blocker", "error", "high", "h", "major"):
        return Severity.HIGH
    if t in ("2", "medium", "m", "warning", "warn", "minor"):
        return Severity.MEDIUM
    if t in ("3", "4", "5", "low", "l", "info", "information", "note", "advisory"):
        return Severity.LOW
    return default
