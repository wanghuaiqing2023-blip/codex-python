"""Action-required terminal title helpers.

Port of Rust ``codex-tui::bottom_pane::action_required_title``.  The helper
builds the title preview string shown when an action is required, omitting the
activity spinner and any caller-excluded terminal title items.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .._porting import RustTuiModule
from .title_setup import TerminalTitleItem

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::action_required_title",
    source="codex/codex-rs/tui/src/bottom_pane/action_required_title.rs",
    status="complete",
)

ACTION_REQUIRED_PREVIEW_PREFIX = "[ ! ] Action Required"


def build_action_required_title_text(
    prefix: str,
    items: Iterable[TerminalTitleItem],
    excluded_items: Iterable[TerminalTitleItem],
    value_for: Callable[[TerminalTitleItem], str | None],
) -> str:
    """Build Rust-compatible action-required title text.

    Rust starts with ``prefix``, skips ``TerminalTitleItem::Spinner`` and items
    present in ``excluded_items``, appends non-``None`` values returned by
    ``value_for``, then joins all parts with ``" | "``.
    """

    excluded = set(excluded_items)
    parts = [prefix]
    for item in items:
        if item is TerminalTitleItem.SPINNER or item in excluded:
            continue
        value = value_for(item)
        if value is not None:
            parts.append(value)
    return " | ".join(parts)


__all__ = [
    "ACTION_REQUIRED_PREVIEW_PREFIX",
    "RUST_MODULE",
    "build_action_required_title_text",
]
