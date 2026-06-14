"""Python port entry point for Codex TUI.

Upstream Rust implementation for the terminal UI is in ``codex-rs/tui``.
This package mirrors the Rust ``codex-tui`` module boundaries so behavior can be
ported module-by-module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any


class TUIUnavailableError(RuntimeError):
    """Backward-compatible exception class for callers that still import it."""


class ExitReason(Enum):
    """Python boundary for Rust ``codex_tui::ExitReason``."""

    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AppExitInfo:
    """Python boundary for Rust ``codex_tui::AppExitInfo``."""

    reason: ExitReason = ExitReason.UNKNOWN
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class Cli:
    """Python boundary for Rust ``codex_tui::Cli``.

    The concrete argparse mapping will be filled in from ``tui/src/cli.rs``.
    """

    raw_args: tuple[str, ...] = ()


def run_tui(*_args: object, stderr: object | None = None, **_kwargs: object) -> int:
    """Start the interactive TUI.

    The non-interactive Python port currently does not implement this path. Return
    the unimplemented command exit code used by the parser (64) after printing a
    clear diagnostic.
    """

    if stderr is None:
        import sys

        stderr = sys.stderr
    write = getattr(stderr, "write", None)
    if callable(write):
        if os.environ.get("PYCODEX_TUI_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}:
            write("pycodex: interactive TUI is disabled in this Python port.\n")
            return 0
        write("pycodex: interactive TUI is recognized but not implemented yet.\n")
    return 64


async def run_main(*_args: object, **_kwargs: object) -> AppExitInfo:
    """Python boundary for Rust ``codex_tui::run_main``."""

    raise TUIUnavailableError("pycodex: codex_tui::run_main is not implemented yet")


__all__ = [
    "AppExitInfo",
    "Cli",
    "ExitReason",
    "TUIUnavailableError",
    "run_main",
    "run_tui",
]

