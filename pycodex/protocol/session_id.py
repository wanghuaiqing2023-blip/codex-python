"""Session identifier protocol type.

Ported from ``codex/codex-rs/protocol/src/session_id.rs``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .thread_id import ThreadId


def _new_uuid() -> uuid.UUID:
    uuid7 = getattr(uuid, "uuid7", None)
    if uuid7 is not None:
        return uuid7()
    return uuid.uuid4()


@dataclass(frozen=True)
class SessionId:
    uuid: uuid.UUID

    def __post_init__(self) -> None:
        if not isinstance(self.uuid, uuid.UUID):
            raise TypeError("session id uuid must be a UUID")

    @classmethod
    def new(cls) -> "SessionId":
        return cls(_new_uuid())

    @classmethod
    def default(cls) -> "SessionId":
        return cls.new()

    @classmethod
    def from_string(cls, value: str) -> "SessionId":
        if not isinstance(value, str):
            raise TypeError("session id must be a string")
        return cls(uuid.UUID(value))

    @classmethod
    def from_thread_id(cls, value: ThreadId) -> "SessionId":
        if not isinstance(value, ThreadId):
            raise TypeError("value must be a ThreadId")
        return cls(value.uuid)

    def to_thread_id(self) -> ThreadId:
        return ThreadId(self.uuid)

    def to_json(self) -> str:
        return str(self.uuid)

    def __str__(self) -> str:
        return str(self.uuid)
