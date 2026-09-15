# CodeHealthMind

**A merge gate that stops AI-written code from quietly importing long-term maintenance cost.**

CodeHealthMind is not a code review bot and not a Sonar replacement. It answers one
question about a change set: *did this make the codebase worse, and can we prove it?*

It detects and grades junk code, dead code, duplication, wrong abstractions,
over-engineering, complexity growth, correctness/perf/concurrency/resource risks,
pointless compatibility layers and testability regressions — then blocks, warns or
passes the merge.

```
AI writes code
      │
      ▼
CodeHealthMind          ← you are here: is the system getting dirty?
      │
      ▼
TestMind                ← does it actually work?
      │
      ▼
Evidence Validator      ← is the evidence real?
      │
      ▼
   PASS
```

## Design principles

| Principle | Meaning |
|---|---|
| **Evidence first** | Every HIGH/CRITICAL finding carries deterministic evidence (a real tool hit, a real symbol reference, real compiler output). "I think this looks wrong" can never block a merge. |
| **AI ≠ evidence** | A model may explain, judge intent, spot a wrong abstraction and propose a repair. It may not *prove* that code is dead, slow or unreachable. |
| **Delete first** | Remove what is not needed → use the language/stdlib → use what the project already has → simplify → only then add abstraction. |
| **Wrong abstraction > duplication** | Duplication alone never triggers an abstraction demand. Seven questions must be answered first. |
| **Context isolation** | The reviewer never sees the author's rationale. The payload is fingerprinted so isolation is provable, not asserted. |
| **No fake green** | A missing tool degrades to `TOOL_DEGRADED`. If a HIGH/CRITICAL verdict depended on it, the gate is `UNKNOWN` — never `PASS`. |

## Install

Nothing to install. Python ≥ 3.10, standard library only (see
[ADR-001](docs/adr/ADR-001-language-and-dependencies.md)).

```bash
git clone <this repo>
cd skills/ai-codeHealthMind
python codehealth.py init          # writes .codehealth.yml
python codehealth.py probe         # shows which real tools are available
python codehealth.py review --diff
```

The external analyzers are optional and auto-detected. Point the engine at them with
environment variables or `.codehealth.yml`:

```bash
export CHM_JAVA_HOME=/path/to/jdk
export CHM_PMD_HOME=/opt/pmd-bin-6.55.0
export CHM_SPOTBUGS_HOME=/opt/spotbugs-4.5.3
export CHM_KNIP_BIN=/opt/knip/node_modules/.bin/knip
export CHM_SEMGREP_BIN=/usr/local/bin/semgrep
```

## Usage

```bash
# Review targets
codehealth review --diff                 # working tree vs HEAD   (default)
codehealth review --staged               # staged change set
codehealth review --commit abc1234       # one commit
codehealth review --range main..HEAD     # a range
codehealth review --file src/A.java      # one file
codehealth review --repo                 # whole repository

# Output
codehealth review --diff --format console
codehealth review --diff --format json    -o report.json
codehealth review --diff --format markdown -o report.md
codehealth review --diff --format sarif    -o report.sarif

# Repair loop
codehealth fix --diff                    # plan only, never edits
codehealth fix --diff --apply            # apply provably safe repairs
codehealth verify --previous <run-id>    # re-run the gate and diff the result

# Explain / baseline / probe
codehealth explain CHM-000123
codehealth baseline --show
codehealth baseline --update
codehealth probe
```

### Exit codes

| Code | Meaning |
|---:|---|
| 0 | `PASS` or `WARN` |
| 1 | `BLOCK` |
| 2 | tool or configuration error |
| 3 | `UNKNOWN` — evidence incomplete for a HIGH/CRITICAL verdict |

### Console output

```
CodeHealthMind 1.0.0

Changed files: 7
Findings: 6
  Critical: 0
  High: 1
  Medium: 3
  Low: 2

Gate: BLOCK

Top issue:
CHM-000103 HIGH
CouponService.java:182
Remote call inside transaction + retry
Evidence: source + transaction annotation + retry wrapper
```

## What it looks at

Sixteen mandatory dimensions, four extensions:

`DEAD_CODE` · `DUPLICATION` · `WRONG_ABSTRACTION` · `OVER_ENGINEERING` · `COMPLEXITY` ·
`LARGE_METHOD` · `LARGE_CLASS` · `DEPENDENCY_GROWTH` · `COMPATIBILITY_JUNK` ·
`DEFENSIVE_JUNK` · `ERROR_HANDLING` · `CONCURRENCY` · `RESOURCE_SAFETY` · `DATABASE` ·
`PERFORMANCE` · `TESTABILITY` · `API_SURFACE_GROWTH` · `CONFIG_INFLATION` ·
`BOILERPLATE` · `ARCHITECTURE_DRIFT`

## Evidence providers

| Provider | Kind | Real invocation | Degrades to |
|---|---|---|---|
| `native-java` / `native-vue` | built-in | pure Python, deterministic | — |
| `javac` | external | `javac` from the JDK | compile skipped |
| `pmd` | external | `java -cp <pmd-lib> net.sourceforge.pmd.PMD -R rules/java/pmd-ruleset.xml` | `MISSING` |
| `cpd` | external | `java -cp <pmd-lib> net.sourceforge.pmd.cpd.CPD` | `MISSING` |
| `spotbugs` | external | `java -jar spotbugs.jar -textui -xml:withMessages` | `UNSUPPORTED` when no compiled classes |
| `semgrep` | external | `semgrep --config rules/ --json` | `MISSING` |
| `knip` | external | `node <knip>/bin/knip.js --reporter json` | `MISSING` |
| `openrewrite` | repair only | Maven/Gradle plugin, dry-run first | `MISSING` |
| `test-runner` | external | whatever `tools.test.args` says | `UNSUPPORTED` |

Every adapter reports its **real command line**, duration, version and failure kind.
Nothing is mocked, and a provider that did not run is never counted as clean.

### Unsupported languages are not a pass

If every changed source file is written in a language no provider covers — Python, Go,
Rust, Kotlin, Scala, C#, PHP, Ruby, C/C++, shell — the gate returns `UNKNOWN`
(exit code 3), not `PASS`:

```
Gate: UNKNOWN

Why this verdict:
  - tool degraded: coverage UNSUPPORTED (no evidence provider covers the changed
    languages (python); 1 source file(s) were not analysed. ...)
  - evidence gap affects HIGH/CRITICAL verification -> UNKNOWN
    (a missing tool is not evidence of absence)
  UNKNOWN is not a pass. Fix the toolchain above, then re-run.
```

Reporting a clean gate for code nobody analysed would be the worst possible failure
mode for a gate, so it is structurally prevented rather than left to convention.

## Scoring and the gate

Ten weighted dimensions totalling 100 (Correctness 20, Simplicity 15, Maintainability 15,
Duplication 10, Complexity 10, Dead Code 10, Performance 5, Concurrency 5,
Resource Safety 5, Testability 5). Every deduction names the finding that caused it.

A hard gate overrides the score entirely — a CRITICAL can never be averaged away:

```
compile fail / test fail                 → BLOCK
CRITICAL (not accepted_risk)             → BLOCK
HIGH     (not accepted_risk)             → BLOCK
new MEDIUM > gates.max_new_medium        → BLOCK
new MEDIUM ≤ threshold                   → WARN
LOW only                                 → PASS
tool degraded, no evidence gap           → WARN
tool degraded, gap blocks HIGH/CRITICAL  → UNKNOWN
```

## Baseline: historical debt is allowed, new debt is not

```bash
codehealth baseline --update     # freeze today's debt
```

From then on the gate compares against it: pre-existing findings are reported as
historical, and only *new* debt can block. `accepted_risks` entries carry an `expires`
date and stop suppressing the finding once they expire.

## Repository layout

```
codehealth.py            zero-install entry point
src/chm/
  schema.py              Finding model + lifecycle (spec §8, §9)
  contracts.py           ScanContext / ProviderResult / EvidenceProvider
  config.py              strict .codehealth.yml loader
  core/
    orchestrator.py      the 12-step workflow
    normalizer.py        RawFinding -> Finding, stable ids
    dedup.py             merge the same issue from N providers into 1
    evidencevalidator.py red-team validation, severity honesty
    riskrouter.py        LOW/MEDIUM/HIGH/CRITICAL -> reviewers + validator
    score.py  gate.py    scoring and merge verdict
    baseline.py  cache.py  ledger.py  repair.py
  context/
    gitctx.py            six review targets, real git
    symbols.py           symbol index + dynamic-entry detection
    packer.py            minimal context, risk-based expansion
    secretfilter.py      scrub before anything reaches a model
  adapters/              real CLI wrappers
  analyzers/             built-in deterministic rules (Java, Vue)
  reviewers/             5 personas + isolation-proving runtime
  reports/               console / json / markdown / sarif
rules/                   PMD ruleset (verified) + Semgrep rules
docs/                    architecture, schema, risk model, rule authoring, ADRs
test/                    fixtures, golden, adversarial, benchmark
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — pipeline, module boundaries, data flow
- [docs/finding-schema.md](docs/finding-schema.md) — the Finding contract
- [docs/risk-model.md](docs/risk-model.md) — severities, scoring, gate matrix
- [docs/rule-authoring.md](docs/rule-authoring.md) — how to add a rule (positive + negative + autofix case)
- [docs/adr/](docs/adr/) — architecture decision records, including deviations from the spec

## Licence

MIT. Third-party tools are invoked as external processes and are not vendored; see
[LICENSE](LICENSE) for the per-tool licence table.
