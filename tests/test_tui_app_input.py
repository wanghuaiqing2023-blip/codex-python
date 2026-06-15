import asyncio

from pycodex.tui.app.input import (
    InputActionPlan,
    KeyEvent,
    MISSING_EDITOR_MESSAGE,
    EXTERNAL_EDITOR_HINT,
    SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE,
    AppInputState,
    app_keymap_shortcuts_available,
    reject_side_backtrack_esc,
    request_external_editor_launch,
    reset_external_editor_state,
    apply_raw_output_mode,
    handle_key_event,
    launch_external_editor,
    refresh_status_line,
    should_handle_backtrack_esc,
    should_reject_side_backtrack_esc,
)


def test_app_keymap_shortcuts_are_disabled_while_keymap_view_is_active():
    """Rust codex-tui app::input::app_keymap_shortcuts_are_disabled_while_keymap_view_is_active."""

    state = AppInputState()
    assert app_keymap_shortcuts_available(state) is True

    state.modal_or_popup_active = True
    assert app_keymap_shortcuts_available(state) is False


def test_app_keymap_shortcuts_are_disabled_while_overlay_is_active():
    """Rust codex-tui app::input::app_keymap_shortcuts_available overlay predicate."""

    assert app_keymap_shortcuts_available(AppInputState(overlay_active=True)) is False


def test_backtrack_esc_predicates_split_main_and_side_conversation():
    """Rust codex-tui app::input should_handle/reject side backtrack Esc predicates."""

    main = AppInputState(side_conversation_active=False, normal_backtrack_mode=True, composer_empty=True)
    side = AppInputState(side_conversation_active=True, normal_backtrack_mode=True, composer_empty=True)

    assert should_handle_backtrack_esc(main) is True
    assert should_reject_side_backtrack_esc(main) is False
    assert should_handle_backtrack_esc(side) is False
    assert should_reject_side_backtrack_esc(side) is True


def test_backtrack_esc_predicates_respect_mode_composer_and_vim_escape():
    """Rust codex-tui app::input Esc forwarding guards."""

    assert should_handle_backtrack_esc(AppInputState(normal_backtrack_mode=False)) is False
    assert should_handle_backtrack_esc(AppInputState(composer_empty=False)) is False
    assert should_handle_backtrack_esc(AppInputState(vim_insert_escape_handled=True)) is False
    assert should_reject_side_backtrack_esc(
        AppInputState(side_conversation_active=True, vim_insert_escape_handled=True)
    ) is False


def test_reject_side_backtrack_esc_resets_backtrack_and_adds_error_message():
    """Rust codex-tui app::input::reject_side_backtrack_esc."""

    state = AppInputState(backtrack_primed=True)

    reject_side_backtrack_esc(state)

    assert state.backtrack_primed is False
    assert state.errors == [SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE]


def test_external_editor_request_and_reset_state_transitions():
    """Rust codex-tui app::input external editor request/reset helpers."""

    state = AppInputState()

    request_external_editor_launch(state)
    assert state.external_editor_state == "Requested"
    assert state.footer_hint_override == [(EXTERNAL_EDITOR_HINT, "")]
    assert state.frame_requested is True

    state.frame_requested = False
    reset_external_editor_state(state)
    assert state.external_editor_state == "Closed"
    assert state.footer_hint_override is None
    assert state.frame_requested is True

def test_external_editor_launch_semantic_success_and_missing_editor():
    state = AppInputState(external_editor_state="Requested")
    applied = asyncio.run(launch_external_editor(state, editor_result="hello   \n"))
    assert applied == InputActionPlan(
        action="external_editor_apply",
        updates=(("composer.external_edit", "hello"),),
        schedule_frame=True,
    )
    assert state.external_editor_state == "Closed"

    missing_state = AppInputState(external_editor_state="Requested")
    missing = asyncio.run(launch_external_editor(missing_state, missing_editor=True))
    assert missing.message == MISSING_EDITOR_MESSAGE
    assert missing_state.errors == [MISSING_EDITOR_MESSAGE]


def test_raw_output_refresh_and_key_dispatch_plans():
    state = AppInputState(raw_output_mode=False)
    assert apply_raw_output_mode(state, True, reflow_error="boom") == InputActionPlan(
        action="apply_raw_output_mode",
        updates=(("raw_output_mode", True), ("notify", False)),
        message="Failed to redraw transcript: boom",
        schedule_frame=True,
    )

    refreshed = refresh_status_line(state)
    assert refreshed.updates == (("status_line_refreshed", True),)
    assert state.status_line_refreshed is True

    esc = asyncio.run(handle_key_event(AppInputState(), KeyEvent("esc")))
    assert esc.action == "handle_backtrack_esc"

    side = asyncio.run(handle_key_event(AppInputState(side_conversation_active=True), KeyEvent("esc")))
    assert side.action == "reject_side_backtrack_esc"

    editor = asyncio.run(handle_key_event(AppInputState(), KeyEvent("e"), command="open_external_editor"))
    assert editor.action == "request_external_editor_launch"

    clear = asyncio.run(handle_key_event(AppInputState(), KeyEvent("l"), command="clear_terminal"))
    assert clear.action == "clear_terminal_ui"
    assert clear.schedule_frame


def test_enter_confirms_primed_backtrack_only_with_selection_and_empty_composer():
    """Rust codex-tui app::input Enter confirms backtrack only when primed and selectable."""

    confirm = asyncio.run(
        handle_key_event(
            AppInputState(backtrack_primed=True, backtrack_nth_user_message=1, composer_empty=True),
            KeyEvent("enter"),
        )
    )
    no_selection = asyncio.run(
        handle_key_event(
            AppInputState(backtrack_primed=True, backtrack_nth_user_message=None, composer_empty=True),
            KeyEvent("enter"),
        )
    )
    draft_text = asyncio.run(
        handle_key_event(
            AppInputState(backtrack_primed=True, backtrack_nth_user_message=1, composer_empty=False),
            KeyEvent("enter"),
        )
    )

    assert confirm == InputActionPlan(
        action="confirm_backtrack",
        updates=(("apply_backtrack_selection", True),),
    )
    assert no_selection.action == "forward_key_to_chat_widget"
    assert draft_text.action == "forward_key_to_chat_widget"
