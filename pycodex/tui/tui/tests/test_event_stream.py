"""Parity tests for Rust ``codex-tui::tui::event_stream``.

Rust source: ``codex/codex-rs/tui/src/tui/event_stream.rs``.
"""

import io
from collections import deque

import pycodex.tui.tui.event_stream as event_stream
from pycodex.tui.tui.event_stream import (
    EventBroker,
    EventBrokerState,
    FakeEventSource,
    FakeEventSourceHandle,
    FocusFlag,
    LineTerminalInputSource,
    SelectTerminalInputSource,
    StringTerminalInputSource,
    TerminalInputSourceProvider,
    TerminalTurnEventLoopRunner,
    TerminalTurnIdleTicker,
    TuiEvent,
    WindowsConsoleInputSource,
    WindowsConsoleEventSource,
    get_or_make_terminal_input_source,
    make_terminal_input_source,
    make_stream,
    poll_terminal_turn_event,
    run_terminal_turn_idle_tick,
    run_terminal_turn_event_loop,
    setup,
    terminal_stdin_is_terminal,
    terminal_turn_event_stream_closed,
)


def test_key_event_skips_unmapped() -> None:
    # Rust: key_event_skips_unmapped.
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)

    handle.send(("focus_lost", None))
    handle.send(("key", "a"))

    assert stream.poll_next() == TuiEvent.key("a")
    assert terminal_focused.value is False


def test_draw_and_key_events_yield_both() -> None:
    # Rust: draw_and_key_events_yield_both.
    broker, handle, draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)

    draw_tx.send()
    handle.send(("key", "a"))

    events = [stream.poll_next(), stream.poll_next()]
    assert TuiEvent.draw() in events
    assert TuiEvent.key("a") in events


def test_lagged_draw_maps_to_draw() -> None:
    # Rust: lagged_draw_maps_to_draw.
    broker, _handle, draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)

    draw_tx.send(lagged=True)

    assert stream.poll_next() == TuiEvent.draw()


def test_resize_event_maps_to_resize() -> None:
    # Rust: resize_event_maps_to_resize.
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)

    handle.send(("resize", (80, 24)))

    assert stream.poll_next() == TuiEvent.resize()


def test_ctrl_u_maps_to_rust_composer_kill_line_event() -> None:
    # Fixed Rust owner/evidence: bottom_pane::textarea uses Ctrl-U for
    # kill-to-beginning-of-line; tui::event_stream must preserve the key.
    assert event_stream.terminal_event_from_char("\x15") == event_stream.TerminalInputEvent("ctrl_u")


def test_paste_and_focus_gained_mapping() -> None:
    # Rust: map_crossterm_event maps Paste and FocusGained to TuiEvent variants.
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    terminal_focused.set(False)
    stream = make_stream(broker, draw_rx, terminal_focused)

    handle.send(("paste", "hello"))
    handle.send(("focus_gained", None))

    assert stream.poll_next() == TuiEvent.paste("hello")
    assert stream.poll_next() == TuiEvent.draw()
    assert terminal_focused.value is True


def test_error_or_eof_ends_stream() -> None:
    # Rust: error_or_eof_ends_stream.
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)

    handle.send(OSError("boom"))

    assert stream.poll_next() is None
    assert stream.ended is True
    assert broker.state is EventBrokerState.START


def test_resume_wakes_paused_stream() -> None:
    # Rust: resume_wakes_paused_stream.
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)

    broker.pause_events()
    assert stream.poll_next() is None

    broker.resume_events()
    handle.send(("key", "r"))

    assert stream.poll_next() == TuiEvent.key("r")


def test_resume_wakes_pending_stream() -> None:
    # Rust: resume_wakes_pending_stream.
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)

    assert stream.poll_next() is None
    broker.pause_events()
    broker.resume_events()
    handle.send(("key", "p"))

    assert stream.poll_next() == TuiEvent.key("p")


def test_pause_drops_source_and_ignores_sends_until_resume() -> None:
    # Rust: FakeEventSourceHandle::send is a no-op while the broker is Paused.
    broker = EventBroker.new(FakeEventSource)
    handle = FakeEventSourceHandle.new(broker)
    stream = make_stream(broker, terminal_focused=FocusFlag(True))

    broker.pause_events()
    handle.send(("key", "x"))
    assert stream.poll_next() is None

    broker.resume_events()
    handle.send(("key", "y"))
    assert stream.poll_next() == TuiEvent.key("y")


def test_windows_console_source_maps_chars_and_special_keys_through_event_stream() -> None:
    # Rust source contract:
    # - codex-tui::tui::event_stream maps Event::Key through TuiEvent::Key.
    # - Python's Windows product path keeps msvcrt polling behind EventSource
    #   instead of letting the app/composer layer consume raw terminal bytes.
    class FakeMsvcrt:
        def __init__(self) -> None:
            self.chars = list("a") + ["\xe0", "K"] + list("b")

        def kbhit(self) -> bool:
            return bool(self.chars)

        def getwch(self) -> str:
            return self.chars.pop(0)

    source = WindowsConsoleEventSource(FakeMsvcrt())
    broker = EventBroker.new(lambda: source)
    stream = make_stream(broker, terminal_focused=FocusFlag(True))

    assert stream.poll_next() == TuiEvent.key("a")
    assert stream.poll_next() == TuiEvent.key("left")
    assert stream.poll_next() == TuiEvent.key("b")
    assert stream.poll_next() is None


def test_windows_console_source_maps_virtual_return_without_unicode_char() -> None:
    # Rust source/product contract:
    # - codex-tui::tui::event_stream receives crossterm KeyCode::Enter from
    #   Windows console input records, not only from UnicodeChar payloads.
    # - Windows Terminal/IME can deliver VK_RETURN with an empty UnicodeChar;
    #   Python must still surface it as the composer submit key.
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": True, "virtual_key": 0x0D, "char": ""},
    ]

    source = WindowsConsoleEventSource(FakeMsvcrt(), console_record_reader=lambda: records.pop(0) if records else None)
    broker = EventBroker.new(lambda: source)
    stream = make_stream(broker, terminal_focused=FocusFlag(True))

    assert stream.poll_next() == TuiEvent.key("\r")
    assert stream.poll_next() is None


def test_windows_console_source_maps_virtual_arrow_with_nul_unicode_char() -> None:
    # Rust source/product contract:
    # - crossterm reports arrow keys as key codes even when Windows console
    #   records carry a NUL UnicodeChar.
    # - The terminal composer must receive a normalized navigation event so
    #   bottom_pane command/list popups can move their selected row.
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": True, "virtual_key": 0x28, "char": "\x00"},
    ]

    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert source.poll(0.0) == event_stream.TerminalInputEvent("down")
    assert source.poll(0.0) is None


def test_windows_console_source_maps_all_transcript_pager_virtual_keys() -> None:
    """Rust tui::event_stream preserves Windows navigation keys for PagerView."""

    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used")

    records = [
        {"kind": "key", "key_down": True, "virtual_key": code, "char": "\x00"}
        for code in (0x26, 0x28, 0x21, 0x22, 0x24, 0x23)
    ]
    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert [source.poll(0.0) for _ in range(6)] == [
        event_stream.TerminalInputEvent("up"),
        event_stream.TerminalInputEvent("down"),
        event_stream.TerminalInputEvent("page_up"),
        event_stream.TerminalInputEvent("page_down"),
        event_stream.TerminalInputEvent("home"),
        event_stream.TerminalInputEvent("end"),
    ]


def test_windows_console_source_maps_virtual_space_with_nul_unicode_char_to_text() -> None:
    # Rust source/product contract:
    # - codex-tui::tui::event_stream treats Space as an ordinary text key when
    #   it is not a popup/navigation binding.
    # - Windows Terminal/IME can deliver VK_SPACE with an empty UnicodeChar
    #   while committing or continuing Chinese input; it must not be dropped
    #   before bottom_pane::chat_composer mutates the draft.
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": True, "virtual_key": 0x20, "char": "\x00"},
    ]

    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", " ")
    assert source.poll(0.0) is None


def test_windows_console_source_preserves_ime_committed_char_on_key_up_record() -> None:
    # Rust source/product contract:
    # - crossterm surfaces committed IME characters as text key events before
    #   bottom_pane::chat_composer mutates the draft.
    # - Windows console records can carry a committed non-ASCII IME character
    #   on a key-up/VK_PACKET or VK_PROCESSKEY record; dropping every key-up
    #   record makes later Chinese characters disappear from the composer.
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": True, "virtual_key": 0xE7, "char": "你"},
        {"kind": "key", "key_down": False, "virtual_key": 0xE7, "char": "好"},
    ]

    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "你")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "好")
    assert source.poll(0.0) is None


def test_windows_console_source_deduplicates_ime_committed_char_key_up_echo() -> None:
    # Rust source/product contract:
    # - crossterm yields one text key event for one committed IME character.
    # - Some Windows console hosts expose both key-down and key-up records with
    #   the same committed UnicodeChar. The event stream must not forward both
    #   records to chat_composer, or typing "你好" appears as "你你好好".
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": True, "virtual_key": 0xE7, "char": "你"},
        {"kind": "key", "key_down": False, "virtual_key": 0xE7, "char": "你"},
        {"kind": "key", "key_down": True, "virtual_key": 0xE7, "char": "好"},
        {"kind": "key", "key_down": False, "virtual_key": 0xE7, "char": "好"},
    ]

    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "你")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "好")
    assert source.poll(0.0) is None


def test_windows_console_source_deduplicates_ime_multichar_key_up_echo() -> None:
    # Rust source/product contract:
    # - one committed IME string should become one text event. Some Windows
    #   hosts surface the committed string on both key-down and key-up records.
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": True, "virtual_key": 0xE7, "char": "你好"},
        {"kind": "key", "key_down": False, "virtual_key": 0xE7, "char": "你好"},
    ]

    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "你好")
    assert source.poll(0.0) is None


def test_windows_console_source_ignores_ascii_key_up_char_to_avoid_double_input() -> None:
    # Rust source/product contract:
    # - tui::event_stream should not turn ordinary key release records into
    #   duplicate typed characters. The key-up escape hatch exists only for
    #   IME/non-ASCII committed text that would otherwise be lost.
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": False, "virtual_key": ord("a"), "char": "a"},
    ]

    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert source.poll(0.0) is None


def test_windows_console_source_ignores_ime_confirmation_space_key_up() -> None:
    # Rust owner/source: codex-tui::tui::event_stream,
    # codex/codex-rs/tui/src/tui/event_stream.rs. Crossterm supplies one
    # logical Key event for one committed terminal key action.
    # - Windows Terminal emits a VK_SPACE key-up record after Space confirms
    #   an IME candidate. That release is not user text and must not append a
    #   synthetic space to the composer draft.
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": False, "virtual_key": 0x20, "char": " "},
    ]

    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert source.poll(0.0) is None


def test_windows_console_source_projects_traced_chinese_commit_without_spaces() -> None:
    # Rust owner/source: codex-tui::tui::event_stream,
    # codex/codex-rs/tui/src/tui/event_stream.rs. This is the Windows Terminal
    # record sequence captured for committing "你好": each committed character
    # has a key-down/key-up pair, followed by an IME-confirmation Space release.
    # It must project to exactly the two committed text events.
    class FakeMsvcrt:
        def kbhit(self) -> bool:
            return False

        def getwch(self) -> str:
            raise AssertionError("console record path should be used before msvcrt fallback")

    records = [
        {"kind": "key", "key_down": True, "virtual_key": 0, "char": "你"},
        {"kind": "key", "key_down": False, "virtual_key": 0, "char": "你"},
        {"kind": "key", "key_down": True, "virtual_key": 0, "char": "好"},
        {"kind": "key", "key_down": False, "virtual_key": 0, "char": "好"},
        {"kind": "key", "key_down": False, "virtual_key": 0x20, "char": " "},
    ]

    source = WindowsConsoleInputSource(
        FakeMsvcrt(),
        console_record_reader=lambda: records.pop(0) if records else None,
    )

    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "你")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "好")
    assert source.poll(0.0) is None


def test_windows_console_source_maps_ansi_arrow_sequence_to_navigation_event() -> None:
    # Rust source/product contract:
    # - terminal escape sequences are normalized at tui::event_stream before
    #   chat_composer / bottom_pane popup handling sees them.
    # - This protects the frame-based bottom pane from terminal-specific
    #   escape bytes such as ESC [ B for Down.
    class FakeMsvcrt:
        def __init__(self) -> None:
            self.chars = ["\x1b", "[", "B"]

        def kbhit(self) -> bool:
            return bool(self.chars)

        def getwch(self) -> str:
            return self.chars.pop(0)

    source = WindowsConsoleInputSource(FakeMsvcrt())

    assert source.poll(0.0) == event_stream.TerminalInputEvent("down")
    assert source.poll(0.0) is None


def test_windows_console_source_maps_escape_prefixed_char_to_alt_key() -> None:
    # Rust source/test contract:
    # - codex-tui::keymap default_bindings maps app.toggle_raw_output to
    #   Alt+R, and tui::event_stream preserves key modifiers from crossterm.
    # - Python's Windows console source receives Alt+letter as an ESC-prefixed
    #   byte pair under ConPTY and must preserve the Alt modifier before the
    #   app keymap layer consumes it.
    class FakeMsvcrt:
        def __init__(self) -> None:
            self.chars = ["\x1b", "r"]

        def kbhit(self) -> bool:
            return bool(self.chars)

        def getwch(self) -> str:
            return self.chars.pop(0)

    source = WindowsConsoleEventSource(FakeMsvcrt())
    broker = EventBroker.new(lambda: source)
    stream = make_stream(broker, terminal_focused=FocusFlag(True))

    assert stream.poll_next() == TuiEvent.key("alt-r")
    assert stream.poll_next() is None


def test_windows_console_source_keeps_repeated_escape_as_two_escape_keys() -> None:
    # Rust source contract:
    # - crossterm EventStream yields Esc key events independently unless a real
    #   modified key is reported by the terminal.
    # - Python's Windows ESC-prefix adapter must not collapse Esc Esc into one
    #   key while trying to preserve Alt+letter.
    class FakeMsvcrt:
        def __init__(self) -> None:
            self.chars = ["\x1b", "\x1b"]

        def kbhit(self) -> bool:
            return bool(self.chars)

        def getwch(self) -> str:
            return self.chars.pop(0)

    source = WindowsConsoleEventSource(FakeMsvcrt())
    broker = EventBroker.new(lambda: source)
    stream = make_stream(broker, terminal_focused=FocusFlag(True))

    assert stream.poll_next() == TuiEvent.key("\x1b")
    assert stream.poll_next() == TuiEvent.key("\x1b")
    assert stream.poll_next() is None


def test_make_terminal_input_source_uses_string_source_for_stringio() -> None:
    # Rust source contract:
    # - tui::event_stream owns conversion from terminal input source to
    #   app-facing events. The terminal runner should not choose the concrete
    #   input adapter itself.
    source = make_terminal_input_source(io.StringIO("a"))

    assert isinstance(source, StringTerminalInputSource)
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "a")


def test_terminal_ctrl_t_maps_to_global_transcript_event() -> None:
    """Rust codex-tui::app::input maps Global.open_transcript before composer input."""

    assert event_stream.terminal_event_from_char("\x14") == event_stream.TerminalInputEvent("ctrl_t")


def test_terminal_stdin_is_terminal_owns_runtime_tty_probe() -> None:
    # Rust source contract:
    # - codex-tui::tui::event_stream owns the terminal input-source boundary.
    # - Python's product adapter keeps host-specific stdin probes here so
    #   terminal_runtime only consumes the event-stream decision.
    class TtyStdin:
        def isatty(self) -> bool:
            return True

    class NonTtyStdin:
        def isatty(self) -> bool:
            return False

    class BrokenTtyStdin:
        def isatty(self) -> bool:
            raise OSError("detached")

    class MissingIsatty:
        pass

    assert terminal_stdin_is_terminal(TtyStdin()) is True
    assert terminal_stdin_is_terminal(NonTtyStdin()) is False
    assert terminal_stdin_is_terminal(BrokenTtyStdin()) is False
    assert terminal_stdin_is_terminal(MissingIsatty()) is False


def test_get_or_make_terminal_input_source_reuses_existing_source() -> None:
    # Rust source contract:
    # - EventBrokerState::Running reuses the active input source instead of
    #   rebuilding it for each consumer poll.
    existing = StringTerminalInputSource(io.StringIO("x"))

    source = get_or_make_terminal_input_source(existing, io.StringIO("y"))

    assert source is existing
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "x")


def test_get_or_make_terminal_input_source_creates_when_absent() -> None:
    # Rust source contract:
    # - EventBrokerState::Start creates the input source lazily on first use.
    source = get_or_make_terminal_input_source(None, io.StringIO("z"))

    assert isinstance(source, StringTerminalInputSource)
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "z")


def test_terminal_input_source_provider_caches_active_source() -> None:
    # Rust source contract:
    # - EventBrokerState owns the active input source slot. The terminal runner
    #   should ask event_stream for the active source instead of storing the
    #   slot itself.
    provider = TerminalInputSourceProvider(io.StringIO("ab"))

    first = provider.get()
    second = provider.get()

    assert first is second
    assert first is not None
    assert first.poll(0.0) == event_stream.TerminalInputEvent("text", "a")
    assert second.poll(0.0) == event_stream.TerminalInputEvent("text", "b")


def test_make_terminal_input_source_uses_windows_console_source(monkeypatch) -> None:
    monkeypatch.setattr(event_stream.os, "name", "nt")
    created: list[dict[str, object]] = []

    class FakeWindowsConsoleInputSource:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    class FakeStdin:
        pass

    monkeypatch.setattr(event_stream, "WindowsConsoleInputSource", FakeWindowsConsoleInputSource)

    source = make_terminal_input_source(FakeStdin())

    assert isinstance(source, FakeWindowsConsoleInputSource)
    assert created == [{"console_handle": None}]


def test_terminal_input_event_from_key_payload_maps_text_and_control_keys() -> None:
    # Rust source contract:
    # - codex-tui::tui::event_stream emits one Key stream where non-ASCII
    #   chars, Enter, Tab, and navigation keys all reach chat_composer.
    assert event_stream.terminal_input_event_from_key_payload("你") == event_stream.TerminalInputEvent("text", "你")
    assert event_stream.terminal_input_event_from_key_payload("好") == event_stream.TerminalInputEvent("text", "好")
    assert event_stream.terminal_input_event_from_key_payload("你好") == event_stream.TerminalInputEvent("text", "你好")
    assert event_stream.terminal_input_event_from_key_payload("好 ") == event_stream.TerminalInputEvent("text", "好 ")
    assert event_stream.terminal_input_event_from_key_payload(" ") == event_stream.TerminalInputEvent("text", " ")
    assert event_stream.terminal_input_event_from_key_payload("space") == event_stream.TerminalInputEvent("text", " ")
    assert event_stream.terminal_input_event_from_key_payload("\r") == event_stream.TerminalInputEvent("enter")
    assert event_stream.terminal_input_event_from_key_payload("down") == event_stream.TerminalInputEvent("down")
    assert event_stream.terminal_input_event_from_key_payload("\t") == event_stream.TerminalInputEvent("tab")
    assert event_stream.terminal_input_event_from_key_payload("alt-r") is None


def test_terminal_input_event_from_event_result_maps_rust_like_events() -> None:
    # Rust source contract:
    # - event_stream normalizes crossterm-like key/resize/paste payloads before
    #   the bottom pane interprets them.
    assert event_stream.terminal_input_event_from_event_result(TuiEvent.key("你")) == event_stream.TerminalInputEvent(
        "text",
        "你",
    )
    assert event_stream.terminal_input_event_from_event_result(("key", "down")) == event_stream.TerminalInputEvent(
        "down"
    )
    assert event_stream.terminal_input_event_from_event_result(("key", "\t")) == event_stream.TerminalInputEvent("tab")
    assert event_stream.terminal_input_event_from_event_result(("resize", (80, 24))) == event_stream.TerminalInputEvent(
        "resize"
    )
    assert event_stream.terminal_input_event_from_event_result(("paste", "你好")) == event_stream.TerminalInputEvent(
        "paste",
        "你好",
    )


def test_windows_console_input_source_maps_event_source_payloads_to_terminal_input() -> None:
    # Rust source contract:
    # - the Windows product path uses console key events, then maps those
    #   crossterm-like payloads to the same TerminalInputEvent contract used by
    #   chat_composer.
    class FakeEventSource:
        def __init__(self) -> None:
            self.events = [
                ("key", "你"),
                ("key", "好"),
                ("key", "\r"),
                ("key", "down"),
                ("key", "\t"),
            ]

        def poll_next(self) -> object | None:
            if not self.events:
                return None
            return self.events.pop(0)

    source = WindowsConsoleInputSource(msvcrt_module=object(), event_source=FakeEventSource())

    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "你")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "好")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("enter")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("down")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("tab")


def test_windows_console_input_source_maps_ime_multichar_key_payload_to_text() -> None:
    # Rust source/product contract:
    # - tui::event_stream forwards committed IME text as text key events even
    #   when the terminal host reports a whole committed string in one payload.
    class FakeEventSource:
        def __init__(self) -> None:
            self.events = [
                ("key", "你好"),
                ("key", "好 "),
            ]

        def poll_next(self) -> object | None:
            if not self.events:
                return None
            return self.events.pop(0)

    source = WindowsConsoleInputSource(msvcrt_module=object(), event_source=FakeEventSource())

    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "你好")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "好 ")
    assert source.poll(0.0) is None


def test_windows_console_input_source_emits_one_multiline_bracketed_paste() -> None:
    # Fixed Rust baseline 1c7832f: tui::event_stream maps crossterm's
    # Event::Paste payload to one TuiEvent::Paste, preserving embedded lines.
    class FakeEventSource:
        def __init__(self) -> None:
            self.events = [
                *(('key', char) for char in "\x1b[200~first\n第二行\x1b[201~"),
                ("key", "\r"),
            ]

        def poll_next(self) -> object | None:
            return self.events.pop(0) if self.events else None

    source = WindowsConsoleInputSource(msvcrt_module=object(), event_source=FakeEventSource())

    assert source.poll(0.1) == event_stream.TerminalInputEvent("paste", "first\n第二行")
    assert source.poll(0.1) == event_stream.TerminalInputEvent("enter")


def test_windows_console_input_source_maps_special_keys_and_tab() -> None:
    class FakeMsvcrt:
        def __init__(self) -> None:
            self.chars = ["\xe0", "P", "\xe0", "H", "\t"]

        def kbhit(self) -> bool:
            return bool(self.chars)

        def getwch(self) -> str:
            return self.chars.pop(0)

    source = WindowsConsoleInputSource(FakeMsvcrt())

    assert source.poll(0.0) == event_stream.TerminalInputEvent("down")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("up")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("tab")


def test_make_terminal_input_source_uses_select_for_non_windows_file(monkeypatch) -> None:
    monkeypatch.setattr(event_stream.os, "name", "posix")

    class FakeStdin:
        def fileno(self) -> int:
            return 0

    assert isinstance(make_terminal_input_source(FakeStdin()), SelectTerminalInputSource)


def test_make_terminal_input_source_rejects_non_file_stdin(monkeypatch) -> None:
    monkeypatch.setattr(event_stream.os, "name", "posix")

    class FakeStdin:
        pass

    assert make_terminal_input_source(FakeStdin()) is None


def test_poll_terminal_turn_event_classifies_event_idle_and_closed_states() -> None:
    # Rust source contract:
    # - tui::event_stream owns the event-source boundary; terminal runner code
    #   should consume event/idle/closed states instead of probing stream
    #   compatibility shapes itself.
    class Stream:
        def __init__(self) -> None:
            self.closed = False
            self.events = ["first", None, None]

        def next_event(self, timeout: float) -> object | None:
            return self.events.pop(0)

    stream = Stream()

    assert poll_terminal_turn_event(stream, timeout=0.1).kind == "event"
    assert poll_terminal_turn_event(stream, timeout=0.1).kind == "idle"
    stream.closed = True
    assert poll_terminal_turn_event(stream, timeout=0.1).kind == "closed"


def test_terminal_turn_event_stream_closed_supports_property_callable_and_is_closed() -> None:
    class CallableClosed:
        def closed(self) -> bool:
            return True

    class PropertyClosed:
        closed = True

    class IsClosed:
        is_closed = True

    class BrokenClosed:
        def closed(self) -> bool:
            raise RuntimeError("not ready")

    assert terminal_turn_event_stream_closed(CallableClosed()) is True
    assert terminal_turn_event_stream_closed(PropertyClosed()) is True
    assert terminal_turn_event_stream_closed(IsClosed()) is True
    assert terminal_turn_event_stream_closed(BrokenClosed()) is False


def test_run_terminal_turn_event_loop_dispatches_idle_event_and_completion() -> None:
    # Rust source contract:
    # - tui::event_stream owns the submitted-turn event loop boundary. The
    #   terminal runner supplies resize/status/event callbacks rather than
    #   interpreting event/idle/closed poll states itself.
    class Event:
        def __init__(self, kind: str) -> None:
            self.kind = kind

    class Stream:
        closed = False

        def __init__(self) -> None:
            self.events = [None, Event("AgentMessageDelta"), Event("TurnCompleted")]

        def next_event(self, timeout: float) -> object | None:
            return self.events.pop(0)

    calls: list[str] = []
    result = run_terminal_turn_event_loop(
        Stream(),
        timeout=0.1,
        on_event=lambda event: calls.append(f"event:{event.kind}"),
        on_closed=lambda: calls.append("closed"),
        on_idle=lambda: calls.append("idle"),
        before_event=lambda: calls.append("before_event"),
    )

    assert getattr(result, "kind", None) == "TurnCompleted"
    assert calls == [
        "idle",
        "before_event",
        "event:AgentMessageDelta",
        "before_event",
        "event:TurnCompleted",
    ]


def test_run_terminal_turn_event_loop_runs_closed_callback() -> None:
    class Stream:
        closed = True

        def next_event(self, timeout: float) -> object | None:
            return None

    calls: list[str] = []
    result = run_terminal_turn_event_loop(
        Stream(),
        timeout=0.1,
        on_event=lambda event: calls.append("event"),
        on_closed=lambda: calls.append("closed"),
        on_idle=lambda: calls.append("idle"),
        before_event=lambda: calls.append("before_event"),
    )

    assert result is None
    assert calls == ["closed"]


def test_terminal_turn_event_loop_runner_binds_runtime_callbacks() -> None:
    # Rust owner: codex-tui::tui::event_stream owns submitted-turn event
    # loop callback dispatch. terminal_runtime should bind these callbacks
    # once and consume a runner rather than assembling event-loop arguments at
    # the call site.
    class Event:
        def __init__(self, kind: str) -> None:
            self.kind = kind

    class Stream:
        closed = False

        def __init__(self) -> None:
            self.events = [None, Event("TurnCompleted")]

        def next_event(self, timeout: float) -> object | None:
            calls.append(f"timeout:{timeout}")
            return self.events.pop(0)

    calls: list[str] = []
    runner = TerminalTurnEventLoopRunner(
        timeout=0.25,
        on_event=lambda event: calls.append(f"event:{event.kind}"),
        on_closed=lambda: calls.append("closed"),
        on_idle=lambda: calls.append("idle"),
        before_event=lambda: calls.append("before_event"),
    )

    result = runner.consume(Stream())

    assert getattr(result, "kind", None) == "TurnCompleted"
    assert calls == [
        "timeout:0.25",
        "idle",
        "timeout:0.25",
        "before_event",
        "event:TurnCompleted",
    ]


def test_run_terminal_turn_idle_tick_checks_resize_before_status_refresh() -> None:
    # Rust owner: codex-tui::tui::event_stream owns idle dispatch for terminal
    # event streams; the terminal product path supplies resize/status callbacks.
    calls: list[str] = []

    run_terminal_turn_idle_tick(
        check_resize=lambda: calls.append("resize"),
        refresh_turn_status=lambda: calls.append("status"),
    )

    assert calls == ["resize", "status"]


def test_terminal_turn_idle_ticker_binds_runtime_idle_callbacks() -> None:
    # Rust owner: codex-tui::tui::event_stream owns idle dispatch for terminal
    # event streams. terminal_runtime should pass a bound event-stream owner
    # callback instead of constructing idle-maintenance lambdas locally.
    calls: list[str] = []
    ticker = TerminalTurnIdleTicker(
        check_resize=lambda: calls.append("resize"),
        refresh_turn_status=lambda: calls.append("status"),
    )

    ticker.tick()

    assert calls == ["resize", "status"]


def test_prefixed_terminal_input_source_replays_turn_input_before_live_source() -> None:
    # Rust owner: tui::event_stream preserves key order while app::input
    # arbitrates turn-time Ctrl+C. Deferred ordinary keys must not be lost.
    live = StringTerminalInputSource(io.StringIO("z"))
    prefix = deque(
        [
            event_stream.TerminalInputEvent("text", "你"),
            event_stream.TerminalInputEvent("enter"),
        ]
    )
    source = event_stream.PrefixedTerminalInputSource(live, prefix)

    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "你")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("enter")
    assert source.poll(0.0) == event_stream.TerminalInputEvent("text", "z")
