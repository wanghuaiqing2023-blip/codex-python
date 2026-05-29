"""Pure helpers from Codex realtime conversation handling.

Ported from the standalone formatting/header helpers in
``codex/codex-rs/core/src/realtime_conversation.rs``. Realtime websocket,
audio, model-client, and session orchestration remain outside this stdlib-only
slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


REALTIME_USER_TEXT_PREFIX = "[USER] "
REALTIME_BACKEND_TEXT_PREFIX = "[BACKEND] "


class RealtimeWsVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"


@dataclass(frozen=True)
class RealtimeTranscriptEntry:
    role: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, str):
            raise TypeError("role must be a string")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

    @classmethod
    def from_value(cls, value: "RealtimeTranscriptEntry | Mapping[str, object]") -> "RealtimeTranscriptEntry":
        if isinstance(value, RealtimeTranscriptEntry):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("transcript entries must be RealtimeTranscriptEntry or mapping values")
        role = value.get("role")
        text = value.get("text")
        if not isinstance(role, str):
            raise TypeError("transcript entry role must be a string")
        if not isinstance(text, str):
            raise TypeError("transcript entry text must be a string")
        return cls(role=role, text=text)


@dataclass(frozen=True)
class RealtimeHandoffRequested:
    handoff_id: str
    item_id: str
    input_transcript: str
    active_transcript: tuple[RealtimeTranscriptEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.handoff_id, str):
            raise TypeError("handoff_id must be a string")
        if not isinstance(self.item_id, str):
            raise TypeError("item_id must be a string")
        if not isinstance(self.input_transcript, str):
            raise TypeError("input_transcript must be a string")
        if isinstance(self.active_transcript, (str, bytes)) or not isinstance(self.active_transcript, Sequence):
            raise TypeError("active_transcript must be a sequence")
        object.__setattr__(
            self,
            "active_transcript",
            tuple(RealtimeTranscriptEntry.from_value(entry) for entry in self.active_transcript),
        )


def realtime_transcript_delta_from_handoff(handoff: RealtimeHandoffRequested) -> str | None:
    handoff = _handoff(handoff)
    active_transcript = "\n".join(f"{entry.role}: {entry.text}" for entry in handoff.active_transcript)
    return active_transcript or None


def realtime_text_from_handoff_request(handoff: RealtimeHandoffRequested) -> str | None:
    handoff = _handoff(handoff)
    if handoff.input_transcript:
        return handoff.input_transcript
    return realtime_transcript_delta_from_handoff(handoff)


def realtime_delegation_from_handoff(handoff: RealtimeHandoffRequested) -> str | None:
    handoff = _handoff(handoff)
    input_text = realtime_text_from_handoff_request(handoff)
    if input_text is None:
        return None
    return wrap_realtime_delegation_input(
        input_text,
        realtime_transcript_delta_from_handoff(handoff),
    )


def wrap_realtime_delegation_input(input: str, transcript_delta: str | None = None) -> str:
    if not isinstance(input, str):
        raise TypeError("input must be a string")
    if transcript_delta is not None and not isinstance(transcript_delta, str):
        raise TypeError("transcript_delta must be a string or None")
    escaped_input = escape_xml_text(input)
    if transcript_delta:
        escaped_delta = escape_xml_text(transcript_delta)
        return (
            "<realtime_delegation>\n"
            f"  <input>{escaped_input}</input>\n"
            f"  <transcript_delta>{escaped_delta}</transcript_delta>\n"
            "</realtime_delegation>"
        )
    return f"<realtime_delegation>\n  <input>{escaped_input}</input>\n</realtime_delegation>"


def escape_xml_text(input: str) -> str:
    if not isinstance(input, str):
        raise TypeError("input must be a string")
    return input.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def realtime_request_headers(
    realtime_session_id: str | None,
    api_key: str | None,
    version: RealtimeWsVersion | str,
) -> dict[str, str]:
    ws_version = RealtimeWsVersion(version)
    headers: dict[str, str] = {}
    if ws_version is RealtimeWsVersion.V1:
        headers["openai-alpha"] = "quicksilver=v1"
    if realtime_session_id is not None:
        if not isinstance(realtime_session_id, str):
            raise TypeError("realtime_session_id must be a string or None")
        if _valid_header_value(realtime_session_id):
            headers["x-session-id"] = realtime_session_id
    if api_key is not None:
        if not isinstance(api_key, str):
            raise TypeError("api_key must be a string or None")
        auth_value = f"Bearer {api_key}"
        if not _valid_header_value(auth_value):
            raise ValueError("invalid realtime api key header")
        headers["authorization"] = auth_value
    return headers


def _valid_header_value(value: str) -> bool:
    return all(ch == "\t" or (ord(ch) >= 32 and ch not in "\r\n") for ch in value)


def _handoff(value: RealtimeHandoffRequested) -> RealtimeHandoffRequested:
    if not isinstance(value, RealtimeHandoffRequested):
        raise TypeError("handoff must be RealtimeHandoffRequested")
    return value


__all__ = [
    "REALTIME_BACKEND_TEXT_PREFIX",
    "REALTIME_USER_TEXT_PREFIX",
    "RealtimeHandoffRequested",
    "RealtimeTranscriptEntry",
    "RealtimeWsVersion",
    "escape_xml_text",
    "realtime_delegation_from_handoff",
    "realtime_request_headers",
    "realtime_text_from_handoff_request",
    "realtime_transcript_delta_from_handoff",
    "wrap_realtime_delegation_input",
]
