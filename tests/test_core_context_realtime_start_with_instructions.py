import unittest

from pycodex.core.context import RealtimeStartWithInstructions, is_standard_contextual_user_text
from pycodex.protocol import (
    ContentItem,
    REALTIME_CONVERSATION_CLOSE_TAG,
    REALTIME_CONVERSATION_OPEN_TAG,
    ResponseInputItem,
    ResponseItem,
)


class RealtimeStartWithInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/realtime_start_with_instructions.rs

    def test_realtime_start_with_instructions_matches_marked_text_but_not_user_context_registry(
        self,
    ) -> None:
        rendered = f"{REALTIME_CONVERSATION_OPEN_TAG}\nSpeak tersely.\n{REALTIME_CONVERSATION_CLOSE_TAG}"

        self.assertTrue(RealtimeStartWithInstructions.matches_text(rendered))
        self.assertTrue(RealtimeStartWithInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(RealtimeStartWithInstructions.matches_text("Speak tersely."))

    def test_realtime_start_with_instructions_matches_rust_contextual_fragment_contract(
        self,
    ) -> None:
        fragment = RealtimeStartWithInstructions.new("Speak tersely.")
        expected_body = "\nSpeak tersely.\n"
        expected_render = (
            f"{REALTIME_CONVERSATION_OPEN_TAG}"
            f"{expected_body}"
            f"{REALTIME_CONVERSATION_CLOSE_TAG}"
        )

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(
            fragment.markers(),
            (REALTIME_CONVERSATION_OPEN_TAG, REALTIME_CONVERSATION_CLOSE_TAG),
        )
        self.assertEqual(
            fragment.type_markers(),
            (REALTIME_CONVERSATION_OPEN_TAG, REALTIME_CONVERSATION_CLOSE_TAG),
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


if __name__ == "__main__":
    unittest.main()
