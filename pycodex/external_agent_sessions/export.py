"""Rollout export for external sessions owned by ``export.rs``."""

from __future__ import annotations

import json
from pathlib import Path

from . import ConversationMessage, ImportedExternalAgentSession, JsonValue, summarize_for_label
from .records import (
    conversation_messages, project_root_from_records, read_records,
    source_title_from_records,
)

EXTERNAL_SESSION_IMPORTED_MARKER = "<EXTERNAL SESSION IMPORTED>"

def load_session_for_import(path: str | Path) -> ImportedExternalAgentSession | None:
    records = read_records(path)
    cwd = project_root_from_records(records)
    if cwd is None:
        return None
    messages = conversation_messages(records)
    rollout_items = _rollout_items_from_messages(messages)
    if not rollout_items:
        return None
    title = source_title_from_records(records)
    if title is None:
        title = next(
            (summarize_for_label(message.text) for message in messages if message.role == "user"),
            None,
        )
    return ImportedExternalAgentSession(cwd=cwd, title=title, rollout_items=rollout_items)

def _rollout_items_from_messages(messages: list[ConversationMessage]) -> list[dict[str, JsonValue]]:
    items: list[dict[str, JsonValue]] = []
    response_items: list[dict[str, JsonValue]] = []
    current_turn: tuple[str, str | None] | None = None
    user_turn_count = 0
    for message in messages:
        if message.role == "user":
            if current_turn is not None:
                items.append(_turn_complete_item(current_turn[0], current_turn[1], None))
            user_turn_count += 1
            turn_id = f"external-import-turn-{user_turn_count}"
            items.append({"type": "event_msg", "event": {"type": "turn_started", "turn_id": turn_id, "started_at": message.timestamp}})
            response = _response_item(message)
            response_items.append(response)
            items.append({"type": "response_item", "item": response})
            items.append({"type": "event_msg", "event": {"type": "user_message", "message": message.text}})
            current_turn = (turn_id, None)
            continue
        if message.role == "assistant" and current_turn is not None:
            response = _response_item(message)
            response_items.append(response)
            items.append({"type": "response_item", "item": response})
            items.append({"type": "event_msg", "event": {"type": "agent_message", "message": message.text}})
            current_turn = (current_turn[0], message.text)
    if current_turn is not None:
        items.append(_external_session_imported_marker_item())
        items.append(_token_count_item(response_items))
        completed_at = messages[-1].timestamp if messages else None
        items.append(_turn_complete_item(current_turn[0], current_turn[1], completed_at))
    return items

def _external_session_imported_marker_item() -> dict[str, JsonValue]:
    return {"type": "event_msg", "event": {"type": "agent_message", "message": EXTERNAL_SESSION_IMPORTED_MARKER}}

def _response_item(message: ConversationMessage) -> dict[str, JsonValue]:
    content_type = "output_text" if message.role == "assistant" else "input_text"
    return {"type": "message", "id": None, "role": message.role, "content": [{"type": content_type, "text": message.text}], "phase": None}

def _token_count_item(response_items: list[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    last_model_generated = -1
    for index, item in enumerate(response_items):
        if item.get("role") == "assistant":
            last_model_generated = index
    total = 0 if last_model_generated < 0 else _estimate_response_items_token_count(response_items[: last_model_generated + 1])
    usage = {"total_tokens": total}
    return {"type": "event_msg", "event": {"type": "token_count", "info": {"total_token_usage": usage, "last_token_usage": usage, "model_context_window": None}, "rate_limits": None}}

def _estimate_response_items_token_count(response_items: list[dict[str, JsonValue]]) -> int:
    total = 0
    for item in response_items:
        total += max(1, len(json.dumps(item, separators=(",", ":"))) // 4)
    return total

def _turn_complete_item(turn_id: str, last_agent_message: str | None, completed_at: int | None) -> dict[str, JsonValue]:
    return {"type": "event_msg", "event": {"type": "turn_complete", "turn_id": turn_id, "last_agent_message": last_agent_message, "completed_at": completed_at}}

__all__ = ["load_session_for_import"]
