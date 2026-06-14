"""Semantic port of codex-rs/tui/src/chatwidget/hooks.rs.

Rust implements these methods on ``ChatWidget``.  Python keeps them as
widget-like helpers so this module owns only the chat-surface hooks browser
contract: fetch request, cwd guard, success/error handling, and view opening.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .._porting import RustTuiModule
from ..bottom_pane.hooks_browser_view import HooksBrowserView
from ..hooks_rpc import hooks_list_entry_for_cwd


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::hooks",
    source="codex/codex-rs/tui/src/chatwidget/hooks.rs",
)


def add_hooks_output(widget: Any) -> None:
    """Request hooks for the widget's current cwd."""

    cwd = Path(getattr(getattr(widget, "config"), "cwd"))
    _send_event(widget, {"type": "FetchHooksList", "cwd": cwd})


def on_hooks_loaded(widget: Any, cwd: str | Path, result: Any) -> None:
    """Handle a hooks-list fetch result for ``cwd``.

    Results for stale cwd values are ignored, matching Rust's early return.
    Errors are accepted as ``Exception`` or string-like values.  Successful
    values are converted through ``hooks_list_entry_for_cwd`` and opened in the
    hooks browser.
    """

    current_cwd = Path(getattr(getattr(widget, "config"), "cwd"))
    loaded_cwd = Path(cwd)
    if current_cwd != loaded_cwd:
        return

    if isinstance(result, Exception):
        widget.add_error_message(f"Failed to load hooks: {result}")
        return
    if isinstance(result, tuple) and len(result) == 2 and result[0] == "Err":
        widget.add_error_message(f"Failed to load hooks: {result[1]}")
        return

    response = result[1] if isinstance(result, tuple) and len(result) == 2 and result[0] == "Ok" else result
    open_hooks_browser(widget, hooks_list_entry_for_cwd(response, loaded_cwd))


def open_hooks_browser(widget: Any, entry: Any) -> None:
    """Open a ``HooksBrowserView`` and request a redraw."""

    bottom_pane = getattr(widget, "bottom_pane")
    list_keymap = bottom_pane.list_keymap() if hasattr(bottom_pane, "list_keymap") else None
    view = HooksBrowserView.from_entry(entry, getattr(widget, "app_event_tx", None), list_keymap)
    bottom_pane.show_view(view)
    widget.request_redraw()


def _send_event(widget: Any, event: dict[str, Any]) -> None:
    sender = getattr(widget, "app_event_tx")
    if hasattr(sender, "send"):
        sender.send(event)
    elif callable(sender):
        sender(event)
    else:
        raise AttributeError("widget.app_event_tx must be callable or provide send")


class HooksMixin:
    """Mixin shape matching the Rust ``impl ChatWidget`` methods."""

    def add_hooks_output(self) -> None:
        add_hooks_output(self)

    def on_hooks_loaded(self, cwd: str | Path, result: Any) -> None:
        on_hooks_loaded(self, cwd, result)

    def open_hooks_browser(self, entry: Any) -> None:
        open_hooks_browser(self, entry)


__all__ = [
    "HooksMixin",
    "RUST_MODULE",
    "add_hooks_output",
    "on_hooks_loaded",
    "open_hooks_browser",
]
