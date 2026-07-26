"""Rust-aligned ``codex_core::rollout`` re-export surface."""

from __future__ import annotations

from pycodex.rollout import (
    ARCHIVED_SESSIONS_SUBDIR,
    INTERACTIVE_SESSION_SOURCES,
    SESSIONS_SUBDIR,
    Cursor,
    EventPersistenceMode,
    RolloutRecorder,
    RolloutRecorderParams,
    SessionMeta,
    SortDirection,
    ThreadItem,
    ThreadSortKey,
    ThreadsPage,
    append_thread_name,
    find_archived_thread_path_by_id_str,
    find_thread_meta_by_name_str,
    find_thread_name_by_id,
    find_thread_names_by_ids,
    find_thread_path_by_id_str,
    parse_cursor,
    read_head_for_summary,
    read_session_meta_line,
    rollout_date_parts,
)

from pycodex.core.session_rollout_init_error import map_session_init_error

from . import list, truncation

find_conversation_path_by_id_str = find_thread_path_by_id_str


__all__ = [
    "ARCHIVED_SESSIONS_SUBDIR",
    "Cursor",
    "EventPersistenceMode",
    "INTERACTIVE_SESSION_SOURCES",
    "RolloutRecorder",
    "RolloutRecorderParams",
    "SESSIONS_SUBDIR",
    "SessionMeta",
    "SortDirection",
    "ThreadItem",
    "ThreadSortKey",
    "ThreadsPage",
    "append_thread_name",
    "find_archived_thread_path_by_id_str",
    "find_conversation_path_by_id_str",
    "find_thread_meta_by_name_str",
    "find_thread_name_by_id",
    "find_thread_names_by_ids",
    "find_thread_path_by_id_str",
    "list",
    "map_session_init_error",
    "parse_cursor",
    "read_head_for_summary",
    "read_session_meta_line",
    "rollout_date_parts",
    "truncation",
]
