"""Rust ``codex-thread-store::local::live_writer`` owner."""

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


async def append_items(store: Any, params: AppendThreadItemsParams) -> None:
    recorder = store._live_recorder(params.thread_id)
    recorder.record_canonical_items(params.items)
    recorder.flush()
    await InMemoryThreadStore.append_items(store, params)

async def discard_thread(store: Any, thread_id: ThreadId) -> None:
    store._live_recorder(thread_id)
    store._live_recorders.pop(thread_id, None)
    await InMemoryThreadStore.discard_thread(store, thread_id)

async def shutdown_thread(store: Any, thread_id: ThreadId) -> None:
    recorder = store._live_recorder(thread_id)
    recorder.shutdown()
    store._live_recorders.pop(thread_id, None)
    await InMemoryThreadStore.shutdown_thread(store, thread_id)

async def rollout_path(store: Any, thread_id: ThreadId) -> Path:
    return store._live_recorder(thread_id).rollout_path

async def create_thread(store: Any, params: CreateThreadParams) -> None:
    from .create_thread import create_thread as create_recorder

    store._ensure_live_recorder_absent(params.thread_id)
    recorder = create_recorder(store, params)
    store._live_recorders[params.thread_id] = recorder
    await InMemoryThreadStore.create_thread(store, params)

async def flush_thread(store: Any, thread_id: ThreadId) -> None:
    store._live_recorder(thread_id).flush()
    await InMemoryThreadStore.flush_thread(store, thread_id)

async def persist_thread(store: Any, thread_id: ThreadId) -> None:
    store._live_recorder(thread_id).persist()
    await InMemoryThreadStore.persist_thread(store, thread_id)

async def resume_thread(store: Any, params: ResumeThreadParams) -> None:
    store._ensure_live_recorder_absent(params.thread_id)
    if params.metadata.cwd is None:
        raise ThreadStoreError.invalid_request("local thread store requires a cwd")
    rollout_path = params.rollout_path
    if rollout_path is None:
        rollout_path = store._rollout_path_for_thread(params.thread_id)
    if rollout_path is None:
        raise ThreadStoreError.internal(f"thread {params.thread_id} does not have a rollout path")
    store._live_recorders[params.thread_id] = RolloutRecorder.new(
        store._rollout_config(params.metadata),
        RolloutRecorderParams.resume(rollout_path),
    )
    await InMemoryThreadStore.resume_thread(store, params)
