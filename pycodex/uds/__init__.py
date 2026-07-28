"""Cross-platform Unix-domain-socket helpers.

Python port of Rust crate ``codex-uds``:

- ``codex/codex-rs/uds/src/lib.rs``
- ``codex/codex-rs/uds/src/lib_tests.rs``
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import platform as _platform


async def prepare_private_socket_directory(socket_dir: str | os.PathLike[str]) -> None:
    """Create ``socket_dir`` and restrict it to owner-only access where possible."""

    await _platform.prepare_private_socket_directory(Path(socket_dir))


async def is_stale_socket_path(socket_path: str | os.PathLike[str]) -> bool:
    """Return whether ``socket_path`` is a stale socket rendezvous path."""

    return await _platform.is_stale_socket_path(Path(socket_path))


class UnixStream:
    """Async Unix-domain-socket stream wrapper."""

    def __init__(self, inner: _platform.Stream) -> None:
        self._inner = inner

    @classmethod
    async def connect(cls, socket_path: str | os.PathLike[str]) -> "UnixStream":
        """Connect to ``socket_path``."""

        return cls(await _platform.connect_stream(Path(socket_path)))

    async def read(self, n: int = -1) -> bytes:
        return await self._inner.read(n)

    async def read_exactly(self, n: int) -> bytes:
        return await self._inner.read_exactly(n)

    def write(self, data: bytes | bytearray | memoryview) -> None:
        self._inner.write(data)

    async def write_all(self, data: bytes | bytearray | memoryview) -> None:
        await self._inner.write_all(data)

    async def drain(self) -> None:
        await self._inner.drain()

    def close(self) -> None:
        self._inner.close()

    async def wait_closed(self) -> None:
        await self._inner.wait_closed()

    async def shutdown_write(self) -> None:
        await self._inner.shutdown_write()


class UnixListener:
    """Async Unix-domain-socket listener wrapper."""

    def __init__(self, inner: _platform.Listener) -> None:
        self._inner = inner

    @classmethod
    async def bind(cls, socket_path: str | os.PathLike[str]) -> "UnixListener":
        """Bind a new listener at ``socket_path``."""

        return cls(await _platform.bind_listener(Path(socket_path)))

    async def accept(self) -> UnixStream:
        """Accept the next incoming stream."""

        return UnixStream(await self._inner.accept())

    def close(self) -> None:
        self._inner.close()

    async def wait_closed(self) -> None:
        await self._inner.wait_closed()

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


__all__ = [
    "UnixListener",
    "UnixStream",
    "is_stale_socket_path",
    "prepare_private_socket_directory",
]
