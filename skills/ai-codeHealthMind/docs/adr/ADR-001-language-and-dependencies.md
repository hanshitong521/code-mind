# ADR-001 — Implementation language and dependency policy

* Status: **accepted**
* Date: 2026-09-15
* Deviation from spec: yes (§6 lists `package.json / pyproject.toml`; §28 shows a
  TypeScript interface signature)

## Context

The specification's recommended layout (§6) allows either a Node or a Python project,
but §28 sketches the adapter interface in TypeScript:

```ts
interface EvidenceProvider {
  name(): string;
  supports(ctx: ScanContext): boolean;
  scan(ctx: ScanContext): Promise<RawFinding[]>;
  version(): Promise<string>;
}
```

Several reference projects are TypeScript (Alibaba OpenCodeReview). The surrounding
`code-mind` control plane, however, is Python-script based (`scripts/*.py`,
zero third-party deps, run with a pinned interpreter).

The gate must run in CI, in a pre-commit hook, and on a developer laptop. Every
dependency it carries is a dependency the gate's *users* must install before they can
be blocked by it. A gate that fails to start is worse than no gate, because a broken
gate is indistinguishable from a passing one.

## Decision

Implement the engine in **Python 3.10+ using only the standard library**.

* The adapter interface is realised as an ABC (`chm.contracts.EvidenceProvider`) with
  exactly the four members of the spec's interface: `name`, `version()`,
  `supports(ctx)`, `scan(ctx) -> ProviderResult`. The async signatures become
  synchronous; parallelism is handled once, centrally, in the orchestrator's thread
  pool, which keeps every adapter simple and deterministic.
* Node is still used — as a *runtime for a real tool*, not as a dependency of the
  engine. The Knip adapter shells out to `node <knip>/bin/knip.js`.
* `pyproject.toml` declares `dependencies = []`. The only optional extra is `PyYAML`,
  and only because it improves config parsing; the engine ships
  `chm/yamlmini.py` and works without it.

## Consequences

**Good**

* `git clone && python codehealth.py review --diff` works with no install step.
* No supply-chain surface in the gate itself.
* Matches the surrounding toolchain, so `code-mind/scripts/*` and this project share
  conventions and a pinned interpreter.
* Trivially embeddable: the whole engine is importable as a package.

**Bad / accepted costs**

* No static typing enforcement beyond annotations; mitigated by `dataclasses` and
  explicit validation (`Finding.validate_schema`).
* Java/TS parsers are not available, so the built-in analyzers use deterministic
  lightweight parsing (brace balancing + regex over a comment/string-stripped
  skeleton) instead of a real AST. This is documented as a limitation and is the
  reason every built-in rule carries an explicit suppression list.
* Contributors who expect a TypeScript codebase must read `src/chm/` instead.

## Verification

* `pyproject.toml` has `dependencies = []`.
* `test/unit` fails if any `src/chm/**` module imports a third-party package other than
  the optional `yaml` shim in `chm/config.py`.
