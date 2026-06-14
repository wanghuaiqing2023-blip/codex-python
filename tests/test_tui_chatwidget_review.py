"""Parity tests for codex-rs/tui/src/chatwidget/review.rs."""

from pycodex.tui.auto_review_denials import RecentAutoReviewDenials, denied_event
from pycodex.tui.chatwidget.review import PreReviewTokenInfoSnapshot, ReviewState
from pycodex.tui.token_usage import TokenUsageInfo


def test_default_review_state_matches_rust_default_fields():
    state = ReviewState()

    assert isinstance(state.recent_auto_review_denials, RecentAutoReviewDenials)
    assert state.recent_auto_review_denials.is_empty() is True
    assert state.is_review_mode is False
    assert state.pre_review_token_info.is_none is True


def test_recent_auto_review_denials_field_uses_real_denial_store():
    state = ReviewState()

    state.recent_auto_review_denials.push(denied_event(1))

    assert [entry.id for entry in state.recent_auto_review_denials.entries()] == ["review-1"]


def test_review_mode_flag_is_plain_mutable_state():
    state = ReviewState()

    state.is_review_mode = True

    assert state.is_review_mode is True


def test_pre_review_token_snapshot_preserves_option_option_tristate():
    token_info = TokenUsageInfo()

    unset = PreReviewTokenInfoSnapshot.not_captured()
    captured_none = PreReviewTokenInfoSnapshot.captured_value(None)
    captured_some = PreReviewTokenInfoSnapshot.captured_value(token_info)

    assert unset.is_none is True
    assert unset.is_some_none is False
    assert captured_none.is_none is False
    assert captured_none.is_some_none is True
    assert captured_some.is_some_some is True
    assert captured_some.token_info is token_info


def test_review_state_can_store_pre_review_token_snapshot():
    token_info = TokenUsageInfo()
    state = ReviewState(
        pre_review_token_info=PreReviewTokenInfoSnapshot.captured_value(token_info)
    )

    assert state.pre_review_token_info.is_some_some is True
    assert state.pre_review_token_info.token_info is token_info
