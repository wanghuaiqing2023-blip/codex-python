"""Rollout persistence and discovery aligned with ``codex-rollout::lib``."""

from __future__ import annotations

from pycodex.protocol import SessionSource
from pycodex.protocol.protocol import SessionMeta

SESSIONS_SUBDIR = "sessions"
ARCHIVED_SESSIONS_SUBDIR = "archived_sessions"
INTERACTIVE_SESSION_SOURCES = (
    SessionSource.cli(),
    SessionSource.vscode(),
    SessionSource.custom_source("atlas"),
    SessionSource.custom_source("chatgpt"),
)

from pycodex.rollout.config import Config, RolloutConfig, RolloutConfigView
from pycodex.rollout.list import (
    Cursor,
    SortDirection,
    ThreadItem,
    ThreadListConfig,
    ThreadListLayout,
    ThreadSortKey,
    ThreadsPage,
    find_archived_thread_path_by_id_str,
    find_thread_path_by_id_str,
    get_threads,
    get_threads_in_root,
    parse_cursor,
    read_head_for_summary,
    read_session_meta_line,
    read_thread_item_from_rollout,
    rollout_date_parts,
)
from pycodex.rollout.metadata import builder_from_items
from pycodex.rollout.policy import (
    EventPersistenceMode,
    is_persisted_rollout_item,
    persisted_rollout_items,
    should_persist_response_item_for_memories,
)
from pycodex.rollout.recorder import (
    RolloutRecorder,
    RolloutRecorderParams,
    append_rollout_item_to_path,
)
from pycodex.rollout.search import (
    first_rollout_content_match_snippet,
    search_rollout_paths,
)
from pycodex.rollout.session_index import (
    append_thread_name,
    find_thread_meta_by_name_str,
    find_thread_name_by_id,
    find_thread_names_by_ids,
)
from pycodex.rollout.state_db import StateDbHandle, sqlite_telemetry_recorder

find_conversation_path_by_id_str = find_thread_path_by_id_str

__all__ = [
    "ARCHIVED_SESSIONS_SUBDIR",
    "Config",
    "Cursor",
    "EventPersistenceMode",
    "INTERACTIVE_SESSION_SOURCES",
    "RolloutConfig",
    "RolloutConfigView",
    "RolloutRecorder",
    "RolloutRecorderParams",
    "SESSIONS_SUBDIR",
    "SessionMeta",
    "SortDirection",
    "ThreadItem",
    "ThreadListConfig",
    "ThreadListLayout",
    "ThreadSortKey",
    "ThreadsPage",
    "StateDbHandle",
    "append_rollout_item_to_path",
    "append_thread_name",
    "builder_from_items",
    "find_archived_thread_path_by_id_str",
    "find_conversation_path_by_id_str",
    "find_thread_meta_by_name_str",
    "find_thread_name_by_id",
    "find_thread_names_by_ids",
    "find_thread_path_by_id_str",
    "first_rollout_content_match_snippet",
    "get_threads",
    "get_threads_in_root",
    "is_persisted_rollout_item",
    "parse_cursor",
    "persisted_rollout_items",
    "read_head_for_summary",
    "read_session_meta_line",
    "read_thread_item_from_rollout",
    "rollout_date_parts",
    "search_rollout_paths",
    "sqlite_telemetry_recorder",
    "should_persist_response_item_for_memories",
]
