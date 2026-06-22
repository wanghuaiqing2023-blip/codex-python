"""Header helper contracts for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/requests/headers.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import MutableMapping


class SubAgentSource(str, Enum):
    REVIEW = "review"
    COMPACT = "compact"
    MEMORY_CONSOLIDATION = "memory_consolidation"
    THREAD_SPAWN = "collab_spawn"


@dataclass(frozen=True)
class SessionSource:
    kind: str
    subagent: SubAgentSource | str | None = None

    @classmethod
    def sub_agent(cls, subagent: SubAgentSource | str) -> "SessionSource":
        return cls("subagent", subagent)

    @classmethod
    def other(cls) -> "SessionSource":
        return cls("other")


def build_session_headers(
    session_id: str | None,
    thread_id: str | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if session_id is not None:
        insert_header(headers, "session-id", session_id)
    if thread_id is not None:
        insert_header(headers, "thread-id", thread_id)
    return headers


def subagent_header(source: SessionSource | None) -> str | None:
    if source is None or source.kind != "subagent":
        return None
    subagent = source.subagent
    if isinstance(subagent, SubAgentSource):
        return subagent.value
    return str(subagent) if subagent is not None else None


def insert_header(headers: MutableMapping[str, str], name: str, value: str) -> None:
    if _valid_header_name(name) and _valid_header_value(value):
        headers[name.lower()] = value


def _valid_header_name(name: str) -> bool:
    if not name:
        return False
    separators = set('()<>@,;:\\"/[]?={} \t')
    return all(33 <= ord(ch) <= 126 and ch not in separators for ch in name)


def _valid_header_value(value: str) -> bool:
    return all(ch == "\t" or " " <= ch <= "~" for ch in value)
