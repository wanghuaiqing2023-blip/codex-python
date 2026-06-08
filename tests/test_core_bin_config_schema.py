from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pycodex.config.schema import config_schema_json
from pycodex.core.bin.config_schema import (
    COMMAND_NAME,
    build_parser,
    default_output_path,
    main,
    parse_args,
    run,
)


class CoreBinConfigSchemaTests(unittest.TestCase):
    def test_parser_matches_rust_command_name_and_out_option(self) -> None:
        # Rust crate: codex-core
        # Rust module: src/bin/config_schema.rs
        # Contract: #[command(name = "codex-write-config-schema")] with -o/--out PATH.
        parser = build_parser()
        self.assertEqual(parser.prog, COMMAND_NAME)
        self.assertEqual(parse_args(["-o", "schema.json"]).out, Path("schema.json"))
        self.assertEqual(parse_args(["--out", "schema.json"]).out, Path("schema.json"))
        self.assertIsNone(parse_args([]).out)

    def test_run_writes_schema_to_explicit_out_path(self) -> None:
        # Rust source: config_schema.rs::main calls codex_config::schema::write_config_schema.
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "custom.schema.json"

            returned = run(["--out", str(out_path)])

            self.assertEqual(returned, out_path)
            self.assertEqual(out_path.read_bytes(), config_schema_json())

    def test_main_returns_zero_after_writing_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "config.schema.json"

            self.assertEqual(main(["-o", str(out_path)]), 0)
            self.assertEqual(out_path.read_bytes(), config_schema_json())

    def test_default_output_path_matches_core_crate_fixture(self) -> None:
        # Rust default: env!("CARGO_MANIFEST_DIR").join("config.schema.json").
        self.assertEqual(
            default_output_path(),
            Path("codex/codex-rs/core/config.schema.json").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
