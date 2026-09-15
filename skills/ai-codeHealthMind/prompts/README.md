# Prompts

The **executable** reviewer prompts live in code and are the single source of truth:

* `src/chm/reviewers/prompt.py` — `SPEC_SECTION_15_RULES`, `REVIEWER_SYSTEM_RULES`,
  `OUTPUT_CONTRACT`, `build_reviewer_prompt`, `build_validator_prompt`,
  `context_payload`, `payload_fingerprint`, `assert_isolation`
* `src/chm/reviewers/personas.py` — the five personas and their rules

Do not copy them here. A second copy drifts, and a drifted prompt is a silent change to
the gate's behaviour.

## Files in this directory

| File | Purpose |
|---|---|
| `team-rules.md` | Optional project/team rules appended to every reviewer prompt. Edit this, not the code, when you need to teach the reviewer something organisation-specific. |

## Rules for editing prompts

1. **Never remove** the eight rules of spec §15 or the enforcement invariants. They are
   what makes "AI is not evidence" and context isolation mechanical rather than
   aspirational.
2. The output contract is strict JSON. If you change it, change
   `src/chm/reviewers/runtime.py`'s parser in the same commit and re-run
   `test/unit/test_reviewers*`.
3. Anything you add must not let the reviewer see the author's rationale. Context
   isolation is verified by `assert_isolation` and by
   `test/adversarial/test_context_isolation.py`; a prompt that asks the reviewer to
   "consider the author's intent" breaks the gate's core guarantee.
4. A rule that cannot be evaluated from the payload is noise. Prefer fewer, checkable
   rules.
