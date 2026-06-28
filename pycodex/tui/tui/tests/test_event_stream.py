"""Parity tests for Rust ``codex-tui::tui::event_stream``.

Rust source: ``codex/codex-rs/tui/src/tui/event_stream.rs``.
"""

from pycodex.tui.tui.event_stream import (
    EventBroker,
    EventBrokerState,
    FakeEventSource,
    FakeEventSourceHandle,
    FocusFlag,
    TuiEvent,
    WindowsConsoleEventSource,
    make_stream,
    setup,
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
