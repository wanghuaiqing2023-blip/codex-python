"""Rust ``codex-thread-store::thread_metadata_sync`` owner."""

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

from .types import *

IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER = "[Image]"

THREAD_UPDATED_AT_TOUCH_INTERVAL_SECONDS = 0.05

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
