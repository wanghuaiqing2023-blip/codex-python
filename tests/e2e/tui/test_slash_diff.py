"""End-to-end coverage for the ``/diff`` slash command."""

from __future__ import annotations

import re

import pytest

from pycodex.ansi_escape import ansi_escape
from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    require_native_slash_comparison,
    run_diff_slash_pair,
)

pytestmark = pytest.mark.e2e


def test_diff_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch starts local diff progress.
    # - get_git_diff runs tracked/untracked Git capture through the workspace
    #   command runner and returns through AppEvent::DiffResult.
    route = terminal_slash_command_routes()[SlashCommand.DIFF]

    assert SlashCommand.DIFF.command() == "diff"
    assert SlashCommand.DIFF.supports_inline_args() is False
    assert SlashCommand.DIFF.available_during_task() is True
    assert SlashCommand.DIFF.available_in_side_conversation() is True
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.argument_form == "bare"


def _scroll_percent(screen: str) -> int:
    matches = re.findall(r"(?<!\d)(\d{1,3})%", screen)
    if not matches:
        # Ratatui updates only the changed digits after the first frame; the
        # conservative VT projector can therefore retain the digits while
        # losing the unchanged percent cell in an incremental checkpoint.
        matches = re.findall(r"(?m)(\d{1,3})\s*$", screen)
    assert matches, f"pager percentage is missing from screen: {screen!r}"
    return int(matches[-1])


def _has_colored_text(raw: str, color: str, needle: str) -> bool:
    role_values = {
        "red": {"red", "light_red", 1, 9},
        "green": {"green", "light_green", 2, 10},
        "cyan": {"cyan", "light_cyan", 6, 14},
    }
    parsed = ansi_escape(raw)
    return any(
        span.style.fg in role_values[color] and needle in span.text
        for line in parsed.lines
        for span in line.spans
    )


def test_windows_conpty_native_and_python_diff_full_screen_pager_contract(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust_result, python_result = run_diff_slash_pair(
        native_exe,
        artifact_dir=tmp_path,
    )

    for label, (transcript, request_count) in (
        ("rust", rust_result),
        ("python", python_result),
    ):
        output = transcript.normalized_stdout()
        initial = transcript.checkpoint_screen("initial", rows=32, cols=120)
        page_down = transcript.checkpoint_screen("page_down", rows=32, cols=120)
        bottom = transcript.checkpoint_screen("bottom", rows=32, cols=120)
        home = transcript.checkpoint_screen("home", rows=32, cols=120)
        restored = transcript.checkpoint_screen("restored", rows=32, cols=120)
        initial_raw = transcript.checkpoint_stdout("initial")
        detail = (
            f"{label}: requests={request_count}; "
            f"returncode={transcript.returncode}; "
            f"stderr={transcript.normalized_stderr()!r}; "
            f"initial={initial!r}; page_down={page_down!r}; "
            f"bottom={bottom!r}; home={home!r}; restored={restored!r}; "
            f"output={output!r}"
        )
        assert request_count == 0, detail
        assert transcript.returncode == 0, detail
        assert transcript.normalized_stderr() == "", detail

        # Rust app::event_dispatch -> pager_overlay::StaticOverlay structure.
        assert "D I F F" in initial, detail
        assert "diff --git a/tracked.txt b/tracked.txt" in output, detail
        assert "@@" in initial, detail
        assert "baseline line 002" in initial, detail
        assert "to scroll" in output, detail
        assert "pgup/pgdn to page" in output, detail
        assert "home/end to jump" in output, detail
        assert "q to quit" in initial, detail
        assert "/model to change" not in initial, detail
        assert "directory:" not in initial, detail

        # Git's ANSI roles survive ansi_escape_line -> terminal buffer output.
        assert _has_colored_text(initial_raw, "red", "baseline line 002"), detail
        assert _has_colored_text(
            initial_raw,
            "green",
            "PYCODEX_DIFF_TOP_MARKER",
        ), detail
        assert _has_colored_text(initial_raw, "cyan", "@@"), detail

        # Real navigation changes both visible content and pager percentage.
        assert "PYCODEX_DIFF_MIDDLE_MARKER" in page_down, detail
        assert "PYCODEX_DIFF_BOTTOM_MARKER" in bottom, detail
        assert "PYCODEX_DIFF_TOP_MARKER" in home, detail
        assert "0%" in output, detail
        assert _scroll_percent(page_down) > 0, detail
        assert _scroll_percent(bottom) == 100, detail
        assert _scroll_percent(home) == 0, detail

        # q closes the overlay and restores the real composer surface.
        assert "D I F F" not in restored, detail
        assert "directory:" in restored, detail
        assert "OpenAI Codex" in restored, detail
        assert "DIFF_SLASH_MUST_NOT_REACH_THE_MODEL" not in output, detail
        assert "product effect is not yet available" not in output, detail
