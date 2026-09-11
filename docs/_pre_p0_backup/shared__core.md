# AI programming stack — shared core

- **Layers:** design (WHAT/HOW choice) → code → debug → requirement gate → concise output.
- **Evidence:** Explore before ask; no invented business rules (UNKNOWN until verified).
- **Handoff:** Machine-checkable YAML; schema in `handoff-schema.yaml`; validate with `scripts/validate_handoff.py`.
- **Verification:** Risk floors in `verification-policy.yaml`; escalate gates by blast radius.
- **Domain packs:** Optional overlays (`domain-packs/`) — never replace shared contracts.
