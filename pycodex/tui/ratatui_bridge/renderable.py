"""Renderable protocol for ratatui-style semantic objects."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .buffer import Buffer
from .layout import Rect


@runtime_checkable
class Renderable(Protocol):
    def render(self, area: Rect, buffer: Buffer) -> Any:
        """Render into the shared ratatui semantic buffer."""

    def desired_height(self, width: int) -> int:
        """Return desired height for a given width."""


__all__ = ["Renderable"]
