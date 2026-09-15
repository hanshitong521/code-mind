"""The CodeHealthMind orchestrator.

Implements the 12-step workflow of spec §25:

    1. Resolve target
    2. Load requirement context
    3. Collect diff
    4. Run deterministic analyzers
    5. Build minimal context
    6. Run semantic reviewer
    7. Normalize findings
    8. Validate high-risk findings
    9. Score
   10. Gate
   11. If fix requested -> route repair
   12. Re-run tests + gate

Nothing here fabricates evidence.  Provider failures are collected into an
``ErrorLedger`` and drive a real ``TOOL_DEGRADED`` / ``UNKNOWN`` outcome.
"""

from __future__ import annotations

import concurrent.futures as futures
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from ..config import Config
from ..contracts import (
    ChangeKind,
    EvidenceProvider,
    ProviderResult,
    ReviewMode,
    SOURCE_LANGUAGES,
    SUPPORTED_LANGUAGES,
    ScanContext,
)
from ..errors import ConfigError, ErrorLedger, ToolError, ToolFailureKind, ToolStatus
from ..schema import (
    Finding,
    GateVerdict,
    RawFinding,
    RepairClass,
    Severity,
    EXIT_CODES,
    EXIT_TOOL_ERROR,
)
from ..util import ensure_dir, read_json, run_cmd, stable_json, write_json

#: Fixed provider order -- reports must be byte-identical across runs.
PROVIDER_ORDER: tuple[str, ...] = (
    "native-java",
    "native-vue",
    "javac",
    "pmd",
    "cpd",
    "semgrep",
    "knip",
    "spotbugs",
    "openrewrite",
    "test-runner",
)

#: Providers that must run after ``javac`` (they need compiled classes).
_SECOND_WAVE = ("spotbugs", "test-runner", "openrewrite")


def _require(module: str, attr: str | None = None) -> Any:
    """Import an engine module, turning ImportError into a loud ConfigError."""
    import importlib

    try:
        mod = importlib.import_module(module)
    except ImportError as exc:  # pragma: no cover - broken install
        raise ConfigError(
            f"engine module '{module}' is missing; installation is incomplete",
            underlying=str(exc),
        ) from exc
    if attr is None:
        return mod
    try:
        return getattr(mod, attr)
    except AttributeError as exc:  # pragma: no cover
        raise ConfigError(f"'{module}' has no attribute '{attr}'") from exc


@dataclass
class RunResult:
    report: dict
    findings: list[Finding]
    ctx: ScanContext
    run_dir: Path
    tool_results: list[ProviderResult] = field(default_factory=list)
    tool_errors: list[ToolError] = field(default_factory=list)

    @property
    def gate(self) -> str:
        return self.report["summary"]["gate"]

    @property
    def exit_code(self) -> int:
        return int(self.report["summary"]["exit_code"])

    def to_dict(self) -> dict:
        return self.report


class Orchestrator:
    """Owns one review run end to end."""

    def __init__(
        self,
        *,
        repo_root: Path | str,
        config: Config,
        mode: ReviewMode | str = ReviewMode.DIFF,
        base_ref: Optional[str] = None,
        head_ref: Optional[str] = None,
        commit: Optional[str] = None,
        file_arg: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
        requirement_context: str = "",
        test_evidence: str = "",
        run_dir: Optional[Path] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config = config
        self.mode = ReviewMode(mode) if not isinstance(mode, ReviewMode) else mode
        self.base_ref = base_ref
        self.head_ref = head_ref
        self.commit = commit
        self.file_arg = file_arg
        self.options = dict(options or {})
        self.requirement_context = requirement_context
        self.test_evidence = test_evidence
        self._run_dir_override = run_dir

    # ------------------------------------------------------------------ run

    def run(self, *, allow_fix: bool = False) -> RunResult:
        started = time.perf_counter()
        ledger_mod = _require("chm.core.ledger")
        run_id = ledger_mod.new_run_id(self.repo_root, mode=self.mode.value, commit=self.commit)

        run_dir = self._run_dir_override or (
            self.repo_root / self.config.run_dir / run_id
        )
        ensure_dir(run_dir)
        cache_dir = ensure_dir(run_dir / "cache")

        # 1-3. resolve target -------------------------------------------------
        gitctx = _require("chm.context.gitctx")
        ctx = gitctx.resolve_context(
            self.repo_root,
            mode=self.mode,
            config=self.config,
            base_ref=self.base_ref,
            head_ref=self.head_ref,
            commit=self.commit,
            file_arg=self.file_arg,
            cache_dir=cache_dir,
        )
        ctx.options.update(self.options)
        ctx.requirement_context = self.requirement_context
        ctx.test_evidence = self.test_evidence
        ctx.config = self.config

        errors = ErrorLedger()
        self._check_language_coverage(ctx, errors)

        # symbol index (used by analyzers, validator and the context packer)
        index = None
        try:
            symbols = _require("chm.context.symbols")
            index = symbols.SymbolIndex(ctx, self.config).build()
            ctx.options["index"] = index
        except Exception as exc:  # pragma: no cover - defensive
            errors.add(
                ToolError(
                    provider="symbol-index",
                    kind=ToolFailureKind.CRASHED,
                    detail=f"symbol index unavailable: {type(exc).__name__}: {exc}",
                    evidence_gap=True,
                )
            )

        # 4. deterministic providers -----------------------------------------
        providers = self._build_providers()
        tool_results = self._run_providers(providers, ctx)
        for res in tool_results:
            if res.error:
                errors.add(res.error)

        raw: list[RawFinding] = []
        for res in tool_results:
            raw.extend(res.findings)

        # 5-6. semantic reviewer via the risk router --------------------------
        normalizer = _require("chm.core.normalizer")
        preliminary, norm_stats = normalizer.normalize_all(raw, config=self.config, ctx=ctx)

        router = _require("chm.core.riskrouter")
        plan = router.plan_route(preliminary, ctx, self.config)

        reviewer_calls: list[dict] = []
        if self.config.review.backend != "off":
            packer = _require("chm.context.packer")
            pack = packer.build_context_pack(
                ctx,
                preliminary,
                risk=plan.risk,
                config=self.config,
                index=index,
                include_writer_rationale=False,
            )
            write_json(run_dir / "context" / "pack.json", pack.to_dict())

            runtime_mod = _require("chm.reviewers.runtime")
            runtime = runtime_mod.ReviewerRuntime(self.config, ledger=None)
            personas_mod = _require("chm.reviewers.personas")

            relevant = personas_mod.personas_for({f.category for f in preliminary})
            if not relevant:
                relevant = [personas_mod.get_persona("simplicity")]

            # Each reviewer pass gets its own persona *and* its own model when
            # cross-model review is configured -- that is what makes the second
            # pass genuinely independent rather than a repeat of the first.
            for i in range(max(1, plan.reviewers)):
                persona = relevant[i % len(relevant)]
                model = plan.models[i] if i < len(plan.models) else plan.models[-1]
                out = runtime.review(persona, ctx, pack, model=model)
                reviewer_calls.append(out.call.to_dict())
                raw.extend(out.findings)
                if not out.call.ok and out.call.error:
                    errors.add(
                        ToolError(
                            provider=f"reviewer:{persona.key}",
                            kind=ToolFailureKind.CRASHED,
                            detail=out.call.error,
                            evidence_gap=False,
                        )
                    )
            ctx.options["reviewer_calls"] = reviewer_calls
            ctx.options["context_fingerprint"] = pack.fingerprint()

        # 7. normalise --------------------------------------------------------
        findings, norm_stats = normalizer.normalize_all(raw, config=self.config, ctx=ctx)

        # 8. validate high-risk findings --------------------------------------
        validator_mod = _require("chm.core.evidencevalidator")
        validator = validator_mod.EvidenceValidator(self.config, ctx, index=index)
        outcomes: list[dict] = []
        if self.config.review.validator_on_high:
            for outcome in validator.validate(findings):
                outcomes.append(outcome.to_dict())
        ctx.options["validation_outcomes"] = outcomes

        # 9-10. dedup, baseline, score, gate ----------------------------------
        dedup_mod = _require("chm.core.dedup")
        dedup = dedup_mod.deduplicate(findings, config=self.config)
        findings = dedup.findings

        baseline_mod = _require("chm.core.baseline")
        baseline_path = self.repo_root / self.config.baseline.path
        baseline = baseline_mod.load_baseline(baseline_path) if self.config.baseline.enabled else None
        new_findings, resolved, preexisting = baseline_mod.classify_against_baseline(
            findings, baseline
        )
        current_metrics = baseline_mod.collect_metrics(findings, config=self.config)
        delta = baseline_mod.compute_delta(baseline, current_metrics)

        score_mod = _require("chm.core.score")
        score = score_mod.score_findings(
            findings,
            config=self.config,
            tool_errors=list(errors.errors),
            compile_ok=ctx.options.get("compile_ok"),
            test_ok=ctx.options.get("test_ok"),
        )

        gate_mod = _require("chm.core.gate")
        gate = gate_mod.evaluate_gate(
            findings,
            score=score,
            config=self.config,
            tool_errors=list(errors.errors),
            compile_ok=ctx.options.get("compile_ok"),
            test_ok=ctx.options.get("test_ok"),
            new_findings=new_findings,
        )

        duration_ms = int((time.perf_counter() - started) * 1000)

        # 11. repair routing ---------------------------------------------------
        repair_plan = self._build_repair_plan(findings) if allow_fix else []

        # 12. report -----------------------------------------------------------
        ledger = ledger_mod.RunLedger(
            run_id=run_id,
            repo=str(self.repo_root),
            commit=ctx.commit or ctx.head_ref,
            base=ctx.base_ref,
            mode=self.mode.value,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            duration_ms=duration_ms,
            gate=gate.verdict.value,
        )
        for res in tool_results:
            ledger.add_tool(res.provider, res.duration_ms, res.status.value)
        totals = self._reviewer_tokens(reviewer_calls)
        ledger.add_llm(totals["calls"], totals["input"], totals["output"])
        ledger.errors = [e.to_dict() for e in errors.errors]
        ledger.cache_hit = self._cache_hit_ratio(ctx)
        ledger.findings = len(findings)
        ledger.dedup_ratio = dedup.dedup_ratio

        report_mod = _require("chm.reports.json_report")
        report = report_mod.build_report(
            run_id=run_id,
            mode=self.mode.value,
            ctx_dict=ctx.to_dict(),
            findings=findings,
            score=score,
            gate=gate,
            dedup=dedup,
            tool_results=tool_results,
            tool_errors=list(errors.errors),
            ledger=ledger,
            baseline_delta=delta,
            index_stats=index.stats() if index is not None else None,
            extra={
                "route_plan": plan.to_dict(),
                "reviewer_calls": reviewer_calls,
                "normalize_stats": norm_stats.to_dict(),
                "validation_outcomes": outcomes,
                "repair_plan": repair_plan,
                # Deliberately suffixed with _ids: these are id lists, not
                # finding objects, and a top-level key called "new_findings"
                # would be read as the latter by any consumer.
                "new_finding_ids": [f.id for f in new_findings],
                "resolved_finding_ids": [f.id for f in resolved],
                "preexisting_finding_ids": [f.id for f in preexisting],
            },
        )
        report["summary"]["changed_files"] = len(ctx.changed_files)
        self._make_paths_portable(report, self.repo_root)

        # persist artefacts
        (run_dir / "report.json").write_text(
            report_mod.render_json(report), encoding="utf-8"
        )
        markdown = _require("chm.reports.markdown")
        (run_dir / "report.md").write_text(markdown.render_markdown(report), encoding="utf-8")
        sarif = _require("chm.reports.sarif")
        write_json(run_dir / "report.sarif", sarif.render_sarif(report))
        ledger.write(run_dir / "ledger.json")
        write_json(run_dir / "context" / "scan.json", ctx.to_dict())

        if self.config.baseline.enabled:
            baseline_mod.save_baseline(baseline_path, current_metrics)

        runs_root = run_dir.parent
        write_json(
            runs_root / "latest.json",
            {"run_id": run_id, "run_dir": str(run_dir), "gate": gate.verdict.value},
        )

        return RunResult(
            report=report,
            findings=findings,
            ctx=ctx,
            run_dir=run_dir,
            tool_results=tool_results,
            tool_errors=list(errors.errors),
        )

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _make_paths_portable(report: dict, repo_root: Path) -> None:
        """Rewrite absolute artefact paths to repo-relative ones.

        Reports are read by humans and diffed by CI on other machines.  An
        absolute ``C:\\Users\\...`` path is noise at best and leaks the
        developer's directory layout at worst.  Command lines are left intact
        because they are evidence -- and the toolchain paths in them are
        absolute for a good reason: that is literally what ran.
        """
        for tool in report.get("tools", []):
            art = tool.get("artefact")
            if not art:
                continue
            try:
                tool["artefact"] = Path(art).resolve().relative_to(repo_root).as_posix()
            except (ValueError, OSError):
                tool["artefact"] = Path(str(art)).name

    @staticmethod
    def _check_language_coverage(ctx: ScanContext, errors: ErrorLedger) -> None:
        """Refuse to report PASS when nothing can analyse the change set.

        If every changed source file is written in a language no provider
        covers (Python, Go, Rust, ...), the run would otherwise end with zero
        findings and a green gate -- a false green, which the specification
        forbids.  Raising an evidence gap makes the gate return ``UNKNOWN``
        instead, which is an honest "I could not check this".
        """
        candidates = [
            cf
            for cf in ctx.changed_files
            if not cf.is_binary and cf.change_kind is not ChangeKind.DELETED
        ]
        source_files = [cf for cf in candidates if cf.language in SOURCE_LANGUAGES]
        if not source_files:
            return
        if any(cf.language in SUPPORTED_LANGUAGES for cf in source_files):
            return

        langs = sorted({cf.language.value for cf in source_files})
        errors.add(
            ToolError(
                provider="coverage",
                kind=ToolFailureKind.UNSUPPORTED,
                detail=(
                    "no evidence provider covers the changed languages ("
                    + ", ".join(langs)
                    + f"); {len(source_files)} source file(s) were not analysed. "
                    "This run cannot conclude PASS -- add a rule pack for these "
                    "languages or review them manually."
                ),
                evidence_gap=True,
            )
        )

    def _build_providers(self) -> list[EvidenceProvider]:
        providers: list[EvidenceProvider] = []

        analyzers = _require("chm.analyzers.registry")
        providers.extend(analyzers.native_analyzers())

        adapters = _require("chm.adapters")
        adapter_map = {
            "javac": ("compile", "CompileAdapter"),
            "pmd": ("pmd", "PmdAdapter"),
            "cpd": ("cpd", "CpdAdapter"),
            "semgrep": ("semgrep", "SemgrepAdapter"),
            "knip": ("knip", "KnipAdapter"),
            "spotbugs": ("spotbugs", "SpotbugsAdapter"),
            "openrewrite": ("openrewrite", "OpenRewriteAdapter"),
            "test-runner": ("testrunner", "TestRunnerAdapter"),
        }
        _ = adapters  # package import validates the whole adapter layer eagerly
        for name in PROVIDER_ORDER:
            if name in ("native-java", "native-vue"):
                continue
            mod_name, cls_name = adapter_map[name]
            mod = _require(f"chm.adapters.{mod_name}")
            cls = getattr(mod, cls_name, None)
            if cls is None:
                continue
            providers.append(cls(self.config))

        # filter by config + declared availability
        enabled: list[EvidenceProvider] = []
        for p in providers:
            tool_cfg = self._tool_config_for(p.name)
            if tool_cfg is not None and not tool_cfg.enabled:
                continue
            enabled.append(p)
        return enabled

    def _tool_config_for(self, provider_name: str):
        mapping = {
            "native-java": "native",
            "native-vue": "native",
            "javac": "compile",
            "pmd": "pmd",
            "cpd": "cpd",
            "semgrep": "semgrep",
            "knip": "knip",
            "spotbugs": "spotbugs",
            "openrewrite": "openrewrite",
            "test-runner": "test",
        }
        key = mapping.get(provider_name)
        if key is None:
            return None
        return self.config.tools.get(key)

    def _run_providers(
        self, providers: Sequence[EvidenceProvider], ctx: ScanContext
    ) -> list[ProviderResult]:
        results: dict[str, ProviderResult] = {}
        wave1: list[EvidenceProvider] = []
        wave2: list[EvidenceProvider] = []
        skipped: list[ProviderResult] = []

        for p in providers:
            try:
                supported = p.supports(ctx)
            except Exception as exc:  # pragma: no cover - defensive
                skipped.append(
                    ProviderResult(
                        provider=p.name,
                        status=ToolStatus.UNAVAILABLE,
                        error=ToolError(
                            provider=p.name,
                            kind=ToolFailureKind.CRASHED,
                            detail=f"supports() failed: {type(exc).__name__}: {exc}",
                            evidence_gap=True,
                        ),
                    )
                )
                continue
            if not supported:
                continue
            (wave2 if p.name in _SECOND_WAVE else wave1).append(p)

        parallel = bool(self.options.get("parallel", True))
        for wave in (wave1, wave2):
            if not wave:
                continue
            if parallel and len(wave) > 1:
                with futures.ThreadPoolExecutor(max_workers=min(4, len(wave))) as pool:
                    futs = {pool.submit(self._safe_scan, p, ctx): p for p in wave}
                    for fut in futures.as_completed(futs):
                        res = fut.result()
                        results[res.provider] = res
            else:
                for p in wave:
                    res = self._safe_scan(p, ctx)
                    results[res.provider] = res

        ordered: list[ProviderResult] = []
        for name in PROVIDER_ORDER:
            if name in results:
                ordered.append(results[name])
        ordered.extend(skipped)
        return ordered

    def _safe_scan(self, provider: EvidenceProvider, ctx: ScanContext) -> ProviderResult:
        try:
            return provider.scan(ctx)
        except Exception as exc:  # pragma: no cover - adapters must not raise
            return ProviderResult(
                provider=provider.name,
                status=ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=provider.name,
                    kind=ToolFailureKind.CRASHED,
                    detail=f"{type(exc).__name__}: {exc}",
                    evidence_gap=True,
                ),
            )

    def _build_repair_plan(self, findings: Iterable[Finding]) -> list[dict]:
        plan: list[dict] = []
        for f in findings:
            if f.repair.repair_class is RepairClass.NONE:
                continue
            plan.append(
                {
                    "finding_id": f.id,
                    "repair_class": f.repair.repair_class.value,
                    "auto_fixable": f.repair.auto_fixable,
                    "recipe": f.repair.recipe,
                    "file": f.location.file,
                    "line": f.location.start_line,
                    "recommendation": f.recommendation.to_dict(),
                    "validation_required": f.validation.required,
                }
            )
        return plan

    @staticmethod
    def _reviewer_tokens(calls: Sequence[dict]) -> dict[str, int]:
        return {
            "calls": len(calls),
            "input": sum(int(c.get("input_tokens", 0)) for c in calls),
            "output": sum(int(c.get("output_tokens", 0)) for c in calls),
        }

    def _cache_hit_ratio(self, ctx: ScanContext) -> float:
        try:
            cache_mod = _require("chm.core.cache")
        except ConfigError:
            return 0.0
        stats = ctx.options.get("_cache_stats")
        if isinstance(stats, dict):
            return float(stats.get("ratio", 0.0))
        return 0.0


# --------------------------------------------------------------------------
# verification helper (step 12: re-run gate after a repair)
# --------------------------------------------------------------------------


def rerun_gate(
    *,
    repo_root: Path | str,
    config: Config,
    previous_report: dict,
    mode: ReviewMode | str = ReviewMode.DIFF,
    **kwargs: Any,
) -> dict:
    """Re-run the gate and diff the result against the previous run.

    Spec §34: "修复后必须 rerun gate".  The returned dict records which
    findings closed, which persisted and whether any *new* HIGH appeared.
    """
    orch = Orchestrator(repo_root=repo_root, config=config, mode=mode, **kwargs)
    result = orch.run()
    before = {f["id"]: f for f in previous_report.get("findings", [])}
    after = {f["id"]: f for f in result.report.get("findings", [])}

    closed = sorted(set(before) - set(after))
    appeared = sorted(set(after) - set(before))
    new_high = [
        after[i]["id"]
        for i in appeared
        if after[i]["severity"] in ("HIGH", "CRITICAL")
    ]
    return {
        "run_id": result.report["run"]["run_id"],
        "gate": result.report["summary"]["gate"],
        "exit_code": result.exit_code,
        "closed": closed,
        "appeared": appeared,
        "new_high_or_critical": new_high,
        "regression": bool(new_high),
        "report": result.report,
    }
