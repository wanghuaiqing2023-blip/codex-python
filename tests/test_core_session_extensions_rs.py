from __future__ import annotations

import asyncio

from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.extension_api import ExtensionData, ExtensionRegistryBuilder
from pycodex.protocol import TokenUsage


class Recorder:
    def __init__(self) -> None:
        self.thread_starts = []
        self.turn_starts = []
        self.turn_stops = []
        self.turn_aborts = []
        self.token_updates = []

    async def on_thread_start(self, input) -> None:
        self.thread_starts.append(input)

    async def on_turn_start(self, input) -> None:
        self.turn_starts.append(input)

    async def on_turn_stop(self, input) -> None:
        self.turn_stops.append(input)

    async def on_turn_abort(self, input) -> None:
        self.turn_aborts.append(input)

    async def on_token_usage(self, session_store, thread_store, turn_store, token_usage) -> None:
        self.token_updates.append((session_store, thread_store, turn_store, token_usage))


def _session_with_recorder(recorder: Recorder) -> InMemoryCodexSession:
    session = InMemoryCodexSession(cwd="C:/work", thread_id="thread-1")
    builder = ExtensionRegistryBuilder.new()
    builder.thread_lifecycle_contributor(recorder)
    builder.turn_lifecycle_contributor(recorder)
    builder.token_usage_contributor(recorder)
    session.services.extensions = builder.build()
    return session


def test_session_owns_rust_scoped_extension_stores() -> None:
    session = InMemoryCodexSession(cwd="C:/work", thread_id="thread-1")

    assert isinstance(session.services.session_extension_data, ExtensionData)
    assert isinstance(session.services.thread_extension_data, ExtensionData)
    assert session.services.thread_extension_data.level_id() == "thread-1"
    first = asyncio.run(session.new_default_turn())
    second = asyncio.run(session.new_default_turn())
    assert isinstance(first.extension_data, ExtensionData)
    assert first.extension_data.level_id() == first.turn_id
    assert first.extension_data is not second.extension_data
    assert first.turn_id != second.turn_id


def test_thread_lifecycle_starts_once_before_turn_creation() -> None:
    recorder = Recorder()
    session = _session_with_recorder(recorder)

    asyncio.run(session.new_default_turn())
    asyncio.run(session.new_default_turn())

    assert len(recorder.thread_starts) == 1
    value = recorder.thread_starts[0]
    assert value.thread_store is session.services.thread_extension_data
    assert value.persistent_thread_state_available is False


def test_session_forwards_turn_and_token_lifecycle_through_registry() -> None:
    recorder = Recorder()
    session = _session_with_recorder(recorder)
    turn = asyncio.run(session.new_default_turn())

    asyncio.run(session.emit_turn_start_lifecycle(turn, TokenUsage(total_tokens=3)))
    asyncio.run(session.record_token_usage_info(turn, TokenUsage(input_tokens=5, output_tokens=2, total_tokens=7)))
    asyncio.run(session.emit_turn_stop_lifecycle(turn.extension_data))
    asyncio.run(session.emit_turn_abort_lifecycle("interrupted", turn.extension_data))

    assert recorder.turn_starts[0].turn_store is turn.extension_data
    assert recorder.token_updates[0][2] is turn.extension_data
    assert recorder.token_updates[0][3].total_token_usage.total_tokens == 7
    assert recorder.turn_stops[0].turn_store is turn.extension_data
    assert recorder.turn_aborts[0].reason == "interrupted"
