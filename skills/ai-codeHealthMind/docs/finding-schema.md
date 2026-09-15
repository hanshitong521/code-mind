# Finding schema

Every provider — external CLI, built-in analyzer or semantic reviewer — emits a
`RawFinding`. The normalizer turns it into a `Finding`. **Only `Finding` objects reach
the score engine, the gate and the reports.**

Source of truth: `src/chm/schema.py`.

## 1. The model

```yaml
id: CHM-000001                        # assigned by the normalizer, deterministic
rule_id: CHM-JAVA-DEAD-001            # provider-owned, stable
category: DEAD_CODE                   # one of the 20 dimensions
title: "疑似无调用 private method"

severity: MEDIUM                      # CRITICAL | HIGH | MEDIUM | LOW
confidence: 0.91                      # 0.0 .. 1.0

location:
  file: src/main/java/a/b/CouponService.java
  start_line: 183
  end_line: 221
  symbol: couponService.neverUsedHelper

change_scope:
  introduced_by_current_diff: true

evidence:
  deterministic:
    - provider: pmd
      rule_id: UnusedPrivateMethod
      result: hit
      detail: "..."
      references: 0
  semantic:
    - provider: "reviewer:simplicity:rule"
      result: hit
      detail: "该方法与当前业务入口无调用关系"

uncertainty:
  reflection_checked: false
  spring_registration_checked: true
  rpc_registration_checked: true
  mq_registration_checked: false
  xml_registration_checked: true
  dynamic_import_checked: false
  notes: []

decision:
  status: VALIDATED                   # lifecycle state
  block_merge: false
  reason: "evidence complete"

recommendation:
  preferred: "确认无反射入口后删除"
  fallback: "保留并标注调用来源"

repair:
  auto_fixable: false
  repair_class: MANUAL_DECISION
  recipe: null

validation:
  required: [compile, unit, regression]
  performed: []
  result: null

perf_confidence: null                 # PROVEN | LIKELY | SUSPECTED (PERFORMANCE only)
sources: [pmd, native-java]           # every provider that reported this issue
historical: false                     # present in the baseline
history: [DETECTED, EVIDENCE_COLLECTED, VALIDATED]
```

## 2. Enumerations

### Severity

| Value | Default decision | Typical content |
|---|---|---|
| `CRITICAL` | BLOCK | data loss, wrong money, auth bypass, deadlock, non-idempotent side effects, `UPDATE`/`DELETE` without `WHERE`, severe leaks |
| `HIGH` | BLOCK (unless accepted) | race conditions, transaction boundary errors, hot-path N+1, unbounded retry, unreleased connections, wrong abstraction across modules |
| `MEDIUM` | WARN, BLOCK above threshold | over-abstraction, duplicated logic, large methods, unused dependencies, wrapper inflation |
| `LOW` | INFO / WARN | naming, mild duplication, local boilerplate, comment quality |

### Category

Sixteen mandatory dimensions plus four extensions:

```
DEAD_CODE  DUPLICATION  WRONG_ABSTRACTION  OVER_ENGINEERING
COMPLEXITY  LARGE_METHOD  LARGE_CLASS  DEPENDENCY_GROWTH
COMPATIBILITY_JUNK  DEFENSIVE_JUNK  ERROR_HANDLING  CONCURRENCY
RESOURCE_SAFETY  DATABASE  PERFORMANCE  TESTABILITY
--- extensions ---
API_SURFACE_GROWTH  CONFIG_INFLATION  BOILERPLATE  ARCHITECTURE_DRIFT
```

### RepairClass

| Value | Who fixes it | Examples |
|---|---|---|
| `SAFE_AUTO_FIX` | the tool | unused import, debug residue, a deterministic recipe |
| `WRITER_FIX` | the author / writing agent | abstraction, duplicated business logic, large method, error handling, concurrency, transaction |
| `MANUAL_DECISION` | a human | business rules, architectural boundaries, dead code with an unproven dynamic entry, unclear compatibility requirement |
| `NONE` | nobody | informational |

### PerfConfidence

`PROVEN` requires one of: benchmark, profiler, real query count, trace, or a static
pattern with a strong guarantee. `LIKELY` is a strong static pattern. Everything else
is `SUSPECTED`. **Without `PROVEN`, a performance finding can never exceed MEDIUM.**

## 3. Lifecycle

```
DETECTED
   ↓
EVIDENCE_COLLECTED
   ↓
VALIDATED / REJECTED / UNCERTAIN
   ↓
BLOCK / WARN / INFO
   ↓
FIXED / ACCEPTED_RISK / FALSE_POSITIVE
   ↓
REVERIFIED
   ↓
CLOSED
```

`DETECTED → FIXED → PASS` is forbidden. `Finding.transition()` enforces the legal
edges and raises `SchemaError` on anything else.

## 4. Schema guards (spec §4)

Enforced by `Finding.validate_schema()` / `validate_evidence()` /
`validate_uncertain_safety()` and re-checked by `transition()`.

| ID | Rule | Where |
|---|---|---|
| `CHM-SCHEMA-001` | required fields must be present and well formed (`id` matches `CHM-NNNNNN`, `rule_id` matches `CHM-...-...`) | `validate_schema` |
| `CHM-SCHEMA-002` | `severity` and `category` must be legal enum members | `validate_schema` |
| `CHM-SCHEMA-003` | `confidence` must be numeric and within `0..1` | `validate_schema` |
| `CHM-SCHEMA-004` | a HIGH/CRITICAL finding may not enter `VALIDATED` without evidence | `validate_evidence`, called from `transition` |
| `CHM-SCHEMA-005` | an `UNCERTAIN` finding may never be `auto_fixable` / `SAFE_AUTO_FIX` | `validate_uncertain_safety` |

## 5. Rules the normalizer enforces

These are not schema violations but they keep severity honest:

1. **Semantic-only findings cannot claim HIGH/CRITICAL.** If `EvidenceKind.SEMANTIC`
   is the only evidence, severity is capped at `MEDIUM` and confidence at `0.6`.
2. **Performance findings are capped at MEDIUM** unless `perf_confidence == PROVEN`.
3. **Findings outside the change set are dropped** unless the provider explicitly sets
   `extra.whole_file` (used by `--repo`).
4. **Dead code is never auto-fixable by default.** `dead_code.allow_auto_delete: false`
   forces `MANUAL_DECISION`; even when enabled, only the mechanical rules
   (`UNUSED-IMPORT`, `DEBUG-RESIDUE`, `TODO-MARKER`, `COMMENTED-CODE`) qualify.

## 6. Evidence rules

* Every provider hit becomes one `EvidenceItem` with the provider name, the provider's
  own rule id, the result and a human-readable detail.
* When several providers report the same issue, the deduplicator keeps the highest
  severity, merges all evidence and records all providers in `sources`.
* `evidence.deterministic` and `evidence.semantic` are kept separate on purpose:
  reports and the validator treat them differently.
* `uncertainty.*` records which dynamic-entry checks were actually performed. A check
  that was not performed must stay `false` — guessing here is what turns a code-health
  tool into a code-deleting machine.

## 7. Machine formats

| Format | Function | Notes |
|---|---|---|
| JSON | `reports.json_report.build_report` / `render_json` | sorted keys; stable across runs except run id, durations and per-run artefact paths — see [architecture §5](architecture.md#the-exact-stability-contract) |
| Markdown | `reports.markdown.render_markdown` | current-diff findings first, historical debt in a separate section |
| SARIF 2.1.0 | `reports.sarif.render_sarif` | `CRITICAL`/`HIGH` → `error`, `MEDIUM` → `warning`, `LOW` → `note`; relative `/`-separated URIs |
| Console | `reports.console.render_console` | the compact form shown in the README; a non-PASS verdict always prints `Why this verdict:` |

SARIF documents can be self-checked with `reports.sarif.validate_sarif(doc)`.
