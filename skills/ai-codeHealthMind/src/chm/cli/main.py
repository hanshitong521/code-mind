"""``codehealth`` command line interface.

Exit codes are part of the public contract (spec §49)::

    0  PASS / WARN
    1  BLOCK
    2  tool or configuration error
    3  UNKNOWN (evidence incomplete for a HIGH/CRITICAL verdict)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from .. import __version__
from ..config import DEFAULT_CONFIG_TEMPLATE, Config, ConfigError, load_config
from ..contracts import ReviewMode
from ..errors import CHMError, ToolFailureKind, ToolStatus
from ..schema import EXIT_CODES, EXIT_TOOL_ERROR, GateVerdict
from ..util import ensure_dir, read_json, write_json

EXIT_OK = 0
EXIT_BLOCK = 1
EXIT_ERROR = EXIT_TOOL_ERROR
EXIT_UNKNOWN = 3


# --------------------------------------------------------------------------
# shared plumbing
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codehealth",
        description="CodeHealthMind -- code health audit and merge gate for AI-written code.",
    )
    parser.add_argument("--version", action="version", version=f"CodeHealthMind {__version__}")
    sub = parser.add_subparsers(dest="command")

    def add_target_flags(p: argparse.ArgumentParser) -> None:
        g = p.add_mutually_exclusive_group()
        g.add_argument("--diff", action="store_true", help="review the working tree against HEAD")
        g.add_argument("--staged", action="store_true", help="review the staged change set")
        g.add_argument("--commit", metavar="SHA", help="review a single commit")
        g.add_argument("--range", metavar="A..B", help="review a commit range")
        g.add_argument("--file", metavar="PATH", help="review one file")
        g.add_argument("--repo", action="store_true", help="review the whole repository")
        p.add_argument("--repo-root", metavar="DIR", help="repository root (default: cwd)")
        p.add_argument("--config", metavar="FILE", help="path to .codehealth.yml")
        p.add_argument("--requirement", metavar="FILE", help="requirement/design excerpt")
        p.add_argument("--test-evidence", metavar="FILE", help="test evidence text")
        p.add_argument("--no-parallel", action="store_true", help="run providers sequentially")
        p.add_argument("--backend", choices=("off", "rule", "llm"), help="reviewer backend")
        p.add_argument("--max-medium", type=int, metavar="N", help="override gates.max_new_medium")

    review = sub.add_parser("review", help="run the gate over a change set")
    add_target_flags(review)
    review.add_argument(
        "--format",
        choices=("console", "json", "markdown", "sarif"),
        default="console",
    )
    review.add_argument("-o", "--output", metavar="FILE", help="write the report to a file")
    review.add_argument("--verbose", action="store_true")
    review.add_argument("--quiet", action="store_true", help="suppress console output")

    fix = sub.add_parser("fix", help="plan (and optionally apply) safe repairs")
    add_target_flags(fix)
    fix.add_argument("--apply", action="store_true", help="actually apply SAFE_AUTO_FIX repairs")
    fix.add_argument("--format", choices=("console", "json"), default="console")

    verify = sub.add_parser("verify", help="re-run the gate and diff against a previous run")
    add_target_flags(verify)
    verify.add_argument("--previous", metavar="RUN_ID", help="previous run id (default: latest)")
    verify.add_argument("--previous-report", metavar="FILE", help="explicit report.json path")
    verify.add_argument("--format", choices=("console", "json"), default="console")

    explain = sub.add_parser("explain", help="explain a single finding")
    explain.add_argument("finding_id", help="e.g. CHM-000123")
    explain.add_argument("--run", metavar="RUN_ID", help="run id (default: latest)")
    explain.add_argument("--repo-root", metavar="DIR")
    explain.add_argument("--config", metavar="FILE")
    explain.add_argument("--format", choices=("console", "json"), default="console")

    baseline = sub.add_parser("baseline", help="inspect or refresh the baseline")
    baseline.add_argument("--show", action="store_true")
    baseline.add_argument("--update", action="store_true")
    baseline.add_argument("--repo-root", metavar="DIR")
    baseline.add_argument("--config", metavar="FILE")

    probe = sub.add_parser("probe", help="report real tool availability and versions")
    probe.add_argument("--repo-root", metavar="DIR")
    probe.add_argument("--config", metavar="FILE")
    probe.add_argument("--format", choices=("console", "json"), default="console")

    init = sub.add_parser("init", help="write a starter .codehealth.yml")
    init.add_argument("--repo-root", metavar="DIR")
    init.add_argument("--force", action="store_true")

    return parser


def _resolve_mode(args: argparse.Namespace) -> tuple[ReviewMode, dict[str, Any]]:
    extra: dict[str, Any] = {}
    if getattr(args, "staged", False):
        return ReviewMode.STAGED, extra
    if getattr(args, "commit", None):
        return ReviewMode.COMMIT, {"commit": args.commit}
    if getattr(args, "range", None):
        rng = args.range
        if ".." not in rng:
            raise ConfigError(f"--range expects A..B, got '{rng}'")
        a, b = rng.split("..", 1)
        return ReviewMode.RANGE, {"base_ref": a or "HEAD~1", "head_ref": b or "HEAD"}
    if getattr(args, "file", None):
        return ReviewMode.FILE, {"file_arg": args.file}
    if getattr(args, "repo", False):
        return ReviewMode.REPO, {"options": {"whole_file": True, "pmd_scope": "repo"}}
    return ReviewMode.DIFF, extra


def _load(args: argparse.Namespace) -> tuple[Path, Config]:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd()).resolve()
    config_path = getattr(args, "config", None)
    cfg = load_config(config_path, repo_root=repo_root)
    if getattr(args, "backend", None):
        cfg.review.backend = args.backend
    if getattr(args, "max_medium", None) is not None:
        cfg.gates.max_new_medium = int(args.max_medium)
    return repo_root, cfg


def _read_optional(path: Optional[str]) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"file not found: {path}")
    from ..context.secretfilter import scrub

    return scrub(p.read_text(encoding="utf-8")).text


def _make_orchestrator(args: argparse.Namespace):
    from ..core.orchestrator import Orchestrator

    repo_root, cfg = _load(args)
    mode, extra = _resolve_mode(args)
    options = dict(extra.pop("options", {}))
    if getattr(args, "no_parallel", False):
        options["parallel"] = False
    return Orchestrator(
        repo_root=repo_root,
        config=cfg,
        mode=mode,
        options=options,
        requirement_context=_read_optional(getattr(args, "requirement", None)),
        test_evidence=_read_optional(getattr(args, "test_evidence", None)),
        **extra,
    )


def _emit(text: str, output: Optional[str]) -> None:
    if output:
        p = Path(output)
        ensure_dir(p.parent if str(p.parent) else Path("."))
        p.write_text(text, encoding="utf-8")
        print(f"report written to {p}")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _render(report: dict, fmt: str, *, verbose: bool = False) -> str:
    if fmt == "json":
        from ..reports.json_report import render_json

        return render_json(report)
    if fmt == "markdown":
        from ..reports.markdown import render_markdown

        return render_markdown(report)
    if fmt == "sarif":
        from ..reports.sarif import render_sarif

        return json.dumps(render_sarif(report), ensure_ascii=False, indent=2)
    from ..reports.console import render_console

    return render_console(report, verbose=verbose)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_review(args: argparse.Namespace) -> int:
    orch = _make_orchestrator(args)
    result = orch.run()
    text = _render(result.report, args.format, verbose=args.verbose)
    if not args.quiet:
        _emit(text, args.output)
    elif args.output:
        _emit(text, args.output)
    return result.exit_code


def cmd_fix(args: argparse.Namespace) -> int:
    orch = _make_orchestrator(args)
    result = orch.run(allow_fix=True)
    # build_report flattens the orchestrator's `extra` payload onto the report
    # root, so repair_plan lives at the top level.
    plan = result.report.get("repair_plan") or (result.report.get("extra") or {}).get(
        "repair_plan", []
    )

    if args.format == "json":
        _emit(json.dumps({"repair_plan": plan, "applied": []}, ensure_ascii=False, indent=2), None)
        return result.exit_code

    lines = [f"CodeHealthMind {__version__}", "", f"Gate: {result.gate}", ""]
    auto = [p for p in plan if p["auto_fixable"]]
    manual = [p for p in plan if not p["auto_fixable"]]
    lines.append(f"Repair plan: {len(plan)} finding(s)")
    lines.append(f"  SAFE_AUTO_FIX: {len(auto)}")
    lines.append(f"  needs author / manual: {len(manual)}")
    lines.append("")
    for item in plan:
        lines.append(
            f"{item['finding_id']} {item['repair_class']:16s} {item['file']}:{item['line']}"
        )
        lines.append(f"    preferred: {item['recommendation']['preferred']}")
        lines.append(f"    fallback : {item['recommendation']['fallback']}")
        lines.append(f"    validate : {', '.join(item['validation_required']) or 'n/a'}")

    applied: list[str] = []
    if args.apply:
        if not auto:
            lines.append("")
            lines.append("Nothing is provably safe to auto-fix; refusing to touch the tree.")
        else:
            from ..core.repair import apply_safe_fixes

            applied, refused = apply_safe_fixes(orch.repo_root, result.findings, orch.config)
            lines.append("")
            lines.append(f"Applied {len(applied)} safe fix(es); refused {len(refused)}.")
            for line in applied:
                lines.append(f"  applied: {line}")
            for line in refused:
                lines.append(f"  refused: {line}")
            lines.append("")
            lines.append("Re-run `codehealth verify` to prove the repair (spec §34).")
    _emit("\n".join(lines), None)
    return result.exit_code


def cmd_verify(args: argparse.Namespace) -> int:
    from ..core.orchestrator import rerun_gate

    repo_root, cfg = _load(args)
    previous_report = None
    if getattr(args, "previous_report", None):
        previous_report = read_json(args.previous_report)
    if previous_report is None:
        run_dir = _find_run_dir(repo_root, cfg, getattr(args, "previous", None))
        previous_report = read_json(run_dir / "report.json") if run_dir else None
    if previous_report is None:
        raise ConfigError(
            "no previous run found; run `codehealth review` first or pass --previous-report"
        )

    mode, extra = _resolve_mode(args)
    result = rerun_gate(
        repo_root=repo_root,
        config=cfg,
        previous_report=previous_report,
        mode=mode,
        **extra,
    )
    if args.format == "json":
        payload = {k: v for k, v in result.items() if k != "report"}
        payload["summary"] = result["report"]["summary"]
        _emit(json.dumps(payload, ensure_ascii=False, indent=2), None)
        return int(result["exit_code"])

    lines = [
        f"CodeHealthMind {__version__}",
        "",
        f"Re-run: {result['run_id']}",
        f"Gate  : {result['gate']}",
        f"Closed findings    : {len(result['closed'])}",
        f"New findings       : {len(result['appeared'])}",
        f"New HIGH/CRITICAL  : {len(result['new_high_or_critical'])}",
        f"Regression         : {'YES' if result['regression'] else 'no'}",
    ]
    if result["closed"]:
        lines.append("  closed: " + ", ".join(result["closed"]))
    if result["appeared"]:
        lines.append("  new   : " + ", ".join(result["appeared"]))
    _emit("\n".join(lines), None)
    return int(result["exit_code"])


def cmd_explain(args: argparse.Namespace) -> int:
    repo_root, cfg = _load(args)
    run_dir = _find_run_dir(repo_root, cfg, getattr(args, "run", None))
    if run_dir is None:
        raise ConfigError("no run directory found; run `codehealth review` first")
    report = read_json(run_dir / "report.json")
    if report is None:
        raise ConfigError(f"report.json missing in {run_dir}")
    target = args.finding_id.upper()
    finding = next((f for f in report.get("findings", []) if f["id"] == target), None)
    if finding is None:
        # A missing id is usually a finding that deduplication merged into a
        # survivor.  Say so and point at the survivor instead of just "not found".
        for group in (report.get("dedup", {}) or {}).get("groups", []):
            if target in (group.get("merged_ids") or []):
                kept = group.get("kept_id")
                print(
                    f"{target} was merged into {kept} as the same issue "
                    f"(dedup): {group.get('reason', '')}"
                )
                print(f"Run `codehealth explain {kept} --run {report['run']['run_id']}`.")
                return EXIT_OK
        print(f"{target} not found in run {report['run']['run_id']}")
        print(
            "Tip: ids come from the report; `codehealth review --format json` "
            "lists the current ones."
        )
        return EXIT_OK

    if args.format == "json":
        _emit(json.dumps(finding, ensure_ascii=False, indent=2), None)
        return EXIT_OK

    det = finding["evidence"]["deterministic"]
    sem = finding["evidence"]["semantic"]
    lines = [
        f"{finding['id']}  {finding['severity']}  {finding['category']}",
        f"{finding['title']}",
        "",
        f"rule       : {finding['rule_id']}",
        f"location   : {finding['location']['file']}:{finding['location']['start_line']}"
        f"-{finding['location']['end_line']}",
        f"symbol     : {finding['location'].get('symbol') or '-'}",
        f"confidence : {finding['confidence']}",
        f"introduced by this change : {finding['change_scope']['introduced_by_current_diff']}",
        f"historical : {finding.get('historical', False)}",
        f"status     : {finding['decision']['status']}"
        + (f" ({finding['decision']['reason']})" if finding["decision"].get("reason") else ""),
        "",
        f"deterministic evidence ({len(det)}):",
    ]
    for e in det:
        lines.append(f"  - {e['provider']}: {e.get('result')}  {e.get('detail') or ''}")
    lines.append(f"semantic evidence ({len(sem)}):")
    for e in sem:
        lines.append(f"  - {e['provider']}: {e.get('result')}  {e.get('detail') or ''}")
    unc = finding["uncertainty"]
    lines += [
        "",
        "dynamic-entry checks:",
        f"  reflection              : {unc['reflection_checked']}",
        f"  spring registration     : {unc['spring_registration_checked']}",
        f"  rpc registration        : {unc['rpc_registration_checked']}",
        f"  mq registration         : {unc['mq_registration_checked']}",
        f"  xml registration        : {unc['xml_registration_checked']}",
        f"  dynamic import          : {unc['dynamic_import_checked']}",
        "",
        f"recommendation : {finding['recommendation']['preferred']}",
        f"fallback       : {finding['recommendation']['fallback']}",
        f"repair class   : {finding['repair']['repair_class']}"
        f" (auto_fixable={finding['repair']['auto_fixable']})",
        f"validation     : {', '.join(finding['validation']['required']) or 'n/a'}",
        f"sources        : {', '.join(finding['sources'])}",
    ]
    if finding.get("perf_confidence"):
        lines.insert(8, f"perf class : {finding['perf_confidence']}")
    _emit("\n".join(lines), None)
    return EXIT_OK


def cmd_baseline(args: argparse.Namespace) -> int:
    from ..core.baseline import load_baseline

    repo_root, cfg = _load(args)
    path = repo_root / cfg.baseline.path
    if args.update:
        from ..core.baseline import collect_metrics, save_baseline

        report = _latest_report(repo_root, cfg)
        if report is None:
            raise ConfigError("no previous run found; run `codehealth review` first")
        from ..schema import Finding

        findings = [Finding.from_dict(d) for d in report.get("findings", [])]
        metrics = collect_metrics(findings, config=cfg)
        save_baseline(path, metrics)
        print(f"baseline updated: {path}")
        print(json.dumps(metrics.to_dict(), ensure_ascii=False, indent=2))
        return EXIT_OK

    metrics = load_baseline(path)
    if metrics is None:
        print(f"no baseline at {path}")
        return EXIT_OK
    print(json.dumps(metrics.to_dict(), ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_probe(args: argparse.Namespace) -> int:
    from ..adapters.probe import probe_all

    repo_root, cfg = _load(args)
    probes = probe_all(None, cfg)
    if args.format == "json":
        _emit(json.dumps([p.to_dict() for p in probes], ensure_ascii=False, indent=2), None)
        return EXIT_OK
    lines = [f"CodeHealthMind {__version__} -- toolchain probe", ""]
    lines.append(f"{'tool':14s} {'available':10s} {'version':12s} path / reason")
    for p in probes:
        lines.append(
            f"{p.name:14s} {str(p.available):10s} {str(p.version or '-'):12s} "
            f"{p.path or p.reason or ''}"
        )
    _emit("\n".join(lines), None)
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd()).resolve()
    target = repo_root / ".codehealth.yml"
    if target.exists() and not args.force:
        print(f"{target} already exists (use --force to overwrite)")
        return EXIT_OK
    target.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    print(f"wrote {target}")
    return EXIT_OK


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _runs_root(repo_root: Path, cfg: Config) -> Path:
    return repo_root / cfg.run_dir


def _latest_run_id(repo_root: Path, cfg: Config) -> Optional[str]:
    latest = read_json(_runs_root(repo_root, cfg) / "latest.json")
    if isinstance(latest, dict) and latest.get("run_id"):
        return str(latest["run_id"])
    return None


def _find_run_dir(repo_root: Path, cfg: Config, run_id: Optional[str]) -> Optional[Path]:
    runs = _runs_root(repo_root, cfg)
    if run_id:
        cand = runs / run_id
        return cand if cand.is_dir() else None
    rid = _latest_run_id(repo_root, cfg)
    if rid:
        cand = runs / rid
        if cand.is_dir():
            return cand
    if runs.is_dir():
        dirs = sorted((d for d in runs.iterdir() if d.is_dir()), reverse=True)
        if dirs:
            return dirs[0]
    return None


def _latest_report(repo_root: Path, cfg: Config) -> Optional[dict]:
    run_dir = _find_run_dir(repo_root, cfg, None)
    if run_dir is None:
        return None
    return read_json(run_dir / "report.json")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

_COMMANDS = {
    "review": cmd_review,
    "fix": cmd_fix,
    "verify": cmd_verify,
    "explain": cmd_explain,
    "baseline": cmd_baseline,
    "probe": cmd_probe,
    "init": cmd_init,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return EXIT_OK
    handler = _COMMANDS[args.command]
    try:
        return int(handler(args))
    except ConfigError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return EXIT_ERROR
    except CHMError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover
        sys.stderr.write("interrupted\n")
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
