"""Serde adapter for ``Option<Duration>`` values expressed as seconds."""

from __future__ import annotations

import math


def serialize(value: float | int | None) -> float | None:
    if value is None:
        return None
    return _duration_seconds(value)


def deserialize(value: object) -> float | None:
    if value is None:
        return None
    return _duration_seconds(value)


def _duration_seconds(value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError("duration must be numeric")
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("duration must be finite and non-negative")
    return seconds


__all__ = ["deserialize", "serialize"]
