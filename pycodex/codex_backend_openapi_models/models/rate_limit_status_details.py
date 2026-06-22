"""Port of Rust ``codex-backend-openapi-models::models::rate_limit_status_details``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_details.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .additional_rate_limit_details import UNSET, Unset
from .rate_limit_window_snapshot import RateLimitWindowSnapshot


@dataclass(frozen=True)
class RateLimitStatusDetails:
    allowed: bool = False
    limit_reached: bool = False
    primary_window: RateLimitWindowSnapshot | None | Unset = UNSET
    secondary_window: RateLimitWindowSnapshot | None | Unset = UNSET

    @classmethod
    def new(cls, allowed: bool, limit_reached: bool) -> "RateLimitStatusDetails":
        return cls(allowed=allowed, limit_reached=limit_reached)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RateLimitStatusDetails":
        return cls(
            allowed=_expect_bool(value.get("allowed", False)),
            limit_reached=_expect_bool(value.get("limit_reached", False)),
            primary_window=_decode_window_double_option(value, "primary_window"),
            secondary_window=_decode_window_double_option(value, "secondary_window"),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "allowed": self.allowed,
            "limit_reached": self.limit_reached,
        }
        if not isinstance(self.primary_window, Unset):
            result["primary_window"] = _window_to_json_value(self.primary_window)
        if not isinstance(self.secondary_window, Unset):
            result["secondary_window"] = _window_to_json_value(self.secondary_window)
        return result


def _decode_window_double_option(value: Mapping[str, Any], key: str) -> RateLimitWindowSnapshot | None | Unset:
    if key not in value:
        return UNSET
    raw = value[key]
    if raw is None or isinstance(raw, RateLimitWindowSnapshot):
        return raw
    if isinstance(raw, Mapping):
        return RateLimitWindowSnapshot.from_mapping(raw)
    raise TypeError("expected rate limit window object or null")


def _window_to_json_value(value: RateLimitWindowSnapshot | None) -> dict[str, int] | None:
    if value is None:
        return None
    return value.to_json_dict()


def _expect_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise TypeError("expected bool")


__all__ = ["RateLimitStatusDetails"]
