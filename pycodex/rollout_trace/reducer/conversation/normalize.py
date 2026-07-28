"""Rust-aligned owner for ``codex-rollout-trace::reducer.conversation.normalize``."""

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

@dataclass(frozen=True)
class _NormalizedConversationItem:
    role: ConversationRole
    channel: ConversationChannel | None
    kind: ConversationItemKind
    body: ConversationBody
    call_id: str | None = None

def normalize_model_item(item: Any, raw_payload: RawPayloadRef) -> _NormalizedConversationItem:
    if not isinstance(item, dict):
        raise ValueError(f"model item in payload {raw_payload.raw_payload_id} did not contain a string type")
    item_type = item.get("type")
    if not isinstance(item_type, str):
        raise ValueError(f"model item in payload {raw_payload.raw_payload_id} did not contain a string type")
    if item_type == "message":
        role_value = item.get("role")
        if not isinstance(role_value, str):
            raise ValueError(f"message item in payload {raw_payload.raw_payload_id} did not contain a string role")
        role = _role_from_str(role_value, raw_payload)
        return _NormalizedConversationItem(
            role=role,
            channel=_channel_from_phase(item.get("phase")),
            kind=ConversationItemKind.MESSAGE,
            body=ConversationBody(_content_parts(item.get("content"), raw_payload)),
        )
    if item_type == "reasoning":
        return _normalize_reasoning_item(item, raw_payload)
    if item_type == "function_call":
        return _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.FUNCTION_CALL,
            body=_raw_text_or_json_body(item.get("arguments"), raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type == "function_call_output":
        return _NormalizedConversationItem(
            role=ConversationRole.TOOL,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.FUNCTION_CALL_OUTPUT,
            body=_tool_output_body(item.get("output"), raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type == "custom_tool_call":
        return _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.CUSTOM_TOOL_CALL,
            body=_custom_tool_call_body(item, raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type == "custom_tool_call_output":
        return _NormalizedConversationItem(
            role=ConversationRole.TOOL,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.CUSTOM_TOOL_CALL_OUTPUT,
            body=_tool_output_body(item.get("output"), raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type in {"tool_search_call", "web_search_call", "image_generation_call", "local_shell_call"}:
        return _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.FUNCTION_CALL,
            body=_json_body(item, raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type in {"tool_search_output", "mcp_tool_call_output"}:
        return _NormalizedConversationItem(
            role=ConversationRole.TOOL,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.FUNCTION_CALL_OUTPUT,
            body=_json_body(item, raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type in {"compaction", "compaction_summary", "context_compaction"}:
        return _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=ConversationChannel.SUMMARY,
            kind=ConversationItemKind.MESSAGE,
            body=_compaction_body(item, raw_payload),
        )
    raise ValueError(f"unsupported model item type {item_type} in payload {raw_payload.raw_payload_id}")

def _normalize_reasoning_item(item: dict[str, Any], raw_payload: RawPayloadRef) -> _NormalizedConversationItem:
    parts: list[ConversationPart] = []
    _append_reasoning_parts(item, "content", raw_payload, parts, summary=False)
    _append_reasoning_parts(item, "summary", raw_payload, parts, summary=True)
    encrypted_content = item.get("encrypted_content")
    if encrypted_content is not None:
        if not isinstance(encrypted_content, str):
            raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had non-string encrypted_content")
        parts.append(ConversationPart.Encoded("encrypted_content", encrypted_content))
    if not parts:
        raise ValueError(
            f"reasoning item in payload {raw_payload.raw_payload_id} contained no content, summary, or encrypted_content"
        )
    return _NormalizedConversationItem(
        role=ConversationRole.ASSISTANT,
        channel=ConversationChannel.ANALYSIS,
        kind=ConversationItemKind.REASONING,
        body=ConversationBody(parts),
    )

def _append_reasoning_parts(
    item: dict[str, Any],
    key: str,
    raw_payload: RawPayloadRef,
    parts: list[ConversationPart],
    *,
    summary: bool,
) -> None:
    if key not in item:
        return
    values = item.get(key)
    if key == "content" and values is None:
        return
    if not isinstance(values, list):
        raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had non-array {key}")
    for content_item in values:
        if not isinstance(content_item, dict):
            raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had {key} entry without string type")
        item_type = content_item.get("type")
        if summary:
            if item_type != "summary_text":
                raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had unsupported summary type {item_type}")
        elif item_type not in {"reasoning_text", "text"}:
            raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had unsupported content type {item_type}")
        text = content_item.get("text")
        if not isinstance(text, str):
            expected = "summary" if summary else "content"
            raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had {expected} entry without string text")
        parts.append(ConversationPart.Summary(text) if summary else ConversationPart.Text(text))

def _custom_tool_call_body(item: dict[str, Any], raw_payload: RawPayloadRef) -> ConversationBody:
    input_value = item.get("input")
    if not isinstance(input_value, str):
        return _json_body(item, raw_payload)
    if item.get("name") == "exec":
        return ConversationBody([ConversationPart.Code("javascript", input_value)])
    return ConversationBody([ConversationPart.Text(input_value)])

def _role_from_str(role: Any, raw_payload: RawPayloadRef) -> ConversationRole:
    try:
        return ConversationRole(role)
    except ValueError as exc:
        raise ValueError(f"unsupported message role {role} in payload {raw_payload.raw_payload_id}") from exc

def _channel_from_phase(phase: Any) -> ConversationChannel | None:
    if phase == "commentary":
        return ConversationChannel.COMMENTARY
    if phase == "final_answer":
        return ConversationChannel.FINAL
    if phase == "summary":
        return ConversationChannel.SUMMARY
    return None

def _content_parts(content: Any, raw_payload: RawPayloadRef) -> list[ConversationPart]:
    if not isinstance(content, list):
        return [ConversationPart.PayloadRef("content", raw_payload.raw_payload_id)]
    parts: list[ConversationPart] = []
    for part in content:
        if not isinstance(part, dict):
            parts.append(ConversationPart.PayloadRef("content", raw_payload.raw_payload_id))
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"} and isinstance(part.get("text"), str):
            parts.append(ConversationPart.Text(part["text"]))
        elif part_type == "input_image":
            parts.append(ConversationPart.PayloadRef("input_image", raw_payload.raw_payload_id))
        elif isinstance(part_type, str):
            parts.append(ConversationPart.PayloadRef(part_type, raw_payload.raw_payload_id))
        else:
            parts.append(ConversationPart.PayloadRef("content", raw_payload.raw_payload_id))
    return parts or [ConversationPart.PayloadRef("empty_content", raw_payload.raw_payload_id)]

def _raw_text_or_json_body(value: Any, raw_payload: RawPayloadRef) -> ConversationBody:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ConversationBody([ConversationPart.Text(value)])
        return _json_body(parsed, raw_payload)
    if value is not None:
        return _json_body(value, raw_payload)
    return ConversationBody([ConversationPart.PayloadRef("payload", raw_payload.raw_payload_id)])

def _tool_output_body(output: Any, raw_payload: RawPayloadRef) -> ConversationBody:
    if isinstance(output, str):
        return ConversationBody([ConversationPart.Text(output)])
    if isinstance(output, list):
        return ConversationBody(_content_parts(output, raw_payload))
    if output is not None:
        return _json_body(output, raw_payload)
    return ConversationBody([ConversationPart.PayloadRef("tool_output", raw_payload.raw_payload_id)])

def _compaction_body(item: dict[str, Any], raw_payload: RawPayloadRef) -> ConversationBody:
    encrypted_content = item.get("encrypted_content")
    if not isinstance(encrypted_content, str):
        raise ValueError(f"compaction item in payload {raw_payload.raw_payload_id} did not contain string encrypted_content")
    return ConversationBody([ConversationPart.Encoded("encrypted_content", encrypted_content)])

def _json_body(value: Any, raw_payload: RawPayloadRef) -> ConversationBody:
    return ConversationBody([ConversationPart.Json(_summarize_json(value), raw_payload.raw_payload_id)])

def _summarize_json(value: Any) -> str:
    summary = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if len(summary) > 240:
        return summary[:240] + "..."
    return summary

def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None

def _token_usage_from_value(value: dict[str, Any]) -> TokenUsage:
    return TokenUsage(
        input_tokens=max(int(value.get("input_tokens") or 0), 0),
        cached_input_tokens=max(int(value.get("cached_input_tokens") or 0), 0),
        output_tokens=max(int(value.get("output_tokens") or 0), 0),
        reasoning_output_tokens=max(int(value.get("reasoning_output_tokens") or 0), 0),
    )

from pycodex.rollout_trace.model.conversation import ConversationBody, ConversationChannel, ConversationItemKind, ConversationPart, ConversationRole, TokenUsage

from pycodex.rollout_trace.payload import RawPayloadRef
