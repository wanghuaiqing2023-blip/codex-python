import unittest

from pycodex.core.context import (
    AvailablePluginsInstructions,
    PluginCapabilitySummary,
    is_standard_contextual_user_text,
)
from pycodex.protocol import (
    ContentItem,
    PLUGINS_INSTRUCTIONS_CLOSE_TAG,
    PLUGINS_INSTRUCTIONS_OPEN_TAG,
    ResponseInputItem,
    ResponseItem,
)


class AvailablePluginsInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/available_plugins_instructions.rs

    def test_available_plugins_instructions_matches_marked_text_but_not_user_context_registry(
        self,
    ) -> None:
        rendered = f"{PLUGINS_INSTRUCTIONS_OPEN_TAG}\n## Plugins\n{PLUGINS_INSTRUCTIONS_CLOSE_TAG}"

        self.assertTrue(AvailablePluginsInstructions.matches_text(rendered))
        self.assertTrue(AvailablePluginsInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(AvailablePluginsInstructions.matches_text("## Plugins"))

    def test_available_plugins_instructions_matches_rust_contextual_fragment_contract(
        self,
    ) -> None:
        fragment = AvailablePluginsInstructions.from_plugins(
            (
                PluginCapabilitySummary(
                    config_name="browser",
                    display_name="Browser",
                    description="Inspect local web targets.",
                ),
                PluginCapabilitySummary(config_name="docs", display_name="Documents"),
            )
        )
        self.assertIsNotNone(fragment)
        assert fragment is not None
        expected_body = (
            "\n## Plugins\n"
            "A plugin is a local bundle of skills, MCP servers, and apps. Below is the list of plugins that are enabled and available in this session.\n"
            "### Available plugins\n"
            "- `Browser`: Inspect local web targets.\n"
            "- `Documents`\n"
            "### How to use plugins\n"
            "- Discovery: The list above is the plugins available in this session.\n"
            "- Skill naming: If a plugin contributes skills, those skill entries are prefixed with `plugin_name:` in the Skills list.\n"
            "- Trigger rules: If the user explicitly names a plugin, prefer capabilities associated with that plugin for that turn.\n"
            "- Relationship to capabilities: Plugins are not invoked directly. Use their underlying skills, MCP tools, and app tools to help solve the task.\n"
            "- Preference: When a relevant plugin is available, prefer using capabilities associated with that plugin over standalone capabilities that provide similar functionality.\n"
            "- Missing/blocked: If the user requests a plugin that is not listed above, or the plugin does not have relevant callable capabilities for the task, say so briefly and continue with the best fallback.\n"
        )
        expected_render = (
            f"{PLUGINS_INSTRUCTIONS_OPEN_TAG}"
            f"{expected_body}"
            f"{PLUGINS_INSTRUCTIONS_CLOSE_TAG}"
        )

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(
            fragment.markers(),
            (PLUGINS_INSTRUCTIONS_OPEN_TAG, PLUGINS_INSTRUCTIONS_CLOSE_TAG),
        )
        self.assertEqual(
            fragment.type_markers(),
            (PLUGINS_INSTRUCTIONS_OPEN_TAG, PLUGINS_INSTRUCTIONS_CLOSE_TAG),
        )
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_render)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(expected_render),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(expected_render),)),
        )

    def test_available_plugins_instructions_omits_empty_plugin_list(self) -> None:
        self.assertIsNone(AvailablePluginsInstructions.from_plugins(()))


if __name__ == "__main__":
    unittest.main()
