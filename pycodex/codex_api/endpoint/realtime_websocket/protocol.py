"""Protocol data used by Rust ``realtime_websocket/protocol.rs`` helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.protocol import RealtimeOutputModality
from pycodex.protocol import RealtimeAudioFrame
from pycodex.protocol import RealtimeVoice


class RealtimeEventParser(str, Enum):
    V1 = "v1"
    REALTIME_V2 = "realtime_v2"


class RealtimeSessionMode(str, Enum):
    CONVERSATIONAL = "conversational"
    TRANSCRIPTION = "transcription"


@dataclass(frozen=True)
class RealtimeSessionConfig:
    instructions: str
    model: str | None
    session_id: str | None
    event_parser: RealtimeEventParser
    session_mode: RealtimeSessionMode
    output_modality: RealtimeOutputModality
    voice: RealtimeVoice


@dataclass(frozen=True)
class RealtimeTranscriptDelta:
    delta: str


@dataclass(frozen=True)
class RealtimeTranscriptDone:
    text: str


@dataclass(frozen=True)
class RealtimeTranscriptEntry:
    role: str
    text: str


@dataclass(frozen=True)
class RealtimeHandoffRequested:
    handoff_id: str
    item_id: str
    input_transcript: str
    active_transcript: tuple[RealtimeTranscriptEntry, ...] = ()


@dataclass(frozen=True)
class RealtimeNoopRequested:
    call_id: str
    item_id: str


@dataclass(frozen=True)
class RealtimeInputAudioSpeechStarted:
    item_id: str | None = None


@dataclass(frozen=True)
class RealtimeResponseCreated:
    response_id: str | None = None


@dataclass(frozen=True)
class RealtimeResponseCancelled:
    response_id: str | None = None


@dataclass(frozen=True)
class RealtimeResponseDone:
    response_id: str | None = None


@dataclass(frozen=True)
class RealtimeEvent:
    kind: str
    payload: Any = None

    @classmethod
    def session_updated(
        cls,
        realtime_session_id: str,
        instructions: str | None,
    ) -> "RealtimeEvent":
        return cls(
            "SessionUpdated",
            {"realtime_session_id": realtime_session_id, "instructions": instructions},
        )

    @classmethod
    def audio_out(cls, frame: RealtimeAudioFrame) -> "RealtimeEvent":
        return cls("AudioOut", frame)

    @classmethod
    def conversation_item_added(cls, item: Any) -> "RealtimeEvent":
        return cls("ConversationItemAdded", item)

    @classmethod
    def conversation_item_done(cls, item_id: str) -> "RealtimeEvent":
        return cls("ConversationItemDone", {"item_id": item_id})

    @classmethod
    def handoff_requested(cls, handoff: RealtimeHandoffRequested) -> "RealtimeEvent":
        return cls("HandoffRequested", handoff)

    @classmethod
    def noop_requested(cls, noop: RealtimeNoopRequested) -> "RealtimeEvent":
        return cls("NoopRequested", noop)

    @classmethod
    def input_transcript_delta(cls, delta: RealtimeTranscriptDelta) -> "RealtimeEvent":
        return cls("InputTranscriptDelta", delta)

    @classmethod
    def input_transcript_done(cls, done: RealtimeTranscriptDone) -> "RealtimeEvent":
        return cls("InputTranscriptDone", done)

    @classmethod
    def output_transcript_delta(cls, delta: RealtimeTranscriptDelta) -> "RealtimeEvent":
        return cls("OutputTranscriptDelta", delta)

    @classmethod
    def output_transcript_done(cls, done: RealtimeTranscriptDone) -> "RealtimeEvent":
        return cls("OutputTranscriptDone", done)

    @classmethod
    def input_audio_speech_started(
        cls,
        started: RealtimeInputAudioSpeechStarted,
    ) -> "RealtimeEvent":
        return cls("InputAudioSpeechStarted", started)

    @classmethod
    def response_created(cls, created: RealtimeResponseCreated) -> "RealtimeEvent":
        return cls("ResponseCreated", created)

    @classmethod
    def response_cancelled(cls, cancelled: RealtimeResponseCancelled) -> "RealtimeEvent":
        return cls("ResponseCancelled", cancelled)

    @classmethod
    def response_done(cls, done: RealtimeResponseDone) -> "RealtimeEvent":
        return cls("ResponseDone", done)

    @classmethod
    def error(cls, message: str) -> "RealtimeEvent":
        return cls("Error", message)


def parse_realtime_event(payload: str, event_parser: RealtimeEventParser) -> RealtimeEvent | None:
    if event_parser == RealtimeEventParser.V1:
        from .protocol_v1 import parse_realtime_event_v1

        return parse_realtime_event_v1(payload)
    from .protocol_v2 import parse_realtime_event_v2

    return parse_realtime_event_v2(payload)
