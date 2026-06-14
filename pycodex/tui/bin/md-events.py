"""Python boundary for Rust ``codex-tui::bin::md-events``.

The Rust binary reads all stdin, feeds it to ``pulldown_cmark::Parser``, and
prints each parser event with Rust ``Debug`` formatting.  Python intentionally
does not fake that dependency-crate event stream with a partial Markdown parser.
Only the module-owned stdin error boundary is represented here; successful
parsing remains an explicit blocked runtime/dependency boundary.
"""

from __future__ import annotations

from typing import Any, TextIO

from .._porting import RustTuiModule, not_ported


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bin::md-events",
    source="codex/codex-rs/tui/src/bin/md-events.rs",
    status="blocked",
    notes="Successful event output depends on pulldown-cmark Parser Debug formatting.",
)


def format_stdin_read_error(error: Any) -> str:
    """Rust stderr text for a failed ``read_to_string`` call."""

    return f"failed to read stdin: {error}"


def markdown_events_debug(input_text: str) -> list[str]:
    """Return Rust pulldown-cmark Debug event lines.

    Blocked deliberately: implementing this without pulldown-cmark would create
    a silent, divergent Markdown parser.  Callers should treat this as a
    dependency boundary until a faithful event source is available.
    """

    raise not_ported("bin::md-events markdown parsing requires pulldown-cmark Parser Debug event parity")


def main(stdin: TextIO | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """Semantic CLI boundary for Rust ``main``.

    Read failures are handled exactly like Rust.  Successful parsing is blocked
    on pulldown-cmark event parity and raises an explicit ``not_ported`` error
    instead of printing approximate Markdown events.
    """

    import sys

    stdin = stdin or sys.stdin
    stderr = stderr or sys.stderr
    try:
        input_text = stdin.read()
    except Exception as err:
        stderr.write(format_stdin_read_error(err) + "\n")
        return 1

    for event in markdown_events_debug(input_text):
        (stdout or sys.stdout).write(event + "\n")
    return 0


__all__ = [
    "RUST_MODULE",
    "format_stdin_read_error",
    "main",
    "markdown_events_debug",
]
