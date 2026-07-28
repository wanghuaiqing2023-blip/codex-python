"""Rust-aligned owner for ``codex-rollout::session_index``."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from pycodex.protocol import SessionSource
from pycodex.protocol.models import ResponseItem
from pycodex.protocol.protocol import (
    USER_MESSAGE_BEGIN,
    CompactedItem,
    EventMsg,
    InitialHistory,
    ResumedHistory,
    RolloutItem,
    ThreadId,
    ThreadRolledBackEvent,
    TurnContextItem,
)
from pycodex.utils.string import sanitize_metric_tag_value

from pycodex.protocol.protocol import GitInfo, SessionMeta, SessionMetaLine
from pycodex.state.model.backfill_state import BackfillState
from pycodex.state.model.thread_metadata import (
    Anchor,
    BackfillStats,
    ExtractionOutcome,
    ThreadMetadata,
    ThreadMetadataBuilder,
)
from pycodex.rollout import SESSIONS_SUBDIR

SESSION_INDEX_FILE = "session_index.jsonl"

@dataclass(frozen=True)
class SessionIndexEntry:
    id: str
    thread_name: str
    updated_at: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SessionIndexEntry":
        return cls(
            id=str(data["id"]),
            thread_name=str(data["thread_name"]),
            updated_at=str(data["updated_at"]),
        )

    def to_mapping(self) -> dict[str, str]:
        return {"id": self.id, "thread_name": self.thread_name, "updated_at": self.updated_at}

def session_index_path(codex_home: Path) -> Path:
    return Path(codex_home) / SESSION_INDEX_FILE

def count_session_rollout_files(codex_home: Path) -> int:
    """Count persisted session JSONL rollout files below ``<codex_home>/sessions``."""

    sessions_dir = Path(codex_home) / SESSIONS_SUBDIR
    if not sessions_dir.exists():
        return 0
    return sum(1 for path in sessions_dir.rglob("*.jsonl") if path.is_file())

def append_thread_name(codex_home: Path, thread_id: str | uuid.UUID, name: str) -> None:
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    append_session_index_entry(
        codex_home,
        SessionIndexEntry(id=str(thread_id), thread_name=name, updated_at=updated_at),
    )

def append_session_index_entry(codex_home: Path, entry: SessionIndexEntry) -> None:
    path = session_index_path(codex_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(entry.to_mapping(), separators=(",", ":")))
        file.write("\n")

def _thread_ids_matching_search_term(codex_home: Path, search_term: str) -> set[str]:
    matches: set[str] = set()
    if search_term == "":
        return matches
    for entry in _read_index_entries(codex_home):
        if entry.thread_name.strip() and search_term in entry.thread_name:
            matches.add(entry.id)
    return matches

def find_thread_name_by_id(codex_home: Path, thread_id: str | uuid.UUID) -> str | None:
    entry = _scan_index_from_end(codex_home, lambda candidate: candidate.id == str(thread_id))
    return entry.thread_name if entry is not None else None

def find_thread_names_by_ids(codex_home: Path, thread_ids: Iterable[str | uuid.UUID]) -> dict[str, str]:
    wanted = {str(thread_id) for thread_id in thread_ids}
    if not wanted:
        return {}
    names: dict[str, str] = {}
    for entry in _read_index_entries(codex_home):
        if entry.id in wanted and entry.thread_name.strip():
            names[entry.id] = entry.thread_name
    return names

def find_thread_meta_by_name_str(codex_home: Path, name: str, state_db_ctx: Any = None) -> tuple[Path, SessionMetaLine] | None:
    """Find the newest indexed thread name with a readable rollout header."""

    if not name.strip():
        return None

    seen: set[str] = set()
    for entry in reversed(_read_index_entries(codex_home)):
        if entry.id in seen:
            continue
        seen.add(entry.id)
        if entry.thread_name != name:
            continue
        path = find_thread_path_by_id_str(codex_home, entry.id, state_db_ctx)
        if path is None:
            continue
        try:
            return path, read_session_meta_line(path)
        except ValueError:
            continue
    return None

def _scan_index_from_end(codex_home: Path, predicate: Callable[[SessionIndexEntry], bool]) -> SessionIndexEntry | None:
    for entry in reversed(_read_index_entries(codex_home)):
        if predicate(entry):
            return entry
    return None

def _read_index_entries(codex_home: Path) -> list[SessionIndexEntry]:
    path = session_index_path(codex_home)
    if not path.exists():
        return []
    entries: list[SessionIndexEntry] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                data = json.loads(trimmed)
                entries.append(SessionIndexEntry.from_mapping(data))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return entries

from pycodex.rollout.list import find_thread_path_by_id_str, read_session_meta_line

__all__ = ['SESSION_INDEX_FILE', 'SessionIndexEntry', 'append_session_index_entry', 'append_thread_name', 'count_session_rollout_files', 'find_thread_meta_by_name_str', 'find_thread_name_by_id', 'find_thread_names_by_ids', 'session_index_path']
