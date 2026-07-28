"""Rust ``codex-thread-store::error`` owner."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from inspect import isawaitable
from pathlib import Path
from time import monotonic
from typing import Any, Mapping, Protocol

from pycodex.protocol import (
    USER_MESSAGE_BEGIN,
    AskForApproval,
    EventMsg,
    GitInfo,
    RolloutItem,
    SandboxPolicy,
    SessionMetaLine,
    SessionSource,
    ThreadId,
    ThreadMemoryMode,
    ThreadSource,
    UserMessageEvent,
)
from pycodex.rollout import (
    ARCHIVED_SESSIONS_SUBDIR,
    EventPersistenceMode,
    RolloutRecorder,
    RolloutRecorderParams,
    ThreadListLayout,
    append_rollout_item_to_path,
    append_thread_name,
    find_archived_thread_path_by_id_str,
    find_thread_name_by_id,
    find_thread_names_by_ids,
    find_thread_path_by_id_str,
    first_rollout_content_match_snippet,
    get_threads,
    get_threads_in_root,
    parse_cursor,
    read_thread_item_from_rollout,
    read_session_meta_line,
    persisted_rollout_items,
    rollout_date_parts,
    search_rollout_paths,
)
from pycodex.rollout.list import list_threads_from_state_metadata

ThreadStoreResult = Any

class ThreadStoreError(Exception):
    kind: str

    def __init__(self, kind: str, message_text: str, **fields: Any) -> None:
        super().__init__(message_text)
        self.kind = kind
        self.fields = fields

    @classmethod
    def thread_not_found(cls, thread_id: ThreadId) -> "ThreadStoreError":
        return cls("thread_not_found", f"thread {thread_id} not found", thread_id=thread_id)

    @classmethod
    def invalid_request(cls, message: str) -> "ThreadStoreError":
        return cls("invalid_request", f"invalid thread-store request: {message}", message=message)

    @classmethod
    def conflict(cls, message: str) -> "ThreadStoreError":
        return cls("conflict", f"thread-store conflict: {message}", message=message)

    @classmethod
    def unsupported(cls, operation: str) -> "ThreadStoreError":
        return cls("unsupported", f"thread-store unsupported operation: {operation}", operation=operation)

    @classmethod
    def internal(cls, message: str) -> "ThreadStoreError":
        return cls("internal", f"thread-store internal error: {message}", message=message)
