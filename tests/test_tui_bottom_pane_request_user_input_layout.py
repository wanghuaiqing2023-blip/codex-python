from dataclasses import dataclass

from pycodex.tui.bottom_pane.request_user_input.layout import LayoutPlan
from pycodex.tui.bottom_pane.request_user_input.layout import OptionsHeights
from pycodex.tui.bottom_pane.request_user_input.layout import OptionsLayoutArgs
from pycodex.tui.bottom_pane.request_user_input.layout import OptionsNormalArgs
from pycodex.tui.bottom_pane.request_user_input.layout import Rect
from pycodex.tui.bottom_pane.request_user_input.layout import build_layout_areas
from pycodex.tui.bottom_pane.request_user_input.layout import layout_sections
from pycodex.tui.bottom_pane.request_user_input.layout import layout_with_options
from pycodex.tui.bottom_pane.request_user_input.layout import layout_with_options_normal
from pycodex.tui.bottom_pane.request_user_input.layout import layout_without_options_normal
from pycodex.tui.bottom_pane.request_user_input.layout import layout_without_options_tight


@dataclass
class Overlay:
    options: bool = False
    notes_visible: bool = False
    question: tuple[str, ...] = ("Q1",)
    footer: int = 1
    notes_height: int = 2
    options_pref: int = 3
    options_full: int = 5

    def has_options(self):
        return self.options

    def notes_ui_visible(self):
        return self.notes_visible

    def footer_required_height(self, width):
        return self.footer

    def notes_input_height(self, width):
        return self.notes_height

    def wrapped_question_lines(self, width):
        return list(self.question)

    def options_preferred_height(self, width):
        return self.options_pref

    def options_required_height(self, width):
        return self.options_full


def test_layout_without_options_tight_truncates_question_and_hides_everything_else():
    lines = ["a", "b", "c"]
    plan = layout_without_options_tight(2, 3, lines)

    assert lines == ["a", "b"]
    assert plan == LayoutPlan(progress_height=0, question_height=2, spacer_after_question=0, options_height=0, spacer_after_options=0, notes_height=0, footer_lines=0)


def test_layout_without_options_normal_allocates_notes_footer_progress_and_extra_to_notes():
    plan = layout_without_options_normal(8, 2, 2, 1)

    assert plan.question_height == 2
    assert plan.notes_height == 4
    assert plan.footer_lines == 1
    assert plan.progress_height == 1


def test_layout_with_options_truncates_question_to_leave_minimum_option_row():
    overlay = Overlay(options=True, question=("q1", "q2", "q3"), options_pref=2, options_full=4)
    lines = ["q1", "q2", "q3"]

    plan = layout_with_options(overlay, OptionsLayoutArgs(available_height=2, width=20, question_height=3, notes_pref_height=0, footer_pref=1, notes_visible=False), lines)

    assert lines == ["q1"]
    assert plan.question_height == 1
    assert plan.options_height == 1


def test_layout_with_options_hidden_notes_reserves_progress_footer_and_spacers_by_shrinking_options():
    plan = layout_with_options_normal(
        OptionsNormalArgs(available_height=8, question_height=2, notes_pref_height=3, footer_pref=1, notes_visible=False),
        OptionsHeights(preferred=5, full=7),
    )

    assert plan.progress_height == 1
    assert plan.footer_lines == 1
    assert plan.spacer_after_options == 1
    assert plan.spacer_after_question == 0
    assert plan.notes_height == 0
    assert plan.options_height == 4


def test_layout_with_options_visible_notes_prefers_footer_spacer_then_notes():
    plan = layout_with_options_normal(
        OptionsNormalArgs(available_height=10, question_height=2, notes_pref_height=3, footer_pref=1, notes_visible=True),
        OptionsHeights(preferred=2, full=5),
    )

    assert plan.progress_height == 1
    assert plan.footer_lines == 1
    assert plan.spacer_after_question == 1
    assert plan.options_height == 2
    assert plan.notes_height == 3


def test_build_layout_areas_stacks_sections_with_spacers():
    areas = build_layout_areas(Rect(5, 10, 30, 20), LayoutPlan(1, 2, 1, 3, 1, 4, 1))

    assert areas == (
        Rect(5, 10, 30, 1),
        Rect(5, 11, 30, 2),
        Rect(5, 14, 30, 3),
        Rect(5, 18, 30, 4),
    )


def test_layout_sections_without_options_returns_truncated_lines_and_areas():
    overlay = Overlay(options=False, question=("q1", "q2", "q3"), notes_height=2, footer=1)
    sections = layout_sections(overlay, Rect(0, 0, 20, 2))

    assert sections.question_lines == ["q1", "q2"]
    assert sections.question_area.height == 2
    assert sections.notes_area.height == 0
    assert sections.footer_lines == 0


def test_layout_sections_with_options_uses_options_area_and_footer_lines():
    overlay = Overlay(options=True, notes_visible=False, question=("q",), footer=1, options_pref=2, options_full=4)
    sections = layout_sections(overlay, {"x": 0, "y": 0, "width": 20, "height": 7})

    assert sections.question_lines == ["q"]
    assert sections.options_area.height >= 1
    assert sections.footer_lines <= 1
