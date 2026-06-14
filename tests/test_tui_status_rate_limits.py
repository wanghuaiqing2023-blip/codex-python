from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pycodex.tui.status.rate_limits import (
    CreditsSnapshotDisplay,
    RateLimitSnapshotDisplay,
    RateLimitWindowDisplay,
    StatusRateLimitData,
    StatusRateLimitRow,
    StatusRateLimitValue,
    compose_rate_limit_data,
    compose_rate_limit_data_many,
    credit_status_row,
    format_credit_balance,
    format_status_limit_summary,
    get_limits_duration,
    limit_label_for_window,
    rate_limit_snapshot_display_for_limit,
    render_status_limit_progress_bar,
)


def window(used_percent: float, minutes: int | None = 300, resets_at: str | None = "soon") -> RateLimitWindowDisplay:
    return RateLimitWindowDisplay(used_percent=used_percent, resets_at=resets_at, window_minutes=minutes)


def test_non_codex_single_limit_renders_combined_row_matches_rust() -> None:
    # Rust: non_codex_single_limit_renders_combined_row.
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    codex = RateLimitSnapshotDisplay(
        limit_name="codex",
        captured_at=now,
        primary=window(10.0),
        credits=CreditsSnapshotDisplay(True, False, "25"),
    )
    other = RateLimitSnapshotDisplay(
        limit_name="codex-other",
        captured_at=now,
        primary=window(20.0),
        credits=CreditsSnapshotDisplay(True, False, "99"),
    )

    data = compose_rate_limit_data_many([codex, other], now)

    assert data.kind == "available"
    assert [row.label for row in data.rows] == ["5h limit", "Credits", "codex-other 5h limit", "Credits"]
    assert sum(1 for row in data.rows if row.label == "Credits") == 2


def test_non_codex_multi_limit_keeps_group_row_matches_rust() -> None:
    # Rust: non_codex_multi_limit_keeps_group_row.
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    other = RateLimitSnapshotDisplay(
        limit_name="codex-other",
        captured_at=now,
        primary=window(20.0, 60),
        secondary=window(40.0, 120, "later"),
    )

    data = compose_rate_limit_data_many([other], now)

    assert data.kind == "available"
    assert [row.label for row in data.rows] == ["codex-other limit", "Usage limit", "Secondary usage limit"]


def test_compose_rate_limit_data_missing_unavailable_and_stale_states() -> None:
    # Rust: compose_rate_limit_data / compose_rate_limit_data_many state classification.
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    assert compose_rate_limit_data(None, now) == StatusRateLimitData.missing()
    assert compose_rate_limit_data_many([], now) == StatusRateLimitData.missing()
    assert compose_rate_limit_data_many([RateLimitSnapshotDisplay("codex", now)], now) == StatusRateLimitData.unavailable()

    old = RateLimitSnapshotDisplay("codex", now - timedelta(minutes=16), primary=window(1.0))
    assert compose_rate_limit_data(old, now).kind == "stale"


def test_credit_rows_and_balance_formatting_match_rust() -> None:
    # Rust: credit_status_row / format_credit_balance.
    assert credit_status_row(CreditsSnapshotDisplay(False, False, "25")) is None
    assert credit_status_row(CreditsSnapshotDisplay(True, True, None)) == StatusRateLimitRow(
        "Credits", StatusRateLimitValue.text_value("Unlimited")
    )
    assert credit_status_row(CreditsSnapshotDisplay(True, False, "25.4")) == StatusRateLimitRow(
        "Credits", StatusRateLimitValue.text_value("25 credits")
    )
    assert credit_status_row(CreditsSnapshotDisplay(True, False, "25.5")) == StatusRateLimitRow(
        "Credits", StatusRateLimitValue.text_value("26 credits")
    )
    assert format_credit_balance("0") is None
    assert format_credit_balance(" ") is None
    assert format_credit_balance("abc") is None


def test_window_label_helpers_and_progress_summary_match_rust_contract() -> None:
    # Rust: limit_label_for_window, render_status_limit_progress_bar, format_status_limit_summary.
    assert get_limits_duration(300) == "5h"
    assert get_limits_duration(1440) == "daily"
    assert get_limits_duration(7 * 1440) == "weekly"
    assert get_limits_duration(30 * 1440) == "monthly"
    assert get_limits_duration(365 * 1440) == "annual"
    assert get_limits_duration(42) is None
    assert limit_label_for_window(None, False) == "usage"
    assert limit_label_for_window(None, True) == "secondary usage"

    assert format_status_limit_summary(12.4) == "12% left"
    assert format_status_limit_summary(12.5) == "12% left"
    assert render_status_limit_progress_bar(50).startswith("[")
    assert render_status_limit_progress_bar(50).endswith("]")
    assert len(render_status_limit_progress_bar(50)) == 22
    assert render_status_limit_progress_bar(-10).count("█") == 0
    assert render_status_limit_progress_bar(110).count("█") == 20


@dataclass
class ProtocolWindow:
    used_percent: float
    resets_at: int | None
    window_duration_mins: int | None


@dataclass
class ProtocolCredits:
    has_credits: bool
    unlimited: bool
    balance: str | None


@dataclass
class ProtocolSnapshot:
    primary: ProtocolWindow | None
    secondary: ProtocolWindow | None
    credits: ProtocolCredits | None


def test_rate_limit_snapshot_display_for_limit_converts_duck_typed_protocol_snapshot() -> None:
    # Rust: rate_limit_snapshot_display_for_limit maps protocol windows/credits to display models.
    captured = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    reset = int((captured + timedelta(hours=1)).timestamp())
    snapshot = ProtocolSnapshot(
        primary=ProtocolWindow(42.0, reset, 300),
        secondary=None,
        credits=ProtocolCredits(True, False, "7"),
    )

    display = rate_limit_snapshot_display_for_limit(snapshot, "codex-other", captured)

    assert display.limit_name == "codex-other"
    assert display.primary is not None
    assert display.primary.used_percent == 42.0
    assert display.primary.window_minutes == 300
    assert display.primary.resets_at is not None
    assert display.credits == CreditsSnapshotDisplay(True, False, "7")
