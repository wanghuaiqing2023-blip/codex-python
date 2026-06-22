"""Port of Rust ``codex-backend-openapi-models::models::rate_limit_window_snapshot``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_window_snapshot.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RateLimitWindowSnapshot:
    used_percent: int = 0
    limit_window_seconds: int = 0
    reset_after_seconds: int = 0
    reset_at: int = 0

    @classmethod
    def new(
        cls,
        used_percent: int,
        limit_window_seconds: int,
        reset_after_seconds: int,
        reset_at: int,
    ) -> "RateLimitWindowSnapshot":
        return cls(
            used_percent=used_percent,
            limit_window_seconds=limit_window_seconds,
            reset_after_seconds=reset_after_seconds,
            reset_at=reset_at,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RateLimitWindowSnapshot":
        return cls(
            used_percent=_expect_int(value.get("used_percent", 0)),
            limit_window_seconds=_expect_int(value.get("limit_window_seconds", 0)),
            reset_after_seconds=_expect_int(value.get("reset_after_seconds", 0)),
            reset_at=_expect_int(value.get("reset_at", 0)),
        )

    def to_json_dict(self) -> dict[str, int]:
        return {
            "used_percent": self.used_percent,
            "limit_window_seconds": self.limit_window_seconds,
            "reset_after_seconds": self.reset_after_seconds,
            "reset_at": self.reset_at,
        }


def _expect_int(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError("expected integer")
    if isinstance(value, int):
        return value
    raise TypeError("expected integer")


__all__ = ["RateLimitWindowSnapshot"]
