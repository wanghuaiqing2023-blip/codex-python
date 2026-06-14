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


class StreamNoCompletedTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_on_early_close(self) -> None:
        # Rust: core/tests/suite/stream_no_completed.rs
        # test `retries_on_early_close`.
        #
        # Contract: closing a stream before response.completed is treated as a
        # retryable response stream failure. With stream_max_retries=1, the
        # first failed attempt is retried once and the turn completes.
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(
            is_azure_responses_endpoint=lambda: False,
            stream_max_retries=1,
        )
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        attempts = 0

        async def sampler(_request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise CodexErr.response_stream_failed(
                    ResponseStreamFailed("stream closed before response.completed")
                )
            return [ResponseItem.message("assistant", (ContentItem.output_text("ok"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(result.turn_status, "completed")
        self.assertEqual(result.last_agent_message, "ok")
        self.assertEqual(len(session.stream_errors), 1)
        self.assertIn("Reconnecting... 1/1", session.stream_errors[0][1])
        self.assertEqual(len(events_of_type(session, "task_complete")), 1)

