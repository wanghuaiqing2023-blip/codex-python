"""Parity tests for codex-rs/tui/src/history_cell/request_user_input.rs."""

from pycodex.tui.history_cell.request_user_input import (
    RequestUserInputResultCell,
    ToolRequestUserInputAnswer,
    ToolRequestUserInputQuestion,
    line_text,
    split_request_user_input_answer,
    wrap_with_prefix,
)


def texts(lines):
    return [line_text(line) for line in lines]


# Rust source: codex/codex-rs/tui/src/history_cell/request_user_input.rs
def test_split_answer_separates_options_from_last_user_note() -> None:
    options, note = split_request_user_input_answer(
        ToolRequestUserInputAnswer(("A", "user_note: first", "B", "user_note: final"))
    )

    assert options == ["A", "B"]
    assert note == "final"


def test_wrap_with_prefix_applies_initial_and_subsequent_prefixes() -> None:
    # Rust source: request_user_input::wrap_with_prefix delegates to the shared
    # adaptive_wrap_line FirstFit word-wrapping contract.
    wrapped = wrap_with_prefix("alpha beta gamma", 10, "? ", "  ")

    assert texts(wrapped) == ["? alpha", "  beta", "  gamma"]


def test_display_lines_counts_answered_and_marks_unanswered() -> None:
    cell = RequestUserInputResultCell.new(
        [
            {"id": "q1", "question": "Pick one", "options": ["A", "B"]},
            {"id": "q2", "question": "Explain"},
        ],
        {"q1": {"answers": ["A"]}},
        False,
    )

    rendered = texts(cell.display_lines(80))

    assert rendered[0] == "- Questions 1/2 answered"
    assert "  ? Pick one" in rendered
    assert "    answer: A" in rendered
    assert "  ? Explain (unanswered)" in rendered


def test_secret_answer_is_masked_in_display_and_raw_lines() -> None:
    cell = RequestUserInputResultCell.new(
        [ToolRequestUserInputQuestion("secret", "Password?", is_secret=True)],
        {"secret": ToolRequestUserInputAnswer(("hunter2",))},
    )

    assert "hunter2" not in "\n".join(texts(cell.display_lines(80)))
    assert "    answer: ******" in texts(cell.display_lines(80))
    assert texts(cell.raw_lines()) == [
        "Questions 1/1 answered",
        "Password?",
        "answer: ******",
    ]


def test_note_label_depends_on_question_options() -> None:
    with_options = RequestUserInputResultCell.new(
        [{"id": "q", "question": "Choose", "options": ["A"]}],
        {"q": {"answers": ["A", "user_note: because"]}},
    )
    freeform = RequestUserInputResultCell.new(
        [{"id": "q", "question": "Say"}],
        {"q": {"answers": ["user_note: hello"]}},
    )

    assert "    note: because" in texts(with_options.display_lines(80))
    assert "    answer: hello" in texts(freeform.display_lines(80))
    assert texts(with_options.raw_lines()) == [
        "Questions 1/1 answered",
        "Choose",
        "answer: A",
        "note: because",
    ]


def test_interrupted_summary_only_when_unanswered_remain() -> None:
    cell = RequestUserInputResultCell.new(
        [
            {"id": "q1", "question": "One"},
            {"id": "q2", "question": "Two"},
        ],
        {"q1": {"answers": ["yes"]}},
        True,
    )

    rendered = texts(cell.display_lines(80))
    raw = texts(cell.raw_lines())

    assert rendered[0] == "- Questions 1/2 answered (interrupted)"
    assert "  -> interrupted with 1 unanswered" in rendered
    assert raw[:2] == ["Questions 1/2 answered", "(interrupted)"]
