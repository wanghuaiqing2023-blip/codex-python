"""Parity tests for codex-rs/tui/src/bottom_pane/memories_settings_view.rs."""

from pycodex.tui.bottom_pane.memories_settings_view import (
    MEMORIES_DOC_URL,
    MemoriesAction,
    MemoriesSettingsView,
    MemoriesSetting,
)


def test_initial_items_headers_and_docs_link_match_rust_contract():
    view = MemoriesSettingsView.new(use_memories=True, generate_memories=False)

    assert view.state.selected_idx == 0
    assert [item.name for item in view.items] == [
        "Use memories",
        "Generate memories",
        "Reset all memories",
    ]
    assert view.current_setting(MemoriesSetting.USE) is True
    assert view.current_setting(MemoriesSetting.GENERATE) is False
    assert view.items[2].action == MemoriesAction.RESET
    assert view.settings_header() == (
        "Memories",
        "Choose how Codex uses and creates memories. Changes are saved to config.toml",
    )
    assert view.render().docs_link == MEMORIES_DOC_URL


def test_toggle_selected_only_changes_setting_rows():
    view = MemoriesSettingsView.new(use_memories=True, generate_memories=False)

    view.toggle_selected()
    assert view.current_setting(MemoriesSetting.USE) is False

    view.move_down()
    view.toggle_selected()
    assert view.current_setting(MemoriesSetting.GENERATE) is True

    view.move_down()
    view.toggle_selected()
    assert view.current_setting(MemoriesSetting.USE) is False
    assert view.current_setting(MemoriesSetting.GENERATE) is True


def test_movement_pages_and_jumps_are_clamped_to_visible_rows():
    view = MemoriesSettingsView.new(use_memories=True, generate_memories=False)

    view.move_up()
    assert view.state.selected_idx == 0

    view.page_down()
    assert view.state.selected_idx == 2

    view.move_down()
    assert view.state.selected_idx == 2

    view.jump_top()
    assert view.state.selected_idx == 0

    view.jump_bottom()
    assert view.state.selected_idx == 2


def test_save_settings_emits_update_event_and_completes():
    sent = []
    view = MemoriesSettingsView.new(
        use_memories=True,
        generate_memories=False,
        app_event_tx=sent.append,
    )
    view.toggle_selected()

    view.save()

    assert view.is_complete() is True
    assert sent == [
        {
            "type": "UpdateMemorySettings",
            "use_memories": False,
            "generate_memories": False,
        }
    ]
    assert view.emitted_events == sent


def test_reset_action_opens_confirmation_and_can_emit_reset_event():
    view = MemoriesSettingsView.new(use_memories=True, generate_memories=True)
    view.jump_bottom()

    view.save()

    assert view.reset_confirmation is not None
    assert view.visible_len() == 2
    assert view.render().title == "Reset all memories?"
    assert view.render().docs_link is None

    view.save()

    assert view.is_complete() is True
    assert view.emitted_events == [{"type": "ResetMemories"}]


def test_reset_confirmation_go_back_returns_to_main_reset_row():
    view = MemoriesSettingsView.new(use_memories=True, generate_memories=True)
    view.jump_bottom()
    view.save()
    view.move_down()

    view.save()

    assert view.reset_confirmation is None
    assert view.state.selected_idx == 2
    assert view.is_complete() is False


def test_cancel_and_ctrl_c_follow_rust_completion_boundaries():
    view = MemoriesSettingsView.new(use_memories=True, generate_memories=True)
    view.jump_bottom()
    view.save()

    view.cancel()

    assert view.reset_confirmation is None
    assert view.is_complete() is False

    assert view.on_ctrl_c() == "handled"
    assert view.is_complete() is True


def test_key_handling_and_rendered_rows_are_semantic_rust_equivalents():
    view = MemoriesSettingsView.new(use_memories=True, generate_memories=False)

    assert view.handle_key_event("down") == "handled"
    assert view.handle_key_event(" ") == "handled"
    assert view.handle_key_event("unknown") == "ignored"

    lines = view.render_lines(width=200)

    assert "> [x] Generate memories - Generate memories from the following threads. Current thread included." in lines
    assert MEMORIES_DOC_URL in lines
    assert lines[-1] == "Press Space to toggle; Enter to save or select"
    assert view.rows_width(1) == 0
