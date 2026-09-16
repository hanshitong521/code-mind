"""RawFinding -> Finding normalisation.

This is the single choke point where provider output becomes a first-class
Finding.  It is responsible for:

* assigning **deterministic** ids (``CHM-000001`` ... ordered by file, line,
  rule, symbol -- so two identical runs produce identical reports);
* filling in a category/severity when a provider was vague, using explicit
  rule-id heuristics rather than guesses;
* attaching the provider's own hit as a structured ``EvidenceItem``;
* deciding ``introduced_by_current_diff`` from the real change set;
* deciding the repair class (spec §23) -- and refusing SAFE_AUTO_FIX for
  anything that is not provably safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from ..config import Config
from ..contracts import ScanContext
from ..schema import (
    Category,
    Decision,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingStatus,
    Location,
    PerfConfidence,
    RawFinding,
    Recommendation,
    Repair,
    RepairClass,
    Severity,
    Uncertainty,
    Validation,
)

# --------------------------------------------------------------------------
# category inference (only when the provider was vague)
# --------------------------------------------------------------------------

_RULE_CATEGORY_HINTS: tuple[tuple[str, Category], ...] = (
    ("UNUSED-PRIVATE-METHOD", Category.DEAD_CODE),
    ("UNUSED-FIELD", Category.DEAD_CODE),
    ("UNUSED-IMPORT", Category.DEAD_CODE),
    ("UNUSED-EXPORT", Category.DEAD_CODE),
    ("UNUSED-DEPENDENCY", Category.DEAD_CODE),
    ("UNUSED-CONFIG", Category.CONFIG_INFLATION),
    ("UNREACHABLE", Category.DEAD_CODE),
    ("COMMENTED-CODE", Category.DEAD_CODE),
    ("DEBUG-RESIDUE", Category.DEAD_CODE),
    ("TODO", Category.DEAD_CODE),
    ("DEAD", Category.DEAD_CODE),
    ("DUPLICATE", Category.DUPLICATION),
    ("DUP-", Category.DUPLICATION),
    ("COPY", Category.DUPLICATION),
    ("WRAPPER", Category.OVER_ENGINEERING),
    ("SINGLE-IMPL", Category.WRONG_ABSTRACTION),
    ("SPECULATIVE", Category.OVER_ENGINEERING),
    ("FACTORY", Category.OVER_ENGINEERING),
    ("OVER-ENGINEER", Category.OVER_ENGINEERING),
    ("COMPAT", Category.COMPATIBILITY_JUNK),
    ("LEGACY", Category.COMPATIBILITY_JUNK),
    ("DEFENSIVE", Category.DEFENSIVE_JUNK),
    ("BOILERPLATE", Category.BOILERPLATE),
    ("LARGE-METHOD", Category.LARGE_METHOD),
    ("LARGE-CLASS", Category.LARGE_CLASS),
    ("LONG-PARAM", Category.COMPLEXITY),
    ("CYCLOMATIC", Category.COMPLEXITY),
    ("NESTING", Category.COMPLEXITY),
    ("COMPLEXITY", Category.COMPLEXITY),
    ("COMPILE-FAIL", Category.ERROR_HANDLING),
    ("TEST-FAIL", Category.ERROR_HANDLING),
    ("EMPTY-CATCH", Category.ERROR_HANDLING),
    ("CATCH", Category.ERROR_HANDLING),
    ("SWALLOW", Category.ERROR_HANDLING),
    ("RETRY", Category.ERROR_HANDLING),
    ("NULL", Category.ERROR_HANDLING),
    ("ERROR", Category.ERROR_HANDLING),
    ("EXCEPTION", Category.ERROR_HANDLING),
    ("RESOURCE", Category.RESOURCE_SAFETY),
    ("STREAM", Category.RESOURCE_SAFETY),
    ("CLOSE", Category.RESOURCE_SAFETY),
    ("EXECUTOR", Category.RESOURCE_SAFETY),
    ("THREADPOOL", Category.RESOURCE_SAFETY),
    ("LEAK", Category.RESOURCE_SAFETY),
    ("SEMAPHORE", Category.CONCURRENCY),
    ("LOCK", Category.CONCURRENCY),
    ("CONCURREN", Category.CONCURRENCY),
    ("SHARED-MUTABLE", Category.CONCURRENCY),
    ("IDEMPOTEN", Category.CONCURRENCY),
    ("RACE", Category.CONCURRENCY),
    ("NPLUS1", Category.DATABASE),
    ("N+1", Category.DATABASE),
    ("SQL", Category.DATABASE),
    ("UPDATE-NO-WHERE", Category.DATABASE),
    ("DELETE-NO-WHERE", Category.DATABASE),
    ("SELECT-STAR", Category.DATABASE),
    ("DB-", Category.DATABASE),
    ("TX-", Category.DATABASE),
    ("TRANSACTION", Category.DATABASE),
    ("PERF", Category.PERFORMANCE),
    ("ON2", Category.PERFORMANCE),
    ("SERIALIZE", Category.PERFORMANCE),
    ("CACHE", Category.PERFORMANCE),
    ("TESTABIL", Category.TESTABILITY),
    ("CLOCK", Category.TESTABILITY),
    ("HARDCODED-TIME", Category.TESTABILITY),
    ("SINGLETON", Category.TESTABILITY),
    ("API-SURFACE", Category.API_SURFACE_GROWTH),
    ("ARCH-DRIFT", Category.ARCHITECTURE_DRIFT),
)


def infer_category(raw: RawFinding) -> Category:
    if raw.category is not None:
        return raw.category
    haystack = f"{raw.rule_id}|{raw.message}".upper()
    for token, category in _RULE_CATEGORY_HINTS:
        if token in haystack:
            return category
    return Category.BOILERPLATE


# --------------------------------------------------------------------------
# repair routing (spec §23)
# --------------------------------------------------------------------------

#: Categories that are only ever *provably* safe when a deterministic provider
#: produced them AND the change is local and mechanical.
_SAFE_AUTO_FIX_CATEGORIES = {
    Category.DEAD_CODE,       # only unused import / debug residue -- see guard below
}

_SAFE_AUTO_FIX_RULE_TOKENS = (
    "UNUSED-IMPORT",
    "DEBUG-RESIDUE",
    "TODO-MARKER",
    "COMMENTED-CODE",
)

_WRITER_FIX_CATEGORIES = {
    Category.WRONG_ABSTRACTION,
    Category.OVER_ENGINEERING,
    Category.DUPLICATION,
    Category.LARGE_METHOD,
    Category.LARGE_CLASS,
    Category.COMPLEXITY,
    Category.ERROR_HANDLING,
    Category.CONCURRENCY,
    Category.DATABASE,
    Category.PERFORMANCE,
    Category.RESOURCE_SAFETY,
    Category.DEFENSIVE_JUNK,
    Category.COMPATIBILITY_JUNK,
    Category.TESTABILITY,
    Category.ARCHITECTURE_DRIFT,
}


def decide_repair(
    raw: RawFinding,
    category: Category,
    severity: Severity,
    *,
    config: Config,
    uncertain: bool,
) -> Repair:
    """Route a finding to SAFE_AUTO_FIX / WRITER_FIX / MANUAL_DECISION.

    Guards are deliberately paranoid.  Spec §18/§23 and CHM-SCHEMA-005 forbid
    auto-deleting anything whose dynamic entry points are not proven absent.
    """
    rule = raw.rule_id.upper()

    # Never auto-fix when we are uncertain or the provider is semantic-only.
    if uncertain or raw.kind is not EvidenceKind.DETERMINISTIC:
        return Repair(auto_fixable=False, repair_class=RepairClass.MANUAL_DECISION)

    # Dead code may only be auto-deleted when explicitly allowed AND proven.
    if category is Category.DEAD_CODE:
        if not config.dead_code.allow_auto_delete:
            return Repair(auto_fixable=False, repair_class=RepairClass.MANUAL_DECISION)
        if not any(tok in rule for tok in _SAFE_AUTO_FIX_RULE_TOKENS):
            return Repair(auto_fixable=False, repair_class=RepairClass.MANUAL_DECISION)
        return Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX)

    if any(tok in rule for tok in _SAFE_AUTO_FIX_RULE_TOKENS):
        if category in _SAFE_AUTO_FIX_CATEGORIES:
            return Repair(auto_fixable=True, repair_class=RepairClass.SAFE_AUTO_FIX)

    if severity in (Severity.CRITICAL, Severity.HIGH):
        return Repair(auto_fixable=False, repair_class=RepairClass.WRITER_FIX)

    if category in _WRITER_FIX_CATEGORIES:
        return Repair(auto_fixable=False, repair_class=RepairClass.WRITER_FIX)

    if category is Category.CONFIG_INFLATION:
        return Repair(auto_fixable=False, repair_class=RepairClass.MANUAL_DECISION)

    return Repair(auto_fixable=False, repair_class=RepairClass.WRITER_FIX)


# --------------------------------------------------------------------------
# validation requirements
# --------------------------------------------------------------------------

_VALIDATION_BY_CATEGORY: dict[Category, list[str]] = {
    Category.DEAD_CODE: ["compile", "unit", "regression"],
    Category.DUPLICATION: ["compile", "unit"],
    Category.WRONG_ABSTRACTION: ["compile", "unit"],
    Category.OVER_ENGINEERING: ["compile", "unit"],
    Category.COMPLEXITY: ["compile", "unit"],
    Category.LARGE_METHOD: ["compile", "unit"],
    Category.LARGE_CLASS: ["compile", "unit"],
    Category.DEPENDENCY_GROWTH: ["build"],
    Category.COMPATIBILITY_JUNK: ["compile", "regression"],
    Category.DEFENSIVE_JUNK: ["unit"],
    Category.ERROR_HANDLING: ["compile", "unit", "regression"],
    Category.CONCURRENCY: ["compile", "unit", "stress"],
    Category.RESOURCE_SAFETY: ["compile", "unit"],
    Category.DATABASE: ["compile", "unit", "regression"],
    Category.PERFORMANCE: ["benchmark"],
    Category.TESTABILITY: ["unit"],
    Category.API_SURFACE_GROWTH: ["compile"],
    Category.CONFIG_INFLATION: ["build"],
    Category.BOILERPLATE: ["compile"],
    Category.ARCHITECTURE_DRIFT: ["compile", "unit"],
}


def validation_for(category: Category, severity: Severity) -> Validation:
    required = list(_VALIDATION_BY_CATEGORY.get(category, ["compile"]))
    if severity is Severity.CRITICAL and "regression" not in required:
        required.append("regression")
    return Validation(required=required)


# --------------------------------------------------------------------------
# recommendations
# --------------------------------------------------------------------------

_DEFAULT_RECOMMENDATIONS: dict[Category, tuple[str, str]] = {
    Category.DEAD_CODE: (
        "确认无反射/IOC/SPI/MQ/XML 动态入口后删除",
        "保留并标注真实调用来源",
    ),
    Category.DUPLICATION: (
        "先确认业务语义与变化原因是否一致，再决定是否收敛",
        "保留重复，仅在注释中标注与另一处的对应关系",
    ),
    Category.WRONG_ABSTRACTION: (
        "删除仅有的抽象层，直接依赖具体实现",
        "若存在真实边界（RPC/第三方/测试替换），补充说明并保留",
    ),
    Category.OVER_ENGINEERING: (
        "删除未被使用的扩展点，等第二个实现出现时再引入抽象",
        "保留但补充真实的扩展需求证据",
    ),
    Category.COMPLEXITY: ("拆分职责单一的子方法", "保持现状并补充单元测试覆盖"),
    Category.LARGE_METHOD: ("按职责提取方法", "仅补充注释与测试，不做结构性改动"),
    Category.LARGE_CLASS: ("按职责拆分类", "保持现状，补齐测试"),
    Category.DEPENDENCY_GROWTH: ("移除未使用的依赖", "在文档中说明该依赖的必要性"),
    Category.COMPATIBILITY_JUNK: (
        "确认版本基线后删除死分支",
        "补充版本基线证据并保留",
    ),
    Category.DEFENSIVE_JUNK: ("删除不可达的防御分支", "保留并说明触发条件"),
    Category.ERROR_HANDLING: (
        "把异常转换为明确的失败信号（抛出或返回 Result）",
        "保留降级路径，但必须记录 metric 与告警",
    ),
    Category.CONCURRENCY: ("收窄锁范围并保证幂等", "改用并发安全结构并补充并发测试"),
    Category.RESOURCE_SAFETY: ("使用 try-with-resources 或显式释放", "在文档中说明生命周期由容器管理"),
    Category.DATABASE: ("改写为批量查询/加 WHERE 条件", "补充索引与执行计划证据"),
    Category.PERFORMANCE: ("补充 benchmark 证据后再优化", "记录当前基线并观察"),
    Category.TESTABILITY: ("注入 Clock / 去除全局状态", "补充集成测试覆盖"),
    Category.API_SURFACE_GROWTH: ("收敛对外暴露面", "说明该 API 的调用方"),
    Category.CONFIG_INFLATION: ("删除未使用的配置项", "补充该配置的真实部署差异"),
    Category.BOILERPLATE: ("使用语言/框架已有能力替换样板", "保留样板并集中管理"),
    Category.ARCHITECTURE_DRIFT: ("把依赖拉回既定边界", "更新架构文档说明该依赖"),
}


def recommendation_for(category: Category, raw: RawFinding) -> Recommendation:
    preferred, fallback = _DEFAULT_RECOMMENDATIONS.get(
        category, ("人工确认后再处理", "记录为已知问题")
    )
    extra_preferred = raw.extra.get("recommendation") if raw.extra else None
    if isinstance(extra_preferred, str) and extra_preferred:
        preferred = extra_preferred
    elif isinstance(extra_preferred, dict):
        preferred = extra_preferred.get("preferred", preferred)
        fallback = extra_preferred.get("fallback", fallback)
    return Recommendation(preferred=preferred, fallback=fallback)


# --------------------------------------------------------------------------
# uncertainty extraction
# --------------------------------------------------------------------------

_UNCERTAINTY_KEYS = (
    ("reflection_checked", "reflection_checked"),
    ("spring_registration_checked", "spring_registration_checked"),
    ("rpc_registration_checked", "rpc_registration_checked"),
    ("mq_registration_checked", "mq_registration_checked"),
    ("xml_registration_checked", "xml_registration_checked"),
    ("xml_checked", "xml_registration_checked"),
    ("dynamic_import_checked", "dynamic_import_checked"),
)


def uncertainty_from_raw(raw: RawFinding) -> Uncertainty:
    unc = Uncertainty()
    extra = raw.extra or {}
    for key, attr in _UNCERTAINTY_KEYS:
        if extra.get(key):
            setattr(unc, attr, True)
    notes = extra.get("uncertainty_notes")
    if isinstance(notes, list):
        unc.notes.extend(str(n) for n in notes)
    kinds = extra.get("dynamic_entry_kinds")
    if isinstance(kinds, list) and kinds:
        unc.notes.append("dynamic entries: " + ", ".join(sorted(str(k) for k in kinds)))
    return unc


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------


@dataclass
class NormalizeStats:
    total: int = 0
    outside_diff: int = 0
    excluded: int = 0
    uncertain: int = 0
    auto_fixable: int = 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "outside_diff": self.outside_diff,
            "excluded": self.excluded,
            "uncertain": self.uncertain,
            "auto_fixable": self.auto_fixable,
        }


def normalize_one(
    raw: RawFinding,
    *,
    index: int,
    config: Config,
    ctx: Optional[ScanContext] = None,
) -> Finding:
    """Turn one RawFinding into a Finding (id assigned by ``index``)."""
    category = infer_category(raw)
    severity = raw.severity or Severity.MEDIUM
    confidence = float(raw.confidence)

    # A provider that produced no rule id still needs a legal one.
    rule_id = raw.rule_id or f"CHM-UNKNOWN-{index:03d}"

    location = Location(
        file=raw.file.replace("\\", "/").lstrip("./"),
        start_line=max(1, int(raw.start_line)),
        end_line=max(int(raw.start_line), int(raw.end_line)),
        symbol=raw.symbol,
    )

    introduced = False
    if ctx is not None:
        cf = ctx.changed_file(location.file)
        if cf is not None:
            introduced = (
                not cf.hunks
                or ctx.is_changed_line(location.file, location.start_line)
            )
    if raw.extra and "introduced_by_current_diff" in raw.extra:
        introduced = bool(raw.extra["introduced_by_current_diff"])

    unc = uncertainty_from_raw(raw)
    uncertain = bool(unc.notes) and not unc.any_check

    # Semantic-only findings with no deterministic support can never claim
    # HIGH/CRITICAL (spec §3.1 / §3.2).
    if raw.kind is EvidenceKind.SEMANTIC and severity in (Severity.CRITICAL, Severity.HIGH):
        severity = Severity.MEDIUM
        confidence = min(confidence, 0.6)

    repair = decide_repair(raw, category, severity, config=config, uncertain=uncertain)

    evidence = [
        EvidenceItem(
            provider=raw.provider,
            result="hit",
            kind=raw.kind,
            rule_id=raw.rule_id,
            detail=raw.detail or raw.message,
            references=raw.extra.get("references") if raw.extra else None,
            raw={k: v for k, v in (raw.extra or {}).items() if k not in ("raw",)} or None,
        )
    ]

    perf_confidence: Optional[PerfConfidence] = None
    if category is Category.PERFORMANCE:
        raw_perf = (raw.extra or {}).get("perf_confidence")
        try:
            perf_confidence = PerfConfidence(raw_perf) if raw_perf else PerfConfidence.SUSPECTED
        except ValueError:
            perf_confidence = PerfConfidence.SUSPECTED
        # Spec §19: without a benchmark/profiler/query-count, HIGH is forbidden.
        if perf_confidence is not PerfConfidence.PROVEN and severity.rank > Severity.MEDIUM.rank:
            severity = Severity.MEDIUM

    finding = Finding(
        id=f"CHM-{index:06d}",
        rule_id=rule_id,
        category=category,
        title=(raw.message or rule_id).strip(),
        severity=severity,
        confidence=confidence,
        location=location,
        introduced_by_current_diff=introduced,
        evidence=evidence,
        uncertainty=unc,
        decision=Decision(status=FindingStatus.DETECTED),
        recommendation=recommendation_for(category, raw),
        repair=repair,
        validation=validation_for(category, severity),
        perf_confidence=perf_confidence,
        sources=[raw.provider],
    )
    finding.history.append(FindingStatus.DETECTED.value)
    finding.clamp_confidence()
    return finding


def _sort_key(f: Finding) -> tuple:
    return (
        f.location.file,
        f.location.start_line,
        f.location.end_line,
        f.rule_id,
        f.location.symbol or "",
        f.title,
    )


def normalize_all(
    raws: Iterable[RawFinding],
    *,
    config: Config,
    ctx: Optional[ScanContext] = None,
) -> tuple[list[Finding], NormalizeStats]:
    """Normalise a whole batch with deterministic ids.

    Ids are assigned *after* sorting so that the same logical finding keeps the
    same id across runs (spec §41 Determinism).
    """
    stats = NormalizeStats()

    prepared: list[RawFinding] = []
    for raw in raws:
        stats.total += 1
        path = raw.file.replace("\\", "/").lstrip("./")
        if config.is_excluded(path):
            stats.excluded += 1
            continue
        if ctx is not None and ctx.changed_files:
            cf = ctx.changed_file(path)
            extra = raw.extra or {}
            if cf is None and not extra.get("report_unchanged") and not extra.get("whole_file"):
                # Findings outside the change set are noise by default.
                stats.outside_diff += 1
                continue
            if cf is not None and cf.hunks and not ctx.is_changed_line(path, raw.start_line):
                if not (raw.extra or {}).get("whole_file"):
                    stats.outside_diff += 1
                    continue
        prepared.append(raw)

    # deterministic ordering BEFORE id assignment
    def pre_key(raw: RawFinding) -> tuple:
        return (
            raw.file.replace("\\", "/").lstrip("./"),
            int(raw.start_line),
            int(raw.end_line),
            raw.rule_id,
            raw.symbol or "",
            raw.message or "",
        )

    prepared.sort(key=pre_key)

    findings: list[Finding] = []
    for i, raw in enumerate(prepared, start=1):
        finding = normalize_one(raw, index=i, config=config, ctx=ctx)
        if finding.decision.status is FindingStatus.DETECTED and finding.repair.auto_fixable:
            stats.auto_fixable += 1
        if finding.uncertainty.notes and not finding.uncertainty.any_check:
            stats.uncertain += 1
        findings.append(finding)

    # Re-check: after normalisation some findings may have been downgraded,
    # so re-sort by severity for reporting while keeping ids stable.
    findings.sort(key=lambda f: (-f.severity.rank, *_sort_key(f)))
    return findings, stats
