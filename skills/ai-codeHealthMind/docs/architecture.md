# Architecture

## 1. Where CodeHealthMind sits

```
                ┌──────────────────┐
                │ RequirementMind  │   freezes WHAT
                └─────────┬────────┘
                          │
                ┌─────────▼────────┐
                │  Writer / AI     │   produces the change set
                └─────────┬────────┘
                          │
                ┌─────────▼────────┐
                │ Writer SelfCheck │   cheap local checks only — never the gate
                └─────────┬────────┘
                          │
        ┌─────────────────▼──────────────────┐
        │        CodeHealthMind              │
        │            Orchestrator            │
        └───┬──────────────┬─────────────┬───┘
            │              │             │
   ┌────────▼───────┐ ┌────▼─────────┐ ┌─▼──────────────┐
   │ Deterministic  │ │  Semantic    │ │    Context     │
   │ Evidence Layer │ │  Reviewer    │ │   Collector    │
   │                │ │              │ │                │
   │ native-java    │ │ 5 personas   │ │ git / AST-lite │
   │ native-vue     │ │ isolated     │ │ symbol index   │
   │ javac / PMD    │ │ context      │ │ requirement    │
   │ CPD / SpotBugs │ │              │ │ test evidence  │
   │ Semgrep / Knip │ │              │ │ secret filter  │
   └────────┬───────┘ └────┬─────────┘ └─┬──────────────┘
            └──────────────┼─────────────┘
                           ▼
                   Finding Normalizer
                           │
                   Finding Deduplicator
                           │
                   Evidence Validator
                           │
                Baseline / Delta + Risk Router
                           │
                    Score Engine  →  Gate
                           │
              PASS / WARN / BLOCK / UNKNOWN
                           │
                   Repair Proposal
                           │
              OpenRewrite / Writer Fix / Manual
                           │
                      TestMind  →  Re-run Gate
```

The same object graph serves two gates:

* **PRE-GATE** (before tests): structure, complexity, dead code, duplication,
  obvious defects, over-engineering.
* **POST-GATE** (after tests): test evidence, regression, debt introduced *by the
  repair*, final delta. `codehealth verify` implements this step.

## 2. The twelve steps

`src/chm/core/orchestrator.py` is the only place that knows the order. Every step
is a separate module so it can be tested without the others.

| # | Step | Module | Failure behaviour |
|---|---|---|---|
| 1 | Resolve target | `context/gitctx.py` | `GitError` → exit 2 |
| 2 | Load requirement context | `cli/main.py` (`--requirement`) | secret-filtered; missing file → exit 2 |
| 3 | Collect diff | `context/gitctx.py` | unborn HEAD degrades to "all untracked+modified" |
| 4 | Run deterministic providers | `adapters/*`, `analyzers/*` | each provider returns a `ProviderResult`; failures become `ToolError`s |
| 5 | Build minimal context | `context/packer.py` | packer missing → minimal inline pack, marked degraded |
| 6 | Run semantic reviewers | `reviewers/runtime.py`, `core/riskrouter.py` | `backend=llm` without a command → CONFIG error, **not** a silent downgrade |
| 7 | Normalise | `core/normalizer.py` | out-of-diff findings dropped by default |
| 8 | Validate high risk | `core/evidencevalidator.py` | downgrades/rejects; never invents evidence |
| 9 | Dedup + baseline | `core/dedup.py`, `core/baseline.py` | historical vs new debt separated |
| 10 | Score + gate | `core/score.py`, `core/gate.py` | hard gate overrides the score |
| 11 | Repair routing | `core/repair.py` | only `SAFE_AUTO_FIX` is ever edited |
| 12 | Re-run gate | `core/orchestrator.rerun_gate` | reports closed / appeared / new-HIGH |

## 3. Module boundaries

```
chm/
  errors.py       ToolError, ToolFailureKind, ErrorLedger         (no deps)
  schema.py       Finding, enums, lifecycle, schema guards        (errors, util)
  contracts.py    ScanContext, ProviderResult, EvidenceProvider   (errors, schema, util)
  util.py         run_cmd, hashing, file walking, text helpers     (stdlib only)
  yamlmini.py     YAML-subset parser                               (stdlib only)
  config.py       strict config loader                             (errors, util, yamlmini)
```

Everything below depends *downwards only*:

```
cli  ─┐
      ├─→ core.orchestrator ─→ { adapters, analyzers, reviewers, context, reports }
core  ─┘                          │
                                  └─→ contracts ─→ schema ─→ errors/util
```

Rules enforced in review:

* `schema.py` never imports a provider — the Finding model must not know how it was found.
* `adapters/` is the **only** package allowed to spawn a process.
* `analyzers/` is the only package allowed to parse source without a tool.
* `reports/` never mutates a Finding.
* Nothing imports `cli`.

## 4. Data flow

```
RawFinding[]                      provider output, loosely typed
     │
     ▼  normalizer.normalize_all()
Finding[]                         stable CHM-NNNNNN ids, category, severity,
     │                            repair class, validation requirements
     ▼  dedup.deduplicate()
Finding[]                         one finding per issue, N evidence sources
     │
     ▼  evidencevalidator.validate()
Finding[]                         severity corrected, uncertainty recorded,
     │                            dynamic-entry rejections applied
     ▼  baseline.classify_against_baseline()
(new, resolved, preexisting)
     │
     ▼  score.score_findings() + gate.evaluate_gate()
ScoreBreakdown + GateResult
     │
     ▼  reports.json_report.build_report()
report dict  →  report.json / report.md / report.sarif / ledger.json
```

`report` is a plain dict so it can be serialised, diffed and asserted byte-for-byte.

## 5. Determinism

Spec §41 requires the same commit and config to produce the same verdict.

* Ids are assigned **after** sorting by `(file, start_line, end_line, rule_id,
  symbol, title)`, so a finding keeps its id across runs.
* Providers run in a fixed order (`PROVIDER_ORDER`), even when executed in parallel
  across a thread pool — results are re-sorted before use.
* All report rendering goes through `util.stable_json` (sorted keys, fixed separators).
* `context.packer.ContextPack.fingerprint()` is a content hash of the payload, which
  is how context isolation is *proved* rather than asserted.

### The exact stability contract

Two runs over the same commit and config produce **byte-identical** values for
everything that carries a judgement:

| Stable across runs | Legitimately varies |
|---|---|
| `findings` (ids, order, severity, evidence, decisions) | `run.run_id` |
| `summary` (gate, score, counts, exit code) | `run.duration_ms`, `ledger.started_at` |
| `score` and its per-finding deductions | `tools[].duration_ms`, `reviewer_calls[].duration_ms` |
| `gate.reasons` / `gate.blockers` | `tools[].artefact` and `tools[].command` paths under `.codehealth/runs/<run_id>/` |
| `dedup.groups`, `route_plan`, `validation_outcomes` | |
| `tool_errors` (kind and detail) | |

In other words: **the verdict and everything that justifies it are reproducible**;
run identifiers, wall-clock timings and per-run artefact locations are not, and
pretending otherwise would just mean deleting useful telemetry. Artefact paths are
rewritten repo-relative (`Orchestrator._make_paths_portable`) so reports stay
portable and diffable across machines.


## 6. Degradation, not fake green

`ProviderResult` carries a `ToolError` with a `ToolFailureKind`:

| Kind | Meaning | `evidence_gap` |
|---|---|---|
| `MISSING` | binary/jar not found | true for PMD/SpotBugs/Semgrep/javac |
| `DISABLED` | switched off in config | false |
| `UNSUPPORTED` | tool present but cannot handle this input (e.g. SpotBugs without classes) | false |
| `TIMEOUT` | exceeded `tools.<name>.timeout_s` | true |
| `NONZERO_EXIT` | ran and failed | depends |
| `MALFORMED_OUTPUT` | output not parseable | true |
| `PARTIAL_OUTPUT` | some output parsed, some dropped | true |
| `CRASHED` | interpreter/OS failure | true |

`gate.evaluate_gate` turns `evidence_gap` into `UNKNOWN` when a HIGH/CRITICAL
conclusion depended on the missing tool. There is no code path where a tool failure
produces `PASS`.

## 7. Reference projects

Design influence only — no source was copied (see
[ADR-002](adr/ADR-002-reference-project-usage.md)):

| Project | Borrowed |
|---|---|
| Ponytail | Delete First, YAGNI, single-caller abstraction detection, wrapper/config inflation |
| Alibaba OpenCodeReview | Review Target Resolver, workspace/diff/commit review, structured findings, session state |
| open-code-review | independent reviewer personas, multi-reviewer synthesis, disagreement handling |
| PMD / CPD | Java smells, complexity, duplication |
| SpotBugs | null/resource/concurrency correctness |
| Semgrep | multi-language and team-specific rules |
| OpenRewrite | deterministic repair recipes |
| Knip | unused files / exports / dependencies in JS+TS |

## 8. Deliberate deviations from the specification

Recorded as ADRs, summarised here:

* **Python instead of TypeScript** for the engine (ADR-001). The spec shows a TS
  `EvidenceProvider` interface and allows `pyproject.toml`; Python was chosen so the
  gate runs in a bare CI container with no install step, and so it matches the
  surrounding `code-mind` toolchain.
* **Built-in deterministic analyzers** in addition to external tools (ADR-003). The
  spec lists PMD/CPD/SpotBugs/Semgrep/Knip; on a host without a JVM or Semgrep those
  all vanish and the gate would have nothing to say. The built-ins cover the
  pattern-provable subset of the same dimensions so the gate still has real evidence.
* **`rule` reviewer backend**. A deterministic local heuristic reviewer that is
  *labelled as such* everywhere. It is explicitly **not** presented as an independent
  model; cross-model review requires `review.backend: llm`.
