"""In-process MCP transport contract."""

from __future__ import annotations

from typing import Any, Protocol


class InProcessTransportFactory(Protocol):
    async def open(self) -> Any: ...


__all__ = ["InProcessTransportFactory"]
