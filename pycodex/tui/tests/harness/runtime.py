"""Fake active-thread runtime for TUI automation harnesses.

Rust ownership:
- ``codex-tui::app`` submits user turns to the active thread runtime.
- ``codex-tui::chatwidget::protocol`` receives server notifications back from
  that active thread.

This test helper models only that runtime boundary.  It is intentionally
independent from the legacy terminal-projection runner so Textual product tests
do not import the old renderer harness.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from queue import Queue
from typing import Any

from pycodex.tui.app.runtime import QueueActiveThreadEventStream
from pycodex.tui.chatwidget.protocol import ServerNotification


@dataclass
class ManualActiveThreadRuntime:
    """Fake active-thread runtime that exposes the Rust-shaped submit boundary."""

    queue: Queue[Any] = field(default_factory=Queue)
    submitted: threading.Event = field(default_factory=threading.Event)
    submitted_condition: threading.Condition = field(default_factory=threading.Condition)
    submitted_ops: list[Any] = field(default_factory=list)
    submitted_thread_ids: list[str] = field(default_factory=list)

    def submit_thread_op(self, thread_id: str, op: Any) -> QueueActiveThreadEventStream:
        with self.submitted_condition:
            self.submitted_thread_ids.append(thread_id)
            self.submitted_ops.append(op)
            self.submitted.set()
            self.submitted_condition.notify_all()
        return QueueActiveThreadEventStream(self.queue)

    def send(self, notification: ServerNotification) -> None:
        self.queue.put(notification)

    def close(self) -> None:
        self.queue.put(None)
