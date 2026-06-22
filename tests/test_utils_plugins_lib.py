import unittest
from pathlib import Path

import pycodex.utils.plugins as plugins
from pycodex.utils.plugins import PluginSkillRoot


class PluginsLibRsParityTests(unittest.TestCase):
    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/lib.rs
    # Rust items: pub mod mcp_connector; pub mod mention_syntax; pub mod plugin_namespace
    # Contract: crate root exposes the utility modules.
    def test_crate_root_exposes_utility_modules(self) -> None:
        self.assertEqual(plugins.TOOL_MENTION_SIGIL, "$")
        self.assertEqual(plugins.PLUGIN_TEXT_MENTION_SIGIL, "@")
        self.assertTrue(callable(plugins.sanitize_name))
        self.assertTrue(callable(plugins.is_connector_id_allowed))
        self.assertTrue(callable(plugins.find_plugin_manifest_path))
        self.assertTrue(callable(plugins.plugin_namespace_for_skill_path))

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/lib.rs
    # Rust items: pub use plugin_namespace::{find_plugin_manifest_path, plugin_namespace_for_skill_path}
    # Contract: namespace helpers are re-exported at crate root.
    def test_plugin_namespace_helpers_are_reexported(self) -> None:
        self.assertIs(plugins.find_plugin_manifest_path, plugins.plugin_namespace.find_plugin_manifest_path)
        self.assertIs(
            plugins.plugin_namespace_for_skill_path,
            plugins.plugin_namespace.plugin_namespace_for_skill_path,
        )

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/lib.rs
    # Rust item: PluginSkillRoot
    # Contract: path, plugin_id, and plugin_root are equality/hash-bearing fields.
    def test_plugin_skill_root_shape_equality_and_hash(self) -> None:
        first = PluginSkillRoot(Path("/plugin/skills"), "sample", Path("/plugin"))
        second = PluginSkillRoot("/plugin/skills", "sample", "/plugin")
        other = PluginSkillRoot(Path("/plugin/other"), "sample", Path("/plugin"))

        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertEqual(hash(first), hash(second))
        self.assertEqual(first.path, Path("/plugin/skills"))
        self.assertEqual(first.plugin_id, "sample")
        self.assertEqual(first.plugin_root, Path("/plugin"))

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/lib.rs
    # Rust item: PluginSkillRoot
    # Contract: Rust `plugin_id: String` is represented as Python str.
    def test_plugin_skill_root_rejects_non_string_plugin_id(self) -> None:
        with self.assertRaisesRegex(TypeError, "plugin_id must be a string"):
            PluginSkillRoot(Path("/plugin/skills"), 123, Path("/plugin"))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
