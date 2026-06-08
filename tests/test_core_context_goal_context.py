import unittest

from pycodex.core.context import GoalContext, is_contextual_user_fragment
from pycodex.core.event_mapping import parse_turn_item
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class GoalContextTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/goal_context.rs

    def test_goal_context_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = GoalContext.new("Continue working toward the active thread goal.")

        body = "\nContinue working toward the active thread goal.\n"
        rendered = "<goal_context>\nContinue working toward the active thread goal.\n</goal_context>"

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(fragment.markers(), ("<goal_context>", "</goal_context>"))
        self.assertEqual(fragment.type_markers(), ("<goal_context>", "</goal_context>"))
        self.assertEqual(fragment.body(), body)
        self.assertEqual(fragment.render(), rendered)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("user", (ContentItem.input_text(rendered),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("user", (ContentItem.input_text(rendered),)),
        )

    def test_goal_context_is_hidden_contextual_user_fragment(self) -> None:
        # Rust tests:
        # - context/contextual_user_message_tests.rs::detects_goal_context_fragment
        # - event_mapping_tests.rs::goal_context_does_not_parse_as_visible_turn_item
        rendered = GoalContext.new("Continue working toward the active thread goal.").render()
        item = ResponseItem.message("user", (ContentItem.input_text(rendered),), id="msg-1")

        self.assertTrue(is_contextual_user_fragment(ContentItem.input_text(rendered)))
        self.assertIsNone(parse_turn_item(item))


if __name__ == "__main__":
    unittest.main()
