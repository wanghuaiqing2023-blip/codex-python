"""Prompt argument parsing helpers.

Port of Rust ``codex-tui::bottom_pane::prompt_args``.
"""

from __future__ import annotations

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::prompt_args",
    source="codex/codex-rs/tui/src/bottom_pane/prompt_args.rs",
)


def parse_slash_name(line: str) -> tuple[str, str, int] | None:
    """Parse a first-line slash command of the form ``/name <rest>``.

    Returns ``(name, rest_after_name, rest_offset)`` when ``line`` starts with
    ``/`` and has a non-empty command name.  ``rest_offset`` mirrors Rust's
    byte index into the original UTF-8 line where the left-trimmed rest begins.
    """

    if not line.startswith("/"):
        return None

    stripped = line[1:]
    name_end_chars = len(stripped)
    for index, char in enumerate(stripped):
        if char.isspace():
            name_end_chars = index
            break

    name = stripped[:name_end_chars]
    if not name:
        return None

    rest_untrimmed = stripped[name_end_chars:]
    rest = rest_untrimmed.lstrip()
    trimmed_prefix = rest_untrimmed[: len(rest_untrimmed) - len(rest)]

    rest_start_prefix = stripped[:name_end_chars] + trimmed_prefix
    rest_offset = 1 + len(rest_start_prefix.encode("utf-8"))
    return name, rest, rest_offset


__all__ = [
    "RUST_MODULE",
    "parse_slash_name",
]
