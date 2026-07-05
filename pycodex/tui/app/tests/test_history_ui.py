from pathlib import Path

from pycodex.tui.app.history_ui import (
    AppHistoryUiState,
    ChatWidget,
    Config,
    Rect,
    ScreenSize,
    Terminal,
    TerminalClearState,
    TerminalClearUiExecutor,
    TerminalSessionHeaderData,
    Tui,
    clear_terminal_ui_alt_and_inline_branches,
    open_url_success_and_failure_messages,
    reset_transcript_state_after_clear_resets_owned_state,
    run_terminal_clear_application_state,
    run_terminal_clear_ui_effects,
    run_terminal_session_header_from_runtime,
    run_terminal_session_header_render,
    terminal_clear_application_state,
    terminal_clear_state_after_clear,
    terminal_session_header_data_from_runtime,
    terminal_session_header_lines,
    terminal_session_header_text,
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
    # Rust crate/module:
    # - codex-tui::app::history_ui::clear_ui_header_lines_with_version
    # - codex-tui::history_cell::session::SessionHeaderHistoryCell
    # Contract: app/history_ui delegates fresh header rendering to the session
    # header history cell rather than keeping a one-line Python-only summary.
    app = AppHistoryUiState(
        chat_widget=ChatWidget(
            model="gpt-test",
            reasoning_effort="high",
            fast_status=True,
        ),
        config=Config(cwd=Path("/tmp/project"), yolo_mode=True),
    )

    lines = app.clear_ui_header_lines_with_version(120, "test")
    text = "\n".join(line.text for line in lines)

    assert len(lines) > 1
    assert ">_ OpenAI Codex (vtest)" in text
    assert "model:" in text
    assert "gpt-test high" in text
    assert "fast" in text
    assert "directory:" in text
    assert "tmp" in text
    assert "project" in text
    assert "permissions:" in text
    assert "YOLO mode" in text


def test_terminal_session_header_lines_respect_zero_width() -> None:
    # Rust: app/history_ui returns no header lines when the available history
    # width cannot render the session header cell.
    assert (
        terminal_session_header_lines(
            TerminalSessionHeaderData(
                model="gpt-test",
                reasoning_effort=None,
                show_fast_status=False,
                directory=Path("/tmp/project"),
                version="test",
            ),
            0,
        )
        == ()
    )


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


def test_terminal_clear_state_after_clear_resets_scrollback_product_state() -> None:
    state = terminal_clear_state_after_clear()

    assert state.history_has_content is False
    assert state.history_ended_with_blank is False
    assert state.history_projection_cells == ()
    assert state.assistant_stream_text == ""
    assert state.resize_reflow_pending is False


def test_terminal_clear_application_state_maps_to_terminal_product_state() -> None:
    # Rust owner: app/history_ui.rs owns clear/reset semantics.  The terminal
    # runner should apply this prepared state instead of rebuilding
    # insert-history and assistant-stream objects itself.
    applied = terminal_clear_application_state(
        TerminalClearState(
            history_has_content=True,
            history_ended_with_blank=True,
            history_projection_cells=("old",),
            assistant_stream_text="partial",
            resize_reflow_pending=True,
        )
    )

    assert applied.history_state.history_has_content is True
    assert applied.history_state.history_ended_with_blank is True
    assert applied.history_state.projection_cells == ("old",)
    assert applied.assistant_stream.active is False
    assert applied.assistant_stream.text == "partial"
    assert applied.resize_reflow_pending is True


def test_run_terminal_clear_application_state_applies_owned_reset_state() -> None:
    # Rust owner: app/history_ui.rs owns clear/reset semantics.  The terminal
    # runner should pass state sinks into this boundary instead of interpreting
    # history, assistant-stream, and resize-pending fields itself.
    calls: list[str] = []
    history_states = []
    assistant_states = []
    resize_pending = []

    applied = run_terminal_clear_application_state(
        TerminalClearState(
            history_has_content=True,
            history_ended_with_blank=True,
            history_projection_cells=("old",),
            assistant_stream_text="partial",
            resize_reflow_pending=True,
        ),
        apply_history_state=lambda state: (calls.append("history"), history_states.append(state)),
        apply_assistant_stream_state=lambda state: (
            calls.append("assistant"),
            assistant_states.append(state),
        ),
        apply_resize_pending=lambda pending: (calls.append("resize"), resize_pending.append(pending)),
    )

    assert calls == ["history", "assistant", "resize"]
    assert history_states == [applied.history_state]
    assert assistant_states == [applied.assistant_stream]
    assert resize_pending == [True]


def test_run_terminal_clear_ui_effects_sequences_terminal_callbacks() -> None:
    # Rust owner: codex-tui::app::history_ui owns clear/reset sequencing.  The
    # terminal runner supplies side-effect callbacks, but should not order the
    # clear, state reset, header repaint, and layout restore itself.
    calls: list[str] = []
    captured: list[TerminalClearState] = []

    returned = run_terminal_clear_ui_effects(
        deactivate_layout=lambda: calls.append("deactivate"),
        clear_terminal=lambda: calls.append("clear"),
        flush_terminal=lambda: calls.append("flush"),
        apply_clear_state=lambda state: (calls.append("apply"), captured.append(state)),
        render_header=lambda: calls.append("header"),
        activate_layout=lambda: calls.append("activate"),
    )

    assert calls == ["deactivate", "clear", "flush", "apply", "header", "activate"]
    assert returned == terminal_clear_state_after_clear()
    assert captured == [returned]


def test_terminal_clear_ui_executor_applies_state_and_sequences_callbacks() -> None:
    # Rust owner: app/history_ui.rs owns /clear ordering and reset state. The
    # terminal runner should supply sinks to an app-owned executor instead of
    # composing run_terminal_clear_ui_effects itself.
    calls: list[str] = []
    history_states = []
    assistant_states = []
    resize_pending = []

    executor = TerminalClearUiExecutor(
        deactivate_layout=lambda: calls.append("deactivate"),
        clear_terminal=lambda: calls.append("clear"),
        flush_terminal=lambda: calls.append("flush"),
        apply_history_state=lambda state: (calls.append("history"), history_states.append(state)),
        apply_assistant_stream_state=lambda state: (
            calls.append("assistant"),
            assistant_states.append(state),
        ),
        apply_resize_pending=lambda pending: (calls.append("resize"), resize_pending.append(pending)),
        render_header=lambda: calls.append("header"),
        activate_layout=lambda: calls.append("activate"),
    )

    returned = executor.run()

    assert calls == ["deactivate", "clear", "flush", "history", "assistant", "resize", "header", "activate"]
    assert returned == terminal_clear_state_after_clear()
    assert history_states[0].projection_cells == ()
    assert assistant_states[0].active is False
    assert resize_pending == [False]


def test_terminal_session_header_data_from_runtime_uses_runtime_providers() -> None:
    # Rust owner: app/history_ui.rs reads App/chat-widget state before building
    # SessionHeaderHistoryCell.  The terminal runner should pass providers, not
    # assemble the header fields itself.
    class Runtime:
        cwd = Path("/workspace/project")

    runtime = Runtime()

    data = terminal_session_header_data_from_runtime(
        runtime,
        display_version=lambda: "9.9.9",
        display_model=lambda value: f"model-for-{value.cwd.name}",
        reasoning_effort=lambda value: f"effort-for-{value.cwd.parent.name}",
        show_fast_status=lambda value: value.cwd.name == "project",
        yolo_mode=lambda value: value.cwd.parent.name == "workspace",
    )

    assert data == TerminalSessionHeaderData(
        model="model-for-project",
        reasoning_effort="effort-for-workspace",
        show_fast_status=True,
        directory=Path("/workspace/project"),
        version="9.9.9",
        yolo_mode=True,
    )


def test_run_terminal_session_header_render_writes_history_cell() -> None:
    # Rust owner: app/history_ui.rs delegates the header display to
    # history_cell/session.rs.  The terminal product path should reuse the same
    # adapter and only provide the history writer callback.
    class Runtime:
        cwd = Path("/workspace/project")

    written: list[str] = []
    data = run_terminal_session_header_render(
        Runtime(),
        display_version=lambda: "test",
        display_model=lambda _: "gpt-test",
        reasoning_effort=lambda _: "high",
        show_fast_status=lambda _: True,
        yolo_mode=lambda _: False,
        write_history_cell=written.append,
        width=100,
    )

    assert written == [terminal_session_header_text(data, 100)]
    assert "OpenAI Codex" in written[0]
    assert "gpt-test high" in written[0]


def test_run_terminal_session_header_from_runtime_uses_canonical_providers(monkeypatch) -> None:
    # Rust owner: app/history_ui.rs owns session-header state collection before
    # delegating to history_cell/session.rs.  The terminal runner should call
    # this boundary instead of importing textual runtime providers directly.
    from pycodex.tui import textual_runtime

    class Runtime:
        cwd = Path("/workspace/project")

    monkeypatch.setattr(textual_runtime, "_display_version", lambda: "runtime-version")
    monkeypatch.setattr(textual_runtime, "_runtime_display_model", lambda runtime: "runtime-model")
    monkeypatch.setattr(
        textual_runtime,
        "_runtime_header_reasoning_effort",
        lambda runtime: "high",
    )
    monkeypatch.setattr(textual_runtime, "_runtime_show_fast_status", lambda runtime: True)
    monkeypatch.setattr(textual_runtime, "_runtime_header_yolo_mode", lambda runtime: True)

    written: list[str] = []
    data = run_terminal_session_header_from_runtime(
        Runtime(),
        write_history_cell=written.append,
        width=100,
    )

    assert data == TerminalSessionHeaderData(
        model="runtime-model",
        reasoning_effort="high",
        show_fast_status=True,
        directory=Path("/workspace/project"),
        version="runtime-version",
        yolo_mode=True,
    )
    assert written == [terminal_session_header_text(data, 100)]
