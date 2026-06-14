"""Chat widget helpers for ambient terminal pets and the pets picker.

Rust source: ``codex/codex-rs/tui/src/chatwidget/pets.rs``.

The Rust module is an impl block on ``ChatWidget``.  Python keeps the
module-owned state transitions in a semantic ``ChatWidgetPetsModel`` while
leaving real image loading/rendering as injectable dependency boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .._porting import RustTuiModule
from ..pets import DEFAULT_PET_ID, DISABLED_PET_ID, PET_PICKER_VIEW_ID, PetPickerPreviewState

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::pets", source="codex/codex-rs/tui/src/chatwidget/pets.rs")

PET_SELECTION_LOADING_VIEW_ID = "pet-selection-loading"
AMBIENT_PET_WRAP_GAP_COLUMNS = 2


@dataclass
class PetsConfig:
    tui_pet: str | None = None
    codex_home: Any = None
    animations: bool = True
    tui_pet_anchor: str = "composer"


@dataclass
class SelectionViewParamsPlan:
    view_id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BottomPanePetsModel:
    modal_or_popup_active: bool = False
    selected_view_ids: set[str] = field(default_factory=set)
    shown_views: list[Any] = field(default_factory=list)
    dismissed_view_ids: list[str] = field(default_factory=list)
    task_running: bool = False

    def no_modal_or_popup_active(self) -> bool:
        return not self.modal_or_popup_active

    def selected_index_for_active_view(self, view_id: str) -> int | None:
        return 0 if view_id in self.selected_view_ids else None

    def show_selection_view(self, params: Any) -> None:
        self.shown_views.append(params)
        view_id = getattr(params, "view_id", None)
        if isinstance(params, dict):
            view_id = params.get("view_id", view_id)
        if view_id is not None:
            self.selected_view_ids.add(view_id)

    def dismiss_active_view_if_id(self, view_id: str) -> None:
        self.dismissed_view_ids.append(view_id)
        self.selected_view_ids.discard(view_id)

    def is_task_running(self) -> bool:
        return self.task_running


@dataclass
class ChatWidgetPetsModel:
    config: PetsConfig = field(default_factory=PetsConfig)
    ambient_pet: Any | None = None
    bottom_pane: BottomPanePetsModel = field(default_factory=BottomPanePetsModel)
    pet_picker_preview_state: PetPickerPreviewState = field(default_factory=PetPickerPreviewState)
    pet_picker_preview_pet: Any | None = None
    pet_picker_preview_image_visible: bool = False
    pet_picker_preview_request_id: int = 0
    pet_selection_load_request_id: int = 0
    pet_image_support_override: Any | None = None
    frame_requester: Any = None
    events: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    redraw_requests: int = 0
    loader: Callable[..., Any] | None = None
    picker_builder: Callable[..., Any] | None = None

    def set_ambient_pet_notification(self, kind: Any, body: str | None) -> None:
        if self.ambient_pet is not None and hasattr(self.ambient_pet, "set_notification"):
            self.ambient_pet.set_notification(kind, body)

    def ambient_pet_image_enabled(self) -> bool:
        return bool(self.ambient_pet is not None and _call_bool(self.ambient_pet, "image_enabled"))

    def disable_ambient_pet_for_session(self) -> None:
        self.ambient_pet = None
        self.request_redraw()

    def ambient_pet_draw(self, area: Any, composer_bottom_y: int) -> Any | None:
        if not self.bottom_pane.no_modal_or_popup_active() or self.ambient_pet is None:
            return None
        anchor_bottom_y = composer_bottom_y if self.config.tui_pet_anchor == "composer" else _area_bottom(area)
        draw_request = getattr(self.ambient_pet, "draw_request", None)
        return draw_request(area, anchor_bottom_y) if callable(draw_request) else None

    def ambient_pet_wrap_reserved_cols(self) -> int:
        if not self.ambient_pet_image_enabled():
            return 0
        columns = getattr(self.ambient_pet, "image_columns", None)
        image_columns = columns() if callable(columns) else int(getattr(self.ambient_pet, "columns", 0))
        return max(0, image_columns) + AMBIENT_PET_WRAP_GAP_COLUMNS

    def history_wrap_width(self, width: int) -> int:
        return max(1, max(0, int(width)) - self.ambient_pet_wrap_reserved_cols())

    def pet_picker_preview_draw(self) -> Any | None:
        if self.bottom_pane.selected_index_for_active_view(PET_PICKER_VIEW_ID) is None:
            return None
        area = self.pet_picker_preview_state.area()
        if area is None or self.pet_picker_preview_pet is None:
            return None
        preview_draw_request = getattr(self.pet_picker_preview_pet, "preview_draw_request", None)
        request = preview_draw_request(area) if callable(preview_draw_request) else None
        if request is None:
            return None
        self.pet_picker_preview_image_visible = True
        return request

    def should_clear_pet_picker_preview_image(self) -> bool:
        previous = self.pet_picker_preview_image_visible
        self.pet_picker_preview_image_visible = False
        return previous

    def fail_pet_picker_preview_render(self, message: str) -> None:
        self.pet_picker_preview_state.set_error(message)
        self.pet_picker_preview_pet = None
        self.request_redraw()

    def open_pets_picker(self) -> None:
        if self.warn_if_pets_unsupported():
            return
        self.pet_picker_preview_state.clear()
        self.pet_picker_preview_pet = None
        if self.picker_builder is None:
            params = SelectionViewParamsPlan(view_id=PET_PICKER_VIEW_ID, title="Select Pet")
        else:
            params = self.picker_builder(self.config.tui_pet, self.config.codex_home, self.pet_picker_preview_state)
        self.bottom_pane.show_selection_view(params)
        initial_pet_id = self.config.tui_pet or DEFAULT_PET_ID
        self.start_pet_picker_preview(initial_pet_id)

    def select_pet_by_id(self, pet_id: str) -> None:
        if self.warn_if_pets_unsupported():
            return
        self.events.append(("PetSelected", pet_id))

    def warn_if_pets_unsupported(self) -> bool:
        support = self.pet_image_support()
        unsupported_message = getattr(support, "unsupported_message", None)
        message = unsupported_message() if callable(unsupported_message) else None
        if message is None:
            return False
        self.add_warning_message(message)
        return True

    def pet_image_support(self) -> Any:
        return self.pet_image_support_override or _SupportedPetImages()

    def set_tui_pet(self, pet: str | None) -> None:
        self.config.tui_pet = pet
        self.ambient_pet = load_ambient_pet(self.config, self.frame_requester, loader=self.loader)
        self.apply_ambient_pet_image_support_override_for_tests()
        self.request_redraw()

    def set_tui_pet_loaded(self, pet: str | None, ambient_pet: Any | None) -> None:
        self.config.tui_pet = pet
        self.ambient_pet = ambient_pet
        self.apply_ambient_pet_image_support_override_for_tests()
        self.request_redraw()

    def apply_ambient_pet_image_support_override_for_tests(self) -> None:
        if self.pet_image_support_override is not None and self.ambient_pet is not None:
            setter = getattr(self.ambient_pet, "set_image_support_for_tests", None)
            if callable(setter):
                setter(self.pet_image_support_override)

    def start_pet_picker_preview(self, pet_id: str) -> None:
        self.pet_picker_preview_request_id = (self.pet_picker_preview_request_id + 1) % (2**64)
        request_id = self.pet_picker_preview_request_id
        self.pet_picker_preview_pet = None
        if pet_id == DISABLED_PET_ID:
            self.pet_picker_preview_state.set_disabled()
            self.request_redraw()
            return
        self.pet_picker_preview_state.set_loading()
        self.request_redraw()
        self.events.append(("PetPreviewLoadRequested", request_id, pet_id))

    def finish_pet_picker_preview_load(self, request_id: int, result: Any) -> None:
        if request_id != self.pet_picker_preview_request_id:
            return
        if isinstance(result, Exception):
            self.pet_picker_preview_state.set_error(str(result))
            self.pet_picker_preview_pet = None
        else:
            self.pet_picker_preview_state.set_ready()
            self.pet_picker_preview_pet = result
            if self.pet_image_support_override is not None:
                setter = getattr(self.pet_picker_preview_pet, "set_image_support_for_tests", None)
                if callable(setter):
                    setter(self.pet_image_support_override)
        self.request_redraw()

    def show_pet_selection_loading_popup(self) -> int:
        self.pet_selection_load_request_id = (self.pet_selection_load_request_id + 1) % (2**64)
        self.pet_picker_preview_state.clear()
        self.pet_picker_preview_pet = None
        self.bottom_pane.show_selection_view(
            SelectionViewParamsPlan(
                view_id=PET_SELECTION_LOADING_VIEW_ID,
                title="Loading Pet",
                subtitle="Preparing the terminal pet.",
                items=[{"name": "Loading selected pet...", "is_disabled": True}],
            )
        )
        return self.pet_selection_load_request_id

    def finish_pet_selection_loading_popup(self, request_id: int) -> bool:
        if request_id != self.pet_selection_load_request_id:
            return False
        self.bottom_pane.dismiss_active_view_if_id(PET_SELECTION_LOADING_VIEW_ID)
        return True

    def set_pet_image_support_for_tests(self, support: Any) -> None:
        self.pet_image_support_override = support
        self.apply_ambient_pet_image_support_override_for_tests()

    def install_test_ambient_pet_for_tests(self, ambient_pet: Any, animations_enabled: bool = True) -> None:
        self.config.animations = animations_enabled
        self.set_tui_pet_loaded("test", ambient_pet)

    def add_warning_message(self, message: str) -> None:
        self.warnings.append(message)

    def request_redraw(self) -> None:
        self.redraw_requests += 1


def load_ambient_pet(config: PetsConfig | Any, frame_requester: Any, *, loader: Callable[..., Any] | None = None) -> Any | None:
    selected_pet = getattr(config, "tui_pet", None)
    if selected_pet is None or selected_pet == DISABLED_PET_ID:
        return None
    if loader is None:
        return None
    try:
        return loader(selected_pet, getattr(config, "codex_home", None), frame_requester, getattr(config, "animations", True))
    except Exception:
        return None


def start_configured_pet_load_if_needed(
    config: PetsConfig | Any,
    ambient_pet_missing: bool,
    frame_requester: Any,
    app_event_tx: Any,
    *,
    loader: Callable[..., Any] | None = None,
) -> bool:
    pet_id = getattr(config, "tui_pet", None)
    if pet_id is None or pet_id == DISABLED_PET_ID or not ambient_pet_missing:
        return False

    def run() -> None:
        try:
            result = loader(pet_id, getattr(config, "codex_home", None), frame_requester, getattr(config, "animations", True)) if loader else None
            payload = ("ConfiguredPetLoaded", pet_id, result)
        except Exception as exc:
            payload = ("ConfiguredPetLoaded", pet_id, str(exc))
        sender = getattr(app_event_tx, "send", None)
        if callable(sender):
            sender(payload)
        elif isinstance(app_event_tx, list):
            app_event_tx.append(payload)

    spawn_pet_load(run)
    return True


def spawn_pet_load(f: Callable[[], Any]) -> None:
    f()


def _call_bool(obj: Any, name: str) -> bool:
    method = getattr(obj, name, None)
    return bool(method()) if callable(method) else bool(getattr(obj, name, False))


def _area_bottom(area: Any) -> int:
    if isinstance(area, dict):
        return int(area.get("y", 0)) + int(area.get("height", 0))
    bottom = getattr(area, "bottom", None)
    if callable(bottom):
        return int(bottom())
    return int(getattr(area, "y", 0)) + int(getattr(area, "height", 0))


class _SupportedPetImages:
    def unsupported_message(self) -> None:
        return None


__all__ = [
    "AMBIENT_PET_WRAP_GAP_COLUMNS",
    "ChatWidgetPetsModel",
    "BottomPanePetsModel",
    "MCP_STARTUP_MULTI_HEADER_PREFIX" if False else "PET_SELECTION_LOADING_VIEW_ID",
    "PetsConfig",
    "RUST_MODULE",
    "SelectionViewParamsPlan",
    "load_ambient_pet",
    "spawn_pet_load",
    "start_configured_pet_load_if_needed",
]
