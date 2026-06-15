"""Semantic helpers for Rust ``codex-tui::app::pets``.

Upstream source: ``codex/codex-rs/tui/src/app/pets.rs``.

The Rust module is implemented as ``impl App`` methods. Python represents the
module-owned behavior as helpers operating on App/Tui-like objects plus
semantic plans for background pet loading and config persistence side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::pets",
    source="codex/codex-rs/tui/src/app/pets.rs",
    status="complete",
)

PetRenderErrorKind = Literal["terminal", "asset"]


@dataclass(frozen=True)
class PetImageRenderError(Exception):
    """Semantic equivalent of Rust ``crate::pets::PetImageRenderError``."""

    kind: PetRenderErrorKind
    error: Any

    @classmethod
    def terminal(cls, error: Any) -> "PetImageRenderError":
        return cls("terminal", error)

    @classmethod
    def asset(cls, error: Any) -> "PetImageRenderError":
        return cls("asset", error)

    def __str__(self) -> str:
        return str(self.error)


@dataclass(frozen=True)
class PetActionPlan:
    action: str
    pet_id: Optional[str] = None
    request_id: Optional[int] = None
    result: Any = None
    updates: Tuple[Tuple[str, Any], ...] = ()
    messages: Tuple[str, ...] = ()
    schedule_frame: bool = False
    continue_run: bool = True


class _ChatWidgetWithAmbientPet(Protocol):
    def disable_ambient_pet_for_session(self) -> None: ...


class _ChatWidgetWithPickerPreview(Protocol):
    def fail_pet_picker_preview_render(self, message: str) -> None: ...


class _AppWithChatWidget(Protocol):
    chat_widget: Any


class _TuiWithAmbientPet(Protocol):
    def clear_ambient_pet_image(self) -> Optional[PetImageRenderError]: ...


class _TuiWithPetPickerPreview(Protocol):
    def draw_pet_picker_preview_image(self, request: Any = None) -> Optional[PetImageRenderError]: ...


def _raise_terminal_error(error: Any) -> None:
    if isinstance(error, BaseException):
        raise error
    raise RuntimeError(str(error))


def _coerce_render_error(error: Any) -> PetImageRenderError:
    if isinstance(error, PetImageRenderError):
        return error
    return PetImageRenderError.terminal(error)


def _handle_clear_result(result: Optional[PetImageRenderError]) -> None:
    if result is None:
        return
    if result.kind == "terminal":
        _raise_terminal_error(result.error)
    # Asset clear errors are warning-only in Rust and intentionally swallowed.


def disable_ambient_pet_before_shutdown(app: _AppWithChatWidget, tui: _TuiWithAmbientPet) -> None:
    """Disable the ambient pet and clear its image before shutdown feedback."""

    app.chat_widget.disable_ambient_pet_for_session()
    _handle_clear_result(tui.clear_ambient_pet_image())


def handle_ambient_pet_image_render_error(app: _AppWithChatWidget, tui: _TuiWithAmbientPet, error: Any) -> None:
    """Handle ambient pet image render failures using Rust's error boundary."""

    err = _coerce_render_error(error)
    if err.kind == "terminal":
        _raise_terminal_error(err.error)
    app.chat_widget.disable_ambient_pet_for_session()
    _handle_clear_result(tui.clear_ambient_pet_image())


def handle_pet_picker_preview_image_render_error(app: _AppWithChatWidget, tui: _TuiWithPetPickerPreview, error: Any) -> None:
    """Handle pet picker preview render failures using Rust's error boundary."""

    err = _coerce_render_error(error)
    if err.kind == "terminal":
        _raise_terminal_error(err.error)
    app.chat_widget.fail_pet_picker_preview_render(str(err.error))
    _handle_clear_result(tui.draw_pet_picker_preview_image(None))


def handle_pet_selected(pet_id: str, request_id: int = 0) -> PetActionPlan:
    return PetActionPlan(
        action="spawn_pet_selection_load",
        pet_id=pet_id,
        request_id=request_id,
        updates=(("show_pet_selection_loading_popup", request_id), ("ensure_builtin_pack_for_pet", pet_id), ("load_ambient_pet", pet_id)),
        schedule_frame=True,
    )


def handle_pet_disabled(error: Any = None) -> PetActionPlan:
    if error is not None:
        return PetActionPlan(action="disable_pet_failed", messages=("Failed to disable pets: %s" % error,))
    return PetActionPlan(
        action="disable_pet",
        updates=(("config.tui_pet", "disabled"), ("chat_widget.config.tui_pet", "disabled")),
        schedule_frame=True,
    )


def handle_pet_preview_loaded(request_id: int, result: Any) -> PetActionPlan:
    return PetActionPlan(
        action="pet_preview_loaded",
        request_id=request_id,
        result=result,
        updates=(("finish_pet_picker_preview_load", request_id),),
        schedule_frame=True,
    )


def handle_pet_selection_loaded(request_id: int, pet_id: str, result: Any, popup_finished: bool = True, save_error: Any = None) -> PetActionPlan:
    if not popup_finished:
        return PetActionPlan(action="pet_selection_popup_stale", request_id=request_id, pet_id=pet_id)
    if isinstance(result, BaseException):
        return PetActionPlan(action="pet_selection_load_failed", request_id=request_id, pet_id=pet_id, messages=("Failed to load pet: %s" % result,))
    if isinstance(result, tuple) and len(result) == 2 and result[0] == "err":
        return PetActionPlan(action="pet_selection_load_failed", request_id=request_id, pet_id=pet_id, messages=("Failed to load pet: %s" % result[1],))
    if save_error is not None:
        return PetActionPlan(action="pet_selection_save_failed", request_id=request_id, pet_id=pet_id, messages=("Failed to save pet selection: %s" % save_error,), schedule_frame=True)
    return PetActionPlan(
        action="pet_selection_loaded",
        request_id=request_id,
        pet_id=pet_id,
        result=result,
        updates=(("config.tui_pet", pet_id), ("chat_widget.set_tui_pet_loaded", pet_id)),
        schedule_frame=True,
    )


def handle_configured_pet_loaded(configured_pet_id: Optional[str], pet_id: str, result: Any) -> PetActionPlan:
    if configured_pet_id != pet_id:
        return PetActionPlan(action="configured_pet_stale", pet_id=pet_id)
    if isinstance(result, BaseException):
        return PetActionPlan(action="configured_pet_load_failed", pet_id=pet_id, messages=("Failed to load configured pet: %s" % result,))
    if isinstance(result, tuple) and len(result) == 2 and result[0] == "err":
        return PetActionPlan(action="configured_pet_load_failed", pet_id=pet_id, messages=("Failed to load configured pet: %s" % result[1],))
    return PetActionPlan(
        action="configured_pet_loaded",
        pet_id=pet_id,
        result=result,
        updates=(("chat_widget.set_tui_pet_loaded", pet_id),),
        schedule_frame=True,
    )


__all__ = [
    "PetActionPlan",
    "PetImageRenderError",
    "RUST_MODULE",
    "disable_ambient_pet_before_shutdown",
    "handle_ambient_pet_image_render_error",
    "handle_configured_pet_loaded",
    "handle_pet_disabled",
    "handle_pet_picker_preview_image_render_error",
    "handle_pet_preview_loaded",
    "handle_pet_selected",
    "handle_pet_selection_loaded",
]
