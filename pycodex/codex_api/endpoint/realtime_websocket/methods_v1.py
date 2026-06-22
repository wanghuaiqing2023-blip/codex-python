"""V1 outbound/session helpers from Rust ``realtime_websocket/methods_v1.rs``."""

from __future__ import annotations

from typing import Any

from pycodex.protocol import RealtimeVoice

from .methods_common_constants import REALTIME_AUDIO_SAMPLE_RATE


def conversation_item_create_message(text: str) -> dict[str, Any]:
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def conversation_handoff_append_message(handoff_id: str, output_text: str) -> dict[str, Any]:
    return {
        "type": "conversation.handoff.append",
        "handoff_id": handoff_id,
        "output_text": output_text,
    }


def session_update_session(instructions: str, voice: RealtimeVoice) -> dict[str, Any]:
    return {
        "type": "quicksilver",
        "instructions": instructions,
        "audio": {
            "input": {"format": {"type": "audio/pcm", "rate": REALTIME_AUDIO_SAMPLE_RATE}},
            "output": {"voice": voice.value},
        },
    }


def websocket_intent() -> str:
    return "quicksilver"
