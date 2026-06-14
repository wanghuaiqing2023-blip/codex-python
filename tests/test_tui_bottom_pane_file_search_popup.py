from pathlib import Path

from pycodex.tui.bottom_pane.file_search_popup import FileMatch, FileSearchPopup, file_match
from pycodex.tui.bottom_pane.popup_consts import MAX_POPUP_ROWS


def test_new_starts_waiting_with_empty_queries_and_visible_height_one():
    popup = FileSearchPopup.new()

    assert popup.display_query == ""
    assert popup.pending_query == ""
    assert popup.waiting
    assert popup.matches == []
    assert popup.selected_match() is None
    assert popup.calculate_required_height() == 1
    assert popup.empty_message() == "loading..."


def test_set_query_only_updates_when_pending_query_changes():
    popup = FileSearchPopup.new()
    popup.waiting = False

    popup.set_query("")
    assert not popup.waiting

    popup.set_query("file")
    assert popup.pending_query == "file"
    assert popup.waiting
    assert popup.display_query == ""


def test_set_empty_prompt_clears_matches_and_resets_selection():
    popup = FileSearchPopup.new()
    popup.set_query("file")
    popup.set_matches("file", [file_match(0), file_match(1)])
    popup.move_down()

    popup.set_empty_prompt()

    assert popup.display_query == ""
    assert popup.pending_query == ""
    assert not popup.waiting
    assert popup.matches == []
    assert popup.state.selected_idx is None
    assert popup.state.scroll_top == 0
    assert popup.empty_message() == "no matches"


def test_set_matches_keeps_only_the_first_page_of_results_matches_rust_test():
    popup = FileSearchPopup.new()
    popup.set_query("file")
    popup.set_matches("file", [file_match(index) for index in range(MAX_POPUP_ROWS + 2)])

    assert popup.matches == [file_match(index) for index in range(MAX_POPUP_ROWS)]
    assert popup.calculate_required_height() == MAX_POPUP_ROWS
    assert popup.display_query == "file"
    assert not popup.waiting
    assert popup.state.selected_idx == 0


def test_set_matches_ignores_stale_query_results():
    popup = FileSearchPopup.new()
    popup.set_query("new")
    popup.set_matches("old", [file_match(0)])

    assert popup.matches == []
    assert popup.display_query == ""
    assert popup.waiting
    assert popup.state.selected_idx is None


def test_set_matches_with_empty_results_stops_waiting_and_keeps_placeholder_height():
    popup = FileSearchPopup.new()
    popup.set_query("file")
    popup.set_matches("file", [file_match(0)])
    popup.move_down()

    popup.set_query("missing")
    popup.set_matches("missing", [])

    assert popup.display_query == "missing"
    assert popup.pending_query == "missing"
    assert popup.matches == []
    assert popup.waiting is False
    assert popup.state.selected_idx is None
    assert popup.calculate_required_height() == 1
    assert popup.empty_message() == "no matches"


def test_set_query_waiting_for_new_results_keeps_existing_matches_stable():
    popup = FileSearchPopup.new()
    popup.set_query("old")
    popup.set_matches("old", [file_match(0), file_match(1)])

    popup.set_query("new")

    assert popup.pending_query == "new"
    assert popup.display_query == "old"
    assert popup.waiting is True
    assert popup.matches == [file_match(0), file_match(1)]
    assert popup.calculate_required_height() == 2


def test_move_up_down_wrap_selection_and_selected_match():
    popup = FileSearchPopup.new()
    popup.set_query("file")
    popup.set_matches("file", [file_match(0), file_match(1), file_match(2)])

    assert popup.selected_match() == Path("src/file_00.rs")
    popup.move_down()
    assert popup.selected_match() == Path("src/file_01.rs")
    popup.move_down()
    assert popup.selected_match() == Path("src/file_02.rs")
    popup.move_down()
    assert popup.selected_match() == Path("src/file_00.rs")
    popup.move_up()
    assert popup.selected_match() == Path("src/file_02.rs")


def test_render_ref_converts_matches_to_generic_rows_and_empty_message():
    popup = FileSearchPopup.new()
    loading = popup.render_ref()
    assert loading.rows == ()
    assert loading.empty_message == "loading..."

    popup.set_query("py")
    popup.set_matches("py", [FileMatch(score=4, path=Path("src/app.py"), indices=[0, 4])])
    rendered = popup.render_ref()

    assert rendered.rows[0].name == "src\\app.py" or rendered.rows[0].name == "src/app.py"
    assert rendered.rows[0].match_indices == [0, 4]
    assert rendered.selected_idx == 0
    assert rendered.empty_message == "no matches"
