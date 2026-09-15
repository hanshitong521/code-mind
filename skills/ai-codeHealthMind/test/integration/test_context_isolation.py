"""Spec §19 -- context isolation between the writer and the reviewer.

The writer of the change knows *why* it did something; the reviewer must not.
That is not a style preference, it is the mechanism that stops "the author said
it was necessary" from being accepted as evidence.  The spec demands that the
property be *mechanical*, so it is proved here rather than asserted:

* the pack built for a normal review (mode A) must not contain the writer's
  rationale -- not in any field, not after serialisation;
* the pack built on an explicit caller opt-in (mode B) must contain it;
* the two packs must have **different fingerprints**, which is what lets a
  reviewer record "which context did you actually see" in the ledger;
* and the isolation check must say so in both directions -- clean for A,
  a detected leak for B.

The rationale used throughout is the exact one from the task: the author
claims "必须用 Factory 才能扩展" while the repository contains exactly one
implementation, i.e. a rationale that a reviewer might otherwise have deferred
to.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from helpers import CHMTestCase, changed_file, hunk, make_config, make_ctx  # noqa: F401

from chm.context.packer import build_context_pack
from chm.context.secretfilter import scrub
from chm.contracts import ReviewMode
from chm.reviewers.prompt import assert_isolation, context_payload, payload_fingerprint
from chm.util import stable_json

# --------------------------------------------------------------------------
# the writer's rationale -- the sentence a reviewer must never be handed
# --------------------------------------------------------------------------

KEY_SENTENCE = "这里必须用 Factory 才能扩展，否则每新增一种支付方式都要改 switch 分支"
FAKE_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
WRITER_RATIONALE = (
    f"{KEY_SENTENCE}。"
    f"顺便记一下联调用的临时凭证 AKIAIOSFODNN7EXAMPLE 不要提交。"
)

PAYMENT_JAVA = """\
package com.shop.pay;

public class PaymentService {
    public String pay(String channel, long cents) {
        switch (channel) {
            case "alipay":
                return "alipay:" + cents;
            case "wechat":
                return "wechat:" + cents;
            default:
                throw new IllegalArgumentException("unknown channel: " + channel);
        }
    }
}
"""

REQUIREMENT = "需求：支付渠道需要支持配置化扩展，不得写死渠道枚举。"


class IsolationBase(CHMTestCase):
    """Builds one real repository and one real context pack on top of it."""

    def project(self) -> Path:
        return self.temp_repo(
            {
                "pom.xml": "<project><modelVersion>4.0.0</modelVersion></project>\n",
                "src/main/java/com/shop/pay/PaymentService.java": PAYMENT_JAVA,
                "docs/requirements.md": "# 支付需求\n\n" + REQUIREMENT + "\n",
            }
        )

    def build_pack(self, *, include_writer_rationale: bool, repo=None, risk: str = "HIGH"):
        repo = repo or self.project()
        ctx = make_ctx(
            repo,
            mode=ReviewMode.REPO,
            changed=[
                changed_file(
                    "src/main/java/com/shop/pay/PaymentService.java",
                    hunks=[hunk(4, 12)],
                    added_lines=12,
                )
            ],
            config=make_config(**{"token.max_context_files": 20}),
        )
        ctx.requirement_context = REQUIREMENT
        ctx.repo_files = [
            "pom.xml",
            "src/main/java/com/shop/pay/PaymentService.java",
            "docs/requirements.md",
        ]
        pack = build_context_pack(
            ctx,
            risk=risk,
            config=ctx.config,
            writer_rationale=WRITER_RATIONALE,
            include_writer_rationale=include_writer_rationale,
        )
        return ctx, pack


# --------------------------------------------------------------------------
# mode A: the default review context
# --------------------------------------------------------------------------


class ModeAWithholdsRationaleTest(IsolationBase):
    """§19 mode A -- the rationale is withheld and cannot be recovered."""

    def test_pack_has_no_rationale_field_populated(self):
        _ctx, pack = self.build_pack(include_writer_rationale=False)
        self.assertEqual(pack.writer_rationale, "")
        self.assertFalse(pack.writer_rationale_included)

    def test_serialised_pack_does_not_contain_the_sentence(self):
        _ctx, pack = self.build_pack(include_writer_rationale=False)
        blob = stable_json(pack.to_dict())
        self.assertNotIn(KEY_SENTENCE, blob)
        self.assertNotIn("Factory", blob)
        # ...and not a single substantive fragment of it either
        self.assertNotIn("才能扩展", blob)

    def test_payload_withholds_rationale_and_says_so(self):
        _ctx, pack = self.build_pack(include_writer_rationale=False)
        payload = context_payload(
            pack, include_writer_rationale=False, writer_rationale=WRITER_RATIONALE
        )
        self.assertNotIn(KEY_SENTENCE, payload)
        self.assertNotIn("才能扩展", payload)
        self.assertIn("withheld by context isolation", payload)
        self.assertNotIn("[AUTHOR RATIONALE -- explicitly supplied by the caller]", payload)

    def test_isolation_check_passes_for_mode_a(self):
        _ctx, pack = self.build_pack(include_writer_rationale=False)
        payload = context_payload(
            pack, include_writer_rationale=False, writer_rationale=WRITER_RATIONALE
        )
        ok, reason = assert_isolation(payload, WRITER_RATIONALE)
        self.assertTrue(ok, f"mode A leaked the rationale: {reason}")
        print(f"mode A isolation: ok={ok} reason={reason!r}")

    def test_withholding_does_not_empty_the_rest_of_the_context(self):
        """Isolation must drop the rationale, not the evidence a reviewer needs."""
        _ctx, pack = self.build_pack(include_writer_rationale=False)
        payload = context_payload(
            pack, include_writer_rationale=False, writer_rationale=WRITER_RATIONALE
        )
        self.assertIn("PaymentService.java", payload)
        self.assertIn("PaymentService", payload)  # the real code body
        self.assertIn("[REQUIREMENT]", payload)
        self.assertIn(REQUIREMENT, payload)  # the requirement *is* fair game
        self.assertGreater(len(payload), 200)

    def test_degraded_pack_still_withholds_rationale(self):
        """No pack at all is the most tempting moment to fall back to the author."""
        payload = context_payload(
            None, include_writer_rationale=False, writer_rationale=WRITER_RATIONALE
        )
        self.assertIn("UNAVAILABLE", payload)
        self.assertNotIn(KEY_SENTENCE, payload)
        ok, _reason = assert_isolation(payload, WRITER_RATIONALE)
        self.assertTrue(ok)


# --------------------------------------------------------------------------
# mode B: explicit caller opt-in
# --------------------------------------------------------------------------


class ModeBIncludesRationaleTest(IsolationBase):
    """§19 mode B -- the caller explicitly asked for the rationale."""

    def test_pack_carries_the_rationale_when_opted_in(self):
        _ctx, pack = self.build_pack(include_writer_rationale=True)
        self.assertTrue(pack.writer_rationale_included)
        self.assertIn(KEY_SENTENCE, pack.writer_rationale)
        self.assertIn(KEY_SENTENCE, stable_json(pack.to_dict()))
        self.assertIn("writer rationale included", pack.expansion_reason)

    def test_payload_contains_the_sentence(self):
        _ctx, pack = self.build_pack(include_writer_rationale=True)
        payload = context_payload(
            pack, include_writer_rationale=True, writer_rationale=WRITER_RATIONALE
        )
        self.assertIn(KEY_SENTENCE, payload)
        self.assertIn("[AUTHOR RATIONALE -- explicitly supplied by the caller]", payload)

    def test_isolation_check_flags_the_opt_in_as_a_leak(self):
        """The check is honest: an opted-in payload *does* contain the rationale."""
        _ctx, pack = self.build_pack(include_writer_rationale=True)
        payload = context_payload(
            pack, include_writer_rationale=True, writer_rationale=WRITER_RATIONALE
        )
        ok, reason = assert_isolation(payload, WRITER_RATIONALE)
        self.assertFalse(ok, "mode B should report the rationale as present")
        self.assertIn("leak", reason.lower())
        print(f"mode B isolation: ok={ok} reason={reason!r}")


# --------------------------------------------------------------------------
# the fingerprints differ -- the property the ledger depends on
# --------------------------------------------------------------------------


class FingerprintDivergenceTest(IsolationBase):
    """Two contexts a reviewer could have seen must not hash the same."""

    def test_pack_fingerprints_differ(self):
        repo = self.project()
        _ctx_a, pack_a = self.build_pack(include_writer_rationale=False, repo=repo)
        _ctx_b, pack_b = self.build_pack(include_writer_rationale=True, repo=repo)
        self.assertNotEqual(pack_a.fingerprint(), pack_b.fingerprint())
        self.assertRegex(pack_a.fingerprint(), r"^[0-9a-f]{64}$")

    def test_payload_fingerprints_differ(self):
        repo = self.project()
        _ctx_a, pack_a = self.build_pack(include_writer_rationale=False, repo=repo)
        _ctx_b, pack_b = self.build_pack(include_writer_rationale=True, repo=repo)
        payload_a = context_payload(
            pack_a, include_writer_rationale=False, writer_rationale=WRITER_RATIONALE
        )
        payload_b = context_payload(
            pack_b, include_writer_rationale=True, writer_rationale=WRITER_RATIONALE
        )
        fp_a = payload_fingerprint(payload_a)
        fp_b = payload_fingerprint(payload_b)
        self.assertNotEqual(fp_a, fp_b)
        self.assertEqual(fp_a, payload_fingerprint(payload_a))  # deterministic
        print(f"payload fingerprint A={fp_a[:16]}... B={fp_b[:16]}...")

    def test_fingerprint_is_stable_for_the_same_mode(self):
        repo = self.project()
        _ctx, first = self.build_pack(include_writer_rationale=False, repo=repo)
        _ctx2, second = self.build_pack(include_writer_rationale=False, repo=repo)
        self.assertEqual(first.fingerprint(), second.fingerprint())

    def test_same_mode_different_risk_changes_the_fingerprint(self):
        repo = self.project()
        _ctx_low, low = self.build_pack(include_writer_rationale=False, repo=repo, risk="LOW")
        _ctx_high, high = self.build_pack(include_writer_rationale=False, repo=repo, risk="HIGH")
        self.assertEqual(low.risk, "LOW")
        self.assertEqual(high.risk, "HIGH")
        self.assertNotEqual(low.fingerprint(), high.fingerprint())


# --------------------------------------------------------------------------
# the rationale itself is still scrubbed before it reaches a reviewer
# --------------------------------------------------------------------------


class RationaleIsScrubbedTest(IsolationBase):
    """Opting the rationale in must not opt secrets in with it."""

    def test_secret_in_pack_rationale_is_redacted(self):
        """The pack scrubs the rationale before storing it -- this part works."""
        _ctx, pack = self.build_pack(include_writer_rationale=True)
        self.assertIn(KEY_SENTENCE, pack.writer_rationale)
        self.assertNotIn(FAKE_AWS_KEY, pack.writer_rationale)
        self.assertIn("[REDACTED", pack.writer_rationale)

    def test_scrub_is_idempotent_on_the_rationale(self):
        once = scrub(WRITER_RATIONALE).text
        twice = scrub(once).text
        self.assertEqual(once, twice)
        self.assertNotIn(FAKE_AWS_KEY, once)

    def test_redacted_rationale_is_what_lands_in_the_serialised_pack(self):
        _ctx, pack = self.build_pack(include_writer_rationale=True)
        blob = stable_json(pack.to_dict())
        self.assertNotIn(FAKE_AWS_KEY, blob)
        self.assertIn("[REDACTED", blob)

    def test_payload_with_opted_in_rationale_is_also_scrubbed(self):
        """REAL DEFECT -- documented, not worked around.

        ``chm/reviewers/prompt.py:context_payload`` appends the
        **caller-supplied** ``writer_rationale`` argument verbatim when
        ``include_writer_rationale=True``.  It never looks at the already
        scrubbed ``pack.writer_rationale``.  ``chm/reviewers/runtime.py:285``
        forwards the raw caller argument straight through, so an opted-in
        review payload can carry a live credential into the model prompt.

        The production path is safe only because ``core/orchestrator.py:217``
        hard-codes ``include_writer_rationale=False``.  Any caller that flips
        that flag leaks secrets, so the invariant this test asserts is the one
        the spec implies and the code does not yet honour.
        """
        _ctx, pack = self.build_pack(include_writer_rationale=True)
        payload = context_payload(
            pack, include_writer_rationale=True, writer_rationale=WRITER_RATIONALE
        )
        self.assertIn(KEY_SENTENCE, payload)
        self.assertNotIn(
            FAKE_AWS_KEY,
            payload,
            "context_payload() inserted the raw caller rationale without "
            "scrubbing it (see chm/reviewers/prompt.py:168-170); the pack's "
            "scrubbed writer_rationale was ignored",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
