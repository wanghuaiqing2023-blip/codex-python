"""Semantic Python port of Rust ``codex-tui::chatwidget::tool_lifecycle``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/tool_lifecycle.rs``.

This module turns non-command tool events into transcript/history activity.
Python models history cells and active cells as semantic records while keeping
real rendering, defer queues, and command lifecycle handlers as explicit
neighboring boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::tool_lifecycle",
    source="codex/codex-rs/tui/src/chatwidget/tool_lifecycle.rs",
    status="complete",
)


class ThreadItemKind(Enum):
    COMMAND_EXECUTION = "CommandExecution"
    FILE_CHANGE = "FileChange"
    MCP_TOOL_CALL = "McpToolCall"
    COLLAB_AGENT_TOOL_CALL = "CollabAgentToolCall"
    OTHER = "Other"


class PatchApplyStatus(Enum):
    SUCCESS = "Success"
    FAILED = "Failed"


class CollabAgentTool(Enum):
    SPAWN_AGENT = "SpawnAgent"
    OTHER = "Other"


class CollabAgentToolCallStatus(Enum):
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    FAILED = "Failed"


@dataclass(frozen=True)
class McpError:
    message: str


@dataclass(frozen=True)
class McpResult:
    content: Any = None
    structured_content: Any = None


@dataclass
class ThreadItem:
    kind: ThreadItemKind
    id: Optional[str] = None
    status: Optional[Any] = None
    server: Optional[str] = None
    tool: Optional[Any] = None
    arguments: Optional[Any] = None
    result: Optional[McpResult] = None
    error: Optional[McpError] = None
    duration_ms: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def file_change(cls, status: PatchApplyStatus) -> "ThreadItem":
        return cls(ThreadItemKind.FILE_CHANGE, status=status)

    @classmethod
    def mcp_tool_call(
        cls,
        *,
        id: str,
        server: str,
        tool: str,
        arguments: Any = None,
        result: Optional[McpResult] = None,
        error: Optional[McpError] = None,
        duration_ms: Optional[int] = None,
    ) -> "ThreadItem":
        return cls(
            ThreadItemKind.MCP_TOOL_CALL,
            id=id,
            server=server,
            tool=tool,
            arguments=arguments,
            result=result,
            error=error,
            duration_ms=duration_ms,
        )

    @classmethod
    def collab_agent_tool_call(
        cls,
        *,
        id: str,
        tool: CollabAgentTool,
        status: CollabAgentToolCallStatus,
        payload: Optional[Dict[str, Any]] = None,
    ) -> "ThreadItem":
        return cls(
            ThreadItemKind.COLLAB_AGENT_TOOL_CALL,
            id=id,
            tool=tool,
            status=status,
            payload=payload or {},
        )


@dataclass
class HistoryCell:
    kind: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActiveWebSearchCell:
    call_id: str
    query: str = ""
    action: Optional[Any] = None
    completed: bool = False

    def update(self, action: Any, query: str) -> None:
        self.action = action
        self.query = query

    def complete(self) -> None:
        self.completed = True


@dataclass
class ActiveMcpToolCallCell:
    call_id: str
    invocation: Dict[str, Any]
    completed: bool = False
    duration_ms: int = 0
    result: Optional[Tuple[str, Any]] = None

    def complete(self, duration_ms: int, result: Tuple[str, Any]) -> Optional[HistoryCell]:
        self.completed = True
        self.duration_ms = max(duration_ms, 0)
        self.result = result
        if result[0] == "error":
            return HistoryCell("mcp_tool_call_error", {"call_id": self.call_id, "message": result[1]})
        return None


@dataclass
class DeferredQueue:
    started: List[ThreadItem] = field(default_factory=list)
    completed: List[ThreadItem] = field(default_factory=list)

    def push_item_started(self, item: ThreadItem) -> None:
        self.started.append(item)

    def push_item_completed(self, item: ThreadItem) -> None:
        self.completed.append(item)


@dataclass
class ToolLifecycleModel:
    cwd: Path = Path(".")
    animations: bool = True
    defer_items: bool = False
    history: List[HistoryCell] = field(default_factory=list)
    boxed_history: List[HistoryCell] = field(default_factory=list)
    active_cell: Optional[Any] = None
    had_work_activity: bool = False
    pending_collab_spawn_requests: Dict[str, Any] = field(default_factory=dict)
    deferred_queue: DeferredQueue = field(default_factory=DeferredQueue)
    answer_stream_flushes: int = 0
    active_cell_flushes: int = 0
    active_cell_revision: int = 0
    redraw_requests: int = 0
    command_started: List[ThreadItem] = field(default_factory=list)
    command_completed: List[ThreadItem] = field(default_factory=list)

    def on_patch_apply_begin(self, changes: Dict[Path, Any]) -> None:
        self.add_to_history(HistoryCell("patch_event", {"changes": changes, "cwd": self.cwd}))

    def on_view_image_tool_call(self, path: Path) -> None:
        self.flush_answer_stream_with_separator()
        self.add_to_history(HistoryCell("view_image_tool_call", {"path": path, "cwd": self.cwd}))
        self.request_redraw()

    def on_image_generation_begin(self) -> None:
        self.flush_answer_stream_with_separator()

    def on_image_generation_end(
        self,
        call_id: str,
        revised_prompt: Optional[str],
        saved_path: Optional[Path],
    ) -> None:
        self.flush_answer_stream_with_separator()
        self.add_to_history(
            HistoryCell(
                "image_generation_call",
                {"call_id": call_id, "revised_prompt": revised_prompt, "saved_path": saved_path},
            )
        )
        self.request_redraw()

    def on_file_change_completed(self, item: ThreadItem) -> None:
        self.defer_or_handle(
            lambda q: q.push_item_completed(item),
            lambda s: s.handle_file_change_completed_now(item),
        )

    def on_mcp_tool_call_started(self, item: ThreadItem) -> None:
        self.defer_or_handle(
            lambda q: q.push_item_started(item),
            lambda s: s.handle_mcp_tool_call_started_now(item),
        )

    def on_mcp_tool_call_completed(self, item: ThreadItem) -> None:
        self.defer_or_handle(
            lambda q: q.push_item_completed(item),
            lambda s: s.handle_mcp_tool_call_completed_now(item),
        )

    def on_web_search_begin(self, call_id: str) -> None:
        self.flush_answer_stream_with_separator()
        self.flush_active_cell()
        self.active_cell = ActiveWebSearchCell(call_id=call_id)
        self.bump_active_cell_revision()
        self.request_redraw()

    def on_web_search_end(self, call_id: str, query: str, action: Any) -> None:
        self.flush_answer_stream_with_separator()
        handled = False
        if isinstance(self.active_cell, ActiveWebSearchCell) and self.active_cell.call_id == call_id:
            self.active_cell.update(action, query)
            self.active_cell.complete()
            self.bump_active_cell_revision()
            self.flush_active_cell()
            handled = True
        if not handled:
            self.add_to_history(
                HistoryCell(
                    "web_search_call",
                    {"call_id": call_id, "query": query, "action": action},
                )
            )
        self.had_work_activity = True

    def on_collab_event(self, cell: HistoryCell) -> None:
        self.flush_answer_stream_with_separator()
        self.add_to_history(cell)
        self.request_redraw()

    def on_collab_agent_tool_call(self, item: ThreadItem) -> None:
        if item.kind is not ThreadItemKind.COLLAB_AGENT_TOOL_CALL:
            return
        if item.tool is CollabAgentTool.SPAWN_AGENT:
            spawn_request = spawn_request_summary(item)
            if spawn_request is not None and item.id is not None:
                self.pending_collab_spawn_requests[item.id] = spawn_request
        cached = None
        if (
            item.tool is CollabAgentTool.SPAWN_AGENT
            and item.status is not CollabAgentToolCallStatus.IN_PROGRESS
            and item.id is not None
        ):
            cached = self.pending_collab_spawn_requests.pop(item.id, None)
        cell = tool_call_history_cell(item, cached)
        if cell is not None:
            self.on_collab_event(cell)

    def handle_file_change_completed_now(self, item: ThreadItem) -> None:
        if item.kind is not ThreadItemKind.FILE_CHANGE:
            return
        if item.status is PatchApplyStatus.FAILED:
            self.add_to_history(HistoryCell("patch_apply_failure", {"message": ""}))
        self.had_work_activity = True

    def handle_mcp_tool_call_started_now(self, item: ThreadItem) -> None:
        if item.kind is not ThreadItemKind.MCP_TOOL_CALL:
            return
        self.flush_answer_stream_with_separator()
        self.flush_active_cell()
        self.active_cell = ActiveMcpToolCallCell(
            call_id=item.id or "",
            invocation={"server": item.server, "tool": item.tool, "arguments": item.arguments},
        )
        self.bump_active_cell_revision()
        self.request_redraw()

    def handle_mcp_tool_call_completed_now(self, item: ThreadItem) -> None:
        self.flush_answer_stream_with_separator()
        if item.kind is not ThreadItemKind.MCP_TOOL_CALL:
            return
        result = mcp_completion_result(item)
        if isinstance(self.active_cell, ActiveMcpToolCallCell) and self.active_cell.call_id == item.id:
            extra_cell = self.active_cell.complete(item.duration_ms or 0, result)
        else:
            self.flush_active_cell()
            self.active_cell = ActiveMcpToolCallCell(
                call_id=item.id or "",
                invocation={"server": item.server, "tool": item.tool, "arguments": item.arguments},
            )
            extra_cell = self.active_cell.complete(item.duration_ms or 0, result)
        self.flush_active_cell()
        if extra_cell is not None:
            self.add_boxed_history(extra_cell)
        self.had_work_activity = True

    def handle_queued_item_started_now(self, item: ThreadItem) -> None:
        if item.kind is ThreadItemKind.COMMAND_EXECUTION:
            self.command_started.append(item)
        elif item.kind is ThreadItemKind.MCP_TOOL_CALL:
            self.handle_mcp_tool_call_started_now(item)

    def handle_queued_item_completed_now(self, item: ThreadItem) -> None:
        if item.kind is ThreadItemKind.COMMAND_EXECUTION:
            self.command_completed.append(item)
        elif item.kind is ThreadItemKind.FILE_CHANGE:
            self.handle_file_change_completed_now(item)
        elif item.kind is ThreadItemKind.MCP_TOOL_CALL:
            self.handle_mcp_tool_call_completed_now(item)

    def defer_or_handle(self, defer, handle) -> None:
        if self.defer_items:
            defer(self.deferred_queue)
        else:
            handle(self)

    def flush_answer_stream_with_separator(self) -> None:
        self.answer_stream_flushes += 1

    def flush_active_cell(self) -> None:
        if self.active_cell is not None:
            self.add_to_history(HistoryCell("active_cell", {"cell": self.active_cell}))
            self.active_cell = None
        self.active_cell_flushes += 1

    def bump_active_cell_revision(self) -> None:
        self.active_cell_revision += 1

    def request_redraw(self) -> None:
        self.redraw_requests += 1

    def add_to_history(self, cell: HistoryCell) -> None:
        self.history.append(cell)

    def add_boxed_history(self, cell: HistoryCell) -> None:
        self.boxed_history.append(cell)


def mcp_completion_result(item: ThreadItem) -> Tuple[str, Any]:
    if item.error is not None:
        return ("error", item.error.message)
    if item.result is not None:
        return (
            "ok",
            {
                "content": item.result.content,
                "structured_content": item.result.structured_content,
                "is_error": False,
            },
        )
    return ("error", "MCP tool call completed without a result")


def spawn_request_summary(item: ThreadItem) -> Optional[Any]:
    return item.payload.get("spawn_request")


def tool_call_history_cell(item: ThreadItem, cached_spawn_request: Optional[Any] = None) -> Optional[HistoryCell]:
    if item.kind is not ThreadItemKind.COLLAB_AGENT_TOOL_CALL:
        return None
    return HistoryCell(
        "collab_agent_tool_call",
        {
            "id": item.id,
            "tool": item.tool,
            "status": item.status,
            "spawn_request": cached_spawn_request or item.payload.get("spawn_request"),
        },
    )


__all__ = [
    "ActiveMcpToolCallCell",
    "ActiveWebSearchCell",
    "CollabAgentTool",
    "CollabAgentToolCallStatus",
    "DeferredQueue",
    "HistoryCell",
    "McpError",
    "McpResult",
    "PatchApplyStatus",
    "RUST_MODULE",
    "ThreadItem",
    "ThreadItemKind",
    "ToolLifecycleModel",
    "mcp_completion_result",
    "spawn_request_summary",
    "tool_call_history_cell",
]
