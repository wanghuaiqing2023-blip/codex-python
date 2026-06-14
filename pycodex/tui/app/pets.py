"""Semantic helpers for Rust ``codex-tui::app::pets``.

Upstream source: ``codex/codex-rs/tui/src/app/pets.rs``.

The Rust module is implemented as ``impl App`` methods.  Python represents the
module-owned behavior as small helpers that operate on App/Tui-like objects with
the methods used by the Rust code.  Async config writes and background pet
loading remain runtime boundaries for later slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::pets",
    source="codex/codex-rs/tui/src/app/pets.rs",
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


class _ChatWidgetWithAmbientPet(Protocol):
    def disable_ambient_pet_for_session(self) -> None: ...


class _ChatWidgetWithPickerPreview(Protocol):
    def fail_pet_picker_preview_render(self, message: str) -> None: ...


class _AppWithChatWidget(Protocol):
    chat_widget: Any


class _TuiWithAmbientPet(Protocol):
    def clear_ambient_pet_image(self) -> PetImageRenderError | None: ...


class _TuiWithPetPickerPreview(Protocol):
    def draw_pet_picker_preview_image(self, request: Any | None = None) -> PetImageRenderError | None: ...


def _raise_terminal_error(error: Any) -> None:
    if isinstance(error, BaseException):
        raise error
    raise RuntimeError(str(error))


def _coerce_render_error(error: PetImageRenderError | BaseException | str) -> PetImageRenderError:
    if isinstance(error, PetImageRenderError):
        return error
    return PetImageRenderError.terminal(error)


def _handle_clear_result(result: PetImageRenderError | None) -> None:
    if result is None:
        return
    if result.kind == "terminal":
        _raise_terminal_error(result.error)
    # Asset clear errors are warning-only in Rust and intentionally swallowed.


def disable_ambient_pet_before_shutdown(app: _AppWithChatWidget, tui: _TuiWithAmbientPet) -> None:
    """Disable the ambient pet and clear its image before shutdown feedback.

    Mirrors Rust ``App::disable_ambient_pet_before_shutdown``: the session pet is
    disabled first; terminal clear failures propagate; asset clear failures are
    warning-only.
    """

    app.chat_widget.disable_ambient_pet_for_session()
    _handle_clear_result(tui.clear_ambient_pet_image())


def handle_ambient_pet_image_render_error(
    app: _AppWithChatWidget,
    tui: _TuiWithAmbientPet,
    error: PetImageRenderError | BaseException | str,
) -> None:
    """Handle ambient pet image render failures using Rust's error boundary."""

    err = _coerce_render_error(error)
    if err.kind == "terminal":
        _raise_terminal_error(err.error)

    app.chat_widget.disable_ambient_pet_for_session()
    _handle_clear_result(tui.clear_ambient_pet_image())


def handle_pet_picker_preview_image_render_error(
    app: _AppWithChatWidget,
    tui: _TuiWithPetPickerPreview,
    error: PetImageRenderError | BaseException | str,
) -> None:
    """Handle pet picker preview render failures using Rust's error boundary."""

    err = _coerce_render_error(error)
    if err.kind == "terminal":
        _raise_terminal_error(err.error)

    app.chat_widget.fail_pet_picker_preview_render(str(err.error))
    _handle_clear_result(tui.draw_pet_picker_preview_image(None))


def handle_pet_selected(*_args: Any, **_kwargs: Any) -> None:
    raise not_ported("app::pets.handle_pet_selected background loading is not ported")


def handle_pet_disabled(*_args: Any, **_kwargs: Any) -> None:
    raise not_ported("app::pets.handle_pet_disabled config persistence is not ported")


def handle_pet_selection_loaded(*_args: Any, **_kwargs: Any) -> None:
    raise not_ported("app::pets.handle_pet_selection_loaded config persistence is not ported")


__all__ = [
    "PetImageRenderError",
    "RUST_MODULE",
    "disable_ambient_pet_before_shutdown",
    "handle_ambient_pet_image_render_error",
    "handle_pet_disabled",
    "handle_pet_picker_preview_image_render_error",
    "handle_pet_selected",
    "handle_pet_selection_loaded",
]
