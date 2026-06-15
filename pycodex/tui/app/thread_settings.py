"""Thread settings sync helpers for Rust ``codex-tui::app::thread_settings``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_settings.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Optional

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_settings",
    source="codex/codex-rs/tui/src/app/thread_settings.rs",
    status="complete",
)


class ModeKind(str):
    Default = "default"
    Other = "other"


@dataclass(eq=True)
class CollaborationSettings:
    model: Optional[str] = None
    reasoning_effort: Optional[Any] = None


@dataclass(eq=True)
class CollaborationMode:
    mode: Any = ModeKind.Default
    settings: CollaborationSettings = field(default_factory=CollaborationSettings)

    def clone_with_thread_settings(self, model: str, effort: Optional[Any]) -> "CollaborationMode":
        return CollaborationMode(
            mode=self.mode,
            settings=CollaborationSettings(model=model, reasoning_effort=effort),
        )


@dataclass(eq=True)
class ThreadSettingsUpdateParams:
    thread_id: str
    cwd: Optional[str] = None
    approval_policy: Optional[Any] = None
    approvals_reviewer: Optional[Any] = None
    sandbox_policy: Optional[Any] = None
    permissions: Optional[Any] = None
    model: Optional[str] = None
    service_tier: Optional[str] = None
    effort: Optional[Any] = None
    summary: Optional[Any] = None
    collaboration_mode: Optional[CollaborationMode] = None
    personality: Optional[Any] = None


@dataclass(eq=True)
class ThreadSettingsUpdateResult:
    sent: bool
    params: Optional[ThreadSettingsUpdateParams] = None
    error_message: Optional[str] = None


@dataclass(eq=True)
class ThreadSessionState:
    model: str
    reasoning_effort: Optional[Any] = None
    model_provider_id: str = ""
    service_tier: Optional[str] = None
    approval_policy: Optional[Any] = None
    approvals_reviewer: Optional[Any] = None
    permission_profile: Optional[Any] = None
    active_permission_profile: Optional[Any] = None
    cwd: str = ""
    runtime_workspace_roots: list = field(default_factory=list)
    personality: Optional[Any] = None
    collaboration_mode: Optional[CollaborationMode] = None


@dataclass(eq=True)
class ThreadSettings:
    model: str
    model_provider: str
    service_tier: Optional[str]
    effort: Optional[Any]
    approval_policy: Any
    approvals_reviewer: Any
    sandbox_policy: Any
    cwd: str
    collaboration_mode: CollaborationMode
    active_permission_profile: Optional[Any] = None
    personality: Optional[Any] = None


def _mode_kind(value: Any) -> str:
    if value == ModeKind.Default:
        return ModeKind.Default
    name = getattr(value, "name", None)
    if name == "Default":
        return ModeKind.Default
    return str(value)


def _approval_reviewer_to_core(value: Any) -> Any:
    return value.to_core() if callable(getattr(value, "to_core", None)) else value


def _permission_profile_from_legacy_sandbox_policy_for_cwd(sandbox_policy: Any, cwd: str) -> Dict[str, Any]:
    return {"sandbox_policy": sandbox_policy, "cwd": str(cwd)}


def apply_thread_settings_to_session(session: ThreadSessionState, settings: ThreadSettings) -> ThreadSessionState:
    """Mutate and return ``session`` using Rust's settings application rules."""

    if _mode_kind(settings.collaboration_mode.mode) == ModeKind.Default:
        session.model = settings.model
        session.reasoning_effort = settings.effort
    session.model_provider_id = settings.model_provider
    session.service_tier = settings.service_tier
    session.approval_policy = settings.approval_policy
    session.approvals_reviewer = _approval_reviewer_to_core(settings.approvals_reviewer)
    session.permission_profile = _permission_profile_from_legacy_sandbox_policy_for_cwd(settings.sandbox_policy, settings.cwd)
    session.active_permission_profile = settings.active_permission_profile
    session.cwd = str(settings.cwd)
    session.runtime_workspace_roots = [_display_path(Path(settings.cwd))]
    session.personality = settings.personality
    session.collaboration_mode = settings.collaboration_mode.clone_with_thread_settings(settings.model, settings.effort)
    return session


def _display_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def apply_thread_settings_to_cached_sessions(
    *,
    thread_id: str,
    primary_thread_id: Optional[str],
    primary_session: Optional[ThreadSessionState],
    channel_sessions: Dict[str, ThreadSessionState],
    settings: ThreadSettings,
) -> Dict[str, Any]:
    updated_channels = dict(channel_sessions)
    if primary_thread_id == thread_id and primary_session is not None:
        primary_session = apply_thread_settings_to_session(replace(primary_session), settings)
    if thread_id in updated_channels:
        updated_channels[thread_id] = apply_thread_settings_to_session(replace(updated_channels[thread_id]), settings)
    return {"primary_session": primary_session, "channel_sessions": updated_channels}


def thread_settings_update_has_changes(params: ThreadSettingsUpdateParams) -> bool:
    return any(
        getattr(params, field_name) is not None
        for field_name in (
            "cwd",
            "approval_policy",
            "approvals_reviewer",
            "sandbox_policy",
            "permissions",
            "model",
            "service_tier",
            "effort",
            "summary",
            "collaboration_mode",
            "personality",
        )
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


def _chat_widget(app: Any) -> Any:
    return _get_attr_or_key(app, "chat_widget", {})


def _collaboration_mode_from_widget(widget: Any, method_name: str) -> CollaborationMode:
    method = getattr(widget, method_name, None)
    if callable(method):
        return method()
    return _get_attr_or_key(widget, "collaboration_mode", CollaborationMode())


def active_thread_model_setting_update_params(app: Any, model: str) -> Optional[ThreadSettingsUpdateParams]:
    thread_id = _get_attr_or_key(app, "active_thread_id")
    if thread_id is None:
        return None
    return ThreadSettingsUpdateParams(
        thread_id=str(thread_id),
        model=model,
        collaboration_mode=_collaboration_mode_from_widget(_chat_widget(app), "effective_collaboration_mode"),
    )


def active_thread_reasoning_setting_update_params(app: Any, effort: Optional[Any]) -> Optional[ThreadSettingsUpdateParams]:
    thread_id = _get_attr_or_key(app, "active_thread_id")
    if thread_id is None:
        return None
    return ThreadSettingsUpdateParams(
        thread_id=str(thread_id),
        effort=effort,
        collaboration_mode=_collaboration_mode_from_widget(_chat_widget(app), "current_collaboration_mode"),
    )


def active_thread_plan_mode_reasoning_setting_update_params(app: Any) -> Optional[ThreadSettingsUpdateParams]:
    thread_id = _get_attr_or_key(app, "active_thread_id")
    if thread_id is None:
        return None
    return ThreadSettingsUpdateParams(
        thread_id=str(thread_id),
        collaboration_mode=_collaboration_mode_from_widget(_chat_widget(app), "effective_collaboration_mode"),
    )


def active_thread_personality_setting_update_params(app: Any, personality: Any) -> Optional[ThreadSettingsUpdateParams]:
    thread_id = _get_attr_or_key(app, "active_thread_id")
    if thread_id is None:
        return None
    return ThreadSettingsUpdateParams(thread_id=str(thread_id), personality=personality)


def override_turn_context_settings_update_params(thread_id: str, op: Any) -> Optional[ThreadSettingsUpdateParams]:
    if _get_attr_or_key(op, "kind") not in (None, "OverrideTurnContext"):
        return None
    active_permission_profile = _get_attr_or_key(op, "active_permission_profile")
    permissions = _get_attr_or_key(active_permission_profile, "id", active_permission_profile)
    effort = _get_attr_or_key(op, "effort")
    return ThreadSettingsUpdateParams(
        thread_id=str(thread_id),
        cwd=_get_attr_or_key(op, "cwd"),
        approval_policy=_get_attr_or_key(op, "approval_policy"),
        approvals_reviewer=_approval_reviewer_to_core(_get_attr_or_key(op, "approvals_reviewer")),
        permissions=permissions,
        model=_get_attr_or_key(op, "model"),
        effort=effort,
        summary=_get_attr_or_key(op, "summary"),
        service_tier=_get_attr_or_key(op, "service_tier"),
        collaboration_mode=_get_attr_or_key(op, "collaboration_mode"),
        personality=_get_attr_or_key(op, "personality"),
    )


async def send_thread_settings_update(app: Any, app_server: Any, params: ThreadSettingsUpdateParams) -> ThreadSettingsUpdateResult:
    if not thread_settings_update_has_changes(params):
        return ThreadSettingsUpdateResult(sent=False, params=params)
    try:
        update = getattr(app_server, "thread_settings_update")
        result = update(params)
        if hasattr(result, "__await__"):
            await result
        return ThreadSettingsUpdateResult(sent=True, params=params)
    except Exception as exc:
        message = "Failed to update thread settings: {0}".format(exc)
        chat_widget = _chat_widget(app)
        add_error = getattr(chat_widget, "add_error_message", None)
        if callable(add_error):
            add_error(message)
        else:
            errors = _get_attr_or_key(app, "errors", [])
            errors.append(message)
            _set_attr_or_key(app, "errors", errors)
        return ThreadSettingsUpdateResult(sent=False, params=params, error_message=message)


async def sync_active_thread_model_setting(app: Any, app_server: Any, model: str) -> ThreadSettingsUpdateResult:
    params = active_thread_model_setting_update_params(app, model)
    if params is None:
        return ThreadSettingsUpdateResult(sent=False)
    return await send_thread_settings_update(app, app_server, params)


async def sync_active_thread_reasoning_setting(app: Any, app_server: Any, effort: Optional[Any]) -> ThreadSettingsUpdateResult:
    params = active_thread_reasoning_setting_update_params(app, effort)
    if params is None:
        return ThreadSettingsUpdateResult(sent=False)
    return await send_thread_settings_update(app, app_server, params)


async def sync_active_thread_plan_mode_reasoning_setting(app: Any, app_server: Any) -> ThreadSettingsUpdateResult:
    params = active_thread_plan_mode_reasoning_setting_update_params(app)
    if params is None:
        return ThreadSettingsUpdateResult(sent=False)
    return await send_thread_settings_update(app, app_server, params)


async def sync_active_thread_personality_setting(app: Any, app_server: Any, personality: Any) -> ThreadSettingsUpdateResult:
    params = active_thread_personality_setting_update_params(app, personality)
    if params is None:
        return ThreadSettingsUpdateResult(sent=False)
    return await send_thread_settings_update(app, app_server, params)


async def sync_override_turn_context_settings(app: Any, app_server: Any, thread_id: str, op: Any) -> ThreadSettingsUpdateResult:
    params = override_turn_context_settings_update_params(thread_id, op)
    if params is None:
        return ThreadSettingsUpdateResult(sent=False)
    return await send_thread_settings_update(app, app_server, params)


__all__ = [
    "CollaborationMode",
    "CollaborationSettings",
    "ModeKind",
    "RUST_MODULE",
    "ThreadSessionState",
    "ThreadSettings",
    "ThreadSettingsUpdateParams",
    "ThreadSettingsUpdateResult",
    "active_thread_model_setting_update_params",
    "active_thread_personality_setting_update_params",
    "active_thread_plan_mode_reasoning_setting_update_params",
    "active_thread_reasoning_setting_update_params",
    "apply_thread_settings_to_cached_sessions",
    "apply_thread_settings_to_session",
    "override_turn_context_settings_update_params",
    "send_thread_settings_update",
    "sync_active_thread_model_setting",
    "sync_active_thread_personality_setting",
    "sync_active_thread_plan_mode_reasoning_setting",
    "sync_active_thread_reasoning_setting",
    "sync_override_turn_context_settings",
    "thread_settings_update_has_changes",
]
