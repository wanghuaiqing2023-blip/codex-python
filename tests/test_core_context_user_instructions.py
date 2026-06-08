import unittest

from pycodex.core.context import UserInstructions, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class UserInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/user_instructions.rs

    def test_user_instructions_matches_marked_text_and_standard_context_registration(self) -> None:
        rendered = (
            "# AGENTS.md instructions for C:/repo/project\n\n"
            "<INSTRUCTIONS>\nPrefer small focused changes.\n</INSTRUCTIONS>"
        )

        self.assertTrue(UserInstructions.matches_text(rendered))
        self.assertTrue(UserInstructions.matches_text(f"\n  {rendered.upper()}  \n"))
        self.assertTrue(is_standard_contextual_user_text(rendered))
        self.assertFalse(
            UserInstructions.matches_text(
                "C:/repo/project\n\n<INSTRUCTIONS>\nPrefer small focused changes.\n</INSTRUCTIONS>"
            )
        )

    def test_user_instructions_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = UserInstructions("C:/repo/project", "Prefer small focused changes.")
        expected_body = "C:/repo/project\n\n<INSTRUCTIONS>\nPrefer small focused changes.\n"
        expected_render = f"# AGENTS.md instructions for {expected_body}</INSTRUCTIONS>"

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(
            fragment.markers(),
            ("# AGENTS.md instructions for ", "</INSTRUCTIONS>"),
        )
        self.assertEqual(
            fragment.type_markers(),
            ("# AGENTS.md instructions for ", "</INSTRUCTIONS>"),
        )
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_render)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("user", (ContentItem.input_text(expected_render),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("user", (ContentItem.input_text(expected_render),)),
        )


if __name__ == "__main__":
    unittest.main()
