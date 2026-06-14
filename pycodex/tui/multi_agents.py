"""Multi-agent presentation helpers for the TUI port.

Rust counterpart: ``codex-rs/tui/src/multi_agents.rs``.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .text_formatting import truncate_text

COLLAB_PROMPT_PREVIEW_GRAPHEMES = 160
COLLAB_AGENT_ERROR_PREVIEW_GRAPHEMES = 160
COLLAB_AGENT_RESPONSE_PREVIEW_GRAPHEMES = 240
DEFAULT_REASONING_EFFORT = "medium"


@dataclass(frozen=True)
class Span:
    content: str
    fg: str | None = None
    bold: bool = False
    dim: bool = False


@dataclass(frozen=True)
class Line:
    spans: tuple[Span, ...]

    @property
    def text(self) -> str:
        return "".join(span.content for span in self.spans)


@dataclass(frozen=True)
class PlainHistoryCell:
    lines: tuple[Line, ...]

    def display_lines(self, width: int = 200) -> list[Line]:
        _ = width
        return list(self.lines)

    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass(frozen=True)
class AgentPickerThreadEntry:
    agent_nickname: str | None = None
    agent_role: str | None = None
    is_closed: bool = False


@dataclass(frozen=True)
class AgentMetadata:
    agent_nickname: str | None = None
    agent_role: str | None = None


@dataclass(frozen=True)
class AgentLabel:
    thread_id: str | None = None
    nickname: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class SpawnRequestSummary:
    model: str
    reasoning_effort: str = DEFAULT_REASONING_EFFORT


@dataclass(frozen=True)
class CollabAgentState:
    status: str
    message: str | None = None


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _trim_nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def agent_picker_status_dot_spans(is_closed: bool) -> list[Span]:
    dot = Span("•") if is_closed else Span("•", fg="green")
    return [dot, Span(" ")]


def format_agent_picker_item_name(agent_nickname: str | None, agent_role: str | None, is_primary: bool) -> str:
    if is_primary:
        return "Main [default]"
    nickname = _trim_nonempty(agent_nickname)
    role = _trim_nonempty(agent_role)
    if nickname and role:
        return f"{nickname} [{role}]"
    if nickname:
        return nickname
    if role:
        return f"[{role}]"
    return "Agent"


def previous_agent_shortcut() -> tuple[str, str]:
    return ("alt", "left")


def next_agent_shortcut() -> tuple[str, str]:
    return ("alt", "right")


def _key_parts(key_event: Any) -> tuple[str | None, str | None, str]:
    if isinstance(key_event, Mapping):
        code = key_event.get("code")
        modifiers = key_event.get("modifiers")
        kind = key_event.get("kind", "press")
    elif isinstance(key_event, tuple):
        modifiers, code = key_event[:2]
        kind = key_event[2] if len(key_event) > 2 else "press"
    else:
        code = getattr(key_event, "code", None)
        modifiers = getattr(key_event, "modifiers", None)
        kind = getattr(key_event, "kind", "press")
    return (str(modifiers).lower() if modifiers is not None else None, str(code).lower() if code is not None else None, str(kind).lower())


def previous_agent_shortcut_matches(key_event: Any, allow_word_motion_fallback: bool) -> bool:
    modifiers, code, kind = _key_parts(key_event)
    return (modifiers == "alt" and code == "left") or previous_agent_word_motion_fallback(key_event, allow_word_motion_fallback)


def next_agent_shortcut_matches(key_event: Any, allow_word_motion_fallback: bool) -> bool:
    modifiers, code, kind = _key_parts(key_event)
    return (modifiers == "alt" and code == "right") or next_agent_word_motion_fallback(key_event, allow_word_motion_fallback)


def previous_agent_word_motion_fallback(key_event: Any, allow_word_motion_fallback: bool) -> bool:
    modifiers, code, kind = _key_parts(key_event)
    return sys.platform == "darwin" and allow_word_motion_fallback and modifiers == "alt" and code == "b" and kind in {"press", "repeat"}


def next_agent_word_motion_fallback(key_event: Any, allow_word_motion_fallback: bool) -> bool:
    modifiers, code, kind = _key_parts(key_event)
    return sys.platform == "darwin" and allow_word_motion_fallback and modifiers == "alt" and code == "f" and kind in {"press", "repeat"}


def parse_thread_id(thread_id: str) -> str | None:
    try:
        return str(uuid.UUID(str(thread_id)))
    except ValueError:
        return None


def spawn_request_summary(item: Any) -> SpawnRequestSummary | None:
    if _field(item, "tool") == "SpawnAgent" and _field(item, "model") is not None and _field(item, "reasoning_effort") is not None:
        return SpawnRequestSummary(str(_field(item, "model")), str(_field(item, "reasoning_effort")))
    return None


def agent_label(thread_id: str, metadata: AgentMetadata) -> AgentLabel:
    return AgentLabel(thread_id=thread_id, nickname=metadata.agent_nickname, role=metadata.agent_role)


def agent_label_spans(agent: AgentLabel) -> list[Span]:
    nickname = _trim_nonempty(agent.nickname)
    role = _trim_nonempty(agent.role)
    if nickname:
        spans = [Span(nickname, fg="cyan", bold=True)]
    elif agent.thread_id:
        spans = [Span(agent.thread_id, fg="cyan")]
    else:
        spans = [Span("agent", fg="cyan")]
    if role:
        spans.extend([Span(" ", dim=True), Span(f"[{role}]")])
    return spans


def agent_label_line(agent: AgentLabel) -> Line:
    return Line(tuple(agent_label_spans(agent)))


def spawn_request_spans(spawn_request: SpawnRequestSummary | None) -> list[Span]:
    if spawn_request is None:
        return []
    model = spawn_request.model.strip()
    effort = spawn_request.reasoning_effort
    if not model and effort == DEFAULT_REASONING_EFFORT:
        return []
    details = f"({effort})" if not model else f"({model} {effort})"
    return [Span(" ", dim=True), Span(details, fg="magenta")]


def title_spans_line(spans: list[Span]) -> Line:
    return Line(tuple([Span("›", dim=True), *spans]))


def title_text(title: str) -> Line:
    return title_spans_line([Span(str(title), bold=True)])


def title_with_agent(prefix: str, agent: AgentLabel, spawn_request: SpawnRequestSummary | None = None) -> Line:
    spans = [Span(f"{prefix} ", bold=True)]
    spans.extend(agent_label_spans(agent))
    spans.extend(spawn_request_spans(spawn_request))
    return title_spans_line(spans)


def prompt_line(prompt: str) -> Line | None:
    trimmed = prompt.strip()
    if not trimmed:
        return None
    return Line((Span(truncate_text(trimmed, COLLAB_PROMPT_PREVIEW_GRAPHEMES)),))


def collab_event(title: Line, details: list[Line]) -> PlainHistoryCell:
    lines = [title]
    for detail in details:
        lines.append(Line((Span("  └", dim=True), Span(detail.text))))
    return PlainHistoryCell(tuple(lines))


def _metadata(agent_metadata: Callable[[str], AgentMetadata], thread_id: str) -> AgentMetadata:
    return agent_metadata(thread_id)


def spawn_end(new_thread_id: str | None, prompt: str, spawn_request: SpawnRequestSummary | None, agent_metadata: Callable[[str], AgentMetadata]) -> PlainHistoryCell:
    if new_thread_id:
        title = title_with_agent("Spawned", agent_label(new_thread_id, _metadata(agent_metadata, new_thread_id)), spawn_request)
    else:
        title = title_text("Agent spawn failed")
    details = []
    line = prompt_line(prompt)
    if line is not None:
        details.append(line)
    return collab_event(title, details)


def interaction_end(receiver_thread_id: str, prompt: str, agent_metadata: Callable[[str], AgentMetadata]) -> PlainHistoryCell:
    title = title_with_agent("Sent input to", agent_label(receiver_thread_id, _metadata(agent_metadata, receiver_thread_id)))
    line = prompt_line(prompt)
    return collab_event(title, [line] if line else [])


def waiting_begin(receiver_thread_ids: Sequence[str], agent_metadata: Callable[[str], AgentMetadata]) -> PlainHistoryCell:
    agents = [(tid, _metadata(agent_metadata, tid)) for tid in map(parse_thread_id, receiver_thread_ids) if tid]
    if len(agents) == 1:
        tid, metadata = agents[0]
        title = title_with_agent("Waiting for", agent_label(tid, metadata))
        details: list[Line] = []
    elif not agents:
        title = title_text("Waiting for agents")
        details = []
    else:
        title = title_text(f"Waiting for {len(agents)} agents")
        details = [agent_label_line(agent_label(tid, metadata)) for tid, metadata in agents]
    return collab_event(title, details)


def error_summary_spans(error: str) -> list[Span]:
    preview = truncate_text(" ".join(str(error).split()), COLLAB_AGENT_ERROR_PREVIEW_GRAPHEMES)
    spans = [Span("Error", fg="red")]
    if preview:
        spans.extend([Span(" - ", dim=True), Span(preview)])
    return spans


def status_summary_spans(status: Any) -> list[Span]:
    status_name = str(_field(status, "status"))
    message = _field(status, "message")
    if status_name == "PendingInit":
        return [Span("Pending init", fg="cyan")]
    if status_name == "Running":
        return [Span("Running", fg="cyan", bold=True)]
    if status_name == "Interrupted":
        return [Span("Interrupted", fg="yellow")]
    if status_name == "Completed":
        spans = [Span("Completed", fg="green")]
        if message:
            preview = truncate_text(" ".join(str(message).split()), COLLAB_AGENT_RESPONSE_PREVIEW_GRAPHEMES)
            if preview:
                spans.extend([Span(" - ", dim=True), Span(preview)])
        return spans
    if status_name == "Errored":
        return error_summary_spans(str(message or "Agent errored"))
    if status_name == "Shutdown":
        return [Span("Shutdown")]
    if status_name == "NotFound":
        return [Span("Not found", fg="red")]
    return error_summary_spans(str(message or status_name))


def status_summary_line(status: Any | None, fallback_error: str) -> Line:
    return Line(tuple(status_summary_spans(status) if status is not None else error_summary_spans(fallback_error)))


def first_agent_state(receiver_thread_ids: Sequence[str], agents_states: Mapping[str, Any]) -> Any | None:
    for thread_id in receiver_thread_ids:
        if thread_id in agents_states:
            return agents_states[thread_id]
    if not agents_states:
        return None
    return agents_states[sorted(agents_states.keys())[0]]


def wait_complete_lines(receiver_thread_ids: Sequence[str], agents_states: Mapping[str, Any], agent_metadata: Callable[[str], AgentMetadata]) -> list[Line]:
    seen: set[str] = set()
    entries: list[tuple[str, AgentMetadata, Any]] = []
    for raw_id in receiver_thread_ids:
        parsed = parse_thread_id(raw_id)
        if parsed and raw_id in agents_states:
            seen.add(parsed)
            entries.append((parsed, _metadata(agent_metadata, parsed), agents_states[raw_id]))
    extras = []
    for raw_id, status in agents_states.items():
        parsed = parse_thread_id(raw_id)
        if parsed and parsed not in seen:
            extras.append((parsed, _metadata(agent_metadata, parsed), status))
    entries.extend(sorted(extras, key=lambda item: item[0]))
    if not entries:
        return [Line((Span("No agents completed yet"),))]
    lines: list[Line] = []
    for thread_id, metadata, status in entries:
        spans = agent_label_spans(agent_label(thread_id, metadata))
        spans.append(Span(": ", dim=True))
        spans.extend(status_summary_spans(status))
        lines.append(Line(tuple(spans)))
    return lines


def waiting_end(receiver_thread_ids: Sequence[str], agents_states: Mapping[str, Any], agent_metadata: Callable[[str], AgentMetadata]) -> PlainHistoryCell:
    return collab_event(title_text("Finished waiting"), wait_complete_lines(receiver_thread_ids, agents_states, agent_metadata))


def close_end(receiver_thread_id: str, agent_metadata: Callable[[str], AgentMetadata]) -> PlainHistoryCell:
    return collab_event(title_with_agent("Closed", agent_label(receiver_thread_id, _metadata(agent_metadata, receiver_thread_id))), [])


def resume_begin(receiver_thread_id: str, agent_metadata: Callable[[str], AgentMetadata]) -> PlainHistoryCell:
    return collab_event(title_with_agent("Resuming", agent_label(receiver_thread_id, _metadata(agent_metadata, receiver_thread_id))), [])


def resume_end(receiver_thread_id: str, status: Any | None, fallback_error: str, agent_metadata: Callable[[str], AgentMetadata]) -> PlainHistoryCell:
    return collab_event(title_with_agent("Resumed", agent_label(receiver_thread_id, _metadata(agent_metadata, receiver_thread_id))), [status_summary_line(status, fallback_error)])


def tool_call_history_cell(item: Any, cached_spawn_request: SpawnRequestSummary | None, agent_metadata: Callable[[str], AgentMetadata]) -> PlainHistoryCell | None:
    if _field(item, "type") not in {None, "CollabAgentToolCall"} and _field(item, "tool") is None:
        return None
    tool = _field(item, "tool")
    status = _field(item, "status")
    receiver_thread_ids = list(_field(item, "receiver_thread_ids", []))
    prompt = _field(item, "prompt", "") or ""
    agents_states = dict(_field(item, "agents_states", {}))
    first_receiver = parse_thread_id(receiver_thread_ids[0]) if receiver_thread_ids else None
    if tool == "SpawnAgent":
        if status == "InProgress":
            return None
        return spawn_end(first_receiver, prompt, cached_spawn_request or spawn_request_summary(item), agent_metadata)
    if tool == "SendInput":
        if status == "InProgress" or first_receiver is None:
            return None
        return interaction_end(first_receiver, prompt, agent_metadata)
    if tool == "ResumeAgent" and first_receiver is not None:
        if status == "InProgress":
            return resume_begin(first_receiver, agent_metadata)
        return resume_end(first_receiver, first_agent_state(receiver_thread_ids, agents_states), "Agent resume failed", agent_metadata)
    if tool == "Wait":
        if status == "InProgress":
            return waiting_begin(receiver_thread_ids, agent_metadata)
        return waiting_end(receiver_thread_ids, agents_states, agent_metadata)
    if tool == "CloseAgent":
        if status == "InProgress" or first_receiver is None:
            return None
        return close_end(first_receiver, agent_metadata)
    return None


def line_to_text(line: Line) -> str:
    return line.text


def cell_to_text(cell: PlainHistoryCell) -> str:
    return cell.text()


__all__ = [name for name in globals() if not name.startswith("_")]
