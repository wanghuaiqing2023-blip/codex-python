"""Parity tests for Rust ``codex-tui::cwd_prompt``.

Rust source: ``codex/codex-rs/tui/src/cwd_prompt.rs``.
"""

import pytest

from pycodex.tui.cwd_prompt import (
    CwdPromptAction,
    CwdPromptOutcome,
    CwdSelection,
    CwdPromptScreen,
    FrameRequester,
    KeyEvent,
    new_prompt,
    run_cwd_selection_prompt,
)


def test_cwd_prompt_action_words_match_rust() -> None:
    assert CwdPromptAction.Resume.verb() == "resume"
    assert CwdPromptAction.Resume.past_participle() == "resumed"
    assert CwdPromptAction.Fork.verb() == "fork"
    assert CwdPromptAction.Fork.past_participle() == "forked"


def test_cwd_prompt_selects_session_by_default() -> None:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("Enter"))
    assert screen.selection() is CwdSelection.Session


def test_cwd_prompt_can_select_current() -> None:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("Down"))
    screen.handle_key(KeyEvent.new("Enter"))
    assert screen.selection() is CwdSelection.Current


def test_cwd_prompt_ctrl_c_exits_instead_of_selecting() -> None:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("c", {"CONTROL"}))
    assert screen.selection() is None
    assert screen.is_done()
    assert screen.should_exit


def test_cwd_prompt_number_and_escape_selection_rules() -> None:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("2"))
    assert screen.selection() is CwdSelection.Current

    screen = new_prompt()
    screen.handle_key(KeyEvent.new("1"))
    assert screen.selection() is CwdSelection.Session

    screen = new_prompt()
    screen.handle_key(KeyEvent.new("Esc"))
    assert screen.selection() is CwdSelection.Session


def test_cwd_prompt_vim_keys_toggle_highlight_like_arrows() -> None:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("j"))
    assert screen.highlighted is CwdSelection.Current
    screen.handle_key(KeyEvent.new("k"))
    assert screen.highlighted is CwdSelection.Session


def test_cwd_prompt_ignores_key_release_and_schedules_on_highlight_change() -> None:
    requester = FrameRequester()
    screen = CwdPromptScreen.new(requester, CwdPromptAction.Resume, "/current", "/session")
    screen.handle_key(KeyEvent.new("Down", kind="Release"))
    assert screen.highlighted is CwdSelection.Session
    assert requester.scheduled == 0
    screen.handle_key(KeyEvent.new("Down"))
    assert screen.highlighted is CwdSelection.Current
    assert requester.scheduled == 1


def test_cwd_prompt_render_lines_resume_and_fork_content() -> None:
    resume = new_prompt().render_lines()
    assert "Choose working directory to resume this session" in resume
    assert "  Session = latest cwd recorded in the resumed session" in resume
    assert any("Use session directory (/Users/example/session)" in line for line in resume)

    fork = CwdPromptScreen.new(FrameRequester(), CwdPromptAction.Fork, "/current", "/session").render_lines()
    assert "Choose working directory to fork this session" in fork
    assert "  Session = latest cwd recorded in the forked session" in fork


class FakeTui:
    def __init__(self, events: list[object]) -> None:
        self.events = events
        self.requester = FrameRequester()
        self.draws: list[list[str]] = []

    def frame_requester(self) -> FrameRequester:
        return self.requester

    def draw(self, lines: list[str]) -> None:
        self.draws.append(lines)


@pytest.mark.asyncio
async def test_run_cwd_selection_prompt_handles_tui_events_and_defaults_to_session() -> None:
    tui = FakeTui(
        [
            {"kind": "Paste", "payload": "ignored"},
            {"kind": "Draw"},
            {"kind": "Key", "payload": KeyEvent.new("Esc")},
        ]
    )

    assert await run_cwd_selection_prompt(
        tui,
        CwdPromptAction.Resume,
        "/current",
        "/session",
    ) == CwdPromptOutcome.Selection(CwdSelection.Session)
    assert len(tui.draws) == 2


@pytest.mark.asyncio
async def test_run_cwd_selection_prompt_returns_exit_on_ctrl_d() -> None:
    tui = FakeTui([{"kind": "Key", "payload": KeyEvent.new("d", {"CONTROL"})}])

    assert await run_cwd_selection_prompt(
        tui,
        CwdPromptAction.Fork,
        "/current",
        "/session",
    ) == CwdPromptOutcome.Exit()
