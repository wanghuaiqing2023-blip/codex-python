"""Parity tests for codex-rs/tui/src/chatwidget/goal_validation.rs."""

from pycodex.protocol import MAX_THREAD_GOAL_OBJECTIVE_CHARS
from pycodex.tui.chatwidget.goal_validation import (
    GOAL_TOO_LONG_FILE_HINT,
    GoalObjectiveValidationSource,
    GoalValidationMixin,
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

    def expand_pending_pastes(self, args, text_elements, pending_pastes):
        return args + "".join(pending_pastes), text_elements


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
    widget.bottom_pane.pending_pastes = ["x" * (MAX_THREAD_GOAL_OBJECTIVE_CHARS + 1)]

    assert goal_objective_with_pending_pastes_is_allowed(widget, "/goal ", []) is False

    assert "4,007 characters" in widget.errors[0]
    assert widget.bottom_pane.composer_updates == [("", [], [])]


def test_pending_paste_validation_requires_expander_when_pending_pastes_exist():
    widget = FakeWidget()
    widget.bottom_pane.pending_pastes = ["large"]
    delattr(widget.bottom_pane, "expand_pending_pastes")

    try:
        goal_objective_with_pending_pastes_is_allowed(widget, "/goal ", [])
    except NotImplementedError as exc:
        assert "pending paste expansion requires" in str(exc)
    else:
        raise AssertionError("expected NotImplementedError")


def test_mixin_exposes_rust_impl_method_shape():
    widget = MixedWidget()

    assert widget.goal_objective_is_allowed("short", "Live") is True
    assert widget.goal_objective_char_count_is_allowed(
        MAX_THREAD_GOAL_OBJECTIVE_CHARS + 1,
        GoalObjectiveValidationSource.QUEUED,
    ) is False
    assert widget.bottom_pane.drained == 0
