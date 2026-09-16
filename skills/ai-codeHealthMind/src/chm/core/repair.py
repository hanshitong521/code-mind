"""Safe, provable repairs only (spec §23 A: SAFE_AUTO_FIX).

Anything that requires judgement -- abstractions, duplicated business rules,
error-handling policy, concurrency, transactions -- is **never** touched here.
It is routed to the author or to OpenRewrite with an explicit recipe.

Every applied fix is reported as ``applied: <file>:<line> <rule_id>`` so the
report can prove what changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from ..config import Config
from ..schema import Finding, RepairClass

#: rule-id fragments that are provably mechanical
_APPLICABLE = (
    "UNUSED-IMPORT",
    "DEBUG-RESIDUE",
)

_UNUSED_IMPORT_RE = re.compile(r"^\s*import\s+(static\s+)?[\w.*]+\s*;\s*$")
_DEBUG_LINE_RE = re.compile(
    r"^\s*(System\.(out|err)\.print\w*|printStackTrace\s*\(\s*\)|console\.(log|debug|info))\b"
)


@dataclass
class FixOutcome:
    finding_id: str
    file: str
    line: int
    rule_id: str
    applied: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "file": self.file,
            "line": self.line,
            "rule_id": self.rule_id,
            "applied": self.applied,
            "reason": self.reason,
        }


def is_applicable(finding: Finding, config: Config) -> tuple[bool, str]:
    """Decide whether this finding may be edited mechanically."""
    if finding.repair.repair_class is not RepairClass.SAFE_AUTO_FIX:
        return False, f"repair_class is {finding.repair.repair_class.value}"
    if not finding.repair.auto_fixable:
        return False, "not marked auto_fixable"
    if not any(tok in finding.rule_id.upper() for tok in _APPLICABLE):
        return False, "rule is not in the provably-mechanical allowlist"
    if finding.category.value == "DEAD_CODE" and not config.dead_code.allow_auto_delete:
        return False, "dead_code.allow_auto_delete is false"
    if finding.uncertainty.notes and not finding.uncertainty.any_check:
        return False, "uncertain dynamic entry -- refusing to delete"
    return True, "safe"


def _line_matches(rule_id: str, text: str) -> bool:
    rule = rule_id.upper()
    if "UNUSED-IMPORT" in rule:
        return bool(_UNUSED_IMPORT_RE.match(text))
    if "DEBUG-RESIDUE" in rule:
        return bool(_DEBUG_LINE_RE.match(text))
    return False


def apply_safe_fixes(
    repo_root: Path,
    findings: Iterable[Finding],
    config: Config,
) -> tuple[list[str], list[str]]:
    """Apply the provably-mechanical subset in place.

    Returns ``(applied, refused)`` human-readable lines.  Line numbers are
    re-verified against the current file content before any edit, so a stale
    report can never delete the wrong line.
    """
    applied: list[str] = []
    refused: list[str] = []
    deferred_non_safe: list[str] = []

    # group by file, edit bottom-up so line numbers stay valid
    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        ok, reason = is_applicable(f, config)
        if not ok:
            line = f"{f.id} {f.location.file}:{f.location.start_line} -- {reason}"
            if f.repair.repair_class is RepairClass.SAFE_AUTO_FIX:
                refused.append(line)
            else:
                deferred_non_safe.append(line)
            continue
        by_file.setdefault(f.location.file, []).append(f)

    for rel_path, items in sorted(by_file.items()):
        target = Path(repo_root) / rel_path
        if not target.is_file():
            refused.append(f"{rel_path} -- file no longer exists")
            continue
        original = target.read_text(encoding="utf-8", errors="replace")
        newline = "\r\n" if "\r\n" in original else "\n"
        lines = original.replace("\r\n", "\n").split("\n")
        changed = False

        for f in sorted(items, key=lambda x: -x.location.start_line):
            idx = f.location.start_line - 1
            if idx < 0 or idx >= len(lines):
                refused.append(f"{f.id} {rel_path}:{f.location.start_line} -- line out of range")
                continue
            if not _line_matches(f.rule_id, lines[idx]):
                refused.append(
                    f"{f.id} {rel_path}:{f.location.start_line} -- content changed, refusing"
                )
                continue
            del lines[idx]
            changed = True
            applied.append(f"{rel_path}:{f.location.start_line} {f.rule_id}")

        if changed:
            target.write_text(newline.join(lines), encoding="utf-8")

    if not applied and deferred_non_safe:
        refused.extend(deferred_non_safe)

    return sorted(applied), sorted(refused)
