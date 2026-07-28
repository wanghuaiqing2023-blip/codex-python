"""Python interface for Rust ``codex-exec-server``."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
import binascii
import errno
import hashlib
from functools import total_ordering
import inspect
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import struct
import sys
import time
import tomllib
from typing import Any
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pycodex.app_server.error_code import internal_error, invalid_params, invalid_request, method_not_found
from pycodex.app_server_protocol.jsonrpc_lite import (
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    PermissionProfile,
    RequestId,
    WindowsSandboxLevel,
)
from pycodex.sandboxing import (
    SandboxCommand,
    SandboxManager,
    SandboxTransformRequest,
    SandboxablePreference,
)
from pycodex.protocol.shell_environment import create_env as create_shell_env
from pycodex.utils.absolute_path import AbsolutePathBuf



from pycodex.file_system import (
    CopyOptions,
    CreateDirectoryOptions,
    ExecutorFileSystem,
    FileMetadata,
    FileSystemSandboxContext,
    ReadDirectoryEntry,
    RemoveOptions,
)
from pycodex.file_system import FileSystemResult


DEFAULT_LISTEN_URL = "ws://127.0.0.1:0"


def _rust_duration_debug(seconds: int | float) -> str:
    if seconds == int(seconds):
        return f"{int(seconds)}s"
    millis = seconds * 1000
    if millis == int(millis):
        return f"{int(millis)}ms"
    return f"{seconds}s"


class ExecServerListenUrlParseErrorKind(str, Enum):
    UNSUPPORTED_LISTEN_URL = "unsupportedListenUrl"
    INVALID_WEBSOCKET_LISTEN_URL = "invalidWebSocketListenUrl"


class ExecServerListenUrlParseError(ValueError):
    def __init__(self, kind: ExecServerListenUrlParseErrorKind, listen_url: str) -> None:
        self.kind = kind
        self.listen_url = listen_url
        super().__init__(str(self))

    @classmethod
    def unsupported_listen_url(cls, listen_url: str) -> "ExecServerListenUrlParseError":
        return cls(ExecServerListenUrlParseErrorKind.UNSUPPORTED_LISTEN_URL, listen_url)

    @classmethod
    def invalid_websocket_listen_url(cls, listen_url: str) -> "ExecServerListenUrlParseError":
        return cls(ExecServerListenUrlParseErrorKind.INVALID_WEBSOCKET_LISTEN_URL, listen_url)

    def __str__(self) -> str:
        if self.kind is ExecServerListenUrlParseErrorKind.UNSUPPORTED_LISTEN_URL:
            return f"unsupported --listen URL `{self.listen_url}`; expected `ws://IP:PORT` or `stdio`"
        return f"invalid websocket --listen URL `{self.listen_url}`; expected `ws://IP:PORT`"


class ExecServerListenTransportKind(str, Enum):
    WEBSOCKET = "websocket"
    STDIO = "stdio"


@dataclass(frozen=True)
class ExecServerListenTransport:
    kind: ExecServerListenTransportKind
    socket_addr: tuple[str, int] | None = None

    @classmethod
    def websocket(cls, host: str, port: int) -> "ExecServerListenTransport":
        return cls(ExecServerListenTransportKind.WEBSOCKET, (host, port))

    @classmethod
    def stdio(cls) -> "ExecServerListenTransport":
        return cls(ExecServerListenTransportKind.STDIO)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ExecServerListenTransportKind):
            object.__setattr__(self, "kind", ExecServerListenTransportKind(self.kind))
        if self.kind is ExecServerListenTransportKind.WEBSOCKET:
            if self.socket_addr is None:
                raise ValueError("socket_addr is required for websocket listen transport")
        elif self.socket_addr is not None:
            raise ValueError("socket_addr is only valid for websocket listen transport")


def parse_listen_url(listen_url: str) -> ExecServerListenTransport:
    if listen_url in {"stdio", "stdio://"}:
        return ExecServerListenTransport.stdio()

    if listen_url.startswith("ws://"):
        socket_addr = listen_url[len("ws://") :]
        parsed = _parse_socket_addr(socket_addr)
        if parsed is None:
            raise ExecServerListenUrlParseError.invalid_websocket_listen_url(listen_url)
        return ExecServerListenTransport.websocket(*parsed)

    raise ExecServerListenUrlParseError.unsupported_listen_url(listen_url)


async def run_transport(listen_url: str, runtime_paths: "ExecServerRuntimePaths") -> None:
    transport = parse_listen_url(listen_url)
    if transport.kind is ExecServerListenTransportKind.STDIO:
        await run_stdio_connection(runtime_paths)
        return
    assert transport.socket_addr is not None
    await run_websocket_listener(transport.socket_addr, runtime_paths)


async def run_stdio_connection(runtime_paths: "ExecServerRuntimePaths") -> None:
    await run_stdio_connection_with_io(sys.stdin.buffer, sys.stdout.buffer, runtime_paths)


async def run_stdio_connection_with_io(reader: Any, writer: Any, runtime_paths: "ExecServerRuntimePaths") -> None:
    processor = ConnectionProcessor.new(runtime_paths)
    await processor.run_connection(JsonRpcConnection.from_stdio(reader, writer, "exec-server stdio"))


async def readiness_handler() -> int:
    return 200


async def run_websocket_listener(
    bind_address: tuple[str, int],
    runtime_paths: "ExecServerRuntimePaths",
) -> None:
    processor = ConnectionProcessor.new(runtime_paths)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_exec_server_http_connection(reader, writer, processor)

    server = await asyncio.start_server(handle, bind_address[0], bind_address[1])
    sockets = server.sockets or ()
    if sockets:
        print(f"ws://{_format_socket_addr(sockets[0].getsockname())}", flush=True)
    async with server:
        await server.serve_forever()


async def _handle_exec_server_http_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    processor: "ConnectionProcessor",
) -> None:
    try:
        request = await _read_http_request(reader)
        if request is None:
            return
        method, target, headers = request
        if method == "GET" and target == "/readyz":
            await _write_http_response(writer, await readiness_handler(), "OK")
            return
        if method == "GET" and target == "/":
            accept_key = _websocket_accept_key(headers)
            if accept_key is None:
                await _write_http_response(writer, 400, "Bad Request")
                return
            await _write_websocket_upgrade_response(writer, accept_key)
            peer = _format_socket_addr(writer.get_extra_info("peername"))
            await processor.run_connection(
                JsonRpcConnection.from_websocket(
                    _StreamWebSocket(reader, writer),
                    f"exec-server websocket {peer}",
                )
            )
            return
        await _write_http_response(writer, 404, "Not Found")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _read_http_request(reader: asyncio.StreamReader) -> tuple[str, str, dict[str, str]] | None:
    data = await reader.readuntil(b"\r\n\r\n")
    head = data.decode("iso-8859-1")
    lines = head.split("\r\n")
    if not lines or not lines[0]:
        return None
    parts = lines[0].split()
    if len(parts) < 3:
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return parts[0], parts[1], headers


async def _write_http_response(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
    response = (
        f"HTTP/1.1 {status} {reason}\r\n"
        "content-length: 0\r\n"
        "connection: close\r\n"
        "\r\n"
    )
    writer.write(response.encode("ascii"))
    await writer.drain()


def _websocket_accept_key(headers: Mapping[str, str]) -> str | None:
    upgrade = headers.get("upgrade", "")
    connection = headers.get("connection", "")
    key = headers.get("sec-websocket-key")
    version = headers.get("sec-websocket-version")
    if upgrade.lower() != "websocket" or "upgrade" not in connection.lower() or not key or version != "13":
        return None
    digest = hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


async def _write_websocket_upgrade_response(writer: asyncio.StreamWriter, accept_key: str) -> None:
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "upgrade: websocket\r\n"
        "connection: Upgrade\r\n"
        f"sec-websocket-accept: {accept_key}\r\n"
        "\r\n"
    )
    writer.write(response.encode("ascii"))
    await writer.drain()


def _format_socket_addr(addr: Any) -> str:
    if isinstance(addr, tuple) and len(addr) >= 2:
        host, port = addr[0], addr[1]
        if ":" in str(host) and not str(host).startswith("["):
            return f"[{host}]:{port}"
        return f"{host}:{port}"
    return str(addr)


class _StreamWebSocket:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        mask_outgoing: bool = False,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.mask_outgoing = mask_outgoing
        self._send_lock = asyncio.Lock()

    async def recv(self) -> JsonRpcWebSocketMessage | None:
        while True:
            header = await self.reader.readexactly(2)
            first, second = header
            opcode = first & 0x0F
            masked = (second & 0x80) != 0
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", await self.reader.readexactly(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", await self.reader.readexactly(8))[0]
            mask = await self.reader.readexactly(4) if masked else b""
            payload = await self.reader.readexactly(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x1:
                return JsonRpcWebSocketMessage.text(payload.decode("utf-8"))
            if opcode == 0x2:
                return JsonRpcWebSocketMessage.binary(payload)
            if opcode == 0x8:
                await self.send(JsonRpcWebSocketMessage.close())
                return JsonRpcWebSocketMessage.close()
            if opcode == 0x9:
                await self.send(JsonRpcWebSocketMessage.pong(payload))
                continue
            if opcode == 0xA:
                return JsonRpcWebSocketMessage.pong(payload)
            raise ValueError(f"unsupported websocket opcode: {opcode}")

    async def send(self, message: JsonRpcWebSocketMessage) -> None:
        if message.kind == "text":
            opcode = 0x1
            payload = (message.data or "").encode("utf-8")
        elif message.kind == "binary":
            opcode = 0x2
            payload = message.data or b""
        elif message.kind == "close":
            opcode = 0x8
            payload = b""
        elif message.kind == "ping":
            opcode = 0x9
            payload = message.data or b""
        elif message.kind == "pong":
            opcode = 0xA
            payload = message.data or b""
        else:
            raise ValueError(f"unknown websocket frame kind: {message.kind}")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        async with self._send_lock:
            self.writer.write(_encode_websocket_frame(opcode, payload, masked=self.mask_outgoing))
            await self.writer.drain()


def _encode_websocket_frame(opcode: int, payload: bytes, *, masked: bool = False) -> bytes:
    first = 0x80 | opcode
    length = len(payload)
    mask_bit = 0x80 if masked else 0
    if length < 126:
        header = bytes((first, mask_bit | length))
    elif length <= 0xFFFF:
        header = bytes((first, mask_bit | 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, mask_bit | 127)) + struct.pack("!Q", length)
    if not masked:
        return header + payload
    mask = os.urandom(4)
    masked_payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return header + mask + masked_payload


async def _connect_websocket_url(websocket_url: str) -> _StreamWebSocket:
    parsed = urlsplit(websocket_url)
    if parsed.scheme not in {"ws", "wss"}:
        raise ValueError(f"unsupported websocket URL scheme `{parsed.scheme}`")
    if not parsed.hostname:
        raise ValueError("websocket URL must include a host")
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    ssl_context = ssl.create_default_context() if parsed.scheme == "wss" else None
    reader, writer = await asyncio.open_connection(parsed.hostname, port, ssl=ssl_context)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    host_header = _websocket_host_header(parsed.hostname, port, parsed.scheme)
    request = (
        f"GET {request_target} HTTP/1.1\r\n"
        f"host: {host_header}\r\n"
        "upgrade: websocket\r\n"
        "connection: Upgrade\r\n"
        f"sec-websocket-key: {key}\r\n"
        "sec-websocket-version: 13\r\n"
        "\r\n"
    )
    writer.write(request.encode("ascii"))
    await writer.drain()
    response = await reader.readuntil(b"\r\n\r\n")
    _validate_websocket_upgrade_response(response, key)
    return _StreamWebSocket(reader, writer, mask_outgoing=True)


def _websocket_host_header(host: str, port: int, scheme: str) -> str:
    default_port = 443 if scheme == "wss" else 80
    display_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    if port == default_port:
        return display_host
    return f"{display_host}:{port}"


def _validate_websocket_upgrade_response(response: bytes, key: str) -> None:
    text = response.decode("iso-8859-1")
    lines = text.split("\r\n")
    status_parts = lines[0].split()
    if len(status_parts) < 2 or status_parts[1] != "101":
        raise ValueError(f"websocket upgrade failed: {lines[0]}")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    expected_accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")
    if not _header_has_token(headers, "upgrade", "websocket"):
        raise ValueError("websocket upgrade failed: invalid Upgrade header")
    if not _header_has_token(headers, "connection", "upgrade"):
        raise ValueError("websocket upgrade failed: invalid Connection header")
    if headers.get("sec-websocket-accept") != expected_accept:
        raise ValueError("websocket upgrade failed: invalid Sec-WebSocket-Accept")


def _header_has_token(headers: Mapping[str, str], name: str, token: str) -> bool:
    value = headers.get(name.lower())
    if value is None:
        return False
    expected = token.lower()
    return any(part.strip().lower() == expected for part in value.split(","))


from pycodex.exec_server.connection import JsonRpcConnection, JsonRpcWebSocketMessage, _parse_socket_addr
from pycodex.exec_server.server.processor import ConnectionProcessor
