import unittest

from pycodex.core.context import GoalContext
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


if __name__ == "__main__":
    unittest.main()
