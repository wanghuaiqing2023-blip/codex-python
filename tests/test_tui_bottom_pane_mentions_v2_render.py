from pycodex.tui.bottom_pane.mentions_v2.candidate import Candidate, MentionType, SearchResult, Selection
from pycodex.tui.bottom_pane.mentions_v2.render import build_line
from pycodex.tui.bottom_pane.mentions_v2.render import content_line
from pycodex.tui.bottom_pane.mentions_v2.render import file_name
from pycodex.tui.bottom_pane.mentions_v2.render import file_name_start
from pycodex.tui.bottom_pane.mentions_v2.render import line_text
from pycodex.tui.bottom_pane.mentions_v2.render import path_spans
from pycodex.tui.bottom_pane.mentions_v2.render import primary_spans
from pycodex.tui.bottom_pane.mentions_v2.render import primary_text_width
from pycodex.tui.bottom_pane.mentions_v2.render import render_popup
from pycodex.tui.bottom_pane.mentions_v2.render import render_rows
from pycodex.tui.bottom_pane.mentions_v2.render import secondary_line
from pycodex.tui.bottom_pane.mentions_v2.search_mode import SearchMode


def _tool(name="PluginTool", desc="Plugin desc", indices=None):
    return SearchResult(name, desc, MentionType.PLUGIN, Selection.Tool("@tool"), indices, 1)


def _file(path="src/main.rs", desc=None, indices=None, kind=MentionType.FILE):
    return SearchResult(path, desc, kind, Selection.File(path), indices, 1)


def test_file_name_start_and_primary_text_width_for_filesystem_rows():
    row = _file("src/nested/main.rs")
    assert file_name_start(row) == len("src/nested/")
    assert file_name(row) == "main.rs"
    assert primary_text_width(row) == len("main.rs")

    root = _file("README.md")
    assert file_name_start(root) == 0
    assert file_name(root) == "README.md"

    tool_file_selection = SearchResult("src/main.rs", None, MentionType.PLUGIN, Selection.File("src/main.rs"), None, 0)
    assert file_name_start(tool_file_selection) == -1
    assert file_name(tool_file_selection) is None


def test_primary_spans_highlight_match_indices_for_tools_and_cyan_file_names():
    spans = primary_spans(_tool("Alpha", indices=[0, 4]))
    assert [span.text for span in spans] == list("Alpha")
    assert spans[0].style == ("magenta", "bold")
    assert spans[1].style == ("magenta",)
    assert spans[4].style == ("magenta", "bold")

    file_spans = primary_spans(_file("src/main.rs"))
    assert file_spans == [file_spans[0]]
    assert file_spans[0].text == "main.rs"
    assert file_spans[0].style == ("cyan",)


def test_path_spans_show_dot_slash_or_path_prefix_with_highlights():
    assert path_spans(_file("main.rs"))[0].text == "./"

    spans = path_spans(_file("src/main.rs", indices=[0, 2, 4]))
    assert "".join(span.text for span in spans) == "src/"
    assert spans[0].style == ("dim", "bold")
    assert spans[1].style == ("dim",)
    assert spans[2].style == ("dim", "bold")


def test_secondary_line_for_file_combines_path_and_description():
    row = _file("src/main.rs", desc="entrypoint")
    secondary = secondary_line(row)
    assert line_text(secondary) == "src/  entrypoint"

    tool_secondary = secondary_line(_tool(desc="Tool description"))
    assert line_text(tool_secondary) == "Tool description"


def test_content_line_aligns_secondary_column_by_primary_width():
    short = _file("a.rs", desc="short")
    long = _file("long_name.rs", desc="long")
    line = content_line(short, primary_column_width=primary_text_width(long))
    assert line_text(line).startswith("a.rs")
    assert "  ./  short" in line_text(line)


def test_build_line_places_tag_at_right_and_bolds_selected_rows():
    line = build_line(_tool("Alpha", indices=[0]), selected=True, width=24, primary_column_width=5)
    text = line_text(line)
    assert text.endswith("Plugin")
    assert len(text) == 24
    assert line.spans[0].style[:2] == ("bold", "magenta")


def test_render_rows_empty_scroll_window_and_selection_adjustment():
    empty = render_rows({"width": 40, "height": 3}, [], [], {"selected_idx": None, "scroll_top": 0}, "No matches")
    assert line_text(empty[0]) == "No matches"
    assert empty[0].spans[0].style == ("italic",)

    rows = [_tool(f"item-{idx}", desc=None) for idx in range(8)]
    rendered = render_rows({"width": 40, "height": 3}, [], rows, {"selected_idx": 7, "scroll_top": 0}, "No matches")
    assert [line_text(line).strip().split()[0] for line in rendered] == ["item-5", "item-6", "item-7"]


def test_render_popup_adds_footer_when_area_is_tall_enough():
    popup = render_popup({"width": 80, "height": 5}, [], [_tool("Alpha")], {"selected_idx": 0, "scroll_top": 0}, "No matches", SearchMode.TOOLS)
    assert popup.footer is not None
    assert "[Plugins]" in popup.footer.text
    assert "Alpha" in line_text(popup.rows[0])
