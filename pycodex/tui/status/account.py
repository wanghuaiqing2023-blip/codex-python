"""Semantic port of codex-rs/tui/src/status/account.rs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="status::account",
    source="codex/codex-rs/tui/src/status/account.rs",
)


@dataclass(frozen=True)
class StatusAccountDisplay:
    """Python representation of Rust ``StatusAccountDisplay``.

    Rust variants:
    - ``ChatGpt { email: Option<String>, plan: Option<String> }``
    - ``ApiKey``
    """

    kind: str
    email: str | None = None
    plan: str | None = None

    @classmethod
    def chat_gpt(
        cls,
        email: str | None = None,
        plan: str | None = None,
    ) -> "StatusAccountDisplay":
        return cls("ChatGpt", email=email, plan=plan)

    @classmethod
    def api_key(cls) -> "StatusAccountDisplay":
        return cls("ApiKey")

    @property
    def is_chat_gpt(self) -> bool:
        return self.kind == "ChatGpt"

    @property
    def is_api_key(self) -> bool:
        return self.kind == "ApiKey"

    def to_wire(self) -> dict[str, Any] | str:
        if self.is_chat_gpt:
            return {"ChatGpt": {"email": self.email, "plan": self.plan}}
        if self.is_api_key:
            return "ApiKey"
        raise ValueError(f"unknown StatusAccountDisplay variant: {self.kind}")

    @classmethod
    def from_wire(cls, value: Any) -> "StatusAccountDisplay":
        if isinstance(value, StatusAccountDisplay):
            return value
        if value == "ApiKey" or value == {"ApiKey": None}:
            return cls.api_key()
        if isinstance(value, dict) and "ChatGpt" in value:
            payload = value["ChatGpt"] or {}
            return cls.chat_gpt(email=payload.get("email"), plan=payload.get("plan"))
        raise ValueError(f"unsupported StatusAccountDisplay wire value: {value!r}")


__all__ = [
    "RUST_MODULE",
    "StatusAccountDisplay",
]
