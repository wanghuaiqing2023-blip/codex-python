"""Port of Rust ``codex-backend-openapi-models::models::credit_status_details``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/credit_status_details.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .additional_rate_limit_details import UNSET, Unset


@dataclass(frozen=True)
class CreditStatusDetails:
    has_credits: bool = False
    unlimited: bool = False
    balance: str | None | Unset = UNSET
    approx_local_messages: tuple[Any, ...] | None | Unset = UNSET
    approx_cloud_messages: tuple[Any, ...] | None | Unset = UNSET

    @classmethod
    def new(cls, has_credits: bool, unlimited: bool) -> "CreditStatusDetails":
        return cls(has_credits=has_credits, unlimited=unlimited)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CreditStatusDetails":
        return cls(
            has_credits=_expect_bool(value.get("has_credits", False)),
            unlimited=_expect_bool(value.get("unlimited", False)),
            balance=_decode_string_double_option(value, "balance"),
            approx_local_messages=_decode_json_array_double_option(value, "approx_local_messages"),
            approx_cloud_messages=_decode_json_array_double_option(value, "approx_cloud_messages"),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "has_credits": self.has_credits,
            "unlimited": self.unlimited,
        }
        if not isinstance(self.balance, Unset):
            result["balance"] = self.balance
        if not isinstance(self.approx_local_messages, Unset):
            result["approx_local_messages"] = _messages_to_json(self.approx_local_messages)
        if not isinstance(self.approx_cloud_messages, Unset):
            result["approx_cloud_messages"] = _messages_to_json(self.approx_cloud_messages)
        return result


def _decode_string_double_option(value: Mapping[str, Any], key: str) -> str | None | Unset:
    raw = _decode_double_option(value, key)
    if raw is None or isinstance(raw, Unset):
        return raw
    if isinstance(raw, str):
        return raw
    raise TypeError("expected string or null")


def _decode_json_array_double_option(value: Mapping[str, Any], key: str) -> tuple[Any, ...] | None | Unset:
    raw = _decode_double_option(value, key)
    if raw is None or isinstance(raw, Unset):
        return raw
    if isinstance(raw, list):
        return tuple(raw)
    raise TypeError("expected array or null")


def _decode_double_option(value: Mapping[str, Any], key: str) -> Any | None | Unset:
    if key not in value:
        return UNSET
    return value[key]


def _messages_to_json(value: tuple[Any, ...] | None) -> list[Any] | None:
    if value is None:
        return None
    return list(value)


def _expect_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise TypeError("expected bool")


__all__ = ["CreditStatusDetails"]
