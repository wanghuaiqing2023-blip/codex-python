import unittest
import asyncio
from collections.abc import Sequence
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.responses_retry import RetryableResponseStreamAction
from pycodex.core.turn_sampler import response_items_from_transport_result
from pycodex.core.turn_sampler import sample_with_model_client_session
from pycodex.core.turn_sampler import sample_with_model_client_session_retries
from pycodex.core.turn_runtime import UserTurnSamplingRequest
from pycodex.protocol import CodexErr, ContentItem, ResponseItem


class ResponseSequence(Sequence):
    def __init__(self, items):
        self._items = tuple(items)

    def __getitem__(self, index):
        return self._items[index]

    def __len__(self):
        return len(self._items)


class TurnSamplerTests(unittest.TestCase):
    def test_response_items_from_transport_result_accepts_sequence(self) -> None:
        first = ResponseItem.message("assistant", (ContentItem.output_text("one"),))
        second = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "two"}],
        }

        items = response_items_from_transport_result(ResponseSequence((first, second)))

        self.assertEqual(items[0], first)
        self.assertEqual(items[1].content[0].text, "two")

    def test_response_items_from_transport_result_rejects_text_sequence(self) -> None:
        with self.assertRaisesRegex(TypeError, "transport result"):
            response_items_from_transport_result("not response items")

    def test_sample_with_model_client_session_retries_retryable_codex_errors(self) -> None:
        async def run():
            attempts = 0
            decisions = []
            sleeps = []

            def transport(_prepared):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise CodexErr.stream("disconnect", retry_after=0)
                return ResponseItem.message("assistant", (ContentItem.output_text("done"),))

            result = await sample_with_model_client_session_retries(
                _sampling_request(),
                _model_session(),
                transport,
                max_retries=2,
                sleep=lambda seconds: sleeps.append(seconds),
                on_retry_decision=lambda decision: decisions.append(decision),
            )
            return attempts, decisions, sleeps, result

        attempts, decisions, sleeps, result = asyncio.run(run())

        self.assertEqual(attempts, 2)
        self.assertEqual(sleeps, [0.0])
        self.assertEqual(len(decisions), 1)
        self.assertIs(decisions[0].action, RetryableResponseStreamAction.RETRY)
        self.assertEqual(result.response_items[0].content[0].text, "done")

    def test_sample_with_model_client_session_retries_can_fallback_transport(self) -> None:
        async def run():
            decisions = []

            def primary(_prepared):
                raise CodexErr.stream("websocket disconnected")

            def fallback(_prepared):
                return ResponseItem.message("assistant", (ContentItem.output_text("https done"),))

            result = await sample_with_model_client_session_retries(
                _sampling_request(),
                _model_session(),
                primary,
                max_retries=0,
                fallback_transport=fallback,
                responses_websocket_enabled=True,
                on_retry_decision=lambda decision: decisions.append(decision),
            )
            return decisions, result

        decisions, result = asyncio.run(run())

        self.assertEqual(len(decisions), 1)
        self.assertIs(decisions[0].action, RetryableResponseStreamAction.FALLBACK_TRANSPORT)
        self.assertEqual(result.response_items[0].content[0].text, "https done")

    def test_sample_with_model_client_session_propagates_transport_stream_events(self) -> None:
        async def run():
            item = ResponseItem.message("assistant", (ContentItem.output_text("done"),))

            def transport(_prepared):
                return SimpleNamespace(
                    response_items=(item,),
                    stream_events=({"type": "completed", "response_id": "resp-1"},),
                )

            return await sample_with_model_client_session(
                _sampling_request(),
                _model_session(),
                transport,
            )

        result = asyncio.run(run())

        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(result.stream_events, ({"type": "completed", "response_id": "resp-1"},))

    def test_sample_with_model_client_session_retries_propagates_non_retryable_codex_error(self) -> None:
        async def run():
            def transport(_prepared):
                raise CodexErr.simple("server_overloaded")

            await sample_with_model_client_session_retries(
                _sampling_request(),
                _model_session(),
                transport,
                max_retries=2,
            )

        with self.assertRaises(CodexErr) as caught:
            asyncio.run(run())

        self.assertEqual(caught.exception.kind, "server_overloaded")


def _model_session():
    return ModelClient(session_id="session", thread_id="thread", installation_id="install").new_session()


def _sampling_request() -> UserTurnSamplingRequest:
    return UserTurnSamplingRequest(
        session=None,
        turn_context=None,
        request_plan=SimpleNamespace(request={"model": "gpt-test", "input": []}),
    )


if __name__ == "__main__":
    unittest.main()
