"""Rust ``codex-thread-store::types`` owner."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from inspect import isawaitable
from pathlib import Path
from time import monotonic
from typing import Any, Mapping, Protocol

from pycodex.protocol import (
    USER_MESSAGE_BEGIN,
    AskForApproval,
    EventMsg,
    GitInfo,
    RolloutItem,
    SandboxPolicy,
    SessionMetaLine,
    SessionSource,
    ThreadId,
    ThreadMemoryMode,
    ThreadSource,
    UserMessageEvent,
)
from pycodex.rollout import (
    ARCHIVED_SESSIONS_SUBDIR,
    EventPersistenceMode,
    RolloutRecorder,
    RolloutRecorderParams,
    ThreadListLayout,
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
    persisted_rollout_items,
    rollout_date_parts,
    search_rollout_paths,
)
from pycodex.rollout.list import list_threads_from_state_metadata

from .optional_option import (
    ClearableField,
    _ClearField,
    clear_field,
    deserialize as _clearable_from_mapping,
    is_clear_field,
    serialize as _put_clearable,
)

class ThreadEventPersistenceMode(str, Enum):
    LIMITED = "limited"
    EXTENDED = "extended"

@dataclass(frozen=True)
class ThreadPersistenceMetadata:
    cwd: Path | None
    model_provider: str
    memory_mode: ThreadMemoryMode

@dataclass(frozen=True)
class CreateThreadParams:
    thread_id: ThreadId
    forked_from_id: ThreadId | None
    source: SessionSource
    thread_source: ThreadSource | None
    base_instructions: Any
    dynamic_tools: tuple[Any, ...]
    metadata: ThreadPersistenceMetadata
    event_persistence_mode: ThreadEventPersistenceMode = ThreadEventPersistenceMode.LIMITED

@dataclass(frozen=True)
class ResumeThreadParams:
    thread_id: ThreadId
    rollout_path: Path | None
    history: tuple[Any, ...] | None
    include_archived: bool
    metadata: ThreadPersistenceMetadata
    event_persistence_mode: ThreadEventPersistenceMode = ThreadEventPersistenceMode.LIMITED

@dataclass(frozen=True)
class AppendThreadItemsParams:
    thread_id: ThreadId
    items: tuple[Any, ...]

@dataclass(frozen=True)
class LoadThreadHistoryParams:
    thread_id: ThreadId
    include_archived: bool

@dataclass(frozen=True)
class StoredThreadHistory:
    thread_id: ThreadId
    items: tuple[Any, ...]

@dataclass(frozen=True)
class ReadThreadParams:
    thread_id: ThreadId
    include_archived: bool
    include_history: bool

@dataclass(frozen=True)
class ReadThreadByRolloutPathParams:
    rollout_path: Path
    include_archived: bool
    include_history: bool

class ThreadSortKey(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"

@dataclass(frozen=True)
class ListThreadsParams:
    page_size: int
    cursor: str | None
    sort_key: ThreadSortKey = ThreadSortKey.CREATED_AT
    sort_direction: SortDirection = SortDirection.DESC
    allowed_sources: tuple[SessionSource, ...] = ()
    model_providers: tuple[str, ...] | None = None
    cwd_filters: tuple[Path, ...] | None = None
    archived: bool = False
    search_term: str | None = None
    use_state_db_only: bool = False

@dataclass(frozen=True)
class SearchThreadsParams:
    page_size: int
    cursor: str | None
    sort_key: ThreadSortKey
    sort_direction: SortDirection
    allowed_sources: tuple[SessionSource, ...]
    archived: bool
    search_term: str

@dataclass(frozen=True)
class ThreadPage:
    items: tuple["StoredThread", ...]
    next_cursor: str | None = None

@dataclass(frozen=True)
class StoredThreadSearchResult:
    thread: "StoredThread"
    snippet: str

@dataclass(frozen=True)
class ThreadSearchPage:
    items: tuple[StoredThreadSearchResult, ...]
    next_cursor: str | None = None

class StoredTurnItemsView(str, Enum):
    NOT_LOADED = "not_loaded"
    SUMMARY = "summary"
    FULL = "full"

class StoredTurnStatus(str, Enum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"

@dataclass(frozen=True)
class StoredTurnError:
    message: str
    additional_details: str | None = None

@dataclass(frozen=True)
class ListTurnsParams:
    thread_id: ThreadId
    include_archived: bool
    cursor: str | None
    page_size: int
    sort_direction: SortDirection
    items_view: StoredTurnItemsView

@dataclass(frozen=True)
class StoredTurn:
    turn_id: str
    items: tuple[Any, ...]
    items_view: StoredTurnItemsView
    status: StoredTurnStatus
    error: StoredTurnError | None = None
    started_at: int | None = None
    completed_at: int | None = None
    duration_ms: int | None = None

@dataclass(frozen=True)
class TurnPage:
    turns: tuple[StoredTurn, ...]
    next_cursor: str | None = None
    backwards_cursor: str | None = None

@dataclass(frozen=True)
class ListItemsParams:
    thread_id: ThreadId
    turn_id: str
    include_archived: bool
    cursor: str | None
    page_size: int
    sort_direction: SortDirection

@dataclass(frozen=True)
class ItemPage:
    items: tuple[Any, ...]
    next_cursor: str | None = None
    backwards_cursor: str | None = None

@dataclass(frozen=True)
class StoredThread:
    thread_id: ThreadId
    rollout_path: Path | None
    forked_from_id: ThreadId | None
    preview: str
    name: str | None
    model_provider: str
    model: str | None
    reasoning_effort: Any
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    cwd: Path
    cli_version: str
    source: SessionSource
    thread_source: ThreadSource | None
    agent_nickname: str | None
    agent_role: str | None
    agent_path: str | None
    git_info: Any
    approval_mode: AskForApproval
    sandbox_policy: SandboxPolicy
    token_usage: Any
    first_user_message: str | None
    history: StoredThreadHistory | None = None

@dataclass(frozen=True)
class GitInfoPatch:
    sha: ClearableField = None
    branch: ClearableField = None
    origin_url: ClearableField = None

    def merge(self, next_patch: "GitInfoPatch") -> "GitInfoPatch":
        return GitInfoPatch(
            sha=next_patch.sha if next_patch.sha is not None else self.sha,
            branch=next_patch.branch if next_patch.branch is not None else self.branch,
            origin_url=next_patch.origin_url if next_patch.origin_url is not None else self.origin_url,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | "GitInfoPatch") -> "GitInfoPatch":
        if isinstance(value, cls):
            return value
        return cls(
            sha=_clearable_from_mapping(value, "sha"),
            branch=_clearable_from_mapping(value, "branch"),
            origin_url=_clearable_from_mapping(value, "origin_url"),
        )

    def to_mapping(self) -> dict[str, Any]:
        output: dict[str, Any] = {}
        _put_clearable(output, "sha", self.sha)
        _put_clearable(output, "branch", self.branch)
        _put_clearable(output, "origin_url", self.origin_url)
        return output

@dataclass(frozen=True)
class ThreadMetadataPatch:
    name: ClearableField = None
    rollout_path: Path | None = None
    preview: str | None = None
    title: str | None = None
    model_provider: str | None = None
    model: str | None = None
    reasoning_effort: Any = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source: SessionSource | None = None
    thread_source: ClearableField = None
    agent_nickname: ClearableField = None
    agent_role: ClearableField = None
    agent_path: ClearableField = None
    cwd: Path | None = None
    cli_version: str | None = None
    approval_mode: AskForApproval | None = None
    sandbox_policy: SandboxPolicy | None = None
    token_usage: Any = None
    first_user_message: str | None = None
    git_info: GitInfoPatch | None = None
    memory_mode: ThreadMemoryMode | None = None

    def merge(self, next_patch: "ThreadMetadataPatch") -> "ThreadMetadataPatch":
        values = self.__dict__.copy()
        for key, value in next_patch.__dict__.items():
            if key == "git_info" and value is not None and values.get("git_info") is not None:
                values[key] = values[key].merge(value)
            elif value is not None:
                values[key] = value
        return ThreadMetadataPatch(**values)

    def is_empty(self) -> bool:
        return all(value is None for value in self.__dict__.values())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | "ThreadMetadataPatch") -> "ThreadMetadataPatch":
        if isinstance(value, cls):
            return value
        git_info = value.get("git_info")
        return cls(
            name=_clearable_from_mapping(value, "name"),
            rollout_path=_optional_path(value.get("rollout_path")),
            preview=_optional_str(value.get("preview")),
            title=_optional_str(value.get("title")),
            model_provider=_optional_str(value.get("model_provider")),
            model=_optional_str(value.get("model")),
            reasoning_effort=value.get("reasoning_effort"),
            created_at=_optional_datetime(value.get("created_at")),
            updated_at=_optional_datetime(value.get("updated_at")),
            source=value.get("source"),
            thread_source=_clearable_from_mapping(value, "thread_source", parser=ThreadSource.parse),
            agent_nickname=_clearable_from_mapping(value, "agent_nickname"),
            agent_role=_clearable_from_mapping(value, "agent_role"),
            agent_path=_clearable_from_mapping(value, "agent_path"),
            cwd=_optional_path(value.get("cwd")),
            cli_version=_optional_str(value.get("cli_version")),
            approval_mode=value.get("approval_mode"),
            sandbox_policy=value.get("sandbox_policy"),
            token_usage=value.get("token_usage"),
            first_user_message=_optional_str(value.get("first_user_message")),
            git_info=GitInfoPatch.from_mapping(git_info) if git_info is not None else None,
            memory_mode=value.get("memory_mode"),
        )

    def to_mapping(self) -> dict[str, Any]:
        output: dict[str, Any] = {}
        _put_clearable(output, "name", self.name)
        _put_optional(output, "rollout_path", _path_to_str(self.rollout_path))
        _put_optional(output, "preview", self.preview)
        _put_optional(output, "title", self.title)
        _put_optional(output, "model_provider", self.model_provider)
        _put_optional(output, "model", self.model)
        _put_optional(output, "reasoning_effort", _enum_or_value(self.reasoning_effort))
        _put_optional(output, "created_at", _datetime_to_rfc3339(self.created_at))
        _put_optional(output, "updated_at", _datetime_to_rfc3339(self.updated_at))
        _put_optional(output, "source", _enum_or_value(self.source))
        _put_clearable(output, "thread_source", self.thread_source)
        _put_clearable(output, "agent_nickname", self.agent_nickname)
        _put_clearable(output, "agent_role", self.agent_role)
        _put_clearable(output, "agent_path", self.agent_path)
        _put_optional(output, "cwd", _path_to_str(self.cwd))
        _put_optional(output, "cli_version", self.cli_version)
        _put_optional(output, "approval_mode", _enum_or_value(self.approval_mode))
        _put_optional(output, "sandbox_policy", _mapping_or_value(self.sandbox_policy))
        _put_optional(output, "token_usage", _mapping_or_value(self.token_usage))
        _put_optional(output, "first_user_message", self.first_user_message)
        if self.git_info is not None:
            output["git_info"] = self.git_info.to_mapping()
        _put_optional(output, "memory_mode", _enum_or_value(self.memory_mode))
        return output

@dataclass(frozen=True)
class UpdateThreadMetadataParams:
    thread_id: ThreadId
    patch: ThreadMetadataPatch
    include_archived: bool

@dataclass(frozen=True)
class ArchiveThreadParams:
    thread_id: ThreadId

def _put_optional(output: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        output[key] = value

def _clearable_to_optional_value(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if is_clear_field(value):
        return None
    return value

def _enum_or_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value

def _mapping_or_value(value: Any) -> Any:
    mapper = getattr(value, "to_mapping", None)
    if callable(mapper):
        return mapper()
    return _enum_or_value(value)

def _metadata_enum_string(value: Any) -> str:
    from pycodex.state.model.thread_metadata import enum_to_string

    return enum_to_string(value)

def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

def _optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    return Path(value)

def _path_to_str(value: Path | None) -> str | None:
    if value is None:
        return None
    return value.as_posix()

def _optional_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

def _datetime_to_rfc3339(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
