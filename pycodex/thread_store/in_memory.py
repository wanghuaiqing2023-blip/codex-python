"""Rust ``codex-thread-store::in_memory`` owner."""

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

from .error import ThreadStoreError
from .types import *
from .types import _clearable_to_optional_value

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
