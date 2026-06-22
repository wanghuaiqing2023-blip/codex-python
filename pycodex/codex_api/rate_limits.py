"""Rate-limit parsing contracts for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/rate_limits.rs``
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.protocol.protocol import RateLimitReachedType


@dataclass(frozen=True)
class RateLimitError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class RateLimitWindow:
    used_percent: float
    window_minutes: int | None = None
    resets_at: int | None = None


@dataclass(frozen=True)
class CreditsSnapshot:
    has_credits: bool
    unlimited: bool
    balance: str | None = None


@dataclass(frozen=True)
class RateLimitSnapshot:
    limit_id: str | None = None
    limit_name: str | None = None
    primary: RateLimitWindow | None = None
    secondary: RateLimitWindow | None = None
    credits: CreditsSnapshot | None = None
    plan_type: str | None = None
    rate_limit_reached_type: str | None = None


def parse_default_rate_limit(headers: Mapping[str, object]) -> RateLimitSnapshot | None:
    return parse_rate_limit_for_limit(headers, None)


def parse_all_rate_limits(headers: Mapping[str, object]) -> list[RateLimitSnapshot]:
    snapshots: list[RateLimitSnapshot] = []
    default = parse_default_rate_limit(headers)
    if default is not None:
        snapshots.append(default)

    limit_ids: set[str] = set()
    for name in headers:
        limit_id = _header_name_to_limit_id(str(name).lower())
        if limit_id is not None and limit_id != "codex":
            limit_ids.add(limit_id)

    for limit_id in sorted(limit_ids):
        snapshot = parse_rate_limit_for_limit(headers, limit_id)
        if snapshot is not None and _has_rate_limit_data(snapshot):
            snapshots.append(snapshot)
    return snapshots


def parse_rate_limit_for_limit(
    headers: Mapping[str, object],
    limit_id: str | None = None,
) -> RateLimitSnapshot | None:
    normalized_limit = (limit_id or "codex").strip() or "codex"
    normalized_limit = normalized_limit.lower().replace("_", "-")
    prefix = f"x-{normalized_limit}"
    primary = _parse_rate_limit_window(
        headers,
        f"{prefix}-primary-used-percent",
        f"{prefix}-primary-window-minutes",
        f"{prefix}-primary-reset-at",
    )
    secondary = _parse_rate_limit_window(
        headers,
        f"{prefix}-secondary-used-percent",
        f"{prefix}-secondary-window-minutes",
        f"{prefix}-secondary-reset-at",
    )
    limit_name = _parse_header_str(headers, f"{prefix}-limit-name")
    if limit_name is not None:
        limit_name = limit_name.strip() or None

    return RateLimitSnapshot(
        limit_id=_normalize_limit_id(normalized_limit),
        limit_name=limit_name,
        primary=primary,
        secondary=secondary,
        credits=_parse_credits_snapshot(headers),
    )


def parse_rate_limit_event(payload: str) -> RateLimitSnapshot | None:
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict) or event.get("type") != "codex.rate_limits":
        return None

    details = event.get("rate_limits")
    primary = secondary = None
    if isinstance(details, dict):
        primary = _map_event_window(details.get("primary"))
        secondary = _map_event_window(details.get("secondary"))

    credits = None
    raw_credits = event.get("credits")
    if isinstance(raw_credits, dict):
        has_credits = raw_credits.get("has_credits")
        unlimited = raw_credits.get("unlimited")
        if not isinstance(has_credits, bool) or not isinstance(unlimited, bool):
            return None
        credits = CreditsSnapshot(
            has_credits=has_credits,
            unlimited=unlimited,
            balance=raw_credits.get("balance"),
        )

    limit_name = event.get("metered_limit_name") or event.get("limit_name")
    return RateLimitSnapshot(
        limit_id=_normalize_limit_id(limit_name) if limit_name else "codex",
        primary=primary,
        secondary=secondary,
        credits=credits,
        plan_type=event.get("plan_type"),
    )


def parse_promo_message(headers: Mapping[str, object]) -> str | None:
    message = _parse_header_str(headers, "x-codex-promo-message")
    if message is None:
        return None
    message = message.strip()
    return message or None


def parse_rate_limit_reached_type(headers: Mapping[str, object]) -> str | None:
    value = _parse_header_str(headers, "x-codex-rate-limit-reached-type")
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return RateLimitReachedType.parse(value).value
    except ValueError:
        return None


def _map_event_window(window: object) -> RateLimitWindow | None:
    if not isinstance(window, dict):
        return None
    used_percent = window.get("used_percent")
    if not isinstance(used_percent, int | float) or not math.isfinite(float(used_percent)):
        return None
    return RateLimitWindow(
        used_percent=float(used_percent),
        window_minutes=_optional_int(window.get("window_minutes")),
        resets_at=_optional_int(window.get("reset_at")),
    )


def _parse_rate_limit_window(
    headers: Mapping[str, object],
    used_percent_header: str,
    window_minutes_header: str,
    resets_at_header: str,
) -> RateLimitWindow | None:
    used_percent = _parse_header_f64(headers, used_percent_header)
    if used_percent is None:
        return None
    window_minutes = _parse_header_i64(headers, window_minutes_header)
    resets_at = _parse_header_i64(headers, resets_at_header)
    has_data = used_percent != 0.0 or (
        window_minutes is not None and window_minutes != 0
    ) or resets_at is not None
    if not has_data:
        return None
    return RateLimitWindow(
        used_percent=used_percent,
        window_minutes=window_minutes,
        resets_at=resets_at,
    )


def _parse_credits_snapshot(headers: Mapping[str, object]) -> CreditsSnapshot | None:
    has_credits = _parse_header_bool(headers, "x-codex-credits-has-credits")
    if has_credits is None:
        return None
    unlimited = _parse_header_bool(headers, "x-codex-credits-unlimited")
    if unlimited is None:
        return None
    balance = _parse_header_str(headers, "x-codex-credits-balance")
    if balance is not None:
        balance = balance.strip() or None
    return CreditsSnapshot(
        has_credits=has_credits,
        unlimited=unlimited,
        balance=balance,
    )


def _parse_header_f64(headers: Mapping[str, object], name: str) -> float | None:
    raw = _parse_header_str(headers, name)
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _parse_header_i64(headers: Mapping[str, object], name: str) -> int | None:
    raw = _parse_header_str(headers, name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_header_bool(headers: Mapping[str, object], name: str) -> bool | None:
    raw = _parse_header_str(headers, name)
    if raw is None:
        return None
    if raw.lower() == "true" or raw == "1":
        return True
    if raw.lower() == "false" or raw == "0":
        return False
    return None


def _parse_header_str(headers: Mapping[str, object], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            if isinstance(value, bytes):
                try:
                    return value.decode()
                except UnicodeDecodeError:
                    return None
            return str(value)
    return None


def _has_rate_limit_data(snapshot: RateLimitSnapshot) -> bool:
    return (
        snapshot.primary is not None
        or snapshot.secondary is not None
        or snapshot.credits is not None
    )


def _header_name_to_limit_id(header_name: str) -> str | None:
    suffix = "-primary-used-percent"
    if not header_name.endswith(suffix):
        return None
    prefix = header_name[: -len(suffix)]
    if not prefix.startswith("x-"):
        return None
    return _normalize_limit_id(prefix[2:])


def _normalize_limit_id(name: object) -> str:
    return str(name).strip().lower().replace("-", "_")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return None
