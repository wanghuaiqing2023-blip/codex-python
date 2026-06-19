"""Python interface for Rust ``codex-shell-escalation``."""

from __future__ import annotations

import asyncio
import json
import os
import socket as _socket
import struct
import sys
from array import array
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Any, Mapping


ESCALATE_SOCKET_ENV_VAR = "CODEX_ESCALATE_SOCKET"
EXEC_WRAPPER_ENV_VAR = "EXEC_WRAPPER"
MAX_FDS_PER_MESSAGE = 16
LENGTH_PREFIX_SIZE = 4
MAX_DATAGRAM_SIZE = 8192


class EscalationExecution(str, Enum):
    UNSANDBOXED = "unsandboxed"
    TURN_DEFAULT = "turn_default"
    PERMISSIONS = "permissions"


@dataclass(frozen=True)
class EscalationDecision:
    kind: str
    execution: EscalationExecution | Any | None = None
    reason: str | None = None

    @classmethod
    def run(cls) -> "EscalationDecision":
        return cls("run")

    @classmethod
    def escalate(cls, execution: EscalationExecution | Any) -> "EscalationDecision":
        return cls("escalate", execution=execution)

    @classmethod
    def deny(cls, reason: str | None = None) -> "EscalationDecision":
        return cls("deny", reason=reason)


@dataclass(frozen=True)
class EscalateAction:
    type: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.type not in {"run", "escalate", "deny"}:
            raise ValueError(f"unknown escalate action type: {self.type}")
        if self.type == "deny":
            if self.reason is not None and not isinstance(self.reason, str):
                raise TypeError("reason must be a string or None")
        elif self.reason is not None:
            raise ValueError(f"{self.type} action must not include reason")

    @classmethod
    def run(cls) -> "EscalateAction":
        return cls("run")

    @classmethod
    def escalate(cls) -> "EscalateAction":
        return cls("escalate")

    @classmethod
    def deny(cls, reason: str | None = None) -> "EscalateAction":
        return cls("deny", reason)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EscalateAction":
        if not isinstance(value, Mapping):
            raise TypeError("escalate action must be a mapping")
        action_type = value.get("type")
        if action_type == "run":
            return cls.run()
        if action_type == "escalate":
            return cls.escalate()
        if action_type == "deny":
            return cls.deny(value.get("reason"))
        raise ValueError(f"unknown escalate action type: {action_type!r}")

    def to_mapping(self) -> dict[str, str | None]:
        if self.type == "deny":
            return {"type": "deny", "reason": self.reason}
        return {"type": self.type}


@dataclass(frozen=True)
class EscalationPermissions:
    value: Any


@dataclass(frozen=True)
class ResolvedPermissionProfile:
    value: Any


@dataclass(frozen=True)
class ExecParams:
    command: str
    workdir: str
    timeout_ms: int | None = None
    login: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, str):
            raise TypeError("command must be a string")
        if not isinstance(self.workdir, str):
            object.__setattr__(self, "workdir", str(self.workdir))
        if self.timeout_ms is not None:
            if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
                raise TypeError("timeout_ms must be an integer or None")
            if self.timeout_ms < 0:
                raise ValueError("timeout_ms must be non-negative")
        if self.login is not None and not isinstance(self.login, bool):
            raise TypeError("login must be a bool or None")


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    duration: float = 0.0
    timed_out: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError("exit_code must be an integer")
        for name in ("stdout", "stderr", "output"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string")
        if not isinstance(self.duration, (int, float)):
            raise TypeError("duration must be numeric seconds")
        if not isinstance(self.timed_out, bool):
            raise TypeError("timed_out must be a bool")


@dataclass(frozen=True)
class PreparedExec:
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    arg0: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, tuple):
            object.__setattr__(self, "command", tuple(self.command))
        for arg in self.command:
            if not isinstance(arg, str):
                raise TypeError("prepared command entries must be strings")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.env, dict):
            object.__setattr__(self, "env", dict(self.env))
        for key, value in self.env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("prepared env must map strings to strings")
        if self.arg0 is not None and not isinstance(self.arg0, str):
            raise TypeError("arg0 must be a string or None")


@dataclass(frozen=True)
class ExecveWrapperCli:
    file: str
    argv: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.file, str):
            raise TypeError("file must be a string")
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, "argv", tuple(self.argv))
        for arg in self.argv:
            if not isinstance(arg, str):
                raise TypeError("argv entries must be strings")

    @classmethod
    def parse(cls, argv: list[str] | tuple[str, ...] | None = None) -> "ExecveWrapperCli":
        args = tuple(sys.argv[1:] if argv is None else argv)
        if not args:
            raise ValueError("missing required executable path")
        return cls(args[0], args[1:])


@dataclass(frozen=True)
class EscalateRequest:
    file: Path
    argv: tuple[str, ...]
    workdir: Path
    env: dict[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.file, Path):
            object.__setattr__(self, "file", Path(self.file))
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, "argv", tuple(self.argv))
        for arg in self.argv:
            if not isinstance(arg, str):
                raise TypeError("escalate request argv entries must be strings")
        if not isinstance(self.workdir, Path):
            object.__setattr__(self, "workdir", Path(self.workdir))
        if not isinstance(self.env, dict):
            object.__setattr__(self, "env", dict(self.env))
        for key, value in self.env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("escalate request env must map strings to strings")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EscalateRequest":
        if not isinstance(value, Mapping):
            raise TypeError("escalate request must be a mapping")
        return cls(
            value.get("file"),  # type: ignore[arg-type]
            tuple(value.get("argv", ())),
            value.get("workdir"),  # type: ignore[arg-type]
            dict(value.get("env", {})),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "file": self.file.as_posix(),
            "argv": list(self.argv),
            "workdir": self.workdir.as_posix(),
            "env": dict(self.env),
        }


@dataclass(frozen=True)
class EscalateResponse:
    action: EscalateAction

    def __post_init__(self) -> None:
        if not isinstance(self.action, EscalateAction):
            object.__setattr__(self, "action", EscalateAction.from_mapping(self.action))  # type: ignore[arg-type]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EscalateResponse":
        if not isinstance(value, Mapping):
            raise TypeError("escalate response must be a mapping")
        return cls(EscalateAction.from_mapping(value.get("action")))  # type: ignore[arg-type]

    def to_mapping(self) -> dict[str, Any]:
        return {"action": self.action.to_mapping()}


@dataclass(frozen=True)
class SuperExecMessage:
    fds: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.fds, tuple):
            object.__setattr__(self, "fds", tuple(self.fds))
        for fd in self.fds:
            if isinstance(fd, bool) or not isinstance(fd, int):
                raise TypeError("fds must contain integer file descriptors")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SuperExecMessage":
        if not isinstance(value, Mapping):
            raise TypeError("super exec message must be a mapping")
        return cls(tuple(value.get("fds", ())))

    def to_mapping(self) -> dict[str, Any]:
        return {"fds": list(self.fds)}


@dataclass(frozen=True)
class SuperExecResult:
    exit_code: int

    def __post_init__(self) -> None:
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError("exit_code must be an integer")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SuperExecResult":
        if not isinstance(value, Mapping):
            raise TypeError("super exec result must be a mapping")
        return cls(value.get("exit_code"))  # type: ignore[arg-type]

    def to_mapping(self) -> dict[str, int]:
        return {"exit_code": self.exit_code}


def encode_length(length: int) -> bytes:
    if isinstance(length, bool) or not isinstance(length, int):
        raise TypeError("message length must be an integer")
    if length < 0 or length > 0xFFFF_FFFF:
        raise ValueError(f"message too large: {length}")
    return struct.pack("<I", length)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _json_payload(message: Any) -> bytes:
    return json.dumps(message, default=_json_default, separators=(",", ":")).encode("utf-8")


def _loads_json(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8"))


def _fd_ancillary(fds: tuple[int, ...]) -> list[tuple[int, int, bytes]]:
    if len(fds) > MAX_FDS_PER_MESSAGE:
        raise ValueError(f"too many fds: {len(fds)}")
    if not fds:
        return []
    if not hasattr(_socket, "SCM_RIGHTS"):
        raise OSError("SCM_RIGHTS file descriptor passing is not supported on this platform")
    packed = array("i", fds)
    return [(_socket.SOL_SOCKET, _socket.SCM_RIGHTS, packed.tobytes())]


def _extract_ancillary_fds(ancillary: list[tuple[int, int, bytes]]) -> tuple[int, ...]:
    if not hasattr(_socket, "SCM_RIGHTS"):
        return ()
    fds: list[int] = []
    for level, ty, data in ancillary:
        if level == _socket.SOL_SOCKET and ty == _socket.SCM_RIGHTS:
            arr = array("i")
            usable = len(data) - (len(data) % arr.itemsize)
            arr.frombytes(data[:usable])
            fds.extend(int(fd) for fd in arr)
    return tuple(fds)


def _control_size() -> int:
    if not hasattr(_socket, "CMSG_SPACE"):
        return 0
    return _socket.CMSG_SPACE(MAX_FDS_PER_MESSAGE * array("i").itemsize)


def _coerce_fd_tuple(fds: tuple[int, ...] | list[int] | None) -> tuple[int, ...]:
    if fds is None:
        return ()
    result = tuple(fds)
    for fd in result:
        if isinstance(fd, bool) or not isinstance(fd, int):
            raise TypeError("fds must contain integer file descriptors")
    return result


async def _to_thread(func: Any, *args: Any) -> Any:
    return await asyncio.to_thread(func, *args)


class AsyncSocket:
    def __init__(self, sock: _socket.socket) -> None:
        self.socket = sock

    @classmethod
    def from_fd(cls, fd: int) -> "AsyncSocket":
        if isinstance(fd, bool) or not isinstance(fd, int):
            raise TypeError("fd must be an integer")
        return cls(_socket.socket(fileno=fd))

    @classmethod
    def pair(cls) -> tuple["AsyncSocket", "AsyncSocket"]:
        if not hasattr(_socket, "socketpair") or not hasattr(_socket, "AF_UNIX"):
            raise OSError("socketpair is not supported on this platform")
        left, right = _socket.socketpair(_socket.AF_UNIX, _socket.SOCK_STREAM)
        return cls(left), cls(right)

    async def send_with_fds(self, message: Any, fds: tuple[int, ...] | list[int] | None = None) -> None:
        fd_tuple = _coerce_fd_tuple(fds)
        payload = _json_payload(message)
        frame = encode_length(len(payload)) + payload
        if fd_tuple:
            ancillary = _fd_ancillary(fd_tuple)
            await _to_thread(self.socket.sendmsg, [frame], ancillary)
        else:
            await _to_thread(self.socket.sendall, frame)

    async def receive_with_fds(self, cls: Any | None = None) -> tuple[Any, tuple[int, ...]]:
        header, fds = await self._recv_exact_with_fds(LENGTH_PREFIX_SIZE)
        if len(header) != LENGTH_PREFIX_SIZE:
            raise EOFError("socket closed while receiving frame header")
        payload_len = struct.unpack("<I", header)[0]
        payload = await self._recv_exact(payload_len)
        if len(payload) != payload_len:
            raise EOFError("socket closed while receiving frame payload")
        decoded = _loads_json(payload)
        if cls is not None and hasattr(cls, "from_mapping"):
            decoded = cls.from_mapping(decoded)
        return decoded, fds

    async def send(self, message: Any) -> None:
        await self.send_with_fds(message, ())

    async def receive(self, cls: Any | None = None) -> Any:
        message, _fds = await self.receive_with_fds(cls)
        return message

    def into_inner(self) -> _socket.socket:
        sock = self.socket
        self.socket = None  # type: ignore[assignment]
        return sock

    async def _recv_exact(self, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining:
            chunk = await _to_thread(self.socket.recv, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    async def _recv_exact_with_fds(self, count: int) -> tuple[bytes, tuple[int, ...]]:
        if hasattr(self.socket, "recvmsg"):
            chunk, ancillary, _flags, _addr = await _to_thread(self.socket.recvmsg, count, _control_size())
            data = bytearray(chunk)
            fds = _extract_ancillary_fds(list(ancillary))
        else:
            data = bytearray(await _to_thread(self.socket.recv, count))
            fds = ()
        while len(data) < count:
            chunk = await _to_thread(self.socket.recv, count - len(data))
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data), fds


class AsyncDatagramSocket:
    def __init__(self, sock: _socket.socket) -> None:
        self.socket = sock

    @classmethod
    def from_raw_fd(cls, fd: int) -> "AsyncDatagramSocket":
        if isinstance(fd, bool) or not isinstance(fd, int):
            raise TypeError("fd must be an integer")
        return cls(_socket.socket(fileno=fd))

    @classmethod
    def pair(cls) -> tuple["AsyncDatagramSocket", "AsyncDatagramSocket"]:
        if not hasattr(_socket, "socketpair") or not hasattr(_socket, "AF_UNIX"):
            raise OSError("socketpair is not supported on this platform")
        left, right = _socket.socketpair(_socket.AF_UNIX, _socket.SOCK_DGRAM)
        return cls(left), cls(right)

    async def send_with_fds(self, data: bytes, fds: tuple[int, ...] | list[int] | None = None) -> None:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("datagram data must be bytes-like")
        fd_tuple = _coerce_fd_tuple(fds)
        ancillary = _fd_ancillary(fd_tuple)
        payload = bytes(data)
        if ancillary:
            written = await _to_thread(self.socket.sendmsg, [payload], ancillary)
        else:
            written = await _to_thread(self.socket.send, payload)
        if written != len(payload):
            raise OSError(f"short datagram write: wrote {written} bytes out of {len(payload)}")

    async def receive_with_fds(self) -> tuple[bytes, tuple[int, ...]]:
        if hasattr(self.socket, "recvmsg"):
            data, ancillary, _flags, _addr = await _to_thread(
                self.socket.recvmsg, MAX_DATAGRAM_SIZE, _control_size()
            )
            return data, _extract_ancillary_fds(list(ancillary))
        return await _to_thread(self.socket.recv, MAX_DATAGRAM_SIZE), ()

    def into_inner(self) -> _socket.socket:
        sock = self.socket
        self.socket = None  # type: ignore[assignment]
        return sock


def get_escalate_client(env: Mapping[str, str] | None = None) -> AsyncDatagramSocket:
    source = os.environ if env is None else env
    raw_fd = source[ESCALATE_SOCKET_ENV_VAR]
    fd = int(raw_fd)
    if fd < 0:
        raise ValueError(f"{ESCALATE_SOCKET_ENV_VAR} is not a valid file descriptor: {fd}")
    return AsyncDatagramSocket.from_raw_fd(fd)


def duplicate_fd_for_transfer(fd: int, name: str = "fd") -> int:
    if isinstance(fd, bool) or not isinstance(fd, int):
        raise TypeError(f"{name} must be an integer file descriptor")
    try:
        return os.dup(fd)
    except OSError as exc:
        raise OSError(f"failed to duplicate {name} for escalation transfer") from exc


def shell_escalation_request_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    result: dict[str, str] = {}
    for key, value in source.items():
        if key in {ESCALATE_SOCKET_ENV_VAR, EXEC_WRAPPER_ENV_VAR}:
            continue
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("environment must map strings to strings")
        result[key] = value
    return result


async def run_shell_escalation_execve_wrapper(
    file: str,
    argv: list[str] | tuple[str, ...],
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | str | None = None,
) -> int:
    handshake_client = get_escalate_client(env)
    server, client = AsyncSocket.pair()
    server_socket = server.into_inner()
    try:
        await handshake_client.send_with_fds(b"\x00", [server_socket.fileno()])
    finally:
        server_socket.close()

    request = EscalateRequest(
        file=Path(file),
        argv=tuple(argv),
        workdir=Path.cwd() if cwd is None else Path(cwd),
        env=shell_escalation_request_env(env),
    )
    await client.send(request)
    response = await client.receive(EscalateResponse)

    if response.action.type == "escalate":
        destination_fds = (0, 1, 2)
        fds_to_send = tuple(duplicate_fd_for_transfer(fd, name) for fd, name in zip(destination_fds, ("stdin", "stdout", "stderr")))
        try:
            await client.send_with_fds(SuperExecMessage(destination_fds), fds_to_send)
        finally:
            for fd in fds_to_send:
                try:
                    os.close(fd)
                except OSError:
                    pass
        result = await client.receive(SuperExecResult)
        return result.exit_code

    if response.action.type == "run":
        os.execv(file, list(argv))
        raise OSError("execv unexpectedly returned")

    if response.action.type == "deny":
        if response.action.reason is None:
            print("Execution denied", file=sys.stderr)
        else:
            print(f"Execution denied: {response.action.reason}", file=sys.stderr)
        return 1

    raise ValueError(f"unknown escalate action type: {response.action.type}")


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def cancelled(self) -> None:
        await self._event.wait()


class Stopwatch:
    def __init__(self, limit: float | None = None) -> None:
        self.limit = limit
        self._elapsed = 0.0
        self._running_since: float | None = monotonic()
        self._active_pauses = 0
        self._condition = asyncio.Condition()

    @classmethod
    def new(cls, limit: float) -> "Stopwatch":
        return cls(limit)

    @classmethod
    def unlimited(cls) -> "Stopwatch":
        return cls(None)

    def elapsed(self) -> float:
        current = self._elapsed
        if self._running_since is not None:
            current += monotonic() - self._running_since
        return current

    def cancellation_token(self) -> CancellationToken:
        token = CancellationToken()
        if self.limit is None:
            return token
        asyncio.create_task(self._cancel_after_limit(token))
        return token

    async def pause_for(self, awaitable: Any) -> Any:
        await self._pause()
        try:
            return await awaitable
        finally:
            await self._resume()

    async def _cancel_after_limit(self, token: CancellationToken) -> None:
        assert self.limit is not None
        while not token.is_cancelled():
            async with self._condition:
                elapsed = self.elapsed()
                if elapsed >= self.limit:
                    break
                running = self._running_since is not None
                remaining = self.limit - elapsed
                if not running:
                    await self._condition.wait()
                    continue
            try:
                await asyncio.wait_for(self._wait_for_change(), timeout=remaining)
            except TimeoutError:
                break
        token.cancel()

    async def _wait_for_change(self) -> None:
        async with self._condition:
            await self._condition.wait()

    async def _pause(self) -> None:
        async with self._condition:
            self._active_pauses += 1
            if self._active_pauses == 1 and self._running_since is not None:
                self._elapsed += monotonic() - self._running_since
                self._running_since = None
                self._condition.notify_all()

    async def _resume(self) -> None:
        async with self._condition:
            if self._active_pauses == 0:
                return
            self._active_pauses -= 1
            if self._active_pauses == 0 and self._running_since is None:
                self._running_since = monotonic()
                self._condition.notify_all()


class EscalationPolicy:
    async def determine_action(self, file: Path, argv: list[str], workdir: Path) -> EscalationDecision:
        raise NotImplementedError("codex-shell-escalation policy decision is not implemented")


class ShellCommandExecutor:
    async def run(
        self,
        command: list[str],
        cwd: Path,
        env_overlay: dict[str, str],
        cancel_rx: CancellationToken,
        after_spawn: Any | None = None,
    ) -> ExecResult:
        raise NotImplementedError("codex-shell-escalation command execution is not ported")

    async def prepare_escalated_exec(
        self,
        program: Path,
        argv: list[str],
        workdir: Path,
        env: dict[str, str],
        execution: EscalationExecution | Any,
    ) -> PreparedExec:
        raise NotImplementedError("codex-shell-escalation escalated exec preparation is not ported")


class EscalationSession:
    def __init__(
        self,
        env: dict[str, str],
        task: asyncio.Task[Any],
        client_socket: _socket.socket,
        cancellation_token: CancellationToken,
    ) -> None:
        self._env = env
        self.task = task
        self.client_socket = client_socket
        self.cancellation_token = cancellation_token

    def env(self) -> dict[str, str]:
        return self._env

    def close_client_socket(self) -> None:
        sock = self.client_socket
        if sock is not None:
            self.client_socket = None  # type: ignore[assignment]
            sock.close()

    def close(self) -> None:
        self.close_client_socket()
        self.cancellation_token.cancel()
        self.task.cancel()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


class EscalateServer:
    def __init__(self, shell_path: Path | str, execve_wrapper: Path | str, policy: EscalationPolicy) -> None:
        self.shell_path = Path(shell_path)
        self.execve_wrapper = Path(execve_wrapper)
        self.policy = policy

    async def exec(
        self,
        params: ExecParams,
        cancel_rx: CancellationToken,
        command_executor: ShellCommandExecutor,
    ) -> ExecResult:
        session = self.start_session(cancel_rx, command_executor)
        env_overlay = dict(session.env())
        client_socket = session.client_socket

        def after_spawn() -> None:
            if client_socket is not None:
                session.close_client_socket()

        command = [
            self.shell_path.as_posix(),
            "-c" if params.login is False else "-lc",
            params.command,
        ]
        return await command_executor.run(
            command,
            Path(params.workdir),
            env_overlay,
            cancel_rx,
            after_spawn,
        )

    def start_session(
        self,
        parent_cancellation_token: CancellationToken,
        command_executor: ShellCommandExecutor,
    ) -> EscalationSession:
        session_cancellation_token = CancellationToken()
        server, client = AsyncDatagramSocket.pair()
        client_socket = client.into_inner()
        env = {
            ESCALATE_SOCKET_ENV_VAR: str(client_socket.fileno()),
            EXEC_WRAPPER_ENV_VAR: self.execve_wrapper.as_posix(),
        }
        task = asyncio.create_task(
            escalate_task(
                server,
                self.policy,
                command_executor,
                parent_cancellation_token,
                session_cancellation_token,
            )
        )
        return EscalationSession(env, task, client_socket, session_cancellation_token)


async def escalate_task(
    socket: AsyncDatagramSocket,
    policy: EscalationPolicy,
    command_executor: ShellCommandExecutor,
    parent_cancellation_token: CancellationToken,
    session_cancellation_token: CancellationToken,
) -> None:
    while not parent_cancellation_token.is_cancelled() and not session_cancellation_token.is_cancelled():
        receive = asyncio.create_task(socket.receive_with_fds())
        parent_wait = asyncio.create_task(parent_cancellation_token.cancelled())
        session_wait = asyncio.create_task(session_cancellation_token.cancelled())
        done, pending = await asyncio.wait(
            {receive, parent_wait, session_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if receive not in done:
            return
        _data, fds = receive.result()
        if len(fds) != 1:
            continue
        stream_socket = AsyncSocket.from_fd(fds[0])
        asyncio.create_task(
            handle_escalate_session_with_policy(
                stream_socket,
                policy,
                command_executor,
                parent_cancellation_token,
                session_cancellation_token,
            )
        )


async def handle_escalate_session_with_policy(
    socket: AsyncSocket,
    policy: EscalationPolicy,
    command_executor: ShellCommandExecutor,
    parent_cancellation_token: CancellationToken,
    session_cancellation_token: CancellationToken,
) -> None:
    if parent_cancellation_token.is_cancelled() or session_cancellation_token.is_cancelled():
        return
    request = await socket.receive(EscalateRequest)
    program = request.file if request.file.is_absolute() else request.workdir / request.file
    decision = await policy.determine_action(program, list(request.argv), request.workdir)

    if decision.kind == "run":
        await socket.send(EscalateResponse(EscalateAction.run()))
        return

    if decision.kind == "deny":
        await socket.send(EscalateResponse(EscalateAction.deny(decision.reason)))
        return

    if decision.kind != "escalate":
        raise ValueError(f"unknown escalation decision kind: {decision.kind}")

    await socket.send(EscalateResponse(EscalateAction.escalate()))
    message, fds = await socket.receive_with_fds(SuperExecMessage)
    if len(fds) != len(message.fds):
        raise ValueError(
            "mismatched number of fds in SuperExecMessage: "
            f"{len(message.fds)} in the message, {len(fds)} from the control message"
        )
    prepared = await command_executor.prepare_escalated_exec(
        program,
        list(request.argv),
        request.workdir,
        dict(request.env),
        decision.execution,
    )
    if not prepared.command:
        raise ValueError("prepared escalated command must not be empty")
    process_env = os.environ.copy()
    process_env.update(prepared.env)
    proc = await asyncio.create_subprocess_exec(
        *prepared.command,
        cwd=prepared.cwd,
        env=process_env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    exit_code = await proc.wait()
    await socket.send(SuperExecResult(exit_code if exit_code is not None else 127))


async def main_execve_wrapper(argv: list[str] | tuple[str, ...] | None = None) -> int:
    parsed = ExecveWrapperCli.parse(argv)
    return await run_shell_escalation_execve_wrapper(parsed.file, list(parsed.argv))


def codex_execve_wrapper_main(
    argv: list[str] | tuple[str, ...] | None = None,
    *,
    platform: str | None = None,
) -> int:
    current_platform = os.name if platform is None else platform
    if current_platform != "posix":
        print("codex-execve-wrapper is only implemented for UNIX", file=sys.stderr)
        return 1
    return asyncio.run(main_execve_wrapper(argv))


__all__ = [
    "ESCALATE_SOCKET_ENV_VAR",
    "EXEC_WRAPPER_ENV_VAR",
    "MAX_DATAGRAM_SIZE",
    "MAX_FDS_PER_MESSAGE",
    "LENGTH_PREFIX_SIZE",
    "AsyncDatagramSocket",
    "AsyncSocket",
    "EscalateAction",
    "EscalateRequest",
    "EscalateResponse",
    "EscalateServer",
    "EscalationDecision",
    "EscalationExecution",
    "EscalationPermissions",
    "EscalationPolicy",
    "EscalationSession",
    "CancellationToken",
    "ExecParams",
    "ExecResult",
    "ExecveWrapperCli",
    "PreparedExec",
    "ResolvedPermissionProfile",
    "ShellCommandExecutor",
    "Stopwatch",
    "SuperExecMessage",
    "SuperExecResult",
    "codex_execve_wrapper_main",
    "encode_length",
    "duplicate_fd_for_transfer",
    "get_escalate_client",
    "main_execve_wrapper",
    "run_shell_escalation_execve_wrapper",
    "shell_escalation_request_env",
]
