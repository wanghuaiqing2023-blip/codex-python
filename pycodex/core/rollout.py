"""Core rollout coordinate re-exports.

Rust ``codex-core::rollout`` mostly re-exports the companion
``codex_rollout`` crate and wires a few core-local submodules back in.  Python
keeps the actual rollout implementation in ``pycodex.rollout``; this module
preserves the core module coordinate without duplicating that implementation.
"""

from __future__ import annotations

from enum import Enum

from pycodex.protocol import SessionSource
from pycodex.rollout import (
    ARCHIVED_SESSIONS_SUBDIR,
    SESSIONS_SUBDIR,
    Cursor,
    RolloutRecorder,
    RolloutRecorderParams,
    SessionMeta,
    ThreadItem,
    ThreadsPage,
    ThreadSortKey,
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
from pycodex.core.thread_rollout_truncation import (
    truncate_rollout_before_nth_user_message_from_start,
    truncate_rollout_to_last_n_fork_turns,
)

INTERACTIVE_SESSION_SOURCES = (
    SessionSource.cli(),
    SessionSource.vscode(),
    SessionSource.custom_source("atlas"),
    SessionSource.custom_source("chatgpt"),
)


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class EventPersistenceMode(str, Enum):
    LIMITED = "limited"
    EXTENDED = "extended"
    NONE = "none"


find_conversation_path_by_id_str = find_thread_path_by_id_str


__all__ = [
    "ARCHIVED_SESSIONS_SUBDIR",
    "Cursor",
    "EventPersistenceMode",
    "INTERACTIVE_SESSION_SOURCES",
    "SESSIONS_SUBDIR",
    "RolloutRecorder",
    "RolloutRecorderParams",
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
    "map_session_init_error",
    "parse_cursor",
    "read_head_for_summary",
    "read_session_meta_line",
    "rollout_date_parts",
    "truncate_rollout_before_nth_user_message_from_start",
    "truncate_rollout_to_last_n_fork_turns",
]
