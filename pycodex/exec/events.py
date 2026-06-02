"""JSONL event types emitted by ``codex exec --json``.

Ported from ``codex/codex-rs/exec/src/exec_events.rs``.  The Rust source uses
serde-tagged enums; the Python port keeps the same external JSON shape with
small standard-library dataclasses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    AgentMessageItem,
    CallToolResult,
    CollabAgentToolCallItem,
    CommandExecutionItem,
    FileChangeItem,
    McpToolCallItem,
    ReasoningItem,
    TurnItem,
    WebSearchItem,
)

JsonValue = Any


class CommandExecutionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DECLINED = "declined"


class McpToolCallStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CollabToolCallStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CollabTool(str, Enum):
    SPAWN_AGENT = "spawn_agent"
    SEND_INPUT = "send_input"
    WAIT = "wait"
    CLOSE_AGENT = "close_agent"


class CollabAgentStatus(str, Enum):
    PENDING_INIT = "pending_init"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    ERRORED = "errored"
    SHUTDOWN = "shutdown"
    NOT_FOUND = "not_found"


class PatchApplyStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DECLINED = "declined"


class PatchChangeKind(str, Enum):
    ADD = "add"
    DELETE = "delete"
    UPDATE = "update"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0

    def to_mapping(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_output_tokens": self.reasoning_output_tokens,
        }


@dataclass(frozen=True)
class ThreadErrorEvent:
    message: str

    def to_mapping(self) -> dict[str, str]:
        return {"message": self.message}


@dataclass(frozen=True)
class ExecThreadItem:
    id: str
    type: str
    payload: Mapping[str, JsonValue]

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id, "type": self.type, **_to_json(dict(self.payload))}


@dataclass(frozen=True)
class ThreadEvent:
    type: str
    payload: Mapping[str, JsonValue]

    @classmethod
    def thread_started(cls, thread_id: str) -> "ThreadEvent":
        return cls("thread.started", {"thread_id": thread_id})

    @classmethod
    def turn_started(cls) -> "ThreadEvent":
        return cls("turn.started", {})

    @classmethod
    def turn_completed(cls, usage: Usage | None = None) -> "ThreadEvent":
        return cls("turn.completed", {"usage": usage or Usage()})

    @classmethod
    def turn_failed(cls, error: ThreadErrorEvent | str) -> "ThreadEvent":
        parsed_error = error if isinstance(error, ThreadErrorEvent) else ThreadErrorEvent(str(error))
        return cls("turn.failed", {"error": parsed_error})

    @classmethod
    def item_started(cls, item: ExecThreadItem) -> "ThreadEvent":
        return cls("item.started", {"item": item})

    @classmethod
    def item_updated(cls, item: ExecThreadItem) -> "ThreadEvent":
        return cls("item.updated", {"item": item})

    @classmethod
    def item_completed(cls, item: ExecThreadItem) -> "ThreadEvent":
        return cls("item.completed", {"item": item})

    @classmethod
    def error(cls, error: ThreadErrorEvent | str) -> "ThreadEvent":
        parsed_error = error if isinstance(error, ThreadErrorEvent) else ThreadErrorEvent(str(error))
        return cls("error", parsed_error.to_mapping())

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"type": self.type, **_to_json(dict(self.payload))}

    def to_json_line(self) -> str:
        return json.dumps(self.to_mapping(), ensure_ascii=False, separators=(",", ":"))


def error_item(id: str, message: str) -> ExecThreadItem:
    return ExecThreadItem(id, "error", {"message": message})


def agent_message_item(id: str, text: str) -> ExecThreadItem:
    return ExecThreadItem(id, "agent_message", {"text": text})


def reasoning_item(id: str, text: str) -> ExecThreadItem:
    return ExecThreadItem(id, "reasoning", {"text": text})


def command_execution_item(
    id: str,
    *,
    command: str,
    cwd: str | Path | None = None,
    process_id: str | None = None,
    source: str | None = None,
    command_actions: tuple[JsonValue, ...] | list[JsonValue] | None = None,
    aggregated_output: str = "",
    exit_code: int | None = None,
    duration_ms: int | None = None,
    status: JsonValue = CommandExecutionStatus.IN_PROGRESS,
) -> ExecThreadItem:
    payload: dict[str, JsonValue] = {
        "command": command,
        "aggregated_output": aggregated_output,
        "exit_code": exit_code,
        "status": _command_status(status),
    }
    if cwd is not None:
        payload["cwd"] = cwd.as_posix() if isinstance(cwd, Path) else str(cwd)
    if process_id is not None:
        payload["process_id"] = process_id
    if source is not None:
        payload["source"] = source
    if command_actions is not None:
        payload["command_actions"] = list(command_actions)
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    return ExecThreadItem(
        id,
        "command_execution",
        payload,
    )


def mcp_tool_call_item(id: str, item: McpToolCallItem) -> ExecThreadItem:
    result = _call_tool_result_to_mapping(item.result) if item.result is not None else None
    error = {"message": item.error.message} if item.error is not None else None
    return ExecThreadItem(
        id,
        "mcp_tool_call",
        {
            "server": item.server,
            "tool": item.tool,
            "arguments": item.arguments,
            "result": result,
            "error": error,
            "status": _mcp_status(item.status),
        },
    )


def collab_tool_call_item(
    id: str,
    *,
    tool: JsonValue,
    sender_thread_id: str,
    receiver_thread_ids: tuple[str, ...] | list[str],
    prompt: str | None = None,
    agents_states: Mapping[str, JsonValue] | None = None,
    status: JsonValue = CollabToolCallStatus.IN_PROGRESS,
) -> ExecThreadItem:
    return ExecThreadItem(
        id,
        "collab_tool_call",
        {
            "tool": _collab_tool(tool),
            "sender_thread_id": sender_thread_id,
            "receiver_thread_ids": list(receiver_thread_ids),
            "prompt": prompt,
            "agents_states": _collab_agents_states(agents_states or {}),
            "status": _collab_tool_call_status(status),
        },
    )


def file_change_item(id: str, item: FileChangeItem) -> ExecThreadItem:
    changes = [
        {
            "path": path.as_posix(),
            "kind": _patch_kind(change),
        }
        for path, change in item.changes.items()
    ]
    payload: dict[str, object] = {"changes": changes, "status": _patch_status(item.status)}
    if item.auto_approved is not None:
        payload["auto_approved"] = item.auto_approved
    if item.stdout is not None:
        payload["stdout"] = item.stdout
    if item.stderr is not None:
        payload["stderr"] = item.stderr
    return ExecThreadItem(id, "file_change", payload)


def web_search_item(id: str, item: WebSearchItem) -> ExecThreadItem:
    return ExecThreadItem(
        id,
        "web_search",
        {
            "query": item.query,
            "action": _web_search_action(item.action),
        },
    )


def todo_list_item(id: str, items: tuple[tuple[str, bool], ...] | list[tuple[str, bool]]) -> ExecThreadItem:
    return ExecThreadItem(
        id,
        "todo_list",
        {"items": [{"text": text, "completed": completed} for text, completed in items]},
    )


def exec_item_from_turn_item(item: TurnItem, id: str) -> ExecThreadItem | None:
    if item.type == "AgentMessage" and isinstance(item.item, AgentMessageItem):
        return agent_message_item(id, _agent_message_text(item.item))
    if item.type == "Reasoning" and isinstance(item.item, ReasoningItem):
        text = "\n".join(item.item.summary_text)
        if text.strip() == "":
            return None
        return reasoning_item(id, text)
    if item.type == "McpToolCall" and isinstance(item.item, McpToolCallItem):
        return mcp_tool_call_item(id, item.item)
    if item.type == "CommandExecution" and isinstance(item.item, CommandExecutionItem):
        return command_execution_item(
            id,
            command=item.item.command,
            cwd=item.item.cwd,
            process_id=item.item.process_id,
            source=item.item.source,
            command_actions=item.item.command_actions,
            aggregated_output=item.item.aggregated_output or "",
            exit_code=item.item.exit_code,
            duration_ms=item.item.duration_ms,
            status=item.item.status,
        )
    if item.type == "FileChange" and isinstance(item.item, FileChangeItem):
        return file_change_item(id, item.item)
    if item.type == "WebSearch" and isinstance(item.item, WebSearchItem):
        return web_search_item(id, item.item)
    if item.type == "CollabAgentToolCall" and isinstance(item.item, CollabAgentToolCallItem):
        return collab_tool_call_item(
            id,
            tool=item.item.tool,
            sender_thread_id=item.item.sender_thread_id,
            receiver_thread_ids=item.item.receiver_thread_ids,
            prompt=item.item.prompt,
            agents_states=item.item.agents_states,
            status=item.item.status,
        )
    return None


def final_message_from_turn_items(items: tuple[TurnItem, ...] | list[TurnItem]) -> str | None:
    for item in reversed(items):
        if item.type == "AgentMessage" and isinstance(item.item, AgentMessageItem):
            return _agent_message_text(item.item)
    for item in reversed(items):
        if item.type == "Plan":
            return getattr(item.item, "text", None)
    return None


def _agent_message_text(item: AgentMessageItem) -> str:
    return "".join(content.text for content in item.content)


def _call_tool_result_to_mapping(result: CallToolResult) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = {
        "content": list(result.content),
        "structured_content": result.structured_content,
    }
    if result.meta is not None:
        data["_meta"] = result.meta
    return data


def _mcp_status(status: JsonValue) -> str:
    raw = getattr(status, "value", status)
    if raw is None:
        return McpToolCallStatus.IN_PROGRESS.value
    if raw in {"inProgress", "InProgress", "in_progress"}:
        return McpToolCallStatus.IN_PROGRESS.value
    if raw in {"completed", "Completed"}:
        return McpToolCallStatus.COMPLETED.value
    if raw in {"failed", "Failed"}:
        return McpToolCallStatus.FAILED.value
    return str(raw)


def _collab_tool_call_status(status: JsonValue) -> str:
    raw = getattr(status, "value", status)
    if raw is None:
        return CollabToolCallStatus.IN_PROGRESS.value
    if raw in {"inProgress", "InProgress", "in_progress"}:
        return CollabToolCallStatus.IN_PROGRESS.value
    if raw in {"completed", "Completed"}:
        return CollabToolCallStatus.COMPLETED.value
    if raw in {"failed", "Failed"}:
        return CollabToolCallStatus.FAILED.value
    return str(raw)


def _collab_tool(tool: JsonValue) -> str:
    raw = getattr(tool, "value", tool)
    if raw in {"spawnAgent", "SpawnAgent", "spawn_agent"}:
        return CollabTool.SPAWN_AGENT.value
    if raw in {"sendInput", "SendInput", "send_input"}:
        return CollabTool.SEND_INPUT.value
    if raw in {"closeAgent", "CloseAgent", "close_agent"}:
        return CollabTool.CLOSE_AGENT.value
    if raw in {"resumeAgent", "ResumeAgent", "resume_agent", "wait", "Wait"}:
        return CollabTool.WAIT.value
    return str(raw)


def _collab_agent_status(status: JsonValue) -> str:
    raw = getattr(status, "value", status)
    aliases = {
        "pendingInit": CollabAgentStatus.PENDING_INIT.value,
        "PendingInit": CollabAgentStatus.PENDING_INIT.value,
        "pending_init": CollabAgentStatus.PENDING_INIT.value,
        "running": CollabAgentStatus.RUNNING.value,
        "Running": CollabAgentStatus.RUNNING.value,
        "interrupted": CollabAgentStatus.INTERRUPTED.value,
        "Interrupted": CollabAgentStatus.INTERRUPTED.value,
        "completed": CollabAgentStatus.COMPLETED.value,
        "Completed": CollabAgentStatus.COMPLETED.value,
        "errored": CollabAgentStatus.ERRORED.value,
        "Errored": CollabAgentStatus.ERRORED.value,
        "shutdown": CollabAgentStatus.SHUTDOWN.value,
        "Shutdown": CollabAgentStatus.SHUTDOWN.value,
        "notFound": CollabAgentStatus.NOT_FOUND.value,
        "NotFound": CollabAgentStatus.NOT_FOUND.value,
        "not_found": CollabAgentStatus.NOT_FOUND.value,
    }
    return aliases.get(str(raw), str(raw))


def _collab_agents_states(states: Mapping[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    return {
        str(thread_id): {
            "status": _collab_agent_status(_field(state, "status")),
            "message": _field(state, "message"),
        }
        for thread_id, state in states.items()
    }


def _command_status(status: JsonValue) -> str:
    raw = getattr(status, "value", status)
    if raw is None:
        return CommandExecutionStatus.IN_PROGRESS.value
    if raw in {"inProgress", "InProgress", "in_progress"}:
        return CommandExecutionStatus.IN_PROGRESS.value
    if raw in {"completed", "Completed"}:
        return CommandExecutionStatus.COMPLETED.value
    if raw in {"failed", "Failed"}:
        return CommandExecutionStatus.FAILED.value
    if raw in {"declined", "Declined"}:
        return CommandExecutionStatus.DECLINED.value
    return str(raw)


def _patch_status(status: JsonValue) -> str:
    raw = getattr(status, "value", status)
    if raw is None:
        return PatchApplyStatus.IN_PROGRESS.value
    if raw in {"inProgress", "InProgress", "in_progress"}:
        return PatchApplyStatus.IN_PROGRESS.value
    if raw in {"completed", "Completed"}:
        return PatchApplyStatus.COMPLETED.value
    if raw in {"failed", "Failed"}:
        return PatchApplyStatus.FAILED.value
    if raw in {"declined", "Declined"}:
        return PatchApplyStatus.DECLINED.value
    return str(raw)


def _patch_kind(change: JsonValue) -> str:
    kind = getattr(change, "type", None) or getattr(change, "kind", None)
    raw = getattr(kind, "value", kind)
    if raw == "add":
        return PatchChangeKind.ADD.value
    if raw == "delete":
        return PatchChangeKind.DELETE.value
    if raw in {"update", "Update"} or raw is None:
        return PatchChangeKind.UPDATE.value
    return str(raw)


def _web_search_action(action: JsonValue) -> dict[str, JsonValue]:
    if action is None:
        return {"type": "other"}
    if hasattr(action, "to_mapping") and callable(action.to_mapping):
        return _web_search_action(action.to_mapping())
    if not isinstance(action, Mapping):
        return {"type": "other"}
    action_type = _field(action, "type")
    if action_type == "search":
        data: dict[str, JsonValue] = {"type": "search"}
        query = _field(action, "query")
        queries = _field(action, "queries")
        if query is not None:
            data["query"] = query
        if queries is not None:
            data["queries"] = _to_json(queries)
        return data
    if action_type == "open_page":
        data = {"type": "open_page"}
        url = _field(action, "url")
        if url is not None:
            data["url"] = url
        return data
    if action_type == "find_in_page":
        data = {"type": "find_in_page"}
        url = _field(action, "url")
        pattern = _field(action, "pattern")
        if url is not None:
            data["url"] = url
        if pattern is not None:
            data["pattern"] = pattern
        return data
    if action_type == "other":
        return {"type": "other"}
    return {"type": "other"}


def _field(value: JsonValue, *names: str) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _to_json(value: JsonValue) -> JsonValue:
    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return value.to_mapping()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _to_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json(item) for item in value]
    return value


__all__ = [
    "CommandExecutionStatus",
    "CollabAgentStatus",
    "CollabTool",
    "CollabToolCallStatus",
    "ExecThreadItem",
    "McpToolCallStatus",
    "PatchApplyStatus",
    "PatchChangeKind",
    "ThreadErrorEvent",
    "ThreadEvent",
    "Usage",
    "agent_message_item",
    "collab_tool_call_item",
    "command_execution_item",
    "error_item",
    "exec_item_from_turn_item",
    "file_change_item",
    "final_message_from_turn_items",
    "mcp_tool_call_item",
    "reasoning_item",
    "todo_list_item",
    "web_search_item",
]
