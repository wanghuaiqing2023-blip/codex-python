"""Server-notification dispatch for chat-widget semantic models.

Rust ``codex-tui::chatwidget::protocol`` owns app-server notification routing
for ``ChatWidget``.  This Python module keeps the same behavior boundary using
dict/object friendly notifications and widget callback hooks instead of Rust
protocol enums.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Protocol, Union

from .._porting import RustTuiModule
from ..token_usage import TokenUsage, TokenUsageInfo
from .replay import ThreadItemRenderSource

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::protocol",
    source="codex/codex-rs/tui/src/chatwidget/protocol.rs",
    status="complete",
)

__all__ = [
    "ItemCompletedNotification",
    "ItemStartedNotification",
    "ReplayKind",
    "RUST_MODULE",
    "ServerNotification",
    "TurnCompletedNotification",
    "TurnStatus",
    "handle_item_completed_notification",
    "handle_item_started_notification",
    "handle_server_notification",
    "handle_turn_completed_notification",
    "token_usage_info_from_app_server",
]


class ReplayKind(str, Enum):
    RESUME_INITIAL_MESSAGES = "ResumeInitialMessages"
    THREAD_SNAPSHOT = "ThreadSnapshot"
    OTHER = "Other"


class TurnStatus(str, Enum):
    COMPLETED = "Completed"
    INTERRUPTED = "Interrupted"
    FAILED = "Failed"
    IN_PROGRESS = "InProgress"


@dataclass(frozen=True)
class ServerNotification:
    kind: str
    payload: Any = None


@dataclass(frozen=True)
class TurnCompletedNotification:
    turn: Any


@dataclass(frozen=True)
class ItemStartedNotification:
    item: Any


@dataclass(frozen=True)
class ItemCompletedNotification:
    item: Any
    turn_id: str


class ProtocolWidget(Protocol):
    active_side_conversation: bool
    config: Any
    turn_lifecycle: Any
    last_non_retry_error: Optional[Any]
    last_rendered_user_message_display: Optional[Any]


def handle_server_notification(
    widget: Any,
    notification: Union[ServerNotification, Mapping[str, Any], Any],
    replay_kind: Optional[Union[ReplayKind, str]] = None,
) -> None:
    """Route one app-server notification to the matching widget callback."""

    kind = _kind(notification)
    payload = _payload(notification)
    from_replay = replay_kind is not None

    if from_replay and kind.startswith("ThreadRealtime"):
        return

    if (
        bool(getattr(widget, "active_side_conversation", False))
        and replay_kind is None
        and kind == "McpServerStatusUpdated"
    ):
        return

    is_resume_initial_replay = _replay_name(replay_kind) == ReplayKind.RESUME_INITIAL_MESSAGES.value
    is_retry_error = kind == "Error" and bool(_get(payload, "will_retry", False))
    if not is_resume_initial_replay and not is_retry_error:
        _call_optional(widget, "restore_retry_status_header_if_present")

    if kind == "ThreadTokenUsageUpdated":
        _call(
            widget,
            "set_token_info",
            token_usage_info_from_app_server(_get(payload, "token_usage")),
        )
    elif kind == "ThreadNameUpdated":
        thread_id = _get(payload, "thread_id")
        if thread_id:
            _call(widget, "on_thread_name_updated", thread_id, _get(payload, "thread_name", None))
    elif kind == "ThreadGoalUpdated":
        _call(widget, "on_thread_goal_updated", _get(payload, "goal"), _get(payload, "turn_id", None))
    elif kind == "ThreadGoalCleared":
        _call(widget, "on_thread_goal_cleared", str(_get(payload, "thread_id")))
    elif kind == "ThreadSettingsUpdated":
        _call(widget, "on_thread_settings_updated", payload)
    elif kind == "TurnStarted":
        turn = _get(payload, "turn")
        widget.turn_lifecycle.last_turn_id = _get(turn, "id")
        widget.last_non_retry_error = None
        if not is_resume_initial_replay:
            _call(widget, "on_task_started")
    elif kind == "TurnCompleted":
        handle_turn_completed_notification(widget, payload, replay_kind)
    elif kind == "ItemStarted":
        handle_item_started_notification(widget, payload, from_replay)
    elif kind == "ItemCompleted":
        handle_item_completed_notification(widget, payload, replay_kind)
    elif kind == "AgentMessageDelta":
        _call(widget, "on_agent_message_delta", _get(payload, "delta"))
    elif kind == "PlanDelta":
        _call(widget, "on_plan_delta", _get(payload, "delta"))
    elif kind == "ReasoningSummaryTextDelta":
        _call(widget, "on_agent_reasoning_delta", _get(payload, "delta"))
    elif kind == "ReasoningTextDelta":
        if bool(getattr(widget.config, "show_raw_agent_reasoning", False)):
            _call(widget, "on_agent_reasoning_delta", _get(payload, "delta"))
    elif kind == "ReasoningSummaryPartAdded":
        _call(widget, "on_reasoning_section_break")
    elif kind == "TerminalInteraction":
        _call(widget, "on_terminal_interaction", _get(payload, "process_id"), _get(payload, "stdin"))
    elif kind == "CommandExecutionOutputDelta":
        _call(widget, "on_exec_command_output_delta", _get(payload, "item_id"), _get(payload, "delta"))
    elif kind == "FileChangeOutputDelta":
        _call(widget, "on_patch_apply_output_delta", _get(payload, "item_id"), _get(payload, "delta"))
    elif kind == "TurnDiffUpdated":
        _call(widget, "on_turn_diff", _get(payload, "diff"))
    elif kind == "TurnPlanUpdated":
        _call(widget, "on_plan_update", _plan_update_args(payload))
    elif kind == "HookStarted":
        _call(widget, "on_hook_started", _get(payload, "run"))
    elif kind == "HookCompleted":
        _call(widget, "on_hook_completed", _get(payload, "run"))
    elif kind == "Error":
        _handle_error_notification(widget, payload, from_replay)
    elif kind == "SkillsChanged":
        _call(widget, "refresh_skills_for_current_cwd", True)
    elif kind == "ModelVerification":
        _call(widget, "on_app_server_model_verification", _get(payload, "verifications"))
    elif kind in {"Warning", "GuardianWarning"}:
        _call(widget, "on_warning", _get(payload, "message"))
    elif kind == "DeprecationNotice":
        _call(widget, "on_deprecation_notice", _get(payload, "summary"), _get(payload, "details", None))
    elif kind == "ConfigWarning":
        details = _get(payload, "details", None)
        summary = _get(payload, "summary")
        _call(widget, "on_warning", f"{summary}: {details}" if details else summary)
    elif kind == "McpServerStatusUpdated":
        _call(widget, "on_mcp_server_status_updated", payload)
    elif kind == "ItemGuardianApprovalReviewStarted":
        _call(
            widget,
            "on_guardian_review_notification",
            _get(payload, "review_id"),
            _get(payload, "turn_id"),
            _get(payload, "started_at_ms"),
            _get(payload, "review"),
            None,
            _get(payload, "action"),
        )
    elif kind == "ItemGuardianApprovalReviewCompleted":
        _call(
            widget,
            "on_guardian_review_notification",
            _get(payload, "review_id"),
            _get(payload, "turn_id"),
            _get(payload, "started_at_ms"),
            _get(payload, "review"),
            (_get(payload, "completed_at_ms"), _get(payload, "decision_source")),
            _get(payload, "action"),
        )
    elif kind == "ThreadClosed":
        if not from_replay:
            _call(widget, "on_shutdown_complete")
    elif kind.startswith("ThreadRealtime"):
        if not from_replay:
            _handle_realtime_notification(widget, kind, payload)
    elif kind in _NOOP_NOTIFICATIONS:
        return
    elif kind == "ContextCompacted":
        return
    elif kind == "ModelRerouted":
        return
    else:
        raise ValueError(f"unsupported ServerNotification variant: {kind!r}")


def handle_turn_completed_notification(
    widget: Any,
    notification: Union[TurnCompletedNotification, Mapping[str, Any], Any],
    replay_kind: Optional[Union[ReplayKind, str]] = None,
) -> None:
    widget.last_rendered_user_message_display = None
    turn = _get(notification, "turn")
    status = _status_name(_get(turn, "status"))
    if status == TurnStatus.COMPLETED.value:
        widget.last_non_retry_error = None
        _call(widget, "on_task_complete", None, _get(turn, "duration_ms", None), replay_kind is not None)
    elif status == TurnStatus.INTERRUPTED.value:
        widget.last_non_retry_error = None
        budget_limited = bool(_call_optional(widget.turn_lifecycle, "take_budget_limited", str(_get(turn, "id")), default=False))
        _call(widget, "on_interrupted_turn", "BudgetLimited" if budget_limited else "Interrupted")
    elif status == TurnStatus.FAILED.value:
        error = _get(turn, "error", None)
        if error is not None:
            pair = (_get(turn, "id"), _get(error, "message"))
            if getattr(widget, "last_non_retry_error", None) == pair:
                widget.last_non_retry_error = None
            else:
                _call(widget, "handle_non_retry_error", _get(error, "message"), _get(error, "codex_error_info", None))
        else:
            widget.last_non_retry_error = None
            _call(widget, "finalize_turn")
            _call(widget, "request_redraw")
            _call(widget, "maybe_send_next_queued_input")
    elif status == TurnStatus.IN_PROGRESS.value:
        return
    else:
        raise ValueError(f"unsupported TurnStatus: {status!r}")


def handle_item_started_notification(
    widget: Any,
    notification: Union[ItemStartedNotification, Mapping[str, Any], Any],
    from_replay: bool,
) -> None:
    item = _get(notification, "item")
    kind = _kind(item)
    if kind == "CommandExecution":
        _call(widget, "on_command_execution_started", item)
    elif kind == "FileChange":
        _call(widget, "on_patch_apply_begin", _get(item, "changes", None))
    elif kind == "McpToolCall":
        _call(widget, "on_mcp_tool_call_started", item)
    elif kind == "WebSearch":
        _call(widget, "on_web_search_begin", _get(item, "id"))
    elif kind == "ImageGeneration":
        _call(widget, "on_image_generation_begin")
    elif kind == "CollabAgentToolCall":
        _call(widget, "on_collab_agent_tool_call", item)
    elif kind == "EnteredReviewMode" and not from_replay:
        _call(widget, "enter_review_mode_with_hint", _get(item, "review"), False)


def handle_item_completed_notification(
    widget: Any,
    notification: Union[ItemCompletedNotification, Mapping[str, Any], Any],
    replay_kind: Optional[Union[ReplayKind, str]] = None,
) -> None:
    source = ThreadItemRenderSource.live() if replay_kind is None else ThreadItemRenderSource.replay(replay_kind)
    _call(widget, "handle_thread_item", _get(notification, "item"), _get(notification, "turn_id"), source)


def _handle_error_notification(widget: Any, notification: Any, from_replay: bool) -> None:
    error = _get(notification, "error")
    if bool(_get(notification, "will_retry", False)):
        if not from_replay:
            _call(widget, "on_stream_error", _get(error, "message"), _get(error, "additional_details", None))
    else:
        widget.last_non_retry_error = (_get(notification, "turn_id", None), _get(error, "message"))
        _call(widget, "handle_non_retry_error", _get(error, "message"), _get(error, "codex_error_info", None))


def _handle_realtime_notification(widget: Any, kind: str, payload: Any) -> None:
    method = {
        "ThreadRealtimeStarted": "on_realtime_conversation_started",
        "ThreadRealtimeItemAdded": "on_realtime_item_added",
        "ThreadRealtimeOutputAudioDelta": "on_realtime_output_audio_delta",
        "ThreadRealtimeError": "on_realtime_error",
        "ThreadRealtimeClosed": "on_realtime_conversation_closed",
    }.get(kind)
    if method is not None:
        _call(widget, method, payload)
    elif kind == "ThreadRealtimeSdp":
        _call(widget, "on_realtime_conversation_sdp", _get(payload, "sdp"))


def _plan_update_args(payload: Any) -> Dict[str, Any]:
    return {
        "explanation": _get(payload, "explanation", None),
        "plan": [
            {"step": _get(step, "step"), "status": _status_name(_get(step, "status"))}
            for step in (_get(payload, "plan", ()) or ())
        ],
    }


def token_usage_info_from_app_server(token_usage: Any) -> TokenUsageInfo:
    """Match Rust ``token_usage_info_from_app_server`` field mapping."""

    total = _get(token_usage, "total")
    last = _get(token_usage, "last")
    return TokenUsageInfo(
        total_token_usage=_token_usage_from_app_server(total),
        last_token_usage=_token_usage_from_app_server(last),
        model_context_window=_get(token_usage, "model_context_window", None),
    )


def _token_usage_from_app_server(token_usage: Any) -> TokenUsage:
    return TokenUsage(
        total_tokens=int(_get(token_usage, "total_tokens", 0) or 0),
        input_tokens=int(_get(token_usage, "input_tokens", 0) or 0),
        cached_input_tokens=int(_get(token_usage, "cached_input_tokens", 0) or 0),
        output_tokens=int(_get(token_usage, "output_tokens", 0) or 0),
        reasoning_output_tokens=int(_get(token_usage, "reasoning_output_tokens", 0) or 0),
    )


def _kind(value: Union[ServerNotification, Mapping[str, Any], Any]) -> str:
    raw = _get(value, "kind", None) or _get(value, "type", None)
    if raw is None and isinstance(value, ServerNotification):
        raw = value.kind
    if raw is None:
        raise ValueError("notification/item is missing a kind/type discriminator")
    return _status_name(raw)


def _payload(value: Union[ServerNotification, Mapping[str, Any], Any]) -> Any:
    if isinstance(value, ServerNotification):
        return value.payload
    payload = _get(value, "payload", None)
    return value if payload is None else payload


def _get(value: Union[Mapping[str, Any], Any], key: str, default: Any = ...):
    if isinstance(value, Mapping):
        if default is ...:
            return value[key]
        return value.get(key, default)
    if default is ...:
        return getattr(value, key)
    return getattr(value, key, default)


def _status_name(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    text = str(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _replay_name(value: Optional[Union[ReplayKind, str]]) -> Optional[str]:
    return None if value is None else _status_name(value)


def _call(target: Any, method_name: str, *args: Any) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        raise AttributeError(f"protocol target does not implement {method_name}()")
    return method(*args)


def _call_optional(target: Any, method_name: str, *args: Any, default: Any = None) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        return default
    return method(*args)


_NOOP_NOTIFICATIONS = {
    "ServerRequestResolved",
    "AccountUpdated",
    "AccountRateLimitsUpdated",
    "ThreadStarted",
    "ThreadStatusChanged",
    "ThreadArchived",
    "ThreadUnarchived",
    "RawResponseItemCompleted",
    "CommandExecOutputDelta",
    "ProcessOutputDelta",
    "ProcessExited",
    "FileChangePatchUpdated",
    "McpToolCallProgress",
    "McpServerOauthLoginCompleted",
    "AppListUpdated",
    "RemoteControlStatusChanged",
    "ExternalAgentConfigImportCompleted",
    "FsChanged",
    "FuzzyFileSearchSessionUpdated",
    "FuzzyFileSearchSessionCompleted",
    "ThreadRealtimeTranscriptDelta",
    "ThreadRealtimeTranscriptDone",
    "WindowsWorldWritableWarning",
    "WindowsSandboxSetupCompleted",
    "AccountLoginCompleted",
}
