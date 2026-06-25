"""External-agent session import helpers aligned with Rust ``codex-external-agent-sessions``."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JsonValue = Any

SESSION_TITLE_MAX_LEN = 120
NOTE_MAX_LEN = 2000
TOOL_RESULT_MAX_LEN = 4000
SESSION_IMPORT_MAX_COUNT = 50
SESSION_IMPORT_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
SESSION_IMPORT_LEDGER_FILE = "external_agent_session_imports.json"
EXTERNAL_AGENT_TOOL_CALL_TAG = "external_agent_tool_call"
EXTERNAL_AGENT_TOOL_RESULT_TAG = "external_agent_tool_result"
EXTERNAL_SESSION_IMPORTED_MARKER = "<EXTERNAL SESSION IMPORTED>"


@dataclass(frozen=True)
class ExternalAgentSessionMigration:
    path: Path
    cwd: Path
    title: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "cwd", Path(self.cwd))


@dataclass(frozen=True)
class SessionSummary:
    latest_timestamp: int
    migration: ExternalAgentSessionMigration


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    text: str
    timestamp: int | None = None


@dataclass(frozen=True)
class ImportedExternalAgentSession:
    cwd: Path
    title: str | None
    rollout_items: list[dict[str, JsonValue]]


@dataclass(frozen=True)
class PendingSessionImport:
    source_path: Path
    session: ImportedExternalAgentSession


class PrepareSessionImportsError(Exception):
    pass


class SessionNotDetected(PrepareSessionImportsError):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__(f"external agent session was not detected for import: {self.path}")


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


def detect_recent_sessions(
    external_agent_home: str | Path,
    codex_home: str | Path,
) -> list[ExternalAgentSessionMigration]:
    external_agent_home = Path(external_agent_home)
    codex_home = Path(codex_home)
    projects_root = external_agent_home / "projects"
    if not projects_root.is_dir():
        return []
    now = now_unix_seconds()
    ledger = _load_import_ledger(codex_home)
    candidates: list[tuple[int, ExternalAgentSessionMigration]] = []
    for project_path in projects_root.iterdir():
        if not project_path.is_dir():
            continue
        try:
            entries = list(project_path.iterdir())
        except OSError:
            continue
        for path in entries:
            if path.suffix != ".jsonl":
                continue
            try:
                summary = summarize_session(path)
                if summary is None:
                    continue
                if _ledger_contains_current_source(ledger, path):
                    continue
            except OSError:
                continue
            if not _is_recent_enough(now, summary.latest_timestamp):
                continue
            if not summary.migration.cwd.is_dir():
                continue
            candidates.append((summary.latest_timestamp, summary.migration))
    candidates.sort(key=lambda item: (-item[0], str(item[1].path)))
    return [migration for _, migration in candidates[:SESSION_IMPORT_MAX_COUNT]]


def has_current_session_been_imported(codex_home: str | Path, source_path: str | Path) -> bool:
    return _ledger_contains_current_source(_load_import_ledger(Path(codex_home)), Path(source_path))


def record_imported_session(
    codex_home: str | Path,
    source_path: str | Path,
    imported_thread_id: str,
) -> None:
    codex_home = Path(codex_home)
    source_path = Path(source_path).resolve()
    content_sha256 = _session_content_sha256(source_path)
    ledger = _load_import_ledger(codex_home)
    records = ledger.setdefault("records", [])
    if any(
        Path(record.get("source_path", "")) == source_path
        and record.get("content_sha256") == content_sha256
        for record in records
    ):
        return
    records.append(
        {
            "source_path": str(source_path),
            "content_sha256": content_sha256,
            "imported_thread_id": str(imported_thread_id),
            "imported_at": now_unix_seconds(),
        }
    )
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / SESSION_IMPORT_LEDGER_FILE).write_text(
        json.dumps(ledger, indent=2),
        encoding="utf-8",
    )


def prepare_pending_session_imports(
    codex_home: str | Path,
    requested_sessions: list[ExternalAgentSessionMigration],
    detected_sessions: list[ExternalAgentSessionMigration],
) -> list[PendingSessionImport]:
    detected_session_paths = {session.path for session in detected_sessions}
    pending: list[PendingSessionImport] = []
    for session in requested_sessions:
        try:
            has_been_imported = has_current_session_been_imported(codex_home, session.path)
        except OSError:
            continue
        if session.path not in detected_session_paths and not has_been_imported:
            raise SessionNotDetected(session.path)
        if has_been_imported:
            continue
        imported_session = _load_importable_session(session.path)
        if imported_session is None:
            continue
        pending.append(PendingSessionImport(session.path, imported_session))
    return pending


def prepare_validated_session_imports(
    codex_home: str | Path,
    requested_sessions: list[ExternalAgentSessionMigration],
) -> list[PendingSessionImport]:
    pending: list[PendingSessionImport] = []
    for session in requested_sessions:
        if has_current_session_been_imported(codex_home, session.path):
            continue
        imported_session = _load_importable_session(session.path)
        if imported_session is not None:
            pending.append(PendingSessionImport(session.path, imported_session))
    return pending


def summarize_for_label(text: str) -> str:
    return truncate((text.splitlines() or [""])[0].strip(), SESSION_TITLE_MAX_LEN)


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max(max_len - 3, 0)] + "..."


def now_unix_seconds() -> int:
    return int(time.time())


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


def _load_importable_session(path: str | Path) -> ImportedExternalAgentSession | None:
    imported_session = load_session_for_import(path)
    if imported_session is None or not imported_session.cwd.is_dir():
        return None
    return imported_session


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


def _is_recent_enough(now: int, latest_timestamp: int) -> bool:
    return latest_timestamp >= max(0, now - SESSION_IMPORT_MAX_AGE_SECONDS)


def _load_import_ledger(codex_home: Path) -> dict[str, JsonValue]:
    path = codex_home / SESSION_IMPORT_LEDGER_FILE
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"records": []}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid external agent session import ledger")
    data.setdefault("records", [])
    return data


def _ledger_contains_current_source(ledger: dict[str, JsonValue], source_path: Path) -> bool:
    source_path = source_path.resolve()
    content_sha256 = _session_content_sha256(source_path)
    return any(
        Path(record.get("source_path", "")) == source_path
        and record.get("content_sha256") == content_sha256
        for record in ledger.get("records", [])
        if isinstance(record, dict)
    )


def _session_content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [name for name in globals() if not name.startswith("_")]
