from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pycodex.app_server.connection_rpc_gate import ConnectionRpcGate
from pycodex.app_server.request_serialization import (
    QueuedInitializedRequest,
    RequestSerializationAccess,
    RequestSerializationQueueKey,
    RequestSerializationQueues,
)
from pycodex.app_server_protocol import ClientRequestSerializationScope


def request(gate: ConnectionRpcGate, body):
    return QueuedInitializedRequest.new(gate, body)


@pytest.mark.asyncio
async def test_same_key_requests_run_fifo() -> None:
    # Rust source: same_key_requests_run_fifo.
    queues = RequestSerializationQueues.default()
    key = RequestSerializationQueueKey.global_("test")
    gate = ConnectionRpcGate.new()
    values: list[int] = []

    for value in [1, 2, 3]:
        await queues.enqueue(
            key,
            RequestSerializationAccess.EXCLUSIVE,
            request(gate, lambda value=value: values.append(value)),
        )

    await queues.wait_idle()
    assert values == [1, 2, 3]


@pytest.mark.asyncio
async def test_different_keys_run_concurrently() -> None:
    # Rust source: different_keys_run_concurrently.
    queues = RequestSerializationQueues.default()
    blocked_started = asyncio.Event()
    release_blocked = asyncio.Event()
    other_ran = asyncio.Event()

    async def blocked() -> None:
        blocked_started.set()
        await release_blocked.wait()

    async def other() -> None:
        other_ran.set()

    await queues.enqueue(
        RequestSerializationQueueKey.global_("blocked"),
        RequestSerializationAccess.EXCLUSIVE,
        request(ConnectionRpcGate.new(), blocked),
    )
    await blocked_started.wait()
    await queues.enqueue(
        RequestSerializationQueueKey.global_("other"),
        RequestSerializationAccess.EXCLUSIVE,
        request(ConnectionRpcGate.new(), other),
    )

    await asyncio.wait_for(other_ran.wait(), timeout=1)
    release_blocked.set()
    await queues.wait_idle()


@pytest.mark.asyncio
async def test_closed_gate_request_is_skipped_and_following_requests_continue() -> None:
    # Rust source: closed_gate_request_is_skipped_and_following_requests_continue.
    queues = RequestSerializationQueues.default()
    key = RequestSerializationQueueKey.global_("test")
    live_gate = ConnectionRpcGate.new()
    closed_gate = ConnectionRpcGate.new()
    await closed_gate.shutdown()
    values: list[int] = []
    release_first = asyncio.Event()

    async def first() -> None:
        values.append(1)
        await release_first.wait()

    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(live_gate, first))
    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(closed_gate, lambda: values.append(2)))
    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(live_gate, lambda: values.append(3)))

    while values != [1]:
        await asyncio.sleep(0)
    release_first.set()
    await queues.wait_idle()
    assert values == [1, 3]


@pytest.mark.asyncio
async def test_shutdown_of_live_gate_skips_already_queued_requests() -> None:
    # Rust source: shutdown_of_live_gate_skips_already_queued_requests.
    queues = RequestSerializationQueues.default()
    key = RequestSerializationQueueKey.global_("test")
    live_gate = ConnectionRpcGate.new()
    values: list[int] = []
    release_first = asyncio.Event()

    async def first() -> None:
        values.append(1)
        await release_first.wait()

    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(live_gate, first))
    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(live_gate, lambda: values.append(2)))

    while values != [1]:
        await asyncio.sleep(0)
    shutdown_task = asyncio.create_task(live_gate.shutdown())
    await asyncio.sleep(0)
    assert not shutdown_task.done()
    release_first.set()
    await queues.wait_idle()
    await shutdown_task
    assert values == [1]


@pytest.mark.asyncio
async def test_same_key_shared_reads_run_concurrently() -> None:
    # Rust source: same_key_shared_reads_run_concurrently.
    queues = RequestSerializationQueues.default()
    key = RequestSerializationQueueKey.global_("test")
    blocker_started = asyncio.Event()
    blocker_release = asyncio.Event()
    shared_started: list[int] = []
    shared_release = asyncio.Event()

    async def blocker() -> None:
        blocker_started.set()
        await blocker_release.wait()

    async def shared(value: int) -> None:
        shared_started.append(value)
        await shared_release.wait()

    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(ConnectionRpcGate.new(), blocker))
    await blocker_started.wait()
    for value in [1, 2]:
        await queues.enqueue(
            key,
            RequestSerializationAccess.SHARED_READ,
            request(ConnectionRpcGate.new(), lambda value=value: shared(value)),
        )

    blocker_release.set()
    while sorted(shared_started) != [1, 2]:
        await asyncio.sleep(0)
    assert shared_started == [1, 2]
    shared_release.set()
    await queues.wait_idle()


@pytest.mark.asyncio
async def test_exclusive_write_waits_for_running_shared_reads() -> None:
    # Rust source: exclusive_write_waits_for_running_shared_reads.
    queues = RequestSerializationQueues.default()
    key = RequestSerializationQueueKey.global_("test")
    blocker_started = asyncio.Event()
    blocker_release = asyncio.Event()
    read_started: list[int] = []
    read_release = asyncio.Event()
    write_started = asyncio.Event()

    async def blocker() -> None:
        blocker_started.set()
        await blocker_release.wait()

    async def read(value: int) -> None:
        read_started.append(value)
        await read_release.wait()

    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(ConnectionRpcGate.new(), blocker))
    await blocker_started.wait()
    for value in [1, 2]:
        await queues.enqueue(
            key,
            RequestSerializationAccess.SHARED_READ,
            request(ConnectionRpcGate.new(), lambda value=value: read(value)),
        )
    await queues.enqueue(
        key,
        RequestSerializationAccess.EXCLUSIVE,
        request(ConnectionRpcGate.new(), lambda: write_started.set()),
    )

    blocker_release.set()
    while sorted(read_started) != [1, 2]:
        await asyncio.sleep(0)
    assert not write_started.is_set()
    read_release.set()
    await asyncio.wait_for(write_started.wait(), timeout=1)
    await queues.wait_idle()


@pytest.mark.asyncio
async def test_later_shared_reads_do_not_jump_ahead_of_queued_write() -> None:
    # Rust source: later_shared_reads_do_not_jump_ahead_of_queued_write.
    queues = RequestSerializationQueues.default()
    key = RequestSerializationQueueKey.global_("test")
    blocker_started = asyncio.Event()
    blocker_release = asyncio.Event()
    first_read_started = asyncio.Event()
    first_read_release = asyncio.Event()
    write_started = asyncio.Event()
    write_release = asyncio.Event()
    later_read_started = asyncio.Event()

    async def blocker() -> None:
        blocker_started.set()
        await blocker_release.wait()

    async def first_read() -> None:
        first_read_started.set()
        await first_read_release.wait()

    async def write() -> None:
        write_started.set()
        await write_release.wait()

    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(ConnectionRpcGate.new(), blocker))
    await blocker_started.wait()
    await queues.enqueue(key, RequestSerializationAccess.SHARED_READ, request(ConnectionRpcGate.new(), first_read))
    await queues.enqueue(key, RequestSerializationAccess.EXCLUSIVE, request(ConnectionRpcGate.new(), write))
    await queues.enqueue(
        key,
        RequestSerializationAccess.SHARED_READ,
        request(ConnectionRpcGate.new(), lambda: later_read_started.set()),
    )

    blocker_release.set()
    await asyncio.wait_for(first_read_started.wait(), timeout=1)
    assert not write_started.is_set()
    assert not later_read_started.is_set()
    first_read_release.set()
    await asyncio.wait_for(write_started.wait(), timeout=1)
    assert not later_read_started.is_set()
    write_release.set()
    await asyncio.wait_for(later_read_started.wait(), timeout=1)
    await queues.wait_idle()


def test_queue_key_from_scope_maps_connection_scoped_variants() -> None:
    # Rust source: RequestSerializationQueueKey::from_scope maps connection-scoped process/fs-watch variants.
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.global_("config"),
    ) == (RequestSerializationQueueKey.global_("config"), RequestSerializationAccess.EXCLUSIVE)
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.global_shared_read("config"),
    ) == (RequestSerializationQueueKey.global_("config"), RequestSerializationAccess.SHARED_READ)
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.thread("thread-1"),
    ) == (RequestSerializationQueueKey.thread("thread-1"), RequestSerializationAccess.EXCLUSIVE)
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.thread_path(Path("resume.jsonl")),
    ) == (RequestSerializationQueueKey.thread_path(Path("resume.jsonl")), RequestSerializationAccess.EXCLUSIVE)
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.command_exec_process("proc-1"),
    ) == (RequestSerializationQueueKey.command_exec_process(7, "proc-1"), RequestSerializationAccess.EXCLUSIVE)
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.process("handle-1"),
    ) == (RequestSerializationQueueKey.process(7, "handle-1"), RequestSerializationAccess.EXCLUSIVE)
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.fuzzy_file_search_session("session-1"),
    ) == (RequestSerializationQueueKey.fuzzy_file_search_session("session-1"), RequestSerializationAccess.EXCLUSIVE)
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.fs_watch("watch-1"),
    ) == (RequestSerializationQueueKey.fs_watch(7, "watch-1"), RequestSerializationAccess.EXCLUSIVE)
    assert RequestSerializationQueueKey.from_scope(
        7,
        ClientRequestSerializationScope.mcp_oauth("server-a"),
    ) == (RequestSerializationQueueKey.mcp_oauth("server-a"), RequestSerializationAccess.EXCLUSIVE)
