"""Rust ``codex-thread-store::local::archive_thread`` owner."""

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

from .helpers import matching_rollout_file_name, _maybe_await, scoped_rollout_path

async def archive_thread(store: Any, params: ArchiveThreadParams) -> None:
    thread_id = params.thread_id
    codex_home = store.config.codex_home or Path()
    try:
        rollout_path = find_thread_path_by_id_str(codex_home, str(thread_id), store._state_db)
    except Exception as exc:
        raise ThreadStoreError.invalid_request(f"failed to locate thread id {thread_id}: {exc}") from exc
    if rollout_path is None:
        raise ThreadStoreError.invalid_request(f"no rollout found for thread id {thread_id}")
    canonical_rollout_path = scoped_rollout_path(codex_home / "sessions", Path(rollout_path), "sessions")
    file_name = matching_rollout_file_name(canonical_rollout_path, thread_id, Path(rollout_path))
    archive_folder = codex_home / ARCHIVED_SESSIONS_SUBDIR
    try:
        archive_folder.mkdir(parents=True, exist_ok=True)
        archived_path = archive_folder / file_name
        canonical_rollout_path.replace(archived_path)
    except OSError as exc:
        raise ThreadStoreError.internal(f"failed to archive thread: {exc}") from exc
    marker = getattr(store._state_db, "mark_archived", None)
    if callable(marker):
        await _maybe_await(marker(thread_id, archived_path, datetime.now(timezone.utc)))
