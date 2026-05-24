"""Thread and session id protocol wrappers.

Ported from:

- ``codex/codex-rs/protocol/src/thread_id.rs``
- ``codex/codex-rs/protocol/src/session_id.rs``
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


def _new_uuid() -> uuid.UUID:
    uuid7 = getattr(uuid, "uuid7", None)
    if uuid7 is not None:
        return uuid7()
    return uuid.uuid4()


@dataclass(frozen=True)
class ThreadId:
    uuid: uuid.UUID

    @classmethod
    def new(cls) -> "ThreadId":
        return cls(_new_uuid())

    @classmethod
    def default(cls) -> "ThreadId":
        return cls.new()

    @classmethod
    def from_string(cls, value: str) -> "ThreadId":
        return cls(uuid.UUID(value))

    def to_json(self) -> str:
        return str(self.uuid)

    def __str__(self) -> str:
        return str(self.uuid)


@dataclass(frozen=True)
class SessionId:
    uuid: uuid.UUID

    @classmethod
    def new(cls) -> "SessionId":
        return cls(_new_uuid())

    @classmethod
    def default(cls) -> "SessionId":
        return cls.new()

    @classmethod
    def from_string(cls, value: str) -> "SessionId":
        return cls(uuid.UUID(value))

    @classmethod
    def from_thread_id(cls, value: ThreadId) -> "SessionId":
        return cls(value.uuid)

    def to_thread_id(self) -> ThreadId:
        return ThreadId(self.uuid)

    def to_json(self) -> str:
        return str(self.uuid)

    def __str__(self) -> str:
        return str(self.uuid)
