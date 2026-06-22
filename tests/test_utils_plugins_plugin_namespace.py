import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pycodex.utils.plugins import find_plugin_manifest_path, plugin_namespace_for_skill_path


class PluginNamespaceRsParityTests(unittest.TestCase):
    # Source: rust_test_migrated
    # Rust crate: codex-utils-plugins
    # Rust module: src/plugin_namespace.rs
    # Rust test: uses_manifest_name
    # Contract: nearest ancestor with .codex-plugin/plugin.json supplies manifest name.
    def test_uses_manifest_name_from_nearest_ancestor(self) -> None:
        with TemporaryDirectory() as tmp:
            plugin_root = Path(tmp) / "plugins" / "sample"
            skill_path = plugin_root / "skills" / "search" / "SKILL.md"
            manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
            skill_path.parent.mkdir(parents=True)
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('{"name":"sample"}', encoding="utf-8")
            skill_path.write_text("---\ndescription: search\n---\n", encoding="utf-8")

            self.assertEqual(plugin_namespace_for_skill_path(skill_path), "sample")
            self.assertEqual(find_plugin_manifest_path(plugin_root), manifest_path)

    # Source: rust_test_migrated
    # Rust crate: codex-utils-plugins
    # Rust module: src/plugin_namespace.rs
    # Rust test: uses_name_from_alternate_discoverable_manifest_path
    # Contract: .claude-plugin/plugin.json is discoverable.
    def test_uses_name_from_alternate_discoverable_manifest_path(self) -> None:
        with TemporaryDirectory() as tmp:
            plugin_root = Path(tmp) / "plugins" / "sample"
            skill_path = plugin_root / "skills" / "search" / "SKILL.md"
            manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
            skill_path.parent.mkdir(parents=True)
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('{"name":"sample"}', encoding="utf-8")
            skill_path.write_text("---\ndescription: search\n---\n", encoding="utf-8")

            self.assertEqual(plugin_namespace_for_skill_path(skill_path), "sample")
            self.assertEqual(find_plugin_manifest_path(plugin_root), manifest_path)

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/plugin_namespace.rs
    # Rust items: plugin_manifest_name; plugin_namespace_for_skill_path
    # Contract: empty manifest name falls back to the plugin root directory name.
    def test_empty_manifest_name_falls_back_to_plugin_root_name(self) -> None:
        with TemporaryDirectory() as tmp:
            plugin_root = Path(tmp) / "plugins" / "fallback"
            skill_path = plugin_root / "skills" / "search" / "SKILL.md"
            manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
            skill_path.parent.mkdir(parents=True)
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('{"name":"   "}', encoding="utf-8")
            skill_path.write_text("---\ndescription: search\n---\n", encoding="utf-8")

            self.assertEqual(plugin_namespace_for_skill_path(skill_path), "fallback")

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/plugin_namespace.rs
    # Rust items: plugin_manifest_name; plugin_namespace_for_skill_path
    # Contract: missing or invalid manifests produce no namespace.
    def test_missing_or_invalid_manifest_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            plugin_root = Path(tmp) / "plugins" / "sample"
            skill_path = plugin_root / "skills" / "search" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("---\ndescription: search\n---\n", encoding="utf-8")

            self.assertIsNone(plugin_namespace_for_skill_path(skill_path))
            self.assertIsNone(find_plugin_manifest_path(plugin_root))

            manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text("{not json", encoding="utf-8")

            self.assertIsNone(plugin_namespace_for_skill_path(skill_path))


if __name__ == "__main__":
    unittest.main()
