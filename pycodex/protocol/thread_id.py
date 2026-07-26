"""Thread identifier protocol type.

Ported from ``codex/codex-rs/protocol/src/thread_id.rs``.
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

    def __post_init__(self) -> None:
        if not isinstance(self.uuid, uuid.UUID):
            raise TypeError("thread id uuid must be a UUID")

    @classmethod
    def new(cls) -> "ThreadId":
        return cls(_new_uuid())

    @classmethod
    def default(cls) -> "ThreadId":
        return cls.new()

    @classmethod
    def from_string(cls, value: str) -> "ThreadId":
        if not isinstance(value, str):
            raise TypeError("thread id must be a string")
        return cls(uuid.UUID(value))

    def to_json(self) -> str:
        return str(self.uuid)

    def __str__(self) -> str:
        return str(self.uuid)
