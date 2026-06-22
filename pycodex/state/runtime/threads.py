"""Thread runtime store ported from ``codex-state/src/runtime/threads.rs``."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.protocol import ThreadId

from ..extract import apply_rollout_item
from ..model import (
    Anchor,
    DirectionalThreadSpawnEdgeStatus,
    SortDirection,
    SortKey,
    ThreadMetadata,
    ThreadMetadataBuilder,
    ThreadRow,
    ThreadsPage,
    anchor_from_item,
    datetime_to_epoch_millis,
    datetime_to_epoch_seconds,
    epoch_millis_to_datetime,
)
from ..model.thread_metadata import enum_to_string
from ..paths import file_modified_time_utc

JsonValue = Any
UNSET_GIT_FIELD = object()
_THREAD_SPAWN_SOURCE_RE = re.compile(r"(?:subagent_)?thread_spawn_([0-9a-fA-F-]{36})_d\d+")


@dataclass(frozen=True)
class ThreadFilterOptions:
    archived_only: bool = False
    allowed_sources: tuple[str, ...] = ()
    model_providers: tuple[str, ...] | None = None
    cwd_filters: tuple[Path, ...] | None = None
    anchor: Anchor | None = None
    sort_key: SortKey = SortKey.UPDATED_AT
    sort_direction: SortDirection = SortDirection.DESC
    search_term: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "archived_only", bool(self.archived_only))
        object.__setattr__(self, "allowed_sources", tuple(_required_str(source, "allowed_sources item") for source in self.allowed_sources))
        if self.model_providers is not None:
            object.__setattr__(
                self,
                "model_providers",
                tuple(_required_str(provider, "model_providers item") for provider in self.model_providers),
            )
        if self.cwd_filters is not None:
            object.__setattr__(self, "cwd_filters", tuple(_path(cwd, "cwd_filters item") for cwd in self.cwd_filters))
        if self.anchor is not None and not isinstance(self.anchor, Anchor):
            raise TypeError("anchor must be Anchor or None")
        if not isinstance(self.sort_key, SortKey):
            object.__setattr__(self, "sort_key", SortKey(str(self.sort_key)))
        if not isinstance(self.sort_direction, SortDirection):
            object.__setattr__(self, "sort_direction", SortDirection(str(self.sort_direction)))
        if self.search_term is not None:
            object.__setattr__(self, "search_term", _required_str(self.search_term, "search_term"))


class RuntimeThreadStore:
    def __init__(
        self,
        db: sqlite3.Connection | Path | str,
        *,
        default_provider: str = "test-provider",
        memories: JsonValue | None = None,
        thread_goals: JsonValue | None = None,
    ):
        self._db = db
        self.default_provider = _required_str(default_provider, "default_provider")
        self.memories = memories
        self.thread_goals = thread_goals
        self._thread_updated_at_millis = 0

    async def get_thread(self, thread_id: ThreadId) -> ThreadMetadata | None:
        return await _call(self._db, _get_thread_sync, _thread_id(thread_id))

    async def get_thread_memory_mode(self, thread_id: ThreadId) -> str | None:
        return await _call(self._db, _get_thread_memory_mode_sync, _thread_id(thread_id))

    async def set_thread_preview_if_empty(self, thread_id: ThreadId, preview: str) -> bool:
        return await _call(self._db, _set_thread_preview_if_empty_sync, _thread_id(thread_id), _required_str(preview, "preview"))

    async def upsert_thread_spawn_edge(
        self,
        parent_thread_id: ThreadId,
        child_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus,
    ) -> None:
        await _call(
            self._db,
            _upsert_thread_spawn_edge_sync,
            _thread_id(parent_thread_id),
            _thread_id(child_thread_id),
            _edge_status(status).as_ref(),
        )

    async def set_thread_spawn_edge_status(
        self,
        child_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus,
    ) -> bool:
        return await _call(self._db, _set_thread_spawn_edge_status_sync, _thread_id(child_thread_id), _edge_status(status).as_ref())

    async def list_thread_spawn_children_with_status(
        self,
        parent_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus | None = None,
    ) -> list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]]:
        return await _call(
            self._db,
            _list_thread_spawn_children_with_status_sync,
            _thread_id(parent_thread_id),
            _edge_status(status).as_ref() if status is not None else None,
        )

    async def list_thread_spawn_children(
        self,
        parent_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus | None = None,
    ) -> list[ThreadId]:
        rows = await self.list_thread_spawn_children_with_status(parent_thread_id, status)
        return [thread_id for thread_id, _ in rows]

    async def list_thread_spawn_descendants_with_status(
        self,
        root_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus | None = None,
    ) -> list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]]:
        return await _call(
            self._db,
            _list_thread_spawn_descendants_with_status_sync,
            _thread_id(root_thread_id),
            _edge_status(status).as_ref() if status is not None else None,
        )

    async def list_thread_spawn_descendants(
        self,
        root_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus | None = None,
    ) -> list[ThreadId]:
        rows = await self.list_thread_spawn_descendants_with_status(root_thread_id, status)
        return [thread_id for thread_id, _ in rows]

    async def find_thread_spawn_child_by_path(self, parent_thread_id: ThreadId, agent_path: str) -> ThreadId | None:
        return await _call(
            self._db,
            _find_thread_spawn_child_by_path_sync,
            _thread_id(parent_thread_id),
            _required_str(agent_path, "agent_path"),
        )

    async def find_thread_spawn_descendant_by_path(self, root_thread_id: ThreadId, agent_path: str) -> ThreadId | None:
        return await _call(
            self._db,
            _find_thread_spawn_descendant_by_path_sync,
            _thread_id(root_thread_id),
            _required_str(agent_path, "agent_path"),
        )

    async def insert_thread_spawn_edge_if_absent(self, parent_thread_id: ThreadId, child_thread_id: ThreadId) -> bool:
        return await _call(self._db, _insert_thread_spawn_edge_if_absent_sync, _thread_id(parent_thread_id), _thread_id(child_thread_id))

    async def insert_thread_spawn_edge_from_source_if_absent(self, child_thread_id: ThreadId, source: str) -> bool:
        return await _call(self._db, _insert_thread_spawn_edge_from_source_if_absent_sync, _thread_id(child_thread_id), source)

    async def find_rollout_path_by_id(self, thread_id: ThreadId, *, archived_only: bool | None = None) -> Path | None:
        return await _call(self._db, _find_rollout_path_by_id_sync, _thread_id(thread_id), archived_only)

    async def find_thread_by_exact_title(
        self,
        title: str,
        *,
        allowed_sources: Iterable[str] = (),
        model_providers: Iterable[str] | None = None,
        archived_only: bool = False,
        cwd: Path | str | None = None,
    ) -> ThreadMetadata | None:
        return await _call(
            self._db,
            _find_thread_by_exact_title_sync,
            _required_str(title, "title"),
            tuple(_required_str(source, "allowed_sources item") for source in allowed_sources),
            tuple(_required_str(provider, "model_providers item") for provider in model_providers) if model_providers is not None else None,
            archived_only,
            str(_path(cwd, "cwd")) if cwd is not None else None,
        )

    async def list_threads(self, page_size: int, filters: ThreadFilterOptions | None = None) -> ThreadsPage:
        return await _call(self._db, _list_threads_sync, _usize(page_size, "page_size"), filters or ThreadFilterOptions())

    async def list_thread_ids(
        self,
        limit: int,
        *,
        anchor: Anchor | None = None,
        sort_key: SortKey = SortKey.UPDATED_AT,
        allowed_sources: Iterable[str] = (),
        model_providers: Iterable[str] | None = None,
        archived_only: bool = False,
    ) -> list[ThreadId]:
        filters = ThreadFilterOptions(
            archived_only=archived_only,
            allowed_sources=tuple(allowed_sources),
            model_providers=tuple(model_providers) if model_providers is not None else None,
            anchor=anchor,
            sort_key=sort_key,
            sort_direction=SortDirection.DESC,
        )
        return await _call(self._db, _list_thread_ids_sync, _usize(limit, "limit"), filters)

    async def insert_thread_if_absent(self, metadata: ThreadMetadata) -> bool:
        updated_at = self.allocate_thread_updated_at(metadata.updated_at)
        return await _call(self._db, _insert_thread_if_absent_sync, _thread_metadata(metadata), updated_at)

    async def upsert_thread(self, metadata: ThreadMetadata) -> None:
        await self.upsert_thread_with_creation_memory_mode(metadata, None)

    async def set_thread_memory_mode(self, thread_id: ThreadId, memory_mode: str) -> bool:
        return await _call(self._db, _set_thread_memory_mode_sync, _thread_id(thread_id), _required_str(memory_mode, "memory_mode"))

    async def update_thread_title(self, thread_id: ThreadId, title: str) -> bool:
        return await _call(self._db, _update_thread_title_sync, _thread_id(thread_id), _required_str(title, "title"))

    async def touch_thread_updated_at(self, thread_id: ThreadId, updated_at) -> bool:
        allocated = self.allocate_thread_updated_at(updated_at)
        return await _call(self._db, _touch_thread_updated_at_sync, _thread_id(thread_id), allocated)

    def allocate_thread_updated_at(self, updated_at) -> Any:
        candidate = datetime_to_epoch_millis(updated_at)
        current = self._thread_updated_at_millis
        if candidate > current:
            self._thread_updated_at_millis = candidate
            return updated_at
        if candidate + 1000 <= current:
            return updated_at
        bumped = current + 1
        self._thread_updated_at_millis = bumped
        return epoch_millis_to_datetime(bumped)

    async def update_thread_git_info(
        self,
        thread_id: ThreadId,
        *,
        git_sha: str | None | object = UNSET_GIT_FIELD,
        git_branch: str | None | object = UNSET_GIT_FIELD,
        git_origin_url: str | None | object = UNSET_GIT_FIELD,
    ) -> bool:
        return await _call(
            self._db,
            _update_thread_git_info_sync,
            _thread_id(thread_id),
            _git_update(git_sha, "git_sha"),
            _git_update(git_branch, "git_branch"),
            _git_update(git_origin_url, "git_origin_url"),
        )

    async def upsert_thread_with_creation_memory_mode(
        self,
        metadata: ThreadMetadata,
        creation_memory_mode: str | None = None,
    ) -> None:
        updated_at = self.allocate_thread_updated_at(metadata.updated_at)
        await _call(
            self._db,
            _upsert_thread_with_creation_memory_mode_sync,
            _thread_metadata(metadata),
            updated_at,
            creation_memory_mode or "enabled",
        )

    async def apply_rollout_items(
        self,
        builder: ThreadMetadataBuilder,
        items: Sequence[JsonValue],
        *,
        new_thread_memory_mode: str | None = None,
        updated_at_override: Any | None = None,
    ) -> None:
        if not items:
            return
        existing = await self.get_thread(builder.id)
        metadata = existing if existing is not None else builder.build(self.default_provider)
        metadata.rollout_path = builder.rollout_path
        for item in items:
            apply_rollout_item(metadata, item, self.default_provider)
        if existing is not None:
            metadata.prefer_existing_git_info(existing)
        updated_at = updated_at_override
        if updated_at is None:
            updated_at = await file_modified_time_utc(builder.rollout_path)
        if updated_at is not None:
            metadata.updated_at = updated_at
        if existing is None:
            await self.upsert_thread_with_creation_memory_mode(metadata, new_thread_memory_mode)
        else:
            await self.upsert_thread(metadata)
        memory_mode = extract_memory_mode(items)
        if memory_mode is not None:
            await self.set_thread_memory_mode(builder.id, memory_mode)

    async def mark_archived(self, thread_id: ThreadId, rollout_path: Path | str, archived_at: Any) -> None:
        metadata = await self.get_thread(thread_id)
        if metadata is None:
            return
        metadata.archived_at = archived_at
        metadata.rollout_path = _path(rollout_path, "rollout_path")
        file_updated_at = await file_modified_time_utc(metadata.rollout_path)
        if file_updated_at is not None:
            metadata.updated_at = file_updated_at
        await self.upsert_thread(metadata)

    async def mark_unarchived(self, thread_id: ThreadId, rollout_path: Path | str) -> None:
        metadata = await self.get_thread(thread_id)
        if metadata is None:
            return
        metadata.archived_at = None
        metadata.rollout_path = _path(rollout_path, "rollout_path")
        file_updated_at = await file_modified_time_utc(metadata.rollout_path)
        if file_updated_at is not None:
            metadata.updated_at = file_updated_at
        await self.upsert_thread(metadata)

    async def delete_thread(self, thread_id: ThreadId) -> int:
        rows = await _call(self._db, _delete_thread_sync, _thread_id(thread_id))
        if rows > 0:
            await _maybe_call_delete(self.memories, "delete_thread_memory", thread_id)
            await _maybe_call_delete(self.thread_goals, "delete_thread_goal", thread_id)
        return rows


def _get_thread_sync(connection: sqlite3.Connection, thread_id: str) -> ThreadMetadata | None:
    rows = _rows(connection, _thread_select_sql("WHERE threads.id = ?"), [thread_id])
    return _thread_metadata_from_row(rows[0]) if rows else None


def _get_thread_memory_mode_sync(connection: sqlite3.Connection, thread_id: str) -> str | None:
    row = connection.execute("SELECT memory_mode FROM threads WHERE id = ?", (thread_id,)).fetchone()
    return None if row is None else row[0]


def _set_thread_preview_if_empty_sync(connection: sqlite3.Connection, thread_id: str, preview: str) -> bool:
    preview = preview.strip()
    if not preview:
        return False
    result = connection.execute("UPDATE threads SET preview = ? WHERE id = ? AND preview = ''", (preview, thread_id))
    connection.commit()
    return result.rowcount > 0


def _upsert_thread_spawn_edge_sync(connection: sqlite3.Connection, parent_thread_id: str, child_thread_id: str, status: str) -> None:
    connection.execute(
        """
        INSERT INTO thread_spawn_edges(parent_thread_id, child_thread_id, status)
        VALUES (?, ?, ?)
        ON CONFLICT(child_thread_id) DO UPDATE SET
            parent_thread_id = excluded.parent_thread_id,
            status = excluded.status
        """,
        (parent_thread_id, child_thread_id, status),
    )
    connection.commit()


def _set_thread_spawn_edge_status_sync(connection: sqlite3.Connection, child_thread_id: str, status: str) -> bool:
    result = connection.execute("UPDATE thread_spawn_edges SET status = ? WHERE child_thread_id = ?", (status, child_thread_id))
    connection.commit()
    return result.rowcount > 0


def _list_thread_spawn_children_with_status_sync(
    connection: sqlite3.Connection,
    parent_thread_id: str,
    status: str | None,
) -> list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]]:
    where = "parent_thread_id = ?"
    params: list[JsonValue] = [parent_thread_id]
    if status is not None:
        where += " AND status = ?"
        params.append(status)
    rows = connection.execute(
        f"SELECT child_thread_id, status FROM thread_spawn_edges WHERE {where} ORDER BY child_thread_id ASC",
        params,
    ).fetchall()
    return [(ThreadId.from_string(str(row[0])), DirectionalThreadSpawnEdgeStatus.parse(str(row[1]))) for row in rows]


def _list_thread_spawn_descendants_with_status_sync(
    connection: sqlite3.Connection,
    root_thread_id: str,
    status: str | None,
) -> list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]]:
    status_filter = "AND e.status = ?" if status is not None else ""
    params: list[JsonValue] = [root_thread_id]
    if status is not None:
        params.append(status)
    params.append(root_thread_id)
    if status is not None:
        params.append(status)
    rows = connection.execute(
        f"""
        WITH RECURSIVE descendants(child_thread_id, status, depth) AS (
            SELECT e.child_thread_id, e.status, 1
            FROM thread_spawn_edges e
            WHERE e.parent_thread_id = ? {status_filter}
            UNION ALL
            SELECT e.child_thread_id, e.status, d.depth + 1
            FROM thread_spawn_edges e
            JOIN descendants d ON e.parent_thread_id = d.child_thread_id
            WHERE d.child_thread_id != ? {status_filter}
        )
        SELECT child_thread_id, status FROM descendants ORDER BY depth ASC, child_thread_id ASC
        """,
        params,
    ).fetchall()
    return [(ThreadId.from_string(str(row[0])), DirectionalThreadSpawnEdgeStatus.parse(str(row[1]))) for row in rows]


def _find_thread_spawn_child_by_path_sync(connection: sqlite3.Connection, parent_thread_id: str, agent_path: str) -> ThreadId | None:
    rows = connection.execute(
        """
        SELECT t.id
        FROM thread_spawn_edges e
        JOIN threads t ON t.id = e.child_thread_id
        WHERE e.parent_thread_id = ? AND t.agent_path = ?
        ORDER BY t.id ASC
        LIMIT 2
        """,
        (parent_thread_id, agent_path),
    ).fetchall()
    return _one_thread_id_from_rows(rows, agent_path)


def _find_thread_spawn_descendant_by_path_sync(connection: sqlite3.Connection, root_thread_id: str, agent_path: str) -> ThreadId | None:
    rows = connection.execute(
        """
        WITH RECURSIVE descendants(child_thread_id, depth) AS (
            SELECT e.child_thread_id, 1
            FROM thread_spawn_edges e
            WHERE e.parent_thread_id = ?
            UNION ALL
            SELECT e.child_thread_id, d.depth + 1
            FROM thread_spawn_edges e
            JOIN descendants d ON e.parent_thread_id = d.child_thread_id
            WHERE d.child_thread_id != ?
        )
        SELECT t.id
        FROM descendants d
        JOIN threads t ON t.id = d.child_thread_id
        WHERE t.agent_path = ?
        ORDER BY d.depth ASC, t.id ASC
        LIMIT 2
        """,
        (root_thread_id, root_thread_id, agent_path),
    ).fetchall()
    return _one_thread_id_from_rows(rows, agent_path)


def _insert_thread_spawn_edge_if_absent_sync(connection: sqlite3.Connection, parent_thread_id: str, child_thread_id: str) -> bool:
    result = connection.execute(
        """
        INSERT INTO thread_spawn_edges(parent_thread_id, child_thread_id, status)
        VALUES (?, ?, ?)
        ON CONFLICT(child_thread_id) DO NOTHING
        """,
        (parent_thread_id, child_thread_id, DirectionalThreadSpawnEdgeStatus.OPEN.as_ref()),
    )
    connection.commit()
    return result.rowcount > 0


def _insert_thread_spawn_edge_from_source_if_absent_sync(connection: sqlite3.Connection, child_thread_id: str, source: str) -> bool:
    parent_thread_id = thread_spawn_parent_thread_id_from_source_str(source)
    if parent_thread_id is None:
        return False
    return _insert_thread_spawn_edge_if_absent_sync(connection, str(parent_thread_id), child_thread_id)


def _find_rollout_path_by_id_sync(connection: sqlite3.Connection, thread_id: str, archived_only: bool | None) -> Path | None:
    sql = "SELECT rollout_path FROM threads WHERE id = ?"
    params: list[JsonValue] = [thread_id]
    if archived_only is True:
        sql += " AND archived = 1"
    elif archived_only is False:
        sql += " AND archived = 0"
    row = connection.execute(sql, params).fetchone()
    return None if row is None else Path(str(row[0]))


def _find_thread_by_exact_title_sync(
    connection: sqlite3.Connection,
    title: str,
    allowed_sources: tuple[str, ...],
    model_providers: tuple[str, ...] | None,
    archived_only: bool,
    cwd: str | None,
) -> ThreadMetadata | None:
    clauses = ["threads.title = ?", "threads.archived = ?"]
    params: list[JsonValue] = [title, 1 if archived_only else 0]
    _push_allowed_sources(clauses, params, allowed_sources)
    _push_model_providers(clauses, params, model_providers)
    if cwd is not None:
        clauses.append("threads.cwd = ?")
        params.append(cwd)
    rows = _rows(connection, _thread_select_sql("WHERE " + " AND ".join(clauses) + " ORDER BY threads.updated_at_ms DESC, threads.id DESC LIMIT 1"), params)
    return _thread_metadata_from_row(rows[0]) if rows else None


def _list_threads_sync(connection: sqlite3.Connection, page_size: int, filters: ThreadFilterOptions) -> ThreadsPage:
    clauses, params = _thread_filters(filters)
    sql = _thread_select_sql("WHERE " + " AND ".join(clauses) + _thread_order_and_limit(filters.sort_key, filters.sort_direction, page_size + 1))
    rows = _rows(connection, sql, params)
    scanned = len(rows)
    items = [_thread_metadata_from_row(row) for row in rows[:page_size]]
    next_anchor = anchor_from_item(items[-1], filters.sort_key) if scanned > page_size and items else None
    return ThreadsPage(items=tuple(items), next_anchor=next_anchor, num_scanned_rows=scanned)


def _list_thread_ids_sync(connection: sqlite3.Connection, limit: int, filters: ThreadFilterOptions) -> list[ThreadId]:
    clauses, params = _thread_filters(filters)
    sql = "SELECT threads.id FROM threads WHERE " + " AND ".join(clauses) + _thread_order_and_limit(filters.sort_key, filters.sort_direction, limit)
    return [ThreadId.from_string(str(row[0])) for row in connection.execute(sql, params).fetchall()]


def _insert_thread_if_absent_sync(connection: sqlite3.Connection, metadata: ThreadMetadata, updated_at) -> bool:
    values = _thread_insert_values(metadata, updated_at, "enabled")
    result = connection.execute(_thread_insert_sql("ON CONFLICT(id) DO NOTHING"), values)
    _insert_thread_spawn_edge_from_source_if_absent_sync(connection, str(metadata.id), metadata.source)
    connection.commit()
    return result.rowcount > 0


def _set_thread_memory_mode_sync(connection: sqlite3.Connection, thread_id: str, memory_mode: str) -> bool:
    result = connection.execute("UPDATE threads SET memory_mode = ? WHERE id = ?", (memory_mode, thread_id))
    connection.commit()
    return result.rowcount > 0


def _update_thread_title_sync(connection: sqlite3.Connection, thread_id: str, title: str) -> bool:
    result = connection.execute("UPDATE threads SET title = ? WHERE id = ?", (title, thread_id))
    connection.commit()
    return result.rowcount > 0


def _touch_thread_updated_at_sync(connection: sqlite3.Connection, thread_id: str, updated_at) -> bool:
    result = connection.execute(
        "UPDATE threads SET updated_at = ?, updated_at_ms = ? WHERE id = ?",
        (datetime_to_epoch_seconds(updated_at), datetime_to_epoch_millis(updated_at), thread_id),
    )
    connection.commit()
    return result.rowcount > 0


def _update_thread_git_info_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    git_sha: tuple[bool, str | None],
    git_branch: tuple[bool, str | None],
    git_origin_url: tuple[bool, str | None],
) -> bool:
    result = connection.execute(
        """
        UPDATE threads
        SET
            git_sha = CASE WHEN ? THEN ? ELSE git_sha END,
            git_branch = CASE WHEN ? THEN ? ELSE git_branch END,
            git_origin_url = CASE WHEN ? THEN ? ELSE git_origin_url END
        WHERE id = ?
        """,
        (
            git_sha[0],
            git_sha[1],
            git_branch[0],
            git_branch[1],
            git_origin_url[0],
            git_origin_url[1],
            thread_id,
        ),
    )
    connection.commit()
    return result.rowcount > 0


def _upsert_thread_with_creation_memory_mode_sync(
    connection: sqlite3.Connection,
    metadata: ThreadMetadata,
    updated_at,
    creation_memory_mode: str,
) -> None:
    update = """
    ON CONFLICT(id) DO UPDATE SET
        rollout_path = excluded.rollout_path,
        created_at = excluded.created_at,
        updated_at = excluded.updated_at,
        created_at_ms = excluded.created_at_ms,
        updated_at_ms = excluded.updated_at_ms,
        source = excluded.source,
        thread_source = excluded.thread_source,
        agent_nickname = excluded.agent_nickname,
        agent_role = excluded.agent_role,
        agent_path = excluded.agent_path,
        model_provider = excluded.model_provider,
        model = excluded.model,
        reasoning_effort = excluded.reasoning_effort,
        cwd = excluded.cwd,
        cli_version = excluded.cli_version,
        title = excluded.title,
        preview = COALESCE(NULLIF(excluded.preview, ''), threads.preview),
        sandbox_policy = excluded.sandbox_policy,
        approval_mode = excluded.approval_mode,
        tokens_used = excluded.tokens_used,
        first_user_message = excluded.first_user_message,
        archived = excluded.archived,
        archived_at = excluded.archived_at,
        git_sha = COALESCE(threads.git_sha, excluded.git_sha),
        git_branch = COALESCE(threads.git_branch, excluded.git_branch),
        git_origin_url = COALESCE(threads.git_origin_url, excluded.git_origin_url)
    """
    connection.execute(_thread_insert_sql(update), _thread_insert_values(metadata, updated_at, creation_memory_mode))
    _insert_thread_spawn_edge_from_source_if_absent_sync(connection, str(metadata.id), metadata.source)
    connection.commit()


def _delete_thread_sync(connection: sqlite3.Connection, thread_id: str) -> int:
    result = connection.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
    connection.commit()
    return result.rowcount


def _thread_select_sql(suffix: str) -> str:
    return (
        """
        SELECT
            threads.id,
            threads.rollout_path,
            COALESCE(threads.created_at_ms, threads.created_at) AS created_at,
            COALESCE(threads.updated_at_ms, threads.updated_at) AS updated_at,
            threads.source,
            threads.thread_source,
            threads.agent_nickname,
            threads.agent_role,
            threads.agent_path,
            threads.model_provider,
            threads.model,
            threads.reasoning_effort,
            threads.cwd,
            threads.cli_version,
            threads.title,
            threads.preview,
            threads.sandbox_policy,
            threads.approval_mode,
            threads.tokens_used,
            threads.first_user_message,
            threads.archived_at,
            threads.git_sha,
            threads.git_branch,
            threads.git_origin_url
        FROM threads
        """
        + suffix
    )


def _thread_insert_sql(conflict_clause: str) -> str:
    return (
        """
        INSERT INTO threads (
            id, rollout_path, created_at, updated_at, created_at_ms, updated_at_ms,
            source, thread_source, agent_nickname, agent_role, agent_path,
            model_provider, model, reasoning_effort, cwd, cli_version,
            title, preview, sandbox_policy, approval_mode, tokens_used,
            first_user_message, archived, archived_at, git_sha, git_branch,
            git_origin_url, memory_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        + conflict_clause
    )


def _thread_insert_values(metadata: ThreadMetadata, updated_at, memory_mode: str) -> tuple[JsonValue, ...]:
    return (
        str(metadata.id),
        str(metadata.rollout_path),
        datetime_to_epoch_seconds(metadata.created_at),
        datetime_to_epoch_seconds(updated_at),
        datetime_to_epoch_millis(metadata.created_at),
        datetime_to_epoch_millis(updated_at),
        metadata.source,
        enum_to_string(metadata.thread_source) if metadata.thread_source is not None else None,
        metadata.agent_nickname,
        metadata.agent_role,
        metadata.agent_path,
        metadata.model_provider,
        metadata.model,
        enum_to_string(metadata.reasoning_effort) if metadata.reasoning_effort is not None else None,
        str(metadata.cwd),
        metadata.cli_version,
        metadata.title,
        metadata_preview(metadata),
        metadata.sandbox_policy,
        metadata.approval_mode,
        metadata.tokens_used,
        metadata.first_user_message or "",
        1 if metadata.archived_at is not None else 0,
        datetime_to_epoch_seconds(metadata.archived_at) if metadata.archived_at is not None else None,
        metadata.git_sha,
        metadata.git_branch,
        metadata.git_origin_url,
        memory_mode,
    )


def metadata_preview(metadata: ThreadMetadata) -> str:
    return metadata.preview or metadata.first_user_message or ""


def extract_memory_mode(items: Sequence[JsonValue]) -> str | None:
    for item in reversed(items):
        item_type, payload = _rollout_parts(item)
        if item_type != "session_meta":
            continue
        meta = _field(payload, "meta", default=payload)
        mode = _field(meta, "memory_mode", default=None)
        if mode is not None:
            return _required_str(mode, "memory_mode")
    return None


def thread_spawn_parent_thread_id_from_source_str(source: str) -> ThreadId | None:
    source = _required_str(source, "source")
    if match := _THREAD_SPAWN_SOURCE_RE.search(source):
        try:
            return ThreadId.from_string(match.group(1))
        except ValueError:
            return None
    try:
        parsed = json.loads(source)
    except json.JSONDecodeError:
        return None
    parent = _find_parent_thread_id(parsed)
    if isinstance(parent, str):
        try:
            return ThreadId.from_string(parent)
        except ValueError:
            return None
    return None


def _find_parent_thread_id(value: JsonValue) -> JsonValue | None:
    if isinstance(value, Mapping):
        if "parent_thread_id" in value:
            return value["parent_thread_id"]
        for child in value.values():
            found = _find_parent_thread_id(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_parent_thread_id(child)
            if found is not None:
                return found
    return None


def _thread_filters(filters: ThreadFilterOptions) -> tuple[list[str], list[JsonValue]]:
    clauses = ["threads.archived = ?", "threads.preview <> ''"]
    params: list[JsonValue] = [1 if filters.archived_only else 0]
    _push_allowed_sources(clauses, params, filters.allowed_sources)
    _push_model_providers(clauses, params, filters.model_providers)
    if filters.cwd_filters is not None:
        if not filters.cwd_filters:
            clauses.append("1 = 0")
        else:
            placeholders = ", ".join("?" for _ in filters.cwd_filters)
            clauses.append(f"threads.cwd IN ({placeholders})")
            params.extend(str(cwd) for cwd in filters.cwd_filters)
    if filters.anchor is not None:
        column = "threads.created_at_ms" if filters.sort_key is SortKey.CREATED_AT else "threads.updated_at_ms"
        op = ">" if filters.sort_direction is SortDirection.ASC else "<"
        clauses.append(f"{column} {op} ?")
        params.append(datetime_to_epoch_millis(filters.anchor.ts))
    if filters.search_term:
        clauses.append("(INSTR(threads.title, ?) > 0 OR INSTR(threads.preview, ?) > 0)")
        params.extend([filters.search_term, filters.search_term])
    return clauses, params


def _push_allowed_sources(clauses: list[str], params: list[JsonValue], allowed_sources: Sequence[str]) -> None:
    if allowed_sources:
        placeholders = ", ".join("?" for _ in allowed_sources)
        clauses.append(f"threads.source IN ({placeholders})")
        params.extend(allowed_sources)


def _push_model_providers(clauses: list[str], params: list[JsonValue], model_providers: Sequence[str] | None) -> None:
    if model_providers:
        placeholders = ", ".join("?" for _ in model_providers)
        clauses.append(f"threads.model_provider IN ({placeholders})")
        params.extend(model_providers)


def _thread_order_and_limit(sort_key: SortKey, direction: SortDirection, limit: int) -> str:
    column = "threads.created_at_ms" if sort_key is SortKey.CREATED_AT else "threads.updated_at_ms"
    direction_sql = "ASC" if direction is SortDirection.ASC else "DESC"
    id_direction_sql = "ASC" if direction is SortDirection.ASC else "DESC"
    return f" ORDER BY {column} {direction_sql}, threads.id {id_direction_sql} LIMIT {limit}"


def _one_thread_id_from_rows(rows: Sequence[Sequence[JsonValue]], agent_path: str) -> ThreadId | None:
    ids = [ThreadId.from_string(str(row[0])) for row in rows]
    if len(ids) == 0:
        return None
    if len(ids) == 1:
        return ids[0]
    raise ValueError(f"multiple agents found for canonical path `{agent_path}`")


def _thread_metadata_from_row(row: sqlite3.Row) -> ThreadMetadata:
    return ThreadRow.from_mapping(dict(row)).to_thread_metadata()


def _rollout_parts(item: JsonValue) -> tuple[str, JsonValue]:
    if isinstance(item, Mapping):
        return _required_str(item.get("type"), "type"), item.get("payload")
    item_type = getattr(item, "type", None)
    payload = getattr(item, "payload", None)
    if item_type is None:
        raise TypeError("rollout item must be mapping-like or have type/payload attributes")
    return _required_str(item_type, "type"), payload


def _field(value: JsonValue, name: str, *, default: JsonValue = None) -> JsonValue:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


async def _maybe_call_delete(store: JsonValue, method_name: str, thread_id: ThreadId) -> None:
    if store is None:
        return
    method = getattr(store, method_name, None)
    if not callable(method):
        return
    result = method(thread_id)
    if asyncio.iscoroutine(result):
        await result


def _rows(connection: sqlite3.Connection, sql: str, params: Sequence[JsonValue]) -> list[sqlite3.Row]:
    old_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.row_factory = old_factory


async def _call(db: sqlite3.Connection | Path | str, fn, *args, **kwargs):
    if isinstance(db, sqlite3.Connection):
        return fn(db, *args, **kwargs)
    return await asyncio.to_thread(_with_connection, _path(db, "db"), fn, *args, **kwargs)


def _with_connection(path: Path, fn, *args, **kwargs):
    connection = sqlite3.connect(path)
    try:
        return fn(connection, *args, **kwargs)
    finally:
        connection.close()


def _thread_id(value: ThreadId) -> str:
    if not isinstance(value, ThreadId):
        raise TypeError("thread_id must be ThreadId")
    return str(value)


def _thread_metadata(value: JsonValue) -> ThreadMetadata:
    if not isinstance(value, ThreadMetadata):
        raise TypeError("metadata must be ThreadMetadata")
    return value


def _edge_status(value: DirectionalThreadSpawnEdgeStatus | str | None) -> DirectionalThreadSpawnEdgeStatus:
    if value is None:
        raise TypeError("status must not be None")
    if isinstance(value, DirectionalThreadSpawnEdgeStatus):
        return value
    return DirectionalThreadSpawnEdgeStatus.parse(str(value))


def _git_update(value: str | None | object, name: str) -> tuple[bool, str | None]:
    if value is UNSET_GIT_FIELD:
        return (False, None)
    if value is not None:
        _required_str(value, name)
    return (True, value)


def _usize(value: JsonValue, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _path(value: JsonValue, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a string or Path")
    return Path(value)


__all__ = [
    "RuntimeThreadStore",
    "ThreadFilterOptions",
    "UNSET_GIT_FIELD",
    "extract_memory_mode",
    "metadata_preview",
    "thread_spawn_parent_thread_id_from_source_str",
]
