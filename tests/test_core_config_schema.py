from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pycodex.config.schema import config_schema
from pycodex.core.config.schema import canonicalize, config_schema_json, write_config_schema


class CoreConfigSchemaTests(unittest.TestCase):
    def test_canonicalize_sorts_object_keys_recursively_without_sorting_arrays(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/schema.rs::canonicalize
        value = {
            "z": [{"b": 1, "a": 2}, {"d": 3, "c": 4}],
            "a": {"b": 1, "a": 2},
        }

        self.assertEqual(
            list(canonicalize(value).keys()),
            ["a", "z"],
        )
        self.assertEqual(
            canonicalize(value)["z"],
            [{"a": 2, "b": 1}, {"c": 4, "d": 3}],
        )

    def test_config_schema_json_matches_rust_fixture_after_canonicalization(self) -> None:
        # Rust crate: codex-core
        # Rust module: src/config/schema.rs
        # Rust test: config_schema_matches_fixture
        fixture_path = Path("codex/codex-rs/core/config.schema.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        generated = json.loads(config_schema_json())

        self.assertEqual(canonicalize(generated), canonicalize(fixture))
        self.assertEqual(
            config_schema_json().decode("utf-8"),
            json.dumps(canonicalize(fixture), indent=2, ensure_ascii=False),
        )

    def test_write_config_schema_writes_generated_json(self) -> None:
        # Rust crate: codex-core
        # Rust module: src/config/schema.rs
        # Rust test: config_schema_matches_fixture write-back branch
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.schema.json"
            write_config_schema(path)
            self.assertEqual(path.read_bytes(), config_schema_json())

    def test_config_schema_hides_unsupported_inline_mcp_bearer_token(self) -> None:
        # Rust crate: codex-core
        # Rust module: src/config/schema.rs
        # Rust test: config_schema_hides_unsupported_inline_mcp_bearer_token
        properties = config_schema()["definitions"]["RawMcpServerConfig"]["properties"]

        self.assertNotIn("bearer_token", properties)
        self.assertIn("bearer_token_env_var", properties)


if __name__ == "__main__":
    unittest.main()
