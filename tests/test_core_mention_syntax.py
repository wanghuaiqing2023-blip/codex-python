import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pycodex.utils.plugins import (
    DISALLOWED_CONNECTOR_IDS,
    FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS,
    PLUGIN_TEXT_MENTION_SIGIL,
    TOOL_MENTION_SIGIL,
    PluginSkillRoot,
    find_plugin_manifest_path,
    is_connector_id_allowed,
    plugin_namespace_for_skill_path,
    sanitize_name,
)


class MentionSyntaxTests(unittest.TestCase):
    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/mention_syntax.rs
    # Rust items: TOOL_MENTION_SIGIL; PLUGIN_TEXT_MENTION_SIGIL
    # Contract: utils.plugins.mention_syntax_sigils
    def test_sigil_constants_match_upstream_plugin_utils(self) -> None:
        self.assertEqual(TOOL_MENTION_SIGIL, "$")
        self.assertEqual(PLUGIN_TEXT_MENTION_SIGIL, "@")

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/mention_syntax.rs
    # Contract: utils.plugins.mention_syntax_sigils
    def test_sigil_constants_are_single_characters(self) -> None:
        self.assertEqual(len(TOOL_MENTION_SIGIL), 1)
        self.assertEqual(len(PLUGIN_TEXT_MENTION_SIGIL), 1)

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/mcp_connector.rs
    # Rust items: sanitize_name; sanitize_slug
    # Contract: utils.plugins.mcp_connector_sanitize_name
    def test_mcp_connector_sanitize_name_matches_rust_slug_rules(self) -> None:
        self.assertEqual(sanitize_name("Google Calendar"), "google_calendar")
        self.assertEqual(sanitize_name("A/B+C"), "a_b_c")
        self.assertEqual(sanitize_name(" -- "), "app")
        self.assertEqual(sanitize_name("Agentlar\u0131m"), "agentlar_m")
        with self.assertRaisesRegex(TypeError, "name must be a string"):
            sanitize_name(123)  # type: ignore[arg-type]

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/mcp_connector.rs
    # Rust item: is_connector_id_allowed
    # Contract: utils.plugins.mcp_connector_allowed_ids
    def test_mcp_connector_id_allowlist_matches_rust_blocklists(self) -> None:
        self.assertFalse(is_connector_id_allowed(next(iter(DISALLOWED_CONNECTOR_IDS))))
        self.assertTrue(is_connector_id_allowed("connector_allowed"))
        first_party_only = next(iter(FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS))
        self.assertTrue(is_connector_id_allowed(first_party_only))
        self.assertFalse(
            is_connector_id_allowed(
                first_party_only,
                first_party_chat_originator=True,
            )
        )
        with self.assertRaisesRegex(TypeError, "connector_id must be a string"):
            is_connector_id_allowed(123)  # type: ignore[arg-type]

    # Source: rust_test_migrated
    # Rust crate: codex-utils-plugins
    # Rust module: src/plugin_namespace.rs
    # Rust tests: uses_manifest_name; uses_name_from_alternate_discoverable_manifest_path
    # Contract: utils.plugins.plugin_namespace_manifest_discovery
    def test_plugin_namespace_uses_nearest_manifest_name(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins" / "sample"
            skill_path = root / "skills" / "search" / "SKILL.md"
            manifest_path = root / ".codex-plugin" / "plugin.json"
            skill_path.parent.mkdir(parents=True)
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('{"name":"sample"}', encoding="utf-8")
            skill_path.write_text("---\ndescription: search\n---\n", encoding="utf-8")

            self.assertEqual(plugin_namespace_for_skill_path(skill_path), "sample")
            self.assertEqual(find_plugin_manifest_path(root), manifest_path)

    # Source: rust_test_migrated
    # Rust crate: codex-utils-plugins
    # Rust module: src/plugin_namespace.rs
    # Rust test: uses_name_from_alternate_discoverable_manifest_path
    # Contract: utils.plugins.plugin_namespace_alternate_manifest
    def test_plugin_namespace_uses_alternate_manifest_and_fallback_name(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins" / "sample"
            skill_path = root / "skills" / "search" / "SKILL.md"
            manifest_path = root / ".claude-plugin" / "plugin.json"
            skill_path.parent.mkdir(parents=True)
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text('{"name":"   "}', encoding="utf-8")
            skill_path.write_text("---\ndescription: search\n---\n", encoding="utf-8")

            self.assertEqual(plugin_namespace_for_skill_path(skill_path), "sample")
            self.assertEqual(find_plugin_manifest_path(root), manifest_path)

    # Source: rust_source_inferred
    # Rust crate: codex-utils-plugins
    # Rust module: src/plugin_namespace.rs and src/lib.rs
    # Rust items: plugin_namespace_for_skill_path; PluginSkillRoot
    # Contract: utils.plugins.plugin_namespace_boundaries
    def test_plugin_namespace_boundaries_and_skill_root_shape(self) -> None:
        with TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "skills" / "search" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("---\ndescription: search\n---\n", encoding="utf-8")

            self.assertIsNone(plugin_namespace_for_skill_path(skill_path))
            self.assertIsNone(find_plugin_manifest_path(skill_path.parent))

        root = Path("/plugin")
        skill_root = PluginSkillRoot(Path("/plugin/skills"), "sample", root)
        self.assertEqual(skill_root.path, Path("/plugin/skills"))
        self.assertEqual(skill_root.plugin_id, "sample")
        self.assertEqual(skill_root.plugin_root, root)
        with self.assertRaisesRegex(TypeError, "plugin_id must be a string"):
            PluginSkillRoot(Path("/plugin/skills"), 123, root)  # type: ignore[arg-type]
