import tempfile
import unittest
from pathlib import Path

from pycodex.config import (
    ConfigError,
    ConfigLoadError,
    TextPosition,
    TextRange,
    config_error_from_toml,
    config_error_from_typed_toml,
    first_layer_config_error_from_entries,
    format_config_error,
    format_config_error_with_source,
)
from pycodex.config.diagnostics import position_for_offset, text_range_from_span


class ConfigDiagnosticsTests(unittest.TestCase):
    def test_text_range_from_span_uses_one_based_line_columns(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/diagnostics.rs
        # Behavior anchor: text ranges use 1-based line/column coordinates and
        # the end position points at span.end - 1 for non-empty spans.
        contents = "model = \"gpt\"\napproval_policy = \"never\"\n"

        self.assertEqual(
            text_range_from_span(contents, range(14, 29)),
            TextRange(TextPosition(2, 1), TextPosition(2, 15)),
        )
        self.assertEqual(position_for_offset("", 0), TextPosition(1, 1))

    def test_config_load_error_display_matches_rust_shape(self) -> None:
        # Rust module: src/diagnostics.rs
        error = ConfigError(
            Path("/tmp/config.toml"),
            TextRange(TextPosition(3, 4), TextPosition(3, 8)),
            "invalid type",
        )

        load_error = ConfigLoadError(error)

        self.assertIs(load_error.config_error(), error)
        self.assertEqual(str(load_error), f"{Path('/tmp/config.toml')}:3:4: invalid type")

    def test_format_config_error_renders_source_line_and_carets(self) -> None:
        # Rust module: src/diagnostics.rs
        contents = 'model = "gpt"\nunknown_key = true\n'
        error = ConfigError(
            Path("/tmp/config.toml"),
            TextRange(TextPosition(2, 1), TextPosition(2, 11)),
            "unknown configuration field `unknown_key`",
        )

        expected = "\n".join(
            [
                f"{Path('/tmp/config.toml')}:2:1: unknown configuration field `unknown_key`",
                "  |",
                "2 | unknown_key = true",
                "  | ^^^^^^^^^^^",
            ]
        )

        self.assertEqual(format_config_error(error, contents), expected)

    def test_config_error_from_toml_uses_decode_error_position(self) -> None:
        # Rust module: src/diagnostics.rs
        contents = "model =\n"
        try:
            from pycodex.config.toml_compat import loads

            loads(contents)
        except ValueError as err:
            error = config_error_from_toml("/tmp/config.toml", contents, err)
        else:  # pragma: no cover - invalid TOML must fail.
            self.fail("invalid TOML unexpectedly parsed")

        self.assertEqual(error.path, Path("/tmp/config.toml"))
        self.assertTrue(error.message)

    def test_config_error_from_typed_toml_prefers_validator_error_after_parse(self) -> None:
        # Rust module: src/diagnostics.rs
        def validator(config):
            raise TypeError("invalid type: string \"wide\", expected i64")

        error = config_error_from_typed_toml(
            "/tmp/config.toml",
            'model_context_window = "wide"\n',
            validator,
        )

        self.assertEqual(
            error,
            ConfigError(
                Path("/tmp/config.toml"),
                TextRange(TextPosition(1, 1), TextPosition(1, 1)),
                'invalid type: string "wide", expected i64',
            ),
        )

    def test_first_layer_config_error_from_entries_returns_first_concrete_file_error(self) -> None:
        # Rust module: src/diagnostics.rs
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing = root / "missing.toml"
            bad = root / "bad.toml"
            bad.write_text("model =\n", encoding="utf-8")
            good = root / "good.toml"
            good.write_text('model = "gpt"\n', encoding="utf-8")

            error = first_layer_config_error_from_entries(
                [
                    {"name": {"file": missing}},
                    {"name": {"file": bad}},
                    {"name": {"file": good}},
                ],
                "config.toml",
            )

            self.assertIsNotNone(error)
            assert error is not None
            self.assertEqual(error.path, bad)

    def test_format_config_error_with_source_falls_back_without_file_contents(self) -> None:
        # Rust module: src/diagnostics.rs
        error = ConfigError(
            Path("/tmp/does-not-exist.toml"),
            TextRange(TextPosition(9, 2), TextPosition(9, 2)),
            "bad config",
        )

        self.assertEqual(
            format_config_error_with_source(error),
            f"{Path('/tmp/does-not-exist.toml')}:9:2: bad config",
        )


if __name__ == "__main__":
    unittest.main()
