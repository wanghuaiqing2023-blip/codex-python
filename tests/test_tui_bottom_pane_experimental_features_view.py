from pycodex.tui.bottom_pane.experimental_features_view import ExperimentalFeatureItem
from pycodex.tui.bottom_pane.experimental_features_view import ExperimentalFeaturesView
from pycodex.tui.bottom_pane.experimental_features_view import experimental_popup_hint_line


def _items(count=3):
    return [
        ExperimentalFeatureItem(f"feature-{idx}", f"Feature {idx}", f"Description {idx}", idx % 2 == 0)
        for idx in range(count)
    ]


def test_new_initializes_selection_only_when_features_exist():
    view = ExperimentalFeaturesView.new(_items(2))
    empty = ExperimentalFeaturesView.new([])

    assert view.selected_idx == 0
    assert empty.selected_idx is None
    assert view.visible_len() == 2
    assert empty.visible_len() == 0


def test_build_rows_marks_selected_and_enabled_state():
    view = ExperimentalFeaturesView.new(_items(2))
    rows = view.build_rows()

    assert rows[0].name == "› [x] Feature 0"
    assert rows[0].description == "Description 0"
    assert rows[0].selected is True
    assert rows[1].name == "  [ ] Feature 1"


def test_navigation_wraps_pages_and_jumps_with_scroll_visibility():
    view = ExperimentalFeaturesView.new(_items(12))

    view.move_up()
    assert view.selected_idx == 11
    assert view.scroll_top > 0

    view.move_down()
    assert view.selected_idx == 0
    assert view.scroll_top == 0

    view.page_down()
    assert view.selected_idx == 8
    view.page_up()
    assert view.selected_idx == 0

    view.jump_bottom()
    assert view.selected_idx == 11
    view.jump_top()
    assert view.selected_idx == 0


def test_toggle_selected_and_key_events():
    view = ExperimentalFeaturesView.new(_items(2))

    view.handle_key_event(" ")
    assert view.features[0].enabled is False

    view.handle_key_event("down")
    assert view.selected_idx == 1
    view.handle_key_event(" ")
    assert view.features[1].enabled is True


def test_on_ctrl_c_saves_updates_and_completes_only_when_features_exist():
    events = []
    view = ExperimentalFeaturesView.new(_items(2), events)

    assert view.on_ctrl_c() == "Handled"
    assert view.is_complete()
    assert events == [
        {
            "type": "UpdateFeatureFlags",
            "updates": [("feature-0", True), ("feature-1", False)],
        }
    ]

    empty_events = []
    empty = ExperimentalFeaturesView.new([], empty_events)
    empty.on_ctrl_c()
    assert empty_events == []
    assert empty.is_complete()


def test_rows_width_hint_desired_height_and_render_empty_state():
    assert ExperimentalFeaturesView.rows_width(1) == 0
    assert ExperimentalFeaturesView.rows_width(10) == 8
    assert experimental_popup_hint_line() == "Press Space to select or Enter to save for next conversation"

    view = ExperimentalFeaturesView.new([])
    assert view.desired_height(40) == 7
    lines = view.render((0, 0, 40, 10))
    assert lines[0].text == "Experimental features"
    assert any("No experimental features" in line.text for line in lines)
    assert lines[-1].style == "hint"
