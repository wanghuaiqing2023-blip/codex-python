from pycodex.tui.bottom_pane.mentions_v2.candidate import Candidate, MentionType, Selection
from pycodex.tui.bottom_pane.mentions_v2.filter import FileMatch
from pycodex.tui.bottom_pane.mentions_v2.filter import best_tool_match
from pycodex.tui.bottom_pane.mentions_v2.filter import file_match_to_row
from pycodex.tui.bottom_pane.mentions_v2.filter import filtered_candidates
from pycodex.tui.bottom_pane.mentions_v2.filter import sort_rows
from pycodex.tui.bottom_pane.mentions_v2.search_mode import SearchMode


def _candidate(name, mention_type, terms=()):
    return Candidate(name, None, list(terms), mention_type, Selection.Tool("@" + name))


def test_empty_query_returns_accepted_candidates_with_zero_scores_and_type_sorting():
    rows = filtered_candidates(
        [_candidate("skill-b", MentionType.SKILL), _candidate("plugin-a", MentionType.PLUGIN), _candidate("file-c", MentionType.FILE)],
        [],
        "   ",
        SearchMode.RESULTS,
        False,
    )
    assert [(row.display_name, row.score, row.match_indices) for row in rows] == [
        ("plugin-a", 0, None),
        ("skill-b", 0, None),
        ("file-c", 0, None),
    ]


def test_best_tool_match_prefers_display_name_indices_then_search_terms_score_only():
    display_candidate = _candidate("Open File", MentionType.PLUGIN, ["filesystem opener"])
    assert best_tool_match(display_candidate, "of")[0] == [0, 5]

    term_candidate = _candidate("Browse", MentionType.SKILL, ["open file", "workspace"])
    indices, score = best_tool_match(term_candidate, "of")
    assert indices is None
    assert isinstance(score, int)

    assert best_tool_match(_candidate("Browse", MentionType.SKILL, ["workspace"]), "zzz") is None


def test_filtered_candidates_applies_search_mode_before_matching():
    rows = filtered_candidates(
        [_candidate("Plugin One", MentionType.PLUGIN), _candidate("File One", MentionType.FILE)],
        [],
        "one",
        SearchMode.TOOLS,
        False,
    )
    assert [row.display_name for row in rows] == ["Plugin One"]


def test_file_matches_are_appended_when_enabled_and_filtered_by_mode():
    rows = filtered_candidates(
        [_candidate("Plugin", MentionType.PLUGIN)],
        [FileMatch("src/main.rs", "File", [0, 4], 8), FileMatch("src", "Directory", [0], 12)],
        "",
        SearchMode.FILESYSTEM_ONLY,
        True,
    )
    assert [row.display_name for row in rows] == ["src", "src/main.rs"]
    assert rows[0].mention_type is MentionType.DIRECTORY
    assert rows[0].selection == Selection.File("src")


def test_file_match_to_row_preserves_indices_and_score():
    row = file_match_to_row({"path": "docs", "match_type": "Directory", "indices": [1, 2], "score": 99})
    assert row.display_name == "docs"
    assert row.mention_type is MentionType.DIRECTORY
    assert row.match_indices == [1, 2]
    assert row.score == 99


def test_sort_rows_orders_tools_by_direct_match_before_search_term_match():
    direct = _candidate("Alpha", MentionType.PLUGIN).to_result([0, 1], 10)
    term = _candidate("Zed", MentionType.PLUGIN).to_result(None, 1)
    skill = _candidate("A Skill", MentionType.SKILL).to_result([0], 0)
    rows = [skill, term, direct]

    sort_rows(rows, "a")

    assert [row.display_name for row in rows] == ["Alpha", "Zed", "A Skill"]


def test_filesystem_rows_sort_by_descending_score_within_rank():
    low = file_match_to_row(FileMatch("b.txt", "File", score=1))
    high = file_match_to_row(FileMatch("a.txt", "File", score=10))
    rows = [low, high]

    sort_rows(rows, "anything")

    assert [row.display_name for row in rows] == ["a.txt", "b.txt"]
