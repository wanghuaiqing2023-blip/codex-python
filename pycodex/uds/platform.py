"""Platform implementation for :mod:`pycodex.uds`.

Python owner for the inline Rust module ``codex-uds::platform``.
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
from pathlib import Path
from typing import Any

SOCKET_DIR_MODE = 0o700
SOCKET_DIR_PERMISSION_BITS = 0o777


def _is_windows() -> bool:
    return sys.platform == "win32"


def unix_socket_support_available() -> bool:
    return hasattr(asyncio, "start_unix_server") and hasattr(
        asyncio, "open_unix_connection"
    )


async def prepare_private_socket_directory(socket_dir: Path) -> None:
    if _is_windows():
        socket_dir.mkdir(parents=True, exist_ok=True)
        return

    try:
        socket_dir.mkdir(mode=SOCKET_DIR_MODE)
        return
    except FileExistsError:
        pass

    metadata = os.lstat(socket_dir)
    if not stat.S_ISDIR(metadata.st_mode):
        raise FileExistsError(
            f"socket directory path exists and is not a directory: {socket_dir}"
        )

    if metadata.st_mode & SOCKET_DIR_PERMISSION_BITS != SOCKET_DIR_MODE:
        os.chmod(socket_dir, SOCKET_DIR_MODE)


async def is_stale_socket_path(socket_path: Path) -> bool:
    if _is_windows():
        return socket_path.exists()

    metadata = os.lstat(socket_path)
    return stat.S_ISSOCK(metadata.st_mode)


class Stream:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self.reader = reader
        self.writer = writer

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


class Listener:
    def __init__(self, server: asyncio.AbstractServer, queue: asyncio.Queue[Stream]) -> None:
        self._server = server
        self._queue = queue

    async def accept(self) -> Stream:
        return await self._queue.get()

    def close(self) -> None:
        self._server.close()

    async def wait_closed(self) -> None:
        await self._server.wait_closed()


async def bind_listener(socket_path: Path) -> Listener:
    if not hasattr(asyncio, "start_unix_server"):
        raise OSError("asyncio.start_unix_server is not available")

    queue: asyncio.Queue[Stream] = asyncio.Queue()

    async def handle_client(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await queue.put(Stream(reader, writer))

    server = await asyncio.start_unix_server(handle_client, path=str(socket_path))
    return Listener(server, queue)


async def connect_stream(socket_path: Path) -> Stream:
    if not hasattr(asyncio, "open_unix_connection"):
        raise OSError("asyncio.open_unix_connection is not available")
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    return Stream(reader, writer)


__all__ = [
    "Listener",
    "SOCKET_DIR_MODE",
    "SOCKET_DIR_PERMISSION_BITS",
    "Stream",
    "bind_listener",
    "connect_stream",
    "is_stale_socket_path",
    "prepare_private_socket_directory",
]
