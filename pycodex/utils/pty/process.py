"""Process handles and driver adapters from codex-utils-pty/src/process.rs."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TerminalSize:
    rows: int = 24
    cols: int = 80

    def __post_init__(self) -> None:
        for name, value in (("rows", self.rows), ("cols", self.cols)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0 or value > 0xFFFF:
                raise ValueError(f"{name} must fit in u16")


class _WriterSender:
    def __init__(self, write: Callable[[bytes], Awaitable[None]]) -> None:
        self._write = write

    async def send(self, chunk: bytes | bytearray | memoryview) -> None:
        await self._write(bytes(chunk))


class ProcessHandle:
    def __init__(
        self,
        process: asyncio.subprocess.Process | subprocess.Popen[bytes] | Any | None,
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
        self._stdin_closed = False

    def writer_sender(self) -> _WriterSender:
        async def send(chunk: bytes) -> None:
            if not self._stdin_closed and self._stdin_writer is not None:
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
        self._stdin_closed = True
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
    tasks = [asyncio.create_task(_forward_queue(driver.stdout_rx, stdout_rx))]
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


__all__ = [
    "ProcessDriver",
    "ProcessHandle",
    "SpawnedProcess",
    "TerminalSize",
    "combine_output_receivers",
    "spawn_from_driver",
]
