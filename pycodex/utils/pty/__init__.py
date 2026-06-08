"""Python port of the public ``codex-utils-pty`` crate interface.

Rust reference:
- ``codex/codex-rs/utils/pty/src/lib.rs``
- ``codex/codex-rs/utils/pty/src/process.rs``
- ``codex/codex-rs/utils/pty/src/pipe.rs``
- ``codex/codex-rs/utils/pty/src/pty.rs``
- ``codex/codex-rs/utils/pty/src/process_group.rs``
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_BYTES_CAP = 1024 * 1024


@dataclass(frozen=True)
class TerminalSize:
    rows: int = 24
    cols: int = 80


class _WriterSender:
    def __init__(self, write: Callable[[bytes], Awaitable[None]]) -> None:
        self._write = write

    async def send(self, chunk: bytes | bytearray | memoryview) -> None:
        await self._write(bytes(chunk))


class ProcessHandle:
    """Handle for driving an interactive process.

    This mirrors the Rust handle's user-visible contract: expose a stdin sender,
    exit state/code, resize, close stdin, and terminate helpers.
    """

    def __init__(
        self,
        process: asyncio.subprocess.Process | subprocess.Popen[bytes] | None,
        *,
        stdin_writer: Callable[[bytes], Awaitable[None]] | None = None,
        close_stdin: Callable[[], None] | None = None,
        terminator: Callable[[], None] | None = None,
        resizer: Callable[[TerminalSize], None] | None = None,
        exit_future: asyncio.Future[int] | None = None,
        helper_tasks: Sequence[asyncio.Task[Any]] = (),
    ) -> None:
        self._process = process
        self._stdin_writer = stdin_writer
        self._close_stdin = close_stdin
        self._terminator = terminator
        self._resizer = resizer
        self._exit_future = exit_future
        self._helper_tasks = list(helper_tasks)

    def writer_sender(self) -> _WriterSender:
        async def send(chunk: bytes) -> None:
            if self._stdin_writer is not None:
                await self._stdin_writer(chunk)

        return _WriterSender(send)

    def has_exited(self) -> bool:
        if self._exit_future is not None:
            return self._exit_future.done()
        return self._process is not None and self._process.returncode is not None

    def exit_code(self) -> int | None:
        if self._exit_future is not None and self._exit_future.done():
            try:
                return self._exit_future.result()
            except Exception:
                return -1
        if self._process is None:
            return None
        return self._process.returncode

    def resize(self, size: TerminalSize) -> None:
        if self._resizer is None:
            raise RuntimeError("process is not attached to a PTY")
        self._resizer(size)

    def close_stdin(self) -> None:
        if self._close_stdin is not None:
            self._close_stdin()

    def request_terminate(self) -> None:
        if self._terminator is not None:
            self._terminator()
            return
        if self._process is not None and self._process.returncode is None:
            self._process.kill()

    def terminate(self) -> None:
        self.request_terminate()
        for task in self._helper_tasks:
            task.cancel()


@dataclass
class SpawnedProcess:
    session: ProcessHandle
    stdout_rx: asyncio.Queue[bytes]
    stderr_rx: asyncio.Queue[bytes]
    exit_rx: asyncio.Future[int]


@dataclass
class ProcessDriver:
    writer_tx: Any
    stdout_rx: Any
    stderr_rx: Any | None
    exit_rx: Awaitable[int] | asyncio.Future[int]
    terminator: Callable[[], None] | None = None
    writer_handle: asyncio.Task[Any] | None = None
    resizer: Callable[[TerminalSize], None] | None = None


async def _read_stream(stream: asyncio.StreamReader | None, queue: asyncio.Queue[bytes]) -> None:
    if stream is None:
        return
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        await queue.put(chunk)


async def _wait_process(process: asyncio.subprocess.Process) -> int:
    try:
        return await process.wait()
    except Exception:
        return -1


def _normalize_env(env: Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in env.items()}


async def _spawn_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None,
    *,
    stdin_enabled: bool,
) -> SpawnedProcess:
    if not program:
        raise ValueError("missing program for pipe spawn")

    creationflags = 0
    preexec_fn = None
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        preexec_fn = os.setsid

    argv = [program, *map(str, args)]
    executable = program
    if arg0 is not None:
        argv[0] = arg0

    process = await asyncio.create_subprocess_exec(
        *argv,
        executable=executable,
        cwd=Path(cwd),
        env=_normalize_env(env),
        stdin=asyncio.subprocess.PIPE if stdin_enabled else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=creationflags,
        preexec_fn=preexec_fn,
    )

    stdout_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
    stderr_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
    stdout_task = asyncio.create_task(_read_stream(process.stdout, stdout_rx))
    stderr_task = asyncio.create_task(_read_stream(process.stderr, stderr_rx))
    exit_future = asyncio.create_task(_wait_process(process))

    async def write_stdin(chunk: bytes) -> None:
        if process.stdin is None or process.stdin.is_closing():
            return
        process.stdin.write(chunk)
        await process.stdin.drain()

    def close_stdin() -> None:
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()

    def terminate_process() -> None:
        if process.returncode is not None:
            return
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    handle = ProcessHandle(
        process,
        stdin_writer=write_stdin if stdin_enabled else None,
        close_stdin=close_stdin,
        terminator=terminate_process,
        exit_future=exit_future,
        helper_tasks=(stdout_task, stderr_task),
    )
    return SpawnedProcess(handle, stdout_rx, stderr_rx, exit_future)


async def spawn_pipe_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
) -> SpawnedProcess:
    return await _spawn_process(program, args, cwd, env, arg0, stdin_enabled=True)


async def spawn_pipe_process_no_stdin(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
) -> SpawnedProcess:
    return await _spawn_process(program, args, cwd, env, arg0, stdin_enabled=False)


async def spawn_pty_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    size: TerminalSize = TerminalSize(),
) -> SpawnedProcess:
    del size
    return await _spawn_process(program, args, cwd, env, arg0, stdin_enabled=True)


ExecCommandSession = ProcessHandle
SpawnedPty = SpawnedProcess


def conpty_supported() -> bool:
    return os.name != "nt" or sys.getwindowsversion().major >= 10


async def _forward_queue(src: Any, dst: asyncio.Queue[bytes]) -> None:
    while True:
        if hasattr(src, "get"):
            item = await src.get()
        elif hasattr(src, "recv"):
            item = await src.recv()
        else:
            raise TypeError("output receiver must provide get() or recv()")
        if item is None:
            break
        await dst.put(bytes(item))


def combine_output_receivers(stdout_rx: Any, stderr_rx: Any) -> asyncio.Queue[bytes]:
    combined: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
    asyncio.create_task(_forward_queue(stdout_rx, combined))
    asyncio.create_task(_forward_queue(stderr_rx, combined))
    return combined


def spawn_from_driver(driver: ProcessDriver) -> SpawnedProcess:
    stdout_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
    stderr_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
    tasks = [
        asyncio.create_task(_forward_queue(driver.stdout_rx, stdout_rx)),
    ]
    if driver.stderr_rx is not None:
        tasks.append(asyncio.create_task(_forward_queue(driver.stderr_rx, stderr_rx)))
    if driver.writer_handle is not None:
        tasks.append(driver.writer_handle)

    exit_future = asyncio.ensure_future(driver.exit_rx)

    async def write_stdin(chunk: bytes) -> None:
        writer = driver.writer_tx
        if hasattr(writer, "put"):
            await writer.put(chunk)
        elif hasattr(writer, "send"):
            result = writer.send(chunk)
            if hasattr(result, "__await__"):
                await result
        else:
            raise TypeError("driver writer must provide put() or send()")

    handle = ProcessHandle(
        None,
        stdin_writer=write_stdin,
        terminator=driver.terminator,
        resizer=driver.resizer,
        exit_future=exit_future,
        helper_tasks=tasks,
    )
    return SpawnedProcess(handle, stdout_rx, stderr_rx, exit_future)


class process_group:
    @staticmethod
    def set_parent_death_signal(parent_pid: int) -> None:
        del parent_pid

    @staticmethod
    def detach_from_tty() -> None:
        if os.name != "nt":
            os.setsid()

    @staticmethod
    def set_process_group() -> None:
        if os.name != "nt":
            os.setpgid(0, 0)

    @staticmethod
    def kill_process_group_by_pid(pid: int) -> None:
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except ProcessLookupError:
                return

    @staticmethod
    def terminate_process_group(process_group_id: int) -> bool:
        if os.name == "nt":
            return False
        try:
            os.killpg(process_group_id, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return False

    @staticmethod
    def kill_process_group(process_group_id: int) -> None:
        if os.name != "nt":
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                return

    @staticmethod
    def kill_child_process_group(child: Any) -> None:
        pid = getattr(child, "pid", None)
        if pid is not None:
            process_group.kill_process_group_by_pid(pid)


__all__ = [
    "DEFAULT_OUTPUT_BYTES_CAP",
    "ExecCommandSession",
    "ProcessDriver",
    "ProcessHandle",
    "SpawnedProcess",
    "SpawnedPty",
    "TerminalSize",
    "combine_output_receivers",
    "conpty_supported",
    "process_group",
    "spawn_from_driver",
    "spawn_pipe_process",
    "spawn_pipe_process_no_stdin",
    "spawn_pty_process",
]
