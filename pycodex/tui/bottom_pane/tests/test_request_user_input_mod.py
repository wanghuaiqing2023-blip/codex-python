from pycodex.tui.bottom_pane.request_user_input import (
    ANSWER_PLACEHOLDER,
    NOTES_PLACEHOLDER,
    OTHER_OPTION_LABEL,
    SELECT_OPTION_PLACEHOLDER,
    TIP_SEPARATOR,
    AnswerState,
    ComposerDraft,
    Focus,
    FooterTip,
    RequestUserInputOverlay,
    backspace_in_options_clears_selection,
    enter_commits_default_selection_on_last_option_question,
    esc_in_notes_mode_clears_notes_and_hides_ui,
    freeform_questions_submit_empty_when_empty,
    freeform_shift_enter_inserts_newline_without_advancing,
    is_other_adds_none_of_the_above_and_submits_it,
    notes_submission_commits_selected_option,
    number_keys_select_and_submit_options,
    queued_requests_are_fifo,
    resolved_current_request_advances_to_next_same_turn_prompt,
    resolved_queued_request_removes_only_that_prompt,
    resolved_request_dismisses_overlay_without_emitting_events,
    tab_opens_notes_when_option_selected,
    typing_in_options_does_not_open_notes,
)


def question(question="Pick one", options=None, is_other=False):
    return {"question": question, "options": options, "is_other": is_other}


def option(label):
    return {"label": label, "description": f"{label} description"}


def request(*questions):
    return {"questions": list(questions)}


# Rust source: codex/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs
def test_constants_and_focus_variants_match_rust_visible_copy():
    assert NOTES_PLACEHOLDER == "Add notes"
    assert ANSWER_PLACEHOLDER == "Type your answer (optional)"
    assert SELECT_OPTION_PLACEHOLDER == "Select an option to add notes"
    assert TIP_SEPARATOR == " | "
    assert OTHER_OPTION_LABEL == "None of the above"
    assert [focus.name for focus in Focus] == ["Options", "Notes"]


def test_composer_draft_text_with_pending_expands_placeholders():
    draft = ComposerDraft(text="before <paste> after", pending_pastes=[("<paste>", "large text")])
    assert draft.text_with_pending() == "before large text after"
    assert ComposerDraft(text="plain").text_with_pending() == "plain"


def test_overlay_option_detection_digit_mapping_and_other_option():
    overlay = RequestUserInputOverlay.new(request(question(options=[option("A"), option("B")], is_other=True)))
    assert overlay.has_options()
    assert overlay.options_len() == 3
    assert overlay.option_index_for_digit("1") == 0
    assert overlay.option_index_for_digit("3") == 2
    assert overlay.option_index_for_digit("0") is None
    assert overlay.option_label_for_index(2) == OTHER_OPTION_LABEL


def test_notes_visibility_and_focus_for_freeform_and_option_questions():
    freeform = RequestUserInputOverlay.new(request(question(options=None)))
    assert freeform.focus is Focus.Notes
    assert freeform.notes_ui_visible()

    overlay = RequestUserInputOverlay.new(request(question(options=[option("A")])) )
    assert overlay.focus is Focus.Options
    assert not overlay.notes_ui_visible()
    overlay.answers[0].notes_visible = True
    assert overlay.notes_ui_visible()


def test_wrapped_question_lines_are_width_bounded():
    overlay = RequestUserInputOverlay.new(request(question(question="alpha beta gamma", options=None)))
    assert overlay.wrapped_question_lines(6) == ["alpha", "beta", "gamma"]


def test_footer_tip_constructors_and_wrapping_do_not_split_tips():
    plain = FooterTip.new("plain")
    highlighted = FooterTip.highlighted("important")
    assert not plain.highlight
    assert highlighted.highlight

    overlay = RequestUserInputOverlay.new(request(question(options=[option("A")]), question(options=None)))
    overlay.answers[0].options_state.selected_idx = 0
    # Rust: codex-tui bottom_pane::request_user_input
    # test footer_wraps_tips_without_splitting_individual_tips uses width = 36.
    lines = overlay.footer_tip_lines(36)
    assert len(lines) > 1
    for line in lines:
        joined = TIP_SEPARATOR.join(tip.text for tip in line)
        assert len(joined) <= 36


def test_footer_required_height_counts_wrapped_tip_lines():
    overlay = RequestUserInputOverlay.new(request(question(options=[option("A")]), question(options=None)))
    assert overlay.footer_required_height(24) == len(overlay.footer_tip_lines(24))


def test_queue_and_resolution_contracts_match_rust_mod_tests():
    # Rust: codex-tui::bottom_pane::request_user_input::tests
    # Contracts: FIFO queued prompts and server-resolved prompts are consumed without user events.
    assert queued_requests_are_fifo() is True
    assert resolved_request_dismisses_overlay_without_emitting_events() is True
    assert resolved_current_request_advances_to_next_same_turn_prompt() is True
    assert resolved_queued_request_removes_only_that_prompt() is True


def test_option_keyboard_contracts_match_rust_mod_tests():
    # Rust: codex-tui::bottom_pane::request_user_input::tests
    # Contracts: enter/digit commits selection, typing does not open notes, backspace clears selection.
    assert enter_commits_default_selection_on_last_option_question() is True
    assert number_keys_select_and_submit_options() is True
    assert typing_in_options_does_not_open_notes() is True
    assert backspace_in_options_clears_selection() is True


def test_notes_and_freeform_submission_contracts_match_rust_mod_tests():
    # Rust: codex-tui::bottom_pane::request_user_input::tests
    # Contracts: tab opens notes, notes append to selected option, freeform empty submits [].
    assert tab_opens_notes_when_option_selected() is True
    assert esc_in_notes_mode_clears_notes_and_hides_ui() is True
    assert notes_submission_commits_selected_option() is True
    assert is_other_adds_none_of_the_above_and_submits_it() is True
    assert freeform_questions_submit_empty_when_empty() is True
    assert freeform_shift_enter_inserts_newline_without_advancing() is True
