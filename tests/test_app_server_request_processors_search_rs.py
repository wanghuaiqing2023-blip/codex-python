"""Rust parity tests for ``request_processors/search.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pycodex.app_server.fuzzy_file_search import CancellationFlag
from pycodex.app_server.request_processors_search import (
    SearchRequestProcessor,
    SearchRequestProcessorError,
)
from pycodex.app_server_protocol import (
    FuzzyFileSearchParams,
    FuzzyFileSearchSessionStartParams,
    FuzzyFileSearchSessionStopParams,
    FuzzyFileSearchSessionUpdateParams,
)


async def _run_search(query: str, roots: list[str], cancellation_flag: CancellationFlag) -> list[Any]:
    return [{"query": query, "roots": roots, "canceled": cancellation_flag.canceled}]


@dataclass
class FakeSession:
    closed: bool = False
    queries: list[str] = field(default_factory=list)

    def update_query(self, query: str) -> None:
        self.queries.append(query)

    def close(self) -> None:
        self.closed = True


def test_fuzzy_file_search_empty_query_returns_empty_without_runner() -> None:
    # Rust source: search.rs fuzzy_file_search returns vec![] for an empty query.
    calls: list[str] = []

    async def runner(query: str, roots: list[str], cancellation_flag: CancellationFlag) -> list[Any]:
        calls.append(query)
        return []

    processor = SearchRequestProcessor(object(), run_search=runner)

    response = asyncio.run(
        processor.fuzzy_file_search(FuzzyFileSearchParams(query="", roots=["/repo"], cancellation_token=None))
    )

    assert response.files == []
    assert calls == []


def test_fuzzy_file_search_replaces_matching_cancellation_token_and_cleans_current_flag() -> None:
    # Rust source: matching cancellation_token cancels the existing flag and inserts a new one.
    processor = SearchRequestProcessor(object(), run_search=_run_search)
    old_flag = CancellationFlag()
    processor.pending_fuzzy_searches["same"] = old_flag

    response = asyncio.run(
        processor.fuzzy_file_search(FuzzyFileSearchParams(query="cfg", roots=["/repo"], cancellation_token="same"))
    )

    assert old_flag.canceled is True
    assert processor.pending_fuzzy_searches == {}
    assert response.files[0]["query"] == "cfg"
    assert response.files[0]["canceled"] is False


def test_fuzzy_file_search_keeps_newer_pending_flag_when_current_finishes_late() -> None:
    # Rust source: cleanup removes only when the map still points at the current flag.
    replacement = CancellationFlag()

    async def runner(query: str, roots: list[str], cancellation_flag: CancellationFlag) -> list[Any]:
        processor.pending_fuzzy_searches["tok"] = replacement
        return []

    processor = SearchRequestProcessor(object(), run_search=runner)

    asyncio.run(processor.fuzzy_file_search({"query": "needle", "roots": ["/repo"], "cancellationToken": "tok"}))

    assert processor.pending_fuzzy_searches == {"tok": replacement}


def test_fuzzy_file_search_session_start_rejects_empty_session_id() -> None:
    # Rust source: fuzzy_file_search_session_start_response validates non-empty session_id.
    processor = SearchRequestProcessor(object())

    try:
        processor.fuzzy_file_search_session_start_response(FuzzyFileSearchSessionStartParams(session_id="", roots=[]))
    except SearchRequestProcessorError as exc:
        assert exc.error.code == -32600
        assert exc.error.message == "sessionId must not be empty"
    else:
        raise AssertionError("expected SearchRequestProcessorError")


def test_fuzzy_file_search_session_start_stores_session_and_maps_start_error() -> None:
    # Rust source: start errors become internal_error with the fuzzy session prefix.
    session = FakeSession()

    def factory(session_id: str, roots: list[str], outgoing: object) -> FakeSession:
        assert session_id == "s1"
        assert roots == ["/repo"]
        return session

    processor = SearchRequestProcessor(object(), start_session=factory)

    assert processor.fuzzy_file_search_session_start_response({"sessionId": "s1", "roots": ["/repo"]}).to_mapping() == {}
    assert processor.fuzzy_search_sessions["s1"] is session

    def failing_factory(session_id: str, roots: list[str], outgoing: object) -> FakeSession:
        raise OSError("boom")

    processor = SearchRequestProcessor(object(), start_session=failing_factory)
    try:
        processor.fuzzy_file_search_session_start_response({"sessionId": "s2", "roots": []})
    except SearchRequestProcessorError as exc:
        assert exc.error.code == -32603
        assert exc.error.message == "failed to start fuzzy file search session: boom"
    else:
        raise AssertionError("expected SearchRequestProcessorError")


def test_fuzzy_file_search_session_update_and_stop_match_session_map_behavior() -> None:
    # Rust source: update errors on missing session; stop removes if present and always succeeds.
    session = FakeSession()
    processor = SearchRequestProcessor(object())
    processor.fuzzy_search_sessions["s1"] = session

    assert processor.fuzzy_file_search_session_update_response(
        FuzzyFileSearchSessionUpdateParams(session_id="s1", query="main")
    ).to_mapping() == {}
    assert session.queries == ["main"]

    try:
        processor.fuzzy_file_search_session_update_response({"sessionId": "missing", "query": "x"})
    except SearchRequestProcessorError as exc:
        assert exc.error.code == -32600
        assert exc.error.message == "fuzzy file search session not found: missing"
    else:
        raise AssertionError("expected SearchRequestProcessorError")

    assert processor.fuzzy_file_search_session_stop(
        FuzzyFileSearchSessionStopParams(session_id="s1")
    ).to_mapping() == {}
    assert session.closed is True
    assert processor.fuzzy_search_sessions == {}

    assert processor.fuzzy_file_search_session_stop({"sessionId": "missing"}).to_mapping() == {}
