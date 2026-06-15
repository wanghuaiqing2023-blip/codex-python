from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.settings import (
    CollaborationMode,
    CollaborationModeMask,
    Feature,
    FeatureSet,
    ModeKind,
    PlanModeNudgeScope,
    ReasoningEffortConfig,
    RealtimeAudioDeviceKind,
    SettingsConfig,
    active_mode_kind,
    collaboration_mode_label,
    current_model,
    current_plan_type,
    current_realtime_audio_selection_label,
    effective_reasoning_effort,
    has_chatgpt_account,
    image_inputs_not_supported_message,
    is_session_configured,
    model_display_name,
    on_thread_settings_updated,
    runtime_model_provider_base_url,
    set_permission_network,
    set_permission_profile_from_session_snapshot,
    set_permission_profile_with_active_profile,
    set_approval_policy,
    set_approvals_reviewer,
    set_collaboration_mask,
    set_feature_enabled,
    set_full_access_warning_acknowledged,
    set_model,
    set_personality,
    set_plan_mode_reasoning_effort,
    set_realtime_audio_device,
    set_reasoning_effort,
    set_tui_theme,
    set_windows_sandbox_mode,
    status_account_display,
    set_world_writable_warning_acknowledged,
    should_show_plan_mode_nudge,
    update_account_state,
    world_writable_warning_hidden,
)


class Pane:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.text = ""
        self.input_enabled = True
        self.task_running = False
        self.no_popup = True

    def __getattr__(self, name: str):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder

    def composer_text(self) -> str:
        return self.text

    def composer_input_enabled(self) -> bool:
        return self.input_enabled

    def is_task_running(self) -> bool:
        return self.task_running

    def no_modal_or_popup_active(self) -> bool:
        return self.no_popup


class Header:
    def __init__(self) -> None:
        self.model = None

    def set_model(self, model: str) -> None:
        self.model = model


class Widget:
    def __init__(self) -> None:
        self.config = SettingsConfig(model="gpt")
        self.current_collaboration_mode = CollaborationMode(
            model_value="gpt", reasoning_effort_value=ReasoningEffortConfig.MEDIUM
        )
        self.active_collaboration_mask = None
        self.thread_id = None
        self.bottom_pane = Pane()
        self.session_header = Header()
        self.events: list[tuple] = []
        self.dismissed_plan_mode_nudge_scopes: set[PlanModeNudgeScope] = set()
        self.turn_lifecycle = SimpleNamespace(
            goal_status_active_turn_started_at="start",
            budget_limited_turn_ids={"turn"},
            set_prevent_idle_sleep=lambda enabled: self.events.append(("prevent_idle_sleep", enabled)),
        )
        self.current_goal_status_indicator = "indicator"
        self.current_goal_status = "goal"
        self.status_account_display = None
        self.plan_type = None
        self.has_chatgpt_account = False

    def __getattr__(self, name: str):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder

    def plan_mask_available(self) -> bool:
        return True

    def connectors_enabled(self) -> bool:
        return self.has_chatgpt_account


def test_set_model_updates_collaboration_state_and_refreshes_surfaces() -> None:
    widget = Widget()
    widget.active_collaboration_mask = CollaborationModeMask(name="Plan", mode=ModeKind.PLAN)

    set_model(widget, "o4-mini")

    assert current_model(widget) == "o4-mini"
    assert widget.current_collaboration_mode.model() == "o4-mini"
    assert widget.active_collaboration_mask.model == "o4-mini"
    assert widget.session_header.model == "o4-mini"
    assert ("refresh_status_line",) in widget.events


def test_reasoning_effort_updates_non_plan_mask_but_plan_override_is_separate() -> None:
    widget = Widget()
    widget.active_collaboration_mask = CollaborationModeMask(name="Default", mode=ModeKind.DEFAULT)

    set_reasoning_effort(widget, ReasoningEffortConfig.HIGH)

    assert effective_reasoning_effort(widget) == ReasoningEffortConfig.HIGH
    assert widget.active_collaboration_mask.reasoning_effort == ReasoningEffortConfig.HIGH

    widget.active_collaboration_mask = CollaborationModeMask(name="Plan", mode=ModeKind.PLAN)
    set_reasoning_effort(widget, ReasoningEffortConfig.LOW)
    assert widget.active_collaboration_mask.reasoning_effort is not ReasoningEffortConfig.LOW

    set_plan_mode_reasoning_effort(widget, ReasoningEffortConfig.XHIGH)
    assert widget.config.plan_mode_reasoning_effort == ReasoningEffortConfig.XHIGH
    assert widget.active_collaboration_mask.reasoning_effort == ReasoningEffortConfig.XHIGH


def test_feature_side_effects_match_rust_settings_branches() -> None:
    widget = Widget()
    widget.config.features = FeatureSet({Feature.GOALS, Feature.PREVENT_IDLE_SLEEP})

    assert set_feature_enabled(widget, Feature.GOALS, False) is False

    assert widget.current_goal_status_indicator is None
    assert widget.current_goal_status is None
    assert widget.turn_lifecycle.goal_status_active_turn_started_at is None
    assert widget.turn_lifecycle.budget_limited_turn_ids == set()
    assert ("update_collaboration_mode_indicator",) in widget.events

    set_feature_enabled(widget, Feature.PREVENT_IDLE_SLEEP, True)
    assert ("prevent_idle_sleep", True) in widget.events


def test_realtime_audio_device_helpers_use_system_default_label() -> None:
    widget = Widget()

    assert current_realtime_audio_selection_label(widget, RealtimeAudioDeviceKind.MICROPHONE) == "System default"

    set_realtime_audio_device(widget, RealtimeAudioDeviceKind.MICROPHONE, "Studio Mic")
    assert current_realtime_audio_selection_label(widget, RealtimeAudioDeviceKind.MICROPHONE) == "Studio Mic"


def test_small_settings_setters_update_config_and_status_surfaces() -> None:
    widget = Widget()

    set_approval_policy(widget, "on-request")
    set_approvals_reviewer(widget, "auto")
    set_full_access_warning_acknowledged(widget, True)
    set_world_writable_warning_acknowledged(widget, True)
    set_personality(widget, "friendly")
    set_tui_theme(widget, "dark")

    assert widget.config.approval_policy == "on-request"
    assert widget.config.approvals_reviewer == "auto"
    assert widget.config.notices.hide_full_access_warning is True
    assert world_writable_warning_hidden(widget) is True
    assert widget.config.personality == "friendly"
    assert widget.config.tui_theme == "dark"
    assert widget.events.count(("refresh_status_surfaces",)) == 2


def test_update_account_state_refreshes_connector_enablement() -> None:
    widget = Widget()

    update_account_state(widget, "account", "pro", True)

    assert widget.status_account_display == "account"
    assert widget.plan_type == "pro"
    assert widget.has_chatgpt_account is True
    assert ("set_connectors_enabled", True) in widget.bottom_pane.events
    assert status_account_display(widget) == "account"
    assert current_plan_type(widget) == "pro"
    assert has_chatgpt_account(widget) is True


def test_permission_and_sandbox_setters_update_config_and_refresh_surfaces() -> None:
    widget = Widget()

    set_permission_profile_from_session_snapshot(widget, {"profile": "workspace-write"})
    set_permission_profile_with_active_profile(widget, "read-only", "active")
    set_permission_network(widget, {"proxy": "none"})
    set_windows_sandbox_mode(widget, "restricted")

    assert widget.config.permissions["permission_profile_snapshot"] == {
        "profile": "read-only",
        "active_permission_profile": "active",
    }
    assert widget.config.permissions["network"] == {"proxy": "none"}
    assert widget.config.network == {"proxy": "none"}
    assert widget.config.windows_sandbox_mode == "restricted"
    assert widget.events.count(("refresh_status_surfaces",)) == 2


def test_thread_settings_update_applies_only_current_thread_and_refreshes_runtime_state() -> None:
    widget = Widget()
    widget.thread_id = "thread-1"
    widget.runtime_model_provider_base_url = "http://localhost"

    on_thread_settings_updated(
        widget,
        {
            "thread_id": "other",
            "thread_settings": {"cwd": "/elsewhere"},
        },
    )
    assert widget.config.cwd is None

    on_thread_settings_updated(
        widget,
        {
            "thread_id": "thread-1",
            "thread_settings": {
                "cwd": "/workspace",
                "model_provider": "local",
                "service_tier": "fast",
                "approval_policy": "on-request",
                "approvals_reviewer": "auto",
                "personality": "warm",
                "permission_profile_snapshot": {"profile": "trusted"},
                "model": "o4-plan",
                "effort": ReasoningEffortConfig.HIGH,
                "collaboration_mode": CollaborationMode(mode=ModeKind.PLAN, model_value="old"),
            },
        },
    )

    assert is_session_configured(widget)
    assert widget.config.cwd == "/workspace"
    assert widget.config.model_provider_id == "local"
    assert widget.config.service_tier == "fast"
    assert widget.config.permissions["permission_profile_snapshot"] == {"profile": "trusted"}
    assert current_model(widget) == "o4-plan"
    assert effective_reasoning_effort(widget) == ReasoningEffortConfig.HIGH
    assert runtime_model_provider_base_url(widget) == "http://localhost"
    assert ("request_redraw",) in widget.events


def test_plan_mode_nudge_policy_filters_commands_running_state_and_dismissal() -> None:
    widget = Widget()
    widget.bottom_pane.text = "please plan this change"

    assert should_show_plan_mode_nudge(widget) is True

    widget.bottom_pane.text = "/plan maybe"
    assert should_show_plan_mode_nudge(widget) is False

    widget.bottom_pane.text = "please plan this change"
    widget.dismissed_plan_mode_nudge_scopes.add(PlanModeNudgeScope.NEW_THREAD)
    assert should_show_plan_mode_nudge(widget) is False


def test_collaboration_mask_applies_plan_override_dismisses_nudge_and_reports_model_change() -> None:
    widget = Widget()
    widget.config.plan_mode_reasoning_effort = ReasoningEffortConfig.HIGH

    set_collaboration_mask(
        widget,
        CollaborationModeMask(
            name="Plan",
            mode=ModeKind.PLAN,
            model="o4-plan",
            reasoning_effort=ReasoningEffortConfig.LOW,
        ),
    )

    assert active_mode_kind(widget) == ModeKind.PLAN
    assert collaboration_mode_label(widget) == "Plan"
    assert current_model(widget) == "o4-plan"
    assert effective_reasoning_effort(widget) == ReasoningEffortConfig.HIGH
    assert PlanModeNudgeScope.NEW_THREAD in widget.dismissed_plan_mode_nudge_scopes
    assert ("request_redraw",) in widget.events
    assert any(event[0] == "add_info_message" and "Plan mode" in event[1] for event in widget.events)


def test_display_name_and_image_error_message_use_effective_model() -> None:
    widget = Widget()
    widget.current_collaboration_mode = CollaborationMode(model_value="")

    assert model_display_name(widget) == "Default"

    widget.current_collaboration_mode = CollaborationMode(model_value="gpt-test")
    assert image_inputs_not_supported_message(widget) == (
        "Model gpt-test does not support image inputs. Remove images or switch models."
    )
