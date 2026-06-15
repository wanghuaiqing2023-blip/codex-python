"""Python parity for Rust ``codex-tui`` integration tests.

Rust sources:
- ``codex/codex-rs/tui/tests/manager_dependency_regression.rs``
- ``codex/codex-rs/tui/tests/suite/status_indicator.rs``
- ``codex/codex-rs/tui/tests/suite/vt100_history.rs``
- ``codex/codex-rs/tui/tests/suite/vt100_live_commit.rs``
- ``codex/codex-rs/tui/tests/suite/resize_reflow.rs``

The Rust resize tests are ``#[ignore]`` manual tmux smoke tests.  Python keeps
matching skipped tests so the crate-level integration inventory is represented
without pretending a local tmux/codex-binary runtime is available.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pycodex.ansi_escape import ansi_escape_line
from pycodex.tui.insert_history import Line, Span, Style, TerminalModel, insert_history_lines
from pycodex.tui.live_wrap import RowBuilder


REPO_ROOT = Path(__file__).resolve().parents[1]


def _visible_output(terminal: TerminalModel) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", terminal.output.getvalue()).replace("\r", "")


def _terminal(width: int, height: int, viewport_y: int) -> TerminalModel:
    return TerminalModel(width=width, height=height, viewport_y=viewport_y, viewport_height=1)


def test_tui_runtime_source_does_not_depend_on_manager_escape_hatches() -> None:
    """Rust integration: ``manager_dependency_regression.rs``."""

    forbidden = ["AuthManager", "ThreadManager", "auth_manager(", "thread_manager("]
    violations = []
    for path in sorted((REPO_ROOT / "pycodex" / "tui").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                violations.append(f"{path} contains `{needle}`")

    assert violations == []


def test_ansi_escape_line_strips_escape_sequences() -> None:
    """Rust integration: ``suite/status_indicator.rs``."""

    line = ansi_escape_line("\x1b[31mRED\x1b[0m")

    assert line.text == "RED"
    assert "\x1b" not in line.text


def test_vt100_history_basic_insertion_no_wrap() -> None:
    """Rust integration: ``suite/vt100_history.rs::basic_insertion_no_wrap``."""

    terminal = _terminal(width=20, height=6, viewport_y=5)

    insert_history_lines(terminal, ["first", "second"])
    output = _visible_output(terminal)

    assert "first" in output
    assert "second" in output


def test_vt100_history_long_token_wraps_and_preserves_characters() -> None:
    """Rust integration: ``suite/vt100_history.rs::long_token_wraps``."""

    terminal = _terminal(width=20, height=6, viewport_y=5)
    long = "A" * 45

    insert_history_lines(terminal, [long])

    assert _visible_output(terminal).count("A") == len(long)
    assert terminal.history_rows_inserted >= 3


def test_vt100_history_emoji_and_cjk_are_preserved() -> None:
    """Rust integration: ``suite/vt100_history.rs::emoji_and_cjk``."""

    terminal = _terminal(width=20, height=6, viewport_y=5)
    text = "😀😀😀😀😀 你好世界"

    insert_history_lines(terminal, [text])
    output = _visible_output(terminal)

    for ch in (c for c in text if not c.isspace()):
        assert ch in output


def test_vt100_history_mixed_ansi_spans_preserve_visible_text() -> None:
    """Rust integration: ``suite/vt100_history.rs::mixed_ansi_spans``."""

    terminal = _terminal(width=20, height=6, viewport_y=5)
    line = Line((Span("red", Style(fg="red")), Span("+plain")))

    insert_history_lines(terminal, [line])

    assert "red+plain" in _visible_output(terminal)


def test_vt100_history_cursor_restoration_boundary() -> None:
    """Rust integration: ``suite/vt100_history.rs::cursor_restoration``.

    Python's semantic ``TerminalModel`` does not expose cursor mutation; the
    integration contract is that history insertion does not require or fabricate
    cursor state on this model.
    """

    terminal = _terminal(width=20, height=6, viewport_y=5)

    insert_history_lines(terminal, ["x"])

    assert not hasattr(terminal, "last_known_cursor_pos")
    assert "x" in _visible_output(terminal)


def test_vt100_history_word_wrap_no_mid_word_split() -> None:
    """Rust integration: ``suite/vt100_history.rs::word_wrap_no_mid_word_split``."""

    terminal = _terminal(width=40, height=10, viewport_y=9)
    sample = (
        "Years passed, and Willowmere thrived in peace and friendship. Mira's "
        "herb garden flourished with both ordinary and enchanted plants, and "
        "travelers spoke of the kindness of the woman who tended them."
    )

    insert_history_lines(terminal, [sample])

    assert "bo\nth" not in _visible_output(terminal)


def test_vt100_history_em_dash_and_space_word_wrap() -> None:
    """Rust integration: ``suite/vt100_history.rs::em_dash_and_space_word_wrap``."""

    terminal = _terminal(width=40, height=10, viewport_y=9)
    sample = (
        "Mara found an old key on the shore. Curious, she opened a tarnished "
        "box half-buried in sand-and inside lay a single, glowing seed."
    )

    insert_history_lines(terminal, [sample])

    assert "insi\nde" not in _visible_output(terminal)


def test_vt100_live_commit_on_overflow() -> None:
    """Rust integration: ``suite/vt100_live_commit.rs::live_001_commit_on_overflow``."""

    terminal = _terminal(width=20, height=6, viewport_y=5)
    rb = RowBuilder.new(target_width=20)
    rb.push_fragment("one\n")
    rb.push_fragment("two\n")
    rb.push_fragment("three\n")
    rb.push_fragment("four\n")
    rb.push_fragment("five\n")

    commit_rows = rb.drain_commit_ready(max_keep=3)
    insert_history_lines(terminal, [row.text for row in commit_rows])
    output = _visible_output(terminal)

    assert "one" in output
    assert "two" in output
    assert [row.text for row in rb.display_rows()] == ["three", "four", "five"]


@pytest.mark.skip(reason="Rust integration test is #[ignore]: requires tmux and a locally built codex binary.")
def test_tmux_split_preserves_fresh_session_composer_row_after_resize_reflow() -> None:
    """Rust integration inventory: ``suite/resize_reflow.rs`` manual smoke."""


@pytest.mark.skip(reason="Rust integration test is #[ignore]: requires tmux and a locally built codex binary.")
def test_tmux_repeated_resizes_do_not_push_composer_down() -> None:
    """Rust integration inventory: ``suite/resize_reflow.rs`` manual smoke."""


@pytest.mark.skip(reason="Rust integration test is #[ignore]: requires tmux and a locally built codex binary.")
def test_tmux_width_resize_restore_keeps_visible_content_anchored() -> None:
    """Rust integration inventory: ``suite/resize_reflow.rs`` manual smoke."""
