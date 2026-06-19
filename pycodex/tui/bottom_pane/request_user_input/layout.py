"""Layout planner for Rust bottom_pane/request_user_input/layout.rs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..._porting import RustTuiModule
from ...ratatui_bridge import Rect

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::request_user_input::layout",
    source="codex/codex-rs/tui/src/bottom_pane/request_user_input/layout.rs",
)

DESIRED_SPACERS_BETWEEN_SECTIONS = 2


@dataclass
class LayoutSections:
    progress_area: Rect
    question_area: Rect
    question_lines: list[str]
    options_area: Rect
    notes_area: Rect
    footer_lines: int


@dataclass
class LayoutPlan:
    progress_height: int = 0
    question_height: int = 0
    spacer_after_question: int = 0
    options_height: int = 0
    spacer_after_options: int = 0
    notes_height: int = 0
    footer_lines: int = 0


@dataclass
class OptionsLayoutArgs:
    available_height: int
    width: int
    question_height: int
    notes_pref_height: int
    footer_pref: int
    notes_visible: bool


@dataclass
class OptionsNormalArgs:
    available_height: int
    question_height: int
    notes_pref_height: int
    footer_pref: int
    notes_visible: bool


@dataclass
class OptionsHeights:
    preferred: int
    full: int


def layout_sections(overlay: Any, area: Any) -> LayoutSections:
    rect = _rect(area)
    has_options = bool(_call(overlay, "has_options"))
    notes_visible = (not has_options) or bool(_call(overlay, "notes_ui_visible"))
    footer_pref = int(_call(overlay, "footer_required_height", rect.width))
    notes_pref_height = int(_call(overlay, "notes_input_height", rect.width))
    question_lines = list(_call(overlay, "wrapped_question_lines", rect.width))
    question_height = len(question_lines)

    if has_options:
        plan = layout_with_options(
            overlay,
            OptionsLayoutArgs(rect.height, rect.width, question_height, notes_pref_height, footer_pref, notes_visible),
            question_lines,
        )
    else:
        plan = layout_without_options(rect.height, question_height, notes_pref_height, footer_pref, question_lines)

    progress_area, question_area, options_area, notes_area = build_layout_areas(rect, plan)
    return LayoutSections(progress_area, question_area, question_lines, options_area, notes_area, plan.footer_lines)


def layout_with_options(overlay: Any, args: OptionsLayoutArgs, question_lines: list[str]) -> LayoutPlan:
    available_height = _u16(args.available_height)
    question_height = _u16(args.question_height)
    min_options_height = min(available_height, 1)
    max_question_height = _sat_sub(available_height, min_options_height)
    if question_height > max_question_height:
        question_height = max_question_height
        del question_lines[question_height:]
    return layout_with_options_normal(
        OptionsNormalArgs(available_height, question_height, args.notes_pref_height, args.footer_pref, args.notes_visible),
        OptionsHeights(preferred=int(_call(overlay, "options_preferred_height", args.width)), full=int(_call(overlay, "options_required_height", args.width))),
    )


def layout_with_options_normal(args: OptionsNormalArgs, options: OptionsHeights) -> LayoutPlan:
    available_height = _u16(args.available_height)
    question_height = _u16(args.question_height)
    max_options_height = _sat_sub(available_height, question_height)
    min_options_height = min(max_options_height, 1)
    options_height = max(min(_u16(options.preferred), max_options_height), min_options_height)
    used = question_height + options_height
    remaining = _sat_sub(available_height, used)

    desired_spacers = 1 if args.notes_visible else 1
    required_extra = _u16(args.footer_pref) + 1 + desired_spacers
    if remaining < required_extra:
        deficit = required_extra - remaining
        reducible = _sat_sub(options_height, min_options_height)
        reduce_by = min(deficit, reducible, 1 if not args.notes_visible else deficit)
        options_height = _sat_sub(options_height, reduce_by)
        remaining += reduce_by

    progress_height = 0
    if remaining > 0:
        progress_height = 1
        remaining -= 1

    if not args.notes_visible:
        spacer_after_options = 0
        if remaining > _u16(args.footer_pref):
            spacer_after_options = 1
            remaining -= 1
        elif remaining > 0 and _u16(args.footer_pref) > 0:
            spacer_after_options = 1
            remaining -= 1
        footer_lines = _u16(args.footer_pref)
        spacer_after_question = 0
        grow_by = min(remaining, _sat_sub(_u16(options.full), options_height))
        options_height += grow_by
        return LayoutPlan(progress_height, question_height, spacer_after_question, options_height, spacer_after_options, 0, footer_lines)

    footer_lines = min(_u16(args.footer_pref), remaining)
    remaining -= footer_lines
    spacer_after_question = 0
    if remaining > 0:
        spacer_after_question = 1
        remaining -= 1
    notes_height = min(_u16(args.notes_pref_height), remaining)
    remaining -= notes_height
    notes_height += remaining
    return LayoutPlan(progress_height, question_height, spacer_after_question, options_height, 0, notes_height, footer_lines)


def layout_without_options(available_height: int, question_height: int, notes_pref_height: int, footer_pref: int, question_lines: list[str]) -> LayoutPlan:
    if _u16(question_height) > _u16(available_height):
        return layout_without_options_tight(available_height, question_height, question_lines)
    return layout_without_options_normal(available_height, question_height, notes_pref_height, footer_pref)


def layout_without_options_tight(available_height: int, question_height: int, question_lines: list[str]) -> LayoutPlan:
    adjusted = min(_u16(question_height), _u16(available_height))
    del question_lines[adjusted:]
    return LayoutPlan(0, adjusted, 0, 0, 0, 0, 0)


def layout_without_options_normal(available_height: int, question_height: int, notes_pref_height: int, footer_pref: int) -> LayoutPlan:
    remaining = _sat_sub(_u16(available_height), _u16(question_height))
    notes_height = min(_u16(notes_pref_height), remaining)
    remaining -= notes_height
    footer_lines = min(_u16(footer_pref), remaining)
    remaining -= footer_lines
    progress_height = 0
    if remaining > 0:
        progress_height = 1
        remaining -= 1
    notes_height += remaining
    return LayoutPlan(progress_height, _u16(question_height), 0, 0, 0, notes_height, footer_lines)


def build_layout_areas(area: Any, heights: LayoutPlan) -> tuple[Rect, Rect, Rect, Rect]:
    rect = _rect(area)
    cursor_y = rect.y
    progress_area = Rect(rect.x, cursor_y, rect.width, heights.progress_height)
    cursor_y += heights.progress_height
    question_area = Rect(rect.x, cursor_y, rect.width, heights.question_height)
    cursor_y += heights.question_height + heights.spacer_after_question
    options_area = Rect(rect.x, cursor_y, rect.width, heights.options_height)
    cursor_y += heights.options_height + heights.spacer_after_options
    notes_area = Rect(rect.x, cursor_y, rect.width, heights.notes_height)
    return progress_area, question_area, options_area, notes_area


def _call(obj: Any, name: str, *args: Any) -> Any:
    value = getattr(obj, name)
    return value(*args) if callable(value) else value


def _rect(area: Any) -> Rect:
    if isinstance(area, Rect):
        return area
    if isinstance(area, dict):
        return Rect(int(area.get("x", 0)), int(area.get("y", 0)), max(int(area.get("width", 0)), 0), max(int(area.get("height", 0)), 0))
    return Rect(int(getattr(area, "x", 0)), int(getattr(area, "y", 0)), max(int(getattr(area, "width", 0)), 0), max(int(getattr(area, "height", 0)), 0))


def _u16(value: int) -> int:
    return max(int(value), 0)


def _sat_sub(left: int, right: int) -> int:
    return max(_u16(left) - _u16(right), 0)


__all__ = [
    "DESIRED_SPACERS_BETWEEN_SECTIONS",
    "LayoutPlan",
    "LayoutSections",
    "OptionsHeights",
    "OptionsLayoutArgs",
    "OptionsNormalArgs",
    "RUST_MODULE",
    "Rect",
    "build_layout_areas",
    "layout_sections",
    "layout_with_options",
    "layout_with_options_normal",
    "layout_without_options",
    "layout_without_options_normal",
    "layout_without_options_tight",
]
