import unittest

from pycodex.core.context import PersonalitySpecInstructions, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class PersonalitySpecInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/personality_spec_instructions.rs

    def test_personality_spec_instructions_matches_marked_text_but_not_user_context_registry(
        self,
    ) -> None:
        rendered = (
            "<personality_spec> The user has requested a new communication style. "
            "Future messages should adhere to the following personality: \n"
            "Be concise but warm. </personality_spec>"
        )

        self.assertTrue(PersonalitySpecInstructions.matches_text(rendered))
        self.assertTrue(PersonalitySpecInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertFalse(is_standard_contextual_user_text(rendered))
        self.assertFalse(PersonalitySpecInstructions.matches_text("Be concise but warm."))

    def test_personality_spec_instructions_matches_rust_contextual_fragment_contract(
        self,
    ) -> None:
        fragment = PersonalitySpecInstructions.new("Be concise but warm.")
        expected_body = (
            " The user has requested a new communication style. "
            "Future messages should adhere to the following personality: \n"
            "Be concise but warm. "
        )
        expected_render = f"<personality_spec>{expected_body}</personality_spec>"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), ("<personality_spec>", "</personality_spec>"))
        self.assertEqual(fragment.type_markers(), ("<personality_spec>", "</personality_spec>"))
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
