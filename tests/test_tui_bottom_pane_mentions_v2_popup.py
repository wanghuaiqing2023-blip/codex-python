from pycodex.tui.bottom_pane.mentions_v2.candidate import Candidate, MentionType, Selection
from pycodex.tui.bottom_pane.mentions_v2.filter import FileMatch
from pycodex.tui.bottom_pane.mentions_v2.popup import FileSearch, Popup
from pycodex.tui.bottom_pane.mentions_v2.search_mode import SearchMode


def candidate(name, mention_type=MentionType.PLUGIN):
    return Candidate(
        display_name=name,
        description=f"{name} desc",
        search_terms=[name],
        mention_type=mention_type,
        selection=Selection.Tool(f"@{name}"),
    )


def test_file_search_query_state_matches_rust_pending_display_and_clear_rules():
    search = FileSearch()

    search.set_query("a")
    assert search.pending_query == "a"
    assert search.display_query == ""
    assert search.waiting
    assert search.empty_message() == "loading..."

    search.set_matches("stale", [FileMatch("ignored.py")])
    assert search.matches == []
    assert search.waiting

    search.set_matches("a", [FileMatch(f"{idx}.py") for idx in range(12)])
    assert search.display_query == "a"
    assert len(search.matches) == 8
    assert not search.waiting
    assert search.should_show_matches()
    assert search.empty_message() == "no matches"

    search.set_query("")
    assert search.pending_query == ""
    assert search.display_query == ""
    assert not search.waiting
    assert search.matches == []


def test_popup_initial_state_required_height_and_selection_navigation():
    popup = Popup.new([candidate("alpha"), candidate("beta")])

    assert popup.query == ""
    assert popup.search_mode is SearchMode.RESULTS
    assert popup.calculate_required_height(1) == 10
    assert popup.selected() is None

    popup.move_down()
    assert popup.selected().insert_text == "@alpha"
    popup.move_down()
    assert popup.selected().insert_text == "@beta"
    popup.move_down()
    assert popup.selected().insert_text == "@alpha"
    popup.move_up()
    assert popup.selected().insert_text == "@beta"


def test_popup_set_query_updates_file_search_and_clamps_selection():
    popup = Popup.new([candidate("alpha"), candidate("beta")])

    popup.set_query("be")

    assert popup.query == "be"
    assert popup.file_search.pending_query == "be"
    assert popup.file_search.waiting
    assert popup.state.selected_idx == 0
    assert [row.display_name for row in popup.rows()] == ["beta"]
    assert popup.selected().insert_text == "@beta"

    popup.set_query("zzz")
    assert popup.rows() == []
    assert popup.state.selected_idx is None
    assert popup.state.scroll_top == 0


def test_popup_set_candidates_replaces_rows_and_clamps_selection():
    popup = Popup.new([candidate("alpha"), candidate("beta"), candidate("gamma")])
    popup.move_down()
    popup.move_down()
    assert popup.selected().insert_text == "@beta"

    popup.set_candidates([candidate("alpha")])

    assert [row.display_name for row in popup.rows()] == ["alpha"]
    assert popup.state.selected_idx == 0
    assert popup.selected().insert_text == "@alpha"

    popup.set_candidates([])
    assert popup.rows() == []
    assert popup.state.selected_idx is None
    assert popup.state.scroll_top == 0


def test_popup_file_matches_show_only_for_matching_pending_query_and_cap_to_popup_rows():
    popup = Popup.new([])
    popup.set_query("src")

    popup.set_file_matches("other", [FileMatch("ignored.py")])
    assert popup.rows() == []
    assert popup.file_search.empty_message() == "loading..."

    popup.set_file_matches("src", [FileMatch(f"src/{idx}.py", score=idx) for idx in range(12)])
    rows = popup.rows()
    assert len(rows) == 8
    assert popup.file_search.empty_message() == "no matches"
    assert popup.state.selected_idx == 0
    assert popup.selected().kind == "File"


def test_popup_search_mode_cycles_and_filters_rows():
    popup = Popup.new(
        [
            candidate("plugin", MentionType.PLUGIN),
            candidate("skill", MentionType.SKILL),
        ]
    )
    popup.set_query("p")
    popup.set_file_matches("p", [FileMatch("path.py")])

    assert [row.mention_type for row in popup.rows()] == [MentionType.PLUGIN, MentionType.FILE]

    popup.next_search_mode()
    assert popup.search_mode is SearchMode.FILESYSTEM_ONLY
    assert [row.mention_type for row in popup.rows()] == [MentionType.FILE]

    popup.next_search_mode()
    assert popup.search_mode is SearchMode.TOOLS
    assert [row.mention_type for row in popup.rows()] == [MentionType.PLUGIN]

    popup.previous_search_mode()
    assert popup.search_mode is SearchMode.FILESYSTEM_ONLY


def test_popup_render_ref_delegates_to_semantic_renderer_with_empty_messages():
    popup = Popup.new([])
    popup.set_query("pending")

    rendered = popup.render_ref({"width": 20, "height": 4})
    assert rendered.rows[0].text() == "loading..."
    assert rendered.footer is not None

    popup.set_query("")
    rendered = popup.render_ref({"width": 20, "height": 1})
    assert rendered.rows[0].text() == "no matches"
    assert rendered.footer is None
