"""Shared client request/stream models.

Ported from ``codex/codex-rs/core/src/client_common.rs``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.core.tools.network_approval import CancellationToken
from pycodex.protocol import BaseInstructions, Personality, ResponseItem

JsonValue = Any
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_RUST_CORE_ROOT = _WORKSPACE_ROOT / "codex" / "codex-rs" / "core"


def _include_rust_str(relative_path: str) -> str:
    return (_RUST_CORE_ROOT / relative_path).read_text(encoding="utf-8")


REVIEW_PROMPT = _include_rust_str("review_prompt.md")
REVIEW_EXIT_SUCCESS_TMPL = _include_rust_str("templates/review/exit_success.xml")
REVIEW_EXIT_INTERRUPTED_TMPL = _include_rust_str("templates/review/exit_interrupted.xml")


@dataclass
class Prompt:
    input: list[ResponseItem] = field(default_factory=list)
    tools: list[JsonValue] = field(default_factory=list)
    parallel_tool_calls: bool = False
    base_instructions: BaseInstructions = field(default_factory=BaseInstructions.default)
    personality: Personality | None = None
    output_schema: JsonValue | None = None
    output_schema_strict: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.input, tuple):
            self.input = list(self.input)
        if not isinstance(self.input, list) or not all(isinstance(item, ResponseItem) for item in self.input):
            raise TypeError("input must be a list of ResponseItem")
        if isinstance(self.tools, tuple):
            self.tools = list(self.tools)
        if not isinstance(self.tools, list):
            raise TypeError("tools must be a list")
        if not isinstance(self.parallel_tool_calls, bool):
            raise TypeError("parallel_tool_calls must be a bool")
        if not isinstance(self.base_instructions, BaseInstructions):
            raise TypeError("base_instructions must be BaseInstructions")
        if self.personality is not None and not isinstance(self.personality, Personality):
            raise TypeError("personality must be Personality or None")
        if not isinstance(self.output_schema_strict, bool):
            raise TypeError("output_schema_strict must be a bool")

    @classmethod
    def default(cls) -> "Prompt":
        return cls()

    def get_formatted_input(self) -> list[ResponseItem]:
        return list(self.input)


class ResponseStream:
    def __init__(
        self,
        rx_event: asyncio.Queue[Any] | None = None,
        consumer_dropped: CancellationToken | None = None,
    ) -> None:
        if rx_event is None:
            rx_event = asyncio.Queue()
        if not isinstance(rx_event, asyncio.Queue):
            raise TypeError("rx_event must be an asyncio.Queue")
        if consumer_dropped is None:
            consumer_dropped = CancellationToken()
        if not isinstance(consumer_dropped, CancellationToken):
            raise TypeError("consumer_dropped must be a CancellationToken")
        self.rx_event = rx_event
        self.consumer_dropped = consumer_dropped
        self._closed = False

    def __aiter__(self) -> "ResponseStream":
        return self

    async def __anext__(self) -> Any:
        item = await self.rx_event.get()
        if item is None:
            self.close()
            raise StopAsyncIteration
        return item

    async def next(self) -> Any | None:
        item = await self.rx_event.get()
        if item is None:
            self.close()
            return None
        return item

    def close(self) -> None:
        if not self._closed:
            self.consumer_dropped.cancel()
            self._closed = True

    def __del__(self) -> None:
        self.close()


__all__ = [
    "Prompt",
    "REVIEW_EXIT_INTERRUPTED_TMPL",
    "REVIEW_EXIT_SUCCESS_TMPL",
    "REVIEW_PROMPT",
    "ResponseStream",
]
