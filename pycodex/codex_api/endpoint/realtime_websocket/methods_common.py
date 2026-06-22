"""Common helpers from Rust ``realtime_websocket/methods_common.rs``."""

from __future__ import annotations

from typing import Any

from pycodex.protocol import RealtimeOutputModality
from pycodex.protocol import RealtimeVoice

from . import methods_v1
from . import methods_v2
from .methods_common_constants import REALTIME_AUDIO_SAMPLE_RATE
from .protocol import RealtimeEventParser
from .protocol import RealtimeSessionConfig
from .protocol import RealtimeSessionMode

AGENT_FINAL_MESSAGE_PREFIX = '"Agent Final Message":\n\n'


def normalized_session_mode(
    event_parser: RealtimeEventParser,
    session_mode: RealtimeSessionMode,
) -> RealtimeSessionMode:
    if event_parser == RealtimeEventParser.V1:
        return RealtimeSessionMode.CONVERSATIONAL
    return session_mode


def conversation_item_create_message(
    event_parser: RealtimeEventParser,
    text: str,
) -> dict[str, Any]:
    if event_parser == RealtimeEventParser.V1:
        return methods_v1.conversation_item_create_message(text)
    return methods_v2.conversation_item_create_message(text)


def conversation_function_call_output_message(
    event_parser: RealtimeEventParser,
    call_id: str,
    output_text: str,
) -> dict[str, Any]:
    if event_parser == RealtimeEventParser.V1:
        return methods_v1.conversation_handoff_append_message(
            call_id,
            f"{AGENT_FINAL_MESSAGE_PREFIX}{output_text}",
        )
    return methods_v2.conversation_function_call_output_message(call_id, output_text)


def session_update_session(
    event_parser: RealtimeEventParser,
    instructions: str,
    session_mode: RealtimeSessionMode,
    output_modality: RealtimeOutputModality,
    voice: RealtimeVoice,
) -> dict[str, Any]:
    normalized_mode = normalized_session_mode(event_parser, session_mode)
    if event_parser == RealtimeEventParser.V1:
        return methods_v1.session_update_session(instructions, voice)
    return methods_v2.session_update_session(instructions, normalized_mode, output_modality, voice)


def session_update_session_json(config: RealtimeSessionConfig) -> dict[str, Any]:
    session = session_update_session(
        config.event_parser,
        config.instructions,
        config.session_mode,
        config.output_modality,
        config.voice,
    )
    if config.session_id is not None:
        session["id"] = config.session_id
    if config.model is not None:
        session["model"] = config.model
    return session


def session_update_message(config: RealtimeSessionConfig) -> dict[str, Any]:
    return {"type": "session.update", "session": session_update_session_json(config)}


def websocket_intent(event_parser: RealtimeEventParser) -> str | None:
    if event_parser == RealtimeEventParser.V1:
        return methods_v1.websocket_intent()
    return methods_v2.websocket_intent()
