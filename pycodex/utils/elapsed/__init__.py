"""Elapsed time formatting ported from ``codex-utils-elapsed``."""

from __future__ import annotations

from datetime import timedelta


def format_duration(duration: timedelta) -> str:
    if not isinstance(duration, timedelta):
        raise TypeError("duration must be a datetime.timedelta")
    millis = _duration_millis(duration)
    if millis < 0:
        raise ValueError("duration must be non-negative")
    return _format_elapsed_millis(millis)


def _duration_millis(duration: timedelta) -> int:
    return (
        duration.days * 24 * 60 * 60 * 1000
        + duration.seconds * 1000
        + duration.microseconds // 1000
    )


def _format_elapsed_millis(millis: int) -> str:
    if millis < 1000:
        return f"{millis}ms"
    if millis < 60_000:
        return f"{millis / 1000.0:.2f}s"
    minutes = millis // 60_000
    seconds = (millis % 60_000) // 1000
    return f"{minutes}m {seconds:02d}s"


__all__ = ["format_duration"]
