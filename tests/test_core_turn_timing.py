import time
import unittest

from pycodex.core import (
    ResponseEvent,
    TurnTimingState,
    now_unix_timestamp_ms,
    raw_assistant_output_text_from_item,
    response_event_records_turn_ttft,
    response_item_records_turn_ttft,
)
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageItem,
    ContentItem,
    FunctionCallOutputPayload,
    ReasoningItemContent,
    ReasoningItemReasoningSummary,
    ResponseItem,
    TurnItem,
)


class CoreTurnTimingTests(unittest.TestCase):
    def test_turn_timing_state_records_ttft_only_once_per_turn(self) -> None:
        state = TurnTimingState()
        self.assertIsNone(state.record_ttft_for_response_event(ResponseEvent.output_text_delta()))

        state.mark_turn_started(time.monotonic())
        self.assertIsNone(state.record_ttft_for_response_event(ResponseEvent.created()))
        self.assertIsNotNone(state.record_ttft_for_response_event(ResponseEvent.output_text_delta()))
        self.assertIsNone(state.record_ttft_for_response_event(ResponseEvent.output_text_delta()))

    def test_turn_timing_state_records_ttfm_independently_of_ttft(self) -> None:
        state = TurnTimingState()
        state.mark_turn_started(time.monotonic())

        self.assertIsNotNone(state.record_ttft_for_response_event(ResponseEvent.output_text_delta()))
        first_message = TurnItem.agent_message(
            AgentMessageItem(
                "msg-1",
                (AgentMessageContent.text_content("hello"),),
            )
        )
        second_message = TurnItem.agent_message(
            AgentMessageItem(
                "msg-2",
                (AgentMessageContent.text_content("again"),),
            )
        )

        self.assertIsNotNone(state.record_ttfm_for_turn_item(first_message))
        self.assertIsNone(state.record_ttfm_for_turn_item(second_message))

    def test_turn_timing_state_records_epoch_millis_and_duration(self) -> None:
        state = TurnTimingState()
        before = now_unix_timestamp_ms()

        started_at_unix_ms = state.mark_turn_started(time.monotonic())

        after = now_unix_timestamp_ms()
        self.assertGreaterEqual(started_at_unix_ms, before)
        self.assertLessEqual(started_at_unix_ms, after)
        self.assertEqual(state.started_at_unix_secs(), started_at_unix_ms // 1000)
        completed_at, duration_ms = state.completed_at_and_duration_ms()
        self.assertIsNotNone(completed_at)
        self.assertIsNotNone(duration_ms)
        self.assertGreaterEqual(duration_ms, 0)

    def test_response_item_records_turn_ttft_for_first_output_signals(self) -> None:
        self.assertTrue(
            response_item_records_turn_ttft(
                ResponseItem.function_call("shell", "{}", "call-1")
            )
        )
        self.assertTrue(
            response_item_records_turn_ttft(
                ResponseItem.custom_tool_call("custom", "echo hi", "call-2")
            )
        )
        self.assertTrue(
            response_item_records_turn_ttft(
                ResponseItem.message(
                    "assistant",
                    (ContentItem.output_text("hello"),),
                )
            )
        )
        self.assertTrue(
            response_item_records_turn_ttft(
                ResponseItem(
                    "reasoning",
                    summary=(ReasoningItemReasoningSummary.summary_text("summary"),),
                )
            )
        )
        self.assertTrue(
            response_item_records_turn_ttft(
                ResponseItem(
                    "reasoning",
                    reasoning_content=(ReasoningItemContent.reasoning_text("raw"),),
                )
            )
        )

    def test_response_item_records_turn_ttft_ignores_empty_non_output_items(self) -> None:
        self.assertFalse(
            response_item_records_turn_ttft(
                ResponseItem.message(
                    "assistant",
                    (ContentItem.output_text(""),),
                )
            )
        )
        self.assertFalse(
            response_item_records_turn_ttft(
                ResponseItem(
                    "function_call_output",
                    call_id="call-1",
                    output=FunctionCallOutputPayload.from_text("ok"),
                )
            )
        )
        self.assertFalse(response_item_records_turn_ttft(ResponseItem.compaction_trigger()))
        self.assertFalse(response_item_records_turn_ttft(ResponseItem.other()))

    def test_response_event_records_turn_ttft_matches_upstream_categories(self) -> None:
        message = ResponseItem.message("assistant", (ContentItem.output_text("hello"),))

        self.assertTrue(response_event_records_turn_ttft(ResponseEvent.output_item_done(message)))
        self.assertTrue(response_event_records_turn_ttft(ResponseEvent.output_item_added(message)))
        self.assertTrue(response_event_records_turn_ttft(ResponseEvent.output_text_delta()))
        self.assertTrue(response_event_records_turn_ttft(ResponseEvent.reasoning_summary_delta()))
        self.assertTrue(response_event_records_turn_ttft(ResponseEvent.reasoning_content_delta()))
        self.assertFalse(response_event_records_turn_ttft(ResponseEvent.created()))
        self.assertFalse(response_event_records_turn_ttft(ResponseEvent.server_model()))
        self.assertFalse(response_event_records_turn_ttft(ResponseEvent.model_verifications()))
        self.assertFalse(response_event_records_turn_ttft(ResponseEvent.tool_call_input_delta()))
        self.assertFalse(response_event_records_turn_ttft(ResponseEvent.completed()))
        self.assertFalse(response_event_records_turn_ttft(ResponseEvent.rate_limits()))

    def test_raw_assistant_output_text_from_item_combines_output_text_only(self) -> None:
        self.assertEqual(
            raw_assistant_output_text_from_item(
                ResponseItem.message(
                    "assistant",
                    (
                        ContentItem.output_text("hello"),
                        ContentItem.input_text("ignored"),
                        ContentItem.output_text(" world"),
                    ),
                )
            ),
            "hello world",
        )
        self.assertIsNone(
            raw_assistant_output_text_from_item(
                ResponseItem.message("user", (ContentItem.output_text("nope"),))
            )
        )

    def test_rejects_non_rust_input_shapes(self) -> None:
        with self.assertRaises(TypeError):
            ResponseEvent(1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            ResponseEvent.output_item_done(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            ResponseEvent("created", ResponseItem.other())

        state = TurnTimingState()
        with self.assertRaises(TypeError):
            state.mark_turn_started("now")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            state.record_ttft_for_response_event(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            state.record_ttfm_for_turn_item(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            response_event_records_turn_ttft(object())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            response_item_records_turn_ttft(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
