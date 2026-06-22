"""Port of Rust ``codex-login::token_data``.

Rust source:
- ``codex/codex-rs/login/src/token_data.rs``
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from pycodex.protocol.auth import PlanType


class IdTokenInfoError(ValueError):
    pass


class InvalidIdTokenFormatError(IdTokenInfoError):
    def __str__(self) -> str:
        return "invalid ID token format"


@dataclass(frozen=True)
class IdTokenInfo:
    email: str | None = None
    chatgpt_plan_type: PlanType | None = None
    chatgpt_user_id: str | None = None
    chatgpt_account_id: str | None = None
    chatgpt_account_is_fedramp: bool = False
    raw_jwt: str = ""

    def get_chatgpt_plan_type(self) -> str | None:
        if self.chatgpt_plan_type is None:
            return None
        if self.chatgpt_plan_type.known is not None:
            return self.chatgpt_plan_type.known.display_name()
        return self.chatgpt_plan_type.unknown

    def get_chatgpt_plan_type_raw(self) -> str | None:
        if self.chatgpt_plan_type is None:
            return None
        if self.chatgpt_plan_type.known is not None:
            return self.chatgpt_plan_type.known.raw_value()
        return self.chatgpt_plan_type.unknown

    def is_workspace_account(self) -> bool:
        return self.chatgpt_plan_type is not None and self.chatgpt_plan_type.known is not None and self.chatgpt_plan_type.known.is_workspace_account()

    def is_fedramp_account(self) -> bool:
        return self.chatgpt_account_is_fedramp


@dataclass(frozen=True)
class TokenData:
    id_token: IdTokenInfo = field(default_factory=IdTokenInfo)
    access_token: str = ""
    refresh_token: str = ""
    account_id: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "TokenData":
        raw_id_token = _expect_str(data.get("id_token", ""))
        return cls(
            id_token=parse_chatgpt_jwt_claims(raw_id_token),
            access_token=_expect_str(data.get("access_token", "")),
            refresh_token=_expect_str(data.get("refresh_token", "")),
            account_id=_optional_str(data.get("account_id")),
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id_token": self.id_token.raw_jwt,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "account_id": self.account_id,
        }


def parse_jwt_expiration(jwt: str) -> datetime | None:
    claims = _decode_jwt_payload(jwt)
    exp = claims.get("exp")
    if exp is None:
        return None
    return datetime.fromtimestamp(int(exp), timezone.utc)


def parse_chatgpt_jwt_claims(jwt: str) -> IdTokenInfo:
    claims = _decode_jwt_payload(jwt)
    email = _optional_str(claims.get("email"))
    profile = claims.get("https://api.openai.com/profile")
    if email is None and isinstance(profile, Mapping):
        email = _optional_str(profile.get("email"))

    auth = claims.get("https://api.openai.com/auth")
    if not isinstance(auth, Mapping):
        return IdTokenInfo(email=email, raw_jwt=jwt)

    raw_plan = _optional_str(auth.get("chatgpt_plan_type"))
    return IdTokenInfo(
        email=email,
        raw_jwt=jwt,
        chatgpt_plan_type=PlanType.from_raw_value(raw_plan) if raw_plan is not None else None,
        chatgpt_user_id=_optional_str(auth.get("chatgpt_user_id")) or _optional_str(auth.get("user_id")),
        chatgpt_account_id=_optional_str(auth.get("chatgpt_account_id")),
        chatgpt_account_is_fedramp=bool(auth.get("chatgpt_account_is_fedramp", False)),
    )


def _decode_jwt_payload(jwt: str) -> dict[str, Any]:
    parts = jwt.split(".")
    if len(parts) < 3 or not parts[0] or not parts[1] or not parts[2]:
        raise InvalidIdTokenFormatError()
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    payload = base64.urlsafe_b64decode((payload_b64 + padding).encode("ascii"))
    claims = json.loads(payload.decode("utf-8"))
    if not isinstance(claims, dict):
        raise TypeError("JWT payload must decode to an object")
    return claims


def _expect_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError("expected optional string")


__all__ = [
    "IdTokenInfo",
    "IdTokenInfoError",
    "InvalidIdTokenFormatError",
    "TokenData",
    "parse_chatgpt_jwt_claims",
    "parse_jwt_expiration",
]
