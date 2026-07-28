from __future__ import annotations

import ipaddress
import platform
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from pycodex.app_server_transport.outgoing_message import OutgoingMessage


@dataclass(frozen=True)
class RemoteControlTarget:
    websocket_url: str
    enroll_url: str


@dataclass(frozen=True)
class EnrollRemoteServerRequest:
    name: str
    installation_id: str
    os: str = platform.system().lower()
    arch: str = platform.machine().lower()
    app_server_version: str = "0.1.0"

    def to_mapping(self) -> dict[str, str]:
        return {
            "name": self.name,
            "os": self.os,
            "arch": self.arch,
            "app_server_version": self.app_server_version,
            "installation_id": self.installation_id,
        }


@dataclass(frozen=True)
class EnrollRemoteServerResponse:
    server_id: str
    environment_id: str


@dataclass(frozen=True)
class ClientId:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class StreamId:
    value: str

    @classmethod
    def new_random(cls) -> "StreamId":
        return cls(str(uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ClientEvent:
    class Kind(Enum):
        CLIENT_MESSAGE = "client_message"
        CLIENT_MESSAGE_CHUNK = "client_message_chunk"
        ACK = "ack"
        PING = "ping"
        CLIENT_CLOSED = "client_closed"

    kind: Kind
    message: Any = None
    segment_id: int | None = None
    segment_count: int | None = None
    message_size_bytes: int | None = None
    message_chunk_base64: str | None = None

    @classmethod
    def client_message(cls, message: Any) -> "ClientEvent":
        return cls(cls.Kind.CLIENT_MESSAGE, message=message)

    @classmethod
    def client_message_chunk(
        cls,
        *,
        segment_id: int,
        segment_count: int,
        message_size_bytes: int,
        message_chunk_base64: str,
    ) -> "ClientEvent":
        return cls(
            cls.Kind.CLIENT_MESSAGE_CHUNK,
            segment_id=segment_id,
            segment_count=segment_count,
            message_size_bytes=message_size_bytes,
            message_chunk_base64=message_chunk_base64,
        )

    @classmethod
    def ack(cls, *, segment_id: int | None = None) -> "ClientEvent":
        return cls(cls.Kind.ACK, segment_id=segment_id)

    @classmethod
    def ping(cls) -> "ClientEvent":
        return cls(cls.Kind.PING)

    @classmethod
    def client_closed(cls) -> "ClientEvent":
        return cls(cls.Kind.CLIENT_CLOSED)

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.kind.value}
        if self.kind is self.Kind.CLIENT_MESSAGE:
            result["message"] = self.message
        elif self.kind is self.Kind.CLIENT_MESSAGE_CHUNK:
            result.update(
                {
                    "segment_id": self.segment_id,
                    "segment_count": self.segment_count,
                    "message_size_bytes": self.message_size_bytes,
                    "message_chunk_base64": self.message_chunk_base64,
                }
            )
        elif self.kind is self.Kind.ACK and self.segment_id is not None:
            result["segment_id"] = self.segment_id
        return result

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ClientEvent":
        kind = cls.Kind(value["type"])
        if kind is cls.Kind.CLIENT_MESSAGE:
            return cls.client_message(value.get("message"))
        if kind is cls.Kind.CLIENT_MESSAGE_CHUNK:
            return cls.client_message_chunk(
                segment_id=int(value["segment_id"]),
                segment_count=int(value["segment_count"]),
                message_size_bytes=int(value["message_size_bytes"]),
                message_chunk_base64=str(value["message_chunk_base64"]),
            )
        if kind is cls.Kind.ACK:
            segment_id = value.get("segment_id")
            return cls.ack(segment_id=None if segment_id is None else int(segment_id))
        if kind is cls.Kind.PING:
            return cls.ping()
        return cls.client_closed()


@dataclass(frozen=True)
class ClientEnvelope:
    event: ClientEvent
    client_id: ClientId
    stream_id: StreamId | None = None
    seq_id: int | None = None
    cursor: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        result = self.event.to_mapping()
        result["client_id"] = self.client_id.value
        if self.stream_id is not None:
            result["stream_id"] = self.stream_id.value
        if self.seq_id is not None:
            result["seq_id"] = self.seq_id
        if self.cursor is not None:
            result["cursor"] = self.cursor
        return result

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ClientEnvelope":
        stream_id = value.get("stream_id")
        seq_id = value.get("seq_id")
        return cls(
            event=ClientEvent.from_mapping(value),
            client_id=ClientId(str(value["client_id"])),
            stream_id=None if stream_id is None else StreamId(str(stream_id)),
            seq_id=None if seq_id is None else int(seq_id),
            cursor=value.get("cursor"),
        )


class PongStatus(Enum):
    ACTIVE = "active"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ServerEvent:
    class Kind(Enum):
        SERVER_MESSAGE = "server_message"
        SERVER_MESSAGE_CHUNK = "server_message_chunk"
        ACK = "ack"
        PONG = "pong"

    kind: Kind
    message: OutgoingMessage | None = None
    segment_id: int | None = None
    segment_count: int | None = None
    message_size_bytes: int | None = None
    message_chunk_base64: str | None = None
    status: PongStatus | None = None

    @classmethod
    def server_message(cls, message: OutgoingMessage) -> "ServerEvent":
        return cls(cls.Kind.SERVER_MESSAGE, message=message)

    @classmethod
    def server_message_chunk(
        cls,
        *,
        segment_id: int,
        segment_count: int,
        message_size_bytes: int,
        message_chunk_base64: str,
    ) -> "ServerEvent":
        return cls(
            cls.Kind.SERVER_MESSAGE_CHUNK,
            segment_id=segment_id,
            segment_count=segment_count,
            message_size_bytes=message_size_bytes,
            message_chunk_base64=message_chunk_base64,
        )

    @classmethod
    def ack(cls) -> "ServerEvent":
        return cls(cls.Kind.ACK)

    @classmethod
    def pong(cls, status: PongStatus) -> "ServerEvent":
        return cls(cls.Kind.PONG, status=status)

    def wire_segment_id(self) -> int | None:
        if self.kind is self.Kind.SERVER_MESSAGE_CHUNK:
            return self.segment_id
        return None

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.kind.value}
        if self.kind is self.Kind.SERVER_MESSAGE:
            if self.message is None:
                raise ValueError("server_message requires message")
            result["message"] = self.message.to_mapping()
        elif self.kind is self.Kind.SERVER_MESSAGE_CHUNK:
            result.update(
                {
                    "segment_id": self.segment_id,
                    "segment_count": self.segment_count,
                    "message_size_bytes": self.message_size_bytes,
                    "message_chunk_base64": self.message_chunk_base64,
                }
            )
        elif self.kind is self.Kind.PONG:
            if self.status is None:
                raise ValueError("pong requires status")
            result["status"] = self.status.value
        return result


@dataclass(frozen=True)
class ServerEnvelope:
    event: ServerEvent
    client_id: ClientId
    stream_id: StreamId
    seq_id: int

    def to_mapping(self) -> dict[str, Any]:
        result = self.event.to_mapping()
        result.update(
            {
                "client_id": self.client_id.value,
                "stream_id": self.stream_id.value,
                "seq_id": self.seq_id,
            }
        )
        return result


def _is_localhost(host: str | None) -> bool:
    if host == "localhost":
        return True
    if host is None:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_allowed_chatgpt_host(host: str | None) -> bool:
    if host is None:
        return False
    return (
        host in {"chatgpt.com", "chatgpt-staging.com"}
        or host.endswith(".chatgpt.com")
        or host.endswith(".chatgpt-staging.com")
    )


def normalize_remote_control_url(remote_control_url: str) -> RemoteControlTarget:
    try:
        parsed = urlparse(remote_control_url)
        host = parsed.hostname
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("missing URL scheme or host")
        parsed.port
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"invalid remote control URL `{remote_control_url}`: {exc}"
        ) from exc

    localhost = _is_localhost(host)
    if parsed.scheme == "https" and (localhost or _is_allowed_chatgpt_host(host)):
        websocket_scheme = "wss"
    elif parsed.scheme == "http" and localhost:
        websocket_scheme = "ws"
    else:
        raise ValueError(
            f"invalid remote control URL `{remote_control_url}`; expected HTTPS URL "
            "for chatgpt.com or chatgpt-staging.com, or HTTP/HTTPS URL for localhost"
        )

    base_path = parsed.path if parsed.path.endswith("/") else f"{parsed.path}/"
    normalized = urlunparse(parsed._replace(path=base_path))
    enroll_url = urljoin(normalized, "wham/remote/control/server/enroll")
    websocket_http_url = urljoin(normalized, "wham/remote/control/server")
    websocket_parts = urlparse(websocket_http_url)._replace(scheme=websocket_scheme)
    return RemoteControlTarget(
        websocket_url=urlunparse(websocket_parts),
        enroll_url=enroll_url,
    )


__all__ = [
    "ClientEnvelope",
    "ClientEvent",
    "ClientId",
    "EnrollRemoteServerRequest",
    "EnrollRemoteServerResponse",
    "PongStatus",
    "RemoteControlTarget",
    "ServerEnvelope",
    "ServerEvent",
    "StreamId",
    "normalize_remote_control_url",
]

