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


class RelayFrameBodyKind(str, Enum):
    DATA = "data"
    ACK = "ack"
    RESUME = "resume"
    RESET = "reset"
    HEARTBEAT = "heartbeat"


RELAY_MESSAGE_FRAME_VERSION = 1


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


from pycodex.exec_server.client import ExecServerError
from pycodex.exec_server.connection import CHANNEL_CAPACITY, JsonRpcConnection, JsonRpcConnectionEvent, JsonRpcWebSocketMessage, _websocket_recv, _websocket_send
from pycodex.exec_server.relay_proto.generated import RelayAck, RelayData, RelayHeartbeat, RelayMessageFrame, RelayReset, RelayResume



