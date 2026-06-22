"""Realtime V2 event parser from Rust ``realtime_websocket/protocol_v2.rs``."""

from __future__ import annotations

import json
from typing import Any

from pycodex.protocol import RealtimeAudioFrame

from .protocol import RealtimeEvent
from .protocol import RealtimeHandoffRequested
from .protocol import RealtimeInputAudioSpeechStarted
from .protocol import RealtimeNoopRequested
from .protocol import RealtimeResponseCancelled
from .protocol import RealtimeResponseCreated
from .protocol import RealtimeResponseDone
from .protocol_common import parse_error_event
from .protocol_common import parse_realtime_payload
from .protocol_common import parse_session_updated_event
from .protocol_common import parse_transcript_delta_event
from .protocol_common import parse_transcript_done_event

BACKGROUND_AGENT_TOOL_NAME = "background_agent"
SILENCE_TOOL_NAME = "remain_silent"
DEFAULT_AUDIO_SAMPLE_RATE = 24_000
DEFAULT_AUDIO_CHANNELS = 1
TOOL_ARGUMENT_KEYS = ("input_transcript", "input", "text", "prompt", "query")
U32_MAX = 2**32 - 1
U16_MAX = 2**16 - 1


def parse_realtime_event_v2(payload: str) -> RealtimeEvent | None:
    parsed_payload = parse_realtime_payload(payload, "realtime v2")
    if parsed_payload is None:
        return None
    parsed, message_type = parsed_payload
    if message_type == "session.updated":
        return parse_session_updated_event(parsed)
    if message_type in ("response.output_audio.delta", "response.audio.delta"):
        return _parse_output_audio_delta_event(parsed)
    if message_type == "conversation.item.input_audio_transcription.delta":
        delta = parse_transcript_delta_event(parsed, "delta")
        return None if delta is None else RealtimeEvent.input_transcript_delta(delta)
    if message_type == "conversation.item.input_audio_transcription.completed":
        done = parse_transcript_done_event(parsed, "transcript")
        return None if done is None else RealtimeEvent.input_transcript_done(done)
    if message_type in ("response.output_text.delta", "response.output_audio_transcript.delta"):
        delta = parse_transcript_delta_event(parsed, "delta")
        return None if delta is None else RealtimeEvent.output_transcript_delta(delta)
    if message_type == "response.output_text.done":
        done = parse_transcript_done_event(parsed, "text")
        return None if done is None else RealtimeEvent.output_transcript_done(done)
    if message_type == "response.output_audio_transcript.done":
        done = parse_transcript_done_event(parsed, "transcript")
        return None if done is None else RealtimeEvent.output_transcript_done(done)
    if message_type == "input_audio_buffer.speech_started":
        item_id = parsed.get("item_id")
        return RealtimeEvent.input_audio_speech_started(
            RealtimeInputAudioSpeechStarted(item_id if isinstance(item_id, str) else None)
        )
    if message_type in ("conversation.item.added", "conversation.item.created"):
        if "item" not in parsed:
            return None
        return RealtimeEvent.conversation_item_added(parsed["item"])
    if message_type == "conversation.item.done":
        return _parse_conversation_item_done_event(parsed)
    if message_type == "response.created":
        return RealtimeEvent.response_created(
            RealtimeResponseCreated(_parse_response_event_response_id(parsed))
        )
    if message_type == "response.cancelled":
        return RealtimeEvent.response_cancelled(
            RealtimeResponseCancelled(_parse_response_event_response_id(parsed))
        )
    if message_type == "response.done":
        return RealtimeEvent.response_done(
            RealtimeResponseDone(_parse_response_event_response_id(parsed))
        )
    if message_type == "error":
        return parse_error_event(parsed)
    return None


def _parse_response_event_response_id(parsed: dict[str, Any]) -> str | None:
    response = parsed.get("response")
    if isinstance(response, dict):
        response_id = response.get("id")
        if isinstance(response_id, str):
            return response_id
    response_id = parsed.get("response_id")
    return response_id if isinstance(response_id, str) else None


def _parse_output_audio_delta_event(parsed: dict[str, Any]) -> RealtimeEvent | None:
    data = parsed.get("delta")
    if not isinstance(data, str):
        return None
    sample_rate = _as_u32(parsed.get("sample_rate"))
    channels = _as_u16(parsed.get("channels", parsed.get("num_channels")))
    samples_per_channel = _as_u32(parsed.get("samples_per_channel"))
    item_id = parsed.get("item_id")
    return RealtimeEvent.audio_out(
        RealtimeAudioFrame(
            data=data,
            sample_rate=sample_rate if sample_rate is not None else DEFAULT_AUDIO_SAMPLE_RATE,
            num_channels=channels if channels is not None else DEFAULT_AUDIO_CHANNELS,
            samples_per_channel=samples_per_channel,
            item_id=item_id if isinstance(item_id, str) else None,
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
    handoff = _parse_handoff_requested_event(item)
    if handoff is not None:
        return handoff
    noop = _parse_noop_requested_event(item)
    if noop is not None:
        return noop
    item_id = item.get("id")
    if not isinstance(item_id, str):
        return None
    return RealtimeEvent.conversation_item_done(item_id)


def _parse_handoff_requested_event(item: dict[str, Any]) -> RealtimeEvent | None:
    if item.get("type") != "function_call" or item.get("name") != BACKGROUND_AGENT_TOOL_NAME:
        return None
    call_id = item.get("call_id")
    if not isinstance(call_id, str):
        call_id = item.get("id")
    if not isinstance(call_id, str):
        return None
    item_id = item.get("id")
    arguments = item.get("arguments")
    return RealtimeEvent.handoff_requested(
        RealtimeHandoffRequested(
            handoff_id=call_id,
            item_id=item_id if isinstance(item_id, str) else call_id,
            input_transcript=_extract_input_transcript(arguments if isinstance(arguments, str) else ""),
            active_transcript=(),
        )
    )


def _parse_noop_requested_event(item: dict[str, Any]) -> RealtimeEvent | None:
    if item.get("type") != "function_call" or item.get("name") != SILENCE_TOOL_NAME:
        return None
    call_id = item.get("call_id")
    if not isinstance(call_id, str):
        call_id = item.get("id")
    if not isinstance(call_id, str):
        return None
    item_id = item.get("id")
    return RealtimeEvent.noop_requested(
        RealtimeNoopRequested(
            call_id=call_id,
            item_id=item_id if isinstance(item_id, str) else call_id,
        )
    )


def _extract_input_transcript(arguments: str) -> str:
    if not arguments:
        return ""
    try:
        arguments_json = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
    if isinstance(arguments_json, dict):
        for key in TOOL_ARGUMENT_KEYS:
            value = arguments_json.get(key)
            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed:
                    return trimmed
    return arguments
