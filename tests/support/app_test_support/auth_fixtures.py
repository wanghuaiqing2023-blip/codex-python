from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass(frozen=True)
class ChatGptIdTokenClaims:
    email_value: str | None = None
    plan_type_value: str | None = None
    chatgpt_user_id_value: str | None = None
    chatgpt_account_id_value: str | None = None

    def email(self, value: str) -> "ChatGptIdTokenClaims":
        return replace(self, email_value=value)

    def plan_type(self, value: str) -> "ChatGptIdTokenClaims":
        return replace(self, plan_type_value=value)

    def chatgpt_user_id(self, value: str) -> "ChatGptIdTokenClaims":
        return replace(self, chatgpt_user_id_value=value)

    def chatgpt_account_id(self, value: str) -> "ChatGptIdTokenClaims":
        return replace(self, chatgpt_account_id_value=value)

    with_email = email
    with_plan_type = plan_type
    with_chatgpt_user_id = chatgpt_user_id
    with_chatgpt_account_id = chatgpt_account_id


@dataclass(frozen=True)
class ChatGptAuthFixture:
    access_token: str
    refresh_token_value: str = "refresh-token"
    account_id_value: str | None = None
    claims_value: ChatGptIdTokenClaims = ChatGptIdTokenClaims()
    last_refresh_value: datetime | None = None

    def refresh_token(self, value: str) -> "ChatGptAuthFixture":
        return replace(self, refresh_token_value=value)

    def account_id(self, value: str) -> "ChatGptAuthFixture":
        return replace(self, account_id_value=value)

    def plan_type(self, value: str) -> "ChatGptAuthFixture":
        return replace(self, claims_value=self.claims_value.plan_type(value))

    def chatgpt_user_id(self, value: str) -> "ChatGptAuthFixture":
        return replace(self, claims_value=self.claims_value.chatgpt_user_id(value))

    def chatgpt_account_id(self, value: str) -> "ChatGptAuthFixture":
        return replace(self, claims_value=self.claims_value.chatgpt_account_id(value))

    def email(self, value: str) -> "ChatGptAuthFixture":
        return replace(self, claims_value=self.claims_value.email(value))

    def last_refresh(self, value: datetime | None) -> "ChatGptAuthFixture":
        return replace(self, last_refresh_value=value)

    def claims(self, value: ChatGptIdTokenClaims) -> "ChatGptAuthFixture":
        return replace(self, claims_value=value)

    with_refresh_token = refresh_token
    with_account_id = account_id
    with_plan_type = plan_type
    with_chatgpt_user_id = chatgpt_user_id
    with_chatgpt_account_id = chatgpt_account_id
    with_email = email
    with_last_refresh = last_refresh
    with_claims = claims


def encode_id_token(claims: ChatGptIdTokenClaims) -> str:
    header = {"alg": "none", "typ": "JWT"}
    payload: dict[str, object] = {}
    if claims.email_value is not None:
        payload["email"] = claims.email_value
    auth_payload: dict[str, str] = {}
    if claims.plan_type_value is not None:
        auth_payload["chatgpt_plan_type"] = claims.plan_type_value
    if claims.chatgpt_user_id_value is not None:
        auth_payload["chatgpt_user_id"] = claims.chatgpt_user_id_value
    if claims.chatgpt_account_id_value is not None:
        auth_payload["chatgpt_account_id"] = claims.chatgpt_account_id_value
    if auth_payload:
        payload["https://api.openai.com/auth"] = auth_payload
    return ".".join(
        (
            _b64url(json.dumps(header, separators=(",", ":")).encode()),
            _b64url(json.dumps(payload, separators=(",", ":")).encode()),
            _b64url(b"signature"),
        )
    )


def write_chatgpt_auth(
    codex_home: Path,
    fixture: ChatGptAuthFixture,
    _credentials_store_mode: object = None,
) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    last_refresh = fixture.last_refresh_value
    if last_refresh is None:
        last_refresh = datetime.now(timezone.utc)
    auth = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": encode_id_token(fixture.claims_value),
            "access_token": fixture.access_token,
            "refresh_token": fixture.refresh_token_value,
            "account_id": fixture.account_id_value,
        },
        "last_refresh": last_refresh.isoformat().replace("+00:00", "Z"),
    }
    (codex_home / "auth.json").write_text(
        json.dumps(auth, indent=2),
        encoding="utf-8",
    )


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")
