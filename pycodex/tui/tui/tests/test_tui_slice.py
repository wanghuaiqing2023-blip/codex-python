"""Parity tests for pure Rust ``codex-tui::tui`` behavior slices.

Rust source: ``codex/codex-rs/tui/src/tui.rs``.
"""

from __future__ import annotations

from io import StringIO

import pytest

from pycodex.tui.tui import (
    DisableAlternateScroll,
    EnableAlternateScroll,
    NotificationCondition,
    should_emit_notification,
)


def test_notification_condition_matches_rust_focus_rules() -> None:
    assert should_emit_notification(NotificationCondition.UNFOCUSED, terminal_focused=True) is False
    assert should_emit_notification(NotificationCondition.UNFOCUSED, terminal_focused=False) is True
    assert should_emit_notification(NotificationCondition.ALWAYS, terminal_focused=True) is True
    assert should_emit_notification("always", terminal_focused=False) is True


def test_alternate_scroll_commands_write_rust_ansi_sequences() -> None:
    out = StringIO()
    EnableAlternateScroll().write_ansi(out)
    assert out.getvalue() == "\x1b[?1007h"

    out = StringIO()
    DisableAlternateScroll().write_ansi(out)
    assert out.getvalue() == "\x1b[?1007l"


def test_alternate_scroll_commands_reject_winapi_like_rust() -> None:
    assert EnableAlternateScroll().is_ansi_code_supported() is True
    assert DisableAlternateScroll().is_ansi_code_supported() is True
    with pytest.raises(OSError):
        EnableAlternateScroll().execute_winapi()
    with pytest.raises(OSError):
        DisableAlternateScroll().execute_winapi()
