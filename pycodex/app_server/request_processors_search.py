"""Search request processor projection.

Ported from ``codex-app-server/src/request_processors/search.rs``.  The Rust
module owns the request-processor state around fuzzy file search: cancellation
token replacement for one-shot searches and lifecycle management for stateful
fuzzy-search sessions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server.fuzzy_file_search import (
    CancellationFlag,
    FuzzyFileSearchSession,
    run_fuzzy_file_search,
    start_fuzzy_file_search_session,
)
from pycodex.app_server_protocol import (
    FuzzyFileSearchParams,
    FuzzyFileSearchResponse,
    FuzzyFileSearchSessionStartParams,
    FuzzyFileSearchSessionStartResponse,
    FuzzyFileSearchSessionStopParams,
    FuzzyFileSearchSessionStopResponse,
    FuzzyFileSearchSessionUpdateParams,
    FuzzyFileSearchSessionUpdateResponse,
    JSONRPCErrorError,
)

JsonValue = Any


class SearchRequestProcessorError(Exception):
    """Exception wrapper carrying Rust's JSON-RPC error payload."""

    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


class SearchRequestProcessor:
    def __init__(
        self,
        outgoing: Any,
        *,
        run_search: Any | None = None,
        start_session: Any | None = None,
    ) -> None:
        self.outgoing = outgoing
        self.pending_fuzzy_searches: dict[str, CancellationFlag] = {}
        self.fuzzy_search_sessions: dict[str, FuzzyFileSearchSession] = {}
        self._run_search = run_search or run_fuzzy_file_search
        self._start_session = start_session or start_fuzzy_file_search_session

    @classmethod
    def new(cls, outgoing: Any) -> "SearchRequestProcessor":
        return cls(outgoing)

    async def fuzzy_file_search(
        self,
        params: FuzzyFileSearchParams | Mapping[str, JsonValue],
    ) -> FuzzyFileSearchResponse:
        params = _fuzzy_file_search_params(params)
        cancel_flag = CancellationFlag()
        token = params.cancellation_token
        if token is not None:
            existing = self.pending_fuzzy_searches.get(token)
            if existing is not None:
                existing.cancel()
            self.pending_fuzzy_searches[token] = cancel_flag

        files = [] if params.query == "" else await self._run_search(params.query, params.roots, cancel_flag)

        if token is not None and self.pending_fuzzy_searches.get(token) is cancel_flag:
            del self.pending_fuzzy_searches[token]

        return FuzzyFileSearchResponse(files=files)

    def fuzzy_file_search_session_start_response(
        self,
        params: FuzzyFileSearchSessionStartParams | Mapping[str, JsonValue],
    ) -> FuzzyFileSearchSessionStartResponse:
        params = _fuzzy_file_search_session_start_params(params)
        if params.session_id == "":
            raise SearchRequestProcessorError(invalid_request("sessionId must not be empty"))

        try:
            session = self._start_session(params.session_id, params.roots, self.outgoing)
        except Exception as exc:
            raise SearchRequestProcessorError(
                internal_error(f"failed to start fuzzy file search session: {exc}")
            ) from exc
        previous = self.fuzzy_search_sessions.get(params.session_id)
        if previous is not None:
            previous.close()
        self.fuzzy_search_sessions[params.session_id] = session
        return FuzzyFileSearchSessionStartResponse()

    def fuzzy_file_search_session_update_response(
        self,
        params: FuzzyFileSearchSessionUpdateParams | Mapping[str, JsonValue],
    ) -> FuzzyFileSearchSessionUpdateResponse:
        params = _fuzzy_file_search_session_update_params(params)
        session = self.fuzzy_search_sessions.get(params.session_id)
        if session is None:
            raise SearchRequestProcessorError(
                invalid_request(f"fuzzy file search session not found: {params.session_id}")
            )
        session.update_query(params.query)
        return FuzzyFileSearchSessionUpdateResponse()

    def fuzzy_file_search_session_stop(
        self,
        params: FuzzyFileSearchSessionStopParams | Mapping[str, JsonValue],
    ) -> FuzzyFileSearchSessionStopResponse:
        params = _fuzzy_file_search_session_stop_params(params)
        session = self.fuzzy_search_sessions.pop(params.session_id, None)
        if session is not None:
            session.close()
        return FuzzyFileSearchSessionStopResponse()


def _fuzzy_file_search_params(params: FuzzyFileSearchParams | Mapping[str, JsonValue]) -> FuzzyFileSearchParams:
    if isinstance(params, FuzzyFileSearchParams):
        return params
    return FuzzyFileSearchParams.from_mapping(params)


def _fuzzy_file_search_session_start_params(
    params: FuzzyFileSearchSessionStartParams | Mapping[str, JsonValue],
) -> FuzzyFileSearchSessionStartParams:
    if isinstance(params, FuzzyFileSearchSessionStartParams):
        return params
    return FuzzyFileSearchSessionStartParams.from_mapping(params)


def _fuzzy_file_search_session_update_params(
    params: FuzzyFileSearchSessionUpdateParams | Mapping[str, JsonValue],
) -> FuzzyFileSearchSessionUpdateParams:
    if isinstance(params, FuzzyFileSearchSessionUpdateParams):
        return params
    return FuzzyFileSearchSessionUpdateParams.from_mapping(params)


def _fuzzy_file_search_session_stop_params(
    params: FuzzyFileSearchSessionStopParams | Mapping[str, JsonValue],
) -> FuzzyFileSearchSessionStopParams:
    if isinstance(params, FuzzyFileSearchSessionStopParams):
        return params
    return FuzzyFileSearchSessionStopParams.from_mapping(params)


__all__ = [
    "SearchRequestProcessor",
    "SearchRequestProcessorError",
]
