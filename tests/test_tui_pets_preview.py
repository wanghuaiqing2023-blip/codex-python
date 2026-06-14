"""Parity tests for ``codex-tui/src/pets/preview.rs``."""

from __future__ import annotations

from pycodex.tui.pets.preview import (
    PetPickerPreviewState,
    PetPickerPreviewStatus,
    centered_text_area,
)


def test_centered_text_area_centers_vertically():
    assert centered_text_area((5, 10, 20, 8), 2) == (5, 13, 20, 2)
    assert centered_text_area((5, 10, 20, 1), 2) == (5, 10, 20, 1)


def test_preview_state_transitions_and_area_tracking():
    state = PetPickerPreviewState()
    renderable = state.renderable()

    assert renderable.render((1, 2, 30, 8)) is None
    assert state.area() == (1, 2, 30, 8)

    state.set_loading()
    plan = renderable.render((1, 2, 30, 8))
    assert plan is not None
    assert plan.text_area == (1, 5, 30, 1)
    assert [(line.text, line.style) for line in plan.lines] == [("Loading preview...", "bold")]

    state.set_disabled()
    plan = renderable.render({"x": 1, "y": 2, "width": 30, "height": 8})
    assert plan is not None
    assert plan.text_area == (1, 5, 30, 2)
    assert [(line.text, line.style) for line in plan.lines] == [
        ("Terminal pets disabled", "bold"),
        ("No pet will be shown.", "dim"),
    ]

    state.set_ready()
    assert renderable.render((1, 2, 30, 8)) is None
    assert state.area() == (1, 2, 30, 8)

    state.set_error("boom")
    plan = renderable.render((1, 2, 30, 8))
    assert plan is not None
    assert [(line.text, line.style) for line in plan.lines] == [
        ("Preview unavailable", "bold"),
        ("boom", "dim"),
    ]

    state.clear()
    assert state.status is PetPickerPreviewStatus.Hidden
    assert state.area() is None
    assert renderable.desired_height(100) == 4
