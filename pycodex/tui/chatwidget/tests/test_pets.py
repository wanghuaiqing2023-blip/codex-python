from pycodex.tui.chatwidget.pets import (
    AMBIENT_PET_WRAP_GAP_COLUMNS,
    PET_SELECTION_LOADING_VIEW_ID,
    ChatWidgetPetsModel,
    PetsConfig,
    load_ambient_pet,
    start_configured_pet_load_if_needed,
)
from pycodex.tui.pets import DISABLED_PET_ID
from pycodex.tui.pets.preview import PetPickerPreviewStatus


class Pet:
    def __init__(self, columns: int = 5):
        self.columns = columns
        self.support = None
        self.notifications = []

    def image_enabled(self):
        return True

    def image_columns(self):
        return self.columns

    def draw_request(self, area, anchor_bottom_y):
        return ("draw", area, anchor_bottom_y)

    def preview_draw_request(self, area):
        return ("preview", area)

    def set_notification(self, kind, body):
        self.notifications.append((kind, body))

    def set_image_support_for_tests(self, support):
        self.support = support


class Unsupported:
    def unsupported_message(self):
        return "no pets here"


def test_load_ambient_pet_skips_missing_disabled_and_swallows_loader_errors() -> None:
    assert load_ambient_pet(PetsConfig(tui_pet=None), None, loader=lambda *args: Pet()) is None
    assert load_ambient_pet(PetsConfig(tui_pet=DISABLED_PET_ID), None, loader=lambda *args: Pet()) is None
    assert load_ambient_pet(PetsConfig(tui_pet="codex"), None, loader=lambda *args: (_ for _ in ()).throw(RuntimeError("boom"))) is None

    pet = Pet()
    assert load_ambient_pet(PetsConfig(tui_pet="codex", animations=False), "frame", loader=lambda *args: pet) is pet


def test_start_configured_pet_load_if_needed_gates_and_sends_event() -> None:
    events = []
    assert start_configured_pet_load_if_needed(PetsConfig(tui_pet=None), True, None, events, loader=lambda *args: Pet()) is False
    assert start_configured_pet_load_if_needed(PetsConfig(tui_pet=DISABLED_PET_ID), True, None, events, loader=lambda *args: Pet()) is False
    assert start_configured_pet_load_if_needed(PetsConfig(tui_pet="codex"), False, None, events, loader=lambda *args: Pet()) is False

    assert start_configured_pet_load_if_needed(PetsConfig(tui_pet="codex"), True, "frame", events, loader=lambda *args: "pet") is True
    assert events == [("ConfiguredPetLoaded", "codex", "pet")]


def test_start_configured_pet_load_failure_sends_error_string() -> None:
    # Rust parity: start_configured_pet_load_if_needed maps load errors into
    # AppEvent::ConfiguredPetLoaded { result: Err(err.to_string()) }.
    events = []

    def fail(*_args):
        raise RuntimeError("pack missing")

    assert start_configured_pet_load_if_needed(PetsConfig(tui_pet="codex"), True, "frame", events, loader=fail) is True
    assert events == [("ConfiguredPetLoaded", "codex", "pack missing")]


def test_widget_ambient_pet_methods_and_wrap_width() -> None:
    model = ChatWidgetPetsModel(ambient_pet=Pet(columns=7))
    model.set_ambient_pet_notification("happy", "hi")

    assert model.ambient_pet.notifications == [("happy", "hi")]
    assert model.ambient_pet_wrap_reserved_cols() == 7 + AMBIENT_PET_WRAP_GAP_COLUMNS
    assert model.history_wrap_width(3) == 1
    assert model.ambient_pet_draw({"y": 2, "height": 10}, composer_bottom_y=4) == ("draw", {"y": 2, "height": 10}, 4)

    model.config.tui_pet_anchor = "screen-bottom"
    assert model.ambient_pet_draw({"y": 2, "height": 10}, composer_bottom_y=4) == ("draw", {"y": 2, "height": 10}, 12)

    model.bottom_pane.modal_or_popup_active = True
    assert model.ambient_pet_draw({"y": 2, "height": 10}, composer_bottom_y=4) is None

    model.disable_ambient_pet_for_session()
    assert model.ambient_pet is None
    assert model.redraw_requests == 1


def test_pets_picker_unsupported_blocks_open_and_select() -> None:
    model = ChatWidgetPetsModel(pet_image_support_override=Unsupported())

    model.open_pets_picker()
    model.select_pet_by_id("codex")

    assert model.warnings == ["no pets here", "no pets here"]
    assert model.events == []
    assert model.bottom_pane.shown_views == []


def test_open_pets_picker_success_starts_preview_and_select_emits_event() -> None:
    model = ChatWidgetPetsModel()

    model.open_pets_picker()
    model.select_pet_by_id("codex")

    assert model.bottom_pane.shown_views[-1].view_id == "pet-picker"
    assert model.events == [
        ("PetPreviewLoadRequested", 1, "codex"),
        ("PetSelected", "codex"),
    ]


def test_set_tui_pet_loads_pet_and_loaded_variant_applies_support() -> None:
    pet = Pet()
    model = ChatWidgetPetsModel(loader=lambda *args: pet, pet_image_support_override="support")

    model.set_tui_pet("codex")

    assert model.config.tui_pet == "codex"
    assert model.ambient_pet is pet
    assert pet.support == "support"
    assert model.redraw_requests == 1

    second = Pet()
    model.set_tui_pet_loaded("other", second)
    assert model.config.tui_pet == "other"
    assert model.ambient_pet is second
    assert second.support == "support"


def test_preview_load_disabled_ready_error_and_stale_request() -> None:
    model = ChatWidgetPetsModel()

    model.start_pet_picker_preview(DISABLED_PET_ID)
    assert model.pet_picker_preview_state.status() is PetPickerPreviewStatus.Disabled
    disabled_request_id = model.pet_picker_preview_request_id

    model.start_pet_picker_preview("codex")
    assert model.pet_picker_preview_state.status() is PetPickerPreviewStatus.Loading
    assert model.events[-1] == ("PetPreviewLoadRequested", disabled_request_id + 1, "codex")

    model.finish_pet_picker_preview_load(999, Pet())
    assert model.pet_picker_preview_pet is None

    pet = Pet()
    model.finish_pet_picker_preview_load(model.pet_picker_preview_request_id, pet)
    assert model.pet_picker_preview_state.status() is PetPickerPreviewStatus.Ready
    assert model.pet_picker_preview_pet is pet

    model.start_pet_picker_preview("codex")
    model.finish_pet_picker_preview_load(model.pet_picker_preview_request_id, RuntimeError("bad pet"))
    assert model.pet_picker_preview_state.status() is PetPickerPreviewStatus.Error
    assert model.pet_picker_preview_pet is None


def test_pet_preview_and_selection_request_ids_wrap_like_u64() -> None:
    # Rust parity: both pet_picker_preview_request_id and pet_selection_load_request_id
    # use wrapping_add(1) on u64 counters.
    model = ChatWidgetPetsModel()
    model.pet_picker_preview_request_id = 2**64 - 1
    model.start_pet_picker_preview("codex")
    assert model.pet_picker_preview_request_id == 0
    assert model.events[-1] == ("PetPreviewLoadRequested", 0, "codex")

    model.pet_selection_load_request_id = 2**64 - 1
    assert model.show_pet_selection_loading_popup() == 0
    assert model.pet_selection_load_request_id == 0


def test_preview_draw_visibility_clear_and_render_failure() -> None:
    model = ChatWidgetPetsModel(pet_picker_preview_pet=Pet())
    model.bottom_pane.selected_view_ids.add("pet-picker")
    model.pet_picker_preview_state.update(lambda inner: setattr(inner, "last_area", (1, 2, 3, 4)))

    assert model.pet_picker_preview_draw() == ("preview", (1, 2, 3, 4))
    assert model.should_clear_pet_picker_preview_image() is True
    assert model.should_clear_pet_picker_preview_image() is False

    model.fail_pet_picker_preview_render("render failed")
    assert model.pet_picker_preview_state.status() is PetPickerPreviewStatus.Error
    assert model.pet_picker_preview_pet is None


def test_selection_loading_popup_request_id_and_dismissal() -> None:
    model = ChatWidgetPetsModel(pet_picker_preview_pet=Pet())
    request_id = model.show_pet_selection_loading_popup()

    assert request_id == 1
    assert model.pet_picker_preview_pet is None
    assert model.bottom_pane.shown_views[-1].view_id == PET_SELECTION_LOADING_VIEW_ID
    assert model.finish_pet_selection_loading_popup(999) is False
    assert model.finish_pet_selection_loading_popup(request_id) is True
    assert model.bottom_pane.dismissed_view_ids == [PET_SELECTION_LOADING_VIEW_ID]
