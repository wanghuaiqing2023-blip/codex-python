"""Terminal bottom-pane footprint for the hybrid terminal backend.

Rust bottom-pane widgets report desired heights and the custom terminal draws
an inline viewport. Python keeps that same boundary as a compact row footprint
so resize/reflow and history insertion can reason about the live pane without
owning frame/buffer rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import os

from ..custom_terminal import LiveViewportClearRequest


IDLE_BOTTOM_PANE_ROWS = 4
STATUS_BOTTOM_PANE_ROWS = 6


class TerminalLiveStatusFootprintProtocol(Protocol):
    """Live-status shape consumed by bottom-pane footprint projection.

    Rust owners: ``codex-tui::chatwidget::status_surfaces`` owns whether live
    status should reserve terminal rows, while ``bottom_pane`` consumes that
    boolean as compact footprint input. The hybrid terminal adapter should not
    guess this shape with reflection.
    """

    @property
    def footprint_active(self) -> bool: ...


@dataclass(frozen=True)
class TerminalBottomPaneFootprint:
    """Rows reserved by the live bottom pane.

    Rust ``bottom_pane`` computes desired heights from the active view and
    composer/footer state. The real-terminal adapter keeps the same boundary
    by reporting a compact footprint value to ``app::resize_reflow``.
    """

    live_status_active: bool = False
    popup_height: int = 0
    active_tail_height: int = 0
    composer_height: int = 1

    @classmethod
    def from_surface(
        cls,
        live_status: TerminalLiveStatusFootprintProtocol,
        popup_height: int = 0,
        active_tail_height: int = 0,
        composer_height: int = 1,
    ) -> "TerminalBottomPaneFootprint":
        return cls(
            live_status_active=bool(live_status.footprint_active),
            popup_height=max(0, int(popup_height)),
            active_tail_height=max(0, int(active_tail_height)),
            composer_height=max(1, int(composer_height)),
        )

    def rows_for_size(self, size: os.terminal_size) -> list[int]:
        return bottom_pane_rows_for_size(
            size,
            live_status_active=self.live_status_active,
            popup_height=self.popup_height,
            active_tail_height=self.active_tail_height,
            composer_height=self.composer_height,
        )

    def height_for_size(self, size: os.terminal_size) -> int:
        return len(self.rows_for_size(size))


@dataclass(frozen=True)
class TerminalBottomPaneLayoutRows:
    """Concrete bottom-pane row assignment for terminal frame rendering.

    Rust owners: ``codex-tui::bottom_pane`` and
    ``bottom_pane::chat_composer`` own desired-height/layout decisions. The
    Python hybrid frame renderer consumes this value instead of deriving
    status/composer/popup/footer row positions locally.
    """

    clear_rows: tuple[int, ...]
    live_status_row: int | None
    composer_rows: tuple[int, ...]
    popup_rows: tuple[int, ...]
    footer_row: int
    active_tail_rows: tuple[int, ...] = ()

    @property
    def composer_row(self) -> int:
        return self.composer_rows[-1]


def bottom_pane_rows_for_size(
    size: os.terminal_size,
    *,
    live_status_active: bool,
    popup_height: int = 0,
    active_tail_height: int = 0,
    composer_height: int = 1,
) -> list[int]:
    rows = size.lines
    height = bottom_pane_height(
        live_status_active=live_status_active,
        popup_height=popup_height,
        active_tail_height=active_tail_height,
        composer_height=composer_height,
    )
    if height != IDLE_BOTTOM_PANE_ROWS:
        return [max(1, rows - offset) for offset in range(height - 1, -1, -1)]
    return [
        max(1, rows - 3),
        max(1, rows - 2),
        max(1, rows - 1),
        max(1, rows),
    ]


def status_row(size: os.terminal_size, *, live_status_active: bool) -> int | None:
    """Return the live-status row reserved by the terminal bottom pane."""

    if not live_status_active:
        return None
    return max(1, size.lines - 5)


def composer_row(size: os.terminal_size) -> int:
    """Return the primary composer row reserved by the terminal bottom pane."""

    return max(1, size.lines - 2)


def footer_row(size: os.terminal_size) -> int:
    """Return the passive footer row reserved by the terminal bottom pane."""

    return max(1, size.lines)


def terminal_bottom_pane_layout_rows(
    size: os.terminal_size,
    *,
    live_status_active: bool,
    popup_height: int = 0,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    active_tail_height: int = 0,
    clear_active_tail_height: int = 0,
    composer_height: int = 1,
    clear_composer_height: int = 1,
) -> TerminalBottomPaneLayoutRows:
    """Return terminal row assignments for the bottom-pane frame.

    The clear footprint can be larger than the current visible footprint when
    resize/reflow asks a render pass to erase a previously taller popup or
    live-status area.  The visible row assignments still follow the current
    bottom-pane state.
    """

    clear_rows = tuple(
        bottom_pane_rows_for_size(
            size,
            live_status_active=live_status_active or clear_live_status_active,
            popup_height=max(int(popup_height), int(clear_popup_height)),
            active_tail_height=max(int(active_tail_height), int(clear_active_tail_height)),
            composer_height=max(int(composer_height), int(clear_composer_height)),
        )
    )
    base_rows = bottom_pane_rows_for_size(
        size,
        live_status_active=live_status_active,
        popup_height=popup_height,
        composer_height=composer_height,
    )
    active_tail_rows = tuple(clear_rows[: max(0, int(active_tail_height))])
    if popup_height:
        rows = base_rows
        cursor = 0
        live_status = None
        if live_status_active:
            live_status = rows[cursor]
            cursor += 1
        composer_rows = tuple(rows[cursor : cursor + max(1, int(composer_height))])
        cursor += len(composer_rows)
        return TerminalBottomPaneLayoutRows(
            clear_rows=clear_rows,
            live_status_row=live_status,
            composer_rows=composer_rows,
            popup_rows=tuple(rows[cursor:-1])[: int(popup_height)],
            footer_row=rows[-1],
            active_tail_rows=active_tail_rows,
        )

    composer_end = len(base_rows) - 2
    composer_start = max(0, composer_end - max(1, int(composer_height)))
    return TerminalBottomPaneLayoutRows(
        clear_rows=clear_rows,
        live_status_row=status_row(size, live_status_active=live_status_active),
        composer_rows=tuple(base_rows[composer_start:composer_end]),
        popup_rows=(),
        footer_row=footer_row(size),
        active_tail_rows=active_tail_rows,
    )


def bottom_pane_height(
    *,
    live_status_active: bool,
    popup_height: int = 0,
    active_tail_height: int = 0,
    composer_height: int = 1,
) -> int:
    if popup_height:
        base = max(
            STATUS_BOTTOM_PANE_ROWS if live_status_active else IDLE_BOTTOM_PANE_ROWS,
            (1 if live_status_active else 0) + 1 + int(popup_height) + 1,
        )
    else:
        base = STATUS_BOTTOM_PANE_ROWS if live_status_active else IDLE_BOTTOM_PANE_ROWS
    return base + max(0, int(active_tail_height)) + max(0, int(composer_height) - 1)


def terminal_bottom_pane_clear_request(
    size: os.terminal_size,
    *,
    live_status_active: bool,
    popup_height: int = 0,
) -> LiveViewportClearRequest:
    """Project a bottom-pane footprint into a live-viewport clear request.

    Rust owners: ``codex-tui::bottom_pane`` owns the bottom-pane footprint and
    ``codex-tui::custom_terminal`` consumes the generic clear request. The
    terminal surface should bridge this request without computing rows itself.
    """

    return LiveViewportClearRequest.new(
        bottom_pane_rows_for_size(
            size,
            live_status_active=live_status_active,
            popup_height=popup_height,
        )
    )


__all__ = [
    "IDLE_BOTTOM_PANE_ROWS",
    "STATUS_BOTTOM_PANE_ROWS",
    "TerminalBottomPaneFootprint",
    "TerminalBottomPaneLayoutRows",
    "TerminalLiveStatusFootprintProtocol",
    "bottom_pane_height",
    "bottom_pane_rows_for_size",
    "composer_row",
    "footer_row",
    "status_row",
    "terminal_bottom_pane_layout_rows",
    "terminal_bottom_pane_clear_request",
]
