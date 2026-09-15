# ADR-002 — How reference projects are used

* Status: **accepted**
* Date: 2026-09-15

## Context

The specification (§4) names eight reference projects and says explicitly:

> 如果某参考项目许可证不适合直接拷贝实现，采用 CLI 调用 / Adapter

The available local copies under `资料--22/` are:

| Project | Licence (upstream) |
|---|---|
| Ponytail | MIT |
| Alibaba OpenCodeReview | Apache-2.0 |
| open-code-review | MIT |
| PMD | BSD-style |
| SpotBugs | LGPL-2.1 |
| Semgrep | LGPL-2.1 |
| OpenRewrite | Apache-2.0 |
| Knip | ISC |

LGPL in particular makes copying source into this MIT project a licence problem, and
vendoring PMD/SpotBugs/Semgrep would also make the gate enormous and version-fragile.

## Decision

**No source code is copied from any reference project.** Each is used in exactly one
of two ways:

1. **External process.** PMD, CPD, SpotBugs, Semgrep, Knip, OpenRewrite and `javac` are
   invoked as command line programs. We parse their public output formats (PMD XML,
   SpotBugs XML, Semgrep JSON, Knip JSON, compiler stderr). Because they are separate
   processes consumed over their documented CLI, their licences do not propagate.
   This is also the spec's own requirement ("必须使用 Adapter，不耦合 PMD API").
2. **Design influence only.** Ponytail, Alibaba OpenCodeReview and open-code-review
   inform the *design*, not the code:

   | Source | What was borrowed | Where it landed |
   |---|---|---|
   | Ponytail | Delete First, YAGNI, native/stdlib-first, single-caller abstraction, wrapper inflation, config inflation | `docs/rule-authoring.md`, `core/normalizer.decide_repair`, the `simplicity` persona |
   | Alibaba OpenCodeReview | Review Target Resolver, workspace/diff/commit review modes, structured findings | `context/gitctx.py` (six targets), `schema.Finding` |
   | open-code-review | independent reviewer personas, multi-reviewer synthesis, disagreement handling | `reviewers/personas.py`, `core/riskrouter.py`, `core/evidencevalidator.py` |

What is deliberately **not** borrowed from Ponytail: treating line-count reduction as a
goal, and excluding correctness/safety/performance from scope. CodeHealthMind's whole
point is that removing code is only correct when it is provable.

## Consequences

**Good**

* MIT licence stays clean; the per-tool licence table in `LICENSE` is accurate.
* Tools can be upgraded independently; no vendored fork to maintain.
* A missing tool degrades honestly instead of breaking the build.

**Bad / accepted costs**

* Output parsing is version-sensitive. Mitigation: each adapter probes the real version,
  caches on `tool-version` (§14.3), and reports `MALFORMED_OUTPUT` rather than crashing
  when a format shifts.
* Some tool capabilities are not reachable through the CLI (e.g. custom PMD rules
  loaded programmatically). Accepted; the shipped ruleset covers what we need.
* No AST access from external tools for cross-file reasoning; the built-in symbol index
  fills that gap for reference counting and dynamic-entry detection.

## Verification

* `git log --diff-filter=A --numstat` shows no file copied from a reference project.
* `LICENSE` documents how each tool is driven and under which licence.
