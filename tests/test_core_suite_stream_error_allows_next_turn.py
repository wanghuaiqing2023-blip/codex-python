from __future__ import annotations

from types import SimpleNamespace
import unittest

from pycodex.core.client import ModelClient
from pycodex.core.session.turn.runtime import run_user_turn_sampling_from_session
from pycodex.protocol import (
    CodexErr,
    ContentItem,
    ResponseItem,
    ResponseStreamFailed,
    UserInput,
)

from test_core_turn_runtime import Router, Session, events_of_type


class StreamErrorAllowsNextTurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_continue_after_stream_error(self) -> None:
        # Rust: core/tests/suite/stream_error_allows_next_turn.rs
        # test `continue_after_stream_error`.
        #
        # Contract: a terminal stream/request error must emit an Error and
        # TurnComplete lifecycle event, releasing the session so a follow-up
        # user turn can run normally.
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(
            is_azure_responses_endpoint=lambda: False,
            stream_max_retries=0,
        )
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        attempts: list[str] = []

        async def failing_sampler(request):
            attempts.append(request.request_plan.request["input"][-1].content[0].text)
            raise CodexErr.response_stream_failed(
                ResponseStreamFailed("synthetic client error")
            )

        first = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("first message"),),
            client,
            provider,
            model_info,
            failing_sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(attempts, ["first message"])
        self.assertEqual(first.turn_status, "completed")
        self.assertEqual(first.response_items, ())
        self.assertEqual(len(events_of_type(session, "error")), 1)
        self.assertEqual(len(events_of_type(session, "task_complete")), 1)

        async def succeeding_sampler(request):
            attempts.append(request.request_plan.request["input"][-1].content[0].text)
            return [ResponseItem.message("assistant", (ContentItem.output_text("ok"),))]

        second = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("follow up"),),
            client,
            provider,
            model_info,
            succeeding_sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(attempts, ["first message", "follow up"])
        self.assertEqual(second.turn_status, "completed")
        self.assertEqual(second.last_agent_message, "ok")
        self.assertEqual(len(events_of_type(session, "task_complete")), 2)

