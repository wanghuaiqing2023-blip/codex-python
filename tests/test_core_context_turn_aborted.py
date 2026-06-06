import unittest

from pycodex.core.context import TurnAborted, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class TurnAbortedTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/turn_aborted.rs

    def test_turn_aborted_matches_marked_text_and_standard_context_registration(self) -> None:
        rendered = f"<turn_aborted>\n{TurnAborted.INTERRUPTED_GUIDANCE}\n</turn_aborted>"

        self.assertTrue(TurnAborted.matches_text(rendered))
        self.assertTrue(TurnAborted.matches_text(rendered.upper()))
        self.assertTrue(is_standard_contextual_user_text(rendered))
        self.assertFalse(TurnAborted.matches_text(TurnAborted.INTERRUPTED_GUIDANCE))

    def test_turn_aborted_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = TurnAborted.new(TurnAborted.INTERRUPTED_GUIDANCE)

        body = f"\n{TurnAborted.INTERRUPTED_GUIDANCE}\n"
        rendered = f"<turn_aborted>{body}</turn_aborted>"

        self.assertEqual(
            TurnAborted.INTERRUPTED_GUIDANCE,
            "The user interrupted the previous turn on purpose. Any running unified exec processes may still be "
            "running in the background. If any tools/commands were aborted, they may have partially executed.",
        )
        self.assertEqual(
            TurnAborted.INTERRUPTED_DEVELOPER_GUIDANCE,
            "The previous turn was interrupted on purpose. Any running unified exec processes may still be "
            "running in the background. If any tools/commands were aborted, they may have partially executed.",
        )
        self.assertEqual(fragment.role(), "user")
        self.assertEqual(fragment.markers(), ("<turn_aborted>", "</turn_aborted>"))
        self.assertEqual(fragment.type_markers(), ("<turn_aborted>", "</turn_aborted>"))
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
