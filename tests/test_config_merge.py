import unittest

from pycodex.config import MemoriesConfig, merge_toml_values


class ConfigMergeTests(unittest.TestCase):
    def test_merge_toml_values_normalizes_legacy_key_from_base_layer(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/merge.rs
        # Rust test: merge_toml_values_normalizes_legacy_key_from_base_layer
        base = {"memories": {"no_memories_if_mcp_or_web_search": False}}
        overlay = {"memories": {"disable_on_external_context": True}}

        merge_toml_values(base, overlay)

        self.assertEqual(base, {"memories": {"disable_on_external_context": True}})
        self.assertEqual(
            MemoriesConfig.from_toml(base["memories"]),
            MemoriesConfig(disable_on_external_context=True),
        )

    def test_merge_toml_values_normalizes_legacy_key_from_overlay_layer(self) -> None:
        # Rust test: merge_toml_values_normalizes_legacy_key_from_overlay_layer
        base = {"memories": {"disable_on_external_context": False}}
        overlay = {"memories": {"no_memories_if_mcp_or_web_search": True}}

        merge_toml_values(base, overlay)

        self.assertEqual(base, {"memories": {"disable_on_external_context": True}})
        self.assertEqual(
            MemoriesConfig.from_toml(base["memories"]),
            MemoriesConfig(disable_on_external_context=True),
        )

    def test_merge_toml_values_prefers_canonical_key_when_one_layer_has_both_names(self) -> None:
        # Rust test: merge_toml_values_prefers_canonical_key_when_one_layer_has_both_names
        base = {}
        overlay = {
            "memories": {
                "disable_on_external_context": True,
                "no_memories_if_mcp_or_web_search": False,
            }
        }

        merge_toml_values(base, overlay)

        self.assertEqual(base, {"memories": {"disable_on_external_context": True}})

    def test_merge_toml_values_normalizes_permission_network_domains_before_overlaying(self) -> None:
        # Rust test: merge_toml_values_normalizes_permission_network_domains_before_overlaying
        base = {
            "permissions": {
                "dev": {"network": {"domains": {"example.com": "deny"}}}
            }
        }
        overlay = {
            "permissions": {
                "dev": {"network": {"domains": {"EXAMPLE.COM": "allow"}}}
            }
        }

        merge_toml_values(base, overlay)

        self.assertEqual(
            base,
            {
                "permissions": {
                    "dev": {"network": {"domains": {"example.com": "allow"}}}
                }
            },
        )

    def test_merge_toml_values_replaces_non_table_with_normalized_overlay(self) -> None:
        # Rust source: non-table or mixed table/non-table values are replaced by
        # normalized overlay values.
        base = {"memories": False}
        overlay = {"memories": {"no_memories_if_mcp_or_web_search": True}}

        merge_toml_values(base, overlay)

        self.assertEqual(base, {"memories": {"disable_on_external_context": True}})


if __name__ == "__main__":
    unittest.main()
