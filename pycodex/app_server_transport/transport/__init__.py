from __future__ import annotations

import asyncio
import itertools
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.app_server_transport.outgoing_message import ConnectionId
from pycodex.app_server_transport.outgoing_message import OutgoingError
from pycodex.app_server_transport.outgoing_message import OutgoingMessage
from pycodex.app_server_transport.outgoing_message import QueuedOutgoingMessage
from pycodex.app_server_transport.transport.stdio import start_stdio_connection

CHANNEL_CAPACITY = 128
OVERLOADED_ERROR_CODE = -32001
APP_SERVER_CONTROL_SOCKET_DIR_NAME = "app-server-control"
APP_SERVER_CONTROL_SOCKET_FILE_NAME = "app-server-control.sock"
APP_SERVER_STARTUP_LOCK_FILE_NAME = "app-server-startup.lock"


class AppServerTransportKind(Enum):
    STDIO = "stdio"
    UNIX_SOCKET = "unix-socket"
    WEB_SOCKET = "web-socket"
    OFF = "off"


@dataclass(frozen=True)
class AppServerTransport:
    kind: AppServerTransportKind
    socket_path: Path | None = None
    bind_address: str | None = None

    DEFAULT_LISTEN_URL = "stdio://"

    @classmethod
    def from_listen_url(cls, listen_url: str) -> "AppServerTransport":
        if listen_url == cls.DEFAULT_LISTEN_URL:
            return cls(AppServerTransportKind.STDIO)
        if listen_url.startswith("unix://"):
            raw_path = listen_url.removeprefix("unix://")
            path = (
                app_server_control_socket_path(_find_codex_home())
                if not raw_path
                else Path(raw_path).resolve()
            )
            return cls(AppServerTransportKind.UNIX_SOCKET, socket_path=path)
        if listen_url == "off":
            return cls(AppServerTransportKind.OFF)
        if listen_url.startswith("ws://"):
            bind_address = listen_url.removeprefix("ws://")
            _parse_bind_address(bind_address)
            return cls(AppServerTransportKind.WEB_SOCKET, bind_address=bind_address)
        raise AppServerTransportParseError(
            f"unsupported --listen URL `{listen_url}`; expected `stdio://`, "
            "`unix://`, `unix://PATH`, `ws://IP:PORT`, or `off`"
        )


class AppServerTransportParseError(ValueError):
    pass


class ConnectionOrigin(Enum):
    STDIO = "Stdio"
    IN_PROCESS = "InProcess"
    WEB_SOCKET = "WebSocket"
    REMOTE_CONTROL = "RemoteControl"


class TransportEventKind(Enum):
    CONNECTION_OPENED = "ConnectionOpened"
    CONNECTION_CLOSED = "ConnectionClosed"
    INCOMING_MESSAGE = "IncomingMessage"


@dataclass(frozen=True)
class TransportEvent:
    kind: TransportEventKind
    connection_id: ConnectionId
    origin: ConnectionOrigin | None = None
    writer: asyncio.Queue[QueuedOutgoingMessage] | None = None
    disconnect_sender: Any | None = None
    message: Any | None = None

    @classmethod
    def connection_opened(
        cls,
        connection_id: ConnectionId,
        origin: ConnectionOrigin,
        writer: asyncio.Queue[QueuedOutgoingMessage],
        disconnect_sender: Any | None,
    ) -> "TransportEvent":
        return cls(
            TransportEventKind.CONNECTION_OPENED,
            connection_id,
            origin=origin,
            writer=writer,
            disconnect_sender=disconnect_sender,
        )

    @classmethod
    def connection_closed(cls, connection_id: ConnectionId) -> "TransportEvent":
        return cls(TransportEventKind.CONNECTION_CLOSED, connection_id)

    @classmethod
    def incoming_message(
        cls,
        connection_id: ConnectionId,
        message: Any,
    ) -> "TransportEvent":
        return cls(
            TransportEventKind.INCOMING_MESSAGE,
            connection_id,
            message=message,
        )


_CONNECTION_ID_COUNTER = itertools.count()


def next_connection_id() -> ConnectionId:
    return ConnectionId(next(_CONNECTION_ID_COUNTER))


def app_server_control_socket_path(codex_home: str | os.PathLike[str]) -> Path:
    return (
        Path(codex_home)
        / APP_SERVER_CONTROL_SOCKET_DIR_NAME
        / APP_SERVER_CONTROL_SOCKET_FILE_NAME
    ).resolve()


def app_server_startup_lock_path(codex_home: str | os.PathLike[str]) -> Path:
    return (
        Path(codex_home)
        / APP_SERVER_CONTROL_SOCKET_DIR_NAME
        / APP_SERVER_STARTUP_LOCK_FILE_NAME
    ).resolve()


async def forward_incoming_message(
    transport_event_tx: asyncio.Queue[TransportEvent],
    writer: asyncio.Queue[QueuedOutgoingMessage],
    connection_id: ConnectionId,
    payload: str,
) -> bool:
    try:
        message = json.loads(payload)
    except json.JSONDecodeError:
        return True
    return await enqueue_incoming_message(
        transport_event_tx,
        writer,
        connection_id,
        message,
    )


async def enqueue_incoming_message(
    transport_event_tx: asyncio.Queue[TransportEvent],
    writer: asyncio.Queue[QueuedOutgoingMessage],
    connection_id: ConnectionId,
    message: Any,
) -> bool:
    event = TransportEvent.incoming_message(connection_id, message)
    try:
        transport_event_tx.put_nowait(event)
        return True
    except asyncio.QueueFull:
        if _jsonrpc_message_kind(message) != "request":
            await transport_event_tx.put(event)
            return True
        request_id = _mapping_field(message, "id")
        overload = OutgoingMessage.error(
            OutgoingError(
                error={
                    "code": OVERLOADED_ERROR_CODE,
                    "message": "Server overloaded; retry later.",
                },
                id=request_id,
            )
        )
        try:
            writer.put_nowait(QueuedOutgoingMessage.new(overload))
        except asyncio.QueueFull:
            pass
        return True


def serialize_outgoing_message(message: OutgoingMessage) -> str | None:
    try:
        return json.dumps(
            message.to_mapping(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return None


def _parse_bind_address(value: str) -> tuple[str, int]:
    host, separator, raw_port = value.rpartition(":")
    if not separator or not host:
        raise AppServerTransportParseError(
            f"invalid websocket --listen URL `ws://{value}`; expected `ws://IP:PORT`"
        )
    try:
        port = int(raw_port)
    except ValueError:
        raise AppServerTransportParseError(
            f"invalid websocket --listen URL `ws://{value}`; expected `ws://IP:PORT`"
        ) from None
    if not 0 <= port <= 65535:
        raise AppServerTransportParseError(
            f"invalid websocket --listen URL `ws://{value}`; expected `ws://IP:PORT`"
        )
    return host.strip("[]"), port


def _find_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).resolve()


def _jsonrpc_message_kind(message: Any) -> str | None:
    if isinstance(message, dict):
        if "method" in message and "id" in message:
            return "request"
        if "method" in message:
            return "notification"
        if "result" in message or "error" in message:
            return "response"
    return getattr(message, "kind", None)


def _mapping_field(message: Any, name: str) -> Any:
    if isinstance(message, dict):
        return message.get(name)
    return getattr(message, name, None)


from pycodex.app_server_transport.transport.auth import WebsocketAuthPolicy
from pycodex.app_server_transport.transport.auth import policy_from_settings
from pycodex.app_server_transport.transport.unix_socket import AppServerStartupLock
from pycodex.app_server_transport.transport.unix_socket import (
    acquire_app_server_startup_lock,
)
from pycodex.app_server_transport.transport.unix_socket import prepare_control_socket_path
from pycodex.app_server_transport.transport.unix_socket import (
    start_control_socket_acceptor,
)
from pycodex.app_server_transport.transport.websocket import start_websocket_acceptor
from pycodex.app_server_transport.transport.remote_control import (
    RemoteControlHandle,
    RemoteControlStartConfig,
    RemoteControlUnavailable,
    start_remote_control,
)


__all__ = [
    "AppServerStartupLock",
    "AppServerTransport",
    "AppServerTransportKind",
    "AppServerTransportParseError",
    "CHANNEL_CAPACITY",
    "ConnectionOrigin",
    "RemoteControlHandle",
    "RemoteControlStartConfig",
    "RemoteControlUnavailable",
    "TransportEvent",
    "TransportEventKind",
    "WebsocketAuthPolicy",
    "acquire_app_server_startup_lock",
    "app_server_control_socket_path",
    "app_server_startup_lock_path",
    "enqueue_incoming_message",
    "forward_incoming_message",
    "next_connection_id",
    "policy_from_settings",
    "prepare_control_socket_path",
    "serialize_outgoing_message",
    "start_control_socket_acceptor",
    "start_remote_control",
    "start_stdio_connection",
    "start_websocket_acceptor",
]
