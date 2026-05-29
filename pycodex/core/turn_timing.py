"""Turn timing state helpers ported from Codex core."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta

from pycodex.core.stream_events_utils import raw_assistant_output_text_from_item
from pycodex.protocol import ResponseItem, TurnItem


@dataclass(frozen=True)
class ResponseEvent:
    type: str
    item: ResponseItem | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("response event type must be a string")
        if self.type in {"output_item_done", "output_item_added"}:
            if not isinstance(self.item, ResponseItem):
                raise TypeError(f"{self.type} event requires a ResponseItem")
        elif self.item is not None:
            raise TypeError(f"{self.type} event must not include an item")

    @classmethod
    def created(cls) -> "ResponseEvent":
        return cls("created")

    @classmethod
    def output_item_done(cls, item: ResponseItem) -> "ResponseEvent":
        return cls("output_item_done", item)

    @classmethod
    def output_item_added(cls, item: ResponseItem) -> "ResponseEvent":
        return cls("output_item_added", item)

    @classmethod
    def output_text_delta(cls) -> "ResponseEvent":
        return cls("output_text_delta")

    @classmethod
    def reasoning_summary_delta(cls) -> "ResponseEvent":
        return cls("reasoning_summary_delta")

    @classmethod
    def reasoning_content_delta(cls) -> "ResponseEvent":
        return cls("reasoning_content_delta")

    @classmethod
    def server_model(cls) -> "ResponseEvent":
        return cls("server_model")

    @classmethod
    def model_verifications(cls) -> "ResponseEvent":
        return cls("model_verifications")

    @classmethod
    def server_reasoning_included(cls) -> "ResponseEvent":
        return cls("server_reasoning_included")

    @classmethod
    def tool_call_input_delta(cls) -> "ResponseEvent":
        return cls("tool_call_input_delta")

    @classmethod
    def completed(cls) -> "ResponseEvent":
        return cls("completed")

    @classmethod
    def reasoning_summary_part_added(cls) -> "ResponseEvent":
        return cls("reasoning_summary_part_added")

    @classmethod
    def rate_limits(cls) -> "ResponseEvent":
        return cls("rate_limits")

    @classmethod
    def models_etag(cls) -> "ResponseEvent":
        return cls("models_etag")


@dataclass
class TurnTimingState:
    started_at: float | None = None
    started_at_unix_secs_value: int | None = None
    first_token_at: float | None = None
    first_message_at: float | None = None

    def mark_turn_started(self, started_at: float | None = None) -> int:
        if started_at is not None and (
            isinstance(started_at, bool) or not isinstance(started_at, int | float)
        ):
            raise TypeError("started_at must be a monotonic timestamp or None")
        started_at_unix_ms = now_unix_timestamp_ms()
        self.started_at = time.monotonic() if started_at is None else started_at
        self.started_at_unix_secs_value = started_at_unix_ms // 1000
        self.first_token_at = None
        self.first_message_at = None
        return started_at_unix_ms

    def started_at_unix_secs(self) -> int | None:
        return self.started_at_unix_secs_value

    def completed_at_and_duration_ms(self) -> tuple[int | None, int | None]:
        completed_at = now_unix_timestamp_secs()
        if self.started_at is None:
            return completed_at, None
        return completed_at, max(0, int((time.monotonic() - self.started_at) * 1000))

    def time_to_first_token_ms(self) -> int | None:
        duration = self._time_to_first_token()
        if duration is None:
            return None
        return max(0, int(duration.total_seconds() * 1000))

    def record_ttft_for_response_event(
        self,
        event: ResponseEvent,
    ) -> timedelta | None:
        if not isinstance(event, ResponseEvent):
            raise TypeError("event must be a ResponseEvent")
        if not response_event_records_turn_ttft(event):
            return None
        return self._record_turn_ttft()

    def record_ttfm_for_turn_item(self, item: TurnItem) -> timedelta | None:
        if not isinstance(item, TurnItem):
            raise TypeError("item must be a TurnItem")
        if item.type != "AgentMessage":
            return None
        return self._record_turn_ttfm()

    def _time_to_first_token(self) -> timedelta | None:
        if self.first_token_at is None or self.started_at is None:
            return None
        return timedelta(seconds=max(0.0, self.first_token_at - self.started_at))

    def _record_turn_ttft(self) -> timedelta | None:
        if self.first_token_at is not None or self.started_at is None:
            return None
        self.first_token_at = time.monotonic()
        return self._time_to_first_token()

    def _record_turn_ttfm(self) -> timedelta | None:
        if self.first_message_at is not None or self.started_at is None:
            return None
        self.first_message_at = time.monotonic()
        return timedelta(seconds=max(0.0, self.first_message_at - self.started_at))


def now_unix_timestamp_secs() -> int:
    return now_unix_timestamp_ms() // 1000


def now_unix_timestamp_ms() -> int:
    return int(time.time() * 1000)


def response_event_records_turn_ttft(event: ResponseEvent) -> bool:
    if not isinstance(event, ResponseEvent):
        raise TypeError("event must be a ResponseEvent")
    if event.type in {"output_item_done", "output_item_added"}:
        return event.item is not None and response_item_records_turn_ttft(event.item)
    if event.type in {
        "output_text_delta",
        "reasoning_summary_delta",
        "reasoning_content_delta",
    }:
        return True
    return False


def response_item_records_turn_ttft(item: ResponseItem) -> bool:
    if not isinstance(item, ResponseItem):
        raise TypeError("item must be a ResponseItem")
    if item.type == "message":
        raw_text = raw_assistant_output_text_from_item(item)
        return raw_text is not None and raw_text != ""

    if item.type == "reasoning":
        has_summary = any(
            summary.text != ""
            for summary in item.summary
            if summary.type == "summary_text"
        )
        if has_summary:
            return True
        return any(
            content.text != ""
            for content in item.reasoning_content or ()
            if content.type in {"reasoning_text", "text"}
        )

    if item.type in {
        "local_shell_call",
        "function_call",
        "custom_tool_call",
        "tool_search_call",
        "web_search_call",
        "image_generation_call",
        "compaction",
        "context_compaction",
    }:
        return True

    return False


__all__ = [
    "ResponseEvent",
    "TurnTimingState",
    "now_unix_timestamp_ms",
    "now_unix_timestamp_secs",
    "response_event_records_turn_ttft",
    "response_item_records_turn_ttft",
]
