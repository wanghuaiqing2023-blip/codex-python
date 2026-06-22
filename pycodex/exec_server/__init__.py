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


CODEX_EXEC_SERVER_URL_ENV_VAR = "CODEX_EXEC_SERVER_URL"
LOCAL_ENVIRONMENT_ID = "local"
REMOTE_ENVIRONMENT_ID = "remote"
CODEX_FS_HELPER_ARG1 = "--codex-run-as-fs-helper"
DEFAULT_LISTEN_URL = "ws://127.0.0.1:0"

INITIALIZE_METHOD = "initialize"
INITIALIZED_METHOD = "initialized"
EXEC_METHOD = "process/start"
EXEC_READ_METHOD = "process/read"
EXEC_WRITE_METHOD = "process/write"
EXEC_TERMINATE_METHOD = "process/terminate"
EXEC_OUTPUT_DELTA_METHOD = "process/output"
EXEC_EXITED_METHOD = "process/exited"
EXEC_CLOSED_METHOD = "process/closed"
FS_READ_FILE_METHOD = "fs/readFile"
FS_WRITE_FILE_METHOD = "fs/writeFile"
FS_CREATE_DIRECTORY_METHOD = "fs/createDirectory"
FS_GET_METADATA_METHOD = "fs/getMetadata"
FS_READ_DIRECTORY_METHOD = "fs/readDirectory"
FS_REMOVE_METHOD = "fs/remove"
FS_COPY_METHOD = "fs/copy"
HTTP_REQUEST_METHOD = "http/request"
HTTP_REQUEST_BODY_DELTA_METHOD = "http/request/bodyDelta"
CHANNEL_CAPACITY = 128
STDIO_TERMINATION_GRACE_PERIOD = 2.0
ENVIRONMENT_CLIENT_NAME = "codex-environment"


class ExecServerError(Exception):
    def __init__(self, message: str, kind: str | None = None, **attrs: Any) -> None:
        self.message = message
        self.kind = kind
        for key, value in attrs.items():
            setattr(self, key, value)
        super().__init__(str(self))

    @classmethod
    def protocol(cls, message: str) -> "ExecServerError":
        return cls(message, "protocol")

    @classmethod
    def environment_registry_config(cls, message: str) -> "ExecServerError":
        return cls(message, "environment_registry_config")

    @classmethod
    def environment_registry_auth(cls, message: str) -> "ExecServerError":
        return cls(message, "environment_registry_auth")

    @classmethod
    def environment_registry_http(
        cls,
        status: int,
        code: str | None,
        message: str,
    ) -> "ExecServerError":
        return cls(message, "environment_registry_http", status=status, code=code)

    @classmethod
    def http_request(cls, message: str) -> "ExecServerError":
        return cls(message, "http_request")

    @classmethod
    def websocket_connect_timeout(cls, url: str, timeout: int | float) -> "ExecServerError":
        timeout_display = _rust_duration_debug(timeout)
        return cls(
            f"timed out connecting to exec-server websocket `{url}` after {timeout_display}",
            "websocket_connect_timeout",
            url=url,
            timeout=timeout,
        )

    @classmethod
    def websocket_connect(cls, url: str, source: BaseException) -> "ExecServerError":
        return cls(
            f"failed to connect to exec-server websocket `{url}`: {source}",
            "websocket_connect",
            url=url,
            source=source,
        )

    def __str__(self) -> str:
        if self.kind == "protocol":
            return f"exec-server protocol error: {self.message}"
        return self.message


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


class RpcCallError(Exception):
    kind: str

    @classmethod
    def closed(cls) -> "RpcCallError":
        return cls("closed")

    @classmethod
    def json(cls, message: Any) -> "RpcCallError":
        return cls("json", str(message))

    @classmethod
    def server(cls, error: JSONRPCErrorError) -> "RpcCallError":
        err = cls("server", error.message)
        err.error = error
        return err

    def __init__(self, kind: str, message: str | None = None) -> None:
        self.kind = kind
        self.message = message
        super().__init__(message or kind)


@dataclass(frozen=True)
class RpcClientEvent:
    kind: str
    notification: JSONRPCNotification | None = None
    reason: str | None = None

    @classmethod
    def notification_event(cls, notification: JSONRPCNotification) -> "RpcClientEvent":
        return cls("notification", notification=notification)

    @classmethod
    def disconnected(cls, reason: str | None = None) -> "RpcClientEvent":
        return cls("disconnected", reason=reason)


@dataclass(frozen=True)
class JsonRpcConnectionEvent:
    kind: str
    message: JSONRPCMessage | None = None
    reason: str | None = None

    @classmethod
    def message_event(cls, message: JSONRPCMessage) -> "JsonRpcConnectionEvent":
        return cls("message", message=message)

    @classmethod
    def malformed_message(cls, reason: str) -> "JsonRpcConnectionEvent":
        return cls("malformed", reason=reason)

    @classmethod
    def disconnected(cls, reason: str | None = None) -> "JsonRpcConnectionEvent":
        return cls("disconnected", reason=reason)


@dataclass(frozen=True)
class JsonRpcTransport:
    kind: str = "plain"
    stdio_transport: "StdioTransport | None" = None

    @classmethod
    def plain(cls) -> "JsonRpcTransport":
        return cls("plain")

    @classmethod
    def from_child_process(cls, child_process: Any) -> "JsonRpcTransport":
        return cls("stdio", StdioTransport.spawn(child_process))

    def terminate(self) -> None:
        if self.stdio_transport is not None:
            self.stdio_transport.terminate()


class StdioTransport:
    def __init__(self, handle: "StdioTransportHandle") -> None:
        self.handle = handle

    @classmethod
    def spawn(
        cls,
        child_process: Any,
        grace_period: float = STDIO_TERMINATION_GRACE_PERIOD,
    ) -> "StdioTransport":
        return cls(StdioTransportHandle.spawn(child_process, grace_period))

    def terminate(self) -> None:
        self.handle.terminate()


class StdioTransportHandle:
    def __init__(self, terminate_event: asyncio.Event, task: "asyncio.Task[Any] | None") -> None:
        self.terminate_event = terminate_event
        self.task = task
        self.terminate_requested = False

    @classmethod
    def spawn(cls, child_process: Any, grace_period: float) -> "StdioTransportHandle":
        terminate_event = asyncio.Event()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            task = None
        else:
            task = loop.create_task(_stdio_child_supervisor(child_process, terminate_event, grace_period))
        return cls(terminate_event, task)

    def terminate(self) -> None:
        if self.terminate_requested:
            return
        self.terminate_requested = True
        self.terminate_event.set()


class JsonRpcConnection:
    def __init__(
        self,
        outgoing_tx: "asyncio.Queue[JSONRPCMessage]",
        incoming_rx: "asyncio.Queue[JsonRpcConnectionEvent]",
        disconnected: asyncio.Event,
        task_handles: list[asyncio.Task[Any]],
        transport: JsonRpcTransport | None = None,
    ) -> None:
        self.outgoing_tx = outgoing_tx
        self.incoming_rx = incoming_rx
        self.disconnected = disconnected
        self.task_handles = task_handles
        self.transport = transport or JsonRpcTransport.plain()

    @classmethod
    def from_stdio(cls, reader: Any, writer: Any, connection_label: str) -> "JsonRpcConnection":
        outgoing_tx: asyncio.Queue[JSONRPCMessage] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
        incoming_rx: asyncio.Queue[JsonRpcConnectionEvent] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
        disconnected = asyncio.Event()

        reader_task = asyncio.create_task(
            _stdio_connection_reader(reader, incoming_rx, disconnected, connection_label)
        )
        writer_task = asyncio.create_task(
            _stdio_connection_writer(writer, outgoing_tx, incoming_rx, disconnected, connection_label)
        )
        return cls(outgoing_tx, incoming_rx, disconnected, [reader_task, writer_task])

    @classmethod
    def from_websocket_stream(
        cls,
        websocket: Any,
        connection_label: str,
        ping_interval: float | None = None,
    ) -> "JsonRpcConnection":
        outgoing_tx: asyncio.Queue[JSONRPCMessage] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
        incoming_rx: asyncio.Queue[JsonRpcConnectionEvent] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
        disconnected = asyncio.Event()
        websocket_task = asyncio.create_task(
            _websocket_connection_loop(websocket, outgoing_tx, incoming_rx, disconnected, connection_label, ping_interval)
        )
        return cls(outgoing_tx, incoming_rx, disconnected, [websocket_task])

    @classmethod
    def from_websocket(cls, websocket: Any, connection_label: str) -> "JsonRpcConnection":
        return cls.from_websocket_stream(websocket, connection_label, None)

    def with_child_process(self, child_process: Any) -> "JsonRpcConnection":
        self.transport = JsonRpcTransport.from_child_process(child_process)
        return self

    async def close(self) -> None:
        self.transport.terminate()
        for task in self.task_handles:
            task.cancel()
        if self.task_handles:
            await asyncio.gather(*self.task_handles, return_exceptions=True)


@dataclass(frozen=True)
class JsonRpcWebSocketMessage:
    kind: str
    data: str | bytes | None = None

    @classmethod
    def text(cls, value: str) -> "JsonRpcWebSocketMessage":
        return cls("text", value)

    @classmethod
    def binary(cls, value: bytes) -> "JsonRpcWebSocketMessage":
        return cls("binary", bytes(value))

    @classmethod
    def close(cls) -> "JsonRpcWebSocketMessage":
        return cls("close")

    @classmethod
    def ping(cls) -> "JsonRpcWebSocketMessage":
        return cls("ping", b"")

    @classmethod
    def pong(cls, value: bytes = b"") -> "JsonRpcWebSocketMessage":
        return cls("pong", bytes(value))

    def parse_jsonrpc_frame(self) -> "JsonRpcWebSocketFrame":
        if self.kind == "text":
            if not isinstance(self.data, str):
                raise ValueError("websocket text frame must contain text")
            return JsonRpcWebSocketFrame.message(JSONRPCMessage.from_mapping(json.loads(self.data)))
        if self.kind == "binary":
            if not isinstance(self.data, bytes):
                raise ValueError("websocket binary frame must contain bytes")
            return JsonRpcWebSocketFrame.message(JSONRPCMessage.from_mapping(json.loads(self.data.decode("utf-8"))))
        if self.kind == "close":
            return JsonRpcWebSocketFrame.close()
        if self.kind in {"ping", "pong"}:
            return JsonRpcWebSocketFrame.ignore()
        raise ValueError(f"unknown websocket frame kind: {self.kind}")


@dataclass(frozen=True)
class JsonRpcWebSocketFrame:
    kind: str
    message: JSONRPCMessage | None = None

    @classmethod
    def message(cls, message: JSONRPCMessage) -> "JsonRpcWebSocketFrame":
        return cls("message", message)

    @classmethod
    def close(cls) -> "JsonRpcWebSocketFrame":
        return cls("close")

    @classmethod
    def ignore(cls) -> "JsonRpcWebSocketFrame":
        return cls("ignore")


RELAY_MESSAGE_FRAME_VERSION = 1


class RelayFrameBodyKind(str, Enum):
    DATA = "data"
    ACK = "ack"
    RESUME = "resume"
    RESET = "reset"
    HEARTBEAT = "heartbeat"


@dataclass(frozen=True)
class RelayData:
    seq: int
    segment_index: int = 0
    segment_count: int = 1
    payload: bytes = b""


@dataclass(frozen=True)
class RelayResume:
    next_seq: int = 0


@dataclass(frozen=True)
class RelayReset:
    reason: str


@dataclass(frozen=True)
class RelayAck:
    pass


@dataclass(frozen=True)
class RelayHeartbeat:
    pass


@dataclass(frozen=True)
class RelayMessageFrame:
    version: int
    stream_id: str
    ack: int = 0
    ack_bits: int = 0
    body_kind: RelayFrameBodyKind | str | None = None
    body: RelayData | RelayResume | RelayReset | RelayAck | RelayHeartbeat | None = None

    def __post_init__(self) -> None:
        if self.body_kind is not None and not isinstance(self.body_kind, RelayFrameBodyKind):
            object.__setattr__(self, "body_kind", RelayFrameBodyKind(self.body_kind))

    @classmethod
    def data(cls, stream_id: str, seq: int, payload: bytes) -> "RelayMessageFrame":
        return cls(
            version=RELAY_MESSAGE_FRAME_VERSION,
            stream_id=stream_id,
            body_kind=RelayFrameBodyKind.DATA,
            body=RelayData(seq=seq, payload=bytes(payload)),
        )

    @classmethod
    def resume(cls, stream_id: str) -> "RelayMessageFrame":
        return cls(
            version=RELAY_MESSAGE_FRAME_VERSION,
            stream_id=stream_id,
            body_kind=RelayFrameBodyKind.RESUME,
            body=RelayResume(next_seq=0),
        )

    @classmethod
    def reset(cls, stream_id: str, reason: str) -> "RelayMessageFrame":
        return cls(
            version=RELAY_MESSAGE_FRAME_VERSION,
            stream_id=stream_id,
            body_kind=RelayFrameBodyKind.RESET,
            body=RelayReset(reason),
        )

    def validate(self) -> RelayFrameBodyKind:
        if self.version != RELAY_MESSAGE_FRAME_VERSION:
            raise ExecServerError.protocol(f"unsupported relay message frame version {self.version}")
        if not self.stream_id.strip():
            raise ExecServerError.protocol("relay message frame is missing stream_id")
        if self.body_kind is RelayFrameBodyKind.DATA and isinstance(self.body, RelayData):
            if self.body.segment_index != 0 or self.body.segment_count != 1 or not self.body.payload:
                raise ExecServerError.protocol("relay data message frame is missing required fields")
            return RelayFrameBodyKind.DATA
        if self.body_kind is RelayFrameBodyKind.ACK and isinstance(self.body, RelayAck):
            return RelayFrameBodyKind.ACK
        if self.body_kind is RelayFrameBodyKind.RESUME and isinstance(self.body, RelayResume):
            return RelayFrameBodyKind.RESUME
        if self.body_kind is RelayFrameBodyKind.RESET and isinstance(self.body, RelayReset):
            if not self.body.reason:
                raise ExecServerError.protocol("relay reset message frame is missing reason")
            return RelayFrameBodyKind.RESET
        if self.body_kind is RelayFrameBodyKind.HEARTBEAT and isinstance(self.body, RelayHeartbeat):
            return RelayFrameBodyKind.HEARTBEAT
        raise ExecServerError.protocol("relay message frame is missing body")

    def into_jsonrpc_message(self) -> JSONRPCMessage:
        kind = self.validate()
        if kind is not RelayFrameBodyKind.DATA:
            raise ExecServerError.protocol("expected relay data message frame")
        assert isinstance(self.body, RelayData)
        try:
            payload = json.loads(self.body.payload.decode("utf-8"))
            return JSONRPCMessage.from_mapping(payload)
        except Exception as exc:
            raise ExecServerError(str(exc), "json") from exc

    def into_reset_reason(self) -> str | None:
        if self.body_kind is RelayFrameBodyKind.RESET and isinstance(self.body, RelayReset) and self.body.reason:
            return self.body.reason
        return None


def jsonrpc_payload(message: JSONRPCMessage) -> bytes:
    return json.dumps(message.to_mapping(), separators=(",", ":")).encode("utf-8")


def encode_relay_message_frame(frame: RelayMessageFrame) -> bytes:
    chunks: list[bytes] = []
    if frame.version:
        chunks.append(_protobuf_key(1, 0) + _protobuf_varint(frame.version))
    if frame.stream_id:
        chunks.append(_protobuf_bytes_field(2, frame.stream_id.encode("utf-8")))
    if frame.ack:
        chunks.append(_protobuf_key(3, 0) + _protobuf_varint(frame.ack))
    if frame.ack_bits:
        chunks.append(_protobuf_key(4, 0) + _protobuf_varint(frame.ack_bits))
    if frame.body_kind is RelayFrameBodyKind.DATA and isinstance(frame.body, RelayData):
        chunks.append(_protobuf_bytes_field(5, _encode_relay_data(frame.body)))
    elif frame.body_kind is RelayFrameBodyKind.ACK and isinstance(frame.body, RelayAck):
        chunks.append(_protobuf_bytes_field(6, b""))
    elif frame.body_kind is RelayFrameBodyKind.RESUME and isinstance(frame.body, RelayResume):
        chunks.append(_protobuf_bytes_field(7, _encode_relay_resume(frame.body)))
    elif frame.body_kind is RelayFrameBodyKind.RESET and isinstance(frame.body, RelayReset):
        chunks.append(_protobuf_bytes_field(8, _encode_relay_reset(frame.body)))
    elif frame.body_kind is RelayFrameBodyKind.HEARTBEAT and isinstance(frame.body, RelayHeartbeat):
        chunks.append(_protobuf_bytes_field(9, b""))
    return b"".join(chunks)


def decode_relay_message_frame(payload: bytes) -> RelayMessageFrame:
    try:
        fields = _protobuf_fields(payload)
        version = 0
        stream_id = ""
        ack = 0
        ack_bits = 0
        body_kind: RelayFrameBodyKind | None = None
        body: RelayData | RelayResume | RelayReset | RelayAck | RelayHeartbeat | None = None
        for field_number, wire_type, value in fields:
            if field_number == 1 and wire_type == 0:
                version = int(value)
            elif field_number == 2 and wire_type == 2:
                stream_id = bytes(value).decode("utf-8")
            elif field_number == 3 and wire_type == 0:
                ack = int(value)
            elif field_number == 4 and wire_type == 0:
                ack_bits = int(value)
            elif field_number == 5 and wire_type == 2:
                body_kind = RelayFrameBodyKind.DATA
                body = _decode_relay_data(bytes(value))
            elif field_number == 6 and wire_type == 2:
                body_kind = RelayFrameBodyKind.ACK
                body = RelayAck()
            elif field_number == 7 and wire_type == 2:
                body_kind = RelayFrameBodyKind.RESUME
                body = _decode_relay_resume(bytes(value))
            elif field_number == 8 and wire_type == 2:
                body_kind = RelayFrameBodyKind.RESET
                body = _decode_relay_reset(bytes(value))
            elif field_number == 9 and wire_type == 2:
                body_kind = RelayFrameBodyKind.HEARTBEAT
                body = RelayHeartbeat()
        return RelayMessageFrame(version, stream_id, ack, ack_bits, body_kind, body)
    except ExecServerError:
        raise
    except Exception as exc:
        raise ExecServerError.protocol(f"invalid relay message frame: {exc}") from exc


def _encode_relay_data(data: RelayData) -> bytes:
    chunks: list[bytes] = []
    if data.seq:
        chunks.append(_protobuf_key(1, 0) + _protobuf_varint(data.seq))
    if data.segment_index:
        chunks.append(_protobuf_key(2, 0) + _protobuf_varint(data.segment_index))
    if data.segment_count:
        chunks.append(_protobuf_key(3, 0) + _protobuf_varint(data.segment_count))
    if data.payload:
        chunks.append(_protobuf_bytes_field(4, data.payload))
    return b"".join(chunks)


def _decode_relay_data(payload: bytes) -> RelayData:
    seq = 0
    segment_index = 0
    segment_count = 0
    data_payload = b""
    for field_number, wire_type, value in _protobuf_fields(payload):
        if field_number == 1 and wire_type == 0:
            seq = int(value)
        elif field_number == 2 and wire_type == 0:
            segment_index = int(value)
        elif field_number == 3 and wire_type == 0:
            segment_count = int(value)
        elif field_number == 4 and wire_type == 2:
            data_payload = bytes(value)
    return RelayData(seq=seq, segment_index=segment_index, segment_count=segment_count, payload=data_payload)


def _encode_relay_resume(resume: RelayResume) -> bytes:
    if resume.next_seq:
        return _protobuf_key(1, 0) + _protobuf_varint(resume.next_seq)
    return b""


def _decode_relay_resume(payload: bytes) -> RelayResume:
    next_seq = 0
    for field_number, wire_type, value in _protobuf_fields(payload):
        if field_number == 1 and wire_type == 0:
            next_seq = int(value)
    return RelayResume(next_seq)


def _encode_relay_reset(reset: RelayReset) -> bytes:
    if reset.reason:
        return _protobuf_bytes_field(1, reset.reason.encode("utf-8"))
    return b""


def _decode_relay_reset(payload: bytes) -> RelayReset:
    reason = ""
    for field_number, wire_type, value in _protobuf_fields(payload):
        if field_number == 1 and wire_type == 2:
            reason = bytes(value).decode("utf-8")
    return RelayReset(reason)


def _protobuf_key(field_number: int, wire_type: int) -> bytes:
    return _protobuf_varint((field_number << 3) | wire_type)


def _protobuf_bytes_field(field_number: int, value: bytes) -> bytes:
    return _protobuf_key(field_number, 2) + _protobuf_varint(len(value)) + bytes(value)


def _protobuf_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("protobuf varint cannot be negative")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _protobuf_read_varint(payload: bytes, index: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while index < len(payload):
        byte = payload[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, index
        shift += 7
        if shift >= 64:
            raise ValueError("varint is too long")
    raise ValueError("unexpected EOF while reading varint")


def _protobuf_fields(payload: bytes) -> list[tuple[int, int, int | bytes]]:
    fields: list[tuple[int, int, int | bytes]] = []
    index = 0
    while index < len(payload):
        key, index = _protobuf_read_varint(payload, index)
        field_number = key >> 3
        wire_type = key & 0x07
        if field_number == 0:
            raise ValueError("field number 0 is invalid")
        if wire_type == 0:
            value, index = _protobuf_read_varint(payload, index)
            fields.append((field_number, wire_type, value))
        elif wire_type == 2:
            length, index = _protobuf_read_varint(payload, index)
            end = index + length
            if end > len(payload):
                raise ValueError("length-delimited field exceeds payload")
            fields.append((field_number, wire_type, payload[index:end]))
            index = end
        else:
            raise ValueError(f"unsupported wire type {wire_type}")
    return fields


def harness_connection_from_websocket(
    websocket: Any,
    connection_label: str,
    *,
    stream_id: str | None = None,
) -> JsonRpcConnection:
    relay_stream_id = stream_id or str(uuid.uuid4())
    outgoing_tx: asyncio.Queue[JSONRPCMessage] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
    incoming_rx: asyncio.Queue[JsonRpcConnectionEvent] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
    disconnected = asyncio.Event()
    task = asyncio.create_task(
        _relay_harness_connection_loop(websocket, connection_label, relay_stream_id, outgoing_tx, incoming_rx, disconnected)
    )
    return JsonRpcConnection(outgoing_tx, incoming_rx, disconnected, [task])


async def _relay_harness_connection_loop(
    websocket: Any,
    connection_label: str,
    stream_id: str,
    outgoing_tx: asyncio.Queue[JSONRPCMessage],
    incoming_rx: asyncio.Queue[JsonRpcConnectionEvent],
    disconnected: asyncio.Event,
) -> None:
    try:
        await _websocket_send(
            websocket,
            JsonRpcWebSocketMessage.binary(encode_relay_message_frame(RelayMessageFrame.resume(stream_id))),
        )
    except Exception:
        disconnected.set()
        return

    next_seq = 0
    pending_recv: asyncio.Task[Any] | None = None
    pending_outgoing: asyncio.Task[Any] | None = None
    try:
        while True:
            if pending_recv is None:
                pending_recv = asyncio.create_task(_websocket_recv(websocket))
            if pending_outgoing is None:
                pending_outgoing = asyncio.create_task(outgoing_tx.get())
            done, _pending = await asyncio.wait(
                {pending_recv, pending_outgoing},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if pending_outgoing in done:
                message = pending_outgoing.result()
                pending_outgoing = None
                payload = jsonrpc_payload(message)
                frame = RelayMessageFrame.data(stream_id, next_seq, payload)
                next_seq = (next_seq + 1) % (2**32)
                try:
                    await _websocket_send(websocket, JsonRpcWebSocketMessage.binary(encode_relay_message_frame(frame)))
                except Exception:
                    disconnected.set()
                    break
                continue

            if pending_recv in done:
                incoming = pending_recv.result()
                pending_recv = None
                if incoming is None or incoming.kind == "close":
                    disconnected.set()
                    await incoming_rx.put(JsonRpcConnectionEvent.disconnected(None))
                    break
                if incoming.kind in {"ping", "pong"}:
                    continue
                if incoming.kind == "text":
                    await incoming_rx.put(
                        JsonRpcConnectionEvent.malformed_message(
                            "relay exec-server transport expects binary protobuf frames"
                        )
                    )
                    continue
                if incoming.kind != "binary" or not isinstance(incoming.data, bytes):
                    continue
                try:
                    frame = decode_relay_message_frame(incoming.data)
                except ExecServerError as exc:
                    await incoming_rx.put(
                        JsonRpcConnectionEvent.malformed_message(
                            f"failed to parse relay message frame from {connection_label}: {exc}"
                        )
                    )
                    continue
                if frame.stream_id != stream_id:
                    continue
                try:
                    kind = frame.validate()
                except ExecServerError as exc:
                    await incoming_rx.put(JsonRpcConnectionEvent.malformed_message(str(exc)))
                    continue
                if kind is RelayFrameBodyKind.DATA:
                    try:
                        await incoming_rx.put(JsonRpcConnectionEvent.message_event(frame.into_jsonrpc_message()))
                    except ExecServerError as exc:
                        await incoming_rx.put(JsonRpcConnectionEvent.malformed_message(str(exc)))
                elif kind is RelayFrameBodyKind.RESET:
                    disconnected.set()
                    await incoming_rx.put(JsonRpcConnectionEvent.disconnected(frame.into_reset_reason()))
                    break
                else:
                    continue
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        disconnected.set()
        await incoming_rx.put(
            JsonRpcConnectionEvent.disconnected(
                f"failed to read relay websocket frame from {connection_label}: {exc}"
            )
        )
    finally:
        for task in (pending_recv, pending_outgoing):
            if task is not None and not task.done():
                task.cancel()


@dataclass
class _RelayVirtualStream:
    incoming_tx: asyncio.Queue[JsonRpcConnectionEvent]
    disconnected: asyncio.Event
    writer_task: asyncio.Task[Any]
    processor_task: asyncio.Task[Any]

    async def disconnect(self, reason: str | None) -> None:
        self.disconnected.set()
        await self.incoming_tx.put(JsonRpcConnectionEvent.disconnected(reason))


async def run_multiplexed_environment(websocket: Any, processor: Any) -> None:
    physical_outgoing_tx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
    streams: dict[str, _RelayVirtualStream] = {}
    pending_recv: asyncio.Task[Any] | None = None
    pending_physical: asyncio.Task[Any] | None = None
    try:
        while True:
            if pending_recv is None:
                pending_recv = asyncio.create_task(_websocket_recv(websocket))
            if pending_physical is None:
                pending_physical = asyncio.create_task(physical_outgoing_tx.get())
            done, _pending = await asyncio.wait(
                {pending_recv, pending_physical},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if pending_physical in done:
                encoded = pending_physical.result()
                pending_physical = None
                try:
                    await _websocket_send(websocket, JsonRpcWebSocketMessage.binary(encoded))
                except Exception:
                    break
                continue

            if pending_recv not in done:
                continue
            incoming = pending_recv.result()
            pending_recv = None
            if incoming is None or incoming.kind == "close":
                break
            if incoming.kind in {"ping", "pong"}:
                continue
            if incoming.kind != "binary" or not isinstance(incoming.data, bytes):
                continue
            try:
                frame = decode_relay_message_frame(incoming.data)
                kind = frame.validate()
            except ExecServerError:
                continue

            if kind is RelayFrameBodyKind.DATA:
                stream_id = frame.stream_id
                try:
                    message = frame.into_jsonrpc_message()
                except ExecServerError:
                    continue
                stream = streams.get(stream_id)
                if stream is None:
                    stream = _spawn_virtual_stream(stream_id, processor, physical_outgoing_tx)
                    streams[stream_id] = stream
                try:
                    stream.incoming_tx.put_nowait(JsonRpcConnectionEvent.message_event(message))
                except asyncio.QueueFull:
                    streams.pop(stream_id, None)
                    await stream.disconnect(None)
            elif kind is RelayFrameBodyKind.RESET:
                stream = streams.pop(frame.stream_id, None)
                if stream is not None:
                    await stream.disconnect(frame.into_reset_reason())
            else:
                continue
    finally:
        for task in (pending_recv, pending_physical):
            if task is not None and not task.done():
                task.cancel()
        for stream in list(streams.values()):
            await stream.disconnect(None)


def _spawn_virtual_stream(
    stream_id: str,
    processor: Any,
    physical_outgoing_tx: asyncio.Queue[bytes],
) -> _RelayVirtualStream:
    json_outgoing_tx: asyncio.Queue[JSONRPCMessage] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
    incoming_tx: asyncio.Queue[JsonRpcConnectionEvent] = asyncio.Queue(maxsize=CHANNEL_CAPACITY)
    disconnected = asyncio.Event()

    writer_task = asyncio.create_task(_relay_virtual_stream_writer(stream_id, json_outgoing_tx, physical_outgoing_tx))
    connection = JsonRpcConnection(json_outgoing_tx, incoming_tx, disconnected, [writer_task])
    processor_task = asyncio.create_task(processor.run_connection(connection))
    return _RelayVirtualStream(incoming_tx, disconnected, writer_task, processor_task)


async def _relay_virtual_stream_writer(
    stream_id: str,
    json_outgoing_tx: asyncio.Queue[JSONRPCMessage],
    physical_outgoing_tx: asyncio.Queue[bytes],
) -> None:
    next_seq = 0
    try:
        while True:
            message = await json_outgoing_tx.get()
            payload = jsonrpc_payload(message)
            frame = RelayMessageFrame.data(stream_id, next_seq, payload)
            next_seq = (next_seq + 1) % (2**32)
            await physical_outgoing_tx.put(encode_relay_message_frame(frame))
    except asyncio.CancelledError:
        raise
    except Exception:
        return


@dataclass(frozen=True)
class RpcServerOutboundMessage:
    kind: str
    request_id: RequestId | str | int | None = None
    result: Any | None = None
    error: JSONRPCErrorError | None = None
    notification: JSONRPCNotification | None = None

    @classmethod
    def response(cls, request_id: RequestId | str | int, result: Any) -> "RpcServerOutboundMessage":
        return cls("response", request_id=RequestId.from_value(request_id), result=result)

    @classmethod
    def error_message(
        cls,
        request_id: RequestId | str | int,
        error: JSONRPCErrorError,
    ) -> "RpcServerOutboundMessage":
        return cls("error", request_id=RequestId.from_value(request_id), error=error)

    @classmethod
    def notification_message(cls, notification: JSONRPCNotification) -> "RpcServerOutboundMessage":
        return cls("notification", notification=notification)


def encode_server_message(message: RpcServerOutboundMessage) -> JSONRPCMessage:
    if message.kind == "response":
        if message.request_id is None:
            raise ValueError("response requires request_id")
        return JSONRPCMessage(JSONRPCResponse(id=message.request_id, result=message.result))
    if message.kind == "error":
        if message.request_id is None or message.error is None:
            raise ValueError("error requires request_id and error")
        return JSONRPCMessage(JSONRPCError(id=message.request_id, error=message.error))
    if message.kind == "notification":
        if message.notification is None:
            raise ValueError("notification requires notification")
        return JSONRPCMessage(message.notification)
    raise ValueError(f"unknown RPC outbound message kind: {message.kind}")


class RpcNotificationSender:
    def __init__(self, outgoing_tx: asyncio.Queue[RpcServerOutboundMessage]) -> None:
        self.outgoing_tx = outgoing_tx

    @classmethod
    def new(cls, outgoing_tx: asyncio.Queue[RpcServerOutboundMessage]) -> "RpcNotificationSender":
        return cls(outgoing_tx)

    async def response(self, request_id: RequestId | str | int, result: Any) -> None | JSONRPCErrorError:
        try:
            self.outgoing_tx.put_nowait(RpcServerOutboundMessage.response(request_id, result))
        except asyncio.QueueFull:
            return internal_error("RPC connection closed while sending response")
        return None

    async def notify(self, method: str, params: Any) -> None | JSONRPCErrorError:
        try:
            self.outgoing_tx.put_nowait(
                RpcServerOutboundMessage.notification_message(JSONRPCNotification(method=method, params=params))
            )
        except asyncio.QueueFull:
            return internal_error("RPC connection closed while sending notification")
        return None


class RpcRouter:
    def __init__(self) -> None:
        self.request_routes: dict[str, Any] = {}
        self.notification_routes: dict[str, Any] = {}

    @classmethod
    def new(cls) -> "RpcRouter":
        return cls()

    def request(self, method: str, handler: Any, decoder: Any | None = None, encoder: Any | None = None) -> None:
        async def route(state: Any, request: JSONRPCRequest) -> RpcServerOutboundMessage:
            params_or_error = decode_request_params(request.params, decoder)
            if isinstance(params_or_error, JSONRPCErrorError):
                return RpcServerOutboundMessage.error_message(request.id, params_or_error)
            try:
                result = await _maybe_await(handler(state, params_or_error))
            except Exception as exc:
                return RpcServerOutboundMessage.error_message(request.id, internal_error(exc))
            if isinstance(result, JSONRPCErrorError):
                return RpcServerOutboundMessage.error_message(request.id, result)
            if encoder is not None:
                try:
                    result = encoder(result)
                except Exception as exc:
                    return RpcServerOutboundMessage.error_message(request.id, internal_error(exc))
            return RpcServerOutboundMessage.response(request.id, result)

        self.request_routes[method] = route

    def request_with_id(self, method: str, handler: Any, decoder: Any | None = None) -> None:
        async def route(state: Any, request: JSONRPCRequest) -> RpcServerOutboundMessage | None:
            params_or_error = decode_request_params(request.params, decoder)
            if isinstance(params_or_error, JSONRPCErrorError):
                return RpcServerOutboundMessage.error_message(request.id, params_or_error)
            try:
                result = await _maybe_await(handler(state, request.id, params_or_error))
            except Exception as exc:
                return RpcServerOutboundMessage.error_message(request.id, internal_error(exc))
            if isinstance(result, JSONRPCErrorError):
                return RpcServerOutboundMessage.error_message(request.id, result)
            return None

        self.request_routes[method] = route

    def notification(self, method: str, handler: Any, decoder: Any | None = None) -> None:
        async def route(state: Any, notification: JSONRPCNotification) -> None | str:
            params_or_error = decode_notification_params(notification.params, decoder)
            if isinstance(params_or_error, str):
                return params_or_error
            try:
                result = await _maybe_await(handler(state, params_or_error))
            except Exception as exc:
                return str(exc)
            if isinstance(result, JSONRPCErrorError):
                return result.message
            if isinstance(result, str):
                return result
            return None

        self.notification_routes[method] = route

    def request_route(self, method: str) -> Any | None:
        return self.request_routes.get(method)

    def notification_route(self, method: str) -> Any | None:
        return self.notification_routes.get(method)


def build_router() -> RpcRouter:
    router = RpcRouter.new()
    router.notification(INITIALIZED_METHOD, lambda handler, _params: handler.initialized())
    router.request(
        INITIALIZE_METHOD,
        lambda handler, params: handler.initialize(params),
        decoder=decode_initialize_params,
        encoder=encode_initialize_response,
    )
    router.request_with_id(
        HTTP_REQUEST_METHOD,
        lambda handler, request_id, params: handler.http_request(request_id, params),
        decoder=decode_http_request_params,
    )
    router.request(
        EXEC_METHOD,
        lambda handler, params: handler.exec(params),
        decoder=decode_exec_params,
        encoder=encode_exec_response,
    )
    router.request(
        EXEC_READ_METHOD,
        lambda handler, params: handler.exec_read(params),
        decoder=decode_read_params,
        encoder=encode_read_response,
    )
    router.request(
        EXEC_WRITE_METHOD,
        lambda handler, params: handler.exec_write(params),
        decoder=decode_write_params,
        encoder=encode_write_response,
    )
    router.request(
        EXEC_TERMINATE_METHOD,
        lambda handler, params: handler.terminate(params),
        decoder=decode_terminate_params,
        encoder=encode_terminate_response,
    )
    router.request(FS_READ_FILE_METHOD, lambda handler, params: handler.fs_read_file(params))
    router.request(FS_WRITE_FILE_METHOD, lambda handler, params: handler.fs_write_file(params))
    router.request(FS_CREATE_DIRECTORY_METHOD, lambda handler, params: handler.fs_create_directory(params))
    router.request(FS_GET_METADATA_METHOD, lambda handler, params: handler.fs_get_metadata(params))
    router.request(FS_READ_DIRECTORY_METHOD, lambda handler, params: handler.fs_read_directory(params))
    router.request(FS_REMOVE_METHOD, lambda handler, params: handler.fs_remove(params))
    router.request(FS_COPY_METHOD, lambda handler, params: handler.fs_copy(params))
    return router


class RpcClient:
    def __init__(self, outgoing_tx: asyncio.Queue[JSONRPCMessage] | None = None) -> None:
        self.outgoing_tx = outgoing_tx or asyncio.Queue()
        self.events: asyncio.Queue[RpcClientEvent] = asyncio.Queue()
        self.pending: dict[RequestId, asyncio.Future[Any]] = {}
        self.next_request_id = 1
        self.disconnected = False

    @classmethod
    def new_for_tests(cls) -> "RpcClient":
        return cls()

    async def notify(self, method: str, params: Any) -> None:
        if self.disconnected:
            raise RpcCallError.closed()
        await self.outgoing_tx.put(JSONRPCMessage(JSONRPCNotification(method=method, params=params)))

    def is_disconnected(self) -> bool:
        return self.disconnected

    async def call(self, method: str, params: Any) -> Any:
        if self.disconnected:
            raise RpcCallError.closed()
        request_id = RequestId.integer(self.next_request_id)
        self.next_request_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self.pending[request_id] = future
        await self.outgoing_tx.put(
            JSONRPCMessage(JSONRPCRequest(id=request_id, method=method, params=params, trace=None))
        )
        try:
            return await future
        finally:
            self.pending.pop(request_id, None)

    async def receive_server_message(self, message: JSONRPCMessage) -> None:
        await handle_server_message(self.pending, self.events, message)

    async def disconnect(self, reason: str | None = None) -> None:
        self.disconnected = True
        await self.events.put(RpcClientEvent.disconnected(reason))
        await drain_pending(self.pending)

    def pending_request_count(self) -> int:
        return len(self.pending)


def not_found(message: Any) -> JSONRPCErrorError:
    return JSONRPCErrorError(code=-32004, message=str(message), data=None)


def decode_request_params(params: Any | None, decoder: Any | None = None) -> Any | JSONRPCErrorError:
    result = decode_params(params, decoder)
    if isinstance(result, Exception):
        return invalid_params(str(result))
    return result


def decode_notification_params(params: Any | None, decoder: Any | None = None) -> Any | str:
    result = decode_params(params, decoder)
    if isinstance(result, Exception):
        return str(result)
    return result


def decode_params(params: Any | None, decoder: Any | None = None) -> Any | Exception:
    decoder = decoder or (lambda value: value)
    value = None if params is None else params
    try:
        return decoder(value)
    except Exception as original_error:
        if value == {}:
            try:
                return decoder(None)
            except Exception:
                return original_error
        return original_error


async def handle_server_message(
    pending: dict[RequestId, asyncio.Future[Any]],
    event_tx: asyncio.Queue[RpcClientEvent],
    message: JSONRPCMessage,
) -> None:
    value = message.value
    if isinstance(value, JSONRPCResponse):
        future = pending.pop(value.id, None)
        if future is not None and not future.done():
            future.set_result(value.result)
        return
    if isinstance(value, JSONRPCError):
        future = pending.pop(value.id, None)
        if future is not None and not future.done():
            future.set_exception(RpcCallError.server(value.error))
        return
    if isinstance(value, JSONRPCNotification):
        await event_tx.put(RpcClientEvent.notification_event(value))
        return
    if isinstance(value, JSONRPCRequest):
        raise ValueError(f"unexpected JSON-RPC request from remote server: {value.method}")


async def drain_pending(pending: dict[RequestId, asyncio.Future[Any]]) -> None:
    futures = list(pending.values())
    pending.clear()
    for future in futures:
        if not future.done():
            future.set_exception(RpcCallError.closed())


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


DETACHED_SESSION_TTL = 10.0
MAX_RETAINED_OUTPUT_BYTES_PER_PROCESS = 1024 * 1024
LOCAL_PROCESS_EXITED_PROCESS_RETENTION_SECONDS = 30.0


@dataclass
class RetainedOutputChunk:
    seq: int
    stream: "ExecOutputStream"
    chunk: bytes


@dataclass
class LocalRunningProcess:
    output: list[RetainedOutputChunk] = field(default_factory=list)
    next_seq: int = 1
    exit_code: int | None = None
    closed: bool = False
    retained_bytes: int = 0
    tty: bool = False
    pipe_stdin: bool = False
    writer_open: bool = True
    written_chunks: list[bytes] = field(default_factory=list)
    terminate_called: bool = False
    child_process: Any | None = None
    stdin_writer: Any | None = None
    task_handles: list[asyncio.Task[Any]] = field(default_factory=list)
    open_streams: int = 0
    output_event: asyncio.Event = field(default_factory=asyncio.Event)
    events: "ExecProcessEventLog | None" = None
    wake_queue: asyncio.Queue[int] = field(default_factory=asyncio.Queue)

    def record_output(self, stream: "ExecOutputStream", chunk: bytes) -> int:
        seq = self.next_seq
        self.next_seq += 1
        data = bytes(chunk)
        self.retained_bytes += len(data)
        self.output.append(RetainedOutputChunk(seq=seq, stream=stream, chunk=data))
        while self.retained_bytes > MAX_RETAINED_OUTPUT_BYTES_PER_PROCESS and self.output:
            evicted = self.output.pop(0)
            self.retained_bytes = max(0, self.retained_bytes - len(evicted.chunk))
        self.output_event.set()
        _put_latest_nowait(self.wake_queue, seq)
        if self.events is not None:
            self.events.publish(
                ExecProcessEvent.output(
                    ProcessOutputChunk(seq=seq, stream=stream, chunk=ByteChunk(data))
                )
            )
        return seq

    def record_exit(self, exit_code: int) -> int:
        seq = self.next_seq
        self.next_seq += 1
        self.exit_code = exit_code
        self.output_event.set()
        _put_latest_nowait(self.wake_queue, seq)
        if self.events is not None:
            self.events.publish(ExecProcessEvent.exited(seq=seq, exit_code=exit_code))
        return seq

    def mark_closed(self, seq: int | None = None) -> None:
        self.closed = True
        self.output_event.set()
        if seq is None:
            seq = self.next_seq
            self.next_seq += 1
        _put_latest_nowait(self.wake_queue, seq)
        if self.events is not None:
            self.events.publish(ExecProcessEvent.closed(seq=seq))

    def accepts_stdin(self) -> bool:
        return self.tty or self.pipe_stdin

    async def write_stdin(self, chunk: bytes) -> None:
        if not self.writer_open:
            raise BrokenPipeError("failed to write to process stdin")
        if self.stdin_writer is not None:
            self.stdin_writer.write(bytes(chunk))
            drain = getattr(self.stdin_writer, "drain", None)
            if drain is not None:
                await _maybe_await(drain())
            return
        self.written_chunks.append(bytes(chunk))

    def terminate(self) -> None:
        self.terminate_called = True
        if self.child_process is not None:
            _terminate_process_tree(self.child_process)


class LocalProcessStarting:
    pass


def _put_latest_nowait(queue: asyncio.Queue[int], value: int) -> None:
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    try:
        queue.put_nowait(value)
    except asyncio.QueueFull:
        pass


class LocalProcess:
    def __init__(self, notifications: RpcNotificationSender | None, spawn_process: Any | None = None) -> None:
        self.notifications = notifications
        self.shutdown_called = False
        self.processes: dict[ProcessId, LocalRunningProcess | LocalProcessStarting] = {}
        self.spawn_process = spawn_process

    @classmethod
    def new(cls, notifications: RpcNotificationSender | None) -> "LocalProcess":
        return cls(notifications)

    async def shutdown(self) -> None:
        self.shutdown_called = True
        running = [process for process in self.processes.values() if isinstance(process, LocalRunningProcess)]
        self.processes.clear()
        for process in running:
            process.terminate()
        for process in running:
            for task in process.task_handles:
                task.cancel()
            if process.task_handles:
                await asyncio.gather(*process.task_handles, return_exceptions=True)

    def set_notification_sender(self, notifications: RpcNotificationSender | None) -> None:
        self.notifications = notifications

    def insert_running_process_for_tests(
        self,
        process_id: ProcessId | str,
        process: LocalRunningProcess | None = None,
    ) -> LocalRunningProcess:
        process_id = ProcessId.new(process_id) if isinstance(process_id, str) else process_id
        process = process or LocalRunningProcess()
        self.processes[process_id] = process
        return process

    def insert_starting_process_for_tests(self, process_id: ProcessId | str) -> None:
        process_id = ProcessId.new(process_id) if isinstance(process_id, str) else process_id
        self.processes[process_id] = LocalProcessStarting()

    async def exec(self, params: ExecParams) -> ExecResponse | JSONRPCErrorError:
        return await self.start_process(params)

    async def start_process(self, params: ExecParams) -> ExecResponse | JSONRPCErrorError:
        process_id = params.process_id
        if not params.argv:
            return invalid_params("argv must not be empty")
        if process_id in self.processes:
            return invalid_request(f"process {process_id} already exists")
        self.processes[process_id] = LocalProcessStarting()
        try:
            if self.spawn_process is None:
                spawned = await _spawn_local_running_process(params, child_env(params), self)
            else:
                spawned = await _maybe_await(self.spawn_process(params, child_env(params)))
        except Exception as exc:
            if isinstance(self.processes.get(process_id), LocalProcessStarting):
                self.processes.pop(process_id, None)
            return internal_error(exc)
        if isinstance(spawned, LocalRunningProcess):
            process = spawned
        else:
            process = LocalRunningProcess(tty=params.tty, pipe_stdin=params.pipe_stdin)
        process.tty = params.tty
        process.pipe_stdin = params.pipe_stdin
        if process.events is None:
            process.events = ExecProcessEventLog.new(256, MAX_RETAINED_OUTPUT_BYTES_PER_PROCESS)
        self.processes[process_id] = process
        return ExecResponse(process_id=process_id)

    async def start(self, params: ExecParams) -> StartedExecProcess | ExecServerError:
        response = await self.start_process(params)
        if isinstance(response, JSONRPCErrorError):
            return ExecServerError(f"exec-server rejected request ({response.code}): {response.message}", "server")
        process = self.processes.get(response.process_id)
        if not isinstance(process, LocalRunningProcess):
            return ExecServerError.protocol(f"process id {response.process_id} is starting")
        return StartedExecProcess(process=LocalExecProcess(response.process_id, self, process))

    async def exec_read(self, params: ReadParams) -> ReadResponse:
        process = self.processes.get(params.process_id)
        if process is None:
            return invalid_request(f"unknown process id {params.process_id}")
        if isinstance(process, LocalProcessStarting):
            return invalid_request(f"process id {params.process_id} is starting")
        deadline = time.monotonic() + ((params.wait_ms or 0) / 1000)
        after_seq = params.after_seq if params.after_seq is not None else 0
        while True:
            response = _local_process_read_response(process, params)
            has_new_terminal_event = response.exited and after_seq < max(0, response.next_seq - 1)
            if response.chunks or response.closed or has_new_terminal_event or time.monotonic() >= deadline:
                return response
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return response
            process.output_event.clear()
            try:
                await asyncio.wait_for(process.output_event.wait(), timeout=remaining)
            except TimeoutError:
                return _local_process_read_response(process, params)

    async def exec_write(self, params: WriteParams) -> WriteResponse:
        process = self.processes.get(params.process_id)
        if process is None:
            return WriteResponse(status=WriteStatus.UNKNOWN_PROCESS)
        if isinstance(process, LocalProcessStarting):
            return WriteResponse(status=WriteStatus.STARTING)
        if not process.accepts_stdin():
            return WriteResponse(status=WriteStatus.STDIN_CLOSED)
        try:
            await process.write_stdin(params.chunk.into_inner())
        except BrokenPipeError as exc:
            return internal_error(exc)
        return WriteResponse(status=WriteStatus.ACCEPTED)

    async def terminate_process(self, params: TerminateParams) -> TerminateResponse:
        process = self.processes.get(params.process_id)
        if process is None or isinstance(process, LocalProcessStarting):
            return TerminateResponse(running=False)
        if process.exit_code is not None:
            return TerminateResponse(running=False)
        process.terminate()
        return TerminateResponse(running=True)


def _local_process_read_response(process: LocalRunningProcess, params: ReadParams) -> ReadResponse:
    after_seq = params.after_seq if params.after_seq is not None else 0
    max_bytes = params.max_bytes if params.max_bytes is not None else sys.maxsize
    chunks: list[ProcessOutputChunk] = []
    total_bytes = 0
    next_seq = process.next_seq
    for retained in (chunk for chunk in process.output if chunk.seq > after_seq):
        chunk_len = len(retained.chunk)
        if chunks and total_bytes + chunk_len > max_bytes:
            break
        total_bytes += chunk_len
        chunks.append(
            ProcessOutputChunk(
                seq=retained.seq,
                stream=retained.stream,
                chunk=ByteChunk(retained.chunk),
            )
        )
        next_seq = retained.seq + 1
        if total_bytes >= max_bytes:
            break
    return ReadResponse(
        chunks=chunks,
        next_seq=next_seq,
        exited=process.exit_code is not None,
        exit_code=process.exit_code,
        closed=process.closed,
        failure=None,
    )


async def _spawn_local_running_process(
    params: ExecParams,
    env: dict[str, str],
    backend: LocalProcess,
) -> LocalRunningProcess:
    if params.tty:
        return await _spawn_local_pty_process(params, env, backend)
    program, *args = params.argv
    command_args = [program, *args]
    kwargs: dict[str, Any] = {
        "cwd": params.cwd,
        "env": env,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "stdin": asyncio.subprocess.PIPE if params.pipe_stdin else asyncio.subprocess.DEVNULL,
    }
    if os.name == "posix":
        kwargs["process_group"] = 0
    if params.arg0 is not None:
        command_args = [params.arg0, *args]
        kwargs["executable"] = program
    child = await asyncio.create_subprocess_exec(*command_args, **kwargs)
    child_process = _LocalPipeChildProcess(child)
    process = LocalRunningProcess(
        tty=False,
        pipe_stdin=params.pipe_stdin,
        child_process=child_process,
        stdin_writer=child.stdin if params.pipe_stdin else None,
        open_streams=2,
    )
    process.task_handles.extend(
        [
            asyncio.create_task(
                _local_process_stream_output(
                    backend,
                    params.process_id,
                    process,
                    ExecOutputStream.STDOUT,
                    child.stdout,
                )
            ),
            asyncio.create_task(
                _local_process_stream_output(
                    backend,
                    params.process_id,
                    process,
                    ExecOutputStream.STDERR,
                    child.stderr,
                )
            ),
            asyncio.create_task(_local_process_watch_exit(backend, params.process_id, process, child_process)),
        ]
    )
    return process


class _EmptyAsyncReader:
    async def read(self, _size: int = -1) -> bytes:
        return b""


class _PtyStdinWriter:
    def __init__(self, fd: int) -> None:
        self._fd = fd

    def write(self, chunk: bytes) -> None:
        try:
            os.write(self._fd, bytes(chunk))
        except OSError as exc:
            raise BrokenPipeError("failed to write to process stdin") from exc

    async def drain(self) -> None:
        return None


class _LocalPipeChildProcess:
    def __init__(self, child: Any) -> None:
        self._child = child

    async def wait(self) -> int:
        result = await _maybe_await(self._child.wait())
        return int(result if result is not None else -1)

    def terminate(self) -> None:
        if _terminate_child_process_group(self._child, 15):
            return
        self._child.terminate()

    def kill(self) -> None:
        if _terminate_child_process_group(self._child, 9):
            return
        self._child.kill()


class _LocalPtyChildProcess:
    def __init__(self, child: Any) -> None:
        self._child = child

    async def wait(self) -> int:
        return await asyncio.to_thread(self._child.wait)

    def terminate(self) -> None:
        if _terminate_child_process_group(self._child, 15):
            return
        self._child.terminate()

    def kill(self) -> None:
        if _terminate_child_process_group(self._child, 9):
            return
        self._child.kill()


def _terminate_child_process_group(child: Any, signal_number: int) -> bool:
    if os.name != "posix":
        return False
    pid = getattr(child, "pid", None)
    if pid is None:
        return False
    try:
        os.killpg(int(pid), signal_number)
        return True
    except ProcessLookupError:
        return True
    except OSError:
        return False


async def _spawn_local_pty_process(
    params: ExecParams,
    env: dict[str, str],
    backend: LocalProcess,
) -> LocalRunningProcess:
    if os.name != "posix":
        raise RuntimeError("codex-exec-server LocalProcess PTY runtime is not ported")

    import fcntl
    import pty
    import struct
    import subprocess
    import termios

    program, *args = params.argv
    master_fd, slave_fd = pty.openpty()
    try:
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    except OSError:
        pass

    def configure_child() -> None:
        os.setsid()
        try:
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        except OSError:
            pass

    command_args = [program, *args]
    kwargs: dict[str, Any] = {
        "cwd": params.cwd,
        "env": env,
        "stdin": slave_fd,
        "stdout": slave_fd,
        "stderr": slave_fd,
        "close_fds": True,
        "preexec_fn": configure_child,
    }
    if params.arg0 is not None:
        command_args = [params.arg0, *args]
        kwargs["executable"] = program
    try:
        child = subprocess.Popen(command_args, **kwargs)
    finally:
        try:
            os.close(slave_fd)
        except OSError:
            pass

    child_process = _LocalPtyChildProcess(child)
    process = LocalRunningProcess(
        tty=True,
        pipe_stdin=params.pipe_stdin,
        child_process=child_process,
        stdin_writer=_PtyStdinWriter(master_fd),
        open_streams=2,
    )
    process.task_handles.extend(
        [
            asyncio.create_task(
                _local_process_stream_output(
                    backend,
                    params.process_id,
                    process,
                    ExecOutputStream.PTY,
                    _PtyMasterReader(master_fd),
                )
            ),
            asyncio.create_task(
                _local_process_stream_output(
                    backend,
                    params.process_id,
                    process,
                    ExecOutputStream.PTY,
                    _EmptyAsyncReader(),
                )
            ),
            asyncio.create_task(_local_process_watch_exit(backend, params.process_id, process, child_process)),
        ]
    )
    return process


class _PtyMasterReader:
    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._closed = False

    async def read(self, size: int = 4096) -> bytes:
        if self._closed:
            return b""
        try:
            return await asyncio.to_thread(os.read, self._fd, size)
        except OSError as exc:
            if exc.errno in {errno.EIO, errno.EBADF}:
                self.close()
                return b""
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            os.close(self._fd)
        except OSError:
            pass


async def _local_process_stream_output(
    backend: LocalProcess,
    process_id: ProcessId,
    process: LocalRunningProcess,
    stream: "ExecOutputStream",
    reader: Any,
) -> None:
    try:
        while reader is not None:
            chunk = await _maybe_await(reader.read(4096))
            if not chunk:
                break
            seq = process.record_output(stream, bytes(chunk))
            if backend.notifications is not None:
                await backend.notifications.notify(
                    EXEC_OUTPUT_DELTA_METHOD,
                    ExecOutputDeltaNotification(
                        process_id=process_id,
                        seq=seq,
                        stream=stream,
                        chunk=ByteChunk(bytes(chunk)),
                    ),
                )
    finally:
        close = getattr(reader, "close", None)
        if close is not None:
            close()
        process.open_streams = max(0, process.open_streams - 1)
        await _local_process_maybe_mark_closed(backend, process_id, process)


async def _local_process_watch_exit(
    backend: LocalProcess,
    process_id: ProcessId,
    process: LocalRunningProcess,
    child: Any,
) -> None:
    wait_result = await _maybe_await(child.wait())
    exit_code = int(wait_result if wait_result is not None else -1)
    seq = process.record_exit(exit_code)
    if backend.notifications is not None:
        await backend.notifications.notify(
            EXEC_EXITED_METHOD,
            ExecExitedNotification(process_id=process_id, seq=seq, exit_code=exit_code),
        )
    await _local_process_maybe_mark_closed(backend, process_id, process)


async def _local_process_maybe_mark_closed(
    backend: LocalProcess,
    process_id: ProcessId,
    process: LocalRunningProcess,
) -> None:
    if process.closed or process.open_streams != 0 or process.exit_code is None:
        return
    seq = process.next_seq
    process.next_seq += 1
    process.mark_closed(seq)
    if backend.notifications is not None:
        await backend.notifications.notify(
            EXEC_CLOSED_METHOD,
            ExecClosedNotification(process_id=process_id, seq=seq),
        )
    cleanup_task = asyncio.create_task(_local_process_cleanup_closed_after_retention(backend, process_id, process))
    process.task_handles.append(cleanup_task)


async def _local_process_cleanup_closed_after_retention(
    backend: LocalProcess,
    process_id: ProcessId,
    process: LocalRunningProcess,
) -> None:
    await asyncio.sleep(LOCAL_PROCESS_EXITED_PROCESS_RETENTION_SECONDS)
    if backend.processes.get(process_id) is process and process.closed:
        backend.processes.pop(process_id, None)


class LocalExecProcess:
    def __init__(self, process_id: ProcessId, backend: LocalProcess, process: LocalRunningProcess) -> None:
        self._process_id = process_id
        self._backend = backend
        self._process = process

    def process_id(self) -> ProcessId:
        return self._process_id

    def subscribe_wake(self) -> asyncio.Queue[int]:
        return self._process.wake_queue

    def subscribe_events(self) -> ExecProcessEventReceiver:
        if self._process.events is None:
            return ExecProcessEventReceiver.empty()
        return self._process.events.subscribe()

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        response = await self._backend.exec_read(
            ReadParams(
                process_id=self._process_id,
                after_seq=after_seq,
                max_bytes=max_bytes,
                wait_ms=wait_ms,
            )
        )
        if isinstance(response, JSONRPCErrorError):
            raise ExecServerError(f"exec-server rejected request ({response.code}): {response.message}", "server")
        return response

    async def write(self, chunk: bytes) -> WriteResponse:
        response = await self._backend.exec_write(
            WriteParams(process_id=self._process_id, chunk=ByteChunk(chunk))
        )
        if isinstance(response, JSONRPCErrorError):
            raise ExecServerError(f"exec-server rejected request ({response.code}): {response.message}", "server")
        return response

    async def terminate(self) -> None:
        response = await self._backend.terminate_process(TerminateParams(process_id=self._process_id))
        if isinstance(response, JSONRPCErrorError):
            raise ExecServerError(f"exec-server rejected request ({response.code}): {response.message}", "server")


class ProcessHandler:
    def __init__(self, process: LocalProcess | RpcNotificationSender | None) -> None:
        if isinstance(process, LocalProcess) or _has_local_process_surface(process):
            self.process = process
        else:
            self.process = LocalProcess.new(process)

    @classmethod
    def new(cls, notifications: RpcNotificationSender | None) -> "ProcessHandler":
        return cls(LocalProcess.new(notifications))

    @property
    def notifications(self) -> RpcNotificationSender | None:
        return getattr(self.process, "notifications", None)

    @property
    def shutdown_called(self) -> bool:
        return bool(getattr(self.process, "shutdown_called", False))

    async def shutdown(self) -> None:
        await self.process.shutdown()

    def set_notification_sender(self, notifications: RpcNotificationSender | None) -> None:
        self.process.set_notification_sender(notifications)

    async def exec(self, params: ExecParams) -> ExecResponse:
        return await self.process.exec(params)

    async def exec_read(self, params: ReadParams) -> ReadResponse:
        return await self.process.exec_read(params)

    async def exec_write(self, params: WriteParams) -> WriteResponse:
        return await self.process.exec_write(params)

    async def terminate(self, params: TerminateParams) -> TerminateResponse:
        terminate = getattr(self.process, "terminate_process", None)
        if callable(terminate):
            return await terminate(params)
        return await self.process.terminate(params)


def _has_local_process_surface(value: Any) -> bool:
    return all(
        callable(getattr(value, name, None))
        for name in ("shutdown", "set_notification_sender", "exec", "exec_read", "exec_write")
    )


@dataclass(frozen=True)
class ConnectionId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> "ConnectionId":
        return cls(uuid.uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class AttachmentState:
    current_connection_id: ConnectionId | None
    detached_connection_id: ConnectionId | None = None
    detached_expires_at: float | None = None


class SessionEntry:
    def __init__(self, session_id: str, process: ProcessHandler, connection_id: ConnectionId) -> None:
        self.session_id = session_id
        self.process = process
        self.attachment = AttachmentState(current_connection_id=connection_id)

    @classmethod
    def new(cls, session_id: str, process: ProcessHandler, connection_id: ConnectionId) -> "SessionEntry":
        return cls(session_id, process, connection_id)

    def attach(self, connection_id: ConnectionId) -> None:
        self.attachment.current_connection_id = connection_id
        self.attachment.detached_connection_id = None
        self.attachment.detached_expires_at = None

    def detach(self, connection_id: ConnectionId, ttl: float = DETACHED_SESSION_TTL) -> bool:
        if self.attachment.current_connection_id != connection_id:
            return False
        self.attachment.current_connection_id = None
        self.attachment.detached_connection_id = connection_id
        self.attachment.detached_expires_at = time.monotonic() + ttl
        return True

    def has_active_connection(self) -> bool:
        return self.attachment.current_connection_id is not None

    def is_attached_to(self, connection_id: ConnectionId) -> bool:
        return self.attachment.current_connection_id == connection_id

    def is_expired(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return self.attachment.detached_expires_at is not None and now >= self.attachment.detached_expires_at

    def is_detached_connection_expired(self, connection_id: ConnectionId, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return (
            self.attachment.current_connection_id is None
            and self.attachment.detached_connection_id == connection_id
            and self.attachment.detached_expires_at is not None
            and now >= self.attachment.detached_expires_at
        )


class SessionRegistry:
    def __init__(self, detached_session_ttl: float = DETACHED_SESSION_TTL) -> None:
        self.sessions: dict[str, SessionEntry] = {}
        self.detached_session_ttl = detached_session_ttl

    @classmethod
    def new(cls, detached_session_ttl: float = DETACHED_SESSION_TTL) -> "SessionRegistry":
        return cls(detached_session_ttl=detached_session_ttl)

    async def attach(
        self,
        resume_session_id: str | None,
        notifications: RpcNotificationSender | None,
    ) -> "SessionHandle | JSONRPCErrorError":
        connection_id = ConnectionId.new()
        if resume_session_id is not None:
            entry = self.sessions.get(resume_session_id)
            if entry is None:
                return invalid_request(f"unknown session id {resume_session_id}")
            if entry.is_expired():
                removed = self.sessions.pop(resume_session_id, None)
                if removed is not None:
                    await removed.process.shutdown()
                return invalid_request(f"unknown session id {resume_session_id}")
            if entry.has_active_connection():
                return invalid_request(f"session {resume_session_id} is already attached to another connection")
            entry.process.set_notification_sender(notifications)
            entry.attach(connection_id)
            return SessionHandle(self, entry, connection_id)

        session_id = str(uuid.uuid4())
        entry = SessionEntry.new(session_id, ProcessHandler.new(notifications), connection_id)
        self.sessions[session_id] = entry
        return SessionHandle(self, entry, connection_id)

    async def expire_if_detached(self, session_id: str, connection_id: ConnectionId) -> None:
        await asyncio.sleep(self.detached_session_ttl)
        entry = self.sessions.get(session_id)
        if entry is None:
            return
        if not entry.is_detached_connection_expired(connection_id):
            return
        removed = self.sessions.pop(session_id, None)
        if removed is not None:
            await removed.process.shutdown()


@dataclass(frozen=True)
class SessionHandle:
    registry: SessionRegistry
    entry: SessionEntry
    connection_id_value: ConnectionId

    def session_id(self) -> str:
        return self.entry.session_id

    def connection_id(self) -> str:
        return str(self.connection_id_value)

    def is_session_attached(self) -> bool:
        return self.entry.is_attached_to(self.connection_id_value)

    def process(self) -> ProcessHandler:
        return self.entry.process

    async def detach(self) -> None:
        if not self.entry.detach(self.connection_id_value, self.registry.detached_session_ttl):
            return
        self.entry.process.set_notification_sender(None)
        asyncio.create_task(self.registry.expire_if_detached(self.entry.session_id, self.connection_id_value))


class ExecServerHandler:
    def __init__(
        self,
        session_registry: SessionRegistry,
        notifications: RpcNotificationSender | None,
        runtime_paths: "ExecServerRuntimePaths",
        file_system: "FileSystemHandler | None" = None,
    ) -> None:
        self.session_registry = session_registry
        self.notifications = notifications
        self.runtime_paths = runtime_paths
        self.file_system = file_system
        self.session_handle: SessionHandle | None = None
        self.initialize_requested = False
        self.initialized_flag = False
        self.shutdown_called = False

    @classmethod
    def new(
        cls,
        session_registry: SessionRegistry,
        notifications: RpcNotificationSender | None,
        runtime_paths: "ExecServerRuntimePaths",
    ) -> "ExecServerHandler":
        return cls(session_registry, notifications, runtime_paths)

    async def shutdown(self) -> None:
        self.shutdown_called = True
        if self.session_handle is not None:
            await self.session_handle.detach()

    def is_session_attached(self) -> bool:
        return self.session_handle is None or self.session_handle.is_session_attached()

    async def initialize(self, params: "InitializeParams") -> "InitializeResponse | JSONRPCErrorError":
        if self.initialize_requested:
            return invalid_request("initialize may only be sent once per connection")
        self.initialize_requested = True
        session = await self.session_registry.attach(params.resume_session_id, self.notifications)
        if isinstance(session, JSONRPCErrorError):
            self.initialize_requested = False
            return session
        self.session_handle = session
        return InitializeResponse(session_id=session.session_id())

    def initialized(self) -> None | str:
        if not self.initialize_requested:
            return "received `initialized` notification before `initialize`"
        session = self.require_session_attached()
        if isinstance(session, JSONRPCErrorError):
            return session.message
        self.initialized_flag = True
        return None

    async def exec(self, params: "ExecParams") -> "ExecResponse | JSONRPCErrorError":
        session = self.require_initialized_for("exec")
        if isinstance(session, JSONRPCErrorError):
            return session
        return await session.process().exec(params)

    async def exec_read(self, params: "ReadParams") -> "ReadResponse | JSONRPCErrorError":
        session = self.require_initialized_for("exec")
        if isinstance(session, JSONRPCErrorError):
            return session
        response = await session.process().exec_read(params)
        if isinstance(response, JSONRPCErrorError):
            return response
        attached = self.require_session_attached()
        if isinstance(attached, JSONRPCErrorError):
            return attached
        return response

    async def exec_write(self, params: "WriteParams") -> "WriteResponse | JSONRPCErrorError":
        session = self.require_initialized_for("exec")
        if isinstance(session, JSONRPCErrorError):
            return session
        return await session.process().exec_write(params)

    async def terminate(self, params: "TerminateParams") -> "TerminateResponse | JSONRPCErrorError":
        session = self.require_initialized_for("exec")
        if isinstance(session, JSONRPCErrorError):
            return session
        return await session.process().terminate(params)

    async def http_request(self, request_id: RequestId, params: Any) -> None | JSONRPCErrorError:
        error = self.require_initialized_for("http")
        if isinstance(error, JSONRPCErrorError):
            return error
        return JSONRPCErrorError(code=-32603, message="codex-exec-server HTTP runtime is not ported")

    async def fs_read_file(self, params: "FsReadFileParams") -> "FsReadFileResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().read_file(params)

    async def fs_write_file(self, params: "FsWriteFileParams") -> "FsWriteFileResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().write_file(params)

    async def fs_create_directory(
        self,
        params: "FsCreateDirectoryParams",
    ) -> "FsCreateDirectoryResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().create_directory(params)

    async def fs_get_metadata(self, params: "FsGetMetadataParams") -> "FsGetMetadataResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().get_metadata(params)

    async def fs_read_directory(
        self,
        params: "FsReadDirectoryParams",
    ) -> "FsReadDirectoryResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().read_directory(params)

    async def fs_remove(self, params: "FsRemoveParams") -> "FsRemoveResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().remove(params)

    async def fs_copy(self, params: "FsCopyParams") -> "FsCopyResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().copy(params)

    def require_initialized_for(self, method_family: str) -> SessionHandle | JSONRPCErrorError:
        if not self.initialize_requested:
            return invalid_request(f"client must call initialize before using {method_family} methods")
        session = self.require_session_attached()
        if isinstance(session, JSONRPCErrorError):
            return session
        if not self.initialized_flag:
            return invalid_request(f"client must send initialized before using {method_family} methods")
        return session

    def require_session_attached(self) -> SessionHandle | JSONRPCErrorError:
        if self.session_handle is None:
            return invalid_request("client must call initialize before using methods")
        if self.session_handle.is_session_attached():
            return self.session_handle
        return invalid_request("session has been resumed by another connection")

    def _file_system(self) -> "FileSystemHandler":
        if self.file_system is None:
            self.file_system = FileSystemHandler.new(self.runtime_paths)
        return self.file_system


DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT = 10
DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT = 10
DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT_SECONDS = DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT
DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT_SECONDS = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
ENVIRONMENTS_TOML_FILE = "environments.toml"
MAX_ENVIRONMENT_ID_LEN = 64
MAX_READ_FILE_BYTES = 512 * 1024 * 1024
FS_HELPER_ENV_ALLOWLIST = ("PATH", "TMPDIR", "TMP", "TEMP")
FS_HELPER_BAZEL_BWRAP_ENV_ALLOWLIST = (
    "CARGO_BIN_EXE_bwrap",
    "RUNFILES_DIR",
    "RUNFILES_MANIFEST_FILE",
    "RUNFILES_MANIFEST_ONLY",
    "TEST_SRCDIR",
    "TEST_WORKSPACE",
)


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


class ConnectionProcessor:
    def __init__(
        self,
        runtime_paths: "ExecServerRuntimePaths",
        session_registry: "SessionRegistry | None" = None,
        router: RpcRouter | None = None,
    ) -> None:
        self.session_registry = session_registry or SessionRegistry.new()
        self.runtime_paths = runtime_paths
        self.router = router or build_router()

    @classmethod
    def new(cls, runtime_paths: "ExecServerRuntimePaths") -> "ConnectionProcessor":
        return cls(runtime_paths)

    async def run_stdio(self, reader: Any, writer: Any) -> None:
        await self.run_connection(JsonRpcConnection.from_stdio(reader, writer, "exec-server stdio"))

    async def run_connection(self, connection: JsonRpcConnection) -> None:
        outgoing_tx: asyncio.Queue[RpcServerOutboundMessage] = asyncio.Queue()
        notifications = RpcNotificationSender.new(outgoing_tx)
        handler = ExecServerHandler.new(self.session_registry, notifications, self.runtime_paths)
        try:
            while handler.is_session_attached():
                event = await connection.incoming_rx.get()
                if event.kind == "disconnected":
                    break
                if event.kind == "malformed":
                    await connection.outgoing_tx.put(
                        encode_server_message(
                            RpcServerOutboundMessage.error_message(
                                RequestId.integer(-1),
                                invalid_request(event.reason or "malformed JSON-RPC message"),
                            )
                        )
                    )
                    await _drain_outbound_connection(connection.outgoing_tx, outgoing_tx)
                    continue
                if event.message is None:
                    break
                should_continue = await _process_server_connection_message(
                    handler,
                    self.router,
                    event.message,
                    connection.outgoing_tx,
                    connection.disconnected,
                )
                await _drain_outbound_connection(connection.outgoing_tx, outgoing_tx)
                if not should_continue:
                    break
        finally:
            await handler.shutdown()
            try:
                await asyncio.wait_for(connection.outgoing_tx.join(), timeout=0.1)
            except TimeoutError:
                pass
            await connection.close()


async def _process_server_connection_message(
    handler: "ExecServerHandler",
    router: RpcRouter,
    message: JSONRPCMessage,
    outgoing_tx: "asyncio.Queue[JSONRPCMessage]",
    disconnected: asyncio.Event | None = None,
) -> bool:
    value = message.value
    if isinstance(value, JSONRPCRequest):
        route = router.request_route(value.method)
        if route is None:
            outbound = RpcServerOutboundMessage.error_message(
                value.id,
                method_not_found(f"exec-server stub does not implement `{value.method}` yet"),
            )
        else:
            outbound = await _run_server_route_until_disconnect(route(handler, value), disconnected)
            if outbound is _SERVER_ROUTE_DISCONNECTED:
                return False
        if outbound is not None:
            await outgoing_tx.put(encode_server_message(outbound))
        return True
    if isinstance(value, JSONRPCNotification):
        route = router.notification_route(value.method)
        if route is None:
            return False
        result = await _run_server_route_until_disconnect(route(handler, value), disconnected)
        if result is _SERVER_ROUTE_DISCONNECTED:
            return False
        return result is None
    return False


_SERVER_ROUTE_DISCONNECTED = object()


async def _run_server_route_until_disconnect(route_result: Any, disconnected: asyncio.Event | None) -> Any:
    route_task = asyncio.create_task(_maybe_await(route_result))
    if disconnected is None:
        return await route_task
    disconnect_task = asyncio.create_task(disconnected.wait())
    try:
        done, pending = await asyncio.wait(
            {route_task, disconnect_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if disconnect_task in done and disconnected.is_set() and route_task not in done:
            route_task.cancel()
            await asyncio.gather(route_task, return_exceptions=True)
            return _SERVER_ROUTE_DISCONNECTED
        return await route_task
    finally:
        disconnect_task.cancel()
        await asyncio.gather(disconnect_task, return_exceptions=True)


async def _drain_outbound_connection(
    json_outgoing_tx: "asyncio.Queue[JSONRPCMessage]",
    outgoing_tx: "asyncio.Queue[RpcServerOutboundMessage]",
) -> None:
    while True:
        try:
            outbound = outgoing_tx.get_nowait()
        except asyncio.QueueEmpty:
            return
        await json_outgoing_tx.put(encode_server_message(outbound))


async def _stdio_connection_reader(
    reader: Any,
    incoming_rx: "asyncio.Queue[JsonRpcConnectionEvent]",
    disconnected: asyncio.Event,
    connection_label: str,
) -> None:
    while True:
        try:
            line = await _read_stdio_line(reader)
        except Exception as exc:
            await _send_stdio_disconnected(
                incoming_rx,
                disconnected,
                f"failed to read JSON-RPC message from {connection_label}: {exc}",
            )
            return
        if not line:
            await _send_stdio_disconnected(incoming_rx, disconnected, None)
            return
        if not line.strip():
            continue
        message = _decode_stdio_jsonrpc_line(line)
        if isinstance(message, str):
            await incoming_rx.put(
                JsonRpcConnectionEvent.malformed_message(
                    f"failed to parse JSON-RPC message from {connection_label}: {message}"
                )
            )
        else:
            await incoming_rx.put(JsonRpcConnectionEvent.message_event(message))


async def _stdio_connection_writer(
    writer: Any,
    outgoing_tx: "asyncio.Queue[JSONRPCMessage]",
    incoming_rx: "asyncio.Queue[JsonRpcConnectionEvent]",
    disconnected: asyncio.Event,
    connection_label: str,
) -> None:
    while True:
        message = await outgoing_tx.get()
        try:
            await _write_stdio_jsonrpc_line(writer, message)
        except Exception as exc:
            await _send_stdio_disconnected(
                incoming_rx,
                disconnected,
                f"failed to write JSON-RPC message to {connection_label}: {exc}",
            )
            return
        finally:
            outgoing_tx.task_done()


async def _send_stdio_disconnected(
    incoming_rx: "asyncio.Queue[JsonRpcConnectionEvent]",
    disconnected: asyncio.Event,
    reason: str | None,
) -> None:
    disconnected.set()
    await incoming_rx.put(JsonRpcConnectionEvent.disconnected(reason))


async def _websocket_connection_loop(
    websocket: Any,
    outgoing_tx: "asyncio.Queue[JSONRPCMessage]",
    incoming_rx: "asyncio.Queue[JsonRpcConnectionEvent]",
    disconnected: asyncio.Event,
    connection_label: str,
    ping_interval: float | None,
) -> None:
    next_ping: asyncio.Task[Any] | None = None
    if ping_interval is not None:
        next_ping = asyncio.create_task(asyncio.sleep(ping_interval))
    outgoing_task: asyncio.Task[Any] = asyncio.create_task(outgoing_tx.get())
    incoming_task: asyncio.Task[Any] = asyncio.create_task(_websocket_recv(websocket))
    try:
        while True:
            wait_set = {outgoing_task, incoming_task}
            if next_ping is not None:
                wait_set.add(next_ping)
            done, _pending = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

            if outgoing_task in done:
                message = outgoing_task.result()
                try:
                    await _send_websocket_jsonrpc_message(websocket, connection_label, message)
                except Exception as exc:
                    await _send_websocket_disconnected(
                        incoming_rx,
                        disconnected,
                        str(exc),
                    )
                    return
                finally:
                    outgoing_tx.task_done()
                outgoing_task = asyncio.create_task(outgoing_tx.get())

            if next_ping is not None and next_ping in done:
                try:
                    await _websocket_send(websocket, JsonRpcWebSocketMessage.ping())
                except Exception as exc:
                    await _send_websocket_disconnected(
                        incoming_rx,
                        disconnected,
                        f"failed to write websocket ping to {connection_label}: {exc}",
                    )
                    return
                next_ping = asyncio.create_task(asyncio.sleep(ping_interval))

            if incoming_task in done:
                try:
                    message = incoming_task.result()
                except Exception as exc:
                    await _send_websocket_disconnected(
                        incoming_rx,
                        disconnected,
                        f"failed to read websocket JSON-RPC message from {connection_label}: {exc}",
                    )
                    return
                if message is None:
                    await _send_websocket_disconnected(incoming_rx, disconnected, None)
                    return
                try:
                    frame = message.parse_jsonrpc_frame()
                except Exception as exc:
                    await incoming_rx.put(
                        JsonRpcConnectionEvent.malformed_message(
                            f"failed to parse websocket JSON-RPC message from {connection_label}: {exc}"
                        )
                    )
                else:
                    if frame.kind == "message":
                        if frame.message is not None:
                            await incoming_rx.put(JsonRpcConnectionEvent.message_event(frame.message))
                    elif frame.kind == "close":
                        await _send_websocket_disconnected(incoming_rx, disconnected, None)
                        return
                incoming_task = asyncio.create_task(_websocket_recv(websocket))
    finally:
        outgoing_task.cancel()
        incoming_task.cancel()
        if next_ping is not None:
            next_ping.cancel()
        await asyncio.gather(outgoing_task, incoming_task, *( [next_ping] if next_ping is not None else [] ), return_exceptions=True)


async def _websocket_recv(websocket: Any) -> JsonRpcWebSocketMessage | None:
    if hasattr(websocket, "recv"):
        message = await _maybe_await(websocket.recv())
    elif hasattr(websocket, "receive"):
        message = await _maybe_await(websocket.receive())
    else:
        raise AttributeError("websocket must expose recv() or receive()")
    if message is None or isinstance(message, JsonRpcWebSocketMessage):
        return message
    if isinstance(message, str):
        return JsonRpcWebSocketMessage.text(message)
    if isinstance(message, bytes):
        return JsonRpcWebSocketMessage.binary(message)
    raise TypeError(f"unsupported websocket message type: {type(message).__name__}")


async def _websocket_send(websocket: Any, message: JsonRpcWebSocketMessage) -> None:
    if hasattr(websocket, "send"):
        await _maybe_await(websocket.send(message))
        return
    raise AttributeError("websocket must expose send()")


async def _send_websocket_jsonrpc_message(
    websocket: Any,
    connection_label: str,
    message: JSONRPCMessage,
) -> None:
    try:
        encoded = json.dumps(message.to_mapping(), separators=(",", ":"))
    except Exception as exc:
        raise RuntimeError(f"failed to serialize JSON-RPC message for {connection_label}: {exc}") from exc
    try:
        await _websocket_send(websocket, JsonRpcWebSocketMessage.text(encoded))
    except Exception as exc:
        raise RuntimeError(f"failed to write websocket JSON-RPC message to {connection_label}: {exc}") from exc


async def _send_websocket_disconnected(
    incoming_rx: "asyncio.Queue[JsonRpcConnectionEvent]",
    disconnected: asyncio.Event,
    reason: str | None,
) -> None:
    disconnected.set()
    await incoming_rx.put(JsonRpcConnectionEvent.disconnected(reason))


async def _stdio_child_supervisor(child_process: Any, terminate_event: asyncio.Event, grace_period: float) -> None:
    wait_task = asyncio.create_task(_wait_child_process(child_process))
    terminate_task = asyncio.create_task(terminate_event.wait())
    try:
        done, _pending = await asyncio.wait({wait_task, terminate_task}, return_when=asyncio.FIRST_COMPLETED)
        if wait_task in done:
            _log_stdio_child_wait_result(wait_task)
            _kill_process_tree(child_process)
            return
        await _terminate_stdio_child(child_process, grace_period)
    finally:
        wait_task.cancel()
        terminate_task.cancel()
        await asyncio.gather(wait_task, terminate_task, return_exceptions=True)


async def _terminate_stdio_child(child_process: Any, grace_period: float) -> None:
    _terminate_process_tree(child_process)
    wait_task = asyncio.create_task(_wait_child_process(child_process))
    try:
        await asyncio.wait_for(wait_task, timeout=grace_period)
        _log_stdio_child_wait_result(wait_task)
    except TimeoutError:
        _kill_process_tree(child_process)
        try:
            await _wait_child_process(child_process)
        except Exception:
            return


async def _wait_child_process(child_process: Any) -> Any:
    wait = getattr(child_process, "wait", None)
    if wait is None:
        return None
    return await _maybe_await(wait())


def _terminate_process_tree(child_process: Any) -> None:
    terminate = getattr(child_process, "terminate", None)
    if terminate is not None:
        try:
            terminate()
        except ProcessLookupError:
            return
        return
    kill_direct = getattr(child_process, "start_kill", None)
    if kill_direct is not None:
        try:
            kill_direct()
        except ProcessLookupError:
            return


def _kill_process_tree(child_process: Any) -> None:
    kill = getattr(child_process, "kill", None)
    if kill is not None:
        try:
            kill()
        except ProcessLookupError:
            return
        return
    kill_direct = getattr(child_process, "start_kill", None)
    if kill_direct is not None:
        try:
            kill_direct()
        except ProcessLookupError:
            return


def _log_stdio_child_wait_result(wait_task: "asyncio.Task[Any]") -> None:
    try:
        wait_task.result()
    except Exception:
        return


async def _read_stdio_line(reader: Any) -> bytes:
    line = await _maybe_await(reader.readline())
    if isinstance(line, str):
        return line.encode("utf-8")
    return bytes(line)


def _decode_stdio_jsonrpc_line(line: bytes) -> JSONRPCMessage | str:
    try:
        decoded = json.loads(line.decode("utf-8"))
        return JSONRPCMessage.from_mapping(decoded)
    except Exception as exc:
        return str(exc)


async def _write_stdio_jsonrpc_line(writer: Any, message: JSONRPCMessage) -> None:
    encoded = json.dumps(message.to_mapping(), separators=(",", ":")).encode("utf-8") + b"\n"
    writer.write(encoded)
    drain = getattr(writer, "drain", None)
    if drain is not None:
        await _maybe_await(drain())


def _parse_socket_addr(value: str) -> tuple[str, int] | None:
    if value.startswith("["):
        end = value.find("]")
        if end < 0 or len(value) <= end + 2 or value[end + 1] != ":":
            return None
        host = value[1:end]
        port_text = value[end + 2 :]
    else:
        if value.count(":") != 1:
            return None
        host, port_text = value.rsplit(":", 1)
    if not host or not port_text:
        return None
    try:
        ipaddress.ip_address(host)
        port = int(port_text, 10)
    except ValueError:
        return None
    if not 0 <= port <= 65535:
        return None
    return host, port


@dataclass(frozen=True)
class ByteChunk:
    data: bytes

    def into_inner(self) -> bytes:
        return self.data

    def to_base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @classmethod
    def from_base64(cls, value: str) -> "ByteChunk":
        return cls(base64.b64decode(value, validate=True))


@total_ordering
@dataclass(frozen=True)
class ProcessId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", str(self.value))

    @classmethod
    def new(cls, value: str) -> "ProcessId":
        return cls(value)

    def as_str(self) -> str:
        return self.value

    def into_inner(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ProcessId):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return False

    def __lt__(self, other: object) -> bool:
        if isinstance(other, ProcessId):
            return self.value < other.value
        if isinstance(other, str):
            return self.value < other
        return NotImplemented


@dataclass(frozen=True)
class InitializeParams:
    client_name: str
    resume_session_id: str | None = None


@dataclass(frozen=True)
class InitializeResponse:
    session_id: str


def decode_initialize_params(value: Any) -> InitializeParams:
    if not isinstance(value, Mapping):
        raise ValueError("InitializeParams must be a mapping")
    client_name = value.get("clientName")
    if not isinstance(client_name, str):
        raise ValueError("clientName must be a string")
    resume_session_id = value.get("resumeSessionId")
    if resume_session_id is not None and not isinstance(resume_session_id, str):
        raise ValueError("resumeSessionId must be a string or null")
    return InitializeParams(client_name=client_name, resume_session_id=resume_session_id)


def encode_initialize_response(value: InitializeResponse) -> dict[str, Any]:
    return {"sessionId": value.session_id}


@dataclass(frozen=True)
class ExecEnvPolicy:
    inherit: Any
    ignore_default_excludes: bool
    exclude: list[str] = field(default_factory=list)
    set: dict[str, str] = field(default_factory=dict)
    include_only: list[str] = field(default_factory=list)


def shell_environment_policy(env_policy: ExecEnvPolicy) -> ShellEnvironmentPolicy:
    return ShellEnvironmentPolicy(
        inherit=ShellEnvironmentPolicyInherit(env_policy.inherit),
        ignore_default_excludes=env_policy.ignore_default_excludes,
        exclude=tuple(env_policy.exclude),
        set_values=dict(env_policy.set),
        include_only=tuple(env_policy.include_only),
        use_profile=False,
    )


def child_env(params: ExecParams) -> dict[str, str]:
    if params.env_policy is None:
        return dict(params.env)
    env = create_shell_env(shell_environment_policy(params.env_policy), None)
    env.update(params.env)
    return env


@dataclass(frozen=True)
class ExecParams:
    process_id: ProcessId
    argv: list[str]
    cwd: str
    env: dict[str, str]
    tty: bool
    env_policy: ExecEnvPolicy | None = None
    pipe_stdin: bool = False
    arg0: str | None = None


def decode_exec_params(value: Any) -> ExecParams:
    if not isinstance(value, Mapping):
        raise ValueError("ExecParams must be a mapping")
    process_id = _decode_process_id(value.get("processId"))
    argv = value.get("argv")
    if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
        raise ValueError("argv must be a list of strings")
    cwd = value.get("cwd")
    if not isinstance(cwd, str):
        raise ValueError("cwd must be a string")
    env_value = value.get("env")
    if not isinstance(env_value, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in env_value.items()
    ):
        raise ValueError("env must be an object with string values")
    tty = value.get("tty")
    if not isinstance(tty, bool):
        raise ValueError("tty must be a bool")
    pipe_stdin = value.get("pipeStdin", False)
    if not isinstance(pipe_stdin, bool):
        raise ValueError("pipeStdin must be a bool")
    arg0 = value.get("arg0")
    if arg0 is not None and not isinstance(arg0, str):
        raise ValueError("arg0 must be a string or null")
    env_policy_value = value.get("envPolicy")
    env_policy = None if env_policy_value is None else decode_exec_env_policy(env_policy_value)
    return ExecParams(
        process_id=process_id,
        argv=list(argv),
        cwd=cwd,
        env=dict(env_value),
        tty=tty,
        env_policy=env_policy,
        pipe_stdin=pipe_stdin,
        arg0=arg0,
    )


def decode_exec_env_policy(value: Any) -> ExecEnvPolicy:
    if not isinstance(value, Mapping):
        raise ValueError("ExecEnvPolicy must be a mapping")
    inherit = value.get("inherit")
    if not isinstance(inherit, str):
        raise ValueError("inherit must be a string")
    ignore_default_excludes = value.get("ignoreDefaultExcludes")
    if not isinstance(ignore_default_excludes, bool):
        raise ValueError("ignoreDefaultExcludes must be a bool")
    exclude = value.get("exclude", [])
    include_only = value.get("includeOnly", [])
    set_values = value.get("set", {})
    if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
        raise ValueError("exclude must be a list of strings")
    if not isinstance(include_only, list) or not all(isinstance(item, str) for item in include_only):
        raise ValueError("includeOnly must be a list of strings")
    if not isinstance(set_values, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in set_values.items()
    ):
        raise ValueError("set must be an object with string values")
    return ExecEnvPolicy(
        inherit=ShellEnvironmentPolicyInherit(inherit),
        ignore_default_excludes=ignore_default_excludes,
        exclude=list(exclude),
        set=dict(set_values),
        include_only=list(include_only),
    )


@dataclass(frozen=True)
class ExecResponse:
    process_id: ProcessId


def encode_exec_response(value: ExecResponse) -> dict[str, Any]:
    return {"processId": value.process_id.as_str()}


@dataclass(frozen=True)
class ReadParams:
    process_id: ProcessId
    after_seq: int | None = None
    max_bytes: int | None = None
    wait_ms: int | None = None


def decode_read_params(value: Any) -> ReadParams:
    if not isinstance(value, Mapping):
        raise ValueError("ReadParams must be a mapping")
    return ReadParams(
        process_id=_decode_process_id(value.get("processId")),
        after_seq=_decode_optional_int(value.get("afterSeq"), "afterSeq"),
        max_bytes=_decode_optional_int(value.get("maxBytes"), "maxBytes"),
        wait_ms=_decode_optional_int(value.get("waitMs"), "waitMs"),
    )


def encode_read_params(value: ReadParams) -> dict[str, Any]:
    return {
        "processId": value.process_id.as_str(),
        "afterSeq": value.after_seq,
        "maxBytes": value.max_bytes,
        "waitMs": value.wait_ms,
    }


class ExecOutputStream(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    PTY = "pty"


@dataclass(frozen=True)
class ProcessOutputChunk:
    seq: int
    stream: ExecOutputStream
    chunk: ByteChunk


@dataclass(frozen=True)
class ReadResponse:
    chunks: list[ProcessOutputChunk]
    next_seq: int
    exited: bool
    exit_code: int | None
    closed: bool
    failure: str | None = None


def encode_read_response(value: ReadResponse) -> dict[str, Any]:
    return {
        "chunks": [
            {
                "seq": chunk.seq,
                "stream": chunk.stream.value,
                "chunk": chunk.chunk.to_base64(),
            }
            for chunk in value.chunks
        ],
        "nextSeq": value.next_seq,
        "exited": value.exited,
        "exitCode": value.exit_code,
        "closed": value.closed,
        "failure": value.failure,
    }


def decode_read_response(value: Any) -> ReadResponse:
    if not isinstance(value, Mapping):
        raise ValueError("ReadResponse must be a mapping")
    chunks_value = value.get("chunks")
    if not isinstance(chunks_value, list):
        raise ValueError("chunks must be a list")
    chunks: list[ProcessOutputChunk] = []
    for chunk_value in chunks_value:
        if not isinstance(chunk_value, Mapping):
            raise ValueError("chunk must be a mapping")
        stream_value = chunk_value.get("stream")
        chunk_b64 = chunk_value.get("chunk")
        if not isinstance(stream_value, str) or not isinstance(chunk_b64, str):
            raise ValueError("stream and chunk are required")
        seq = _decode_optional_int(chunk_value.get("seq"), "seq")
        if seq is None:
            raise ValueError("seq must be an integer")
        chunks.append(
            ProcessOutputChunk(
                seq=seq,
                stream=ExecOutputStream(stream_value),
                chunk=ByteChunk.from_base64(chunk_b64),
            )
        )
    next_seq = _decode_optional_int(value.get("nextSeq"), "nextSeq")
    if next_seq is None:
        raise ValueError("nextSeq must be an integer")
    exited = value.get("exited")
    closed = value.get("closed")
    if not isinstance(exited, bool):
        raise ValueError("exited must be a bool")
    if not isinstance(closed, bool):
        raise ValueError("closed must be a bool")
    exit_code = _decode_optional_int(value.get("exitCode"), "exitCode")
    failure = value.get("failure")
    if failure is not None and not isinstance(failure, str):
        raise ValueError("failure must be a string or null")
    return ReadResponse(
        chunks=chunks,
        next_seq=next_seq,
        exited=exited,
        exit_code=exit_code,
        closed=closed,
        failure=failure,
    )


@dataclass(frozen=True)
class WriteParams:
    process_id: ProcessId
    chunk: ByteChunk


def decode_write_params(value: Any) -> WriteParams:
    if not isinstance(value, Mapping):
        raise ValueError("WriteParams must be a mapping")
    chunk = value.get("chunk")
    if not isinstance(chunk, str):
        raise ValueError("chunk must be a base64 string")
    return WriteParams(process_id=_decode_process_id(value.get("processId")), chunk=ByteChunk.from_base64(chunk))


def encode_write_params(value: WriteParams) -> dict[str, Any]:
    return {
        "processId": value.process_id.as_str(),
        "chunk": value.chunk.to_base64(),
    }


class WriteStatus(str, Enum):
    ACCEPTED = "accepted"
    UNKNOWN_PROCESS = "unknownProcess"
    STDIN_CLOSED = "stdinClosed"
    STARTING = "starting"


@dataclass(frozen=True)
class WriteResponse:
    status: WriteStatus


def encode_write_response(value: WriteResponse) -> dict[str, Any]:
    return {"status": value.status.value}


def decode_write_response(value: Any) -> WriteResponse:
    if not isinstance(value, Mapping):
        raise ValueError("WriteResponse must be a mapping")
    status = value.get("status")
    if not isinstance(status, str):
        raise ValueError("status must be a string")
    return WriteResponse(WriteStatus(status))


@dataclass(frozen=True)
class TerminateParams:
    process_id: ProcessId


def decode_terminate_params(value: Any) -> TerminateParams:
    if not isinstance(value, Mapping):
        raise ValueError("TerminateParams must be a mapping")
    return TerminateParams(process_id=_decode_process_id(value.get("processId")))


def encode_terminate_params(value: TerminateParams) -> dict[str, Any]:
    return {"processId": value.process_id.as_str()}


@dataclass(frozen=True)
class TerminateResponse:
    running: bool


def encode_terminate_response(value: TerminateResponse) -> dict[str, Any]:
    return {"running": value.running}


def decode_terminate_response(value: Any) -> TerminateResponse:
    if not isinstance(value, Mapping):
        raise ValueError("TerminateResponse must be a mapping")
    running = value.get("running")
    if not isinstance(running, bool):
        raise ValueError("running must be a bool")
    return TerminateResponse(running=running)


def _decode_process_id(value: Any) -> ProcessId:
    if not isinstance(value, str):
        raise ValueError("processId must be a string")
    return ProcessId.new(value)


def _decode_optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer or null")
    return value


@dataclass(frozen=True)
class ExecProcessEvent:
    kind: str
    chunk: ProcessOutputChunk | None = None
    seq_value: int | None = None
    exit_code: int | None = None
    message: str | None = None

    @classmethod
    def output(cls, chunk: ProcessOutputChunk) -> "ExecProcessEvent":
        return cls("output", chunk=chunk)

    @classmethod
    def exited(cls, seq: int, exit_code: int) -> "ExecProcessEvent":
        return cls("exited", seq_value=seq, exit_code=exit_code)

    @classmethod
    def closed(cls, seq: int) -> "ExecProcessEvent":
        return cls("closed", seq_value=seq)

    @classmethod
    def failed(cls, message: str) -> "ExecProcessEvent":
        return cls("failed", message=str(message))

    def seq(self) -> int | None:
        if self.kind == "output" and self.chunk is not None:
            return self.chunk.seq
        if self.kind in {"exited", "closed"}:
            return self.seq_value
        return None

    def retained_len(self) -> int:
        if self.kind == "output" and self.chunk is not None:
            return _byte_chunk_len(self.chunk.chunk)
        if self.kind == "failed":
            return len(self.message or "")
        return 0


class ExecProcessEventReceiver:
    def __init__(
        self,
        replay: list[ExecProcessEvent] | tuple[ExecProcessEvent, ...] | None = None,
        live_queue: asyncio.Queue[ExecProcessEvent] | None = None,
    ) -> None:
        self._replay = deque(replay or ())
        self._live_queue = live_queue or asyncio.Queue()

    @classmethod
    def empty(cls) -> "ExecProcessEventReceiver":
        return cls()

    async def recv(self) -> ExecProcessEvent:
        if self._replay:
            return self._replay.popleft()
        return await self._live_queue.get()


class ExecProcessEventLog:
    def __init__(self, event_capacity: int, byte_capacity: int) -> None:
        self.event_capacity = max(0, int(event_capacity))
        self.byte_capacity = max(0, int(byte_capacity))
        self._events: deque[ExecProcessEvent] = deque()
        self._retained_bytes = 0
        self._subscribers: list[asyncio.Queue[ExecProcessEvent]] = []

    @classmethod
    def new(cls, event_capacity: int, byte_capacity: int) -> "ExecProcessEventLog":
        return cls(event_capacity, byte_capacity)

    def publish(self, event: ExecProcessEvent) -> None:
        self._retained_bytes += event.retained_len()
        self._events.append(event)
        while len(self._events) > self.event_capacity or self._retained_bytes > self.byte_capacity:
            if not self._events:
                break
            evicted = self._events.popleft()
            self._retained_bytes = max(0, self._retained_bytes - evicted.retained_len())

        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(event)

    def subscribe(self) -> ExecProcessEventReceiver:
        live_queue: asyncio.Queue[ExecProcessEvent] = asyncio.Queue(maxsize=self.event_capacity or 1)
        self._subscribers.append(live_queue)
        return ExecProcessEventReceiver(list(self._events), live_queue)

    def retained_len(self) -> int:
        return len(self._events)

    def retained_bytes(self) -> int:
        return self._retained_bytes


@dataclass(frozen=True)
class StartedExecProcess:
    process: "ExecProcess"


class ExecProcess:
    def process_id(self) -> ProcessId:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    def subscribe_wake(self) -> Any:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    def subscribe_events(self) -> ExecProcessEventReceiver:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    async def write(self, chunk: bytes) -> WriteResponse:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    async def terminate(self) -> None:
        raise NotImplementedError("codex-exec-server process runtime is not ported")


class ExecBackend:
    async def start(self, params: ExecParams) -> StartedExecProcess:
        raise NotImplementedError("codex-exec-server process runtime is not ported")


PROCESS_EVENT_CHANNEL_CAPACITY = 256
PROCESS_EVENT_RETAINED_BYTES = 1024 * 1024
HTTP_BODY_DELTA_CHANNEL_CAPACITY = 256


class HttpResponseBodyStream:
    def __init__(
        self,
        client: "ExecServerClient | None" = None,
        request_id: str | None = None,
        rx: asyncio.Queue[HttpRequestBodyDeltaNotification | None] | None = None,
        *,
        local_chunks: list[bytes] | None = None,
        local_error: str | None = None,
    ) -> None:
        self.client = client
        self.request_id = request_id
        self.rx = rx
        self.local_chunks = deque(local_chunks or [])
        self.local_error = local_error
        self.next_seq = 1
        self.pending_eof = False
        self.closed = False

    @classmethod
    def local(
        cls,
        chunks: list[bytes] | tuple[bytes, ...],
        *,
        error: str | None = None,
    ) -> "HttpResponseBodyStream":
        return cls(local_chunks=[bytes(chunk) for chunk in chunks], local_error=error)

    @classmethod
    def remote(
        cls,
        client: "ExecServerClient",
        request_id: str,
        rx: asyncio.Queue[HttpRequestBodyDeltaNotification | None],
    ) -> "HttpResponseBodyStream":
        return cls(client, request_id, rx)

    async def recv(self) -> bytes | None:
        if self.client is None:
            if self.local_chunks:
                return self.local_chunks.popleft()
            if self.local_error is not None:
                error = self.local_error
                self.local_error = None
                raise ExecServerError.http_request(error)
            return None

        if self.pending_eof:
            self.pending_eof = False
            await self._finish()
            return None

        if self.rx is None or self.request_id is None:
            raise ExecServerError.protocol("http response stream is not registered")
        delta = await self.rx.get()
        if delta is None:
            await self._finish()
            failure = self.client.take_http_body_stream_failure(self.request_id)
            if failure is not None:
                raise ExecServerError.protocol(
                    f"http response stream `{self.request_id}` failed: {failure}"
                )
            return None

        if delta.seq != self.next_seq:
            await self._finish()
            raise ExecServerError.protocol(
                f"http response stream `{self.request_id}` received seq {delta.seq}, expected {self.next_seq}"
            )
        self.next_seq += 1
        chunk = delta.delta.into_inner()

        if delta.error is not None:
            await self._finish()
            raise ExecServerError.protocol(
                f"http response stream `{self.request_id}` failed: {delta.error}"
            )
        if delta.done:
            await self._finish()
            if not chunk:
                return None
            self.pending_eof = True
        return chunk

    async def _finish(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.client is not None and self.request_id is not None:
            await self.client.remove_http_body_stream(self.request_id)

    def __del__(self) -> None:
        if self.closed:
            return
        if self.client is None or self.request_id is None:
            self.closed = True
            return
        self.closed = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.client.remove_http_body_stream(self.request_id))


class ClientSessionState:
    def __init__(self) -> None:
        self.wake_queue: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
        self.wake_value = 0
        self.events = ExecProcessEventLog.new(PROCESS_EVENT_CHANNEL_CAPACITY, PROCESS_EVENT_RETAINED_BYTES)
        self.last_published_seq = 0
        self.pending_events: dict[int, ExecProcessEvent] = {}
        self.failure: str | None = None

    def subscribe_wake(self) -> asyncio.Queue[int]:
        return self.wake_queue

    def subscribe_events(self) -> ExecProcessEventReceiver:
        return self.events.subscribe()

    def note_change(self, seq: int) -> None:
        self.wake_value = max(self.wake_value, seq)
        _put_latest_nowait(self.wake_queue, self.wake_value)

    def publish_ordered_event(self, event: ExecProcessEvent) -> bool:
        seq = event.seq()
        if seq is None:
            self.events.publish(event)
            return False
        if seq <= self.last_published_seq:
            return False
        self.pending_events.setdefault(seq, event)
        ready: list[ExecProcessEvent] = []
        while True:
            next_seq = self.last_published_seq + 1
            next_event = self.pending_events.pop(next_seq, None)
            if next_event is None:
                break
            self.last_published_seq = next_seq
            ready.append(next_event)
        published_closed = False
        for ready_event in ready:
            published_closed = published_closed or ready_event.kind == "closed"
            self.events.publish(ready_event)
        return published_closed

    def set_failure(self, message: str) -> None:
        should_publish = self.failure is None
        if should_publish:
            self.failure = message
        self.wake_value += 1
        _put_latest_nowait(self.wake_queue, self.wake_value)
        if should_publish:
            self.publish_ordered_event(ExecProcessEvent.failed(message))

    def failed_response(self) -> ReadResponse | None:
        if self.failure is None:
            return None
        return self.synthesized_failure(self.failure)

    def synthesized_failure(self, message: str) -> ReadResponse:
        return ReadResponse(
            chunks=[],
            next_seq=self.wake_value + 1,
            exited=True,
            exit_code=None,
            closed=True,
            failure=message,
        )


class ClientSession(ExecProcess):
    def __init__(self, client: "ExecServerClient", process_id: ProcessId, state: ClientSessionState) -> None:
        self.client = client
        self._process_id = process_id
        self.state = state

    def process_id(self) -> ProcessId:
        return self._process_id

    def subscribe_wake(self) -> asyncio.Queue[int]:
        return self.state.subscribe_wake()

    def subscribe_events(self) -> ExecProcessEventReceiver:
        return self.state.subscribe_events()

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        failed = self.state.failed_response()
        if failed is not None:
            return failed
        return await self.client.read(ReadParams(self._process_id, after_seq, max_bytes, wait_ms))

    async def write(self, chunk: bytes) -> WriteResponse:
        return await self.client.write(self._process_id, chunk)

    async def terminate(self) -> None:
        await self.client.terminate(self._process_id)

    async def unregister(self) -> None:
        await self.client.unregister_session(self._process_id)


def _byte_chunk_len(chunk: ByteChunk | bytes | bytearray | memoryview | Any) -> int:
    if isinstance(chunk, ByteChunk):
        return len(chunk.data)
    try:
        return len(chunk)
    except TypeError:
        inner = getattr(chunk, "data", b"")
        return len(inner)


@dataclass(frozen=True)
class FsReadFileParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsReadFileResponse:
    data_base64: str


@dataclass(frozen=True)
class FsWriteFileParams:
    path: str
    data_base64: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsWriteFileResponse:
    pass


@dataclass(frozen=True)
class FsCreateDirectoryParams:
    path: str
    recursive: bool | None = None
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsCreateDirectoryResponse:
    pass


@dataclass(frozen=True)
class FsGetMetadataParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsGetMetadataResponse:
    is_directory: bool
    is_file: bool
    is_symlink: bool
    created_at_ms: int
    modified_at_ms: int


@dataclass(frozen=True)
class FsReadDirectoryParams:
    path: str
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsReadDirectoryEntry:
    file_name: str
    is_directory: bool
    is_file: bool


@dataclass(frozen=True)
class FsReadDirectoryResponse:
    entries: list[FsReadDirectoryEntry]


@dataclass(frozen=True)
class FsRemoveParams:
    path: str
    recursive: bool | None = None
    force: bool | None = None
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsRemoveResponse:
    pass


@dataclass(frozen=True)
class FsCopyParams:
    source_path: str
    destination_path: str
    recursive: bool
    sandbox: Any | None = None


@dataclass(frozen=True)
class FsCopyResponse:
    pass


@dataclass(frozen=True)
class CopyOptions:
    recursive: bool


@dataclass(frozen=True)
class CreateDirectoryOptions:
    recursive: bool


@dataclass(frozen=True)
class RemoveOptions:
    recursive: bool
    force: bool


@dataclass(frozen=True)
class FileMetadata:
    is_directory: bool
    is_file: bool
    is_symlink: bool
    created_at_ms: int
    modified_at_ms: int


@dataclass(frozen=True)
class ReadDirectoryEntry:
    file_name: str
    is_directory: bool
    is_file: bool


class ExecutorFileSystem:
    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        raise NotImplementedError("executor filesystem read_file is not implemented")

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        raise NotImplementedError("executor filesystem write_file is not implemented")

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        raise NotImplementedError("executor filesystem create_directory is not implemented")

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        raise NotImplementedError("executor filesystem get_metadata is not implemented")

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        raise NotImplementedError("executor filesystem read_directory is not implemented")

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        raise NotImplementedError("executor filesystem remove is not implemented")

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        raise NotImplementedError("executor filesystem copy is not implemented")


class DirectFileSystem(ExecutorFileSystem):
    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        _reject_sandbox_context(sandbox)
        path = _fs_path(path)
        if path.stat().st_size > MAX_READ_FILE_BYTES:
            raise ValueError(f"file is too large to read: limit is {MAX_READ_FILE_BYTES} bytes")
        return path.read_bytes()

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        _reject_sandbox_context(sandbox)
        _fs_path(path).write_bytes(bytes(contents))

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_sandbox_context(sandbox)
        _fs_path(path).mkdir(parents=options.recursive, exist_ok=options.recursive)

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        _reject_sandbox_context(sandbox)
        path = _fs_path(path)
        metadata = path.stat()
        return FileMetadata(
            is_directory=path.is_dir(),
            is_file=path.is_file(),
            is_symlink=path.is_symlink(),
            created_at_ms=_system_time_to_unix_ms(metadata.st_ctime),
            modified_at_ms=_system_time_to_unix_ms(metadata.st_mtime),
        )

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        _reject_sandbox_context(sandbox)
        entries: list[ReadDirectoryEntry] = []
        for entry in _fs_path(path).iterdir():
            try:
                metadata = entry.stat()
            except OSError:
                continue
            entries.append(
                ReadDirectoryEntry(
                    file_name=entry.name,
                    is_directory=entry.is_dir(),
                    is_file=metadata is not None and entry.is_file(),
                )
            )
        return entries

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_sandbox_context(sandbox)
        _remove_path(_fs_path(path), recursive=options.recursive, force=options.force)

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_sandbox_context(sandbox)
        _copy_path(_fs_path(source_path), _fs_path(destination_path), recursive=options.recursive)


class UnsandboxedFileSystem(ExecutorFileSystem):
    def __init__(self, file_system: DirectFileSystem | None = None) -> None:
        self.file_system = file_system or DirectFileSystem()

    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        _reject_platform_sandbox_context(sandbox)
        return await self.file_system.read_file(path, None)

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        _reject_platform_sandbox_context(sandbox)
        await self.file_system.write_file(path, contents, None)

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_platform_sandbox_context(sandbox)
        await self.file_system.create_directory(path, options, None)

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        _reject_platform_sandbox_context(sandbox)
        return await self.file_system.get_metadata(path, None)

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        _reject_platform_sandbox_context(sandbox)
        return await self.file_system.read_directory(path, None)

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_platform_sandbox_context(sandbox)
        await self.file_system.remove(path, options, None)

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_platform_sandbox_context(sandbox)
        await self.file_system.copy(source_path, destination_path, options, None)


class SandboxedFileSystem(ExecutorFileSystem):
    def __init__(self, sandbox_runner: Any) -> None:
        self.sandbox_runner = sandbox_runner

    @classmethod
    def new(cls, runtime_paths: "ExecServerRuntimePaths") -> "SandboxedFileSystem":
        return cls(FileSystemSandboxRunner.new(runtime_paths))

    async def run_sandboxed(
        self,
        sandbox: Any,
        request: FsHelperRequest,
    ) -> FsHelperPayload:
        payload = await _maybe_await(self.sandbox_runner.run(sandbox, request))
        if isinstance(payload, JSONRPCErrorError):
            raise map_sandbox_error(payload)
        if not isinstance(payload, FsHelperPayload):
            raise TypeError("sandbox runner returned an invalid fs helper payload")
        return payload

    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(sandbox, FsHelperRequest.read_file(FsReadFileParams(str(_fs_path(path)))))
        response = payload.expect_read_file()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)
        try:
            return base64.b64decode(response.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise OSError(f"fs/readFile returned invalid base64 dataBase64: {exc}") from exc

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.write_file(
                FsWriteFileParams(str(_fs_path(path)), base64.b64encode(bytes(contents)).decode("ascii"))
            ),
        )
        response = payload.expect_write_file()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.create_directory(
                FsCreateDirectoryParams(str(_fs_path(path)), recursive=options.recursive, sandbox=None)
            ),
        )
        response = payload.expect_create_directory()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.get_metadata(FsGetMetadataParams(str(_fs_path(path)), sandbox=None)),
        )
        response = payload.expect_get_metadata()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)
        return FileMetadata(
            is_directory=response.is_directory,
            is_file=response.is_file,
            is_symlink=response.is_symlink,
            created_at_ms=response.created_at_ms,
            modified_at_ms=response.modified_at_ms,
        )

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.read_directory(FsReadDirectoryParams(str(_fs_path(path)), sandbox=None)),
        )
        response = payload.expect_read_directory()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)
        return [
            ReadDirectoryEntry(
                file_name=entry.file_name,
                is_directory=entry.is_directory,
                is_file=entry.is_file,
            )
            for entry in response.entries
        ]

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.remove(
                FsRemoveParams(
                    str(_fs_path(path)),
                    recursive=options.recursive,
                    force=options.force,
                    sandbox=None,
                )
            ),
        )
        response = payload.expect_remove()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.copy(
                FsCopyParams(
                    str(_fs_path(source_path)),
                    str(_fs_path(destination_path)),
                    recursive=options.recursive,
                    sandbox=None,
                )
            ),
        )
        response = payload.expect_copy()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)


class LocalFileSystem(ExecutorFileSystem):
    def __init__(
        self,
        unsandboxed: UnsandboxedFileSystem | None = None,
        sandboxed: ExecutorFileSystem | None = None,
    ) -> None:
        self.unsandboxed = unsandboxed or UnsandboxedFileSystem()
        self.sandboxed = sandboxed

    @classmethod
    def unsandboxed_fs(cls) -> "LocalFileSystem":
        return cls()

    @classmethod
    def unsandboxed(cls) -> "LocalFileSystem":
        return cls()

    @classmethod
    def with_runtime_paths(cls, runtime_paths: "ExecServerRuntimePaths") -> "LocalFileSystem":
        return cls(sandboxed=SandboxedFileSystem.new(runtime_paths))

    def file_system_for(self, sandbox: Any | None = None) -> tuple[ExecutorFileSystem, Any | None]:
        if _sandbox_should_run_in_sandbox(sandbox):
            if self.sandboxed is None:
                raise ValueError("sandboxed filesystem operations require configured runtime paths")
            return self.sandboxed, sandbox
        return self.unsandboxed, sandbox

    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        file_system, sandbox = self.file_system_for(sandbox)
        return await file_system.read_file(path, sandbox)

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        file_system, sandbox = self.file_system_for(sandbox)
        await file_system.write_file(path, contents, sandbox)

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        file_system, sandbox = self.file_system_for(sandbox)
        await file_system.create_directory(path, options, sandbox)

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        file_system, sandbox = self.file_system_for(sandbox)
        return await file_system.get_metadata(path, sandbox)

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        file_system, sandbox = self.file_system_for(sandbox)
        return await file_system.read_directory(path, sandbox)

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        file_system, sandbox = self.file_system_for(sandbox)
        await file_system.remove(path, options, sandbox)

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        file_system, sandbox = self.file_system_for(sandbox)
        await file_system.copy(source_path, destination_path, options, sandbox)


class FileSystemHandler:
    def __init__(self, file_system: LocalFileSystem | None = None) -> None:
        self.file_system = file_system or LocalFileSystem.unsandboxed()

    @classmethod
    def new(cls, runtime_paths: "ExecServerRuntimePaths") -> "FileSystemHandler":
        return cls(LocalFileSystem.with_runtime_paths(runtime_paths))

    async def read_file(self, params: FsReadFileParams) -> FsReadFileResponse | JSONRPCErrorError:
        try:
            data = await self.file_system.read_file(params.path, params.sandbox)
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsReadFileResponse(data_base64=base64.b64encode(data).decode("ascii"))

    async def write_file(self, params: FsWriteFileParams) -> FsWriteFileResponse | JSONRPCErrorError:
        try:
            data = base64.b64decode(params.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            return invalid_request(f"{FS_WRITE_FILE_METHOD} requires valid base64 dataBase64: {exc}")
        try:
            await self.file_system.write_file(params.path, data, params.sandbox)
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsWriteFileResponse()

    async def create_directory(
        self,
        params: FsCreateDirectoryParams,
    ) -> FsCreateDirectoryResponse | JSONRPCErrorError:
        try:
            await self.file_system.create_directory(
                params.path,
                CreateDirectoryOptions(recursive=True if params.recursive is None else params.recursive),
                params.sandbox,
            )
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsCreateDirectoryResponse()

    async def get_metadata(self, params: FsGetMetadataParams) -> FsGetMetadataResponse | JSONRPCErrorError:
        try:
            metadata = await self.file_system.get_metadata(params.path, params.sandbox)
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsGetMetadataResponse(
            is_directory=metadata.is_directory,
            is_file=metadata.is_file,
            is_symlink=metadata.is_symlink,
            created_at_ms=metadata.created_at_ms,
            modified_at_ms=metadata.modified_at_ms,
        )

    async def read_directory(
        self,
        params: FsReadDirectoryParams,
    ) -> FsReadDirectoryResponse | JSONRPCErrorError:
        try:
            entries = await self.file_system.read_directory(params.path, params.sandbox)
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsReadDirectoryResponse(
            [
                FsReadDirectoryEntry(
                    file_name=entry.file_name,
                    is_directory=entry.is_directory,
                    is_file=entry.is_file,
                )
                for entry in entries
            ]
        )

    async def remove(self, params: FsRemoveParams) -> FsRemoveResponse | JSONRPCErrorError:
        try:
            await self.file_system.remove(
                params.path,
                RemoveOptions(
                    recursive=True if params.recursive is None else params.recursive,
                    force=True if params.force is None else params.force,
                ),
                params.sandbox,
            )
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsRemoveResponse()

    async def copy(self, params: FsCopyParams) -> FsCopyResponse | JSONRPCErrorError:
        try:
            await self.file_system.copy(
                params.source_path,
                params.destination_path,
                CopyOptions(recursive=params.recursive),
                params.sandbox,
            )
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsCopyResponse()


_FS_REQUEST_PARAM_TYPES = {
    FS_READ_FILE_METHOD: FsReadFileParams,
    FS_WRITE_FILE_METHOD: FsWriteFileParams,
    FS_CREATE_DIRECTORY_METHOD: FsCreateDirectoryParams,
    FS_GET_METADATA_METHOD: FsGetMetadataParams,
    FS_READ_DIRECTORY_METHOD: FsReadDirectoryParams,
    FS_REMOVE_METHOD: FsRemoveParams,
    FS_COPY_METHOD: FsCopyParams,
}


_FS_RESPONSE_TYPES = {
    FS_READ_FILE_METHOD: FsReadFileResponse,
    FS_WRITE_FILE_METHOD: FsWriteFileResponse,
    FS_CREATE_DIRECTORY_METHOD: FsCreateDirectoryResponse,
    FS_GET_METADATA_METHOD: FsGetMetadataResponse,
    FS_READ_DIRECTORY_METHOD: FsReadDirectoryResponse,
    FS_REMOVE_METHOD: FsRemoveResponse,
    FS_COPY_METHOD: FsCopyResponse,
}


@dataclass(frozen=True)
class FsHelperRequest:
    operation: str
    params: Any

    @classmethod
    def read_file(cls, params: FsReadFileParams) -> "FsHelperRequest":
        return cls(FS_READ_FILE_METHOD, params)

    @classmethod
    def write_file(cls, params: FsWriteFileParams) -> "FsHelperRequest":
        return cls(FS_WRITE_FILE_METHOD, params)

    @classmethod
    def create_directory(cls, params: FsCreateDirectoryParams) -> "FsHelperRequest":
        return cls(FS_CREATE_DIRECTORY_METHOD, params)

    @classmethod
    def get_metadata(cls, params: FsGetMetadataParams) -> "FsHelperRequest":
        return cls(FS_GET_METADATA_METHOD, params)

    @classmethod
    def read_directory(cls, params: FsReadDirectoryParams) -> "FsHelperRequest":
        return cls(FS_READ_DIRECTORY_METHOD, params)

    @classmethod
    def remove(cls, params: FsRemoveParams) -> "FsHelperRequest":
        return cls(FS_REMOVE_METHOD, params)

    @classmethod
    def copy(cls, params: FsCopyParams) -> "FsHelperRequest":
        return cls(FS_COPY_METHOD, params)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FsHelperRequest":
        operation = str(value["operation"])
        param_type = _FS_REQUEST_PARAM_TYPES.get(operation)
        if param_type is None:
            raise ValueError(f"unsupported fs helper operation: {operation}")
        return cls(operation, _fs_dataclass_from_mapping(param_type, value.get("params", {})))

    def to_mapping(self) -> dict[str, Any]:
        return {"operation": self.operation, "params": _fs_dataclass_to_camel_mapping(self.params)}


@dataclass(frozen=True)
class FsHelperPayload:
    operation: str
    response: Any

    @classmethod
    def read_file(cls, response: FsReadFileResponse) -> "FsHelperPayload":
        return cls(FS_READ_FILE_METHOD, response)

    @classmethod
    def write_file(cls, response: FsWriteFileResponse) -> "FsHelperPayload":
        return cls(FS_WRITE_FILE_METHOD, response)

    @classmethod
    def create_directory(cls, response: FsCreateDirectoryResponse) -> "FsHelperPayload":
        return cls(FS_CREATE_DIRECTORY_METHOD, response)

    @classmethod
    def get_metadata(cls, response: FsGetMetadataResponse) -> "FsHelperPayload":
        return cls(FS_GET_METADATA_METHOD, response)

    @classmethod
    def read_directory(cls, response: FsReadDirectoryResponse) -> "FsHelperPayload":
        return cls(FS_READ_DIRECTORY_METHOD, response)

    @classmethod
    def remove(cls, response: FsRemoveResponse) -> "FsHelperPayload":
        return cls(FS_REMOVE_METHOD, response)

    @classmethod
    def copy(cls, response: FsCopyResponse) -> "FsHelperPayload":
        return cls(FS_COPY_METHOD, response)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FsHelperPayload":
        operation = str(value["operation"])
        response_type = _FS_RESPONSE_TYPES.get(operation)
        if response_type is None:
            raise ValueError(f"unsupported fs helper operation: {operation}")
        return cls(operation, _fs_dataclass_from_mapping(response_type, value.get("response", {})))

    def to_mapping(self) -> dict[str, Any]:
        return {"operation": self.operation, "response": _fs_dataclass_to_camel_mapping(self.response)}

    def expect_read_file(self) -> FsReadFileResponse | JSONRPCErrorError:
        return self._expect(FS_READ_FILE_METHOD)

    def expect_write_file(self) -> FsWriteFileResponse | JSONRPCErrorError:
        return self._expect(FS_WRITE_FILE_METHOD)

    def expect_create_directory(self) -> FsCreateDirectoryResponse | JSONRPCErrorError:
        return self._expect(FS_CREATE_DIRECTORY_METHOD)

    def expect_get_metadata(self) -> FsGetMetadataResponse | JSONRPCErrorError:
        return self._expect(FS_GET_METADATA_METHOD)

    def expect_read_directory(self) -> FsReadDirectoryResponse | JSONRPCErrorError:
        return self._expect(FS_READ_DIRECTORY_METHOD)

    def expect_remove(self) -> FsRemoveResponse | JSONRPCErrorError:
        return self._expect(FS_REMOVE_METHOD)

    def expect_copy(self) -> FsCopyResponse | JSONRPCErrorError:
        return self._expect(FS_COPY_METHOD)

    def _expect(self, expected: str) -> Any | JSONRPCErrorError:
        if self.operation == expected:
            return self.response
        return unexpected_response(expected, self.operation)


@dataclass(frozen=True)
class FsHelperResponse:
    status: str
    payload: FsHelperPayload | JSONRPCErrorError

    @classmethod
    def ok(cls, payload: FsHelperPayload) -> "FsHelperResponse":
        return cls("ok", payload)

    @classmethod
    def error(cls, error: JSONRPCErrorError) -> "FsHelperResponse":
        return cls("error", error)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FsHelperResponse":
        status = str(value["status"])
        payload = value.get("payload", {})
        if status == "ok":
            return cls.ok(FsHelperPayload.from_mapping(payload))
        if status == "error":
            return cls.error(JSONRPCErrorError.from_mapping(payload))
        raise ValueError(f"unsupported fs helper response status: {status}")

    def to_mapping(self) -> dict[str, Any]:
        if self.status == "ok":
            return {"status": "ok", "payload": self.payload.to_mapping()}  # type: ignore[union-attr]
        return {"status": "error", "payload": self.payload.to_mapping()}  # type: ignore[union-attr]


def unexpected_response(expected: str, actual: str) -> JSONRPCErrorError:
    return internal_error(f"unexpected fs sandbox helper response: expected {expected}, got {actual}")


async def run_direct_request(request: FsHelperRequest) -> FsHelperPayload | JSONRPCErrorError:
    try:
        return _run_direct_request_sync(request)
    except Exception as exc:
        return map_fs_error(exc)


async def run_fs_helper_once(input_bytes: bytes) -> bytes:
    request_mapping = json.loads(input_bytes)
    request = FsHelperRequest.from_mapping(request_mapping)
    result = await run_direct_request(request)
    if isinstance(result, JSONRPCErrorError):
        response = FsHelperResponse.error(result)
    else:
        response = FsHelperResponse.ok(result)
    return json.dumps(response.to_mapping(), separators=(",", ":")).encode("utf-8") + b"\n"


def run_fs_helper_main(input_stream: Any | None = None, output_stream: Any | None = None, error_stream: Any | None = None) -> None:
    input_stream = input_stream or sys.stdin.buffer
    output_stream = output_stream or sys.stdout.buffer
    error_stream = error_stream or sys.stderr
    try:
        input_data = input_stream.read()
        if isinstance(input_data, str):
            input_data = input_data.encode("utf-8")
        output_data = asyncio.run(run_fs_helper_once(input_data))
        if hasattr(output_stream, "buffer"):
            output_stream = output_stream.buffer
        try:
            output_stream.write(output_data)
        except TypeError:
            output_stream.write(output_data.decode("utf-8"))
        output_stream.flush()
    except Exception as exc:
        print(f"fs sandbox helper failed: {exc}", file=error_stream)
        raise SystemExit(1) from exc
    raise SystemExit(0)


def _run_direct_request_sync(request: FsHelperRequest) -> FsHelperPayload:
    operation = request.operation
    params = request.params
    if operation == FS_READ_FILE_METHOD:
        _reject_sandbox_context(params.sandbox)
        path = Path(params.path)
        if path.stat().st_size > MAX_READ_FILE_BYTES:
            raise ValueError(f"file is too large to read: limit is {MAX_READ_FILE_BYTES} bytes")
        data = path.read_bytes()
        return FsHelperPayload.read_file(FsReadFileResponse(data_base64=base64.b64encode(data).decode("ascii")))
    if operation == FS_WRITE_FILE_METHOD:
        _reject_sandbox_context(params.sandbox)
        try:
            data = base64.b64decode(params.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"{FS_WRITE_FILE_METHOD} requires valid base64 dataBase64: {exc}") from exc
        Path(params.path).write_bytes(data)
        return FsHelperPayload.write_file(FsWriteFileResponse())
    if operation == FS_CREATE_DIRECTORY_METHOD:
        _reject_sandbox_context(params.sandbox)
        recursive = True if params.recursive is None else params.recursive
        Path(params.path).mkdir(parents=recursive, exist_ok=recursive)
        return FsHelperPayload.create_directory(FsCreateDirectoryResponse())
    if operation == FS_GET_METADATA_METHOD:
        _reject_sandbox_context(params.sandbox)
        path = Path(params.path)
        metadata = path.stat()
        return FsHelperPayload.get_metadata(
            FsGetMetadataResponse(
                is_directory=path.is_dir(),
                is_file=path.is_file(),
                is_symlink=path.is_symlink(),
                created_at_ms=int(metadata.st_ctime * 1000),
                modified_at_ms=int(metadata.st_mtime * 1000),
            )
        )
    if operation == FS_READ_DIRECTORY_METHOD:
        _reject_sandbox_context(params.sandbox)
        entries: list[FsReadDirectoryEntry] = []
        for entry in Path(params.path).iterdir():
            try:
                entry_metadata = entry.stat()
            except OSError:
                continue
            entries.append(
                FsReadDirectoryEntry(
                    file_name=entry.name,
                    is_directory=entry.is_dir(),
                    is_file=entry_metadata is not None and entry.is_file(),
                )
            )
        return FsHelperPayload.read_directory(FsReadDirectoryResponse(entries))
    if operation == FS_REMOVE_METHOD:
        _reject_sandbox_context(params.sandbox)
        _remove_path(Path(params.path), recursive=True if params.recursive is None else params.recursive, force=True if params.force is None else params.force)
        return FsHelperPayload.remove(FsRemoveResponse())
    if operation == FS_COPY_METHOD:
        _reject_sandbox_context(params.sandbox)
        _copy_path(Path(params.source_path), Path(params.destination_path), recursive=params.recursive)
        return FsHelperPayload.copy(FsCopyResponse())
    raise ValueError(f"unsupported fs helper operation: {operation}")


def map_fs_error(err: BaseException) -> JSONRPCErrorError:
    if isinstance(err, FileNotFoundError):
        return not_found(err)
    if isinstance(err, (ValueError, PermissionError)):
        return invalid_request(err)
    err_no = getattr(err, "errno", None)
    if err_no in {errno.EINVAL, errno.EACCES, errno.EPERM}:
        return invalid_request(err)
    return internal_error(err)


def _reject_sandbox_context(sandbox: Any | None) -> None:
    if sandbox is not None:
        raise ValueError("direct filesystem operations do not accept sandbox context")


def _reject_platform_sandbox_context(sandbox: Any | None) -> None:
    if _sandbox_should_run_in_sandbox(sandbox):
        raise ValueError("sandboxed filesystem operations require configured runtime paths")


def _require_platform_sandbox(sandbox: Any | None) -> Any:
    if not _sandbox_should_run_in_sandbox(sandbox):
        raise ValueError(
            "sandboxed filesystem operations require ReadOnly or WorkspaceWrite sandbox policy"
        )
    return sandbox


def _sandbox_should_run_in_sandbox(sandbox: Any | None) -> bool:
    if sandbox is None:
        return False
    should_run = getattr(sandbox, "should_run_in_sandbox", None)
    if callable(should_run):
        return bool(should_run())
    return bool(getattr(sandbox, "run_in_sandbox", False))


def map_sandbox_error(error: JSONRPCErrorError) -> OSError:
    if error.code == -32004:
        return FileNotFoundError(error.message)
    if error.code == -32600:
        return ValueError(error.message)
    return OSError(error.message)


def _remove_path(path: Path, *, recursive: bool, force: bool) -> None:
    try:
        metadata_is_dir = path.is_dir() and not path.is_symlink()
    except OSError:
        metadata_is_dir = False
    if not path.exists() and not path.is_symlink():
        if force:
            return
        raise FileNotFoundError(path)
    if metadata_is_dir:
        if recursive:
            shutil.rmtree(path)
        else:
            path.rmdir()
    else:
        path.unlink()


def _copy_path(source_path: Path, destination_path: Path, *, recursive: bool) -> None:
    if source_path.is_dir() and not source_path.is_symlink():
        if not recursive:
            raise ValueError("fs/copy requires recursive: true when sourcePath is a directory")
        source_resolved = source_path.resolve()
        destination_existing = _resolve_existing_path(destination_path)
        if destination_existing == source_resolved or source_resolved in destination_existing.parents:
            raise ValueError("fs/copy cannot copy a directory to itself or one of its descendants")
        _copy_dir_recursive(source_path, destination_path)
        return
    if source_path.is_symlink():
        target = os.readlink(source_path)
        os.symlink(target, destination_path, target_is_directory=source_path.is_dir())
        return
    if source_path.is_file():
        shutil.copyfile(source_path, destination_path)
        return
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    raise ValueError("fs/copy only supports regular files, directories, and symlinks")


def _copy_dir_recursive(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target_path = target / entry.name
        if entry.is_dir() and not entry.is_symlink():
            _copy_dir_recursive(entry, target_path)
        elif entry.is_symlink():
            os.symlink(os.readlink(entry), target_path, target_is_directory=entry.is_dir())
        elif entry.is_file():
            shutil.copyfile(entry, target_path)


def _resolve_existing_path(path: Path) -> Path:
    existing = path
    unresolved: list[Path] = []
    while not existing.exists():
        if existing.name == "":
            break
        unresolved.append(Path(existing.name))
        parent = existing.parent
        if parent == existing:
            break
        existing = parent
    resolved = existing.resolve()
    for item in reversed(unresolved):
        resolved = resolved / item
    return resolved


def resolve_existing_path(path: str | Path | AbsolutePathBuf) -> Path:
    return _resolve_existing_path(_fs_path(path))


def current_sandbox_cwd() -> Path:
    try:
        cwd = Path.cwd()
    except OSError as exc:
        raise OSError(f"failed to read current dir: {exc}") from exc
    return resolve_existing_path(cwd)


def _fs_path(path: str | Path | AbsolutePathBuf) -> Path:
    if isinstance(path, AbsolutePathBuf):
        return path.as_path()
    return Path(path)


def _system_time_to_unix_ms(seconds: float) -> int:
    if seconds < 0:
        return 0
    return int(seconds * 1000)


def _fs_dataclass_from_mapping(cls: type, value: dict[str, Any]) -> Any:
    if cls is FsReadFileParams:
        return cls(path=value["path"], sandbox=value.get("sandbox"))
    if cls is FsWriteFileParams:
        return cls(path=value["path"], data_base64=value.get("dataBase64", value.get("data_base64", "")), sandbox=value.get("sandbox"))
    if cls is FsCreateDirectoryParams:
        return cls(path=value["path"], recursive=value.get("recursive"), sandbox=value.get("sandbox"))
    if cls is FsGetMetadataParams:
        return cls(path=value["path"], sandbox=value.get("sandbox"))
    if cls is FsReadDirectoryParams:
        return cls(path=value["path"], sandbox=value.get("sandbox"))
    if cls is FsRemoveParams:
        return cls(path=value["path"], recursive=value.get("recursive"), force=value.get("force"), sandbox=value.get("sandbox"))
    if cls is FsCopyParams:
        return cls(
            source_path=value.get("sourcePath", value.get("source_path")),
            destination_path=value.get("destinationPath", value.get("destination_path")),
            recursive=value.get("recursive", False),
            sandbox=value.get("sandbox"),
        )
    if cls is FsReadFileResponse:
        return cls(data_base64=value.get("dataBase64", value.get("data_base64", "")))
    if cls in {FsWriteFileResponse, FsCreateDirectoryResponse, FsRemoveResponse, FsCopyResponse}:
        return cls()
    if cls is FsGetMetadataResponse:
        return cls(
            is_directory=value.get("isDirectory", value.get("is_directory")),
            is_file=value.get("isFile", value.get("is_file")),
            is_symlink=value.get("isSymlink", value.get("is_symlink")),
            created_at_ms=value.get("createdAtMs", value.get("created_at_ms")),
            modified_at_ms=value.get("modifiedAtMs", value.get("modified_at_ms")),
        )
    if cls is FsReadDirectoryResponse:
        return cls(entries=[_fs_dataclass_from_mapping(FsReadDirectoryEntry, item) for item in value.get("entries", [])])
    if cls is FsReadDirectoryEntry:
        return cls(
            file_name=value.get("fileName", value.get("file_name")),
            is_directory=value.get("isDirectory", value.get("is_directory")),
            is_file=value.get("isFile", value.get("is_file")),
        )
    raise TypeError(f"unsupported fs dataclass: {cls!r}")


def _fs_dataclass_to_camel_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, FsReadFileParams):
        return _without_none({"path": str(value.path), "sandbox": value.sandbox})
    if isinstance(value, FsWriteFileParams):
        return _without_none({"path": str(value.path), "dataBase64": value.data_base64, "sandbox": value.sandbox})
    if isinstance(value, FsCreateDirectoryParams):
        return _without_none({"path": str(value.path), "recursive": value.recursive, "sandbox": value.sandbox})
    if isinstance(value, FsGetMetadataParams):
        return _without_none({"path": str(value.path), "sandbox": value.sandbox})
    if isinstance(value, FsReadDirectoryParams):
        return _without_none({"path": str(value.path), "sandbox": value.sandbox})
    if isinstance(value, FsRemoveParams):
        return _without_none({"path": str(value.path), "recursive": value.recursive, "force": value.force, "sandbox": value.sandbox})
    if isinstance(value, FsCopyParams):
        return _without_none(
            {
                "sourcePath": str(value.source_path),
                "destinationPath": str(value.destination_path),
                "recursive": value.recursive,
                "sandbox": value.sandbox,
            }
        )
    if isinstance(value, FsReadFileResponse):
        return {"dataBase64": value.data_base64}
    if isinstance(value, (FsWriteFileResponse, FsCreateDirectoryResponse, FsRemoveResponse, FsCopyResponse)):
        return {}
    if isinstance(value, FsGetMetadataResponse):
        return {
            "isDirectory": value.is_directory,
            "isFile": value.is_file,
            "isSymlink": value.is_symlink,
            "createdAtMs": value.created_at_ms,
            "modifiedAtMs": value.modified_at_ms,
        }
    if isinstance(value, FsReadDirectoryResponse):
        return {"entries": [_fs_dataclass_to_camel_mapping(item) for item in value.entries]}
    if isinstance(value, FsReadDirectoryEntry):
        return {"fileName": value.file_name, "isDirectory": value.is_directory, "isFile": value.is_file}
    if isinstance(value, JSONRPCErrorError):
        return value.to_mapping()
    raise TypeError(f"unsupported fs dataclass value: {value!r}")


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


@dataclass(frozen=True)
class HttpHeader:
    name: str
    value: str


@dataclass(frozen=True)
class HttpRequestParams:
    method: str
    url: str
    headers: list[HttpHeader]
    request_id: str
    body: ByteChunk | None = None
    timeout_ms: int | None = None
    stream_response: bool = False


def decode_http_header(value: Any) -> HttpHeader:
    if not isinstance(value, Mapping):
        raise ValueError("HttpHeader must be a mapping")
    name = value.get("name")
    header_value = value.get("value")
    if not isinstance(name, str):
        raise ValueError("header name must be a string")
    if not isinstance(header_value, str):
        raise ValueError("header value must be a string")
    return HttpHeader(name=name, value=header_value)


def encode_http_header(value: HttpHeader) -> dict[str, Any]:
    return {"name": value.name, "value": value.value}


def decode_http_request_params(value: Any) -> HttpRequestParams:
    if not isinstance(value, Mapping):
        raise ValueError("HttpRequestParams must be a mapping")
    method = value.get("method")
    url = value.get("url")
    request_id = value.get("requestId")
    if not isinstance(method, str):
        raise ValueError("method must be a string")
    if not isinstance(url, str):
        raise ValueError("url must be a string")
    if not isinstance(request_id, str):
        raise ValueError("requestId must be a string")
    headers_value = value.get("headers", [])
    if not isinstance(headers_value, list):
        raise ValueError("headers must be a list")
    body_value = value.get("bodyBase64")
    if body_value is not None and not isinstance(body_value, str):
        raise ValueError("bodyBase64 must be a base64 string or null")
    stream_response = value.get("streamResponse", False)
    if not isinstance(stream_response, bool):
        raise ValueError("streamResponse must be a bool")
    return HttpRequestParams(
        method=method,
        url=url,
        headers=[decode_http_header(item) for item in headers_value],
        request_id=request_id,
        body=None if body_value is None else ByteChunk.from_base64(body_value),
        timeout_ms=_decode_optional_int(value.get("timeoutMs"), "timeoutMs"),
        stream_response=stream_response,
    )


@dataclass(frozen=True)
class HttpRequestResponse:
    status: int
    headers: list[HttpHeader]
    body: ByteChunk


def encode_http_request_response(value: HttpRequestResponse) -> dict[str, Any]:
    return {
        "status": value.status,
        "headers": [encode_http_header(header) for header in value.headers],
        "bodyBase64": value.body.to_base64(),
    }


@dataclass(frozen=True)
class HttpRequestBodyDeltaNotification:
    request_id: str
    seq: int
    delta: ByteChunk
    done: bool = False
    error: str | None = None


def decode_http_request_body_delta_notification(value: Any) -> HttpRequestBodyDeltaNotification:
    if isinstance(value, HttpRequestBodyDeltaNotification):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("http/request/bodyDelta params must be an object")
    request_id = value.get("requestId")
    if not isinstance(request_id, str):
        raise ValueError("http/request/bodyDelta requestId must be a string")
    seq = _decode_optional_int(value.get("seq"), "seq")
    if seq is None:
        raise ValueError("http/request/bodyDelta seq must be an integer")
    delta = value.get("deltaBase64")
    if not isinstance(delta, str):
        raise ValueError("http/request/bodyDelta deltaBase64 must be a base64 string")
    done = value.get("done", False)
    if not isinstance(done, bool):
        raise ValueError("http/request/bodyDelta done must be a boolean")
    error = value.get("error")
    if error is not None and not isinstance(error, str):
        raise ValueError("http/request/bodyDelta error must be a string")
    return HttpRequestBodyDeltaNotification(
        request_id=request_id,
        seq=seq,
        delta=ByteChunk.from_base64(delta),
        done=done,
        error=error,
    )


def encode_http_request_body_delta_notification(value: HttpRequestBodyDeltaNotification) -> dict[str, Any]:
    return _without_none(
        {
            "requestId": value.request_id,
            "seq": value.seq,
            "deltaBase64": value.delta.to_base64(),
            "done": value.done,
            "error": value.error,
        }
    )


@dataclass(frozen=True)
class ExecOutputDeltaNotification:
    process_id: ProcessId
    seq: int
    stream: ExecOutputStream
    chunk: ByteChunk


def encode_exec_output_delta_notification(value: ExecOutputDeltaNotification) -> dict[str, Any]:
    return {
        "processId": value.process_id.as_str(),
        "seq": value.seq,
        "stream": value.stream.value,
        "chunk": value.chunk.to_base64(),
    }


@dataclass(frozen=True)
class ExecExitedNotification:
    process_id: ProcessId
    seq: int
    exit_code: int


def encode_exec_exited_notification(value: ExecExitedNotification) -> dict[str, Any]:
    return {"processId": value.process_id.as_str(), "seq": value.seq, "exitCode": value.exit_code}


@dataclass(frozen=True)
class ExecClosedNotification:
    process_id: ProcessId
    seq: int


def encode_exec_closed_notification(value: ExecClosedNotification) -> dict[str, Any]:
    return {"processId": value.process_id.as_str(), "seq": value.seq}


@dataclass(frozen=True)
class FileSystemSandboxContext:
    permissions: PermissionProfile
    cwd: AbsolutePathBuf | None = None
    use_legacy_landlock: bool = False
    windows_sandbox_level: Any | None = None
    windows_sandbox_private_desktop: bool = False

    @classmethod
    def from_permission_profile(cls, permissions: PermissionProfile) -> "FileSystemSandboxContext":
        return cls(permissions=permissions)

    @classmethod
    def from_permission_profile_with_cwd(
        cls,
        permissions: PermissionProfile,
        cwd: AbsolutePathBuf | str | Path,
    ) -> "FileSystemSandboxContext":
        if not isinstance(cwd, AbsolutePathBuf):
            cwd = AbsolutePathBuf.from_absolute_path(cwd)
        return cls(permissions=permissions, cwd=cwd)

    def has_cwd_dependent_permissions(self) -> bool:
        policy = self.permissions.file_system_sandbox_policy()
        return any(_file_system_path_is_cwd_dependent(entry.path) for entry in policy.entries)

    def drop_cwd_if_unused(self) -> "FileSystemSandboxContext":
        if self.cwd is None or self.has_cwd_dependent_permissions():
            return self
        return FileSystemSandboxContext(
            permissions=self.permissions,
            cwd=None,
            use_legacy_landlock=self.use_legacy_landlock,
            windows_sandbox_level=self.windows_sandbox_level,
            windows_sandbox_private_desktop=self.windows_sandbox_private_desktop,
        )


@dataclass(frozen=True)
class ExecServerClientConnectOptions:
    client_name: str = "codex-core"
    initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
    resume_session_id: str | None = None

    @classmethod
    def from_remote(cls, value: "RemoteExecServerConnectArgs") -> "ExecServerClientConnectOptions":
        return cls(
            client_name=value.client_name,
            initialize_timeout=value.initialize_timeout,
            resume_session_id=value.resume_session_id,
        )

    @classmethod
    def from_stdio(cls, value: "StdioExecServerConnectArgs") -> "ExecServerClientConnectOptions":
        return cls(
            client_name=value.client_name,
            initialize_timeout=value.initialize_timeout,
            resume_session_id=value.resume_session_id,
        )


@dataclass(frozen=True)
class RemoteExecServerConnectArgs:
    websocket_url: str
    client_name: str
    connect_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT
    initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
    resume_session_id: str | None = None

    @classmethod
    def new(cls, websocket_url: str, client_name: str) -> "RemoteExecServerConnectArgs":
        return cls(websocket_url=websocket_url, client_name=client_name)

    def to_client_connect_options(self) -> ExecServerClientConnectOptions:
        return ExecServerClientConnectOptions.from_remote(self)


@dataclass(frozen=True)
class StdioExecServerCommand:
    program: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "program", str(self.program))
        object.__setattr__(self, "args", [str(arg) for arg in self.args])
        object.__setattr__(self, "env", {str(key): str(value) for key, value in self.env.items()})
        if self.cwd is not None and not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))


@dataclass(frozen=True)
class StdioExecServerConnectArgs:
    command: StdioExecServerCommand
    client_name: str
    initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
    resume_session_id: str | None = None

    def to_client_connect_options(self) -> ExecServerClientConnectOptions:
        return ExecServerClientConnectOptions.from_stdio(self)


@dataclass(frozen=True)
class EnvironmentToml:
    id: str
    url: str | None = None
    program: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: Path | None = None
    connect_timeout_sec: int | float | None = None
    initialize_timeout_sec: int | float | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "EnvironmentToml":
        _reject_unknown_fields(
            data,
            {
                "id",
                "url",
                "program",
                "args",
                "env",
                "cwd",
                "connect_timeout_sec",
                "initialize_timeout_sec",
            },
        )
        return cls(
            id=str(data.get("id", "")),
            url=_optional_str(data.get("url")),
            program=_optional_str(data.get("program")),
            args=_optional_str_list(data.get("args")),
            env=_optional_str_dict(data.get("env")),
            cwd=Path(data["cwd"]) if data.get("cwd") is not None else None,
            connect_timeout_sec=_optional_duration_seconds(data.get("connect_timeout_sec")),
            initialize_timeout_sec=_optional_duration_seconds(data.get("initialize_timeout_sec")),
        )


@dataclass(frozen=True)
class EnvironmentsToml:
    default: str | None = None
    include_local: bool | None = None
    environments: list[EnvironmentToml] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "EnvironmentsToml":
        _reject_unknown_fields(data, {"default", "include_local", "environments"})
        environments_raw = data.get("environments", [])
        if not isinstance(environments_raw, list):
            raise ExecServerError.protocol("environment config environments must be a list")
        include_local = data.get("include_local")
        if include_local is not None and not isinstance(include_local, bool):
            raise ExecServerError.protocol("environment config include_local must be a boolean")
        return cls(
            default=_optional_str(data.get("default")),
            include_local=include_local,
            environments=[EnvironmentToml.from_mapping(item) for item in environments_raw],
        )


@dataclass(frozen=True)
class TomlEnvironmentProvider:
    default: EnvironmentDefault
    include_local: bool
    environments: list[tuple[str, ExecServerTransportParams]]

    @classmethod
    def new(cls, config: EnvironmentsToml) -> "TomlEnvironmentProvider":
        return cls.new_with_config_dir(config, None)

    @classmethod
    def new_with_config_dir(
        cls,
        config: EnvironmentsToml,
        config_dir: str | Path | None,
    ) -> "TomlEnvironmentProvider":
        include_local = True if config.include_local is None else config.include_local
        ids: set[str] = set()
        if include_local:
            ids.add(LOCAL_ENVIRONMENT_ID)
        parsed_environments: list[tuple[str, ExecServerTransportParams]] = []
        config_dir_path = Path(config_dir) if config_dir is not None else None
        for item in config.environments:
            environment_id, transport = parse_environment_toml(item, config_dir_path)
            if environment_id in ids:
                raise ExecServerError.protocol(f"environment id `{environment_id}` is duplicated")
            ids.add(environment_id)
            parsed_environments.append((environment_id, transport))
        default = normalize_default_environment_id(config.default, include_local, ids)
        return cls(default=default, include_local=include_local, environments=parsed_environments)

    def snapshot(self) -> EnvironmentProviderSnapshot:
        return EnvironmentProviderSnapshot(
            environments=[
                (environment_id, Environment.remote_with_transport(transport, local_runtime_paths=None))
                for environment_id, transport in self.environments
            ],
            default=self.default,
            include_local=self.include_local,
        )


def parse_environment_toml(
    item: EnvironmentToml,
    config_dir: str | Path | None = None,
) -> tuple[str, ExecServerTransportParams]:
    validate_environment_id(item.id)
    if item.program is None and (item.args is not None or item.env is not None or item.cwd is not None):
        raise ExecServerError.protocol(f"environment `{item.id}` args, env, and cwd require program")
    if item.url is None and item.connect_timeout_sec is not None:
        raise ExecServerError.protocol(f"environment `{item.id}` connect_timeout_sec requires url")

    connect_timeout = (
        DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT
        if item.connect_timeout_sec is None
        else item.connect_timeout_sec
    )
    initialize_timeout = (
        DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
        if item.initialize_timeout_sec is None
        else item.initialize_timeout_sec
    )

    if item.url is not None and item.program is None:
        url = validate_websocket_url(item.url)
        return (
            item.id,
            ExecServerTransportParams.from_websocket_url(
                url,
                connect_timeout=connect_timeout,
                initialize_timeout=initialize_timeout,
            ),
        )
    if item.url is None and item.program is not None:
        program = item.program.strip()
        if not program:
            raise ExecServerError.protocol(f"environment `{item.id}` program cannot be empty")
        cwd = normalize_stdio_cwd(item.id, item.cwd, config_dir)
        return (
            item.id,
            ExecServerTransportParams.stdio_command(
                StdioExecServerCommand(
                    program=program,
                    args=item.args or [],
                    env=item.env or {},
                    cwd=cwd,
                ),
                initialize_timeout=initialize_timeout,
            ),
        )

    raise ExecServerError.protocol(f"environment `{item.id}` must set exactly one of url or program")


def normalize_stdio_cwd(
    environment_id: str,
    cwd: str | Path | None,
    config_dir: str | Path | None,
) -> Path | None:
    if cwd is None:
        return None
    cwd_path = cwd if isinstance(cwd, Path) else Path(cwd)
    if cwd_path.is_absolute():
        return cwd_path
    if config_dir is None:
        raise ExecServerError.protocol(f"environment `{environment_id}` cwd must be absolute")
    return Path(config_dir) / cwd_path


def normalize_default_environment_id(
    default: str | None,
    include_local: bool,
    ids: set[str],
) -> EnvironmentDefault:
    if default is None:
        if include_local:
            return EnvironmentDefault.environment_id_value(LOCAL_ENVIRONMENT_ID)
        return EnvironmentDefault.disabled()
    default = default.strip()
    if not default:
        raise ExecServerError.protocol("default environment id cannot be empty")
    if default.lower() != "none" and default not in ids:
        raise ExecServerError.protocol(f"default environment `{default}` is not configured")
    if default.lower() == "none":
        return EnvironmentDefault.disabled()
    return EnvironmentDefault.environment_id_value(default)


def validate_environment_id(environment_id: str) -> None:
    trimmed = environment_id.strip()
    if not trimmed:
        raise ExecServerError.protocol("environment id cannot be empty")
    if trimmed != environment_id:
        raise ExecServerError.protocol(
            f"environment id `{environment_id}` must not contain surrounding whitespace"
        )
    if environment_id == LOCAL_ENVIRONMENT_ID or environment_id.lower() == "none":
        raise ExecServerError.protocol(f"environment id `{environment_id}` is reserved")
    if len(environment_id) > MAX_ENVIRONMENT_ID_LEN:
        raise ExecServerError.protocol(
            f"environment id `{environment_id}` cannot be longer than {MAX_ENVIRONMENT_ID_LEN} characters"
        )
    if not all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in environment_id):
        raise ExecServerError.protocol(
            f"environment id `{environment_id}` must contain only ASCII letters, numbers, '-' or '_'"
        )


def validate_websocket_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ExecServerError.protocol("environment url cannot be empty")
    if not (url.startswith("ws://") or url.startswith("wss://")):
        raise ExecServerError.protocol(f"environment url `{url}` must use ws:// or wss://")
    # Rust validates with tungstenite's IntoClientRequest. For this dependency-
    # light port, require a non-empty network location after ws:// or wss://.
    rest = url.split("://", 1)[1]
    if not rest or rest.startswith("/") or rest.isspace():
        raise ExecServerError.protocol(f"environment url `{url}` is invalid: invalid URL")
    return url


def load_environments_toml(path: str | Path) -> EnvironmentsToml:
    path = Path(path)
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExecServerError.protocol(f"failed to read environment config `{path}`: {exc}") from exc
    try:
        data = tomllib.loads(contents)
    except tomllib.TOMLDecodeError as exc:
        raise ExecServerError.protocol(f"failed to parse environment config `{path}`: {exc}") from exc
    return EnvironmentsToml.from_mapping(data)


def environment_provider_from_codex_home(codex_home: str | Path) -> EnvironmentProvider | TomlEnvironmentProvider:
    codex_home = Path(codex_home)
    path = codex_home / ENVIRONMENTS_TOML_FILE
    try:
        exists = path.exists()
    except OSError as exc:
        raise ExecServerError.protocol(f"failed to inspect environment config `{path}`: {exc}") from exc
    if not exists:
        return DefaultEnvironmentProvider.from_env()
    environments = load_environments_toml(path)
    return TomlEnvironmentProvider.new_with_config_dir(environments, codex_home)


def _reject_unknown_fields(data: dict[str, Any], allowed: set[str]) -> None:
    unknown = next((key for key in data if key not in allowed), None)
    if unknown is not None:
        raise ExecServerError.protocol(f"unknown field `{unknown}`")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ExecServerError.protocol("environment config args must be a list")
    return [str(item) for item in value]


def _optional_str_dict(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ExecServerError.protocol("environment config env must be a table")
    return {str(key): str(item) for key, item in value.items()}


def _optional_duration_seconds(value: Any) -> int | float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ExecServerError.protocol("duration value must be a non-negative number of seconds")
    return value


@dataclass(frozen=True)
class FsSandboxExecRequest:
    argv: list[str]
    cwd: AbsolutePathBuf
    env: dict[str, str]
    arg0: str | None = None


@dataclass(frozen=True)
class FsSandboxCommandOutput:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    status_text: str | None = None

    def status_success(self) -> bool:
        return self.returncode == 0

    def status_display(self) -> str:
        return self.status_text if self.status_text is not None else f"exit status: {self.returncode}"


@dataclass(frozen=True)
class FileSystemSandboxRunner:
    runtime_paths: ExecServerRuntimePaths
    helper_env: dict[str, str] = field(default_factory=lambda: helper_env())
    command_runner: Any | None = None

    @classmethod
    def new(cls, runtime_paths: ExecServerRuntimePaths) -> "FileSystemSandboxRunner":
        return cls(runtime_paths=runtime_paths, helper_env=helper_env())

    async def run(
        self,
        sandbox: FileSystemSandboxContext,
        request: FsHelperRequest,
    ) -> FsHelperPayload | JSONRPCErrorError:
        cwd_or_error = sandbox_cwd(sandbox)
        if isinstance(cwd_or_error, JSONRPCErrorError):
            return cwd_or_error
        cwd = cwd_or_error
        file_system_policy = sandbox.permissions.file_system_sandbox_policy()
        read_roots = [] if sandbox.use_legacy_landlock else helper_read_roots(self.runtime_paths)
        file_system_policy = add_helper_runtime_permissions(file_system_policy, read_roots, cwd.as_path())
        permission_profile = PermissionProfile.from_runtime_permissions_with_enforcement(
            sandbox.permissions.enforcement(),
            file_system_policy,
            NetworkSandboxPolicy.RESTRICTED,
        )
        command = self.sandbox_exec_request(permission_profile, cwd, sandbox)
        if isinstance(command, JSONRPCErrorError):
            return command
        try:
            request_json = json.dumps(request.to_mapping(), separators=(",", ":")).encode("utf-8")
        except Exception as exc:
            return _fs_sandbox_json_error(exc)
        return await self.run_command(command, request_json)

    async def run_command(
        self,
        command: FsSandboxExecRequest,
        request_json: bytes,
    ) -> FsHelperPayload | JSONRPCErrorError:
        if not command.argv:
            return invalid_request("fs sandbox command was empty")
        if self.command_runner is None:
            output_or_error = await _run_fs_sandbox_subprocess(command, request_json)
            if isinstance(output_or_error, JSONRPCErrorError):
                return output_or_error
            output = output_or_error
        else:
            try:
                output = await _maybe_await(self.command_runner(command, request_json))
            except OSError as exc:
                return internal_error(exc)
        output = _fs_sandbox_command_output(output)
        if not output.status_success():
            stderr = output.stderr.decode("utf-8", errors="replace").strip()
            return internal_error(
                f"fs sandbox helper failed with status {output.status_display()}: {stderr}"
            )
        try:
            response = FsHelperResponse.from_mapping(json.loads(output.stdout))
        except Exception as exc:
            return _fs_sandbox_json_error(exc)
        if response.status == "error":
            return response.payload  # type: ignore[return-value]
        return response.payload  # type: ignore[return-value]

    def sandbox_exec_request(
        self,
        permission_profile: PermissionProfile,
        cwd: AbsolutePathBuf,
        sandbox_context: FileSystemSandboxContext,
    ) -> FsSandboxExecRequest | JSONRPCErrorError:
        sandbox_manager = SandboxManager.new()
        file_system_policy, network_policy = permission_profile.to_runtime_permissions()
        windows_sandbox_level = sandbox_context.windows_sandbox_level or WindowsSandboxLevel.DISABLED
        sandbox = sandbox_manager.select_initial(
            file_system_policy,
            network_policy,
            SandboxablePreference.AUTO,
            windows_sandbox_level,
            False,
        )
        command = SandboxCommand(
            program=str(self.runtime_paths.codex_self_exe),
            args=(CODEX_FS_HELPER_ARG1,),
            cwd=cwd.as_path(),
            env=dict(self.helper_env),
            additional_permissions=None,
        )
        try:
            transformed = sandbox_manager.transform(
                SandboxTransformRequest(
                    command=command,
                    permissions=permission_profile,
                    sandbox=sandbox,
                    enforce_managed_network=False,
                    network=None,
                    sandbox_policy_cwd=cwd.as_path(),
                    codex_linux_sandbox_exe=(
                        self.runtime_paths.codex_linux_sandbox_exe.as_path()
                        if self.runtime_paths.codex_linux_sandbox_exe is not None
                        else None
                    ),
                    use_legacy_landlock=sandbox_context.use_legacy_landlock,
                    windows_sandbox_level=windows_sandbox_level,
                    windows_sandbox_private_desktop=sandbox_context.windows_sandbox_private_desktop,
                )
            )
        except Exception as exc:
            return invalid_request(f"failed to prepare fs sandbox: {exc}")
        return FsSandboxExecRequest(
            argv=list(transformed.command),
            cwd=AbsolutePathBuf.from_absolute_path(transformed.cwd),
            env=dict(transformed.env),
            arg0=transformed.arg0,
        )


def _fs_sandbox_command_output(value: Any) -> FsSandboxCommandOutput:
    if isinstance(value, FsSandboxCommandOutput):
        return value
    if isinstance(value, tuple):
        if len(value) == 3:
            return FsSandboxCommandOutput(int(value[0]), bytes(value[1]), bytes(value[2]))
        if len(value) == 4:
            return FsSandboxCommandOutput(int(value[0]), bytes(value[1]), bytes(value[2]), str(value[3]))
    return FsSandboxCommandOutput(
        int(getattr(value, "returncode")),
        bytes(getattr(value, "stdout", b"")),
        bytes(getattr(value, "stderr", b"")),
        getattr(value, "status_text", None),
    )


async def _run_fs_sandbox_subprocess(
    command: FsSandboxExecRequest,
    request_json: bytes,
) -> FsSandboxCommandOutput | JSONRPCErrorError:
    if not command.argv:
        return invalid_request("fs sandbox command was empty")
    program = command.argv[0]
    args = command.argv[1:]
    popen_args = [program, *args]
    kwargs: dict[str, Any] = {
        "cwd": str(command.cwd),
        "env": dict(command.env),
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if command.arg0 and os.name != "nt":
        popen_args = [command.arg0, *args]
        kwargs["executable"] = program
    try:
        child = await asyncio.create_subprocess_exec(*popen_args, **kwargs)
        stdout, stderr = await child.communicate(request_json)
    except OSError as exc:
        return internal_error(exc)
    return FsSandboxCommandOutput(
        child.returncode if child.returncode is not None else 0,
        stdout,
        stderr,
    )


def _fs_sandbox_json_error(error: BaseException) -> JSONRPCErrorError:
    return internal_error(f"failed to encode or decode fs sandbox helper message: {error}")


def sandbox_cwd(sandbox: FileSystemSandboxContext) -> AbsolutePathBuf | JSONRPCErrorError:
    if sandbox.cwd is not None:
        return sandbox.cwd
    if sandbox.has_cwd_dependent_permissions():
        return invalid_request("file system sandbox context with dynamic permissions requires cwd")
    return AbsolutePathBuf.from_absolute_path(Path.cwd())


def helper_read_roots(runtime_paths: ExecServerRuntimePaths) -> list[AbsolutePathBuf]:
    roots: list[AbsolutePathBuf] = []
    for path in (runtime_paths.codex_self_exe, runtime_paths.codex_linux_sandbox_exe):
        if path is None:
            continue
        parent = path.as_path().parent
        root = AbsolutePathBuf.from_absolute_path(parent)
        if root not in roots:
            roots.append(root)
    return roots


def add_helper_runtime_permissions(
    file_system_policy: FileSystemSandboxPolicy,
    helper_read_roots_value: list[AbsolutePathBuf] | tuple[AbsolutePathBuf, ...],
    cwd: str | Path,
) -> FileSystemSandboxPolicy:
    entries = list(file_system_policy.entries)
    if not file_system_policy.has_full_disk_read_access():
        minimal_read_entry = FileSystemSandboxEntry(
            FileSystemPath.special(FileSystemSpecialPath.minimal()),
            FileSystemAccessMode.READ,
        )
        if minimal_read_entry not in entries:
            entries.append(minimal_read_entry)

    candidate = file_system_policy
    for helper_read_root in helper_read_roots_value:
        if candidate.can_read_path_with_cwd(helper_read_root.as_path(), cwd):
            continue
        entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path(helper_read_root.as_path()),
            FileSystemAccessMode.READ,
        )
        if entry not in entries:
            entries.append(entry)
        candidate = candidate._replace(entries=tuple(entries))

    return file_system_policy._replace(entries=tuple(entries))


def helper_env() -> dict[str, str]:
    return helper_env_from_vars(os.environ.items())


def helper_env_from_vars(vars_iter: Any) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in vars_iter:
        key_text = os.fsdecode(key)
        if helper_env_key_is_allowed(key_text):
            env[key_text] = os.fsdecode(value)
    return env


def helper_env_key_is_allowed(key: str) -> bool:
    return (
        key in FS_HELPER_ENV_ALLOWLIST
        or bazel_bwrap_env_key_is_allowed(key)
        or (os.name == "nt" and key.lower() == "path")
    )


def bazel_bwrap_env_key_is_allowed(key: str) -> bool:
    return os.environ.get("BAZEL_PACKAGE") is not None and key in FS_HELPER_BAZEL_BWRAP_ENV_ALLOWLIST


def _file_system_path_is_cwd_dependent(path: FileSystemPath) -> bool:
    if path.type == "special" and path.value is not None:
        return path.value.kind == "project_roots"
    if path.type == "glob_pattern" and path.pattern is not None:
        return "codex-project-roots://" in path.pattern
    return False


class ExecServerTransportKind(str, Enum):
    WEBSOCKET_URL = "websocketUrl"
    STDIO_COMMAND = "stdioCommand"


@dataclass(frozen=True)
class ExecServerTransportParams:
    kind: ExecServerTransportKind
    websocket_url: str | None = None
    command: StdioExecServerCommand | None = None
    connect_timeout: int | None = None
    initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT

    @classmethod
    def websocket_url_params(cls, websocket_url: str) -> "ExecServerTransportParams":
        return cls(
            kind=ExecServerTransportKind.WEBSOCKET_URL,
            websocket_url=websocket_url,
            connect_timeout=DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT,
            initialize_timeout=DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
        )

    @classmethod
    def from_websocket_url(
        cls,
        websocket_url: str,
        *,
        connect_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT,
        initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
    ) -> "ExecServerTransportParams":
        return cls(
            kind=ExecServerTransportKind.WEBSOCKET_URL,
            websocket_url=websocket_url,
            connect_timeout=connect_timeout,
            initialize_timeout=initialize_timeout,
        )

    @classmethod
    def stdio_command(
        cls,
        command: StdioExecServerCommand,
        *,
        initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
    ) -> "ExecServerTransportParams":
        return cls(
            kind=ExecServerTransportKind.STDIO_COMMAND,
            command=command,
            initialize_timeout=initialize_timeout,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ExecServerTransportKind):
            object.__setattr__(self, "kind", ExecServerTransportKind(self.kind))
        if self.kind is ExecServerTransportKind.WEBSOCKET_URL:
            if self.websocket_url is None:
                raise ValueError("websocket_url is required for WebSocketUrl transport")
            if self.command is not None:
                raise ValueError("command is only valid for StdioCommand transport")
            if self.connect_timeout is None:
                object.__setattr__(self, "connect_timeout", DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT)
        elif self.kind is ExecServerTransportKind.STDIO_COMMAND:
            if self.command is None:
                raise ValueError("command is required for StdioCommand transport")
            if self.websocket_url is not None:
                raise ValueError("websocket_url is only valid for WebSocketUrl transport")
            if self.connect_timeout is not None:
                raise ValueError("connect_timeout is only valid for WebSocketUrl transport")


@dataclass(frozen=True)
class ExecServerRuntimePaths:
    codex_self_exe: AbsolutePathBuf
    codex_linux_sandbox_exe: AbsolutePathBuf | None = None

    @classmethod
    def from_optional_paths(
        cls,
        codex_self_exe: str | Path | None,
        codex_linux_sandbox_exe: str | Path | None = None,
    ) -> "ExecServerRuntimePaths":
        if codex_self_exe is None:
            raise ValueError("Codex executable path is not configured")
        return cls.new(codex_self_exe, codex_linux_sandbox_exe)

    @classmethod
    def new(
        cls,
        codex_self_exe: str | Path,
        codex_linux_sandbox_exe: str | Path | None = None,
    ) -> "ExecServerRuntimePaths":
        return cls(
            codex_self_exe=AbsolutePathBuf.from_absolute_path(codex_self_exe),
            codex_linux_sandbox_exe=(
                AbsolutePathBuf.from_absolute_path(codex_linux_sandbox_exe)
                if codex_linux_sandbox_exe is not None
                else None
            ),
        )

    def to_mapping(self) -> dict[str, str | None]:
        return {
            "codex_self_exe": str(self.codex_self_exe),
            "codex_linux_sandbox_exe": (
                str(self.codex_linux_sandbox_exe) if self.codex_linux_sandbox_exe is not None else None
            ),
        }


@dataclass(frozen=True)
class Environment:
    exec_server_url_value: str | None = None
    remote_transport: ExecServerTransportParams | None = None
    local_runtime_paths: ExecServerRuntimePaths | None = None
    exec_backend: ExecBackend | None = None
    filesystem: ExecutorFileSystem | None = None
    http_client: Any | None = None

    @classmethod
    def default_for_tests(cls) -> "Environment":
        return cls(
            exec_backend=LocalProcess.new(None),
            filesystem=LocalFileSystem.unsandboxed(),
            http_client=ReqwestHttpClient(),
        )

    @classmethod
    def create(
        cls,
        exec_server_url: str | None,
        local_runtime_paths: ExecServerRuntimePaths,
    ) -> "Environment":
        return cls._create_inner(exec_server_url, local_runtime_paths)

    @classmethod
    def create_for_tests(cls, exec_server_url: str | None = None) -> "Environment":
        return cls._create_inner(exec_server_url, None)

    @classmethod
    def _create_inner(
        cls,
        exec_server_url: str | None,
        local_runtime_paths: ExecServerRuntimePaths | None,
    ) -> "Environment":
        normalized_url, disabled = normalize_exec_server_url(exec_server_url)
        if disabled:
            raise ExecServerError.protocol("disabled mode does not create an Environment")
        if normalized_url is not None:
            return cls.remote_inner(normalized_url, local_runtime_paths)
        if local_runtime_paths is not None:
            return cls.local(local_runtime_paths)
        return cls.default_for_tests()

    @classmethod
    def local(cls, local_runtime_paths: ExecServerRuntimePaths) -> "Environment":
        return cls(
            local_runtime_paths=local_runtime_paths,
            exec_backend=LocalProcess.new(None),
            filesystem=LocalFileSystem.with_runtime_paths(local_runtime_paths),
            http_client=ReqwestHttpClient(),
        )

    @classmethod
    def remote_inner(
        cls,
        exec_server_url: str,
        local_runtime_paths: ExecServerRuntimePaths | None = None,
    ) -> "Environment":
        return cls.remote_with_transport(
            ExecServerTransportParams.from_websocket_url(exec_server_url),
            local_runtime_paths,
        )

    @classmethod
    def remote_with_transport(
        cls,
        remote_transport: ExecServerTransportParams,
        local_runtime_paths: ExecServerRuntimePaths | None = None,
    ) -> "Environment":
        exec_server_url = (
            remote_transport.websocket_url
            if remote_transport.kind is ExecServerTransportKind.WEBSOCKET_URL
            else None
        )
        return cls(
            exec_server_url_value=exec_server_url,
            remote_transport=remote_transport,
            local_runtime_paths=local_runtime_paths,
            exec_backend=RemoteProcessBoundary(remote_transport),
            filesystem=RemoteFileSystemBoundary(remote_transport),
            http_client=LazyRemoteExecServerClient(remote_transport),
        )

    def is_remote(self) -> bool:
        return self.exec_server_url_value is not None or self.remote_transport is not None

    def exec_server_url(self) -> str | None:
        return self.exec_server_url_value

    def get_exec_backend(self) -> ExecBackend:
        return self.exec_backend if self.exec_backend is not None else LocalProcess.new(None)

    def get_filesystem(self) -> ExecutorFileSystem:
        return self.filesystem if self.filesystem is not None else LocalFileSystem.unsandboxed()

    def get_http_client(self) -> Any:
        return self.http_client if self.http_client is not None else ReqwestHttpClient()


@dataclass
class LazyRemoteExecServerClient:
    transport_params: ExecServerTransportParams
    client: Any | None = None
    connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get(self) -> Any:
        client = self.connected_client()
        if client is not None:
            return client
        async with self.connect_lock:
            client = self.connected_client()
            if client is not None:
                return client
            cached_client = self.client
            if cached_client is not None and self.transport_params.kind is not ExecServerTransportKind.WEBSOCKET_URL:
                return cached_client
            next_client = await ExecServerClient.connect_for_transport(self.transport_params)
            self.client = next_client
            return next_client

    def cached_client(self) -> Any | None:
        return self.client

    def connected_client(self) -> Any | None:
        client = self.cached_client()
        if client is None:
            return None
        is_disconnected = getattr(client, "is_disconnected", None)
        if callable(is_disconnected) and is_disconnected():
            return None
        return client

    async def http_request(self, params: "HttpRequestParams") -> "HttpRequestResponse":
        return await (await self.get()).http_request(params)

    async def http_request_stream(
        self,
        params: "HttpRequestParams",
    ) -> tuple["HttpRequestResponse", "HttpResponseBodyStream"]:
        return await (await self.get()).http_request_stream(params)


@dataclass(frozen=True)
class RemoteProcessBoundary(ExecBackend):
    transport_params: ExecServerTransportParams | None = None
    client: LazyRemoteExecServerClient | None = None

    @classmethod
    def new(cls, client: LazyRemoteExecServerClient) -> "RemoteProcessBoundary":
        return cls(client=client)

    async def start(self, params: ExecParams) -> StartedExecProcess:
        process_id = params.process_id
        client = await self._client()
        session = await client.register_session(process_id)
        try:
            await client.exec(params)
        except Exception:
            await session.unregister()
            raise
        return StartedExecProcess(process=RemoteExecProcess(session))

    async def _client(self) -> Any:
        if self.client is not None:
            return await self.client.get()
        if self.transport_params is None:
            raise ExecServerError.protocol("remote process requires transport params")
        return await LazyRemoteExecServerClient(self.transport_params).get()


@dataclass
class RemoteExecProcess(ExecProcess):
    session: Any
    _unregistered: bool = False

    def process_id(self) -> ProcessId:
        return self.session.process_id()

    def subscribe_wake(self) -> Any:
        return self.session.subscribe_wake()

    def subscribe_events(self) -> ExecProcessEventReceiver:
        return self.session.subscribe_events()

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        return await self.session.read(after_seq, max_bytes, wait_ms)

    async def write(self, chunk: bytes) -> WriteResponse:
        return await self.session.write(chunk)

    async def terminate(self) -> None:
        await self.session.terminate()

    async def unregister(self) -> None:
        if not self._unregistered:
            self._unregistered = True
            await self.session.unregister()

    def __del__(self) -> None:
        if self._unregistered:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._unregistered = True
        loop.create_task(self.session.unregister())


@dataclass(frozen=True)
class RemoteFileSystemBoundary(ExecutorFileSystem):
    transport_params: ExecServerTransportParams | None = None
    client: LazyRemoteExecServerClient | None = None

    @classmethod
    def new(cls, client: LazyRemoteExecServerClient) -> "RemoteFileSystemBoundary":
        return cls(client=client)

    async def _client(self) -> Any:
        if self.client is not None:
            return await self.client.get()
        if self.transport_params is None:
            raise ExecServerError.protocol("remote filesystem requires transport params")
        return await LazyRemoteExecServerClient(self.transport_params).get()

    async def read_file(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> bytes:
        client = await self._client()
        try:
            response = await client.fs_read_file(FsReadFileParams(str(path), remote_sandbox_context(sandbox)))
            data = base64.b64decode(response.data_base64, validate=True)
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc
        except binascii.Error as exc:
            raise OSError(f"remote fs/readFile returned invalid base64 dataBase64: {exc}") from exc
        return data

    async def write_file(
        self,
        path: str | Path | AbsolutePathBuf,
        contents: bytes,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        client = await self._client()
        try:
            await client.fs_write_file(
                FsWriteFileParams(
                    str(path),
                    base64.b64encode(contents).decode("ascii"),
                    remote_sandbox_context(sandbox),
                )
            )
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        client = await self._client()
        try:
            await client.fs_create_directory(
                FsCreateDirectoryParams(str(path), options.recursive, remote_sandbox_context(sandbox))
            )
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc

    async def get_metadata(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> FileMetadata:
        client = await self._client()
        try:
            response = await client.fs_get_metadata(FsGetMetadataParams(str(path), remote_sandbox_context(sandbox)))
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc
        return FileMetadata(
            is_directory=response.is_directory,
            is_file=response.is_file,
            is_symlink=response.is_symlink,
            created_at_ms=response.created_at_ms,
            modified_at_ms=response.modified_at_ms,
        )

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> list[ReadDirectoryEntry]:
        client = await self._client()
        try:
            response = await client.fs_read_directory(FsReadDirectoryParams(str(path), remote_sandbox_context(sandbox)))
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc
        return [
            ReadDirectoryEntry(entry.file_name, entry.is_directory, entry.is_file)
            for entry in response.entries
        ]

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        client = await self._client()
        try:
            await client.fs_remove(
                FsRemoveParams(str(path), options.recursive, options.force, remote_sandbox_context(sandbox))
            )
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        client = await self._client()
        try:
            await client.fs_copy(
                FsCopyParams(
                    str(source_path),
                    str(destination_path),
                    options.recursive,
                    remote_sandbox_context(sandbox),
                )
            )
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc


def remote_sandbox_context(
    sandbox: FileSystemSandboxContext | None,
) -> FileSystemSandboxContext | None:
    if sandbox is None:
        return None
    return sandbox.drop_cwd_if_unused()


def map_remote_error(error: ExecServerError) -> OSError:
    code = getattr(error, "code", None)
    message = getattr(error, "message", str(error))
    if getattr(error, "kind", None) == "server":
        if code == -32004:
            return FileNotFoundError(message)
        if code == -32600:
            return OSError(errno.EINVAL, message)
        return OSError(message)
    if getattr(error, "kind", None) in {"closed", "disconnected"}:
        return BrokenPipeError("exec-server transport closed")
    return OSError(str(error))


class EnvironmentDefaultKind(str, Enum):
    DISABLED = "disabled"
    ENVIRONMENT_ID = "environmentId"


@dataclass(frozen=True)
class EnvironmentDefault:
    kind: EnvironmentDefaultKind
    environment_id: str | None = None

    @classmethod
    def disabled(cls) -> "EnvironmentDefault":
        return cls(EnvironmentDefaultKind.DISABLED)

    @classmethod
    def environment_id_value(cls, environment_id: str) -> "EnvironmentDefault":
        return cls(EnvironmentDefaultKind.ENVIRONMENT_ID, environment_id)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EnvironmentDefaultKind):
            object.__setattr__(self, "kind", EnvironmentDefaultKind(self.kind))
        if self.kind is EnvironmentDefaultKind.DISABLED:
            if self.environment_id is not None:
                raise ValueError("environment_id is only valid for EnvironmentId default")
        elif not self.environment_id:
            raise ValueError("environment_id is required for EnvironmentId default")


@dataclass(frozen=True)
class EnvironmentProviderSnapshot:
    environments: list[tuple[str, Environment]]
    default: EnvironmentDefault
    include_local: bool


class EnvironmentProvider:
    def snapshot(self) -> EnvironmentProviderSnapshot:
        raise NotImplementedError("environment provider snapshot is not implemented")


def normalize_exec_server_url(exec_server_url: str | None) -> tuple[str | None, bool]:
    if exec_server_url is None:
        return None, False
    url = exec_server_url.strip()
    if not url:
        return None, False
    if url.lower() == "none":
        return None, True
    return url, False


@dataclass(frozen=True)
class DefaultEnvironmentProvider(EnvironmentProvider):
    exec_server_url: str | None = None

    @classmethod
    def new(cls, exec_server_url: str | None) -> "DefaultEnvironmentProvider":
        return cls(exec_server_url)

    @classmethod
    def from_env(cls) -> "DefaultEnvironmentProvider":
        return cls(os.environ.get(CODEX_EXEC_SERVER_URL_ENV_VAR))

    def snapshot_inner(self) -> EnvironmentProviderSnapshot:
        environments: list[tuple[str, Environment]] = []
        exec_server_url, disabled = normalize_exec_server_url(self.exec_server_url)
        if exec_server_url is not None:
            environments.append(
                (
                    REMOTE_ENVIRONMENT_ID,
                    Environment.remote_inner(exec_server_url, local_runtime_paths=None),
                )
            )

        has_remote = any(environment_id == REMOTE_ENVIRONMENT_ID for environment_id, _ in environments)
        include_local = not disabled and not has_remote
        if disabled:
            default = EnvironmentDefault.disabled()
        elif has_remote:
            default = EnvironmentDefault.environment_id_value(REMOTE_ENVIRONMENT_ID)
        else:
            default = EnvironmentDefault.environment_id_value(LOCAL_ENVIRONMENT_ID)
        return EnvironmentProviderSnapshot(environments=environments, default=default, include_local=include_local)

    def snapshot(self) -> EnvironmentProviderSnapshot:
        return self.snapshot_inner()


class EnvironmentManager:
    def __init__(
        self,
        environments: dict[str, Environment] | None = None,
        default_environment: str | None = LOCAL_ENVIRONMENT_ID,
        local_runtime_paths: ExecServerRuntimePaths | None = None,
        local_environment: Environment | None = None,
    ) -> None:
        self.environments = (
            {LOCAL_ENVIRONMENT_ID: Environment.default_for_tests()} if environments is None else environments
        )
        self._default_environment = default_environment
        self.local_runtime_paths = local_runtime_paths
        self.local_environment = local_environment or self.environments.get(LOCAL_ENVIRONMENT_ID)

    @classmethod
    def default_for_tests(cls) -> "EnvironmentManager":
        local = Environment.default_for_tests()
        return cls({LOCAL_ENVIRONMENT_ID: local}, LOCAL_ENVIRONMENT_ID, None, local)

    @classmethod
    def without_environments(cls) -> "EnvironmentManager":
        return cls({}, None, None, None)

    @classmethod
    def create_for_tests(
        cls,
        exec_server_url: str | None,
        local_runtime_paths: ExecServerRuntimePaths | None,
    ) -> "EnvironmentManager":
        provider = DefaultEnvironmentProvider.new(exec_server_url)
        return cls.from_snapshot(provider.snapshot_inner(), local_runtime_paths)

    @classmethod
    def create_for_tests_with_local(
        cls,
        exec_server_url: str | None,
        local_runtime_paths: ExecServerRuntimePaths,
    ) -> "EnvironmentManager":
        snapshot = DefaultEnvironmentProvider.new(exec_server_url).snapshot_inner()
        return cls.from_snapshot(
            EnvironmentProviderSnapshot(
                environments=list(snapshot.environments),
                default=snapshot.default,
                include_local=True,
            ),
            local_runtime_paths,
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: EnvironmentProviderSnapshot,
        local_runtime_paths: ExecServerRuntimePaths | None,
    ) -> "EnvironmentManager":
        environment_map: dict[str, Environment] = {}
        local_environment = None
        if snapshot.include_local:
            if local_runtime_paths is None:
                raise ExecServerError.protocol("local environment requires configured runtime paths")
            local_environment = Environment.local(local_runtime_paths)
            environment_map[LOCAL_ENVIRONMENT_ID] = local_environment
        for environment_id, environment in snapshot.environments:
            if environment_id == "":
                raise ExecServerError.protocol("environment id cannot be empty")
            if environment_id == LOCAL_ENVIRONMENT_ID:
                raise ExecServerError.protocol(
                    f"environment id `{LOCAL_ENVIRONMENT_ID}` is reserved for EnvironmentManager"
                )
            if environment_id in environment_map:
                raise ExecServerError.protocol(f"environment id `{environment_id}` is duplicated")
            environment_map[environment_id] = environment
        if snapshot.default.kind is EnvironmentDefaultKind.DISABLED:
            default_environment = None
        else:
            default_environment = snapshot.default.environment_id
            if default_environment not in environment_map:
                raise ExecServerError.protocol(f"default environment `{default_environment}` is not configured")
        return cls(environment_map, default_environment, local_runtime_paths, local_environment)

    def default_environment(self) -> Environment | None:
        return self.get_environment(self._default_environment) if self._default_environment else None

    def default_environment_id(self) -> str | None:
        return self._default_environment

    def default_environment_ids(self) -> list[str]:
        if not self._default_environment:
            return []
        rest = [key for key in self.environments if key != self._default_environment]
        return [self._default_environment, *rest]

    def try_local_environment(self) -> Environment | None:
        return self.local_environment

    def default_or_local_environment(self) -> Environment | None:
        return self.default_environment() or self.try_local_environment()

    def get_environment(self, environment_id: str | None) -> Environment | None:
        return self.environments.get(environment_id or "")

    def upsert_environment(self, environment_id: str, exec_server_url: str) -> None:
        if not environment_id:
            raise ExecServerError.protocol("environment id cannot be empty")
        normalized_url, disabled = normalize_exec_server_url(exec_server_url)
        if disabled:
            raise ExecServerError.protocol("remote environment cannot use disabled exec-server url")
        if normalized_url is None:
            raise ExecServerError.protocol("remote environment requires an exec-server url")
        self.environments[environment_id] = Environment.remote_inner(normalized_url, self.local_runtime_paths)


class ExecServerClient:
    def __init__(
        self,
        connection: JsonRpcConnection,
        options: ExecServerClientConnectOptions,
        session_id: str | None = None,
        *,
        start_reader: bool = True,
    ) -> None:
        self.connection = connection
        self.options = options
        self._session_id = session_id
        self.sessions: dict[ProcessId, ClientSessionState] = {}
        self.http_body_streams: dict[str, asyncio.Queue[HttpRequestBodyDeltaNotification | None]] = {}
        self.http_body_stream_failures: dict[str, str] = {}
        self.http_body_stream_next_id = 1
        self.pending_calls: dict[RequestId, asyncio.Future[Any]] = {}
        self.next_request_id = 1
        self.disconnected_message: str | None = None
        self.reader_task: asyncio.Task[Any] | None = None
        if start_reader:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self.reader_task = None
            else:
                self.reader_task = loop.create_task(self._reader_loop())

    def session_id(self) -> str | None:
        return self._session_id

    def is_disconnected(self) -> bool:
        return self.disconnected_message is not None or self.connection.disconnected.is_set()

    async def register_session(self, process_id: ProcessId | str) -> ClientSession:
        process_id = ProcessId.new(process_id) if isinstance(process_id, str) else process_id
        if self.disconnected_message is not None:
            raise ExecServerError(self.disconnected_message, "disconnected")
        if process_id in self.sessions:
            raise ExecServerError.protocol(f"session already registered for process {process_id}")
        state = ClientSessionState()
        self.sessions[process_id] = state
        return ClientSession(self, process_id, state)

    async def unregister_session(self, process_id: ProcessId | str) -> None:
        process_id = ProcessId.new(process_id) if isinstance(process_id, str) else process_id
        self.sessions.pop(process_id, None)

    async def read(self, params: ReadParams) -> ReadResponse:
        result = await self.call(EXEC_READ_METHOD, encode_read_params(params))
        return decode_read_response(result)

    async def write(self, process_id: ProcessId, chunk: bytes) -> WriteResponse:
        params = WriteParams(process_id=process_id, chunk=ByteChunk(chunk))
        result = await self.call(EXEC_WRITE_METHOD, encode_write_params(params))
        return decode_write_response(result)

    async def terminate(self, process_id: ProcessId) -> TerminateResponse:
        result = await self.call(EXEC_TERMINATE_METHOD, encode_terminate_params(TerminateParams(process_id)))
        return decode_terminate_response(result)

    async def call(self, method: str, params: Any) -> Any:
        call_impl = getattr(self, "call_impl", None)
        if call_impl is not None:
            result = call_impl(method, params)
            if inspect.isawaitable(result):
                return await result
            return result
        if self.disconnected_message is not None or self.connection.disconnected.is_set():
            raise ExecServerError(self.disconnected_message or _disconnected_message(), "disconnected")
        request_id = RequestId.integer(self.next_request_id)
        self.next_request_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self.pending_calls[request_id] = future
        await self.connection.outgoing_tx.put(
            JSONRPCMessage(JSONRPCRequest(id=request_id, method=method, params=params, trace=None))
        )
        try:
            return await future
        except RpcCallError as exc:
            if exc.kind == "server":
                error = getattr(exc, "error")
                raise ExecServerError(
                    f"exec-server rejected request ({error.code}): {error.message}",
                    "server",
                    code=error.code,
                    server_message=error.message,
                ) from exc
            if exc.kind == "closed":
                message = _disconnected_message()
                self.disconnected_message = self.disconnected_message or message
                raise ExecServerError(self.disconnected_message, "disconnected") from exc
            raise ExecServerError(f"failed to serialize or deserialize exec-server JSON: {exc}", "json") from exc
        finally:
            self.pending_calls.pop(request_id, None)

    async def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
        params = replace(params, stream_response=False)
        return await self.call(HTTP_REQUEST_METHOD, params)

    async def http_request_stream(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, HttpResponseBodyStream]:
        request_id = self.next_http_body_stream_request_id()
        params = replace(params, stream_response=True, request_id=request_id)
        queue: asyncio.Queue[HttpRequestBodyDeltaNotification | None] = asyncio.Queue(
            maxsize=HTTP_BODY_DELTA_CHANNEL_CAPACITY
        )
        await self.insert_http_body_stream(request_id, queue)
        try:
            response = await self.call(HTTP_REQUEST_METHOD, params)
        except Exception:
            await self.remove_http_body_stream(request_id)
            raise
        return response, HttpResponseBodyStream.remote(self, request_id, queue)

    def next_http_body_stream_request_id(self) -> str:
        request_id = f"http-{self.http_body_stream_next_id}"
        self.http_body_stream_next_id += 1
        return request_id

    async def insert_http_body_stream(
        self,
        request_id: str,
        queue: asyncio.Queue[HttpRequestBodyDeltaNotification | None],
    ) -> None:
        if request_id in self.http_body_streams:
            raise ExecServerError.protocol(f"http response stream already registered for request {request_id}")
        self.http_body_streams[request_id] = queue
        self.http_body_stream_failures.pop(request_id, None)

    async def remove_http_body_stream(
        self,
        request_id: str,
    ) -> asyncio.Queue[HttpRequestBodyDeltaNotification | None] | None:
        return self.http_body_streams.pop(request_id, None)

    def take_http_body_stream_failure(self, request_id: str) -> str | None:
        return self.http_body_stream_failures.pop(request_id, None)

    async def handle_http_body_delta_notification(self, params: Any) -> None:
        notification = decode_http_request_body_delta_notification(params)
        queue = self.http_body_streams.get(notification.request_id)
        if queue is None:
            return
        terminal_delta = notification.done or notification.error is not None
        try:
            queue.put_nowait(notification)
            if terminal_delta:
                await self.remove_http_body_stream(notification.request_id)
        except asyncio.QueueFull:
            self.http_body_stream_failures[
                notification.request_id
            ] = "body delta channel filled before delivery"
            await self.remove_http_body_stream(notification.request_id)
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def fail_all_http_body_streams(self, message: str) -> None:
        streams = list(self.http_body_streams.items())
        self.http_body_streams.clear()
        for request_id, queue in streams:
            delta = HttpRequestBodyDeltaNotification(
                request_id=request_id,
                seq=1,
                delta=ByteChunk(b""),
                done=True,
                error=message,
            )
            try:
                queue.put_nowait(delta)
            except asyncio.QueueFull:
                self.http_body_stream_failures[request_id] = message

    async def _reader_loop(self) -> None:
        while True:
            event = await self.connection.incoming_rx.get()
            if event.kind == "disconnected":
                message = _disconnected_message(event.reason)
                self._fail_all_sessions(message)
                self._fail_pending_calls(message)
                return
            if event.kind == "malformed":
                message = f"exec-server notification handling failed: {event.reason}"
                self._fail_all_sessions(message)
                self._fail_pending_calls(message)
                return
            if event.message is None:
                continue
            value = event.message.value
            if isinstance(value, JSONRPCNotification):
                try:
                    await self._handle_server_notification(value)
                except Exception as exc:
                    message = f"exec-server notification handling failed: {exc}"
                    self._fail_all_sessions(message)
                    self._fail_pending_calls(message)
                    return
            elif isinstance(value, JSONRPCResponse):
                future = self.pending_calls.get(value.id)
                if future is not None and not future.done():
                    future.set_result(value.result)
            elif isinstance(value, JSONRPCError):
                future = self.pending_calls.get(value.id)
                if future is not None and not future.done():
                    future.set_exception(RpcCallError.server(value.error))

    async def _handle_server_notification(self, notification: JSONRPCNotification) -> None:
        params = notification.params or {}
        if notification.method == EXEC_OUTPUT_DELTA_METHOD:
            process_id = _decode_process_id(params.get("processId") if isinstance(params, Mapping) else None)
            state = self.sessions.get(process_id)
            if state is None:
                return
            stream_value = params.get("stream")
            chunk_value = params.get("chunk")
            if not isinstance(stream_value, str) or not isinstance(chunk_value, str):
                raise ValueError("process/output requires stream and chunk")
            seq = _decode_optional_int(params.get("seq"), "seq")
            if seq is None:
                raise ValueError("seq must be an integer")
            state.note_change(seq)
            published_closed = state.publish_ordered_event(
                ExecProcessEvent.output(
                    ProcessOutputChunk(
                        seq=seq,
                        stream=ExecOutputStream(stream_value),
                        chunk=ByteChunk.from_base64(chunk_value),
                    )
                )
            )
            if published_closed:
                self.sessions.pop(process_id, None)
            return
        if notification.method == EXEC_EXITED_METHOD:
            process_id = _decode_process_id(params.get("processId") if isinstance(params, Mapping) else None)
            state = self.sessions.get(process_id)
            if state is None:
                return
            seq = _decode_optional_int(params.get("seq"), "seq")
            exit_code = _decode_optional_int(params.get("exitCode"), "exitCode")
            if seq is None or exit_code is None:
                raise ValueError("process/exited requires seq and exitCode")
            state.note_change(seq)
            published_closed = state.publish_ordered_event(ExecProcessEvent.exited(seq=seq, exit_code=exit_code))
            if published_closed:
                self.sessions.pop(process_id, None)
            return
        if notification.method == EXEC_CLOSED_METHOD:
            process_id = _decode_process_id(params.get("processId") if isinstance(params, Mapping) else None)
            state = self.sessions.get(process_id)
            if state is None:
                return
            seq = _decode_optional_int(params.get("seq"), "seq")
            if seq is None:
                raise ValueError("process/closed requires seq")
            state.note_change(seq)
            published_closed = state.publish_ordered_event(ExecProcessEvent.closed(seq=seq))
            if published_closed:
                self.sessions.pop(process_id, None)
            return
        if notification.method == HTTP_REQUEST_BODY_DELTA_METHOD:
            await self.handle_http_body_delta_notification(params)

    def _fail_all_sessions(self, message: str) -> None:
        if self.disconnected_message is None:
            self.disconnected_message = message
        for state in list(self.sessions.values()):
            state.set_failure(self.disconnected_message)
        self.sessions.clear()
        if self.http_body_streams:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self.http_body_streams.clear()
            else:
                loop.create_task(self.fail_all_http_body_streams(self.disconnected_message))

    def _fail_pending_calls(self, message: str) -> None:
        self.disconnected_message = self.disconnected_message or message
        for future in list(self.pending_calls.values()):
            if not future.done():
                future.set_exception(ExecServerError(self.disconnected_message, "disconnected"))
        self.pending_calls.clear()

    @classmethod
    async def connect_for_transport(
        cls,
        transport_params: ExecServerTransportParams,
        *,
        websocket_connector: Any | None = None,
        stdio_connector: Any | None = None,
        initializer: Any | None = None,
    ) -> "ExecServerClient":
        if transport_params.kind is ExecServerTransportKind.WEBSOCKET_URL:
            return await cls.connect_websocket(
                RemoteExecServerConnectArgs(
                    websocket_url=transport_params.websocket_url or "",
                    client_name=ENVIRONMENT_CLIENT_NAME,
                    connect_timeout=transport_params.connect_timeout
                    or DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT,
                    initialize_timeout=transport_params.initialize_timeout,
                    resume_session_id=None,
                ),
                websocket_connector=websocket_connector,
                initializer=initializer,
            )
        return await cls.connect_stdio_command(
            StdioExecServerConnectArgs(
                command=transport_params.command,
                client_name=ENVIRONMENT_CLIENT_NAME,
                initialize_timeout=transport_params.initialize_timeout,
                resume_session_id=None,
            ),
            stdio_connector=stdio_connector,
            initializer=initializer,
        )

    @classmethod
    async def connect_websocket(
        cls,
        args: RemoteExecServerConnectArgs,
        *,
        websocket_connector: Any | None = None,
        initializer: Any | None = None,
    ) -> "ExecServerClient":
        connect = _connect_websocket_url if websocket_connector is None else websocket_connector
        try:
            connection = await asyncio.wait_for(
                _maybe_await(connect(args.websocket_url) if websocket_connector is None else connect(args)),
                timeout=args.connect_timeout,
            )
        except TimeoutError as exc:
            raise ExecServerError.websocket_connect_timeout(
                args.websocket_url,
                args.connect_timeout,
            ) from exc
        except Exception as exc:
            raise ExecServerError.websocket_connect(args.websocket_url, exc) from exc
        if not isinstance(connection, JsonRpcConnection):
            connection_label = f"exec-server websocket {args.websocket_url}"
            if is_rendezvous_harness_url(args.websocket_url):
                connection = harness_connection_from_websocket(connection, connection_label)
            else:
                connection = JsonRpcConnection.from_websocket(connection, connection_label)
        return await cls.connect(connection, args.to_client_connect_options(), initializer=initializer)

    @classmethod
    async def connect_stdio_command(
        cls,
        args: StdioExecServerConnectArgs,
        *,
        stdio_connector: Any | None = None,
        initializer: Any | None = None,
    ) -> "ExecServerClient":
        if stdio_connector is None:
            connection = await _spawn_stdio_command_connection(args.command)
        else:
            connection = await _maybe_await(stdio_connector(args.command))
        if not isinstance(connection, JsonRpcConnection):
            raise TypeError("stdio_connector must return JsonRpcConnection")
        return await cls.connect(connection, args.to_client_connect_options(), initializer=initializer)

    @classmethod
    async def connect(
        cls,
        connection: JsonRpcConnection,
        options: ExecServerClientConnectOptions,
        *,
        initializer: Any | None = None,
    ) -> "ExecServerClient":
        if initializer is None:
            session_id = await _initialize_exec_server_connection(connection, options)
        else:
            session_id = await _maybe_await(initializer(connection, options))
        return cls(connection=connection, options=options, session_id=session_id)


async def _initialize_exec_server_connection(
    connection: JsonRpcConnection,
    options: ExecServerClientConnectOptions,
) -> str:
    request_id = RequestId.integer(1)
    params: dict[str, Any] = {"clientName": options.client_name}
    if options.resume_session_id is not None:
        params["resumeSessionId"] = options.resume_session_id
    await connection.outgoing_tx.put(
        JSONRPCMessage(
            JSONRPCRequest(
                id=request_id,
                method=INITIALIZE_METHOD,
                params=params,
                trace=None,
            )
        )
    )
    while True:
        event = await asyncio.wait_for(connection.incoming_rx.get(), timeout=options.initialize_timeout)
        if event.kind == "disconnected":
            raise ExecServerError.protocol("exec-server transport disconnected")
        if event.kind == "malformed":
            raise ExecServerError.protocol(event.reason or "malformed JSON-RPC message")
        if event.message is None:
            continue
        value = event.message.value
        if isinstance(value, JSONRPCResponse) and value.id == request_id:
            result = value.result
            if not isinstance(result, Mapping) or not isinstance(result.get("sessionId"), str):
                raise ExecServerError.protocol("initialize response missing sessionId")
            await connection.outgoing_tx.put(
                JSONRPCMessage(JSONRPCNotification(method=INITIALIZED_METHOD, params=None))
            )
            return result["sessionId"]
        if isinstance(value, JSONRPCError) and value.id == request_id:
            raise ExecServerError.protocol(value.error.message)


def _disconnected_message(reason: str | None = None) -> str:
    if reason:
        return f"exec-server transport disconnected: {reason}"
    return "exec-server transport disconnected"


def is_rendezvous_harness_url(websocket_url: str) -> bool:
    if "?" not in websocket_url:
        return False
    _path, query = websocket_url.split("?", 1)
    for pair in query.split("&"):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        if key == "role" and value == "harness":
            return True
    return False


@dataclass(frozen=True)
class StdioCommandProcessSpec:
    program: str
    args: tuple[str, ...]
    env: dict[str, str]
    cwd: Path | None
    stdin_piped: bool = True
    stdout_piped: bool = True
    stderr_piped: bool = True
    process_group_zero: bool = os.name != "nt"


def stdio_command_process_spec(stdio_command: StdioExecServerCommand) -> StdioCommandProcessSpec:
    return StdioCommandProcessSpec(
        program=stdio_command.program,
        args=tuple(stdio_command.args),
        env=dict(stdio_command.env),
        cwd=stdio_command.cwd,
    )


async def _spawn_stdio_command_connection(stdio_command: StdioExecServerCommand) -> JsonRpcConnection:
    spec = stdio_command_process_spec(stdio_command)
    env = os.environ.copy()
    env.update(spec.env)
    kwargs: dict[str, Any] = {
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "env": env,
    }
    if spec.cwd is not None:
        kwargs["cwd"] = spec.cwd
    if spec.process_group_zero:
        kwargs["process_group"] = 0
    try:
        child = await asyncio.create_subprocess_exec(spec.program, *spec.args, **kwargs)
    except Exception as exc:
        raise ExecServerError(f"failed to spawn exec-server: {exc}", "spawn") from exc
    if child.stdin is None:
        raise ExecServerError.protocol("spawned exec-server command has no stdin")
    if child.stdout is None:
        raise ExecServerError.protocol("spawned exec-server command has no stdout")
    if child.stderr is not None:
        asyncio.create_task(_drain_stdio_command_stderr(child.stderr))
    return JsonRpcConnection.from_stdio(
        child.stdout,
        child.stdin,
        "exec-server stdio command",
    ).with_child_process(child)


async def _drain_stdio_command_stderr(stderr: Any) -> None:
    while True:
        try:
            line = await _read_stdio_line(stderr)
        except Exception:
            return
        if not line:
            return


@dataclass(frozen=True)
class PendingReqwestHttpBodyStream:
    request_id: str
    chunks: list[bytes]


class ReqwestHttpRequestRunner:
    def __init__(self, timeout_ms: int | None = None) -> None:
        self.timeout_ms = timeout_ms

    @classmethod
    def new(cls, timeout_ms: int | None = None) -> "ReqwestHttpRequestRunner":
        return cls(timeout_ms)

    async def run(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, PendingReqwestHttpBodyStream | None] | JSONRPCErrorError:
        return await asyncio.to_thread(self._run_sync, params)

    def _run_sync(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, PendingReqwestHttpBodyStream | None] | JSONRPCErrorError:
        method_error = _validate_http_method(params.method)
        if method_error is not None:
            return invalid_params(f"http/request method is invalid: {method_error}")
        parsed_url = urlsplit(params.url)
        if not parsed_url.scheme:
            return invalid_params("http/request url is invalid: relative URL without a base")
        if parsed_url.scheme not in ("http", "https"):
            return invalid_params(
                f"http/request only supports http and https URLs, got {parsed_url.scheme}"
            )
        if not parsed_url.netloc:
            return invalid_params("http/request url is invalid: relative URL without a base")

        headers_error = self.build_headers(params.headers)
        if isinstance(headers_error, JSONRPCErrorError):
            return headers_error

        body = None if params.body is None else params.body.into_inner()
        request = Request(
            params.url,
            data=body,
            method=params.method,
        )
        for header in params.headers:
            request.add_header(header.name, header.value)
        timeout = None if params.timeout_ms is None else params.timeout_ms / 1000

        try:
            response_obj = urlopen(request, timeout=timeout)
        except HTTPError as exc:
            response_obj = exc
        except Exception as exc:
            return internal_error(f"http/request failed: {exc}")

        try:
            status = int(getattr(response_obj, "status", getattr(response_obj, "code", 0)))
            headers = self.response_headers(response_obj.headers.items())
            chunks: list[bytes] = []
            while True:
                chunk = response_obj.read(64 * 1024)
                if not chunk:
                    break
                chunks.append(bytes(chunk))
        except Exception as exc:
            return internal_error(f"failed to read http/request response body: {exc}")
        finally:
            close = getattr(response_obj, "close", None)
            if close is not None:
                close()

        if params.stream_response:
            return (
                HttpRequestResponse(status=status, headers=headers, body=ByteChunk(b"")),
                PendingReqwestHttpBodyStream(params.request_id, chunks),
            )
        return (
            HttpRequestResponse(status=status, headers=headers, body=ByteChunk(b"".join(chunks))),
            None,
        )

    @staticmethod
    async def stream_body(
        pending_stream: PendingReqwestHttpBodyStream,
        notifications: Any,
    ) -> None:
        seq = 1
        for chunk in pending_stream.chunks:
            delta = HttpRequestBodyDeltaNotification(
                request_id=pending_stream.request_id,
                seq=seq,
                delta=ByteChunk(chunk),
                done=False,
                error=None,
            )
            if not await send_body_delta(notifications, delta):
                return
            seq += 1
        await send_body_delta(
            notifications,
            HttpRequestBodyDeltaNotification(
                request_id=pending_stream.request_id,
                seq=seq,
                delta=ByteChunk(b""),
                done=True,
                error=None,
            ),
        )

    @staticmethod
    def build_headers(headers: list[HttpHeader]) -> dict[str, str] | JSONRPCErrorError:
        result: dict[str, str] = {}
        for header in headers:
            name_error = _validate_http_header_name(header.name)
            if name_error is not None:
                return invalid_params(f"http/request header name is invalid: {name_error}")
            value_error = _validate_http_header_value(header.value)
            if value_error is not None:
                return invalid_params(
                    f"http/request header value is invalid for {header.name}: {value_error}"
                )
            result[header.name] = header.value
        return result

    @staticmethod
    def response_headers(headers: Any) -> list[HttpHeader]:
        result: list[HttpHeader] = []
        for name, value in headers:
            try:
                text = str(value)
            except Exception:
                continue
            result.append(HttpHeader(str(name), text))
        return result


class ReqwestHttpClient:
    async def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
        runner = ReqwestHttpRequestRunner.new(params.timeout_ms)
        result = await runner.run(replace(params, stream_response=False))
        if isinstance(result, JSONRPCErrorError):
            raise ExecServerError.http_request(result.message)
        response, _ = result
        return response

    async def http_request_stream(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, HttpResponseBodyStream]:
        runner = ReqwestHttpRequestRunner.new(params.timeout_ms)
        result = await runner.run(replace(params, stream_response=True))
        if isinstance(result, JSONRPCErrorError):
            raise ExecServerError.http_request(result.message)
        response, pending_stream = result
        if pending_stream is None:
            raise ExecServerError.protocol("http request stream did not return a response body stream")
        return response, HttpResponseBodyStream.local(pending_stream.chunks)


async def send_body_delta(notifications: Any, delta: HttpRequestBodyDeltaNotification) -> bool:
    try:
        result = notifications.notify(HTTP_REQUEST_BODY_DELTA_METHOD, delta)
        if inspect.isawaitable(result):
            await result
        return True
    except Exception:
        return False


_HTTP_TOKEN_SEPARATORS = set('()<>@,;:\\"/[]?={} \t')


def _validate_http_method(method: str) -> str | None:
    if not method:
        return "empty method"
    for ch in method:
        if ord(ch) < 33 or ord(ch) > 126 or ch in _HTTP_TOKEN_SEPARATORS:
            return f"invalid token character {ch!r}"
    return None


def _validate_http_header_name(name: str) -> str | None:
    if not name:
        return "empty header name"
    for ch in name:
        if ord(ch) < 33 or ord(ch) > 126 or ch in _HTTP_TOKEN_SEPARATORS:
            return f"invalid token character {ch!r}"
    return None


def _validate_http_header_value(value: str) -> str | None:
    if "\r" in value or "\n" in value:
        return "header value contains a newline"
    return None


class HttpClient:
    def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
        raise NotImplementedError("codex-exec-server HTTP transport is not ported")

    def http_request_stream(self, params: HttpRequestParams) -> tuple[HttpRequestResponse, Any]:
        raise NotImplementedError("codex-exec-server streamed HTTP transport is not ported")

LOCAL_FS = LocalFileSystem()
FileSystemResult = object

ERROR_BODY_PREVIEW_BYTES = 4096


@dataclass(frozen=True)
class RemoteEnvironmentConfig:
    base_url: str
    environment_id: str
    auth_provider: Any
    name: str = "codex-exec-server"

    @classmethod
    def new(
        cls,
        base_url: str,
        environment_id: str,
        auth_provider: Any,
    ) -> "RemoteEnvironmentConfig":
        return cls(
            base_url=base_url,
            environment_id=normalize_environment_id(environment_id),
            auth_provider=auth_provider,
        )

    def __repr__(self) -> str:
        return (
            "RemoteEnvironmentConfig("
            f"base_url={self.base_url!r}, "
            f"environment_id={self.environment_id!r}, "
            f"name={self.name!r}, "
            "auth_provider='<redacted>')"
        )


@dataclass(frozen=True)
class EnvironmentRegistryRegistrationResponse:
    environment_id: str
    url: str


class EnvironmentRegistryClient:
    def __init__(self, base_url: str, auth_provider: Any, http: Any | None = None) -> None:
        self.base_url = normalize_base_url(base_url)
        self.auth_provider = auth_provider
        self.http = http

    @classmethod
    def new(cls, base_url: str, auth_provider: Any, http: Any | None = None) -> "EnvironmentRegistryClient":
        return cls(base_url, auth_provider, http)

    def __repr__(self) -> str:
        return (
            "EnvironmentRegistryClient("
            f"base_url={self.base_url!r}, "
            "auth_provider='<redacted>', ..)"
        )

    async def register_environment(self, environment_id: str) -> EnvironmentRegistryRegistrationResponse:
        if self.http is None:
            raise ExecServerError.environment_registry_config(
                "environment registry HTTP client is not configured"
            )
        response = self.http.post(
            endpoint_url(self.base_url, f"/cloud/environment/{environment_id}/register"),
            headers=auth_provider_headers(self.auth_provider),
            follow_redirects=False,
        )
        if inspect.isawaitable(response):
            response = await response
        return await self.parse_json_response(response)

    async def parse_json_response(self, response: Any) -> EnvironmentRegistryRegistrationResponse:
        status = response_status(response)
        if 200 <= status < 300:
            payload = response_json(response)
            if inspect.isawaitable(payload):
                payload = await payload
            try:
                return EnvironmentRegistryRegistrationResponse(
                    environment_id=str(payload["environment_id"]),
                    url=str(payload["url"]),
                )
            except Exception as exc:
                raise ExecServerError(f"failed to parse environment registry response: {exc}") from exc

        body = response_text(response)
        if inspect.isawaitable(body):
            body = await body
        if status in {401, 403}:
            raise environment_registry_auth_error(status, body)
        raise environment_registry_http_error(status, body)


def auth_provider_headers(auth_provider: Any) -> dict[str, str]:
    if hasattr(auth_provider, "to_auth_headers"):
        return dict(auth_provider.to_auth_headers())
    if hasattr(auth_provider, "add_auth_headers"):
        headers: dict[str, str] = {}
        auth_provider.add_auth_headers(headers)
        return headers
    if isinstance(auth_provider, Mapping):
        return dict(auth_provider)
    return {}


def response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if callable(status):
        status = status()
    if hasattr(status, "value"):
        status = status.value
    return int(status)


def response_json(response: Any) -> Any:
    json_method = getattr(response, "json", None)
    if callable(json_method):
        return json_method()
    return getattr(response, "json_body")


def response_text(response: Any) -> str:
    text_method = getattr(response, "text", None)
    if callable(text_method):
        return text_method()
    return str(getattr(response, "body", ""))


def normalize_environment_id(environment_id: str) -> str:
    normalized = environment_id.strip()
    if not normalized:
        raise ExecServerError.environment_registry_config(
            "environment id is required for remote exec-server registration"
        )
    return normalized


def normalize_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ExecServerError.environment_registry_config(
            "environment registry base URL is required"
        )
    return normalized


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url}/{path.lstrip('/')}"


def environment_registry_auth_error(status: int, body: str) -> ExecServerError:
    message = registry_error_message(body) or "empty error body"
    return ExecServerError.environment_registry_auth(
        f"environment registry authentication failed ({status_text(status)}): {message}"
    )


def environment_registry_http_error(status: int, body: str) -> ExecServerError:
    code: str | None = None
    message: str | None = None
    try:
        error = json.loads(body).get("error")
        if isinstance(error, Mapping):
            raw_code = error.get("code")
            code = str(raw_code) if raw_code is not None else None
            raw_message = error.get("message")
            if raw_message is not None:
                message = str(raw_message)
    except Exception:
        pass
    if message is None:
        message = preview_error_body(body) or "empty or malformed error body"
    return ExecServerError.environment_registry_http(status, code, message)


def registry_error_message(body: str) -> str | None:
    try:
        error = json.loads(body).get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if message is not None:
                return str(message)
    except Exception:
        pass
    return preview_error_body(body)


def preview_error_body(body: str) -> str | None:
    trimmed = body.strip()
    if not trimmed:
        return None
    return "".join(list(trimmed)[:ERROR_BODY_PREVIEW_BYTES])


def status_text(status: int) -> str:
    known = {
        302: "Found",
        401: "Unauthorized",
        403: "Forbidden",
    }
    reason = known.get(status)
    return f"{status} {reason}" if reason else str(status)


async def run_main(listen_url: str, runtime_paths: ExecServerRuntimePaths) -> None:
    await run_transport(listen_url, runtime_paths)


async def run_remote_environment(
    config: RemoteEnvironmentConfig,
    runtime_paths: ExecServerRuntimePaths,
    *,
    registry_client: Any | None = None,
    websocket_connector: Any | None = None,
    serve_environment: Any | None = None,
    sleep: Any | None = None,
    max_iterations: int | None = None,
    stderr: Any | None = None,
) -> None:
    client = registry_client or EnvironmentRegistryClient.new(config.base_url, config.auth_provider)
    processor = ConnectionProcessor.new(runtime_paths)
    connect = websocket_connector or _connect_remote_environment_websocket
    serve = serve_environment or run_multiplexed_environment
    sleep_fn = sleep or asyncio.sleep
    backoff = 1
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        response = await client.register_environment(config.environment_id)
        print(
            "codex exec-server remote environment registered with environment_id "
            f"{response.environment_id}",
            file=stderr or sys.stderr,
        )
        try:
            websocket = await _maybe_await(connect(response.url))
        except Exception:
            websocket = None
        if websocket is not None:
            backoff = 1
            await _maybe_await(serve(websocket, processor))
        await _maybe_await(sleep_fn(backoff))
        backoff = min(backoff * 2, 30)
        iterations += 1


async def _connect_remote_environment_websocket(_url: str) -> Any:
    return await _connect_websocket_url(_url)


__all__ = [
    "CODEX_EXEC_SERVER_URL_ENV_VAR",
    "CODEX_FS_HELPER_ARG1",
    "CopyOptions",
    "CreateDirectoryOptions",
    "DEFAULT_LISTEN_URL",
    "DefaultEnvironmentProvider",
    "Environment",
    "EnvironmentManager",
    "EnvironmentProvider",
    "ExecBackend",
    "ExecClosedNotification",
    "ExecEnvPolicy",
    "ExecExitedNotification",
    "ExecOutputDeltaNotification",
    "ExecOutputStream",
    "ExecParams",
    "ExecProcess",
    "ExecProcessEvent",
    "ExecProcessEventReceiver",
    "ExecResponse",
    "ExecServerClient",
    "ExecServerClientConnectOptions",
    "ExecServerError",
    "ExecServerListenUrlParseError",
    "ExecServerRuntimePaths",
    "ExecutorFileSystem",
    "FileMetadata",
    "FileSystemResult",
    "FileSystemSandboxContext",
    "FsCopyParams",
    "FsCopyResponse",
    "FsCreateDirectoryParams",
    "FsCreateDirectoryResponse",
    "FsGetMetadataParams",
    "FsGetMetadataResponse",
    "FsReadDirectoryEntry",
    "FsReadDirectoryParams",
    "FsReadDirectoryResponse",
    "FsReadFileParams",
    "FsReadFileResponse",
    "FsRemoveParams",
    "FsRemoveResponse",
    "FsWriteFileParams",
    "FsWriteFileResponse",
    "HttpClient",
    "HttpHeader",
    "HttpRequestBodyDeltaNotification",
    "HttpRequestParams",
    "HttpRequestResponse",
    "HttpResponseBodyStream",
    "InitializeParams",
    "InitializeResponse",
    "LOCAL_ENVIRONMENT_ID",
    "LOCAL_FS",
    "LocalFileSystem",
    "ProcessId",
    "ProcessOutputChunk",
    "REMOTE_ENVIRONMENT_ID",
    "ReadDirectoryEntry",
    "ReadParams",
    "ReadResponse",
    "RemoteEnvironmentConfig",
    "RemoteExecServerConnectArgs",
    "RemoveOptions",
    "ReqwestHttpClient",
    "StartedExecProcess",
    "TerminateParams",
    "TerminateResponse",
    "WriteParams",
    "WriteResponse",
    "WriteStatus",
    "run_fs_helper_main",
    "run_main",
    "run_remote_environment",
]
