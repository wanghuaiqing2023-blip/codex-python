"""Semantic model for Rust ``codex-tui::app::event_dispatch``.

This module is intentionally not a full port of the TUI event loop.  It
captures small, module-owned decision points that can be represented without
ratatui/app-server runtime objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, Optional, Tuple, Union

from pycodex.ansi_escape import AnsiStyle, ansi_escape_line

from .._porting import RustTuiModule
from ..custom_terminal import AlternateScreenRenderer
from ..diff_render import create_diff_summary
from ..pager_overlay import StaticOverlay
from ..ratatui_bridge import Rect
from ..ratatui_bridge.style import Color, Modifier, Style
from ..ratatui_bridge.text import Line, Span
from ..tui.frame_rate_limiter import MIN_FRAME_INTERVAL


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::event_dispatch",
    source="codex/codex-rs/tui/src/app/event_dispatch.rs",
    status="complete",
)

# Rust: const SHUTDOWN_FIRST_EXIT_TIMEOUT: Duration = Duration::from_secs(2)
SHUTDOWN_FIRST_EXIT_TIMEOUT = 2.0


@dataclass(frozen=True)
class TerminalFullScreenApprovalController:
    """Run fixed-Rust ``FullScreenApprovalRequest`` through the shared pager."""

    get_input_source: Callable[[], Any]
    writer: Any
    terminal_size: Callable[[], Any]
    keymap: Callable[[], Any | None]
    run_external_repaint: Callable[[Callable[[], bool]], bool]
    poll_timeout: float = 0.1

    def __call__(self, request: Any) -> bool:
        title, lines = full_screen_approval_projection(request)

        def run() -> bool:
            return run_terminal_static_overlay(
                lines=lines,
                title=title,
                source=self.get_input_source(),
                writer=self.writer,
                terminal_size=self.terminal_size,
                keymap=self.keymap(),
                poll_timeout=self.poll_timeout,
            )

        return bool(self.run_external_repaint(run))


@dataclass(frozen=True)
class TerminalDiffOverlayController:
    """Apply Rust ``AppEvent::DiffResult`` through the shared static pager."""

    get_input_source: Callable[[], Any]
    writer: Any
    terminal_size: Callable[[], Any]
    keymap: Callable[[], Any | None]
    run_external_repaint: Callable[[Callable[[], bool]], bool]
    poll_timeout: float = 0.1

    def __call__(self, text: str) -> bool:
        raw_lines = str(text).splitlines()
        lines: tuple[Line, ...]
        if raw_lines:
            lines = tuple(_bridge_ansi_line(raw) for raw in raw_lines)
        else:
            lines = (
                Line.from_spans(
                    (Span("No changes detected.", Style().italic()),)
                ),
            )

        def run() -> bool:
            return run_terminal_static_overlay(
                lines=lines,
                title="D I F F",
                source=self.get_input_source(),
                writer=self.writer,
                terminal_size=self.terminal_size,
                keymap=self.keymap(),
                poll_timeout=self.poll_timeout,
            )

        return bool(self.run_external_repaint(run))


def full_screen_approval_projection(request: Any, width: int = 120) -> tuple[str, tuple[str, ...]]:
    kind = str(_field(request, "kind", ""))
    if kind == "ApplyPatch":
        rendered = create_diff_summary(
            _field(request, "changes", {}) or {},
            _field(request, "cwd", ".") or ".",
            width,
        )
        return "P A T C H", tuple(_line_text(line) for line in rendered)
    if kind == "Exec":
        command = _field(request, "command", ()) or ()
        return "E X E C", (" ".join(str(part) for part in command),)
    if kind == "Permissions":
        from ..bottom_pane.approval_overlay import format_requested_permissions_rule

        lines = []
        reason = _field(request, "reason")
        if reason:
            lines.extend((f"Reason: {reason}", ""))
        rule = format_requested_permissions_rule(_field(request, "permissions"))
        if rule:
            lines.append(f"Permission rule: {rule}")
        return "P E R M I S S I O N S", tuple(lines)
    return "E L I C I T A T I O N", (
        f"Server: {_field(request, 'server_name', '')}",
        "",
        str(_field(request, "message", "")),
    )


def run_terminal_static_overlay(
    *,
    lines: Tuple[object, ...],
    title: str,
    source: Any,
    writer: Any,
    terminal_size: Callable[[], Any],
    keymap: Any | None = None,
    poll_timeout: float = 0.1,
) -> bool:
    if source is None:
        return False
    overlay = StaticOverlay.with_title(lines, title, keymap)
    renderer = AlternateScreenRenderer(writer)
    target_frame_interval = MIN_FRAME_INTERVAL / 1_000_000_000
    renderer.enter()
    try:
        dirty = True
        next_frame_at = 0.0
        while True:
            size = terminal_size()
            area = Rect(0, 0, max(0, int(size.columns)), max(0, int(size.lines)))
            now = time.monotonic()
            if dirty and now >= next_frame_at:
                renderer.render_lines(overlay.render_frame(area), size)
                dirty = False
            wait = max(0.0, float(poll_timeout))
            if dirty:
                wait = min(wait, max(0.0, next_frame_at - now))
            event = source.poll(wait)
            if event is None:
                continue
            kind = str(getattr(event, "kind", "")).lower().replace("-", "_")
            text = str(getattr(event, "text", ""))
            if kind in {"escape", "esc", "ctrl_t"}:
                return True
            if kind in {"line", "eof"}:
                # Cooked-line input is a compatibility path, not a Rust-like
                # key stream. Leave the modal and return the command/EOF to the
                # outer app loop instead of consuming it inside the pager.
                push_front = getattr(source, "push_front", None)
                if callable(push_front):
                    push_front(event)
                return True
            if kind == "resize":
                dirty = True
                next_frame_at = 0.0
            else:
                handled = overlay.handle_input(kind, text, area)
                if overlay.is_done():
                    return True
                if handled:
                    dirty = True
                    next_frame_at = time.monotonic() + target_frame_interval
    finally:
        renderer.leave()


def _bridge_ansi_line(raw: str) -> Line:
    parsed = ansi_escape_line(raw)
    return Line.from_spans(
        Span(span.text, _bridge_ansi_style(span.style))
        for span in parsed.spans
    )


def _bridge_ansi_style(value: AnsiStyle) -> Style:
    style = Style(
        fg=_bridge_ansi_color(value.fg),
        bg=_bridge_ansi_color(value.bg),
    )
    modifiers: list[Modifier] = []
    if value.bold:
        modifiers.append(Modifier.BOLD)
    if value.dim:
        modifiers.append(Modifier.DIM)
    if value.italic:
        modifiers.append(Modifier.ITALIC)
    if value.underlined:
        modifiers.append(Modifier.UNDERLINED)
    if value.reversed:
        modifiers.append(Modifier.REVERSED)
    return style.add_modifier(*modifiers)


def _bridge_ansi_color(value: object) -> Color | None:
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 3:
        return Color.rgb(*value)
    if isinstance(value, int):
        return Color.indexed(value)
    return Color.named(str(value))


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _line_text(line: Any) -> str:
    spans = getattr(line, "spans", None)
    if spans is None:
        return str(line)
    return "".join(str(getattr(span, "content", span)) for span in spans)


class ExitMode(str, Enum):
    """Semantic counterpart of Rust ``ExitMode`` for this module slice."""

    ShutdownFirst = "shutdown_first"
    Immediate = "immediate"


class ExitReason(str, Enum):
    """Semantic counterpart of Rust ``ExitReason`` values used here."""

    UserRequested = "user_requested"


@dataclass(frozen=True, eq=True)
class AppRunControl:
    """Semantic counterpart for the Rust dispatcher return control."""

    kind: str
    reason: Optional[Union[ExitReason, str]] = None

    @classmethod
    def exit(cls, reason: Union[ExitReason, str] = ExitReason.UserRequested) -> "AppRunControl":
        return cls("exit", reason)

    @classmethod
    def continue_(cls) -> "AppRunControl":
        return cls("continue", None)


@dataclass(eq=True)
class EventDispatchState:
    """Minimal mutable App state touched by Rust ``handle_exit_mode``."""

    active_thread_id: Optional[str] = None
    chat_widget_thread_id: Optional[str] = None
    pending_shutdown_exit_thread_id: Optional[str] = None


@dataclass(frozen=True, eq=True)
class ExitModePlan:
    """Observable decisions made by ``handle_exit_mode``.

    Rust performs the actual async shutdown inline.  Python exposes that as a
    plan so callers can keep the same state-transition contract without
    pretending to own the app-server runtime.
    """

    run_control: AppRunControl
    shutdown_thread_id: Optional[str]
    timeout_seconds: Optional[float]


@dataclass(frozen=True, eq=True)
class EventDispatchPlan:
    """Semantic dispatch result for one Rust ``AppEvent``.

    Rust ``handle_event`` is deliberately a central router: most branches
    delegate to other ``app::*`` modules, mutate widgets, or call app-server
    runtime APIs.  Python keeps that module boundary by exposing the router's
    own observable decision as a stable plan instead of pretending to execute
    those neighboring side effects here.
    """

    action: str
    run_control: AppRunControl = field(default_factory=AppRunControl.continue_)
    updates: Tuple[Tuple[str, Any], ...] = ()
    messages: Tuple[str, ...] = ()
    schedule_frame: bool = False
    enter_alt_screen: bool = False
    forward_event: Optional[str] = None
    exit_mode_plan: Optional[ExitModePlan] = None


def _coerce_exit_mode(mode: Union[ExitMode, str]) -> ExitMode:
    if isinstance(mode, ExitMode):
        return mode
    normalized = mode.replace("-", "_").lower()
    for candidate in ExitMode:
        if normalized in {candidate.value, candidate.name.lower()}:
            return candidate
    raise ValueError("unknown ExitMode: {!r}".format(mode))


def handle_exit_mode_plan(state: EventDispatchState, mode: Union[ExitMode, str]) -> ExitModePlan:
    """Port the Rust ``handle_exit_mode`` state transition as a pure plan.

    Rust behavior:
    - ``ShutdownFirst`` chooses ``active_thread_id`` or falls back to the chat
      widget thread id, stores it as pending, waits up to two seconds when a
      thread exists, clears the pending marker, then exits as user requested.
    - ``Immediate`` clears the pending marker and exits as user requested
      without attempting shutdown.
    """

    exit_mode = _coerce_exit_mode(mode)
    if exit_mode is ExitMode.ShutdownFirst:
        shutdown_thread_id = state.active_thread_id or state.chat_widget_thread_id
        state.pending_shutdown_exit_thread_id = shutdown_thread_id
        timeout_seconds = SHUTDOWN_FIRST_EXIT_TIMEOUT if shutdown_thread_id is not None else None
        state.pending_shutdown_exit_thread_id = None
        return ExitModePlan(
            run_control=AppRunControl.exit(ExitReason.UserRequested),
            shutdown_thread_id=shutdown_thread_id,
            timeout_seconds=timeout_seconds,
        )

    state.pending_shutdown_exit_thread_id = None
    return ExitModePlan(
        run_control=AppRunControl.exit(ExitReason.UserRequested),
        shutdown_thread_id=None,
        timeout_seconds=None,
    )


def _camel_to_snake(value: str) -> str:
    out = []
    for index, char in enumerate(value):
        if char.isupper() and index and (not value[index - 1].isupper()):
            out.append("_")
        out.append(char.lower())
    return "".join(out).replace("__", "_")


def _event_variant(event: Any) -> str:
    if isinstance(event, str):
        return event
    if isinstance(event, dict):
        for key in ("variant", "type", "kind", "event"):
            value = event.get(key)
            if isinstance(value, str):
                return value
        if len(event) == 1:
            return next(iter(event.keys()))
    for attr in ("variant", "type", "kind", "event"):
        value = getattr(event, attr, None)
        if isinstance(value, str):
            return value
    return event.__class__.__name__


def _event_payload(event: Any) -> Any:
    if isinstance(event, dict):
        for key in ("payload", "data", "value"):
            if key in event:
                return event[key]
        if len(event) == 1:
            return next(iter(event.values()))
        if any(isinstance(event.get(key), str) for key in ("variant", "type", "kind", "event")):
            return event
    return getattr(event, "payload", None)


def _payload_value(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _coerce_event_exit_mode(payload: Any) -> ExitMode:
    mode = _payload_value(payload, "mode", payload)
    if isinstance(mode, dict):
        mode = _payload_value(mode, "mode", ExitMode.ShutdownFirst)
    if mode is None:
        mode = ExitMode.ShutdownFirst
    return _coerce_exit_mode(mode)


def dispatch_event_plan(state: EventDispatchState, event: Any) -> EventDispatchPlan:
    """Return the Rust-style dispatch decision for one ``AppEvent``.

    The function accepts a lightweight event representation: a Rust variant
    name string, a ``{"Variant": payload}`` mapping, a mapping with
    ``variant``/``type``/``kind``, or an object with one of those attributes.
    """

    variant = _event_variant(event)
    payload = _event_payload(event)

    if variant == "NewSession":
        return EventDispatchPlan(
            action="start_fresh_session_with_summary_hint",
            updates=(("start_fresh_session", payload),),
            schedule_frame=True,
        )
    if variant == "StartupThreadStarted":
        return EventDispatchPlan(
            action="handle_startup_thread_started",
            updates=(("startup_thread_started", payload),),
            schedule_frame=True,
        )
    if variant == "ClearUi":
        return EventDispatchPlan(
            action="clear_ui_and_start_fresh_session",
            updates=(
                ("clear_terminal_ui", None),
                ("reset_app_ui_state_after_clear", None),
                ("start_fresh_session_with_summary_hint", payload),
            ),
            schedule_frame=True,
        )
    if variant == "RawOutputModeChanged":
        return EventDispatchPlan(
            action="apply_raw_output_mode",
            updates=(("raw_output_mode_changed", payload),),
            schedule_frame=True,
        )
    if variant == "ClearUiAndSubmitUserMessage":
        return EventDispatchPlan(
            action="clear_ui_and_submit_user_message",
            updates=(
                ("clear_terminal_ui", None),
                ("reset_app_ui_state_after_clear", None),
                ("create_initial_user_message", payload),
                ("submit_user_message", payload),
            ),
            schedule_frame=True,
        )
    if variant == "SubmitUserMessageWithMode":
        return EventDispatchPlan(
            action="submit_user_message_with_mode",
            updates=(("submit_user_message_with_mode", payload),),
        )

    history_actions = {
        "BeginInitialHistoryReplayBuffer": "begin_initial_history_replay_buffer",
        "BeginThreadSwitchHistoryReplayBuffer": "begin_thread_switch_history_replay_buffer",
        "InsertHistoryCell": "insert_history_cell",
        "EndInitialHistoryReplayBuffer": "end_initial_history_replay_buffer",
        "EndThreadSwitchHistoryReplayBuffer": "end_thread_switch_history_replay_buffer",
    }
    if variant in history_actions:
        return EventDispatchPlan(
            action=history_actions[variant],
            updates=((history_actions[variant], payload),),
            schedule_frame=variant.startswith("End"),
        )

    if variant == "Exit":
        exit_plan = handle_exit_mode_plan(state, _coerce_event_exit_mode(payload))
        updates = ()
        if exit_plan.shutdown_thread_id is not None:
            updates = (("show_shutdown_feedback", exit_plan.shutdown_thread_id),)
        return EventDispatchPlan(
            action="exit",
            run_control=exit_plan.run_control,
            updates=updates,
            exit_mode_plan=exit_plan,
        )
    if variant == "Logout":
        error = _payload_value(payload, "error", None)
        if error is not None:
            return EventDispatchPlan(
                action="logout_account_failed",
                run_control=AppRunControl.continue_(),
                updates=(("logout_error", error),),
                messages=(str(error),),
                schedule_frame=True,
            )
        exit_plan = handle_exit_mode_plan(state, ExitMode.ShutdownFirst)
        updates = (("logout", payload),)
        if exit_plan.shutdown_thread_id is not None:
            updates = updates + (("show_shutdown_feedback", exit_plan.shutdown_thread_id),)
        return EventDispatchPlan(
            action="logout_account_then_shutdown",
            run_control=exit_plan.run_control,
            updates=updates,
            exit_mode_plan=exit_plan,
        )
    if variant == "FatalExitRequest":
        reason = _payload_value(payload, "reason", _payload_value(payload, "message", "fatal_exit_request"))
        return EventDispatchPlan(
            action="fatal_exit_request",
            run_control=AppRunControl.exit("fatal:{0}".format(reason)),
            messages=(str(reason),),
        )
    if variant == "UpdateModel":
        model = _payload_value(payload, "model", payload)
        return EventDispatchPlan(
            action="update_model",
            updates=(("update_model", model),),
            schedule_frame=True,
        )
    if variant == "UpdateReasoningEffort":
        effort = _payload_value(payload, "effort", payload)
        return EventDispatchPlan(
            action="update_reasoning_effort",
            updates=(("update_reasoning_effort", effort),),
            schedule_frame=True,
        )
    if variant == "PersistModelSelection":
        model = _payload_value(payload, "model", None)
        effort = _payload_value(payload, "effort", None)
        return EventDispatchPlan(
            action="persist_model_selection",
            updates=(("persist_model_selection", {"model": model, "effort": effort}),),
            schedule_frame=True,
        )
    if variant == "SyntaxThemeSelected":
        name = _payload_value(payload, "name", payload)
        return EventDispatchPlan(
            action="persist_syntax_theme",
            updates=(("persist_syntax_theme", name),),
            schedule_frame=True,
        )
    if variant == "SyntaxThemePreviewed":
        return EventDispatchPlan(
            action="refresh_syntax_theme_preview",
            updates=(("refresh_syntax_theme_preview", None),),
            schedule_frame=True,
        )
    if variant == "StatusLineSetup":
        items = _payload_value(payload, "items", ())
        use_theme_colors = bool(_payload_value(payload, "use_theme_colors", False))
        status_line_setup = {
            "items": items,
            "use_theme_colors": use_theme_colors,
        }
        return EventDispatchPlan(
            action="setup_status_line",
            updates=(("setup_status_line", status_line_setup),),
            schedule_frame=True,
        )
    if variant == "StatusLineSetupCancelled":
        return EventDispatchPlan(
            action="cancel_status_line_setup",
            updates=(("cancel_status_line_setup", None),),
            schedule_frame=True,
        )
    if variant == "TerminalTitleSetup":
        items = _payload_value(payload, "items", ())
        return EventDispatchPlan(
            action="setup_terminal_title",
            updates=(("setup_terminal_title", items),),
            schedule_frame=True,
        )
    if variant == "TerminalTitleSetupPreview":
        items = _payload_value(payload, "items", ())
        return EventDispatchPlan(
            action="preview_terminal_title",
            updates=(("preview_terminal_title", items),),
            schedule_frame=True,
        )
    if variant == "TerminalTitleSetupCancelled":
        return EventDispatchPlan(
            action="cancel_terminal_title_setup",
            updates=(("cancel_terminal_title_setup", None),),
            schedule_frame=True,
        )
    if variant == "RefreshRateLimits":
        origin = _payload_value(payload, "origin", payload)
        return EventDispatchPlan(
            action="refresh_rate_limits",
            updates=(("refresh_rate_limits", origin),),
        )
    if variant == "RateLimitsLoaded":
        origin = _payload_value(payload, "origin", None)
        result = _payload_value(payload, "result", None)
        return EventDispatchPlan(
            action="rate_limits_loaded",
            updates=(("rate_limits_loaded", {"origin": origin, "result": result}),),
            schedule_frame=True,
        )
    if variant == "DiffResult":
        text = _payload_value(payload, "text", payload)
        return EventDispatchPlan(
            action="diff_result",
            updates=(("diff_result", text),),
            schedule_frame=True,
        )
    if variant == "FetchMcpInventory":
        request = {
            "detail": _payload_value(payload, "detail", "tools_and_auth_only"),
            "thread_id": _payload_value(payload, "thread_id", None),
        }
        return EventDispatchPlan(
            action="fetch_mcp_inventory",
            updates=(("fetch_mcp_inventory", request),),
            schedule_frame=True,
        )
    if variant == "McpInventoryLoaded":
        result = {
            "detail": _payload_value(payload, "detail", "tools_and_auth_only"),
            "thread_id": _payload_value(payload, "thread_id", None),
            "statuses": _payload_value(payload, "statuses", None),
            "error": _payload_value(payload, "error", None),
        }
        return EventDispatchPlan(
            action="mcp_inventory_loaded",
            updates=(("mcp_inventory_loaded", result),),
            schedule_frame=True,
        )
    if variant == "FetchConnectorsList":
        force_refetch = bool(_payload_value(payload, "force_refetch", False))
        return EventDispatchPlan(
            action="fetch_connectors_list",
            updates=(("fetch_connectors_list", {"force_refetch": force_refetch}),),
            schedule_frame=True,
        )
    if variant == "FetchPluginsList":
        cwd = _payload_value(payload, "cwd", None)
        return EventDispatchPlan(
            action="fetch_plugins_list",
            updates=(("fetch_plugins_list", {"cwd": cwd}),),
            schedule_frame=True,
        )

    delegated_actions = {
        "OpenUrlInBrowser": "open_url_in_browser",
        "OpenThreadGoalMenu": "open_thread_goal_menu",
        "OpenThreadGoalEditor": "open_thread_goal_editor",
        "SetThreadGoalObjective": "set_thread_goal_objective",
        "SetThreadGoalStatus": "set_thread_goal_status",
        "ClearThreadGoal": "clear_thread_goal",
        "OpenResumePicker": "open_resume_picker",
        "OpenAgentPicker": "open_agent_picker",
        "StartSide": "start_side",
        "ResumeSessionByIdOrName": "resume_session_by_id_or_name",
        "ForkCurrentSession": "fork_current_session",
        "ConsolidateAgentMessage": "consolidate_agent_message",
        "ConsolidateProposedPlan": "consolidate_proposed_plan",
        "ApplyThreadRollback": "apply_thread_rollback",
        "StartCommitAnimation": "start_commit_animation",
        "StopCommitAnimation": "stop_commit_animation",
        "CommitTick": "commit_tick",
        "CodexOp": "handle_codex_op",
        "AppendMessageHistoryEntry": "append_message_history_entry",
        "PetSelected": "handle_pet_selected",
        "PetDisabled": "handle_pet_disabled",
        "PetPreviewRequested": "handle_pet_preview_requested",
        "PetPreviewLoaded": "handle_pet_preview_loaded",
        "PetSelectionLoaded": "handle_pet_selection_loaded",
        "ConfiguredPetLoaded": "handle_configured_pet_loaded",
        "KeyEvent": "handle_key_event",
        "Paste": "handle_paste",
        "Resize": "handle_resize",
        "Redraw": "redraw",
        "RequestRedraw": "request_redraw",
    }
    if variant in delegated_actions:
        return EventDispatchPlan(
            action=delegated_actions[variant],
            updates=((delegated_actions[variant], payload),),
            schedule_frame=True,
            forward_event=variant,
        )

    action = "handle_{0}".format(_camel_to_snake(variant))
    return EventDispatchPlan(
        action=action,
        updates=((action, payload),),
        schedule_frame=True,
        forward_event=variant,
    )


handle_event_plan = dispatch_event_plan


async def handle_event(state: EventDispatchState, event: Any) -> EventDispatchPlan:
    return dispatch_event_plan(state, event)


async def handle_exit_mode(state: EventDispatchState, mode: Union[ExitMode, str]) -> ExitModePlan:
    return handle_exit_mode_plan(state, mode)


__all__ = [
    "RUST_MODULE",
    "SHUTDOWN_FIRST_EXIT_TIMEOUT",
    "AppRunControl",
    "EventDispatchPlan",
    "EventDispatchState",
    "TerminalDiffOverlayController",
    "TerminalFullScreenApprovalController",
    "ExitMode",
    "ExitModePlan",
    "ExitReason",
    "dispatch_event_plan",
    "full_screen_approval_projection",
    "handle_event",
    "handle_event_plan",
    "handle_exit_mode",
    "handle_exit_mode_plan",
    "run_terminal_static_overlay",
]
