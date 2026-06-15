"""Transcript cell conversion for ``codex-tui::resume_picker::transcript``.

Rust source: ``codex/codex-rs/tui/src/resume_picker/transcript.rs``.

Rust returns ``Vec<Arc<dyn HistoryCell>>``.  Python represents those cells with
small semantic DTOs that preserve the cell kind, visible text, cwd, and item
metadata without copying ratatui/history-cell framework types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .._porting import RustTuiModule
from ..git_action_directives import parse_assistant_markdown

RUST_MODULE = RustTuiModule(crate="codex-tui", module="resume_picker::transcript", source="codex/codex-rs/tui/src/resume_picker/transcript.rs", status="complete")


class RawReasoningVisibility(Enum):
    Hidden = "hidden"
    Visible = "visible"


@dataclass(frozen=True)
class TranscriptCell:
    kind: str
    text: str = ""
    lines: Tuple[str, ...] = ()
    cwd: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


TranscriptCells = List[TranscriptCell]


async def load_session_transcript(
    app_server: Any,
    thread_id: Any,
    raw_reasoning_visibility: RawReasoningVisibility = RawReasoningVisibility.Hidden,
) -> TranscriptCells:
    """Read a thread through an app-server-like object and convert it to cells."""
    reader = getattr(app_server, "thread_read", None)
    if reader is None:
        raise AttributeError("app_server must provide thread_read")
    result = reader(thread_id, True)
    if hasattr(result, "__await__"):
        result = await result
    return thread_to_transcript_cells(result, raw_reasoning_visibility)


def thread_to_transcript_cells(
    thread: Any,
    raw_reasoning_visibility: RawReasoningVisibility = RawReasoningVisibility.Hidden,
) -> TranscriptCells:
    cwd = _path_text(_get(thread, "cwd", ""))
    cells: TranscriptCells = []
    for item in _thread_items(thread):
        kind = _item_kind(item)
        if kind == "UserMessage":
            cells.append(_user_message_cell(item, cwd))
        elif kind == "AgentMessage":
            text = str(_get(item, "text", ""))
            parsed = parse_assistant_markdown(text)
            visible = parsed.visible_markdown
            if visible.strip():
                cells.append(TranscriptCell("agent_markdown", visible, (visible,), cwd, {"git_actions": parsed.git_actions}))
        elif kind == "Plan":
            text = str(_get(item, "text", ""))
            if text.strip():
                cells.append(TranscriptCell("proposed_plan", text, (text,), cwd))
        elif kind == "Reasoning":
            summary = [str(value) for value in _get(item, "summary", [])]
            content = [str(value) for value in _get(item, "content", [])]
            if raw_reasoning_visibility is RawReasoningVisibility.Visible and content:
                text = "\n\n".join(content)
                source = "content"
            else:
                text = "\n\n".join(summary)
                source = "summary"
            if text.strip():
                cells.append(TranscriptCell("reasoning", text, (text,), cwd, {"title": "Reasoning", "source": source}))
        else:
            fallback = fallback_transcript_cell(item)
            if fallback is not None:
                cells.append(fallback)
    if not cells:
        cells.append(TranscriptCell("plain", "No transcript content available", ("No transcript content available",), cwd, {"style": "italic dim"}))
    return cells


def fallback_transcript_cell(item: Any) -> Optional[TranscriptCell]:
    kind = _item_kind(item)
    lines: List[str]
    metadata: Dict[str, Any] = {"source_kind": kind}

    if kind == "HookPrompt":
        lines = [f"hook prompt: {str(_get(fragment, 'text', '')).strip()}" for fragment in _get(item, "fragments", [])]
    elif kind == "CommandExecution":
        command = str(_get(item, "command", ""))
        status = _debug_value(_get(item, "status", ""))
        exit_code = _get(item, "exit_code", None)
        suffix = f" · exit {exit_code}" if exit_code is not None else ""
        lines = [f"$ {command}", f"status: {status}{suffix}"]
        output = _get(item, "aggregated_output", None)
        if output is not None and str(output).strip():
            lines.extend(f"  {line.rstrip()}" for line in str(output).splitlines())
    elif kind == "FileChange":
        changes = _get(item, "changes", [])
        status = _debug_value(_get(item, "status", ""))
        lines = [f"file changes: {status} · {len(changes)} changes"]
    elif kind == "McpToolCall":
        lines = [f"mcp tool: {_get(item, 'server', '')}/{_get(item, 'tool', '')} · {_debug_value(_get(item, 'status', ''))}"]
    elif kind == "DynamicToolCall":
        namespace = _get(item, "namespace", None)
        tool = str(_get(item, "tool", ""))
        name = f"{namespace}/{tool}" if namespace is not None else tool
        lines = [f"tool: {name} · {_debug_value(_get(item, 'status', ''))}"]
    elif kind == "CollabAgentToolCall":
        lines = [f"agent tool: {_debug_value(_get(item, 'tool', ''))} · {_debug_value(_get(item, 'status', ''))}"]
    elif kind == "WebSearch":
        lines = [f"web search: {_get(item, 'query', '')}"]
    elif kind == "ImageView":
        lines = [f"image: {_path_text(_get(item, 'path', ''))}"]
    elif kind == "ImageGeneration":
        saved_path = _get(item, "saved_path", None)
        saved = f" · {_path_text(saved_path)}" if saved_path is not None else ""
        lines = [f"image generation: {_get(item, 'status', '')}{saved}"]
    elif kind == "EnteredReviewMode":
        lines = [f"review started: {_get(item, 'review', '')}"]
    elif kind == "ExitedReviewMode":
        lines = [f"review finished: {_get(item, 'review', '')}"]
    elif kind == "ContextCompaction":
        lines = ["context compacted"]
    elif kind in {"UserMessage", "AgentMessage", "Plan", "Reasoning"}:
        return None
    else:
        return None

    return TranscriptCell("plain", "\n".join(lines), tuple(lines), metadata=metadata) if lines else None


def _user_message_cell(item: Any, cwd: Optional[str]) -> TranscriptCell:
    content = list(_get(item, "content", []))
    text_parts: List[str] = []
    local_image_paths: List[str] = []
    remote_image_urls: List[str] = []
    text_elements: List[Any] = []
    for entry in content:
        text = _user_input_text(entry)
        if text is not None:
            text_parts.append(text)
            text_elements.append(text)
            continue
        local_path = _get(entry, "path", None)
        if local_path is not None:
            local_image_paths.append(_path_text(local_path))
        url = _get(entry, "url", None)
        if url is not None:
            remote_image_urls.append(str(url))
    message = "\n".join(part for part in text_parts if part != "")
    return TranscriptCell(
        "user",
        message,
        (message,) if message else (),
        cwd,
        {
            "id": _get(item, "id", None),
            "text_elements": tuple(text_elements),
            "local_image_paths": tuple(local_image_paths),
            "remote_image_urls": tuple(remote_image_urls),
        },
    )


def _thread_items(thread: Any) -> List[Any]:
    turns = _get(thread, "turns", [])
    if isinstance(turns, dict):
        turns = turns.values()
    items: List[Any] = []
    for turn in turns:
        turn_items = _get(turn, "items", [])
        items.extend(list(turn_items))
    return items


def _item_kind(item: Any) -> str:
    for key in ("kind", "type", "variant"):
        raw = _get(item, key, None)
        if raw is not None:
            return _normalize_kind(str(raw))
    if isinstance(item, dict) and len(item) == 1:
        return _normalize_kind(next(iter(item)))
    return type(item).__name__


def _normalize_kind(raw: str) -> str:
    compact = raw.replace("_", "-").replace(" ", "-").lower()
    mapping = {
        "user-message": "UserMessage",
        "agent-message": "AgentMessage",
        "plan": "Plan",
        "reasoning": "Reasoning",
        "hook-prompt": "HookPrompt",
        "command-execution": "CommandExecution",
        "file-change": "FileChange",
        "mcp-tool-call": "McpToolCall",
        "dynamic-tool-call": "DynamicToolCall",
        "collab-agent-tool-call": "CollabAgentToolCall",
        "web-search": "WebSearch",
        "image-view": "ImageView",
        "image-generation": "ImageGeneration",
        "entered-review-mode": "EnteredReviewMode",
        "exited-review-mode": "ExitedReviewMode",
        "context-compaction": "ContextCompaction",
    }
    return mapping.get(compact, raw)


def _user_input_text(entry: Any) -> Optional[str]:
    if isinstance(entry, str):
        return entry
    for key in ("text", "message", "content"):
        value = _get(entry, key, None)
        if isinstance(value, str):
            return value
    return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        if len(obj) == 1:
            value = next(iter(obj.values()))
            if isinstance(value, dict):
                return value.get(key, default)
        return default
    return getattr(obj, key, default)


def _path_text(path: Any) -> Optional[str]:
    if path is None:
        return None
    as_path = getattr(path, "as_path", None)
    if callable(as_path):
        return str(as_path())
    return str(path)


def _debug_value(value: Any) -> str:
    if isinstance(value, Enum):
        return value.name
    return str(value)


__all__ = [
    "RUST_MODULE",
    "RawReasoningVisibility",
    "TranscriptCell",
    "TranscriptCells",
    "fallback_transcript_cell",
    "load_session_transcript",
    "thread_to_transcript_cells",
]

