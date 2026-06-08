import unittest

from pycodex.core.context import SkillInstructions, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class SkillInstructionsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/skill_instructions.rs

    def test_skill_instructions_matches_marked_text_and_standard_context_registration(self) -> None:
        rendered = (
            "<skill>\n<name>shell-helper</name>\n"
            "<path>skills/shell-helper/SKILL.md</path>\n"
            "Use safe shell slices.\n</skill>"
        )

        self.assertTrue(SkillInstructions.matches_text(rendered))
        self.assertTrue(SkillInstructions.matches_text(f"  {rendered.upper()}\n"))
        self.assertTrue(is_standard_contextual_user_text(rendered))
        self.assertFalse(
            SkillInstructions.matches_text(
                "<name>shell-helper</name>\n<path>skills/shell-helper/SKILL.md</path>"
            )
        )

    def test_skill_instructions_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = SkillInstructions("shell-helper", "skills/shell-helper/SKILL.md", "Use safe shell slices.")
        expected_body = (
            "\n<name>shell-helper</name>\n"
            "<path>skills/shell-helper/SKILL.md</path>\n"
            "Use safe shell slices.\n"
        )
        expected_render = f"<skill>{expected_body}</skill>"

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(fragment.markers(), ("<skill>", "</skill>"))
        self.assertEqual(fragment.type_markers(), ("<skill>", "</skill>"))
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
