"""Parity tests for codex-rs/tui/src/chatwidget/hooks.rs."""

from pathlib import Path

from pycodex.tui.chatwidget.hooks import HooksMixin, add_hooks_output, on_hooks_loaded, open_hooks_browser
from pycodex.tui.hooks_rpc import HooksListEntry, HooksListResponse


class FakeConfig:
    def __init__(self, cwd):
        self.cwd = Path(cwd)


class FakeBottomPane:
    def __init__(self):
        self.views = []
        self.keymap = "list-keymap"

    def show_view(self, view):
        self.views.append(view)

    def list_keymap(self):
        return self.keymap


class FakeWidget:
    def __init__(self, cwd="/repo"):
        self.config = FakeConfig(cwd)
        self.events = []
        self.errors = []
        self.redraws = 0
        self.bottom_pane = FakeBottomPane()
        self.app_event_tx = self.events.append

    def add_error_message(self, message):
        self.errors.append(message)

    def request_redraw(self):
        self.redraws += 1


class MixedWidget(HooksMixin, FakeWidget):
    pass


def test_add_hooks_output_sends_fetch_event_for_current_cwd():
    widget = FakeWidget("/repo")

    add_hooks_output(widget)

    assert widget.events == [{"type": "FetchHooksList", "cwd": Path("/repo")}]


def test_on_hooks_loaded_ignores_stale_cwd_results():
    widget = FakeWidget("/repo/current")
    response = HooksListResponse(data=[HooksListEntry(cwd=Path("/repo/old"))])

    on_hooks_loaded(widget, "/repo/old", response)

    assert widget.bottom_pane.views == []
    assert widget.errors == []
    assert widget.redraws == 0


def test_on_hooks_loaded_opens_browser_for_matching_success_response():
    widget = FakeWidget("/repo")
    entry = HooksListEntry(cwd=Path("/repo"), hooks=[{"key": "path:one", "event_name": "PreToolUse"}])
    response = HooksListResponse(data=[entry])

    on_hooks_loaded(widget, Path("/repo"), response)

    assert len(widget.bottom_pane.views) == 1
    assert widget.bottom_pane.views[0].entry.cwd == Path("/repo")
    assert widget.redraws == 1
    assert widget.errors == []


def test_on_hooks_loaded_accepts_rust_like_ok_tuple():
    widget = FakeWidget("/repo")
    response = HooksListResponse(data=[HooksListEntry(cwd=Path("/repo"))])

    on_hooks_loaded(widget, "/repo", ("Ok", response))

    assert len(widget.bottom_pane.views) == 1
    assert widget.redraws == 1


def test_on_hooks_loaded_adds_error_message_for_error_result():
    widget = FakeWidget("/repo")

    on_hooks_loaded(widget, "/repo", ("Err", "boom"))

    assert widget.errors == ["Failed to load hooks: boom"]
    assert widget.bottom_pane.views == []
    assert widget.redraws == 0


def test_open_hooks_browser_shows_view_and_requests_redraw():
    widget = FakeWidget("/repo")
    entry = HooksListEntry(cwd=Path("/repo"))

    open_hooks_browser(widget, entry)

    assert len(widget.bottom_pane.views) == 1
    assert widget.bottom_pane.views[0].keymap == "list-keymap"
    assert widget.redraws == 1


def test_mixin_exposes_rust_impl_method_shape():
    widget = MixedWidget("/repo")
    response = HooksListResponse(data=[HooksListEntry(cwd=Path("/repo"))])

    widget.add_hooks_output()
    widget.on_hooks_loaded("/repo", response)

    assert widget.events == [{"type": "FetchHooksList", "cwd": Path("/repo")}]
    assert len(widget.bottom_pane.views) == 1
    assert widget.redraws == 1
