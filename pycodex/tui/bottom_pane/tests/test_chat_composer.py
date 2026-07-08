import io

import pytest

from pycodex.tui.bottom_pane.chat_composer import (
    FOOTER_SPACING_HEIGHT,
    LARGE_PASTE_CHAR_THRESHOLD,
    MAX_USER_INPUT_TEXT_CHARS,
    ChatComposerConfig,
    ChatComposer,
    ChatComposerRenderSnapshot,
    ComposerDraftSnapshot,
    InputResult,
    KeyEvent,
    QueuedInputAction,
    TERMINAL_COMPOSER_INPUT_CONTINUE,
    TerminalComposerEffectRunner,
    TerminalComposerInputAction,
    TerminalComposerPromptReader,
    TerminalCommandPopupState,
    expand_pending_pastes,
    plan_mode_nudge_line,
    run_terminal_composer_blocking_line_prompt,
    run_terminal_composer_eof,
    run_terminal_composer_input_action,
    run_terminal_composer_interrupt,
    run_terminal_composer_prompt_loop,
    run_terminal_composer_read_prompt,
    run_terminal_composer_submit,
    run_terminal_composer_write_nonterminal_prompt,
    run_terminal_command_popup_input_action,
    terminal_command_popup_input_action,
    terminal_composer_draft_after_backspace,
    terminal_composer_draft_after_text,
    terminal_composer_draft_cleared,
    terminal_composer_input_action,
    terminal_composer_line_text,
    terminal_composer_projection,
    terminal_composer_submitted_line,
    terminal_popup_key,
    user_input_too_large_message,
)


def test_chat_composer_constants_and_large_input_message_match_rust_copy():
    assert LARGE_PASTE_CHAR_THRESHOLD == 1000
    assert FOOTER_SPACING_HEIGHT == 0
    assert user_input_too_large_message(123) == (
        f"Message exceeds the maximum length of {MAX_USER_INPUT_TEXT_CHARS} characters (123 provided)."
    )


def test_queued_input_action_variants_match_rust():
    assert [action.name for action in QueuedInputAction] == ["Plain", "ParseSlash", "RunShell"]


def test_input_result_variants_preserve_payload_shapes():
    submitted = InputResult.Submitted("hello", ["element"])
    assert submitted.kind == "Submitted"
    assert submitted.text == "hello"
    assert submitted.text_elements == ["element"]

    queued = InputResult.Queued("run", action=QueuedInputAction.RunShell)
    assert queued.kind == "Queued"
    assert queued.action is QueuedInputAction.RunShell

    assert InputResult.Command("Diff").command == "Diff"
    assert InputResult.ServiceTierCommand("fast").kind == "ServiceTierCommand"
    with_args = InputResult.CommandWithArgs("Plan", "investigate", ["rebased"])
    assert with_args.kind == "CommandWithArgs"
    assert with_args.args == "investigate"
    assert with_args.text_elements == ["rebased"]
    assert InputResult.None_().kind == "None"


def test_chat_composer_config_default_and_plain_text_match_rust_flags():
    assert ChatComposerConfig.default() == ChatComposerConfig(True, True, True)
    assert ChatComposerConfig.plain_text() == ChatComposerConfig(False, False, False)


def test_composer_draft_snapshot_preserves_attachment_and_pending_fields():
    snapshot = ComposerDraftSnapshot(
        text="hello",
        text_elements=["e"],
        local_images=["local.png"],
        remote_image_urls=["https://example.com/img.png"],
        mention_bindings=["mention"],
        pending_pastes=[("[Pasted]", "data")],
    )
    assert snapshot.text == "hello"
    assert snapshot.pending_pastes == [("[Pasted]", "data")]


def test_terminal_popup_key_maps_rust_like_payloads() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer handles popup key
    # routing after tui::event_stream has normalized key payloads.
    assert terminal_popup_key("down") == "down"
    assert terminal_popup_key("key", "up") == "up"
    assert terminal_popup_key("text", "\t") == "tab"
    assert terminal_popup_key("text", "\r") == "enter"
    assert terminal_popup_key("text", "你") == ""


def test_terminal_command_popup_input_action_plans_navigation_completion_and_command_view() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer routes popup keys to
    # command_popup selection, completion, or view-opening command actions.
    class SelectedCommand:
        def __init__(self, name: str) -> None:
            self._name = name

        def command(self) -> str:
            return self._name

    assert terminal_command_popup_input_action("/m", "up").kind == "move_up"
    assert terminal_command_popup_input_action("/m", "down").kind == "move_down"

    completion = terminal_command_popup_input_action("/m", "tab", selected_command=SelectedCommand("memories"))
    assert completion.kind == "complete"
    assert completion.draft == "/memories "

    no_selection = terminal_command_popup_input_action("/m", "tab")
    assert no_selection.kind == "handled"
    assert no_selection.draft == "/m"

    open_command_view = terminal_command_popup_input_action(
        "/model",
        "enter",
        selected_command=SelectedCommand("model"),
    )
    assert open_command_view.kind == "open_command_view"
    assert open_command_view.draft == ""
    assert open_command_view.command == "model"

    local_command = terminal_command_popup_input_action("/clear", "enter", selected_command=SelectedCommand("clear"))
    assert local_command.kind == "open_command_view"
    assert local_command.command == "clear"


def test_terminal_command_popup_state_syncs_draft_and_hides_for_active_view() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer::sync_popups owns the
    # command-popup lifecycle; command_popup owns filtering/selection internals.
    state = TerminalCommandPopupState.new()

    assert state.sync_draft("/m") is True
    assert state.visible is True
    assert state.selected_item().command() == "model"
    assert state.terminal_lines(width=80)[0].text.startswith("/model")

    state.move_down()
    assert state.selected_item().command() == "memories"

    assert state.sync_draft("hello") is False
    assert state.visible is False
    assert state.terminal_lines(width=80) == []

    assert state.sync_draft("/m", active_view_present=True) is False
    assert state.visible is False


def test_terminal_command_popup_runner_applies_navigation_completion_and_model_view() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer routes popup keys and
    # applies slash-popup outcomes before normal composer input. The terminal
    # adapter only supplies callbacks for concrete view creation/presentation.
    state = TerminalCommandPopupState.new()
    shown: list[object] = []
    params = object()

    assert state.sync_draft("/m") is True
    assert run_terminal_command_popup_input_action(state, "/m", "down") == "/m"
    assert state.selected_item().command() == "memories"
    assert run_terminal_command_popup_input_action(state, "/m", "tab") == "/memories "

    assert state.sync_draft("/model") is True
    assert (
        run_terminal_command_popup_input_action(
            state,
            "/model",
            "enter",
            open_command_view=lambda command: params if command == "model" else None,
            show_selection_view=shown.append,
        )
        == ""
    )
    assert shown == [params]

    assert state.sync_draft("/clear") is True
    assert run_terminal_command_popup_input_action(state, "/clear", "enter") is None
    assert (
        run_terminal_command_popup_input_action(
            state,
            "/clear",
            "enter",
            open_command_view=lambda command: None,
            show_selection_view=shown.append,
        )
        is None
    )
    assert shown == [params]


def test_terminal_command_popup_runner_ignores_keys_when_popup_hidden() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer::sync_popups owns
    # whether the command popup is active; terminal adapters should delegate
    # hidden-popup fallthrough to the composer owner instead of branching.
    state = TerminalCommandPopupState.new()

    assert state.visible is False
    assert run_terminal_command_popup_input_action(state, "/m", "down") is None


def test_terminal_composer_draft_helpers_match_text_only_product_path():
    # Rust owner: codex-tui::bottom_pane::chat_composer owns text draft
    # mutation before render. The real-terminal path uses this text-only slice.
    draft = terminal_composer_draft_cleared()

    draft, changed = terminal_composer_draft_after_text(draft, "hello\r\nthere")
    assert changed is True
    assert draft == "hello\nthere"

    draft, changed = terminal_composer_draft_after_text(draft, "")
    assert changed is False
    assert draft == "hello\nthere"

    assert terminal_composer_draft_after_backspace(draft) == "hello\nther"
    assert terminal_composer_draft_after_backspace("") == ""
    assert terminal_composer_submitted_line("hello") == "hello\n"


def test_terminal_composer_projection_owns_live_prompt_text_and_cursor_width() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer owns composer text
    # projection before terminal adapters adapt it into the live viewport.
    assert terminal_composer_line_text("hello\nthere") == "\u203a hello there"

    wide = terminal_composer_projection("你好", columns=20)
    clipped = terminal_composer_projection("你好", columns=5)
    empty = terminal_composer_projection("", columns=20)

    assert wide.line == "\u203a 你好"
    assert wide.cursor_column == 7
    assert clipped.line == "\u203a 你"
    assert clipped.cursor_column == 5
    assert empty.line == "\u203a "
    assert empty.cursor_column == 3


def test_terminal_composer_input_action_plans_text_only_terminal_events():
    # Rust owner: codex-tui::bottom_pane::chat_composer handles key input by
    # mutating draft state or returning a submitted input result. The Python
    # terminal path keeps that decision here while tui::tui executes repaint.
    assert terminal_composer_input_action("", "text", "hello\r\n") == TerminalComposerInputAction(
        "render",
        "hello\n",
    )
    assert terminal_composer_input_action("hello", "text", "") == TerminalComposerInputAction(
        "continue",
        "hello",
    )
    assert terminal_composer_input_action("好", "text", " ") == TerminalComposerInputAction(
        "render",
        "好 ",
    )
    assert terminal_composer_input_action("hello", "backspace") == TerminalComposerInputAction(
        "render",
        "hell",
    )
    assert terminal_composer_input_action("hello", "enter") == TerminalComposerInputAction(
        "submit",
        "",
        "hello\n",
    )
    assert terminal_composer_input_action("stale", "line", "/model\n") == TerminalComposerInputAction(
        "submit",
        "",
        "/model\n",
    )
    assert terminal_composer_input_action("hello", "eof") == TerminalComposerInputAction("eof", "")
    assert terminal_composer_input_action("hello", "interrupt") == TerminalComposerInputAction(
        "interrupt",
        "hello",
    )
    assert terminal_composer_input_action("hello", "resize") == TerminalComposerInputAction(
        "continue",
        "hello",
    )


def test_run_terminal_composer_input_action_dispatches_terminal_effects():
    # Rust owner: codex-tui::bottom_pane::chat_composer interprets composer
    # input outcomes. The terminal runner supplies concrete effects.
    calls: list[tuple[str, str | None]] = []

    def render() -> None:
        calls.append(("render", None))

    def submit(line: str) -> str:
        calls.append(("submit", line))
        return f"submitted:{line}"

    def interrupt() -> None:
        calls.append(("interrupt", None))
        raise KeyboardInterrupt

    def eof() -> None:
        calls.append(("eof", None))
        return None

    callbacks = {
        "render": render,
        "submit": submit,
        "interrupt": interrupt,
        "eof": eof,
    }

    assert (
        run_terminal_composer_input_action(TerminalComposerInputAction("render", "hello"), **callbacks)
        is TERMINAL_COMPOSER_INPUT_CONTINUE
    )
    assert (
        run_terminal_composer_input_action(TerminalComposerInputAction("continue", "hello"), **callbacks)
        is TERMINAL_COMPOSER_INPUT_CONTINUE
    )
    assert (
        run_terminal_composer_input_action(TerminalComposerInputAction("submit", "", "hello\n"), **callbacks)
        == "submitted:hello\n"
    )
    assert run_terminal_composer_input_action(TerminalComposerInputAction("eof", ""), **callbacks) is None
    with pytest.raises(KeyboardInterrupt):
        run_terminal_composer_input_action(TerminalComposerInputAction("interrupt", "hello"), **callbacks)

    assert calls == [
        ("render", None),
        ("submit", "hello\n"),
        ("eof", None),
        ("interrupt", None),
    ]


def test_terminal_composer_submit_eof_and_interrupt_effect_helpers():
    # Rust owner: codex-tui::bottom_pane::chat_composer owns composer submit,
    # EOF, and interrupt outcomes. The terminal runner supplies concrete
    # live-pane clearing but should not own these result semantics.
    calls: list[str] = []

    assert run_terminal_composer_submit(
        "hello\n",
        clear_bottom_pane=lambda: calls.append("clear-submit"),
    ) == "hello\n"
    assert run_terminal_composer_eof(
        clear_bottom_pane=lambda: calls.append("clear-eof"),
    ) is None
    with pytest.raises(KeyboardInterrupt):
        run_terminal_composer_interrupt()

    assert calls == ["clear-submit", "clear-eof"]


def test_terminal_composer_effect_runner_binds_prompt_submit_and_eof_callbacks() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer owns prompt
    # presentation plus submit/EOF effect semantics. terminal_runtime should
    # pass the bound runner methods instead of building prompt/submit/eof
    # wrappers locally.
    calls: list[str] = []
    writer = io.StringIO()
    runner = TerminalComposerEffectRunner(
        writer=writer,
        clear_bottom_pane=lambda: calls.append("clear"),
    )

    runner.write_nonterminal_prompt()
    assert runner.submit("hello\n") == "hello\n"
    assert runner.eof() is None
    assert writer.getvalue() == "\n\u203a "
    assert calls == ["clear", "clear"]


def test_terminal_composer_write_nonterminal_prompt_owns_fallback_prompt_text() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer owns the composer
    # fallback prompt presentation. terminal_runtime should delegate this
    # non-TTY prompt write instead of carrying the literal prompt string.
    writer = io.StringIO()

    run_terminal_composer_write_nonterminal_prompt(writer)

    assert writer.getvalue() == "\n\u203a "


def test_run_terminal_composer_prompt_loop_polls_and_submits_with_rendered_draft():
    # Rust owner: codex-tui::bottom_pane::chat_composer owns the prompt input
    # loop's draft/render/submit sequencing; tui::tui supplies the event source.
    class Source:
        def __init__(self) -> None:
            self.events = [
                None,
                type("Event", (), {"kind": "text", "text": "h"})(),
                type("Event", (), {"kind": "text", "text": "i"})(),
                type("Event", (), {"kind": "enter", "text": ""})(),
            ]

        def poll(self, timeout: float):
            assert timeout == 0.1
            return self.events.pop(0)

    drafts: list[str] = []
    renders: list[str] = []
    resizes = 0
    submissions: list[str] = []

    def apply_draft(draft: str) -> None:
        drafts.append(draft)

    def check_resize() -> None:
        nonlocal resizes
        resizes += 1

    def render() -> None:
        renders.append(drafts[-1])

    def submit(line: str) -> str:
        submissions.append(line)
        return line

    result = run_terminal_composer_prompt_loop(
        Source(),
        poll_timeout=0.1,
        apply_draft=apply_draft,
        check_resize=check_resize,
        render=render,
        submit=submit,
        interrupt=lambda: (_ for _ in ()).throw(KeyboardInterrupt),
        eof=lambda: None,
    )

    assert result == "hi\n"
    assert submissions == ["hi\n"]
    assert drafts == ["", "h", "hi", ""]
    assert renders == ["", "h", "hi"]
    assert resizes == 4


def test_run_terminal_composer_prompt_loop_skips_resize_events_before_input():
    # Rust owner: codex-tui::tui emits resize events while the composer remains
    # active; bottom_pane::chat_composer keeps waiting for input afterward.
    class Source:
        def __init__(self) -> None:
            self.events = [
                type("Event", (), {"kind": "resize", "text": ""})(),
                type("Event", (), {"kind": "line", "text": "/model\n"})(),
            ]

        def poll(self, timeout: float):
            return self.events.pop(0)

    drafts: list[str] = []
    resizes = 0

    def check_resize() -> None:
        nonlocal resizes
        resizes += 1

    result = run_terminal_composer_prompt_loop(
        Source(),
        poll_timeout=0.25,
        apply_draft=drafts.append,
        check_resize=check_resize,
        render=lambda: None,
        submit=lambda line: f"submitted:{line}",
        interrupt=lambda: (_ for _ in ()).throw(KeyboardInterrupt),
        eof=lambda: None,
    )

    assert result == "submitted:/model\n"
    assert drafts == ["", ""]
    assert resizes == 3


def test_run_terminal_composer_prompt_loop_routes_popup_keys_before_text_actions():
    # Rust owner: ChatComposer::handle_key_event routes key input to the active
    # popup before falling back to handle_key_event_without_popup.
    class Source:
        def __init__(self) -> None:
            self.events = [
                type("Event", (), {"kind": "text", "text": "/"})(),
                type("Event", (), {"kind": "text", "text": "m"})(),
                type("Event", (), {"kind": "down", "text": ""})(),
                type("Event", (), {"kind": "tab", "text": ""})(),
                type("Event", (), {"kind": "enter", "text": ""})(),
            ]

        def poll(self, timeout: float):
            return self.events.pop(0)

    drafts: list[str] = []
    renders: list[str] = []
    handled: list[tuple[str, str]] = []

    def apply_draft(draft: str) -> None:
        drafts.append(draft)

    def handle_key(draft: str, kind: str, text: str) -> str | None:
        handled.append((kind, draft))
        if kind == "down":
            return draft
        if kind == "tab":
            return "/memories "
        return None

    result = run_terminal_composer_prompt_loop(
        Source(),
        poll_timeout=0.1,
        apply_draft=apply_draft,
        check_resize=lambda: None,
        render=lambda: renders.append(drafts[-1]),
        submit=lambda line: line,
        interrupt=lambda: (_ for _ in ()).throw(KeyboardInterrupt),
        eof=lambda: None,
        handle_key=handle_key,
    )

    assert result == "/memories \n"
    assert handled == [
        ("text", ""),
        ("text", "/"),
        ("down", "/m"),
        ("tab", "/m"),
        ("enter", "/memories "),
    ]
    assert renders == ["", "/", "/m", "/m", "/memories "]
    assert drafts == ["", "/", "/m", "/memories ", ""]


def test_run_terminal_composer_blocking_line_prompt_preserves_fallback_sequence():
    # Rust owner: codex-tui::bottom_pane::chat_composer owns composer prompt
    # lifecycle; tui::tui supplies blocking stdin fallback and terminal effects.
    calls: list[tuple[str, str | None]] = []

    line = run_terminal_composer_blocking_line_prompt(
        read_line=lambda: "hello\n",
        apply_draft=lambda draft: calls.append(("draft", draft)),
        render=lambda: calls.append(("render", None)),
        check_resize=lambda: calls.append(("resize", None)),
        clear_bottom_pane=lambda: calls.append(("clear", None)),
    )

    assert line == "hello\n"
    assert calls == [
        ("draft", ""),
        ("render", None),
        ("resize", None),
        ("clear", None),
    ]


def test_run_terminal_composer_blocking_line_prompt_maps_eof_to_none():
    calls: list[str] = []

    line = run_terminal_composer_blocking_line_prompt(
        read_line=lambda: "",
        apply_draft=lambda draft: calls.append(f"draft:{draft}"),
        render=lambda: calls.append("render"),
        check_resize=lambda: calls.append("resize"),
        clear_bottom_pane=lambda: calls.append("clear"),
    )

    assert line is None
    assert calls == ["draft:", "render", "resize", "clear"]


def test_run_terminal_composer_read_prompt_uses_nonterminal_line_prompt():
    # Rust owner: codex-tui::bottom_pane::chat_composer owns prompt input
    # lifecycle; tui::tui supplies non-terminal stdin/stdout effects.
    calls: list[str] = []

    result = run_terminal_composer_read_prompt(
        terminal_active=False,
        get_input_source=lambda: (_ for _ in ()).throw(AssertionError("unused source")),
        read_line=lambda: "hello\n",
        write_nonterminal_prompt=lambda: calls.append("prompt"),
        apply_draft=lambda draft: calls.append(f"draft:{draft}"),
        check_resize=lambda: calls.append("resize"),
        render=lambda: calls.append("render"),
        clear_bottom_pane=lambda: calls.append("clear"),
        submit=lambda line: line,
        interrupt=lambda: None,
        eof=lambda: None,
    )

    assert result == "hello\n"
    assert calls == ["prompt"]


def test_run_terminal_composer_read_prompt_uses_blocking_fallback_without_input_source():
    calls: list[str] = []

    result = run_terminal_composer_read_prompt(
        terminal_active=True,
        get_input_source=lambda: None,
        read_line=lambda: "fallback\n",
        write_nonterminal_prompt=lambda: calls.append("prompt"),
        apply_draft=lambda draft: calls.append(f"draft:{draft}"),
        check_resize=lambda: calls.append("resize"),
        render=lambda: calls.append("render"),
        clear_bottom_pane=lambda: calls.append("clear"),
        submit=lambda line: f"submitted:{line}",
        interrupt=lambda: None,
        eof=lambda: None,
    )

    assert result == "fallback\n"
    assert calls == ["draft:", "render", "resize", "clear"]


def test_run_terminal_composer_read_prompt_uses_event_source_when_available():
    class Source:
        def __init__(self) -> None:
            self.events = [
                type("Event", (), {"kind": "text", "text": "o"})(),
                type("Event", (), {"kind": "enter", "text": ""})(),
            ]

        def poll(self, timeout: float):
            assert timeout == 0.2
            return self.events.pop(0)

    calls: list[str] = []

    result = run_terminal_composer_read_prompt(
        terminal_active=True,
        get_input_source=Source,
        read_line=lambda: (_ for _ in ()).throw(AssertionError("unused line reader")),
        write_nonterminal_prompt=lambda: calls.append("prompt"),
        apply_draft=lambda draft: calls.append(f"draft:{draft}"),
        check_resize=lambda: calls.append("resize"),
        render=lambda: calls.append("render"),
        clear_bottom_pane=lambda: calls.append("clear"),
        submit=lambda line: f"submitted:{line}",
        interrupt=lambda: None,
        eof=lambda: None,
        poll_timeout=0.2,
    )

    assert result == "submitted:o\n"
    assert calls == ["draft:", "render", "resize", "draft:o", "render", "resize", "draft:"]


def test_terminal_composer_prompt_reader_binds_runtime_callbacks() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer owns the terminal
    # prompt input lifecycle. terminal_runtime should consume a bound reader
    # instead of assembling read-prompt callbacks at the call site.
    class Source:
        def __init__(self) -> None:
            self.events = [
                type("Event", (), {"kind": "text", "text": "o"})(),
                type("Event", (), {"kind": "enter", "text": ""})(),
            ]

        def poll(self, timeout: float):
            calls.append(f"poll:{timeout}")
            return self.events.pop(0)

    calls: list[str] = []
    reader = TerminalComposerPromptReader(
        terminal_active=lambda: True,
        get_input_source=Source,
        read_line=lambda: (_ for _ in ()).throw(AssertionError("unused line reader")),
        write_nonterminal_prompt=lambda: calls.append("prompt"),
        apply_draft=lambda draft: calls.append(f"draft:{draft}"),
        check_resize=lambda: calls.append("resize"),
        render=lambda: calls.append("render"),
        clear_bottom_pane=lambda: calls.append("clear"),
        submit=lambda line: f"submitted:{line}",
        interrupt=lambda: calls.append("interrupt"),
        eof=lambda: calls.append("eof"),
        poll_timeout=0.2,
    )

    assert reader.read() == "submitted:o\n"
    assert calls == [
        "draft:",
        "render",
        "poll:0.2",
        "resize",
        "draft:o",
        "render",
        "poll:0.2",
        "resize",
        "draft:",
    ]


def test_plan_mode_nudge_line_keeps_visible_actions():
    line = " ".join(plan_mode_nudge_line())
    assert "Create a plan?" in line
    assert "Plan mode" in line
    assert "dismiss" in line


def test_handle_key_event_short_circuits_disabled_and_release_events():
    # Rust: codex-tui bottom_pane/chat_composer.rs ChatComposer::handle_key_event
    # returns (InputResult::None, false) before popup sync when input is disabled
    # or when crossterm reports KeyEventKind::Release.
    disabled = ChatComposer(input_enabled=False)
    result, handled = disabled.handle_key_event(KeyEvent.char_event("x"))
    assert result.kind == "None"
    assert handled is False
    assert disabled.dispatch_log == []
    assert disabled.sync_count == 0

    composer = ChatComposer()
    result, handled = composer.handle_key_event(KeyEvent.char_event("x", kind="release"))
    assert result.kind == "None"
    assert handled is False
    assert composer.dispatch_log == []
    assert composer.sync_count == 0


def test_handle_key_event_prioritizes_history_search_without_popup_sync():
    # Rust: existing history search handles the key directly, and the configured
    # history-search binding begins search before active popup dispatch.
    active = ChatComposer(history_search_active=True, active_popup="command")
    result, handled = active.handle_key_event(KeyEvent.char_event("a"))
    assert result.kind == "None"
    assert handled is False
    assert active.dispatch_log == ["history_search"]
    assert active.sync_count == 0

    composer = ChatComposer(active_popup="command")
    result, handled = composer.handle_key_event(KeyEvent.char_event("r", modifiers=("control",)))
    assert result.kind == "None"
    assert handled is True
    assert composer.history_search_active is True
    assert composer.dispatch_log == ["begin_history_search"]
    assert composer.sync_count == 0


def test_handle_key_event_dispatches_active_popup_then_syncs_popups():
    # Rust: active popup variants dispatch to popup-specific handlers, then
    # reset_vim_mode_after_successful_dispatch and sync_popups run once.
    composer = ChatComposer(
        active_popup="command",
        handlers={"slash_popup": lambda _event: (InputResult.Command("Diff"), True)},
    )
    result, handled = composer.handle_key_event(KeyEvent.key("enter"))
    assert result.kind == "Command"
    assert result.command == "Diff"
    assert handled is True
    assert composer.dispatch_log == ["slash_popup"]
    assert composer.reset_vim_count == 1
    assert composer.sync_count == 1


def test_handle_key_event_without_popup_supports_plain_text_submit_boundary():
    # Rust: when no popup is active, the top-level handler delegates to
    # handle_key_event_without_popup; detailed editing remains textarea.rs.
    composer = ChatComposer()
    result, handled = composer.handle_key_event(KeyEvent.char_event("h"))
    assert result.kind == "None"
    assert handled is True
    assert composer.dispatch_log == ["without_popup"]
    assert composer.sync_count == 1

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))
    assert result == InputResult.Submitted("h")
    assert handled is True
    assert composer.dispatch_log == ["without_popup", "without_popup"]
    assert composer.sync_count == 2


def test_shift_enter_inserts_newline_without_submitting():
    # Rust source: codex-tui::bottom_pane::chat_composer::handle_key_event_without_popup.
    # Rust test: chatwidget/tests/composer_submission.rs
    # shift_enter_with_only_remote_images_does_not_submit_user_turn.
    # Contract: only plain Enter is a submit key; Shift+Enter is textarea input.
    composer = ChatComposer()
    composer.handle_key_event(KeyEvent.char_event("a"))

    result, handled = composer.handle_key_event(KeyEvent.key("enter", modifiers=("shift",)))

    assert result.kind == "None"
    assert handled is True
    assert composer.render().text == "a\n"
    assert composer.dispatch_log == ["without_popup", "without_popup"]

    result, handled = composer.handle_key_event(KeyEvent.char_event("b"))
    assert result.kind == "None"
    assert handled is True

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))
    assert result == InputResult.Submitted("a\nb")
    assert handled is True


def test_enter_with_only_remote_images_submits_empty_text_boundary():
    # Rust test: chatwidget/tests/composer_submission.rs
    # enter_with_only_remote_images_submits_user_turn, plus
    # chat_composer.rs::prepare_submission_with_only_remote_images_returns_empty_text.
    composer = ChatComposer(remote_image_urls=["https://example.com/remote-only.png"])

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))

    assert result == InputResult.Submitted("")
    assert handled is True
    assert composer.current_text() == ""


def test_shift_enter_with_only_remote_images_does_not_submit():
    # Rust test: chatwidget/tests/composer_submission.rs
    # shift_enter_with_only_remote_images_does_not_submit_user_turn.
    composer = ChatComposer(remote_image_urls=["https://example.com/remote-only.png"])

    result, handled = composer.handle_key_event(KeyEvent.key("enter", modifiers=("shift",)))

    assert result.kind == "None"
    assert handled is True
    assert composer.remote_image_urls == ["https://example.com/remote-only.png"]


def test_enter_with_only_remote_images_does_not_submit_when_modal_active_or_disabled():
    # Rust tests:
    # enter_with_only_remote_images_does_not_submit_when_modal_is_active
    # enter_with_only_remote_images_does_not_submit_when_input_disabled.
    modal = ChatComposer(active_popup="review", remote_image_urls=["https://example.com/remote-only.png"])
    result, handled = modal.handle_key_event(KeyEvent.key("enter"))
    assert result.kind == "None"
    assert handled is False
    assert modal.remote_image_urls == ["https://example.com/remote-only.png"]

    disabled = ChatComposer(input_enabled=False, remote_image_urls=["https://example.com/remote-only.png"])
    result, handled = disabled.handle_key_event(KeyEvent.key("enter"))
    assert result.kind == "None"
    assert handled is False
    assert disabled.remote_image_urls == ["https://example.com/remote-only.png"]


def test_empty_enter_during_task_does_not_submit_or_queue():
    # Rust test: chatwidget/tests/composer_submission.rs
    # empty_enter_during_task_does_not_queue.
    composer = ChatComposer(is_task_running=True)

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))

    assert result.kind == "None"
    assert handled is False
    assert composer.current_text() == ""


def test_large_paste_placeholder_expands_on_submit_and_clears_pending_state():
    # Rust tests: chat_composer.rs handle_paste_large_uses_placeholder_and_replaces_on_submit,
    # current_text_with_pending_expands_placeholders, and test_multiple_pastes_submission.
    payload = "x" * (LARGE_PASTE_CHAR_THRESHOLD + 1)
    composer = ChatComposer()

    assert composer.handle_paste(payload) is True
    assert composer.current_text() == f"[Pasted Content {len(payload)} chars]"
    assert composer.current_text_with_pending() == payload

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))

    assert result == InputResult.Submitted(payload, composer.text_elements)
    assert handled is True
    assert composer.current_text() == ""
    assert composer.pending_pastes_value() == []


def test_pending_paste_expansion_is_fifo_and_normalizes_crlf():
    # Rust tests: current_text_with_pending_expands_overlapping_placeholders
    # and pasted_crlf_normalizes_newlines_for_elements.
    composer = ChatComposer()
    first = "a" * (LARGE_PASTE_CHAR_THRESHOLD + 4)
    second = "b\r\nc"

    composer.handle_paste(first)
    composer.handle_paste(second)

    assert composer.current_text_with_pending() == first + "b\nc"


def test_prepare_submission_rejects_expanded_input_over_limit_without_clearing_draft():
    # Rust tests: oversized direct and pending-paste submissions emit
    # user_input_too_large_message and suppress submission.
    placeholder = "[Pasted Content oversized chars]"
    payload = "x" * (MAX_USER_INPUT_TEXT_CHARS + 1)
    composer = ChatComposer(text=placeholder, pending_pastes=[(placeholder, payload)])

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))

    assert result.kind == "None"
    assert handled is True
    assert composer.current_text() == placeholder
    assert composer.pending_pastes_value() == [(placeholder, payload)]
    assert composer.errors == [user_input_too_large_message(len(payload))]


def test_expand_pending_pastes_replaces_placeholders_once_in_order():
    # Rust source: ChatComposer::expand_pending_pastes walks pending placeholders
    # in order so duplicate-sized large pastes preserve FIFO payload mapping.
    text, elements = expand_pending_pastes(
        "<paste><paste>",
        [{"range": (0, 7), "placeholder": "<paste>"}],
        [("<paste>", "first"), ("<paste>", "second")],
    )

    assert text == "firstsecond"
    assert elements == [{"range": (0, 7), "placeholder": "<paste>"}]


def test_render_delegates_to_masked_render_and_returns_semantic_snapshot():
    # Rust: WidgetRef::render calls render_with_mask(..., None), which delegates
    # to render_with_mask_and_textarea_right_reserve(..., 0).
    composer = ChatComposer(text="secret", remote_image_urls=["https://example.com/a.png"], footer=["? for shortcuts"])
    buf = []
    snapshot = composer.render(area=(0, 0, 40, 6), buf=buf)
    assert isinstance(snapshot, ChatComposerRenderSnapshot)
    assert snapshot.text == "secret"
    assert snapshot.mask_char is None
    assert snapshot.textarea_right_reserve == 0
    assert snapshot.remote_image_urls == ("https://example.com/a.png",)
    assert snapshot.footer == ("? for shortcuts",)
    assert buf == [snapshot]
    assert composer.render_log == [("render_with_mask_and_textarea_right_reserve", (0, 0, 40, 6), None, 0)]

    masked = composer.render_with_mask(area=(0, 0, 40, 6), mask_char="*")
    assert masked.text == "******"
    assert masked.mask_char == "*"
