"""Behavior port for Rust ``codex-tui::chatwidget::rate_limits``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::rate_limits", source="codex/codex-rs/tui/src/chatwidget/rate_limits.rs")

NUDGE_MODEL_SLUG = "gpt-5.4-mini"
RATE_LIMIT_SWITCH_PROMPT_THRESHOLD = 90.0
RATE_LIMIT_WARNING_THRESHOLDS = (75.0, 90.0, 95.0)
PRIMARY_LIMIT_FALLBACK_LABEL = "usage"
SECONDARY_LIMIT_FALLBACK_LABEL = "secondary usage"
MINUTES_PER_HOUR = 60
MINUTES_PER_5_HOURS = 5 * MINUTES_PER_HOUR
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY
MINUTES_PER_MONTH = 30 * MINUTES_PER_DAY
MINUTES_PER_YEAR = 365 * MINUTES_PER_DAY


@dataclass
class RateLimitWarningState:
    secondary_index: int = 0
    primary_index: int = 0

    def take_warnings(
        self,
        secondary_used_percent: float | None,
        secondary_window_minutes: int | None,
        primary_used_percent: float | None,
        primary_window_minutes: int | None,
    ) -> list[str]:
        reached_secondary_cap = secondary_used_percent == 100.0
        reached_primary_cap = primary_used_percent == 100.0
        if reached_secondary_cap or reached_primary_cap:
            return []

        warnings: list[str] = []
        if secondary_used_percent is not None:
            threshold = self._advance_secondary(float(secondary_used_percent))
            if threshold is not None:
                limit_label = limit_label_for_window(secondary_window_minutes, True)
                warnings.append(_warning_message(100.0 - threshold, limit_label))
        if primary_used_percent is not None:
            threshold = self._advance_primary(float(primary_used_percent))
            if threshold is not None:
                limit_label = limit_label_for_window(primary_window_minutes, False)
                warnings.append(_warning_message(100.0 - threshold, limit_label))
        return warnings

    def _advance_secondary(self, used_percent: float) -> float | None:
        highest = None
        while self.secondary_index < len(RATE_LIMIT_WARNING_THRESHOLDS) and used_percent >= RATE_LIMIT_WARNING_THRESHOLDS[self.secondary_index]:
            highest = RATE_LIMIT_WARNING_THRESHOLDS[self.secondary_index]
            self.secondary_index += 1
        return highest

    def _advance_primary(self, used_percent: float) -> float | None:
        highest = None
        while self.primary_index < len(RATE_LIMIT_WARNING_THRESHOLDS) and used_percent >= RATE_LIMIT_WARNING_THRESHOLDS[self.primary_index]:
            highest = RATE_LIMIT_WARNING_THRESHOLDS[self.primary_index]
            self.primary_index += 1
        return highest


class RateLimitSwitchPromptState(Enum):
    IDLE = "idle"
    PENDING = "pending"
    SHOWN = "shown"


class RateLimitErrorKind(Enum):
    SERVER_OVERLOADED = "server_overloaded"
    USAGE_LIMIT = "usage_limit"
    GENERIC = "generic"


def limit_label_for_window(window_minutes: int | None, is_secondary: bool) -> str:
    duration = get_limits_duration(window_minutes) if window_minutes is not None else None
    return duration or fallback_limit_label(is_secondary)


def get_limits_duration(windows_minutes: int) -> str | None:
    minutes = max(int(windows_minutes), 0)
    if is_approximate_window(minutes, MINUTES_PER_5_HOURS):
        return "5h"
    if is_approximate_window(minutes, MINUTES_PER_DAY):
        return "daily"
    if is_approximate_window(minutes, MINUTES_PER_WEEK):
        return "weekly"
    if is_approximate_window(minutes, MINUTES_PER_MONTH):
        return "monthly"
    if is_approximate_window(minutes, MINUTES_PER_YEAR):
        return "annual"
    return None


def fallback_limit_label(is_secondary: bool) -> str:
    return SECONDARY_LIMIT_FALLBACK_LABEL if is_secondary else PRIMARY_LIMIT_FALLBACK_LABEL


def is_approximate_window(minutes: int, expected_minutes: int) -> bool:
    value = float(minutes)
    expected = float(expected_minutes)
    return value >= expected * 0.95 and value <= expected * 1.05


def app_server_rate_limit_error_kind(info: Any) -> RateLimitErrorKind | None:
    name = _variant_name(info)
    if name == "ServerOverloaded":
        return RateLimitErrorKind.SERVER_OVERLOADED
    if name == "UsageLimitExceeded":
        return RateLimitErrorKind.USAGE_LIMIT
    if name == "ResponseTooManyFailedAttempts":
        status = _get(info, "http_status_code")
        if status == 429:
            return RateLimitErrorKind.GENERIC
    return None


def is_app_server_cyber_policy_error(info: Any) -> bool:
    return _variant_name(info) == "CyberPolicy"


def _warning_message(remaining_percent: float, limit_label: str) -> str:
    return f"Heads up, you have less than {remaining_percent:.0f}% of your {limit_label} limit left. Run /status for a breakdown."


def _variant_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "kind" in value:
            return str(value["kind"])
        if "type" in value:
            return str(value["type"])
        if len(value) == 1:
            return str(next(iter(value)))
    name = getattr(value, "kind", getattr(value, "type", getattr(value, "name", None)))
    if name is not None:
        return str(name)
    return type(value).__name__


def _get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        payload = value.get(key)
        if payload is None and len(value) == 1:
            inner = next(iter(value.values()))
            if isinstance(inner, dict):
                payload = inner.get(key)
        return payload
    return getattr(value, key, None)


__all__ = [
    "MINUTES_PER_5_HOURS",
    "MINUTES_PER_DAY",
    "MINUTES_PER_HOUR",
    "MINUTES_PER_MONTH",
    "MINUTES_PER_WEEK",
    "MINUTES_PER_YEAR",
    "NUDGE_MODEL_SLUG",
    "PRIMARY_LIMIT_FALLBACK_LABEL",
    "RATE_LIMIT_SWITCH_PROMPT_THRESHOLD",
    "RATE_LIMIT_WARNING_THRESHOLDS",
    "RUST_MODULE",
    "RateLimitErrorKind",
    "RateLimitSwitchPromptState",
    "RateLimitWarningState",
    "SECONDARY_LIMIT_FALLBACK_LABEL",
    "app_server_rate_limit_error_kind",
    "fallback_limit_label",
    "get_limits_duration",
    "is_app_server_cyber_policy_error",
    "is_approximate_window",
    "limit_label_for_window",
]
