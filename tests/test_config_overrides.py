import unittest

from pycodex.config import (
    CliConfigOverrides,
    ConfigOverride,
    ConfigOverrideError,
    apply_single_override,
    build_cli_overrides_layer,
    canonicalize_override_key,
    default_empty_table,
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

    def test_default_empty_table_returns_empty_mapping(self):
        # Rust crate: codex-config
        # Rust module: src/overrides.rs
        # Rust source: default_empty_table returns TomlValue::Table(Default::default()).
        self.assertEqual(default_empty_table(), {})

    def test_build_cli_overrides_layer_applies_dotted_paths_in_order(self):
        # Rust source: build_cli_overrides_layer applies each parsed path/value.
        layer = build_cli_overrides_layer(
            [
                ("model", "gpt-5.2"),
                ("features.web_search_request", True),
                ("features.use_legacy_landlock", False),
            ]
        )

        self.assertEqual(
            layer,
            {
                "model": "gpt-5.2",
                "features": {
                    "web_search_request": True,
                    "use_legacy_landlock": False,
                },
            },
        )

    def test_build_cli_overrides_layer_replaces_non_mapping_intermediate(self):
        # Rust source: apply_toml_override replaces a non-table intermediate
        # with a table before continuing.
        layer = build_cli_overrides_layer(
            [
                ("features", False),
                ("features.use_legacy_landlock", True),
            ]
        )

        self.assertEqual(layer, {"features": {"use_legacy_landlock": True}})

    def test_build_cli_overrides_layer_accepts_config_override_objects(self):
        layer = build_cli_overrides_layer(
            [
                ConfigOverride("sandbox", "read-only"),
                ConfigOverride("shell_environment_policy.inherit", "all"),
            ]
        )

        self.assertEqual(
            layer,
            {
                "sandbox": "read-only",
                "shell_environment_policy": {"inherit": "all"},
            },
        )

    def test_cli_config_overrides_build_layer_uses_parsed_values(self):
        overrides = CliConfigOverrides(["model='gpt-5.2'", "features.web_search_request=true"])

        self.assertEqual(
            overrides.build_layer(),
            {"model": "gpt-5.2", "features": {"web_search_request": True}},
        )

    def test_canonicalize_override_key_leaves_other_keys_unchanged(self):
        self.assertEqual(canonicalize_override_key("model"), "model")


if __name__ == "__main__":
    unittest.main()
