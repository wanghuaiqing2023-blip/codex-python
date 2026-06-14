from pycodex.tui.app.input import (
    EXTERNAL_EDITOR_HINT,
    SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE,
    AppInputState,
    app_keymap_shortcuts_available,
    reject_side_backtrack_esc,
    request_external_editor_launch,
    reset_external_editor_state,
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