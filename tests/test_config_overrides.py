import unittest

from pycodex.config import (
    CliConfigOverrides,
    ConfigOverrideError,
    apply_single_override,
    canonicalize_override_key,
    parse_toml_value,
)
from pycodex.config.overrides import parse_override


class ConfigOverrideTests(unittest.TestCase):
    def test_parses_basic_scalar(self):
        self.assertEqual(parse_toml_value("42"), 42)

    def test_parses_bool(self):
        self.assertIs(parse_toml_value("true"), True)
        self.assertIs(parse_toml_value("false"), False)

    def test_fails_on_unquoted_string(self):
        with self.assertRaises(ValueError):
            parse_toml_value("hello")

    def test_parse_override_falls_back_to_string_for_unquoted_string(self):
        parsed = parse_override("model=gpt-5")

        self.assertEqual(parsed.path, "model")
        self.assertEqual(parsed.value, "gpt-5")

    def test_parse_override_splits_only_on_first_equal(self):
        parsed = parse_override("instructions=a=b=c")

        self.assertEqual(parsed.path, "instructions")
        self.assertEqual(parsed.value, "a=b=c")

    def test_parse_override_strips_outer_quote_chars_on_fallback(self):
        parsed = parse_override("model='gpt-5'")

        self.assertEqual(parsed.value, "gpt-5")

    def test_parses_array(self):
        self.assertEqual(parse_toml_value("[1, 2, 3]"), [1, 2, 3])

    def test_parses_inline_table(self):
        self.assertEqual(parse_toml_value("{a = 1, b = 2}"), {"a": 1, "b": 2})

    def test_canonicalizes_use_legacy_landlock_alias(self):
        overrides = CliConfigOverrides(["use_legacy_landlock=true"])
        parsed = overrides.parse_overrides()

        self.assertEqual(parsed[0].path, "features.use_legacy_landlock")
        self.assertIs(parsed[0].value, True)

    def test_prepends_root_overrides(self):
        subcommand_overrides = CliConfigOverrides(['model="gpt-5.2"'])
        subcommand_overrides.prepend_root_overrides(CliConfigOverrides(['model="gpt-5.1"']))

        self.assertEqual(subcommand_overrides.raw_overrides, ['model="gpt-5.1"', 'model="gpt-5.2"'])

    def test_empty_key_errors(self):
        with self.assertRaisesRegex(ConfigOverrideError, "Empty key"):
            parse_override(" = true")

    def test_missing_equal_errors(self):
        with self.assertRaisesRegex(ConfigOverrideError, "missing '='"):
            parse_override("model")

    def test_apply_single_override_creates_nested_mappings(self):
        target = {}

        apply_single_override(target, "shell_environment_policy.inherit", "all")

        self.assertEqual(target, {"shell_environment_policy": {"inherit": "all"}})

    def test_apply_single_override_replaces_non_mapping_intermediate(self):
        target = {"features": False}

        apply_single_override(target, "features.use_legacy_landlock", True)

        self.assertEqual(target, {"features": {"use_legacy_landlock": True}})

    def test_apply_on_mapping_applies_parsed_overrides(self):
        target = {"model": "gpt-5.1"}
        overrides = CliConfigOverrides(["model='gpt-5.2'", "approval_policy=never"])

        overrides.apply_on_mapping(target)

        self.assertEqual(target, {"model": "gpt-5.2", "approval_policy": "never"})

    def test_canonicalize_override_key_leaves_other_keys_unchanged(self):
        self.assertEqual(canonicalize_override_key("model"), "model")


if __name__ == "__main__":
    unittest.main()
