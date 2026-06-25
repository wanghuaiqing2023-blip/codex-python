from pycodex.tui.bottom_pane.textarea import (
    KillBufferKind,
    TextArea,
    delete_backward_and_forward_edges,
    delete_forward_deletes_element_at_left_edge,
    insert_and_replace_update_cursor_and_text,
    insert_str_at_clamps_to_char_boundary,
    is_word_separator,
    kill_buffer_persists_across_set_text,
    set_text_clamps_cursor_to_char_boundary,
    split_word_pieces,
    word_navigation_helpers,
    wrapping_and_cursor_positions,
    yank_restores_last_kill,
)
from pycodex.tui.bottom_pane.textarea.vim import VimMode


def test_word_separator_and_split_word_pieces_match_rust_boundary():
    # Rust: codex-tui::bottom_pane::textarea::{is_word_separator, split_word_pieces}
    assert is_word_separator("-")
    assert not is_word_separator("a")
    assert split_word_pieces("hello-world") == [(0, "hello"), (5, "-"), (6, "world")]


def test_text_replacement_cursor_and_edge_delete_contracts():
    # Rust tests: insert_and_replace_update_cursor_and_text,
    # insert_str_at_clamps_to_char_boundary, set_text_clamps_cursor_to_char_boundary,
    # delete_backward_and_forward_edges.
    assert insert_and_replace_update_cursor_and_text() is True
    assert insert_str_at_clamps_to_char_boundary() is True
    assert set_text_clamps_cursor_to_char_boundary() is True
    assert delete_backward_and_forward_edges() is True


def test_text_elements_are_atomic_for_insert_delete_and_replacement():
    # Rust tests: delete_forward_deletes_element_at_left_edge plus fuzz invariants for element atoms.
    assert delete_forward_deletes_element_at_left_edge() is True
    textarea = TextArea.new()
    textarea.set_text_clearing_elements("abef")
    textarea.set_cursor(2)
    element_id = textarea.insert_element("CD")
    assert textarea.element_id_for_exact_range(range(2, 4)) == element_id
    textarea.set_cursor(3)
    assert textarea.cursor() == 2
    textarea.replace_range(range(3, 3), "X")
    assert textarea.text() == "abCDXef"
    assert textarea.element_payloads() == ["CD"]


def test_kill_buffer_yank_and_set_text_preservation():
    # Rust tests: yank_restores_last_kill and kill_buffer_persists_across_set_text.
    assert yank_restores_last_kill() is True
    assert kill_buffer_persists_across_set_text() is True
    textarea = TextArea.new()
    textarea.set_text_clearing_elements("one\ntwo")
    textarea.kill_current_line()
    assert textarea.kill_buffer_kind is KillBufferKind.Linewise
    textarea.yank()
    assert "one\n" in textarea.text()


def test_wrapping_cursor_position_and_word_navigation_helpers():
    # Rust tests: wrapping_and_cursor_positions and word_navigation_helpers.
    assert wrapping_and_cursor_positions() is True
    assert word_navigation_helpers() is True


def test_vim_mode_public_state_contracts():
    # Rust tests: vim_insert_and_escape, vim_insert_key_enters_insert_mode, and mode label helpers.
    textarea = TextArea.new()
    textarea.set_text_clearing_elements("abc")
    assert textarea.vim_mode_label() is None
    textarea.set_vim_enabled(True)
    assert textarea.is_vim_enabled()
    assert textarea.is_vim_normal_mode()
    assert textarea.vim_mode_label() == "Normal"
    assert not textarea.allows_paste_burst()
    textarea.handle_vim_normal("i")
    assert textarea.vim_mode is VimMode.Insert
    assert textarea.uses_vim_insert_cursor()
    assert textarea.should_handle_vim_insert_escape("esc")
    textarea.handle_vim_insert("esc")
    assert textarea.vim_mode is VimMode.Normal
