"""Rust-aligned owner for ``codex-rollout::list``."""

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
from pycodex.rollout import ARCHIVED_SESSIONS_SUBDIR, SESSIONS_SUBDIR

HEAD_RECORD_LIMIT = 10

USER_EVENT_SCAN_LIMIT = 200

MAX_SCAN_FILES = 10000

class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"

@dataclass(frozen=True)
class Cursor:
    """Pagination cursor represented by an RFC3339 timestamp."""

    timestamp: datetime

    def to_json(self) -> str:
        return _format_rfc3339(self.timestamp)

class ThreadSortKey(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class ThreadListLayout(str, Enum):
    NESTED_BY_DATE = "nested_by_date"
    FLAT = "flat"

@dataclass(frozen=True)
class ThreadListConfig:
    """Filters and layout shared by Rust rollout listing entry points."""

    allowed_sources: Sequence[SessionSource] = ()
    model_providers: Sequence[str] | None = None
    cwd_filters: Sequence[Path] | None = None
    default_provider: str = ""
    layout: ThreadListLayout = ThreadListLayout.NESTED_BY_DATE

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_sources", tuple(self.allowed_sources))
        if self.model_providers is not None:
            object.__setattr__(self, "model_providers", tuple(self.model_providers))
        if self.cwd_filters is not None:
            object.__setattr__(
                self,
                "cwd_filters",
                tuple(Path(path) for path in self.cwd_filters),
            )
        if not isinstance(self.layout, ThreadListLayout):
            object.__setattr__(self, "layout", ThreadListLayout(str(self.layout)))

@dataclass(frozen=True)
class ThreadItem:
    """Summary information for a thread rollout file."""

    path: Path
    thread_id: ThreadId | None = None
    first_user_message: str | None = None
    preview: str | None = None
    cwd: Path | None = None
    git_branch: str | None = None
    git_sha: str | None = None
    git_origin_url: str | None = None
    source: SessionSource | str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    model_provider: str | None = None
    cli_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

@dataclass(frozen=True)
class ThreadsPage:
    """Returned page of thread summaries."""

    items: list[ThreadItem]
    next_cursor: Cursor | None = None
    num_scanned_files: int = 0
    reached_scan_cap: bool = False

ConversationItem = ThreadItem
ConversationsPage = ThreadsPage

def rollout_date_parts(file_name: str | Path) -> tuple[str, str, str] | None:
    """Extract ``YYYY/MM/DD`` components from a rollout filename."""

    name = Path(file_name).name
    if not name.startswith("rollout-") or len(name) < len("rollout-") + 10:
        return None
    date = name[len("rollout-") : len("rollout-") + 10]
    return date[:4], date[5:7], date[8:10]

def parse_cursor(token: str) -> Cursor | None:
    """Parse the upstream cursor token format."""

    if "|" in token:
        return None
    parsed = _parse_rfc3339(token)
    if parsed is None:
        try:
            parsed = datetime.strptime(token, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return Cursor(parsed)

def parse_timestamp_uuid_from_filename(name: str) -> tuple[datetime, str] | None:
    """Parse ``rollout-YYYY-MM-DDThh-mm-ss-<uuid>.jsonl`` filenames."""

    core = name.removeprefix("rollout-")
    if core == name:
        return None
    core = core.removesuffix(".jsonl")
    if core == name.removeprefix("rollout-"):
        return None

    for index in range(len(core) - 1, -1, -1):
        if core[index] != "-":
            continue
        try:
            rollout_id = uuid.UUID(core[index + 1 :])
        except ValueError:
            continue
        try:
            timestamp = datetime.strptime(core[:index], "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        return timestamp, str(rollout_id)
    return None

def get_threads(
    codex_home: Path,
    page_size: int,
    cursor: Cursor | str | None = None,
    sort_key: ThreadSortKey | str = ThreadSortKey.CREATED_AT,
    allowed_sources: Sequence[str] = (),
    model_providers: Sequence[str] | None = None,
    cwd_filters: Sequence[Path] | None = None,
    default_provider: str = "",
    search_term: str | None = None,
) -> ThreadsPage:
    """List persisted threads below ``<codex_home>/sessions``."""

    codex_home = Path(codex_home)
    return get_threads_in_root(
        codex_home / SESSIONS_SUBDIR,
        page_size,
        cursor=cursor,
        sort_key=sort_key,
        allowed_sources=allowed_sources,
        model_providers=model_providers,
        cwd_filters=cwd_filters,
        default_provider=default_provider,
        layout=ThreadListLayout.NESTED_BY_DATE,
        codex_home=codex_home,
        search_term=search_term,
    )

def get_threads_in_root(
    root: Path,
    page_size: int,
    cursor: Cursor | str | None = None,
    sort_key: ThreadSortKey | str = ThreadSortKey.CREATED_AT,
    allowed_sources: Sequence[str] = (),
    model_providers: Sequence[str] | None = None,
    cwd_filters: Sequence[Path] | None = None,
    default_provider: str = "",
    layout: ThreadListLayout | str = ThreadListLayout.NESTED_BY_DATE,
    codex_home: Path | None = None,
    search_term: str | None = None,
) -> ThreadsPage:
    """List rollout files in a sessions root with upstream-style pagination."""

    if page_size <= 0:
        raise ValueError("page_size must be positive")

    root = Path(root)
    if not root.is_dir():
        return ThreadsPage(items=[])

    sort_key = _coerce_sort_key(sort_key)
    layout = _coerce_layout(layout)
    cursor_obj = parse_cursor(cursor) if isinstance(cursor, str) else cursor

    candidates, scanned, reached_scan_cap = _collect_rollout_candidates(root, layout, sort_key)
    items: list[ThreadItem] = []
    more_matches_available = False
    allowed_sources_set = {_session_source_key(source) for source in allowed_sources}
    search_match_ids: set[str] | None = None
    if search_term is not None:
        if codex_home is None:
            raise ValueError("codex_home is required when search_term is provided")
        search_match_ids = _thread_ids_matching_search_term(Path(codex_home), search_term)

    for candidate in candidates:
        sort_timestamp = candidate.sort_timestamp(sort_key)
        if cursor_obj is not None and sort_timestamp >= cursor_obj.timestamp:
            continue
        updated_at = _format_rfc3339(candidate.updated_at) if candidate.updated_at is not None else None
        item = _build_thread_item(
            candidate.path,
            allowed_sources=allowed_sources_set,
            model_providers=model_providers,
            cwd_filters=cwd_filters,
            default_provider=default_provider,
            updated_at=updated_at,
        )
        if item is None:
            continue
        if search_match_ids is not None and (
            item.thread_id is None or str(item.thread_id) not in search_match_ids
        ):
            continue
        if len(items) == page_size:
            more_matches_available = True
            break
        items.append(item)

    next_cursor = None
    if items and (more_matches_available or reached_scan_cap):
        next_cursor = _build_next_cursor(items, sort_key)

    return ThreadsPage(
        items=items,
        next_cursor=next_cursor,
        num_scanned_files=scanned,
        reached_scan_cap=reached_scan_cap,
    )

def list_threads_from_state_metadata(
    metadata_items: Iterable[ThreadMetadata],
    page_size: int,
    cursor: Cursor | str | None = None,
    sort_key: ThreadSortKey | str = ThreadSortKey.CREATED_AT,
    allowed_sources: Sequence[str] = (),
    model_providers: Sequence[str] | None = None,
    cwd_filters: Sequence[Path] | None = None,
    default_provider: str = "",
    search_term: str | None = None,
    repair_runtime: Any = None,
    drop_missing_rollout_paths: bool = False,
    codex_home: Path | None = None,
    repair_stale_rollout_paths: bool = False,
) -> ThreadsPage:
    """List threads from state metadata without scanning JSONL rollout files."""

    if page_size <= 0:
        raise ValueError("page_size must be positive")

    sort_key = _coerce_sort_key(sort_key)
    cursor_obj = parse_cursor(cursor) if isinstance(cursor, str) else cursor
    allowed_sources_set = {_session_source_key(source) for source in allowed_sources}
    items: list[ThreadItem] = []

    for metadata in metadata_items:
        if (drop_missing_rollout_paths or repair_stale_rollout_paths) and not metadata.rollout_path.exists():
            repaired_path = None
            if repair_stale_rollout_paths and codex_home is not None:
                repaired_path = find_thread_path_by_id_str(Path(codex_home), str(metadata.id))
            if repaired_path is None:
                if drop_missing_rollout_paths:
                    _delete_missing_state_thread(repair_runtime, metadata.id)
                    continue
            else:
                _repair_state_thread_path(repair_runtime, metadata.id, repaired_path)
                metadata = replace(metadata, rollout_path=repaired_path)
        item = thread_item_from_state_metadata(metadata)
        if allowed_sources_set and (
            item.source is None or _session_source_key(item.source) not in allowed_sources_set
        ):
            continue
        if not _matches_provider(item.model_provider, model_providers, default_provider):
            continue
        if not _matches_cwd(item.cwd, cwd_filters):
            continue
        if search_term is not None and search_term not in (metadata.preview or metadata.first_user_message or ""):
            continue
        sort_timestamp = _state_thread_sort_timestamp(item, sort_key)
        if sort_timestamp is None:
            continue
        if cursor_obj is not None and sort_timestamp >= cursor_obj.timestamp:
            continue
        items.append(item)

    items.sort(key=lambda item: _state_thread_sort_timestamp(item, sort_key) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    more_matches_available = len(items) > page_size
    items = items[:page_size]
    next_cursor = _state_next_cursor(items, sort_key) if items and more_matches_available else None
    return ThreadsPage(items=items, next_cursor=next_cursor, num_scanned_files=0, reached_scan_cap=False)

def _delete_missing_state_thread(runtime: Any, thread_id: str) -> None:
    if runtime is None:
        return
    for name in ("delete_thread", "remove_thread", "delete_thread_by_id"):
        method = getattr(runtime, name, None)
        if callable(method):
            method(thread_id)
            return
    if isinstance(runtime, dict):
        runtime.pop(thread_id, None)

def _repair_state_thread_path(runtime: Any, thread_id: str, rollout_path: Path) -> None:
    if runtime is None:
        return
    for name in ("update_thread_rollout_path", "repair_thread_rollout_path", "set_thread_rollout_path"):
        method = getattr(runtime, name, None)
        if callable(method):
            method(thread_id, rollout_path)
            return
    paths = getattr(runtime, "paths_by_id", None)
    if isinstance(paths, dict):
        paths[thread_id] = Path(rollout_path)
        return
    if isinstance(runtime, dict):
        runtime[thread_id] = Path(rollout_path)

def read_thread_item_from_rollout(path: Path) -> ThreadItem | None:
    """Read a single rollout into the same summary shape used by listing."""

    return _build_thread_item(
        Path(path),
        allowed_sources=set(),
        model_providers=None,
        cwd_filters=None,
        default_provider="",
        updated_at=None,
    )

def read_head_for_summary(path: Path, limit: int = HEAD_RECORD_LIMIT) -> list[Any]:
    """Read up to ``HEAD_RECORD_LIMIT`` persisted summary records from a rollout."""

    head: list[Any] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if len(head) >= limit:
                break
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                rollout_line = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            item_type = rollout_line.get("type")
            if item_type in {"session_meta", "response_item"}:
                head.append(rollout_line.get("payload"))
    return head

def read_session_meta_line(path: Path) -> SessionMetaLine:
    """Read the first rollout item as ``SessionMetaLine``."""

    head = read_head_for_summary(path)
    if not head:
        raise ValueError(f"rollout at {Path(path)} is empty")
    first = head[0]
    if not isinstance(first, dict):
        raise ValueError(f"rollout at {Path(path)} does not start with session metadata")
    try:
        return SessionMetaLine.from_mapping(first)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"rollout at {Path(path)} does not start with session metadata") from exc

def find_thread_path_by_id_str(codex_home: Path, id_str: str, state_db_ctx: Any = None) -> Path | None:
    state_path = _state_db_thread_path_by_id(state_db_ctx, id_str, archived=False)
    if state_path is not None:
        return state_path
    return _find_thread_path_by_id_str_in_subdir(codex_home, SESSIONS_SUBDIR, id_str)

def find_archived_thread_path_by_id_str(codex_home: Path, id_str: str, state_db_ctx: Any = None) -> Path | None:
    state_path = _state_db_thread_path_by_id(state_db_ctx, id_str, archived=True)
    if state_path is not None:
        return state_path
    return _find_thread_path_by_id_str_in_subdir(codex_home, ARCHIVED_SESSIONS_SUBDIR, id_str)

def _state_db_thread_path_by_id(state_db_ctx: Any, id_str: str, *, archived: bool) -> Path | None:
    if state_db_ctx is None:
        return None
    finder = getattr(state_db_ctx, "find_thread_path_by_id", None)
    if callable(finder):
        try:
            value = finder(id_str, archived=archived)
        except TypeError:
            value = finder(id_str)
        return Path(value) if value is not None else None
    finder = getattr(state_db_ctx, "thread_path_by_id", None)
    if callable(finder):
        value = finder(id_str)
        return Path(value) if value is not None else None
    paths = getattr(state_db_ctx, "paths_by_id", None)
    if isinstance(paths, Mapping):
        value = paths.get(id_str)
        return Path(value) if value is not None else None
    if isinstance(state_db_ctx, Mapping):
        value = state_db_ctx.get(id_str)
        return Path(value) if value is not None else None
    return None

def _find_thread_path_by_id_str_in_subdir(codex_home: Path, subdir: str, id_str: str) -> Path | None:
    try:
        uuid.UUID(id_str)
    except ValueError:
        return None

    root = Path(codex_home) / subdir
    if not root.exists():
        return None
    matches = sorted(root.rglob(f"*{id_str}*.jsonl"))
    return matches[0] if matches else None

@dataclass(frozen=True)
class _RolloutCandidate:
    created_at: datetime
    rollout_id: str
    path: Path
    updated_at: datetime | None = None

    def sort_timestamp(self, sort_key: ThreadSortKey) -> datetime:
        if sort_key is ThreadSortKey.UPDATED_AT:
            return self.updated_at or datetime.fromtimestamp(0, timezone.utc)
        return self.created_at

@dataclass
class _HeadSummary:
    saw_session_meta: bool = False
    thread_id: ThreadId | None = None
    first_user_message: str | None = None
    preview: str | None = None
    cwd: Path | None = None
    git_branch: str | None = None
    git_sha: str | None = None
    git_origin_url: str | None = None
    source: SessionSource | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    model_provider: str | None = None
    cli_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

def _session_source_key(source: SessionSource | str) -> str:
    return str(source)

def _coerce_sort_key(sort_key: ThreadSortKey | str) -> ThreadSortKey:
    if isinstance(sort_key, ThreadSortKey):
        return sort_key
    normalized = str(sort_key)
    try:
        return ThreadSortKey(normalized)
    except ValueError:
        if normalized in {"CreatedAt", "createdAt"}:
            return ThreadSortKey.CREATED_AT
        if normalized in {"UpdatedAt", "updatedAt"}:
            return ThreadSortKey.UPDATED_AT
        raise

def _metadata_value(metadata: Any, name: str, default: Any = None) -> Any:
    if isinstance(metadata, Mapping):
        return metadata.get(name, default)
    return getattr(metadata, name, default)

def _coerce_layout(layout: ThreadListLayout | str) -> ThreadListLayout:
    if isinstance(layout, ThreadListLayout):
        return layout
    normalized = str(layout)
    try:
        return ThreadListLayout(normalized)
    except ValueError:
        if normalized in {"NestedByDate", "nestedByDate"}:
            return ThreadListLayout.NESTED_BY_DATE
        if normalized == "Flat":
            return ThreadListLayout.FLAT
        raise

def _collect_rollout_candidates(
    root: Path,
    layout: ThreadListLayout,
    sort_key: ThreadSortKey,
) -> tuple[list[_RolloutCandidate], int, bool]:
    candidates: list[_RolloutCandidate] = []
    scanned = 0
    reached_scan_cap = False

    for path in _iter_rollout_files(root, layout):
        parsed = parse_timestamp_uuid_from_filename(path.name)
        if parsed is None:
            continue
        if scanned >= MAX_SCAN_FILES:
            reached_scan_cap = True
            break
        created_at, rollout_id = parsed
        scanned += 1
        updated_at = _file_modified_time(path)
        candidates.append(_RolloutCandidate(created_at, rollout_id, path, updated_at))

    if sort_key is ThreadSortKey.UPDATED_AT:
        candidates.sort(key=lambda item: (item.sort_timestamp(sort_key), item.rollout_id), reverse=True)
    else:
        candidates.sort(key=lambda item: (item.created_at, item.rollout_id), reverse=True)
    return candidates, scanned, reached_scan_cap

def _iter_rollout_files(root: Path, layout: ThreadListLayout) -> Iterable[Path]:
    if layout is ThreadListLayout.FLAT:
        try:
            entries = sorted(root.iterdir(), key=lambda item: item.name, reverse=True)
        except OSError:
            return []
        return (entry for entry in entries if entry.is_file() and entry.name.startswith("rollout-"))
    return root.rglob("rollout-*.jsonl")

def _file_modified_time(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None

def _build_next_cursor(items: Sequence[ThreadItem], sort_key: ThreadSortKey) -> Cursor | None:
    if not items:
        return None
    last = items[-1]
    if sort_key is ThreadSortKey.CREATED_AT:
        parsed = parse_timestamp_uuid_from_filename(last.path.name)
        return Cursor(parsed[0]) if parsed is not None else None
    if last.updated_at is None:
        return None
    return parse_cursor(last.updated_at)

def _state_thread_sort_timestamp(item: ThreadItem, sort_key: ThreadSortKey) -> datetime | None:
    value = item.created_at if sort_key is ThreadSortKey.CREATED_AT else item.updated_at
    if value is None:
        return None
    parsed = parse_cursor(value)
    return None if parsed is None else parsed.timestamp

def _state_next_cursor(items: Sequence[ThreadItem], sort_key: ThreadSortKey) -> Cursor | None:
    if not items:
        return None
    timestamp = _state_thread_sort_timestamp(items[-1], sort_key)
    return Cursor(timestamp) if timestamp is not None else None

def _build_thread_item(
    path: Path,
    allowed_sources: set[str],
    model_providers: Sequence[str] | None,
    cwd_filters: Sequence[Path] | None,
    default_provider: str,
    updated_at: str | None,
) -> ThreadItem | None:
    summary = _read_head_summary(path, HEAD_RECORD_LIMIT)
    latest_cwd = _read_latest_turn_context_cwd(path)
    if latest_cwd is not None:
        summary.cwd = latest_cwd
    if allowed_sources and (
        summary.source is None or _session_source_key(summary.source) not in allowed_sources
    ):
        return None
    if not _matches_provider(summary.model_provider, model_providers, default_provider):
        return None
    if not _matches_cwd(summary.cwd, cwd_filters):
        return None
    if not summary.saw_session_meta or summary.preview is None:
        return None

    item_updated_at = summary.updated_at or updated_at or summary.created_at
    return ThreadItem(
        path=Path(path),
        thread_id=summary.thread_id,
        first_user_message=summary.first_user_message,
        preview=summary.preview,
        cwd=summary.cwd,
        git_branch=summary.git_branch,
        git_sha=summary.git_sha,
        git_origin_url=summary.git_origin_url,
        source=summary.source,
        agent_nickname=summary.agent_nickname,
        agent_role=summary.agent_role,
        model_provider=summary.model_provider,
        cli_version=summary.cli_version,
        created_at=summary.created_at,
        updated_at=item_updated_at,
    )

def _read_head_summary(path: Path, head_limit: int) -> _HeadSummary:
    summary = _HeadSummary()
    lines_scanned = 0
    try:
        file = Path(path).open("r", encoding="utf-8")
    except OSError:
        return summary

    with file:
        while (
            lines_scanned < head_limit
            or (
                summary.saw_session_meta
                and (summary.preview is None or summary.first_user_message is None)
                and lines_scanned < head_limit + USER_EVENT_SCAN_LIMIT
            )
        ):
            line = file.readline()
            if not line:
                break
            trimmed = line.strip()
            if not trimmed:
                continue
            lines_scanned += 1
            try:
                rollout_line = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            if not isinstance(rollout_line, dict):
                continue
            item_type = rollout_line.get("type")
            payload = rollout_line.get("payload")
            timestamp = rollout_line.get("timestamp")

            if item_type == "session_meta":
                if summary.saw_session_meta or not isinstance(payload, dict):
                    continue
                try:
                    meta_line = SessionMetaLine.from_mapping(payload)
                except (KeyError, TypeError, ValueError):
                    continue
                meta = meta_line.meta
                summary.saw_session_meta = True
                summary.thread_id = meta.id
                summary.cwd = Path(meta.cwd)
                summary.source = meta.source
                summary.agent_nickname = meta.agent_nickname
                summary.agent_role = meta.agent_role
                summary.model_provider = meta.model_provider
                summary.cli_version = meta.cli_version
                summary.created_at = meta.timestamp
                if meta_line.git is not None:
                    summary.git_branch = meta_line.git.branch
                    summary.git_sha = (
                        meta_line.git.commit_hash.to_json()
                        if meta_line.git.commit_hash is not None
                        else None
                    )
                    summary.git_origin_url = meta_line.git.repository_url
            elif item_type == "response_item":
                if summary.created_at is None and isinstance(timestamp, str):
                    summary.created_at = timestamp
                preview, is_user_message = _response_item_preview(payload)
                if preview is None:
                    continue
                if summary.preview is None:
                    summary.preview = preview
                if is_user_message and summary.first_user_message is None:
                    summary.first_user_message = preview
            elif item_type == "turn_context":
                cwd = _turn_context_cwd(payload)
                if cwd is not None:
                    summary.cwd = cwd
            elif item_type == "event_msg":
                preview, is_user_message = _event_msg_preview(payload)
                if preview is None:
                    continue
                if summary.preview is None:
                    summary.preview = preview
                if is_user_message and summary.first_user_message is None:
                    summary.first_user_message = preview

            if (
                lines_scanned >= head_limit
                and summary.saw_session_meta
                and summary.preview is not None
                and summary.first_user_message is not None
            ):
                break
    return summary

def _turn_context_cwd(payload: Any) -> Path | None:
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    return Path(cwd)

def _read_latest_turn_context_cwd(path: Path) -> Path | None:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for line in reversed(text.splitlines()):
        trimmed = line.strip()
        if not trimmed:
            continue
        try:
            rollout_line = json.loads(trimmed)
        except json.JSONDecodeError:
            continue
        if not isinstance(rollout_line, dict) or rollout_line.get("type") != "turn_context":
            continue
        cwd = _turn_context_cwd(rollout_line.get("payload"))
        if cwd is not None:
            return cwd
    return None

def _event_msg_preview(payload: Any) -> tuple[str | None, bool]:
    if not isinstance(payload, dict):
        return None, False

    event_type = _normalize_event_type(payload.get("type"))
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload

    if event_type == "usermessage":
        message = body.get("message")
        text = _strip_user_message_prefix(message if isinstance(message, str) else "")
        if text:
            return text, True
        if _has_items(body.get("images")) or _has_items(body.get("local_images")):
            return "[Image]", True
        return None, True

    if event_type == "threadgoalupdated":
        goal = body.get("goal")
        if isinstance(goal, dict):
            objective = goal.get("objective")
            if isinstance(objective, str) and objective.strip():
                return objective.strip(), False
    return None, False

def _response_item_preview(payload: Any) -> tuple[str | None, bool]:
    if not isinstance(payload, dict):
        return None, False
    if payload.get("type") != "message":
        return None, False
    role = payload.get("role")
    is_user_message = role == "user"
    text = _response_item_content_text(payload.get("content"))
    if text:
        return text, is_user_message
    if is_user_message and _response_item_content_has_image(payload.get("content")):
        return "[Image]", True
    return None, is_user_message

def _response_item_content_text(content: Any) -> str | None:
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    joined = "".join(parts).strip()
    return joined or None

def _response_item_content_has_image(content: Any) -> bool:
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        return False
    return any(isinstance(item, dict) and item.get("type") == "input_image" for item in content)

def _normalize_event_type(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value.lower() if character.isalnum())

def _strip_user_message_prefix(text: str) -> str:
    index = text.find(USER_MESSAGE_BEGIN)
    if index >= 0:
        return text[index + len(USER_MESSAGE_BEGIN) :].strip()
    return text.strip()

def _has_items(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and bool(value)

def _matches_provider(
    session_provider: str | None,
    model_providers: Sequence[str] | None,
    default_provider: str,
) -> bool:
    if model_providers is None or len(model_providers) == 0:
        return True
    filters = {str(provider) for provider in model_providers}
    if session_provider is not None:
        return session_provider in filters
    return default_provider in filters

def _matches_cwd(cwd: Path | None, cwd_filters: Sequence[Path] | None) -> bool:
    if cwd_filters is None:
        return True
    if cwd is None:
        return False
    return any(_normalized_path(cwd) == _normalized_path(candidate) for candidate in cwd_filters)

def _rollout_path_for_meta(codex_home: Path, meta: SessionMeta) -> Path:
    file_timestamp = _rollout_filename_timestamp(meta.timestamp)
    year, month, day = file_timestamp[:4], file_timestamp[5:7], file_timestamp[8:10]
    return Path(codex_home) / SESSIONS_SUBDIR / year / month / day / f"rollout-{file_timestamp}-{meta.id}.jsonl"

def _rollout_filename_timestamp(timestamp: str) -> str:
    """Format Rust ``precompute_log_file_info`` local, second-precision names."""

    parsed = _parse_rfc3339(timestamp)
    if parsed is None:
        raise ValueError(f"invalid rollout timestamp: {timestamp!r}")
    return parsed.astimezone().strftime("%Y-%m-%dT%H-%M-%S")

def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))

def _parse_rfc3339(token: str) -> datetime | None:
    normalized = token
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _format_rfc3339(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond == 0:
        timespec = "seconds"
    elif normalized.microsecond % 1000 == 0:
        timespec = "milliseconds"
    else:
        timespec = "microseconds"
    text = normalized.isoformat(timespec=timespec)
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text

from pycodex.rollout.recorder import thread_item_from_state_metadata
from pycodex.rollout.session_index import _thread_ids_matching_search_term

__all__ = ['ConversationItem', 'ConversationsPage', 'Cursor', 'HEAD_RECORD_LIMIT', 'MAX_SCAN_FILES', 'SortDirection', 'ThreadItem', 'ThreadListConfig', 'ThreadListLayout', 'ThreadSortKey', 'ThreadsPage', 'USER_EVENT_SCAN_LIMIT', 'find_archived_thread_path_by_id_str', 'find_thread_path_by_id_str', 'get_threads', 'get_threads_in_root', 'list_threads_from_state_metadata', 'parse_cursor', 'parse_timestamp_uuid_from_filename', 'read_head_for_summary', 'read_session_meta_line', 'read_thread_item_from_rollout', 'rollout_date_parts']
