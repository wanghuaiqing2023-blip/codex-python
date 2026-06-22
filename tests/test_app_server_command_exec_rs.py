"""Parity tests for Rust ``app-server/src/command_exec.rs`` control-plane behavior."""

from __future__ import annotations

import asyncio
import base64

import pytest

from pycodex.app_server.command_exec import (
    DEFAULT_OUTPUT_BYTES_CAP,
    WINDOWS_SANDBOX_UNSUPPORTED_CONTROL_MESSAGE,
    CommandControlKind,
    CommandExecError,
    CommandExecManager,
    CommandExecSession,
    CommandExecSessionKind,
    ConnectionProcessId,
    InternalProcessId,
    StartCommandExecParams,
    command_no_longer_running_error,
    terminal_size_from_protocol,
)
from pycodex.app_server.error_code import INVALID_PARAMS_ERROR_CODE, INVALID_REQUEST_ERROR_CODE
from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server_protocol import (
    CommandExecResizeParams,
    CommandExecTerminalSize,
    CommandExecTerminateParams,
    CommandExecWriteParams,
)


def _request(connection_id: int = 7, request_id: int = 99) -> ConnectionRequestId:
    return ConnectionRequestId(connection_id=connection_id, request_id=request_id)


def _assert_error(excinfo: pytest.ExceptionInfo[CommandExecError], code: int, message: str) -> None:
    assert excinfo.value.error.code == code
    assert excinfo.value.error.message == message


def test_streaming_exec_requires_client_process_id() -> None:
    # Rust module: CommandExecManager::start rejects tty/stdin/stdout streaming
    # without a client processId before spawning any process.
    manager = CommandExecManager()

    with pytest.raises(CommandExecError) as excinfo:
        asyncio.run(
            manager.start(
                StartCommandExecParams(
                    request_id=_request(),
                    command=("echo", "hi"),
                    process_id=None,
                    tty=True,
                )
            )
        )

    _assert_error(
        excinfo,
        INVALID_REQUEST_ERROR_CODE,
        "command/exec tty or streaming requires a client-supplied processId",
    )


def test_windows_sandbox_streaming_exec_is_rejected() -> None:
    # Rust test: windows_sandbox_streaming_exec_is_rejected.
    manager = CommandExecManager()

    with pytest.raises(CommandExecError) as excinfo:
        asyncio.run(
            manager.start(
                StartCommandExecParams(
                    request_id=_request(),
                    command=("cmd",),
                    process_id="proc-42",
                    sandbox="WindowsRestrictedToken",
                    stream_stdout_stderr=True,
                )
            )
        )

    _assert_error(
        excinfo,
        INVALID_REQUEST_ERROR_CODE,
        "streaming command/exec is not supported with windows sandbox",
    )


def test_windows_sandbox_custom_output_cap_is_rejected() -> None:
    # Rust module: Windows sandbox only accepts the default output cap.
    manager = CommandExecManager()

    with pytest.raises(CommandExecError) as excinfo:
        asyncio.run(
            manager.start(
                StartCommandExecParams(
                    request_id=_request(),
                    command=("cmd",),
                    process_id="proc-42",
                    sandbox={"type": "WindowsRestrictedToken"},
                    output_bytes_cap=DEFAULT_OUTPUT_BYTES_CAP + 1,
                )
            )
        )

    _assert_error(
        excinfo,
        INVALID_REQUEST_ERROR_CODE,
        "custom outputBytesCap is not supported with windows sandbox",
    )


def test_windows_sandbox_process_ids_reject_write_and_terminate_requests() -> None:
    # Rust tests: windows_sandbox_process_ids_reject_write_requests and
    # windows_sandbox_process_ids_reject_terminate_requests.
    manager = CommandExecManager()
    request_id = _request(11, 1)
    process_id = ConnectionProcessId(request_id.connection_id, InternalProcessId.client("proc-11"))
    manager.sessions[process_id] = CommandExecSession.unsupported_windows_sandbox()

    with pytest.raises(CommandExecError) as excinfo:
        asyncio.run(
            manager.write(
                request_id,
                CommandExecWriteParams(
                    process_id="proc-11",
                    delta_base64=base64.b64encode(b"hello").decode("ascii"),
                ),
            )
        )
    _assert_error(excinfo, INVALID_REQUEST_ERROR_CODE, WINDOWS_SANDBOX_UNSUPPORTED_CONTROL_MESSAGE)

    with pytest.raises(CommandExecError) as excinfo:
        asyncio.run(manager.terminate(request_id, CommandExecTerminateParams(process_id="proc-11")))
    _assert_error(excinfo, INVALID_REQUEST_ERROR_CODE, WINDOWS_SANDBOX_UNSUPPORTED_CONTROL_MESSAGE)


def test_write_requires_delta_or_close_stdin() -> None:
    # Rust module: CommandExecManager::write validates an actionable write
    # request before looking up a session.
    manager = CommandExecManager()

    with pytest.raises(CommandExecError) as excinfo:
        asyncio.run(manager.write(_request(), CommandExecWriteParams(process_id="proc-1")))

    _assert_error(
        excinfo,
        INVALID_PARAMS_ERROR_CODE,
        "command/exec/write requires deltaBase64 or closeStdin",
    )


def test_write_decodes_base64_and_records_control_for_active_stream() -> None:
    # Rust module: decoded write controls are sent to the active process control channel.
    manager = CommandExecManager()
    request_id = _request(13, 3)
    asyncio.run(
        manager.start(
            StartCommandExecParams(
                request_id=request_id,
                command=("cat",),
                process_id="proc-13",
                stream_stdin=True,
            )
        )
    )

    response = asyncio.run(
        manager.write(
            request_id,
            CommandExecWriteParams(
                process_id="proc-13",
                delta_base64=base64.b64encode(b"hello").decode("ascii"),
                close_stdin=True,
            ),
        )
    )

    assert response.to_mapping() == {}
    session = manager.session_for(13, "proc-13")
    assert session is not None
    assert session.controls[-1].kind is CommandControlKind.WRITE
    assert session.controls[-1].delta == b"hello"
    assert session.controls[-1].close_stdin is True


def test_write_rejects_when_stdin_streaming_not_enabled() -> None:
    # Rust helper: handle_process_write rejects write controls if stdin
    # streaming was not enabled for the command.
    manager = CommandExecManager()
    request_id = _request(14, 4)
    asyncio.run(
        manager.start(
            StartCommandExecParams(
                request_id=request_id,
                command=("true",),
                process_id="proc-14",
            )
        )
    )

    with pytest.raises(CommandExecError) as excinfo:
        asyncio.run(
            manager.write(
                request_id,
                CommandExecWriteParams(
                    process_id="proc-14",
                    delta_base64=base64.b64encode(b"hello").decode("ascii"),
                ),
            )
        )

    _assert_error(excinfo, INVALID_REQUEST_ERROR_CODE, "stdin streaming is not enabled for this command/exec")


def test_resize_validates_terminal_size() -> None:
    # Rust helper: terminal_size_from_protocol.
    assert terminal_size_from_protocol(CommandExecTerminalSize(rows=24, cols=80)).rows == 24

    with pytest.raises(CommandExecError) as excinfo:
        terminal_size_from_protocol(CommandExecTerminalSize(rows=0, cols=80))
    _assert_error(
        excinfo,
        INVALID_PARAMS_ERROR_CODE,
        "command/exec size rows and cols must be greater than 0",
    )


def test_resize_records_control_for_active_session() -> None:
    # Rust module: CommandExecManager::resize sends a Resize control after size validation.
    manager = CommandExecManager()
    request_id = _request(15, 5)
    asyncio.run(
        manager.start(
            StartCommandExecParams(
                request_id=request_id,
                command=("sh",),
                process_id="proc-15",
                tty=True,
            )
        )
    )

    response = asyncio.run(
        manager.resize(
            request_id,
            CommandExecResizeParams(process_id="proc-15", size=CommandExecTerminalSize(rows=40, cols=120)),
        )
    )

    assert response.to_mapping() == {}
    session = manager.session_for(15, "proc-15")
    assert session is not None
    assert session.controls[-1].kind is CommandControlKind.RESIZE
    assert session.controls[-1].size.rows == 40
    assert session.controls[-1].size.cols == 120


def test_duplicate_active_process_id_is_rejected_with_json_string_repr() -> None:
    # Rust module: duplicate active command/exec process id uses JSON string
    # rendering for client-provided ids.
    manager = CommandExecManager()
    request_id = _request(16, 6)
    params = StartCommandExecParams(request_id=request_id, command=("true",), process_id="proc-16")
    asyncio.run(manager.start(params))

    with pytest.raises(CommandExecError) as excinfo:
        asyncio.run(manager.start(params))

    _assert_error(
        excinfo,
        INVALID_REQUEST_ERROR_CODE,
        'duplicate active command/exec process id: "proc-16"',
    )


def test_connection_closed_removes_sessions_and_marks_active_controls_terminated() -> None:
    # Rust module: connection_closed removes only sessions for that connection
    # and sends Terminate controls to active sessions.
    manager = CommandExecManager()
    asyncio.run(manager.start(StartCommandExecParams(_request(17, 7), ("sleep", "1"), process_id="proc-17")))
    asyncio.run(manager.start(StartCommandExecParams(_request(18, 8), ("sleep", "1"), process_id="proc-18")))
    removed_session = manager.session_for(17, "proc-17")

    asyncio.run(manager.connection_closed(17))

    assert removed_session is not None
    assert removed_session.closed is True
    assert removed_session.controls[-1].kind is CommandControlKind.TERMINATE
    assert manager.session_for(17, "proc-17") is None
    assert manager.session_for(18, "proc-18") is not None


def test_command_no_longer_running_error_uses_process_error_repr() -> None:
    # Rust test: dropped_control_request_is_reported_as_not_running anchors the
    # same helper text.
    err = command_no_longer_running_error(InternalProcessId.client("proc-13"))

    assert err.code == INVALID_REQUEST_ERROR_CODE
    assert err.message == 'command/exec "proc-13" is no longer running'


def test_generated_process_ids_are_unquoted_and_increment() -> None:
    # Rust module: generated ids use the AtomicI64 sequence and numeric error repr.
    manager = CommandExecManager()

    first = asyncio.run(manager.start(StartCommandExecParams(_request(19, 9), ("true",))))
    second = asyncio.run(manager.start(StartCommandExecParams(_request(19, 10), ("true",))))

    assert first.process_id == InternalProcessId.generated(1)
    assert second.process_id == InternalProcessId.generated(2)
    assert first.process_id.error_repr() == "1"
    assert first.notification_process_id is None
    assert manager.sessions[ConnectionProcessId(19, InternalProcessId.generated(1))].kind is CommandExecSessionKind.ACTIVE
