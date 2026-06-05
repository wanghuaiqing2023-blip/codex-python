from __future__ import annotations

import unittest

from pycodex.core import (
    PluginCapabilitySummary,
    render_apps_section,
    render_explicit_plugin_instructions,
    render_plugins_section,
)
from pycodex.app_server_protocol.apps import AppInfo
from pycodex.protocol import (
    APPS_INSTRUCTIONS_CLOSE_TAG,
    APPS_INSTRUCTIONS_OPEN_TAG,
    PLUGINS_INSTRUCTIONS_CLOSE_TAG,
    PLUGINS_INSTRUCTIONS_OPEN_TAG,
)


def connector(id: str, *, is_accessible: bool, is_enabled: bool) -> AppInfo:
    return AppInfo(id=id, name=id, is_accessible=is_accessible, is_enabled=is_enabled)


class AppPluginRenderingTests(unittest.TestCase):
    def test_render_apps_section_omits_without_accessible_enabled_apps(self) -> None:
        self.assertIsNone(render_apps_section(()))
        self.assertIsNone(render_apps_section((connector("calendar", is_accessible=True, is_enabled=False),)))
        self.assertIsNone(render_apps_section((connector("calendar", is_accessible=False, is_enabled=True),)))

    def test_render_apps_section_wraps_accessible_enabled_apps(self) -> None:
        rendered = render_apps_section((connector("calendar", is_accessible=True, is_enabled=True),))

        self.assertIsNotNone(rendered)
        assert rendered is not None
        self.assertTrue(rendered.startswith(APPS_INSTRUCTIONS_OPEN_TAG))
        self.assertIn("## Apps (Connectors)", rendered)
        self.assertTrue(rendered.endswith(APPS_INSTRUCTIONS_CLOSE_TAG))

    def test_render_plugins_section_omits_empty_plugins(self) -> None:
        self.assertIsNone(render_plugins_section(()))

    def test_render_plugins_section_includes_descriptions_and_skill_naming_guidance(self) -> None:
        rendered = render_plugins_section(
            (
                PluginCapabilitySummary(
                    config_name="sample@test",
                    display_name="sample",
                    description="inspect sample data",
                    has_skills=True,
                ),
            )
        )

        expected = (
            f"{PLUGINS_INSTRUCTIONS_OPEN_TAG}\n"
            "## Plugins\n"
            "A plugin is a local bundle of skills, MCP servers, and apps. Below is the list of plugins that are enabled and available in this session.\n"
            "### Available plugins\n"
            "- `sample`: inspect sample data\n"
            "### How to use plugins\n"
            "- Discovery: The list above is the plugins available in this session.\n"
            "- Skill naming: If a plugin contributes skills, those skill entries are prefixed with `plugin_name:` in the Skills list.\n"
            "- Trigger rules: If the user explicitly names a plugin, prefer capabilities associated with that plugin for that turn.\n"
            "- Relationship to capabilities: Plugins are not invoked directly. Use their underlying skills, MCP tools, and app tools to help solve the task.\n"
            "- Preference: When a relevant plugin is available, prefer using capabilities associated with that plugin over standalone capabilities that provide similar functionality.\n"
            "- Missing/blocked: If the user requests a plugin that is not listed above, or the plugin does not have relevant callable capabilities for the task, say so briefly and continue with the best fallback.\n"
            f"{PLUGINS_INSTRUCTIONS_CLOSE_TAG}"
        )
        self.assertEqual(rendered, expected)

    def test_render_explicit_plugin_instructions_omits_empty_capabilities(self) -> None:
        self.assertIsNone(
            render_explicit_plugin_instructions(
                PluginCapabilitySummary("sample", "sample"),
                (),
                (),
            )
        )

    def test_render_explicit_plugin_instructions_lists_skills_servers_and_apps(self) -> None:
        rendered = render_explicit_plugin_instructions(
            PluginCapabilitySummary(config_name="github@test", display_name="github", has_skills=True),
            ("github-mcp", "issues"),
            ("pull-requests",),
        )

        self.assertEqual(
            rendered,
            "Capabilities from the `github` plugin:\n"
            "- Skills from this plugin are prefixed with `github:`.\n"
            "- MCP servers from this plugin available in this session: `github-mcp`, `issues`.\n"
            "- Apps from this plugin available in this session: `pull-requests`.\n"
            "Use these plugin-associated capabilities to help solve the task.",
        )

    def test_rejects_non_rust_input_shapes(self) -> None:
        with self.assertRaises(TypeError):
            render_apps_section((object(),))
        with self.assertRaises(TypeError):
            render_plugins_section(({"display_name": "sample"},))  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            render_explicit_plugin_instructions({"display_name": "sample"}, (), ())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            render_explicit_plugin_instructions(
                PluginCapabilitySummary("sample", "sample"),
                (1,),  # type: ignore[list-item]
                (),
            )
        with self.assertRaises(TypeError):
            render_explicit_plugin_instructions(
                PluginCapabilitySummary("sample", "sample"),
                (),
                (1,),  # type: ignore[list-item]
            )


if __name__ == "__main__":
    unittest.main()
