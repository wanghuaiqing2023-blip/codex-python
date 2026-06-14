import pytest

from pycodex.tui.keymap import (
    AppKeymap,
    ApprovalKeymap,
    ChatKeymap,
    ComposerKeymap,
    EditorKeymap,
    KeyBinding,
    ListKeymap,
    PagerKeymap,
    RuntimeKeymap,
    VimNormalKeymap,
    VimOperatorKeymap,
    VimTextObjectKeymap,
    alt,
    ctrl,
    ctrl_shift,
    parse_bindings,
    parse_keybinding,
    plain,
    primary_binding,
    resolve_bindings,
    resolve_bindings_with_global_fallback,
    shift,
)


def _field_names(cls):
    return tuple(cls.__dataclass_fields__.keys())


def test_keymap_struct_field_inventory_matches_rust_module() -> None:
    assert _field_names(AppKeymap) == (
        "open_transcript",
        "open_external_editor",
        "copy",
        "clear_terminal",
        "toggle_vim_mode",
        "toggle_fast_mode",
        "toggle_raw_output",
    )
    assert _field_names(ChatKeymap) == (
        "interrupt_turn",
        "decrease_reasoning_effort",
        "increase_reasoning_effort",
        "edit_queued_message",
    )
    assert _field_names(ComposerKeymap) == (
        "submit",
        "queue",
        "toggle_shortcuts",
        "history_search_previous",
        "history_search_next",
    )
    assert _field_names(EditorKeymap) == (
        "insert_newline",
        "move_left",
        "move_right",
        "move_up",
        "move_down",
        "move_word_left",
        "move_word_right",
        "move_line_start",
        "move_line_end",
        "delete_backward",
        "delete_forward",
        "delete_backward_word",
        "delete_forward_word",
        "kill_line_start",
        "kill_whole_line",
        "kill_line_end",
        "yank",
    )
    assert _field_names(VimNormalKeymap) == (
        "enter_insert",
        "append_after_cursor",
        "append_line_end",
        "insert_line_start",
        "open_line_below",
        "open_line_above",
        "move_left",
        "move_right",
        "move_up",
        "move_down",
        "move_word_forward",
        "move_word_backward",
        "move_word_end",
        "move_line_start",
        "move_line_end",
        "delete_char",
        "delete_to_line_end",
        "change_to_line_end",
        "yank_line",
        "paste_after",
        "start_delete_operator",
        "start_yank_operator",
        "start_change_operator",
        "cancel_operator",
    )
    assert _field_names(VimOperatorKeymap) == (
        "delete_line",
        "yank_line",
        "motion_left",
        "motion_right",
        "motion_up",
        "motion_down",
        "motion_word_forward",
        "motion_word_backward",
        "motion_word_end",
        "motion_line_start",
        "motion_line_end",
        "select_inner_text_object",
        "select_around_text_object",
        "cancel",
    )
    assert _field_names(VimTextObjectKeymap) == (
        "word",
        "big_word",
        "parentheses",
        "brackets",
        "braces",
        "double_quote",
        "single_quote",
        "backtick",
        "cancel",
    )
    assert _field_names(PagerKeymap) == (
        "scroll_up",
        "scroll_down",
        "page_up",
        "page_down",
        "half_page_up",
        "half_page_down",
        "jump_top",
        "jump_bottom",
        "close",
        "close_transcript",
    )
    assert _field_names(ListKeymap) == (
        "move_up",
        "move_down",
        "move_left",
        "move_right",
        "page_up",
        "page_down",
        "jump_top",
        "jump_bottom",
        "accept",
        "cancel",
    )
    assert _field_names(ApprovalKeymap) == (
        "open_fullscreen",
        "open_thread",
        "approve",
        "approve_for_session",
        "approve_for_prefix",
        "deny",
        "decline",
        "cancel",
    )


def test_parses_function_keys_and_rejects_out_of_range_function_keys() -> None:
    # Rust source: keymap.rs::tests::parses_function_keys_and_rejects_out_of_range_function_keys.
    assert parse_keybinding("f1") == plain("F1")
    assert parse_keybinding("f13") is None


def test_parses_all_named_non_character_keys() -> None:
    cases = {
        "tab": "Tab",
        "backspace": "Backspace",
        "esc": "Esc",
        "delete": "Delete",
        "insert": "Insert",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "home": "Home",
        "end": "End",
        "page-up": "PageUp",
        "pageup": "PageUp",
        "page-down": "PageDown",
        "pagedown": "PageDown",
        "space": " ",
        "minus": "-",
    }
    for spec, code in cases.items():
        assert parse_keybinding(spec) == plain(code)


def test_rejects_modifier_only_and_nonnumeric_function_key_specs() -> None:
    assert parse_keybinding("ctrl") is None
    assert parse_keybinding("ff") is None


def test_parses_minus_alias_and_legacy_literal_minus() -> None:
    assert parse_keybinding("alt-minus") == alt("-")
    assert parse_keybinding("alt--") == alt("-")
    assert parse_keybinding("-") == plain("-")


def test_parse_bindings_supports_string_array_and_deduplicates() -> None:
    assert parse_bindings("ctrl-o") == [ctrl("o")]
    assert parse_bindings("control-o") == [ctrl("o")]
    assert parse_bindings("ctrl-shift-u") == [ctrl_shift("u")]
    assert parse_bindings(["ctrl-o", "ctrl-o", "alt-r"]) == [ctrl("o"), alt("r")]
    assert parse_bindings([]) == []
    with pytest.raises(ValueError) as exc:
        parse_bindings("meta-o", "tui.keymap.global.copy")
    assert "tui.keymap.global.copy" in str(exc.value)


def test_resolve_binding_helpers_match_rust_precedence_and_unbind_semantics() -> None:
    defaults = [plain("Enter")]

    assert resolve_bindings(None, defaults, "tui.keymap.composer.submit") == defaults
    assert resolve_bindings([], defaults, "tui.keymap.composer.submit") == []
    assert resolve_bindings(["ctrl-m"], defaults, "tui.keymap.composer.submit") == [ctrl("m")]

    assert resolve_bindings_with_global_fallback(None, None, defaults, "tui.keymap.composer.submit") == defaults
    assert resolve_bindings_with_global_fallback(None, ["ctrl-j"], defaults, "tui.keymap.composer.submit") == [ctrl("j")]
    assert resolve_bindings_with_global_fallback([], ["ctrl-j"], defaults, "tui.keymap.composer.submit") == []
    assert resolve_bindings_with_global_fallback(["ctrl-m"], ["ctrl-j"], defaults, "tui.keymap.composer.submit") == [ctrl("m")]


def test_resolve_new_default_bindings_preserves_configured_legacy_keys() -> None:
    from pycodex.tui.keymap import configured_bindings_to_preserve, resolve_new_default_bindings

    defaults = [plain("PageDown"), ctrl("f")]
    assert configured_bindings_to_preserve(["page-down"]) == {plain("PageDown")}
    assert resolve_new_default_bindings(defaults, ["page-down"]) == [ctrl("f")]
    assert resolve_new_default_bindings(defaults, []) == defaults


def test_primary_binding_returns_first_or_none() -> None:
    bindings = [ctrl("a"), shift("b")]
    assert primary_binding(bindings) == ctrl("a")
    assert primary_binding([]) is None


def test_selected_defaults_match_rust_tests() -> None:
    runtime = RuntimeKeymap.defaults()
    assert runtime.app.copy == [ctrl("o")]
    assert runtime.app.toggle_raw_output == [alt("r")]
    assert runtime.editor.insert_newline == [ctrl("j"), ctrl("m"), plain("Enter"), shift("Enter"), alt("Enter")]
    assert alt("d") in runtime.editor.delete_forward_word
    assert shift("Backspace") in runtime.editor.delete_backward
    assert shift("Delete") in runtime.editor.delete_forward
    assert ctrl("Backspace") in runtime.editor.delete_backward_word
    assert KeyBinding("Backspace", frozenset({"CONTROL", "SHIFT"})) in runtime.editor.delete_backward_word
    assert ctrl("Delete") in runtime.editor.delete_forward_word
    assert KeyBinding("Delete", frozenset({"CONTROL", "SHIFT"})) in runtime.editor.delete_forward_word
    assert shift("?") in runtime.composer.toggle_shortcuts
    assert KeyBinding("a", frozenset({"CONTROL", "SHIFT"})) in runtime.approval.open_fullscreen


def test_raw_output_toggle_defaults_and_can_be_remapped() -> None:
    runtime = RuntimeKeymap.defaults()
    assert runtime.app.toggle_raw_output == [alt("r")]

    runtime = RuntimeKeymap.from_config({"global": {"toggle_raw_output": ["f12"]}})
    assert runtime.app.toggle_raw_output == [plain("F12")]


def test_editor_and_approval_default_aliases_match_rust_contract() -> None:
    runtime = RuntimeKeymap.defaults()
    assert runtime.editor.insert_newline == [ctrl("j"), ctrl("m"), plain("Enter"), shift("Enter"), alt("Enter")]
    assert alt("d") in runtime.editor.delete_forward_word
    assert shift("Backspace") in runtime.editor.delete_backward
    assert shift("Delete") in runtime.editor.delete_forward
    assert ctrl("Backspace") in runtime.editor.delete_backward_word
    assert ctrl_shift("Backspace") in runtime.editor.delete_backward_word
    assert ctrl("Delete") in runtime.editor.delete_forward_word
    assert ctrl_shift("Delete") in runtime.editor.delete_forward_word
    assert shift("?") in runtime.composer.toggle_shortcuts
    assert ctrl_shift("a") in runtime.approval.open_fullscreen


def test_vim_normal_defaults_include_insert_and_arrow_aliases() -> None:
    runtime = RuntimeKeymap.defaults()
    assert runtime.vim_normal.enter_insert == [plain("i"), plain("Insert")]
    assert runtime.vim_normal.move_left == [plain("h"), plain("Left")]
    assert runtime.vim_normal.move_right == [plain("l"), plain("Right")]
    assert runtime.vim_normal.move_up == [plain("k"), plain("Up")]
    assert runtime.vim_normal.move_down == [plain("j"), plain("Down")]


def test_from_config_remaps_unbinds_and_validates_conflicts() -> None:
    runtime = RuntimeKeymap.from_config({"global": {"copy": ["f12"], "toggle_raw_output": []}})
    assert runtime.app.copy == [plain("F12")]
    assert runtime.app.toggle_raw_output == []

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"editor": {"move_left": ["ctrl-h"], "move_right": ["ctrl-h"]}})


def test_invalid_global_copy_binding_reports_global_path() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"copy": ["meta-o"]}})
    assert "tui.keymap.global.copy" in str(exc.value)
    assert "meta-o" in str(exc.value)


def test_conflict_errors_include_both_action_names() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"editor": {"move_left": ["ctrl-h"], "move_right": ["ctrl-h"]}})
    message = str(exc.value)
    assert "move_left" in message
    assert "move_right" in message

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"list": {"page_up": ["home"], "jump_top": ["home"]}})
    message = str(exc.value)
    assert "page_up" in message
    assert "jump_top" in message


def test_conflict_validation_covers_vim_and_pager_scopes() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"vim_normal": {"move_left": ["x"], "delete_char": ["x"]}})
    message = str(exc.value)
    assert "move_left" in message
    assert "delete_char" in message

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"vim_text_object": {"word": ["w"], "big_word": ["w"]}})
    message = str(exc.value)
    assert "word" in message
    assert "big_word" in message

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"pager": {"scroll_up": ["ctrl-u"], "half_page_up": ["ctrl-u"]}})
    message = str(exc.value)
    assert "scroll_up" in message
    assert "half_page_up" in message


def test_global_fallback_and_explicit_unbind_match_rust_precedence() -> None:
    # Rust keymap.rs: resolve_bindings_with_global_fallback applies precedence
    # before validate_conflicts rejects globally remapped submit keys that shadow
    # editor insert_newline defaults.
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"submit": ["ctrl-j"]}})
    assert "composer.submit" in str(exc.value)
    assert "editor.insert_newline" in str(exc.value)

    runtime = RuntimeKeymap.from_config({"global": {"submit": ["ctrl-j"]}, "composer": {"submit": []}})
    assert runtime.composer.submit == []

    runtime = RuntimeKeymap.from_config({"global": {"copy": ["f12"]}, "composer": {"submit": ["f11"]}})
    assert runtime.app.copy == [plain("F12")]
    assert runtime.composer.submit == [plain("F11")]


def test_explicit_empty_array_unbinds_action() -> None:
    runtime = RuntimeKeymap.from_config({"composer": {"toggle_shortcuts": []}})
    assert runtime.composer.toggle_shortcuts == []


def test_legacy_list_bindings_prune_new_default_keys() -> None:
    runtime = RuntimeKeymap.from_config({"list": {"move_up": ["page-up", "ctrl-b"]}})
    assert runtime.list.move_up == [plain("PageUp"), ctrl("b")]
    assert runtime.list.page_up == []

    runtime = RuntimeKeymap.from_config({"list": {"move_up": ["page-up"], "move_down": ["page-down"]}})
    assert runtime.list.move_up == [plain("PageUp")]
    assert runtime.list.move_down == [plain("PageDown")]
    assert runtime.list.page_up == [ctrl("b")]
    assert runtime.list.page_down == [ctrl("f")]

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"list": {"move_up": ["page-up"], "page_up": ["page-up"]}})
    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"list": {"move_down": ["page-down"], "page_down": ["page-down"]}})


def test_configured_cross_surface_bindings_prune_new_defaults_but_explicit_conflicts_still_error() -> None:
    runtime = RuntimeKeymap.from_config({"global": {"copy": ["page-down"]}})
    assert runtime.app.copy == [plain("PageDown")]
    assert runtime.list.page_down == [ctrl("f")]

    runtime = RuntimeKeymap.from_config({"approval": {"approve": ["home"]}})
    assert runtime.approval.approve == [plain("Home")]
    assert runtime.list.jump_top == []

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"approval": {"approve": ["home"]}, "list": {"jump_top": ["home"]}})


def test_legacy_vim_bindings_prune_new_operator_defaults() -> None:
    runtime = RuntimeKeymap.from_config({"vim_normal": {"move_left": ["c"]}})
    assert runtime.vim_normal.move_left == [plain("c")]
    assert runtime.vim_normal.start_change_operator == []

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"vim_normal": {"move_left": ["c"], "start_change_operator": ["c"]}})

    runtime = RuntimeKeymap.from_config({"vim_operator": {"motion_left": ["i"], "motion_right": ["a"]}})
    assert runtime.vim_operator.motion_left == [plain("i")]
    assert runtime.vim_operator.motion_right == [plain("a")]
    assert runtime.vim_operator.select_inner_text_object == []
    assert runtime.vim_operator.select_around_text_object == []

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"vim_operator": {"motion_left": ["i"], "select_inner_text_object": ["i"]}})


def test_reserved_and_overlay_conflicts_match_rust_rules() -> None:
    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"composer": {"submit": ["ctrl-v"]}})
    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"pager": {"close": ["left"]}})
    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"list": {"accept": ["y"]}})
    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"list": {"cancel": ["c"]}})

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"approval": {"approve": ["y"], "decline": ["y"]}})
    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"approval": {"approve": ["y"], "deny": ["y"]}})


def test_keymap_optional_actions_can_be_assigned_and_conflict_until_original_unbound() -> None:
    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"global": {"copy": ["alt-."]}})

    runtime = RuntimeKeymap.from_config({"global": {"copy": ["alt-."]}, "chat": {"increase_reasoning_effort": []}})
    assert runtime.app.copy == [alt(".")]

    runtime = RuntimeKeymap.from_config({"editor": {"kill_whole_line": ["ctrl-shift-u"]}})
    assert runtime.editor.kill_whole_line == [ctrl_shift("u")]

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"editor": {"kill_whole_line": ["ctrl-u"]}})

    runtime = RuntimeKeymap.from_config({"editor": {"kill_line_start": [], "kill_whole_line": ["ctrl-u"]}})
    assert runtime.editor.kill_whole_line == [ctrl("u")]

    runtime = RuntimeKeymap.from_config({"global": {"toggle_fast_mode": ["ctrl-shift-f"]}})
    assert runtime.app.toggle_fast_mode == [ctrl_shift("f")]

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"global": {"toggle_fast_mode": ["ctrl-l"]}})


def test_interrupt_turn_can_use_escape_but_rejects_other_reserved_or_list_navigation_collisions() -> None:
    runtime = RuntimeKeymap.from_config({})
    assert runtime.chat.interrupt_turn == [plain("Esc")]

    runtime = RuntimeKeymap.from_config({"chat": {"interrupt_turn": ["f12"]}})
    assert runtime.chat.interrupt_turn == [plain("F12")]

    runtime = RuntimeKeymap.from_config({"chat": {"interrupt_turn": []}})
    assert runtime.chat.interrupt_turn == []

    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"chat": {"interrupt_turn": ["ctrl-v"]}})
    with pytest.raises(ValueError):
        RuntimeKeymap.from_config({"chat": {"interrupt_turn": ["f12"]}, "list": {"move_right": ["f12"]}})


def test_defaults_pass_conflict_validation() -> None:
    RuntimeKeymap.defaults().validate_conflicts()


def test_parse_canonical_ctrl_alt_shift_binding_matches_rust() -> None:
    assert parse_keybinding("ctrl-alt-shift-a") == KeyBinding(
        "a", frozenset(["CONTROL", "ALT", "SHIFT"])
    )


def test_runtime_keymap_rejects_app_shadowing_approval_and_list_handlers() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"open_transcript": "y"}})
    assert "open_transcript" in str(exc.value)
    assert "approval.approve" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"copy": "down"}})
    assert "copy" in str(exc.value)
    assert "list.move_down" in str(exc.value)

    keymap = RuntimeKeymap.from_config({"global": {"clear_terminal": "ctrl-l"}, "list": {"move_right": "ctrl-l"}})
    assert keymap.app.clear_terminal == [ctrl("l")]
    assert keymap.list.move_right == [ctrl("l")]


def test_runtime_keymap_rejects_main_handler_shadowing_editor_handlers() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"composer": {"submit": "ctrl-j"}, "editor": {"insert_newline": "ctrl-j"}})
    assert "composer.submit" in str(exc.value)
    assert "editor.insert_newline" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"copy": "ctrl-y"}, "editor": {"yank": "ctrl-y"}})
    assert "copy" in str(exc.value)
    assert "editor.yank" in str(exc.value)


def test_runtime_keymap_allows_rust_plain_enter_submit_newline_overlap() -> None:
    runtime = RuntimeKeymap.from_config({"editor": {"insert_newline": "enter"}})
    assert runtime.composer.submit == [plain("Enter")]
    assert runtime.editor.insert_newline == [plain("Enter")]


def test_runtime_keymap_rejects_app_shadowing_composer_queue_and_shortcut_toggle() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"open_external_editor": "ctrl-g"}, "composer": {"queue": "ctrl-g"}})
    assert "open_external_editor" in str(exc.value)
    assert "composer.queue" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"open_transcript": "ctrl-k"}, "composer": {"toggle_shortcuts": "ctrl-k"}})
    assert "open_transcript" in str(exc.value)
    assert "composer.toggle_shortcuts" in str(exc.value)


def test_runtime_keymap_rejects_app_shadowing_composer_submit() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"open_transcript": "ctrl-t"}, "composer": {"submit": "ctrl-t"}})
    assert "open_transcript" in str(exc.value)
    assert "composer.submit" in str(exc.value)


def test_runtime_keymap_main_surface_defaults_match_rust() -> None:
    runtime = RuntimeKeymap.defaults()

    assert runtime.app.open_transcript == [ctrl("t")]
    assert runtime.app.open_external_editor == [ctrl("g")]
    assert runtime.app.copy == [ctrl("o")]
    assert runtime.app.clear_terminal == [ctrl("l")]
    assert runtime.app.toggle_vim_mode == []
    assert runtime.app.toggle_fast_mode == []
    assert runtime.app.toggle_raw_output == [alt("r")]

    assert runtime.chat.interrupt_turn == [plain("Esc")]
    assert runtime.chat.decrease_reasoning_effort == [alt(",")]
    assert runtime.chat.increase_reasoning_effort == [alt(".")]
    assert runtime.chat.edit_queued_message == [alt("Up"), shift("Left")]

    assert runtime.composer.submit == [plain("Enter")]
    assert runtime.composer.queue == [plain("Tab")]
    assert runtime.composer.toggle_shortcuts == [plain("?"), shift("?")]
    assert runtime.composer.history_search_previous == [ctrl("r")]
    assert runtime.composer.history_search_next == [ctrl("s")]


def test_runtime_keymap_editor_defaults_match_rust() -> None:
    runtime = RuntimeKeymap.defaults()

    assert runtime.editor.insert_newline == [ctrl("j"), ctrl("m"), plain("Enter"), shift("Enter"), alt("Enter")]
    assert runtime.editor.move_left == [plain("Left"), ctrl("b")]
    assert runtime.editor.move_right == [plain("Right"), ctrl("f")]
    assert runtime.editor.move_up == [plain("Up"), ctrl("p")]
    assert runtime.editor.move_down == [plain("Down"), ctrl("n")]
    assert runtime.editor.move_word_left == [alt("b"), alt("Left"), ctrl("Left")]
    assert runtime.editor.move_word_right == [alt("f"), alt("Right"), ctrl("Right")]
    assert runtime.editor.move_line_start == [plain("Home"), ctrl("a")]
    assert runtime.editor.move_line_end == [plain("End"), ctrl("e")]
    assert runtime.editor.delete_backward == [plain("Backspace"), shift("Backspace"), ctrl("h")]
    assert runtime.editor.delete_forward == [plain("Delete"), shift("Delete"), ctrl("d")]
    assert runtime.editor.delete_backward_word == [
        alt("Backspace"),
        ctrl("Backspace"),
        ctrl_shift("Backspace"),
        ctrl("w"),
        KeyBinding("h", frozenset(["CONTROL", "ALT"])),
    ]
    assert runtime.editor.delete_forward_word == [alt("Delete"), ctrl("Delete"), ctrl_shift("Delete"), alt("d")]
    assert runtime.editor.kill_line_start == [ctrl("u")]
    assert runtime.editor.kill_whole_line == []
    assert runtime.editor.kill_line_end == [ctrl("k")]
    assert runtime.editor.yank == [ctrl("y")]


def test_runtime_keymap_vim_defaults_match_rust() -> None:
    runtime = RuntimeKeymap.defaults()

    assert runtime.vim_normal.enter_insert == [plain("i"), plain("Insert")]
    assert runtime.vim_normal.append_after_cursor == [plain("a")]
    assert runtime.vim_normal.append_line_end == [shift("a"), plain("A")]
    assert runtime.vim_normal.insert_line_start == [shift("i"), plain("I")]
    assert runtime.vim_normal.open_line_below == [plain("o")]
    assert runtime.vim_normal.open_line_above == [shift("o"), plain("O")]
    assert runtime.vim_normal.move_left == [plain("h"), plain("Left")]
    assert runtime.vim_normal.move_right == [plain("l"), plain("Right")]
    assert runtime.vim_normal.move_up == [plain("k"), plain("Up")]
    assert runtime.vim_normal.move_down == [plain("j"), plain("Down")]
    assert runtime.vim_normal.move_word_forward == [plain("w")]
    assert runtime.vim_normal.move_word_backward == [plain("b")]
    assert runtime.vim_normal.move_word_end == [plain("e")]
    assert runtime.vim_normal.move_line_start == [plain("0")]
    assert runtime.vim_normal.move_line_end == [plain("$"), shift("$")]
    assert runtime.vim_normal.delete_char == [plain("x")]
    assert runtime.vim_normal.delete_to_line_end == [shift("d"), plain("D")]
    assert runtime.vim_normal.change_to_line_end == [shift("c"), plain("C")]
    assert runtime.vim_normal.yank_line == [shift("y"), plain("Y")]
    assert runtime.vim_normal.paste_after == [plain("p")]
    assert runtime.vim_normal.start_delete_operator == [plain("d")]
    assert runtime.vim_normal.start_yank_operator == [plain("y")]
    assert runtime.vim_normal.start_change_operator == [plain("c")]
    assert runtime.vim_normal.cancel_operator == [plain("Esc")]

    assert runtime.vim_operator.delete_line == [plain("d")]
    assert runtime.vim_operator.yank_line == [plain("y")]
    assert runtime.vim_operator.motion_left == [plain("h")]
    assert runtime.vim_operator.motion_right == [plain("l")]
    assert runtime.vim_operator.motion_up == [plain("k")]
    assert runtime.vim_operator.motion_down == [plain("j")]
    assert runtime.vim_operator.motion_word_forward == [plain("w")]
    assert runtime.vim_operator.motion_word_backward == [plain("b")]
    assert runtime.vim_operator.motion_word_end == [plain("e")]
    assert runtime.vim_operator.motion_line_start == [plain("0")]
    assert runtime.vim_operator.motion_line_end == [plain("$"), shift("$")]
    assert runtime.vim_operator.select_inner_text_object == [plain("i")]
    assert runtime.vim_operator.select_around_text_object == [plain("a")]
    assert runtime.vim_operator.cancel == [plain("Esc")]

    assert runtime.vim_text_object.word == [plain("w")]
    assert runtime.vim_text_object.big_word == [shift("w"), plain("W")]
    assert runtime.vim_text_object.parentheses == [plain("("), shift("("), plain(")"), shift(")"), plain("b")]
    assert runtime.vim_text_object.brackets == [plain("["), plain("]")]
    assert runtime.vim_text_object.braces == [plain("{"), shift("{"), plain("}"), shift("}"), shift("b"), plain("B")]
    assert runtime.vim_text_object.double_quote == [plain('"'), shift('"')]
    assert runtime.vim_text_object.single_quote == [plain("'")]
    assert runtime.vim_text_object.backtick == [plain("`")]
    assert runtime.vim_text_object.cancel == [plain("Esc")]


def test_runtime_keymap_pager_list_approval_defaults_match_rust() -> None:
    runtime = RuntimeKeymap.defaults()

    assert runtime.pager.scroll_up == [plain("Up"), plain("k")]
    assert runtime.pager.scroll_down == [plain("Down"), plain("j")]
    assert runtime.pager.page_up == [plain("PageUp"), shift(" "), ctrl("b")]
    assert runtime.pager.page_down == [plain("PageDown"), plain(" "), ctrl("f")]
    assert runtime.pager.half_page_up == [ctrl("u")]
    assert runtime.pager.half_page_down == [ctrl("d")]
    assert runtime.pager.jump_top == [plain("Home")]
    assert runtime.pager.jump_bottom == [plain("End")]
    assert runtime.pager.close == [plain("q"), ctrl("c")]
    assert runtime.pager.close_transcript == [ctrl("t")]

    assert runtime.list.move_up == [plain("Up"), ctrl("p"), ctrl("k"), plain("k")]
    assert runtime.list.move_down == [plain("Down"), ctrl("n"), ctrl("j"), plain("j")]
    assert runtime.list.move_left == [plain("Left"), ctrl("h")]
    assert runtime.list.move_right == [plain("Right"), ctrl("l")]
    assert runtime.list.page_up == [plain("PageUp"), ctrl("b")]
    assert runtime.list.page_down == [plain("PageDown"), ctrl("f")]
    assert runtime.list.jump_top == [plain("Home")]
    assert runtime.list.jump_bottom == [plain("End")]
    assert runtime.list.accept == [plain("Enter")]
    assert runtime.list.cancel == [plain("Esc")]

    assert runtime.approval.open_fullscreen == [ctrl("a"), ctrl_shift("a")]
    assert runtime.approval.open_thread == [plain("o")]
    assert runtime.approval.approve == [plain("y")]
    assert runtime.approval.approve_for_session == [plain("a")]
    assert runtime.approval.approve_for_prefix == [plain("p")]
    assert runtime.approval.deny == [plain("d")]
    assert runtime.approval.decline == [plain("Esc"), plain("n")]
    assert runtime.approval.cancel == [plain("c")]


def test_invalid_global_open_transcript_and_editor_bindings_report_global_paths() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"open_transcript": "ctrl-"}})
    assert "tui.keymap.global.open_transcript" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"open_external_editor": "ctrl-"}})
    assert "tui.keymap.global.open_external_editor" in str(exc.value)


def test_legacy_list_bindings_can_prune_all_new_default_page_up_keys() -> None:
    runtime = RuntimeKeymap.from_config({"list": {"move_up": ["page-up", "ctrl-b"]}})
    assert runtime.list.move_up == [plain("PageUp"), ctrl("b")]
    assert runtime.list.page_up == []


def test_configured_app_and_approval_bindings_prune_new_list_defaults_exactly() -> None:
    runtime = RuntimeKeymap.from_config({"global": {"copy": "page-down"}})
    assert runtime.app.copy == [plain("PageDown")]
    assert runtime.list.page_down == [ctrl("f")]

    runtime = RuntimeKeymap.from_config({"approval": {"approve": "home"}})
    assert runtime.approval.approve == [plain("Home")]
    assert runtime.list.jump_top == []

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"approval": {"approve": "home"}, "list": {"jump_top": "home"}})
    assert "list.jump_top" in str(exc.value)
    assert "approval.approve" in str(exc.value)


def test_configured_vim_legacy_bindings_prune_new_operator_defaults_exactly() -> None:
    runtime = RuntimeKeymap.from_config({"vim_normal": {"move_left": "c"}})
    assert runtime.vim_normal.move_left == [plain("c")]
    assert runtime.vim_normal.start_change_operator == []

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"vim_normal": {"move_left": "c", "start_change_operator": "c"}})
    assert "move_left" in str(exc.value)
    assert "start_change_operator" in str(exc.value)

    runtime = RuntimeKeymap.from_config({"vim_operator": {"motion_left": "i", "motion_right": "a"}})
    assert runtime.vim_operator.motion_left == [plain("i")]
    assert runtime.vim_operator.motion_right == [plain("a")]
    assert runtime.vim_operator.select_inner_text_object == []
    assert runtime.vim_operator.select_around_text_object == []

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"vim_operator": {"motion_left": "i", "select_inner_text_object": "i"}})
    assert "motion_left" in str(exc.value)
    assert "select_inner_text_object" in str(exc.value)


def test_approval_overlay_allows_decline_escape_but_rejects_other_cancel_conflicts() -> None:
    runtime = RuntimeKeymap.defaults()
    runtime.validate_conflicts()
    assert runtime.list.cancel == [plain("Esc")]
    assert runtime.approval.decline == [plain("Esc"), plain("n")]

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"list": {"cancel": "c"}})
    assert "list.cancel" in str(exc.value)
    assert "approval.cancel" in str(exc.value)


def test_context_unique_conflicts_match_rust_named_cases() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"editor": {"move_left": "ctrl-h", "move_right": "ctrl-h"}})
    assert "move_left" in str(exc.value)
    assert "move_right" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"pager": {"scroll_up": "ctrl-u", "scroll_down": "ctrl-u"}})
    assert "scroll_up" in str(exc.value)
    assert "scroll_down" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"list": {"move_up": "up", "move_down": "up"}})
    assert "move_up" in str(exc.value)
    assert "move_down" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"list": {"move_left": "left", "move_right": "left"}})
    assert "move_left" in str(exc.value)
    assert "move_right" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"list": {"page_up": "home", "jump_top": "home"}})
    assert "page_up" in str(exc.value)
    assert "jump_top" in str(exc.value)


def test_invalid_global_copy_meta_binding_reports_global_path() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"copy": "meta-o"}})
    assert "tui.keymap.global.copy" in str(exc.value)


def test_reassignable_and_reserved_fixed_shortcut_edges_match_rust() -> None:
    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"composer": {"submit": "ctrl-v"}})
    assert "composer.submit" in str(exc.value)
    assert "fixed.paste_image" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"copy": "alt-."}})
    assert "copy" in str(exc.value)
    assert "chat.increase_reasoning_effort" in str(exc.value)

    runtime = RuntimeKeymap.from_config({"global": {"copy": "alt-."}, "chat": {"increase_reasoning_effort": []}})
    assert runtime.app.copy == [alt(".")]
    assert runtime.chat.increase_reasoning_effort == []

    runtime = RuntimeKeymap.from_config({"editor": {"kill_whole_line": "ctrl-shift-u"}})
    assert runtime.editor.kill_whole_line == [ctrl_shift("u")]

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"editor": {"kill_whole_line": "ctrl-u"}})
    assert "kill_line_start" in str(exc.value)
    assert "kill_whole_line" in str(exc.value)

    runtime = RuntimeKeymap.from_config({"editor": {"kill_line_start": [], "kill_whole_line": "ctrl-u"}})
    assert runtime.editor.kill_line_start == []
    assert runtime.editor.kill_whole_line == [ctrl("u")]

    runtime = RuntimeKeymap.from_config({"global": {"toggle_fast_mode": "ctrl-shift-f"}})
    assert runtime.app.toggle_fast_mode == [ctrl_shift("f")]

    with pytest.raises(ValueError) as exc:
        RuntimeKeymap.from_config({"global": {"toggle_fast_mode": "ctrl-l"}})
    assert "toggle_fast_mode" in str(exc.value)
    assert "clear_terminal" in str(exc.value)


def test_pair_shadow_validator_allows_exact_overlap_exceptions_only() -> None:
    from pycodex.tui.keymap import validate_no_shadow_pairs

    validate_no_shadow_pairs(
        "scope",
        [("primary.action", [plain("x")])],
        [("secondary.action", [plain("x")])],
        {("primary.action", "secondary.action", plain("x"))},
    )

    with pytest.raises(ValueError) as exc:
        validate_no_shadow_pairs(
            "scope",
            [("primary.action", [plain("x")])],
            [("secondary.action", [plain("x")])],
            set(),
        )
    assert "primary.action" in str(exc.value)
    assert "secondary.action" in str(exc.value)
