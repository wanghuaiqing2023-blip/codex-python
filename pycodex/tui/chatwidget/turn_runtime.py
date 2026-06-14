"""Semantic turn-runtime port for Rust ``codex-tui::chatwidget::turn_runtime``.

Rust source: ``codex/codex-rs/tui/src/chatwidget/turn_runtime.rs``.

The Rust file is an ``impl ChatWidget`` module.  Python represents the owned
state transitions with a compact semantic runtime object so module-local
behavior can be tested without constructing the full TUI widget tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Set, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::turn_runtime",
    source="codex/codex-rs/tui/src/chatwidget/turn_runtime.rs",
)

PLAN_IMPLEMENTATION_TITLE = "Ready to implement?"
TRUSTED_ACCESS_FOR_CYBER_VERIFICATION_WARNING = (
    "Trusted access for cyber is enabled. Review generated commands carefully."
)


class TerminalTitleStatusKind(str, Enum):
    IDLE = "idle"
    WORKING = "working"


class TurnAbortReason(str, Enum):
    BUDGET_LIMITED = "budget_limited"
    OTHER = "other"


class StepStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"


class ModeKind(str, Enum):
    PLAN = "plan"
    CHAT = "chat"


@dataclass(frozen=True)
class PlanItem:
    status: StepStatus
    text: str = ""


@dataclass(frozen=True)
class UpdatePlanArgs:
    plan: List[PlanItem]


@dataclass(frozen=True)
class TokenUsageInfo:
    total_token_limit: Optional[int] = None
    total_tokens: Optional[int] = None
    used_percent: Optional[int] = None


@dataclass
class RuntimeMetricsSummary:
    websocket_timing_label: Optional[str] = None
    values: List[Any] = field(default_factory=list)

    def is_empty(self) -> bool:
        return self.websocket_timing_label is None and not self.values

    def merge(self, other: "RuntimeMetricsSummary") -> None:
        if other.websocket_timing_label is not None:
            self.websocket_timing_label = other.websocket_timing_label
        self.values.extend(other.values)


@dataclass
class SessionTelemetry:
    pending_delta: Optional[RuntimeMetricsSummary] = None
    reset_count: int = 0

    def runtime_metrics_summary(self) -> Optional[RuntimeMetricsSummary]:
        delta = self.pending_delta
        self.pending_delta = None
        return delta

    def reset_runtime_metrics(self) -> None:
        self.pending_delta = None
        self.reset_count += 1


@dataclass
class TurnLifecycle:
    agent_turn_running: bool = False
    started_at: Any = None
    finish_count: int = 0

    def start(self, now: Any = None) -> None:
        self.agent_turn_running = True
        self.started_at = now

    def finish(self) -> None:
        self.agent_turn_running = False
        self.finish_count += 1


@dataclass
class BottomPane:
    task_running: bool = False
    quit_shortcut_hint_cleared: bool = False
    interrupt_hint_visible: bool = False
    modal_or_popup_active: bool = False
    selection_views: List[Any] = field(default_factory=list)

    def set_task_running(self, value: bool) -> None:
        self.task_running = bool(value)

    def clear_quit_shortcut_hint(self) -> None:
        self.quit_shortcut_hint_cleared = True

    def set_interrupt_hint_visible(self, visible: bool) -> None:
        self.interrupt_hint_visible = bool(visible)

    def no_modal_or_popup_active(self) -> bool:
        return not self.modal_or_popup_active

    def show_selection_view(self, params: Any) -> None:
        self.selection_views.append(params)


@dataclass
class TranscriptState:
    saw_copy_source_this_turn: bool = False
    saw_plan_item_this_turn: bool = False
    saw_plan_update_this_turn: bool = False
    latest_proposed_plan_markdown: Optional[str] = None
    last_plan_progress: Optional[Tuple[int, int]] = None
    needs_final_message_separator: bool = False
    had_work_activity: bool = False
    reset_turn_flags_count: int = 0

    def reset_turn_flags(self) -> None:
        self.saw_copy_source_this_turn = False
        self.saw_plan_item_this_turn = False
        self.saw_plan_update_this_turn = False
        self.last_plan_progress = None
        self.needs_final_message_separator = False
        self.had_work_activity = False
        self.reset_turn_flags_count += 1


@dataclass
class InputQueue:
    user_turn_pending_start: bool = False
    submit_pending_steers_after_interrupt: bool = False
    pending_steers: List[Any] = field(default_factory=list)
    queued_follow_up_messages: List[Any] = field(default_factory=list)

    def has_queued_follow_up_messages(self) -> bool:
        return bool(self.queued_follow_up_messages)


@dataclass
class StatusState:
    retry_status_header: Optional[str] = None
    pending_status_indicator_restore: bool = False
    terminal_title_status_kind: TerminalTitleStatusKind = TerminalTitleStatusKind.IDLE


@dataclass
class WarningDisplayState:
    seen: Set[str] = field(default_factory=set)

    def should_display(self, message: str) -> bool:
        if message in self.seen:
            return False
        self.seen.add(message)
        return True


@dataclass
class SemanticTurnRuntime:
    bottom_pane: BottomPane = field(default_factory=BottomPane)
    turn_lifecycle: TurnLifecycle = field(default_factory=TurnLifecycle)
    transcript: TranscriptState = field(default_factory=TranscriptState)
    input_queue: InputQueue = field(default_factory=InputQueue)
    status_state: StatusState = field(default_factory=StatusState)
    warning_display_state: WarningDisplayState = field(default_factory=WarningDisplayState)
    session_telemetry: SessionTelemetry = field(default_factory=SessionTelemetry)
    turn_runtime_metrics: RuntimeMetricsSummary = field(default_factory=RuntimeMetricsSummary)
    mcp_startup_status: Optional[Any] = None
    active_hook_cell: Optional[Any] = None
    plan_stream_controller: Optional[Any] = None
    stream_controller: Optional[Any] = None
    adaptive_chunking_reset_count: int = 0
    running_commands: List[Any] = field(default_factory=list)
    suppressed_exec_calls: List[Any] = field(default_factory=list)
    last_unified_wait: Optional[Any] = None
    unified_exec_wait_streak: Optional[Any] = None
    full_reasoning_buffer: List[Any] = field(default_factory=list)
    reasoning_buffer: List[Any] = field(default_factory=list)
    quit_shortcut_expires_at: Optional[Any] = None
    quit_shortcut_key: Optional[Any] = None
    status_header: Optional[str] = None
    history: List[Any] = field(default_factory=list)
    notifications: List[Any] = field(default_factory=list)
    ambient_pet_notifications: List[Any] = field(default_factory=list)
    redraw_requests: int = 0
    active_cell_revisions: int = 0
    status_surface_refreshes: int = 0
    plan_mode_nudge_refreshes: int = 0
    status_line_branch_refreshes: int = 0
    status_line_git_summary_refreshes: int = 0
    pending_rate_limit_prompt_checks: int = 0
    queued_input_send_attempts: int = 0
    collaboration_modes: bool = True
    mode_kind: ModeKind = ModeKind.CHAT
    rate_limit_switch_prompt_pending: bool = False
    token_info: Optional[TokenUsageInfo] = None

    def update_task_running_state(self) -> None:
        self.bottom_pane.set_task_running(
            self.turn_lifecycle.agent_turn_running or self.mcp_startup_status is not None
        )
        self.refresh_plan_mode_nudge()
        self.refresh_status_surfaces()

    def collect_runtime_metrics_delta(self) -> None:
        delta = self.session_telemetry.runtime_metrics_summary()
        if delta is not None:
            self.apply_runtime_metrics_delta(delta)

    def apply_runtime_metrics_delta(self, delta: RuntimeMetricsSummary) -> None:
        should_log_timing = has_websocket_timing_metrics(delta)
        self.turn_runtime_metrics.merge(delta)
        if should_log_timing:
            self.log_websocket_timing_totals(delta)

    def log_websocket_timing_totals(self, delta: RuntimeMetricsSummary) -> None:
        if delta.websocket_timing_label:
            self.add_plain_history_lines(["WebSocket timing: " + delta.websocket_timing_label])

    def refresh_runtime_metrics(self) -> None:
        self.collect_runtime_metrics_delta()

    def on_task_started(self) -> None:
        self.input_queue.user_turn_pending_start = False
        self.turn_lifecycle.start("now")
        self.transcript.reset_turn_flags()
        self.adaptive_chunking_reset_count += 1
        self.plan_stream_controller = None
        self.turn_runtime_metrics = RuntimeMetricsSummary()
        self.session_telemetry.reset_runtime_metrics()
        self.bottom_pane.clear_quit_shortcut_hint()
        self.quit_shortcut_expires_at = None
        self.quit_shortcut_key = None
        self.update_task_running_state()
        self.status_state.retry_status_header = None
        if self.active_hook_cell is not None:
            self.active_hook_cell = None
            self.bump_active_cell_revision()
        self.status_state.pending_status_indicator_restore = False
        self.bottom_pane.set_interrupt_hint_visible(True)
        self.status_state.terminal_title_status_kind = TerminalTitleStatusKind.WORKING
        if self.mcp_startup_status is None or not self.status_header_is_mcp_startup_owned():
            self.set_status_header("Working")
        self.full_reasoning_buffer.clear()
        self.reasoning_buffer.clear()
        self.set_ambient_pet_notification("running", None)
        self.request_redraw()

    def finalize_turn(self) -> None:
        self.clear_active_stream_tail()
        self.finalize_active_cell_as_failed()
        if self.active_hook_cell is not None:
            self.active_hook_cell = None
            self.bump_active_cell_revision()
        self.input_queue.user_turn_pending_start = False
        self.turn_lifecycle.finish()
        self.update_task_running_state()
        self.running_commands.clear()
        self.suppressed_exec_calls.clear()
        self.last_unified_wait = None
        self.unified_exec_wait_streak = None
        self.adaptive_chunking_reset_count += 1
        self.stream_controller = None
        self.plan_stream_controller = None
        self.status_state.pending_status_indicator_restore = False
        self.request_status_line_branch_refresh()
        self.request_status_line_git_summary_refresh()
        self.maybe_show_pending_rate_limit_prompt()

    def on_warning(self, message: Any) -> None:
        text = str(message)
        if not self.warning_display_state.should_display(text):
            return
        self.add_to_history({"kind": "warning", "message": text})
        self.request_redraw()

    def on_plan_update(self, update: UpdatePlanArgs) -> None:
        self.transcript.saw_plan_update_this_turn = True
        total = len(update.plan)
        completed = sum(1 for item in update.plan if item.status is StepStatus.COMPLETED)
        self.transcript.last_plan_progress = (completed, total) if total > 0 else None
        self.refresh_status_surfaces()
        self.add_to_history({"kind": "plan_update", "update": update})

    def maybe_prompt_plan_implementation(self) -> None:
        if not self.collaboration_modes_enabled():
            return
        if self.has_queued_follow_up_messages():
            return
        if self.active_mode_kind() is not ModeKind.PLAN:
            return
        if not self.transcript.saw_plan_item_this_turn:
            return
        if not self.bottom_pane.no_modal_or_popup_active():
            return
        if self.rate_limit_switch_prompt_pending:
            return
        self.open_plan_implementation_prompt()

    def open_plan_implementation_prompt(self) -> None:
        params = {
            "title": PLAN_IMPLEMENTATION_TITLE,
            "latest_plan": self.transcript.latest_proposed_plan_markdown,
            "context_usage_label": self.plan_implementation_context_usage_label(),
        }
        self.bottom_pane.show_selection_view(params)
        self.notify({"kind": "plan_mode_prompt", "title": PLAN_IMPLEMENTATION_TITLE})

    def plan_implementation_context_usage_label(self) -> Optional[str]:
        info = self.token_info
        if info is None:
            return None
        percent = self.context_remaining_percent(info)
        used_tokens = self.context_used_tokens(info, percent is not None)
        if percent is not None:
            used_percent = 100 - max(0, min(percent, 100))
            if used_percent <= 0:
                return None
            return str(used_percent) + "% used"
        if used_tokens is not None and used_tokens > 0:
            return format_tokens_compact(used_tokens) + " used"
        return None

    def has_queued_follow_up_messages(self) -> bool:
        return self.input_queue.has_queued_follow_up_messages()

    def interrupted_turn_message(self, reason: TurnAbortReason) -> str:
        return interrupted_turn_message(reason)

    def collaboration_modes_enabled(self) -> bool:
        return self.collaboration_modes

    def active_mode_kind(self) -> ModeKind:
        return self.mode_kind

    def context_remaining_percent(self, info: TokenUsageInfo) -> Optional[int]:
        if info.used_percent is not None:
            return 100 - info.used_percent
        if info.total_token_limit and info.total_tokens is not None:
            remaining = max(info.total_token_limit - info.total_tokens, 0)
            return int((remaining * 100) / info.total_token_limit)
        return None

    def context_used_tokens(self, info: TokenUsageInfo, _has_percent: bool) -> Optional[int]:
        return info.total_tokens

    def status_header_is_mcp_startup_owned(self) -> bool:
        return self.status_header == "MCP startup"

    def set_status_header(self, value: str) -> None:
        self.status_header = value

    def add_plain_history_lines(self, lines: List[Any]) -> None:
        self.history.append({"kind": "plain_lines", "lines": lines})

    def add_to_history(self, item: Any) -> None:
        self.history.append(item)

    def notify(self, notification: Any) -> None:
        self.notifications.append(notification)

    def request_redraw(self) -> None:
        self.redraw_requests += 1

    def bump_active_cell_revision(self) -> None:
        self.active_cell_revisions += 1

    def refresh_plan_mode_nudge(self) -> None:
        self.plan_mode_nudge_refreshes += 1

    def refresh_status_surfaces(self) -> None:
        self.status_surface_refreshes += 1

    def request_status_line_branch_refresh(self) -> None:
        self.status_line_branch_refreshes += 1

    def request_status_line_git_summary_refresh(self) -> None:
        self.status_line_git_summary_refreshes += 1

    def maybe_show_pending_rate_limit_prompt(self) -> None:
        self.pending_rate_limit_prompt_checks += 1

    def maybe_send_next_queued_input(self) -> bool:
        self.queued_input_send_attempts += 1
        if self.input_queue.queued_follow_up_messages:
            self.input_queue.queued_follow_up_messages.pop(0)
            return True
        return False

    def clear_active_stream_tail(self) -> None:
        pass

    def finalize_active_cell_as_failed(self) -> None:
        pass

    def set_ambient_pet_notification(self, kind: str, body: Optional[str]) -> None:
        self.ambient_pet_notifications.append({"kind": kind, "body": body})


ChatWidgetTurnRuntime = SemanticTurnRuntime


def has_websocket_timing_metrics(delta: RuntimeMetricsSummary) -> bool:
    return bool(delta.websocket_timing_label)


def update_task_running_state(runtime: SemanticTurnRuntime) -> None:
    runtime.update_task_running_state()


def on_task_started(runtime: SemanticTurnRuntime) -> None:
    runtime.on_task_started()


def finalize_turn(runtime: SemanticTurnRuntime) -> None:
    runtime.finalize_turn()


def on_warning(runtime: SemanticTurnRuntime, message: Any) -> None:
    runtime.on_warning(message)


def on_plan_update(runtime: SemanticTurnRuntime, update: UpdatePlanArgs) -> None:
    runtime.on_plan_update(update)


def interrupted_turn_message(reason: TurnAbortReason) -> str:
    if reason is TurnAbortReason.BUDGET_LIMITED:
        return "Goal budget reached - the turn was stopped."
    return (
        "Conversation interrupted - tell the model what to do differently. "
        "Something went wrong? Hit `/feedback` to report the issue."
    )


def format_tokens_compact(tokens: int) -> str:
    if tokens >= 1_000_000:
        value = tokens / 1_000_000
        suffix = "M"
    elif tokens >= 1_000:
        value = tokens / 1_000
        suffix = "K"
    else:
        return str(tokens)
    if value.is_integer():
        return str(int(value)) + suffix
    return ("%.1f" % value).rstrip("0").rstrip(".") + suffix


__all__ = [
    "BottomPane",
    "ChatWidgetTurnRuntime",
    "InputQueue",
    "ModeKind",
    "PLAN_IMPLEMENTATION_TITLE",
    "PlanItem",
    "RUST_MODULE",
    "RuntimeMetricsSummary",
    "SemanticTurnRuntime",
    "SessionTelemetry",
    "StatusState",
    "StepStatus",
    "TRUSTED_ACCESS_FOR_CYBER_VERIFICATION_WARNING",
    "TerminalTitleStatusKind",
    "TokenUsageInfo",
    "TranscriptState",
    "TurnAbortReason",
    "TurnLifecycle",
    "UpdatePlanArgs",
    "WarningDisplayState",
    "finalize_turn",
    "format_tokens_compact",
    "has_websocket_timing_metrics",
    "interrupted_turn_message",
    "on_plan_update",
    "on_task_started",
    "on_warning",
    "update_task_running_state",
]
