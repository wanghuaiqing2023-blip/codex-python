"""Rollout-to-thread-metadata extraction helpers ported from ``codex-state/src/extract.rs``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pycodex.protocol import EventMsg, RolloutItem, SessionMetaLine, TurnContextItem, USER_MESSAGE_BEGIN, UserMessageEvent

from .model import ThreadMetadata
from .model.thread_metadata import enum_to_string

JsonValue = Any

IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER = "[Image]"
_AFFECTING_EVENT_TYPES = {"token_count", "user_message", "thread_goal_updated"}


def apply_rollout_item(metadata: ThreadMetadata, item: RolloutItem | Mapping[str, JsonValue], default_provider: str) -> None:
    """Apply one rollout item to thread metadata.

    This mirrors Rust's in-place mutation contract and intentionally ignores
    response items and compacted records.
    """

    if not isinstance(metadata, ThreadMetadata):
        raise TypeError("metadata must be ThreadMetadata")
    item_type, payload = _rollout_parts(item)
    if item_type == "session_meta":
        _apply_session_meta_from_item(metadata, payload)
    elif item_type == "turn_context":
        _apply_turn_context(metadata, payload)
    elif item_type == "event_msg":
        _apply_event_msg(metadata, payload)
    elif item_type in {"response_item", "compacted"}:
        pass
    if metadata.model_provider == "":
        metadata.model_provider = _required_str(default_provider, "default_provider")


def rollout_item_affects_thread_metadata(item: RolloutItem | Mapping[str, JsonValue]) -> bool:
    item_type, payload = _rollout_parts(item)
    if item_type in {"session_meta", "turn_context"}:
        return True
    if item_type != "event_msg":
        return False
    event_type, _ = _event_parts(payload)
    return event_type in _AFFECTING_EVENT_TYPES


def strip_user_message_prefix(text: str) -> str:
    text = _required_str(text, "text")
    index = text.find(USER_MESSAGE_BEGIN)
    if index >= 0:
        return text[index + len(USER_MESSAGE_BEGIN) :].strip()
    return text.strip()


def user_message_preview(user: UserMessageEvent | Mapping[str, JsonValue]) -> str | None:
    message = strip_user_message_prefix(_field(user, "message", default=""))
    if message:
        return message
    images = _field(user, "images", default=None)
    local_images = _field(user, "local_images", default=())
    if images or local_images:
        return IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER
    return None


def _apply_session_meta_from_item(metadata: ThreadMetadata, meta_line: JsonValue) -> None:
    if isinstance(meta_line, SessionMetaLine):
        session_meta = meta_line.meta
        git = meta_line.git
    else:
        session_meta = _field(meta_line, "meta", default=meta_line)
        git = _field(meta_line, "git", default=None)
    session_id = _field(session_meta, "id")
    if metadata.id != session_id:
        return
    metadata.id = session_id
    metadata.source = enum_to_string(_field(session_meta, "source"))
    metadata.thread_source = _field(session_meta, "thread_source", default=None)
    metadata.agent_nickname = _field(session_meta, "agent_nickname", default=None)
    metadata.agent_role = _field(session_meta, "agent_role", default=None)
    metadata.agent_path = _field(session_meta, "agent_path", default=None)
    provider = _field(session_meta, "model_provider", default=None)
    if provider is not None:
        metadata.model_provider = _required_str(provider, "model_provider")
    cli_version = _field(session_meta, "cli_version", default="")
    if cli_version:
        metadata.cli_version = _required_str(cli_version, "cli_version")
    cwd = _field(session_meta, "cwd", default=Path())
    if not _path_is_empty(cwd):
        metadata.cwd = Path(cwd)
    if git is not None:
        commit_hash = _field(git, "commit_hash", default=None)
        metadata.git_sha = _to_optional_string(commit_hash)
        metadata.git_branch = _field(git, "branch", default=None)
        metadata.git_origin_url = _field(git, "repository_url", default=None)


def _apply_turn_context(metadata: ThreadMetadata, turn_ctx: JsonValue) -> None:
    if _path_is_empty(metadata.cwd):
        metadata.cwd = Path(_field(turn_ctx, "cwd"))
    metadata.model = _required_str(_field(turn_ctx, "model"), "model")
    metadata.reasoning_effort = _field(turn_ctx, "effort", default=None)
    metadata.sandbox_policy = enum_to_string(_field(turn_ctx, "sandbox_policy"))
    metadata.approval_mode = enum_to_string(_field(turn_ctx, "approval_policy"))


def _apply_event_msg(metadata: ThreadMetadata, event: EventMsg | Mapping[str, JsonValue]) -> None:
    event_type, payload = _event_parts(event)
    if event_type == "token_count":
        info = _field(payload, "info", default=None)
        if info is not None:
            total_usage = _field(info, "total_token_usage", default=None)
            total_tokens = _field(total_usage, "total_tokens", default=0) if total_usage is not None else 0
            metadata.tokens_used = max(int(total_tokens), 0)
        return
    if event_type == "user_message":
        preview = user_message_preview(payload)
        if metadata.first_user_message is None:
            metadata.first_user_message = preview
        _set_preview_if_empty(metadata, preview)
        if metadata.title == "":
            title = strip_user_message_prefix(_field(payload, "message", default=""))
            if title:
                metadata.title = title
        return
    if event_type == "thread_goal_updated":
        goal = _field(payload, "goal", default=None)
        objective = _field(goal, "objective", default="") if goal is not None else ""
        objective = _required_str(objective, "objective").strip()
        if objective:
            _set_preview_if_empty(metadata, objective)


def _set_preview_if_empty(metadata: ThreadMetadata, preview: str | None) -> None:
    if metadata.preview is None:
        metadata.preview = preview


def _rollout_parts(item: RolloutItem | Mapping[str, JsonValue]) -> tuple[str, JsonValue]:
    if isinstance(item, RolloutItem):
        return item.type, item.payload
    data = _mapping(item, "rollout item")
    return _required_str(data.get("type"), "type"), data.get("payload")


def _event_parts(event: EventMsg | Mapping[str, JsonValue]) -> tuple[str, JsonValue]:
    if isinstance(event, EventMsg):
        return event.type, event.payload
    data = _mapping(event, "event msg")
    event_type = _required_str(data.get("type"), "type")
    if "payload" in data:
        return event_type, data.get("payload")
    payload = dict(data)
    payload.pop("type", None)
    return event_type, payload


def _field(value: JsonValue, name: str, *, default: JsonValue = None) -> JsonValue:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _mapping(value: JsonValue, name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _to_optional_string(value: JsonValue) -> str | None:
    if value is None:
        return None
    to_json = getattr(value, "to_json", None)
    if callable(to_json):
        rendered = to_json()
        return rendered if isinstance(rendered, str) else json.dumps(rendered, separators=(",", ":"))
    return str(value)


def _path_is_empty(value: JsonValue) -> bool:
    rendered = str(value)
    return rendered == "" or rendered == "."


__all__ = [
    "IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER",
    "apply_rollout_item",
    "enum_to_string",
    "rollout_item_affects_thread_metadata",
    "strip_user_message_prefix",
    "user_message_preview",
]
