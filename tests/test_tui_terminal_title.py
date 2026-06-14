"""Parity tests for Rust ``codex-tui::terminal_title``.

Rust source: ``codex/codex-rs/tui/src/terminal_title.rs``.
"""

import io

from pycodex.tui.terminal_title import (
    MAX_TERMINAL_TITLE_CHARS,
    SetTerminalTitleResult,
    SetWindowTitle,
    clear_terminal_title,
    sanitize_terminal_title,
    set_terminal_title,
)


class FakeTerminal(io.StringIO):
    def __init__(self, terminal: bool) -> None:
        super().__init__()
        self._terminal = terminal

    def isatty(self) -> bool:
        return self._terminal


def test_sanitizes_terminal_title() -> None:
    sanitized = sanitize_terminal_title("  Project\t|\nWorking\x1b\x07\u009d\u009c |  Thread  ")
    assert sanitized == "Project | Working | Thread"


def test_strips_invisible_format_chars_from_terminal_title() -> None:
    sanitized = sanitize_terminal_title(
        "Pro\u202ej\u2066e\u200fc\u061ct\u200b \ufeffT\u2060itle"
    )
    assert sanitized == "Project Title"


def test_truncates_terminal_title() -> None:
    sanitized = sanitize_terminal_title("a" * (MAX_TERMINAL_TITLE_CHARS + 10))
    assert len(sanitized) == MAX_TERMINAL_TITLE_CHARS


def test_truncation_prefers_visible_char_over_pending_space() -> None:
    sanitized = sanitize_terminal_title(f"{'a' * (MAX_TERMINAL_TITLE_CHARS - 1)} b")
    assert len(sanitized) == MAX_TERMINAL_TITLE_CHARS
    assert sanitized[-1] == "b"


def test_writes_osc_title_with_bel_terminator() -> None:
    assert SetWindowTitle("hello").write_ansi() == "\x1b]0;hello\x07"


def test_set_terminal_title_result_and_clear_terminal_title() -> None:
    non_terminal = FakeTerminal(False)
    assert set_terminal_title("hello", stdout=non_terminal) is SetTerminalTitleResult.Applied
    assert non_terminal.getvalue() == ""

    terminal = FakeTerminal(True)
    assert set_terminal_title("  hello  ", stdout=terminal) is SetTerminalTitleResult.Applied
    assert terminal.getvalue() == "\x1b]0;hello\x07"

    empty_terminal = FakeTerminal(True)
    assert set_terminal_title("\x1b\u202e", stdout=empty_terminal) is SetTerminalTitleResult.NoVisibleContent
    assert empty_terminal.getvalue() == ""

    clear_terminal_title(stdout=terminal)
    assert terminal.getvalue().endswith("\x1b]0;\x07")
