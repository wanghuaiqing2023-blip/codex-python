"""Command execution manager projection ported from ``app-server/src/command_exec.rs``."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from pycodex.app_server.error_code import invalid_params, invalid_request
from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server_protocol import (
    CommandExecResizeParams,
    CommandExecResizeResponse,
    CommandExecTerminalSize,
    CommandExecTerminateParams,
    CommandExecTerminateResponse,
    CommandExecWriteParams,
    CommandExecWriteResponse,
    JSONRPCErrorError,
)

EXEC_TIMEOUT_EXIT_CODE = 124
OUTPUT_CHUNK_SIZE_HINT = 64 * 1024
DEFAULT_OUTPUT_BYTES_CAP = 200_000
WINDOWS_SANDBOX_UNSUPPORTED_CONTROL_MESSAGE = (
    "command/exec/write, command/exec/terminate, and command/exec/resize are not supported "
    "for windows sandbox processes"
)


class CommandExecError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class TerminalSize:
    rows: int
    cols: int


class InternalProcessIdKind(Enum):
    GENERATED = "Generated"
    CLIENT = "Client"


@dataclass(frozen=True)
class InternalProcessId:
    kind: InternalProcessIdKind
    value: int | str

    @classmethod
    def generated(cls, value: int) -> "InternalProcessId":
        return cls(InternalProcessIdKind.GENERATED, int(value))

    @classmethod
    def client(cls, value: str) -> "InternalProcessId":
        return cls(InternalProcessIdKind.CLIENT, str(value))

    def error_repr(self) -> str:
        if self.kind is InternalProcessIdKind.GENERATED:
            return str(self.value)
        return json.dumps(str(self.value))


@dataclass(frozen=True)
class ConnectionProcessId:
    connection_id: Any
    process_id: InternalProcessId


class CommandControlKind(Enum):
    WRITE = "Write"
    RESIZE = "Resize"
    TERMINATE = "Terminate"


@dataclass(frozen=True)
class CommandControl:
    kind: CommandControlKind
    delta: bytes = b""
    close_stdin: bool = False
    size: TerminalSize | None = None

    @classmethod
    def write(cls, delta: bytes, close_stdin: bool) -> "CommandControl":
        return cls(CommandControlKind.WRITE, bytes(delta), bool(close_stdin))

    @classmethod
    def resize(cls, size: TerminalSize) -> "CommandControl":
        return cls(CommandControlKind.RESIZE, size=size)

    @classmethod
    def terminate(cls) -> "CommandControl":
        return cls(CommandControlKind.TERMINATE)


class CommandExecSessionKind(Enum):
    ACTIVE = "Active"
    UNSUPPORTED_WINDOWS_SANDBOX = "UnsupportedWindowsSandbox"


@dataclass
class CommandExecSession:
    kind: CommandExecSessionKind
    stream_stdin: bool = False
    controls: list[CommandControl] = field(default_factory=list)
    closed: bool = False

    @classmethod
    def active(cls, *, stream_stdin: bool) -> "CommandExecSession":
        return cls(CommandExecSessionKind.ACTIVE, stream_stdin=stream_stdin)

    @classmethod
    def unsupported_windows_sandbox(cls) -> "CommandExecSession":
        return cls(CommandExecSessionKind.UNSUPPORTED_WINDOWS_SANDBOX)


@dataclass(frozen=True)
class StartCommandExecParams:
    request_id: ConnectionRequestId
    command: tuple[str, ...]
    process_id: str | None = None
    sandbox: Any = None
    tty: bool = False
    stream_stdin: bool = False
    stream_stdout_stderr: bool = False
    output_bytes_cap: int | None = None


@dataclass(frozen=True)
class StartCommandExecProjection:
    process_id: InternalProcessId
    notification_process_id: str | None
    stream_stdin: bool
    stream_stdout_stderr: bool
    windows_sandbox: bool


class CommandExecManager:
    """In-memory projection of Rust's command/exec control-plane manager."""

    def __init__(self) -> None:
        self.sessions: dict[ConnectionProcessId, CommandExecSession] = {}
        self.next_generated_process_id = 1

    async def start(self, params: StartCommandExecParams) -> StartCommandExecProjection:
        if params.process_id is None and (params.tty or params.stream_stdin or params.stream_stdout_stderr):
            raise CommandExecError(invalid_request("command/exec tty or streaming requires a client-supplied processId"))

        process_id = self._next_process_id(params.process_id)
        process_key = ConnectionProcessId(params.request_id.connection_id, process_id)
        windows_sandbox = is_windows_restricted_token_sandbox(params.sandbox)

        if windows_sandbox:
            if params.tty or params.stream_stdin or params.stream_stdout_stderr:
                raise CommandExecError(invalid_request("streaming command/exec is not supported with windows sandbox"))
            if params.output_bytes_cap != DEFAULT_OUTPUT_BYTES_CAP:
                raise CommandExecError(invalid_request("custom outputBytesCap is not supported with windows sandbox"))
            if process_id.kind is InternalProcessIdKind.CLIENT:
                self._insert_session(process_key, CommandExecSession.unsupported_windows_sandbox())
            return StartCommandExecProjection(
                process_id=process_id,
                notification_process_id=None if process_id.kind is InternalProcessIdKind.GENERATED else str(process_id.value),
                stream_stdin=False,
                stream_stdout_stderr=False,
                windows_sandbox=True,
            )

        if not params.command:
            raise CommandExecError(invalid_request("command must not be empty"))

        stream_stdin = params.tty or params.stream_stdin
        stream_stdout_stderr = params.tty or params.stream_stdout_stderr
        self._insert_session(process_key, CommandExecSession.active(stream_stdin=stream_stdin))
        return StartCommandExecProjection(
            process_id=process_id,
            notification_process_id=None if process_id.kind is InternalProcessIdKind.GENERATED else str(process_id.value),
            stream_stdin=stream_stdin,
            stream_stdout_stderr=stream_stdout_stderr,
            windows_sandbox=False,
        )

    async def write(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecWriteParams,
    ) -> CommandExecWriteResponse:
        if params.delta_base64 is None and not params.close_stdin:
            raise CommandExecError(invalid_params("command/exec/write requires deltaBase64 or closeStdin"))

        if params.delta_base64 is None:
            delta = b""
        else:
            try:
                delta = base64.b64decode(params.delta_base64, validate=True)
            except Exception as exc:  # binascii.Error is implementation-specific enough to keep broad.
                raise CommandExecError(invalid_params(f"invalid deltaBase64: {exc}")) from exc

        target = ConnectionProcessId(request_id.connection_id, InternalProcessId.client(params.process_id))
        self._send_control(target, CommandControl.write(delta, params.close_stdin))
        return CommandExecWriteResponse()

    async def terminate(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecTerminateParams,
    ) -> CommandExecTerminateResponse:
        target = ConnectionProcessId(request_id.connection_id, InternalProcessId.client(params.process_id))
        self._send_control(target, CommandControl.terminate())
        return CommandExecTerminateResponse()

    async def resize(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecResizeParams,
    ) -> CommandExecResizeResponse:
        target = ConnectionProcessId(request_id.connection_id, InternalProcessId.client(params.process_id))
        self._send_control(target, CommandControl.resize(terminal_size_from_protocol(params.size)))
        return CommandExecResizeResponse()

    async def connection_closed(self, connection_id: Any) -> None:
        process_ids = [process_id for process_id in self.sessions if process_id.connection_id == connection_id]
        for process_id in process_ids:
            session = self.sessions.pop(process_id)
            if session.kind is CommandExecSessionKind.ACTIVE:
                session.controls.append(CommandControl.terminate())
                session.closed = True

    def session_for(self, connection_id: Any, process_id: str) -> CommandExecSession | None:
        return self.sessions.get(ConnectionProcessId(connection_id, InternalProcessId.client(process_id)))

    def _next_process_id(self, process_id: str | None) -> InternalProcessId:
        if process_id is not None:
            return InternalProcessId.client(process_id)
        generated = self.next_generated_process_id
        self.next_generated_process_id += 1
        return InternalProcessId.generated(generated)

    def _insert_session(self, process_id: ConnectionProcessId, session: CommandExecSession) -> None:
        if process_id in self.sessions:
            raise CommandExecError(
                invalid_request(f"duplicate active command/exec process id: {process_id.process_id.error_repr()}")
            )
        self.sessions[process_id] = session

    def _send_control(self, process_id: ConnectionProcessId, control: CommandControl) -> None:
        session = self.sessions.get(process_id)
        if session is None or session.closed:
            raise CommandExecError(command_no_longer_running_error(process_id.process_id))
        if session.kind is CommandExecSessionKind.UNSUPPORTED_WINDOWS_SANDBOX:
            raise CommandExecError(invalid_request(WINDOWS_SANDBOX_UNSUPPORTED_CONTROL_MESSAGE))
        if control.kind is CommandControlKind.WRITE and not session.stream_stdin:
            raise CommandExecError(invalid_request("stdin streaming is not enabled for this command/exec"))
        session.controls.append(control)


def terminal_size_from_protocol(size: CommandExecTerminalSize) -> TerminalSize:
    if size.rows == 0 or size.cols == 0:
        raise CommandExecError(invalid_params("command/exec size rows and cols must be greater than 0"))
    return TerminalSize(rows=size.rows, cols=size.cols)


def command_no_longer_running_error(process_id: InternalProcessId) -> JSONRPCErrorError:
    return invalid_request(f"command/exec {process_id.error_repr()} is no longer running")


def is_windows_restricted_token_sandbox(sandbox: Any) -> bool:
    raw = getattr(sandbox, "value", sandbox)
    raw = getattr(raw, "type", raw)
    if isinstance(raw, Mapping):
        raw = raw.get("type") or raw.get("kind") or raw.get("sandbox")
    return str(raw).lower() in {
        "windowsrestrictedtoken",
        "windows_restricted_token",
        "windows-restricted-token",
        "windows",
    }


__all__ = [
    "DEFAULT_OUTPUT_BYTES_CAP",
    "EXEC_TIMEOUT_EXIT_CODE",
    "OUTPUT_CHUNK_SIZE_HINT",
    "WINDOWS_SANDBOX_UNSUPPORTED_CONTROL_MESSAGE",
    "CommandControl",
    "CommandControlKind",
    "CommandExecError",
    "CommandExecManager",
    "CommandExecSession",
    "CommandExecSessionKind",
    "ConnectionProcessId",
    "InternalProcessId",
    "InternalProcessIdKind",
    "StartCommandExecParams",
    "StartCommandExecProjection",
    "TerminalSize",
    "command_no_longer_running_error",
    "is_windows_restricted_token_sandbox",
    "terminal_size_from_protocol",
]
