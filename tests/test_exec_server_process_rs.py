"""Rust-derived tests for codex-exec-server/src/process.rs."""

from __future__ import annotations

import asyncio

import pytest

from pycodex.exec_server import (
    ByteChunk,
    ExecOutputStream,
    ExecProcess,
    ExecProcessEvent,
    ExecProcessEventLog,
    ExecProcessEventReceiver,
    ProcessOutputChunk,
    StartedExecProcess,
)


def test_process_event_seq_matches_rust_variants():
    # Rust: codex-exec-server/src/process.rs::ExecProcessEvent::seq
    # Contract: Output/Exited/Closed carry process-owned sequence numbers,
    # while Failed is synthesized by the client and intentionally unsequenced.
    output = ExecProcessEvent.output(
        ProcessOutputChunk(seq=7, stream=ExecOutputStream.STDOUT, chunk=ByteChunk(b"ok"))
    )

    assert output.seq() == 7
    assert ExecProcessEvent.exited(seq=8, exit_code=0).seq() == 8
    assert ExecProcessEvent.closed(seq=9).seq() == 9
    assert ExecProcessEvent.failed("disconnected").seq() is None


def test_process_event_retained_len_matches_rust_variants():
    # Rust: codex-exec-server/src/process.rs::ExecProcessEvent::retained_len
    # Contract: Output retains chunk byte length, Failed retains message
    # length, and lifecycle events do not count against byte capacity.
    output = ExecProcessEvent.output(
        ProcessOutputChunk(seq=1, stream=ExecOutputStream.STDERR, chunk=ByteChunk(b"large"))
    )

    assert output.retained_len() == 5
    assert ExecProcessEvent.failed("offline").retained_len() == 7
    assert ExecProcessEvent.exited(seq=2, exit_code=0).retained_len() == 0
    assert ExecProcessEvent.closed(seq=3).retained_len() == 0


def test_event_history_replay_is_bounded_by_retained_bytes():
    # Rust: codex-exec-server/src/process.rs
    # Test: event_history_replay_is_bounded_by_retained_bytes
    # Contract: replay history is bounded by retained output bytes, so a large
    # output event can be evicted while zero-byte lifecycle events remain.
    log = ExecProcessEventLog.new(event_capacity=8, byte_capacity=3)

    log.publish(
        ExecProcessEvent.output(
            ProcessOutputChunk(seq=1, stream=ExecOutputStream.STDOUT, chunk=ByteChunk(b"large"))
        )
    )
    log.publish(ExecProcessEvent.exited(seq=2, exit_code=0))
    log.publish(ExecProcessEvent.closed(seq=3))

    async def replay() -> list[ExecProcessEvent]:
        events = log.subscribe()
        return [
            await asyncio.wait_for(events.recv(), timeout=1),
            await asyncio.wait_for(events.recv(), timeout=1),
        ]

    assert asyncio.run(replay()) == [
        ExecProcessEvent.exited(seq=2, exit_code=0),
        ExecProcessEvent.closed(seq=3),
    ]


def test_event_history_replay_is_bounded_by_event_count():
    # Rust: codex-exec-server/src/process.rs::ExecProcessEventLog::publish
    # Contract: event_capacity also bounds replay history, independent of
    # retained byte count.
    log = ExecProcessEventLog.new(event_capacity=2, byte_capacity=100)
    log.publish(ExecProcessEvent.closed(seq=1))
    log.publish(ExecProcessEvent.closed(seq=2))
    log.publish(ExecProcessEvent.closed(seq=3))

    async def replay() -> list[ExecProcessEvent]:
        events = log.subscribe()
        return [
            await asyncio.wait_for(events.recv(), timeout=1),
            await asyncio.wait_for(events.recv(), timeout=1),
        ]

    assert asyncio.run(replay()) == [
        ExecProcessEvent.closed(seq=2),
        ExecProcessEvent.closed(seq=3),
    ]
    assert log.retained_len() == 2


def test_subscriber_drains_replay_then_receives_live_events():
    # Rust: codex-exec-server/src/process.rs::ExecProcessEventReceiver::recv
    # Contract: receivers first drain replayed history, then continue on the
    # live broadcast stream.
    log = ExecProcessEventLog.new(event_capacity=4, byte_capacity=100)
    log.publish(ExecProcessEvent.closed(seq=1))
    events = log.subscribe()
    log.publish(ExecProcessEvent.closed(seq=2))

    async def receive() -> list[ExecProcessEvent]:
        return [
            await asyncio.wait_for(events.recv(), timeout=1),
            await asyncio.wait_for(events.recv(), timeout=1),
        ]

    assert asyncio.run(receive()) == [
        ExecProcessEvent.closed(seq=1),
        ExecProcessEvent.closed(seq=2),
    ]


def test_empty_receiver_has_no_replay():
    # Rust: codex-exec-server/src/process.rs::ExecProcessEventReceiver::empty
    # Contract: an empty receiver has no replayed events and only waits on its
    # live channel.
    receiver = ExecProcessEventReceiver.empty()

    async def receive() -> None:
        await asyncio.wait_for(receiver.recv(), timeout=0.01)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(receive())


def test_process_trait_boundaries_are_explicitly_unported():
    # Rust: codex-exec-server/src/process.rs::ExecProcess / StartedExecProcess
    # Contract: Python exposes the process trait surface but does not claim the
    # actual runtime implementation in this module slice.
    process = ExecProcess()
    started = StartedExecProcess(process=process)

    assert started.process is process
    with pytest.raises(NotImplementedError, match="process runtime is not ported"):
        process.process_id()
