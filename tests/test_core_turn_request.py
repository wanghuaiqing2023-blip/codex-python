import unittest
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.turn_request import build_turn_responses_request
from pycodex.protocol import BaseInstructions, ContentItem, ResponseItem


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return [{"type": "function", "name": "tool"}]


class TurnRequestTests(unittest.TestCase):
    def test_build_turn_responses_request_assembles_prompt_then_request(self) -> None:
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        context = SimpleNamespace(user_instructions="project instructions", cwd="C:/work/project")
        user = ResponseItem.message("user", (ContentItem.input_text("hello"),))

        plan = build_turn_responses_request(
            client,
            provider,
            model_info,
            [user],
            Router(),
            context,
            BaseInstructions("base"),
            has_current_user_input=True,
            service_tier="auto",
        )

        self.assertEqual(plan.request["model"], "gpt-test")
        self.assertEqual(plan.request["instructions"], "base")
        self.assertEqual(plan.request["tools"], [{"type": "function", "name": "tool"}])
        self.assertEqual(plan.request["service_tier"], "auto")
        self.assertEqual(plan.request["input"][0], user)
        self.assertNotIn("project instructions", plan.request["input"][0].content[0].text)

    def test_build_turn_responses_request_carries_parallel_tool_calls(self) -> None:
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        context = SimpleNamespace(
            user_instructions=None,
            cwd="C:/work/project",
            model_info=SimpleNamespace(supports_parallel_tool_calls=True),
        )
        user = ResponseItem.message("user", (ContentItem.input_text("hello"),))

        plan = build_turn_responses_request(
            client,
            provider,
            model_info,
            [user],
            Router(),
            context,
            BaseInstructions("base"),
        )

        self.assertTrue(plan.prompt.parallel_tool_calls)
        self.assertTrue(plan.request["parallel_tool_calls"])


if __name__ == "__main__":
    unittest.main()
