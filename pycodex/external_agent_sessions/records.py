"""External session record parsing owned by ``records.rs``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import (
    ConversationMessage, ExternalAgentSessionMigration, JsonValue,
    now_unix_seconds, summarize_for_label, truncate,
)

NOTE_MAX_LEN = 2000

TOOL_RESULT_MAX_LEN = 4000

EXTERNAL_AGENT_TOOL_CALL_TAG = "external_agent_tool_call"

EXTERNAL_AGENT_TOOL_RESULT_TAG = "external_agent_tool_result"

@dataclass(frozen=True)
class SessionSummary:
    latest_timestamp: int
    migration: ExternalAgentSessionMigration

def summarize_session(path: str | Path) -> SessionSummary | None:
    path = Path(path)
    cwd: Path | None = None
    custom_title: str | None = None
    ai_title: str | None = None
    title: str | None = None
    latest_timestamp: int | None = None
    saw_message = False

    for record in _iter_jsonl_records(path):
        if cwd is None and isinstance(record.get("cwd"), str):
            cwd = Path(record["cwd"])
        custom_title = _custom_title_from_record(record) or custom_title
        ai_title = _ai_title_from_record(record) or ai_title
        message = _conversation_message_from_record(record)
        if message is None:
            continue
        saw_message = True
        if title is None and message.role == "user":
            title = summarize_for_label(message.text)
        if message.timestamp is not None:
            latest_timestamp = (
                message.timestamp
                if latest_timestamp is None
                else max(latest_timestamp, message.timestamp)
            )

    if cwd is None or not saw_message or latest_timestamp is None:
        return None
    return SessionSummary(
        latest_timestamp=latest_timestamp,
        migration=ExternalAgentSessionMigration(path, cwd, custom_title or ai_title or title),
    )

def read_records(path: str | Path) -> list[dict[str, JsonValue]]:
    return list(_iter_jsonl_records(Path(path)))

def project_root_from_records(records: list[dict[str, JsonValue]]) -> Path | None:
    for record in records:
        cwd = record.get("cwd")
        if isinstance(cwd, str):
            return Path(cwd)
    return None

def source_title_from_records(records: list[dict[str, JsonValue]]) -> str | None:
    return _latest_title_from_records(records, _custom_title_from_record) or _latest_title_from_records(
        records, _ai_title_from_record
    )

def conversation_messages(records: list[dict[str, JsonValue]]) -> list[ConversationMessage]:
    return [
        message
        for record in records
        if (message := _conversation_message_from_record(record)) is not None
    ]

def tool_call_note(block: dict[str, JsonValue]) -> str:
    name = block.get("name") if isinstance(block.get("name"), str) else "unknown"
    lines = [f"[{EXTERNAL_AGENT_TOOL_CALL_TAG}: {name}]"]
    input_value = block.get("input")
    if isinstance(input_value, dict):
        if isinstance(input_value.get("description"), str):
            lines.append(f"description: {input_value['description']}")
        if isinstance(input_value.get("command"), str):
            lines.append(f"command: {input_value['command']}")
        file_value = input_value.get("file_path", input_value.get("file"))
        if isinstance(file_value, str):
            lines.append(f"file: {file_value}")
        if len(lines) == 1:
            lines.append(f"input: {truncate(json.dumps(input_value, separators=(',', ':')), NOTE_MAX_LEN)}")
    elif input_value is not None:
        lines.append(f"input: {truncate(json.dumps(input_value, separators=(',', ':')), NOTE_MAX_LEN)}")
    lines.append(f"[/{EXTERNAL_AGENT_TOOL_CALL_TAG}]")
    return "\n".join(lines)

def tool_result_note(block: dict[str, JsonValue]) -> str:
    label = (
        f"[{EXTERNAL_AGENT_TOOL_RESULT_TAG}: error]"
        if block.get("is_error") is True
        else f"[{EXTERNAL_AGENT_TOOL_RESULT_TAG}]"
    )
    text = _tool_result_text(block.get("content"))
    if not text:
        return f"{label}\n[/{EXTERNAL_AGENT_TOOL_RESULT_TAG}]"
    return f"{label}\n{truncate(text, TOOL_RESULT_MAX_LEN)}\n[/{EXTERNAL_AGENT_TOOL_RESULT_TAG}]"

def _iter_jsonl_records(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                value = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value

def _latest_title_from_records(records, title_from_record) -> str | None:
    for record in reversed(records):
        title = title_from_record(record)
        if title is not None:
            return title
    return None

def _custom_title_from_record(record: dict[str, JsonValue]) -> str | None:
    return _title_from_record(record, "custom-title", "customTitle")

def _ai_title_from_record(record: dict[str, JsonValue]) -> str | None:
    return _title_from_record(record, "ai-title", "aiTitle")

def _title_from_record(record: dict[str, JsonValue], record_type: str, field: str) -> str | None:
    if record.get("type") != record_type or not isinstance(record.get(field), str):
        return None
    title = record[field].strip()
    return title or None

def _conversation_message_from_record(record: dict[str, JsonValue]) -> ConversationMessage | None:
    record_type = record.get("type")
    if record_type not in {"assistant", "user"}:
        return None
    if record.get("isMeta") is True or record.get("isSidechain") is True:
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    extracted = _extract_message_text(message.get("content"))
    if extracted is None:
        return None
    text, only_tool_result = extracted
    role = "assistant" if record_type == "assistant" or only_tool_result else "user"
    timestamp = _parse_timestamp(record.get("timestamp"))
    return ConversationMessage(role=role, text=text, timestamp=timestamp)

def _extract_message_text(content: JsonValue) -> tuple[str, bool] | None:
    blocks = _content_blocks(content)
    parts: list[str] = []
    only_tool_result = bool(blocks)
    for block in blocks:
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
                only_tool_result = False
        elif block_type == "tool_use":
            parts.append(tool_call_note(block))
            only_tool_result = False
        elif block_type == "tool_result":
            parts.append(tool_result_note(block))
        elif block_type == "thinking":
            pass
        elif isinstance(block_type, str):
            parts.append(f"[external unsupported block: {block_type}]")
            only_tool_result = False
    text = "\n\n".join(part for part in parts if part.strip())
    if not text:
        return None
    return text, only_tool_result

def _content_blocks(content: JsonValue) -> list[dict[str, JsonValue]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [item for item in content if isinstance(item, dict)]
    return []

def _tool_result_text(content: JsonValue) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item["text"]
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"]
        )
    return ""

def _parse_timestamp(timestamp: JsonValue) -> int | None:
    if not isinstance(timestamp, str):
        return None
    normalized = timestamp.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return None

__all__ = [
    "SessionSummary", "conversation_messages", "project_root_from_records",
    "read_records", "source_title_from_records", "summarize_session",
    "tool_call_note", "tool_result_note",
]
