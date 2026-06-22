"""Python API boundary for Rust crate ``codex-realtime-webrtc``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from queue import Queue
from typing import Any


class RealtimeWebrtcError(RuntimeError):
    """Python boundary for Rust ``RealtimeWebrtcError``."""

    @classmethod
    def message(cls, value: str) -> "RealtimeWebrtcError":
        return cls(value)


class UnsupportedPlatform(RealtimeWebrtcError):
    """Realtime WebRTC is unsupported on this Python backend/platform."""


class RealtimeWebrtcEventKind(Enum):
    CONNECTED = "Connected"
    LOCAL_AUDIO_LEVEL = "LocalAudioLevel"
    CLOSED = "Closed"
    FAILED = "Failed"


@dataclass(frozen=True)
class RealtimeWebrtcEvent:
    kind: RealtimeWebrtcEventKind
    value: int | str | None = None


@dataclass
class RealtimeWebrtcSessionHandle:
    local_audio_peak_value: int = 0
    inner: Any = None

    def apply_answer_sdp(self, answer_sdp: str) -> None:
        raise UnsupportedPlatform("realtime WebRTC is not supported on this platform")

    def close(self) -> None:
        return None

    def local_audio_peak(self) -> int:
        return self.local_audio_peak_value


@dataclass
class StartedRealtimeWebrtcSession:
    offer_sdp: str
    handle: RealtimeWebrtcSessionHandle
    events: Queue[RealtimeWebrtcEvent] = field(default_factory=Queue)


class RealtimeWebrtcSession:
    @staticmethod
    def start() -> StartedRealtimeWebrtcSession:
        raise UnsupportedPlatform("realtime WebRTC is not supported on this platform")


def message_error(prefix: str, err: object) -> RealtimeWebrtcError:
    return RealtimeWebrtcError.message(f"{prefix}: {err}")


def audio_level_to_peak(audio_level: float) -> int:
    clamped = min(1.0, max(0.0, float(audio_level)))
    return round(clamped * 32767)


__all__ = [
    "RealtimeWebrtcError",
    "RealtimeWebrtcEvent",
    "RealtimeWebrtcEventKind",
    "RealtimeWebrtcSession",
    "RealtimeWebrtcSessionHandle",
    "StartedRealtimeWebrtcSession",
    "UnsupportedPlatform",
    "audio_level_to_peak",
    "message_error",
]
