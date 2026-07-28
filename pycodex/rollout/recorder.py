"""Rust-aligned owner for ``codex-rollout::recorder``."""

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
from pycodex.rollout import SESSIONS_SUBDIR

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
    file_timestamp = _rollout_filename_timestamp(timestamp)
    year, month, day = file_timestamp[:4], file_timestamp[5:7], file_timestamp[8:10]
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

from pycodex.rollout.config import _config_path, _config_value
from pycodex.rollout.list import ThreadItem, ThreadSortKey, _format_rfc3339, _rollout_filename_timestamp, _rollout_path_for_meta, find_thread_path_by_id_str, get_threads

__all__ = ['PreviousTurnSettings', 'RolloutReconstruction', 'RolloutRecorder', 'RolloutRecorderParams', 'RolloutWriterState', 'append_event_msg_to_rollout', 'append_response_item_to_rollout', 'append_rollout_item_to_path', 'append_turn_context_to_rollout', 'append_turn_to_latest_thread_rollout', 'append_turn_to_rollout', 'append_turn_to_thread_rollout', 'fill_missing_thread_item_metadata', 'find_session_rollout_containing_response_marker', 'last_user_image_count_in_rollout', 'materialize_session_rollout', 'read_event_msgs_from_rollout', 'read_model_history_from_rollout', 'read_response_items_from_rollout', 'read_rollout_reconstruction_from_rollout', 'thread_item_from_state_metadata']
