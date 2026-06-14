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
