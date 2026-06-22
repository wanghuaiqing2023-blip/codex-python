"""Process exec request processor projection.

Ported from ``codex-app-server/src/request_processors/process_exec_processor.rs``.
The Rust module owns app-server process/spawn request validation, process
handle session bookkeeping, and process control routing before delegating to
PTY/process runtime code. Python keeps the same boundary with injectable
spawn/session hooks instead of starting real OS processes.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.app_server.command_exec import DEFAULT_OUTPUT_BYTES_CAP, TerminalSize
from pycodex.app_server.error_code import internal_error, invalid_params, invalid_request
from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    ProcessKillParams,
    ProcessKillResponse,
    ProcessOutputDeltaNotification,
    ProcessOutputStream,
    ProcessResizePtyParams,
    ProcessResizePtyResponse,
    ProcessSpawnParams,
    ProcessSpawnResponse,
    ProcessTerminalSize,
    ProcessWriteStdinParams,
    ProcessWriteStdinResponse,
)

JsonValue = Any
EXEC_TIMEOUT_EXIT_CODE = 124
OUTPUT_CHUNK_SIZE_HINT = 64 * 1024


class ProcessExecRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class ExecExpirationProjection:
    kind: str
    timeout_ms: int | None = None


@dataclass(frozen=True)
class ConnectionProcessHandle:
    connection_id: Any
    process_handle: str


class ProcessControlKind(Enum):
    WRITE = "Write"
    RESIZE = "Resize"
    KILL = "Kill"


@dataclass(frozen=True)
class ProcessControl:
    kind: ProcessControlKind
    delta: bytes = b""
    close_stdin: bool = False
    size: TerminalSize | None = None

    @classmethod
    def write(cls, delta: bytes, close_stdin: bool) -> "ProcessControl":
        return cls(ProcessControlKind.WRITE, bytes(delta), bool(close_stdin))

    @classmethod
    def resize(cls, size: TerminalSize) -> "ProcessControl":
        return cls(ProcessControlKind.RESIZE, size=size)

    @classmethod
    def kill(cls) -> "ProcessControl":
        return cls(ProcessControlKind.KILL)


@dataclass
class ProcessSession:
    stream_stdin: bool = False
    controls: list[ProcessControl] = field(default_factory=list)
    closed: bool = False


@dataclass(frozen=True)
class StartProcessParams:
    outgoing: Any
    request_id: ConnectionRequestId
    process_handle: str
    command: tuple[str, ...]
    cwd: Any
    env: dict[str, str]
    expiration: ExecExpirationProjection
    tty: bool
    stream_stdin: bool
    stream_stdout_stderr: bool
    output_bytes_cap: int | None
    size: TerminalSize | None


@dataclass(frozen=True)
class StartProcessProjection:
    program: str
    args: tuple[str, ...]
    stream_stdin: bool
    stream_stdout_stderr: bool
    output_bytes_cap: int | None
    size: TerminalSize | None


@dataclass(frozen=True)
class ProcessOutputCapture:
    text: str
    cap_reached: bool


class ProcessExecRequestProcessor:
    def __init__(
        self,
        outgoing: Any,
        environment_manager: Any,
        *,
        process_exec_manager: "ProcessExecManager | None" = None,
    ) -> None:
        self.outgoing = outgoing
        self.environment_manager = environment_manager
        self.process_exec_manager = process_exec_manager or ProcessExecManager()

    @classmethod
    def new(cls, outgoing: Any, environment_manager: Any) -> "ProcessExecRequestProcessor":
        return cls(outgoing, environment_manager)

    async def process_spawn(
        self,
        request_id: ConnectionRequestId,
        params: ProcessSpawnParams | Mapping[str, JsonValue],
    ) -> None:
        self.require_local_environment()
        params = _params(ProcessSpawnParams, params)
        if not params.command:
            raise ProcessExecRequestProcessorError(invalid_request("command must not be empty"))
        if not params.process_handle:
            raise ProcessExecRequestProcessorError(invalid_request("processHandle must not be empty"))
        if params.size is not None and not params.tty:
            raise ProcessExecRequestProcessorError(invalid_params("process/spawn size requires tty: true"))

        env = dict(os.environ)
        if params.env is not None:
            for key, value in params.env.items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value

        expiration = _expiration(params.timeout_ms)
        output_bytes_cap = DEFAULT_OUTPUT_BYTES_CAP if params.output_bytes_cap is _protocol_unset() else params.output_bytes_cap
        size = None
        if params.size is not None:
            try:
                size = terminal_size_from_protocol(params.size)
            except ProcessExecRequestProcessorError:
                raise

        try:
            await self.process_exec_manager.start(
                StartProcessParams(
                    outgoing=self.outgoing,
                    request_id=request_id,
                    process_handle=params.process_handle,
                    command=params.command,
                    cwd=params.cwd,
                    env=env,
                    expiration=expiration,
                    tty=params.tty,
                    stream_stdin=params.stream_stdin,
                    stream_stdout_stderr=params.stream_stdout_stderr,
                    output_bytes_cap=output_bytes_cap,
                    size=size,
                )
            )
        except ProcessExecManagerError as exc:
            raise ProcessExecRequestProcessorError(exc.error) from exc
        return None

    async def process_write_stdin(
        self,
        request_id: ConnectionRequestId,
        params: ProcessWriteStdinParams | Mapping[str, JsonValue],
    ) -> ProcessWriteStdinResponse:
        try:
            return await self.process_exec_manager.write_stdin(request_id, _params(ProcessWriteStdinParams, params))
        except ProcessExecManagerError as exc:
            raise ProcessExecRequestProcessorError(exc.error) from exc

    async def process_resize_pty(
        self,
        request_id: ConnectionRequestId,
        params: ProcessResizePtyParams | Mapping[str, JsonValue],
    ) -> ProcessResizePtyResponse:
        try:
            return await self.process_exec_manager.resize_pty(request_id, _params(ProcessResizePtyParams, params))
        except ProcessExecManagerError as exc:
            raise ProcessExecRequestProcessorError(exc.error) from exc

    async def process_kill(
        self,
        request_id: ConnectionRequestId,
        params: ProcessKillParams | Mapping[str, JsonValue],
    ) -> ProcessKillResponse:
        try:
            return await self.process_exec_manager.kill(request_id, _params(ProcessKillParams, params))
        except ProcessExecManagerError as exc:
            raise ProcessExecRequestProcessorError(exc.error) from exc

    async def connection_closed(self, connection_id: Any) -> None:
        await self.process_exec_manager.connection_closed(connection_id)

    def require_local_environment(self) -> None:
        local = _optional_call(self.environment_manager, "try_local_environment")
        if local is None:
            raise ProcessExecRequestProcessorError(internal_error("local environment is not configured"))


class ProcessExecManagerError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


class ProcessExecManager:
    def __init__(self, *, spawn_hook: Any = None) -> None:
        self.sessions: dict[ConnectionProcessHandle, ProcessSession] = {}
        self.spawn_hook = spawn_hook
        self.started: list[StartProcessParams] = []

    async def start(self, params: StartProcessParams) -> StartProcessProjection:
        if not params.command:
            raise ProcessExecManagerError(invalid_request("command must not be empty"))
        program, *args = params.command
        process_key = ConnectionProcessHandle(params.request_id.connection_id, params.process_handle)
        if process_key in self.sessions:
            raise ProcessExecManagerError(
                invalid_request(f"duplicate active process handle: {params.process_handle!r}")
            )

        stream_stdin = params.tty or params.stream_stdin
        stream_stdout_stderr = params.tty or params.stream_stdout_stderr
        self.sessions[process_key] = ProcessSession(stream_stdin=stream_stdin)
        self.started.append(params)
        projection = StartProcessProjection(
            program=program,
            args=tuple(args),
            stream_stdin=stream_stdin,
            stream_stdout_stderr=stream_stdout_stderr,
            output_bytes_cap=params.output_bytes_cap,
            size=params.size,
        )
        try:
            if self.spawn_hook is not None:
                self.spawn_hook(params, projection)
        except Exception as exc:
            self.sessions.pop(process_key, None)
            raise ProcessExecManagerError(internal_error(f"failed to spawn process: {exc}")) from exc
        sender = getattr(params.outgoing, "send_response", None)
        if callable(sender):
            await sender(params.request_id, ProcessSpawnResponse())
        return projection

    async def write_stdin(
        self,
        request_id: ConnectionRequestId,
        params: ProcessWriteStdinParams,
    ) -> ProcessWriteStdinResponse:
        if params.delta_base64 is None and not params.close_stdin:
            raise ProcessExecManagerError(invalid_params("process/writeStdin requires deltaBase64 or closeStdin"))
        try:
            delta = b"" if params.delta_base64 is None else base64.b64decode(params.delta_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ProcessExecManagerError(invalid_params(f"invalid deltaBase64: {exc}")) from exc
        self._send_control(
            request_id.connection_id,
            params.process_handle,
            ProcessControl.write(delta, params.close_stdin),
        )
        return ProcessWriteStdinResponse()

    async def kill(self, request_id: ConnectionRequestId, params: ProcessKillParams) -> ProcessKillResponse:
        self._send_control(request_id.connection_id, params.process_handle, ProcessControl.kill())
        return ProcessKillResponse()

    async def resize_pty(
        self,
        request_id: ConnectionRequestId,
        params: ProcessResizePtyParams,
    ) -> ProcessResizePtyResponse:
        try:
            size = terminal_size_from_protocol(params.size)
        except ProcessExecRequestProcessorError as exc:
            raise ProcessExecManagerError(exc.error) from exc
        self._send_control(
            request_id.connection_id,
            params.process_handle,
            ProcessControl.resize(size),
        )
        return ProcessResizePtyResponse()

    async def connection_closed(self, connection_id: Any) -> None:
        process_handles = [key for key in self.sessions if key.connection_id == connection_id]
        for process_handle in process_handles:
            session = self.sessions.pop(process_handle)
            session.controls.append(ProcessControl.kill())
            session.closed = True

    def session_for(self, connection_id: Any, process_handle: str) -> ProcessSession | None:
        return self.sessions.get(ConnectionProcessHandle(connection_id, process_handle))

    def _send_control(self, connection_id: Any, process_handle: str, control: ProcessControl) -> None:
        key = ConnectionProcessHandle(connection_id, process_handle)
        session = self.sessions.get(key)
        if session is None or session.closed:
            raise ProcessExecManagerError(no_active_process_error(process_handle))
        if control.kind is ProcessControlKind.WRITE and not session.stream_stdin:
            raise ProcessExecManagerError(invalid_request("stdin streaming is not enabled for this process"))
        session.controls.append(control)


def terminal_size_from_protocol(size: ProcessTerminalSize) -> TerminalSize:
    if size.rows == 0 or size.cols == 0:
        raise ProcessExecRequestProcessorError(invalid_params("process size rows and cols must be greater than 0"))
    return TerminalSize(rows=size.rows, cols=size.cols)


def no_active_process_error(process_handle: str) -> JSONRPCErrorError:
    return invalid_request(f"no active process for process handle {process_handle!r}")


def process_no_longer_running_error(process_handle: str) -> JSONRPCErrorError:
    return invalid_request(f"process {process_handle!r} is no longer running")


def handle_process_output(
    process_handle: str,
    stream: ProcessOutputStream,
    chunks: list[bytes],
    *,
    stream_output: bool,
    output_bytes_cap: int | None,
) -> tuple[ProcessOutputCapture, list[ProcessOutputDeltaNotification]]:
    buffer = bytearray()
    observed_num_bytes = 0
    cap_reached = False
    notifications: list[ProcessOutputDeltaNotification] = []
    for chunk in chunks:
        capped_chunk = chunk
        if output_bytes_cap is not None:
            capped_chunk_len = max(output_bytes_cap - observed_num_bytes, 0)
            capped_chunk = chunk[:capped_chunk_len]
            observed_num_bytes += len(capped_chunk)
            cap_reached = observed_num_bytes == output_bytes_cap
        if stream_output:
            notifications.append(
                ProcessOutputDeltaNotification(
                    process_handle=process_handle,
                    stream=stream,
                    delta_base64=base64.b64encode(capped_chunk).decode("ascii"),
                    cap_reached=cap_reached,
                )
            )
        else:
            buffer.extend(capped_chunk)
        if cap_reached:
            break
    return ProcessOutputCapture(text=bytes(buffer).decode("utf-8", errors="replace"), cap_reached=cap_reached), notifications


def _expiration(timeout_ms: int | None | object) -> ExecExpirationProjection:
    if timeout_ms is _protocol_unset():
        return ExecExpirationProjection("DefaultTimeout")
    if timeout_ms is None:
        return ExecExpirationProjection("Cancellation")
    if timeout_ms < 0:
        raise ProcessExecRequestProcessorError(
            invalid_params(f"process/spawn timeoutMs must be non-negative, got {timeout_ms}")
        )
    return ExecExpirationProjection("Timeout", int(timeout_ms))


def _protocol_unset() -> object:
    from pycodex.app_server_protocol import UNSET

    return UNSET


def _params(cls: type, value: Any) -> Any:
    if isinstance(value, cls):
        return value
    if isinstance(value, Mapping):
        return cls.from_mapping(value)
    return value


def _optional_call(obj: Any, name: str, *args: Any) -> Any:
    method = getattr(obj, name, None)
    if not callable(method):
        return None
    return method(*args)


__all__ = [
    "EXEC_TIMEOUT_EXIT_CODE",
    "OUTPUT_CHUNK_SIZE_HINT",
    "ConnectionProcessHandle",
    "ExecExpirationProjection",
    "ProcessControl",
    "ProcessControlKind",
    "ProcessExecManager",
    "ProcessExecManagerError",
    "ProcessExecRequestProcessor",
    "ProcessExecRequestProcessorError",
    "ProcessOutputCapture",
    "ProcessSession",
    "StartProcessParams",
    "StartProcessProjection",
    "handle_process_output",
    "no_active_process_error",
    "process_no_longer_running_error",
    "terminal_size_from_protocol",
]
