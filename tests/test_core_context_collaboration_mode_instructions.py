import unittest
from types import SimpleNamespace

from pycodex.core.context import CollaborationModeInstructions, is_standard_contextual_user_text
from pycodex.protocol import (
    COLLABORATION_MODE_CLOSE_TAG,
    COLLABORATION_MODE_OPEN_TAG,
    ContentItem,
    ResponseInputItem,
    ResponseItem,
)


class CollaborationModeInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/collaboration_mode_instructions.rs

    def test_collaboration_mode_instructions_matches_marked_text_but_not_user_context_registry(
        self,
    ) -> None:
        rendered = f"{COLLABORATION_MODE_OPEN_TAG}Pair closely with the user.{COLLABORATION_MODE_CLOSE_TAG}"

        self.assertTrue(CollaborationModeInstructions.matches_text(rendered))
        self.assertTrue(CollaborationModeInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(CollaborationModeInstructions.matches_text("Pair closely with the user."))

    def test_collaboration_mode_instructions_matches_rust_contextual_fragment_contract(
        self,
    ) -> None:
        mode = SimpleNamespace(
            settings=SimpleNamespace(developer_instructions="Pair closely with the user.")
        )
        fragment = CollaborationModeInstructions.from_collaboration_mode(mode)
        self.assertIsNotNone(fragment)
        assert fragment is not None
        expected_body = "Pair closely with the user."
        expected_render = f"{COLLABORATION_MODE_OPEN_TAG}{expected_body}{COLLABORATION_MODE_CLOSE_TAG}"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), (COLLABORATION_MODE_OPEN_TAG, COLLABORATION_MODE_CLOSE_TAG))
        self.assertEqual(fragment.type_markers(), (COLLABORATION_MODE_OPEN_TAG, COLLABORATION_MODE_CLOSE_TAG))
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

    def test_collaboration_mode_instructions_omits_empty_developer_instructions(self) -> None:
        empty_mode = SimpleNamespace(settings=SimpleNamespace(developer_instructions=""))
        missing_mode = SimpleNamespace(settings=SimpleNamespace(developer_instructions=None))

        self.assertIsNone(CollaborationModeInstructions.from_collaboration_mode(empty_mode))
        self.assertIsNone(CollaborationModeInstructions.from_collaboration_mode(missing_mode))


if __name__ == "__main__":
    unittest.main()
