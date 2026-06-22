"""Tests for the Textual event-source adapter behind Rust-style event_stream APIs."""

from dataclasses import dataclass

from pycodex.tui.tui.event_stream import TuiEvent
from pycodex.tui.tui.textual_event_source import (
    TextualEventBridge,
    make_textual_event_runtime,
    textual_event_to_crossterm_like,
)


@dataclass
class Key:
    key: str


@dataclass
class Resize:
    width: int
    height: int


@dataclass
class Paste:
    text: str


class Focus:
    pass


class Blur:
    pass


class MouseMove:
    pass


def test_textual_event_to_crossterm_like_maps_common_textual_events() -> None:
    assert textual_event_to_crossterm_like(Key("ctrl+c")) == ("key", "ctrl+c")
    assert textual_event_to_crossterm_like(Resize(80, 24)) == ("resize", (80, 24))
    assert textual_event_to_crossterm_like(Paste("hello")) == ("paste", "hello")
    assert textual_event_to_crossterm_like(Focus()) == ("focus_gained", None)
    assert textual_event_to_crossterm_like(Blur()) == ("focus_lost", None)
    assert textual_event_to_crossterm_like(MouseMove()) is None


def test_textual_runtime_feeds_rust_style_event_stream() -> None:
    runtime = make_textual_event_runtime()

    runtime.send_textual_event(Key("a"))
    runtime.send_textual_event(Resize(120, 40))
    runtime.send_textual_event(Paste("clip"))

    assert runtime.stream.poll_next() == TuiEvent.key("a")
    assert runtime.stream.poll_next() == TuiEvent.resize()
    assert runtime.stream.poll_next() == TuiEvent.paste("clip")


def test_textual_runtime_focus_and_draw_events_share_rust_api() -> None:
    runtime = make_textual_event_runtime()
    runtime.terminal_focused.set(False)

    runtime.request_draw()
    runtime.send_textual_event(Focus())

    events = [runtime.stream.poll_next(), runtime.stream.poll_next()]
    assert TuiEvent.draw() in events
    assert runtime.terminal_focused.value is True


def test_textual_runtime_pause_resume_uses_event_broker_boundary() -> None:
    runtime = make_textual_event_runtime()

    runtime.pause_events()
    runtime.send_textual_event(Key("x"))
    assert runtime.stream.poll_next() is None

    runtime.resume_events()
    runtime.send_textual_event(Key("y"))
    assert runtime.stream.poll_next() == TuiEvent.key("y")


def test_textual_event_bridge_lifecycle_hooks_feed_rust_style_stream() -> None:
    bridge = TextualEventBridge.new()

    bridge.on_key(Key("enter"))
    bridge.on_resize(Resize(100, 30))
    bridge.on_paste(Paste("pasted"))
    bridge.on_focus()
    bridge.on_blur()

    assert bridge.stream.poll_next() == TuiEvent.key("enter")
    assert bridge.stream.poll_next() == TuiEvent.resize()
    assert bridge.stream.poll_next() == TuiEvent.paste("pasted")
    assert bridge.stream.poll_next() == TuiEvent.draw()
    assert bridge.runtime.terminal_focused.value is False


def test_textual_event_bridge_pause_resume_delegates_to_runtime() -> None:
    bridge = TextualEventBridge.new()

    bridge.pause_events()
    bridge.on_key(Key("ignored"))
    assert bridge.stream.poll_next() is None

    bridge.resume_events()
    bridge.on_key(Key("accepted"))
    assert bridge.stream.poll_next() == TuiEvent.key("accepted")
