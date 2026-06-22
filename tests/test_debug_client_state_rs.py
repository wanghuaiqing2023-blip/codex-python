"""Prepared parity tests for Rust ``codex-debug-client/src/state.rs``.

Pytest is deferred until the full ``codex-debug-client`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

from pycodex.debug_client.state import PendingRequest, ReaderEvent, State


def test_state_default_matches_rust_default() -> None:
    # Rust source: State derives Default with empty pending/known_threads and no thread_id.
    state = State()

    assert state.pending == {}
    assert state.thread_id is None
    assert state.known_threads == []


def test_pending_request_variants_match_rust_names() -> None:
    # Rust source: PendingRequest variants Start, Resume, List.
    assert PendingRequest.START.value == "Start"
    assert PendingRequest.RESUME.value == "Resume"
    assert PendingRequest.LIST.value == "List"


def test_state_tracks_pending_request_and_thread_lists() -> None:
    # Rust source: State fields are public and mutated by client/reader modules.
    state = State()

    state.pending["1"] = PendingRequest.START
    state.thread_id = "thr_1"
    state.known_threads.extend(["thr_1", "thr_2"])

    assert state.pending == {"1": PendingRequest.START}
    assert state.thread_id == "thr_1"
    assert state.known_threads == ["thr_1", "thr_2"]


def test_reader_event_thread_ready() -> None:
    # Rust source: ReaderEvent::ThreadReady { thread_id }.
    assert ReaderEvent.thread_ready("thr_1") == ReaderEvent("ThreadReady", thread_id="thr_1")


def test_reader_event_thread_list() -> None:
    # Rust source: ReaderEvent::ThreadList { thread_ids, next_cursor }.
    assert ReaderEvent.thread_list(["thr_1"], "cursor") == ReaderEvent(
        "ThreadList", thread_ids=["thr_1"], next_cursor="cursor"
    )
    assert ReaderEvent.thread_list(["thr_1"]).next_cursor is None
