from pycodex.tui.chatwidget.status_state import (
    GUARDIAN_REVIEW_DETAIL_PREFIX,
    STATUS_DETAILS_DEFAULT_MAX_LINES,
    PendingGuardianReviewStatus,
    StatusIndicatorState,
    StatusState,
    TerminalTitleStatusKind,
    default,
    guardian_status_aggregates_parallel_reviews,
    retry_status_header_is_taken_once,
)


def test_status_indicator_working_matches_rust_defaults():
    """Rust codex-tui chatwidget::status_state::StatusIndicatorState::working."""

    assert StatusIndicatorState.working() == StatusIndicatorState(
        header="Working",
        details=None,
        details_max_lines=STATUS_DETAILS_DEFAULT_MAX_LINES,
    )


def test_status_indicator_guardian_review_detection():
    """Rust codex-tui chatwidget::status_state::StatusIndicatorState::is_guardian_review."""

    assert StatusIndicatorState("Reviewing approval request").is_guardian_review() is True
    assert StatusIndicatorState("Reviewing 2 approval requests").is_guardian_review() is True
    assert StatusIndicatorState("Working").is_guardian_review() is False


def test_guardian_status_aggregates_parallel_reviews():
    """Rust codex-tui chatwidget::status_state::guardian_status_aggregates_parallel_reviews."""

    assert guardian_status_aggregates_parallel_reviews()


def test_guardian_status_single_empty_update_finish_and_more_lines():
    """Rust PendingGuardianReviewStatus start_or_update/finish/status_indicator_state semantics."""

    state = PendingGuardianReviewStatus()
    assert state.is_empty() is True
    assert state.status_indicator_state() is None

    state.start_or_update("a", "first")
    assert state.status_indicator_state() == StatusIndicatorState(
        header="Reviewing approval request",
        details="first",
        details_max_lines=1,
    )

    state.start_or_update("a", "updated")
    assert state.status_indicator_state().details == "updated"

    state.start_or_update("b", "second")
    state.start_or_update("c", "third")
    state.start_or_update("d", "fourth")
    assert state.status_indicator_state() == StatusIndicatorState(
        header="Reviewing 4 approval requests",
        details=(
            f"{GUARDIAN_REVIEW_DETAIL_PREFIX}updated\n"
            f"{GUARDIAN_REVIEW_DETAIL_PREFIX}second\n"
            f"{GUARDIAN_REVIEW_DETAIL_PREFIX}third\n"
            "+1 more"
        ),
        details_max_lines=4,
    )

    assert state.finish("missing") is False
    assert state.finish("a") is True


def test_retry_status_header_is_taken_once():
    """Rust codex-tui chatwidget::status_state::retry_status_header_is_taken_once."""

    assert retry_status_header_is_taken_once()


def test_retry_status_header_remembers_first_header_only_until_taken():
    """Rust StatusState::remember_retry_status_header keeps existing remembered value."""

    state = StatusState()
    state.current_status = StatusIndicatorState("Thinking")
    state.remember_retry_status_header()
    state.current_status = StatusIndicatorState("Working")
    state.remember_retry_status_header()

    assert state.take_retry_status_header() == "Thinking"
    assert state.take_retry_status_header() is None


def test_status_state_default_and_set_status():
    """Rust StatusState::default and set_status."""

    state = default()
    assert state.current_status == StatusIndicatorState.working()
    assert state.pending_guardian_review_status.is_empty() is True
    assert state.terminal_title_status_kind is TerminalTitleStatusKind.Working
    assert state.retry_status_header is None
    assert state.pending_status_indicator_restore is False

    status = StatusIndicatorState("Custom", "detail", 2)
    state.set_status(status)
    assert state.current_status == status
