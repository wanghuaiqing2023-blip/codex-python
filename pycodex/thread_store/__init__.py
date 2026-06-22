"""Port of Rust ``codex-thread-store`` public API surface.

Rust sources:
- ``codex/codex-rs/thread-store/src/lib.rs``
- ``codex/codex-rs/thread-store/src/types.rs``
- ``codex/codex-rs/thread-store/src/store.rs``
- ``codex/codex-rs/thread-store/src/error.rs``
"""

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
    list_threads_from_state_metadata,
    parse_cursor,
    read_thread_item_from_rollout,
    read_session_meta_line,
    persisted_rollout_items,
    rollout_date_parts,
    search_rollout_paths,
)


ThreadStoreResult = Any
IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER = "[Image]"
THREAD_UPDATED_AT_TOUCH_INTERVAL_SECONDS = 0.05


@dataclass(frozen=True)
class _ClearField:
    pass


_CLEAR_FIELD = _ClearField()
ClearableField = Any


def clear_field() -> _ClearField:
    """Return the Python marker for Rust ``Some(None)`` clearable fields."""

    return _CLEAR_FIELD


def is_clear_field(value: Any) -> bool:
    return isinstance(value, _ClearField)


class ThreadStoreError(Exception):
    kind: str

    def __init__(self, kind: str, message_text: str, **fields: Any) -> None:
        super().__init__(message_text)
        self.kind = kind
        self.fields = fields

    @classmethod
    def thread_not_found(cls, thread_id: ThreadId) -> "ThreadStoreError":
        return cls("thread_not_found", f"thread {thread_id} not found", thread_id=thread_id)

    @classmethod
    def invalid_request(cls, message: str) -> "ThreadStoreError":
        return cls("invalid_request", f"invalid thread-store request: {message}", message=message)

    @classmethod
    def conflict(cls, message: str) -> "ThreadStoreError":
        return cls("conflict", f"thread-store conflict: {message}", message=message)

    @classmethod
    def unsupported(cls, operation: str) -> "ThreadStoreError":
        return cls("unsupported", f"thread-store unsupported operation: {operation}", operation=operation)

    @classmethod
    def internal(cls, message: str) -> "ThreadStoreError":
        return cls("internal", f"thread-store internal error: {message}", message=message)


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
class PendingThreadMetadataPatch:
    patch: ThreadMetadataPatch
    generation: int


class ThreadMetadataSync:
    """Rust ``thread_metadata_sync.rs`` metadata derivation helper."""

    def __init__(
        self,
        *,
        thread_id: ThreadId,
        cwd_seen: bool = False,
        preview_seen: bool = False,
        first_user_message_seen: bool = False,
        title_seen: bool = False,
        pending_update: ThreadMetadataPatch | None = None,
        pending_update_generation: int = 0,
        last_touch_persisted_at: float | None = None,
        defer_create_update_until_history_exists: bool = False,
        defer_resume_update_until_append: bool = False,
    ) -> None:
        self.thread_id = thread_id
        self.cwd_seen = cwd_seen
        self.preview_seen = preview_seen
        self.first_user_message_seen = first_user_message_seen
        self.title_seen = title_seen
        self.pending_update = pending_update
        self.pending_update_generation = pending_update_generation
        self.last_touch_persisted_at = last_touch_persisted_at
        self.defer_create_update_until_history_exists = defer_create_update_until_history_exists
        self.defer_resume_update_until_append = defer_resume_update_until_append

    @classmethod
    async def for_create(cls, params: CreateThreadParams) -> "ThreadMetadataSync":
        created_at = datetime.now(timezone.utc)
        cwd = params.metadata.cwd or Path()
        source = params.source
        update = ThreadMetadataPatch(
            model_provider=params.metadata.model_provider,
            created_at=created_at,
            updated_at=created_at,
            source=source,
            thread_source=params.thread_source,
            agent_nickname=_source_call_or_none(source, "get_nickname"),
            agent_role=_source_call_or_none(source, "get_agent_role"),
            agent_path=_source_call_or_none(source, "get_agent_path"),
            cwd=cwd,
            cli_version="test",
            memory_mode=params.metadata.memory_mode,
        )
        return cls(
            thread_id=params.thread_id,
            cwd_seen=bool(str(cwd)),
            pending_update=update,
            pending_update_generation=1,
            defer_create_update_until_history_exists=True,
        )

    @classmethod
    def for_resume(cls, params: ResumeThreadParams) -> "ThreadMetadataSync":
        cwd_seen = params.metadata.cwd is not None and bool(str(params.metadata.cwd))
        sync = cls(thread_id=params.thread_id, cwd_seen=cwd_seen)
        if params.history is not None:
            update = sync._observe_resume_history(params.history)
            sync._merge_pending_update(update)
            sync.defer_resume_update_until_append = sync.pending_update is not None
        return sync

    def take_pending_update(self) -> PendingThreadMetadataPatch | None:
        if self.pending_update is None:
            return None
        return PendingThreadMetadataPatch(self.pending_update, self.pending_update_generation)

    def take_pending_update_for_existing_history(self) -> PendingThreadMetadataPatch | None:
        if self.defer_create_update_until_history_exists:
            return None
        if self.defer_resume_update_until_append:
            return None
        return self.take_pending_update()

    def mark_pending_update_applied(self, update: PendingThreadMetadataPatch) -> None:
        if self.pending_update_generation == update.generation:
            self.pending_update = None
        if update.patch.updated_at is not None:
            self.last_touch_persisted_at = monotonic()

    def observe_appended_items(self, items: tuple[Any, ...] | list[Any]) -> PendingThreadMetadataPatch | None:
        self.defer_create_update_until_history_exists = False
        self.defer_resume_update_until_append = False
        affects_metadata = any(rollout_item_affects_thread_metadata(item) for item in items)
        update = self._observe_items(items) if affects_metadata else thread_updated_at_touch()
        self._merge_pending_update(update)
        if (
            not affects_metadata
            and self.pending_update is not None
            and not update_has_metadata_facts(self.pending_update)
            and self.last_touch_persisted_at is not None
            and monotonic() - self.last_touch_persisted_at < THREAD_UPDATED_AT_TOUCH_INTERVAL_SECONDS
        ):
            return None
        return self.take_pending_update()

    def _observe_items(self, items: tuple[Any, ...] | list[Any]) -> ThreadMetadataPatch | None:
        return self._observe_items_with_update(items, ThreadMetadataPatch(updated_at=datetime.now(timezone.utc)))

    def _observe_resume_history(self, items: tuple[Any, ...] | list[Any]) -> ThreadMetadataPatch | None:
        return self._observe_items_with_update(items, ThreadMetadataPatch())

    def _observe_items_with_update(
        self,
        items: tuple[Any, ...] | list[Any],
        update: ThreadMetadataPatch,
    ) -> ThreadMetadataPatch | None:
        if not items:
            return None
        for raw_item in items:
            item = _rollout_item(raw_item)
            if item.type == "session_meta":
                meta_line = _session_meta_line(item.payload)
                if meta_line is not None and meta_line.meta.id == self.thread_id:
                    update = self._observe_session_meta(meta_line, update)
            elif item.type == "turn_context":
                update = self._observe_turn_context(item.payload, update)
            elif item.type == "event_msg":
                update = self._observe_event_msg(item.payload, update)
        return update

    def _observe_session_meta(self, meta_line: SessionMetaLine, update: ThreadMetadataPatch) -> ThreadMetadataPatch:
        meta = meta_line.meta
        values = update.__dict__.copy()
        values["created_at"] = parse_session_timestamp(meta.timestamp)
        values["source"] = meta.source
        values["thread_source"] = meta.thread_source
        values["agent_nickname"] = meta.agent_nickname
        values["agent_role"] = meta.agent_role
        values["agent_path"] = meta.agent_path
        if meta.model_provider:
            values["model_provider"] = meta.model_provider
        if meta.cli_version:
            values["cli_version"] = meta.cli_version
        if str(meta.cwd):
            self.cwd_seen = True
            values["cwd"] = meta.cwd
        if meta_line.git is not None:
            values["git_info"] = git_info_patch_from_observation(meta_line.git)
        memory_mode = parse_memory_mode(meta.memory_mode)
        if memory_mode is not None:
            values["memory_mode"] = memory_mode
        return ThreadMetadataPatch(**values)

    def _observe_turn_context(self, turn_ctx: Any, update: ThreadMetadataPatch) -> ThreadMetadataPatch:
        values = update.__dict__.copy()
        cwd = getattr(turn_ctx, "cwd", None)
        if not self.cwd_seen and cwd is not None and str(cwd):
            self.cwd_seen = True
            values["cwd"] = Path(cwd)
        values["model"] = getattr(turn_ctx, "model", None)
        values["reasoning_effort"] = getattr(turn_ctx, "effort", None)
        values["approval_mode"] = getattr(turn_ctx, "approval_policy", None)
        values["sandbox_policy"] = getattr(turn_ctx, "sandbox_policy", None)
        return ThreadMetadataPatch(**values)

    def _observe_event_msg(self, raw_event: Any, update: ThreadMetadataPatch) -> ThreadMetadataPatch:
        event = _event_msg(raw_event)
        values = update.__dict__.copy()
        if event.type == "user_message":
            user = event.payload
            if isinstance(user, UserMessageEvent):
                preview = user_message_preview(user)
                if preview is not None:
                    if not self.first_user_message_seen:
                        self.first_user_message_seen = True
                        values["first_user_message"] = preview
                    if not self.preview_seen:
                        self.preview_seen = True
                        values["preview"] = preview
                if not self.title_seen:
                    title = strip_user_message_prefix(user.message)
                    if title:
                        self.title_seen = True
                        values["title"] = title
        elif event.type == "token_count":
            info = getattr(event.payload, "info", None)
            if info is not None:
                values["token_usage"] = getattr(info, "total_token_usage", None)
        elif event.type == "thread_goal_updated" and not self.preview_seen:
            goal = getattr(event.payload, "goal", None)
            objective = str(getattr(goal, "objective", "")).strip()
            if objective:
                self.preview_seen = True
                values["preview"] = objective
        return ThreadMetadataPatch(**values)

    def _merge_pending_update(self, update: ThreadMetadataPatch | None) -> None:
        if update is None:
            return
        if self.pending_update is None:
            self.pending_update = update
        else:
            self.pending_update = self.pending_update.merge(update)
        self.pending_update_generation = (self.pending_update_generation + 1) & ((1 << 64) - 1)


@dataclass(frozen=True)
class ArchiveThreadParams:
    thread_id: ThreadId


class ThreadStore(Protocol):
    async def create_thread(self, params: CreateThreadParams) -> ThreadStoreResult:
        ...

    async def resume_thread(self, params: ResumeThreadParams) -> ThreadStoreResult:
        ...

    async def append_items(self, params: AppendThreadItemsParams) -> ThreadStoreResult:
        ...

    async def persist_thread(self, thread_id: ThreadId) -> ThreadStoreResult:
        ...

    async def flush_thread(self, thread_id: ThreadId) -> ThreadStoreResult:
        ...

    async def shutdown_thread(self, thread_id: ThreadId) -> ThreadStoreResult:
        ...

    async def discard_thread(self, thread_id: ThreadId) -> ThreadStoreResult:
        ...

    async def load_history(self, params: LoadThreadHistoryParams) -> StoredThreadHistory:
        ...

    async def read_thread(self, params: ReadThreadParams) -> StoredThread:
        ...

    async def read_thread_by_rollout_path(self, params: ReadThreadByRolloutPathParams) -> StoredThread:
        ...

    async def list_threads(self, params: ListThreadsParams) -> ThreadPage:
        ...

    async def search_threads(self, params: SearchThreadsParams) -> ThreadSearchPage:
        ...

    async def list_turns(self, params: ListTurnsParams) -> TurnPage:
        ...

    async def list_items(self, params: ListItemsParams) -> ItemPage:
        ...

    async def update_thread_metadata(self, params: UpdateThreadMetadataParams) -> StoredThread:
        ...

    async def archive_thread(self, params: ArchiveThreadParams) -> ThreadStoreResult:
        ...

    async def unarchive_thread(self, params: ArchiveThreadParams) -> StoredThread:
        ...


@dataclass(frozen=True)
class InMemoryThreadStoreCalls:
    create_thread: int = 0
    resume_thread: int = 0
    append_items: int = 0
    persist_thread: int = 0
    flush_thread: int = 0
    shutdown_thread: int = 0
    discard_thread: int = 0
    load_history: int = 0
    read_thread: int = 0
    read_thread_by_rollout_path: int = 0
    list_threads: int = 0
    update_thread_metadata: int = 0
    archive_thread: int = 0
    unarchive_thread: int = 0


class InMemoryThreadStore:
    _stores: dict[str, "InMemoryThreadStore"] = {}

    def __init__(self) -> None:
        self._calls = InMemoryThreadStoreCalls()
        self._created_threads: dict[ThreadId, CreateThreadParams] = {}
        self._histories: dict[ThreadId, list[Any]] = {}
        self._metadata_updates: dict[ThreadId, ThreadMetadataPatch] = {}
        self._names: dict[ThreadId, str | None] = {}
        self._rollout_paths: dict[Path, ThreadId] = {}

    @classmethod
    def for_id(cls, id: str) -> "InMemoryThreadStore":
        return cls._stores.setdefault(id, cls())

    @classmethod
    def remove_id(cls, id: str) -> "InMemoryThreadStore | None":
        return cls._stores.pop(id, None)

    async def calls(self) -> InMemoryThreadStoreCalls:
        return self._calls

    async def create_thread(self, params: CreateThreadParams) -> None:
        self._calls = replace(self._calls, create_thread=self._calls.create_thread + 1)
        self._histories.setdefault(params.thread_id, [])
        self._created_threads[params.thread_id] = params

    async def resume_thread(self, params: ResumeThreadParams) -> None:
        self._calls = replace(self._calls, resume_thread=self._calls.resume_thread + 1)
        self._histories.setdefault(params.thread_id, [])
        if params.rollout_path is not None:
            self._rollout_paths[params.rollout_path] = params.thread_id

    async def append_items(self, params: AppendThreadItemsParams) -> None:
        self._calls = replace(self._calls, append_items=self._calls.append_items + 1)
        self._histories.setdefault(params.thread_id, []).extend(params.items)

    async def persist_thread(self, _thread_id: ThreadId) -> None:
        self._calls = replace(self._calls, persist_thread=self._calls.persist_thread + 1)

    async def flush_thread(self, _thread_id: ThreadId) -> None:
        self._calls = replace(self._calls, flush_thread=self._calls.flush_thread + 1)

    async def shutdown_thread(self, _thread_id: ThreadId) -> None:
        self._calls = replace(self._calls, shutdown_thread=self._calls.shutdown_thread + 1)

    async def discard_thread(self, _thread_id: ThreadId) -> None:
        self._calls = replace(self._calls, discard_thread=self._calls.discard_thread + 1)

    async def load_history(self, params: LoadThreadHistoryParams) -> StoredThreadHistory:
        self._calls = replace(self._calls, load_history=self._calls.load_history + 1)
        if params.thread_id not in self._histories:
            raise ThreadStoreError.thread_not_found(params.thread_id)
        return StoredThreadHistory(params.thread_id, tuple(self._histories[params.thread_id]))

    async def read_thread(self, params: ReadThreadParams) -> StoredThread:
        self._calls = replace(self._calls, read_thread=self._calls.read_thread + 1)
        return self._stored_thread_from_state(params.thread_id, params.include_history)

    async def read_thread_by_rollout_path(self, params: ReadThreadByRolloutPathParams) -> StoredThread:
        self._calls = replace(self._calls, read_thread_by_rollout_path=self._calls.read_thread_by_rollout_path + 1)
        thread_id = self._rollout_paths.get(params.rollout_path)
        if thread_id is None:
            raise ThreadStoreError.invalid_request(
                f"in-memory thread store does not know rollout path {params.rollout_path}"
            )
        return self._stored_thread_from_state(thread_id, params.include_history)

    async def list_threads(self, _params: ListThreadsParams) -> ThreadPage:
        self._calls = replace(self._calls, list_threads=self._calls.list_threads + 1)
        thread_ids = sorted(self._created_threads, key=str)
        return ThreadPage(tuple(self._stored_thread_from_state(thread_id, False) for thread_id in thread_ids))

    async def search_threads(self, _params: SearchThreadsParams) -> ThreadSearchPage:
        raise ThreadStoreError.unsupported("thread/search")

    async def list_turns(self, _params: ListTurnsParams) -> TurnPage:
        raise ThreadStoreError.unsupported("list_turns")

    async def list_items(self, _params: ListItemsParams) -> ItemPage:
        raise ThreadStoreError.unsupported("list_items")

    async def update_thread_metadata(self, params: UpdateThreadMetadataParams) -> StoredThread:
        self._calls = replace(self._calls, update_thread_metadata=self._calls.update_thread_metadata + 1)
        if params.patch.name is not None:
            self._names[params.thread_id] = params.patch.name
        existing = self._metadata_updates.get(params.thread_id, ThreadMetadataPatch())
        self._metadata_updates[params.thread_id] = existing.merge(params.patch)
        return self._stored_thread_from_state(params.thread_id, False)

    async def archive_thread(self, _params: ArchiveThreadParams) -> None:
        self._calls = replace(self._calls, archive_thread=self._calls.archive_thread + 1)

    async def unarchive_thread(self, params: ArchiveThreadParams) -> StoredThread:
        self._calls = replace(self._calls, unarchive_thread=self._calls.unarchive_thread + 1)
        return self._stored_thread_from_state(params.thread_id, False)

    def _stored_thread_from_state(self, thread_id: ThreadId, include_history: bool) -> StoredThread:
        created = self._created_threads.get(thread_id)
        if created is None:
            raise ThreadStoreError.thread_not_found(thread_id)
        patch = self._metadata_updates.get(thread_id, ThreadMetadataPatch())
        now = datetime.now(timezone.utc)
        history = StoredThreadHistory(thread_id, tuple(self._histories.get(thread_id, ()))) if include_history else None
        rollout_path = patch.rollout_path
        if rollout_path is None:
            for candidate_path, mapped_thread_id in self._rollout_paths.items():
                if mapped_thread_id == thread_id:
                    rollout_path = candidate_path
                    break
        return StoredThread(
            thread_id=thread_id,
            rollout_path=rollout_path,
            forked_from_id=created.forked_from_id,
            preview=patch.preview or "",
            name=_clearable_to_optional_value(self._names.get(thread_id)),
            model_provider=patch.model_provider or "test",
            model=patch.model,
            reasoning_effort=patch.reasoning_effort,
            created_at=patch.created_at or now,
            updated_at=patch.updated_at or now,
            archived_at=None,
            cwd=patch.cwd or Path(),
            cli_version=patch.cli_version or "test",
            source=patch.source or created.source,
            thread_source=_clearable_to_optional_value(patch.thread_source, created.thread_source),
            agent_nickname=_clearable_to_optional_value(patch.agent_nickname),
            agent_role=_clearable_to_optional_value(patch.agent_role),
            agent_path=_clearable_to_optional_value(patch.agent_path),
            git_info=None,
            approval_mode=patch.approval_mode or AskForApproval.NEVER,
            sandbox_policy=patch.sandbox_policy or SandboxPolicy.new_read_only_policy(),
            token_usage=patch.token_usage,
            first_user_message=patch.first_user_message,
            history=history,
        )


@dataclass(frozen=True)
class LocalThreadStoreConfig:
    codex_home: Path | None = None
    sqlite_home: Path | None = None
    default_model_provider_id: str = "test"

    @classmethod
    def from_config(cls, config: Any) -> "LocalThreadStoreConfig":
        codex_home = getattr(config, "codex_home", None)
        return cls(
            codex_home=codex_home,
            sqlite_home=getattr(config, "sqlite_home", codex_home),
            default_model_provider_id=str(getattr(config, "default_model_provider_id", "test")),
        )


class LocalThreadStore(InMemoryThreadStore):
    def __init__(self, config: LocalThreadStoreConfig | None = None, state_db: Any | None = None) -> None:
        super().__init__()
        self.config = config or LocalThreadStoreConfig()
        self._state_db = state_db
        self._live_recorders: dict[ThreadId, RolloutRecorder] = {}

    async def create_thread(self, params: CreateThreadParams) -> None:
        self._ensure_live_recorder_absent(params.thread_id)
        recorder = self._new_create_recorder(params)
        self._live_recorders[params.thread_id] = recorder
        await super().create_thread(params)

    async def resume_thread(self, params: ResumeThreadParams) -> None:
        self._ensure_live_recorder_absent(params.thread_id)
        if params.metadata.cwd is None:
            raise ThreadStoreError.invalid_request("local thread store requires a cwd")
        rollout_path = params.rollout_path
        if rollout_path is None:
            rollout_path = self._rollout_path_for_thread(params.thread_id)
        if rollout_path is None:
            raise ThreadStoreError.internal(f"thread {params.thread_id} does not have a rollout path")
        self._live_recorders[params.thread_id] = RolloutRecorder.new(
            self._rollout_config(params.metadata),
            RolloutRecorderParams.resume(rollout_path),
        )
        await super().resume_thread(params)

    async def append_items(self, params: AppendThreadItemsParams) -> None:
        recorder = self._live_recorder(params.thread_id)
        recorder.record_canonical_items(params.items)
        recorder.flush()
        await super().append_items(params)

    async def persist_thread(self, thread_id: ThreadId) -> None:
        self._live_recorder(thread_id).persist()
        await super().persist_thread(thread_id)

    async def flush_thread(self, thread_id: ThreadId) -> None:
        self._live_recorder(thread_id).flush()
        await super().flush_thread(thread_id)

    async def shutdown_thread(self, thread_id: ThreadId) -> None:
        recorder = self._live_recorder(thread_id)
        recorder.shutdown()
        self._live_recorders.pop(thread_id, None)
        await super().shutdown_thread(thread_id)

    async def discard_thread(self, thread_id: ThreadId) -> None:
        self._live_recorder(thread_id)
        self._live_recorders.pop(thread_id, None)
        await super().discard_thread(thread_id)

    async def live_rollout_path(self, thread_id: ThreadId) -> Path:
        return self._live_recorder(thread_id).rollout_path

    async def load_history(self, params: LoadThreadHistoryParams) -> StoredThreadHistory:
        if params.thread_id in self._histories:
            return await super().load_history(params)
        rollout_path = self._resolve_local_rollout_path(params.thread_id, params.include_archived)
        if rollout_path is None:
            raise ThreadStoreError.invalid_request(f"no rollout found for thread id {params.thread_id}")
        return _load_history_from_rollout_path(params.thread_id, rollout_path)

    async def read_thread(self, params: ReadThreadParams) -> StoredThread:
        if params.thread_id in self._created_threads:
            return await super().read_thread(params)
        metadata = await _read_state_thread_metadata(self, params.thread_id)
        if metadata is not None and _state_metadata_can_satisfy_read(self, metadata, params):
            thread = _stored_thread_from_state_metadata(self, metadata)
            if not params.include_history:
                rollout_path = getattr(metadata, "rollout_path", None)
                if rollout_path is not None:
                    try:
                        rollout_thread = _read_thread_from_rollout_path(
                            self,
                            Path(rollout_path),
                            include_archived=params.include_archived,
                            include_history=False,
                        )
                    except Exception:
                        rollout_thread = None
                    if (
                        rollout_thread is not None
                        and str(rollout_thread.thread_id) == str(params.thread_id)
                        and (params.include_archived or rollout_thread.archived_at is None)
                        and rollout_thread.preview
                    ):
                        thread = replace(
                            rollout_thread,
                            name=thread.name if thread.name is not None else rollout_thread.name,
                            git_info=thread.git_info,
                        )
            if params.include_history:
                thread = replace(thread, history=_load_history_from_rollout_path(params.thread_id, thread.rollout_path))
            return thread
        rollout_path = self._resolve_local_rollout_path(params.thread_id, params.include_archived)
        if rollout_path is None:
            raise ThreadStoreError.invalid_request(f"no rollout found for thread id {params.thread_id}")
        thread = _read_thread_from_rollout_path(
            self,
            rollout_path,
            include_archived=params.include_archived,
            include_history=params.include_history,
        )
        if str(thread.thread_id) != str(params.thread_id):
            raise ThreadStoreError.invalid_request(f"no rollout found for thread id {params.thread_id}")
        return thread

    async def read_thread_by_rollout_path(self, params: ReadThreadByRolloutPathParams) -> StoredThread:
        path = params.rollout_path
        if not path.is_absolute():
            path = (self.config.codex_home or Path()).joinpath(path)
        try:
            path = path.resolve(strict=True)
        except OSError as exc:
            raise ThreadStoreError.invalid_request(f"failed to resolve rollout path `{path}`: {exc}") from exc
        thread = _read_thread_from_rollout_path(
            self,
            path,
            include_archived=params.include_archived,
            include_history=params.include_history,
        )
        metadata = await _read_state_thread_metadata(self, thread.thread_id)
        if metadata is not None:
            thread = replace(thread, git_info=_merge_state_git_info(metadata, thread.git_info))
        return thread

    async def list_threads(self, params: ListThreadsParams) -> ThreadPage:
        if params.cursor is not None and parse_cursor(params.cursor) is None:
            raise ThreadStoreError.invalid_request(f"invalid cursor: {params.cursor}")
        try:
            page = _list_local_rollout_threads(self, params)
        except Exception as exc:
            raise ThreadStoreError.internal(f"failed to list threads: {exc}") from exc
        items = tuple(
            thread
            for item in page.items
            if (thread := _stored_thread_from_rollout_item(self, item, archived=params.archived)) is not None
        )
        items = await _apply_list_thread_names(self, items)
        next_cursor = page.next_cursor.to_json() if getattr(page, "next_cursor", None) is not None else None
        return ThreadPage(items=items, next_cursor=next_cursor)

    async def search_threads(self, params: SearchThreadsParams) -> ThreadSearchPage:
        if params.search_term == "":
            raise ThreadStoreError.invalid_request("thread/search requires search_term")
        if params.cursor is not None and parse_cursor(params.cursor) is None:
            raise ThreadStoreError.invalid_request(f"invalid cursor: {params.cursor}")
        try:
            return await _search_local_rollout_threads(self, params)
        except ThreadStoreError:
            raise
        except Exception as exc:
            raise ThreadStoreError.internal(f"failed to search rollout contents: {exc}") from exc

    async def update_thread_metadata(self, params: UpdateThreadMetadataParams) -> StoredThread:
        if params.patch.is_empty():
            return await self.read_thread(
                ReadThreadParams(
                    thread_id=params.thread_id,
                    include_archived=params.include_archived,
                    include_history=False,
                  )
              )
        observed_metadata_update = _patch_has_observed_metadata_facts(params.patch)
        if params.thread_id in self._created_threads:
            stored: StoredThread | None = await super().update_thread_metadata(params)
        else:
            existing_patch = self._metadata_updates.get(params.thread_id, ThreadMetadataPatch())
            self._metadata_updates[params.thread_id] = existing_patch.merge(params.patch)
            stored = None
        if (
            params.thread_id in self._live_recorders
            and (params.patch.name is not None or params.patch.memory_mode is not None or params.patch.git_info is not None)
        ):
            await self.persist_thread(params.thread_id)
        rollout_path = self._resolve_local_rollout_path(params.thread_id, params.include_archived)
        observed_metadata = None
        if observed_metadata_update:
            try:
                observed_metadata = await _apply_observed_metadata_update(
                    self,
                    params.thread_id,
                    params.patch,
                    include_archived=params.include_archived,
                    rollout_path=rollout_path,
                )
            except Exception as exc:
                _handle_sqlite_write_exception(params.patch, exc)
                observed_metadata = None
            if rollout_path is None:
                rollout_path = Path(getattr(observed_metadata, "rollout_path")) if observed_metadata is not None else None
        if params.patch.memory_mode is not None:
            if rollout_path is None:
                raise ThreadStoreError.internal(f"thread metadata unavailable before memory mode update: {params.thread_id}")
            _append_thread_memory_mode_to_rollout(rollout_path, params.thread_id, params.patch.memory_mode)
        if params.patch.name is not None:
            name = _clearable_to_optional_value(params.patch.name)
            append_thread_name(self.config.codex_home or Path(), params.thread_id, "" if name is None else name)
            try:
                await _apply_thread_name_update(self, params.thread_id, "" if name is None else name)
            except Exception as exc:
                _handle_sqlite_write_exception(params.patch, exc)
        if rollout_path is not None and params.thread_id not in self._created_threads:
            stored = _read_thread_from_rollout_path(
                self,
                rollout_path,
                include_archived=params.include_archived,
                include_history=False,
            )
        if params.patch.git_info is not None:
            if rollout_path is None:
                raise ThreadStoreError.internal(f"thread metadata unavailable before git update: {params.thread_id}")
            git_info = await _apply_thread_git_info_update(self, params.thread_id, rollout_path, params.patch.git_info)
            if stored is None:
                stored = _read_thread_from_rollout_path(
                    self,
                    rollout_path,
                    include_archived=params.include_archived,
                    include_history=False,
                )
            stored = replace(stored, git_info=git_info)
        if observed_metadata is not None and rollout_path is not None:
            try:
                rollout_thread = _read_thread_from_rollout_path(
                    self,
                    rollout_path,
                    include_archived=params.include_archived,
                    include_history=False,
                )
                stored = replace(
                    rollout_thread,
                    name=_distinct_state_metadata_title(observed_metadata) or rollout_thread.name,
                    git_info=_git_info_from_state_metadata(observed_metadata) or rollout_thread.git_info,
                )
            except Exception:
                stored = _stored_thread_from_state_metadata(self, observed_metadata)
        if stored is None:
            raise ThreadStoreError.invalid_request(f"thread not found: {params.thread_id}")
        return stored

    async def archive_thread(self, params: ArchiveThreadParams) -> None:
        thread_id = params.thread_id
        codex_home = self.config.codex_home or Path()
        try:
            rollout_path = find_thread_path_by_id_str(codex_home, str(thread_id), self._state_db)
        except Exception as exc:
            raise ThreadStoreError.invalid_request(f"failed to locate thread id {thread_id}: {exc}") from exc
        if rollout_path is None:
            raise ThreadStoreError.invalid_request(f"no rollout found for thread id {thread_id}")
        canonical_rollout_path = _scoped_rollout_path(codex_home / "sessions", Path(rollout_path), "sessions")
        file_name = _matching_rollout_file_name(canonical_rollout_path, thread_id, Path(rollout_path))
        archive_folder = codex_home / ARCHIVED_SESSIONS_SUBDIR
        try:
            archive_folder.mkdir(parents=True, exist_ok=True)
            archived_path = archive_folder / file_name
            canonical_rollout_path.replace(archived_path)
        except OSError as exc:
            raise ThreadStoreError.internal(f"failed to archive thread: {exc}") from exc
        marker = getattr(self._state_db, "mark_archived", None)
        if callable(marker):
            await _maybe_await(marker(thread_id, archived_path, datetime.now(timezone.utc)))

    async def unarchive_thread(self, params: ArchiveThreadParams) -> StoredThread:
        thread_id = params.thread_id
        codex_home = self.config.codex_home or Path()
        try:
            archived_path = find_archived_thread_path_by_id_str(codex_home, str(thread_id), self._state_db)
        except Exception as exc:
            raise ThreadStoreError.invalid_request(f"failed to locate archived thread id {thread_id}: {exc}") from exc
        if archived_path is None:
            raise ThreadStoreError.invalid_request(f"no archived rollout found for thread id {thread_id}")
        canonical_archived_path = _scoped_rollout_path(
            codex_home / ARCHIVED_SESSIONS_SUBDIR,
            Path(archived_path),
            "archived",
        )
        file_name = _matching_rollout_file_name(canonical_archived_path, thread_id, Path(archived_path))
        date_parts = rollout_date_parts(file_name)
        if date_parts is None:
            raise ThreadStoreError.invalid_request(f"rollout path `{archived_path}` missing filename timestamp")
        year, month, day = date_parts
        dest_dir = codex_home / "sessions" / year / month / day
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            restored_path = dest_dir / file_name
            canonical_archived_path.replace(restored_path)
            _touch_modified_time(restored_path)
        except OSError as exc:
            raise ThreadStoreError.internal(f"failed to unarchive thread: {exc}") from exc
        marker = getattr(self._state_db, "mark_unarchived", None)
        if callable(marker):
            await _maybe_await(marker(thread_id, restored_path))
        item = read_thread_item_from_rollout(restored_path)
        if item is None:
            raise ThreadStoreError.internal(f"failed to read unarchived thread {restored_path}")
        thread = _stored_thread_from_rollout_item(self, item, archived=False)
        if thread is None:
            raise ThreadStoreError.internal(f"failed to read unarchived thread id from {restored_path}")
        return thread

    def _ensure_live_recorder_absent(self, thread_id: ThreadId) -> None:
        if thread_id in self._live_recorders:
            raise ThreadStoreError.invalid_request(f"thread {thread_id} already has a live local writer")

    def _live_recorder(self, thread_id: ThreadId) -> RolloutRecorder:
        recorder = self._live_recorders.get(thread_id)
        if recorder is None:
            raise ThreadStoreError.thread_not_found(thread_id)
        return recorder

    def _new_create_recorder(self, params: CreateThreadParams) -> RolloutRecorder:
        if params.metadata.cwd is None:
            raise ThreadStoreError.invalid_request("local thread store requires a cwd")
        return RolloutRecorder.new(
            self._rollout_config(params.metadata),
            RolloutRecorderParams.new(
                params.thread_id,
                params.forked_from_id,
                params.source,
                params.thread_source,
                params.base_instructions,
                params.dynamic_tools,
            ),
        )

    def _rollout_config(self, metadata: ThreadPersistenceMetadata) -> Any:
        return _LocalRolloutConfig(
            codex_home=self.config.codex_home or Path(),
            sqlite_home=self.config.sqlite_home or self.config.codex_home or Path(),
            cwd=metadata.cwd or Path(),
            model_provider_id=metadata.model_provider,
        )

    def _rollout_path_for_thread(self, thread_id: ThreadId) -> Path | None:
        for path, mapped_thread_id in self._rollout_paths.items():
            if mapped_thread_id == thread_id:
                return path
        return None

    def _resolve_local_rollout_path(self, thread_id: ThreadId, include_archived: bool = False) -> Path | None:
        recorder = self._live_recorders.get(thread_id)
        if recorder is not None:
            path = recorder.rollout_path
            if path.exists():
                return path
        path = self._rollout_path_for_thread(thread_id)
        if path is not None and path.exists():
            return path
        codex_home = self.config.codex_home
        if codex_home is None:
            return None
        path = find_thread_path_by_id_str(codex_home, str(thread_id), self._state_db)
        if path is not None:
            return path
        if include_archived:
            return find_archived_thread_path_by_id_str(codex_home, str(thread_id))
        return None


@dataclass(frozen=True)
class _LocalRolloutConfig:
    codex_home: Path
    sqlite_home: Path
    cwd: Path
    model_provider_id: str


class LiveThread:
    """Storage-neutral live thread lifecycle handle from Rust ``live_thread.rs``."""

    def __init__(
        self,
        *,
        thread_id: ThreadId,
        thread_store: ThreadStore,
        event_persistence_mode: EventPersistenceMode,
        metadata_sync: ThreadMetadataSync,
    ) -> None:
        self.thread_id = thread_id
        self.thread_store = thread_store
        self.event_persistence_mode = event_persistence_mode
        self.metadata_sync = metadata_sync

    @classmethod
    async def create(cls, thread_store: ThreadStore, params: CreateThreadParams) -> "LiveThread":
        thread_id = params.thread_id
        event_mode = _event_persistence_mode(params.event_persistence_mode)
        metadata_sync = await ThreadMetadataSync.for_create(params)
        await thread_store.create_thread(params)
        return cls(
            thread_id=thread_id,
            thread_store=thread_store,
            event_persistence_mode=event_mode,
            metadata_sync=metadata_sync,
        )

    @classmethod
    async def resume(cls, thread_store: ThreadStore, params: ResumeThreadParams) -> "LiveThread":
        thread_id = params.thread_id
        event_mode = _event_persistence_mode(params.event_persistence_mode)
        should_load_history = params.history is None
        include_archived = params.include_archived
        await thread_store.resume_thread(params)
        if should_load_history:
            try:
                history = await thread_store.load_history(
                    LoadThreadHistoryParams(thread_id=thread_id, include_archived=include_archived)
                )
            except Exception:
                await thread_store.discard_thread(thread_id)
                raise
            params = replace(params, history=history.items)
        metadata_sync = ThreadMetadataSync.for_resume(params)
        return cls(
            thread_id=thread_id,
            thread_store=thread_store,
            event_persistence_mode=event_mode,
            metadata_sync=metadata_sync,
        )

    async def append_items(self, items: tuple[Any, ...] | list[Any]) -> None:
        canonical_items = persisted_rollout_items(items, self.event_persistence_mode)
        if not canonical_items:
            return
        await self.thread_store.append_items(
            AppendThreadItemsParams(thread_id=self.thread_id, items=tuple(canonical_items))
        )
        update = self.metadata_sync.observe_appended_items(canonical_items)
        if update is not None:
            await self.thread_store.update_thread_metadata(
                UpdateThreadMetadataParams(
                    thread_id=self.thread_id,
                    patch=update.patch,
                    include_archived=True,
                )
            )
            self.metadata_sync.mark_pending_update_applied(update)

    async def persist(self) -> None:
        await self.thread_store.persist_thread(self.thread_id)
        await self._flush_pending_metadata_update()

    async def flush(self) -> None:
        await self.thread_store.flush_thread(self.thread_id)
        await self._flush_pending_metadata_update_for_existing_history()

    async def shutdown(self) -> None:
        await self._flush_pending_metadata_update_for_existing_history()
        await self.thread_store.shutdown_thread(self.thread_id)

    async def discard(self) -> None:
        await self.thread_store.discard_thread(self.thread_id)

    async def load_history(self, include_archived: bool) -> StoredThreadHistory:
        return await self.thread_store.load_history(
            LoadThreadHistoryParams(thread_id=self.thread_id, include_archived=include_archived)
        )

    async def read_thread(self, include_archived: bool, include_history: bool) -> StoredThread:
        return await self.thread_store.read_thread(
            ReadThreadParams(
                thread_id=self.thread_id,
                include_archived=include_archived,
                include_history=include_history,
            )
        )

    async def update_memory_mode(self, mode: ThreadMemoryMode, include_archived: bool) -> None:
        await self._flush_pending_metadata_update()
        await self.thread_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=self.thread_id,
                patch=ThreadMetadataPatch(memory_mode=mode),
                include_archived=include_archived,
            )
        )

    async def update_metadata(self, patch: ThreadMetadataPatch, include_archived: bool) -> StoredThread:
        await self._flush_pending_metadata_update()
        return await self.thread_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=self.thread_id,
                patch=patch,
                include_archived=include_archived,
            )
        )

    async def local_rollout_path(self) -> Path | None:
        method = getattr(self.thread_store, "live_rollout_path", None)
        if callable(method):
            return await method(self.thread_id)
        return None

    async def _flush_pending_metadata_update(self) -> None:
        await self._apply_pending_metadata_update(self.metadata_sync.take_pending_update())

    async def _flush_pending_metadata_update_for_existing_history(self) -> None:
        await self._apply_pending_metadata_update(self.metadata_sync.take_pending_update_for_existing_history())

    async def _apply_pending_metadata_update(self, update: PendingThreadMetadataPatch | None) -> None:
        if update is None:
            return
        await self.thread_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=self.thread_id,
                patch=update.patch,
                include_archived=True,
            )
        )
        self.metadata_sync.mark_pending_update_applied(update)


class LiveThreadInitGuard:
    def __init__(self, live_thread: LiveThread | None) -> None:
        self.live_thread = live_thread

    @classmethod
    def new(cls, live_thread: LiveThread | None) -> "LiveThreadInitGuard":
        return cls(live_thread)

    def as_ref(self) -> LiveThread | None:
        return self.live_thread

    def commit(self) -> None:
        self.live_thread = None

    async def discard(self) -> None:
        live_thread = self.live_thread
        self.live_thread = None
        if live_thread is not None:
            await live_thread.discard()


__all__ = [
    "AppendThreadItemsParams",
    "ArchiveThreadParams",
    "ClearableField",
    "CreateThreadParams",
    "GitInfoPatch",
    "IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER",
    "InMemoryThreadStore",
    "InMemoryThreadStoreCalls",
    "ItemPage",
    "ListItemsParams",
    "ListThreadsParams",
    "ListTurnsParams",
    "LiveThread",
    "LiveThreadInitGuard",
    "LoadThreadHistoryParams",
    "LocalThreadStore",
    "LocalThreadStoreConfig",
    "ReadThreadByRolloutPathParams",
    "ReadThreadParams",
    "ResumeThreadParams",
    "SearchThreadsParams",
    "SortDirection",
    "StoredThread",
    "StoredThreadHistory",
    "StoredThreadSearchResult",
    "StoredTurn",
    "StoredTurnError",
    "StoredTurnItemsView",
    "StoredTurnStatus",
    "ThreadEventPersistenceMode",
    "ThreadMetadataPatch",
    "ThreadMetadataSync",
    "ThreadPage",
    "ThreadPersistenceMetadata",
    "ThreadSearchPage",
    "ThreadSortKey",
    "ThreadStore",
    "ThreadStoreError",
    "ThreadStoreResult",
    "PendingThreadMetadataPatch",
    "THREAD_UPDATED_AT_TOUCH_INTERVAL_SECONDS",
    "TurnPage",
    "UpdateThreadMetadataParams",
    "clear_field",
    "parse_memory_mode",
    "parse_session_timestamp",
    "rollout_item_affects_thread_metadata",
    "strip_user_message_prefix",
    "thread_updated_at_touch",
    "update_has_metadata_facts",
    "user_message_preview",
    "is_clear_field",
]


def parse_memory_mode(value: Any) -> ThreadMemoryMode | None:
    if isinstance(value, ThreadMemoryMode):
        return value
    if value == "enabled":
        return ThreadMemoryMode.ENABLED
    if value == "disabled":
        return ThreadMemoryMode.DISABLED
    return None


def parse_session_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def strip_user_message_prefix(text: str) -> str:
    index = text.find(USER_MESSAGE_BEGIN)
    if index >= 0:
        return text[index + len(USER_MESSAGE_BEGIN) :].strip()
    return text.strip()


def user_message_preview(user: UserMessageEvent) -> str | None:
    message = strip_user_message_prefix(user.message)
    if message:
        return message
    if user.images or user.local_images:
        return IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER
    return None


def thread_updated_at_touch() -> ThreadMetadataPatch:
    return ThreadMetadataPatch(updated_at=datetime.now(timezone.utc))


def update_has_metadata_facts(update: ThreadMetadataPatch) -> bool:
    return any(
        value is not None
        for key, value in update.__dict__.items()
        if key != "updated_at"
    )


def git_info_patch_from_observation(git_info: Any) -> GitInfoPatch:
    commit_hash = getattr(git_info, "commit_hash", None)
    sha = getattr(commit_hash, "value", commit_hash)
    return GitInfoPatch(
        sha=str(sha) if sha is not None else None,
        branch=getattr(git_info, "branch", None),
        origin_url=getattr(git_info, "repository_url", None),
    )


def rollout_item_affects_thread_metadata(item: Any) -> bool:
    rollout_item = _rollout_item(item)
    if rollout_item.type in {"session_meta", "turn_context"}:
        return True
    if rollout_item.type != "event_msg":
        return False
    event = _event_msg(rollout_item.payload)
    if event.type == "token_count":
        return getattr(event.payload, "info", None) is not None
    return event.type in {"user_message", "thread_goal_updated"}


def _rollout_item(item: Any) -> RolloutItem:
    if isinstance(item, RolloutItem):
        return item
    if isinstance(item, Mapping):
        return RolloutItem.from_mapping(item)
    item_type = getattr(item, "type", None)
    payload = getattr(item, "payload", None)
    if isinstance(item_type, str):
        return RolloutItem(item_type, payload)
    raise TypeError("metadata sync expects RolloutItem-compatible values")


def _event_msg(event: Any) -> EventMsg:
    if isinstance(event, EventMsg):
        return event
    if isinstance(event, Mapping):
        return EventMsg.from_mapping(event)
    event_type = getattr(event, "type", None)
    if isinstance(event_type, str):
        return EventMsg.with_payload(event_type, getattr(event, "payload", None))
    raise TypeError("metadata sync expects EventMsg-compatible values")


def _session_meta_line(value: Any) -> SessionMetaLine | None:
    if isinstance(value, SessionMetaLine):
        return value
    if isinstance(value, Mapping):
        return SessionMetaLine.from_mapping(value)
    meta = getattr(value, "meta", None)
    if meta is not None:
        return SessionMetaLine(meta=meta, git=getattr(value, "git", None))
    return None


def _source_call_or_none(source: Any, name: str) -> Any:
    method = getattr(source, name, None)
    if callable(method):
        return method()
    return None


def _event_persistence_mode(mode: ThreadEventPersistenceMode) -> EventPersistenceMode:
    if mode == ThreadEventPersistenceMode.EXTENDED:
        return EventPersistenceMode.EXTENDED
    return EventPersistenceMode.LIMITED


def _append_thread_memory_mode_to_rollout(
    rollout_path: Path,
    thread_id: ThreadId,
    memory_mode: ThreadMemoryMode,
) -> None:
    session_meta = read_session_meta_line(rollout_path)
    if str(session_meta.meta.id) != str(thread_id):
        raise ThreadStoreError.internal(
            "failed to set thread memory mode: "
            f"rollout session metadata id mismatch: expected {thread_id}, found {session_meta.meta.id}"
        )
    meta = replace(session_meta.meta, memory_mode=_enum_or_value(memory_mode))
    append_rollout_item_to_path(rollout_path, RolloutItem.session_meta(SessionMetaLine(meta=meta, git=None)))


def _patch_has_observed_metadata_facts(patch: ThreadMetadataPatch) -> bool:
    return any(
        value is not None
        for value in (
            patch.rollout_path,
            patch.preview,
            patch.title,
            patch.model_provider,
            patch.model,
            patch.reasoning_effort,
            patch.created_at,
            patch.updated_at,
            patch.source,
            patch.thread_source,
            patch.agent_nickname,
            patch.agent_role,
            patch.agent_path,
            patch.cwd,
            patch.cli_version,
            patch.approval_mode,
            patch.sandbox_policy,
            patch.token_usage,
            patch.first_user_message,
        )
    )


def _sqlite_write_failure_should_block(patch: ThreadMetadataPatch) -> bool:
    return patch.git_info is not None and not _patch_has_observed_metadata_facts(patch)


def _sqlite_write_error_is_best_effort(exc: BaseException) -> bool:
    return not isinstance(exc, ThreadStoreError) or exc.kind == "internal"


def _handle_sqlite_write_exception(patch: ThreadMetadataPatch, exc: BaseException) -> None:
    if _sqlite_write_failure_should_block(patch) or not _sqlite_write_error_is_best_effort(exc):
        if isinstance(exc, ThreadStoreError):
            raise exc
        raise ThreadStoreError.internal(f"failed to update thread metadata: {exc}") from exc


async def _apply_observed_metadata_update(
    store: LocalThreadStore,
    thread_id: ThreadId,
    patch: ThreadMetadataPatch,
    *,
    include_archived: bool,
    rollout_path: Path | None,
) -> Any:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        return None
    existing = await _read_state_thread_metadata(store, thread_id)
    if existing is None:
        if rollout_path is None:
            rollout_path = store._resolve_local_rollout_path(thread_id, include_archived)
        if rollout_path is None:
            raise ThreadStoreError.invalid_request(f"thread not found: {thread_id}")
        metadata = _state_metadata_from_rollout(store, thread_id, rollout_path)
    else:
        metadata = existing
        if rollout_path is not None:
            setattr(metadata, "rollout_path", rollout_path)
    if patch.rollout_path is not None:
        setattr(metadata, "rollout_path", patch.rollout_path)
    if patch.preview is not None:
        setattr(metadata, "preview", patch.preview)
    if patch.name is not None:
        setattr(metadata, "title", _clearable_to_optional_value(patch.name) or "")
    if patch.title is not None:
        setattr(metadata, "title", patch.title)
    if patch.model_provider is not None:
        setattr(metadata, "model_provider", patch.model_provider)
    if patch.model is not None:
        setattr(metadata, "model", patch.model)
    if patch.reasoning_effort is not None:
        setattr(metadata, "reasoning_effort", patch.reasoning_effort)
    if patch.created_at is not None:
        setattr(metadata, "created_at", patch.created_at)
    if patch.updated_at is not None:
        setattr(metadata, "updated_at", patch.updated_at)
    if patch.source is not None:
        setattr(metadata, "source", _metadata_enum_string(patch.source))
    if patch.thread_source is not None:
        setattr(metadata, "thread_source", _clearable_to_optional_value(patch.thread_source))
    if patch.agent_nickname is not None:
        setattr(metadata, "agent_nickname", _clearable_to_optional_value(patch.agent_nickname))
    if patch.agent_role is not None:
        setattr(metadata, "agent_role", _clearable_to_optional_value(patch.agent_role))
    if patch.agent_path is not None:
        setattr(metadata, "agent_path", _clearable_to_optional_value(patch.agent_path))
    if patch.cwd is not None:
        setattr(metadata, "cwd", _normalize_cwd(patch.cwd))
    if patch.cli_version is not None:
        setattr(metadata, "cli_version", patch.cli_version)
    if patch.approval_mode is not None:
        setattr(metadata, "approval_mode", _enum_or_value(patch.approval_mode))
    if patch.sandbox_policy is not None:
        setattr(metadata, "sandbox_policy", _metadata_enum_string(patch.sandbox_policy))
    if patch.token_usage is not None:
        total_tokens = getattr(patch.token_usage, "total_tokens", None)
        if total_tokens is not None:
            setattr(metadata, "tokens_used", max(0, int(total_tokens)))
    if patch.first_user_message is not None:
        setattr(metadata, "first_user_message", patch.first_user_message)
    archived = _rollout_path_is_archived(store.config.codex_home or Path(), Path(getattr(metadata, "rollout_path")))
    if archived and getattr(metadata, "archived_at", None) is None:
        setattr(metadata, "archived_at", getattr(metadata, "updated_at", datetime.now(timezone.utc)))
    upserter = getattr(state_db, "upsert_thread", None)
    if callable(upserter):
        await _maybe_await(upserter(metadata))
    return metadata


async def _apply_thread_name_update(store: LocalThreadStore, thread_id: ThreadId, name: str) -> None:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        return
    updater = getattr(state_db, "update_thread_title", None)
    if callable(updater):
        updated = await _maybe_await(updater(thread_id, name))
        if updated is False:
            metadata = await _read_state_thread_metadata(store, thread_id)
            if metadata is None:
                return
            setattr(metadata, "title", name)
            upserter = getattr(state_db, "upsert_thread", None)
            if callable(upserter):
                await _maybe_await(upserter(metadata))
        return
    metadata = await _read_state_thread_metadata(store, thread_id)
    if metadata is None:
        return
    setattr(metadata, "title", name)
    upserter = getattr(state_db, "upsert_thread", None)
    if callable(upserter):
        await _maybe_await(upserter(metadata))


def _state_metadata_from_rollout(store: LocalThreadStore, thread_id: ThreadId, rollout_path: Path) -> Any:
    from pycodex.state.model.thread_metadata import ThreadMetadataBuilder

    meta = read_session_meta_line(rollout_path).meta
    created_at = parse_session_timestamp(meta.timestamp) or datetime.now(timezone.utc)
    builder = ThreadMetadataBuilder.new(
        thread_id,
        rollout_path,
        created_at,
        SessionSource.from_startup_arg(meta.source),
    )
    builder.model_provider = meta.model_provider
    builder.thread_source = meta.thread_source
    builder.agent_nickname = meta.agent_nickname
    builder.agent_role = meta.agent_role
    builder.agent_path = meta.agent_path
    builder.cwd = Path(meta.cwd)
    builder.cli_version = meta.cli_version
    metadata = builder.build(store.config.default_model_provider_id)
    if _rollout_path_is_archived(store.config.codex_home or Path(), rollout_path):
        metadata.archived_at = metadata.updated_at
    return metadata


def _normalize_cwd(cwd: Path) -> Path:
    try:
        return Path(cwd).resolve(strict=False)
    except OSError:
        return Path(cwd)


async def _apply_thread_git_info_update(
    store: LocalThreadStore,
    thread_id: ThreadId,
    rollout_path: Path,
    patch: GitInfoPatch,
) -> GitInfoPatch:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        raise ThreadStoreError.internal(f"sqlite state db unavailable for thread {thread_id}")
    metadata = await _read_state_thread_metadata(store, thread_id)
    if metadata is None:
        metadata = _state_metadata_from_rollout(store, thread_id, rollout_path)
        upserter = getattr(state_db, "upsert_thread", None)
        if not callable(upserter):
            raise ThreadStoreError.internal(f"sqlite state db unavailable for thread {thread_id}")
        try:
            await _maybe_await(upserter(metadata))
        except Exception as exc:
            raise ThreadStoreError.internal(f"failed to update thread metadata for {thread_id}: {exc}") from exc
    memory_mode = None
    getter = getattr(state_db, "get_thread_memory_mode", None)
    if callable(getter):
        memory_mode = await _maybe_await(getter(thread_id))
    existing_git_info = _git_info_from_state_metadata(metadata)
    sha, branch, origin_url = _resolve_git_info_patch(existing_git_info, patch)
    _append_thread_git_info_to_rollout(
        rollout_path,
        thread_id,
        sha=sha,
        branch=branch,
        origin_url=origin_url,
        memory_mode=memory_mode,
    )
    updater = getattr(state_db, "update_thread_git_info", None)
    if not callable(updater):
        raise ThreadStoreError.internal(f"sqlite state db unavailable for thread {thread_id}")
    try:
        updated = await _maybe_await(updater(thread_id, sha, branch, origin_url))
    except Exception as exc:
        raise ThreadStoreError.internal(f"failed to update git metadata for thread {thread_id}: {exc}") from exc
    if updated is False:
        raise ThreadStoreError.internal(f"thread metadata disappeared before update completed: {thread_id}")
    return GitInfoPatch(sha=sha, branch=branch, origin_url=origin_url)


def _resolve_git_info_patch(existing_git_info: Any, patch: GitInfoPatch) -> tuple[str | None, str | None, str | None]:
    return (
        _resolve_clearable_git_field(patch.sha, _git_sha(existing_git_info)),
        _resolve_clearable_git_field(patch.branch, _git_branch(existing_git_info)),
        _resolve_clearable_git_field(patch.origin_url, _git_origin_url(existing_git_info)),
    )


def _resolve_clearable_git_field(value: Any, existing: str | None) -> str | None:
    if value is None:
        return existing
    if is_clear_field(value):
        return None
    return str(value)


def _append_thread_git_info_to_rollout(
    rollout_path: Path,
    thread_id: ThreadId,
    *,
    sha: str | None,
    branch: str | None,
    origin_url: str | None,
    memory_mode: str | ThreadMemoryMode | None,
) -> None:
    session_meta = read_session_meta_line(rollout_path)
    if str(session_meta.meta.id) != str(thread_id):
        raise ThreadStoreError.internal(
            "failed to set thread git metadata: "
            f"rollout session metadata id mismatch: expected {thread_id}, found {session_meta.meta.id}"
        )
    memory_value = _enum_or_value(memory_mode) if memory_mode is not None else None
    meta = replace(session_meta.meta, memory_mode=memory_value)
    git = GitInfo(commit_hash=sha, branch=branch, repository_url=origin_url)
    append_rollout_item_to_path(rollout_path, RolloutItem.session_meta(SessionMetaLine(meta=meta, git=git)))


def _scoped_rollout_path(root: Path, rollout_path: Path, root_name: str) -> Path:
    try:
        canonical_root = Path(root).resolve(strict=True)
    except OSError as exc:
        raise ThreadStoreError.internal(f"failed to resolve {root_name} directory `{root}`: {exc}") from exc
    try:
        canonical_rollout_path = Path(rollout_path).resolve(strict=True)
    except OSError as exc:
        raise ThreadStoreError.invalid_request(f"rollout path `{rollout_path}` must be in {root_name} directory") from exc
    try:
        canonical_rollout_path.relative_to(canonical_root)
    except ValueError as exc:
        raise ThreadStoreError.invalid_request(f"rollout path `{rollout_path}` must be in {root_name} directory") from exc
    return canonical_rollout_path


def _matching_rollout_file_name(rollout_path: Path, thread_id: ThreadId, display_path: Path) -> str:
    file_name = Path(rollout_path).name
    if not file_name:
        raise ThreadStoreError.invalid_request(f"rollout path `{display_path}` missing file name")
    if not file_name.endswith(f"{thread_id}.jsonl"):
        raise ThreadStoreError.invalid_request(f"rollout path `{display_path}` does not match thread id {thread_id}")
    return file_name


def _touch_modified_time(path: Path) -> None:
    Path(path).touch(exist_ok=True)


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
        thread = _stored_thread_from_rollout_item(store, item, archived=params.archived)
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


def _rollout_sort_key(sort_key: ThreadSortKey) -> str:
    if sort_key == ThreadSortKey.UPDATED_AT:
        return "updated_at"
    return "created_at"


async def _apply_list_thread_names(store: LocalThreadStore, items: tuple[StoredThread, ...]) -> tuple[StoredThread, ...]:
    names: dict[str, str] = {}
    for thread in items:
        metadata = await _read_state_thread_metadata(store, thread.thread_id)
        if metadata is None:
            continue
        title = _distinct_state_metadata_title(metadata)
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
            updated.append(_set_thread_name_from_title(thread, title))
        else:
            updated.append(thread)
    return tuple(updated)


def _set_thread_name_from_title(thread: StoredThread, title: str) -> StoredThread:
    if not title.strip() or thread.preview.strip() == title.strip():
        return thread
    return replace(thread, name=title)


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


async def _read_state_thread_metadata(store: LocalThreadStore, thread_id: ThreadId) -> Any | None:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        return None
    getter = getattr(state_db, "get_thread", None)
    if not callable(getter):
        return None
    try:
        return await _maybe_await(getter(thread_id))
    except Exception:
        return None


def _state_metadata_can_satisfy_read(
    store: LocalThreadStore,
    metadata: Any,
    params: ReadThreadParams,
) -> bool:
    if not params.include_archived:
        if getattr(metadata, "archived_at", None) is not None:
            return False
        rollout_path = getattr(metadata, "rollout_path", None)
        if rollout_path is not None and _rollout_path_is_archived(store.config.codex_home or Path(), Path(rollout_path)):
            return False
    if not params.include_history:
        return True
    rollout_path = getattr(metadata, "rollout_path", None)
    if rollout_path is None or not Path(rollout_path).exists():
        return False
    try:
        thread = _read_thread_from_rollout_path(
            store,
            Path(rollout_path),
            include_archived=params.include_archived,
            include_history=False,
        )
    except Exception:
        return False
    return str(thread.thread_id) == str(params.thread_id)


def _stored_thread_from_state_metadata(store: LocalThreadStore, metadata: Any) -> StoredThread:
    thread_id = ThreadId.from_string(str(getattr(metadata, "id")))
    rollout_path = Path(getattr(metadata, "rollout_path"))
    first_user_message = getattr(metadata, "first_user_message", None)
    preview = getattr(metadata, "preview", None) or first_user_message or ""
    title = _distinct_state_metadata_title(metadata)
    if title is None:
        title = find_thread_name_by_id(store.config.codex_home or Path(), thread_id)
        if title is not None and not title.strip():
            title = None
    return StoredThread(
        thread_id=thread_id,
        rollout_path=rollout_path,
        forked_from_id=_state_metadata_forked_from_id(rollout_path),
        preview=preview,
        name=title,
        model_provider=getattr(metadata, "model_provider", None) or store.config.default_model_provider_id,
        model=getattr(metadata, "model", None),
        reasoning_effort=getattr(metadata, "reasoning_effort", None),
        created_at=getattr(metadata, "created_at"),
        updated_at=getattr(metadata, "updated_at"),
        archived_at=getattr(metadata, "archived_at", None),
        cwd=Path(getattr(metadata, "cwd", Path())),
        cli_version=getattr(metadata, "cli_version", "") or "",
        source=SessionSource.from_startup_arg(getattr(metadata, "source", "unknown") or "unknown"),
        thread_source=getattr(metadata, "thread_source", None),
        agent_nickname=getattr(metadata, "agent_nickname", None),
        agent_role=getattr(metadata, "agent_role", None),
        agent_path=getattr(metadata, "agent_path", None),
        git_info=_git_info_from_state_metadata(metadata),
        approval_mode=_parse_approval_or_default(getattr(metadata, "approval_mode", None)),
        sandbox_policy=_parse_sandbox_or_default(getattr(metadata, "sandbox_policy", None)),
        token_usage=None,
        first_user_message=first_user_message,
        history=None,
    )


def _distinct_state_metadata_title(metadata: Any) -> str | None:
    title = str(getattr(metadata, "title", "") or "").strip()
    first_user_message = getattr(metadata, "first_user_message", None)
    if not title or (isinstance(first_user_message, str) and first_user_message.strip() == title):
        return None
    return title


def _state_metadata_forked_from_id(rollout_path: Path) -> ThreadId | None:
    try:
        meta = read_session_meta_line(rollout_path).meta
    except Exception:
        return None
    return ThreadId.from_string(str(meta.forked_from_id)) if meta.forked_from_id else None


def _git_info_from_state_metadata(metadata: Any) -> Any:
    sha = getattr(metadata, "git_sha", None)
    branch = getattr(metadata, "git_branch", None)
    origin_url = getattr(metadata, "git_origin_url", None)
    if sha is None and branch is None and origin_url is None:
        return None
    return GitInfoPatch(sha=sha, branch=branch, origin_url=origin_url)


def _merge_state_git_info(metadata: Any, existing_git_info: Any) -> Any:
    fallback_sha = _git_sha(existing_git_info)
    fallback_branch = _git_branch(existing_git_info)
    fallback_origin_url = _git_origin_url(existing_git_info)
    sha = getattr(metadata, "git_sha", None) or fallback_sha
    branch = getattr(metadata, "git_branch", None) or fallback_branch
    origin_url = getattr(metadata, "git_origin_url", None) or fallback_origin_url
    if sha is None and branch is None and origin_url is None:
        return None
    return GitInfoPatch(sha=sha, branch=branch, origin_url=origin_url)


def _git_sha(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "sha", None) or getattr(value, "commit_hash", None)


def _git_branch(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "branch", None)


def _git_origin_url(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "origin_url", None) or getattr(value, "repository_url", None)


def _parse_approval_or_default(value: Any) -> AskForApproval:
    if isinstance(value, AskForApproval):
        return value
    if isinstance(value, str) and value:
        try:
            return AskForApproval.parse(value)
        except Exception:
            return AskForApproval.ON_REQUEST
    return AskForApproval.ON_REQUEST


def _parse_sandbox_or_default(value: Any) -> SandboxPolicy:
    if isinstance(value, SandboxPolicy):
        return value
    if isinstance(value, str):
        if value == "danger-full-access":
            return SandboxPolicy.danger_full_access()
        if value == "workspace-write":
            return SandboxPolicy.workspace_write()
        if value == "read-only":
            return SandboxPolicy.new_read_only_policy()
    if isinstance(value, Mapping):
        try:
            return SandboxPolicy.from_mapping(value)
        except Exception:
            return SandboxPolicy.new_read_only_policy()
    return SandboxPolicy.new_read_only_policy()


def _load_history_from_rollout_path(thread_id: ThreadId, rollout_path: Path) -> StoredThreadHistory:
    try:
        items, _rollout_thread_id, _parse_errors = RolloutRecorder.load_rollout_items(rollout_path)
    except OSError as exc:
        raise ThreadStoreError.internal(f"failed to load thread history {rollout_path}: {exc}") from exc
    return StoredThreadHistory(thread_id, tuple(items))


def _read_thread_from_rollout_path(
    store: LocalThreadStore,
    rollout_path: Path,
    *,
    include_archived: bool,
    include_history: bool,
) -> StoredThread:
    rollout_path = Path(rollout_path)
    archived = _rollout_path_is_archived(store.config.codex_home or Path(), rollout_path)
    if archived and not include_archived:
        meta = read_session_meta_line(rollout_path).meta
        raise ThreadStoreError.invalid_request(f"thread {meta.id} is archived")
    item = read_thread_item_from_rollout(rollout_path)
    if item is None or item.thread_id is None:
        thread = _stored_thread_from_session_meta(store, rollout_path, archived=archived)
    else:
        thread = _stored_thread_from_rollout_item(store, item, archived=archived)
        try:
            meta_line = read_session_meta_line(rollout_path)
        except ValueError:
            meta_line = None
        if meta_line is not None:
            meta = meta_line.meta
            thread = replace(
                thread,
                forked_from_id=ThreadId.from_string(str(meta.forked_from_id)) if meta.forked_from_id else None,
                model_provider=meta.model_provider or thread.model_provider,
            )
        thread_name = find_thread_name_by_id(store.config.codex_home or Path(), thread.thread_id)
        if thread_name is not None and thread_name.strip():
            thread = replace(thread, name=thread_name)
    if include_history:
        thread = replace(thread, history=_load_history_from_rollout_path(thread.thread_id, rollout_path))
    return thread


def _stored_thread_from_rollout_item(store: LocalThreadStore, item: Any, *, archived: bool) -> StoredThread:
    thread_id = ThreadId.from_string(str(item.thread_id))
    created_at = parse_session_timestamp(getattr(item, "created_at", None)) or datetime.now(timezone.utc)
    updated_at = parse_session_timestamp(getattr(item, "updated_at", None)) or created_at
    return StoredThread(
        thread_id=thread_id,
        rollout_path=Path(item.path),
        forked_from_id=None,
        preview=getattr(item, "preview", None) or getattr(item, "first_user_message", None) or "",
        name=None,
        model_provider=getattr(item, "model_provider", None) or store.config.default_model_provider_id,
        model=None,
        reasoning_effort=None,
        created_at=created_at,
        updated_at=updated_at,
        archived_at=updated_at if archived else None,
        cwd=Path(getattr(item, "cwd", None) or ""),
        cli_version=getattr(item, "cli_version", None) or "",
        source=SessionSource.from_startup_arg(getattr(item, "source", None) or "unknown"),
        thread_source=None,
        agent_nickname=getattr(item, "agent_nickname", None),
        agent_role=getattr(item, "agent_role", None),
        agent_path=None,
        git_info=_git_info_from_rollout_item(item),
        approval_mode=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.new_read_only_policy(),
        token_usage=None,
        first_user_message=getattr(item, "first_user_message", None),
        history=None,
    )


def _stored_thread_from_session_meta(store: LocalThreadStore, rollout_path: Path, *, archived: bool) -> StoredThread:
    meta_line = read_session_meta_line(rollout_path)
    meta = meta_line.meta
    thread_id = ThreadId.from_string(str(meta.id))
    created_at = parse_session_timestamp(meta.timestamp) or datetime.now(timezone.utc)
    try:
        updated_at = datetime.fromtimestamp(Path(rollout_path).stat().st_mtime, timezone.utc)
    except OSError:
        updated_at = created_at
    return StoredThread(
        thread_id=thread_id,
        rollout_path=Path(rollout_path),
        forked_from_id=ThreadId.from_string(str(meta.forked_from_id)) if meta.forked_from_id else None,
        preview="",
        name=None,
        model_provider=meta.model_provider or store.config.default_model_provider_id,
        model=None,
        reasoning_effort=None,
        created_at=created_at,
        updated_at=updated_at,
        archived_at=updated_at if archived else None,
        cwd=Path(meta.cwd),
        cli_version=meta.cli_version,
        source=SessionSource.from_startup_arg(meta.source),
        thread_source=ThreadSource.parse(meta.thread_source) if meta.thread_source else None,
        agent_nickname=meta.agent_nickname,
        agent_role=meta.agent_role,
        agent_path=meta.agent_path,
        git_info=meta_line.git,
        approval_mode=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.new_read_only_policy(),
        token_usage=None,
        first_user_message=None,
        history=None,
    )


def _git_info_from_rollout_item(item: Any) -> Any:
    sha = getattr(item, "git_sha", None)
    branch = getattr(item, "git_branch", None)
    origin_url = getattr(item, "git_origin_url", None)
    if sha is None and branch is None and origin_url is None:
        return None
    return GitInfoPatch(sha=sha, branch=branch, origin_url=origin_url)


def _rollout_path_is_archived(codex_home: Path, rollout_path: Path) -> bool:
    try:
        relative = Path(rollout_path).resolve().relative_to(Path(codex_home).resolve())
    except (OSError, ValueError):
        return False
    return relative.parts[:1] == ("archived_sessions",)


def _stored_thread_from_rollout_path(
    thread_id: ThreadId,
    rollout_path: Path,
    default_provider: str,
    *,
    patch: ThreadMetadataPatch,
) -> StoredThread:
    meta = read_session_meta_line(rollout_path).meta
    created_at = parse_session_timestamp(meta.timestamp) or datetime.now(timezone.utc)
    return StoredThread(
        thread_id=thread_id,
        rollout_path=rollout_path,
        forked_from_id=meta.forked_from_id,
        preview=patch.preview or patch.first_user_message or "",
        name=_clearable_to_optional_value(patch.name),
        model_provider=patch.model_provider or meta.model_provider or default_provider,
        model=patch.model,
        reasoning_effort=patch.reasoning_effort,
        created_at=patch.created_at or created_at,
        updated_at=patch.updated_at or created_at,
        archived_at=None,
        cwd=patch.cwd or meta.cwd,
        cli_version=patch.cli_version or meta.cli_version,
        source=patch.source or meta.source,
        thread_source=_clearable_to_optional_value(patch.thread_source, meta.thread_source),
        agent_nickname=_clearable_to_optional_value(patch.agent_nickname, meta.agent_nickname),
        agent_role=_clearable_to_optional_value(patch.agent_role, meta.agent_role),
        agent_path=_clearable_to_optional_value(patch.agent_path, meta.agent_path),
        git_info=None,
        approval_mode=patch.approval_mode or AskForApproval.ON_REQUEST,
        sandbox_policy=patch.sandbox_policy or SandboxPolicy.new_read_only_policy(),
        token_usage=patch.token_usage,
        first_user_message=patch.first_user_message,
        history=None,
    )


def _clearable_from_mapping(value: Mapping[str, Any], key: str, *, parser: Any = None) -> Any:
    if key not in value:
        return None
    raw = value[key]
    if raw is None:
        return clear_field()
    return parser(raw) if parser is not None else raw


def _put_clearable(output: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    output[key] = None if is_clear_field(value) else _enum_or_value(value)


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
