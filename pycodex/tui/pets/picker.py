"""Builds the ``/pets`` picker dialog model for the TUI.

Upstream source: ``codex/codex-rs/tui/src/pets/picker.rs``.

Rust returns bottom-pane ``SelectionViewParams`` containing callbacks and ratatui
side-content.  Python represents the same contract as semantic dataclasses with
explicit action/event plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .._porting import RustTuiModule
from . import catalog
from .model import CUSTOM_PET_PREFIX, Pet, custom_pet_selector
from .preview import PetPickerPreviewState

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::picker",
    source="codex/codex-rs/tui/src/pets/picker.rs",
    status="complete",
)

DEFAULT_PET_ID = "codex"
DISABLED_PET_ID = "disabled"
PET_PICKER_VIEW_ID = "pet-picker"
PET_PICKER_PREVIEW_WIDTH = 30
PET_PICKER_PREVIEW_MIN_WIDTH = 28
DISABLED_SEARCH_VALUE = "disable disabled hide hidden off none"


@dataclass(frozen=True)
class PetPickerEntry:
    selector: str
    legacy_selector: Optional[str]
    display_name: str
    description: Optional[str] = None


@dataclass(frozen=True)
class SelectionActionPlan:
    event: str
    payload: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionItemPlan:
    name: str
    description: Optional[str]
    is_current: bool
    dismiss_on_select: bool
    search_value: Optional[str]
    actions: Tuple[SelectionActionPlan, ...]


@dataclass(frozen=True)
class SelectionViewParamsPlan:
    view_id: Optional[str]
    title: Optional[str]
    subtitle: Optional[str]
    footer_hint: Optional[str]
    items: Tuple[SelectionItemPlan, ...]
    is_searchable: bool
    search_placeholder: Optional[str]
    initial_selected_idx: Optional[int]
    side_content: Any
    side_content_width: Tuple[str, int]
    side_content_min_width: int
    stacked_side_content: bool
    preserve_side_content_bg: bool
    preview_pet_ids: Tuple[str, ...]

    def selection_changed_event(self, idx: int) -> Optional[SelectionActionPlan]:
        if idx < 0 or idx >= len(self.preview_pet_ids):
            return None
        return SelectionActionPlan("PetPreviewRequested", {"pet_id": self.preview_pet_ids[idx]})


def build_pet_picker_params(
    current_pet: Optional[str],
    codex_home: Union[str, Path],
    preview_state: PetPickerPreviewState,
) -> SelectionViewParamsPlan:
    preferred_pet = current_pet if current_pet is not None else DEFAULT_PET_ID
    entries = sorted(available_pet_entries(codex_home), key=lambda entry: entry.display_name)
    for idx, entry in enumerate(list(entries)):
        if entry.selector == DISABLED_PET_ID:
            disabled = entries.pop(idx)
            entries.insert(0, disabled)
            break

    initial_selected_idx: Optional[int] = None
    preview_pet_ids = tuple(entry.selector for entry in entries)
    items: List[SelectionItemPlan] = []
    for idx, entry in enumerate(entries):
        is_current = current_pet is not None and (
            current_pet == entry.selector or entry.legacy_selector == current_pet
        )
        if preferred_pet == entry.selector or entry.legacy_selector == preferred_pet:
            initial_selected_idx = idx

        pet_id = entry.selector
        if pet_id == DISABLED_PET_ID:
            search_value = DISABLED_SEARCH_VALUE
            actions = (SelectionActionPlan("PetDisabled"),)
        else:
            search_value = entry.selector
            actions = (SelectionActionPlan("PetSelected", {"pet_id": pet_id}),)

        items.append(
            SelectionItemPlan(
                name=entry.display_name,
                description=entry.description,
                is_current=is_current,
                dismiss_on_select=True,
                search_value=search_value,
                actions=actions,
            )
        )

    return SelectionViewParamsPlan(
        view_id=PET_PICKER_VIEW_ID,
        title="Select Pet",
        subtitle="Choose a pet to wake in the terminal.",
        footer_hint="standard_popup_hint_line",
        items=tuple(items),
        is_searchable=True,
        search_placeholder="Type to filter pets...",
        initial_selected_idx=initial_selected_idx,
        side_content=preview_state.renderable(),
        side_content_width=("fixed", PET_PICKER_PREVIEW_WIDTH),
        side_content_min_width=PET_PICKER_PREVIEW_MIN_WIDTH,
        stacked_side_content=True,
        preserve_side_content_bg=True,
        preview_pet_ids=preview_pet_ids,
    )


def available_pet_entries(codex_home: Union[str, Path]) -> List[PetPickerEntry]:
    entries = [
        PetPickerEntry(
            selector=pet.id,
            legacy_selector=None,
            display_name=pet.display_name,
            description=pet.description,
        )
        for pet in catalog.BUILTIN_PETS
    ]
    entries.append(
        PetPickerEntry(
            selector=DISABLED_PET_ID,
            legacy_selector=None,
            display_name="Disable terminal pets",
            description=None,
        )
    )
    entries.extend(custom_pet_entries(codex_home))
    return entries


def custom_pet_entries(codex_home: Union[str, Path]) -> List[PetPickerEntry]:
    home = Path(codex_home)
    entries_by_selector: Dict[str, PetPickerEntry] = {}
    for directory_name, manifest_file in (("avatars", "avatar.json"), ("pets", "pet.json")):
        root = home / directory_name
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or not (child / manifest_file).is_file():
                continue
            pet_id = child.name
            if pet_id == DISABLED_PET_ID or pet_id.startswith(CUSTOM_PET_PREFIX):
                continue
            selector = custom_pet_selector(pet_id)
            try:
                pet = Pet.load_with_codex_home(selector, home)
            except Exception:
                continue
            entries_by_selector[selector] = PetPickerEntry(
                selector=selector,
                legacy_selector=pet_id,
                display_name=pet.display_name,
                description=pet.description or None,
            )
    return list(entries_by_selector.values())


__all__ = [
    "DEFAULT_PET_ID",
    "DISABLED_PET_ID",
    "DISABLED_SEARCH_VALUE",
    "PET_PICKER_PREVIEW_MIN_WIDTH",
    "PET_PICKER_PREVIEW_WIDTH",
    "PET_PICKER_VIEW_ID",
    "PetPickerEntry",
    "RUST_MODULE",
    "SelectionActionPlan",
    "SelectionItemPlan",
    "SelectionViewParamsPlan",
    "available_pet_entries",
    "build_pet_picker_params",
    "custom_pet_entries",
]
