from __future__ import annotations

from pycodex.protocol import ModeKind
from pycodex.tui.chatwidget.constructor import (
    BottomPaneParams,
    ChatWidgetInit,
    CodexOpTarget,
    PLACEHOLDERS,
    SIDE_PLACEHOLDERS,
    new_with_app_event,
    new_with_op_target,
    select_placeholder,
)
from pycodex.tui.chatwidget.settings import FeatureSet, SettingsConfig


def config() -> SettingsConfig:
    cfg = SettingsConfig()
    cfg.cwd = "/repo"
    cfg.features = FeatureSet({"PreventIdleSleep"})
    cfg.disable_paste_burst = True
    cfg.animations = True
    cfg.tui_vim_mode_default = True
    return cfg


class FakeRng:
    def __init__(self, indexes: list[int]):
        self.indexes = list(indexes)

    def random_range(self, start: int, end: int) -> int:
        assert start == 0
        assert end > 0
        return self.indexes.pop(0)


def test_placeholder_sets_match_rust_chatwidget_constructor_constants() -> None:
    # Rust source contract:
    # codex-tui/src/chatwidget.rs::PLACEHOLDERS and SIDE_PLACEHOLDERS provide
    # the candidate composer examples used by chatwidget/constructor.rs.
    assert PLACEHOLDERS == (
        "Explain this codebase",
        "Summarize recent commits",
        "Implement {feature}",
        "Find and fix a bug in @filename",
        "Write tests for @filename",
        "Improve documentation in @filename",
        "Run /review on my current changes",
        "Use /skills to list available skills",
    )
    assert SIDE_PLACEHOLDERS == (
        "Check recently modified functions for compatibility",
        "How many files have been modified?",
        "Will this algorithm scale well?",
    )


def test_select_placeholder_uses_rust_random_range_shape() -> None:
    assert select_placeholder(PLACEHOLDERS, rng=FakeRng([4])) == "Write tests for @filename"


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
    assert widget.session_header == {"model": "loading"}
    assert widget.current_collaboration_mode.model() == "loading"
    assert widget.active_collaboration_mask is not None
    assert widget.active_collaboration_mask.mode == ModeKind.DEFAULT
    assert widget.active_collaboration_mask.model is None
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
        factories={"bottom_pane": bottom_factory, "rng": FakeRng([4, 1])},
    )

    params = captured[0]
    assert params.frame_requester == "frame"
    assert params.app_event_tx == "tx"
    assert params.has_input_focus is True
    assert params.enhanced_keys_supported is False
    assert params.placeholder_text == "Write tests for @filename"
    assert widget.normal_placeholder_text == "Write tests for @filename"
    assert widget.side_placeholder_text == "How many files have been modified?"
    assert params.disable_paste_burst is True
    assert params.animations_enabled is True
    assert widget.transcript.active_cell == {
        "kind": "placeholder_session_header",
        "model": "loading",
        "cwd": "/repo",
    }


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


def test_constructor_wires_keymap_service_tier_rate_limit_and_pet_hooks() -> None:
    cfg = config()
    cfg.tui_raw_output_mode = True
    cfg.tui_keymap = {
        "app": {"copy": "ctrl+shift+c"},
        "chat": {"edit_queued_message": "alt+e"},
    }
    pet_calls = []

    widget = new_with_app_event(
        ChatWidgetInit(config=cfg, frame_requester="frame", app_event_tx="tx", model="gpt"),
        factories={
            "effective_service_tier": lambda config, model, catalog: ("tier", model),
            "terminal_info": lambda: "terminal-info",
            "start_configured_pet_load_if_needed": lambda *args: pet_calls.append(args),
        },
    )

    bottom_calls = widget.bottom_pane.calls
    widget_calls = [name for name, _ in widget.calls]

    assert widget.raw_output_mode is True
    assert widget.effective_service_tier == ("tier", "gpt")
    assert widget.current_terminal_info == "terminal-info"
    assert widget.copy_last_response_binding == "ctrl+shift+c"
    assert widget.chat_keymap == {"edit_queued_message": "alt+e"}
    assert widget.queued_message_edit_hint_binding == "alt+e"
    assert ("set_keymap_bindings", (cfg.tui_keymap,)) in bottom_calls
    assert ("set_queued_message_edit_binding", ("alt+e",)) in bottom_calls
    assert "prefetch_rate_limits" in widget_calls
    assert pet_calls == [(cfg, True, "frame", "tx")]
