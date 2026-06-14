from __future__ import annotations

from pycodex.tui.chatwidget.constructor import (
    BottomPaneParams,
    ChatWidgetInit,
    CodexOpTarget,
    new_with_app_event,
    new_with_op_target,
)
from pycodex.tui.chatwidget.settings import FeatureSet, ModeKind, SettingsConfig


def config() -> SettingsConfig:
    cfg = SettingsConfig()
    cfg.cwd = "/repo"
    cfg.features = FeatureSet({"PreventIdleSleep"})
    cfg.disable_paste_burst = True
    cfg.animations = True
    cfg.tui_vim_mode_default = True
    return cfg


def test_new_with_app_event_delegates_to_app_event_target_and_filters_blank_model() -> None:
    cfg = config()
    init = ChatWidgetInit(
        config=cfg,
        frame_requester="frame",
        app_event_tx="tx",
        model="   ",
        is_first_run=True,
    )

    widget = new_with_app_event(init)

    assert widget.codex_op_target == CodexOpTarget.APP_EVENT
    assert widget.config.model is None
    assert widget.session_header == {"model": "Default"}
    assert widget.current_collaboration_mode.model() == "Default"
    assert widget.active_collaboration_mask is None
    assert widget.show_welcome_banner is True
    assert widget.current_cwd == "/repo"
    assert widget.turn_lifecycle == {"prevent_idle_sleep": True}


def test_new_with_op_target_uses_model_override_for_mask_header_and_collaboration_mode() -> None:
    cfg = config()
    init = ChatWidgetInit(
        config=cfg,
        frame_requester="frame",
        app_event_tx="tx",
        model=" o4-mini ",
        enhanced_keys_supported=True,
    )

    widget = new_with_op_target(init, CodexOpTarget.DIRECT)

    assert widget.codex_op_target == CodexOpTarget.DIRECT
    assert widget.config.model == "o4-mini"
    assert widget.active_collaboration_mask is not None
    assert widget.active_collaboration_mask.mode == ModeKind.DEFAULT
    assert widget.active_collaboration_mask.model == "o4-mini"
    assert widget.session_header == {"model": "o4-mini"}
    assert widget.current_collaboration_mode.model() == "o4-mini"


def test_bottom_pane_params_and_transcript_active_cell_are_wired() -> None:
    captured: list[BottomPaneParams] = []

    def bottom_factory(params: BottomPaneParams):
        captured.append(params)
        from pycodex.tui.chatwidget.constructor import RecordingBottomPane

        return RecordingBottomPane(params)

    widget = new_with_app_event(
        ChatWidgetInit(config=config(), frame_requester="frame", app_event_tx="tx", model="gpt"),
        factories={"bottom_pane": bottom_factory},
    )

    params = captured[0]
    assert params.frame_requester == "frame"
    assert params.app_event_tx == "tx"
    assert params.has_input_focus is True
    assert params.enhanced_keys_supported is False
    assert params.placeholder_text == "Ask Codex"
    assert params.disable_paste_burst is True
    assert params.animations_enabled is True
    assert widget.transcript.active_cell == {"kind": "placeholder_session_header", "cwd": "/repo"}


def test_post_construct_sync_calls_bottom_pane_and_widget_hooks() -> None:
    widget = new_with_app_event(
        ChatWidgetInit(config=config(), frame_requester="frame", app_event_tx="tx", model="gpt")
    )

    bottom_calls = [name for name, _ in widget.bottom_pane.calls]
    widget_calls = [name for name, _ in widget.calls]

    assert "set_vim_enabled" in bottom_calls
    assert "set_realtime_conversation_enabled" in bottom_calls
    assert "set_audio_device_selection_enabled" in bottom_calls
    assert "set_status_line_enabled" in bottom_calls
    assert "set_collaboration_modes_enabled" in bottom_calls
    assert "set_connectors_enabled" in bottom_calls
    assert "sync_service_tier_commands" in widget_calls
    assert "sync_personality_command_enabled" in widget_calls
    assert "sync_plugins_command_enabled" in widget_calls
    assert "sync_goal_command_enabled" in widget_calls
    assert "sync_mentions_v2_enabled" in widget_calls
    assert "update_collaboration_mode_indicator" in widget_calls
    assert "refresh_status_surfaces" in widget_calls
