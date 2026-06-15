import unittest

from pycodex.config import normalize_key_aliases, normalized_with_key_aliases


class ConfigKeyAliasesTests(unittest.TestCase):
    def test_normalize_key_aliases_renames_memories_legacy_key(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/key_aliases.rs
        # Behavior anchor: memories.no_memories_if_mcp_or_web_search is
        # normalized to memories.disable_on_external_context.
        table = {"no_memories_if_mcp_or_web_search": True}

        normalize_key_aliases(("memories",), table)

        self.assertEqual(table, {"disable_on_external_context": True})

    def test_normalize_key_aliases_preserves_existing_canonical_key(self) -> None:
        # Rust module: src/key_aliases.rs
        # Behavior anchor: TomlMap::entry(...).or_insert(value) means the
        # canonical key wins when both legacy and canonical names are present.
        table = {
            "disable_on_external_context": False,
            "no_memories_if_mcp_or_web_search": True,
        }

        normalize_key_aliases(("memories",), table)

        self.assertEqual(table, {"disable_on_external_context": False})

    def test_normalize_key_aliases_only_applies_at_matching_table_path(self) -> None:
        # Rust module: src/key_aliases.rs
        # Behavior anchor: alias matching compares the full table path.
        table = {"no_memories_if_mcp_or_web_search": True}

        normalize_key_aliases(("profiles", "work", "memories"), table)

        self.assertEqual(table, {"no_memories_if_mcp_or_web_search": True})

    def test_normalized_with_key_aliases_recurses_into_nested_tables(self) -> None:
        # Rust module: src/key_aliases.rs
        value = {"memories": {"no_memories_if_mcp_or_web_search": True}}

        normalized = normalized_with_key_aliases(value)

        self.assertEqual(normalized, {"memories": {"disable_on_external_context": True}})
        self.assertEqual(value, {"memories": {"no_memories_if_mcp_or_web_search": True}})

    def test_normalized_with_key_aliases_recurses_arrays_without_extending_path(self) -> None:
        # Rust module: src/key_aliases.rs
        # Behavior anchor: array items are normalized with the same path rather
        # than an index-extended path.
        value = {"memories": [{"no_memories_if_mcp_or_web_search": True}]}

        normalized = normalized_with_key_aliases(value)

        self.assertEqual(normalized, {"memories": [{"disable_on_external_context": True}]})


if __name__ == "__main__":
    unittest.main()
