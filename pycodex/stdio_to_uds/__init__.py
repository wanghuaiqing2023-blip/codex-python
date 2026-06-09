"""Port of Rust ``codex-stdio-to-uds``.

Rust source:
- ``codex/codex-rs/stdio-to-uds/src/lib.rs``
- ``codex/codex-rs/stdio-to-uds/src/main.rs``
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import BinaryIO, Sequence


class StdioToUdsError(OSError):
    """Raised when stdio-to-UDS relay setup or execution fails."""


async def run(socket_path: str | os.PathLike[str]) -> None:
    """Connect to ``socket_path`` and relay data between stdio and the socket."""

    reader, writer = await _connect_unix_socket(socket_path)

    async def copy_socket_to_stdout() -> None:
        while True:
            chunk = await reader.read(64 * 1024)
            if not chunk:
                break
            await asyncio.to_thread(sys.stdout.buffer.write, chunk)
        await asyncio.to_thread(sys.stdout.buffer.flush)

    async def copy_stdin_to_socket() -> None:
        await _copy_file_to_writer(sys.stdin.buffer, writer)
        try:
            writer.write_eof()
            await writer.drain()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    try:
        await asyncio.gather(copy_stdin_to_socket(), copy_socket_to_stdout())
    except Exception as exc:
        raise StdioToUdsError("failed to relay data between stdio and socket") from exc


async def _connect_unix_socket(socket_path: str | os.PathLike[str]) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    if not hasattr(asyncio, "open_unix_connection"):
        raise StdioToUdsError("Unix domain sockets are not supported on this platform")
    path = Path(socket_path)
    try:
        return await asyncio.open_unix_connection(str(path))
    except OSError as exc:
        raise StdioToUdsError(f"failed to connect to socket at {path}") from exc


async def _copy_file_to_writer(source: BinaryIO, writer: asyncio.StreamWriter) -> None:
    while True:
        chunk = await asyncio.to_thread(source.read, 64 * 1024)
        if not chunk:
            break
        writer.write(chunk)
        await writer.drain()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codex-stdio-to-uds",
        usage="codex-stdio-to-uds <socket-path>",
        add_help=False,
    )
    parser.add_argument("socket_path", nargs="?")
    parser.add_argument("extra", nargs="*")
    args = parser.parse_args(argv)

    if args.socket_path is None:
        print("Usage: codex-stdio-to-uds <socket-path>", file=sys.stderr)
        return 1
    if args.extra:
        print("Expected exactly one argument: <socket-path>", file=sys.stderr)
        return 1

    asyncio.run(run(args.socket_path))
    return 0


__all__ = [
    "StdioToUdsError",
    "main",
    "run",
]
