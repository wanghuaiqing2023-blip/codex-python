"""Common parsers from Rust ``realtime_websocket/protocol_common.rs``."""

from __future__ import annotations

import json
from typing import Any

from .protocol import RealtimeEvent
from .protocol import RealtimeTranscriptDelta
from .protocol import RealtimeTranscriptDone


def parse_realtime_payload(payload: str, parser_name: str) -> tuple[dict[str, Any], str] | None:
    del parser_name
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    message_type = parsed.get("type")
    if not isinstance(message_type, str):
        return None
    return parsed, message_type


def parse_session_updated_event(parsed: dict[str, Any]) -> RealtimeEvent | None:
    session = parsed.get("session")
    if not isinstance(session, dict):
        return None
    session_id = session.get("id")
    if not isinstance(session_id, str):
        return None
    instructions = session.get("instructions")
    return RealtimeEvent.session_updated(
        session_id,
        instructions if isinstance(instructions, str) else None,
    )


def parse_transcript_delta_event(
    parsed: dict[str, Any],
    field: str,
) -> RealtimeTranscriptDelta | None:
    value = parsed.get(field)
    if not isinstance(value, str):
        return None
    return RealtimeTranscriptDelta(value)


def parse_transcript_done_event(
    parsed: dict[str, Any],
    field: str,
) -> RealtimeTranscriptDone | None:
    value = parsed.get(field)
    if not isinstance(value, str):
        return None
    return RealtimeTranscriptDone(value)


def parse_error_event(parsed: dict[str, Any]) -> RealtimeEvent | None:
    message = parsed.get("message")
    if isinstance(message, str):
        return RealtimeEvent.error(message)
    error = parsed.get("error")
    if isinstance(error, dict):
        nested_message = error.get("message")
        if isinstance(nested_message, str):
            return RealtimeEvent.error(nested_message)
    if error is not None:
        return RealtimeEvent.error(json.dumps(error, separators=(",", ":")))
    return None
