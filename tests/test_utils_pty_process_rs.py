"""Rust-derived tests for codex-utils-pty/src/process.rs."""

from __future__ import annotations

import asyncio

import pytest

from pycodex.utils.pty import ProcessDriver, ProcessHandle, TerminalSize, spawn_from_driver


def test_terminal_size_default_and_u16_bounds_match_rust_type() -> None:
    # Rust: codex-utils-pty/src/process.rs::TerminalSize
    # Contract: TerminalSize defaults to 24x80 and stores u16 row/col cells.
    assert TerminalSize() == TerminalSize(rows=24, cols=80)
    assert TerminalSize(rows=0, cols=65535) == TerminalSize(rows=0, cols=65535)

    with pytest.raises(ValueError, match="rows must fit in u16"):
        TerminalSize(rows=-1, cols=80)
    with pytest.raises(ValueError, match="cols must fit in u16"):
        TerminalSize(rows=24, cols=65536)
    with pytest.raises(TypeError, match="rows must be an integer"):
        TerminalSize(rows=True, cols=80)


def test_process_handle_resize_without_pty_or_resizer_reports_rust_error() -> None:
    # Rust: codex-utils-pty/src/process.rs::ProcessHandle::resize
    # Contract: handles without PTY handles or a driver resizer fail with the
    # Rust error message.
    handle = ProcessHandle(None)

    with pytest.raises(RuntimeError, match="process is not attached to a PTY"):
        handle.resize(TerminalSize(rows=40, cols=120))


def test_driver_backed_process_can_resize_via_resizer_hook() -> None:
    # Rust test: driver_backed_process_can_resize_via_resizer_hook
    # Contract: spawn_from_driver installs the optional resizer hook, and
    # ProcessHandle::resize forwards the requested TerminalSize into it.
    async def run() -> list[TerminalSize]:
        writer: asyncio.Queue[bytes] = asyncio.Queue()
        stdout: asyncio.Queue[bytes | None] = asyncio.Queue()
        exit_future: asyncio.Future[int] = asyncio.Future()
        resized: list[TerminalSize] = []
        spawned = spawn_from_driver(
            ProcessDriver(
                writer_tx=writer,
                stdout_rx=stdout,
                stderr_rx=None,
                exit_rx=exit_future,
                resizer=resized.append,
            )
        )

        spawned.session.resize(TerminalSize(rows=40, cols=120))
        exit_future.set_result(0)
        await spawned.exit_rx
        return resized

    assert asyncio.run(run()) == [TerminalSize(rows=40, cols=120)]


def test_writer_sender_after_close_stdin_is_closed() -> None:
    # Rust: codex-utils-pty/src/process.rs::ProcessHandle::close_stdin
    # Contract: close_stdin removes the internal writer_tx; a later
    # writer_sender() returns a closed fallback sender rather than forwarding
    # bytes to the original process writer.
    async def run() -> list[bytes]:
        written: list[bytes] = []

        async def write(chunk: bytes) -> None:
            written.append(chunk)

        handle = ProcessHandle(None, stdin_writer=write)
        handle.close_stdin()
        await handle.writer_sender().send(b"after-close")
        return written

    assert asyncio.run(run()) == []
