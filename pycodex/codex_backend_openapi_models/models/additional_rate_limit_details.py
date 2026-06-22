"""Port of Rust ``codex-backend-openapi-models::models::additional_rate_limit_details``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/additional_rate_limit_details.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class Unset:
    """Sentinel for omitted serde ``Option`` fields."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET = Unset()


@dataclass(frozen=True)
class AdditionalRateLimitDetails:
    limit_name: str = ""
    metered_feature: str = ""
    rate_limit: Any | None | Unset = UNSET

    @classmethod
    def new(cls, limit_name: str, metered_feature: str) -> "AdditionalRateLimitDetails":
        return cls(limit_name=limit_name, metered_feature=metered_feature, rate_limit=UNSET)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AdditionalRateLimitDetails":
        return cls(
            limit_name=_expect_str(value.get("limit_name", "")),
            metered_feature=_expect_str(value.get("metered_feature", "")),
            rate_limit=_decode_double_option(value, "rate_limit"),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "limit_name": self.limit_name,
            "metered_feature": self.metered_feature,
        }
        if not isinstance(self.rate_limit, Unset):
            result["rate_limit"] = _to_json_value(self.rate_limit)
        return result


def _decode_double_option(value: Mapping[str, Any], key: str) -> Any | None | Unset:
    if key not in value:
        return UNSET
    return value[key]


def _to_json_value(value: Any) -> Any:
    if hasattr(value, "to_json_dict"):
        return value.to_json_dict()
    return value


def _expect_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string")


__all__ = [
    "AdditionalRateLimitDetails",
    "UNSET",
    "Unset",
]
