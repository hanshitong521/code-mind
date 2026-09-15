# Authoring a rule

A rule without a negative case is not a rule — it is a false-positive generator. The
spec's hard limits are **MEDIUM+ false positives ≤ 8 %** and **HIGH+ ≤ 3 %**, so every
rule you add must carry proof that it stays quiet on legitimate code.

## 1. Choose the layer

| Layer | Use when | Where |
|---|---|---|
| Built-in analyzer | the pattern is provable from source text/structure and you need it even without a JVM or Semgrep | `src/chm/analyzers/native_java.py`, `native_vue.py` |
| PMD ruleset | PMD already ships the rule and its thresholds can be tuned | `rules/java/pmd-ruleset.xml` |
| Semgrep rule | project-specific pattern, multi-language, needs AST-ish matching | `rules/{common,java,vue2,...}/*.yml` |
| Knip | unused JS/TS files, exports, dependencies | configuration only |
| Reviewer persona | judgement is genuinely required (semantics, intent, architecture) | `src/chm/reviewers/personas.py` |

Prefer the lowest layer that can prove the claim. A reviewer persona must never be used
to assert something a deterministic tool could have proven.

## 2. Rule id convention

```
CHM-<LANG>-<SOURCE>-<NAME>

CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD     built-in analyzer
CHM-JAVA-PMD-UNUSEDPRIVATEMETHOD       PMD
CHM-JAVA-SB-OS_OPEN_STREAM             SpotBugs
CHM-JAVA-CPD-DUP                       CPD
CHM-JAVA-SG-TX-REMOTE-CALL             Semgrep
CHM-JS-KNIP-UNUSED-DEPENDENCY          Knip
CHM-REV-<PERSONA>-<NNN>                semantic reviewer
```

`rule_id` is part of the public contract: it appears in baselines, accepted-risk globs
and regression anchors. Renaming one is a breaking change.

## 3. Checklist for a new built-in rule

1. **Pick the dimension.** Exactly one of the 20 `Category` values. If you cannot pick
   one, the rule is doing too much.
2. **Pick the severity ceiling.** Ask: if this is wrong, does it lose data / money /
   availability? `CRITICAL`. Cross-module correctness or hot path? `HIGH`. Local
   maintainability? `MEDIUM`. Cosmetic? `LOW`.
   Never let a pattern-only rule claim `PROVEN` performance.
3. **Write the match condition** as an explicit, commented predicate. Reuse
   `util.strip_comments_and_strings()` so comments and string literals cannot trigger it.
4. **Write the suppression list.** This is the part people skip and the part that
   decides whether the tool is usable. For each match, ask: *what legitimate code looks
   exactly like this?* Encode each answer as a guard.
5. **Only report on changed lines.** Use `ctx.is_changed_line(path, line)` unless
   `ctx.options["whole_file"]` is set. This is both the token and the false-positive
   control.
6. **Emit structured evidence.** Put the matched snippet, the line and the reason in
   `RawFinding.detail` / `RawFinding.extra`. A `HIGH` without evidence will be rejected
   by the schema guard anyway.
7. **Be deterministic.** No randomness, no iteration over a `set`, no time. Two runs
   must produce identical `stable_json`.
8. **Add a positive case and a negative case** under `test/adversarial/`.
9. **Record the suppression rationale** in a comment above the rule, naming the
   counter-example it protects.

### Skeleton

```python
_CHM_JAVA_MY_RULE = re.compile(r"\.\.\.")

# CHM-JAVA-NAT-MY-RULE  (MEDIUM / COMPLEXITY)
#   Hit : <the exact shape that is a defect>
#   Miss: <the legitimate shape that looks identical>
#         - <guard 1: why it is legitimate>
#         - <guard 2>
def _check_my_rule(rel: str, lines: list[str], skeleton: list[str],
                   cfg: Config) -> list[RawFinding]:
    out: list[RawFinding] = []
    for i, line in enumerate(skeleton, start=1):
        if not _CHM_JAVA_MY_RULE.search(line):
            continue
        if _is_legitimate(lines, i):          # <- suppression, never optional
            continue
        out.append(RawFinding(
            provider="native-java",
            rule_id="CHM-JAVA-NAT-MY-RULE",
            message="...",
            file=rel, start_line=i, end_line=i,
            category=Category.COMPLEXITY,
            severity=Severity.MEDIUM,
            confidence=0.7,
            detail="matched: " + line.strip(),
            extra={"reason": "...", "line": i},
        ))
    return out
```

## 4. Adding a PMD rule

**Verify the rule name against the jar first.** A typo aborts the whole PMD run and the
gate silently loses all Java evidence.

```bash
jar xf pmd-bin-6.55.0/lib/pmd-java-6.55.0.jar category/java/
grep -o 'name="[A-Za-z0-9]*"' category/java/design.xml
```

Then:

1. Add `<rule ref="category/java/<cat>.xml/<RuleName>"/>` to
   `rules/java/pmd-ruleset.xml`.
2. **Add the rule to `RULE_CATEGORY` in `src/chm/adapters/pmd.py`.** If you forget, the
   rule falls back to its ruleset name and lands in a nonsense dimension (this is how
   `LooseCoupling` once ended up as `DEAD_CODE`).
3. Mirror the threshold with `complexity_thresholds` in `.codehealth.yml` so the
   external tool and the built-in analyzers do not contradict each other.
4. Run the ruleset for real and confirm zero load errors:
   ```bash
   java -cp "<pmd-lib>/*" net.sourceforge.pmd.PMD \
        -d <dir> -R rules/java/pmd-ruleset.xml -f xml -r out.xml --no-cache
   ```
5. `test/unit` includes a cross-check that every `<rule ref>` in the ruleset has an
   explicit `RULE_CATEGORY` entry (or a correct ruleset-level fallback).

## 5. Adding a Semgrep rule

Every rule needs `positive case`, `negative case`, and `autofix case` when it has one —
a rule with only a positive case is rejected in review.

```yaml
rules:
  - id: chm.java.my-rule
    languages: [java]
    severity: WARNING
    message: >-
      One sentence a developer can act on: what is wrong, and what to do instead.
    metadata:
      chm_category: ERROR_HANDLING
      chm_rule: CHM-JAVA-SG-MY-RULE
      confidence: MEDIUM
    patterns:
      - pattern-either: [...]
      - pattern-not: [...]      # <- the negative case, in-rule
```

Validate before committing:

```bash
semgrep --validate --config rules/
semgrep --config rules/ --test test/fixtures/semgrep/
```

> On Windows Semgrep has no official build. The shipped rules are schema-correct but
> have not been executed here; `codehealth probe` reports the provider as unavailable
> and the gate records a tool gap instead of pretending the rules ran.

## 6. Adding a reviewer persona rule

Persona rules live in `src/chm/reviewers/personas.py` and are heuristics, not proofs.
Therefore:

* `confidence` must stay in the honest heuristic band (0.4 – 0.7). Never 0.9.
* Severity is capped at `MEDIUM`; the normalizer additionally caps semantic-only
  findings at `MEDIUM`.
* Performance personas may only emit `SUSPECTED`.
* Every persona rule list must contain: *lower confidence when evidence is missing*,
  and *do not demand an abstraction just because duplication exists*.

## 7. Regression anchors

Whenever a real false negative is found in the wild, add it to
`test/adversarial/test_false_negative.py` with the template below and never remove it.

```yaml
id: CHM-FN-042
category: CONCURRENCY
priority: HIGH
source: "production incident 2026-08-xx"
action: "detect semaphore acquire outside try"
expected: "finding emitted, severity >= HIGH"
regression_reason: "was missed because release() appeared in a nested finally"
added: 2026-09-15
```

## 8. Review gates for a rule change

A rule change is only merged when all of the following hold:

- [ ] positive case passes
- [ ] negative case stays silent
- [ ] determinism check passes (3 identical runs)
- [ ] false-positive suite still under target
- [ ] false-negative suite still above target
- [ ] rule id, category and severity documented in `docs/finding-schema.md` if new
- [ ] the report renders the new finding readably
