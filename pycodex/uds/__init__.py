"""Cross-platform Unix-domain-socket helpers.

Python port of Rust crate ``codex-uds``:

- ``codex/codex-rs/uds/src/lib.rs``
- ``codex/codex-rs/uds/src/lib_tests.rs``
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

SOCKET_DIR_MODE = 0o700
SOCKET_DIR_PERMISSION_BITS = 0o777


class UnsupportedUnixSocketError(OSError):
    """Raised when Python's standard library lacks Unix socket support."""


def _is_windows() -> bool:
    return sys.platform == "win32"


def unix_socket_support_available() -> bool:
    """Return whether this Python runtime exposes asyncio Unix socket APIs."""

    return hasattr(asyncio, "start_unix_server") and hasattr(asyncio, "open_unix_connection")


async def prepare_private_socket_directory(socket_dir: str | os.PathLike[str]) -> None:
    """Create ``socket_dir`` and restrict it to owner-only access where possible."""

    path = Path(socket_dir)
    if _is_windows():
        path.mkdir(parents=True, exist_ok=True)
        return

    try:
        path.mkdir(mode=SOCKET_DIR_MODE)
        return
    except FileExistsError:
        pass

    metadata = os.lstat(path)
    if not stat.S_ISDIR(metadata.st_mode):
        raise FileExistsError(f"socket directory path exists and is not a directory: {path}")

    if metadata.st_mode & SOCKET_DIR_PERMISSION_BITS != SOCKET_DIR_MODE:
        os.chmod(path, SOCKET_DIR_MODE)


async def is_stale_socket_path(socket_path: str | os.PathLike[str]) -> bool:
    """Return whether ``socket_path`` is a stale socket rendezvous path."""

    path = Path(socket_path)
    if _is_windows():
        return path.exists()

    metadata = os.lstat(path)
    return stat.S_ISSOCK(metadata.st_mode)


class UnixStream:
    """Async Unix-domain-socket stream wrapper."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    @classmethod
    async def connect(cls, socket_path: str | os.PathLike[str]) -> "UnixStream":
        """Connect to ``socket_path``."""

        if not hasattr(asyncio, "open_unix_connection"):
            raise UnsupportedUnixSocketError("asyncio.open_unix_connection is not available")
        reader, writer = await asyncio.open_unix_connection(str(Path(socket_path)))
        return cls(reader, writer)

    async def read(self, n: int = -1) -> bytes:
        return await self.reader.read(n)

    async def read_exactly(self, n: int) -> bytes:
        return await self.reader.readexactly(n)

    def write(self, data: bytes | bytearray | memoryview) -> None:
        self.writer.write(bytes(data))

    async def write_all(self, data: bytes | bytearray | memoryview) -> None:
        self.write(data)
        await self.writer.drain()

    async def drain(self) -> None:
        await self.writer.drain()

    def close(self) -> None:
        self.writer.close()

    async def wait_closed(self) -> None:
        await self.writer.wait_closed()

    async def shutdown_write(self) -> None:
        try:
            self.writer.write_eof()
        finally:
            await self.writer.drain()


class UnixListener:
    """Async Unix-domain-socket listener wrapper."""

    def __init__(self, server: asyncio.AbstractServer, queue: asyncio.Queue[UnixStream]) -> None:
        self._server = server
        self._queue = queue

    @classmethod
    async def bind(cls, socket_path: str | os.PathLike[str]) -> "UnixListener":
        """Bind a new listener at ``socket_path``."""

        if not hasattr(asyncio, "start_unix_server"):
            raise UnsupportedUnixSocketError("asyncio.start_unix_server is not available")

        queue: asyncio.Queue[UnixStream] = asyncio.Queue()

        async def handle_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            await queue.put(UnixStream(reader, writer))

        server = await asyncio.start_unix_server(handle_client, path=str(Path(socket_path)))
        return cls(server, queue)

    async def accept(self) -> UnixStream:
        """Accept the next incoming stream."""

        return await self._queue.get()

    def close(self) -> None:
        self._server.close()

    async def wait_closed(self) -> None:
        await self._server.wait_closed()

    async def __aenter__(self) -> "UnixListener":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        self.close()
        await self.wait_closed()


async def run_connected_pair(
    socket_path: str | os.PathLike[str],
    server_task: Callable[[UnixStream], Awaitable[None]],
    client_task: Callable[[UnixStream], Awaitable[None]],
) -> None:
    """Small test helper mirroring the Rust listener/client rendezvous pattern."""

    listener = await UnixListener.bind(socket_path)
    try:
        async def serve_once() -> None:
            stream = await listener.accept()
            await server_task(stream)

        server = asyncio.create_task(serve_once())
        client = await UnixStream.connect(socket_path)
        try:
            await client_task(client)
        finally:
            client.close()
            await client.wait_closed()
        await server
    finally:
        listener.close()
        await listener.wait_closed()


__all__ = [
    "SOCKET_DIR_MODE",
    "SOCKET_DIR_PERMISSION_BITS",
    "UnsupportedUnixSocketError",
    "UnixListener",
    "UnixStream",
    "is_stale_socket_path",
    "prepare_private_socket_directory",
    "run_connected_pair",
    "unix_socket_support_available",
]
