"""Rust ``codex-thread-store::store`` owner."""

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

from .error import ThreadStoreError, ThreadStoreResult
from .types import *

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
