from __future__ import annotations

import asyncio

import pytest

from pycodex.exec_server import (
    ByteChunk,
    ExecOutputStream,
    ExecParams,
    ExecProcessEvent,
    ExecProcessEventLog,
    ExecServerError,
    ExecServerTransportParams,
    LazyRemoteExecServerClient,
    ProcessId,
    ProcessOutputChunk,
    ReadResponse,
    RemoteExecProcess,
    RemoteProcessBoundary,
    WriteResponse,
    WriteStatus,
)


def _transport() -> ExecServerTransportParams:
    return ExecServerTransportParams.from_websocket_url("ws://127.0.0.1:9999")


def _backend(client: object) -> RemoteProcessBoundary:
    return RemoteProcessBoundary.new(LazyRemoteExecServerClient(_transport(), client=client))


def _exec_params(process_id: str = "remote-proc") -> ExecParams:
    return ExecParams(
        process_id=ProcessId.new(process_id),
        argv=["echo", "hi"],
        cwd="/tmp",
        env={},
        tty=False,
        pipe_stdin=False,
    )


def test_remote_process_start_registers_session_then_execs() -> None:
    # Rust crate/module:
    # codex-exec-server/src/remote_process.rs::RemoteProcess::start.
    # Contract: remote start obtains the lazy client, registers the process
    # session, calls client.exec with the original params, and returns a process
    # facade backed by that session.
    async def run() -> tuple[list[object], ProcessId]:
        client = RecordingRemoteClient()
        started = await _backend(client).start(_exec_params("alpha"))
        return client.calls, started.process.process_id()

    calls, process_id = asyncio.run(run())

    assert calls == [
        ("register_session", ProcessId.new("alpha")),
        ("exec", _exec_params("alpha")),
    ]
    assert process_id == ProcessId.new("alpha")


def test_remote_process_start_unregisters_session_when_exec_fails() -> None:
    # Rust source contract: if client.exec(params) fails after registration,
    # RemoteProcess unregisters the session before returning the error.
    async def run() -> tuple[str, list[object], list[str]]:
        client = RecordingRemoteClient(exec_error=ExecServerError.protocol("boom"))
        with pytest.raises(ExecServerError) as exc_info:
            await _backend(client).start(_exec_params("failing"))
        return str(exc_info.value), client.calls, client.sessions["failing"].unregisters

    error, calls, unregisters = asyncio.run(run())

    assert error == "exec-server protocol error: boom"
    assert calls == [
        ("register_session", ProcessId.new("failing")),
        ("exec", _exec_params("failing")),
    ]
    assert unregisters == ["failing"]


def test_remote_exec_process_delegates_session_methods() -> None:
    # Rust crate/module:
    # codex-exec-server/src/remote_process.rs impl ExecProcess for
    # RemoteExecProcess. Contract: all process APIs delegate to the client
    # session returned by register_session.
    async def run() -> tuple[object, object, object, object, object, object, list[object], list[str]]:
        session = RecordingSession(ProcessId.new("delegate"))
        process = RemoteExecProcess(session)
        events = process.subscribe_events()
        wake = process.subscribe_wake()
        read = await process.read(1, 2, 3)
        write = await process.write(b"stdin")
        terminate = await process.terminate()
        await process.unregister()
        return (
            process.process_id(),
            events,
            wake,
            read,
            write,
            terminate,
            session.calls,
            session.unregisters,
        )

    process_id, events, wake, read, write, terminate, calls, unregisters = asyncio.run(run())

    assert process_id == ProcessId.new("delegate")
    assert events is not None
    assert wake == "wake:delegate"
    assert read == ReadResponse(chunks=[], next_seq=4, exited=False, exit_code=None, closed=False)
    assert write == WriteResponse(status=WriteStatus.ACCEPTED)
    assert terminate is None
    assert calls == [
        ("subscribe_events",),
        ("subscribe_wake",),
        ("read", 1, 2, 3),
        ("write", b"stdin"),
        ("terminate",),
    ]
    assert unregisters == ["delegate"]


class RecordingRemoteClient:
    def __init__(self, exec_error: Exception | None = None) -> None:
        self.exec_error = exec_error
        self.calls: list[object] = []
        self.sessions: dict[str, RecordingSession] = {}

    async def register_session(self, process_id: ProcessId) -> "RecordingSession":
        self.calls.append(("register_session", process_id))
        session = RecordingSession(process_id)
        self.sessions[process_id.as_str()] = session
        return session

    async def exec(self, params: ExecParams) -> None:
        self.calls.append(("exec", params))
        if self.exec_error is not None:
            raise self.exec_error


class RecordingSession:
    def __init__(self, process_id: ProcessId) -> None:
        self._process_id = process_id
        self.calls: list[object] = []
        self.unregisters: list[str] = []
        self.event_log = ExecProcessEventLog.new(4, 1024)
        self.event_log.publish(
            ExecProcessEvent.output(
                ProcessOutputChunk(1, ExecOutputStream.STDOUT, ByteChunk(b"ready"))
            )
        )

    def process_id(self) -> ProcessId:
        return self._process_id

    def subscribe_wake(self) -> str:
        self.calls.append(("subscribe_wake",))
        return f"wake:{self._process_id.as_str()}"

    def subscribe_events(self):
        self.calls.append(("subscribe_events",))
        return self.event_log.subscribe()

    async def read(self, after_seq, max_bytes, wait_ms) -> ReadResponse:
        self.calls.append(("read", after_seq, max_bytes, wait_ms))
        return ReadResponse(chunks=[], next_seq=4, exited=False, exit_code=None, closed=False)

    async def write(self, chunk: bytes) -> WriteResponse:
        self.calls.append(("write", chunk))
        return WriteResponse(status=WriteStatus.ACCEPTED)

    async def terminate(self) -> None:
        self.calls.append(("terminate",))

    async def unregister(self) -> None:
        self.unregisters.append(self._process_id.as_str())
