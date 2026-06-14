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
    current_realtime_audio_selection_label,
    effective_reasoning_effort,
    image_inputs_not_supported_message,
    model_display_name,
    set_collaboration_mask,
    set_feature_enabled,
    set_model,
    set_plan_mode_reasoning_effort,
    set_realtime_audio_device,
    set_reasoning_effort,
    should_show_plan_mode_nudge,
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

    def __getattr__(self, name: str):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder

    def plan_mask_available(self) -> bool:
        return True


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
