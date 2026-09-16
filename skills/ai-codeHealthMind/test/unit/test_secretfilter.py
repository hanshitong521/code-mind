"""Spec §37 secret filtering: real fake credentials, idempotent scrubbing."""

from __future__ import annotations

import unittest

import helpers

from chm.context.secretfilter import (
    PII_KINDS,
    SECRET_FILENAMES,
    ScrubResult,
    is_secret_file,
    redact_report,
    scrub,
)

AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
PRIVATE_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyzABCDEF\n"
    "GhIjKlMnOpQrStUvWxYz0123456789+/=ABCDEFGHIJKLMNOPQRSTUVWXYZ12\n"
    "-----END RSA PRIVATE KEY-----"
)
JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ"
    ".dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
)
DB_PASSWORD_LITERAL = 'db.password = "s3cr3t-value-9000"'
CONNECTION_STRING = "postgres://appuser:hunter2secret@db.internal:5432/app"
TOKEN_LITERAL = 'api_key = "sk-live-abcdef1234567890"'

#: The exact strings that must not survive scrubbing.
SECRETS = {
    "aws_access_key": (AWS_KEY, f"key = {AWS_KEY}"),
    "db_password": (DB_PASSWORD_LITERAL.split('"')[1], DB_PASSWORD_LITERAL),
    "generic_secret": (TOKEN_LITERAL.split('"')[1], TOKEN_LITERAL),
    "private_key": ("MIIEowIBAAKCAQEA", PRIVATE_KEY),
    "jwt": (JWT, f"Authorization: {JWT}"),
    "connection_string": ("hunter2secret", CONNECTION_STRING),
}


class ScrubTest(unittest.TestCase):
    def test_each_of_the_six_secret_classes_is_removed(self):
        for name, (secret, text) in SECRETS.items():
            with self.subTest(kind=name):
                result = scrub(text)
                self.assertNotIn(secret, result.text, f"{name} survived scrubbing")
                self.assertTrue(result.had_secret, f"{name} was not detected at all")
                self.assertIn("[REDACTED", result.text)

    def test_aws_key_kind_is_reported(self):
        result = scrub(f"key = {AWS_KEY}")
        self.assertIn("aws_access_key", result.kinds())

    def test_jwt_kind_is_reported(self):
        result = scrub(JWT)
        self.assertIn("jwt", result.kinds())

    def test_private_key_kind_is_reported(self):
        result = scrub(PRIVATE_KEY)
        self.assertIn("private_key", result.kinds())

    def test_connection_string_password_kind_is_reported(self):
        result = scrub(CONNECTION_STRING)
        self.assertIn("db_password", result.kinds())

    def test_scrub_is_idempotent(self):
        for name, (_secret, text) in SECRETS.items():
            with self.subTest(kind=name):
                once = scrub(text).text
                twice = scrub(once).text
                self.assertEqual(twice, once)

    def test_scrub_is_deterministic(self):
        for name, (_secret, text) in SECRETS.items():
            with self.subTest(kind=name):
                a = scrub(text)
                b = scrub(text)
                self.assertEqual(a.text, b.text)
                self.assertEqual(a.to_dict(), b.to_dict())

    def test_clean_text_is_untouched(self):
        text = "public class A { void m() { int x = 1; } }"
        result = scrub(text)
        self.assertEqual(result.text, text)
        self.assertFalse(result.had_secret)
        self.assertEqual(result.redactions, [])

    def test_empty_text(self):
        result = scrub("")
        self.assertEqual(result.text, "")
        self.assertFalse(result.had_secret)

    def test_code_lookups_are_not_redacted(self):
        """``token = os.environ[...]`` is a lookup, not a literal secret."""
        text = 'token = os.environ["API_TOKEN"]\nsecret = os.getenv("SECRET")\n'
        result = scrub(text)
        self.assertIn('os.environ["API_TOKEN"]', result.text)
        self.assertIn('os.getenv("SECRET")', result.text)
        self.assertFalse(result.had_secret)

    def test_redaction_count_is_real(self):
        result = scrub(f"{AWS_KEY} and again {AWS_KEY}")
        kinds = dict((r.kind, r.count) for r in result.redactions)
        self.assertEqual(kinds.get("aws_access_key"), 2)
        self.assertEqual(result.total, 2)

    def test_pii_can_be_switched_off(self):
        text = "phone 13800138000 and id 11010119900307721X"
        with_pii = scrub(text, pii=True)
        without_pii = scrub(text, pii=False)
        self.assertNotIn("13800138000", with_pii.text)
        self.assertIn("13800138000", without_pii.text)
        self.assertTrue(PII_KINDS)

    def test_result_dict_never_leaks_the_text(self):
        payload = scrub(f"key = {AWS_KEY}").to_dict()
        self.assertNotIn("text", payload)
        self.assertNotIn(AWS_KEY, str(payload))
        self.assertTrue(payload["had_secret"])
        self.assertGreater(payload["text_chars"], 0)

    def test_marker_keeps_a_two_character_prefix(self):
        result = scrub(TOKEN_LITERAL)
        self.assertIn("sk[REDACTED]", result.text)


class SecretFileTest(unittest.TestCase):
    def test_secret_files_are_flagged(self):
        for path in (
            ".env",
            "config/.env",
            "certs/server.pem",
            "keys/client.key",
            "home/id_rsa",
            "home/id_rsa.pub",
            "deploy/keystore.jks",
            ".npmrc",
            ".netrc",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_secret_file(path), f"{path} must be treated as secret")

    def test_allowlisted_templates_are_not_secret(self):
        for path in (".env.example", ".env.sample", ".env.template", "config/.env.dist"):
            with self.subTest(path=path):
                self.assertFalse(is_secret_file(path))

    def test_ordinary_files_are_not_secret(self):
        for path in ("src/main/java/A.java", "README.md", "package.json", "config.yaml"):
            with self.subTest(path=path):
                self.assertFalse(is_secret_file(path))

    def test_windows_separators_are_handled(self):
        self.assertTrue(is_secret_file("config\\certs\\server.pem"))
        self.assertTrue(is_secret_file("C:\\app\\id_rsa"))

    def test_declared_filename_list_is_not_empty(self):
        self.assertIn(".env", SECRET_FILENAMES)
        self.assertIn("*.pem", SECRET_FILENAMES)


class RedactReportTest(unittest.TestCase):
    def test_recurses_into_dicts_and_lists(self):
        payload = {
            "findings": [
                {"id": "CHM-000001", "detail": f"hardcoded {AWS_KEY} in config"},
                {"id": "CHM-000002", "detail": CONNECTION_STRING},
            ],
            "meta": {"nested": {"token": TOKEN_LITERAL}},
            "count": 2,
            "ok": True,
            "none": None,
        }
        cleaned = redact_report(payload)
        dumped = str(cleaned)
        self.assertNotIn(AWS_KEY, dumped)
        self.assertNotIn("hunter2secret", dumped)
        self.assertNotIn("sk-live-abcdef1234567890", dumped)
        self.assertIn("[REDACTED", dumped)
        self.assertEqual(cleaned["count"], 2)
        self.assertIs(cleaned["ok"], True)
        self.assertIsNone(cleaned["none"])
        self.assertEqual(cleaned["findings"][0]["id"], "CHM-000001")

    def test_redact_report_is_idempotent(self):
        payload = {"a": [AWS_KEY, {"b": TOKEN_LITERAL}]}
        once = redact_report(payload)
        self.assertEqual(redact_report(once), once)

    def test_scalars_pass_through(self):
        self.assertEqual(redact_report(7), 7)
        self.assertIsNone(redact_report(None))
        self.assertIs(redact_report(True), True)

    def test_scrub_result_is_a_real_dataclass(self):
        self.assertIsInstance(scrub("x"), ScrubResult)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
