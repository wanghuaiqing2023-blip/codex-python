"""Rust-aligned owner for ``codex-rollout::policy``."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from pycodex.protocol import SessionSource
from pycodex.protocol.models import ResponseItem
from pycodex.protocol.protocol import (
    USER_MESSAGE_BEGIN,
    CompactedItem,
    EventMsg,
    InitialHistory,
    ResumedHistory,
    RolloutItem,
    ThreadId,
    ThreadRolledBackEvent,
    TurnContextItem,
)
from pycodex.utils.string import sanitize_metric_tag_value

from pycodex.protocol.protocol import GitInfo, SessionMeta, SessionMetaLine
from pycodex.state.model.backfill_state import BackfillState
from pycodex.state.model.thread_metadata import (
    Anchor,
    BackfillStats,
    ExtractionOutcome,
    ThreadMetadata,
    ThreadMetadataBuilder,
)

PERSISTED_EXEC_AGGREGATED_OUTPUT_MAX_BYTES = 10_000

class EventPersistenceMode(str, Enum):
    LIMITED = "limited"
    EXTENDED = "extended"

def is_persisted_rollout_item(item: RolloutItem | Mapping[str, Any], mode: EventPersistenceMode | str = EventPersistenceMode.LIMITED) -> bool:
    mapping = _rollout_item_mapping(item)
    item_type = mapping.get("type")
    if item_type == "response_item":
        return should_persist_response_item(mapping.get("payload"))
    if item_type == "event_msg":
        return should_persist_event_msg(mapping.get("payload"), mode)
    return item_type in {"compacted", "turn_context", "session_meta"}

def persisted_rollout_items(
    items: Iterable[RolloutItem | Mapping[str, Any]],
    mode: EventPersistenceMode | str = EventPersistenceMode.LIMITED,
) -> list[dict[str, Any]]:
    persisted: list[dict[str, Any]] = []
    for item in items:
        mapping = _rollout_item_mapping(item)
        if is_persisted_rollout_item(mapping, mode):
            persisted.append(_sanitize_rollout_item_for_persistence(mapping, mode))
    return persisted

def should_persist_response_item(item: Any) -> bool:
    if not isinstance(item, Mapping):
        return False
    return item.get("type") in {
        "message",
        "reasoning",
        "local_shell_call",
        "function_call",
        "tool_search_call",
        "function_call_output",
        "tool_search_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "web_search_call",
        "image_generation_call",
        "compaction",
        "context_compaction",
    }

def should_persist_response_item_for_memories(item: Any) -> bool:
    if not isinstance(item, Mapping):
        return False
    item_type = item.get("type")
    if item_type == "message":
        return item.get("role") != "developer"
    return item_type in {
        "local_shell_call",
        "function_call",
        "tool_search_call",
        "function_call_output",
        "tool_search_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "web_search_call",
    }

def should_persist_event_msg(event: Any, mode: EventPersistenceMode | str = EventPersistenceMode.LIMITED) -> bool:
    minimum = _event_msg_persistence_mode(event)
    if minimum is None:
        return False
    mode_value = _coerce_event_persistence_mode(mode)
    return minimum == EventPersistenceMode.LIMITED or mode_value == EventPersistenceMode.EXTENDED

def _sanitize_rollout_item_for_persistence(item: Mapping[str, Any], mode: EventPersistenceMode | str) -> dict[str, Any]:
    result = dict(item)
    if _coerce_event_persistence_mode(mode) != EventPersistenceMode.EXTENDED:
        return result
    if result.get("type") != "event_msg":
        return result
    payload = result.get("payload")
    if not isinstance(payload, Mapping) or payload.get("type") != "exec_command_end":
        return result
    sanitized_payload = dict(payload)
    aggregated = sanitized_payload.get("aggregated_output")
    if isinstance(aggregated, str):
        sanitized_payload["aggregated_output"] = _truncate_middle_chars(aggregated, PERSISTED_EXEC_AGGREGATED_OUTPUT_MAX_BYTES)
    sanitized_payload["stdout"] = ""
    sanitized_payload["stderr"] = ""
    sanitized_payload["formatted_output"] = ""
    result["payload"] = sanitized_payload
    return result

def _event_msg_persistence_mode(event: Any) -> EventPersistenceMode | None:
    if not isinstance(event, Mapping):
        return None
    event_type = event.get("type")
    if event_type in {
        "user_message",
        "agent_message",
        "agent_reasoning",
        "agent_reasoning_raw_content",
        "patch_apply_end",
        "token_count",
        "thread_goal_updated",
        "context_compacted",
        "entered_review_mode",
        "exited_review_mode",
        "mcp_tool_call_end",
        "thread_rolled_back",
        "turn_aborted",
        "turn_started",
        "turn_complete",
        "web_search_end",
        "image_generation_end",
    }:
        return EventPersistenceMode.LIMITED
    if event_type == "item_completed":
        item = event.get("item")
        return EventPersistenceMode.LIMITED if isinstance(item, Mapping) and item.get("type") == "plan" else None
    if event_type in {
        "error",
        "guardian_assessment",
        "exec_command_end",
        "view_image_tool_call",
        "collab_agent_spawn_end",
        "collab_agent_interaction_end",
        "collab_waiting_end",
        "collab_close_end",
        "collab_resume_end",
        "dynamic_tool_call_request",
        "dynamic_tool_call_response",
    }:
        return EventPersistenceMode.EXTENDED
    return None

def _rollout_item_mapping(item: RolloutItem | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(item, RolloutItem):
        return item.to_mapping()
    return dict(item)

def _coerce_event_persistence_mode(mode: EventPersistenceMode | str) -> EventPersistenceMode:
    return mode if isinstance(mode, EventPersistenceMode) else EventPersistenceMode(str(mode))

def _truncate_middle_chars(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 1:
        return value[:max_chars]
    left = max_chars // 2
    right = max_chars - left
    return value[:left] + value[-right:]



__all__ = ['EventPersistenceMode', 'PERSISTED_EXEC_AGGREGATED_OUTPUT_MAX_BYTES', 'is_persisted_rollout_item', 'persisted_rollout_items', 'should_persist_event_msg', 'should_persist_response_item', 'should_persist_response_item_for_memories']
