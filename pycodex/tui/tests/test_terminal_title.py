import io

import pytest

from pycodex.tui.terminal_title import (
    MAX_TERMINAL_TITLE_CHARS,
    SetTerminalTitleResult,
    SetWindowTitle,
    clear_terminal_title,
    execute_winapi,
    is_ansi_code_supported,
    sanitize_terminal_title,
    set_terminal_title,
    write_ansi,
)


class _TtyStringIO(io.StringIO):
    def __init__(self, *, is_tty: bool) -> None:
        super().__init__()
        self._is_tty = is_tty
        self.flushed = False

    def isatty(self) -> bool:
        return self._is_tty

    def flush(self) -> None:
        self.flushed = True
        super().flush()


def test_sanitizes_terminal_title() -> None:
    """Rust codex-tui::terminal_title::tests::sanitizes_terminal_title."""

    sanitized = sanitize_terminal_title("  Project\t|\nWorking\x1b\x07\u009d\u009c |  Thread  ")

    assert sanitized == "Project | Working | Thread"


def test_strips_invisible_format_chars_from_terminal_title() -> None:
    """Rust codex-tui::terminal_title::tests::strips_invisible_format_chars_from_terminal_title."""

    sanitized = sanitize_terminal_title(
        "Pro\u202ej\u2066e\u200fc\u061ct\u200b \ufeffT\u2060itle"
    )

    assert sanitized == "Project Title"


def test_truncates_terminal_title() -> None:
    """Rust codex-tui::terminal_title::tests::truncates_terminal_title."""

    sanitized = sanitize_terminal_title("a" * (MAX_TERMINAL_TITLE_CHARS + 10))

    assert len(sanitized) == MAX_TERMINAL_TITLE_CHARS


def test_truncation_prefers_visible_char_over_pending_space() -> None:
    """Rust codex-tui::terminal_title::tests::truncation_prefers_visible_char_over_pending_space."""

    sanitized = sanitize_terminal_title(f"{'a' * (MAX_TERMINAL_TITLE_CHARS - 1)} b")

    assert len(sanitized) == MAX_TERMINAL_TITLE_CHARS
    assert sanitized[-1] == "b"


def test_writes_osc_title_with_bel_terminator() -> None:
    """Rust codex-tui::terminal_title::tests::writes_osc_title_with_bel_terminator."""

    assert write_ansi(SetWindowTitle("hello")) == "\x1b]0;hello\x07"


def test_set_terminal_title_writes_sanitized_title_only_for_tty() -> None:
    """Rust source contract: set_terminal_title sanitizes before OSC 0 write."""

    tty = _TtyStringIO(is_tty=True)

    result = set_terminal_title("  Project\nTitle  ", stdout=tty)

    assert result is SetTerminalTitleResult.Applied
    assert tty.getvalue() == "\x1b]0;Project Title\x07"
    assert tty.flushed is True

    non_tty = _TtyStringIO(is_tty=False)
    result = set_terminal_title("Project", stdout=non_tty)

    assert result is SetTerminalTitleResult.Applied
    assert non_tty.getvalue() == ""


def test_set_terminal_title_noops_for_empty_visible_title() -> None:
    """Rust source contract: empty sanitized content is not treated as clear."""

    tty = _TtyStringIO(is_tty=True)

    result = set_terminal_title("\x1b\u202e\ufeff", stdout=tty)

    assert result is SetTerminalTitleResult.NoVisibleContent
    assert tty.getvalue() == ""


def test_clear_terminal_title_writes_empty_osc_payload_only_for_tty() -> None:
    """Rust source contract: clear_terminal_title emits empty OSC title payload."""

    tty = _TtyStringIO(is_tty=True)
    clear_terminal_title(stdout=tty)
    assert tty.getvalue() == "\x1b]0;\x07"
    assert tty.flushed is True

    non_tty = _TtyStringIO(is_tty=False)
    clear_terminal_title(stdout=non_tty)
    assert non_tty.getvalue() == ""


def test_set_window_title_winapi_is_rejected_and_ansi_is_supported() -> None:
    """Rust source contract: Windows title updates use ANSI, not WinAPI."""

    command = SetWindowTitle("Project")

    assert is_ansi_code_supported(command) is True
    with pytest.raises(OSError, match="WinAPI"):
        execute_winapi(command)
