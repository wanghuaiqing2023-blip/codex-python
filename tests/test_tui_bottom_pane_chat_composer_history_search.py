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
    history_search_accepts_matching_entry,
    history_search_ctrl_c_restores_original_draft,
    history_search_esc_resets_normal_history_navigation,
    history_search_esc_restores_original_draft,
    history_search_flushes_buffered_paste_before_snapshot,
    history_search_flushes_pending_first_char_before_snapshot,
    history_search_footer_action_hints_are_emphasized,
    history_search_highlights_matches_until_accepted,
    history_search_match_ranges_are_case_insensitive,
    history_search_no_match_restores_preview_but_keeps_search_open,
    history_search_opens_without_previewing_latest_entry,
    history_search_stays_on_single_match_at_boundaries,
    vim_normal_history_search_preview_places_cursor_on_last_char,
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
        " · ",
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



def test_rust_chat_composer_history_search_lifecycle_helpers():
    assert history_search_opens_without_previewing_latest_entry() is True
    assert history_search_match_ranges_are_case_insensitive() is True
    assert history_search_accepts_matching_entry() is True
    assert vim_normal_history_search_preview_places_cursor_on_last_char() is True
    assert history_search_stays_on_single_match_at_boundaries() is True
    assert history_search_footer_action_hints_are_emphasized() is True
    assert history_search_highlights_matches_until_accepted() is True
    assert history_search_esc_restores_original_draft() is True
    assert history_search_ctrl_c_restores_original_draft() is True
    assert history_search_flushes_pending_first_char_before_snapshot() is True
    assert history_search_flushes_buffered_paste_before_snapshot() is True
    assert history_search_esc_resets_normal_history_navigation() is True
    assert history_search_no_match_restores_preview_but_keeps_search_open() is True
