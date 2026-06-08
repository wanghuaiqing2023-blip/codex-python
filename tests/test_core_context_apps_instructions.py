import unittest
from types import SimpleNamespace

from pycodex.core.context import AppsInstructions, is_standard_contextual_user_text
from pycodex.protocol import (
    APPS_INSTRUCTIONS_CLOSE_TAG,
    APPS_INSTRUCTIONS_OPEN_TAG,
    ContentItem,
    ResponseInputItem,
    ResponseItem,
)


class AppsInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/apps_instructions.rs
    # - codex/codex-rs/codex-mcp/src/mcp/mod.rs::CODEX_APPS_MCP_SERVER_NAME

    def test_apps_instructions_matches_marked_text_but_not_user_context_registry(self) -> None:
        rendered = f"{APPS_INSTRUCTIONS_OPEN_TAG}\n## Apps (Connectors)\n{APPS_INSTRUCTIONS_CLOSE_TAG}"

        self.assertTrue(AppsInstructions.matches_text(rendered))
        self.assertTrue(AppsInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(AppsInstructions.matches_text("## Apps (Connectors)"))

    def test_apps_instructions_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = AppsInstructions.from_connectors(
            (
                SimpleNamespace(is_accessible=False, is_enabled=True),
                SimpleNamespace(is_accessible=True, is_enabled=False),
                SimpleNamespace(is_accessible=True, is_enabled=True),
            )
        )
        self.assertIsNotNone(fragment)
        assert fragment is not None
        expected_body = (
            "\n## Apps (Connectors)\n"
            "Apps (Connectors) can be explicitly triggered in user messages in the format "
            "`[$app-name](app://{connector_id})`. Apps can also be implicitly triggered as long as "
            "the context suggests usage of available apps.\n"
            "An app is equivalent to a set of MCP tools within the `codex_apps` MCP.\n"
            "An installed app's MCP tools are either provided to you already, or can be lazy-loaded "
            "through the `tool_search` tool. If `tool_search` is available, the apps that are "
            "searchable by `tools_search` will be listed by it.\n"
            "Do not additionally call list_mcp_resources or list_mcp_resource_templates for apps.\n"
        )
        expected_render = f"{APPS_INSTRUCTIONS_OPEN_TAG}{expected_body}{APPS_INSTRUCTIONS_CLOSE_TAG}"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), (APPS_INSTRUCTIONS_OPEN_TAG, APPS_INSTRUCTIONS_CLOSE_TAG))
        self.assertEqual(fragment.type_markers(), (APPS_INSTRUCTIONS_OPEN_TAG, APPS_INSTRUCTIONS_CLOSE_TAG))
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

    def test_apps_instructions_omits_when_no_connector_is_accessible_and_enabled(self) -> None:
        connectors = (
            SimpleNamespace(is_accessible=False, is_enabled=True),
            SimpleNamespace(is_accessible=True, is_enabled=False),
            SimpleNamespace(is_accessible=False, is_enabled=False),
        )

        self.assertIsNone(AppsInstructions.from_connectors(connectors))


if __name__ == "__main__":
    unittest.main()
