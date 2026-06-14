"""TUI file-search session orchestration for Rust ``codex-tui::file_search``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable, List, Optional, Protocol, Union

from ._porting import RustTuiModule
from .app_event import AppEvent

RUST_MODULE = RustTuiModule(crate="codex-tui", module="file_search", source="codex/codex-rs/tui/src/file_search.rs")


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
    _roots: List[Path],
    _options: FileSearchOptions,
    _reporter: "TuiSessionReporter",
    _cancel_flag: Any,
) -> FileSearchSession:
    raise RuntimeError("file search session backend is not configured")


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
            self.state.session = None
            self.state.latest_query = ""

    def on_user_query(self, query: str) -> None:
        with self._lock:
            if query == self.state.latest_query:
                return
            self.state.latest_query = query

            if query == "":
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

