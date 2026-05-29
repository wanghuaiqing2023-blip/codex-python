import unittest
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.turn_sampler import sample_with_model_client_session
from pycodex.core.turn_runtime import build_user_turn_responses_request_from_session, run_user_turn_sampling_from_session
from pycodex.protocol import BaseInstructions, ContentItem, ResponseItem, UserInput


class History:
    def __init__(self, items: list[ResponseItem]) -> None:
        self.items = items

    def for_prompt(self, _modalities: object) -> list[ResponseItem]:
        return list(self.items)


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return [{"type": "function", "name": "tool"}]


class Session:
    def __init__(self) -> None:
        self.turn_context = SimpleNamespace(
            model_info=SimpleNamespace(input_modalities=("text",)),
            user_instructions="project instructions",
            cwd="C:/work/project",
        )
        self.history = [ResponseItem.message("developer", (ContentItem.input_text("context"),))]
        self.recorded: list[tuple[ResponseItem, ...]] = []
        self.context_recorded = False

    async def new_default_turn(self) -> object:
        return self.turn_context

    async def record_context_updates_and_set_reference_context_item(self, turn_context: object) -> None:
        self.context_recorded = turn_context is self.turn_context

    async def record_conversation_items(self, _turn_context: object, items: tuple[ResponseItem, ...]) -> None:
        self.recorded.append(items)
        self.history.extend(items)

    async def clone_history(self) -> History:
        return History(self.history)

    async def get_base_instructions(self) -> BaseInstructions:
        return BaseInstructions("base")


class TurnRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_user_turn_responses_request_records_turn_and_builds_request(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
            service_tier="auto",
        )

        self.assertTrue(session.context_recorded)
        self.assertEqual(len(session.recorded), 1)
        self.assertEqual(plan.request["model"], "gpt-test")
        self.assertEqual(plan.request["instructions"], "base")
        self.assertEqual(plan.request["tools"], [{"type": "function", "name": "tool"}])
        self.assertEqual(plan.request["service_tier"], "auto")
        self.assertEqual(plan.request["input"][0].role, "developer")
        self.assertIn("project instructions", plan.request["input"][1].content[0].text)
        self.assertEqual(plan.request["input"][2].content[0].text, "hello")

    async def test_run_user_turn_sampling_records_sampler_response_items(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 1)
        self.assertIs(seen_requests[0].session, session)
        self.assertIs(seen_requests[0].turn_context, session.turn_context)
        self.assertEqual(result.response_items[0].role, "assistant")
        self.assertEqual(session.recorded[-1], result.response_items)
        self.assertEqual(session.history[-1].content[0].text, "done")

    async def test_run_user_turn_sampling_can_use_model_client_session_sampler(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        model_session = client.new_session()
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        transported = []

        async def transport(prepared):
            transported.append(prepared)
            self.assertEqual(prepared.prepared_request["model"], "gpt-test")
            self.assertEqual(prepared.prepared_request["instructions"], "base")
            self.assertIn("input", prepared.prepared_request)
            return [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}]

        async def sampler(request):
            return await sample_with_model_client_session(request, model_session, transport)

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(transported), 1)
        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(session.history[-1].content[0].text, "done")


if __name__ == "__main__":
    unittest.main()
