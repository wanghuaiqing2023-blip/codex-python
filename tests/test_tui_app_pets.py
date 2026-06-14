from __future__ import annotations

import pytest

from pycodex.tui.app.pets import (
    PetImageRenderError,
    disable_ambient_pet_before_shutdown,
    handle_ambient_pet_image_render_error,
    handle_pet_picker_preview_image_render_error,
)


class ChatWidget:
    def __init__(self) -> None:
        self.disabled = 0
        self.preview_failures: list[str] = []

    def disable_ambient_pet_for_session(self) -> None:
        self.disabled += 1

    def fail_pet_picker_preview_render(self, message: str) -> None:
        self.preview_failures.append(message)


class App:
    def __init__(self) -> None:
        self.chat_widget = ChatWidget()


class Tui:
    def __init__(self, *, clear_result=None, preview_result=None) -> None:
        self.clear_result = clear_result
        self.preview_result = preview_result
        self.clear_calls = 0
        self.preview_requests: list[object | None] = []

    def clear_ambient_pet_image(self):
        self.clear_calls += 1
        return self.clear_result

    def draw_pet_picker_preview_image(self, request=None):
        self.preview_requests.append(request)
        return self.preview_result


def test_disable_ambient_pet_before_shutdown_disables_then_swallows_asset_clear_error() -> None:
    app = App()
    tui = Tui(clear_result=PetImageRenderError.asset("missing asset"))

    disable_ambient_pet_before_shutdown(app, tui)

    assert app.chat_widget.disabled == 1
    assert tui.clear_calls == 1


def test_ambient_render_asset_error_disables_and_terminal_clear_error_propagates() -> None:
    app = App()
    terminal_error = OSError("terminal failed")
    tui = Tui(clear_result=PetImageRenderError.terminal(terminal_error))

    with pytest.raises(OSError, match="terminal failed"):
        handle_ambient_pet_image_render_error(app, tui, PetImageRenderError.asset("bad png"))

    assert app.chat_widget.disabled == 1
    assert tui.clear_calls == 1


def test_picker_preview_asset_error_records_failure_and_clears_preview() -> None:
    app = App()
    tui = Tui(preview_result=PetImageRenderError.asset("clear asset failed"))

    handle_pet_picker_preview_image_render_error(app, tui, PetImageRenderError.asset("decode failed"))

    assert app.chat_widget.preview_failures == ["decode failed"]
    assert tui.preview_requests == [None]


def test_terminal_render_errors_propagate_without_state_changes() -> None:
    app = App()
    tui = Tui()

    with pytest.raises(RuntimeError, match="terminal boom"):
        handle_ambient_pet_image_render_error(app, tui, PetImageRenderError.terminal("terminal boom"))
    with pytest.raises(RuntimeError, match="preview boom"):
        handle_pet_picker_preview_image_render_error(app, tui, PetImageRenderError.terminal("preview boom"))

    assert app.chat_widget.disabled == 0
    assert app.chat_widget.preview_failures == []
    assert tui.clear_calls == 0
    assert tui.preview_requests == []
