"""Rust ``codex-thread-store::local`` owner."""

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

from ..error import ThreadStoreError
from ..in_memory import InMemoryThreadStore
from ..thread_metadata_sync import parse_session_timestamp
from ..types import *
from ..types import (
    _clearable_to_optional_value,
    _enum_or_value,
    _metadata_enum_string,
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
        from .live_writer import create_thread

        await create_thread(self, params)

    async def resume_thread(self, params: ResumeThreadParams) -> None:
        from .live_writer import resume_thread

        await resume_thread(self, params)

    async def append_items(self, params: AppendThreadItemsParams) -> None:
        from .live_writer import append_items

        await append_items(self, params)

    async def persist_thread(self, thread_id: ThreadId) -> None:
        from .live_writer import persist_thread

        await persist_thread(self, thread_id)

    async def flush_thread(self, thread_id: ThreadId) -> None:
        from .live_writer import flush_thread

        await flush_thread(self, thread_id)

    async def shutdown_thread(self, thread_id: ThreadId) -> None:
        from .live_writer import shutdown_thread

        await shutdown_thread(self, thread_id)

    async def discard_thread(self, thread_id: ThreadId) -> None:
        from .live_writer import discard_thread

        await discard_thread(self, thread_id)

    async def live_rollout_path(self, thread_id: ThreadId) -> Path:
        from .live_writer import rollout_path

        return await rollout_path(self, thread_id)

    async def load_history(self, params: LoadThreadHistoryParams) -> StoredThreadHistory:
        from .read_thread import load_history

        return await load_history(self, params)

    async def read_thread(self, params: ReadThreadParams) -> StoredThread:
        from .read_thread import read_thread

        return await read_thread(self, params)

    async def read_thread_by_rollout_path(self, params: ReadThreadByRolloutPathParams) -> StoredThread:
        from .read_thread import read_thread_by_rollout_path

        return await read_thread_by_rollout_path(self, params)

    async def list_threads(self, params: ListThreadsParams) -> ThreadPage:
        from .list_threads import list_threads

        return await list_threads(self, params)

    async def search_threads(self, params: SearchThreadsParams) -> ThreadSearchPage:
        from .search_threads import search_threads

        return await search_threads(self, params)

    async def update_thread_metadata(self, params: UpdateThreadMetadataParams) -> StoredThread:
        from .update_thread_metadata import update_thread_metadata

        return await update_thread_metadata(self, params)

    async def archive_thread(self, params: ArchiveThreadParams) -> None:
        from .archive_thread import archive_thread

        await archive_thread(self, params)

    async def unarchive_thread(self, params: ArchiveThreadParams) -> StoredThread:
        from .unarchive_thread import unarchive_thread

        return await unarchive_thread(self, params)

    def _ensure_live_recorder_absent(self, thread_id: ThreadId) -> None:
        if thread_id in self._live_recorders:
            raise ThreadStoreError.invalid_request(f"thread {thread_id} already has a live local writer")

    def _live_recorder(self, thread_id: ThreadId) -> RolloutRecorder:
        recorder = self._live_recorders.get(thread_id)
        if recorder is None:
            raise ThreadStoreError.thread_not_found(thread_id)
        return recorder

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












































