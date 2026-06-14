"""Model migration prompt semantics for Rust ``codex-tui::model_migration``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Set

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="model_migration", source="codex/codex-rs/tui/src/model_migration.rs")


class ModelMigrationOutcome(Enum):
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    EXIT = "Exit"


@dataclass(frozen=True)
class ModelMigrationCopy:
    heading: List[str] = field(default_factory=list)
    content: List[str] = field(default_factory=list)
    can_opt_out: bool = False
    markdown: Optional[str] = None


class MigrationMenuOption(Enum):
    TRY_NEW_MODEL = "TryNewModel"
    USE_EXISTING_MODEL = "UseExistingModel"

    @classmethod
    def all(cls) -> List["MigrationMenuOption"]:
        return [cls.TRY_NEW_MODEL, cls.USE_EXISTING_MODEL]

    def label(self) -> str:
        if self is MigrationMenuOption.TRY_NEW_MODEL:
            return "Try new model"
        return "Use existing model"


def migration_copy_for_models(
    current_model: str,
    target_model: str,
    model_link: Optional[str],
    migration_copy: Optional[str],
    migration_markdown: Optional[str],
    target_display_name: str,
    target_description: Optional[str],
    can_opt_out: bool,
) -> ModelMigrationCopy:
    if migration_markdown is not None:
        return ModelMigrationCopy(
            can_opt_out=can_opt_out,
            markdown=fill_migration_markdown(migration_markdown, current_model, target_model),
        )

    heading = [f"Codex just got an upgrade. Introducing {target_display_name}."]
    if migration_copy is not None:
        description_line = migration_copy
    elif target_description:
        description_line = target_description
    else:
        description_line = f"{target_display_name} is recommended for better performance and reliability."

    content: List[str] = []
    if migration_copy is None:
        content.append(f"We recommend switching from {current_model} to {target_model}.")
        content.append("")

    if model_link is not None:
        content.append(f"{description_line} Learn more about {target_display_name} at {model_link}")
        content.append("")
    else:
        content.append(description_line)
        content.append("")

    if can_opt_out:
        content.append(f"You can continue using {current_model} if you prefer.")
    else:
        content.append("Press enter to continue")

    return ModelMigrationCopy(heading=heading, content=content, can_opt_out=can_opt_out, markdown=None)


async def run_model_migration_prompt(tui: Any, copy: ModelMigrationCopy) -> ModelMigrationOutcome:
    alt = AltScreenGuard.enter(tui)
    screen = ModelMigrationScreen.new(_frame_requester_from_tui(alt.tui), copy)
    try:
        _draw_model_migration_screen(alt.tui, screen)
        events = alt.tui.event_stream()
        async for event in events:
            if screen.is_done():
                break
            kind = getattr(event, "kind", None) if not isinstance(event, dict) else event.get("kind")
            if kind == "Key":
                screen.handle_key(getattr(event, "key", None) if not isinstance(event, dict) else event.get("key"))
            elif kind == "Paste":
                continue
            elif kind in {"Draw", "Resize"}:
                _draw_model_migration_screen(alt.tui, screen)
        if not screen.is_done():
            screen.accept()
        return screen.outcome()
    finally:
        alt.close()


def _draw_model_migration_screen(tui: Any, screen: "ModelMigrationScreen") -> None:
    draw = getattr(tui, "draw", None)
    if callable(draw):
        draw(screen.render_ref)


def _frame_requester_from_tui(tui: Any) -> Any:
    requester = getattr(tui, "frame_requester", None)
    return requester() if callable(requester) else requester


class ModelMigrationScreen:
    def __init__(self, request_frame: Any, copy: ModelMigrationCopy) -> None:
        self.request_frame = request_frame
        self.copy = copy
        self.done = False
        self._outcome = ModelMigrationOutcome.ACCEPTED
        self.highlighted_option = MigrationMenuOption.TRY_NEW_MODEL

    @classmethod
    def new(cls, request_frame: Any, copy: ModelMigrationCopy) -> "ModelMigrationScreen":
        return cls(request_frame, copy)

    def finish_with(self, outcome: ModelMigrationOutcome) -> None:
        self._outcome = outcome
        self.done = True
        _schedule_frame(self.request_frame)

    def accept(self) -> None:
        self.finish_with(ModelMigrationOutcome.ACCEPTED)

    def reject(self) -> None:
        self.finish_with(ModelMigrationOutcome.REJECTED)

    def exit(self) -> None:
        self.finish_with(ModelMigrationOutcome.EXIT)

    def confirm_selection(self) -> None:
        if self.copy.can_opt_out:
            if self.highlighted_option is MigrationMenuOption.TRY_NEW_MODEL:
                self.accept()
            else:
                self.reject()
        else:
            self.accept()

    def highlight_option(self, option: MigrationMenuOption) -> None:
        if self.highlighted_option is not option:
            self.highlighted_option = option
            _schedule_frame(self.request_frame)

    def handle_key(self, key_event: Any) -> None:
        if _key_kind(key_event) == "Release":
            return
        if is_ctrl_exit_combo(key_event):
            self.exit()
            return
        code = _key_code(key_event)
        if self.copy.can_opt_out:
            self.handle_menu_key(code)
        elif code in {"Esc", "Enter"}:
            self.accept()

    def is_done(self) -> bool:
        return self.done

    def outcome(self) -> ModelMigrationOutcome:
        return self._outcome

    def handle_menu_key(self, code: str) -> None:
        if code in {"Up", "k"}:
            self.highlight_option(MigrationMenuOption.TRY_NEW_MODEL)
        elif code in {"Down", "j"}:
            self.highlight_option(MigrationMenuOption.USE_EXISTING_MODEL)
        elif code == "1":
            self.highlight_option(MigrationMenuOption.TRY_NEW_MODEL)
            self.accept()
        elif code == "2":
            self.highlight_option(MigrationMenuOption.USE_EXISTING_MODEL)
            self.reject()
        elif code in {"Enter", "Esc"}:
            self.confirm_selection()

    def heading_line(self) -> str:
        return "> " + "".join(self.copy.heading)

    def render_content(self) -> List[str]:
        return self.render_lines(self.copy.content)

    def render_lines(self, lines: List[str]) -> List[str]:
        return [f"  {line}" if line else "" for line in lines]

    def render_markdown_content(self, markdown: str, area_width: Optional[int] = None) -> List[str]:
        return self.render_lines(_wrap_preserving_tail(markdown, max((area_width or 80) - 2, 1)))

    def render_menu(self) -> List[str]:
        rows = ["", "  Choose how you'd like Codex to proceed.", ""]
        for idx, option in enumerate(MigrationMenuOption.all()):
            marker = ">" if self.highlighted_option is option else " "
            rows.append(f"{marker} {idx + 1}. {option.label()}")
        rows.extend(["", "  Use Up/Down to move, press Enter to confirm"])
        return rows

    def render_ref(self, area_width: Optional[int] = None) -> List[str]:
        rows = [""]
        if self.copy.markdown is not None:
            rows.extend(self.render_markdown_content(self.copy.markdown, area_width))
        else:
            rows.append(self.heading_line())
            rows.append("")
            rows.extend(self.render_content())
        if self.copy.can_opt_out:
            rows.extend(self.render_menu())
        return rows


def _schedule_frame(request_frame: Any) -> None:
    schedule = getattr(request_frame, "schedule_frame", None)
    if callable(schedule):
        schedule()
    elif callable(request_frame):
        request_frame()


@dataclass
class AltScreenGuard:
    tui: Any

    @classmethod
    def enter(cls, tui: Any) -> "AltScreenGuard":
        enter = getattr(tui, "enter_alt_screen", None)
        if callable(enter):
            enter()
        return cls(tui)

    def close(self) -> None:
        leave = getattr(self.tui, "leave_alt_screen", None)
        if callable(leave):
            leave()


def drop(value: Any) -> None:
    if isinstance(value, AltScreenGuard):
        value.close()


def render_ref(screen: ModelMigrationScreen, area_width: Optional[int] = None) -> List[str]:
    return screen.render_ref(area_width)


def is_ctrl_exit_combo(key_event: Any) -> bool:
    modifiers = _key_modifiers(key_event)
    return "CONTROL" in modifiers and _key_code(key_event) in {"c", "d"}


def fill_migration_markdown(template: str, current_model: str, target_model: str) -> str:
    return template.replace("{model_from}", current_model).replace("{model_to}", target_model)


def _key_code(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event
    if isinstance(key_event, dict):
        code = key_event.get("code", "")
    else:
        code = getattr(key_event, "code", "")
    if isinstance(code, str) and code.startswith("Char(") and code.endswith(")"):
        return code[5:-1].strip("'\"")
    return str(code)


def _key_kind(key_event: Any) -> str:
    if isinstance(key_event, dict):
        return str(key_event.get("kind", "Press"))
    return str(getattr(key_event, "kind", "Press"))


def _key_modifiers(key_event: Any) -> Set[str]:
    if isinstance(key_event, dict):
        value = key_event.get("modifiers", set())
    else:
        value = getattr(key_event, "modifiers", set())
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value}


def _wrap_preserving_tail(text: str, width: int) -> List[str]:
    if width <= 0 or len(text) <= width:
        return [text]
    return [text[index : index + width] for index in range(0, len(text), width)]


__all__ = [
    "AltScreenGuard",
    "MigrationMenuOption",
    "ModelMigrationCopy",
    "ModelMigrationOutcome",
    "ModelMigrationScreen",
    "RUST_MODULE",
    "drop",
    "fill_migration_markdown",
    "is_ctrl_exit_combo",
    "migration_copy_for_models",
    "render_ref",
    "run_model_migration_prompt",
]
