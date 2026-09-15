#!/usr/bin/env python3
"""Run the acceptance suite and produce the delivery report.

Spec §62 defines the execution order and §63/§64 the artefacts:

    reports/
      unit.json  integration.json  golden.json  adversarial.json
      false-positive.json  false-negative.json  real-repo.json
      multi-agent.json  cross-model.json  token-benchmark.json
      performance.json  fault-injection.json  final-score.json
      FINAL-ACCEPTANCE.md

**This script never invents a number.**  A dimension whose evidence artefact is
absent scores 0 and is reported as ``NOT_MEASURED``.  A suite that fails scores 0.
The point of the report is to be readable by someone who wants to argue with it.

Usage::

    python scripts/acceptance.py                  # run everything, write reports/
    python scripts/acceptance.py --skip-tests     # only re-score existing artefacts
    python scripts/acceptance.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
REPORTS = ROOT / "reports"

sys.path.insert(0, str(SRC))

# --------------------------------------------------------------------------
# the 100-point model of spec §60
# --------------------------------------------------------------------------


@dataclass
class Dimension:
    name: str
    weight: int
    artefact: str
    #: (metric_key, threshold, direction) -- direction is "min" or "max"
    criteria: list[tuple[str, float, str]] = field(default_factory=list)


DIMENSIONS: list[Dimension] = [
    Dimension("Correctness / Gate", 15, "gate.json",
              [("matrix_cases_passed", 1.0, "min")]),
    Dimension("Dead Code Precision", 10, "false-positive.json",
              [("high_false_positive_rate", 0.03, "max")]),
    Dimension("High-risk Recall", 10, "false-negative.json",
              [("high_critical_recall", 0.95, "min")]),
    Dimension("Duplication / Abstraction", 10, "golden.json",
              [("dup_abstraction_precision", 1.0, "min")]),
    Dimension("Deterministic Evidence", 10, "determinism.json",
              [("identical_runs", 1.0, "min")]),
    Dimension("Multi-Agent Isolation", 8, "multi-agent.json",
              [("isolation_proven", 1.0, "min")]),
    Dimension("False Positive Control", 8, "false-positive.json",
              [("medium_plus_false_positive_rate", 0.08, "max")]),
    Dimension("Failure Degradation", 7, "fault-injection.json",
              [("no_pass_on_tool_failure", 1.0, "min")]),
    Dimension("Token Efficiency", 7, "token-benchmark.json",
              [("token_ratio_vs_full_repo", 0.50, "max")]),
    Dimension("Performance", 5, "performance.json",
              [("diff_review_warm_p95_ms", 15000.0, "max")]),
    Dimension("Repair Verification", 5, "repair.json",
              [("rerun_closes_findings", 1.0, "min")]),
    Dimension("Docs / Operability", 5, "docs.json",
              [("required_docs_present", 1.0, "min")]),
]

#: Spec §61 -- any failure here fails acceptance no matter the total.
HARD_INDICATORS = [
    "HIGH/CRITICAL recall >= 95%",
    "HIGH+ false positive <= 3%",
    "no auto-delete of code with dynamic entry points",
    "no silent PASS on tool failure",
    "reviewer cannot manufacture an evidence-free HIGH",
    "repair always re-runs the gate",
    "context isolation actually in effect",
    "token usage clearly below whole-repo review",
    "same commit produces a stable gate",
    "no secret reaches the LLM context",
]


# --------------------------------------------------------------------------
# running the suites
# --------------------------------------------------------------------------


def run_unittest(suite: str) -> dict[str, Any]:
    """Run ``unittest discover`` on one directory and return real counts."""
    target = ROOT / "test" / suite
    if not target.is_dir():
        return {
            "suite": suite,
            "status": "MISSING",
            "total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
            "duration_ms": 0,
            "command": None,
            "output_tail": "",
        }

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONIOENCODING"] = "utf-8"
    argv = [sys.executable, "-m", "unittest", "discover", "-s", str(target), "-v", "-t", str(ROOT)]

    started = time.perf_counter()
    proc = subprocess.run(
        argv, cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=3600,
    )
    duration = int((time.perf_counter() - started) * 1000)
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")

    ran = re.search(r"Ran (\d+) tests? in", output)
    total = int(ran.group(1)) if ran else 0
    skipped = len(re.findall(r"\.\.\. skipped", output)) + len(re.findall(r"skipped '", output))
    failures = len(re.findall(r"^FAIL: ", output, re.M))
    errors = len(re.findall(r"^ERROR: ", output, re.M))

    return {
        "suite": suite,
        "status": "OK" if proc.returncode == 0 else "FAILED",
        "total": total,
        "passed": max(0, total - failures - errors),
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "duration_ms": duration,
        "command": " ".join(argv),
        "exit_code": proc.returncode,
        "output_tail": "\n".join(output.strip().splitlines()[-40:]),
    }


# --------------------------------------------------------------------------
# artefact loading
# --------------------------------------------------------------------------


def load_artefact(name: str) -> Optional[dict[str, Any]]:
    p = REPORTS / name
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else {"value": data}


def metric_value(artefact: Optional[dict[str, Any]], key: str) -> Optional[float]:
    if not artefact:
        return None
    if key in artefact:
        try:
            return float(artefact[key])
        except (TypeError, ValueError):
            return None
    nested = artefact.get("metrics")
    if isinstance(nested, dict) and key in nested:
        try:
            return float(nested[key])
        except (TypeError, ValueError):
            return None
    return None


def score_dimension(dim: Dimension) -> dict[str, Any]:
    artefact = load_artefact(dim.artefact)
    if artefact is None:
        return {
            "dimension": dim.name,
            "weight": dim.weight,
            "score": 0.0,
            "status": "NOT_MEASURED",
            "artefact": dim.artefact,
            "criteria": [],
            "reason": f"evidence artefact reports/{dim.artefact} is absent",
        }

    criteria: list[dict[str, Any]] = []
    earned = 0.0
    per = dim.weight / max(1, len(dim.criteria))
    for key, threshold, direction in dim.criteria:
        value = metric_value(artefact, key)
        if value is None:
            criteria.append({
                "metric": key, "threshold": threshold, "direction": direction,
                "value": None, "met": False, "reason": "metric missing from artefact",
            })
            continue
        met = value >= threshold if direction == "min" else value <= threshold
        if met:
            earned += per
        criteria.append({
            "metric": key, "threshold": threshold, "direction": direction,
            "value": value, "met": met, "reason": "ok" if met else "threshold missed",
        })

    return {
        "dimension": dim.name,
        "weight": dim.weight,
        "score": round(earned, 2),
        "status": "MEASURED",
        "artefact": dim.artefact,
        "criteria": criteria,
        "reason": "",
    }


# --------------------------------------------------------------------------
# environment + docs
# --------------------------------------------------------------------------


def probe_toolchain() -> list[dict[str, Any]]:
    try:
        from chm.adapters.probe import probe_all
        from chm.config import load_config

        cfg = load_config(None, repo_root=ROOT)
        return [p.to_dict() for p in probe_all(None, cfg)]
    except Exception as exc:  # pragma: no cover - report the failure honestly
        return [{"error": f"{type(exc).__name__}: {exc}"}]


REQUIRED_DOCS = [
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "SKILL.md",
    ".codehealth.example.yml",
    "docs/architecture.md",
    "docs/finding-schema.md",
    "docs/risk-model.md",
    "docs/rule-authoring.md",
    "docs/adr/ADR-001-language-and-dependencies.md",
    "docs/adr/ADR-002-reference-project-usage.md",
    "docs/adr/ADR-003-toolchain-availability-and-degradation.md",
]


def docs_report() -> dict[str, Any]:
    missing = [d for d in REQUIRED_DOCS if not (ROOT / d).is_file()]
    return {
        "required": REQUIRED_DOCS,
        "missing": missing,
        "required_docs_present": 1.0 if not missing else 0.0,
        "present_count": len(REQUIRED_DOCS) - len(missing),
        "total": len(REQUIRED_DOCS),
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-tests", action="store_true", help="do not run the suites")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    REPORTS.mkdir(parents=True, exist_ok=True)

    suites: dict[str, Any] = {}
    if not args.skip_tests:
        for suite in ("unit", "integration", "golden", "adversarial", "benchmark"):
            result = run_unittest(suite)
            suites[suite] = result
            (REPORTS / f"{suite}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    # docs + toolchain are always measurable
    docs = docs_report()
    (REPORTS / "docs.json").write_text(
        json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tools = probe_toolchain()
    (REPORTS / "toolchain.json").write_text(
        json.dumps({"tools": tools}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dimensions = [score_dimension(d) for d in DIMENSIONS]
    total = round(sum(d["score"] for d in dimensions), 2)

    measured = [d for d in dimensions if d["status"] == "MEASURED"]
    not_measured = [d for d in dimensions if d["status"] != "MEASURED"]

    # A hard indicator is "verified" only when we have a real measurement that
    # supports it.  Anything else stays unverified rather than assumed good.
    hard = []
    fp = load_artefact("false-positive.json") or {}
    fn = load_artefact("false-negative.json") or {}
    fault = load_artefact("fault-injection.json") or {}
    iso = load_artefact("multi-agent.json") or {}
    token = load_artefact("token-benchmark.json") or {}
    det = load_artefact("determinism.json") or {}

    checks = [
        ("HIGH/CRITICAL recall >= 95%",
         fn.get("high_critical_recall"), lambda v: v is not None and float(v) >= 0.95),
        ("HIGH+ false positive <= 3%",
         fp.get("high_false_positive_rate"), lambda v: v is not None and float(v) <= 0.03),
        ("no silent PASS on tool failure",
         fault.get("no_pass_on_tool_failure"), lambda v: v is not None and float(v) >= 1.0),
        ("context isolation actually in effect",
         iso.get("isolation_proven"), lambda v: v is not None and float(v) >= 1.0),
        ("token usage clearly below whole-repo review",
         token.get("token_ratio_vs_full_repo"), lambda v: v is not None and float(v) <= 0.50),
        ("same commit produces a stable gate",
         det.get("identical_runs"), lambda v: v is not None and float(v) >= 1.0),
    ]
    for label, value, predicate in checks:
        if value is None:
            hard.append({"indicator": label, "status": "UNVERIFIED", "value": None})
        else:
            ok = predicate(value)
            hard.append({
                "indicator": label,
                "status": "PASS" if ok else "FAIL",
                "value": value,
            })

    # indicators with no measurement hook at all are listed, not assumed
    covered = {c["indicator"] for c in hard}
    for label in HARD_INDICATORS:
        if label not in covered:
            hard.append({"indicator": label, "status": "UNVERIFIED", "value": None})

    unverified = [h for h in hard if h["status"] == "UNVERIFIED"]
    failed = [h for h in hard if h["status"] == "FAIL"]
    any_suite_failed = any(s.get("status") == "FAILED" for s in suites.values())

    if failed:
        readiness = "NOT_READY"
    elif unverified or any_suite_failed:
        readiness = "TRIAL_ONLY"
    elif total >= 99:
        readiness = "ULTIMATE"
    elif total >= 95:
        readiness = "MAIN_PIPELINE"
    elif total >= 90:
        readiness = "TRIAL_ONLY"
    else:
        readiness = "NOT_READY"

    final = {
        "generated_by": "scripts/acceptance.py",
        "score_model": "spec §60 (100 points)",
        "total": total,
        "max_total": 100,
        "measured_dimensions": len(measured),
        "not_measured_dimensions": [d["dimension"] for d in not_measured],
        "dimensions": dimensions,
        "hard_indicators": hard,
        "suites": {k: {kk: vv for kk, vv in v.items() if kk != "output_tail"}
                   for k, v in suites.items()},
        "readiness": readiness,
        "interpretation": {
            "NOT_READY": "a hard indicator failed or a suite failed",
            "TRIAL_ONLY": "no hard failure, but some evidence is missing or the score is < 95",
            "MAIN_PIPELINE": "score >= 95 with every hard indicator verified",
            "ULTIMATE": "score >= 99 with every hard indicator verified",
        }[readiness],
    }
    (REPORTS / "final-score.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = render_final_acceptance(final, suites, docs, tools)
    (REPORTS / "FINAL-ACCEPTANCE.md").write_text(md, encoding="utf-8")

    if args.json:
        print(json.dumps(final, ensure_ascii=False, indent=2))
    else:
        print(md)

    # Exit non-zero when a suite failed, so CI cannot treat this as green.
    return 1 if any_suite_failed or failed else 0


def render_final_acceptance(
    final: dict[str, Any],
    suites: dict[str, Any],
    docs: dict[str, Any],
    tools: list[dict[str, Any]],
) -> str:
    L: list[str] = []
    L.append("# FINAL-ACCEPTANCE")
    L.append("")
    L.append("> Generated by `scripts/acceptance.py`. Every number below comes from a real run.")
    L.append("> A dimension whose evidence artefact is missing scores **0** and is reported as")
    L.append("> `NOT_MEASURED` — absence of evidence is never treated as evidence of quality.")
    L.append("")

    L.append("## Verdict")
    L.append("")
    L.append(f"- **Total score**: {final['total']} / 100")
    L.append(f"- **Readiness**: `{final['readiness']}` — {final['interpretation']}")
    L.append(f"- **Measured dimensions**: {final['measured_dimensions']} / {len(final['dimensions'])}")
    if final["not_measured_dimensions"]:
        L.append(f"- **Not measured**: {', '.join(final['not_measured_dimensions'])}")
    L.append("")

    L.append("## Environment")
    L.append("")
    L.append(f"- Python: `{sys.version.split()[0]}` (`{sys.executable}`)")
    L.append(f"- Platform: `{sys.platform}`")
    L.append("")
    L.append("| tool | available | version | path / reason |")
    L.append("|---|---|---|---|")
    for t in tools:
        if "error" in t:
            L.append(f"| — | — | — | {t['error']} |")
            continue
        # When a tool is unavailable the *reason* is the useful information;
        # showing only the path would hide the actual problem.
        if t.get("available"):
            note = t.get("path") or ""
        else:
            note = t.get("reason") or t.get("path") or ""
        note = str(note).replace("|", "\\|")
        L.append(
            f"| `{t.get('name')}` | {t.get('available')} | {t.get('version') or '-'} | {note} |"
        )
    L.append("")

    L.append("## Test suites")
    L.append("")
    if not suites:
        L.append("_Suites were not run (`--skip-tests`)._")
    else:
        L.append("| suite | status | total | passed | failed | errors | skipped | duration |")
        L.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for name, s in suites.items():
            L.append(
                f"| `{name}` | {s['status']} | {s['total']} | {s['passed']} | "
                f"{s['failed']} | {s['errors']} | {s['skipped']} | {s['duration_ms']} ms |"
            )
    L.append("")

    L.append("## Dimensions (spec §60)")
    L.append("")
    L.append("| dimension | weight | score | status | evidence |")
    L.append("|---|---:|---:|---|---|")
    for d in final["dimensions"]:
        L.append(
            f"| {d['dimension']} | {d['weight']} | {d['score']} | {d['status']} | "
            f"`reports/{d['artefact']}` |"
        )
    L.append("")

    L.append("### Criterion detail")
    L.append("")
    L.append("| dimension | metric | threshold | direction | actual | met |")
    L.append("|---|---|---|---|---:|---|")
    for d in final["dimensions"]:
        for c in d["criteria"]:
            actual = "—" if c["value"] is None else c["value"]
            L.append(
                f"| {d['dimension']} | `{c['metric']}` | {c['threshold']} | "
                f"{c['direction']} | {actual} | {'yes' if c['met'] else 'NO'} |"
            )
    L.append("")

    L.append("## Hard indicators (spec §61)")
    L.append("")
    L.append("Any `FAIL` fails acceptance regardless of the total score.")
    L.append("")
    L.append("| indicator | status | value |")
    L.append("|---|---|---:|")
    for h in final["hard_indicators"]:
        value = "—" if h["value"] is None else h["value"]
        L.append(f"| {h['indicator']} | {h['status']} | {value} |")
    L.append("")

    L.append("## Documentation")
    L.append("")
    L.append(f"- Present: {docs['present_count']} / {docs['total']}")
    if docs["missing"]:
        L.append(f"- **Missing**: {', '.join(docs['missing'])}")
    L.append("")

    L.append("## How to reproduce")
    L.append("")
    L.append("```bash")
    L.append("cd skills/ai-codeHealthMind")
    L.append("python scripts/acceptance.py")
    L.append("python codehealth.py probe")
    L.append("python codehealth.py review --repo")
    L.append("```")
    L.append("")
    L.append("## Known limitations")
    L.append("")
    L.append("- Semgrep and OpenRewrite are unavailable on Windows; their adapters report")
    L.append("  `UNAVAILABLE` with the real reason and the gate records a tool gap.")
    L.append("- SpotBugs needs compiled classes; without a compile step it reports")
    L.append("  `UNSUPPORTED` instead of pretending to have scanned.")
    L.append("- The `rule` reviewer backend is deterministic local heuristics, labelled as")
    L.append("  such in every report. Cross-model review requires `review.backend: llm`.")
    L.append("- Built-in analyzers use lightweight parsing, not a real AST; this is a")
    L.append("  recall limitation, reported honestly by the golden suite.")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
