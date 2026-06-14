"""Python interface scaffold for Rust ``codex-tui::bottom_pane::request_user_input``.

Upstream source: ``codex/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from ..._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="bottom_pane::request_user_input", source="codex/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs")

NOTES_PLACEHOLDER: Any = None

ANSWER_PLACEHOLDER: Any = None

MIN_COMPOSER_HEIGHT: Any = None

SELECT_OPTION_PLACEHOLDER: Any = None

TIP_SEPARATOR: Any = None

DESIRED_SPACERS_BETWEEN_SECTIONS: Any = None

OTHER_OPTION_LABEL: Any = None

OTHER_OPTION_DESCRIPTION: Any = None

UNANSWERED_CONFIRM_TITLE: Any = None

UNANSWERED_CONFIRM_GO_BACK: Any = None

UNANSWERED_CONFIRM_GO_BACK_DESC: Any = None

UNANSWERED_CONFIRM_SUBMIT: Any = None

UNANSWERED_CONFIRM_SUBMIT_DESC_SINGULAR: Any = None

UNANSWERED_CONFIRM_SUBMIT_DESC_PLURAL: Any = None

class Focus(Enum):
    """Python boundary for Rust enum ``bottom_pane::request_user_input::Focus``."""
    UNPORTED = "unported"

@dataclass
class ComposerDraft:
    """Python boundary for Rust ``bottom_pane::request_user_input::ComposerDraft``."""
    _payload: Any = None

    def text_with_pending(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ComposerDraft.text_with_pending")

@dataclass
class AnswerState:
    """Python boundary for Rust ``bottom_pane::request_user_input::AnswerState``."""
    _payload: Any = None

@dataclass
class FooterTip:
    """Python boundary for Rust ``bottom_pane::request_user_input::FooterTip``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "FooterTip.new")

    def highlighted(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "FooterTip.highlighted")

@dataclass
class RequestUserInputOverlay:
    """Python boundary for Rust ``bottom_pane::request_user_input::RequestUserInputOverlay``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.new")

    def new_with_keymap(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.new_with_keymap")

    def current_index(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.current_index")

    def current_question(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.current_question")

    def current_answer_mut(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.current_answer_mut")

    def current_answer(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.current_answer")

    def question_count(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.question_count")

    def advance_queue_or_complete(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.advance_queue_or_complete")

    def has_options(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.has_options")

    def options_len(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.options_len")

    def option_index_for_digit(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.option_index_for_digit")

    def selected_option_index(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.selected_option_index")

    def notes_has_content(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.notes_has_content")

    def notes_ui_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.notes_ui_visible")

    def wrapped_question_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.wrapped_question_lines")

    def focus_is_notes(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.focus_is_notes")

    def confirm_unanswered_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.confirm_unanswered_active")

    def option_rows(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.option_rows")

    def options_required_height(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.options_required_height")

    def options_preferred_height(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.options_preferred_height")

    def capture_composer_draft(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.capture_composer_draft")

    def save_current_draft(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.save_current_draft")

    def restore_current_draft(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.restore_current_draft")

    def notes_placeholder(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.notes_placeholder")

    def sync_composer_placeholder(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.sync_composer_placeholder")

    def clear_notes_draft(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.clear_notes_draft")

    def footer_tips(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.footer_tips")

    def footer_tip_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.footer_tip_lines")

    def footer_tip_lines_with_prefix(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.footer_tip_lines_with_prefix")

    def wrap_footer_tips(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.wrap_footer_tips")

    def footer_required_height(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.footer_required_height")

    def ensure_focus_available(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.ensure_focus_available")

    def reset_for_request(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.reset_for_request")

    def options_len_for_question(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.options_len_for_question")

    def other_option_enabled_for_question(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.other_option_enabled_for_question")

    def option_label_for_index(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.option_label_for_index")

    def move_question(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.move_question")

    def jump_to_question(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.jump_to_question")

    def select_current_option(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.select_current_option")

    def clear_selection(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.clear_selection")

    def clear_notes_and_focus_options(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.clear_notes_and_focus_options")

    def ensure_selected_for_notes(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.ensure_selected_for_notes")

    def go_next_or_submit(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.go_next_or_submit")

    def submit_answers(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.submit_answers")

    def dismiss_resolved_request(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.dismiss_resolved_request")

    def open_unanswered_confirmation(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.open_unanswered_confirmation")

    def close_unanswered_confirmation(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.close_unanswered_confirmation")

    def unanswered_question_count(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.unanswered_question_count")

    def unanswered_submit_description(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.unanswered_submit_description")

    def first_unanswered_index(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.first_unanswered_index")

    def unanswered_confirmation_rows(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.unanswered_confirmation_rows")

    def is_question_answered(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.is_question_answered")

    def unanswered_count(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.unanswered_count")

    def notes_input_height(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.notes_input_height")

    def apply_submission_to_draft(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.apply_submission_to_draft")

    def apply_submission_draft(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.apply_submission_draft")

    def handle_composer_input_result(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.handle_composer_input_result")

    def handle_confirm_unanswered_key_event(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RequestUserInputOverlay.handle_confirm_unanswered_key_event")

def prefer_esc_to_handle_key_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::prefer_esc_to_handle_key_event``."""
    return not_ported(RUST_MODULE, "prefer_esc_to_handle_key_event")

def handle_key_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::handle_key_event``."""
    return not_ported(RUST_MODULE, "handle_key_event")

def terminal_title_requires_action(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::terminal_title_requires_action``."""
    return not_ported(RUST_MODULE, "terminal_title_requires_action")

def on_ctrl_c(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::on_ctrl_c``."""
    return not_ported(RUST_MODULE, "on_ctrl_c")

def is_complete(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::is_complete``."""
    return not_ported(RUST_MODULE, "is_complete")

def handle_paste(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::handle_paste``."""
    return not_ported(RUST_MODULE, "handle_paste")

def flush_paste_burst_if_due(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::flush_paste_burst_if_due``."""
    return not_ported(RUST_MODULE, "flush_paste_burst_if_due")

def is_in_paste_burst(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::is_in_paste_burst``."""
    return not_ported(RUST_MODULE, "is_in_paste_burst")

def try_consume_user_input_request(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::try_consume_user_input_request``."""
    return not_ported(RUST_MODULE, "try_consume_user_input_request")

def dismiss_app_server_request(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::dismiss_app_server_request``."""
    return not_ported(RUST_MODULE, "dismiss_app_server_request")

def test_sender(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::test_sender``."""
    return not_ported(RUST_MODULE, "test_sender")

def expect_interrupt_only(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::expect_interrupt_only``."""
    return not_ported(RUST_MODULE, "expect_interrupt_only")

def question_with_options(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::question_with_options``."""
    return not_ported(RUST_MODULE, "question_with_options")

def question_with_options_and_other(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::question_with_options_and_other``."""
    return not_ported(RUST_MODULE, "question_with_options_and_other")

def question_with_wrapped_options(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::question_with_wrapped_options``."""
    return not_ported(RUST_MODULE, "question_with_wrapped_options")

def question_with_very_long_option_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::question_with_very_long_option_text``."""
    return not_ported(RUST_MODULE, "question_with_very_long_option_text")

def question_with_long_scroll_options(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::question_with_long_scroll_options``."""
    return not_ported(RUST_MODULE, "question_with_long_scroll_options")

def question_without_options(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::question_without_options``."""
    return not_ported(RUST_MODULE, "question_without_options")

def request_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_event``."""
    return not_ported(RUST_MODULE, "request_event")

def snapshot_buffer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::snapshot_buffer``."""
    return not_ported(RUST_MODULE, "snapshot_buffer")

def render_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::render_snapshot``."""
    return not_ported(RUST_MODULE, "render_snapshot")

def queued_requests_are_fifo(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::queued_requests_are_fifo``."""
    return not_ported(RUST_MODULE, "queued_requests_are_fifo")

def interrupt_discards_queued_requests_and_emits_interrupt(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::interrupt_discards_queued_requests_and_emits_interrupt``."""
    return not_ported(RUST_MODULE, "interrupt_discards_queued_requests_and_emits_interrupt")

def resolved_request_dismisses_overlay_without_emitting_events(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::resolved_request_dismisses_overlay_without_emitting_events``."""
    return not_ported(RUST_MODULE, "resolved_request_dismisses_overlay_without_emitting_events")

def resolved_current_request_advances_to_next_same_turn_prompt(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::resolved_current_request_advances_to_next_same_turn_prompt``."""
    return not_ported(RUST_MODULE, "resolved_current_request_advances_to_next_same_turn_prompt")

def resolved_queued_request_removes_only_that_prompt(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::resolved_queued_request_removes_only_that_prompt``."""
    return not_ported(RUST_MODULE, "resolved_queued_request_removes_only_that_prompt")

def options_can_submit_empty_when_unanswered(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::options_can_submit_empty_when_unanswered``."""
    return not_ported(RUST_MODULE, "options_can_submit_empty_when_unanswered")

def enter_commits_default_selection_on_last_option_question(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::enter_commits_default_selection_on_last_option_question``."""
    return not_ported(RUST_MODULE, "enter_commits_default_selection_on_last_option_question")

def enter_commits_default_selection_on_non_last_option_question(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::enter_commits_default_selection_on_non_last_option_question``."""
    return not_ported(RUST_MODULE, "enter_commits_default_selection_on_non_last_option_question")

def number_keys_select_and_submit_options(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::number_keys_select_and_submit_options``."""
    return not_ported(RUST_MODULE, "number_keys_select_and_submit_options")

def vim_keys_move_option_selection(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::vim_keys_move_option_selection``."""
    return not_ported(RUST_MODULE, "vim_keys_move_option_selection")

def typing_in_options_does_not_open_notes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::typing_in_options_does_not_open_notes``."""
    return not_ported(RUST_MODULE, "typing_in_options_does_not_open_notes")

def h_l_move_between_questions_in_options(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::h_l_move_between_questions_in_options``."""
    return not_ported(RUST_MODULE, "h_l_move_between_questions_in_options")

def left_right_move_between_questions_in_options(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::left_right_move_between_questions_in_options``."""
    return not_ported(RUST_MODULE, "left_right_move_between_questions_in_options")

def horizontal_list_keys_move_between_questions_in_options(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::horizontal_list_keys_move_between_questions_in_options``."""
    return not_ported(RUST_MODULE, "horizontal_list_keys_move_between_questions_in_options")

def options_notes_focus_hides_question_navigation_tip(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::options_notes_focus_hides_question_navigation_tip``."""
    return not_ported(RUST_MODULE, "options_notes_focus_hides_question_navigation_tip")

def freeform_shows_ctrl_p_and_ctrl_n_question_navigation_tip(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_shows_ctrl_p_and_ctrl_n_question_navigation_tip``."""
    return not_ported(RUST_MODULE, "freeform_shows_ctrl_p_and_ctrl_n_question_navigation_tip")

def freeform_footer_shows_configured_submit_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_footer_shows_configured_submit_binding``."""
    return not_ported(RUST_MODULE, "freeform_footer_shows_configured_submit_binding")

def request_user_input_uses_remapped_interrupt_binding_while_notes_are_visible(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_uses_remapped_interrupt_binding_while_notes_are_visible``."""
    return not_ported(RUST_MODULE, "request_user_input_uses_remapped_interrupt_binding_while_notes_are_visible")

def tab_opens_notes_when_option_selected(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::tab_opens_notes_when_option_selected``."""
    return not_ported(RUST_MODULE, "tab_opens_notes_when_option_selected")

def switching_to_options_resets_notes_focus_when_notes_hidden(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::switching_to_options_resets_notes_focus_when_notes_hidden``."""
    return not_ported(RUST_MODULE, "switching_to_options_resets_notes_focus_when_notes_hidden")

def switching_from_freeform_with_text_resets_focus_and_keeps_last_option_empty(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::switching_from_freeform_with_text_resets_focus_and_keeps_last_option_empty``."""
    return not_ported(RUST_MODULE, "switching_from_freeform_with_text_resets_focus_and_keeps_last_option_empty")

def esc_in_notes_mode_without_options_interrupts(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::esc_in_notes_mode_without_options_interrupts``."""
    return not_ported(RUST_MODULE, "esc_in_notes_mode_without_options_interrupts")

def esc_in_options_mode_interrupts(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::esc_in_options_mode_interrupts``."""
    return not_ported(RUST_MODULE, "esc_in_options_mode_interrupts")

def esc_in_notes_mode_clears_notes_and_hides_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::esc_in_notes_mode_clears_notes_and_hides_ui``."""
    return not_ported(RUST_MODULE, "esc_in_notes_mode_clears_notes_and_hides_ui")

def esc_in_notes_mode_with_text_clears_notes_and_hides_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::esc_in_notes_mode_with_text_clears_notes_and_hides_ui``."""
    return not_ported(RUST_MODULE, "esc_in_notes_mode_with_text_clears_notes_and_hides_ui")

def esc_drops_committed_answers(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::esc_drops_committed_answers``."""
    return not_ported(RUST_MODULE, "esc_drops_committed_answers")

def backspace_in_options_clears_selection(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::backspace_in_options_clears_selection``."""
    return not_ported(RUST_MODULE, "backspace_in_options_clears_selection")

def backspace_on_empty_notes_closes_notes_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::backspace_on_empty_notes_closes_notes_ui``."""
    return not_ported(RUST_MODULE, "backspace_on_empty_notes_closes_notes_ui")

def tab_in_notes_clears_notes_and_hides_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::tab_in_notes_clears_notes_and_hides_ui``."""
    return not_ported(RUST_MODULE, "tab_in_notes_clears_notes_and_hides_ui")

def skipped_option_questions_count_as_unanswered(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::skipped_option_questions_count_as_unanswered``."""
    return not_ported(RUST_MODULE, "skipped_option_questions_count_as_unanswered")

def highlighted_option_questions_are_unanswered(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::highlighted_option_questions_are_unanswered``."""
    return not_ported(RUST_MODULE, "highlighted_option_questions_are_unanswered")

def freeform_requires_enter_with_text_to_mark_answered(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_requires_enter_with_text_to_mark_answered``."""
    return not_ported(RUST_MODULE, "freeform_requires_enter_with_text_to_mark_answered")

def freeform_enter_with_empty_text_is_unanswered(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_enter_with_empty_text_is_unanswered``."""
    return not_ported(RUST_MODULE, "freeform_enter_with_empty_text_is_unanswered")

def freeform_shift_enter_inserts_newline_without_advancing(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_shift_enter_inserts_newline_without_advancing``."""
    return not_ported(RUST_MODULE, "freeform_shift_enter_inserts_newline_without_advancing")

def freeform_uses_configured_composer_submit_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_uses_configured_composer_submit_binding``."""
    return not_ported(RUST_MODULE, "freeform_uses_configured_composer_submit_binding")

def freeform_submit_binding_wins_over_question_navigation(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_submit_binding_wins_over_question_navigation``."""
    return not_ported(RUST_MODULE, "freeform_submit_binding_wins_over_question_navigation")

def freeform_questions_submit_empty_when_empty(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_questions_submit_empty_when_empty``."""
    return not_ported(RUST_MODULE, "freeform_questions_submit_empty_when_empty")

def freeform_draft_is_not_submitted_without_enter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_draft_is_not_submitted_without_enter``."""
    return not_ported(RUST_MODULE, "freeform_draft_is_not_submitted_without_enter")

def freeform_commit_resets_when_draft_changes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::freeform_commit_resets_when_draft_changes``."""
    return not_ported(RUST_MODULE, "freeform_commit_resets_when_draft_changes")

def notes_are_captured_for_selected_option(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::notes_are_captured_for_selected_option``."""
    return not_ported(RUST_MODULE, "notes_are_captured_for_selected_option")

def notes_submission_commits_selected_option(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::notes_submission_commits_selected_option``."""
    return not_ported(RUST_MODULE, "notes_submission_commits_selected_option")

def is_other_adds_none_of_the_above_and_submits_it(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::is_other_adds_none_of_the_above_and_submits_it``."""
    return not_ported(RUST_MODULE, "is_other_adds_none_of_the_above_and_submits_it")

def large_paste_is_preserved_when_switching_questions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::large_paste_is_preserved_when_switching_questions``."""
    return not_ported(RUST_MODULE, "large_paste_is_preserved_when_switching_questions")

def pending_paste_placeholder_survives_submission_and_back_navigation(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::pending_paste_placeholder_survives_submission_and_back_navigation``."""
    return not_ported(RUST_MODULE, "pending_paste_placeholder_survives_submission_and_back_navigation")

def request_user_input_options_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_options_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_options_snapshot")

def request_user_input_options_notes_visible_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_options_notes_visible_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_options_notes_visible_snapshot")

def request_user_input_tight_height_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_tight_height_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_tight_height_snapshot")

def layout_allocates_all_wrapped_options_when_space_allows(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::layout_allocates_all_wrapped_options_when_space_allows``."""
    return not_ported(RUST_MODULE, "layout_allocates_all_wrapped_options_when_space_allows")

def desired_height_keeps_spacers_and_preferred_options_visible(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::desired_height_keeps_spacers_and_preferred_options_visible``."""
    return not_ported(RUST_MODULE, "desired_height_keeps_spacers_and_preferred_options_visible")

def footer_wraps_tips_without_splitting_individual_tips(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::footer_wraps_tips_without_splitting_individual_tips``."""
    return not_ported(RUST_MODULE, "footer_wraps_tips_without_splitting_individual_tips")

def request_user_input_wrapped_options_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_wrapped_options_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_wrapped_options_snapshot")

def request_user_input_long_option_text_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_long_option_text_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_long_option_text_snapshot")

def selected_long_wrapped_option_stays_visible(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::selected_long_wrapped_option_stays_visible``."""
    return not_ported(RUST_MODULE, "selected_long_wrapped_option_stays_visible")

def request_user_input_footer_wrap_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_footer_wrap_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_footer_wrap_snapshot")

def request_user_input_scroll_options_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_scroll_options_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_scroll_options_snapshot")

def request_user_input_hidden_options_footer_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_hidden_options_footer_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_hidden_options_footer_snapshot")

def request_user_input_freeform_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_freeform_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_freeform_snapshot")

def request_user_input_freeform_remapped_submit_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_freeform_remapped_submit_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_freeform_remapped_submit_snapshot")

def request_user_input_freeform_remapped_interrupt_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_freeform_remapped_interrupt_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_freeform_remapped_interrupt_snapshot")

def request_user_input_multi_question_first_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_multi_question_first_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_multi_question_first_snapshot")

def request_user_input_multi_question_last_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_multi_question_last_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_multi_question_last_snapshot")

def request_user_input_unanswered_confirmation_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::request_user_input_unanswered_confirmation_snapshot``."""
    return not_ported(RUST_MODULE, "request_user_input_unanswered_confirmation_snapshot")

def options_scroll_while_editing_notes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::request_user_input::options_scroll_while_editing_notes``."""
    return not_ported(RUST_MODULE, "options_scroll_while_editing_notes")

__all__ = [
    "ANSWER_PLACEHOLDER",
    "AnswerState",
    "ComposerDraft",
    "DESIRED_SPACERS_BETWEEN_SECTIONS",
    "Focus",
    "FooterTip",
    "MIN_COMPOSER_HEIGHT",
    "NOTES_PLACEHOLDER",
    "OTHER_OPTION_DESCRIPTION",
    "OTHER_OPTION_LABEL",
    "RUST_MODULE",
    "RequestUserInputOverlay",
    "SELECT_OPTION_PLACEHOLDER",
    "TIP_SEPARATOR",
    "UNANSWERED_CONFIRM_GO_BACK",
    "UNANSWERED_CONFIRM_GO_BACK_DESC",
    "UNANSWERED_CONFIRM_SUBMIT",
    "UNANSWERED_CONFIRM_SUBMIT_DESC_PLURAL",
    "UNANSWERED_CONFIRM_SUBMIT_DESC_SINGULAR",
    "UNANSWERED_CONFIRM_TITLE",
    "backspace_in_options_clears_selection",
    "backspace_on_empty_notes_closes_notes_ui",
    "desired_height_keeps_spacers_and_preferred_options_visible",
    "dismiss_app_server_request",
    "enter_commits_default_selection_on_last_option_question",
    "enter_commits_default_selection_on_non_last_option_question",
    "esc_drops_committed_answers",
    "esc_in_notes_mode_clears_notes_and_hides_ui",
    "esc_in_notes_mode_with_text_clears_notes_and_hides_ui",
    "esc_in_notes_mode_without_options_interrupts",
    "esc_in_options_mode_interrupts",
    "expect_interrupt_only",
    "flush_paste_burst_if_due",
    "footer_wraps_tips_without_splitting_individual_tips",
    "freeform_commit_resets_when_draft_changes",
    "freeform_draft_is_not_submitted_without_enter",
    "freeform_enter_with_empty_text_is_unanswered",
    "freeform_footer_shows_configured_submit_binding",
    "freeform_questions_submit_empty_when_empty",
    "freeform_requires_enter_with_text_to_mark_answered",
    "freeform_shift_enter_inserts_newline_without_advancing",
    "freeform_shows_ctrl_p_and_ctrl_n_question_navigation_tip",
    "freeform_submit_binding_wins_over_question_navigation",
    "freeform_uses_configured_composer_submit_binding",
    "h_l_move_between_questions_in_options",
    "handle_key_event",
    "handle_paste",
    "highlighted_option_questions_are_unanswered",
    "horizontal_list_keys_move_between_questions_in_options",
    "interrupt_discards_queued_requests_and_emits_interrupt",
    "is_complete",
    "is_in_paste_burst",
    "is_other_adds_none_of_the_above_and_submits_it",
    "large_paste_is_preserved_when_switching_questions",
    "layout_allocates_all_wrapped_options_when_space_allows",
    "left_right_move_between_questions_in_options",
    "notes_are_captured_for_selected_option",
    "notes_submission_commits_selected_option",
    "number_keys_select_and_submit_options",
    "on_ctrl_c",
    "options_can_submit_empty_when_unanswered",
    "options_notes_focus_hides_question_navigation_tip",
    "options_scroll_while_editing_notes",
    "pending_paste_placeholder_survives_submission_and_back_navigation",
    "prefer_esc_to_handle_key_event",
    "question_with_long_scroll_options",
    "question_with_options",
    "question_with_options_and_other",
    "question_with_very_long_option_text",
    "question_with_wrapped_options",
    "question_without_options",
    "queued_requests_are_fifo",
    "render_snapshot",
    "request_event",
    "request_user_input_footer_wrap_snapshot",
    "request_user_input_freeform_remapped_interrupt_snapshot",
    "request_user_input_freeform_remapped_submit_snapshot",
    "request_user_input_freeform_snapshot",
    "request_user_input_hidden_options_footer_snapshot",
    "request_user_input_long_option_text_snapshot",
    "request_user_input_multi_question_first_snapshot",
    "request_user_input_multi_question_last_snapshot",
    "request_user_input_options_notes_visible_snapshot",
    "request_user_input_options_snapshot",
    "request_user_input_scroll_options_snapshot",
    "request_user_input_tight_height_snapshot",
    "request_user_input_unanswered_confirmation_snapshot",
    "request_user_input_uses_remapped_interrupt_binding_while_notes_are_visible",
    "request_user_input_wrapped_options_snapshot",
    "resolved_current_request_advances_to_next_same_turn_prompt",
    "resolved_queued_request_removes_only_that_prompt",
    "resolved_request_dismisses_overlay_without_emitting_events",
    "selected_long_wrapped_option_stays_visible",
    "skipped_option_questions_count_as_unanswered",
    "snapshot_buffer",
    "switching_from_freeform_with_text_resets_focus_and_keeps_last_option_empty",
    "switching_to_options_resets_notes_focus_when_notes_hidden",
    "tab_in_notes_clears_notes_and_hides_ui",
    "tab_opens_notes_when_option_selected",
    "terminal_title_requires_action",
    "test_sender",
    "try_consume_user_input_request",
    "typing_in_options_does_not_open_notes",
    "vim_keys_move_option_selection",
]

# --- Ported semantic slice for Rust request_user_input/mod.rs ---
# Kept at the end intentionally: this overrides the original interface-only
# scaffold definitions without pretending to port the full overlay state machine.

from collections import deque as _deque
import textwrap as _textwrap

NOTES_PLACEHOLDER = "Add notes"
ANSWER_PLACEHOLDER = "Type your answer (optional)"
MIN_COMPOSER_HEIGHT = 3
SELECT_OPTION_PLACEHOLDER = "Select an option to add notes"
TIP_SEPARATOR = " | "
DESIRED_SPACERS_BETWEEN_SECTIONS = 2
OTHER_OPTION_LABEL = "None of the above"
OTHER_OPTION_DESCRIPTION = "Optionally, add details in notes (tab)."
UNANSWERED_CONFIRM_TITLE = "Submit with unanswered questions?"
UNANSWERED_CONFIRM_GO_BACK = "Go back"
UNANSWERED_CONFIRM_GO_BACK_DESC = "Return to the first unanswered question."
UNANSWERED_CONFIRM_SUBMIT = "Proceed"
UNANSWERED_CONFIRM_SUBMIT_DESC_SINGULAR = "question"
UNANSWERED_CONFIRM_SUBMIT_DESC_PLURAL = "questions"


class Focus(Enum):
    Options = "options"
    Notes = "notes"


@dataclass
class ComposerDraft:
    text: str = ""
    text_elements: list[Any] | None = None
    local_image_paths: list[Any] | None = None
    pending_pastes: list[tuple[str, str]] | None = None

    def __post_init__(self) -> None:
        if self.text_elements is None:
            self.text_elements = []
        if self.local_image_paths is None:
            self.local_image_paths = []
        if self.pending_pastes is None:
            self.pending_pastes = []

    def text_with_pending(self) -> str:
        if not self.pending_pastes:
            return self.text
        expanded = self.text
        for marker, replacement in self.pending_pastes:
            expanded = expanded.replace(marker, replacement)
        return expanded


@dataclass
class _ScrollState:
    selected_idx: int | None = None
    scroll_top: int = 0

    def clamp_selection(self, length: int) -> None:
        if length <= 0:
            self.selected_idx = None
            self.scroll_top = 0
        elif self.selected_idx is None:
            self.selected_idx = 0
        elif self.selected_idx >= length:
            self.selected_idx = length - 1


@dataclass
class AnswerState:
    options_state: _ScrollState | None = None
    draft: ComposerDraft | None = None
    answer_committed: bool = False
    notes_visible: bool = False

    def __post_init__(self) -> None:
        if self.options_state is None:
            self.options_state = _ScrollState()
        if self.draft is None:
            self.draft = ComposerDraft()


@dataclass
class FooterTip:
    text: str
    highlight: bool = False

    @classmethod
    def new(cls, text: Any) -> "FooterTip":
        return cls(str(text), False)

    @classmethod
    def highlighted(cls, text: Any) -> "FooterTip":
        return cls(str(text), True)


@dataclass
class RequestUserInputOverlay:
    request: Any
    app_event_tx: Any = None
    answers: list[AnswerState] | None = None
    current_idx: int = 0
    focus: Focus = Focus.Options
    done: bool = False
    queue: Any = None
    composer_submit_keys: list[Any] | None = None
    interrupt_turn_keys: list[Any] | None = None

    @classmethod
    def new(cls, request: Any, app_event_tx: Any = None, *args: Any, **kwargs: Any) -> "RequestUserInputOverlay":
        return cls(request=request, app_event_tx=app_event_tx)

    @classmethod
    def new_with_keymap(cls, request: Any, app_event_tx: Any = None, *args: Any, **kwargs: Any) -> "RequestUserInputOverlay":
        return cls.new(request, app_event_tx)

    def __post_init__(self) -> None:
        if self.queue is None:
            self.queue = _deque()
        if self.composer_submit_keys is None:
            self.composer_submit_keys = ["enter"]
        if self.interrupt_turn_keys is None:
            self.interrupt_turn_keys = ["esc"]
        if self.answers is None:
            self.answers = [AnswerState() for _ in self.questions()]
        self.ensure_focus_available()

    def questions(self) -> list[Any]:
        return list(_get(self.request, "questions", []) or [])

    def current_index(self) -> int:
        return self.current_idx

    def current_question(self) -> Any | None:
        questions = self.questions()
        return questions[self.current_idx] if 0 <= self.current_idx < len(questions) else None

    def current_answer(self) -> AnswerState | None:
        return self.answers[self.current_idx] if self.answers and 0 <= self.current_idx < len(self.answers) else None

    def current_answer_mut(self) -> AnswerState | None:
        return self.current_answer()

    def question_count(self) -> int:
        return len(self.questions())

    def has_options(self) -> bool:
        question = self.current_question()
        options = _get(question, "options", None) if question is not None else None
        return bool(options)

    def options_len(self) -> int:
        question = self.current_question()
        return self.options_len_for_question(question) if question is not None else 0

    @staticmethod
    def options_len_for_question(question: Any) -> int:
        options = list(_get(question, "options", []) or [])
        return len(options) + (1 if RequestUserInputOverlay.other_option_enabled_for_question(question) else 0)

    @staticmethod
    def other_option_enabled_for_question(question: Any) -> bool:
        return bool(_get(question, "is_other", False))

    def option_index_for_digit(self, ch: str) -> int | None:
        if not self.has_options() or not str(ch).isdigit():
            return None
        digit = int(ch)
        if digit == 0:
            return None
        idx = digit - 1
        return idx if idx < self.options_len() else None

    def selected_option_index(self) -> int | None:
        if not self.has_options():
            return None
        answer = self.current_answer()
        return None if answer is None else answer.options_state.selected_idx

    def notes_has_content(self, idx: int) -> bool:
        if not self.answers or idx < 0 or idx >= len(self.answers):
            return False
        return bool(self.answers[idx].draft.text_with_pending().strip())

    def notes_ui_visible(self) -> bool:
        if not self.has_options():
            return True
        answer = self.current_answer()
        return bool(answer and (answer.notes_visible or self.notes_has_content(self.current_idx)))

    def wrapped_question_lines(self, width: int) -> list[str]:
        question = self.current_question()
        text = str(_get(question, "question", "")) if question is not None else ""
        return _textwrap.wrap(text, width=max(int(width), 1)) if text else []

    def focus_is_notes(self) -> bool:
        return self.focus is Focus.Notes

    def ensure_focus_available(self) -> None:
        if not self.has_options():
            self.focus = Focus.Notes
        elif self.focus is Focus.Notes and not self.notes_ui_visible():
            self.focus = Focus.Options

    def option_label_for_index(self, idx: int) -> str | None:
        question = self.current_question()
        options = list(_get(question, "options", []) or []) if question is not None else []
        if 0 <= idx < len(options):
            return str(_get(options[idx], "label", ""))
        if idx == len(options) and question is not None and self.other_option_enabled_for_question(question):
            return OTHER_OPTION_LABEL
        return None

    def footer_tip_lines(self, width: int) -> list[list[FooterTip]]:
        return self.wrap_footer_tips(width, self.footer_tips())

    def footer_tip_lines_with_prefix(self, width: int, prefix: FooterTip | None) -> list[list[FooterTip]]:
        tips = ([] if prefix is None else [prefix]) + self.footer_tips()
        return self.wrap_footer_tips(width, tips)

    def footer_tips(self) -> list[FooterTip]:
        tips: list[FooterTip] = []
        if self.has_options() and self.selected_option_index() is not None and not self.notes_ui_visible():
            tips.append(FooterTip.highlighted("tab to add notes"))
        submit = self.composer_submit_keys[0] if self.focus_is_notes() or not self.has_options() else "enter"
        if self.question_count() == 1:
            tips.append(FooterTip.highlighted(f"{submit} to submit answer"))
        else:
            last = self.current_idx + 1 >= self.question_count()
            tips.append(FooterTip.highlighted(f"{submit} to submit all") if last else FooterTip.new(f"{submit} to submit answer"))
        if self.question_count() > 1:
            tips.append(FooterTip.new("ctrl + p / ctrl + n change question") if not self.has_options() else FooterTip.new("left/right to navigate questions"))
        if self.interrupt_turn_keys:
            tips.append(FooterTip.new(f"{self.interrupt_turn_keys[0]} to interrupt"))
        return tips

    def wrap_footer_tips(self, width: int, tips: list[FooterTip]) -> list[list[FooterTip]]:
        max_width = max(int(width), 1)
        if not tips:
            return [[]]
        lines: list[list[FooterTip]] = []
        current: list[FooterTip] = []
        used = 0
        sep_width = len(TIP_SEPARATOR)
        for tip in tips:
            tip_width = min(len(tip.text), max_width)
            extra = tip_width if not current else sep_width + tip_width
            if current and used + extra > max_width:
                lines.append(current)
                current = []
                used = 0
                extra = tip_width
            current.append(tip)
            used += extra
        if current:
            lines.append(current)
        return lines

    def footer_required_height(self, width: int) -> int:
        return len(self.footer_tip_lines(width))


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
