"""Rust ``codex-thread-store::local::create_thread`` owner."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from pycodex.protocol import (
    AskForApproval,
    GitInfo,
    RolloutItem,
    SandboxPolicy,
    SessionMetaLine,
    SessionSource,
    ThreadId,
    ThreadMemoryMode,
    ThreadSource,
)
from pycodex.rollout import (
    ARCHIVED_SESSIONS_SUBDIR,
    RolloutRecorder,
    RolloutRecorderParams,
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
    rollout_date_parts,
    search_rollout_paths,
)
from pycodex.rollout.list import list_threads_from_state_metadata

from ..error import ThreadStoreError
from ..in_memory import InMemoryThreadStore
from ..thread_metadata_sync import parse_session_timestamp
from ..types import *
from ..types import (
    _clearable_to_optional_value,
    _enum_or_value,
    _metadata_enum_string,
)

def create_thread(store: Any, params: CreateThreadParams) -> RolloutRecorder:
    if params.metadata.cwd is None:
        raise ThreadStoreError.invalid_request("local thread store requires a cwd")
    return RolloutRecorder.new(
        store._rollout_config(params.metadata),
        RolloutRecorderParams.new(
            params.thread_id,
            params.forked_from_id,
            params.source,
            params.thread_source,
            params.base_instructions,
            params.dynamic_tools,
        ),
    )
