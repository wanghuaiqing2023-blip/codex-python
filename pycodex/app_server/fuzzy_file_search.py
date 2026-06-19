"""Fuzzy file search bridge for ``codex-app-server/src/fuzzy_file_search.rs``."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from inspect import isawaitable
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from pycodex import file_search
from pycodex.app_server_protocol import (
    FuzzyFileSearchMatchType,
    FuzzyFileSearchResult,
    FuzzyFileSearchSessionCompletedNotification,
    FuzzyFileSearchSessionUpdatedNotification,
)
from pycodex.app_server_protocol.item_builders import ServerNotification

MATCH_LIMIT = 50
MAX_THREADS = 12


class SupportsFileSearchSession(Protocol):
    def update_query(self, pattern_text: str) -> None: ...


RunSearch = Callable[
    [str, list[Path], file_search.FileSearchOptions, Any | None],
    file_search.FileSearchResults,
]
CreateSession = Callable[
    [list[Path], file_search.FileSearchOptions, file_search.SessionReporter, Any | None],
    SupportsFileSearchSession,
]


@dataclass
class CancellationFlag:
    canceled: bool = False

    def cancel(self) -> None:
        self.canceled = True


async def run_fuzzy_file_search(
    query: str,
    roots: Iterable[str],
    cancellation_flag: Any | None = None,
    *,
    runner: RunSearch | None = None,
) -> list[FuzzyFileSearchResult]:
    """Run a one-shot fuzzy file search and map Rust result payloads."""

    root_list = list(roots)
    if not root_list:
        return []

    options = file_search.FileSearchOptions(
        limit=MATCH_LIMIT,
        threads=_thread_count(),
        compute_indices=True,
    )
    search_dirs = [Path(root) for root in root_list]
    runner = runner or file_search.run

    try:
        results = await asyncio.to_thread(runner, str(query), search_dirs, options, cancellation_flag)
    except Exception:
        return []

    files = [_result_from_match(match, roots=search_dirs) for match in getattr(results, "matches", ())]
    return sorted(files, key=lambda item: (-item.score, item.path))


class FuzzyFileSearchSession:
    def __init__(self, session: SupportsFileSearchSession, shared: "_SessionShared") -> None:
        self._session = session
        self._shared = shared

    def update_query(self, query: str) -> None:
        if self._shared.cancellation_flag.canceled:
            return
        with self._shared.lock:
            self._shared.latest_query = str(query)
        self._session.update_query(str(query))

    def close(self) -> None:
        self._shared.cancellation_flag.cancel()

    def __enter__(self) -> "FuzzyFileSearchSession":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def start_fuzzy_file_search_session(
    session_id: str,
    roots: Iterable[str],
    outgoing: Any,
    *,
    create_session: CreateSession | None = None,
) -> FuzzyFileSearchSession:
    """Create a stateful fuzzy search session with Rust's reporter gates."""

    cancellation_flag = CancellationFlag()
    shared = _SessionShared(
        session_id=str(session_id),
        outgoing=outgoing,
        cancellation_flag=cancellation_flag,
    )
    reporter = _SessionReporterImpl(shared)
    options = file_search.FileSearchOptions(
        limit=MATCH_LIMIT,
        threads=_thread_count(),
        compute_indices=True,
    )
    factory = create_session or file_search.create_session
    session = factory([Path(root) for root in roots], options, reporter, cancellation_flag)
    return FuzzyFileSearchSession(session, shared)


@dataclass
class _SessionShared:
    session_id: str
    outgoing: Any
    cancellation_flag: CancellationFlag
    latest_query: str = ""
    lock: Lock = field(default_factory=Lock)


class _SessionReporterImpl:
    def __init__(self, shared: _SessionShared) -> None:
        self._shared = shared

    def on_update(self, snapshot: Any) -> None:
        self.send_snapshot(snapshot)

    def on_complete(self) -> None:
        self.send_complete()

    def send_snapshot(self, snapshot: Any) -> None:
        if self._shared.cancellation_flag.canceled:
            return
        with self._shared.lock:
            query = self._shared.latest_query
        if getattr(snapshot, "query", None) != query:
            return

        files = [] if query == "" else collect_files(snapshot)
        payload = FuzzyFileSearchSessionUpdatedNotification(
            session_id=self._shared.session_id,
            query=query,
            files=files,
        )
        _dispatch_notification(
            self._shared.outgoing,
            ServerNotification("FuzzyFileSearchSessionUpdated", payload),
        )

    def send_complete(self) -> None:
        if self._shared.cancellation_flag.canceled:
            return
        payload = FuzzyFileSearchSessionCompletedNotification(session_id=self._shared.session_id)
        _dispatch_notification(
            self._shared.outgoing,
            ServerNotification("FuzzyFileSearchSessionCompleted", payload),
        )


def collect_files(snapshot: Any) -> list[FuzzyFileSearchResult]:
    files = [_result_from_match(match) for match in getattr(snapshot, "matches", ())]
    return sorted(files, key=lambda item: (-item.score, item.path))


def _result_from_match(match: Any, *, roots: list[Path] | None = None) -> FuzzyFileSearchResult:
    path = Path(getattr(match, "path"))
    root = getattr(match, "root", None)
    if root is None:
        root = _matching_root(path, roots or ())
    match_type = getattr(match, "match_type", file_search.MatchType.FILE)
    return FuzzyFileSearchResult(
        root=str(root),
        path=str(path),
        match_type=_match_type(match_type),
        file_name=path.name,
        score=int(getattr(match, "score", 0) or 0),
        indices=list(getattr(match, "indices", None) or []),
    )


def _matching_root(path: Path, roots: Iterable[Path]) -> Path:
    for root in roots:
        try:
            path.relative_to(root)
            return root
        except ValueError:
            continue
    return Path("")


def _match_type(match_type: Any) -> FuzzyFileSearchMatchType:
    value = getattr(match_type, "value", match_type)
    if value in {file_search.MatchType.DIRECTORY.value, "Directory", "directory"}:
        return FuzzyFileSearchMatchType.DIRECTORY
    return FuzzyFileSearchMatchType.FILE


def _thread_count() -> int:
    cores = os.cpu_count() or 1
    return max(1, min(cores, MAX_THREADS))


def _dispatch_notification(outgoing: Any, notification: ServerNotification) -> None:
    sender = getattr(outgoing, "send_server_notification", None)
    if not callable(sender):
        raise TypeError("outgoing must provide send_server_notification")
    result = sender(notification)
    if not isawaitable(result):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(result)
    else:
        loop.create_task(result)


__all__ = [
    "CancellationFlag",
    "FuzzyFileSearchSession",
    "MATCH_LIMIT",
    "MAX_THREADS",
    "collect_files",
    "run_fuzzy_file_search",
    "start_fuzzy_file_search_session",
]
