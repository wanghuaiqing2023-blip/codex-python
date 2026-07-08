"""Parity tests for codex-rs/tui/src/history_cell/messages.rs."""

from pycodex.tui.history_cell.messages import (
    AgentMarkdownCell,
    AgentMessageCell,
    StreamingAgentTailCell,
    TerminalAssistantStreamState,
    TerminalAssistantStreamWriter,
    TerminalUserPromptOutputWriter,
    TextElement,
    build_user_message_lines_with_elements,
    line_text,
    local_image_label_text,
    new_reasoning_summary_block,
    new_user_prompt,
    run_terminal_assistant_stream_delta_plan,
    run_terminal_assistant_stream_finalization,
    run_terminal_user_prompt_output,
    terminal_assistant_delta_text,
    terminal_assistant_projection_text,
    terminal_assistant_stream_after_delta,
    terminal_assistant_stream_delta_plan,
    terminal_assistant_stream_finalized,
    terminal_assistant_stream_initial_column,
    terminal_assistant_stream_opened,
    terminal_assistant_stream_prefix,
    terminal_user_prompt_text,
    trim_trailing_blank_lines,
)
from pycodex.tui.line_truncation import Line
from pycodex.tui.terminal_hyperlinks import HyperlinkLine


def texts(lines):
    return [line_text(line) for line in lines]


def hyperlink_texts(lines):
    return [line_text(line.line) for line in lines]


def test_build_user_message_lines_with_elements_interleaves_styled_ranges() -> None:
    message = "hello token\nsecond"
    lines = build_user_message_lines_with_elements(
        message,
        [TextElement.new((6, 11), "token")],
        style="base",
        element_style="element",
    )

    assert texts(lines) == ["hello token", "second"]
    assert [span.style for span in lines[0].spans] == [None, "element"]
    assert lines[0].style == "base"


def test_build_user_message_lines_skips_invalid_utf8_byte_boundaries() -> None:
    message = "a界b"
    lines = build_user_message_lines_with_elements(
        message,
        [TextElement.new((2, 3), None)],
        style="base",
        element_style="element",
    )

    assert texts(lines) == ["a界b"]
    assert lines[0].spans[0].style is None


def test_user_history_cell_trims_trailing_blank_message_lines_and_keeps_one_outer_blank() -> None:
    cell = new_user_prompt(
        "line one\n\n   \n\t \n",
        remote_image_urls=["https://example.com/one.png"],
    )

    rendered = texts(cell.display_lines(80))

    assert "line one" in "\n".join(rendered)
    trailing_blank_count = 0
    for line in reversed(rendered):
        if line.strip():
            break
        trailing_blank_count += 1
    assert trailing_blank_count == 1
    assert "› line one" in rendered


def test_user_history_cell_raw_lines_include_remote_image_labels() -> None:
    cell = new_user_prompt("hello\n", remote_image_urls=["https://example.com/img.png"])

    assert texts(cell.raw_lines()) == ["hello", "", local_image_label_text(1)]
    assert local_image_label_text(2) == "[Image #2]"


def test_terminal_user_prompt_text_matches_scrollback_product_shape() -> None:
    # Rust owner: codex-tui::history_cell::messages::new_user_prompt.
    assert terminal_user_prompt_text("hello?") == "\u203a hello?"


def test_run_terminal_user_prompt_output_writes_and_renders_when_terminal_active() -> None:
    # Rust owner: codex-tui::history_cell::messages owns user prompt history
    # output; terminal runtime supplies side-effect callbacks.
    calls: list[tuple[str, str | bool | None]] = []

    run_terminal_user_prompt_output(
        "hello?",
        terminal_active=True,
        clear_live_status=lambda: calls.append(("clear_live", None)),
        write_history_cell=lambda text, reserve_active_bottom_pane=False: calls.append(
            ("write", f"{text}|reserve={reserve_active_bottom_pane}")
        ),
        render_bottom_pane=lambda: calls.append(("render", None)),
    )

    assert calls == [
        ("clear_live", None),
        ("write", "\u203a hello?|reserve=True"),
        ("render", None),
    ]


def test_run_terminal_user_prompt_output_skips_render_when_terminal_inactive() -> None:
    calls: list[tuple[str, str | None]] = []

    run_terminal_user_prompt_output(
        "offline",
        terminal_active=False,
        clear_live_status=lambda: calls.append(("clear_live", None)),
        write_history_cell=lambda text, **kwargs: calls.append(("write", text)),
        render_bottom_pane=lambda: calls.append(("render", None)),
    )

    assert calls == [("clear_live", None), ("write", "\u203a offline")]


def test_terminal_user_prompt_output_writer_binds_runtime_callbacks() -> None:
    # Rust owner: codex-tui::history_cell::messages owns terminal user-prompt
    # scrollback output. terminal_runtime should call the bound writer instead
    # of passing prompt-output side-effect callbacks at the submit site.
    active = [True]
    calls: list[tuple[str, str | bool | None]] = []
    writer = TerminalUserPromptOutputWriter(
        terminal_active=lambda: active[0],
        clear_live_status=lambda: calls.append(("clear_live", None)),
        write_history_cell=lambda text, reserve_active_bottom_pane=False: calls.append(
            ("write", f"{text}|reserve={reserve_active_bottom_pane}")
        ),
        render_bottom_pane=lambda: calls.append(("render", None)),
    )

    writer.write("hello?")
    active[0] = False
    writer.write("offline")

    assert calls == [
        ("clear_live", None),
        ("write", "\u203a hello?|reserve=True"),
        ("render", None),
        ("clear_live", None),
        ("write", "\u203a offline|reserve=True"),
    ]


def test_trim_trailing_blank_lines_removes_blank_only_lines() -> None:
    lines = [Line.from_text("a"), Line.from_text(" "), Line.from_text("")]

    assert texts(trim_trailing_blank_lines(lines)) == ["a"]


def test_agent_message_cell_prefixes_and_raw_lines() -> None:
    cell = AgentMessageCell.new([Line.from_text("hello")], is_first_line=True)

    rendered = texts(cell.display_lines(80))
    assert rendered == ["• hello"]
    assert "鈥?" not in "\n".join(rendered)
    assert texts(cell.raw_lines()) == ["hello"]
    assert cell.is_stream_continuation() is False


def test_terminal_assistant_delta_text_wraps_like_streaming_tail_cell() -> None:
    # Rust owner: codex-tui::history_cell::messages::StreamingAgentTailCell.
    rendered, column = terminal_assistant_delta_text(
        "wxyz",
        current_column=4,
        wrap_width=5,
    )

    assert rendered == "w\r\n  xyz"
    assert column == 5


def test_terminal_assistant_delta_text_handles_newlines_cr_and_wide_chars() -> None:
    # Rust owner: codex-tui::history_cell::messages::StreamingAgentTailCell.
    rendered, column = terminal_assistant_delta_text(
        "a\r\n好b",
        current_column=2,
        wrap_width=5,
    )

    assert rendered == "a\r\n  好b"
    assert column == 5


def test_terminal_assistant_delta_text_preserves_terminal_tab_width() -> None:
    # Rust owner: codex-tui::history_cell::messages::StreamingAgentTailCell.
    rendered, column = terminal_assistant_delta_text(
        "\tx",
        current_column=2,
        wrap_width=7,
    )

    assert rendered == "\tx"
    assert column == 7


def test_terminal_assistant_stream_prefix_and_projection_shape() -> None:
    # Rust owner: codex-tui::history_cell::messages::AgentMessageCell.
    prefix = terminal_assistant_stream_prefix()

    assert prefix == "\u2022 "
    assert terminal_assistant_stream_initial_column(prefix) == 2
    assert terminal_assistant_projection_text("answer") == "\u2022 answer"
    assert terminal_assistant_projection_text("") is None


def test_terminal_assistant_stream_state_opens_updates_and_finalizes_projection() -> None:
    # Rust owner: codex-tui::history_cell::messages::StreamingAgentTailCell.
    state = terminal_assistant_stream_opened()

    assert state == TerminalAssistantStreamState(active=True, column=2, text="")

    rendered, state = terminal_assistant_stream_after_delta(
        state,
        "wxyz",
        wrap_width=5,
    )

    assert rendered == "wxy\r\n  z"
    assert state == TerminalAssistantStreamState(active=True, column=3, text="wxyz")

    projection, state = terminal_assistant_stream_finalized(state)

    assert projection == "\u2022 wxyz"
    assert state == TerminalAssistantStreamState.inactive()


def test_terminal_assistant_stream_delta_plan_opens_once_and_updates_state() -> None:
    # Rust owner: codex-tui::history_cell::messages::StreamingAgentTailCell.
    plan = terminal_assistant_stream_delta_plan(
        TerminalAssistantStreamState.inactive(),
        "wxyz",
        wrap_width=5,
    )

    assert plan.open_prefix == "\u2022 "
    assert plan.text == "wxy\r\n  z"
    assert plan.state == TerminalAssistantStreamState(active=True, column=3, text="wxyz")

    next_plan = terminal_assistant_stream_delta_plan(
        plan.state,
        "!",
        wrap_width=5,
    )

    assert next_plan.open_prefix is None
    assert next_plan.text == "!"
    assert next_plan.state == TerminalAssistantStreamState(active=True, column=4, text="wxyz!")


def test_run_terminal_assistant_stream_delta_plan_dispatches_open_then_write() -> None:
    # Rust owner: codex-tui::history_cell::messages::StreamingAgentTailCell.
    # The terminal runner supplies side effects; messages owns the stream
    # opening, delta rendering, and state advancement sequence.
    calls: list[tuple[str, str]] = []

    state = run_terminal_assistant_stream_delta_plan(
        TerminalAssistantStreamState.inactive(),
        "wxyz",
        wrap_width=5,
        open_stream=lambda prefix: calls.append(("open", prefix)),
        write_delta=lambda text: calls.append(("write", text)),
    )

    assert state == TerminalAssistantStreamState(active=True, column=3, text="wxyz")
    assert calls == [("open", "\u2022 "), ("write", "wxy\r\n  z")]

    calls.clear()
    state = run_terminal_assistant_stream_delta_plan(
        state,
        "!",
        wrap_width=5,
        open_stream=lambda prefix: calls.append(("open", prefix)),
        write_delta=lambda text: calls.append(("write", text)),
    )

    assert state == TerminalAssistantStreamState(active=True, column=4, text="wxyz!")
    assert calls == [("write", "!")]


def test_run_terminal_assistant_stream_finalization_orders_projection_before_reflow() -> None:
    # Rust owner: codex-tui::history_cell::messages owns assistant stream
    # finalization; insert_history/app::resize_reflow remain caller effects.
    calls: list[tuple[str, str | None]] = []

    stream_state, history_state = run_terminal_assistant_stream_finalization(
        TerminalAssistantStreamState(active=True, column=4, text="done"),
        finish_projection=lambda projection: calls.append(("projection", projection)) or "history-next",
        apply_history_state=lambda state: calls.append(("apply", state)),
        finish_stream_reflow=lambda: calls.append(("reflow", None)),
    )

    assert stream_state == TerminalAssistantStreamState.inactive()
    assert history_state == "history-next"
    assert calls == [("projection", "\u2022 done"), ("apply", "history-next"), ("reflow", None)]


def test_run_terminal_assistant_stream_finalization_keeps_empty_projection_none() -> None:
    calls: list[tuple[str, str | None]] = []

    stream_state, history_state = run_terminal_assistant_stream_finalization(
        TerminalAssistantStreamState(active=True, column=2, text=""),
        finish_projection=lambda projection: calls.append(("projection", projection)) or "unchanged",
        finish_stream_reflow=lambda: calls.append(("reflow", None)),
    )

    assert stream_state == TerminalAssistantStreamState.inactive()
    assert history_state == "unchanged"
    assert calls == [("projection", None), ("reflow", None)]


def test_terminal_assistant_stream_writer_owns_delta_state_and_effect_order() -> None:
    # Rust owner: codex-tui::history_cell::messages owns streaming assistant
    # text and terminal projection state; the runner only supplies effects.
    calls: list[tuple[str, str]] = []
    width = {"value": 5}
    writer = TerminalAssistantStreamWriter(
        wrap_width=lambda: width["value"],
        open_stream=lambda prefix: calls.append(("open", prefix)),
        write_delta=lambda text: calls.append(("write", text)),
        finish_projection=lambda projection: calls.append(("projection", str(projection))) or "history",
        finish_stream_reflow=lambda: calls.append(("reflow", "")),
    )

    writer.handle_delta("wxyz")
    writer.handle_delta("!")

    assert writer.active is True
    assert writer.state == TerminalAssistantStreamState(active=True, column=4, text="wxyz!")
    assert calls == [("open", "\u2022 "), ("write", "wxy\r\n  z"), ("write", "!")]


def test_terminal_assistant_stream_writer_repaints_active_projection_after_delta() -> None:
    # Rust owner: codex-tui::history_cell::messages owns the active assistant
    # stream text; the terminal runner may project that text into the current
    # viewport before the stream is finalized.
    repaints: list[str | None] = []
    writer = TerminalAssistantStreamWriter(
        wrap_width=lambda: 20,
        open_stream=lambda _prefix: None,
        write_delta=lambda _text: None,
        finish_projection=lambda projection: projection,
        finish_stream_reflow=lambda: None,
        repaint_active_stream=repaints.append,
    )

    writer.handle_delta("first")
    writer.handle_delta(" second")

    assert repaints == ["\u2022 first", "\u2022 first second"]


def test_terminal_assistant_stream_writer_finalizes_projection_and_resets_state() -> None:
    calls: list[tuple[str, str | None]] = []
    applied: list[str] = []
    writer = TerminalAssistantStreamWriter(
        wrap_width=lambda: 20,
        open_stream=lambda prefix: calls.append(("open", prefix)),
        write_delta=lambda text: calls.append(("write", text)),
        finish_projection=lambda projection: calls.append(("projection", projection)) or "history-next",
        apply_history_state=lambda state: applied.append(state),
        finish_stream_reflow=lambda: calls.append(("reflow", None)),
    )

    writer.handle_delta("done")
    history_state = writer.finalize()

    assert history_state == "history-next"
    assert applied == ["history-next"]
    assert writer.state == TerminalAssistantStreamState.inactive()
    assert calls == [
        ("open", "\u2022 "),
        ("write", "done"),
        ("projection", "\u2022 done"),
        ("reflow", None),
    ]


def test_terminal_assistant_stream_writer_reset_and_apply_state() -> None:
    writer = TerminalAssistantStreamWriter(
        wrap_width=lambda: 20,
        open_stream=lambda _prefix: None,
        write_delta=lambda _text: None,
        finish_projection=lambda projection: projection,
        finish_stream_reflow=lambda: None,
    )

    writer.handle_delta("active")
    assert writer.active is True

    writer.reset()
    assert writer.active is False

    writer.apply_state(TerminalAssistantStreamState(active=True, column=3, text="abc"))
    assert writer.active is True
    assert writer.state.text == "abc"


def test_streaming_agent_tail_cell_uses_bullet_then_continuation_prefixes() -> None:
    first = StreamingAgentTailCell.new(
        [HyperlinkLine.new(Line.from_text("tail"))],
        is_first_line=True,
    )
    continuation = StreamingAgentTailCell.new(
        [HyperlinkLine.new(Line.from_text("tail"))],
        is_first_line=False,
    )

    assert texts(first.display_lines(80)) == ["• tail"]
    assert texts(continuation.display_lines(80)) == ["  tail"]
    assert continuation.is_stream_continuation() is True


def test_agent_markdown_cell_renders_from_source_and_preserves_raw() -> None:
    cell = AgentMarkdownCell.new("see https://example.com", ".")

    assert texts(cell.raw_lines()) == ["see https://example.com"]
    links = cell.display_hyperlink_lines(80)
    assert hyperlink_texts(links) == ["• see https://example.com"]


def test_reasoning_summary_block_splits_header_only_when_summary_exists() -> None:
    visible = new_reasoning_summary_block("**Reasoning** useful detail", ".")
    transcript_only = new_reasoning_summary_block("no bold header", ".")

    assert visible.transcript_only is False
    assert texts(visible.raw_lines()) == [" useful detail"]
    assert texts(visible.display_lines(80)) == ["•  useful detail"]
    assert transcript_only.transcript_only is True
    assert transcript_only.raw_lines() == []
