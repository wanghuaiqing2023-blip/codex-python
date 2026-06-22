"""Rust-derived tests for ``codex-api/src/sse/responses.rs``.

Rust crate: ``codex-api``
Rust module: ``src/sse/responses.rs``
Contract: pure Responses SSE event decoding and error classification.
"""

from __future__ import annotations

import unittest

from pycodex.codex_client import IdleTimeout
from pycodex.codex_client import StreamResponse
from pycodex.codex_client import TransportError
from pycodex.codex_api.sse.responses import CYBER_POLICY_FALLBACK_MESSAGE
from pycodex.codex_api.sse.responses import TRUSTED_ACCESS_FOR_CYBER_VERIFICATION
from pycodex.codex_api.sse.responses import ResponsesEventError
from pycodex.codex_api.sse.responses import ResponsesStreamEvent
from pycodex.codex_api.sse.responses import process_responses_event
from pycodex.codex_api.sse.responses import process_sse
from pycodex.codex_api.sse.responses import spawn_response_stream
from pycodex.codex_api.sse.responses import try_parse_retry_after


class CodexApiSseResponsesRsTests(unittest.TestCase):
    def _sse(self, event: dict[str, object]) -> bytes:
        return f"event: {event['type']}\ndata: {self._json(event)}\n\n".encode()

    def _json(self, value: dict[str, object]) -> str:
        import json

        return json.dumps(value, separators=(",", ":"))

    def test_response_model_reads_top_level_headers(self) -> None:
        event = ResponsesStreamEvent.from_json_dict(
            {"type": "response.metadata", "headers": {"openai-model": "gpt-5.3-codex"}}
        )

        self.assertEqual(event.response_model(), "gpt-5.3-codex")

    def test_response_model_reads_x_openai_model_array_value(self) -> None:
        event = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.created",
                "headers": {"X-OpenAI-Model": ["gpt-5.3-codex", "ignored"]},
            }
        )

        self.assertEqual(event.response_model(), "gpt-5.3-codex")

    def test_response_model_prefers_response_headers(self) -> None:
        event = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.created",
                "headers": {"openai-model": "top-level-model"},
                "response": {"headers": {"openai-model": "gpt-5.3-codex"}},
            }
        )

        self.assertEqual(event.response_model(), "gpt-5.3-codex")

    def test_model_verification_reads_metadata_field(self) -> None:
        event = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.metadata",
                "metadata": {
                    "openai_verification_recommendation": [
                        TRUSTED_ACCESS_FOR_CYBER_VERIFICATION
                    ]
                },
            }
        )

        self.assertEqual(event.model_verifications(), [TRUSTED_ACCESS_FOR_CYBER_VERIFICATION])

    def test_model_verification_ignores_unknown_or_non_array(self) -> None:
        unknown = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.metadata",
                "metadata": {"openai_verification_recommendation": ["unknown"]},
            }
        )
        non_array = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.metadata",
                "metadata": {
                    "openai_verification_recommendation": TRUSTED_ACCESS_FOR_CYBER_VERIFICATION
                },
            }
        )

        self.assertIsNone(unknown.model_verifications())
        self.assertIsNone(non_array.model_verifications())

    def test_process_responses_event_maps_basic_event_kinds(self) -> None:
        created = process_responses_event(
            ResponsesStreamEvent.from_json_dict({"type": "response.created", "response": {}})
        )
        text = process_responses_event(
            ResponsesStreamEvent.from_json_dict(
                {"type": "response.output_text.delta", "delta": "hi"}
            )
        )
        completed = process_responses_event(
            ResponsesStreamEvent.from_json_dict(
                {"type": "response.completed", "response": {"id": "resp-1"}}
            )
        )

        self.assertEqual(created.kind, "created")
        self.assertEqual(text.value, "hi")
        self.assertEqual(
            completed.value,
            {"response_id": "resp-1", "token_usage": None, "end_turn": None},
        )

    def test_process_responses_event_maps_tool_and_reasoning_deltas(self) -> None:
        tool = process_responses_event(
            ResponsesStreamEvent.from_json_dict(
                {
                    "type": "response.custom_tool_call_input.delta",
                    "call_id": "call-1",
                    "delta": "chunk",
                }
            )
        )
        summary = process_responses_event(
            ResponsesStreamEvent.from_json_dict(
                {
                    "type": "response.reasoning_summary_text.delta",
                    "summary_index": 2,
                    "delta": "summary",
                }
            )
        )
        content = process_responses_event(
            ResponsesStreamEvent.from_json_dict(
                {
                    "type": "response.reasoning_text.delta",
                    "content_index": 3,
                    "delta": "reasoning",
                }
            )
        )

        self.assertEqual(
            tool.value,
            {"item_id": "call-1", "call_id": "call-1", "delta": "chunk"},
        )
        self.assertEqual(summary.value, {"delta": "summary", "summary_index": 2})
        self.assertEqual(content.value, {"delta": "reasoning", "content_index": 3})

    def test_process_responses_event_maps_added_events_and_ignores_unknown(self) -> None:
        item = {"id": "item-1", "type": "message"}
        added = process_responses_event(
            ResponsesStreamEvent.from_json_dict(
                {"type": "response.output_item.added", "item": item}
            )
        )
        summary_part = process_responses_event(
            ResponsesStreamEvent.from_json_dict(
                {"type": "response.reasoning_summary_part.added", "summary_index": 4}
            )
        )
        unknown = process_responses_event(
            ResponsesStreamEvent.from_json_dict({"type": "response.not_a_real_event"})
        )

        self.assertEqual(added.kind, "output_item_added")
        self.assertEqual(added.value, item)
        self.assertEqual(summary_part.value, {"summary_index": 4})
        self.assertIsNone(unknown)

    def test_process_responses_event_maps_completed_usage(self) -> None:
        event = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.completed",
                "response": {
                    "id": "resp-1",
                    "usage": {
                        "input_tokens": 4,
                        "input_tokens_details": {"cached_tokens": 2},
                        "output_tokens": 3,
                        "output_tokens_details": {"reasoning_tokens": 1},
                        "total_tokens": 7,
                    },
                    "end_turn": True,
                },
            }
        )

        result = process_responses_event(event)

        self.assertEqual(result.kind, "completed")
        self.assertEqual(result.value["token_usage"]["cached_input_tokens"], 2)
        self.assertEqual(result.value["token_usage"]["reasoning_output_tokens"], 1)
        self.assertTrue(result.value["end_turn"])

    def test_completed_parse_failure_maps_to_stream_error(self) -> None:
        # Rust module: codex-api/src/sse/responses.rs
        # Contract: response.completed deserialization errors are converted to
        # ApiError::Stream("failed to parse ResponseCompleted: ...").
        for response in [{}, {"id": "resp-1", "usage": {"input_tokens": "bad"}}]:
            with self.subTest(response=response):
                event = ResponsesStreamEvent.from_json_dict(
                    {"type": "response.completed", "response": response}
                )

                with self.assertRaises(ResponsesEventError) as caught:
                    process_responses_event(event)

                error = caught.exception.into_api_error()
                self.assertEqual(error.kind, "stream")
                self.assertIn("failed to parse ResponseCompleted", error.message)

    def test_failed_rate_limit_event_is_retryable_with_delay(self) -> None:
        event = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.failed",
                "response": {
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Rate limit reached. Please try again in 11.054s.",
                    }
                },
            }
        )

        with self.assertRaises(ResponsesEventError) as caught:
            process_responses_event(event)

        error = caught.exception.into_api_error()
        self.assertEqual(error.kind, "retryable")
        self.assertEqual(error.delay, 11.054)

    def test_failed_fatal_error_classification(self) -> None:
        for code, expected in [
            ("context_length_exceeded", "context_window_exceeded"),
            ("insufficient_quota", "quota_exceeded"),
            ("usage_not_included", "usage_not_included"),
            ("server_is_overloaded", "server_overloaded"),
            ("slow_down", "server_overloaded"),
        ]:
            event = ResponsesStreamEvent.from_json_dict(
                {"type": "response.failed", "response": {"error": {"code": code}}}
            )
            with self.subTest(code=code):
                with self.assertRaises(ResponsesEventError) as caught:
                    process_responses_event(event)
                self.assertEqual(caught.exception.into_api_error().kind, expected)

    def test_cyber_policy_uses_message_or_fallback(self) -> None:
        with_message = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.failed",
                "response": {
                    "error": {"code": "cyber_policy", "message": "flagged"}
                },
            }
        )
        without_message = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.failed",
                "response": {
                    "error": {"code": "cyber_policy", "message": "   "}
                },
            }
        )

        with self.assertRaises(ResponsesEventError) as first:
            process_responses_event(with_message)
        with self.assertRaises(ResponsesEventError) as second:
            process_responses_event(without_message)

        self.assertEqual(first.exception.into_api_error().message, "flagged")
        self.assertEqual(second.exception.into_api_error().message, CYBER_POLICY_FALLBACK_MESSAGE)

    def test_invalid_prompt_and_incomplete_errors(self) -> None:
        invalid = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.failed",
                "response": {
                    "error": {"code": "invalid_prompt", "message": "Invalid prompt"}
                },
            }
        )
        incomplete = ResponsesStreamEvent.from_json_dict(
            {
                "type": "response.incomplete",
                "response": {"incomplete_details": {"reason": "max_tokens"}},
            }
        )

        with self.assertRaises(ResponsesEventError) as first:
            process_responses_event(invalid)
        with self.assertRaises(ResponsesEventError) as second:
            process_responses_event(incomplete)

        self.assertEqual(first.exception.into_api_error().kind, "invalid_request")
        self.assertEqual(str(second.exception.into_api_error()), "stream error: Incomplete response returned, reason: max_tokens")

    def test_try_parse_retry_after_units(self) -> None:
        self.assertEqual(
            try_parse_retry_after(
                {
                    "code": "rate_limit_exceeded",
                    "message": "Please try again in 28ms.",
                }
            ),
            0.028,
        )
        self.assertEqual(
            try_parse_retry_after(
                {
                    "code": "rate_limit_exceeded",
                    "message": "Try again in 35 seconds.",
                }
            ),
            35,
        )

    def test_process_sse_emits_events_until_completed(self) -> None:
        events = list(
            process_sse(
                [
                    self._sse(
                        {
                            "type": "response.output_text.delta",
                            "delta": "hello",
                        }
                    ),
                    self._sse(
                        {
                            "type": "response.completed",
                            "response": {"id": "resp-1"},
                        }
                    ),
                    self._sse(
                        {
                            "type": "response.output_text.delta",
                            "delta": "ignored",
                        }
                    ),
                ],
                idle_timeout=1.0,
            )
        )

        self.assertEqual([event.kind for event in events], ["output_text_delta", "completed"])
        self.assertEqual(events[0].value, "hello")

    def test_process_sse_reports_missing_completed(self) -> None:
        events = list(
            process_sse(
                [
                    self._sse(
                        {
                            "type": "response.output_text.delta",
                            "delta": "hello",
                        }
                    )
                ],
                idle_timeout=1.0,
            )
        )

        self.assertEqual(events[0].kind, "output_text_delta")
        self.assertEqual(events[1].kind, "stream")
        self.assertEqual(events[1].message, "stream closed before response.completed")

    def test_process_sse_defers_failed_error_until_stream_close(self) -> None:
        events = list(
            process_sse(
                [
                    self._sse(
                        {
                            "type": "response.failed",
                            "response": {
                                "error": {
                                    "code": "rate_limit_exceeded",
                                    "message": "Please try again in 28ms.",
                                }
                            },
                        }
                    )
                ],
                idle_timeout=1.0,
            )
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "retryable")
        self.assertEqual(events[0].delay, 0.028)

    def test_process_sse_emits_server_model_and_model_verifications(self) -> None:
        events = list(
            process_sse(
                [
                    self._sse(
                        {
                            "type": "response.created",
                            "response": {
                                "id": "resp-1",
                                "model": "ignored-model",
                                "headers": {"OpenAI-Model": "gpt-5.3-codex"},
                            },
                        }
                    ),
                    self._sse(
                        {
                            "type": "response.metadata",
                            "metadata": {
                                "openai_verification_recommendation": [
                                    TRUSTED_ACCESS_FOR_CYBER_VERIFICATION
                                ]
                            },
                        }
                    ),
                    self._sse(
                        {
                            "type": "response.completed",
                            "response": {"id": "resp-1"},
                        }
                    ),
                ],
                idle_timeout=1.0,
            )
        )

        self.assertEqual(events[0].kind, "server_model")
        self.assertEqual(events[0].value, "gpt-5.3-codex")
        self.assertEqual(events[2].kind, "model_verifications")
        self.assertEqual(events[2].value, [TRUSTED_ACCESS_FOR_CYBER_VERIFICATION])
        self.assertEqual(events[-1].kind, "completed")

    def test_process_sse_ignores_response_model_field_and_header_verification(self) -> None:
        # Rust tests: process_sse_ignores_response_model_field_in_payload and
        # spawn_response_stream_ignores_model_verification_header.
        # Contract: response.model alone does not emit ServerModel, and model
        # verification is read only from response.metadata, not headers.
        stream = spawn_response_stream(
            StreamResponse(
                status=200,
                headers={
                    "openai-verification-recommendation": TRUSTED_ACCESS_FOR_CYBER_VERIFICATION
                },
                bytes=[
                    self._sse(
                        {
                            "type": "response.created",
                            "response": {
                                "id": "resp-1",
                                "model": "gpt-5.3-codex",
                            },
                        }
                    ),
                    self._sse(
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp-1",
                                "model": "gpt-5.3-codex",
                            },
                        }
                    ),
                ],
            ),
            idle_timeout=1.0,
        )

        events = list(stream)

        kinds = [event.kind for event in events]
        self.assertNotIn("server_model", kinds)
        self.assertNotIn("model_verifications", kinds)
        self.assertIn("created", kinds)
        self.assertIn("completed", kinds)

    def test_process_sse_transport_and_idle_errors(self) -> None:
        transport_events = list(
            process_sse([TransportError.network("boom")], idle_timeout=1.0)
        )
        idle_events = list(process_sse([IdleTimeout()], idle_timeout=1.0))

        self.assertEqual(transport_events[0].kind, "stream")
        self.assertIn("boom", transport_events[0].message)
        self.assertEqual(idle_events[0].message, "idle timeout waiting for SSE")

    def test_spawn_response_stream_emits_header_events_and_turn_state(self) -> None:
        turn_state: dict[str, str] = {}
        stream = spawn_response_stream(
            StreamResponse(
                status=200,
                headers={
                    "X-Request-Id": "req-1",
                    "OpenAI-Model": "gpt-5.3-codex",
                    "X-Models-Etag": "etag-1",
                    "X-Reasoning-Included": "true",
                    "X-Codex-Turn-State": "turn-1",
                },
                bytes=[
                    self._sse(
                        {
                            "type": "response.completed",
                            "response": {"id": "resp-1"},
                        }
                    )
                ],
            ),
            idle_timeout=1.0,
            telemetry=None,
            turn_state=turn_state,
        )

        self.assertEqual(stream.upstream_request_id, "req-1")
        self.assertEqual(turn_state["value"], "turn-1")
        events = list(stream)
        self.assertEqual(
            [event.kind for event in events],
            [
                "server_model",
                "rate_limits",
                "models_etag",
                "server_reasoning_included",
                "completed",
            ],
        )
        self.assertEqual(events[0].value, "gpt-5.3-codex")


if __name__ == "__main__":
    unittest.main()
