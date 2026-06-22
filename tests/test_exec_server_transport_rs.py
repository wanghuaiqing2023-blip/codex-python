from __future__ import annotations

import asyncio
import base64
import json
import os
import struct
from typing import Any

import pytest

import pycodex.exec_server as exec_server
from pycodex.exec_server import (
    ConnectionProcessor,
    DEFAULT_LISTEN_URL,
    ExecServerRuntimePaths,
    ExecServerListenTransport,
    ExecServerListenTransportKind,
    ExecServerListenUrlParseError,
    ExecServerListenUrlParseErrorKind,
    INITIALIZED_METHOD,
    INITIALIZE_METHOD,
    parse_listen_url,
    run_stdio_connection_with_io,
)


def test_parse_listen_url_accepts_default_websocket_url() -> None:
    # Rust crate/module/test:
    # codex-exec-server/src/server/transport_tests.rs
    # parse_listen_url_accepts_default_websocket_url.
    transport = parse_listen_url(DEFAULT_LISTEN_URL)

    assert transport == ExecServerListenTransport.websocket("127.0.0.1", 0)
    assert transport.kind is ExecServerListenTransportKind.WEBSOCKET
    assert transport.socket_addr == ("127.0.0.1", 0)


def test_parse_listen_url_accepts_stdio_forms() -> None:
    # Rust tests: parse_listen_url_accepts_stdio and
    # parse_listen_url_accepts_stdio_url.
    assert parse_listen_url("stdio") == ExecServerListenTransport.stdio()
    assert parse_listen_url("stdio://") == ExecServerListenTransport.stdio()


def test_parse_listen_url_accepts_websocket_url() -> None:
    # Rust test: parse_listen_url_accepts_websocket_url.
    assert parse_listen_url("ws://127.0.0.1:1234") == ExecServerListenTransport.websocket(
        "127.0.0.1",
        1234,
    )


def test_parse_listen_url_rejects_invalid_websocket_url() -> None:
    # Rust test: parse_listen_url_rejects_invalid_websocket_url.
    with pytest.raises(ExecServerListenUrlParseError) as exc_info:
        parse_listen_url("ws://localhost:1234")

    err = exc_info.value
    assert err.kind is ExecServerListenUrlParseErrorKind.INVALID_WEBSOCKET_LISTEN_URL
    assert err.listen_url == "ws://localhost:1234"
    assert str(err) == "invalid websocket --listen URL `ws://localhost:1234`; expected `ws://IP:PORT`"


def test_parse_listen_url_rejects_unsupported_url() -> None:
    # Rust test: parse_listen_url_rejects_unsupported_url.
    with pytest.raises(ExecServerListenUrlParseError) as exc_info:
        parse_listen_url("http://127.0.0.1:1234")

    err = exc_info.value
    assert err.kind is ExecServerListenUrlParseErrorKind.UNSUPPORTED_LISTEN_URL
    assert err.listen_url == "http://127.0.0.1:1234"
    assert (
        str(err)
        == "unsupported --listen URL `http://127.0.0.1:1234`; expected `ws://IP:PORT` or `stdio`"
    )


def test_parse_listen_url_rejects_bad_ports_and_missing_ports() -> None:
    # Rust module contract: websocket URLs must parse as std::net::SocketAddr.
    for listen_url in ("ws://127.0.0.1", "ws://127.0.0.1:not-a-port", "ws://127.0.0.1:65536"):
        with pytest.raises(ExecServerListenUrlParseError) as exc_info:
            parse_listen_url(listen_url)
        assert exc_info.value.kind is ExecServerListenUrlParseErrorKind.INVALID_WEBSOCKET_LISTEN_URL


def test_stdio_listen_transport_serves_initialize(tmp_path) -> None:
    # Rust crate/module/test:
    # codex-exec-server/src/server/transport_tests.rs
    # stdio_listen_transport_serves_initialize.
    # Contract: stdio listen transport runs a JSON-RPC connection over newline
    # framed IO, routes initialize through ConnectionProcessor/build_router, and
    # exits cleanly once the client sends initialized and disconnects.
    async def run() -> list[dict[str, object]]:
        reader = asyncio.StreamReader()
        writer = MemoryWriter()
        initialize = {
            "id": 1,
            "method": INITIALIZE_METHOD,
            "params": {
                "clientName": "exec-server-transport-test",
            },
        }
        initialized = {
            "method": INITIALIZED_METHOD,
            "params": None,
        }
        reader.feed_data(json.dumps(initialize, separators=(",", ":")).encode("utf-8") + b"\n")
        reader.feed_data(json.dumps(initialized, separators=(",", ":")).encode("utf-8") + b"\n")
        reader.feed_eof()

        await run_stdio_connection_with_io(
            reader,
            writer,
            ExecServerRuntimePaths.new(tmp_path / "codex", None),
        )
        return [json.loads(line) for line in writer.text_lines()]

    responses = asyncio.run(run())

    assert len(responses) == 1
    assert responses[0]["id"] == 1
    assert isinstance(responses[0]["result"], dict)
    assert isinstance(responses[0]["result"]["sessionId"], str)
    assert responses[0]["result"]["sessionId"]


def test_websocket_http_handler_serves_readyz_and_initialize(tmp_path) -> None:
    # Rust crate/module/source contract:
    # codex-exec-server/src/server/transport.rs::run_websocket_listener,
    # readiness_handler, and websocket_upgrade_handler.
    # Contract: websocket listen transport binds ws://IP:PORT, serves GET
    # /readyz with 200 OK, upgrades GET / to a websocket, and routes frames
    # through JsonRpcConnection::from_axum_websocket into ConnectionProcessor.
    async def run() -> None:
        readyz_reader = asyncio.StreamReader()
        readyz_writer = MemoryAsyncWriter()
        readyz_reader.feed_data(b"GET /readyz HTTP/1.1\r\nhost: 127.0.0.1\r\n\r\n")
        readyz_reader.feed_eof()
        await exec_server._handle_exec_server_http_connection(
            readyz_reader,
            readyz_writer,
            ConnectionProcessor.new(ExecServerRuntimePaths.new(tmp_path / "codex", None)),
        )
        assert readyz_writer.bytes().startswith(b"HTTP/1.1 200 OK\r\n")

        websocket_reader = asyncio.StreamReader()
        websocket_writer = MemoryAsyncWriter()
        websocket_reader.feed_data(websocket_handshake_bytes())
        websocket_task = asyncio.create_task(exec_server._handle_exec_server_http_connection(
            websocket_reader,
            websocket_writer,
            ConnectionProcessor.new(ExecServerRuntimePaths.new(tmp_path / "codex", None)),
        ))
        await wait_until(lambda: b"\r\n\r\n" in websocket_writer.bytes())
        websocket_reader.feed_data(websocket_initialize_frame())
        await wait_until(lambda: websocket_writer.bytes().count(b"\r\n\r\n") == 1 and len(websocket_writer.bytes().split(b"\r\n\r\n", 1)[1]) > 2)
        assert_websocket_initialize_response(websocket_writer.bytes())
        websocket_reader.feed_data(websocket_initialized_frame() + client_websocket_frame(b"", opcode=0x8))
        websocket_reader.feed_eof()
        await asyncio.wait_for(websocket_task, timeout=1.0)

    asyncio.run(run())


class MemoryWriter:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def text_lines(self) -> list[str]:
        return [line.decode("utf-8") for line in bytes(self.data).splitlines()]


class MemoryAsyncWriter(MemoryWriter):
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None

    def get_extra_info(self, name: str, default: object | None = None) -> object | None:
        if name == "peername":
            return ("127.0.0.1", 44444)
        return default

    def bytes(self) -> bytes:
        return bytes(self.data)


def websocket_handshake_bytes() -> bytes:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    return (
        "GET / HTTP/1.1\r\n"
        "host: 127.0.0.1\r\n"
        "upgrade: websocket\r\n"
        "connection: Upgrade\r\n"
        f"sec-websocket-key: {key}\r\n"
        "sec-websocket-version: 13\r\n"
        "\r\n"
    ).encode("ascii")


def websocket_initialize_frame() -> bytes:
    initialize = {
        "id": 7,
        "method": INITIALIZE_METHOD,
        "params": {
            "clientName": "exec-server-websocket-test",
        },
    }
    return client_websocket_frame(json.dumps(initialize, separators=(",", ":")).encode("utf-8"))


def websocket_initialized_frame() -> bytes:
    initialized = {
        "method": INITIALIZED_METHOD,
        "params": None,
    }
    return client_websocket_frame(json.dumps(initialized, separators=(",", ":")).encode("utf-8"))


def assert_websocket_initialize_response(data: bytes) -> None:
    head, payload = data.split(b"\r\n\r\n", 1)
    assert head.startswith(b"HTTP/1.1 101 Switching Protocols\r\n")
    assert b"sec-websocket-accept:" in head.lower()
    response_payload, _rest = read_server_websocket_payload(payload)
    response_message = json.loads(response_payload.decode("utf-8"))
    assert response_message["id"] == 7
    assert response_message["result"]["sessionId"]


def client_websocket_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    mask = os.urandom(4)
    length = len(payload)
    first = 0x80 | opcode
    if length < 126:
        header = bytes((first, 0x80 | length))
    elif length <= 0xFFFF:
        header = bytes((first, 0x80 | 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, 0x80 | 127)) + struct.pack("!Q", length)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return header + mask + masked


async def wait_until(predicate: Any, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not satisfied before timeout")


def read_server_websocket_payload(data: bytes) -> tuple[bytes, bytes]:
    first, second = data[0], data[1]
    offset = 2
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", data[offset : offset + 2])[0]
        offset += 2
    elif length == 127:
        length = struct.unpack("!Q", data[offset : offset + 8])[0]
        offset += 8
    payload = data[offset : offset + length]
    assert opcode == 0x1
    return payload, data[offset + length :]
