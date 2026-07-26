"""Rust ``codex-thread-store::local::list_threads`` owner."""

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
    distinct_thread_metadata_title,
    set_thread_name_from_title,
    stored_thread_from_rollout_item,
)
from .read_thread import _read_state_thread_metadata

async def _apply_list_thread_names(store: LocalThreadStore, items: tuple[StoredThread, ...]) -> tuple[StoredThread, ...]:
    names: dict[str, str] = {}
    for thread in items:
        metadata = await _read_state_thread_metadata(store, thread.thread_id)
        if metadata is None:
            continue
        title = distinct_thread_metadata_title(metadata)
        if title is not None:
            names[str(thread.thread_id)] = title
    missing = [thread.thread_id for thread in items if str(thread.thread_id) not in names]
    if missing:
        try:
            legacy_names = find_thread_names_by_ids(store.config.codex_home or Path(), missing)
        except Exception:
            legacy_names = {}
        for key, value in legacy_names.items():
            names.setdefault(str(key), value)
    updated = []
    for thread in items:
        title = names.get(str(thread.thread_id))
        if title is not None:
            updated.append(set_thread_name_from_title(thread, title))
        else:
            updated.append(thread)
    return tuple(updated)

def _state_metadata_items_for_list(store: LocalThreadStore, params: ListThreadsParams) -> tuple[Any, ...]:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        return ()
    values = None
    if hasattr(state_db, "threads"):
        raw = getattr(state_db, "threads")
        if isinstance(raw, Mapping):
            values = raw.values()
    if values is None:
        lister = getattr(state_db, "list_threads", None)
        if callable(lister):
            try:
                values = lister()
            except Exception:
                values = ()
    if values is None:
        return ()
    items = tuple(item for item in values if (getattr(item, "archived_at", None) is not None) == params.archived)
    if params.search_term is None:
        return items
    needle = params.search_term
    return tuple(
        item
        for item in items
        if needle in (getattr(item, "title", "") or "")
        or needle in (getattr(item, "preview", "") or "")
        or needle in (getattr(item, "first_user_message", "") or "")
    )

def _list_local_rollout_threads(store: LocalThreadStore, params: ListThreadsParams) -> Any:
    codex_home = store.config.codex_home or Path()
    allowed_sources = tuple(_enum_or_value(source) for source in params.allowed_sources)
    sort_key = _rollout_sort_key(params.sort_key)
    if params.use_state_db_only:
        metadata_items = _state_metadata_items_for_list(store, params)
        page = list_threads_from_state_metadata(
            metadata_items,
            params.page_size,
            cursor=params.cursor,
            sort_key=sort_key,
            allowed_sources=allowed_sources,
            model_providers=params.model_providers,
            cwd_filters=params.cwd_filters,
            default_provider=store.config.default_model_provider_id,
            search_term=None,
            repair_runtime=store._state_db,
            codex_home=codex_home,
        )
    elif params.archived:
        page = get_threads_in_root(
            codex_home / ARCHIVED_SESSIONS_SUBDIR,
            params.page_size,
            cursor=params.cursor,
            sort_key=sort_key,
            allowed_sources=allowed_sources,
            model_providers=params.model_providers,
            cwd_filters=params.cwd_filters,
            default_provider=store.config.default_model_provider_id,
            layout=ThreadListLayout.FLAT,
            codex_home=codex_home,
            search_term=params.search_term,
        )
    else:
        page = get_threads(
            codex_home,
            params.page_size,
            cursor=params.cursor,
            sort_key=sort_key,
            allowed_sources=allowed_sources,
            model_providers=params.model_providers,
            cwd_filters=params.cwd_filters,
            default_provider=store.config.default_model_provider_id,
            search_term=params.search_term,
        )
    if params.sort_direction == SortDirection.ASC:
        page.items.reverse()
    return page

def _rollout_sort_key(sort_key: ThreadSortKey) -> str:
    if sort_key == ThreadSortKey.UPDATED_AT:
        return "updated_at"
    return "created_at"

async def list_threads(store: Any, params: ListThreadsParams) -> ThreadPage:
    if params.cursor is not None and parse_cursor(params.cursor) is None:
        raise ThreadStoreError.invalid_request(f"invalid cursor: {params.cursor}")
    try:
        page = _list_local_rollout_threads(store, params)
    except Exception as exc:
        raise ThreadStoreError.internal(f"failed to list threads: {exc}") from exc
    items = tuple(
        thread
        for item in page.items
        if (thread := stored_thread_from_rollout_item(store, item, archived=params.archived)) is not None
    )
    items = await _apply_list_thread_names(store, items)
    next_cursor = page.next_cursor.to_json() if getattr(page, "next_cursor", None) is not None else None
    return ThreadPage(items=items, next_cursor=next_cursor)
