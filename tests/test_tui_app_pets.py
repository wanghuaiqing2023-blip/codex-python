from __future__ import annotations

import pytest

from pycodex.tui.app.pets import (
    PetActionPlan,
    PetImageRenderError,
    disable_ambient_pet_before_shutdown,
    handle_ambient_pet_image_render_error,
    handle_pet_picker_preview_image_render_error,
    handle_configured_pet_loaded,
    handle_pet_disabled,
    handle_pet_preview_loaded,
    handle_pet_selected,
    handle_pet_selection_loaded,
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


def test_pet_selection_and_disabled_paths_are_semantic_plans() -> None:
    selected = handle_pet_selected("chefito", request_id=7)
    assert selected == PetActionPlan(
        action="spawn_pet_selection_load",
        pet_id="chefito",
        request_id=7,
        updates=(("show_pet_selection_loading_popup", 7), ("ensure_builtin_pack_for_pet", "chefito"), ("load_ambient_pet", "chefito")),
        schedule_frame=True,
    )

    assert handle_pet_disabled() == PetActionPlan(
        action="disable_pet",
        updates=(("config.tui_pet", "disabled"), ("chat_widget.config.tui_pet", "disabled")),
        schedule_frame=True,
    )
    assert handle_pet_disabled(RuntimeError("disk")) == PetActionPlan(
        action="disable_pet_failed",
        messages=("Failed to disable pets: disk",),
    )


def test_pet_loaded_callbacks_are_semantic_plans() -> None:
    assert handle_pet_preview_loaded(3, "pet") == PetActionPlan(
        action="pet_preview_loaded",
        request_id=3,
        result="pet",
        updates=(("finish_pet_picker_preview_load", 3),),
        schedule_frame=True,
    )

    stale = handle_pet_selection_loaded(9, "chefito", "pet", popup_finished=False)
    assert stale.action == "pet_selection_popup_stale"

    loaded = handle_pet_selection_loaded(9, "chefito", "pet")
    assert loaded.action == "pet_selection_loaded"
    assert loaded.schedule_frame

    failed = handle_pet_selection_loaded(9, "chefito", ("err", "missing"))
    assert failed.messages == ("Failed to load pet: missing",)

    configured = handle_configured_pet_loaded("chefito", "chefito", "pet")
    assert configured.action == "configured_pet_loaded"
    assert configured.schedule_frame
    assert handle_configured_pet_loaded("other", "chefito", "pet").action == "configured_pet_stale"


def test_configured_pet_load_failure_reports_warning_without_frame() -> None:
    """Rust codex-tui app::pets::handle_configured_pet_loaded Err branch."""

    failed = handle_configured_pet_loaded("chefito", "chefito", ("err", "missing pack"))

    assert failed == PetActionPlan(
        action="configured_pet_load_failed",
        pet_id="chefito",
        messages=("Failed to load configured pet: missing pack",),
    )
    assert failed.schedule_frame is False
