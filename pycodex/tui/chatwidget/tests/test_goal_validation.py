"""Parity tests for codex-rs/tui/src/chatwidget/goal_validation.rs."""

from pycodex.protocol import MAX_THREAD_GOAL_OBJECTIVE_CHARS
from pycodex.protocol.user_input import ByteRange, TextElement
from pycodex.tui.chatwidget.goal_validation import (
    GOAL_TOO_LONG_FILE_HINT,
    GoalObjectiveValidationSource,
    GoalValidationMixin,
    expand_pending_pastes_like_rust,
    goal_objective_is_allowed,
    goal_objective_with_pending_pastes_is_allowed,
)


class FakeBottomPane:
    def __init__(self):
        self.pending_pastes = []
        self.composer_updates = []
        self.drained = 0

    def composer_pending_pastes(self):
        return list(self.pending_pastes)

    def set_composer_text(self, text, text_elements, attachments):
        self.composer_updates.append((text, text_elements, attachments))

    def drain_pending_submission_state(self):
        self.drained += 1


class FakeWidget:
    def __init__(self):
        self.bottom_pane = FakeBottomPane()
        self.errors = []

    def add_error_message(self, message):
        self.errors.append(message)


class MixedWidget(GoalValidationMixin, FakeWidget):
    pass


def test_goal_objective_accepts_objective_at_limit():
    widget = FakeWidget()
    objective = "x" * MAX_THREAD_GOAL_OBJECTIVE_CHARS

    assert goal_objective_is_allowed(widget, objective, GoalObjectiveValidationSource.LIVE) is True
    assert widget.errors == []
    assert widget.bottom_pane.composer_updates == []


def test_live_goal_objective_rejects_oversized_objective_with_goal_specific_error_and_clears_composer():
    widget = FakeWidget()
    objective = "x" * (MAX_THREAD_GOAL_OBJECTIVE_CHARS + 1)

    assert goal_objective_is_allowed(widget, objective, GoalObjectiveValidationSource.LIVE) is False

    assert widget.errors == [
        f"Goal objective is too long: 4,001 characters. Limit: 4,000 characters. {GOAL_TOO_LONG_FILE_HINT}"
    ]
    assert widget.bottom_pane.composer_updates == [("", [], [])]
    assert widget.bottom_pane.drained == 1
    assert "Message exceeds the maximum length" not in widget.errors[0]


def test_queued_goal_objective_rejects_oversized_objective_without_live_cleanup():
    widget = FakeWidget()
    objective = "x" * (MAX_THREAD_GOAL_OBJECTIVE_CHARS + 1)

    assert goal_objective_is_allowed(widget, objective, GoalObjectiveValidationSource.QUEUED) is False

    assert "Goal objective is too long" in widget.errors[0]
    assert widget.bottom_pane.composer_updates == []
    assert widget.bottom_pane.drained == 0


def test_pending_paste_validation_uses_expanded_trimmed_length():
    widget = FakeWidget()
    placeholder = "[Pasted text #1]"
    widget.bottom_pane.pending_pastes = [(placeholder, "x" * (MAX_THREAD_GOAL_OBJECTIVE_CHARS + 1))]
    text = "/goal " + placeholder
    text_elements = [TextElement.new(ByteRange(6, 6 + len(placeholder)), placeholder)]

    assert goal_objective_with_pending_pastes_is_allowed(widget, text, text_elements) is False

    assert "4,007 characters" in widget.errors[0]
    assert widget.bottom_pane.composer_updates == [("", [], [])]


def test_pending_paste_validation_without_text_elements_matches_rust_no_expand_fast_path():
    widget = FakeWidget()
    widget.bottom_pane.pending_pastes = [("[Pasted text #1]", "large")]

    assert goal_objective_with_pending_pastes_is_allowed(widget, "/goal ", []) is True
    assert widget.errors == []


def test_expand_pending_pastes_replaces_placeholders_fifo_and_rebases_survivors():
    # Rust: ChatComposer::expand_pending_pastes indexes pending pastes by
    # placeholder, consumes replacements FIFO, drops replaced placeholder
    # elements, and rebases surviving elements into the rebuilt byte stream.
    text = "A [P] B [P] C [KEEP]"
    first_start = len("A ")
    first_end = first_start + len("[P]")
    second_start = len("A [P] B ")
    second_end = second_start + len("[P]")
    keep_start = len("A [P] B [P] C ")
    keep_end = keep_start + len("[KEEP]")
    elements = [
        TextElement.new(ByteRange(first_start, first_end), "[P]"),
        TextElement.new(ByteRange(second_start, second_end), "[P]"),
        TextElement.new(ByteRange(keep_start, keep_end), "[KEEP]"),
    ]

    expanded, rebuilt_elements = expand_pending_pastes_like_rust(
        text,
        elements,
        [("[P]", "one"), ("[P]", "two")],
    )

    assert expanded == "A one B two C [KEEP]"
    assert len(rebuilt_elements) == 1
    assert rebuilt_elements[0].byte_range == ByteRange(
        len("A one B two C "),
        len("A one B two C [KEEP]"),
    )
    assert rebuilt_elements[0].placeholder(expanded) == "[KEEP]"


def test_mixin_exposes_rust_impl_method_shape():
    widget = MixedWidget()

    assert widget.goal_objective_is_allowed("short", "Live") is True
    assert widget.goal_objective_char_count_is_allowed(
        MAX_THREAD_GOAL_OBJECTIVE_CHARS + 1,
        GoalObjectiveValidationSource.QUEUED,
    ) is False
    assert widget.bottom_pane.drained == 0
