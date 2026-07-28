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


CHANNEL_CAPACITY = 128


STDIO_TERMINATION_GRACE_PERIOD = 2.0


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


from pycodex.exec_server.rpc import _maybe_await, encode_server_message
from pycodex.exec_server.server.processor import _SERVER_ROUTE_DISCONNECTED
