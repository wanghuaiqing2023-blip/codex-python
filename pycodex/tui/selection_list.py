"""Semantic selection-list row helpers for the TUI port.

Rust counterpart: ``codex-rs/tui/src/selection_list.rs``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

SELECTED_MARKER = "›"
UNSELECTED_MARKER = " "
MAX_LABEL_WIDTH = 65535


@dataclass(frozen=True)
class SelectionStyle:
    """Small semantic style model for Rust ``ratatui::style::Style`` usage."""

    foreground: str | None = None
    dim: bool = False


@dataclass(frozen=True)
class SelectionSegment:
    """One renderable row segment from Rust ``RowRenderable``."""

    width: int
    text: str
    style: SelectionStyle
    wrap: bool = False
    trim: bool = False


@dataclass(frozen=True)
class SelectionOptionRow:
    """Semantic mirror of the two-cell row returned by Rust."""

    prefix: SelectionSegment
    label: SelectionSegment

    @property
    def segments(self) -> tuple[SelectionSegment, SelectionSegment]:
        return (self.prefix, self.label)

    def plain_text(self) -> str:
        return f"{self.prefix.text}{self.label.text}"


def display_width(text: str) -> int:
    """Return terminal cell width for simple TUI strings.

    This mirrors ``unicode_width::UnicodeWidthStr::width`` closely enough for the
    selected module's prefixes without introducing a third-party dependency.
    """

    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def selection_option_prefix(index: int, is_selected: bool) -> str:
    if index < 0:
        raise ValueError("selection option index must be non-negative")
    marker = SELECTED_MARKER if is_selected else UNSELECTED_MARKER
    return f"{marker} {index + 1}. "


def selection_option_style(is_selected: bool, dim: bool = False) -> SelectionStyle:
    if is_selected:
        return SelectionStyle(foreground="cyan")
    if dim:
        return SelectionStyle(dim=True)
    return SelectionStyle()


def selection_option_row(index: int, label: str, is_selected: bool) -> SelectionOptionRow:
    return selection_option_row_with_dim(index, label, is_selected, dim=False)


def selection_option_row_with_dim(
    index: int,
    label: str,
    is_selected: bool,
    dim: bool,
) -> SelectionOptionRow:
    prefix = selection_option_prefix(index, is_selected)
    style = selection_option_style(is_selected, dim)
    return SelectionOptionRow(
        prefix=SelectionSegment(
            width=display_width(prefix),
            text=prefix,
            style=style,
        ),
        label=SelectionSegment(
            width=MAX_LABEL_WIDTH,
            text=str(label),
            style=style,
            wrap=True,
            trim=False,
        ),
    )


__all__ = [
    "MAX_LABEL_WIDTH",
    "SELECTED_MARKER",
    "UNSELECTED_MARKER",
    "SelectionOptionRow",
    "SelectionSegment",
    "SelectionStyle",
    "display_width",
    "selection_option_prefix",
    "selection_option_row",
    "selection_option_row_with_dim",
    "selection_option_style",
]
