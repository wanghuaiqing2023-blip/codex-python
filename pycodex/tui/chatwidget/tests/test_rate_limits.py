from __future__ import annotations

from pycodex.tui.chatwidget.rate_limits import (
    MINUTES_PER_5_HOURS,
    MINUTES_PER_DAY,
    MINUTES_PER_MONTH,
    MINUTES_PER_WEEK,
    MINUTES_PER_YEAR,
    NUDGE_MODEL_SLUG,
    RATE_LIMIT_SWITCH_PROMPT_THRESHOLD,
    RATE_LIMIT_WARNING_THRESHOLDS,
    RateLimitErrorKind,
    RateLimitSwitchPromptState,
    RateLimitWarningState,
    app_server_rate_limit_error_kind,
    fallback_limit_label,
    get_limits_duration,
    is_app_server_cyber_policy_error,
    is_approximate_window,
    limit_label_for_window,
)


def test_constants_and_prompt_states_match_rust_values() -> None:
    # Rust: module constants and RateLimitSwitchPromptState variants.
    assert NUDGE_MODEL_SLUG == "gpt-5.4-mini"
    assert RATE_LIMIT_SWITCH_PROMPT_THRESHOLD == 90.0
    assert RATE_LIMIT_WARNING_THRESHOLDS == (75.0, 90.0, 95.0)
    assert [state.value for state in RateLimitSwitchPromptState] == ["idle", "pending", "shown"]


def test_limit_duration_labels_use_five_percent_tolerance() -> None:
    # Rust: get_limits_duration and is_approximate_window.
    assert is_approximate_window(int(MINUTES_PER_DAY * 0.95), MINUTES_PER_DAY) is True
    assert is_approximate_window(int(MINUTES_PER_DAY * 1.05), MINUTES_PER_DAY) is True
    assert is_approximate_window(int(MINUTES_PER_DAY * 1.05) + 1, MINUTES_PER_DAY) is False
    assert get_limits_duration(-10) is None
    assert get_limits_duration(MINUTES_PER_5_HOURS) == "5h"
    assert get_limits_duration(MINUTES_PER_DAY) == "daily"
    assert get_limits_duration(MINUTES_PER_WEEK) == "weekly"
    assert get_limits_duration(MINUTES_PER_MONTH) == "monthly"
    assert get_limits_duration(MINUTES_PER_YEAR) == "annual"
    assert get_limits_duration(42) is None


def test_limit_label_falls_back_by_primary_or_secondary() -> None:
    # Rust: limit_label_for_window / fallback_limit_label.
    assert fallback_limit_label(False) == "usage"
    assert fallback_limit_label(True) == "secondary usage"
    assert limit_label_for_window(None, False) == "usage"
    assert limit_label_for_window(None, True) == "secondary usage"
    assert limit_label_for_window(MINUTES_PER_5_HOURS, False) == "5h"


def test_warning_state_emits_highest_new_threshold_once_per_limit() -> None:
    # Rust: RateLimitWarningState::take_warnings walks thresholds and advances indices.
    state = RateLimitWarningState()
    assert state.take_warnings(None, None, 74.0, MINUTES_PER_5_HOURS) == []

    assert state.take_warnings(None, None, 91.0, MINUTES_PER_5_HOURS) == [
        "Heads up, you have less than 10% of your 5h limit left. Run /status for a breakdown."
    ]
    assert state.primary_index == 2
    assert state.take_warnings(None, None, 92.0, MINUTES_PER_5_HOURS) == []

    assert state.take_warnings(None, None, 96.0, MINUTES_PER_5_HOURS) == [
        "Heads up, you have less than 5% of your 5h limit left. Run /status for a breakdown."
    ]
    assert state.take_warnings(None, None, 99.0, MINUTES_PER_5_HOURS) == []


def test_warning_state_handles_secondary_then_primary_order_and_cap_suppression() -> None:
    # Rust emits secondary warning before primary and returns no warnings when either cap reaches 100%.
    state = RateLimitWarningState()
    assert state.take_warnings(75.0, MINUTES_PER_DAY, 75.0, None) == [
        "Heads up, you have less than 25% of your daily limit left. Run /status for a breakdown.",
        "Heads up, you have less than 25% of your usage limit left. Run /status for a breakdown.",
    ]
    assert state.take_warnings(100.0, MINUTES_PER_DAY, 80.0, None) == []
    assert state.take_warnings(80.0, MINUTES_PER_DAY, 100.0, None) == []


def test_rate_limit_error_kind_mapping_matches_app_server_variants() -> None:
    # Rust: app_server_rate_limit_error_kind.
    assert app_server_rate_limit_error_kind("ServerOverloaded") == RateLimitErrorKind.SERVER_OVERLOADED
    assert app_server_rate_limit_error_kind("UsageLimitExceeded") == RateLimitErrorKind.USAGE_LIMIT
    assert app_server_rate_limit_error_kind({"kind": "ResponseTooManyFailedAttempts", "http_status_code": 429}) == RateLimitErrorKind.GENERIC
    assert app_server_rate_limit_error_kind({"ResponseTooManyFailedAttempts": {"http_status_code": 429}}) == RateLimitErrorKind.GENERIC
    assert app_server_rate_limit_error_kind({"kind": "ResponseTooManyFailedAttempts", "http_status_code": 500}) is None
    assert app_server_rate_limit_error_kind("Other") is None


def test_cyber_policy_detection_is_separate_from_rate_limit_errors() -> None:
    # Rust: is_app_server_cyber_policy_error.
    assert is_app_server_cyber_policy_error("CyberPolicy") is True
    assert is_app_server_cyber_policy_error({"kind": "CyberPolicy"}) is True
    assert is_app_server_cyber_policy_error("UsageLimitExceeded") is False
