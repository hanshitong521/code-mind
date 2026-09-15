"""Shared harness for the CodeHealthMind acceptance tests.

Only the Python standard library is used.  The harness runs the *real*
``Orchestrator`` in ``ReviewMode.REPO`` over a fixture directory and returns the
findings it produced -- nothing is mocked, nothing is stubbed and no finding is
fabricated.

Design notes
------------
* External CLI tools (PMD/CPD/SpotBugs/Semgrep/Knip) are disabled by default so
  a golden run measures the *built-in deterministic analyzers* only.  That is
  deliberate: the golden fixtures declare expectations about ``CHM-JAVA-NAT-*``
  / ``CHM-VUE-NAT-*`` rule ids.  When a fixture's ``.codehealth.yml`` asks for
  external tools they are enabled and their real availability is reported.
* ``review.backend = "off"`` keeps the semantic reviewer (and therefore any
  network/LLM dependency) out of the deterministic golden comparison.
* ``baseline.enabled = False`` stops the run from writing
  ``.codehealth-baseline.json`` into a fixture directory.
* Run artefacts always go to the system temp directory and are removed again.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# -- make ``chm`` importable no matter how unittest was invoked -------------
_HERE = Path(__file__).resolve()
_SKILL_ROOT = _HERE.parents[2]  # test/golden/_chm.py -> skill root
_SRC = _SKILL_ROOT / "src"
import sys

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from chm.config import Config, parse_config  # noqa: E402
from chm.contracts import ReviewMode  # noqa: E402
from chm.core.orchestrator import Orchestrator  # noqa: E402
from chm.schema import Severity  # noqa: E402

FIXTURES = _SKILL_ROOT / "test" / "fixtures"
ADVERSARIAL = _SKILL_ROOT / "test" / "adversarial"


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


def golden_config(extra: Optional[dict] = None) -> Config:
    """A config that isolates the built-in analyzers.

    External tools off, semantic reviewer off, baseline off.  A fixture may
    override anything by shipping its own ``.codehealth.yml`` (see
    :func:`load_fixture_config`).
    """
    data = {
        "version": 1,
        "mode": "repo",
        "tools": {
            "pmd": False,
            "cpd": False,
            "spotbugs": False,
            "semgrep": False,
            "knip": False,
            "openrewrite": False,
            "compile": False,
            "test": False,
            "native": True,
        },
        "review": {"backend": "off", "validator_on_high": True, "validator_on_critical": True},
        "baseline": {"enabled": False},
        "run_dir": ".codehealth/runs",
    }
    if extra:
        _deep_merge(data, extra)
    return parse_config(data)


def load_fixture_config(fixture_dir: Path, extra: Optional[dict] = None) -> Config:
    """Load a fixture's ``.codehealth.yml`` on top of the golden defaults.

    The fixture file wins for every key it declares, so a fixture can opt back
    into real external tools (and the harness will then report the real
    availability instead of hiding it).
    """
    cfg_file = Path(fixture_dir) / ".codehealth.yml"
    base = {
        "version": 1,
        "mode": "repo",
        "tools": {
            "pmd": False,
            "cpd": False,
            "spotbugs": False,
            "semgrep": False,
            "knip": False,
            "openrewrite": False,
            "compile": False,
            "test": False,
            "native": True,
        },
        "review": {"backend": "off"},
        "baseline": {"enabled": False},
    }
    if cfg_file.is_file():
        from chm.config import load_yaml

        loaded = load_yaml(cfg_file.read_text(encoding="utf-8")) or {}
        _deep_merge(base, loaded)
    if extra:
        _deep_merge(base, extra)
    return parse_config(base, source_path=str(cfg_file) if cfg_file.is_file() else None)


def _deep_merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


# --------------------------------------------------------------------------
# findings view
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class F:
    """A flat, comparable view of one ``Finding``."""

    rule_id: str
    file: str
    line: int
    severity: str
    category: str
    status: str = ""
    title: str = ""
    auto_fixable: bool = False
    symbol: str = ""

    @property
    def medplus(self) -> bool:
        return self.severity in ("MEDIUM", "HIGH", "CRITICAL")

    @property
    def highplus(self) -> bool:
        return self.severity in ("HIGH", "CRITICAL")

    def __str__(self) -> str:  # pragma: no cover - debug aid
        return f"{self.severity:<8} {self.rule_id:<38} {self.file}:{self.line} [{self.status}]"


def to_flat(findings: Iterable) -> list[F]:
    out: list[F] = []
    for f in findings:
        out.append(
            F(
                rule_id=f.rule_id,
                file=f.location.file.replace("\\", "/"),
                line=int(f.location.start_line),
                severity=f.severity.value,
                category=f.category.value,
                status=f.decision.status.value,
                title=f.title,
                auto_fixable=bool(f.repair.auto_fixable),
                symbol=f.location.symbol or "",
            )
        )
    return out


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------


@dataclass
class Run:
    findings: list[F]
    report: dict
    tool_results: list
    run_dir: Path
    raw_findings: list[F] = field(default_factory=list)

    def by_rule(self, rule_id: str) -> list[F]:
        return [f for f in self.findings if f.rule_id == rule_id]

    def rules(self) -> set[str]:
        return {f.rule_id for f in self.findings}

    def raw_rules(self) -> set[str]:
        """Rule ids the deterministic providers emitted *before* dedup/validation.

        A rule can legitimately disappear from ``findings`` because the
        deduplicator folded it into a neighbouring finding of the same category
        (see ``KNOWN_GAPS``); the raw set proves the rule actually fired.
        """
        return {f.rule_id for f in self.raw_findings}

    def medplus(self) -> list[F]:
        return [f for f in self.findings if f.medplus]

    def highplus(self) -> list[F]:
        return [f for f in self.findings if f.highplus]

    def on_file(self, suffix: str) -> list[F]:
        return [f for f in self.findings if f.file.endswith(suffix)]


def is_inside_git_repo(path: Path) -> bool:
    """True when ``git rev-parse --show-toplevel`` resolves from ``path``."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def run_repo(
    repo_root: Path | str,
    *,
    config: Optional[Config] = None,
    options: Optional[dict] = None,
    requirement_context: str = "",
    keep_run_dir: bool = False,
    isolate: bool = True,
    allow_fix: bool = False,
) -> Run:
    """Run the real orchestrator over ``repo_root`` in REPO mode.

    ``isolate=True`` (the default) copies the tree into a fresh system-temp
    directory first.  This matters: the fixtures live *inside* the
    CodeHealthMind git repository, so ``probe_repo`` would otherwise resolve
    ``--show-toplevel`` to the enclosing project and scan the whole skill repo
    instead of the fixture.  The temp copy has no git history, which is exactly
    the ``mode=repo`` semantics the fixtures are written for (every source file
    is treated as changed, ``hunks`` is empty).
    """
    repo_root = Path(repo_root).resolve()
    cfg = config or golden_config()
    tmp = Path(tempfile.mkdtemp(prefix="chm-run-"))
    try:
        if isolate:
            scan_root = tmp / "repo"
            shutil.copytree(repo_root, scan_root)
            if is_inside_git_repo(scan_root):  # pragma: no cover - env guard
                raise RuntimeError(
                    f"system temp dir {tmp} is inside a git repository; "
                    "fixtures cannot be isolated, results would be meaningless"
                )
        else:
            scan_root = repo_root
        raw_findings = _raw_provider_findings(scan_root, cfg)
        orch = Orchestrator(
            repo_root=scan_root,
            config=cfg,
            mode=ReviewMode.REPO,
            options=dict(options or {}),
            requirement_context=requirement_context,
            run_dir=tmp / "run",
        )
        result = orch.run(allow_fix=allow_fix)
        run = Run(
            findings=to_flat(result.findings),
            report=result.report,
            tool_results=list(result.tool_results),
            run_dir=result.run_dir,
            raw_findings=raw_findings,
        )
    finally:
        if not keep_run_dir:
            shutil.rmtree(tmp, ignore_errors=True)
    return run


def _raw_provider_findings(scan_root: Path, cfg: Config) -> list[F]:
    """Run the built-in analyzers directly and flatten what they emitted.

    This is the same code path the orchestrator uses (same ``ScanContext``
    resolution, same providers), but captured *before* dedup and evidence
    validation so a test can tell "the rule never fired" apart from "the rule
    fired and a later stage folded it away".
    """
    from chm.analyzers.registry import native_analyzers
    from chm.context.gitctx import resolve_context

    try:
        ctx = resolve_context(scan_root, mode=ReviewMode.REPO, config=cfg)
    except Exception:  # pragma: no cover - defensive
        return []
    out: list[F] = []
    for provider in native_analyzers():
        try:
            if not provider.supports(ctx):
                continue
            result = provider.scan(ctx)
        except Exception:  # pragma: no cover - defensive
            continue
        for rf in result.findings:
            out.append(
                F(
                    rule_id=rf.rule_id,
                    file=str(rf.file).replace("\\", "/"),
                    line=int(rf.start_line),
                    severity=(rf.severity or Severity.MEDIUM).value,
                    category=rf.category.value if rf.category else "",
                    status="RAW",
                    title=rf.message,
                )
            )
    return out


def run_source(
    source: str,
    *,
    filename: str = "src/main/java/demo/Sample.java",
    config: Optional[Config] = None,
    extra_files: Optional[dict[str, str]] = None,
    options: Optional[dict] = None,
) -> Run:
    """Materialise one inline source string into a temp repo and scan it.

    Used by the adversarial suites so a case is a few lines of Java/Vue next to
    its assertion instead of a whole fixture directory.
    """
    tmp = Path(tempfile.mkdtemp(prefix="chm-src-"))
    try:
        if is_inside_git_repo(tmp):  # pragma: no cover - env guard
            raise RuntimeError(
                f"system temp dir {tmp} is inside a git repository; inline cases "
                "cannot be isolated"
            )
        target = tmp / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
        for rel, text in (extra_files or {}).items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return run_repo(tmp, config=config, options=options, isolate=False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# assertions
# --------------------------------------------------------------------------


def assert_no_medplus(test: unittest.TestCase, run: Run, label: str) -> None:
    bad = run.medplus()
    if bad:
        detail = "\n".join("    " + str(f) for f in bad)
        test.fail(f"{label}: expected no MEDIUM+ finding, got {len(bad)}:\n{detail}")


def rules_in(fixture_dir: Path, extra: Optional[dict] = None) -> Run:
    return run_repo(fixture_dir, config=load_fixture_config(fixture_dir, extra))


def env_tool_paths() -> dict[str, str]:
    """Real tool locations used by the fixtures/benchmarks on this machine."""
    return {
        "CHM_PMD_HOME": os.environ.get("CHM_PMD_HOME", ""),
        "CHM_SPOTBUGS_HOME": os.environ.get("CHM_SPOTBUGS_HOME", ""),
        "CHM_JAVA_HOME": os.environ.get("CHM_JAVA_HOME", ""),
    }


__all__ = [
    "F",
    "Run",
    "FIXTURES",
    "ADVERSARIAL",
    "Severity",
    "golden_config",
    "load_fixture_config",
    "run_repo",
    "run_source",
    "to_flat",
    "assert_no_medplus",
    "rules_in",
    "env_tool_paths",
]
