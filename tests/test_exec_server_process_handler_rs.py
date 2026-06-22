"""Rust-derived tests for codex-exec-server/src/server/process_handler.rs."""

from __future__ import annotations

import asyncio

from pycodex.exec_server import (
    ByteChunk,
    ExecParams,
    ExecResponse,
    LocalProcess,
    ProcessHandler,
    ProcessId,
    ReadParams,
    ReadResponse,
    TerminateParams,
    TerminateResponse,
    WriteParams,
    WriteResponse,
    WriteStatus,
)


class FakeLocalProcess:
    def __init__(self) -> None:
        self.notifications = "initial"
        self.shutdown_called = False
        self.calls: list[tuple[str, object]] = []

    async def shutdown(self) -> None:
        self.shutdown_called = True
        self.calls.append(("shutdown", None))

    def set_notification_sender(self, notifications) -> None:
        self.notifications = notifications
        self.calls.append(("set_notification_sender", notifications))

    async def exec(self, params: ExecParams) -> ExecResponse:
        self.calls.append(("exec", params))
        return ExecResponse(process_id=params.process_id)

    async def exec_read(self, params: ReadParams) -> ReadResponse:
        self.calls.append(("exec_read", params))
        return ReadResponse(chunks=[], next_seq=1, exited=False, exit_code=None, closed=False)

    async def exec_write(self, params: WriteParams) -> WriteResponse:
        self.calls.append(("exec_write", params))
        return WriteResponse(status=WriteStatus.ACCEPTED)

    async def terminate_process(self, params: TerminateParams) -> TerminateResponse:
        self.calls.append(("terminate_process", params))
        return TerminateResponse(running=False)


def _exec_params(process_id: str = "proc-1") -> ExecParams:
    return ExecParams(
        process_id=ProcessId.new(process_id),
        argv=["echo", "ok"],
        cwd=".",
        env={},
        tty=False,
    )


def test_process_handler_new_wraps_local_process_boundary():
    # Rust: codex-exec-server/src/server/process_handler.rs::ProcessHandler::new
    # Contract: ProcessHandler owns a LocalProcess created with the notification
    # sender; PTY execution remains a separate local_process.rs runtime slice.
    handler = ProcessHandler.new("notifications")

    assert isinstance(handler.process, LocalProcess)
    assert handler.notifications == "notifications"
    result = asyncio.run(handler.exec(ExecParams(**{**_exec_params().__dict__, "tty": True})))
    assert result.code == -32603
    assert result.message == "codex-exec-server LocalProcess PTY runtime is not ported"


def test_process_handler_delegates_lifecycle_and_notification_sender():
    # Rust: ProcessHandler::{shutdown,set_notification_sender}
    # Contract: lifecycle and notification sender updates are thin delegates to
    # the wrapped LocalProcess.
    process = FakeLocalProcess()
    handler = ProcessHandler(process)

    async def run():
        handler.set_notification_sender("next")
        await handler.shutdown()

    asyncio.run(run())

    assert handler.notifications == "next"
    assert handler.shutdown_called is True
    assert process.calls == [("set_notification_sender", "next"), ("shutdown", None)]


def test_process_handler_delegates_exec_read_write_and_terminate():
    # Rust: ProcessHandler::{exec,exec_read,exec_write,terminate}
    # Contract: process requests are delegated unchanged, and terminate calls
    # LocalProcess::terminate_process.
    process = FakeLocalProcess()
    handler = ProcessHandler(process)
    exec_params = _exec_params()
    read_params = ReadParams(process_id=exec_params.process_id, after_seq=2, max_bytes=10, wait_ms=5)
    write_params = WriteParams(process_id=exec_params.process_id, chunk=ByteChunk(b"x"))
    terminate_params = TerminateParams(process_id=exec_params.process_id)

    async def run():
        exec_response = await handler.exec(exec_params)
        read_response = await handler.exec_read(read_params)
        write_response = await handler.exec_write(write_params)
        terminate_response = await handler.terminate(terminate_params)
        return exec_response, read_response, write_response, terminate_response

    exec_response, read_response, write_response, terminate_response = asyncio.run(run())

    assert exec_response == ExecResponse(process_id=exec_params.process_id)
    assert read_response == ReadResponse(chunks=[], next_seq=1, exited=False, exit_code=None, closed=False)
    assert write_response == WriteResponse(status=WriteStatus.ACCEPTED)
    assert terminate_response == TerminateResponse(running=False)
    assert process.calls == [
        ("exec", exec_params),
        ("exec_read", read_params),
        ("exec_write", write_params),
        ("terminate_process", terminate_params),
    ]
