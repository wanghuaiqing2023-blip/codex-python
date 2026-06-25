from pathlib import Path

from pycodex.tui.app.history_ui import (
    AppHistoryUiState,
    ChatWidget,
    Config,
    Rect,
    ScreenSize,
    Terminal,
    Tui,
    clear_terminal_ui_alt_and_inline_branches,
    open_url_success_and_failure_messages,
    reset_transcript_state_after_clear_resets_owned_state,
)


def test_open_url_success_and_failure_messages() -> None:
    # Rust: app/history_ui.rs open_url_in_browser success/error chat messages.
    assert open_url_success_and_failure_messages()


def test_clear_terminal_ui_alt_and_inline_branches() -> None:
    # Rust: clear_terminal_ui clears pending lines then branches on alt screen.
    assert clear_terminal_ui_alt_and_inline_branches()


def test_reset_transcript_state_after_clear_resets_owned_state() -> None:
    # Rust: reset_transcript_state_after_clear clears transcript/backtrack/reflow state.
    assert reset_transcript_state_after_clear_resets_owned_state()


def test_header_lines_include_model_cwd_version_effort_fast_and_yolo_semantics() -> None:
    app = AppHistoryUiState(
        chat_widget=ChatWidget(
            model="gpt-test",
            reasoning_effort="high",
            fast_status=True,
        ),
        config=Config(cwd=Path("/tmp/project"), yolo_mode=True),
    )

    lines = app.clear_ui_header_lines_with_version(120, "v-test")

    assert len(lines) == 1
    assert "Codex v-test" in lines[0].text
    assert "model: gpt-test" in lines[0].text
    assert "cwd: /tmp/project" in lines[0].text
    assert "effort: high" in lines[0].text
    assert "fast" in lines[0].text
    assert "yolo" in lines[0].text


def test_queue_clear_ui_header_sets_history_emitted_only_when_lines_exist() -> None:
    app = AppHistoryUiState(chat_widget=ChatWidget(wrap_width=0))
    tui = Tui(terminal=Terminal(last_known_screen_size=ScreenSize(width=80, height=24)))

    assert app.queue_clear_ui_header(tui) == []
    assert not app.has_emitted_history_lines

    app.chat_widget.wrap_width = 80
    lines = app.queue_clear_ui_header(tui)

    assert lines
    assert app.has_emitted_history_lines
    assert tui.inserted_history_lines[-1] == lines


def test_clear_terminal_ui_without_redraw_does_not_queue_header() -> None:
    app = AppHistoryUiState(has_emitted_history_lines=True)
    tui = Tui(
        terminal=Terminal(
            last_known_screen_size=ScreenSize(width=80, height=24),
            viewport_area=Rect(y=0, width=80, height=24),
        )
    )

    app.clear_terminal_ui(tui, redraw_header=False)

    assert not app.has_emitted_history_lines
    assert tui.inserted_history_lines == []
    assert tui.terminal.scrollback_and_visible_ansi_clears == 1
