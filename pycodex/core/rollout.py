"""Rollout persistence helpers.

Ported from ``codex/codex-rs/rollout/src``. This module intentionally starts
with filesystem and JSONL metadata helpers; the SQLite-backed state runtime is
left for a later port.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from pycodex.protocol.protocol import USER_MESSAGE_BEGIN

SESSIONS_SUBDIR = "sessions"
ARCHIVED_SESSIONS_SUBDIR = "archived_sessions"
SESSION_INDEX_FILE = "session_index.jsonl"
HEAD_RECORD_LIMIT = 10
USER_EVENT_SCAN_LIMIT = 200
MAX_SCAN_FILES = 10000


@dataclass(frozen=True)
class Cursor:
    """Pagination cursor represented by an RFC3339 timestamp."""

    timestamp: datetime

    def to_json(self) -> str:
        return _format_rfc3339(self.timestamp)


@dataclass(frozen=True)
class GitInfo:
    commit_hash: str | None = None
    branch: str | None = None
    repository_url: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "GitInfo | None":
        if data is None:
            return None
        return cls(
            commit_hash=data.get("commit_hash"),
            branch=data.get("branch"),
            repository_url=data.get("repository_url"),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.commit_hash is not None:
            data["commit_hash"] = self.commit_hash
        if self.branch is not None:
            data["branch"] = self.branch
        if self.repository_url is not None:
            data["repository_url"] = self.repository_url
        return data


@dataclass(frozen=True)
class SessionMeta:
    id: str
    timestamp: str
    cwd: str
    originator: str
    cli_version: str
    source: str = "vscode"
    forked_from_id: str | None = None
    thread_source: str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    agent_path: str | None = None
    model_provider: str | None = None
    base_instructions: Any | None = None
    dynamic_tools: Any | None = None
    memory_mode: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SessionMeta":
        _require_keys(data, ("id", "timestamp", "cwd", "originator", "cli_version"))
        return cls(
            id=str(data.get("id", "")),
            forked_from_id=data.get("forked_from_id"),
            timestamp=str(data.get("timestamp", "")),
            cwd=str(data.get("cwd", "")),
            originator=str(data.get("originator", "")),
            cli_version=str(data.get("cli_version", "")),
            source=str(data.get("source", "vscode")),
            thread_source=data.get("thread_source"),
            agent_nickname=data.get("agent_nickname"),
            agent_role=data.get("agent_role", data.get("agent_type")),
            agent_path=data.get("agent_path"),
            model_provider=data.get("model_provider"),
            base_instructions=data.get("base_instructions"),
            dynamic_tools=data.get("dynamic_tools"),
            memory_mode=data.get("memory_mode"),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
            "cwd": self.cwd,
            "originator": self.originator,
            "cli_version": self.cli_version,
            "source": self.source,
            "model_provider": self.model_provider,
            "base_instructions": self.base_instructions,
        }
        for key in (
            "forked_from_id",
            "thread_source",
            "agent_nickname",
            "agent_role",
            "agent_path",
            "dynamic_tools",
            "memory_mode",
        ):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class SessionMetaLine:
    meta: SessionMeta
    git: GitInfo | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SessionMetaLine":
        payload = dict(data)
        git = GitInfo.from_mapping(payload.pop("git", None))
        return cls(meta=SessionMeta.from_mapping(payload), git=git)

    def to_mapping(self) -> dict[str, Any]:
        data = self.meta.to_mapping()
        if self.git is not None:
            data["git"] = self.git.to_mapping()
        return data


@dataclass(frozen=True)
class SessionIndexEntry:
    id: str
    thread_name: str
    updated_at: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SessionIndexEntry":
        return cls(
            id=str(data["id"]),
            thread_name=str(data["thread_name"]),
            updated_at=str(data["updated_at"]),
        )

    def to_mapping(self) -> dict[str, str]:
        return {"id": self.id, "thread_name": self.thread_name, "updated_at": self.updated_at}


class ThreadSortKey(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class ThreadListLayout(str, Enum):
    NESTED_BY_DATE = "nested_by_date"
    FLAT = "flat"


@dataclass(frozen=True)
class ThreadItem:
    """Summary information for a thread rollout file."""

    path: Path
    thread_id: str | None = None
    first_user_message: str | None = None
    preview: str | None = None
    cwd: Path | None = None
    git_branch: str | None = None
    git_sha: str | None = None
    git_origin_url: str | None = None
    source: str | None = None
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
) -> ThreadsPage:
    """List persisted threads below ``<codex_home>/sessions``."""

    return get_threads_in_root(
        Path(codex_home) / SESSIONS_SUBDIR,
        page_size,
        cursor=cursor,
        sort_key=sort_key,
        allowed_sources=allowed_sources,
        model_providers=model_providers,
        cwd_filters=cwd_filters,
        default_provider=default_provider,
        layout=ThreadListLayout.NESTED_BY_DATE,
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
    allowed_sources_set = {str(source) for source in allowed_sources}

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


def session_index_path(codex_home: Path) -> Path:
    return Path(codex_home) / SESSION_INDEX_FILE


def append_thread_name(codex_home: Path, thread_id: str | uuid.UUID, name: str) -> None:
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    append_session_index_entry(
        codex_home,
        SessionIndexEntry(id=str(thread_id), thread_name=name, updated_at=updated_at),
    )


def append_session_index_entry(codex_home: Path, entry: SessionIndexEntry) -> None:
    path = session_index_path(codex_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(entry.to_mapping(), separators=(",", ":")))
        file.write("\n")


def find_thread_name_by_id(codex_home: Path, thread_id: str | uuid.UUID) -> str | None:
    entry = _scan_index_from_end(codex_home, lambda candidate: candidate.id == str(thread_id))
    return entry.thread_name if entry is not None else None


def find_thread_names_by_ids(codex_home: Path, thread_ids: Iterable[str | uuid.UUID]) -> dict[str, str]:
    wanted = {str(thread_id) for thread_id in thread_ids}
    if not wanted:
        return {}
    names: dict[str, str] = {}
    for entry in _read_index_entries(codex_home):
        if entry.id in wanted and entry.thread_name.strip():
            names[entry.id] = entry.thread_name
    return names


def find_thread_meta_by_name_str(codex_home: Path, name: str) -> tuple[Path, SessionMetaLine] | None:
    """Find the newest indexed thread name with a readable rollout header."""

    if not name.strip():
        return None

    seen: set[str] = set()
    for entry in reversed(_read_index_entries(codex_home)):
        if entry.id in seen:
            continue
        seen.add(entry.id)
        if entry.thread_name != name:
            continue
        path = find_thread_path_by_id_str(codex_home, entry.id)
        if path is None:
            continue
        try:
            return path, read_session_meta_line(path)
        except ValueError:
            continue
    return None


def find_thread_path_by_id_str(codex_home: Path, id_str: str) -> Path | None:
    return _find_thread_path_by_id_str_in_subdir(codex_home, SESSIONS_SUBDIR, id_str)


def find_archived_thread_path_by_id_str(codex_home: Path, id_str: str) -> Path | None:
    return _find_thread_path_by_id_str_in_subdir(codex_home, ARCHIVED_SESSIONS_SUBDIR, id_str)


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


def _scan_index_from_end(codex_home: Path, predicate: Callable[[SessionIndexEntry], bool]) -> SessionIndexEntry | None:
    for entry in reversed(_read_index_entries(codex_home)):
        if predicate(entry):
            return entry
    return None


def _read_index_entries(codex_home: Path) -> list[SessionIndexEntry]:
    path = session_index_path(codex_home)
    if not path.exists():
        return []
    entries: list[SessionIndexEntry] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                data = json.loads(trimmed)
                entries.append(SessionIndexEntry.from_mapping(data))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return entries


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
    thread_id: str | None = None
    first_user_message: str | None = None
    preview: str | None = None
    cwd: Path | None = None
    git_branch: str | None = None
    git_sha: str | None = None
    git_origin_url: str | None = None
    source: str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    model_provider: str | None = None
    cli_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


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


def _build_thread_item(
    path: Path,
    allowed_sources: set[str],
    model_providers: Sequence[str] | None,
    cwd_filters: Sequence[Path] | None,
    default_provider: str,
    updated_at: str | None,
) -> ThreadItem | None:
    summary = _read_head_summary(path, HEAD_RECORD_LIMIT)
    if allowed_sources and (summary.source is None or summary.source not in allowed_sources):
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
                    summary.git_sha = meta_line.git.commit_hash
                    summary.git_origin_url = meta_line.git.repository_url
            elif item_type == "response_item":
                if summary.created_at is None and isinstance(timestamp, str):
                    summary.created_at = timestamp
            elif item_type == "event_msg":
                preview, is_user_message = _event_msg_preview(payload)
                if preview is None:
                    continue
                if summary.preview is None:
                    summary.preview = preview
                if is_user_message and summary.first_user_message is None:
                    summary.first_user_message = preview

            if summary.saw_session_meta and summary.preview is not None and summary.first_user_message is not None:
                break
    return summary


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


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _require_keys(data: dict[str, Any], keys: Iterable[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise KeyError(", ".join(missing))


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
