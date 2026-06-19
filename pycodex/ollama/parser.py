"""JSON pull-update parser for Rust ``codex-ollama/src/parser.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .pull import ChunkProgress, PullEvent, Status, Success


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_u64(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def pull_events_from_value(value: Mapping[str, Any] | object) -> list[PullEvent]:
    """Convert one JSON object representing a pull update into events."""

    if not isinstance(value, Mapping):
        return []

    events: list[PullEvent] = []
    status = _as_str(value.get("status"))
    if status is not None:
        events.append(Status(status))
        if status == "success":
            events.append(Success())

    digest = _as_str(value.get("digest")) or ""
    total = _as_u64(value.get("total"))
    completed = _as_u64(value.get("completed"))
    if total is not None or completed is not None:
        events.append(ChunkProgress(digest=digest, total=total, completed=completed))

    return events


__all__ = ["pull_events_from_value"]
