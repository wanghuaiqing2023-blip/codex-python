"""Shared state models for Rust ``codex-debug-client/src/state.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PendingRequest(str, Enum):
    START = "Start"
    RESUME = "Resume"
    LIST = "List"


@dataclass
class State:
    pending: dict[str, PendingRequest] = field(default_factory=dict)
    thread_id: str | None = None
    known_threads: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReaderEvent:
    kind: str
    thread_id: str | None = None
    thread_ids: list[str] = field(default_factory=list)
    next_cursor: str | None = None

    @classmethod
    def thread_ready(cls, thread_id: str) -> "ReaderEvent":
        return cls("ThreadReady", thread_id=str(thread_id))

    @classmethod
    def thread_list(cls, thread_ids: list[str], next_cursor: str | None = None) -> "ReaderEvent":
        return cls("ThreadList", thread_ids=list(thread_ids), next_cursor=next_cursor)


__all__ = ["PendingRequest", "ReaderEvent", "State"]
