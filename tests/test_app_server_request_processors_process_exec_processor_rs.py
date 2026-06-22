"""Rust parity tests for ``codex-app-server/src/request_processors/process_exec_processor.rs``."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.app_server.command_exec import DEFAULT_OUTPUT_BYTES_CAP, TerminalSize
from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server.request_processors_process_exec_processor import (
    ProcessControlKind,
    ProcessExecManager,
    ProcessExecManagerError,
    ProcessExecRequestProcessor,
    ProcessExecRequestProcessorError,
    handle_process_output,
    no_active_process_error,
    process_no_longer_running_error,
    terminal_size_from_protocol,
)
from pycodex.app_server_protocol import (
    ProcessKillParams,
    ProcessOutputStream,
    ProcessResizePtyParams,
    ProcessSpawnParams,
    ProcessTerminalSize,
    ProcessWriteStdinParams,
    UNSET,
)


class EnvironmentManager:
    def __init__(self, has_local_environment: bool = True) -> None:
        self.has_local_environment = has_local_environment

    def try_local_environment(self):
        return object() if self.has_local_environment else None


class Outgoing:
    def __init__(self) -> None:
        self.responses = []

    async def send_response(self, request_id, response) -> None:
        self.responses.append((request_id, response))


def request_id(connection_id=7):
    return ConnectionRequestId(connection_id=connection_id, request_id=1)


def spawn_params(**overrides):
    values = {
        "command": ("python", "-V"),
        "process_handle": "proc-1",
        "cwd": Path.cwd(),
    }
    values.update(overrides)
    return ProcessSpawnParams(**values)


def assert_error(excinfo, message: str, code: int) -> None:
    assert excinfo.value.error.message == message
    assert excinfo.value.error.code == code


def test_process_spawn_requires_local_environment_like_rust() -> None:
    processor = ProcessExecRequestProcessor.new(Outgoing(), EnvironmentManager(False))

    with pytest.raises(ProcessExecRequestProcessorError) as excinfo:
        asyncio.run(processor.process_spawn(request_id(), spawn_params()))

    assert_error(excinfo, "local environment is not configured", -32603)


def test_process_spawn_validates_rust_request_fields_before_start() -> None:
    processor = ProcessExecRequestProcessor.new(Outgoing(), EnvironmentManager())

    with pytest.raises(ProcessExecRequestProcessorError) as excinfo:
        asyncio.run(
            processor.process_spawn(
                request_id(),
                SimpleNamespace(
                    command=(),
                    process_handle="proc",
                    cwd=Path.cwd(),
                    tty=False,
                    stream_stdin=False,
                    stream_stdout_stderr=False,
                    output_bytes_cap=UNSET,
                    timeout_ms=UNSET,
                    env=None,
                    size=None,
                ),
            )
        )
    assert_error(excinfo, "command must not be empty", -32600)

    with pytest.raises(ProcessExecRequestProcessorError) as excinfo:
        asyncio.run(
            processor.process_spawn(
                request_id(),
                SimpleNamespace(
                    command=("python",),
                    process_handle="",
                    cwd=Path.cwd(),
                    tty=False,
                    stream_stdin=False,
                    stream_stdout_stderr=False,
                    output_bytes_cap=UNSET,
                    timeout_ms=UNSET,
                    env=None,
                    size=None,
                ),
            )
        )
    assert_error(excinfo, "processHandle must not be empty", -32600)

    with pytest.raises(ProcessExecRequestProcessorError) as excinfo:
        asyncio.run(processor.process_spawn(request_id(), spawn_params(size=ProcessTerminalSize(rows=24, cols=80))))
    assert_error(excinfo, "process/spawn size requires tty: true", -32602)


def test_process_spawn_projects_env_timeout_output_size_and_sends_response() -> None:
    outgoing = Outgoing()
    manager = ProcessExecManager()
    processor = ProcessExecRequestProcessor(
        outgoing,
        EnvironmentManager(),
        process_exec_manager=manager,
    )

    asyncio.run(
        processor.process_spawn(
            request_id(),
            spawn_params(
                tty=True,
                stream_stdin=False,
                stream_stdout_stderr=False,
                output_bytes_cap=128,
                timeout_ms=2500,
                env={"PYCODEX_PROCESS_TEST": "1", "PATH": None},
                size=ProcessTerminalSize(rows=30, cols=100),
            ),
        )
    )

    started = manager.started[-1]
    projection = manager.session_for(7, "proc-1")
    assert started.command == ("python", "-V")
    assert started.expiration.kind == "Timeout"
    assert started.expiration.timeout_ms == 2500
    assert started.output_bytes_cap == 128
    assert started.size == TerminalSize(rows=30, cols=100)
    assert started.env["PYCODEX_PROCESS_TEST"] == "1"
    assert "PATH" not in started.env
    assert projection is not None
    assert projection.stream_stdin is True
    assert len(outgoing.responses) == 1


def test_process_spawn_defaults_output_cap_and_timeout_semantics() -> None:
    manager = ProcessExecManager()
    processor = ProcessExecRequestProcessor(Outgoing(), EnvironmentManager(), process_exec_manager=manager)

    asyncio.run(processor.process_spawn(request_id(), spawn_params()))
    assert manager.started[-1].output_bytes_cap == DEFAULT_OUTPUT_BYTES_CAP
    assert manager.started[-1].expiration.kind == "DefaultTimeout"

    asyncio.run(processor.process_spawn(request_id(), spawn_params(process_handle="proc-2", timeout_ms=None)))
    assert manager.started[-1].expiration.kind == "Cancellation"

    with pytest.raises(ProcessExecRequestProcessorError) as excinfo:
        asyncio.run(processor.process_spawn(request_id(), spawn_params(process_handle="proc-3", timeout_ms=-1)))
    assert_error(excinfo, "process/spawn timeoutMs must be non-negative, got -1", -32602)


def test_manager_rejects_duplicate_handles_and_routes_controls() -> None:
    manager = ProcessExecManager()
    processor = ProcessExecRequestProcessor(Outgoing(), EnvironmentManager(), process_exec_manager=manager)

    asyncio.run(processor.process_spawn(request_id(), spawn_params(stream_stdin=True)))

    with pytest.raises(ProcessExecRequestProcessorError) as excinfo:
        asyncio.run(processor.process_spawn(request_id(), spawn_params()))
    assert_error(excinfo, "duplicate active process handle: 'proc-1'", -32600)

    delta = base64.b64encode(b"hello").decode("ascii")
    response = asyncio.run(
        processor.process_write_stdin(
            request_id(),
            ProcessWriteStdinParams(process_handle="proc-1", delta_base64=delta, close_stdin=True),
        )
    )
    assert response.to_mapping() == {}
    session = manager.session_for(7, "proc-1")
    assert session is not None
    assert session.controls[-1].kind is ProcessControlKind.WRITE
    assert session.controls[-1].delta == b"hello"
    assert session.controls[-1].close_stdin is True

    asyncio.run(
        processor.process_resize_pty(
            request_id(),
            ProcessResizePtyParams(process_handle="proc-1", size=ProcessTerminalSize(rows=40, cols=120)),
        )
    )
    assert session.controls[-1].kind is ProcessControlKind.RESIZE
    assert session.controls[-1].size == TerminalSize(rows=40, cols=120)

    asyncio.run(processor.process_kill(request_id(), ProcessKillParams(process_handle="proc-1")))
    assert session.controls[-1].kind is ProcessControlKind.KILL


def test_write_stdin_validation_and_missing_process_errors_match_rust() -> None:
    manager = ProcessExecManager()

    with pytest.raises(ProcessExecManagerError) as excinfo:
        asyncio.run(
            manager.write_stdin(
                request_id(),
                ProcessWriteStdinParams(process_handle="missing", delta_base64=None, close_stdin=False),
            )
        )
    assert_error(excinfo, "process/writeStdin requires deltaBase64 or closeStdin", -32602)

    with pytest.raises(ProcessExecManagerError) as excinfo:
        asyncio.run(
            manager.write_stdin(
                request_id(),
                ProcessWriteStdinParams(process_handle="missing", delta_base64="not-base64!", close_stdin=False),
            )
        )
    assert "invalid deltaBase64:" in excinfo.value.error.message
    assert excinfo.value.error.code == -32602

    with pytest.raises(ProcessExecManagerError) as excinfo:
        asyncio.run(manager.kill(request_id(), ProcessKillParams(process_handle="missing")))
    assert_error(excinfo, "no active process for process handle 'missing'", -32600)


def test_terminal_size_and_error_helpers_match_rust_text() -> None:
    assert terminal_size_from_protocol(ProcessTerminalSize(rows=1, cols=2)) == TerminalSize(rows=1, cols=2)
    with pytest.raises(ProcessExecRequestProcessorError) as excinfo:
        terminal_size_from_protocol(ProcessTerminalSize(rows=0, cols=2))
    assert_error(excinfo, "process size rows and cols must be greater than 0", -32602)

    assert no_active_process_error("abc").message == "no active process for process handle 'abc'"
    assert process_no_longer_running_error("abc").message == "process 'abc' is no longer running"


def test_connection_closed_removes_sessions_and_records_kill_control() -> None:
    manager = ProcessExecManager()
    processor = ProcessExecRequestProcessor(Outgoing(), EnvironmentManager(), process_exec_manager=manager)
    asyncio.run(processor.process_spawn(request_id(), spawn_params(stream_stdin=True)))
    session = manager.session_for(7, "proc-1")

    asyncio.run(processor.connection_closed(7))

    assert manager.session_for(7, "proc-1") is None
    assert session is not None
    assert session.closed is True
    assert session.controls[-1].kind is ProcessControlKind.KILL


def test_output_capture_caps_and_stream_notifications_match_contract() -> None:
    capture, notifications = handle_process_output(
        "proc",
        ProcessOutputStream.STDOUT,
        [b"abc", b"def"],
        stream_output=False,
        output_bytes_cap=4,
    )

    assert capture.text == "abcd"
    assert capture.cap_reached is True
    assert notifications == []

    capture, notifications = handle_process_output(
        "proc",
        ProcessOutputStream.STDERR,
        [b"err"],
        stream_output=True,
        output_bytes_cap=None,
    )

    assert capture.text == ""
    assert capture.cap_reached is False
    assert notifications[0].process_handle == "proc"
    assert notifications[0].stream is ProcessOutputStream.STDERR
    assert notifications[0].delta_base64 == base64.b64encode(b"err").decode("ascii")
