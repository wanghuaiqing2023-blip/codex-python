"""Rust ``codex-thread-store::local::search_threads`` owner."""

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

from .helpers import stored_thread_from_rollout_item
from .list_threads import _apply_list_thread_names, _list_local_rollout_threads

async def _search_local_rollout_threads(store: LocalThreadStore, params: SearchThreadsParams) -> ThreadSearchPage:
    codex_home = store.config.codex_home or Path()
    matching_paths = search_rollout_paths(None, codex_home, params.archived, params.search_term)
    if not matching_paths:
        return ThreadSearchPage(items=())

    scan_page_size = max(256, min(2048, params.page_size * 8))
    page_cursor = params.cursor
    remaining_paths = {Path(path) for path in matching_paths}
    matching_items: list[tuple[Any, str]] = []

    while True:
        scan_params = ListThreadsParams(
            page_size=scan_page_size,
            cursor=page_cursor,
            sort_key=params.sort_key,
            sort_direction=params.sort_direction,
            allowed_sources=params.allowed_sources,
            model_providers=None,
            cwd_filters=None,
            archived=params.archived,
            search_term=None,
            use_state_db_only=store._state_db is not None,
        )
        page = _list_local_rollout_threads(store, scan_params)
        for item in page.items:
            item_path = Path(item.path)
            if item_path not in remaining_paths:
                continue
            remaining_paths.remove(item_path)
            snippet = first_rollout_content_match_snippet(item_path, params.search_term)
            if snippet is None:
                continue
            matching_items.append((item, snippet))
            if len(matching_items) > params.page_size:
                break

        next_page_cursor = getattr(page, "next_cursor", None)
        page_cursor = next_page_cursor.to_json() if next_page_cursor is not None else None
        if len(matching_items) > params.page_size or not remaining_paths or page_cursor is None:
            break

    more_matches_available = len(matching_items) > params.page_size
    matching_items = matching_items[: params.page_size]
    next_cursor = (
        _cursor_from_thread_search_item(matching_items[-1][0], params.sort_key)
        if more_matches_available and matching_items
        else None
    )

    results: list[StoredThreadSearchResult] = []
    for item, snippet in matching_items:
        thread = stored_thread_from_rollout_item(store, item, archived=params.archived)
        if thread is not None:
            results.append(StoredThreadSearchResult(thread=thread, snippet=snippet))
    results = list(await _apply_search_thread_names(store, tuple(results)))
    return ThreadSearchPage(items=tuple(results), next_cursor=next_cursor)

def _cursor_from_thread_search_item(item: Any, sort_key: ThreadSortKey) -> str | None:
    timestamp = getattr(item, "updated_at", None) if sort_key == ThreadSortKey.UPDATED_AT else getattr(item, "created_at", None)
    if timestamp is None and sort_key == ThreadSortKey.UPDATED_AT:
        timestamp = getattr(item, "created_at", None)
    cursor = parse_cursor(timestamp) if timestamp is not None else None
    return cursor.to_json() if cursor is not None else None

async def _apply_search_thread_names(
    store: LocalThreadStore,
    items: tuple[StoredThreadSearchResult, ...],
) -> tuple[StoredThreadSearchResult, ...]:
    named_threads = await _apply_list_thread_names(store, tuple(item.thread for item in items))
    by_id = {str(thread.thread_id): thread for thread in named_threads}
    return tuple(
        replace(item, thread=by_id.get(str(item.thread.thread_id), item.thread))
        for item in items
    )

async def search_threads(store: Any, params: SearchThreadsParams) -> ThreadSearchPage:
    if params.search_term == "":
        raise ThreadStoreError.invalid_request("thread/search requires search_term")
    if params.cursor is not None and parse_cursor(params.cursor) is None:
        raise ThreadStoreError.invalid_request(f"invalid cursor: {params.cursor}")
    try:
        return await _search_local_rollout_threads(store, params)
    except ThreadStoreError:
        raise
    except Exception as exc:
        raise ThreadStoreError.internal(f"failed to search rollout contents: {exc}") from exc
