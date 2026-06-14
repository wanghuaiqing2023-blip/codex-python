"""Status-surface pure helpers for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/status_surfaces.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable, TypeVar

from .._porting import RustTuiModule
from ..bottom_pane.status_line_setup import StatusLineItem
from ..bottom_pane.title_setup import TerminalTitleItem
from ..status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay
from .rate_limits import get_limits_duration

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::status_surfaces",
    source="codex/codex-rs/tui/src/chatwidget/status_surfaces.rs",
)

DEFAULT_STATUS_LINE_ITEMS = ("model-with-reasoning", "current-dir")
DEFAULT_TERMINAL_TITLE_ITEMS = ("activity", "project-name")

TERMINAL_TITLE_SPINNER_FRAMES = ("⠁", "⠂", "⠄", "⡀", "⢀", "⠠", "⠐", "⠈", "⠐", "⠠")
TERMINAL_TITLE_SPINNER_INTERVAL = timedelta(milliseconds=100)
TERMINAL_TITLE_ACTION_REQUIRED_INTERVAL = timedelta(seconds=1)
TERMINAL_TITLE_ACTION_REQUIRED_PREFIX = "[ ! ] Action Required"
TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN = "[ . ] Action Required"

T = TypeVar("T")


@dataclass(frozen=True)
class StatusSurfaceSelections:
    """Parsed status-surface configuration for one refresh pass."""

    status_line_items: tuple[StatusLineItem, ...] = ()
    invalid_status_line_items: tuple[str, ...] = ()
    terminal_title_items: tuple[TerminalTitleItem, ...] = ()
    invalid_terminal_title_items: tuple[str, ...] = ()

    def uses_git_branch(self) -> bool:
        return (
            StatusLineItem.GIT_BRANCH in self.status_line_items
            or TerminalTitleItem.GIT_BRANCH in self.terminal_title_items
        )

    def uses_git_summary(self) -> bool:
        return (
            StatusLineItem.PULL_REQUEST_NUMBER in self.status_line_items
            or StatusLineItem.BRANCH_CHANGES in self.status_line_items
        )


@dataclass(frozen=True)
class CachedProjectRootName:
    cwd: Path
    root_name: str | None


def parse_status_line_items_with_invalids(ids: Iterable[Any]) -> tuple[list[StatusLineItem], list[str]]:
    return parse_items_with_invalids(ids, StatusLineItem.parse)


def parse_terminal_title_items_with_invalids(ids: Iterable[Any]) -> tuple[list[TerminalTitleItem], list[str]]:
    return parse_items_with_invalids(ids, TerminalTitleItem.from_id)


def status_surface_selections(
    status_line_ids: Iterable[Any] | None = None,
    terminal_title_ids: Iterable[Any] | None = None,
) -> StatusSurfaceSelections:
    status_items, invalid_status = parse_status_line_items_with_invalids(
        DEFAULT_STATUS_LINE_ITEMS if status_line_ids is None else status_line_ids
    )
    title_items, invalid_title = parse_terminal_title_items_with_invalids(
        DEFAULT_TERMINAL_TITLE_ITEMS if terminal_title_ids is None else terminal_title_ids
    )
    return StatusSurfaceSelections(
        status_line_items=tuple(status_items),
        invalid_status_line_items=tuple(invalid_status),
        terminal_title_items=tuple(title_items),
        invalid_terminal_title_items=tuple(invalid_title),
    )


def five_hour_status_window(
    snapshot: RateLimitSnapshotDisplay,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    return (
        find_primary_codex_window(snapshot, "5h")
        or secondary_window_with_label_when_weekly_is_available(snapshot, "5h")
        or non_weekly_primary_window(snapshot)
        or non_weekly_secondary_window_when_primary_is_weekly(snapshot)
    )


def weekly_status_window(
    snapshot: RateLimitSnapshotDisplay,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    return find_codex_window(snapshot, "weekly") or (
        (snapshot.secondary, True) if snapshot.secondary is not None else None
    )


def find_codex_window(
    snapshot: RateLimitSnapshotDisplay,
    label: str,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if snapshot.primary is not None and matches_window_label(snapshot.primary, label):
        return (snapshot.primary, False)
    if snapshot.secondary is not None and matches_window_label(snapshot.secondary, label):
        return (snapshot.secondary, True)
    return None


def find_primary_codex_window(
    snapshot: RateLimitSnapshotDisplay,
    label: str,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if snapshot.primary is not None and matches_window_label(snapshot.primary, label):
        return (snapshot.primary, False)
    return None


def secondary_window_with_label_when_weekly_is_available(
    snapshot: RateLimitSnapshotDisplay,
    label: str,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if find_codex_window(snapshot, "weekly") is None:
        return None
    if snapshot.secondary is not None and matches_window_label(snapshot.secondary, label):
        return (snapshot.secondary, True)
    return None


def non_weekly_primary_window(
    snapshot: RateLimitSnapshotDisplay,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if snapshot.primary is None or matches_window_label(snapshot.primary, "weekly"):
        return None
    return (snapshot.primary, False)


def non_weekly_secondary_window_when_primary_is_weekly(
    snapshot: RateLimitSnapshotDisplay,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if snapshot.primary is None or not matches_window_label(snapshot.primary, "weekly"):
        return None
    if snapshot.secondary is None or matches_window_label(snapshot.secondary, "weekly"):
        return None
    return (snapshot.secondary, True)


def matches_window_label(window: RateLimitWindowDisplay, label: str) -> bool:
    minutes = window.window_minutes
    if minutes is None:
        return False
    return get_limits_duration(minutes) == label


def truncate_terminal_title_part(value: str, max_chars: int) -> str:
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if max_chars == 0:
        return ""
    graphemes = _graphemes(value)
    head = "".join(graphemes[:max_chars])
    if len(graphemes) <= max_chars or max_chars <= 3:
        return head
    return "".join(graphemes[: max_chars - 3]) + "..."


def terminal_title_spinner_frame_at(elapsed: timedelta) -> str:
    frame_index = int(elapsed.total_seconds() * 1000) // int(
        TERMINAL_TITLE_SPINNER_INTERVAL.total_seconds() * 1000
    )
    return TERMINAL_TITLE_SPINNER_FRAMES[frame_index % len(TERMINAL_TITLE_SPINNER_FRAMES)]


def action_required_terminal_title_prefix_at(
    elapsed: timedelta,
    animations: bool = True,
) -> str:
    if not animations:
        return TERMINAL_TITLE_ACTION_REQUIRED_PREFIX
    phase = int(elapsed.total_seconds()) % 2
    return (
        TERMINAL_TITLE_ACTION_REQUIRED_PREFIX
        if phase == 0
        else TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN
    )


def parse_items_with_invalids(
    ids: Iterable[Any],
    parser: Any | None = None,
) -> tuple[list[Any], list[str]]:
    parse_one = parser if parser is not None else _parse_status_or_title_item
    invalid: list[str] = []
    invalid_seen: set[str] = set()
    items: list[Any] = []
    for item_id in ids:
        text = str(item_id)
        try:
            items.append(parse_one(item_id))
        except Exception:
            if text not in invalid_seen:
                invalid_seen.add(text)
                invalid.append(f'"{text}"')
    return items, invalid


def permissions_display(*_: Any, **__: Any) -> str:
    raise NotImplementedError(
        "permissions_display depends on Rust permission-profile summarization and is outside this pure-helper slice"
    )


def approval_mode_display(*_: Any, **__: Any) -> str:
    raise NotImplementedError(
        "approval_mode_display depends on full Config permission policy state and is outside this pure-helper slice"
    )


def _parse_status_or_title_item(value: Any) -> Any:
    try:
        return StatusLineItem.parse(value)
    except ValueError:
        return TerminalTitleItem.from_id(value)


def _graphemes(text: str) -> list[str]:
    clusters: list[str] = []
    for ch in text:
        if clusters and _is_combining_mark(ch):
            clusters[-1] += ch
        else:
            clusters.append(ch)
    return clusters


def _is_combining_mark(ch: str) -> bool:
    import unicodedata

    return bool(unicodedata.combining(ch))


__all__ = [
    "CachedProjectRootName",
    "DEFAULT_STATUS_LINE_ITEMS",
    "DEFAULT_TERMINAL_TITLE_ITEMS",
    "RUST_MODULE",
    "StatusSurfaceSelections",
    "TERMINAL_TITLE_ACTION_REQUIRED_INTERVAL",
    "TERMINAL_TITLE_ACTION_REQUIRED_PREFIX",
    "TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN",
    "TERMINAL_TITLE_SPINNER_FRAMES",
    "TERMINAL_TITLE_SPINNER_INTERVAL",
    "action_required_terminal_title_prefix_at",
    "approval_mode_display",
    "find_codex_window",
    "find_primary_codex_window",
    "five_hour_status_window",
    "matches_window_label",
    "non_weekly_primary_window",
    "non_weekly_secondary_window_when_primary_is_weekly",
    "parse_items_with_invalids",
    "parse_status_line_items_with_invalids",
    "parse_terminal_title_items_with_invalids",
    "permissions_display",
    "secondary_window_with_label_when_weekly_is_available",
    "status_surface_selections",
    "terminal_title_spinner_frame_at",
    "truncate_terminal_title_part",
    "weekly_status_window",
]
