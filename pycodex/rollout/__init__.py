"""Rollout persistence helpers.

Ported from ``codex/codex-rs/rollout/src``. This module intentionally starts
with filesystem and JSONL metadata helpers; the SQLite-backed state runtime is
left for a later port.
"""

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


SESSIONS_SUBDIR = "sessions"
ARCHIVED_SESSIONS_SUBDIR = "archived_sessions"
SESSION_INDEX_FILE = "session_index.jsonl"
HEAD_RECORD_LIMIT = 10
USER_EVENT_SCAN_LIMIT = 200
MAX_SCAN_FILES = 10000
BACKFILL_BATCH_SIZE = 200
BACKFILL_STATUS_RUNNING = "running"
BACKFILL_STATUS_COMPLETE = "complete"
PERSISTED_EXEC_AGGREGATED_OUTPUT_MAX_BYTES = 10_000
MATCH_CONTEXT_BEFORE_CHARS = 48
MATCH_CONTEXT_AFTER_CHARS = 96
ORIGINATOR_TAG = "originator"
OTHER_ORIGINATOR_TAG_VALUE = "other"
KNOWN_ORIGINATOR_TAG_VALUES = frozenset(
    {
        "codex_desktop",
        "codex-app-server",
        "codex_mcp_server",
        "codex_cli_rs",
        "codex-tui",
        "codex_vscode",
        "none",
        "codex_exec",
        "codex-cli",
        "codex_sdk_ts",
        "codex-app-server-sdk",
    }
)


class EventPersistenceMode(str, Enum):
    LIMITED = "limited"
    EXTENDED = "extended"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


INTERACTIVE_SESSION_SOURCES = (
    SessionSource.cli(),
    SessionSource.vscode(),
    SessionSource.custom_source("atlas"),
    SessionSource.custom_source("chatgpt"),
)


@dataclass(frozen=True)
class RolloutConfig:
    """Python semantic mirror of Rust ``codex-rollout/src/config.rs``."""

    codex_home: Path
    sqlite_home: Path
    cwd: Path
    model_provider_id: str
    generate_memories: bool

    @classmethod
    def from_view(cls, view: object) -> "RolloutConfig":
        return cls(
            codex_home=_config_path(view, "codex_home"),
            sqlite_home=_config_path(view, "sqlite_home"),
            cwd=_config_path(view, "cwd"),
            model_provider_id=str(_config_value(view, "model_provider_id")),
            generate_memories=bool(_config_value(view, "generate_memories")),
        )


Config = RolloutConfig


@dataclass(frozen=True)
class PreviousTurnSettings:
    model: str
    realtime_active: bool | None = None


@dataclass(frozen=True)
class RolloutReconstruction:
    history: tuple[ResponseItem, ...]
    previous_turn_settings: PreviousTurnSettings | None = None
    reference_context_item: TurnContextItem | None = None


@dataclass(frozen=True)
class RolloutRecorderParams:
    """Create/resume parameters matching Rust's ``RolloutRecorderParams``."""

    type: str
    conversation_id: ThreadId | None = None
    forked_from_id: ThreadId | None = None
    source: object | None = None
    thread_source: object | None = None
    base_instructions: object | None = None
    dynamic_tools: tuple[object, ...] = ()
    path: Path | None = None

    @classmethod
    def new(
        cls,
        conversation_id: ThreadId | str,
        forked_from_id: ThreadId | str | None,
        source: object,
        thread_source: object | None,
        base_instructions: object | None = None,
        dynamic_tools: Iterable[object] = (),
    ) -> "RolloutRecorderParams":
        return cls(
            "Create",
            conversation_id=ThreadId.from_string(str(conversation_id)),
            forked_from_id=None if forked_from_id is None else ThreadId.from_string(str(forked_from_id)),
            source=source,
            thread_source=thread_source,
            base_instructions=base_instructions,
            dynamic_tools=tuple(dynamic_tools),
        )

    @classmethod
    def resume(cls, path: Path | str) -> "RolloutRecorderParams":
        return cls("Resume", path=Path(path))

    def __post_init__(self) -> None:
        if self.type not in {"Create", "Resume"}:
            raise ValueError(f"unknown RolloutRecorderParams type: {self.type}")
        if self.type == "Create":
            if self.conversation_id is None:
                raise ValueError("Create rollout params require conversation_id")
            if not isinstance(self.conversation_id, ThreadId):
                object.__setattr__(self, "conversation_id", ThreadId.from_string(str(self.conversation_id)))
            if self.forked_from_id is not None and not isinstance(self.forked_from_id, ThreadId):
                object.__setattr__(self, "forked_from_id", ThreadId.from_string(str(self.forked_from_id)))
        if self.type == "Resume":
            if self.path is None:
                raise ValueError("Resume rollout params require path")
            if not isinstance(self.path, Path):
                object.__setattr__(self, "path", Path(self.path))


class RolloutRecorder:
    """Small JSONL rollout recorder façade for the core re-export coordinate."""

    def __init__(self, rollout_path: Path, *, meta: SessionMeta | None = None) -> None:
        if not isinstance(rollout_path, Path):
            rollout_path = Path(rollout_path)
        if meta is not None and not isinstance(meta, SessionMeta):
            raise TypeError("meta must be SessionMeta or None")
        self._rollout_path = rollout_path
        self._meta = meta
        self._persisted = rollout_path.exists()
        self._pending_items: list[RolloutItem] = []

    @classmethod
    def new(cls, config: object, params: RolloutRecorderParams) -> "RolloutRecorder":
        if not isinstance(params, RolloutRecorderParams):
            raise TypeError("params must be RolloutRecorderParams")
        if params.type == "Resume":
            assert params.path is not None
            return cls(params.path)

        codex_home = _config_path(config, "codex_home")
        cwd = _config_path(config, "cwd")
        sqlite_home = _config_path(config, "sqlite_home", default=codex_home)
        _ = sqlite_home
        model_provider = _config_value(config, "model_provider_id", default="unknown")
        timestamp = _format_rfc3339(datetime.now(timezone.utc))
        assert params.conversation_id is not None
        meta = SessionMeta(
            id=params.conversation_id.to_json(),
            forked_from_id=None if params.forked_from_id is None else params.forked_from_id.to_json(),
            timestamp=timestamp,
            cwd=os.fspath(cwd),
            originator="codex_python",
            cli_version="pycodex",
            source=_session_source_to_string(params.source),
            thread_source=_optional_string(params.thread_source),
            model_provider=str(model_provider),
            base_instructions=params.base_instructions,
            dynamic_tools=None if not params.dynamic_tools else list(params.dynamic_tools),
        )
        return cls(_rollout_path_for_meta(codex_home, meta), meta=meta)

    @property
    def rollout_path(self) -> Path:
        return self._rollout_path

    def persist(self) -> None:
        if self._persisted:
            return
        self._rollout_path.parent.mkdir(parents=True, exist_ok=True)
        if self._meta is None:
            self._rollout_path.touch()
        else:
            line = {
                "timestamp": self._meta.timestamp,
                "type": "session_meta",
                "payload": SessionMetaLine(meta=self._meta).to_mapping(),
            }
            self._rollout_path.write_text(
                json.dumps(line, separators=(",", ":"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        self._persisted = True

    def flush(self) -> None:
        self.persist()
        if not self._pending_items:
            return
        pending = list(self._pending_items)
        for item in pending:
            append_rollout_item_to_path(self._rollout_path, item)
        del self._pending_items[: len(pending)]

    def shutdown(self) -> None:
        self.flush()

    def record_canonical_items(self, items: Iterable[RolloutItem | Mapping[str, Any]]) -> None:
        for item in items:
            self._pending_items.append(RolloutItem.from_mapping(item))
        if self._persisted:
            self.flush()

    @staticmethod
    def load_rollout_items(path: Path | str) -> tuple[list[RolloutItem], ThreadId | None, int]:
        rollout_path = Path(path)
        text = rollout_path.read_text(encoding="utf-8")
        if not text.strip():
            raise OSError("empty session file")
        items: list[RolloutItem] = []
        thread_id: ThreadId | None = None
        parse_errors = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                item = RolloutItem.from_mapping(raw)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                parse_errors += 1
                continue
            if item.type == "response_item" and isinstance(item.payload, Mapping) and item.payload.get("type") == "ghost_snapshot":
                continue
            if item.type == "session_meta" and thread_id is None:
                payload = item.payload
                meta = getattr(payload, "meta", None)
                raw_id = getattr(meta, "id", None)
                if raw_id is not None:
                    thread_id = ThreadId.from_string(str(raw_id))
            items.append(item)
        return items, thread_id, parse_errors

    @staticmethod
    def get_rollout_history(path: Path | str) -> InitialHistory:
        rollout_path = Path(path)
        items, thread_id, _parse_errors = RolloutRecorder.load_rollout_items(rollout_path)
        if thread_id is None:
            raise OSError("failed to parse thread ID from rollout file")
        if not items:
            return InitialHistory.new()
        return InitialHistory.resumed_history(
            ResumedHistory(thread_id, tuple(items), rollout_path=rollout_path)
        )


class RolloutWriterState:
    """Semantic mirror of Rust's internal rollout writer state.

    Pending items are removed only after they are written successfully.  If a
    supplied writer fails, flush drops that handle, reopens ``rollout_path`` in
    append mode, and retries the unwritten suffix.
    """

    def __init__(
        self,
        writer: Any | None,
        rollout_path: Path | str,
        *,
        deferred_log_file_info: object | None = None,
        meta: SessionMeta | None = None,
        cwd: Path | str | None = None,
    ) -> None:
        self.writer = writer
        self.deferred_log_file_info = deferred_log_file_info
        self.meta = meta
        self.cwd = Path("." if cwd is None else cwd)
        self.rollout_path = Path(rollout_path)
        self.pending_items: list[RolloutItem] = []
        self.last_logged_error: str | None = None

    def add_items(self, items: Iterable[RolloutItem | Mapping[str, Any]]) -> None:
        self.pending_items.extend(RolloutItem.from_mapping(item) for item in items)

    def flush(self) -> None:
        if self.writer is None and self.deferred_log_file_info is not None and not self.pending_items:
            return
        try:
            self._write_pending_once()
        except OSError as first_error:
            self._enter_recovery_mode(first_error)
            self._write_pending_once()
            self.last_logged_error = None

    def persist(self) -> None:
        self.flush()

    def shutdown(self) -> None:
        self.flush()

    def _enter_recovery_mode(self, error: OSError) -> None:
        self.last_logged_error = str(error)
        close = getattr(self.writer, "close", None)
        if callable(close):
            try:
                close()
            except OSError:
                pass
        self.writer = None

    def _ensure_writer_open(self) -> None:
        if self.writer is not None:
            return
        self.rollout_path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = self.rollout_path.open("a", encoding="utf-8", newline="\n")
        self.deferred_log_file_info = None

    def _write_pending_once(self) -> None:
        self._ensure_writer_open()
        written_count = 0
        try:
            assert self.writer is not None
            for item in self.pending_items:
                self.writer.write(_rollout_item_json_line(item))
                written_count += 1
            flush = getattr(self.writer, "flush", None)
            if callable(flush):
                flush()
        finally:
            if written_count:
                del self.pending_items[:written_count]


class SqliteMetricsRecorder:
    """Semantic mirror of rollout ``sqlite_metrics.rs`` telemetry wrapper."""

    def __init__(self, metrics: Any, originator: str) -> None:
        self.metrics = metrics
        self.originator = bounded_originator_tag_value(originator)

    def counter(self, name: str, inc: int, tags: Sequence[tuple[str, str]]) -> object:
        return self.metrics.counter(name, inc, with_originator(tags, self.originator))

    def record_duration(self, name: str, duration: Any, tags: Sequence[tuple[str, str]]) -> object:
        return self.metrics.record_duration(name, duration, with_originator(tags, self.originator))


def sqlite_metrics_recorder(metrics: Any, originator: str) -> SqliteMetricsRecorder:
    return SqliteMetricsRecorder(metrics, originator)


def bounded_originator_tag_value(originator: str) -> str:
    sanitized = sanitize_metric_tag_value(originator)
    if sanitized in KNOWN_ORIGINATOR_TAG_VALUES:
        return sanitized
    return OTHER_ORIGINATOR_TAG_VALUE


def with_originator(tags: Sequence[tuple[str, str]], originator: str) -> list[tuple[str, str]]:
    return [*tags, (ORIGINATOR_TAG, originator)]


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


def search_rollout_paths(
    rg_command: Path | str | None,
    codex_home: Path | str,
    archived: bool,
    search_term: str,
) -> set[Path]:
    """Return rollout JSONL paths whose raw file body contains the JSON-escaped term.

    Rust uses ripgrep first and falls back to an async filesystem scan.  Python
    keeps the semantic fallback path as the primary implementation to avoid a
    hard dependency on an external ``rg`` binary.
    """

    _ = rg_command
    root = Path(codex_home) / (ARCHIVED_SESSIONS_SUBDIR if archived else SESSIONS_SUBDIR)
    if not root.exists():
        return set()
    escaped = _json_escaped_search_term(search_term).casefold()
    matches: set[Path] = set()
    for path in root.rglob("*.jsonl"):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                if any(escaped in line.casefold() for line in file):
                    matches.add(path)
        except OSError:
            raise
        except UnicodeDecodeError:
            continue
    return matches


def first_rollout_content_match_snippet(path: Path | str, search_term: str) -> str | None:
    json_search_term = _json_escaped_search_term(search_term).casefold()
    needle = search_term.casefold()
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if json_search_term not in line.casefold():
                continue
            text = _conversation_text_from_jsonl_line(line)
            if text is None:
                continue
            snippet = _excerpt_around_match(text, needle)
            if snippet is not None:
                return snippet
    return None


def _json_escaped_search_term(search_term: str) -> str:
    serialized = json.dumps(search_term, ensure_ascii=False)
    return serialized[1:-1]


def _conversation_text_from_jsonl_line(line: str) -> str | None:
    try:
        rollout_line = json.loads(line.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(rollout_line, Mapping):
        return None
    item_type = rollout_line.get("type")
    payload = rollout_line.get("payload")
    if item_type == "event_msg":
        return _conversation_text_from_event_msg(payload)
    if item_type == "response_item":
        return _conversation_text_from_response_item(payload)
    return None


def _conversation_text_from_event_msg(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    event_type = payload.get("type")
    if event_type == "user_message":
        text = _strip_user_message_prefix(str(payload.get("message", "")))
        return text or None
    if event_type == "agent_message":
        text = str(payload.get("message", "")).strip()
        return text or None
    return None


def _conversation_text_from_response_item(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    if payload.get("type") != "message" or payload.get("role") not in {"user", "assistant"}:
        return None
    content = payload.get("content")
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") in {"input_text", "output_text"} and isinstance(item.get("text"), str):
            parts.append(item["text"])
    text = " ".join(parts).strip()
    return text or None


def _excerpt_around_match(text: str, needle: str) -> str | None:
    normalized = _normalize_preview_text(text)
    match_start = normalized.casefold().find(needle)
    if match_start < 0:
        return None
    match_end = match_start + len(needle)
    excerpt_start = _char_start_before(normalized, match_start, MATCH_CONTEXT_BEFORE_CHARS)
    excerpt_end = _char_end_after(normalized, match_end, MATCH_CONTEXT_AFTER_CHARS)
    excerpt = normalized[excerpt_start:excerpt_end].strip()
    if not excerpt:
        return None
    prefix = "... " if excerpt_start > 0 else ""
    suffix = " ..." if excerpt_end < len(normalized) else ""
    return f"{prefix}{excerpt}{suffix}"


def _normalize_preview_text(text: str) -> str:
    return " ".join(text.split())


def _char_start_before(text: str, index: int, chars_before: int) -> int:
    return max(0, index - chars_before)


def _char_end_after(text: str, index: int, chars_after: int) -> int:
    return min(len(text), index + chars_after)


def append_rollout_item_to_path(
    path: Path | str,
    item: RolloutItem | Mapping[str, Any],
    *,
    timestamp: str | None = None,
) -> None:
    rollout_item = RolloutItem.from_mapping(item)
    rollout_path = Path(path)
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(_rollout_item_json_line(rollout_item, timestamp=timestamp))


def _rollout_item_json_line(item: RolloutItem | Mapping[str, Any], *, timestamp: str | None = None) -> str:
    rollout_item = RolloutItem.from_mapping(item)
    line = rollout_item.to_mapping()
    line["timestamp"] = timestamp or _format_rfc3339(datetime.now(timezone.utc))
    return json.dumps(line, separators=(",", ":"), ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class _ParsedRolloutItem:
    type: str
    payload: object


@dataclass
class _ActiveReplaySegment:
    turn_id: str | None = None
    counts_as_user_turn: bool = False
    previous_turn_settings: PreviousTurnSettings | None = None
    reference_context_kind: str = "never"
    reference_context_item: TurnContextItem | None = None
    base_replacement_history: tuple[ResponseItem, ...] | None = None


@dataclass(frozen=True)
class Cursor:
    """Pagination cursor represented by an RFC3339 timestamp."""

    timestamp: datetime

    def to_json(self) -> str:
        return _format_rfc3339(self.timestamp)


@dataclass(frozen=True)
class Anchor:
    """State DB pagination anchor represented by a millisecond UTC timestamp."""

    ts: datetime


@dataclass(frozen=True)
class GitInfo:
    commit_hash: str | None = None
    branch: str | None = None
    repository_url: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "GitInfo | None":
        if data is None:
            return None
        return cls(
            commit_hash=data.get("commit_hash"),
            branch=data.get("branch"),
            repository_url=data.get("repository_url"),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.commit_hash is not None:
            data["commit_hash"] = self.commit_hash
        if self.branch is not None:
            data["branch"] = self.branch
        if self.repository_url is not None:
            data["repository_url"] = self.repository_url
        return data


@dataclass(frozen=True)
class SessionMeta:
    id: str
    timestamp: str
    cwd: str
    originator: str
    cli_version: str
    source: str = "vscode"
    forked_from_id: str | None = None
    thread_source: str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    agent_path: str | None = None
    model_provider: str | None = None
    base_instructions: Any | None = None
    dynamic_tools: Any | None = None
    memory_mode: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SessionMeta":
        _require_keys(data, ("id", "timestamp", "cwd", "originator", "cli_version"))
        return cls(
            id=str(data.get("id", "")),
            forked_from_id=data.get("forked_from_id"),
            timestamp=str(data.get("timestamp", "")),
            cwd=str(data.get("cwd", "")),
            originator=str(data.get("originator", "")),
            cli_version=str(data.get("cli_version", "")),
            source=str(data.get("source", "vscode")),
            thread_source=data.get("thread_source"),
            agent_nickname=data.get("agent_nickname"),
            agent_role=data.get("agent_role", data.get("agent_type")),
            agent_path=data.get("agent_path"),
            model_provider=data.get("model_provider"),
            base_instructions=data.get("base_instructions"),
            dynamic_tools=data.get("dynamic_tools"),
            memory_mode=data.get("memory_mode"),
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
            "cwd": self.cwd,
            "originator": self.originator,
            "cli_version": self.cli_version,
            "source": self.source,
            "model_provider": self.model_provider,
            "base_instructions": self.base_instructions,
        }
        for key in (
            "forked_from_id",
            "thread_source",
            "agent_nickname",
            "agent_role",
            "agent_path",
            "dynamic_tools",
            "memory_mode",
        ):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class SessionMetaLine:
    meta: SessionMeta
    git: GitInfo | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SessionMetaLine":
        payload = dict(data)
        git = GitInfo.from_mapping(payload.pop("git", None))
        return cls(meta=SessionMeta.from_mapping(payload), git=git)

    def to_mapping(self) -> dict[str, Any]:
        data = self.meta.to_mapping()
        if self.git is not None:
            data["git"] = self.git.to_mapping()
        return data


@dataclass(frozen=True)
class SessionIndexEntry:
    id: str
    thread_name: str
    updated_at: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SessionIndexEntry":
        return cls(
            id=str(data["id"]),
            thread_name=str(data["thread_name"]),
            updated_at=str(data["updated_at"]),
        )

    def to_mapping(self) -> dict[str, str]:
        return {"id": self.id, "thread_name": self.thread_name, "updated_at": self.updated_at}


class ThreadSortKey(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class ThreadListLayout(str, Enum):
    NESTED_BY_DATE = "nested_by_date"
    FLAT = "flat"


@dataclass(frozen=True)
class ThreadItem:
    """Summary information for a thread rollout file."""

    path: Path
    thread_id: str | None = None
    first_user_message: str | None = None
    preview: str | None = None
    cwd: Path | None = None
    git_branch: str | None = None
    git_sha: str | None = None
    git_origin_url: str | None = None
    source: str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    model_provider: str | None = None
    cli_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def fill_missing_thread_item_metadata(item: ThreadItem, state_item: ThreadItem) -> ThreadItem:
    """Merge state DB metadata into a filesystem thread item.

    Mirrors Rust ``codex-rollout/src/recorder.rs::fill_missing_thread_item_metadata``:
    filesystem identity/path fields are preserved, regular metadata only fills
    missing values, and state DB git fields win when present.
    """

    return replace(
        item,
        first_user_message=item.first_user_message if item.first_user_message is not None else state_item.first_user_message,
        preview=item.preview if item.preview is not None else state_item.preview,
        cwd=item.cwd if item.cwd is not None else state_item.cwd,
        git_branch=state_item.git_branch if state_item.git_branch is not None else item.git_branch,
        git_sha=state_item.git_sha if state_item.git_sha is not None else item.git_sha,
        git_origin_url=state_item.git_origin_url if state_item.git_origin_url is not None else item.git_origin_url,
        source=item.source if item.source is not None else state_item.source,
        agent_nickname=item.agent_nickname if item.agent_nickname is not None else state_item.agent_nickname,
        agent_role=item.agent_role if item.agent_role is not None else state_item.agent_role,
        model_provider=item.model_provider if item.model_provider is not None else state_item.model_provider,
        cli_version=item.cli_version if item.cli_version is not None else state_item.cli_version,
        created_at=item.created_at if item.created_at is not None else state_item.created_at,
        updated_at=item.updated_at if item.updated_at is not None else state_item.updated_at,
    )


@dataclass(frozen=True)
class ThreadMetadataBuilder:
    """Semantic Python mirror of Rust ``codex_state::ThreadMetadataBuilder``."""

    id: str
    rollout_path: Path
    created_at: datetime
    source: str = "vscode"
    updated_at: datetime | None = None
    thread_source: str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    agent_path: str | None = None
    model_provider: str | None = None
    cwd: Path = field(default_factory=Path)
    cli_version: str | None = None
    sandbox_policy: str = "read-only"
    approval_mode: str = "on-request"
    archived_at: datetime | None = None
    git_sha: str | None = None
    git_branch: str | None = None
    git_origin_url: str | None = None

    def build(self, default_provider: str) -> "ThreadMetadata":
        return ThreadMetadata(
            id=self.id,
            rollout_path=self.rollout_path,
            created_at=self.created_at,
            updated_at=self.updated_at or self.created_at,
            source=self.source,
            thread_source=self.thread_source,
            agent_nickname=self.agent_nickname,
            agent_role=self.agent_role,
            agent_path=self.agent_path,
            model_provider=self.model_provider or default_provider,
            cwd=self.cwd,
            cli_version=self.cli_version or "",
            sandbox_policy=self.sandbox_policy,
            approval_mode=self.approval_mode,
            archived_at=self.archived_at,
            git_sha=self.git_sha,
            git_branch=self.git_branch,
            git_origin_url=self.git_origin_url,
            first_user_message=None,
            preview=None,
        )


@dataclass(frozen=True)
class ThreadMetadata:
    """Semantic metadata extracted from a rollout file."""

    id: str
    rollout_path: Path
    created_at: datetime
    updated_at: datetime
    source: str
    thread_source: str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    agent_path: str | None = None
    model_provider: str = ""
    cwd: Path = field(default_factory=Path)
    cli_version: str = ""
    sandbox_policy: str = "read-only"
    approval_mode: str = "on-request"
    archived_at: datetime | None = None
    git_sha: str | None = None
    git_branch: str | None = None
    git_origin_url: str | None = None
    first_user_message: str | None = None
    preview: str | None = None

    def prefer_existing_git_info(self, existing: "ThreadMetadata") -> "ThreadMetadata":
        """Preserve existing non-null Git fields during rollout reconciliation."""

        return replace(
            self,
            git_sha=existing.git_sha or self.git_sha,
            git_branch=existing.git_branch or self.git_branch,
            git_origin_url=existing.git_origin_url or self.git_origin_url,
        )


def thread_item_from_state_metadata(item: ThreadMetadata) -> ThreadItem:
    """Convert state DB thread metadata into a list ``ThreadItem``."""

    return ThreadItem(
        path=item.rollout_path,
        thread_id=item.id,
        first_user_message=item.first_user_message,
        preview=item.preview,
        cwd=item.cwd,
        git_branch=item.git_branch,
        git_sha=item.git_sha,
        git_origin_url=item.git_origin_url,
        source=item.source,
        agent_nickname=item.agent_nickname,
        agent_role=item.agent_role,
        model_provider=item.model_provider,
        cli_version=item.cli_version,
        created_at=_format_rfc3339(item.created_at),
        updated_at=_format_rfc3339(item.updated_at),
    )


@dataclass(frozen=True)
class ExtractionOutcome:
    """Result of Rust ``extract_metadata_from_rollout``."""

    metadata: ThreadMetadata
    memory_mode: str | None
    parse_errors: int


@dataclass(frozen=True)
class BackfillState:
    status: str | None = None
    last_watermark: str | None = None
    last_success_at: datetime | None = None


@dataclass(frozen=True)
class BackfillStats:
    scanned: int = 0
    upserted: int = 0
    failed: int = 0


@dataclass(frozen=True)
class ThreadsPage:
    """Returned page of thread summaries."""

    items: list[ThreadItem]
    next_cursor: Cursor | None = None
    num_scanned_files: int = 0
    reached_scan_cap: bool = False


def rollout_date_parts(file_name: str | Path) -> tuple[str, str, str] | None:
    """Extract ``YYYY/MM/DD`` components from a rollout filename."""

    name = Path(file_name).name
    if not name.startswith("rollout-") or len(name) < len("rollout-") + 10:
        return None
    date = name[len("rollout-") : len("rollout-") + 10]
    return date[:4], date[5:7], date[8:10]


def parse_cursor(token: str) -> Cursor | None:
    """Parse the upstream cursor token format."""

    if "|" in token:
        return None
    parsed = _parse_rfc3339(token)
    if parsed is None:
        try:
            parsed = datetime.strptime(token, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return Cursor(parsed)


def parse_timestamp_uuid_from_filename(name: str) -> tuple[datetime, str] | None:
    """Parse ``rollout-YYYY-MM-DDThh-mm-ss-<uuid>.jsonl`` filenames."""

    core = name.removeprefix("rollout-")
    if core == name:
        return None
    core = core.removesuffix(".jsonl")
    if core == name.removeprefix("rollout-"):
        return None

    for index in range(len(core) - 1, -1, -1):
        if core[index] != "-":
            continue
        try:
            rollout_id = uuid.UUID(core[index + 1 :])
        except ValueError:
            continue
        try:
            timestamp = datetime.strptime(core[:index], "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        return timestamp, str(rollout_id)
    return None


def parse_timestamp_to_utc(timestamp: str) -> datetime | None:
    """Parse Rust rollout metadata timestamps into UTC datetimes."""

    try:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc)
    except ValueError:
        parsed = _parse_rfc3339(timestamp)
        return parsed.astimezone(timezone.utc) if parsed is not None else None


def builder_from_session_meta(
    session_meta: SessionMetaLine | Mapping[str, Any],
    rollout_path: Path,
) -> ThreadMetadataBuilder | None:
    """Build thread metadata from the first Rust ``RolloutItem::SessionMeta``."""

    try:
        line = session_meta if isinstance(session_meta, SessionMetaLine) else SessionMetaLine.from_mapping(dict(session_meta))
    except (KeyError, TypeError, ValueError):
        return None

    created_at = parse_timestamp_to_utc(line.meta.timestamp)
    if created_at is None:
        return None

    git = line.git
    return ThreadMetadataBuilder(
        id=line.meta.id,
        rollout_path=Path(rollout_path),
        created_at=created_at,
        source=line.meta.source,
        thread_source=line.meta.thread_source,
        agent_nickname=line.meta.agent_nickname,
        agent_role=line.meta.agent_role,
        agent_path=line.meta.agent_path,
        model_provider=line.meta.model_provider,
        cwd=Path(line.meta.cwd),
        cli_version=line.meta.cli_version,
        git_sha=git.commit_hash if git is not None else None,
        git_branch=git.branch if git is not None else None,
        git_origin_url=git.repository_url if git is not None else None,
    )


def builder_from_items(items: Sequence[Any], rollout_path: Path) -> ThreadMetadataBuilder | None:
    """Build metadata from rollout items, falling back to the rollout filename."""

    for item in items:
        payload: Any | None = None
        if isinstance(item, SessionMetaLine):
            payload = item
        elif isinstance(item, Mapping):
            item_type = item.get("type")
            if item_type == "session_meta":
                payload = item.get("payload")
            elif {"id", "timestamp", "cwd", "originator", "cli_version"}.issubset(item.keys()):
                payload = item
        if payload is not None:
            builder = builder_from_session_meta(payload, rollout_path)
            if builder is not None:
                return builder

    parsed = parse_timestamp_uuid_from_filename(Path(rollout_path).name)
    if parsed is None:
        return None
    created_at, thread_id = parsed
    return ThreadMetadataBuilder(
        id=thread_id,
        rollout_path=Path(rollout_path),
        created_at=created_at,
        source="vscode",
    )


def backfill_watermark_for_path(codex_home: Path, path: Path) -> str:
    """Return the Rust metadata backfill watermark key for a rollout path."""

    home = Path(codex_home)
    rollout_path = Path(path)
    try:
        value = rollout_path.relative_to(home)
    except ValueError:
        value = rollout_path
    return value.as_posix()


def extract_metadata_from_rollout(rollout_path: Path, default_provider: str = "") -> ExtractionOutcome:
    """Extract thread metadata from a rollout JSONL file."""

    path = Path(rollout_path)
    items: list[dict[str, Any]] = []
    parse_errors = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"failed to read session file: {path}") from exc

    for raw_line in lines:
        if not raw_line.strip():
            continue
        try:
            line = json.loads(raw_line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if isinstance(line, Mapping):
            items.append(dict(line))
        else:
            parse_errors += 1

    if not items:
        raise ValueError(f"empty session file: {path}")

    builder = builder_from_items(items, path)
    if builder is None:
        raise ValueError(f"rollout missing metadata builder: {path}")

    metadata = builder.build(default_provider)
    updated_at = _file_modified_time(path)
    if updated_at is not None:
        metadata = replace(metadata, updated_at=updated_at)

    memory_mode: str | None = None
    for item in reversed(items):
        if item.get("type") != "session_meta":
            continue
        payload = item.get("payload")
        if isinstance(payload, Mapping):
            value = payload.get("memory_mode")
            if value is not None:
                memory_mode = str(value)
                break

    return ExtractionOutcome(metadata=metadata, memory_mode=memory_mode, parse_errors=parse_errors)


def collect_rollout_paths(root: Path) -> list[Path]:
    """Collect rollout JSONL paths under a root, matching Rust metadata.rs."""

    root = Path(root)
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("rollout-*.jsonl")
        if path.is_file() and path.name.startswith("rollout-") and path.name.endswith(".jsonl")
    )


def _runtime_call(runtime: Any, name: str, *args: Any) -> Any:
    method = getattr(runtime, name, None)
    if not callable(method):
        raise NotImplementedError(f"backfill runtime missing {name}()")
    return method(*args)


def _state_status(state: Any) -> str | None:
    return state.get("status") if isinstance(state, Mapping) else getattr(state, "status", None)


def _state_last_watermark(state: Any) -> str | None:
    return state.get("last_watermark") if isinstance(state, Mapping) else getattr(state, "last_watermark", None)


def _set_memory_mode(runtime: Any, thread_id: str, memory_mode: str) -> None:
    setter = getattr(runtime, "set_thread_memory_mode", None)
    if callable(setter):
        setter(thread_id, memory_mode)


def normalize_cwd_for_state_db(cwd: Path) -> Path:
    """Normalize rollout cwd before state-runtime upsert."""

    try:
        return Path(cwd).resolve(strict=False)
    except OSError:
        return Path(cwd)


def cursor_to_anchor(cursor: Cursor | None) -> Anchor | None:
    if cursor is None:
        return None
    timestamp = cursor.timestamp.astimezone(timezone.utc)
    millis = int(timestamp.timestamp() * 1000)
    return Anchor(datetime.fromtimestamp(millis / 1000, timezone.utc))


def list_thread_ids_db(
    context: Any,
    codex_home: Path | str,
    page_size: int,
    cursor: Cursor | None,
    sort_key: ThreadSortKey | str,
    allowed_sources: Sequence[SessionSource],
    model_providers: Sequence[str] | None,
    archived_only: bool,
    stage: str,
) -> list[Any] | None:
    if context is None:
        return None
    anchor = cursor_to_anchor(cursor)
    allowed_source_values = [_state_db_session_source_value(source) for source in allowed_sources]
    sort_key_value = _state_db_sort_key_value(sort_key)
    try:
        _warn_on_codex_home_mismatch(context, codex_home)
        return context.list_thread_ids(
            page_size,
            anchor,
            sort_key_value,
            allowed_source_values,
            None if model_providers is None else list(model_providers),
            archived_only,
        )
    except Exception:
        _ = stage
        return None


def list_threads_db(
    context: Any,
    codex_home: Path | str,
    page_size: int,
    cursor: Cursor | None,
    sort_key: ThreadSortKey | str,
    sort_direction: SortDirection | str,
    allowed_sources: Sequence[SessionSource],
    model_providers: Sequence[str] | None,
    cwd_filters: Sequence[Path] | None,
    archived: bool,
    search_term: str | None,
) -> Any | None:
    if context is None:
        return None
    options = {
        "archived_only": archived,
        "allowed_sources": [_state_db_session_source_value(source) for source in allowed_sources],
        "model_providers": None if model_providers is None else list(model_providers),
        "cwd_filters": None if cwd_filters is None else [normalize_cwd_for_state_db(cwd) for cwd in cwd_filters],
        "anchor": cursor_to_anchor(cursor),
        "sort_key": _state_db_sort_key_value(sort_key),
        "sort_direction": _state_db_sort_direction_value(sort_direction),
        "search_term": search_term,
    }
    try:
        _warn_on_codex_home_mismatch(context, codex_home)
        page = context.list_threads(page_size, options)
    except Exception:
        return None
    items = list(_state_db_page_items(page))
    valid_items = []
    for item in items:
        rollout_path = _state_db_item_rollout_path(item)
        if rollout_path is not None and rollout_path.exists():
            valid_items.append(item)
            continue
        thread_id = _state_db_item_id(item)
        deleter = getattr(context, "delete_thread", None)
        if callable(deleter) and thread_id is not None:
            try:
                deleter(thread_id)
            except Exception:
                pass
    return _state_db_page_with_items(page, valid_items)


def find_rollout_path_by_id(
    context: Any,
    thread_id: Any,
    archived_only: bool | None,
    stage: str,
) -> Path | None:
    if context is None:
        return None
    finder = getattr(context, "find_rollout_path_by_id", None)
    if not callable(finder):
        return None
    try:
        value = finder(thread_id, archived_only)
    except Exception:
        _ = stage
        return None
    return Path(value) if value is not None else None


def mark_thread_memory_mode_polluted(context: Any, thread_id: Any, stage: str) -> None:
    if context is None:
        return
    memories = getattr(context, "memories", None)
    try:
        memories = memories() if callable(memories) else memories
    except Exception:
        _ = stage
        return
    marker = getattr(memories, "mark_thread_memory_mode_polluted", None)
    if not callable(marker):
        return
    try:
        marker(thread_id)
    except Exception:
        _ = stage


def touch_thread_updated_at(context: Any, thread_id: Any | None, updated_at: datetime, stage: str) -> bool:
    if context is None or thread_id is None:
        return False
    toucher = getattr(context, "touch_thread_updated_at", None)
    if not callable(toucher):
        return False
    try:
        return bool(toucher(thread_id, updated_at))
    except Exception:
        _ = stage
        return False


def read_repair_rollout_path(
    context: Any,
    thread_id: Any | None,
    archived_only: bool | None,
    rollout_path: Path | str,
    default_provider: str = "",
) -> None:
    if context is None:
        return
    path = Path(rollout_path)
    saw_existing_metadata = False
    if thread_id is not None:
        getter = getattr(context, "get_thread", None)
        if callable(getter):
            try:
                metadata = getter(thread_id)
            except Exception:
                metadata = None
            if metadata is not None:
                saw_existing_metadata = True
                repaired = _repair_state_metadata(metadata, path, archived_only)
                if repaired == metadata:
                    return
                upsert = getattr(context, "upsert_thread", None)
                if callable(upsert):
                    try:
                        upsert(repaired)
                        return
                    except Exception:
                        pass
    if saw_existing_metadata:
        return
    try:
        outcome = extract_metadata_from_rollout(path, default_provider)
    except Exception:
        return
    metadata = _repair_state_metadata(outcome.metadata, path, archived_only)
    upsert = getattr(context, "upsert_thread", None)
    if callable(upsert):
        try:
            upsert(metadata)
        except Exception:
            return


def apply_rollout_items(
    context: Any,
    rollout_path: Path | str,
    default_provider: str,
    builder: ThreadMetadataBuilder | None,
    items: Sequence[Any],
    stage: str,
    new_thread_memory_mode: str | None = None,
    updated_at_override: datetime | None = None,
) -> None:
    if context is None:
        return
    path = Path(rollout_path)
    effective_builder = builder if builder is not None else builder_from_items(items, path)
    if effective_builder is None:
        _ = stage
        return
    if effective_builder.model_provider is None:
        effective_builder = replace(effective_builder, model_provider=default_provider)
    effective_builder = replace(
        effective_builder,
        rollout_path=path,
        cwd=normalize_cwd_for_state_db(effective_builder.cwd),
    )
    applier = getattr(context, "apply_rollout_items", None)
    if not callable(applier):
        return
    try:
        applier(effective_builder, list(items), new_thread_memory_mode, updated_at_override)
    except Exception:
        _ = stage
        return


def backfill_sessions(runtime: Any, codex_home: Path, default_provider: str = "") -> BackfillStats:
    """Backfill rollout metadata into a state runtime.

    The runtime is intentionally protocol-shaped: it must provide the same
    method names used by Rust ``StateRuntime`` for this module boundary.
    """

    state = _runtime_call(runtime, "get_backfill_state")
    if _state_status(state) == BACKFILL_STATUS_COMPLETE:
        return BackfillStats()

    claimed = _runtime_call(runtime, "try_claim_backfill")
    if not claimed:
        return BackfillStats()

    state = _runtime_call(runtime, "get_backfill_state")
    if _state_status(state) != BACKFILL_STATUS_RUNNING:
        _runtime_call(runtime, "mark_backfill_running")
        state = BackfillState(status=BACKFILL_STATUS_RUNNING, last_watermark=_state_last_watermark(state))

    codex_home = Path(codex_home)
    rollout_entries: list[tuple[str, Path, bool]] = []
    for root, archived in (
        (codex_home / SESSIONS_SUBDIR, False),
        (codex_home / ARCHIVED_SESSIONS_SUBDIR, True),
    ):
        for path in collect_rollout_paths(root):
            rollout_entries.append((backfill_watermark_for_path(codex_home, path), path, archived))
    rollout_entries.sort(key=lambda entry: entry[0])

    last_state_watermark = _state_last_watermark(state)
    if last_state_watermark is not None:
        rollout_entries = [entry for entry in rollout_entries if entry[0] > last_state_watermark]

    scanned = upserted = failed = 0
    last_watermark = last_state_watermark
    for batch_start in range(0, len(rollout_entries), BACKFILL_BATCH_SIZE):
        batch = rollout_entries[batch_start : batch_start + BACKFILL_BATCH_SIZE]
        for watermark, path, archived in batch:
            scanned += 1
            try:
                outcome = extract_metadata_from_rollout(path, default_provider)
                metadata = replace(outcome.metadata, cwd=normalize_cwd_for_state_db(outcome.metadata.cwd))
                getter = getattr(runtime, "get_thread", None)
                if callable(getter):
                    existing = getter(metadata.id)
                    if existing is not None:
                        metadata = metadata.prefer_existing_git_info(existing)
                if archived and metadata.archived_at is None:
                    metadata = replace(metadata, archived_at=metadata.updated_at)
                _runtime_call(runtime, "upsert_thread", metadata)
                _set_memory_mode(runtime, metadata.id, outcome.memory_mode or "enabled")
                upserted += 1
            except Exception:
                failed += 1
        if batch:
            last_watermark = batch[-1][0]
            _runtime_call(runtime, "checkpoint_backfill", last_watermark)

    _runtime_call(runtime, "mark_backfill_complete", last_watermark)
    return BackfillStats(scanned=scanned, upserted=upserted, failed=failed)


def init_state_runtime_with_backfill(runtime: Any, codex_home: Path, default_provider: str = "") -> Any:
    """Initialize a state runtime by completing rollout backfill before returning it."""

    backfill_sessions(runtime, codex_home, default_provider)
    return runtime


def get_threads(
    codex_home: Path,
    page_size: int,
    cursor: Cursor | str | None = None,
    sort_key: ThreadSortKey | str = ThreadSortKey.CREATED_AT,
    allowed_sources: Sequence[str] = (),
    model_providers: Sequence[str] | None = None,
    cwd_filters: Sequence[Path] | None = None,
    default_provider: str = "",
    search_term: str | None = None,
) -> ThreadsPage:
    """List persisted threads below ``<codex_home>/sessions``."""

    codex_home = Path(codex_home)
    return get_threads_in_root(
        codex_home / SESSIONS_SUBDIR,
        page_size,
        cursor=cursor,
        sort_key=sort_key,
        allowed_sources=allowed_sources,
        model_providers=model_providers,
        cwd_filters=cwd_filters,
        default_provider=default_provider,
        layout=ThreadListLayout.NESTED_BY_DATE,
        codex_home=codex_home,
        search_term=search_term,
    )


def get_threads_in_root(
    root: Path,
    page_size: int,
    cursor: Cursor | str | None = None,
    sort_key: ThreadSortKey | str = ThreadSortKey.CREATED_AT,
    allowed_sources: Sequence[str] = (),
    model_providers: Sequence[str] | None = None,
    cwd_filters: Sequence[Path] | None = None,
    default_provider: str = "",
    layout: ThreadListLayout | str = ThreadListLayout.NESTED_BY_DATE,
    codex_home: Path | None = None,
    search_term: str | None = None,
) -> ThreadsPage:
    """List rollout files in a sessions root with upstream-style pagination."""

    if page_size <= 0:
        raise ValueError("page_size must be positive")

    root = Path(root)
    if not root.is_dir():
        return ThreadsPage(items=[])

    sort_key = _coerce_sort_key(sort_key)
    layout = _coerce_layout(layout)
    cursor_obj = parse_cursor(cursor) if isinstance(cursor, str) else cursor

    candidates, scanned, reached_scan_cap = _collect_rollout_candidates(root, layout, sort_key)
    items: list[ThreadItem] = []
    more_matches_available = False
    allowed_sources_set = {str(source) for source in allowed_sources}
    search_match_ids: set[str] | None = None
    if search_term is not None:
        if codex_home is None:
            raise ValueError("codex_home is required when search_term is provided")
        search_match_ids = _thread_ids_matching_search_term(Path(codex_home), search_term)

    for candidate in candidates:
        sort_timestamp = candidate.sort_timestamp(sort_key)
        if cursor_obj is not None and sort_timestamp >= cursor_obj.timestamp:
            continue
        updated_at = _format_rfc3339(candidate.updated_at) if candidate.updated_at is not None else None
        item = _build_thread_item(
            candidate.path,
            allowed_sources=allowed_sources_set,
            model_providers=model_providers,
            cwd_filters=cwd_filters,
            default_provider=default_provider,
            updated_at=updated_at,
        )
        if item is None:
            continue
        if search_match_ids is not None and (item.thread_id is None or item.thread_id not in search_match_ids):
            continue
        if len(items) == page_size:
            more_matches_available = True
            break
        items.append(item)

    next_cursor = None
    if items and (more_matches_available or reached_scan_cap):
        next_cursor = _build_next_cursor(items, sort_key)

    return ThreadsPage(
        items=items,
        next_cursor=next_cursor,
        num_scanned_files=scanned,
        reached_scan_cap=reached_scan_cap,
    )


def list_threads_from_state_metadata(
    metadata_items: Iterable[ThreadMetadata],
    page_size: int,
    cursor: Cursor | str | None = None,
    sort_key: ThreadSortKey | str = ThreadSortKey.CREATED_AT,
    allowed_sources: Sequence[str] = (),
    model_providers: Sequence[str] | None = None,
    cwd_filters: Sequence[Path] | None = None,
    default_provider: str = "",
    search_term: str | None = None,
    repair_runtime: Any = None,
    drop_missing_rollout_paths: bool = False,
    codex_home: Path | None = None,
    repair_stale_rollout_paths: bool = False,
) -> ThreadsPage:
    """List threads from state metadata without scanning JSONL rollout files."""

    if page_size <= 0:
        raise ValueError("page_size must be positive")

    sort_key = _coerce_sort_key(sort_key)
    cursor_obj = parse_cursor(cursor) if isinstance(cursor, str) else cursor
    allowed_sources_set = {str(source) for source in allowed_sources}
    items: list[ThreadItem] = []

    for metadata in metadata_items:
        if (drop_missing_rollout_paths or repair_stale_rollout_paths) and not metadata.rollout_path.exists():
            repaired_path = None
            if repair_stale_rollout_paths and codex_home is not None:
                repaired_path = find_thread_path_by_id_str(Path(codex_home), metadata.id)
            if repaired_path is None:
                if drop_missing_rollout_paths:
                    _delete_missing_state_thread(repair_runtime, metadata.id)
                    continue
            else:
                _repair_state_thread_path(repair_runtime, metadata.id, repaired_path)
                metadata = replace(metadata, rollout_path=repaired_path)
        item = thread_item_from_state_metadata(metadata)
        if allowed_sources_set and (item.source is None or item.source not in allowed_sources_set):
            continue
        if not _matches_provider(item.model_provider, model_providers, default_provider):
            continue
        if not _matches_cwd(item.cwd, cwd_filters):
            continue
        if search_term is not None and search_term not in (metadata.preview or metadata.first_user_message or ""):
            continue
        sort_timestamp = _state_thread_sort_timestamp(item, sort_key)
        if sort_timestamp is None:
            continue
        if cursor_obj is not None and sort_timestamp >= cursor_obj.timestamp:
            continue
        items.append(item)

    items.sort(key=lambda item: _state_thread_sort_timestamp(item, sort_key) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    more_matches_available = len(items) > page_size
    items = items[:page_size]
    next_cursor = _state_next_cursor(items, sort_key) if items and more_matches_available else None
    return ThreadsPage(items=items, next_cursor=next_cursor, num_scanned_files=0, reached_scan_cap=False)


def _delete_missing_state_thread(runtime: Any, thread_id: str) -> None:
    if runtime is None:
        return
    for name in ("delete_thread", "remove_thread", "delete_thread_by_id"):
        method = getattr(runtime, name, None)
        if callable(method):
            method(thread_id)
            return
    if isinstance(runtime, dict):
        runtime.pop(thread_id, None)


def _repair_state_thread_path(runtime: Any, thread_id: str, rollout_path: Path) -> None:
    if runtime is None:
        return
    for name in ("update_thread_rollout_path", "repair_thread_rollout_path", "set_thread_rollout_path"):
        method = getattr(runtime, name, None)
        if callable(method):
            method(thread_id, rollout_path)
            return
    paths = getattr(runtime, "paths_by_id", None)
    if isinstance(paths, dict):
        paths[thread_id] = Path(rollout_path)
        return
    if isinstance(runtime, dict):
        runtime[thread_id] = Path(rollout_path)


def read_thread_item_from_rollout(path: Path) -> ThreadItem | None:
    """Read a single rollout into the same summary shape used by listing."""

    return _build_thread_item(
        Path(path),
        allowed_sources=set(),
        model_providers=None,
        cwd_filters=None,
        default_provider="",
        updated_at=None,
    )


def read_head_for_summary(path: Path, limit: int = HEAD_RECORD_LIMIT) -> list[Any]:
    """Read up to ``HEAD_RECORD_LIMIT`` persisted summary records from a rollout."""

    head: list[Any] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if len(head) >= limit:
                break
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                rollout_line = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            item_type = rollout_line.get("type")
            if item_type in {"session_meta", "response_item"}:
                head.append(rollout_line.get("payload"))
    return head


def read_session_meta_line(path: Path) -> SessionMetaLine:
    """Read the first rollout item as ``SessionMetaLine``."""

    head = read_head_for_summary(path)
    if not head:
        raise ValueError(f"rollout at {Path(path)} is empty")
    first = head[0]
    if not isinstance(first, dict):
        raise ValueError(f"rollout at {Path(path)} does not start with session metadata")
    try:
        return SessionMetaLine.from_mapping(first)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"rollout at {Path(path)} does not start with session metadata") from exc


def session_index_path(codex_home: Path) -> Path:
    return Path(codex_home) / SESSION_INDEX_FILE


def count_session_rollout_files(codex_home: Path) -> int:
    """Count persisted session JSONL rollout files below ``<codex_home>/sessions``."""

    sessions_dir = Path(codex_home) / SESSIONS_SUBDIR
    if not sessions_dir.exists():
        return 0
    return sum(1 for path in sessions_dir.rglob("*.jsonl") if path.is_file())


def append_response_item_to_rollout(path: Path, payload: Mapping[str, Any], *, timestamp: str | None = None) -> None:
    """Append one persisted Responses item payload to an existing rollout JSONL."""

    rollout_path = Path(path)
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "timestamp": timestamp or _format_rfc3339(datetime.now(timezone.utc)),
        "type": "response_item",
        "payload": dict(payload),
    }
    with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(line, separators=(",", ":"), ensure_ascii=False))
        file.write("\n")


def append_event_msg_to_rollout(path: Path, event: EventMsg | Mapping[str, Any], *, timestamp: str | None = None) -> None:
    """Append one persisted protocol event payload to an existing rollout JSONL."""

    event_payload = event.to_mapping() if isinstance(event, EventMsg) else dict(event)
    rollout_path = Path(path)
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "timestamp": timestamp or _format_rfc3339(datetime.now(timezone.utc)),
        "type": "event_msg",
        "payload": event_payload,
    }
    with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(line, separators=(",", ":"), ensure_ascii=False))
        file.write("\n")


def append_turn_context_to_rollout(
    path: Path,
    cwd: Path | str,
    *,
    timestamp: str | None = None,
    turn_context: TurnContextItem | Mapping[str, Any] | None = None,
) -> None:
    """Append a turn context item that records the cwd for the next resumed turn."""

    rollout_path = Path(path)
    rollout_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(turn_context, TurnContextItem):
        context_payload = turn_context.to_mapping()
    elif turn_context is not None:
        context_payload = dict(turn_context)
    else:
        # A bare context is preferable to fabricated model/permission state;
        # rollout reconstruction already treats bare contexts as non-hydrating.
        context_payload = {"cwd": os.fspath(cwd)}
    line = {
        "timestamp": timestamp or _format_rfc3339(datetime.now(timezone.utc)),
        "type": "turn_context",
        "payload": context_payload,
    }
    with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(line, separators=(",", ":"), ensure_ascii=False))
        file.write("\n")


def append_turn_to_rollout(
    path: Path,
    user_payload: Mapping[str, Any] | None,
    response_payloads: Iterable[Mapping[str, Any]],
    *,
    timestamp: str | None = None,
    cwd: Path | str | None = None,
    turn_context: TurnContextItem | Mapping[str, Any] | None = None,
) -> None:
    """Append one resumed turn's user input and response items to an existing rollout."""

    resolved_timestamp = timestamp or _format_rfc3339(datetime.now(timezone.utc))
    if cwd is not None:
        append_turn_context_to_rollout(path, cwd, timestamp=resolved_timestamp, turn_context=turn_context)
    if user_payload is not None:
        append_response_item_to_rollout(path, user_payload, timestamp=resolved_timestamp)
    for payload in response_payloads:
        append_response_item_to_rollout(path, payload, timestamp=resolved_timestamp)


def append_turn_to_thread_rollout(
    codex_home: Path,
    thread_id: str,
    user_payload: Mapping[str, Any] | None,
    response_payloads: Iterable[Mapping[str, Any]],
    *,
    timestamp: str | None = None,
    cwd: Path | str | None = None,
    turn_context: TurnContextItem | Mapping[str, Any] | None = None,
) -> Path | None:
    """Append one turn to an existing session rollout selected by thread id."""

    path = find_thread_path_by_id_str(codex_home, thread_id)
    if path is None:
        return None
    append_turn_to_rollout(
        path,
        user_payload,
        response_payloads,
        timestamp=timestamp,
        cwd=cwd,
        turn_context=turn_context,
    )
    return path


def append_turn_to_latest_thread_rollout(
    codex_home: Path,
    user_payload: Mapping[str, Any] | None,
    response_payloads: Iterable[Mapping[str, Any]],
    *,
    current_cwd: Path | None = None,
    include_all: bool = False,
    timestamp: str | None = None,
    turn_context: TurnContextItem | Mapping[str, Any] | None = None,
) -> Path | None:
    """Append one turn to the newest matching session rollout."""

    page = get_threads(
        codex_home,
        page_size=1,
        sort_key=ThreadSortKey.CREATED_AT,
        cwd_filters=None if include_all or current_cwd is None else (Path(current_cwd),),
        allowed_sources=("cli",),
    )
    if not page.items:
        return None
    path = page.items[0].path
    append_turn_to_rollout(
        path,
        user_payload,
        response_payloads,
        timestamp=timestamp,
        cwd=current_cwd,
        turn_context=turn_context,
    )
    return path


def find_session_rollout_containing_response_marker(codex_home: Path, marker: str) -> Path | None:
    """Find a session rollout whose response message content contains ``marker``."""

    if not marker:
        return None
    sessions_dir = Path(codex_home) / SESSIONS_SUBDIR
    if not sessions_dir.exists():
        return None
    for path in sessions_dir.rglob("*.jsonl"):
        if not path.is_file():
            continue
        if _rollout_response_items_contain_marker(path, marker):
            return path
    return None


def last_user_image_count_in_rollout(path: Path) -> int:
    """Return the image count from the last persisted user message in a rollout."""

    last_count = 0
    try:
        file = Path(path).open("r", encoding="utf-8")
    except OSError:
        return 0
    with file:
        for line in file:
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                item = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict) or item.get("type") != "response_item":
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "message" or payload.get("role") != "user":
                continue
            content = payload.get("content")
            if not isinstance(content, list | tuple):
                continue
            last_count = sum(
                1
                for entry in content
                if isinstance(entry, dict) and entry.get("type") == "input_image"
            )
    return last_count


def read_response_items_from_rollout(path: Path, *, max_items: int | None = None) -> tuple[ResponseItem, ...]:
    """Read persisted response items from a rollout JSONL in prompt order."""

    if max_items is not None and max_items <= 0:
        return ()
    items: list[ResponseItem] = []
    try:
        file = Path(path).open("r", encoding="utf-8")
    except OSError:
        return ()
    try:
        with file:
            for line in file:
                trimmed = line.strip()
                if not trimmed:
                    continue
                try:
                    rollout_line = json.loads(trimmed)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rollout_line, dict) or rollout_line.get("type") != "response_item":
                    continue
                payload = rollout_line.get("payload")
                if not isinstance(payload, dict):
                    continue
                try:
                    item = ResponseItem.from_mapping(payload)
                except (KeyError, TypeError, ValueError):
                    continue
                items.append(item)
                if max_items is not None and len(items) >= max_items:
                    break
    except UnicodeDecodeError:
        return ()
    return tuple(items)


def read_event_msgs_from_rollout(path: Path, *, max_items: int | None = None) -> tuple[EventMsg, ...]:
    """Read persisted protocol events from a rollout JSONL in prompt order."""

    if max_items is not None and max_items <= 0:
        return ()
    events: list[EventMsg] = []
    try:
        file = Path(path).open("r", encoding="utf-8")
    except OSError:
        return ()
    try:
        with file:
            for line in file:
                trimmed = line.strip()
                if not trimmed:
                    continue
                try:
                    rollout_line = json.loads(trimmed)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rollout_line, dict) or rollout_line.get("type") != "event_msg":
                    continue
                payload = rollout_line.get("payload")
                if not isinstance(payload, dict):
                    continue
                try:
                    event = EventMsg.from_mapping(payload)
                except (KeyError, TypeError, ValueError):
                    continue
                events.append(event)
                if max_items is not None and len(events) >= max_items:
                    break
    except UnicodeDecodeError:
        return ()
    return tuple(events)


def read_rollout_reconstruction_from_rollout(path: Path) -> RolloutReconstruction:
    """Reconstruct model-visible history and resume metadata from a rollout JSONL."""

    return _reconstruct_rollout_items(_read_reconstruction_rollout_items(path))


def read_model_history_from_rollout(path: Path) -> tuple[ResponseItem, ...]:
    """Reconstruct model-visible history from a rollout JSONL for resume."""

    return read_rollout_reconstruction_from_rollout(path).history


def _read_reconstruction_rollout_items(path: Path) -> tuple[_ParsedRolloutItem, ...]:
    items: list[_ParsedRolloutItem] = []
    try:
        file = Path(path).open("r", encoding="utf-8")
    except OSError:
        return ()
    try:
        with file:
            for line in file:
                trimmed = line.strip()
                if not trimmed:
                    continue
                try:
                    rollout_line = json.loads(trimmed)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rollout_line, dict):
                    continue
                payload = rollout_line.get("payload")
                if not isinstance(payload, dict):
                    continue
                item_type = rollout_line.get("type")
                if item_type == "response_item":
                    item = _response_item_from_rollout_payload(payload)
                    if item is not None:
                        items.append(_ParsedRolloutItem("response_item", item))
                elif item_type == "compacted":
                    compacted = _compacted_item_from_payload(payload)
                    if compacted is not None:
                        items.append(_ParsedRolloutItem("compacted", compacted))
                elif item_type == "event_msg":
                    event = _event_msg_from_rollout_payload(payload)
                    if event is not None:
                        items.append(_ParsedRolloutItem("event_msg", event))
                elif item_type == "turn_context":
                    turn_context_item = _turn_context_item_from_rollout_payload(payload)
                    if turn_context_item is not None:
                        items.append(_ParsedRolloutItem("turn_context", turn_context_item))
    except UnicodeDecodeError:
        return ()
    return tuple(items)


def _reconstruct_rollout_items(items: Sequence[_ParsedRolloutItem]) -> RolloutReconstruction:
    base_replacement_history: tuple[ResponseItem, ...] | None = None
    previous_turn_settings: PreviousTurnSettings | None = None
    reference_context_kind = "never"
    reference_context_item: TurnContextItem | None = None
    pending_rollback_turns = 0
    rollout_suffix: Sequence[_ParsedRolloutItem] = items
    active_segment: _ActiveReplaySegment | None = None

    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if item.type == "compacted" and isinstance(item.payload, CompactedItem):
            active_segment = active_segment or _ActiveReplaySegment()
            if active_segment.reference_context_kind == "never":
                active_segment.reference_context_kind = "cleared"
                active_segment.reference_context_item = None
            if active_segment.base_replacement_history is None:
                replacement = _replacement_history_from_compacted(item.payload)
                if replacement is not None:
                    active_segment.base_replacement_history = replacement
                    rollout_suffix = items[index + 1 :]
        elif item.type == "event_msg" and isinstance(item.payload, EventMsg):
            event = item.payload
            rollback_turns = _thread_rollback_turn_count_from_event(event)
            if rollback_turns is not None:
                pending_rollback_turns = _saturating_add_usize(pending_rollback_turns, rollback_turns)
            elif event.type in {"task_complete", "turn_complete"}:
                active_segment = active_segment or _ActiveReplaySegment()
                if active_segment.turn_id is None:
                    active_segment.turn_id = _event_turn_id(event)
            elif event.type == "turn_aborted":
                turn_id = _event_turn_id(event)
                if active_segment is not None:
                    if active_segment.turn_id is None:
                        active_segment.turn_id = turn_id
                elif turn_id is not None:
                    active_segment = _ActiveReplaySegment(turn_id=turn_id)
            elif event.type == "user_message":
                active_segment = active_segment or _ActiveReplaySegment()
                active_segment.counts_as_user_turn = True
            elif event.type in {"task_started", "turn_started"}:
                turn_id = _event_turn_id(event)
                if active_segment is not None and _turn_ids_are_compatible(active_segment.turn_id, turn_id):
                    (
                        base_replacement_history,
                        previous_turn_settings,
                        reference_context_kind,
                        reference_context_item,
                        pending_rollback_turns,
                    ) = _finalize_active_segment(
                        active_segment,
                        base_replacement_history,
                        previous_turn_settings,
                        reference_context_kind,
                        reference_context_item,
                        pending_rollback_turns,
                    )
                    active_segment = None
        elif item.type == "turn_context" and isinstance(item.payload, TurnContextItem):
            ctx = item.payload
            active_segment = active_segment or _ActiveReplaySegment()
            if active_segment.turn_id is None:
                active_segment.turn_id = ctx.turn_id
            if _turn_ids_are_compatible(active_segment.turn_id, ctx.turn_id):
                active_segment.previous_turn_settings = PreviousTurnSettings(
                    model=ctx.model,
                    realtime_active=ctx.realtime_active,
                )
                if active_segment.reference_context_kind == "never":
                    active_segment.reference_context_kind = "latest"
                    active_segment.reference_context_item = ctx
        elif item.type == "response_item" and isinstance(item.payload, ResponseItem):
            active_segment = active_segment or _ActiveReplaySegment()
            active_segment.counts_as_user_turn = active_segment.counts_as_user_turn or _is_rollout_user_turn_boundary(
                item.payload
            )

        if (
            base_replacement_history is not None
            and previous_turn_settings is not None
            and reference_context_kind != "never"
        ):
            break

    if active_segment is not None:
        (
            base_replacement_history,
            previous_turn_settings,
            reference_context_kind,
            reference_context_item,
            pending_rollback_turns,
        ) = _finalize_active_segment(
            active_segment,
            base_replacement_history,
            previous_turn_settings,
            reference_context_kind,
            reference_context_item,
            pending_rollback_turns,
        )

    history: list[ResponseItem] = list(base_replacement_history or ())
    saw_legacy_compaction_without_replacement_history = False
    for item in rollout_suffix:
        if item.type == "response_item" and isinstance(item.payload, ResponseItem):
            history.append(item.payload)
        elif item.type == "compacted" and isinstance(item.payload, CompactedItem):
            replacement = _replacement_history_from_compacted(item.payload)
            if replacement is not None:
                history = list(replacement)
            else:
                saw_legacy_compaction_without_replacement_history = True
                history = list(_legacy_compacted_history(history, item.payload.message))
        elif item.type == "event_msg" and isinstance(item.payload, EventMsg):
            rollback_turns = _thread_rollback_turn_count_from_event(item.payload)
            if rollback_turns is not None:
                _drop_last_user_turns_from_history(history, rollback_turns)

    if reference_context_kind != "latest" or saw_legacy_compaction_without_replacement_history:
        reference_context_item = None

    return RolloutReconstruction(
        history=tuple(history),
        previous_turn_settings=previous_turn_settings,
        reference_context_item=reference_context_item,
    )


def _finalize_active_segment(
    active_segment: _ActiveReplaySegment,
    base_replacement_history: tuple[ResponseItem, ...] | None,
    previous_turn_settings: PreviousTurnSettings | None,
    reference_context_kind: str,
    reference_context_item: TurnContextItem | None,
    pending_rollback_turns: int,
) -> tuple[tuple[ResponseItem, ...] | None, PreviousTurnSettings | None, str, TurnContextItem | None, int]:
    if base_replacement_history is None and active_segment.base_replacement_history is not None:
        base_replacement_history = active_segment.base_replacement_history

    if pending_rollback_turns > 0:
        if active_segment.counts_as_user_turn:
            pending_rollback_turns -= 1
        return (
            base_replacement_history,
            previous_turn_settings,
            reference_context_kind,
            reference_context_item,
            pending_rollback_turns,
        )

    if previous_turn_settings is None and active_segment.counts_as_user_turn:
        previous_turn_settings = active_segment.previous_turn_settings
    if reference_context_kind == "never" and (
        active_segment.counts_as_user_turn or active_segment.reference_context_kind == "cleared"
    ):
        reference_context_kind = active_segment.reference_context_kind
        reference_context_item = active_segment.reference_context_item
    return (
        base_replacement_history,
        previous_turn_settings,
        reference_context_kind,
        reference_context_item,
        pending_rollback_turns,
    )


def _response_item_from_rollout_payload(payload: Mapping[str, Any]) -> ResponseItem | None:
    try:
        return ResponseItem.from_mapping(payload)
    except (KeyError, TypeError, ValueError):
        return None


def _event_msg_from_rollout_payload(payload: Mapping[str, Any]) -> EventMsg | None:
    try:
        return EventMsg.from_mapping(payload)
    except (KeyError, TypeError, ValueError):
        return None


def _turn_context_item_from_rollout_payload(payload: Mapping[str, Any]) -> TurnContextItem | None:
    try:
        return TurnContextItem.from_mapping(payload)
    except (KeyError, TypeError, ValueError):
        return None


def _compacted_item_from_payload(payload: Mapping[str, Any]) -> CompactedItem | None:
    try:
        return CompactedItem.from_mapping(payload)
    except (KeyError, TypeError, ValueError):
        return None


def _compacted_replacement_history(payload: Mapping[str, Any]) -> tuple[ResponseItem, ...] | None:
    compacted = _compacted_item_from_payload(payload)
    if compacted is None:
        return None
    return _replacement_history_from_compacted(compacted)


def _replacement_history_from_compacted(compacted: CompactedItem) -> tuple[ResponseItem, ...] | None:
    if compacted.replacement_history is None:
        return None
    items: list[ResponseItem] = []
    for raw_item in compacted.replacement_history:
        if not isinstance(raw_item, Mapping):
            continue
        item = _response_item_from_rollout_payload(raw_item)
        if item is not None:
            items.append(item)
    return tuple(items)


def _legacy_compacted_history(history: Sequence[ResponseItem], message: str) -> tuple[ResponseItem, ...]:
    compacted_history = [item for item in history if _is_rollout_user_turn_boundary(item)]
    summary = _response_item_from_rollout_payload(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": message}],
        }
    )
    if summary is not None:
        compacted_history.append(summary)
    return tuple(compacted_history)


def _thread_rollback_turn_count(payload: Mapping[str, Any]) -> int | None:
    try:
        event = EventMsg.from_mapping(payload)
    except (KeyError, TypeError, ValueError):
        return None
    if event.type != "thread_rolled_back":
        return None
    rollback = event.payload
    if isinstance(rollback, ThreadRolledBackEvent):
        return rollback.num_turns
    if isinstance(rollback, Mapping):
        try:
            return int(rollback["num_turns"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _thread_rollback_turn_count_from_event(event: EventMsg) -> int | None:
    if event.type != "thread_rolled_back":
        return None
    rollback = event.payload
    if isinstance(rollback, ThreadRolledBackEvent):
        return rollback.num_turns
    if isinstance(rollback, Mapping):
        try:
            return int(rollback["num_turns"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _event_turn_id(event: EventMsg) -> str | None:
    payload = event.payload
    if isinstance(payload, Mapping):
        value = payload.get("turn_id")
        return str(value) if value is not None else None
    value = getattr(payload, "turn_id", None)
    return str(value) if value is not None else None


def _turn_ids_are_compatible(active_turn_id: str | None, item_turn_id: str | None) -> bool:
    return active_turn_id is None or item_turn_id is None or active_turn_id == item_turn_id


def _is_rollout_user_turn_boundary(item: ResponseItem) -> bool:
    from pycodex.core.thread_rollout_truncation import is_user_turn_boundary

    return is_user_turn_boundary(item)


def _saturating_add_usize(left: int, right: int) -> int:
    value = left + right
    return value if value >= 0 else left


def _drop_last_user_turns_from_history(history: list[ResponseItem], num_turns: int) -> None:
    if num_turns <= 0:
        return
    from pycodex.core.thread_rollout_truncation import is_user_turn_boundary

    user_positions = [index for index, item in enumerate(history) if is_user_turn_boundary(item)]
    if not user_positions:
        return
    if num_turns >= len(user_positions):
        cut_index = user_positions[0]
    else:
        cut_index = user_positions[len(user_positions) - num_turns]
    while cut_index > 0 and _is_pre_turn_context_update(history[cut_index - 1]):
        cut_index -= 1
    del history[cut_index:]


def _is_pre_turn_context_update(item: ResponseItem) -> bool:
    if item.type != "message":
        return False
    if item.role == "developer":
        return True
    if item.role != "user":
        return False
    from pycodex.core.thread_rollout_truncation import is_user_turn_boundary

    return not is_user_turn_boundary(item)


def materialize_session_rollout(
    codex_home: Path,
    meta: SessionMeta,
    *,
    ephemeral: bool = False,
    git: GitInfo | None = None,
) -> Path | None:
    """Create the initial session rollout JSONL unless the thread is ephemeral."""

    if ephemeral:
        return None
    timestamp = meta.timestamp
    date = timestamp[:10]
    year, month, day = date[:4], date[5:7], date[8:10]
    file_timestamp = timestamp.replace(":", "-").replace("+00-00", "Z")
    path = Path(codex_home) / SESSIONS_SUBDIR / year / month / day / f"rollout-{file_timestamp}-{meta.id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "timestamp": timestamp,
        "type": "session_meta",
        "payload": SessionMetaLine(meta=meta, git=git).to_mapping(),
    }
    path.write_text(json.dumps(line, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def _rollout_response_items_contain_marker(path: Path, marker: str) -> bool:
    try:
        file = Path(path).open("r", encoding="utf-8")
    except OSError:
        return False
    with file:
        for index, line in enumerate(file):
            if index == 0:
                continue
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                item = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict) or item.get("type") != "response_item":
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "message":
                continue
            if marker in json.dumps(payload.get("content"), ensure_ascii=False):
                return True
    return False


def append_thread_name(codex_home: Path, thread_id: str | uuid.UUID, name: str) -> None:
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    append_session_index_entry(
        codex_home,
        SessionIndexEntry(id=str(thread_id), thread_name=name, updated_at=updated_at),
    )


def append_session_index_entry(codex_home: Path, entry: SessionIndexEntry) -> None:
    path = session_index_path(codex_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(entry.to_mapping(), separators=(",", ":")))
        file.write("\n")


def _thread_ids_matching_search_term(codex_home: Path, search_term: str) -> set[str]:
    matches: set[str] = set()
    if search_term == "":
        return matches
    for entry in _read_index_entries(codex_home):
        if entry.thread_name.strip() and search_term in entry.thread_name:
            matches.add(entry.id)
    return matches


def find_thread_name_by_id(codex_home: Path, thread_id: str | uuid.UUID) -> str | None:
    entry = _scan_index_from_end(codex_home, lambda candidate: candidate.id == str(thread_id))
    return entry.thread_name if entry is not None else None


def find_thread_names_by_ids(codex_home: Path, thread_ids: Iterable[str | uuid.UUID]) -> dict[str, str]:
    wanted = {str(thread_id) for thread_id in thread_ids}
    if not wanted:
        return {}
    names: dict[str, str] = {}
    for entry in _read_index_entries(codex_home):
        if entry.id in wanted and entry.thread_name.strip():
            names[entry.id] = entry.thread_name
    return names


def find_thread_meta_by_name_str(codex_home: Path, name: str, state_db_ctx: Any = None) -> tuple[Path, SessionMetaLine] | None:
    """Find the newest indexed thread name with a readable rollout header."""

    if not name.strip():
        return None

    seen: set[str] = set()
    for entry in reversed(_read_index_entries(codex_home)):
        if entry.id in seen:
            continue
        seen.add(entry.id)
        if entry.thread_name != name:
            continue
        path = find_thread_path_by_id_str(codex_home, entry.id, state_db_ctx)
        if path is None:
            continue
        try:
            return path, read_session_meta_line(path)
        except ValueError:
            continue
    return None


def find_thread_path_by_id_str(codex_home: Path, id_str: str, state_db_ctx: Any = None) -> Path | None:
    state_path = _state_db_thread_path_by_id(state_db_ctx, id_str, archived=False)
    if state_path is not None:
        return state_path
    return _find_thread_path_by_id_str_in_subdir(codex_home, SESSIONS_SUBDIR, id_str)


find_conversation_path_by_id_str = find_thread_path_by_id_str


def find_archived_thread_path_by_id_str(codex_home: Path, id_str: str, state_db_ctx: Any = None) -> Path | None:
    state_path = _state_db_thread_path_by_id(state_db_ctx, id_str, archived=True)
    if state_path is not None:
        return state_path
    return _find_thread_path_by_id_str_in_subdir(codex_home, ARCHIVED_SESSIONS_SUBDIR, id_str)


def _state_db_thread_path_by_id(state_db_ctx: Any, id_str: str, *, archived: bool) -> Path | None:
    if state_db_ctx is None:
        return None
    finder = getattr(state_db_ctx, "find_thread_path_by_id", None)
    if callable(finder):
        try:
            value = finder(id_str, archived=archived)
        except TypeError:
            value = finder(id_str)
        return Path(value) if value is not None else None
    finder = getattr(state_db_ctx, "thread_path_by_id", None)
    if callable(finder):
        value = finder(id_str)
        return Path(value) if value is not None else None
    paths = getattr(state_db_ctx, "paths_by_id", None)
    if isinstance(paths, Mapping):
        value = paths.get(id_str)
        return Path(value) if value is not None else None
    if isinstance(state_db_ctx, Mapping):
        value = state_db_ctx.get(id_str)
        return Path(value) if value is not None else None
    return None


def _find_thread_path_by_id_str_in_subdir(codex_home: Path, subdir: str, id_str: str) -> Path | None:
    try:
        uuid.UUID(id_str)
    except ValueError:
        return None

    root = Path(codex_home) / subdir
    if not root.exists():
        return None
    matches = sorted(root.rglob(f"*{id_str}*.jsonl"))
    return matches[0] if matches else None


def _scan_index_from_end(codex_home: Path, predicate: Callable[[SessionIndexEntry], bool]) -> SessionIndexEntry | None:
    for entry in reversed(_read_index_entries(codex_home)):
        if predicate(entry):
            return entry
    return None


def _read_index_entries(codex_home: Path) -> list[SessionIndexEntry]:
    path = session_index_path(codex_home)
    if not path.exists():
        return []
    entries: list[SessionIndexEntry] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                data = json.loads(trimmed)
                entries.append(SessionIndexEntry.from_mapping(data))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return entries


@dataclass(frozen=True)
class _RolloutCandidate:
    created_at: datetime
    rollout_id: str
    path: Path
    updated_at: datetime | None = None

    def sort_timestamp(self, sort_key: ThreadSortKey) -> datetime:
        if sort_key is ThreadSortKey.UPDATED_AT:
            return self.updated_at or datetime.fromtimestamp(0, timezone.utc)
        return self.created_at


@dataclass
class _HeadSummary:
    saw_session_meta: bool = False
    thread_id: str | None = None
    first_user_message: str | None = None
    preview: str | None = None
    cwd: Path | None = None
    git_branch: str | None = None
    git_sha: str | None = None
    git_origin_url: str | None = None
    source: str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    model_provider: str | None = None
    cli_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _coerce_sort_key(sort_key: ThreadSortKey | str) -> ThreadSortKey:
    if isinstance(sort_key, ThreadSortKey):
        return sort_key
    normalized = str(sort_key)
    try:
        return ThreadSortKey(normalized)
    except ValueError:
        if normalized in {"CreatedAt", "createdAt"}:
            return ThreadSortKey.CREATED_AT
        if normalized in {"UpdatedAt", "updatedAt"}:
            return ThreadSortKey.UPDATED_AT
        raise


def _state_db_sort_key_value(sort_key: ThreadSortKey | str) -> str:
    return _coerce_sort_key(sort_key).value


def _state_db_sort_direction_value(sort_direction: SortDirection | str) -> str:
    if isinstance(sort_direction, SortDirection):
        return sort_direction.value
    normalized = str(sort_direction)
    try:
        return SortDirection(normalized).value
    except ValueError:
        if normalized in {"Asc", "asc"}:
            return SortDirection.ASC.value
        if normalized in {"Desc", "desc"}:
            return SortDirection.DESC.value
        raise


def _state_db_session_source_value(source: SessionSource) -> str:
    if source.type == "custom" and source.custom is not None:
        return json.dumps({"custom": source.custom}, separators=(",", ":"), ensure_ascii=False)
    if source.type == "internal":
        return json.dumps({"internal": str(source.internal_source)}, separators=(",", ":"), ensure_ascii=False)
    if source.type == "subagent":
        return json.dumps({"subagent": str(source.subagent_source)}, separators=(",", ":"), ensure_ascii=False)
    return str(source)


def _warn_on_codex_home_mismatch(context: Any, codex_home: Path | str) -> None:
    getter = getattr(context, "codex_home", None)
    actual = getter() if callable(getter) else getattr(context, "codex_home_value", None)
    if actual is None:
        return
    _ = Path(actual) == Path(codex_home)


def _state_db_page_items(page: Any) -> Sequence[Any]:
    if isinstance(page, Mapping):
        items = page.get("items", ())
    else:
        items = getattr(page, "items", ())
    if callable(items):
        items = items()
    return items if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)) else ()


def _state_db_page_with_items(page: Any, items: list[Any]) -> Any:
    if isinstance(page, Mapping):
        result = dict(page)
        result["items"] = items
        return result
    try:
        setattr(page, "items", items)
        return page
    except Exception:
        return {"items": items}


def _state_db_item_rollout_path(item: Any) -> Path | None:
    value = item.get("rollout_path") if isinstance(item, Mapping) else getattr(item, "rollout_path", None)
    return Path(value) if value is not None else None


def _state_db_item_id(item: Any) -> Any:
    return item.get("id") if isinstance(item, Mapping) else getattr(item, "id", None)


def _repair_state_metadata(metadata: Any, rollout_path: Path, archived_only: bool | None) -> Any:
    cwd = normalize_cwd_for_state_db(Path(_metadata_value(metadata, "cwd", ".")))
    updated_at = _metadata_value(metadata, "updated_at", None)
    archived_at = _metadata_value(metadata, "archived_at", None)
    if archived_only is True and archived_at is None:
        archived_at = updated_at
    elif archived_only is False:
        archived_at = None
    if isinstance(metadata, Mapping):
        repaired = dict(metadata)
        repaired["rollout_path"] = rollout_path
        repaired["cwd"] = cwd
        if archived_at is not None:
            repaired["archived_at"] = archived_at
        elif "archived_at" in repaired:
            repaired["archived_at"] = None
        return repaired
    updates = {"rollout_path": rollout_path, "cwd": cwd}
    if hasattr(metadata, "archived_at"):
        updates["archived_at"] = archived_at
    try:
        return replace(metadata, **updates)
    except TypeError:
        for key, value in updates.items():
            try:
                setattr(metadata, key, value)
            except Exception:
                pass
        return metadata


def _metadata_value(metadata: Any, name: str, default: Any = None) -> Any:
    if isinstance(metadata, Mapping):
        return metadata.get(name, default)
    return getattr(metadata, name, default)


def _coerce_layout(layout: ThreadListLayout | str) -> ThreadListLayout:
    if isinstance(layout, ThreadListLayout):
        return layout
    normalized = str(layout)
    try:
        return ThreadListLayout(normalized)
    except ValueError:
        if normalized in {"NestedByDate", "nestedByDate"}:
            return ThreadListLayout.NESTED_BY_DATE
        if normalized == "Flat":
            return ThreadListLayout.FLAT
        raise


def _collect_rollout_candidates(
    root: Path,
    layout: ThreadListLayout,
    sort_key: ThreadSortKey,
) -> tuple[list[_RolloutCandidate], int, bool]:
    candidates: list[_RolloutCandidate] = []
    scanned = 0
    reached_scan_cap = False

    for path in _iter_rollout_files(root, layout):
        parsed = parse_timestamp_uuid_from_filename(path.name)
        if parsed is None:
            continue
        if scanned >= MAX_SCAN_FILES:
            reached_scan_cap = True
            break
        created_at, rollout_id = parsed
        scanned += 1
        updated_at = _file_modified_time(path)
        candidates.append(_RolloutCandidate(created_at, rollout_id, path, updated_at))

    if sort_key is ThreadSortKey.UPDATED_AT:
        candidates.sort(key=lambda item: (item.sort_timestamp(sort_key), item.rollout_id), reverse=True)
    else:
        candidates.sort(key=lambda item: (item.created_at, item.rollout_id), reverse=True)
    return candidates, scanned, reached_scan_cap


def _iter_rollout_files(root: Path, layout: ThreadListLayout) -> Iterable[Path]:
    if layout is ThreadListLayout.FLAT:
        try:
            entries = sorted(root.iterdir(), key=lambda item: item.name, reverse=True)
        except OSError:
            return []
        return (entry for entry in entries if entry.is_file() and entry.name.startswith("rollout-"))
    return root.rglob("rollout-*.jsonl")


def _file_modified_time(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None


def _build_next_cursor(items: Sequence[ThreadItem], sort_key: ThreadSortKey) -> Cursor | None:
    if not items:
        return None
    last = items[-1]
    if sort_key is ThreadSortKey.CREATED_AT:
        parsed = parse_timestamp_uuid_from_filename(last.path.name)
        return Cursor(parsed[0]) if parsed is not None else None
    if last.updated_at is None:
        return None
    return parse_cursor(last.updated_at)


def _state_thread_sort_timestamp(item: ThreadItem, sort_key: ThreadSortKey) -> datetime | None:
    value = item.created_at if sort_key is ThreadSortKey.CREATED_AT else item.updated_at
    if value is None:
        return None
    parsed = parse_cursor(value)
    return None if parsed is None else parsed.timestamp


def _state_next_cursor(items: Sequence[ThreadItem], sort_key: ThreadSortKey) -> Cursor | None:
    if not items:
        return None
    timestamp = _state_thread_sort_timestamp(items[-1], sort_key)
    return Cursor(timestamp) if timestamp is not None else None


def _build_thread_item(
    path: Path,
    allowed_sources: set[str],
    model_providers: Sequence[str] | None,
    cwd_filters: Sequence[Path] | None,
    default_provider: str,
    updated_at: str | None,
) -> ThreadItem | None:
    summary = _read_head_summary(path, HEAD_RECORD_LIMIT)
    latest_cwd = _read_latest_turn_context_cwd(path)
    if latest_cwd is not None:
        summary.cwd = latest_cwd
    if allowed_sources and (summary.source is None or summary.source not in allowed_sources):
        return None
    if not _matches_provider(summary.model_provider, model_providers, default_provider):
        return None
    if not _matches_cwd(summary.cwd, cwd_filters):
        return None
    if not summary.saw_session_meta or summary.preview is None:
        return None

    item_updated_at = summary.updated_at or updated_at or summary.created_at
    return ThreadItem(
        path=Path(path),
        thread_id=summary.thread_id,
        first_user_message=summary.first_user_message,
        preview=summary.preview,
        cwd=summary.cwd,
        git_branch=summary.git_branch,
        git_sha=summary.git_sha,
        git_origin_url=summary.git_origin_url,
        source=summary.source,
        agent_nickname=summary.agent_nickname,
        agent_role=summary.agent_role,
        model_provider=summary.model_provider,
        cli_version=summary.cli_version,
        created_at=summary.created_at,
        updated_at=item_updated_at,
    )


def _read_head_summary(path: Path, head_limit: int) -> _HeadSummary:
    summary = _HeadSummary()
    lines_scanned = 0
    try:
        file = Path(path).open("r", encoding="utf-8")
    except OSError:
        return summary

    with file:
        while (
            lines_scanned < head_limit
            or (
                summary.saw_session_meta
                and (summary.preview is None or summary.first_user_message is None)
                and lines_scanned < head_limit + USER_EVENT_SCAN_LIMIT
            )
        ):
            line = file.readline()
            if not line:
                break
            trimmed = line.strip()
            if not trimmed:
                continue
            lines_scanned += 1
            try:
                rollout_line = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            if not isinstance(rollout_line, dict):
                continue
            item_type = rollout_line.get("type")
            payload = rollout_line.get("payload")
            timestamp = rollout_line.get("timestamp")

            if item_type == "session_meta":
                if summary.saw_session_meta or not isinstance(payload, dict):
                    continue
                try:
                    meta_line = SessionMetaLine.from_mapping(payload)
                except (KeyError, TypeError, ValueError):
                    continue
                meta = meta_line.meta
                summary.saw_session_meta = True
                summary.thread_id = meta.id
                summary.cwd = Path(meta.cwd)
                summary.source = meta.source
                summary.agent_nickname = meta.agent_nickname
                summary.agent_role = meta.agent_role
                summary.model_provider = meta.model_provider
                summary.cli_version = meta.cli_version
                summary.created_at = meta.timestamp
                if meta_line.git is not None:
                    summary.git_branch = meta_line.git.branch
                    summary.git_sha = meta_line.git.commit_hash
                    summary.git_origin_url = meta_line.git.repository_url
            elif item_type == "response_item":
                if summary.created_at is None and isinstance(timestamp, str):
                    summary.created_at = timestamp
                preview, is_user_message = _response_item_preview(payload)
                if preview is None:
                    continue
                if summary.preview is None:
                    summary.preview = preview
                if is_user_message and summary.first_user_message is None:
                    summary.first_user_message = preview
            elif item_type == "turn_context":
                cwd = _turn_context_cwd(payload)
                if cwd is not None:
                    summary.cwd = cwd
            elif item_type == "event_msg":
                preview, is_user_message = _event_msg_preview(payload)
                if preview is None:
                    continue
                if summary.preview is None:
                    summary.preview = preview
                if is_user_message and summary.first_user_message is None:
                    summary.first_user_message = preview

            if (
                lines_scanned >= head_limit
                and summary.saw_session_meta
                and summary.preview is not None
                and summary.first_user_message is not None
            ):
                break
    return summary


def _turn_context_cwd(payload: Any) -> Path | None:
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    return Path(cwd)


def _read_latest_turn_context_cwd(path: Path) -> Path | None:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for line in reversed(text.splitlines()):
        trimmed = line.strip()
        if not trimmed:
            continue
        try:
            rollout_line = json.loads(trimmed)
        except json.JSONDecodeError:
            continue
        if not isinstance(rollout_line, dict) or rollout_line.get("type") != "turn_context":
            continue
        cwd = _turn_context_cwd(rollout_line.get("payload"))
        if cwd is not None:
            return cwd
    return None


def _event_msg_preview(payload: Any) -> tuple[str | None, bool]:
    if not isinstance(payload, dict):
        return None, False

    event_type = _normalize_event_type(payload.get("type"))
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload

    if event_type == "usermessage":
        message = body.get("message")
        text = _strip_user_message_prefix(message if isinstance(message, str) else "")
        if text:
            return text, True
        if _has_items(body.get("images")) or _has_items(body.get("local_images")):
            return "[Image]", True
        return None, True

    if event_type == "threadgoalupdated":
        goal = body.get("goal")
        if isinstance(goal, dict):
            objective = goal.get("objective")
            if isinstance(objective, str) and objective.strip():
                return objective.strip(), False
    return None, False


def _response_item_preview(payload: Any) -> tuple[str | None, bool]:
    if not isinstance(payload, dict):
        return None, False
    if payload.get("type") != "message":
        return None, False
    role = payload.get("role")
    is_user_message = role == "user"
    text = _response_item_content_text(payload.get("content"))
    if text:
        return text, is_user_message
    if is_user_message and _response_item_content_has_image(payload.get("content")):
        return "[Image]", True
    return None, is_user_message


def _response_item_content_text(content: Any) -> str | None:
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    joined = "".join(parts).strip()
    return joined or None


def _response_item_content_has_image(content: Any) -> bool:
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        return False
    return any(isinstance(item, dict) and item.get("type") == "input_image" for item in content)


def _normalize_event_type(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value.lower() if character.isalnum())


def _strip_user_message_prefix(text: str) -> str:
    index = text.find(USER_MESSAGE_BEGIN)
    if index >= 0:
        return text[index + len(USER_MESSAGE_BEGIN) :].strip()
    return text.strip()


def _has_items(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and bool(value)


def _matches_provider(
    session_provider: str | None,
    model_providers: Sequence[str] | None,
    default_provider: str,
) -> bool:
    if model_providers is None or len(model_providers) == 0:
        return True
    filters = {str(provider) for provider in model_providers}
    if session_provider is not None:
        return session_provider in filters
    return default_provider in filters


def _matches_cwd(cwd: Path | None, cwd_filters: Sequence[Path] | None) -> bool:
    if cwd_filters is None:
        return True
    if cwd is None:
        return False
    return any(_normalized_path(cwd) == _normalized_path(candidate) for candidate in cwd_filters)


def _config_value(config: object, name: str, *, default: object | None = None) -> object:
    if isinstance(config, Mapping):
        value = config.get(name, default)
    else:
        value = getattr(config, name, default)
    if callable(value):
        return value()
    if value is None:
        return default
    return value


def _config_path(config: object, name: str, *, default: Path | None = None) -> Path:
    value = _config_value(config, name, default=default)
    if value is None:
        raise AttributeError(f"config is missing {name}")
    return Path(os.fspath(value))


def _session_source_to_string(source: object | None) -> str:
    if source is None:
        return "vscode"
    raw = getattr(source, "value", source)
    if isinstance(raw, str):
        return raw
    serializer = getattr(source, "to_json", None)
    if callable(serializer):
        return str(serializer())
    return str(source)


def _optional_string(value: object | None) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _rollout_path_for_meta(codex_home: Path, meta: SessionMeta) -> Path:
    date = meta.timestamp[:10]
    year, month, day = date[:4], date[5:7], date[8:10]
    file_timestamp = meta.timestamp.replace(":", "-").replace("+00-00", "Z")
    return Path(codex_home) / SESSIONS_SUBDIR / year / month / day / f"rollout-{file_timestamp}-{meta.id}.jsonl"


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _require_keys(data: dict[str, Any], keys: Iterable[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise KeyError(", ".join(missing))


def _parse_rfc3339(token: str) -> datetime | None:
    normalized = token
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_rfc3339(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond == 0:
        timespec = "seconds"
    elif normalized.microsecond % 1000 == 0:
        timespec = "milliseconds"
    else:
        timespec = "microseconds"
    text = normalized.isoformat(timespec=timespec)
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text
