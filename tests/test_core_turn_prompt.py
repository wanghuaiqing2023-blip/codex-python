import unittest
from types import SimpleNamespace

from pycodex.core.session.turn.prompt import (
    build_turn_prompt,
    input_with_user_instructions,
    is_guardian_reviewer_source,
    render_turn_user_instructions,
)
from pycodex.protocol import BaseInstructions, ContentItem, Personality, ResponseItem, SessionSource, SubAgentSource


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

    def test_input_with_user_instructions_preserves_prompt_input_order(self) -> None:
        context = SimpleNamespace(user_instructions="project instructions", cwd="C:/work/project")
        history = [
            ResponseItem.message("developer", (ContentItem.input_text("context"),)),
            ResponseItem.message("user", (ContentItem.input_text("hello"),)),
        ]

        result = input_with_user_instructions(history, context, has_current_user_input=True)

        self.assertEqual(result, history)

    def test_build_turn_prompt_preserves_prompt_input_order_with_user_instructions_on_context(self) -> None:
        context = SimpleNamespace(user_instructions="project instructions", cwd="C:/work/project")
        history = [
            ResponseItem.message("developer", (ContentItem.input_text("context"),)),
            ResponseItem.message("user", (ContentItem.input_text("hello"),)),
        ]

        prompt = build_turn_prompt(history, Router(), context, BaseInstructions("base"), has_current_user_input=True)

        self.assertEqual(prompt.input, history)

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

    def test_build_turn_prompt_infers_non_strict_output_schema_for_guardian_reviewer(self) -> None:
        context = SimpleNamespace(
            session_source=SessionSource.subagent(SubAgentSource.other_source("guardian")),
        )
        item = ResponseItem.message("user", (ContentItem.input_text("assess"),))

        prompt = build_turn_prompt([item], Router(), context, BaseInstructions("base"), output_schema={"type": "object"})

        self.assertFalse(prompt.output_schema_strict)
        self.assertTrue(is_guardian_reviewer_source(context.session_source))

    def test_build_turn_prompt_allows_explicit_output_schema_strict_override(self) -> None:
        context = SimpleNamespace(
            session_source=SessionSource.subagent(SubAgentSource.other_source("guardian")),
        )
        item = ResponseItem.message("user", (ContentItem.input_text("assess"),))

        prompt = build_turn_prompt(
            [item],
            Router(),
            context,
            BaseInstructions("base"),
            output_schema={"type": "object"},
            output_schema_strict=True,
        )

        self.assertTrue(prompt.output_schema_strict)


if __name__ == "__main__":
    unittest.main()

