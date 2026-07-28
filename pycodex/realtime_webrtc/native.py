"""Platform-native helpers from Rust ``realtime-webrtc/src/native.rs``."""

from __future__ import annotations

import math

from . import RealtimeWebrtcError


def message_error(prefix: str, err: object) -> RealtimeWebrtcError:
    return RealtimeWebrtcError.message(f"{prefix}: {err}")


def audio_level_to_peak(audio_level: float) -> int:
    clamped = min(1.0, max(0.0, float(audio_level)))
    return math.floor(clamped * 32767 + 0.5)


__all__: list[str] = []
