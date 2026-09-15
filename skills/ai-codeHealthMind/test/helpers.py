"""Shared, dependency-free helpers for the CodeHealthMind test suite.

Deliberately **not** a pytest conftest: everything here is plain stdlib and is
imported by ``unittest`` modules through ``test/helpers.py``.  ``conftest.py``
re-exports the same surface for callers that expect that name.

Design rules this module obeys:

* no third-party imports (the engine itself is stdlib-only, ADR-001);
* every temporary artefact lives under the OS temp directory and is removed by
  ``CHMTestCase`` via ``addCleanup``;
* nothing here ever writes into the project tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# --------------------------------------------------------------------------
# make the engine importable without an install step
# --------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SRC_DIR = PROJECT_ROOT / "src"
ENTRY_SCRIPT = PROJECT_ROOT / "codehealth.py"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chm.config import Config  # noqa: E402
from chm.contracts import ChangeKind, ChangedFile, Hunk, ReviewMode, ScanContext  # noqa: E402
from chm.schema import (  # noqa: E402
    Category,
    Decision,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingStatus,
    Location,
    Repair,
    RepairClass,
    Severity,
)

# --------------------------------------------------------------------------
# temp-directory bookkeeping
# --------------------------------------------------------------------------

_TEMP_DIRS: list[Path] = []


def temp_dir(prefix: str = "chm-test-") -> Path:
    """Create a real temporary directory and register it for cleanup."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    _TEMP_DIRS.append(path)
    return path


def cleanup_temp_dirs() -> int:
    """Remove every directory created by :func:`temp_dir`; returns the count."""
    removed = 0
    while _TEMP_DIRS:
        path = _TEMP_DIRS.pop()
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


# --------------------------------------------------------------------------
# toolchain discovery (real paths on this host)
# --------------------------------------------------------------------------


def _toolchain_root() -> Path | None:
    """Locate ``.tools/codehealth`` by walking up from the project root."""
    env = os.environ.get("CHM_TOOLCHAIN_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    for base in (PROJECT_ROOT, *PROJECT_ROOT.parents):
        cand = base / ".tools" / "codehealth"
        if cand.is_dir():
            return cand
    return None


TOOLCHAIN_ROOT = _toolchain_root()


def repo_root() -> Path:
    """Absolute path of the CodeHealthMind project root."""
    return PROJECT_ROOT


def toolchain_available(name: str) -> tuple[bool, str]:
    """Return ``(available, detail)`` for a real tool on this host.

    ``detail`` is the resolved path or the honest reason it is missing -- the
    tests print it rather than pretending.
    """
    root = TOOLCHAIN_ROOT
    if name in ("pmd", "cpd"):
        home = os.environ.get("CHM_PMD_HOME")
        if home and Path(home, "lib").is_dir():
            return True, home
        if root is not None:
            hits = sorted(p for p in root.glob("pmd-bin-*") if (p / "lib").is_dir())
            if hits:
                return True, str(hits[-1])
        return False, "no pmd-bin-* distribution with a lib/ directory found"
    if name == "spotbugs":
        home = os.environ.get("CHM_SPOTBUGS_HOME")
        if home and Path(home, "lib", "spotbugs.jar").is_file():
            return True, home
        if root is not None:
            hits = sorted(p for p in root.glob("spotbugs-*") if (p / "lib" / "spotbugs.jar").is_file())
            if hits:
                return True, str(hits[-1])
        return False, "no spotbugs-* distribution with lib/spotbugs.jar found"
    if name == "knip":
        home = os.environ.get("CHM_KNIP_HOME")
        if home and Path(home, "node_modules", "knip", "bin", "knip.js").is_file():
            return True, home
        if root is not None and (root / "knip" / "node_modules" / "knip" / "bin" / "knip.js").is_file():
            return True, str(root / "knip")
        return False, "knip/bin/knip.js not found"
    if name == "javac":
        env = os.environ.get("CHM_JAVAC_BIN")
        if env and Path(env).is_file():
            return True, env
        found = shutil.which("javac")
        if found:
            return True, found
        home = os.environ.get("CHM_JAVA_HOME") or os.environ.get("JAVA_HOME")
        if home:
            for exe in ("javac.exe", "javac"):
                cand = Path(home) / "bin" / exe
                if cand.is_file():
                    return True, str(cand)
        return False, "no javac found (set CHM_JAVAC_BIN / JAVA_HOME)"
    if name == "node":
        env = os.environ.get("CHM_NODE_BIN")
        if env and Path(env).is_file():
            return True, env
        found = shutil.which("node")
        return (True, found) if found else (False, "no node on PATH")
    if name == "semgrep":
        env = os.environ.get("CHM_SEMGREP_BIN")
        if env and Path(env).is_file():
            return True, env
        found = shutil.which("semgrep")
        return (True, found) if found else (False, "semgrep is not installed on this host")
    if name in ("openrewrite", "mvn"):
        env = os.environ.get("CHM_MVN_BIN")
        if env and Path(env).is_file():
            return True, env
        found = shutil.which("mvn")
        return (True, found) if found else (False, "no Maven executable found on PATH")
    if name == "git":
        found = shutil.which("git")
        return (True, found) if found else (False, "no git on PATH")
    return False, f"unknown tool '{name}'"


# --------------------------------------------------------------------------
# git fixtures
# --------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def git_init(repo: Path) -> None:
    """``git init`` with a deterministic identity and no global config leaks."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "tests@codehealthmind.invalid")
    _git(repo, "config", "user.name", "CodeHealthMind Tests")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")


def write_files(repo: Path, files: dict[str, str]) -> None:
    """Write ``{relative_path: content}`` into ``repo`` (real bytes, utf-8)."""
    for rel, content in files.items():
        target = Path(repo) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")


def write_bytes(repo: Path, rel: str, payload: bytes) -> None:
    target = Path(repo) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def commit_all(repo: Path, message: str = "c") -> str:
    """Stage everything and commit; returns the real commit sha."""
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message, "--allow-empty")
    res = _git(repo, "rev-parse", "HEAD")
    return res.stdout.strip()


def make_temp_repo(files: dict[str, str], *, commit: bool = True) -> Path:
    """Create a real git repository under the OS temp dir.

    ``commit=True`` stages and commits every file so that ``--diff`` and
    ``--staged`` modes have a real HEAD to compare against.
    """
    repo = temp_dir("chm-repo-")
    git_init(repo)
    if files:
        write_files(repo, files)
    if commit:
        commit_all(repo, "initial")
    return repo


def stage_all(repo: Path) -> None:
    _git(repo, "add", "-A")


# --------------------------------------------------------------------------
# CLI invocation (real subprocess)
# --------------------------------------------------------------------------


def cli_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a real ``codehealth`` subprocess.

    Tool locations are pinned explicitly so a test never depends on ambient
    state -- and so a deliberately-broken path can be injected.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(SRC_DIR)
    env.setdefault("CHM_TOOLCHAIN_ROOT", str(TOOLCHAIN_ROOT) if TOOLCHAIN_ROOT else "")
    if TOOLCHAIN_ROOT is not None:
        pmd = sorted(p for p in TOOLCHAIN_ROOT.glob("pmd-bin-*") if (p / "lib").is_dir())
        if pmd:
            env.setdefault("CHM_PMD_HOME", str(pmd[-1]))
        sb = sorted(p for p in TOOLCHAIN_ROOT.glob("spotbugs-*") if (p / "lib").is_dir())
        if sb:
            env.setdefault("CHM_SPOTBUGS_HOME", str(sb[-1]))
        knip = TOOLCHAIN_ROOT / "knip"
        if (knip / "node_modules" / "knip" / "bin" / "knip.js").is_file():
            env.setdefault("CHM_KNIP_HOME", str(knip))
    for key in ("CHM_JAVA_HOME",):
        if key not in env:
            jdk = Path("E:/jdk")
            if (jdk / "bin" / "javac.exe").is_file():
                env[key] = str(jdk)
                env.setdefault("JAVA_HOME", str(jdk))
    if extra:
        env.update(extra)
    return env


def run_cli(
    args: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout_s: float = 300.0
) -> tuple[int, str, str]:
    """Run the real CLI in a subprocess; returns ``(exit_code, stdout, stderr)``."""
    proc = subprocess.run(
        [sys.executable, str(ENTRY_SCRIPT), *args],
        cwd=str(cwd),
        env=cli_env(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_python(
    code: str, *, cwd: Path, env: dict[str, str] | None = None, timeout_s: float = 300.0
) -> tuple[int, str, str]:
    """Run a snippet with ``src`` on ``sys.path``; returns ``(code, out, err)``."""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(cwd),
        env=cli_env(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------
# config / finding fixtures
# --------------------------------------------------------------------------


def make_config(**overrides) -> Config:
    """Build a :class:`Config` with dotted-key overrides.

    Example::

        make_config(**{"gates.max_new_medium": 2, "dead_code.allow_auto_delete": True})
    """
    cfg = Config()
    for dotted, value in overrides.items():
        target = cfg
        parts = dotted.split(".")
        for part in parts[:-1]:
            if not hasattr(target, part):
                raise AttributeError(f"config has no section '{part}' (from '{dotted}')")
            target = getattr(target, part)
        leaf = parts[-1]
        if not hasattr(target, leaf):
            raise AttributeError(f"config has no key '{dotted}'")
        setattr(target, leaf, value)
    return cfg


def make_ctx(
    repo_root_path: Path,
    *,
    changed: list[ChangedFile] | None = None,
    config: Config | None = None,
    mode: ReviewMode = ReviewMode.DIFF,
    options: dict | None = None,
) -> ScanContext:
    """A ``ScanContext`` wired to a real directory and a real config."""
    return ScanContext(
        repo_root=Path(repo_root_path),
        mode=mode,
        changed_files=list(changed or []),
        config=config if config is not None else Config(),
        options=dict(options or {}),
    )


def changed_file(
    path: str,
    *,
    kind: ChangeKind = ChangeKind.MODIFIED,
    old_path: str | None = None,
    hunks: list[Hunk] | None = None,
    added_lines: int = 0,
    removed_lines: int = 0,
    is_binary: bool = False,
) -> ChangedFile:
    """A ``ChangedFile`` with sensible defaults."""
    from chm.contracts import language_of

    return ChangedFile(
        path=path,
        change_kind=kind,
        old_path=old_path,
        language=language_of(path),
        added_lines=added_lines,
        removed_lines=removed_lines,
        is_binary=is_binary,
        hunks=list(hunks or []),
    )


def hunk(new_start: int, new_count: int, *, old_start: int = 1, old_count: int = 0) -> Hunk:
    return Hunk(
        old_start=old_start,
        old_count=old_count,
        new_start=new_start,
        new_count=new_count,
        lines=["+x"] * new_count,
    )


def make_finding(
    finding_id: str = "CHM-000001",
    *,
    rule_id: str = "CHM-JAVA-DEAD-001",
    category: Category = Category.DEAD_CODE,
    title: str = "unused private method",
    severity: Severity = Severity.MEDIUM,
    confidence: float = 0.8,
    file: str = "src/main/java/A.java",
    start_line: int = 10,
    end_line: int | None = None,
    symbol: str | None = None,
    introduced: bool = False,
    evidence: list[EvidenceItem] | None = None,
    status: FindingStatus = FindingStatus.DETECTED,
    repair: Repair | None = None,
    historical: bool = False,
    score_weight: float = 1.0,
    sources: list[str] | None = None,
) -> Finding:
    """Construct a schema-legal :class:`Finding`."""
    return Finding(
        id=finding_id,
        rule_id=rule_id,
        category=category,
        title=title,
        severity=severity,
        confidence=confidence,
        location=Location(
            file=file,
            start_line=start_line,
            end_line=end_line if end_line is not None else start_line,
            symbol=symbol,
        ),
        introduced_by_current_diff=introduced,
        evidence=list(evidence or []),
        decision=Decision(status=status),
        repair=repair if repair is not None else Repair(),
        historical=historical,
        score_weight=score_weight,
        sources=list(sources or []),
    )


def evidence(provider: str, *, kind: EvidenceKind = EvidenceKind.DETERMINISTIC, detail: str | None = None) -> EvidenceItem:
    return EvidenceItem(
        provider=provider,
        result="hit",
        kind=kind,
        rule_id="CHM-JAVA-DEAD-001",
        detail=detail or f"{provider} reported a hit",
    )


def sample_findings() -> list[Finding]:
    """A mixed fixture: 4 severities, several categories, with/without evidence.

    Also mixes ``introduced_by_current_diff`` so baseline / gate logic has both
    kinds of debt to classify.
    """
    return [
        make_finding(
            "CHM-000001",
            rule_id="CHM-JAVA-TX-NO-WHERE",
            category=Category.DATABASE,
            title="UPDATE without WHERE clause",
            severity=Severity.CRITICAL,
            confidence=0.95,
            file="src/main/java/db/UserRepo.java",
            start_line=42,
            symbol="updateAll",
            introduced=True,
            evidence=[evidence("native-java"), evidence("pmd")],
        ),
        make_finding(
            "CHM-000002",
            rule_id="CHM-JAVA-RESOURCE-LEAK",
            category=Category.RESOURCE_SAFETY,
            title="stream is never closed",
            severity=Severity.HIGH,
            confidence=0.9,
            file="src/main/java/io/Reader.java",
            start_line=18,
            symbol="read",
            introduced=True,
            evidence=[evidence("spotbugs", detail="OS_OPEN_STREAM")],
        ),
        make_finding(
            "CHM-000003",
            rule_id="CHM-JAVA-COMPLEXITY-001",
            category=Category.COMPLEXITY,
            title="method cyclomatic complexity is 24",
            severity=Severity.MEDIUM,
            confidence=0.7,
            file="src/main/java/svc/Order.java",
            start_line=77,
            symbol="settle",
            introduced=True,
            evidence=[],
        ),
        make_finding(
            "CHM-000004",
            rule_id="CHM-JAVA-DUP-001",
            category=Category.DUPLICATION,
            title="42 duplicated tokens",
            severity=Severity.LOW,
            confidence=0.5,
            file="src/main/java/svc/Copy.java",
            start_line=5,
            introduced=False,
            evidence=[evidence("cpd")],
            historical=True,
        ),
        make_finding(
            "CHM-000005",
            rule_id="CHM-JAVA-UNUSED-IMPORT",
            category=Category.DEAD_CODE,
            title="unused import java.util.List",
            severity=Severity.LOW,
            confidence=0.99,
            file="src/main/java/svc/Order.java",
            start_line=3,
            introduced=True,
            evidence=[evidence("native-java")],
        ),
    ]


# --------------------------------------------------------------------------
# unittest base class
# --------------------------------------------------------------------------


class CHMTestCase(unittest.TestCase):
    """``TestCase`` that cleans up every temp directory it created."""

    def temp_dir(self, prefix: str = "chm-test-") -> Path:
        path = temp_dir(prefix)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def temp_repo(self, files: dict[str, str], *, commit: bool = True) -> Path:
        repo = make_temp_repo(files, commit=commit)
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)
        return repo


def tearDownModule() -> None:  # pragma: no cover - safety net
    cleanup_temp_dirs()


__all__ = [
    "PROJECT_ROOT",
    "SRC_DIR",
    "ENTRY_SCRIPT",
    "TOOLCHAIN_ROOT",
    "CHMTestCase",
    "changed_file",
    "cli_env",
    "cleanup_temp_dirs",
    "commit_all",
    "evidence",
    "git_init",
    "hunk",
    "make_config",
    "make_ctx",
    "make_finding",
    "make_temp_repo",
    "repo_root",
    "run_cli",
    "run_python",
    "sample_findings",
    "stage_all",
    "temp_dir",
    "toolchain_available",
    "write_bytes",
    "write_files",
]
