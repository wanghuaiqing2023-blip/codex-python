import unittest
from pathlib import Path

from pycodex.config import (
    ConfigError,
    TextPosition,
    TextRange,
    config_error_from_ignored_toml_fields,
    config_error_from_ignored_toml_value_fields,
    ignored_toml_value_field,
    unknown_feature_toml_value_field,
)
from pycodex.config.strict_config import config_error_from_ignored_toml_value_fields_for_source_name
from pycodex.config.toml_compat import loads


class ConfigStrictConfigTests(unittest.TestCase):
    def test_ignored_toml_field_errors_accept_non_file_source_names(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/strict_config.rs
        # Rust test: ignored_toml_field_errors_accept_non_file_source_names
        source_name = "com.openai.codex:config_toml_base64"
        contents = '\nmodel = "gpt-5"\nunknown_key = true'
        value = loads(contents)

        error = config_error_from_ignored_toml_value_fields_for_source_name(source_name, contents, value)

        self.assertEqual(
            error,
            ConfigError(
                Path(source_name),
                TextRange(TextPosition(3, 1), TextPosition(3, 11)),
                "unknown configuration field `unknown_key`",
            ),
        )

    def test_type_errors_take_precedence_over_ignored_fields(self) -> None:
        # Rust test: type_errors_take_precedence_over_ignored_fields
        path = Path("/tmp/config.toml")
        contents = '\nmodel_context_window = "wide"\nunknown_key = true'

        def validator(_value):
            return ConfigError(
                path,
                TextRange(TextPosition(2, 24), TextPosition(2, 29)),
                'invalid type: string "wide", expected i64',
            )

        error = config_error_from_ignored_toml_fields(path, contents, validator=validator)

        self.assertEqual(
            error,
            ConfigError(
                path,
                TextRange(TextPosition(2, 24), TextPosition(2, 29)),
                'invalid type: string "wide", expected i64',
            ),
        )

    def test_strict_config_rejects_unknown_feature_key(self) -> None:
        # Rust test: strict_config_rejects_unknown_feature_key
        path = Path("/tmp/config.toml")
        contents = "\n[features]\nfoo = true"

        error = config_error_from_ignored_toml_fields(path, contents)

        self.assertEqual(
            error,
            ConfigError(
                path,
                TextRange(TextPosition(3, 1), TextPosition(3, 3)),
                "unknown configuration field `features.foo`",
            ),
        )

    def test_strict_config_rejects_unknown_profile_feature_key(self) -> None:
        # Rust test: strict_config_rejects_unknown_profile_feature_key
        path = Path("/tmp/config.toml")
        contents = "\n[profiles.work.features]\nfoo = true"

        error = config_error_from_ignored_toml_fields(path, contents)

        self.assertEqual(
            error,
            ConfigError(
                path,
                TextRange(TextPosition(3, 1), TextPosition(3, 3)),
                "unknown configuration field `profiles.work.features.foo`",
            ),
        )

    def test_strict_config_accepts_opaque_desktop_keys(self) -> None:
        # Rust test: strict_config_accepts_opaque_desktop_keys
        contents = """
[desktop]
appearanceTheme = "dark"

[desktop.workspace]
collapsed = true"""

        self.assertIsNone(config_error_from_ignored_toml_fields("/tmp/config.toml", contents))

    def test_ignored_and_unknown_feature_field_helpers_return_first_path(self) -> None:
        # Rust source: ignored_toml_value_field and unknown_feature_toml_value_field.
        value = {"model": "gpt", "unknown_key": True, "features": {"foo": True}}

        self.assertEqual(ignored_toml_value_field(value), "unknown_key")
        self.assertEqual(unknown_feature_toml_value_field(value), "features.foo")

    def test_config_error_from_ignored_toml_value_fields_accepts_custom_allowed_fields(self) -> None:
        # Rust source: ignored-field behavior is driven by target type T.
        contents = "allowed = true\nunknown = false"
        value = loads(contents)

        error = config_error_from_ignored_toml_value_fields(
            "/tmp/custom.toml",
            contents,
            value,
            allowed_fields={"allowed"},
        )

        self.assertEqual(error.message if error else None, "unknown configuration field `unknown`")


if __name__ == "__main__":
    unittest.main()
