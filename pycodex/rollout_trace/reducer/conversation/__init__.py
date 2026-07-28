"""Rust-aligned owner for ``codex-rollout-trace::reducer.conversation``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.rollout_trace.model import *
from pycodex.rollout_trace.payload import *
from pycodex.rollout_trace.raw_event import *
from pycodex.rollout_trace.bundle import *
from pycodex.rollout_trace.writer import TraceWriter, _NoOpTraceContext, _jsonable, _unix_time_ms

def reconcile_conversation_items(
    rollout: RolloutTrace,
    items: list[_NormalizedConversationItem],
    *,
    thread_id: str,
    codex_turn_id: str,
    wall_time_unix_ms: int,
    produced_by: list[ProducerRef],
    start_index: int,
    append_only: bool,
    snapshot_override: list[ConversationItemId] | None = None,
) -> list[ConversationItemId]:
    previous_snapshot = list(
        snapshot_override
        if snapshot_override is not None
        else rollout.thread_conversation_snapshots.get(thread_id, [])
    )
    item_ids: list[ConversationItemId] = []
    for offset, item in enumerate(items):
        _ensure_call_id_consistency(rollout, thread_id, item)
        index = start_index + offset
        if index < len(previous_snapshot) and _conversation_item_matches(
            rollout.conversation_items.get(previous_snapshot[index]), item
        ):
            item_id = previous_snapshot[index]
        elif not append_only:
            item_id = _find_matching_snapshot_item(rollout, previous_snapshot, item_ids, item)
            if item_id is None:
                item_id = _create_conversation_item(
                    rollout,
                    thread_id,
                    codex_turn_id,
                    wall_time_unix_ms,
                    item,
                    produced_by,
                )
        else:
            item_id = _create_conversation_item(
                rollout,
                thread_id,
                codex_turn_id,
                wall_time_unix_ms,
                item,
                produced_by,
            )
        _update_conversation_item_from_sighting(rollout, item_id, item, produced_by)
        _attach_model_visible_tool_item(rollout, item_id, item.call_id, item.kind)
        _attach_model_visible_code_cell_item(rollout, item_id, item.call_id, item.kind)
        _resolve_pending_agent_edges_for_item(rollout, item_id)
        item_ids.append(item_id)
    return item_ids

def _create_conversation_item(
    rollout: RolloutTrace,
    thread_id: str,
    codex_turn_id: str | None,
    first_seen_at_unix_ms: int,
    item: _NormalizedConversationItem,
    produced_by: list[ProducerRef],
) -> ConversationItemId:
    item_id = f"conversation_item:{rollout._next_conversation_item_ordinal}"
    rollout._next_conversation_item_ordinal += 1
    rollout.conversation_items[item_id] = ConversationItem(
        item_id=item_id,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        first_seen_at_unix_ms=first_seen_at_unix_ms,
        role=item.role,
        channel=item.channel,
        kind=item.kind,
        body=item.body,
        call_id=item.call_id,
        produced_by=list(produced_by),
    )
    return item_id

def _update_conversation_item_from_sighting(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
    normalized: _NormalizedConversationItem,
    produced_by: list[ProducerRef],
) -> None:
    item = rollout.conversation_items[item_id]
    if item.kind == ConversationItemKind.REASONING:
        item.body = _merge_reasoning_body(item.body, normalized.body)
    for producer in produced_by:
        if producer not in item.produced_by:
            item.produced_by.append(producer)

def _append_thread_conversation_items(
    rollout: RolloutTrace,
    thread_id: str,
    item_ids: list[ConversationItemId],
) -> None:
    thread = rollout.threads.get(thread_id)
    if thread is None:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    for item_id in item_ids:
        if item_id not in thread.conversation_item_ids:
            thread.conversation_item_ids.append(item_id)

def _find_matching_snapshot_item(
    rollout: RolloutTrace,
    previous_snapshot: list[ConversationItemId],
    used_item_ids: list[ConversationItemId],
    normalized: _NormalizedConversationItem,
) -> ConversationItemId | None:
    for item_id in previous_snapshot:
        if item_id not in used_item_ids and _conversation_item_matches(
            rollout.conversation_items.get(item_id), normalized
        ):
            return item_id
    return None

def _reconcile_detached_conversation_items(
    rollout: RolloutTrace,
    items: list[_NormalizedConversationItem],
    *,
    thread_id: str,
    codex_turn_id: str,
    wall_time_unix_ms: int,
    produced_by: list[ProducerRef],
    candidates: list[ConversationItemId],
) -> list[ConversationItemId]:
    item_ids: list[ConversationItemId] = []
    for item in items:
        _ensure_call_id_consistency(rollout, thread_id, item)
        item_id = _find_matching_snapshot_item(rollout, candidates, item_ids, item)
        if item_id is None:
            item_id = _create_conversation_item(
                rollout,
                thread_id,
                codex_turn_id,
                wall_time_unix_ms,
                item,
                produced_by,
            )
        _update_conversation_item_from_sighting(rollout, item_id, item, produced_by)
        _attach_model_visible_tool_item(rollout, item_id, item.call_id, item.kind)
        _attach_model_visible_code_cell_item(rollout, item_id, item.call_id, item.kind)
        item_ids.append(item_id)
    return item_ids

def _ensure_call_id_consistency(
    rollout: RolloutTrace,
    thread_id: str,
    normalized: _NormalizedConversationItem,
) -> None:
    if normalized.call_id is None:
        return
    for item in rollout.conversation_items.values():
        if (
            item.thread_id == thread_id
            and item.call_id == normalized.call_id
            and item.kind == normalized.kind
            and not _conversation_item_matches(item, normalized)
        ):
            raise ValueError(
                f"model-visible call id {normalized.call_id} was reused with different content"
            )

def _conversation_item_matches(
    item: ConversationItem | None,
    normalized: _NormalizedConversationItem,
) -> bool:
    if item is None:
        return False
    if item.kind == ConversationItemKind.REASONING and normalized.kind == ConversationItemKind.REASONING:
        body_matches = _reasoning_body_matches(item.body, normalized.body)
    else:
        body_matches = _conversation_body_matches(item.body, normalized.body)
    return (
        item.role == normalized.role
        and item.channel == normalized.channel
        and item.kind == normalized.kind
        and body_matches
        and item.call_id == normalized.call_id
    )

def _conversation_body_matches(left: ConversationBody, right: ConversationBody) -> bool:
    if len(left.parts) != len(right.parts):
        return False
    for left_part, right_part in zip(left.parts, right.parts):
        if left_part.type == "json" and right_part.type == "json":
            if left_part.summary != right_part.summary:
                return False
        elif left_part != right_part:
            return False
    return True

def _reasoning_body_matches(left: ConversationBody, right: ConversationBody) -> bool:
    if _conversation_body_matches(left, right):
        return True
    left_encoded = _reasoning_encoded_part(left)
    right_encoded = _reasoning_encoded_part(right)
    return left_encoded is not None and left_encoded == right_encoded

def _reasoning_encoded_part(body: ConversationBody) -> tuple[str | None, str | None] | None:
    for part in body.parts:
        if part.type == "encoded" and part.label == "encrypted_content":
            return (part.label, part.value)
    return None

def _merge_reasoning_body(existing: ConversationBody, incoming: ConversationBody) -> ConversationBody:
    if _conversation_body_matches(existing, incoming):
        return existing
    if not _reasoning_body_matches(existing, incoming):
        raise ValueError("reasoning item merge attempted with different encrypted_content identity")
    existing_text = [part for part in existing.parts if part.type == "text"]
    existing_summary = [part for part in existing.parts if part.type == "summary"]
    if existing_text and existing_summary:
        return existing
    incoming_text = [part for part in incoming.parts if part.type == "text"]
    incoming_summary = [part for part in incoming.parts if part.type == "summary"]
    encoded = [part for part in existing.parts if part.type == "encoded"] or [
        part for part in incoming.parts if part.type == "encoded"
    ]
    return ConversationBody((existing_text or incoming_text) + (existing_summary or incoming_summary) + encoded)

from pycodex.rollout_trace.model import ConversationItemId, RolloutTrace

from pycodex.rollout_trace.model.conversation import ConversationBody, ConversationItem, ConversationItemKind, ProducerRef

from pycodex.rollout_trace.reducer.code_cell import _attach_model_visible_code_cell_item

from pycodex.rollout_trace.reducer.conversation.normalize import _NormalizedConversationItem

from pycodex.rollout_trace.reducer.tool import _attach_model_visible_tool_item

from pycodex.rollout_trace.reducer.tool.agents import _resolve_pending_agent_edges_for_item
