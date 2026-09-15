<!--
  Team rules appended verbatim to every reviewer prompt.

  Leave this file empty (or delete its content) to append nothing.
  Rules are read at prompt-build time; the file is looked up next to
  `src/chm/reviewers/prompt.py` (../../prompts/team-rules.md).

  Good rule:  checkable from the payload, names a concrete pattern, states what to do.
  Bad rule:   "be careful", "think about maintainability", "prefer clean code".

  Example:

  - Every new @Transactional method must declare a propagation mode; flag any that
    rely on the default when they also perform an external call.
  - New public API in this repository must be added to `docs/api.md`; a missing entry
    is a MEDIUM finding under API_SURFACE_GROWTH.
-->
