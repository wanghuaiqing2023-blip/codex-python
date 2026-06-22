"""V2 outbound/session helpers from Rust ``realtime_websocket/methods_v2.rs``."""

from __future__ import annotations

from typing import Any

from pycodex.protocol import RealtimeOutputModality
from pycodex.protocol import RealtimeVoice

from .methods_common_constants import REALTIME_AUDIO_SAMPLE_RATE
from .protocol import RealtimeSessionMode

REALTIME_V2_OUTPUT_MODALITY_AUDIO = "audio"
REALTIME_V2_OUTPUT_MODALITY_TEXT = "text"
REALTIME_V2_TOOL_CHOICE = "auto"
REALTIME_V2_BACKGROUND_AGENT_TOOL_NAME = "background_agent"
REALTIME_V2_BACKGROUND_AGENT_TOOL_DESCRIPTION = (
    "Send a user request to the background agent. Use this as the default action. Do not "
    "rephrase the user's ask or rewrite it in your own words; pass along the user's own words. "
    "If the background agent is idle, this starts a new task and returns the final result to the "
    "user. If the background agent is already working on a task, this sends the request as "
    "guidance to steer that previous task. If the user asks to do something next, later, after "
    "this, or once current work finishes, call this tool so the work is actually queued instead "
    "of merely promising to do it later."
)
REALTIME_V2_SILENCE_TOOL_NAME = "remain_silent"
REALTIME_V2_SILENCE_TOOL_DESCRIPTION = (
    "Call this when the best response is to say nothing. Use it instead of speaking after hidden "
    "system/control messages, after background agent updates in silent modes, or whenever "
    "acknowledging aloud would be distracting. This tool has no user-visible effect."
)
REALTIME_V2_INPUT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"


def conversation_item_create_message(text: str) -> dict[str, Any]:
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def conversation_function_call_output_message(call_id: str, output_text: str) -> dict[str, Any]:
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output_text,
        },
    }


def session_update_session(
    instructions: str,
    session_mode: RealtimeSessionMode,
    output_modality: RealtimeOutputModality,
    voice: RealtimeVoice,
) -> dict[str, Any]:
    if session_mode == RealtimeSessionMode.TRANSCRIPTION:
        return {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": REALTIME_AUDIO_SAMPLE_RATE},
                    "transcription": {"model": REALTIME_V2_INPUT_TRANSCRIPTION_MODEL},
                }
            },
        }

    return {
        "type": "realtime",
        "instructions": instructions,
        "output_modalities": [_output_modality_value(output_modality)],
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": REALTIME_AUDIO_SAMPLE_RATE},
                "noise_reduction": {"type": "near_field"},
                "transcription": {"model": REALTIME_V2_INPUT_TRANSCRIPTION_MODEL},
                "turn_detection": {
                    "type": "server_vad",
                    "interrupt_response": True,
                    "create_response": True,
                    "silence_duration_ms": 500,
                },
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": REALTIME_AUDIO_SAMPLE_RATE},
                "voice": voice.value,
            },
        },
        "tools": [
            {
                "type": "function",
                "name": REALTIME_V2_BACKGROUND_AGENT_TOOL_NAME,
                "description": REALTIME_V2_BACKGROUND_AGENT_TOOL_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "The user request to delegate to the background agent.",
                        }
                    },
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": REALTIME_V2_SILENCE_TOOL_NAME,
                "description": REALTIME_V2_SILENCE_TOOL_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        ],
        "tool_choice": REALTIME_V2_TOOL_CHOICE,
    }


def websocket_intent() -> None:
    return None


def _output_modality_value(output_modality: RealtimeOutputModality) -> str:
    if output_modality == RealtimeOutputModality.TEXT:
        return REALTIME_V2_OUTPUT_MODALITY_TEXT
    return REALTIME_V2_OUTPUT_MODALITY_AUDIO
