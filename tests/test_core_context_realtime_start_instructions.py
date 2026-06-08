import unittest

from pycodex.core.context import RealtimeStartInstructions, is_standard_contextual_user_text
from pycodex.protocol import (
    ContentItem,
    REALTIME_CONVERSATION_CLOSE_TAG,
    REALTIME_CONVERSATION_OPEN_TAG,
    ResponseInputItem,
    ResponseItem,
)


class RealtimeStartInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/realtime_start_instructions.rs
    # - codex/codex-rs/core/src/context/prompts/realtime/realtime_start.md

    def test_realtime_start_instructions_matches_marked_text_but_not_user_context_registry(self) -> None:
        rendered = (
            f"{REALTIME_CONVERSATION_OPEN_TAG}\n"
            "Realtime conversation started.\n"
            f"{REALTIME_CONVERSATION_CLOSE_TAG}"
        )

        self.assertTrue(RealtimeStartInstructions.matches_text(rendered))
        self.assertTrue(RealtimeStartInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(RealtimeStartInstructions.matches_text("Realtime conversation started."))

    def test_realtime_start_instructions_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = RealtimeStartInstructions()
        rust_prompt = """Realtime conversation started.

You are operating as a backend executor behind an intermediary. The user does not talk to you directly. Any response you produce will be consumed by the intermediary and may be summarized before the user sees it.

When invoked, you receive the latest conversation transcript and any relevant mode or metadata. The intermediary may invoke you even when backend help is not actually needed. Use the transcript to decide whether you should do work. If backend help is unnecessary, avoid verbose responses that add user-visible latency.

When user text is routed from realtime, treat it as a transcript. It may be unpunctuated or contain recognition errors.

- Keep responses concise and action-oriented. Your updates should help the intermediary respond to the user."""
        expected_body = f"\n{rust_prompt}\n"
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
