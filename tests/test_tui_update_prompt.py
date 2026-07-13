from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

from pycodex.tui.ratatui_bridge import Buffer, Cell, Rect
from pycodex.tui.update_prompt import (
    DummyFrameRequester,
    KeyEvent,
    RELEASE_NOTES_URL,
    UpdatePromptOutcomeKind,
    UpdatePromptScreen,
    UpdateSelection,
    new_prompt,
    render_ref,
    run_update_prompt_if_needed,
    update_prompt_confirm_selects_update,
    update_prompt_ctrl_c_skips_update,
    default_update_action,
    update_prompt_dismiss_option_leaves_prompt_in_normal_state,
    update_prompt_dont_remind_selects_dismissal,
    update_prompt_navigation_wraps_between_entries,
    update_prompt_snapshot,
)
from pycodex.tui.version import CODEX_CLI_VERSION


def test_update_prompt_snapshot_visible_contract() -> None:
    lines = update_prompt_snapshot()

    assert f"Update available! {CODEX_CLI_VERSION} -> 9.9.9" in lines[1]
    assert f"Release notes: {RELEASE_NOTES_URL}" in lines[3]
    assert "> 1. Update now (runs `npm install -g @openai/codex`)" in lines[5]
    assert "  2. Skip" in lines[6]
    assert "  3. Skip until next version" in lines[7]
    assert "Press Enter to continue" in lines[-1]


def test_update_prompt_confirm_selects_update() -> None:
    assert update_prompt_confirm_selects_update() is UpdateSelection.UPDATE_NOW


def test_update_prompt_dismiss_option_leaves_prompt_in_normal_state() -> None:
    assert update_prompt_dismiss_option_leaves_prompt_in_normal_state() is UpdateSelection.NOT_NOW


def test_update_prompt_dont_remind_selects_dismissal() -> None:
    assert update_prompt_dont_remind_selects_dismissal() is UpdateSelection.DONT_REMIND


def test_update_prompt_ctrl_c_skips_update() -> None:
    assert update_prompt_ctrl_c_skips_update() is UpdateSelection.NOT_NOW


def test_update_prompt_navigation_wraps_between_entries() -> None:
    assert update_prompt_navigation_wraps_between_entries() is UpdateSelection.UPDATE_NOW


def test_update_prompt_numeric_and_escape_shortcuts() -> None:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("3"))
    assert screen.selection() is UpdateSelection.DONT_REMIND

    screen = new_prompt()
    screen.handle_key(KeyEvent.new("2"))
    assert screen.selection() is UpdateSelection.NOT_NOW

    screen = new_prompt()
    screen.handle_key(KeyEvent.new("esc"))
    assert screen.selection() is UpdateSelection.NOT_NOW


def test_update_prompt_ignores_release_key_and_schedules_on_highlight_change() -> None:
    requester = DummyFrameRequester()
    screen = UpdatePromptScreen.new(requester, "9.9.9", default_update_action())

    screen.handle_key(KeyEvent.new("down", kind="release"))
    assert screen.highlighted is UpdateSelection.UPDATE_NOW
    assert requester.scheduled == 0

    screen.handle_key(KeyEvent.new("down"))
    assert screen.highlighted is UpdateSelection.NOT_NOW
    assert requester.scheduled == 1

    screen.set_highlight(UpdateSelection.NOT_NOW)
    assert requester.scheduled == 1


class _Terminal:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


class _Tui:
    def __init__(self, events: List[object]) -> None:
        self.events = events
        self.terminal = _Terminal()
        self.drawn: List[UpdatePromptScreen] = []
        self.requester = DummyFrameRequester()

    def frame_requester(self) -> DummyFrameRequester:
        return self.requester

    def draw_update_prompt(self, screen: UpdatePromptScreen) -> None:
        self.drawn.append(screen)

    async def next_event(self) -> Optional[object]:
        if not self.events:
            return None
        return self.events.pop(0)


def test_run_update_prompt_returns_run_update_and_clears_terminal() -> None:
    tui = _Tui([KeyEvent.new("enter")])

    outcome = asyncio.run(run_update_prompt_if_needed(
        tui,
        object(),
        latest_version="9.9.9",
        update_action=default_update_action(),
    ))

    assert outcome.kind is UpdatePromptOutcomeKind.RUN_UPDATE
    assert outcome.action is default_update_action()
    assert tui.terminal.cleared is True
    assert tui.drawn


def test_run_update_prompt_dismisses_version_on_dont_remind() -> None:
    class Updates:
        def __init__(self) -> None:
            self.dismissed: List[Tuple[object, str]] = []

        async def dismiss_version(self, config: object, version: str) -> None:
            self.dismissed.append((config, version))

    config = object()
    updates = Updates()
    tui = _Tui([KeyEvent.new("3")])

    outcome = asyncio.run(run_update_prompt_if_needed(
        tui,
        config,
        latest_version="9.9.9",
        update_action=default_update_action(),
        updates_module=updates,
    ))

    assert outcome.kind is UpdatePromptOutcomeKind.CONTINUE
    assert updates.dismissed == [(config, "9.9.9")]


def test_run_update_prompt_continues_when_dependencies_absent() -> None:
    tui = _Tui([])

    outcome = asyncio.run(run_update_prompt_if_needed(tui, object()))

    assert outcome.kind is UpdatePromptOutcomeKind.CONTINUE


def test_update_prompt_renders_to_bridge_buffer_and_clears_area() -> None:
    screen = new_prompt()
    area = Rect.new(0, 0, 80, 12)
    buffer = Buffer.empty(area)
    buffer.fill(area, Cell("."))

    screen.render(area, buffer)

    text = buffer.to_plain_text(trim_end=True)
    assert "Update available!" in text
    assert f"{CODEX_CLI_VERSION} -> 9.9.9" in text
    assert RELEASE_NOTES_URL in text
    assert "> 1. Update now (runs `npm install -g @openai/codex`)" in text
    assert "Press Enter to continue" in text
    assert "." not in buffer.row_plain(0)


def test_update_prompt_bridge_render_tracks_highlight() -> None:
    screen = new_prompt()
    screen.handle_key(KeyEvent.new("down"))
    area = Rect.new(0, 0, 80, 12)
    buffer = Buffer.empty(area)

    screen.render_ref(area, buffer)

    lines = buffer.to_plain_text(trim_end=True).splitlines()
    assert "  1. Update now (runs `npm install -g @openai/codex`)" in lines[5]
    assert "> 2. Skip" in lines[6]


def test_update_prompt_module_render_ref_keeps_snapshot_compatibility() -> None:
    screen = new_prompt()
    area = Rect.new(0, 0, 80, 12)
    buffer = Buffer.empty(area)

    snapshot = render_ref(screen, area, buffer)

    assert snapshot == screen.render_lines()
    assert "Update available!" in buffer.to_plain_text(trim_end=True)
