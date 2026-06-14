"""Parity tests for ``codex-tui`` history search local behavior.

Rust source: codex/codex-rs/tui/src/bottom_pane/chat_composer/history_search.rs
"""

from pycodex.tui.bottom_pane.chat_composer.history_search import (
    HistorySearchSession,
    HistorySearchStatus,
    apply_history_search_result,
    case_insensitive_match_ranges,
    history_search_footer_line,
    history_search_highlight_ranges,
    is_history_search_active,
    status_for_history_result,
)


def test_history_search_session_defaults_and_active_predicate():
    assert not is_history_search_active(None)

    session = HistorySearchSession(original_draft="draft")

    assert is_history_search_active(session)
    assert session.original_draft == "draft"
    assert session.query == ""
    assert session.status is HistorySearchStatus.IDLE


def test_case_insensitive_match_ranges_match_rust_examples():
    assert case_insensitive_match_ranges("git status git", "GIT") == [(0, 3), (11, 14)]
    assert case_insensitive_match_ranges("aİ i", "i") == [(1, 3), (4, 5)]
    assert case_insensitive_match_ranges("git", "") == []


def test_history_search_footer_line_status_variants():
    idle = history_search_footer_line(HistorySearchSession(query="git"))
    assert [span.text for span in idle.spans] == ["reverse-i-search: ", "git"]
    assert [span.style for span in idle.spans] == ["dim", "cyan"]

    searching = history_search_footer_line(
        HistorySearchSession(query="git", status=HistorySearchStatus.SEARCHING)
    )
    assert searching.text == "reverse-i-search: git  searching"
    assert searching.spans[-1].style == "dim"

    match = history_search_footer_line(
        HistorySearchSession(query="git", status=HistorySearchStatus.MATCH)
    )
    assert [span.text for span in match.spans] == [
        "reverse-i-search: ",
        "git",
        "  ",
        "enter",
        " accept",
        " 路 ",
        "esc",
        " cancel",
    ]
    assert match.spans[3].style == "cyan+bold+not_dim"
    assert match.spans[6].style == "cyan+bold+not_dim"

    no_match = history_search_footer_line(
        HistorySearchSession(query="git", status=HistorySearchStatus.NO_MATCH)
    )
    assert no_match.text == "reverse-i-search: git  no match"
    assert no_match.spans[-1].style == "red"


def test_history_search_highlight_ranges_only_for_match_with_query():
    assert history_search_highlight_ranges(None, "git") == []
    assert history_search_highlight_ranges(HistorySearchSession(query="git"), "git") == []
    assert (
        history_search_highlight_ranges(
            HistorySearchSession(query="git", status=HistorySearchStatus.MATCH),
            "git status git",
        )
        == [(0, 3), (11, 14)]
    )


def test_status_for_history_result_and_session_update():
    assert status_for_history_result("Found") is HistorySearchStatus.MATCH
    assert status_for_history_result({"kind": "AtBoundary"}) is HistorySearchStatus.MATCH
    assert status_for_history_result({"type": "Pending"}) is HistorySearchStatus.SEARCHING
    assert status_for_history_result({"name": "NotFound"}) is HistorySearchStatus.NO_MATCH

    original = HistorySearchSession(original_draft="draft", query="git")
    updated = apply_history_search_result(original, "Found")

    assert updated is not original
    assert updated.original_draft == "draft"
    assert updated.query == "git"
    assert updated.status is HistorySearchStatus.MATCH
