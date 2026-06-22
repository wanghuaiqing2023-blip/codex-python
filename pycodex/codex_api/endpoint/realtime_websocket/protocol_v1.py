"""V1 event parser from Rust ``realtime_websocket/protocol_v1.rs``."""

from __future__ import annotations

from typing import Any

from pycodex.protocol import RealtimeAudioFrame

from .protocol import RealtimeEvent
from .protocol import RealtimeHandoffRequested
from .protocol_common import parse_error_event
from .protocol_common import parse_realtime_payload
from .protocol_common import parse_session_updated_event
from .protocol_common import parse_transcript_delta_event
from .protocol_common import parse_transcript_done_event

U32_MAX = 2**32 - 1
U16_MAX = 2**16 - 1


def parse_realtime_event_v1(payload: str) -> RealtimeEvent | None:
    parsed_payload = parse_realtime_payload(payload, "realtime v1")
    if parsed_payload is None:
        return None
    parsed, message_type = parsed_payload
    if message_type == "session.updated":
        return parse_session_updated_event(parsed)
    if message_type == "conversation.output_audio.delta":
        return _parse_audio_delta(parsed)
    if message_type in (
        "conversation.input_transcript.delta",
        "conversation.item.input_audio_transcription.delta",
    ):
        delta = parse_transcript_delta_event(parsed, "delta")
        return None if delta is None else RealtimeEvent.input_transcript_delta(delta)
    if message_type in (
        "conversation.input_transcript.turn_marked",
        "conversation.item.input_audio_transcription.completed",
    ):
        done = parse_transcript_done_event(parsed, "transcript")
        return None if done is None else RealtimeEvent.input_transcript_done(done)
    if message_type in (
        "conversation.output_transcript.delta",
        "response.output_text.delta",
        "response.output_audio_transcript.delta",
    ):
        delta = parse_transcript_delta_event(parsed, "delta")
        return None if delta is None else RealtimeEvent.output_transcript_delta(delta)
    if message_type == "response.output_audio_transcript.done":
        done = parse_transcript_done_event(parsed, "transcript")
        return None if done is None else RealtimeEvent.output_transcript_done(done)
    if message_type == "conversation.item.added":
        if "item" not in parsed:
            return None
        return RealtimeEvent.conversation_item_added(parsed["item"])
    if message_type == "conversation.item.done":
        return _parse_conversation_item_done_event(parsed)
    if message_type == "conversation.handoff.requested":
        return _parse_handoff_requested_event(parsed)
    if message_type == "error":
        return parse_error_event(parsed)
    return None


def _parse_audio_delta(parsed: dict[str, Any]) -> RealtimeEvent | None:
    data = parsed.get("delta")
    if not isinstance(data, str):
        data = parsed.get("data")
    sample_rate = _as_u32(parsed.get("sample_rate"))
    channels = _as_u16(parsed.get("channels", parsed.get("num_channels")))
    if not isinstance(data, str) or sample_rate is None or channels is None:
        return None
    samples_per_channel = parsed.get("samples_per_channel")
    samples_per_channel = _as_u32(samples_per_channel)
    return RealtimeEvent.audio_out(
        RealtimeAudioFrame(
            data=data,
            sample_rate=sample_rate,
            num_channels=channels,
            samples_per_channel=samples_per_channel,
            item_id=None,
        )
    )


def _as_u32(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if 0 <= value <= U32_MAX else None


def _as_u16(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if 0 <= value <= U16_MAX else None


def _parse_conversation_item_done_event(parsed: dict[str, Any]) -> RealtimeEvent | None:
    item = parsed.get("item")
    if not isinstance(item, dict):
        return None
    item_id = item.get("id")
    if not isinstance(item_id, str):
        return None
    return RealtimeEvent.conversation_item_done(item_id)


def _parse_handoff_requested_event(parsed: dict[str, Any]) -> RealtimeEvent | None:
    handoff_id = parsed.get("handoff_id")
    item_id = parsed.get("item_id")
    input_transcript = parsed.get("input_transcript")
    if not all(isinstance(value, str) for value in (handoff_id, item_id, input_transcript)):
        return None
    return RealtimeEvent.handoff_requested(
        RealtimeHandoffRequested(
            handoff_id=handoff_id,
            item_id=item_id,
            input_transcript=input_transcript,
            active_transcript=(),
        )
    )
