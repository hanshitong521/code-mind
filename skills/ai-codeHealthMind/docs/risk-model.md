# Risk and gate model

Source of truth: `src/chm/core/{riskrouter,score,gate,baseline}.py`,
`src/chm/schema.py`.

## 1. Severity → default action

| Severity | Block by default | Rationale |
|---|---|---|
| `CRITICAL` | yes | data loss, wrong money, auth bypass, deadlock, non-idempotent side effects, `UPDATE`/`DELETE` without `WHERE`, severe leak |
| `HIGH` | yes, unless accepted risk | race, transaction boundary, hot-path N+1, unbounded retry, unreleased connection, cross-module wrong abstraction |
| `MEDIUM` | warn; block above `gates.max_new_medium` | over-abstraction, duplicated logic, large method, unused dependency, wrapper inflation |
| `LOW` | never blocks | naming, mild duplication, local boilerplate, comment quality |

## 2. Risk router

`riskrouter.plan_route(findings, ctx, config) -> RoutePlan`

| Risk | Reviewers | Validator | Context expansion |
|---|---:|---|---|
| `LOW` | 1 | no | diff + current file |
| `MEDIUM` | 1 | no | + direct references |
| `HIGH` | 2 | yes | + call graph + tests + config + business rules |
| `CRITICAL` | 2 | yes | full relevant slice |

Before any finding exists (step 6 of the pipeline) the initial risk is derived from the
change set itself: a change touching payment, refund, amount, coupon, order,
transaction, auth, permission or lock code starts at `HIGH`; documentation- or
test-only changes start at `LOW`.

`RoutePlan.models` returns two models for HIGH/CRITICAL when
`review.multi_model_on_high` is set — **but only if `review.backend == "llm"`**. With the
`rule` backend the plan's `reason` explicitly says
`cross-model review not applicable`, because claiming cross-model review without two
real models would be a lie.

## 3. Score model

Total 100, ten weighted dimensions:

| Dimension | Weight |
|---|---:|
| Correctness | 20 |
| Simplicity | 15 |
| Maintainability | 15 |
| Duplication | 10 |
| Complexity | 10 |
| Dead Code | 10 |
| Performance | 5 |
| Concurrency | 5 |
| Resource Safety | 5 |
| Testability | 5 |

Each finding deducts from its dimension (CRITICAL ≈ full dimension, HIGH ≈ 60 %,
MEDIUM ≈ 30 %, LOW ≈ 10 %). Every deduction records the `finding_id` that caused it,
so any score can be explained line by line.

### Hard gate — the score cannot rescue a fatal defect

`hard_gate = True` when any of:

* a `CRITICAL` finding exists,
* an unexplained `HIGH` finding exists,
* `compile_ok is False`,
* `test_ok is False`.

When `hard_gate` is true the total is still reported (it is real information) but the
gate ignores it.

## 4. Gate matrix (spec §47)

| Condition | Verdict | Exit code |
|---|---|---:|
| compile fail | `BLOCK` | 1 |
| test/unit fail | `BLOCK` | 1 |
| `CRITICAL` (not accepted risk) | `BLOCK` | 1 |
| `HIGH` (not accepted risk, `block_on_high`) | `BLOCK` | 1 |
| new `MEDIUM` count > `gates.max_new_medium` | `BLOCK` | 1 |
| new `MEDIUM` count ≤ threshold and > 0 | `WARN` | 0 |
| only `LOW` / info | `PASS` | 0 |
| tool degraded, no evidence gap | `WARN` | 0 |
| tool degraded **and** the gap blocks HIGH/CRITICAL verification | `UNKNOWN` | 3 |
| tool / configuration error | — | 2 |

`UNKNOWN` exists precisely so that a broken toolchain cannot masquerade as a green
build. It is not a softer `PASS`: CI must treat it as "fix the toolchain, then re-run".

## 5. Baseline and delta

The question is not "does this repo have historical junk" but **"did this commit make
it worse"**.

```yaml
baseline: {complexity: 1200, duplication_pct: 7.2, warnings: 34, dead_code: 18}
current:  {complexity: 1210, duplication_pct: 7.0, warnings: 32, dead_code: 15}
delta:    {complexity: +10,  duplication_pct: -0.2, warnings: -2,  dead_code: -3}
```

Invariant: `Code Health After >= Before`. Historical debt may remain; unjustified new
debt blocks. `classify_against_baseline` splits findings into new / resolved /
pre-existing and sets `historical=True` on the last group. Markdown reports render the
two groups in separate sections so reviewers never confuse old debt with this commit.

## 6. Accepted risk

```yaml
accepted_risks:
  - finding_id: CHM-000123
    reason: "legacy protocol kept for partner compatibility"
    owner: "payments-team"
    expires: 2026-12-31
  - rule_id: "CHM-JAVA-NAT-TODO-MARKER"
    reason: "tracked in JIRA-4711"
    owner: "platform"
    expires: 2026-06-30
```

Rules:

* Matching is by exact `finding_id` or by `rule_id` glob.
* **An expired entry stops suppressing.** The finding reappears as a blocker.
* There is no permanent, global ignore. If a risk is permanent, it belongs in a rule
  change or in the baseline — with a visible decision.

## 7. Token discipline

| Risk | What the reviewer sees |
|---|---|
| LOW | diff + current file |
| MEDIUM | + direct references |
| HIGH | + call graph, tests, config, business rules |
| CRITICAL | + full relevant slice |

Additional guards: `token.max_context_files` (default 12) caps the pack;
`token.max_file_bytes_for_llm` truncates large files around the changed lines;
generated files are summarised instead of inlined when
`token.exclude_generated_from_llm` is set; every payload passes the secret filter
first. Caching is keyed on tool version + repo head + file hash + rule version +
config hash, so an unchanged file never gets re-analysed.
