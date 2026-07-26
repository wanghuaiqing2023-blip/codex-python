"""Rust ``codex-thread-store::local::unarchive_thread`` owner."""

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
    list_threads_from_state_metadata,
    parse_cursor,
    read_thread_item_from_rollout,
    read_session_meta_line,
    rollout_date_parts,
    search_rollout_paths,
)

from ..error import ThreadStoreError
from ..in_memory import InMemoryThreadStore
from ..thread_metadata_sync import parse_session_timestamp
from ..types import *
from ..types import (
    _clearable_to_optional_value,
    _enum_or_value,
    _metadata_enum_string,
)

from .helpers import (
    matching_rollout_file_name,
    _maybe_await,
    scoped_rollout_path,
    stored_thread_from_rollout_item,
    touch_modified_time,
)

async def unarchive_thread(store: Any, params: ArchiveThreadParams) -> StoredThread:
    thread_id = params.thread_id
    codex_home = store.config.codex_home or Path()
    try:
        archived_path = find_archived_thread_path_by_id_str(codex_home, str(thread_id), store._state_db)
    except Exception as exc:
        raise ThreadStoreError.invalid_request(f"failed to locate archived thread id {thread_id}: {exc}") from exc
    if archived_path is None:
        raise ThreadStoreError.invalid_request(f"no archived rollout found for thread id {thread_id}")
    canonical_archived_path = scoped_rollout_path(
        codex_home / ARCHIVED_SESSIONS_SUBDIR,
        Path(archived_path),
        "archived",
    )
    file_name = matching_rollout_file_name(canonical_archived_path, thread_id, Path(archived_path))
    date_parts = rollout_date_parts(file_name)
    if date_parts is None:
        raise ThreadStoreError.invalid_request(f"rollout path `{archived_path}` missing filename timestamp")
    year, month, day = date_parts
    dest_dir = codex_home / "sessions" / year / month / day
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        restored_path = dest_dir / file_name
        canonical_archived_path.replace(restored_path)
        touch_modified_time(restored_path)
    except OSError as exc:
        raise ThreadStoreError.internal(f"failed to unarchive thread: {exc}") from exc
    marker = getattr(store._state_db, "mark_unarchived", None)
    if callable(marker):
        await _maybe_await(marker(thread_id, restored_path))
    item = read_thread_item_from_rollout(restored_path)
    if item is None:
        raise ThreadStoreError.internal(f"failed to read unarchived thread {restored_path}")
    thread = stored_thread_from_rollout_item(store, item, archived=False)
    if thread is None:
        raise ThreadStoreError.internal(f"failed to read unarchived thread id from {restored_path}")
    return thread
