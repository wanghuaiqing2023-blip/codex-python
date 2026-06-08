import unittest

from pycodex.core import plugins
from pycodex.core.context import PluginCapabilitySummary
from pycodex.core.plugins.discoverable import list_tool_suggest_discoverable_plugins
from pycodex.core.plugins.injection import build_plugin_injections
from pycodex.core.plugins.mentions import (
    build_connector_slug_counts,
    collect_explicit_app_ids,
    collect_explicit_plugin_mentions,
    collect_tool_mentions_from_messages,
)
from pycodex.core.plugins.render import render_explicit_plugin_instructions
from pycodex.core.skills import build_skill_name_counts


class CorePluginsCoordinateTests(unittest.TestCase):
    def test_plugins_root_reexports_rust_mod_surface(self):
        # Rust source: codex-rs/core/src/plugins/mod.rs
        # Rust contract: root module re-exports PluginCapabilitySummary and
        # public helpers from discoverable, injection, render, and mentions.
        self.assertIs(plugins.PluginCapabilitySummary, PluginCapabilitySummary)
        self.assertIs(plugins.list_tool_suggest_discoverable_plugins, list_tool_suggest_discoverable_plugins)
        self.assertIs(plugins.build_plugin_injections, build_plugin_injections)
        self.assertIs(plugins.render_explicit_plugin_instructions, render_explicit_plugin_instructions)
        self.assertIs(plugins.build_connector_slug_counts, build_connector_slug_counts)
        self.assertIs(plugins.build_skill_name_counts, build_skill_name_counts)
        self.assertIs(plugins.collect_explicit_app_ids, collect_explicit_app_ids)
        self.assertIs(plugins.collect_explicit_plugin_mentions, collect_explicit_plugin_mentions)
        self.assertIs(plugins.collect_tool_mentions_from_messages, collect_tool_mentions_from_messages)

    def test_plugins_root_helpers_smoke(self):
        plugin = plugins.PluginCapabilitySummary(config_name="docs@test", display_name="Docs")
        self.assertEqual(plugin.config_name, "docs@test")
        exact_counts, lower_counts = plugins.build_skill_name_counts((), ())
        self.assertEqual(exact_counts, {})
        self.assertEqual(lower_counts, {})


if __name__ == "__main__":
    unittest.main()
