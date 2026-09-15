# Changelog

All notable changes to CodeHealthMind are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-15

First implementation of the V1.0 specification
(`CodeHealthMind_Development_Spec_V1_99` + `CodeHealthMind_Test_and_Acceptance_Spec_V1_99`).

### Added

**Core engine**
- `Finding` standard model with the 20 audit categories, 4 severities, the
  13-state lifecycle and the five schema guards (CHM-SCHEMA-001..005).
- Deterministic normalisation: stable `CHM-NNNNNN` ids ordered by
  file/line/rule, so two runs over the same input produce byte-identical
  reports.
- Finding deduplication that merges the same issue reported by several
  providers into one finding with several evidence sources.
- Score engine with the ten weighted dimensions of the specification and the
  hard-gate rules (a CRITICAL can never be offset by a high total).
- Merge gate producing `PASS` / `WARN` / `BLOCK` / `UNKNOWN` with the
  documented exit codes `0 / 1 / 2 / 3`.
- Baseline/delta model: historical debt is allowed, unjustified new debt is not.
- Run cache keyed on tool version, repo head, file hash, rule version and
  config hash.
- Observability ledger recording tool durations, token usage, cache hit ratio,
  dedup ratio and the final gate for every run.

**Evidence**
- Real CLI adapters for PMD 6.55, CPD, SpotBugs, Semgrep, Knip, OpenRewrite,
  `javac` and an arbitrary test runner. Each adapter reports missing tools,
  timeouts, non-zero exits, malformed and partial output as structured
  `ToolError`s instead of failing silently.
- Built-in deterministic analyzers for Java and Vue/JS covering the
  pattern-provable part of the sixteen audit dimensions, each with explicit
  false-positive suppression.
- Symbol index with real dynamic-entry detection (reflection, Spring/IOC, SPI,
  MyBatis XML, RPC, MQ, dynamic import) so dead-code findings cannot be turned
  into a code-deleting machine.

**Review**
- Five reviewer personas with context isolation: the reviewer payload is
  fingerprinted and provably excludes the author's rationale.
- Risk router: LOW/MEDIUM/HIGH/CRITICAL selects one or two reviewers plus the
  evidence validator, and records why.
- Evidence validator implementing the red-team cases RV-001..RV-003 plus the
  "semantic-only findings cannot claim HIGH" rule. Reviewer disagreement is
  resolved by validation, never by majority vote.

**Interfaces**
- `codehealth` CLI: `review`, `fix`, `verify`, `explain`, `baseline`, `probe`,
  `init`.
- Six review targets: `--diff`, `--staged`, `--commit`, `--range`, `--file`,
  `--repo`.
- Report formats: console, JSON, Markdown, SARIF 2.1.0.
- `.codehealth.yml` with strict validation, accepted-risk entries with enforced
  expiry, and a shipped PMD rule set verified against PMD 6.55.0.

**Safety**
- Secret filter applied to every context payload before it can reach a model.
- Safe-repair engine that only ever edits provably mechanical findings and
  re-verifies the target line before touching it.

### Known limitations

- Semgrep and OpenRewrite are unavailable on Windows; their adapters report
  `UNAVAILABLE` with the real reason and the gate records a tool gap.
- SpotBugs requires compiled classes; without a compile step it reports
  `UNSUPPORTED` rather than pretending to have scanned.
- The `rule` reviewer backend is deterministic local heuristics. It is labelled
  as such in every report and must not be mistaken for an independent model.
- `rules/*/team-*.yml` (Semgrep) are schema-correct but have not been executed
  against a real Semgrep binary in the development environment.
