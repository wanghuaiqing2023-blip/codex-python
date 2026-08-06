"""TUI file-search session orchestration for Rust ``codex-tui::file_search``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Callable, List, Optional, Protocol, Union

from ._porting import RustTuiModule
from .app_event import AppEvent

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="file_search",
    source="codex/codex-rs/tui/src/file_search.rs",
    status="complete",
)


class FileSearchSession(Protocol):
    def update_query(self, query: str) -> None:
        ...


@dataclass
class SearchState:
    latest_query: str = ""
    session: Optional[FileSearchSession] = None
    session_token: int = 0


@dataclass
class FileSearchOptions:
    compute_indices: bool = True


SessionFactory = Callable[[List[Path], FileSearchOptions, "TuiSessionReporter", Any], FileSearchSession]


def _default_session_factory(
    roots: List[Path],
    options: FileSearchOptions,
    reporter: "TuiSessionReporter",
    cancel_flag: Any,
) -> FileSearchSession:
    return _AsyncFileSearchSession(roots, options, reporter, cancel_flag)


class _AsyncFileSearchSession:
    """Asynchronous adapter over the Rust-aligned ``pycodex.file_search`` API.

    Rust's ``codex_file_search::FileSearchSession`` walks and matches on worker
    threads while ``update_query`` remains cheap.  The TUI manager needs the
    same contract so input and popup repaint are never blocked by a workspace
    walk.
    """

    def __init__(
        self,
        roots: List[Path],
        options: FileSearchOptions,
        reporter: "TuiSessionReporter",
        cancel_flag: Any,
    ) -> None:
        self._roots = list(roots)
        self._options = options
        self._reporter = reporter
        self._cancel_flag = cancel_flag
        self._lock = Lock()
        self._closed = False
        self._pending_query: str | None = None
        self._worker_running = False
        self._core_session: Any = None

    def update_query(self, query: str) -> None:
        with self._lock:
            if self._closed:
                return
            self._pending_query = str(query)
            if self._worker_running:
                return
            self._worker_running = True
        Thread(target=self._run_queries, name="pycodex-file-search", daemon=True).start()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._pending_query = None
            core_session = self._core_session
            self._core_session = None
        _close_session(core_session)

    def _run_queries(self) -> None:
        from pycodex.file_search import FileSearchOptions as CoreFileSearchOptions
        from pycodex.file_search import create_session

        with self._lock:
            core_session = self._core_session
        if core_session is None:
            try:
                core_session = create_session(
                    self._roots,
                    CoreFileSearchOptions(compute_indices=self._options.compute_indices),
                    self._reporter,
                    self._cancel_flag,
                )
            except Exception:
                with self._lock:
                    self._worker_running = False
                self._reporter.on_complete()
                return
            with self._lock:
                if self._closed:
                    self._worker_running = False
                    _close_session(core_session)
                    return
                self._core_session = core_session

        while True:
            with self._lock:
                if self._closed:
                    self._worker_running = False
                    return
                query = self._pending_query
                self._pending_query = None
                if query is None:
                    self._worker_running = False
                    return
            core_session.update_query(query)


class FileSearchManager:
    def __init__(
        self,
        search_dir: Union[str, Path],
        tx: Any,
        session_factory: Optional[SessionFactory] = None,
    ) -> None:
        self.state = SearchState()
        self._lock = Lock()
        self.search_dir = Path(search_dir)
        self.app_tx = tx
        self.session_factory = session_factory or _default_session_factory

    @classmethod
    def new(
        cls,
        search_dir: Union[str, Path],
        tx: Any,
        session_factory: Optional[SessionFactory] = None,
    ) -> "FileSearchManager":
        return cls(search_dir, tx, session_factory=session_factory)

    def update_search_dir(self, new_dir: Union[str, Path]) -> None:
        self.search_dir = Path(new_dir)
        with self._lock:
            _close_session(self.state.session)
            self.state.session = None
            self.state.latest_query = ""

    def on_user_query(self, query: str) -> None:
        with self._lock:
            if query == self.state.latest_query:
                return
            self.state.latest_query = query

            if query == "":
                _close_session(self.state.session)
                self.state.session = None
                return

            if self.state.session is None:
                self.start_session_locked(self.state)
            session = self.state.session

        if session is not None:
            session.update_query(query)

    def start_session_locked(self, st: SearchState) -> None:
        st.session_token = (st.session_token + 1) % (2**64)
        reporter = TuiSessionReporter(state=st, lock=self._lock, app_tx=self.app_tx, session_token=st.session_token)
        try:
            st.session = self.session_factory(
                [self.search_dir],
                FileSearchOptions(compute_indices=True),
                reporter,
                None,
            )
        except Exception:
            st.session = None


@dataclass
class TuiSessionReporter:
    state: SearchState
    lock: Lock
    app_tx: Any
    session_token: int

    def send_snapshot(self, snapshot: Any) -> None:
        with self.lock:
            if self.state.session_token != self.session_token:
                return
            if self.state.latest_query == "":
                return
            query = _field(snapshot, "query", "")
            if query == "":
                return
            matches = list(_field(snapshot, "matches", []))

        _send_event(self.app_tx, AppEvent.file_search_result(query, matches))

    def on_update(self, snapshot: Any) -> None:
        self.send_snapshot(snapshot)

    def on_complete(self) -> None:
        return None


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _send_event(tx: Any, event: AppEvent) -> None:
    send = getattr(tx, "send", None)
    if callable(send):
        send(event)
    elif callable(tx):
        tx(event)
    else:
        raise TypeError("app event target must be callable or expose send(event)")


def _close_session(session: Optional[FileSearchSession]) -> None:
    close = getattr(session, "close", None)
    if callable(close):
        close()


def on_update(reporter: TuiSessionReporter, snapshot: Any) -> None:
    reporter.on_update(snapshot)


def on_complete(reporter: TuiSessionReporter) -> None:
    reporter.on_complete()


__all__ = [
    "FileSearchManager",
    "FileSearchOptions",
    "FileSearchSession",
    "RUST_MODULE",
    "SearchState",
    "TuiSessionReporter",
    "on_complete",
    "on_update",
]

