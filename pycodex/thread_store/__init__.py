"""Port of Rust ``codex-thread-store`` public API surface.

Rust sources:
- ``codex/codex-rs/thread-store/src/lib.rs``
- ``codex/codex-rs/thread-store/src/types.rs``
- ``codex/codex-rs/thread-store/src/store.rs``
- ``codex/codex-rs/thread-store/src/error.rs``
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pycodex.protocol import AskForApproval, SandboxPolicy, SessionSource, ThreadId, ThreadMemoryMode, ThreadSource


ThreadStoreResult = Any
ClearableField = Any


class ThreadStoreError(Exception):
    kind: str

    def __init__(self, kind: str, message: str, **fields: Any) -> None:
        super().__init__(message)
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


@dataclass(frozen=True)
class UpdateThreadMetadataParams:
    thread_id: ThreadId
    patch: ThreadMetadataPatch
    include_archived: bool


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

    async def update_thread_metadata(self, params: UpdateThreadMetadataParams) -> StoredThread:
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
        self._histories.setdefault(params.thread_id, list(params.history or ()))
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
        return ThreadPage(tuple(self._stored_thread_from_state(thread_id, False) for thread_id in self._created_threads))

    async def search_threads(self, _params: SearchThreadsParams) -> ThreadSearchPage:
        raise ThreadStoreError.unsupported("thread/search")

    async def list_turns(self, _params: ListTurnsParams) -> TurnPage:
        raise ThreadStoreError.unsupported("list_turns")

    async def list_items(self, _params: ListItemsParams) -> ItemPage:
        raise ThreadStoreError.unsupported("list_items")

    async def update_thread_metadata(self, params: UpdateThreadMetadataParams) -> StoredThread:
        self._calls = replace(self._calls, update_thread_metadata=self._calls.update_thread_metadata + 1)
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
        return StoredThread(
            thread_id=thread_id,
            rollout_path=patch.rollout_path,
            forked_from_id=created.forked_from_id,
            preview=patch.preview or "",
            name=patch.name,
            model_provider=patch.model_provider or created.metadata.model_provider,
            model=patch.model,
            reasoning_effort=patch.reasoning_effort,
            created_at=patch.created_at or now,
            updated_at=patch.updated_at or now,
            archived_at=None,
            cwd=patch.cwd or created.metadata.cwd or Path.cwd(),
            cli_version=patch.cli_version or "",
            source=patch.source or created.source,
            thread_source=patch.thread_source if patch.thread_source is not None else created.thread_source,
            agent_nickname=patch.agent_nickname,
            agent_role=patch.agent_role,
            agent_path=patch.agent_path,
            git_info=None,
            approval_mode=patch.approval_mode or AskForApproval.NEVER,
            sandbox_policy=patch.sandbox_policy or SandboxPolicy.danger_full_access(),
            token_usage=patch.token_usage,
            first_user_message=patch.first_user_message,
            history=history,
        )


@dataclass(frozen=True)
class LocalThreadStoreConfig:
    codex_home: Path | None = None

    @classmethod
    def from_config(cls, config: Any) -> "LocalThreadStoreConfig":
        return cls(getattr(config, "codex_home", None))


class LocalThreadStore(InMemoryThreadStore):
    def __init__(self, config: LocalThreadStoreConfig | None = None) -> None:
        super().__init__()
        self.config = config or LocalThreadStoreConfig()


@dataclass(frozen=True)
class LiveThread:
    thread_id: ThreadId


@dataclass(frozen=True)
class LiveThreadInitGuard:
    thread_id: ThreadId


__all__ = [
    "AppendThreadItemsParams",
    "ArchiveThreadParams",
    "ClearableField",
    "CreateThreadParams",
    "GitInfoPatch",
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
    "ThreadPage",
    "ThreadPersistenceMetadata",
    "ThreadSearchPage",
    "ThreadSortKey",
    "ThreadStore",
    "ThreadStoreError",
    "ThreadStoreResult",
    "TurnPage",
    "UpdateThreadMetadataParams",
]
