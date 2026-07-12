"""Runtime settings helpers for a Python chat-widget semantic model.

The Rust ``codex-tui::chatwidget::settings`` module mutates a large
``ChatWidget`` object.  This Python port keeps the same module boundary by
providing dependency-light DTOs plus functions that operate on widget-like
objects and call the same semantic refresh/sync hooks where the Rust code does.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Optional, Set, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::settings",
    source="codex/codex-rs/tui/src/chatwidget/settings.rs",
    status="complete",
)

__all__ = [
    "CollaborationMode",
    "CollaborationModeMask",
    "Feature",
    "FeatureSet",
    "ModeKind",
    "PlanModeNudgeScope",
    "RUST_MODULE",
    "RealtimeAudioDeviceKind",
    "RealtimeAudioSettings",
    "ReasoningEffortConfig",
    "SettingsConfig",
    "active_mode_kind",
    "collaboration_mode_label",
    "current_model",
    "current_realtime_audio_device_name",
    "current_realtime_audio_selection_label",
    "current_model_supports_images",
    "current_plan_type",
    "effective_collaboration_mode",
    "effective_reasoning_effort",
    "has_chatgpt_account",
    "image_inputs_not_supported_message",
    "current_model_supports_personality",
    "is_session_configured",
    "model_display_name",
    "model_catalog",
    "on_thread_settings_updated",
    "runtime_model_provider_base_url",
    "set_approval_policy",
    "set_approvals_reviewer",
    "set_collaboration_mask",
    "set_feature_enabled",
    "set_full_access_warning_acknowledged",
    "set_permission_network",
    "set_permission_profile_from_session_snapshot",
    "set_permission_profile_with_active_profile",
    "set_model",
    "set_personality",
    "set_plan_mode_reasoning_effort",
    "set_reasoning_effort",
    "set_realtime_audio_device",
    "set_tui_theme",
    "set_windows_sandbox_mode",
    "status_account_display",
    "set_world_writable_warning_acknowledged",
    "should_show_plan_mode_nudge",
    "update_account_state",
    "world_writable_warning_hidden",
]


DEFAULT_MODEL_DISPLAY_NAME = "Default"
_UNSET = object()


class Feature(str, Enum):
    REALTIME_CONVERSATION = "RealtimeConversation"
    FAST_MODE = "FastMode"
    PERSONALITY = "Personality"
    PLUGINS = "Plugins"
    GOALS = "Goals"
    MENTIONS_V2 = "MentionsV2"
    PREVENT_IDLE_SLEEP = "PreventIdleSleep"


class ModeKind(str, Enum):
    DEFAULT = "Default"
    PLAN = "Plan"
    PAIR_PROGRAMMING = "PairProgramming"
    EXECUTE = "Execute"

    def display_name(self) -> str:
        return {
            ModeKind.DEFAULT: "Default",
            ModeKind.PLAN: "Plan",
            ModeKind.PAIR_PROGRAMMING: "Pair Programming",
            ModeKind.EXECUTE: "Execute",
        }[self]

    def is_tui_visible(self) -> bool:
        return self is ModeKind.PLAN


class ReasoningEffortConfig(str, Enum):
    NONE = "None"
    MINIMAL = "Minimal"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    XHIGH = "XHigh"
    MAX = "Max"
    ULTRA = "Ultra"

    def label(self) -> str:
        return {
            ReasoningEffortConfig.MINIMAL: "minimal",
            ReasoningEffortConfig.LOW: "low",
            ReasoningEffortConfig.MEDIUM: "medium",
            ReasoningEffortConfig.HIGH: "high",
            ReasoningEffortConfig.XHIGH: "xhigh",
            ReasoningEffortConfig.MAX: "max",
            ReasoningEffortConfig.ULTRA: "ultra",
            ReasoningEffortConfig.NONE: "default",
        }[self]


class RealtimeAudioDeviceKind(str, Enum):
    MICROPHONE = "Microphone"
    SPEAKER = "Speaker"


class PlanModeNudgeScope(str, Enum):
    NEW_THREAD = "NewThread"
    THREAD = "Thread"


@dataclass
class FeatureSet:
    enabled_features: Set[Feature] = field(default_factory=set)

    def set_enabled(self, feature: Union[Feature, str], enabled: bool) -> None:
        feature = _feature(feature)
        if enabled:
            self.enabled_features.add(feature)
        else:
            self.enabled_features.discard(feature)

    def enabled(self, feature: Union[Feature, str]) -> bool:
        return _feature(feature) in self.enabled_features


@dataclass
class RealtimeAudioSettings:
    microphone: Optional[str] = None
    speaker: Optional[str] = None


@dataclass
class Notices:
    hide_full_access_warning: Optional[bool] = None
    hide_world_writable_warning: Optional[bool] = None


@dataclass
class SettingsConfig:
    model: str = ""
    features: FeatureSet = field(default_factory=FeatureSet)
    realtime_audio: RealtimeAudioSettings = field(default_factory=RealtimeAudioSettings)
    notices: Notices = field(default_factory=Notices)
    plan_mode_reasoning_effort: Optional[ReasoningEffortConfig] = None
    tui_theme: Optional[str] = None
    personality: Optional[Any] = None
    approval_policy: Optional[Any] = None
    approvals_reviewer: Optional[Any] = None
    model_provider_id: Optional[str] = None
    cwd: Optional[Any] = None
    workspace_roots: list = field(default_factory=list)
    permissions: Any = field(default_factory=dict)
    service_tier: Optional[Any] = None
    windows_sandbox_mode: Optional[Any] = None
    network: Optional[Any] = None


@dataclass(frozen=True)
class CollaborationMode:
    mode: ModeKind = ModeKind.DEFAULT
    model_value: str = ""
    reasoning_effort_value: Optional[ReasoningEffortConfig] = None
    developer_instructions: Optional[str] = None

    def model(self) -> str:
        return self.model_value

    def reasoning_effort(self) -> Optional[ReasoningEffortConfig]:
        return self.reasoning_effort_value

    def with_updates(
        self,
        model: Optional[str] = None,
        reasoning_effort: Union[Optional[ReasoningEffortConfig], object] = _UNSET,
        developer_instructions: Union[Optional[str], object] = _UNSET,
    ) -> "CollaborationMode":
        return replace(
            self,
            model_value=self.model_value if model is None else model,
            reasoning_effort_value=(
                self.reasoning_effort_value
                if reasoning_effort is _UNSET
                else reasoning_effort
            ),
            developer_instructions=(
                self.developer_instructions
                if developer_instructions is _UNSET
                else developer_instructions
            ),
        )

    def apply_mask(self, mask: "CollaborationModeMask") -> "CollaborationMode":
        return CollaborationMode(
            mode=mask.mode or self.mode,
            model_value=self.model_value if mask.model is None else mask.model,
            reasoning_effort_value=(
                self.reasoning_effort_value
                if mask.reasoning_effort is _UNSET
                else mask.reasoning_effort
            ),
            developer_instructions=(
                self.developer_instructions
                if mask.developer_instructions is _UNSET
                else mask.developer_instructions
            ),
        )


@dataclass
class CollaborationModeMask:
    name: str
    mode: Optional[ModeKind] = None
    model: Optional[str] = None
    reasoning_effort: Union[Optional[ReasoningEffortConfig], object] = _UNSET
    developer_instructions: Union[Optional[str], object] = _UNSET


class SettingsWidget:
    config: SettingsConfig
    current_collaboration_mode: CollaborationMode
    active_collaboration_mask: Optional[CollaborationModeMask]
    thread_id: Optional[Any]


def set_approval_policy(widget: Any, policy: Any) -> None:
    widget.config.approval_policy = _to_core(policy)
    _call_optional(widget, "refresh_status_surfaces")


def set_permission_profile_from_session_snapshot(widget: Any, snapshot: Any) -> None:
    permissions = _permissions(widget)
    setter = getattr(permissions, "set_permission_profile_from_session_snapshot", None)
    if setter is not None:
        setter(snapshot)
    else:
        _set_permission_field(permissions, "permission_profile_snapshot", snapshot)
    _call_optional(widget, "refresh_status_surfaces")


def set_permission_profile_with_active_profile(
    widget: Any,
    profile: Any,
    active_permission_profile: Optional[Any],
) -> None:
    snapshot = {
        "profile": profile,
        "active_permission_profile": active_permission_profile,
    }
    set_permission_profile_from_session_snapshot(widget, snapshot)


def set_permission_network(widget: Any, network: Optional[Any]) -> None:
    permissions = _permissions(widget)
    _set_permission_field(permissions, "network", network)
    widget.config.network = network


def set_windows_sandbox_mode(widget: Any, mode: Optional[Any]) -> None:
    widget.config.windows_sandbox_mode = mode
    permissions = _permissions(widget)
    _set_permission_field(permissions, "windows_sandbox_mode", mode)
    _call_optional(
        widget,
        "bottom_pane.set_windows_degraded_sandbox_active",
        bool(_call_optional(widget, "windows_degraded_sandbox_active", default=False)),
    )


def set_approvals_reviewer(widget: Any, policy: Any) -> None:
    widget.config.approvals_reviewer = _to_core(policy)
    _call_optional(widget, "refresh_status_surfaces")


def set_full_access_warning_acknowledged(widget: Any, acknowledged: bool) -> None:
    widget.config.notices.hide_full_access_warning = bool(acknowledged)


def set_world_writable_warning_acknowledged(widget: Any, acknowledged: bool) -> None:
    widget.config.notices.hide_world_writable_warning = bool(acknowledged)


def world_writable_warning_hidden(widget: Any) -> bool:
    return bool(widget.config.notices.hide_world_writable_warning)


def set_personality(widget: Any, personality: Any) -> None:
    widget.config.personality = personality


def update_account_state(
    widget: Any,
    status_account_display: Optional[Any],
    plan_type: Optional[Any],
    has_chatgpt_account: bool,
) -> None:
    widget.status_account_display = status_account_display
    widget.plan_type = plan_type
    widget.has_chatgpt_account = bool(has_chatgpt_account)
    _call_optional(
        widget,
        "bottom_pane.set_connectors_enabled",
        bool(_call_optional(widget, "connectors_enabled", default=False)),
    )


def status_account_display(widget: Any) -> Optional[Any]:
    return getattr(widget, "status_account_display", None)


def runtime_model_provider_base_url(widget: Any) -> Optional[str]:
    return getattr(widget, "runtime_model_provider_base_url", None)


def model_catalog(widget: Any) -> Any:
    return getattr(widget, "model_catalog", None)


def current_plan_type(widget: Any) -> Optional[Any]:
    return getattr(widget, "plan_type", None)


def has_chatgpt_account(widget: Any) -> bool:
    return bool(getattr(widget, "has_chatgpt_account", False))


def set_tui_theme(widget: Any, theme: Optional[str]) -> None:
    widget.config.tui_theme = theme


def set_feature_enabled(widget: Any, feature: Union[Feature, str], enabled: bool) -> bool:
    """Set a feature flag and run the same dependent refreshes as Rust."""

    feature = _feature(feature)
    widget.config.features.set_enabled(feature, enabled)
    enabled = widget.config.features.enabled(feature)

    if feature is Feature.REALTIME_CONVERSATION:
        realtime_enabled = _call_bool(widget, "realtime_conversation_enabled", default=enabled)
        _call_optional(widget, "bottom_pane.set_realtime_conversation_enabled", realtime_enabled)
        _call_optional(
            widget,
            "bottom_pane.set_audio_device_selection_enabled",
            _call_bool(widget, "realtime_audio_device_selection_enabled", default=realtime_enabled),
        )
        live = bool(getattr(getattr(widget, "realtime_conversation", None), "is_live", lambda: False)())
        if not realtime_enabled and live:
            _call_optional(
                widget,
                "request_realtime_conversation_close",
                "Realtime voice mode was closed because the feature was disabled.",
            )
    elif feature is Feature.FAST_MODE:
        _call_optional(widget, "refresh_effective_service_tier")
        _call_optional(widget, "sync_service_tier_commands")
    elif feature is Feature.PERSONALITY:
        sync_personality_command_enabled(widget)
    elif feature is Feature.PLUGINS:
        sync_plugins_command_enabled(widget)
        _call_optional(widget, "refresh_plugin_mentions")
    elif feature is Feature.GOALS:
        sync_goal_command_enabled(widget)
        if not enabled:
            widget.current_goal_status_indicator = None
            widget.current_goal_status = None
            if hasattr(widget, "turn_lifecycle"):
                widget.turn_lifecycle.goal_status_active_turn_started_at = None
                budget = getattr(widget.turn_lifecycle, "budget_limited_turn_ids", None)
                if hasattr(budget, "clear"):
                    budget.clear()
            _call_optional(widget, "update_collaboration_mode_indicator")
    elif feature is Feature.MENTIONS_V2:
        sync_mentions_v2_enabled(widget)
    elif feature is Feature.PREVENT_IDLE_SLEEP and hasattr(widget, "turn_lifecycle"):
        _call_optional(widget.turn_lifecycle, "set_prevent_idle_sleep", enabled)

    return enabled


def set_service_tier(widget: Any, service_tier: Any) -> None:
    widget.config.service_tier = service_tier


def set_plan_mode_reasoning_effort(widget: Any, effort: Optional[ReasoningEffortConfig]) -> None:
    widget.config.plan_mode_reasoning_effort = effort
    mask = getattr(widget, "active_collaboration_mask", None)
    if collaboration_modes_enabled(widget) and mask is not None and mask.mode is ModeKind.PLAN:
        mask.reasoning_effort = effort
    refresh_model_dependent_surfaces(widget)


def set_reasoning_effort(widget: Any, effort: Optional[ReasoningEffortConfig]) -> None:
    widget.current_collaboration_mode = widget.current_collaboration_mode.with_updates(
        reasoning_effort=effort
    )
    mask = getattr(widget, "active_collaboration_mask", None)
    if collaboration_modes_enabled(widget) and mask is not None and mask.mode is not ModeKind.PLAN:
        mask.reasoning_effort = effort
    refresh_model_dependent_surfaces(widget)


def set_realtime_audio_device(
    widget: Any, kind: Union[RealtimeAudioDeviceKind, str], name: Optional[str]
) -> None:
    kind = _audio_kind(kind)
    if kind is RealtimeAudioDeviceKind.MICROPHONE:
        widget.config.realtime_audio.microphone = name
    else:
        widget.config.realtime_audio.speaker = name


def current_realtime_audio_device_name(
    widget: Any, kind: Union[RealtimeAudioDeviceKind, str]
) -> Optional[str]:
    kind = _audio_kind(kind)
    if kind is RealtimeAudioDeviceKind.MICROPHONE:
        return widget.config.realtime_audio.microphone
    return widget.config.realtime_audio.speaker


def current_realtime_audio_selection_label(
    widget: Any, kind: Union[RealtimeAudioDeviceKind, str]
) -> str:
    return current_realtime_audio_device_name(widget, kind) or "System default"


def set_model(widget: Any, model: str) -> None:
    widget.current_collaboration_mode = widget.current_collaboration_mode.with_updates(model=model)
    mask = getattr(widget, "active_collaboration_mask", None)
    if collaboration_modes_enabled(widget) and mask is not None:
        mask.model = model
    _call_optional(widget, "refresh_effective_service_tier")
    refresh_model_dependent_surfaces(widget)


def current_model(widget: Any) -> str:
    if not collaboration_modes_enabled(widget):
        return widget.current_collaboration_mode.model()
    mask = getattr(widget, "active_collaboration_mask", None)
    if mask is not None and mask.model is not None:
        return mask.model
    return widget.current_collaboration_mode.model()


def realtime_conversation_is_live(widget: Any) -> bool:
    realtime = getattr(widget, "realtime_conversation", None)
    is_live = getattr(realtime, "is_live", None)
    return bool(is_live()) if callable(is_live) else False


def active_mode_kind(widget: Any) -> ModeKind:
    mask = getattr(widget, "active_collaboration_mask", None)
    return mask.mode if mask is not None and mask.mode is not None else ModeKind.DEFAULT


def effective_reasoning_effort(widget: Any) -> Optional[ReasoningEffortConfig]:
    current = widget.current_collaboration_mode.reasoning_effort()
    if not collaboration_modes_enabled(widget):
        return current
    mask = getattr(widget, "active_collaboration_mask", None)
    if mask is None or mask.reasoning_effort is _UNSET:
        return current
    return mask.reasoning_effort


def effective_collaboration_mode(widget: Any) -> CollaborationMode:
    if not collaboration_modes_enabled(widget):
        return widget.current_collaboration_mode
    mask = getattr(widget, "active_collaboration_mask", None)
    if mask is None:
        return widget.current_collaboration_mode
    return widget.current_collaboration_mode.apply_mask(mask)


def model_display_name(widget: Any) -> str:
    model = current_model(widget)
    return DEFAULT_MODEL_DISPLAY_NAME if model == "" else model


def collaboration_mode_label(widget: Any) -> Optional[str]:
    if not collaboration_modes_enabled(widget):
        return None
    mode = active_mode_kind(widget)
    return mode.display_name() if mode.is_tui_visible() else None


def should_show_plan_mode_nudge(widget: Any) -> bool:
    text = _call_optional(widget, "bottom_pane.composer_text", default="") or ""
    trimmed = text.lstrip()
    dismissed = getattr(widget, "dismissed_plan_mode_nudge_scopes", set())
    return (
        collaboration_modes_enabled(widget)
        and bool(_call_optional(widget, "plan_mask_available", default=True))
        and active_mode_kind(widget) is not ModeKind.PLAN
        and bool(_call_optional(widget, "bottom_pane.composer_input_enabled", default=True))
        and not bool(_call_optional(widget, "bottom_pane.is_task_running", default=False))
        and bool(_call_optional(widget, "bottom_pane.no_modal_or_popup_active", default=True))
        and not trimmed.startswith("/")
        and not trimmed.startswith("!")
        and contains_plan_keyword(text)
        and plan_mode_nudge_scope(widget) not in dismissed
    )


def dismiss_plan_mode_nudge(widget: Any) -> None:
    getattr(widget, "dismissed_plan_mode_nudge_scopes", set()).add(plan_mode_nudge_scope(widget))
    refresh_plan_mode_nudge(widget)


def set_collaboration_mask(widget: Any, mask: CollaborationModeMask) -> None:
    if not collaboration_modes_enabled(widget):
        return

    previous_mode = active_mode_kind(widget)
    previous_model = current_model(widget)
    previous_effort = effective_reasoning_effort(widget)

    if mask.mode is ModeKind.PLAN and widget.config.plan_mode_reasoning_effort is not None:
        mask.reasoning_effort = widget.config.plan_mode_reasoning_effort
    if mask.mode is ModeKind.PLAN:
        getattr(widget, "dismissed_plan_mode_nudge_scopes", set()).add(plan_mode_nudge_scope(widget))

    widget.active_collaboration_mask = mask
    _call_optional(widget, "update_collaboration_mode_indicator")
    refresh_plan_mode_nudge(widget)
    refresh_model_dependent_surfaces(widget)

    next_mode = active_mode_kind(widget)
    next_model = current_model(widget)
    next_effort = effective_reasoning_effort(widget)
    if previous_mode is not next_mode and (
        previous_model != next_model or previous_effort != next_effort
    ):
        message = f"Model changed to {next_model}"
        if not next_model.startswith("codex-auto-"):
            message += f" {_reasoning_label(next_effort)}"
        message += f" for {next_mode.display_name()} mode."
        _call_optional(widget, "add_info_message", message, None)
    _call_optional(widget, "request_redraw")


def set_collaboration_mask_from_user_action(widget: Any, mask: CollaborationModeMask) -> None:
    set_collaboration_mask(widget, mask)
    submit_collaboration_mode_settings_update(widget)


def set_effective_collaboration_mode(widget: Any, mode: CollaborationMode) -> None:
    settings = mode
    if mode.mode is ModeKind.DEFAULT:
        widget.current_collaboration_mode = CollaborationMode(
            mode=ModeKind.DEFAULT,
            model_value=settings.model(),
            reasoning_effort_value=settings.reasoning_effort(),
            developer_instructions=settings.developer_instructions,
        )
    widget.active_collaboration_mask = CollaborationModeMask(
        name=mode.mode.display_name(),
        mode=mode.mode,
        model=mode.model(),
        reasoning_effort=mode.reasoning_effort(),
        developer_instructions=mode.developer_instructions,
    )
    _call_optional(widget, "update_collaboration_mode_indicator")
    refresh_plan_mode_nudge(widget)
    refresh_model_dependent_surfaces(widget)


def refresh_model_display(widget: Any) -> None:
    effective = effective_collaboration_mode(widget)
    _call_optional(widget, "session_header.set_model", effective.model())
    sync_image_paste_enabled(widget)
    _call_optional(widget, "sync_service_tier_commands")
    _call_optional(widget, "refresh_terminal_title")


def refresh_model_dependent_surfaces(widget: Any) -> None:
    refresh_model_display(widget)
    _call_optional(widget, "refresh_status_line")


def refresh_plan_mode_nudge(widget: Any) -> None:
    _call_optional(
        widget,
        "bottom_pane.set_plan_mode_nudge_visible",
        should_show_plan_mode_nudge(widget),
    )


def sync_personality_command_enabled(widget: Any) -> None:
    _call_optional(
        widget,
        "bottom_pane.set_personality_command_enabled",
        widget.config.features.enabled(Feature.PERSONALITY),
    )


def sync_plugins_command_enabled(widget: Any) -> None:
    _call_optional(
        widget,
        "bottom_pane.set_plugins_command_enabled",
        widget.config.features.enabled(Feature.PLUGINS),
    )


def sync_goal_command_enabled(widget: Any) -> None:
    _call_optional(
        widget,
        "bottom_pane.set_goal_command_enabled",
        widget.config.features.enabled(Feature.GOALS),
    )


def sync_mentions_v2_enabled(widget: Any) -> None:
    _call_optional(
        widget,
        "bottom_pane.set_mentions_v2_enabled",
        widget.config.features.enabled(Feature.MENTIONS_V2),
    )


def current_model_supports_images(widget: Any) -> bool:
    models = _call_optional(widget, "model_catalog.try_list_models", default=None)
    if models is None:
        return True
    model = current_model(widget)
    for preset in models:
        if getattr(preset, "model", None) == model:
            modalities = getattr(preset, "input_modalities", ())
            return "Image" in set(modalities)
    return True


def sync_image_paste_enabled(widget: Any) -> None:
    _call_optional(widget, "bottom_pane.set_image_paste_enabled", current_model_supports_images(widget))


def current_model_supports_personality(widget: Any) -> bool:
    models = _call_optional(widget, "model_catalog.try_list_models", default=None)
    if models is None:
        return False
    model = current_model(widget)
    for preset in models:
        if getattr(preset, "model", None) == model:
            return bool(getattr(preset, "supports_personality", False))
    return False


def on_thread_settings_updated(widget: Any, notification: Any) -> None:
    thread_id = _get_field(notification, "thread_id")
    if getattr(widget, "thread_id", None) is not None and str(widget.thread_id) != str(thread_id):
        return
    apply_thread_settings(widget, _get_field(notification, "thread_settings"))


def apply_thread_settings(widget: Any, settings: Any) -> None:
    new_cwd = _get_field(settings, "cwd", getattr(widget.config, "cwd", None))
    cwd_changed = getattr(widget.config, "cwd", None) != new_cwd
    apply_thread_settings_cwd(widget, new_cwd)
    widget.config.model_provider_id = _get_field(settings, "model_provider", widget.config.model_provider_id)
    set_service_tier(widget, _get_field(settings, "service_tier", widget.config.service_tier))
    set_approval_policy(widget, _get_field(settings, "approval_policy", widget.config.approval_policy))
    set_approvals_reviewer(widget, _get_field(settings, "approvals_reviewer", widget.config.approvals_reviewer))
    widget.config.personality = _get_field(settings, "personality", widget.config.personality)
    if _has_field(settings, "permission_profile_snapshot"):
        set_permission_profile_from_session_snapshot(widget, _get_field(settings, "permission_profile_snapshot"))
    collaboration_mode = _get_field(settings, "collaboration_mode", None)
    if collaboration_mode is not None:
        model = _get_field(settings, "model", None)
        effort = _get_field(settings, "effort", None)
        if isinstance(collaboration_mode, CollaborationMode):
            if model is not None or effort is not None:
                collaboration_mode = collaboration_mode.with_updates(
                    model=model,
                    reasoning_effort=effort if effort is not None else _UNSET,
                )
            set_effective_collaboration_mode(widget, collaboration_mode)
    _call_optional(widget, "refresh_effective_service_tier")
    _call_optional(widget, "refresh_status_surfaces")
    _call_optional(widget, "sync_service_tier_commands")
    sync_personality_command_enabled(widget)
    if cwd_changed:
        _call_optional(widget, "refresh_skills_for_current_cwd", True)
    _call_optional(widget, "refresh_plugin_mentions")
    _call_optional(widget, "request_redraw")


def apply_thread_settings_cwd(widget: Any, cwd: Any) -> None:
    previous_cwd = getattr(widget.config, "cwd", None)
    widget.config.cwd = cwd
    widget.current_cwd = cwd
    widget.status_line_project_root_name_cache = None
    roots = list(getattr(widget.config, "workspace_roots", []) or [])
    if previous_cwd in roots:
        new_roots = [cwd]
        for root in roots:
            if root != previous_cwd and root not in new_roots:
                new_roots.append(root)
        widget.config.workspace_roots = new_roots
        permissions = _permissions(widget)
        setter = getattr(permissions, "set_workspace_roots", None)
        if setter is not None:
            setter(new_roots)
        else:
            _set_permission_field(permissions, "workspace_roots", new_roots)


def image_inputs_not_supported_message(widget: Any) -> str:
    return f"Model {current_model(widget)} does not support image inputs. Remove images or switch models."


def contains_plan_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ("plan", "design", "approach", "strategy"))


def plan_mode_nudge_scope(widget: Any) -> PlanModeNudgeScope:
    return PlanModeNudgeScope.THREAD if getattr(widget, "thread_id", None) is not None else PlanModeNudgeScope.NEW_THREAD


def collaboration_modes_enabled(widget: Any) -> bool:
    class_method = getattr(type(widget), "collaboration_modes_enabled", None)
    if class_method is None:
        return True
    return bool(class_method(widget))


def is_session_configured(widget: Any) -> bool:
    return getattr(widget, "thread_id", None) is not None


def submit_collaboration_mode_settings_update(widget: Any) -> None:
    thread_id = getattr(widget, "thread_id", None)
    if thread_id is None:
        return
    _call_optional(
        widget,
        "app_event_tx.send",
        {
            "kind": "SubmitThreadOp",
            "thread_id": thread_id,
            "collaboration_mode": effective_collaboration_mode(widget),
        },
    )


def _reasoning_label(effort: Optional[ReasoningEffortConfig]) -> str:
    return "default" if effort is None else effort.label()


def _feature(feature: Union[Feature, str]) -> Feature:
    return feature if isinstance(feature, Feature) else Feature(str(feature))


def _audio_kind(kind: Union[RealtimeAudioDeviceKind, str]) -> RealtimeAudioDeviceKind:
    return kind if isinstance(kind, RealtimeAudioDeviceKind) else RealtimeAudioDeviceKind(str(kind))


def _to_core(value: Any) -> Any:
    converter = getattr(value, "to_core", None)
    return converter() if callable(converter) else value


def _permissions(widget: Any) -> Any:
    permissions = getattr(widget.config, "permissions", None)
    if permissions is None:
        permissions = {}
        widget.config.permissions = permissions
    return permissions


def _set_permission_field(permissions: Any, key: str, value: Any) -> None:
    if isinstance(permissions, dict):
        permissions[key] = value
    else:
        setattr(permissions, key, value)


def _get_field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _has_field(value: Any, key: str) -> bool:
    return key in value if isinstance(value, dict) else hasattr(value, key)


def _call_bool(target: Any, dotted_name: str, default: bool) -> bool:
    return bool(_call_optional(target, dotted_name, default=default))


def _call_optional(target: Any, dotted_name: str, *args: Any, default: Any = None) -> Any:
    obj = target
    parts = dotted_name.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part, None)
        if obj is None:
            return default
    method = getattr(obj, parts[-1], None)
    if method is None:
        return default
    return method(*args)
