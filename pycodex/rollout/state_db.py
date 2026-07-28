"""Rust-aligned owner for ``codex-rollout::state_db``."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from pycodex.protocol import SessionSource
from pycodex.protocol.models import ResponseItem
from pycodex.protocol.protocol import (
    USER_MESSAGE_BEGIN,
    CompactedItem,
    EventMsg,
    InitialHistory,
    ResumedHistory,
    RolloutItem,
    ThreadId,
    ThreadRolledBackEvent,
    TurnContextItem,
)
from pycodex.utils.string import sanitize_metric_tag_value

from pycodex.protocol.protocol import GitInfo, SessionMeta, SessionMetaLine
from pycodex.state.model.backfill_state import BackfillState
from pycodex.state.model.thread_metadata import (
    Anchor,
    BackfillStats,
    ExtractionOutcome,
    ThreadMetadata,
    ThreadMetadataBuilder,
)
from pycodex.state import (
    StateRuntime,
    checkpoint_backfill,
    get_backfill_state,
    mark_backfill_complete,
    state_db_path,
    try_claim_backfill,
)
from pycodex.state.model.backfill_state import BackfillStatus
from pycodex.rollout import ARCHIVED_SESSIONS_SUBDIR, SESSIONS_SUBDIR

StateDbHandle = StateRuntime


async def init(config: object) -> StateDbHandle | None:
    """Initialize state persistence and complete the rollout backfill gate."""

    try:
        return await try_init(config)
    except Exception:
        return None


async def try_init(config: object) -> StateDbHandle:
    """Initialize state persistence, surfacing startup failures to the caller."""

    view = RolloutConfig.from_view(config)
    runtime = await StateRuntime.init(view.sqlite_home, view.model_provider_id)
    try:
        await _backfill_sessions_async(runtime, view.codex_home, view.model_provider_id)
    except Exception:
        await runtime.close()
        raise
    return runtime


async def get_state_db(config: object) -> StateDbHandle | None:
    """Open an existing state DB only after its backfill has completed."""

    view = RolloutConfig.from_view(config)
    if not state_db_path(view.sqlite_home).exists():
        return None
    try:
        runtime = await StateRuntime.init(view.sqlite_home, view.model_provider_id)
        state = await get_backfill_state(runtime.state_db)
    except Exception:
        return None
    if state.status is BackfillStatus.COMPLETE:
        return runtime
    await runtime.close()
    return None


def sqlite_telemetry_recorder(metrics: Any, originator: str) -> Any:
    """Build the state DB telemetry recorder owned by rollout."""

    return sqlite_metrics_recorder(metrics, originator)


async def reconcile_rollout(
    context: StateDbHandle | None,
    rollout_path: Path | str,
    default_provider: str,
    builder: ThreadMetadataBuilder | None,
    items: Sequence[Any],
    archived_only: bool | None,
    new_thread_memory_mode: str | None,
) -> None:
    """Reconcile rollout items into SQLite, falling back to file metadata."""

    if context is None:
        return
    path = Path(rollout_path)
    if builder is not None or items:
        effective_builder = builder if builder is not None else builder_from_items(items, path)
        if effective_builder is None:
            return
        if effective_builder.model_provider is None:
            effective_builder = replace(
                effective_builder,
                model_provider=default_provider,
            )
        effective_builder = replace(
            effective_builder,
            rollout_path=path,
            cwd=normalize_cwd_for_state_db(effective_builder.cwd),
        )
        await context.threads.apply_rollout_items(
            effective_builder,
            list(items),
            new_thread_memory_mode=new_thread_memory_mode,
        )
        return

    try:
        outcome = extract_metadata_from_rollout(path, default_provider)
    except Exception:
        return
    metadata = outcome.metadata
    metadata.cwd = normalize_cwd_for_state_db(metadata.cwd)
    existing = await context.threads.get_thread(metadata.id)
    if existing is not None:
        metadata.prefer_existing_git_info(existing)
    if archived_only is True and metadata.archived_at is None:
        metadata.archived_at = metadata.updated_at
    elif archived_only is False:
        metadata.archived_at = None
    await context.threads.upsert_thread(metadata)
    await context.threads.set_thread_memory_mode(
        metadata.id,
        outcome.memory_mode or "enabled",
    )


async def _backfill_sessions_async(
    runtime: StateRuntime,
    codex_home: Path,
    default_provider: str,
) -> BackfillStats:
    state = await get_backfill_state(runtime.state_db)
    if state.status is BackfillStatus.COMPLETE:
        return BackfillStats()
    if not await try_claim_backfill(runtime.state_db, 60):
        return BackfillStats()

    home = Path(codex_home)
    entries: list[tuple[str, Path, bool]] = []
    for root, archived in (
        (home / SESSIONS_SUBDIR, False),
        (home / ARCHIVED_SESSIONS_SUBDIR, True),
    ):
        for path in collect_rollout_paths(root):
            entries.append((backfill_watermark_for_path(home, path), path, archived))
    entries.sort(key=lambda entry: entry[0])
    if state.last_watermark is not None:
        entries = [entry for entry in entries if entry[0] > state.last_watermark]

    scanned = upserted = failed = 0
    last_watermark = state.last_watermark
    for watermark, path, archived in entries:
        scanned += 1
        try:
            outcome = extract_metadata_from_rollout(path, default_provider)
            metadata = outcome.metadata
            metadata.cwd = normalize_cwd_for_state_db(metadata.cwd)
            existing = await runtime.threads.get_thread(metadata.id)
            if existing is not None:
                metadata.prefer_existing_git_info(existing)
            if archived and metadata.archived_at is None:
                metadata.archived_at = metadata.updated_at
            await runtime.threads.upsert_thread(metadata)
            await runtime.threads.set_thread_memory_mode(
                metadata.id,
                outcome.memory_mode or "enabled",
            )
            upserted += 1
        except Exception:
            failed += 1
        last_watermark = watermark
        await checkpoint_backfill(runtime.state_db, watermark)
    await mark_backfill_complete(runtime.state_db, last_watermark)
    return BackfillStats(scanned=scanned, upserted=upserted, failed=failed)

def normalize_cwd_for_state_db(cwd: Path) -> Path:
    """Normalize rollout cwd before state-runtime upsert."""

    try:
        return Path(cwd).resolve(strict=False)
    except OSError:
        return Path(cwd)

def cursor_to_anchor(cursor: Cursor | None) -> Anchor | None:
    if cursor is None:
        return None
    timestamp = cursor.timestamp.astimezone(timezone.utc)
    millis = int(timestamp.timestamp() * 1000)
    return Anchor(datetime.fromtimestamp(millis / 1000, timezone.utc))

def list_thread_ids_db(
    context: Any,
    codex_home: Path | str,
    page_size: int,
    cursor: Cursor | None,
    sort_key: ThreadSortKey | str,
    allowed_sources: Sequence[SessionSource],
    model_providers: Sequence[str] | None,
    archived_only: bool,
    stage: str,
) -> list[Any] | None:
    if context is None:
        return None
    anchor = cursor_to_anchor(cursor)
    allowed_source_values = [_state_db_session_source_value(source) for source in allowed_sources]
    sort_key_value = _state_db_sort_key_value(sort_key)
    try:
        _warn_on_codex_home_mismatch(context, codex_home)
        return context.list_thread_ids(
            page_size,
            anchor,
            sort_key_value,
            allowed_source_values,
            None if model_providers is None else list(model_providers),
            archived_only,
        )
    except Exception:
        _ = stage
        return None

def list_threads_db(
    context: Any,
    codex_home: Path | str,
    page_size: int,
    cursor: Cursor | None,
    sort_key: ThreadSortKey | str,
    sort_direction: SortDirection | str,
    allowed_sources: Sequence[SessionSource],
    model_providers: Sequence[str] | None,
    cwd_filters: Sequence[Path] | None,
    archived: bool,
    search_term: str | None,
) -> Any | None:
    if context is None:
        return None
    options = {
        "archived_only": archived,
        "allowed_sources": [_state_db_session_source_value(source) for source in allowed_sources],
        "model_providers": None if model_providers is None else list(model_providers),
        "cwd_filters": None if cwd_filters is None else [normalize_cwd_for_state_db(cwd) for cwd in cwd_filters],
        "anchor": cursor_to_anchor(cursor),
        "sort_key": _state_db_sort_key_value(sort_key),
        "sort_direction": _state_db_sort_direction_value(sort_direction),
        "search_term": search_term,
    }
    try:
        _warn_on_codex_home_mismatch(context, codex_home)
        page = context.list_threads(page_size, options)
    except Exception:
        return None
    items = list(_state_db_page_items(page))
    valid_items = []
    for item in items:
        rollout_path = _state_db_item_rollout_path(item)
        if rollout_path is not None and rollout_path.exists():
            valid_items.append(item)
            continue
        thread_id = _state_db_item_id(item)
        deleter = getattr(context, "delete_thread", None)
        if callable(deleter) and thread_id is not None:
            try:
                deleter(thread_id)
            except Exception:
                pass
    return _state_db_page_with_items(page, valid_items)

def find_rollout_path_by_id(
    context: Any,
    thread_id: Any,
    archived_only: bool | None,
    stage: str,
) -> Path | None:
    if context is None:
        return None
    finder = getattr(context, "find_rollout_path_by_id", None)
    if not callable(finder):
        return None
    try:
        value = finder(thread_id, archived_only)
    except Exception:
        _ = stage
        return None
    return Path(value) if value is not None else None

def mark_thread_memory_mode_polluted(context: Any, thread_id: Any, stage: str) -> None:
    if context is None:
        return
    memories = getattr(context, "memories", None)
    try:
        memories = memories() if callable(memories) else memories
    except Exception:
        _ = stage
        return
    marker = getattr(memories, "mark_thread_memory_mode_polluted", None)
    if not callable(marker):
        return
    try:
        marker(thread_id)
    except Exception:
        _ = stage

def touch_thread_updated_at(context: Any, thread_id: Any | None, updated_at: datetime, stage: str) -> bool:
    if context is None or thread_id is None:
        return False
    toucher = getattr(context, "touch_thread_updated_at", None)
    if not callable(toucher):
        return False
    try:
        return bool(toucher(thread_id, updated_at))
    except Exception:
        _ = stage
        return False

def read_repair_rollout_path(
    context: Any,
    thread_id: Any | None,
    archived_only: bool | None,
    rollout_path: Path | str,
    default_provider: str = "",
) -> None:
    if context is None:
        return
    path = Path(rollout_path)
    saw_existing_metadata = False
    if thread_id is not None:
        getter = getattr(context, "get_thread", None)
        if callable(getter):
            try:
                metadata = getter(thread_id)
            except Exception:
                metadata = None
            if metadata is not None:
                saw_existing_metadata = True
                repaired = _repair_state_metadata(metadata, path, archived_only)
                if repaired == metadata:
                    return
                upsert = getattr(context, "upsert_thread", None)
                if callable(upsert):
                    try:
                        upsert(repaired)
                        return
                    except Exception:
                        pass
    if saw_existing_metadata:
        return
    try:
        outcome = extract_metadata_from_rollout(path, default_provider)
    except Exception:
        return
    metadata = _repair_state_metadata(outcome.metadata, path, archived_only)
    upsert = getattr(context, "upsert_thread", None)
    if callable(upsert):
        try:
            upsert(metadata)
        except Exception:
            return

def apply_rollout_items(
    context: Any,
    rollout_path: Path | str,
    default_provider: str,
    builder: ThreadMetadataBuilder | None,
    items: Sequence[Any],
    stage: str,
    new_thread_memory_mode: str | None = None,
    updated_at_override: datetime | None = None,
) -> None:
    if context is None:
        return
    path = Path(rollout_path)
    effective_builder = builder if builder is not None else builder_from_items(items, path)
    if effective_builder is None:
        _ = stage
        return
    if effective_builder.model_provider is None:
        effective_builder = replace(effective_builder, model_provider=default_provider)
    effective_builder = replace(
        effective_builder,
        rollout_path=path,
        cwd=normalize_cwd_for_state_db(effective_builder.cwd),
    )
    applier = getattr(context, "apply_rollout_items", None)
    if not callable(applier):
        return
    try:
        applier(effective_builder, list(items), new_thread_memory_mode, updated_at_override)
    except Exception:
        _ = stage
        return

def init_state_runtime_with_backfill(runtime: Any, codex_home: Path, default_provider: str = "") -> Any:
    """Initialize a state runtime by completing rollout backfill before returning it."""

    backfill_sessions(runtime, codex_home, default_provider)
    return runtime

def _state_db_sort_key_value(sort_key: ThreadSortKey | str) -> str:
    return _coerce_sort_key(sort_key).value

def _state_db_sort_direction_value(sort_direction: SortDirection | str) -> str:
    if isinstance(sort_direction, SortDirection):
        return sort_direction.value
    normalized = str(sort_direction)
    try:
        return SortDirection(normalized).value
    except ValueError:
        if normalized in {"Asc", "asc"}:
            return SortDirection.ASC.value
        if normalized in {"Desc", "desc"}:
            return SortDirection.DESC.value
        raise

def _state_db_session_source_value(source: SessionSource) -> str:
    if source.type == "custom" and source.custom is not None:
        return json.dumps({"custom": source.custom}, separators=(",", ":"), ensure_ascii=False)
    if source.type == "internal":
        return json.dumps({"internal": str(source.internal_source)}, separators=(",", ":"), ensure_ascii=False)
    if source.type == "subagent":
        return json.dumps({"subagent": str(source.subagent_source)}, separators=(",", ":"), ensure_ascii=False)
    return str(source)

def _warn_on_codex_home_mismatch(context: Any, codex_home: Path | str) -> None:
    getter = getattr(context, "codex_home", None)
    actual = getter() if callable(getter) else getattr(context, "codex_home_value", None)
    if actual is None:
        return
    _ = Path(actual) == Path(codex_home)

def _state_db_page_items(page: Any) -> Sequence[Any]:
    if isinstance(page, Mapping):
        items = page.get("items", ())
    else:
        items = getattr(page, "items", ())
    if callable(items):
        items = items()
    return items if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)) else ()

def _state_db_page_with_items(page: Any, items: list[Any]) -> Any:
    if isinstance(page, Mapping):
        result = dict(page)
        result["items"] = items
        return result
    try:
        setattr(page, "items", items)
        return page
    except Exception:
        return {"items": items}

def _state_db_item_rollout_path(item: Any) -> Path | None:
    value = item.get("rollout_path") if isinstance(item, Mapping) else getattr(item, "rollout_path", None)
    return Path(value) if value is not None else None

def _state_db_item_id(item: Any) -> Any:
    return item.get("id") if isinstance(item, Mapping) else getattr(item, "id", None)

def _repair_state_metadata(metadata: Any, rollout_path: Path, archived_only: bool | None) -> Any:
    cwd = normalize_cwd_for_state_db(Path(_metadata_value(metadata, "cwd", ".")))
    updated_at = _metadata_value(metadata, "updated_at", None)
    archived_at = _metadata_value(metadata, "archived_at", None)
    if archived_only is True and archived_at is None:
        archived_at = updated_at
    elif archived_only is False:
        archived_at = None
    if isinstance(metadata, Mapping):
        repaired = dict(metadata)
        repaired["rollout_path"] = rollout_path
        repaired["cwd"] = cwd
        if archived_at is not None:
            repaired["archived_at"] = archived_at
        elif "archived_at" in repaired:
            repaired["archived_at"] = None
        return repaired
    updates = {"rollout_path": rollout_path, "cwd": cwd}
    if hasattr(metadata, "archived_at"):
        updates["archived_at"] = archived_at
    try:
        return replace(metadata, **updates)
    except TypeError:
        for key, value in updates.items():
            try:
                setattr(metadata, key, value)
            except Exception:
                pass
        return metadata

from pycodex.rollout.list import Cursor, SortDirection, ThreadSortKey, _coerce_sort_key, _metadata_value
from pycodex.rollout.config import RolloutConfig
from pycodex.rollout.metadata import (
    backfill_sessions,
    backfill_watermark_for_path,
    builder_from_items,
    collect_rollout_paths,
    extract_metadata_from_rollout,
)
from pycodex.rollout.sqlite_metrics import sqlite_metrics_recorder

__all__ = ['StateDbHandle', 'apply_rollout_items', 'cursor_to_anchor', 'find_rollout_path_by_id', 'get_state_db', 'init', 'init_state_runtime_with_backfill', 'list_thread_ids_db', 'list_threads_db', 'mark_thread_memory_mode_polluted', 'normalize_cwd_for_state_db', 'read_repair_rollout_path', 'reconcile_rollout', 'sqlite_telemetry_recorder', 'touch_thread_updated_at', 'try_init']
