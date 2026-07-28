"""Encrypted tool output from Rust ``web-search/src/output.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.core.tools.context import function_tool_response
from pycodex.protocol import FunctionCallOutputContentItem


@dataclass(frozen=True)
class EncryptedSearchOutput:
    encrypted_output: str

    @classmethod
    def new(cls, encrypted_output: str) -> "EncryptedSearchOutput":
        return cls(encrypted_output)

    def log_preview(self) -> str:
        return "[encrypted standalone web search output]"

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: Any) -> Any:
        return function_tool_response(
            call_id,
            payload,
            (FunctionCallOutputContentItem.encrypted(self.encrypted_output),),
            None,
        )

    def post_tool_use_response(self, _call_id: str, _payload: Any) -> None:
        return None


__all__ = ["EncryptedSearchOutput"]
