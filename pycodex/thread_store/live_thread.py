"""Rust ``codex-thread-store::live_thread`` owner."""

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

from .store import ThreadStore
from .thread_metadata_sync import ThreadMetadataSync
from .types import *


def _event_persistence_mode(mode: ThreadEventPersistenceMode) -> EventPersistenceMode:
    if mode == ThreadEventPersistenceMode.EXTENDED:
        return EventPersistenceMode.EXTENDED
    return EventPersistenceMode.LIMITED


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
