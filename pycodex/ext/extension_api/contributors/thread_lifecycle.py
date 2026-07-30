"""Thread lifecycle inputs owned by the Rust extension API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..state import ExtensionData


@dataclass(frozen=True)
class ThreadStartInput:
    config: Any
    session_source: Any
    persistent_thread_state_available: bool
    session_store: ExtensionData
    thread_store: ExtensionData


@dataclass(frozen=True)
class ThreadResumeInput:
    session_store: ExtensionData
    thread_store: ExtensionData


@dataclass(frozen=True)
class ThreadIdleInput:
    session_store: ExtensionData
    thread_store: ExtensionData


@dataclass(frozen=True)
class ThreadStopInput:
    session_store: ExtensionData
    thread_store: ExtensionData


__all__ = [
    "ThreadIdleInput",
    "ThreadResumeInput",
    "ThreadStartInput",
    "ThreadStopInput",
]
