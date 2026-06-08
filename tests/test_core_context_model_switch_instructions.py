import unittest

from pycodex.core.context import ModelSwitchInstructions, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class ModelSwitchInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/model_switch_instructions.rs

    def test_model_switch_instructions_matches_marked_text_but_not_user_context_registry(self) -> None:
        rendered = (
            "<model_switch>\nThe user was previously using a different model. "
            "Please continue the conversation according to the following instructions:\n\n"
            "Prefer concise answers.\n</model_switch>"
        )

        self.assertTrue(ModelSwitchInstructions.matches_text(rendered))
        self.assertTrue(ModelSwitchInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(
            ModelSwitchInstructions.matches_text(
                "The user was previously using a different model. Prefer concise answers."
            )
        )

    def test_model_switch_instructions_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = ModelSwitchInstructions.new("Prefer concise answers.")
        expected_body = (
            "\nThe user was previously using a different model. "
            "Please continue the conversation according to the following instructions:\n\n"
            "Prefer concise answers.\n"
        )
        expected_render = f"<model_switch>{expected_body}</model_switch>"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), ("<model_switch>", "</model_switch>"))
        self.assertEqual(fragment.type_markers(), ("<model_switch>", "</model_switch>"))
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
