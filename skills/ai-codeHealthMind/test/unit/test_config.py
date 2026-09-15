"""Spec §27 configuration defaults, validation, accepted risks and the YAML subset."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401

from chm import yamlmini
from chm.config import (
    DEFAULT_CONFIG_TEMPLATE,
    AcceptedRisk,
    Config,
    ConfigError,
    load_yaml,
    parse_config,
    yaml_backend,
)
from chm.yamlmini import YamlSubsetError


class DefaultTemplateTest(unittest.TestCase):
    """The shipped template must parse and match spec §27 exactly."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = parse_config(load_yaml(DEFAULT_CONFIG_TEMPLATE), source_path="<template>")

    def test_template_parses(self):
        self.assertIsInstance(self.cfg, Config)
        self.assertEqual(self.cfg.version, 1)
        self.assertEqual(self.cfg.mode, "diff")

    def test_tool_defaults(self):
        for name in ("pmd", "cpd", "spotbugs", "semgrep", "knip"):
            self.assertTrue(
                self.cfg.tools.get(name).enabled, f"tools.{name} must default to enabled"
            )
        self.assertFalse(
            self.cfg.tools.openrewrite.enabled, "tools.openrewrite must default to disabled"
        )

    def test_dead_code_defaults(self):
        self.assertFalse(self.cfg.dead_code.allow_auto_delete)
        self.assertTrue(self.cfg.dead_code.require_reference_count_zero)
        self.assertTrue(self.cfg.dead_code.dynamic_entry_check)

    def test_gate_defaults(self):
        self.assertEqual(self.cfg.gates.max_new_medium, 5)
        self.assertTrue(self.cfg.gates.block_on_critical)
        self.assertTrue(self.cfg.gates.block_on_high)
        self.assertTrue(self.cfg.gates.block_on_tool_gap_for_critical)

    def test_review_defaults(self):
        self.assertTrue(self.cfg.review.context_isolation)
        self.assertTrue(self.cfg.review.multi_model_on_high)
        self.assertEqual(self.cfg.review.reviewers_high, 2)
        self.assertEqual(self.cfg.review.reviewers_critical, 2)
        self.assertEqual(self.cfg.review.backend, "rule")

    def test_baseline_and_token_defaults(self):
        self.assertTrue(self.cfg.baseline.enabled)
        self.assertEqual(self.cfg.baseline.path, ".codehealth-baseline.json")
        self.assertTrue(self.cfg.token.diff_first)
        self.assertEqual(self.cfg.token.max_context_files, 12)

    def test_duplication_and_complexity_defaults(self):
        self.assertEqual(self.cfg.duplication_min_tokens, 100)
        self.assertEqual(self.cfg.complexity_thresholds["method_lines"], 80)
        self.assertEqual(self.cfg.complexity_thresholds["method_cyclomatic"], 15)


class ConfigValidationTest(unittest.TestCase):
    def test_unknown_top_level_key_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_config({"gatesx": {}})
        self.assertIn("unknown config keys", str(ctx.exception))

    def test_unknown_section_key_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_config({"gates": {"max_new_mediums": 5}})
        self.assertIn("unknown key", str(ctx.exception))

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"tools": {"checkstyle": {"enabled": True}}})

    def test_unknown_tool_key_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"tools": {"pmd": {"enabld": True}}})

    def test_bool_type_error_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_config({"gates": {"block_on_critical": "yes"}})
        self.assertIn("must be a boolean", str(ctx.exception))

    def test_int_type_error_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            parse_config({"gates": {"max_new_medium": "five"}})
        self.assertIn("must be an integer", str(ctx.exception))

    def test_section_must_be_mapping(self):
        with self.assertRaises(ConfigError):
            parse_config({"gates": ["a"]})

    def test_unsupported_version_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"version": 2})

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"mode": "everything"})

    def test_invalid_backend_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"review": {"backend": "magic"}})

    def test_tool_may_be_shorthand_bool(self):
        cfg = parse_config({"tools": {"pmd": False}})
        self.assertFalse(cfg.tools.pmd.enabled)

    def test_unknown_complexity_threshold_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"complexity_thresholds": {"nope": 3}})

    def test_valid_override_round_trips(self):
        cfg = parse_config({"gates": {"max_new_medium": 2}, "dead_code": {"allow_auto_delete": True}})
        self.assertEqual(cfg.gates.max_new_medium, 2)
        self.assertTrue(cfg.dead_code.allow_auto_delete)


class AcceptedRiskTest(unittest.TestCase):
    def _cfg(self, **risk_kwargs) -> Config:
        return parse_config({"accepted_risks": [risk_kwargs]})

    def test_unexpired_risk_applies(self):
        cfg = self._cfg(finding_id="CHM-000001", reason="legacy", owner="team", expires="2030-01-01")
        found = cfg.accepted_risk_for("CHM-000001", "CHM-JAVA-DEAD-001", "2026-09-15")
        self.assertIsNotNone(found)
        self.assertEqual(found.owner, "team")

    def test_expired_risk_does_not_apply(self):
        cfg = self._cfg(finding_id="CHM-000001", reason="legacy", expires="2020-01-01")
        self.assertIsNone(cfg.accepted_risk_for("CHM-000001", "CHM-JAVA-DEAD-001", "2026-09-15"))

    def test_expiry_boundary_is_inclusive(self):
        cfg = self._cfg(finding_id="CHM-000001", expires="2026-09-15")
        self.assertIsNotNone(cfg.accepted_risk_for("CHM-000001", "CHM-X-Y", "2026-09-15"))
        self.assertIsNone(cfg.accepted_risk_for("CHM-000001", "CHM-X-Y", "2026-09-16"))

    def test_no_expiry_never_expires(self):
        cfg = self._cfg(finding_id="CHM-000001")
        self.assertIsNotNone(cfg.accepted_risk_for("CHM-000001", "CHM-X-Y", "2999-01-01"))

    def test_rule_wildcard_matches(self):
        cfg = self._cfg(rule_id="CHM-JAVA-DUP-*")
        self.assertIsNotNone(cfg.accepted_risk_for("CHM-999999", "CHM-JAVA-DUP-001", "2026-09-15"))
        self.assertIsNone(cfg.accepted_risk_for("CHM-999999", "CHM-JAVA-DEAD-001", "2026-09-15"))

    def test_expired_wildcard_does_not_match(self):
        cfg = self._cfg(rule_id="CHM-JAVA-DUP-*", expires="2020-01-01")
        self.assertIsNone(cfg.accepted_risk_for("CHM-999999", "CHM-JAVA-DUP-001", "2026-09-15"))

    def test_entry_without_id_or_rule_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"accepted_risks": [{"reason": "no id"}]})

    def test_is_expired_helper(self):
        risk = AcceptedRisk(finding_id="CHM-000001", expires="2026-01-01")
        self.assertTrue(risk.is_expired("2026-09-15"))
        self.assertFalse(risk.is_expired("2025-09-15"))
        self.assertFalse(AcceptedRisk(finding_id="X").is_expired("2999-01-01"))


class PathGlobTest(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()

    def test_excludes_hit_directory_components(self):
        self.assertTrue(self.cfg.is_excluded("node_modules/lodash/index.js"))
        self.assertTrue(self.cfg.is_excluded("target/classes/A.class"))
        self.assertTrue(self.cfg.is_excluded("src/build/generated.js"))
        self.assertFalse(self.cfg.is_excluded("src/main/java/A.java"))

    def test_generated_patterns(self):
        self.assertTrue(self.cfg.is_generated("src/main/java/generated/Foo.java"))
        self.assertTrue(self.cfg.is_generated("app/dist/bundle.js"))
        self.assertTrue(self.cfg.is_generated("src/api/user_pb2.py"))
        self.assertTrue(self.cfg.is_generated("src/thing.generated.ts"))
        self.assertFalse(self.cfg.is_generated("src/main/java/A.java"))

    def test_min_js_matches_bare_filename(self):
        """``**/*.min.js`` must match a bare ``vendor.min.js`` (spec §27)."""
        self.assertTrue(self.cfg.is_generated("vendor.min.js"))
        self.assertTrue(self.cfg.is_generated("static/js/vendor.min.js"))
        self.assertFalse(self.cfg.is_generated("vendor.js"))

    def test_custom_excludes_replace_defaults(self):
        cfg = parse_config({"excludes": ["third_party"]})
        self.assertTrue(cfg.is_excluded("third_party/x.js"))
        self.assertFalse(cfg.is_excluded("node_modules/x.js"))


class YamlMiniTest(unittest.TestCase):
    """The zero-dependency YAML subset parser (used when PyYAML is absent)."""

    def test_backend_is_reported(self):
        self.assertIn(yaml_backend(), ("pyyaml", "yamlmini"))

    def test_nested_map_and_scalars(self):
        doc = yamlmini.loads(
            "\n".join(
                [
                    "version: 1",
                    "mode: diff",
                    "nested:",
                    "  enabled: true",
                    "  disabled: false",
                    "  nothing: null",
                    "  tilde: ~",
                    "  ratio: 0.75",
                    "  name: plain",
                ]
            )
        )
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["mode"], "diff")
        self.assertIs(doc["nested"]["enabled"], True)
        self.assertIs(doc["nested"]["disabled"], False)
        self.assertIsNone(doc["nested"]["nothing"])
        self.assertIsNone(doc["nested"]["tilde"])
        self.assertEqual(doc["nested"]["ratio"], 0.75)
        self.assertEqual(doc["nested"]["name"], "plain")

    def test_block_sequence_and_inline_containers(self):
        doc = yamlmini.loads(
            "\n".join(
                [
                    "languages:",
                    "  - java",
                    "  - vue",
                    "inline_list: [a, 1, true, null]",
                    "inline_map: {x: 1, y: false}",
                    "empty_list: []",
                    "empty_map: {}",
                ]
            )
        )
        self.assertEqual(doc["languages"], ["java", "vue"])
        self.assertEqual(doc["inline_list"], ["a", 1, True, None])
        self.assertEqual(doc["inline_map"], {"x": 1, "y": False})
        self.assertEqual(doc["empty_list"], [])
        self.assertEqual(doc["empty_map"], {})

    def test_sequence_of_maps(self):
        doc = yamlmini.loads(
            "\n".join(
                [
                    "accepted_risks:",
                    "  - finding_id: CHM-000001",
                    "    reason: legacy",
                    "    expires: 2030-01-01",
                    "  - finding_id: CHM-000002",
                    "    rule_id: CHM-JAVA-DUP-*",
                ]
            )
        )
        risks = doc["accepted_risks"]
        self.assertEqual(len(risks), 2)
        self.assertEqual(risks[0]["finding_id"], "CHM-000001")
        self.assertEqual(risks[0]["reason"], "legacy")
        self.assertEqual(risks[1]["rule_id"], "CHM-JAVA-DUP-*")

    def test_quotes_and_comments(self):
        doc = yamlmini.loads(
            "\n".join(
                [
                    "# leading comment",
                    'quoted: "a # b"',
                    "single: 'c: d'",
                    "trailing: value # dropped",
                    "",
                    "   ",
                ]
            )
        )
        self.assertEqual(doc["quoted"], "a # b")
        self.assertEqual(doc["single"], "c: d")
        self.assertEqual(doc["trailing"], "value")

    def test_block_scalar(self):
        doc = yamlmini.loads("script: |\n  line one\n  line two\n")
        self.assertEqual(doc["script"], "line one\nline two\n")

    def test_illegal_indentation_raises(self):
        with self.assertRaises(YamlSubsetError) as ctx:
            yamlmini.loads("a: 1\n  b: 2\n")
        self.assertIn("bad indentation", str(ctx.exception))

    def test_non_key_line_raises(self):
        with self.assertRaises(YamlSubsetError):
            yamlmini.loads("just a sentence\n")

    def test_bad_inline_map_raises(self):
        with self.assertRaises(YamlSubsetError):
            yamlmini.loads("m: {broken}\n")

    def test_round_trip_through_dumps(self):
        original = {"a": 1, "b": {"c": True}, "d": ["x", "y"]}
        restored = yamlmini.loads(yamlmini.dumps(original))
        self.assertEqual(restored, original)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
