"""Parity tests for codex-rs/tui/src/history_cell/search.rs."""

from pycodex.tui.history_cell.search import (
    WebSearchAction,
    WebSearchCell,
    line_text,
    new_active_web_search_call,
    new_web_search_call,
    web_search_action_detail,
    web_search_detail,
    web_search_header,
)


def texts(lines):
    return [line_text(line) for line in lines]


def test_web_search_header_matches_completion_state() -> None:
    assert web_search_header(False) == "Searching the web"
    assert web_search_header(True) == "Searched"


def test_search_action_detail_prefers_query_then_first_query_with_ellipsis() -> None:
    assert web_search_action_detail(WebSearchAction.search("rust tui", ["ignored"])) == "rust tui"
    assert web_search_action_detail(WebSearchAction.search("", ["first", "second"])) == "first ..."
    assert web_search_action_detail(WebSearchAction.search(None, ["only"])) == "only"
    assert web_search_action_detail(WebSearchAction.search(None, [])) == ""


def test_open_and_find_action_details_match_rust_cases() -> None:
    assert web_search_action_detail(WebSearchAction.open_page("https://example.com")) == "https://example.com"
    assert (
        web_search_action_detail(WebSearchAction.find_in_page("https://example.com", "needle"))
        == "'needle' in https://example.com"
    )
    assert web_search_action_detail(WebSearchAction.find_in_page(None, "needle")) == "'needle'"
    assert web_search_action_detail(WebSearchAction.find_in_page("https://example.com", None)) == "https://example.com"
    assert web_search_action_detail(WebSearchAction.other()) == ""


def test_web_search_detail_falls_back_to_query_when_action_is_empty() -> None:
    assert web_search_detail(None, "fallback") == "fallback"
    assert web_search_detail(WebSearchAction.other(), "fallback") == "fallback"
    assert web_search_detail(WebSearchAction.open_page("https://example.com"), "fallback") == "https://example.com"


def test_active_web_search_cell_updates_and_completes() -> None:
    cell = new_active_web_search_call("call-1", "initial", animations_enabled=True)

    assert cell.call_id() == "call-1"
    assert texts(cell.raw_lines()) == ["Searching the web initial"]
    assert texts(cell.display_lines(80)) == ["- Searching the web initial"]

    cell.update(WebSearchAction.find_in_page("https://example.com", "needle"), "ignored")
    cell.complete()

    assert texts(cell.raw_lines()) == ["Searched 'needle' in https://example.com"]


def test_completed_web_search_constructor_marks_complete() -> None:
    cell = new_web_search_call("call-2", "fallback", WebSearchAction.search(None, ["first", "second"]))

    assert cell.completed is True
    assert texts(cell.display_lines(80)) == ["- Searched first ..."]


def test_cell_new_accepts_dict_action_facade() -> None:
    cell = WebSearchCell.new(
        "call-3",
        "fallback",
        {"kind": "open_page", "url": "https://example.com"},
        False,
    )
    cell.complete()

    assert texts(cell.raw_lines()) == ["Searched https://example.com"]
