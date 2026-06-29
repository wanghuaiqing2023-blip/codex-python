"""Replay previously recorded thread turns into a chat-widget semantic model.

This mirrors the local behavior in Rust
``codex-tui::chatwidget::replay`` without copying ratatui or app-server
framework types.  Callers provide a widget-like object with the same semantic
handler methods used by the Rust ``ChatWidget`` implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::replay",
    source="codex/codex-rs/tui/src/chatwidget/replay.rs",
    status="complete",
)

__all__ = [
    "AgentMessageItem",
    "ReplayKind",
    "RUST_MODULE",
    "ThreadItemRenderSource",
    "Turn",
    "TurnCompletedNotification",
    "TurnStatus",
    "handle_thread_item",
    "replay_thread_item",
    "replay_thread_turns",
]


class ReplayKind(str, Enum):
    """Replay source used by Rust ``ReplayKind``."""

    THREAD_SNAPSHOT = "ThreadSnapshot"
    RESUME_INITIAL_MESSAGES = "ResumeInitialMessages"
    INITIAL_HISTORY = "InitialHistory"
    OTHER = "Other"


class TurnStatus(str, Enum):
    """Turn statuses observed by replay turn completion logic."""

    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    INTERRUPTED = "Interrupted"
    FAILED = "Failed"
    OTHER = "Other"


@dataclass(frozen=True)
class Turn:
    """Semantic subset of app-server ``Turn`` used by replay."""

    id: str
    items: Tuple[Any, ...] = ()
    status: Union[TurnStatus, str] = TurnStatus.OTHER
    error: Optional[Any] = None
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None
    duration_ms: Optional[int] = None


@dataclass(frozen=True)
class TurnCompletedNotification:
    """Semantic notification passed to ``handle_turn_completed_notification``."""

    thread_id: str
    turn: Turn


@dataclass(frozen=True)
class ThreadItemRenderSource:
    """Equivalent of Rust ``ThreadItemRenderSource`` for replay dispatch."""

    replay_kind: Optional[Union[ReplayKind, str]] = None

    @classmethod
    def replay(cls, replay_kind: Union[ReplayKind, str]) -> "ThreadItemRenderSource":
        return cls(replay_kind=replay_kind)

    @classmethod
    def live(cls) -> "ThreadItemRenderSource":
        return cls(replay_kind=None)

    def is_replay(self) -> bool:
        return self.replay_kind is not None


@dataclass(frozen=True)
class AgentMessageItem:
    """Semantic replacement for Rust ``AgentMessageItem``."""

    id: Optional[str]
    content: Tuple[Mapping[str, Any], ...]
    phase: Optional[Any] = None
    memory_citation: Optional[Any] = None


class ReplayWidget:
    """Protocol documenting the widget callbacks used by this module."""

    config: Any
    last_non_retry_error: Optional[Any]
    thread_id: Optional[Any]

    def on_task_started(self) -> None: ...

    def handle_turn_completed_notification(
        self,
        notification: TurnCompletedNotification,
        replay_kind: Optional[Union[ReplayKind, str]],
    ) -> None: ...


def replay_thread_turns(
    widget: ReplayWidget,
    turns: Sequence[Union[Turn, Mapping[str, Any], Any]],
    replay_kind: Union[ReplayKind, str],
) -> None:
    """Replay turns into ``widget`` using Rust ``ChatWidget`` ordering.

    ``InProgress`` turns start the task before item replay.  Completed,
    interrupted, and failed turns emit a completion notification after their
    items are rehydrated.
    """

    for raw_turn in turns:
        turn = _coerce_turn(raw_turn)
        status = _status_name(turn.status)
        if status == TurnStatus.IN_PROGRESS.value:
            widget.last_non_retry_error = None
            _call(widget, "on_task_started")

        for item in turn.items:
            replay_thread_item(widget, item, turn.id, replay_kind)

        if status in {
            TurnStatus.COMPLETED.value,
            TurnStatus.INTERRUPTED.value,
            TurnStatus.FAILED.value,
        }:
            notification = TurnCompletedNotification(
                thread_id=_thread_id_string(getattr(widget, "thread_id", None)),
                turn=Turn(
                    id=turn.id,
                    items=(),
                    status=turn.status,
                    error=turn.error,
                    started_at=turn.started_at,
                    completed_at=turn.completed_at,
                    duration_ms=turn.duration_ms,
                ),
            )
            _call(widget, "handle_turn_completed_notification", notification, replay_kind)


def replay_thread_item(
    widget: Any,
    item: Union[Mapping[str, Any], Any],
    turn_id: str,
    replay_kind: Union[ReplayKind, str],
) -> None:
    """Replay one item with ``ThreadItemRenderSource::Replay`` semantics."""

    handle_thread_item(widget, item, turn_id, ThreadItemRenderSource.replay(replay_kind))


def handle_thread_item(
    widget: Any,
    item: Union[Mapping[str, Any], Any],
    turn_id: str,
    render_source: ThreadItemRenderSource,
) -> None:
    """Dispatch a ``ThreadItem`` to the matching widget callback.

    Unknown item variants are rejected instead of silently falling back; this
    keeps porting gaps visible when upstream adds a new replayable item kind.
    """

    kind = _item_kind(item)
    from_replay = render_source.is_replay()
    replay_kind = render_source.replay_kind

    if kind == "UserMessage":
        _call(widget, "on_committed_user_message", _get(item, "content"), from_replay)
    elif kind == "AgentMessage":
        _call(
            widget,
            "on_agent_message_item_completed",
            AgentMessageItem(
                id=_get(item, "id", None),
                content=_agent_message_content(item),
                phase=_get(item, "phase", None),
                memory_citation=_convert_memory_citation(_get(item, "memory_citation", None)),
            ),
            from_replay,
        )
    elif kind == "Plan":
        _call(widget, "on_plan_item_completed", _get(item, "text"))
    elif kind == "Reasoning":
        if from_replay:
            for delta in _get(item, "summary", ()) or ():
                _call(widget, "on_agent_reasoning_delta", delta)
            if bool(getattr(getattr(widget, "config", object()), "show_raw_agent_reasoning", False)):
                for delta in _get(item, "content", ()) or ():
                    _call(widget, "on_agent_reasoning_delta", delta)
        _call(widget, "on_agent_reasoning_final")
    elif kind == "CommandExecution":
        if _status_name(_get(item, "status", None)) == "InProgress":
            _call(widget, "on_command_execution_started", item)
        else:
            _call(widget, "on_command_execution_completed", item)
    elif kind == "FileChange":
        if _status_name(_get(item, "status", None)) != "InProgress":
            _call(widget, "on_file_change_completed", item)
    elif kind == "McpToolCall":
        if _status_name(_get(item, "status", None)) == "InProgress":
            _call(widget, "on_mcp_tool_call_started", item)
        else:
            _call(widget, "on_mcp_tool_call_completed", item)
    elif kind == "WebSearch":
        item_id = _get(item, "id")
        _call(widget, "on_web_search_begin", item_id)
        _call(widget, "on_web_search_end", item_id, _get(item, "query"), _get(item, "action", "Other") or "Other")
    elif kind == "ImageView":
        _call(widget, "on_view_image_tool_call", _get(item, "path"))
    elif kind == "ImageGeneration":
        _call(widget, "on_image_generation_end", _get(item, "id"), _get(item, "revised_prompt", None), _get(item, "saved_path", None))
    elif kind == "EnteredReviewMode":
        if from_replay:
            _call(widget, "enter_review_mode_with_hint", _get(item, "review"), True)
    elif kind == "ExitedReviewMode":
        _call(widget, "exit_review_mode_after_item")
    elif kind == "ContextCompaction":
        _call(widget, "add_info_message", "Context compacted", None)
    elif kind == "HookPrompt":
        pass
    elif kind == "CollabAgentToolCall":
        _call(widget, "on_collab_agent_tool_call", item)
    elif kind == "DynamicToolCall":
        pass
    else:
        raise ValueError(f"unsupported ThreadItem variant for replay: {kind!r}")

    if _replay_kind_name(replay_kind) == ReplayKind.THREAD_SNAPSHOT.value and turn_id == "":
        _call(widget, "request_redraw")


def _coerce_turn(turn: Union[Turn, Mapping[str, Any], Any]) -> Turn:
    if isinstance(turn, Turn):
        return turn
    return Turn(
        id=str(_get(turn, "id")),
        items=tuple(_get(turn, "items", ()) or ()),
        status=_get(turn, "status", TurnStatus.OTHER),
        error=_get(turn, "error", None),
        started_at=_get(turn, "started_at", None),
        completed_at=_get(turn, "completed_at", None),
        duration_ms=_get(turn, "duration_ms", None),
    )


def _agent_message_content(item: Union[Mapping[str, Any], Any]) -> Tuple[Mapping[str, Any], ...]:
    content = _get(item, "content", None)
    if content is not None:
        return tuple(
            part if isinstance(part, Mapping) else {"type": _get(part, "type", "Text"), "text": _get(part, "text", "")}
            for part in (content or ())
        )
    return ({"type": "Text", "text": _get(item, "text")},)


def _call(target: Any, method_name: str, *args: Any) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        raise AttributeError(f"replay target does not implement {method_name}()")
    return method(*args)


def _get(value: Union[Mapping[str, Any], Any], key: str, default: Any = ...):
    if isinstance(value, Mapping):
        if default is ...:
            return value[key]
        return value.get(key, default)
    if default is ...:
        return getattr(value, key)
    return getattr(value, key, default)


def _item_kind(item: Union[Mapping[str, Any], Any]) -> str:
    raw_kind = _get(item, "kind", None) or _get(item, "type", None)
    if raw_kind is None:
        raise ValueError("ThreadItem is missing a 'kind' or 'type' discriminator")
    return _status_name(raw_kind)


def _status_name(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    text = str(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _replay_kind_name(value: Optional[Union[ReplayKind, str]]) -> Optional[str]:
    if value is None:
        return None
    return _status_name(value)


def _thread_id_string(thread_id: Optional[Any]) -> str:
    return "" if thread_id is None else str(thread_id)


def _convert_memory_citation(citation: Optional[Any]) -> Optional[Any]:
    if citation is None:
        return None
    entries = tuple(_get(citation, "entries", ()) or ())
    rollout_ids = _get(citation, "thread_ids", _get(citation, "rollout_ids", None))
    return {"entries": entries, "rollout_ids": rollout_ids}
