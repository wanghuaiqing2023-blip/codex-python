from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pycodex.core.tasks.lifecycle import (
    emit_turn_abort_lifecycle,
    emit_turn_error_lifecycle,
    emit_turn_start_lifecycle,
    emit_turn_stop_lifecycle,
)


class Contributors:
    def __init__(self, contributors):
        self._contributors = tuple(contributors)

    def turn_lifecycle_contributors(self):
        return self._contributors


class Recorder:
    def __init__(self):
        self.calls = []

    async def on_turn_start(self, value):
        self.calls.append(("start", value.fields))

    async def on_turn_stop(self, value):
        self.calls.append(("stop", value.fields))

    async def on_turn_abort(self, value):
        self.calls.append(("abort", value.fields))

    async def on_turn_error(self, value):
        self.calls.append(("error", value.fields))


def _session(*contributors):
    return SimpleNamespace(
        services=SimpleNamespace(
            extensions=Contributors(contributors),
            session_extension_data={"session": 1},
            thread_extension_data={"thread": 2},
        )
    )


def _turn_context():
    return SimpleNamespace(
        sub_id="turn-1",
        collaboration_mode="Plan",
        extension_data=SimpleNamespace(as_ref=lambda: {"turn": 3}),
    )


def test_emit_turn_lifecycle_dispatches_rust_input_shapes() -> None:
    # Rust source: codex/codex-rs/core/src/tasks/lifecycle.rs
    # Rust crate/module: codex-core::tasks::lifecycle
    # Contract: turn lifecycle callbacks receive session/thread/turn stores and event-specific fields.
    recorder = Recorder()
    session = _session(recorder)
    turn_context = _turn_context()

    asyncio.run(emit_turn_start_lifecycle(session, turn_context, {"input_tokens": 10}))
    asyncio.run(emit_turn_stop_lifecycle(session, {"turn": 3}))
    asyncio.run(emit_turn_abort_lifecycle(session, "interrupted", {"turn": 3}))
    asyncio.run(emit_turn_error_lifecycle(session, turn_context, {"type": "bad_request"}))

    assert recorder.calls == [
        (
            "start",
            {
                "turn_id": "turn-1",
                "collaboration_mode": "Plan",
                "token_usage_at_turn_start": {"input_tokens": 10},
                "session_store": {"session": 1},
                "thread_store": {"thread": 2},
                "turn_store": {"turn": 3},
            },
        ),
        ("stop", {"session_store": {"session": 1}, "thread_store": {"thread": 2}, "turn_store": {"turn": 3}}),
        (
            "abort",
            {
                "reason": "interrupted",
                "session_store": {"session": 1},
                "thread_store": {"thread": 2},
                "turn_store": {"turn": 3},
            },
        ),
        (
            "error",
            {
                "turn_id": "turn-1",
                "error": {"type": "bad_request"},
                "session_store": {"session": 1},
                "thread_store": {"thread": 2},
                "turn_store": {"turn": 3},
            },
        ),
    ]


def test_emit_turn_lifecycle_ignores_missing_extensions() -> None:
    session = SimpleNamespace(services=SimpleNamespace(extensions=None))
    turn_context = _turn_context()

    asyncio.run(emit_turn_start_lifecycle(session, turn_context, None))
    asyncio.run(emit_turn_stop_lifecycle(session, None))
    asyncio.run(emit_turn_abort_lifecycle(session, "reason", None))
    asyncio.run(emit_turn_error_lifecycle(session, turn_context, "error"))


def test_emit_turn_lifecycle_rejects_non_iterable_contributors_result() -> None:
    session = SimpleNamespace(
        services=SimpleNamespace(
            extensions=SimpleNamespace(turn_lifecycle_contributors=lambda: "bad")
        )
    )

    with pytest.raises(TypeError):
        asyncio.run(emit_turn_stop_lifecycle(session, None))
