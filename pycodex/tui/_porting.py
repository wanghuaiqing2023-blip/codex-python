"""Shared helpers for codex-tui port scaffolds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn


class TuiModuleNotPortedError(NotImplementedError):
    """Raised by TUI scaffolds whose Rust behavior has not been ported yet."""


@dataclass(frozen=True)
class RustTuiModule:
    """Mapping from a Python TUI module scaffold back to its Rust module."""

    crate: str
    module: str
    source: str
    status: str = "interface scaffold"


def not_ported(module: RustTuiModule, item: str) -> NoReturn:
    """Raise a consistent error for an unported Rust TUI item."""

    raise TuiModuleNotPortedError(
        f"{module.crate}::{module.module}.{item} is not ported yet; source: {module.source}"
    )
