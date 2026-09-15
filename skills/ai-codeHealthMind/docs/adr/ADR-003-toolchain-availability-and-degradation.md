# ADR-003 — Built-in deterministic analyzers, and honest degradation

* Status: **accepted**
* Date: 2026-09-15
* Deviation from spec: additive (§4 names external tools only; §28 requires adapters)

## Context

The specification's evidence layer is built from external tools: PMD, CPD, SpotBugs,
Semgrep, Knip. The environment this project was developed and is expected to run in
shows how brittle that assumption is:

| Tool | Availability on the reference host (Windows) | Real reason |
|---|---|---|
| `javac` | available (JDK 8) | — |
| PMD 6.55 / CPD | available once the distribution is unpacked | needs a JVM; PMD 7 would need JDK 11+ |
| SpotBugs 4.5.3 | available once unpacked | needs compiled classes; 4.6+ needs JDK 11+ |
| Knip 5.88 | available via npm | — |
| Semgrep | **not installable** | no official Windows build |
| OpenRewrite | **not runnable** | Maven on this host fails to start; no standalone CLI for Java 8 |
| Maven / Gradle | **broken** | `mvn -v` → `ClassNotFoundException: org.codehaus.plexus.classworlds.launcher.Launcher` |

If the gate's only evidence sources are those tools, then on this host the gate would
have *nothing* to say about Java code — and "nothing to say" would be reported as a
passing build. That is precisely the failure mode the spec forbids (§65 禁止"假绿").

## Decision

Two complementary changes.

### 1. Built-in deterministic analyzers

`src/chm/analyzers/native_java.py` and `native_vue.py` implement the
**pattern-provable subset** of the sixteen dimensions in pure Python, with no external
process and no model:

* dead code with real reference counting and dynamic-entry suppression
* normalised-token duplication detection (independent of CPD)
* error handling (`catch {}`, `catch → return null`, swallow-and-report-success,
  unbounded retry)
* resource safety (unclosed stream, executor per call)
* concurrency (mutable singleton state, semaphore leak, lock-scope remote call,
  double-check without `volatile`)
* database (`UPDATE`/`DELETE` without `WHERE`, N+1, remote call in transaction)
* complexity (method length, cyclomatic, nesting, class size, parameter list)
* over-engineering (single-impl interface, pass-through wrapper, speculative factory)
* compatibility junk, defensive junk, testability

They are ordinary `EvidenceProvider`s, so their output flows through the same
normalisation, dedup and validation pipeline as PMD's. When PMD is also present, the
deduplicator merges the two into one finding with two evidence sources — which is
strictly better evidence than either alone.

**Every rule carries an explicit suppression list**, and the false-positive suite
(`test/adversarial/test_false_positive.py`) is the acceptance criterion. A rule that
cannot stay quiet on legitimate code does not ship.

### 2. Degradation is a first-class outcome

* Every adapter returns a `ProviderResult` with a `ToolError` on failure — never an
  exception, never an empty-but-successful result.
* `evidence_gap=True` marks failures that invalidate a HIGH/CRITICAL conclusion.
* `gate.evaluate_gate` converts an evidence gap into `UNKNOWN` (exit code 3), which is
  explicitly **not** a pass.
* `codehealth probe` shows, per tool, whether it is available, its real version, and
  the real reason it is unavailable.

## Consequences

**Good**

* The gate is useful on a host with no JVM and no Semgrep.
* Cross-tool agreement (built-in + PMD) raises confidence for free.
* "Cannot verify" is a visible, actionable state instead of a silent green.

**Bad / accepted costs**

* The built-ins are not a parser. They use brace balancing over a
  comment/string-stripped skeleton, so deeply nested or macro-heavy code can evade
  them. This is a **recall** limitation, not a false-positive risk, and the golden
  suite reports real recall numbers rather than claims.
* Duplication detection is re-implemented rather than delegated to CPD. Two
  implementations must agree; the deduplicator makes disagreement visible instead of
  hiding it.
* More code to maintain than a pure adapter layer. Mitigated by keeping each rule
  small, self-contained and covered by a positive **and** negative case.

## Verification

* `codehealth probe` on the reference host reports PMD/CPD/SpotBugs/Knip as available
  with real version strings, and Semgrep/OpenRewrite as unavailable with the real
  reason.
* `test/integration/test_fault_injection.py` asserts that no failure path yields
  `PASS`.
* `test/golden/` reports real precision/recall per fixture, including the cases the
  built-ins miss.
