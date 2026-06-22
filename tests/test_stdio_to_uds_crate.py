from __future__ import annotations

import asyncio
import io
import sys

import pytest

from pycodex import stdio_to_uds


def test_main_requires_socket_path(capsys: pytest.CaptureFixture[str]) -> None:
    # Rust crate/module: codex-stdio-to-uds src/main.rs. Behavior contract:
    # missing socket path prints the usage line and exits with status 1.
    assert stdio_to_uds.main([]) == 1
    captured = capsys.readouterr()
    assert captured.err == "Usage: codex-stdio-to-uds <socket-path>\n"


def test_main_rejects_extra_args(capsys: pytest.CaptureFixture[str]) -> None:
    # Rust crate/module: codex-stdio-to-uds src/main.rs. Behavior contract:
    # more than one argument is rejected with the exact user-facing message.
    assert stdio_to_uds.main(["socket", "extra"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "Expected exactly one argument: <socket-path>\n"


def test_main_treats_dash_prefixed_socket_path_as_positional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust crate/module: codex-stdio-to-uds src/main.rs. Behavior contract:
    # args_os().skip(1) has no option parser, so dash-prefixed paths are
    # ordinary socket-path arguments.
    seen: list[str] = []

    async def fake_run(socket_path: str) -> None:
        seen.append(socket_path)

    monkeypatch.setattr(stdio_to_uds, "run", fake_run)

    assert stdio_to_uds.main(["--socket-like"]) == 0
    assert seen == ["--socket-like"]


@pytest.mark.skipif(
    not hasattr(asyncio, "open_unix_connection") or not hasattr(asyncio, "start_unix_server"),
    reason="Unix domain sockets are unavailable on this platform",
)
@pytest.mark.asyncio
async def test_run_pipes_stdin_and_stdout_through_socket(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rust crate/module: codex-stdio-to-uds src/lib.rs, Rust integration test
    # pipes_stdin_and_stdout_through_socket. Behavior contract: stdin bytes are
    # sent to the socket and socket bytes are written to stdout.
    socket_path = tmp_path / "socket"
    request = b"request"
    received: list[bytes] = []

    async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        received.append(await reader.readexactly(len(request)))
        writer.write(b"response")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_connection, path=str(socket_path))
    stdin = type("FakeStdin", (), {"buffer": io.BytesIO(request)})()
    stdout_buffer = io.BytesIO()
    stdout = type("FakeStdout", (), {"buffer": stdout_buffer})()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    async with server:
        await stdio_to_uds.run(socket_path)

    assert received == [request]
    assert stdout_buffer.getvalue() == b"response"
