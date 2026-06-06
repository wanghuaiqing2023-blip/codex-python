import unittest

from pycodex.core.context import PluginInstructions, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class PluginInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/plugin_instructions.rs

    def test_plugin_instructions_empty_markers_do_not_match_arbitrary_text(self) -> None:
        text = "Use the plugin only when explicitly requested."

        self.assertFalse(PluginInstructions.matches_text(text))
        self.assertFalse(is_standard_contextual_user_text(text))

    def test_plugin_instructions_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = PluginInstructions.new("Use the plugin only when explicitly requested.")
        expected_body = "Use the plugin only when explicitly requested."

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_body)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(expected_body),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(expected_body),)),
        )


if __name__ == "__main__":
    unittest.main()
