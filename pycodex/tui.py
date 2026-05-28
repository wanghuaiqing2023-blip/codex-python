"""Python port entry point for Codex TUI.

Upstream Rust implementation for the terminal UI is in ``codex-rs/tui``.
This module provides the public import shape expected by callers while keeping
execution non-interactive until the full TUI is ported.
"""

from __future__ import annotations

import os


class TUIUnavailableError(RuntimeError):
    """Backward-compatible exception class for callers that still import it."""


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


__all__ = ["run_tui", "TUIUnavailableError"]
