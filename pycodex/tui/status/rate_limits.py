"""Behavior port for Rust ``codex-tui::status::rate_limits``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..text_formatting import capitalize_first
from .helpers import format_reset_timestamp

RUST_MODULE = RustTuiModule(crate="codex-tui", module="status::rate_limits", source="codex/codex-rs/tui/src/status/rate_limits.rs")

STATUS_LIMIT_BAR_SEGMENTS = 20
STATUS_LIMIT_BAR_FILLED = "█"
STATUS_LIMIT_BAR_EMPTY = "░"
RATE_LIMIT_STALE_THRESHOLD_MINUTES = 15


@dataclass(frozen=True)
class StatusRateLimitValue:
    kind: str
    percent_used: float | None = None
    resets_at: str | None = None
    text: str | None = None

    @classmethod
    def window(cls, percent_used: float, resets_at: str | None) -> "StatusRateLimitValue":
        return cls("window", percent_used=float(percent_used), resets_at=resets_at)

    @classmethod
    def text_value(cls, text: str) -> "StatusRateLimitValue":
        return cls("text", text=str(text))


@dataclass(frozen=True)
class StatusRateLimitRow:
    label: str
    value: StatusRateLimitValue


@dataclass(frozen=True)
class StatusRateLimitData:
    kind: str
    rows: tuple[StatusRateLimitRow, ...] = ()

    @classmethod
    def available(cls, rows: Iterable[StatusRateLimitRow]) -> "StatusRateLimitData":
        return cls("available", tuple(rows))

    @classmethod
    def stale(cls, rows: Iterable[StatusRateLimitRow]) -> "StatusRateLimitData":
        return cls("stale", tuple(rows))

    @classmethod
    def unavailable(cls) -> "StatusRateLimitData":
        return cls("unavailable")

    @classmethod
    def missing(cls) -> "StatusRateLimitData":
        return cls("missing")


@dataclass(frozen=True)
class RateLimitWindowDisplay:
    used_percent: float
    resets_at: str | None = None
    window_minutes: int | None = None

    @classmethod
    def from_window(cls, window: Any, captured_at: datetime) -> "RateLimitWindowDisplay":
        reset_seconds = _get(window, "resets_at")
        reset_text = None
        if reset_seconds is not None:
            reset_dt = datetime.fromtimestamp(int(reset_seconds), tz=timezone.utc).astimezone()
            reset_text = format_reset_timestamp(reset_dt, _localize(captured_at))
        return cls(
            used_percent=float(_get(window, "used_percent", 0.0)),
            resets_at=reset_text,
            window_minutes=_optional_int(_get(window, "window_duration_mins")),
        )


@dataclass(frozen=True)
class CreditsSnapshotDisplay:
    has_credits: bool
    unlimited: bool
    balance: str | None = None

    @classmethod
    def from_snapshot(cls, value: Any) -> "CreditsSnapshotDisplay":
        return cls(
            has_credits=bool(_get(value, "has_credits", False)),
            unlimited=bool(_get(value, "unlimited", False)),
            balance=_optional_str(_get(value, "balance")),
        )


@dataclass(frozen=True)
class RateLimitSnapshotDisplay:
    limit_name: str
    captured_at: datetime
    primary: RateLimitWindowDisplay | None = None
    secondary: RateLimitWindowDisplay | None = None
    credits: CreditsSnapshotDisplay | None = None


def rate_limit_snapshot_display(snapshot: Any, captured_at: datetime) -> RateLimitSnapshotDisplay:
    return rate_limit_snapshot_display_for_limit(snapshot, "codex", captured_at)


def rate_limit_snapshot_display_for_limit(snapshot: Any, limit_name: str, captured_at: datetime) -> RateLimitSnapshotDisplay:
    primary = _get(snapshot, "primary")
    secondary = _get(snapshot, "secondary")
    credits = _get(snapshot, "credits")
    return RateLimitSnapshotDisplay(
        limit_name=str(limit_name),
        captured_at=_localize(captured_at),
        primary=RateLimitWindowDisplay.from_window(primary, captured_at) if primary is not None else None,
        secondary=RateLimitWindowDisplay.from_window(secondary, captured_at) if secondary is not None else None,
        credits=CreditsSnapshotDisplay.from_snapshot(credits) if credits is not None else None,
    )


def from_(value: Any) -> CreditsSnapshotDisplay:
    return CreditsSnapshotDisplay.from_snapshot(value)


def compose_rate_limit_data(snapshot: RateLimitSnapshotDisplay | None, now: datetime) -> StatusRateLimitData:
    if snapshot is None:
        return StatusRateLimitData.missing()
    return compose_rate_limit_data_many([snapshot], now)


def compose_rate_limit_data_many(snapshots: Iterable[RateLimitSnapshotDisplay], now: datetime) -> StatusRateLimitData:
    snapshot_list = list(snapshots)
    if not snapshot_list:
        return StatusRateLimitData.missing()

    rows: list[StatusRateLimitRow] = []
    stale = False
    now = _localize(now)

    for snapshot in snapshot_list:
        stale = stale or now - _localize(snapshot.captured_at) > timedelta(minutes=RATE_LIMIT_STALE_THRESHOLD_MINUTES)
        limit_bucket_label = snapshot.limit_name
        show_limit_prefix = limit_bucket_label.lower() != "codex"
        primary_label = capitalize_first(limit_label_for_window(snapshot.primary.window_minutes, False)) if snapshot.primary else None
        secondary_label = capitalize_first(limit_label_for_window(snapshot.secondary.window_minutes, True)) if snapshot.secondary else None
        window_count = int(snapshot.primary is not None) + int(snapshot.secondary is not None)
        combine_non_codex_single_limit = show_limit_prefix and window_count == 1

        if show_limit_prefix and not combine_non_codex_single_limit:
            rows.append(StatusRateLimitRow(f"{limit_bucket_label} limit", StatusRateLimitValue.text_value("")))

        if snapshot.primary is not None:
            fallback = capitalize_first(fallback_limit_label(False))
            label = f"{limit_bucket_label} {primary_label or fallback} limit" if combine_non_codex_single_limit else f"{primary_label or fallback} limit"
            rows.append(StatusRateLimitRow(label, StatusRateLimitValue.window(snapshot.primary.used_percent, snapshot.primary.resets_at)))

        if snapshot.secondary is not None:
            fallback = capitalize_first(fallback_limit_label(True))
            label = f"{limit_bucket_label} {secondary_label or fallback} limit" if combine_non_codex_single_limit else f"{secondary_label or fallback} limit"
            rows.append(StatusRateLimitRow(label, StatusRateLimitValue.window(snapshot.secondary.used_percent, snapshot.secondary.resets_at)))

        if snapshot.credits is not None:
            row = credit_status_row(snapshot.credits)
            if row is not None:
                rows.append(row)

    if not rows:
        return StatusRateLimitData.unavailable()
    if stale:
        return StatusRateLimitData.stale(rows)
    return StatusRateLimitData.available(rows)


def render_status_limit_progress_bar(percent_remaining: float) -> str:
    ratio = min(max(float(percent_remaining) / 100.0, 0.0), 1.0)
    filled = min(round(ratio * STATUS_LIMIT_BAR_SEGMENTS), STATUS_LIMIT_BAR_SEGMENTS)
    empty = STATUS_LIMIT_BAR_SEGMENTS - filled
    return f"[{STATUS_LIMIT_BAR_FILLED * filled}{STATUS_LIMIT_BAR_EMPTY * empty}]"


def format_status_limit_summary(percent_remaining: float) -> str:
    return f"{float(percent_remaining):.0f}% left"


def credit_status_row(credits: CreditsSnapshotDisplay) -> StatusRateLimitRow | None:
    if not credits.has_credits:
        return None
    if credits.unlimited:
        return StatusRateLimitRow("Credits", StatusRateLimitValue.text_value("Unlimited"))
    if credits.balance is None:
        return None
    display_balance = format_credit_balance(credits.balance)
    if display_balance is None:
        return None
    return StatusRateLimitRow("Credits", StatusRateLimitValue.text_value(f"{display_balance} credits"))


def format_credit_balance(raw: str) -> str | None:
    trimmed = str(raw).strip()
    if not trimmed:
        return None
    try:
        int_value = int(trimmed, 10)
    except ValueError:
        int_value = None
    if int_value is not None and int_value > 0:
        return str(int_value)
    try:
        value = float(trimmed)
    except ValueError:
        return None
    if value > 0.0:
        return str(round(value))
    return None


def limit_label_for_window(window_minutes: int | None, is_secondary: bool) -> str:
    duration = get_limits_duration(window_minutes) if window_minutes is not None else None
    return duration or fallback_limit_label(is_secondary)


def get_limits_duration(window_minutes: int) -> str | None:
    minutes = max(int(window_minutes), 0)
    hour = 60
    windows = [
        (5 * hour, "5h"),
        (24 * hour, "daily"),
        (7 * 24 * hour, "weekly"),
        (30 * 24 * hour, "monthly"),
        (365 * 24 * hour, "annual"),
    ]
    for expected, label in windows:
        if expected * 0.95 <= minutes <= expected * 1.05:
            return label
    return None


def fallback_limit_label(is_secondary: bool) -> str:
    return "secondary usage" if is_secondary else "usage"


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _localize(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.astimezone()
    return value


__all__ = [
    "CreditsSnapshotDisplay",
    "RATE_LIMIT_STALE_THRESHOLD_MINUTES",
    "RUST_MODULE",
    "RateLimitSnapshotDisplay",
    "RateLimitWindowDisplay",
    "STATUS_LIMIT_BAR_EMPTY",
    "STATUS_LIMIT_BAR_FILLED",
    "STATUS_LIMIT_BAR_SEGMENTS",
    "StatusRateLimitData",
    "StatusRateLimitRow",
    "StatusRateLimitValue",
    "compose_rate_limit_data",
    "compose_rate_limit_data_many",
    "credit_status_row",
    "fallback_limit_label",
    "format_credit_balance",
    "format_status_limit_summary",
    "from_",
    "get_limits_duration",
    "limit_label_for_window",
    "rate_limit_snapshot_display",
    "rate_limit_snapshot_display_for_limit",
    "render_status_limit_progress_bar",
]
