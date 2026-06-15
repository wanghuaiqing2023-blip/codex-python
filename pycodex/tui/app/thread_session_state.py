"""Thread session-state helpers for Rust ``codex-tui::app::thread_session_state``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_session_state.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_session_state",
    source="codex/codex-rs/tui/src/app/thread_session_state.rs",
    status="complete",
)


@dataclass(eq=True)
class ThreadSessionState:
    thread_id: str
    cwd: str
    forked_from_id: Optional[str] = None
    fork_parent_title: Optional[str] = None
    thread_name: Optional[str] = None
    model: str = "gpt-test"
    model_provider_id: str = "test-provider"
    service_tier: Optional[str] = None
    approval_policy: str = "never"
    approvals_reviewer: str = "user"
    permission_profile: Any = "read_only"
    active_permission_profile: Optional[Any] = None
    runtime_workspace_roots: Optional[List[str]] = None
    instruction_source_paths: Optional[List[str]] = None
    reasoning_effort: Optional[Any] = None
    collaboration_mode: Optional[Any] = None
    personality: Optional[Any] = None
    message_history: Optional[Any] = None
    network_proxy: Optional[Any] = None
    rollout_path: Optional[str] = None

    def copy_with(self, **updates: Any) -> "ThreadSessionState":
        return replace(self, **updates)


@dataclass(eq=True)
class ThreadReadSnapshot:
    thread_id: str
    cwd: str
    name: Optional[str] = None
    model_provider: str = "test-provider"
    path: Optional[str] = None


def test_thread_session(thread_id: str, cwd: Any) -> ThreadSessionState:
    path = str(cwd)
    return ThreadSessionState(
        thread_id=thread_id,
        cwd=path,
        runtime_workspace_roots=[path],
        instruction_source_paths=[],
        rollout_path="",
    )


def sync_service_tier_to_cached_sessions(
    *,
    active_thread_id: Optional[str],
    primary_thread_id: Optional[str],
    primary_session: Optional[ThreadSessionState],
    channel_sessions: Dict[str, ThreadSessionState],
    service_tier: Optional[str],
) -> Tuple[Optional[ThreadSessionState], Dict[str, ThreadSessionState]]:
    if active_thread_id is None:
        return primary_session, dict(channel_sessions)
    updated_channels = dict(channel_sessions)
    if primary_thread_id == active_thread_id and primary_session is not None:
        primary_session = primary_session.copy_with(service_tier=service_tier)
    if active_thread_id in updated_channels:
        updated_channels[active_thread_id] = updated_channels[active_thread_id].copy_with(service_tier=service_tier)
    return primary_session, updated_channels


def sync_permission_settings_to_cached_sessions(
    *,
    active_thread_id: Optional[str],
    primary_thread_id: Optional[str],
    primary_session: Optional[ThreadSessionState],
    channel_sessions: Dict[str, ThreadSessionState],
    approval_policy: str,
    approvals_reviewer: str,
    permission_profile: Any,
    active_permission_profile: Optional[Any],
) -> Tuple[Optional[ThreadSessionState], Dict[str, ThreadSessionState]]:
    if active_thread_id is None:
        return primary_session, dict(channel_sessions)
    updates = {
        "approval_policy": approval_policy,
        "approvals_reviewer": approvals_reviewer,
        "permission_profile": permission_profile,
        "active_permission_profile": active_permission_profile,
    }
    updated_channels = dict(channel_sessions)
    if primary_thread_id == active_thread_id and primary_session is not None:
        primary_session = primary_session.copy_with(**updates)
    if active_thread_id in updated_channels:
        updated_channels[active_thread_id] = updated_channels[active_thread_id].copy_with(**updates)
    return primary_session, updated_channels


def session_state_for_thread_read(
    *,
    thread_id: str,
    thread: Any,
    primary_session: Optional[ThreadSessionState],
    current_model: str,
    model_provider_id: str,
    service_tier: Optional[str],
    approval_policy: str,
    approvals_reviewer: str,
    active_permission_profile: Optional[Any],
    permission_profile: Any,
    workspace_roots: List[str],
    reasoning_effort: Optional[Any] = None,
    session_model: Optional[str] = None,
) -> ThreadSessionState:
    thread_cwd = thread["cwd"] if isinstance(thread, dict) else thread.cwd
    thread_name = thread.get("name") if isinstance(thread, dict) else thread.name
    thread_model_provider = thread.get("model_provider", model_provider_id) if isinstance(thread, dict) else thread.model_provider
    thread_path = thread.get("path") if isinstance(thread, dict) else thread.path
    if primary_session is not None:
        session = primary_session.copy_with()
        if session.thread_id != thread_id:
            session = session.copy_with(collaboration_mode=None, personality=None)
    else:
        session = ThreadSessionState(
            thread_id=thread_id,
            cwd=str(thread_cwd),
            model=current_model,
            model_provider_id=model_provider_id,
            service_tier=service_tier,
            approval_policy=approval_policy,
            approvals_reviewer=approvals_reviewer,
            permission_profile=permission_profile,
            active_permission_profile=active_permission_profile,
            runtime_workspace_roots=list(workspace_roots),
            instruction_source_paths=[],
            reasoning_effort=reasoning_effort,
            rollout_path=thread_path,
        )
    model = session.model
    if session_model is not None:
        model = session_model
    elif thread_path is not None:
        model = ""
    return session.copy_with(
        thread_id=thread_id,
        thread_name=thread_name,
        model=model,
        model_provider_id=thread_model_provider,
        cwd=str(thread_cwd),
        permission_profile=permission_profile,
        active_permission_profile=active_permission_profile,
        instruction_source_paths=[],
        rollout_path=thread_path,
        message_history=None,
    )


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set_attr_or_key(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


def _current_service_tier(app: Any) -> Optional[str]:
    chat_widget = _get_attr_or_key(app, "chat_widget")
    if chat_widget is not None:
        current = getattr(chat_widget, "current_service_tier", None)
        if callable(current):
            return current()
        value = _get_attr_or_key(chat_widget, "service_tier")
        if value is not None:
            return value
    return _get_attr_or_key(app, "service_tier")


def _current_permission_settings(app: Any) -> Dict[str, Any]:
    chat_widget = _get_attr_or_key(app, "chat_widget")
    config = _get_attr_or_key(app, "config", {})
    permissions = _get_attr_or_key(config, "permissions", {})
    widget_config = None
    if chat_widget is not None:
        config_ref = getattr(chat_widget, "config_ref", None)
        widget_config = config_ref() if callable(config_ref) else _get_attr_or_key(chat_widget, "config")
    widget_permissions = _get_attr_or_key(widget_config, "permissions", permissions)
    return {
        "approval_policy": _get_attr_or_key(permissions, "approval_policy", _get_attr_or_key(app, "approval_policy", "never")),
        "approvals_reviewer": _get_attr_or_key(config, "approvals_reviewer", _get_attr_or_key(app, "approvals_reviewer", "user")),
        "permission_profile": _get_attr_or_key(widget_permissions, "permission_profile", _get_attr_or_key(app, "permission_profile", "read_only")),
        "active_permission_profile": _get_attr_or_key(widget_permissions, "active_permission_profile", _get_attr_or_key(app, "active_permission_profile")),
    }


async def sync_active_thread_service_tier_to_cached_session(app: Any) -> Tuple[Optional[ThreadSessionState], Dict[str, ThreadSessionState]]:
    primary, channels = sync_service_tier_to_cached_sessions(
        active_thread_id=_get_attr_or_key(app, "active_thread_id"),
        primary_thread_id=_get_attr_or_key(app, "primary_thread_id"),
        primary_session=_get_attr_or_key(app, "primary_session_configured"),
        channel_sessions=_get_attr_or_key(app, "thread_event_channels", {}),
        service_tier=_current_service_tier(app),
    )
    _set_attr_or_key(app, "primary_session_configured", primary)
    _set_attr_or_key(app, "thread_event_channels", channels)
    return primary, channels


async def sync_active_thread_permission_settings_to_cached_session(app: Any) -> Tuple[Optional[ThreadSessionState], Dict[str, ThreadSessionState]]:
    settings = _current_permission_settings(app)
    primary, channels = sync_permission_settings_to_cached_sessions(
        active_thread_id=_get_attr_or_key(app, "active_thread_id"),
        primary_thread_id=_get_attr_or_key(app, "primary_thread_id"),
        primary_session=_get_attr_or_key(app, "primary_session_configured"),
        channel_sessions=_get_attr_or_key(app, "thread_event_channels", {}),
        approval_policy=settings["approval_policy"],
        approvals_reviewer=settings["approvals_reviewer"],
        permission_profile=settings["permission_profile"],
        active_permission_profile=settings["active_permission_profile"],
    )
    _set_attr_or_key(app, "primary_session_configured", primary)
    _set_attr_or_key(app, "thread_event_channels", channels)
    return primary, channels


__all__ = [
    "RUST_MODULE",
    "ThreadReadSnapshot",
    "ThreadSessionState",
    "session_state_for_thread_read",
    "sync_active_thread_permission_settings_to_cached_session",
    "sync_active_thread_service_tier_to_cached_session",
    "sync_permission_settings_to_cached_sessions",
    "sync_service_tier_to_cached_sessions",
    "test_thread_session",
]
