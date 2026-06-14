"""Parity tests for ``codex-tui`` chat composer history behavior.

Rust source: codex/codex-rs/tui/src/bottom_pane/chat_composer_history.rs
"""

from pycodex.tui.bottom_pane.chat_composer_history import (
    ChatComposerHistory,
    HistoryEntry,
    HistoryEntryResponse,
    HistorySearchDirection,
    HistorySearchResult,
)
from pycodex.tui.bottom_pane import MentionBinding


def test_duplicate_submissions_are_not_recorded():
    history = ChatComposerHistory.new()

    history.record_local_submission(HistoryEntry.new(""))
    assert history.local_history == []

    history.record_local_submission(HistoryEntry.new("hello"))
    history.record_local_submission(HistoryEntry.new("hello"))
    history.record_local_submission(HistoryEntry.new("world"))

    assert history.local_history == [HistoryEntry.new("hello"), HistoryEntry.new("world")]


def test_history_entry_new_decodes_persisted_mentions_like_rust() -> None:
    entry = HistoryEntry.new("Use [$figma](app://figma-1) and [@sample](plugin://sample@test).")

    assert entry.text == "Use $figma and @sample."
    assert entry.mention_bindings == [
        MentionBinding(mention="figma", path="app://figma-1"),
        MentionBinding(mention="sample", path="plugin://sample@test"),
    ]
    assert entry.text_elements == []
    assert entry.local_image_paths == []
    assert entry.remote_image_urls == []
    assert entry.pending_pastes == []


def test_navigation_with_async_fetch_and_response():
    events = []
    history = ChatComposerHistory.new()
    history.set_metadata("thread", 1, 3)

    assert history.should_handle_navigation("", 0)
    assert history.navigate_up(events) is None
    assert events == [{"type": "LookupMessageHistoryEntry", "thread_id": "thread", "offset": 2, "log_id": 1}]

    assert history.on_entry_response(1, 2, "latest", events) == HistoryEntryResponse.found(HistoryEntry.new("latest"))
    assert history.navigate_up(events) is None
    assert events[-1] == {"type": "LookupMessageHistoryEntry", "thread_id": "thread", "offset": 1, "log_id": 1}

    assert history.on_entry_response(99, 1, "stale", events) == HistoryEntryResponse.IGNORED
    assert history.on_entry_response(1, 1, "older", events) == HistoryEntryResponse.found(HistoryEntry.new("older"))


def test_local_search_matches_boundaries_and_newer_direction():
    history = ChatComposerHistory.new()
    history.record_local_submission(HistoryEntry.new("git status"))
    history.record_local_submission(HistoryEntry.new("cargo test -p codex-tui"))
    history.record_local_submission(HistoryEntry.new("git diff"))

    assert history.search("git", HistorySearchDirection.OLDER, True) == HistorySearchResult.found(HistoryEntry.new("git diff"))
    assert history.search("git", HistorySearchDirection.OLDER, False) == HistorySearchResult.found(HistoryEntry.new("git status"))
    assert history.search("git", HistorySearchDirection.OLDER, False) == HistorySearchResult.AT_BOUNDARY
    assert history.search("git", HistorySearchDirection.OLDER, False) == HistorySearchResult.AT_BOUNDARY
    assert history.search("git", HistorySearchDirection.NEWER, False) == HistorySearchResult.found(HistoryEntry.new("git diff"))
    assert history.search("git", HistorySearchDirection.NEWER, False) == HistorySearchResult.AT_BOUNDARY


def test_search_skips_duplicate_local_matches_but_can_revisit_cached_unique_matches():
    history = ChatComposerHistory.new()
    history.record_local_submission(HistoryEntry.new("git status"))
    history.record_local_submission(HistoryEntry.new("cargo test -p codex-tui"))
    history.record_local_submission(HistoryEntry.new("git status"))
    history.record_local_submission(HistoryEntry.new("git diff"))

    assert history.search("git", HistorySearchDirection.OLDER, True) == HistorySearchResult.found(HistoryEntry.new("git diff"))
    assert history.search("git", HistorySearchDirection.OLDER, False) == HistorySearchResult.found(HistoryEntry.new("git status"))
    assert history.search("git", HistorySearchDirection.OLDER, False) == HistorySearchResult.AT_BOUNDARY
    assert history.search("git", HistorySearchDirection.NEWER, False) == HistorySearchResult.found(HistoryEntry.new("git diff"))
    assert history.search("git", HistorySearchDirection.OLDER, False) == HistorySearchResult.found(HistoryEntry.new("git status"))


def test_persistent_search_fetches_until_match_and_repeated_boundary_does_not_refetch():
    events = []
    history = ChatComposerHistory.new()
    history.set_metadata("thread", 1, 3)

    assert history.search("needle", HistorySearchDirection.OLDER, True, events) == HistorySearchResult.PENDING
    assert events[-1]["offset"] == 2
    assert history.on_entry_response(1, 2, "needle latest", events) == HistoryEntryResponse.search(
        HistorySearchResult.found(HistoryEntry.new("needle latest"))
    )

    assert history.search("needle", HistorySearchDirection.OLDER, False, events) == HistorySearchResult.PENDING
    assert events[-1]["offset"] == 1
    assert history.on_entry_response(1, 1, "not a match", events) == HistoryEntryResponse.search(HistorySearchResult.PENDING)
    assert events[-1]["offset"] == 0
    assert history.on_entry_response(1, 0, "also not a match", events) == HistoryEntryResponse.search(HistorySearchResult.AT_BOUNDARY)
    event_count = len(events)

    assert history.search("needle", HistorySearchDirection.OLDER, False, events) == HistorySearchResult.AT_BOUNDARY
    assert len(events) == event_count


def test_search_case_insensitive_empty_query_and_navigation_reset():
    history = ChatComposerHistory.new()
    history.record_local_submission(HistoryEntry.new("Build Release"))

    assert history.search("release", HistorySearchDirection.OLDER, True) == HistorySearchResult.found(HistoryEntry.new("Build Release"))
    assert history.search("", HistorySearchDirection.OLDER, True) == HistorySearchResult.found(HistoryEntry.new("Build Release"))

    history.set_metadata("thread", 1, 3)
    history.fetched_history[1] = HistoryEntry.new("command2")
    history.fetched_history[2] = HistoryEntry.new("command3")
    assert history.navigate_up([]) == HistoryEntry.new("command3")
    assert history.navigate_up([]) == HistoryEntry.new("command2")
    history.reset_navigation()
    assert history.history_cursor is None
    assert history.last_history_text is None
    assert history.navigate_up([]) == HistoryEntry.new("command3")


def test_should_handle_navigation_when_cursor_is_at_line_boundaries():
    history = ChatComposerHistory.new()
    history.record_local_submission(HistoryEntry.new("hello"))
    history.last_history_text = "hello"

    assert history.should_handle_navigation("hello", 0)
    assert history.should_handle_navigation("hello", len("hello"))
    assert not history.should_handle_navigation("hello", 1)
    assert not history.should_handle_navigation("other", 0)
