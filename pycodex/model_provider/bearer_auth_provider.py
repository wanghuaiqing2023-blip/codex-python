"""Port of Rust ``codex-model-provider::bearer_auth_provider``.

Rust source:
- ``codex/codex-rs/model-provider/src/bearer_auth_provider.rs``
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BearerAuthProvider:
    token: str | None = None
    account_id: str | None = None
    is_fedramp_account: bool = False

    @classmethod
    def new(cls, token: str) -> "BearerAuthProvider":
        return cls(token=token, account_id=None, is_fedramp_account=False)

    @classmethod
    def for_test(cls, token: str | None, account_id: str | None) -> "BearerAuthProvider":
        return cls(token=token, account_id=account_id, is_fedramp_account=False)

    def add_auth_headers(self, headers: dict[str, str]) -> None:
        if self.token is not None:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.account_id is not None:
            headers["ChatGPT-Account-ID"] = self.account_id
        if self.is_fedramp_account:
            headers["X-OpenAI-Fedramp"] = "true"

    def to_auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        self.add_auth_headers(headers)
        return headers


__all__ = [
    "BearerAuthProvider",
]
