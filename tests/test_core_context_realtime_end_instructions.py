import unittest

from pycodex.core.context import RealtimeEndInstructions, is_standard_contextual_user_text
from pycodex.protocol import (
    ContentItem,
    REALTIME_CONVERSATION_CLOSE_TAG,
    REALTIME_CONVERSATION_OPEN_TAG,
    ResponseInputItem,
    ResponseItem,
)


class RealtimeEndInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/realtime_end_instructions.rs
    # - codex/codex-rs/core/src/context/prompts/realtime/realtime_end.md

    def test_realtime_end_instructions_matches_marked_text_but_not_user_context_registry(self) -> None:
        rendered = (
            f"{REALTIME_CONVERSATION_OPEN_TAG}\n"
            "Realtime conversation ended.\n\n"
            "Reason: microphone disconnected\n"
            f"{REALTIME_CONVERSATION_CLOSE_TAG}"
        )

        self.assertTrue(RealtimeEndInstructions.matches_text(rendered))
        self.assertTrue(RealtimeEndInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(RealtimeEndInstructions.matches_text("Realtime conversation ended."))

    def test_realtime_end_instructions_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = RealtimeEndInstructions.new("microphone disconnected")
        rust_prompt = (
            "Realtime conversation ended.\n\n"
            "Subsequent user input will return to typed text rather than transcript-style text. "
            "Do not assume recognition errors or missing punctuation once realtime has ended. "
            "Resume normal chat behavior."
        )
        expected_body = f"\n{rust_prompt}\n\nReason: microphone disconnected\n"
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
