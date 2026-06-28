"""Session lifecycle helpers for Rust ``codex-tui::app::session_lifecycle``.

Upstream source: ``codex/codex-rs/tui/src/app/session_lifecycle.rs``.

Rust owns high-level app-server thread transitions here. Python models those
transitions as deterministic lifecycle plans while preserving the module-local
error classifiers directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::session_lifecycle",
    source="codex/codex-rs/tui/src/app/session_lifecycle.rs",
    status="complete",
)


@dataclass(frozen=True, eq=True)
class AgentPickerItemPlan:
    thread_id: str
    name: str
    description: str
    is_current: bool = False
    is_closed: bool = False


@dataclass(frozen=True, eq=True)
class SessionLifecyclePlan:
    action: str
    thread_id: Optional[str] = None
    updates: Tuple[Tuple[str, Any], ...] = ()
    messages: Tuple[str, ...] = ()
    items: Tuple[AgentPickerItemPlan, ...] = ()
    live_attached: Optional[bool] = None
    continue_run: bool = True
    exit_requested: bool = False
    schedule_frame: bool = False


def _error_chain_messages(error: Any) -> List[str]:
    messages = []
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(str(current))
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    if not messages:
        messages.append(str(error))
    return messages


def is_terminal_thread_read_error(error: Any) -> bool:
    return any("thread not loaded:" in message for message in _error_chain_messages(error))


def closed_state_for_thread_read_error(error: Any, existing_is_closed: Optional[bool]) -> bool:
    return is_terminal_thread_read_error(error) or bool(existing_is_closed)


def can_fallback_from_include_turns_error(error: Any) -> bool:
    for message in _error_chain_messages(error):
        if (
            "includeTurns is unavailable before first user message" in message
            or "ephemeral threads do not support includeTurns" in message
        ):
            return True
    return False


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _thread_id(value: Any) -> str:
    return str(_get(value, "thread_id", value))


def _agent_name(entry: Any, is_primary: bool = False) -> str:
    nickname = _get(entry, "agent_nickname") or _get(entry, "nickname")
    role = _get(entry, "agent_role") or _get(entry, "role")
    if nickname and role:
        return "%s (%s)" % (nickname, role)
    if nickname:
        return str(nickname)
    if role:
        return str(role)
    return "Primary" if is_primary else "Agent"


def open_agent_picker_plan(
    navigation_entries: List[Any],
    active_thread_id: Optional[Any] = None,
    primary_thread_id: Optional[Any] = None,
    collab_enabled: bool = True,
) -> SessionLifecyclePlan:
    if not collab_enabled and len(navigation_entries) <= 1:
        return SessionLifecyclePlan(action="open_multi_agent_enable_prompt")
    if not navigation_entries:
        return SessionLifecyclePlan(action="agent_picker_empty", messages=("No agents available yet.",))
    items = []
    active = None if active_thread_id is None else str(active_thread_id)
    primary = None if primary_thread_id is None else str(primary_thread_id)
    for entry in navigation_entries:
        tid = _thread_id(entry)
        closed = bool(_get(entry, "is_closed", False))
        items.append(
            AgentPickerItemPlan(
                thread_id=tid,
                name=_agent_name(entry, tid == primary),
                description=tid,
                is_current=tid == active,
                is_closed=closed,
            )
        )
    return SessionLifecyclePlan(action="show_agent_picker", items=tuple(items))


async def open_agent_picker(
    navigation_entries: List[Any],
    active_thread_id: Optional[Any] = None,
    primary_thread_id: Optional[Any] = None,
    collab_enabled: bool = True,
) -> SessionLifecyclePlan:
    return open_agent_picker_plan(
        navigation_entries,
        active_thread_id=active_thread_id,
        primary_thread_id=primary_thread_id,
        collab_enabled=collab_enabled,
    )


async def refresh_agent_picker_thread_liveness(thread_id: Any, existing_entry: Any = None, read_result: Any = None, read_error: Any = None, has_replay_channel: bool = False) -> SessionLifecyclePlan:
    tid = str(thread_id)
    if read_error is None:
        nickname = _get(read_result, "agent_nickname", _get(existing_entry, "agent_nickname"))
        role = _get(read_result, "agent_role", _get(existing_entry, "agent_role"))
        status = _get(read_result, "status", "")
        is_closed = str(status) == "NotLoaded"
        return SessionLifecyclePlan(action="upsert_agent_picker_thread", thread_id=tid, updates=(("agent_nickname", nickname), ("agent_role", role), ("is_closed", is_closed)))
    if is_terminal_thread_read_error(read_error) and not has_replay_channel:
        return SessionLifecyclePlan(action="remove_agent_picker_thread", thread_id=tid)
    is_closed = closed_state_for_thread_read_error(read_error, _get(existing_entry, "is_closed", None))
    return SessionLifecyclePlan(action="upsert_agent_picker_thread", thread_id=tid, updates=(("agent_nickname", _get(existing_entry, "agent_nickname")), ("agent_role", _get(existing_entry, "agent_role")), ("is_closed", is_closed)))


async def attach_live_thread_for_selection(thread_id: Any, has_channel: bool = False, resume_result: Any = None, resume_error: Any = None, read_result: Any = None, read_error: Any = None, fallback_read_result: Any = None) -> SessionLifecyclePlan:
    tid = str(thread_id)
    if has_channel:
        return SessionLifecyclePlan(action="already_attached", thread_id=tid, live_attached=True)
    if resume_error is None and resume_result is not None:
        return SessionLifecyclePlan(action="attach_live_thread", thread_id=tid, updates=(("ensure_thread_channel", tid), ("store.set_session", True)), live_attached=True)
    if read_error is not None and not can_fallback_from_include_turns_error(read_error):
        return SessionLifecyclePlan(action="attach_live_thread_failed", thread_id=tid, messages=(str(read_error),), live_attached=False)
    turns = _get(read_result, "turns", None)
    if turns is None and fallback_read_result is not None:
        turns = []
    if not turns:
        return SessionLifecyclePlan(action="attach_live_thread_unavailable", thread_id=tid, messages=("Agent thread %s is not yet available for replay or live attach." % tid,), live_attached=False)
    return SessionLifecyclePlan(action="attach_replay_only_thread", thread_id=tid, updates=(("ensure_thread_channel", tid), ("session.model.clear", True)), live_attached=False)


async def select_agent_thread(thread_id: Any, active_thread_id: Optional[Any] = None, liveness_ok: bool = True, attach_plan: Optional[SessionLifecyclePlan] = None, is_closed: bool = False, has_channel: bool = True) -> SessionLifecyclePlan:
    tid = str(thread_id)
    if active_thread_id is not None and str(active_thread_id) == tid:
        return SessionLifecyclePlan(action="select_agent_thread_current", thread_id=tid)
    if not liveness_ok:
        return SessionLifecyclePlan(action="select_agent_thread_unavailable", thread_id=tid, messages=("Agent thread %s is no longer available." % tid,))
    if attach_plan is not None and attach_plan.action.endswith("failed"):
        return SessionLifecyclePlan(action="select_agent_thread_attach_failed", thread_id=tid, messages=("Failed to attach to agent thread %s: %s" % (tid, attach_plan.messages[0] if attach_plan.messages else "unknown"),))
    if is_closed and not has_channel:
        return SessionLifecyclePlan(action="select_agent_thread_unavailable", thread_id=tid, messages=("Agent thread %s is no longer available." % tid,))
    updates = (("store_active_thread_receiver", True), ("activate_thread_for_replay", tid), ("replace_chat_widget", True), ("reset_for_thread_switch", True), ("replay_thread_snapshot", True), ("refresh_pending_thread_approvals", True))
    messages = ()
    if is_closed:
        messages = ("Agent thread %s is closed. Replaying saved transcript." % tid,)
    if attach_plan is not None and attach_plan.live_attached is False:
        messages = ("Agent thread %s could not be resumed live. Replaying saved transcript." % tid,)
    return SessionLifecyclePlan(action="select_agent_thread", thread_id=tid, updates=updates, messages=messages)


async def start_fresh_session_with_summary_hint(start_result: Any = None, start_error: Any = None, summary: Any = None) -> SessionLifecyclePlan:
    if start_error is not None:
        return SessionLifecyclePlan(action="start_fresh_session_failed", messages=("Failed to start a fresh session through the app server: %s" % start_error,), updates=(("config.model", "restore_previous"),), schedule_frame=True)
    updates = (("refresh_in_memory_config_from_disk_best_effort", True), ("shutdown_current_thread", True), ("unsubscribe_tracked_threads", True), ("replace_chat_widget_with_app_server_thread", True))
    messages = () if summary is None else (str(summary),)
    return SessionLifecyclePlan(action="start_fresh_session", updates=updates, messages=messages, schedule_frame=True)


async def resume_target_session(target_session: Any, same_thread: bool = False, resolve_exit: bool = False, rebuild_error: Any = None, resume_error: Any = None, summary: Any = None) -> SessionLifecyclePlan:
    tid = str(_get(target_session, "thread_id", target_session))
    if same_thread:
        return SessionLifecyclePlan(action="resume_same_thread_ignored", thread_id=tid, schedule_frame=True)
    if resolve_exit:
        return SessionLifecyclePlan(action="resume_cwd_prompt_exit", thread_id=tid, exit_requested=True)
    if rebuild_error is not None:
        return SessionLifecyclePlan(action="resume_config_rebuild_failed", thread_id=tid, messages=("Failed to rebuild configuration for resume: %s" % rebuild_error,))
    if resume_error is not None:
        label = _get(target_session, "display_label", tid)
        if callable(label):
            label = label()
        return SessionLifecyclePlan(action="resume_thread_failed", thread_id=tid, messages=("Failed to resume session from %s: %s" % (label, resume_error),))
    updates = (("rebuild_config_for_resume_or_fallback", True), ("apply_runtime_policy_overrides", True), ("shutdown_current_thread", True), ("replace_chat_widget_with_app_server_thread", True), ("maybe_prompt_resume_paused_goal_after_resume", True))
    messages = () if summary is None else (str(summary),)
    return SessionLifecyclePlan(action="resume_target_session", thread_id=tid, updates=updates, messages=messages)


__all__ = [
    "AgentPickerItemPlan",
    "RUST_MODULE",
    "SessionLifecyclePlan",
    "attach_live_thread_for_selection",
    "can_fallback_from_include_turns_error",
    "closed_state_for_thread_read_error",
    "is_terminal_thread_read_error",
    "open_agent_picker",
    "open_agent_picker_plan",
    "refresh_agent_picker_thread_liveness",
    "resume_target_session",
    "select_agent_thread",
    "start_fresh_session_with_summary_hint",
]
