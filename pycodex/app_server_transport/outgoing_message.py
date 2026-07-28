from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True, order=True)
class ConnectionId:
    value: int

    def __str__(self) -> str:
        return str(self.value)


class OutgoingMessageKind(Enum):
    REQUEST = "Request"
    APP_SERVER_NOTIFICATION = "AppServerNotification"
    RESPONSE = "Response"
    ERROR = "Error"


@dataclass(frozen=True)
class OutgoingResponse:
    id: Any
    result: Any


@dataclass(frozen=True)
class OutgoingError:
    error: Any
    id: Any


@dataclass(frozen=True)
class OutgoingMessage:
    kind: OutgoingMessageKind
    payload: Any

    @classmethod
    def request(cls, request: Any) -> "OutgoingMessage":
        return cls(OutgoingMessageKind.REQUEST, request)

    @classmethod
    def app_server_notification(cls, notification: Any) -> "OutgoingMessage":
        return cls(OutgoingMessageKind.APP_SERVER_NOTIFICATION, notification)

    @classmethod
    def response(cls, response: OutgoingResponse) -> "OutgoingMessage":
        return cls(OutgoingMessageKind.RESPONSE, response)

    @classmethod
    def error(cls, error: OutgoingError) -> "OutgoingMessage":
        return cls(OutgoingMessageKind.ERROR, error)

    def to_mapping(self) -> Any:
        payload = _to_mapping(self.payload)
        if self.kind in {
            OutgoingMessageKind.REQUEST,
            OutgoingMessageKind.APP_SERVER_NOTIFICATION,
        }:
            return payload
        if self.kind is OutgoingMessageKind.RESPONSE:
            return {"id": payload["id"], "result": payload["result"]}
        return {"error": payload["error"], "id": payload["id"]}


@dataclass
class QueuedOutgoingMessage:
    message: OutgoingMessage
    write_complete_tx: Any | None = None

    @classmethod
    def new(cls, message: OutgoingMessage) -> "QueuedOutgoingMessage":
        return cls(message=message)


def _to_mapping(value: Any) -> Any:
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, dict):
        return value
    if isinstance(value, OutgoingResponse):
        return {"id": value.id, "result": value.result}
    if isinstance(value, OutgoingError):
        return {"error": value.error, "id": value.id}
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value


__all__ = [
    "ConnectionId",
    "OutgoingError",
    "OutgoingMessage",
    "OutgoingMessageKind",
    "OutgoingResponse",
    "QueuedOutgoingMessage",
]
