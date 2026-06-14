"""Python interface scaffold for Rust ``codex-tui::bottom_pane::textarea``.

Upstream source: ``codex/codex-rs/tui/src/bottom_pane/textarea.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from ..._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="bottom_pane::textarea", source="codex/codex-rs/tui/src/bottom_pane/textarea.rs")

WORD_SEPARATORS: Any = None

def is_word_separator(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::is_word_separator``."""
    return not_ported(RUST_MODULE, "is_word_separator")

def split_word_pieces(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::split_word_pieces``."""
    return not_ported(RUST_MODULE, "split_word_pieces")

@dataclass
class TextElement:
    """Python boundary for Rust ``bottom_pane::textarea::TextElement``."""
    _payload: Any = None

@dataclass
class TextElementSnapshot:
    """Python boundary for Rust ``bottom_pane::textarea::TextElementSnapshot``."""
    _payload: Any = None

@dataclass
class TextArea:
    """Python boundary for Rust ``bottom_pane::textarea::TextArea``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.new")

    def set_keymap_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.set_keymap_bindings")

    def set_text_clearing_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.set_text_clearing_elements")

    def set_text_with_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.set_text_with_elements")

    def set_text_inner(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.set_text_inner")

    def set_vim_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.set_vim_enabled")

    def is_vim_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.is_vim_enabled")

    def is_vim_normal_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.is_vim_normal_mode")

    def vim_normal_end_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.vim_normal_end_cursor")

    def is_vim_operator_pending(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.is_vim_operator_pending")

    def enter_vim_insert_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.enter_vim_insert_mode")

    def enter_vim_normal_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.enter_vim_normal_mode")

    def allows_paste_burst(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.allows_paste_burst")

    def uses_vim_insert_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.uses_vim_insert_cursor")

    def should_handle_vim_insert_escape(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.should_handle_vim_insert_escape")

    def vim_mode_label(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.vim_mode_label")

    def text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.text")

    def insert_str(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.insert_str")

    def insert_str_at(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.insert_str_at")

    def replace_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.replace_range")

    def replace_range_raw(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.replace_range_raw")

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.cursor")

    def set_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.set_cursor")

    def desired_height(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.desired_height")

    def cursor_pos(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.cursor_pos")

    def cursor_pos_with_state(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.cursor_pos_with_state")

    def is_empty(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.is_empty")

    def current_display_col(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.current_display_col")

    def wrapped_line_index_by_start(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.wrapped_line_index_by_start")

    def move_to_display_col_on_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.move_to_display_col_on_line")

    def beginning_of_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.beginning_of_line")

    def beginning_of_current_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.beginning_of_current_line")

    def first_non_blank_of_current_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.first_non_blank_of_current_line")

    def end_of_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.end_of_line")

    def end_of_current_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.end_of_current_line")

    def input(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.input")

    def input_with_keymap(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.input_with_keymap")

    def handle_vim_input(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.handle_vim_input")

    def handle_vim_insert(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.handle_vim_insert")

    def handle_vim_normal(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.handle_vim_normal")

    def handle_vim_operator(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.handle_vim_operator")

    def handle_vim_text_object(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.handle_vim_text_object")

    def vim_motion_for_event(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.vim_motion_for_event")

    def apply_vim_operator(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.apply_vim_operator")

    def apply_vim_operator_to_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.apply_vim_operator_to_range")

    def range_for_motion(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.range_for_motion")

    def linewise_range_for_vertical_motion(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.linewise_range_for_vertical_motion")

    def target_for_motion(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.target_for_motion")

    def delete_backward(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.delete_backward")

    def delete_forward(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.delete_forward")

    def delete_forward_kill(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.delete_forward_kill")

    def delete_backward_word(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.delete_backward_word")

    def delete_forward_word(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.delete_forward_word")

    def kill_to_end_of_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.kill_to_end_of_line")

    def vim_kill_to_end_of_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.vim_kill_to_end_of_line")

    def kill_to_beginning_of_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.kill_to_beginning_of_line")

    def yank(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.yank")

    def kill_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.kill_range")

    def kill_line_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.kill_line_range")

    def kill_range_with_kind(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.kill_range_with_kind")

    def yank_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.yank_range")

    def yank_line_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.yank_line_range")

    def yank_range_with_kind(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.yank_range_with_kind")

    def store_kill_buffer(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.store_kill_buffer")

    def paste_after_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.paste_after_cursor")

    def paste_line_after_current_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.paste_line_after_current_line")

    def yank_current_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.yank_current_line")

    def kill_current_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.kill_current_line")

    def current_line_range_with_newline(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.current_line_range_with_newline")

    def move_cursor_left(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.move_cursor_left")

    def move_cursor_right(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.move_cursor_right")

    def move_cursor_up(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.move_cursor_up")

    def move_cursor_down(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.move_cursor_down")

    def move_cursor_to_beginning_of_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.move_cursor_to_beginning_of_line")

    def move_cursor_to_end_of_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.move_cursor_to_end_of_line")

    def element_payloads(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.element_payloads")

    def text_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.text_elements")

    def text_element_snapshots(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.text_element_snapshots")

    def element_id_for_exact_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.element_id_for_exact_range")

    def replace_element_payload(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.replace_element_payload")

    def insert_element(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.insert_element")

    def insert_named_element(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.insert_named_element")

    def replace_element_by_id(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.replace_element_by_id")

    def update_named_element_by_id(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.update_named_element_by_id")

    def named_element_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.named_element_range")

    def add_element_with_id(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.add_element_with_id")

    def add_element(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.add_element")

    def add_element_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.add_element_range")

    def remove_element_range(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.remove_element_range")

    def next_element_id(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.next_element_id")

    def find_element_containing(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.find_element_containing")

    def clamp_pos_to_char_boundary(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.clamp_pos_to_char_boundary")

    def clamp_pos_to_nearest_boundary(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.clamp_pos_to_nearest_boundary")

    def clamp_pos_for_insertion(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.clamp_pos_for_insertion")

    def expand_range_to_element_boundaries(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.expand_range_to_element_boundaries")

    def shift_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.shift_elements")

    def update_elements_after_replace(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.update_elements_after_replace")

    def prev_atomic_boundary(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.prev_atomic_boundary")

    def next_atomic_boundary(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.next_atomic_boundary")

    def beginning_of_previous_word(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.beginning_of_previous_word")

    def end_of_next_word(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.end_of_next_word")

    def end_of_next_word_from(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.end_of_next_word_from")

    def vim_word_end_exclusive(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.vim_word_end_exclusive")

    def vim_word_end_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.vim_word_end_cursor")

    def vim_line_end_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.vim_line_end_cursor")

    def beginning_of_next_word(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.beginning_of_next_word")

    def adjust_pos_out_of_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.adjust_pos_out_of_elements")

    def wrapped_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.wrapped_lines")

    def effective_scroll(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.effective_scroll")

    def render_ref_masked(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.render_ref_masked")

    def render_ref_styled_with_highlights(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.render_ref_styled_with_highlights")

    def render_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.render_lines")

    def render_lines_masked(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TextArea.render_lines_masked")

@dataclass
class WrapCache:
    """Python boundary for Rust ``bottom_pane::textarea::WrapCache``."""
    _payload: Any = None

@dataclass
class TextAreaState:
    """Python boundary for Rust ``bottom_pane::textarea::TextAreaState``."""
    _payload: Any = None

class KillBufferKind(Enum):
    """Python boundary for Rust enum ``bottom_pane::textarea::KillBufferKind``."""
    UNPORTED = "unported"

def render_ref(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::render_ref``."""
    return not_ported(RUST_MODULE, "render_ref")

State: Any = None

def rand_grapheme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::rand_grapheme``."""
    return not_ported(RUST_MODULE, "rand_grapheme")

def ta_with(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::ta_with``."""
    return not_ported(RUST_MODULE, "ta_with")

def insert_and_replace_update_cursor_and_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::insert_and_replace_update_cursor_and_text``."""
    return not_ported(RUST_MODULE, "insert_and_replace_update_cursor_and_text")

def insert_str_at_clamps_to_char_boundary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::insert_str_at_clamps_to_char_boundary``."""
    return not_ported(RUST_MODULE, "insert_str_at_clamps_to_char_boundary")

def set_text_clamps_cursor_to_char_boundary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::set_text_clamps_cursor_to_char_boundary``."""
    return not_ported(RUST_MODULE, "set_text_clamps_cursor_to_char_boundary")

def delete_backward_and_forward_edges(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_backward_and_forward_edges``."""
    return not_ported(RUST_MODULE, "delete_backward_and_forward_edges")

def delete_forward_deletes_element_at_left_edge(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_forward_deletes_element_at_left_edge``."""
    return not_ported(RUST_MODULE, "delete_forward_deletes_element_at_left_edge")

def vim_insert_and_escape(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_insert_and_escape``."""
    return not_ported(RUST_MODULE, "vim_insert_and_escape")

def vim_insert_key_enters_insert_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_insert_key_enters_insert_mode``."""
    return not_ported(RUST_MODULE, "vim_insert_key_enters_insert_mode")

def vim_normal_arrow_keys_move_cursor(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_normal_arrow_keys_move_cursor``."""
    return not_ported(RUST_MODULE, "vim_normal_arrow_keys_move_cursor")

def vim_escape_from_insert_at_start_does_not_underflow(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_escape_from_insert_at_start_does_not_underflow``."""
    return not_ported(RUST_MODULE, "vim_escape_from_insert_at_start_does_not_underflow")

def vim_escape_from_insert_at_line_start_stays_on_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_escape_from_insert_at_line_start_stays_on_line``."""
    return not_ported(RUST_MODULE, "vim_escape_from_insert_at_line_start_stays_on_line")

def vim_escape_moves_by_grapheme_boundary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_escape_moves_by_grapheme_boundary``."""
    return not_ported(RUST_MODULE, "vim_escape_moves_by_grapheme_boundary")

def vim_escape_respects_atomic_element_boundary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_escape_respects_atomic_element_boundary``."""
    return not_ported(RUST_MODULE, "vim_escape_respects_atomic_element_boundary")

def vim_shift_i_enters_insert_at_first_non_blank_with_shift_only_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_shift_i_enters_insert_at_first_non_blank_with_shift_only_binding``."""
    return not_ported(RUST_MODULE, "vim_shift_i_enters_insert_at_first_non_blank_with_shift_only_binding")

def vim_shift_a_enters_insert_at_line_end_with_shift_only_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_shift_a_enters_insert_at_line_end_with_shift_only_binding``."""
    return not_ported(RUST_MODULE, "vim_shift_a_enters_insert_at_line_end_with_shift_only_binding")

def vim_shift_c_changes_to_line_end_and_enters_insert_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_shift_c_changes_to_line_end_and_enters_insert_mode``."""
    return not_ported(RUST_MODULE, "vim_shift_c_changes_to_line_end_and_enters_insert_mode")

def vim_uppercase_c_changes_to_line_end(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_uppercase_c_changes_to_line_end``."""
    return not_ported(RUST_MODULE, "vim_uppercase_c_changes_to_line_end")

def vim_d_at_line_end_does_not_remove_newline(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_d_at_line_end_does_not_remove_newline``."""
    return not_ported(RUST_MODULE, "vim_d_at_line_end_does_not_remove_newline")

def vim_c_at_line_end_enters_insert_without_removing_newline(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_c_at_line_end_enters_insert_without_removing_newline``."""
    return not_ported(RUST_MODULE, "vim_c_at_line_end_enters_insert_without_removing_newline")

def vim_shift_o_opens_line_above_with_shift_only_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_shift_o_opens_line_above_with_shift_only_binding``."""
    return not_ported(RUST_MODULE, "vim_shift_o_opens_line_above_with_shift_only_binding")

def vim_o_opens_line_below_on_inserted_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_o_opens_line_below_on_inserted_line``."""
    return not_ported(RUST_MODULE, "vim_o_opens_line_below_on_inserted_line")

def vim_delete_word(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_delete_word``."""
    return not_ported(RUST_MODULE, "vim_delete_word")

def vim_change_inner_word_deletes_word_and_enters_insert(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_change_inner_word_deletes_word_and_enters_insert``."""
    return not_ported(RUST_MODULE, "vim_change_inner_word_deletes_word_and_enters_insert")

def vim_word_text_objects_cover_delete_yank_and_big_word(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_word_text_objects_cover_delete_yank_and_big_word``."""
    return not_ported(RUST_MODULE, "vim_word_text_objects_cover_delete_yank_and_big_word")

def vim_word_text_objects_accept_cursor_at_word_end(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_word_text_objects_accept_cursor_at_word_end``."""
    return not_ported(RUST_MODULE, "vim_word_text_objects_accept_cursor_at_word_end")

def vim_delimiter_text_objects_select_innermost_pair_and_aliases(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_delimiter_text_objects_select_innermost_pair_and_aliases``."""
    return not_ported(RUST_MODULE, "vim_delimiter_text_objects_select_innermost_pair_and_aliases")

def vim_empty_inner_text_objects_are_valid_targets(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_empty_inner_text_objects_are_valid_targets``."""
    return not_ported(RUST_MODULE, "vim_empty_inner_text_objects_are_valid_targets")

def vim_quote_text_objects_are_line_local_and_handle_escapes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_quote_text_objects_are_line_local_and_handle_escapes``."""
    return not_ported(RUST_MODULE, "vim_quote_text_objects_are_line_local_and_handle_escapes")

def vim_text_object_cancellation_and_unsupported_change_motions_do_not_edit(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_text_object_cancellation_and_unsupported_change_motions_do_not_edit``."""
    return not_ported(RUST_MODULE, "vim_text_object_cancellation_and_unsupported_change_motions_do_not_edit")

def vim_operator_invalid_motion_is_consumed(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_operator_invalid_motion_is_consumed``."""
    return not_ported(RUST_MODULE, "vim_operator_invalid_motion_is_consumed")

def vim_e_lands_on_word_end_character(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_e_lands_on_word_end_character``."""
    return not_ported(RUST_MODULE, "vim_e_lands_on_word_end_character")

def vim_e_advances_from_each_word_end(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_e_advances_from_each_word_end``."""
    return not_ported(RUST_MODULE, "vim_e_advances_from_each_word_end")

def vim_delete_to_word_end_advances_from_existing_word_end(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_delete_to_word_end_advances_from_existing_word_end``."""
    return not_ported(RUST_MODULE, "vim_delete_to_word_end_advances_from_existing_word_end")

def vim_e_from_word_end_can_land_on_trailing_space(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_e_from_word_end_can_land_on_trailing_space``."""
    return not_ported(RUST_MODULE, "vim_e_from_word_end_can_land_on_trailing_space")

def vim_e_advances_across_atomic_element_word_ends(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_e_advances_across_atomic_element_word_ends``."""
    return not_ported(RUST_MODULE, "vim_e_advances_across_atomic_element_word_ends")

def vim_dollar_lands_on_line_end_character(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_dollar_lands_on_line_end_character``."""
    return not_ported(RUST_MODULE, "vim_dollar_lands_on_line_end_character")

def vim_linewise_yank_pastes_below_current_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::vim_linewise_yank_pastes_below_current_line``."""
    return not_ported(RUST_MODULE, "vim_linewise_yank_pastes_below_current_line")

def delete_backward_word_and_kill_line_variants(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_backward_word_and_kill_line_variants``."""
    return not_ported(RUST_MODULE, "delete_backward_word_and_kill_line_variants")

def kill_current_line_removes_current_line_linewise(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::kill_current_line_removes_current_line_linewise``."""
    return not_ported(RUST_MODULE, "kill_current_line_removes_current_line_linewise")

def kill_current_line_keeps_previous_newline_for_final_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::kill_current_line_keeps_previous_newline_for_final_line``."""
    return not_ported(RUST_MODULE, "kill_current_line_keeps_previous_newline_for_final_line")

def kill_whole_line_keymap_dispatch_uses_linewise_kill(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::kill_whole_line_keymap_dispatch_uses_linewise_kill``."""
    return not_ported(RUST_MODULE, "kill_whole_line_keymap_dispatch_uses_linewise_kill")

def delete_forward_word_variants(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_forward_word_variants``."""
    return not_ported(RUST_MODULE, "delete_forward_word_variants")

def delete_forward_word_handles_atomic_elements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_forward_word_handles_atomic_elements``."""
    return not_ported(RUST_MODULE, "delete_forward_word_handles_atomic_elements")

def delete_backward_word_respects_word_separators(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_backward_word_respects_word_separators``."""
    return not_ported(RUST_MODULE, "delete_backward_word_respects_word_separators")

def delete_forward_word_respects_word_separators(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_forward_word_respects_word_separators``."""
    return not_ported(RUST_MODULE, "delete_forward_word_respects_word_separators")

def yank_restores_last_kill(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::yank_restores_last_kill``."""
    return not_ported(RUST_MODULE, "yank_restores_last_kill")

def kill_buffer_persists_across_set_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::kill_buffer_persists_across_set_text``."""
    return not_ported(RUST_MODULE, "kill_buffer_persists_across_set_text")

def cursor_left_and_right_handle_graphemes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::cursor_left_and_right_handle_graphemes``."""
    return not_ported(RUST_MODULE, "cursor_left_and_right_handle_graphemes")

def control_b_and_f_move_cursor(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::control_b_and_f_move_cursor``."""
    return not_ported(RUST_MODULE, "control_b_and_f_move_cursor")

def control_b_f_fallback_control_chars_move_cursor(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::control_b_f_fallback_control_chars_move_cursor``."""
    return not_ported(RUST_MODULE, "control_b_f_fallback_control_chars_move_cursor")

def c0_line_feed_inserts_newline_through_insert_newline_keymap(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::c0_line_feed_inserts_newline_through_insert_newline_keymap``."""
    return not_ported(RUST_MODULE, "c0_line_feed_inserts_newline_through_insert_newline_keymap")

def c0_control_chars_respect_unbound_editor_movement(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::c0_control_chars_respect_unbound_editor_movement``."""
    return not_ported(RUST_MODULE, "c0_control_chars_respect_unbound_editor_movement")

def c0_control_chars_respect_remapped_editor_movement(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::c0_control_chars_respect_remapped_editor_movement``."""
    return not_ported(RUST_MODULE, "c0_control_chars_respect_remapped_editor_movement")

def delete_backward_word_alt_keys(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_backward_word_alt_keys``."""
    return not_ported(RUST_MODULE, "delete_backward_word_alt_keys")

def shift_backspace_and_shift_delete_keep_grapheme_delete_behavior(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::shift_backspace_and_shift_delete_keep_grapheme_delete_behavior``."""
    return not_ported(RUST_MODULE, "shift_backspace_and_shift_delete_keep_grapheme_delete_behavior")

def control_backspace_variants_delete_backward_word(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::control_backspace_variants_delete_backward_word``."""
    return not_ported(RUST_MODULE, "control_backspace_variants_delete_backward_word")

def control_delete_variants_delete_forward_word(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::control_delete_variants_delete_forward_word``."""
    return not_ported(RUST_MODULE, "control_delete_variants_delete_forward_word")

def delete_backward_word_handles_narrow_no_break_space(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_backward_word_handles_narrow_no_break_space``."""
    return not_ported(RUST_MODULE, "delete_backward_word_handles_narrow_no_break_space")

def delete_forward_word_with_without_alt_modifier(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_forward_word_with_without_alt_modifier``."""
    return not_ported(RUST_MODULE, "delete_forward_word_with_without_alt_modifier")

def delete_forward_word_alt_d(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::delete_forward_word_alt_d``."""
    return not_ported(RUST_MODULE, "delete_forward_word_alt_d")

def control_h_backspace(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::control_h_backspace``."""
    return not_ported(RUST_MODULE, "control_h_backspace")

def altgr_ctrl_alt_char_inserts_literal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::altgr_ctrl_alt_char_inserts_literal``."""
    return not_ported(RUST_MODULE, "altgr_ctrl_alt_char_inserts_literal")

def cursor_vertical_movement_across_lines_and_bounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::cursor_vertical_movement_across_lines_and_bounds``."""
    return not_ported(RUST_MODULE, "cursor_vertical_movement_across_lines_and_bounds")

def home_end_and_emacs_style_home_end(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::home_end_and_emacs_style_home_end``."""
    return not_ported(RUST_MODULE, "home_end_and_emacs_style_home_end")

def end_of_line_or_down_at_end_of_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::end_of_line_or_down_at_end_of_text``."""
    return not_ported(RUST_MODULE, "end_of_line_or_down_at_end_of_text")

def word_navigation_helpers(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::word_navigation_helpers``."""
    return not_ported(RUST_MODULE, "word_navigation_helpers")

def word_navigation_cjk_each_char_is_boundary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::word_navigation_cjk_each_char_is_boundary``."""
    return not_ported(RUST_MODULE, "word_navigation_cjk_each_char_is_boundary")

def word_navigation_cjk_forward(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::word_navigation_cjk_forward``."""
    return not_ported(RUST_MODULE, "word_navigation_cjk_forward")

def word_navigation_mixed_ascii_cjk(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::word_navigation_mixed_ascii_cjk``."""
    return not_ported(RUST_MODULE, "word_navigation_mixed_ascii_cjk")

def word_navigation_preserves_separator_breaks_within_unicode_segments(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::word_navigation_preserves_separator_breaks_within_unicode_segments``."""
    return not_ported(RUST_MODULE, "word_navigation_preserves_separator_breaks_within_unicode_segments")

def wrapping_and_cursor_positions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::wrapping_and_cursor_positions``."""
    return not_ported(RUST_MODULE, "wrapping_and_cursor_positions")

def render_highlights_apply_style_without_mutating_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::render_highlights_apply_style_without_mutating_text``."""
    return not_ported(RUST_MODULE, "render_highlights_apply_style_without_mutating_text")

def cursor_pos_with_state_basic_and_scroll_behaviors(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::cursor_pos_with_state_basic_and_scroll_behaviors``."""
    return not_ported(RUST_MODULE, "cursor_pos_with_state_basic_and_scroll_behaviors")

def wrapped_navigation_across_visual_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::wrapped_navigation_across_visual_lines``."""
    return not_ported(RUST_MODULE, "wrapped_navigation_across_visual_lines")

def cursor_pos_with_state_after_movements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::cursor_pos_with_state_after_movements``."""
    return not_ported(RUST_MODULE, "cursor_pos_with_state_after_movements")

def wrapped_navigation_with_newlines_and_spaces(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::wrapped_navigation_with_newlines_and_spaces``."""
    return not_ported(RUST_MODULE, "wrapped_navigation_with_newlines_and_spaces")

def wrapped_navigation_with_wide_graphemes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::wrapped_navigation_with_wide_graphemes``."""
    return not_ported(RUST_MODULE, "wrapped_navigation_with_wide_graphemes")

def fuzz_textarea_randomized(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::textarea::fuzz_textarea_randomized``."""
    return not_ported(RUST_MODULE, "fuzz_textarea_randomized")

__all__ = [
    "KillBufferKind",
    "RUST_MODULE",
    "State",
    "TextArea",
    "TextAreaState",
    "TextElement",
    "TextElementSnapshot",
    "WORD_SEPARATORS",
    "WrapCache",
    "altgr_ctrl_alt_char_inserts_literal",
    "c0_control_chars_respect_remapped_editor_movement",
    "c0_control_chars_respect_unbound_editor_movement",
    "c0_line_feed_inserts_newline_through_insert_newline_keymap",
    "control_b_and_f_move_cursor",
    "control_b_f_fallback_control_chars_move_cursor",
    "control_backspace_variants_delete_backward_word",
    "control_delete_variants_delete_forward_word",
    "control_h_backspace",
    "cursor_left_and_right_handle_graphemes",
    "cursor_pos_with_state_after_movements",
    "cursor_pos_with_state_basic_and_scroll_behaviors",
    "cursor_vertical_movement_across_lines_and_bounds",
    "delete_backward_and_forward_edges",
    "delete_backward_word_alt_keys",
    "delete_backward_word_and_kill_line_variants",
    "delete_backward_word_handles_narrow_no_break_space",
    "delete_backward_word_respects_word_separators",
    "delete_forward_deletes_element_at_left_edge",
    "delete_forward_word_alt_d",
    "delete_forward_word_handles_atomic_elements",
    "delete_forward_word_respects_word_separators",
    "delete_forward_word_variants",
    "delete_forward_word_with_without_alt_modifier",
    "end_of_line_or_down_at_end_of_text",
    "fuzz_textarea_randomized",
    "home_end_and_emacs_style_home_end",
    "insert_and_replace_update_cursor_and_text",
    "insert_str_at_clamps_to_char_boundary",
    "is_word_separator",
    "kill_buffer_persists_across_set_text",
    "kill_current_line_keeps_previous_newline_for_final_line",
    "kill_current_line_removes_current_line_linewise",
    "kill_whole_line_keymap_dispatch_uses_linewise_kill",
    "rand_grapheme",
    "render_highlights_apply_style_without_mutating_text",
    "render_ref",
    "set_text_clamps_cursor_to_char_boundary",
    "shift_backspace_and_shift_delete_keep_grapheme_delete_behavior",
    "split_word_pieces",
    "ta_with",
    "vim_c_at_line_end_enters_insert_without_removing_newline",
    "vim_change_inner_word_deletes_word_and_enters_insert",
    "vim_d_at_line_end_does_not_remove_newline",
    "vim_delete_to_word_end_advances_from_existing_word_end",
    "vim_delete_word",
    "vim_delimiter_text_objects_select_innermost_pair_and_aliases",
    "vim_dollar_lands_on_line_end_character",
    "vim_e_advances_across_atomic_element_word_ends",
    "vim_e_advances_from_each_word_end",
    "vim_e_from_word_end_can_land_on_trailing_space",
    "vim_e_lands_on_word_end_character",
    "vim_empty_inner_text_objects_are_valid_targets",
    "vim_escape_from_insert_at_line_start_stays_on_line",
    "vim_escape_from_insert_at_start_does_not_underflow",
    "vim_escape_moves_by_grapheme_boundary",
    "vim_escape_respects_atomic_element_boundary",
    "vim_insert_and_escape",
    "vim_insert_key_enters_insert_mode",
    "vim_linewise_yank_pastes_below_current_line",
    "vim_normal_arrow_keys_move_cursor",
    "vim_o_opens_line_below_on_inserted_line",
    "vim_operator_invalid_motion_is_consumed",
    "vim_quote_text_objects_are_line_local_and_handle_escapes",
    "vim_shift_a_enters_insert_at_line_end_with_shift_only_binding",
    "vim_shift_c_changes_to_line_end_and_enters_insert_mode",
    "vim_shift_i_enters_insert_at_first_non_blank_with_shift_only_binding",
    "vim_shift_o_opens_line_above_with_shift_only_binding",
    "vim_text_object_cancellation_and_unsupported_change_motions_do_not_edit",
    "vim_uppercase_c_changes_to_line_end",
    "vim_word_text_objects_accept_cursor_at_word_end",
    "vim_word_text_objects_cover_delete_yank_and_big_word",
    "word_navigation_cjk_each_char_is_boundary",
    "word_navigation_cjk_forward",
    "word_navigation_helpers",
    "word_navigation_mixed_ascii_cjk",
    "word_navigation_preserves_separator_breaks_within_unicode_segments",
    "wrapped_navigation_across_visual_lines",
    "wrapped_navigation_with_newlines_and_spaces",
    "wrapped_navigation_with_wide_graphemes",
    "wrapping_and_cursor_positions",
    "yank_restores_last_kill",
]
