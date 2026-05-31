import unittest
from types import SimpleNamespace

from pycodex.core.turn_prompt import build_turn_prompt, input_with_user_instructions, render_turn_user_instructions
from pycodex.protocol import BaseInstructions, ContentItem, Personality, ResponseItem


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return [{"name": "tool"}]


class TurnPromptTests(unittest.TestCase):
    def test_render_turn_user_instructions_uses_agents_md_context_fragment(self) -> None:
        item = render_turn_user_instructions(
            SimpleNamespace(user_instructions="project instructions", cwd="C:/work/project")
        )

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.role, "user")
        self.assertIn("# AGENTS.md instructions for C:/work/project", item.content[0].text)
        self.assertIn("<INSTRUCTIONS>\nproject instructions", item.content[0].text)

    def test_input_with_user_instructions_inserts_before_current_user_input(self) -> None:
        context = SimpleNamespace(user_instructions="project instructions", cwd="C:/work/project")
        history = [
            ResponseItem.message("developer", (ContentItem.input_text("context"),)),
            ResponseItem.message("user", (ContentItem.input_text("hello"),)),
        ]

        result = input_with_user_instructions(history, context, has_current_user_input=True)

        self.assertEqual(result[0], history[0])
        self.assertIn("project instructions", result[1].content[0].text)
        self.assertEqual(result[2], history[1])

    def test_build_turn_prompt_carries_tools_and_base_instructions(self) -> None:
        context = SimpleNamespace(user_instructions=None, cwd="C:/work/project")
        base = BaseInstructions("base")
        item = ResponseItem.message("user", (ContentItem.input_text("hello"),))

        prompt = build_turn_prompt([item], Router(), context, base)

        self.assertEqual(prompt.input, [item])
        self.assertEqual(prompt.tools, [{"name": "tool"}])
        self.assertEqual(prompt.base_instructions, base)

    def test_build_turn_prompt_carries_model_parallel_tools_and_personality(self) -> None:
        context = SimpleNamespace(
            user_instructions=None,
            cwd="C:/work/project",
            model_info=SimpleNamespace(supports_parallel_tool_calls=True),
            personality=Personality.FRIENDLY,
        )
        item = ResponseItem.message("user", (ContentItem.input_text("hello"),))

        prompt = build_turn_prompt([item], Router(), context, BaseInstructions("base"))

        self.assertTrue(prompt.parallel_tool_calls)
        self.assertEqual(prompt.personality, Personality.FRIENDLY)


if __name__ == "__main__":
    unittest.main()
