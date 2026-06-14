from dataclasses import dataclass
from pathlib import Path

from pycodex.tui.app_event import AppEvent
from pycodex.tui.file_search import FileSearchManager, TuiSessionReporter, on_complete, on_update


class Tx:
    def __init__(self) -> None:
        self.events = []

    def send(self, event):
        self.events.append(event)


class Session:
    def __init__(self) -> None:
        self.queries = []

    def update_query(self, query: str) -> None:
        self.queries.append(query)


@dataclass
class Snapshot:
    query: str
    matches: list[str]


def test_manager_starts_session_and_updates_query_once() -> None:
    # Rust source: FileSearchManager::on_user_query starts one session and ignores duplicate query.
    sessions = []

    def factory(roots, options, reporter, cancel_flag):
        assert roots == [Path("/repo")]
        assert options.compute_indices is True
        assert cancel_flag is None
        session = Session()
        sessions.append((session, reporter))
        return session

    manager = FileSearchManager.new("/repo", Tx(), session_factory=factory)
    manager.on_user_query("src")
    manager.on_user_query("src")

    assert len(sessions) == 1
    assert sessions[0][0].queries == ["src"]
    assert manager.state.latest_query == "src"


def test_empty_query_drops_session_and_next_query_restarts() -> None:
    sessions = []

    def factory(_roots, _options, _reporter, _cancel_flag):
        session = Session()
        sessions.append(session)
        return session

    manager = FileSearchManager.new("/repo", Tx(), session_factory=factory)
    manager.on_user_query("a")
    manager.on_user_query("")
    assert manager.state.latest_query == ""
    assert manager.state.session is None

    manager.on_user_query("b")
    assert len(sessions) == 2
    assert sessions[-1].queries == ["b"]


def test_update_search_dir_drops_session_and_clears_query() -> None:
    manager = FileSearchManager.new("/repo", Tx(), session_factory=lambda *_: Session())
    manager.on_user_query("a")
    assert manager.state.session is not None

    manager.update_search_dir("/other")
    assert manager.search_dir == Path("/other")
    assert manager.state.session is None
    assert manager.state.latest_query == ""


def test_failed_session_start_is_swallowed_and_query_is_kept() -> None:
    def factory(*_args):
        raise RuntimeError("boom")

    manager = FileSearchManager.new("/repo", Tx(), session_factory=factory)
    manager.on_user_query("a")
    assert manager.state.latest_query == "a"
    assert manager.state.session is None


def test_reporter_sends_only_current_non_empty_snapshots() -> None:
    tx = Tx()
    sessions = []

    def factory(_roots, _options, reporter, _cancel_flag):
        session = Session()
        sessions.append((session, reporter))
        return session

    manager = FileSearchManager.new("/repo", tx, session_factory=factory)
    manager.on_user_query("a")
    reporter: TuiSessionReporter = sessions[0][1]

    reporter.send_snapshot(Snapshot(query="", matches=["x"]))
    assert tx.events == []

    reporter.send_snapshot(Snapshot(query="a", matches=["x", "y"]))
    assert tx.events == [AppEvent.file_search_result("a", ["x", "y"])]

    manager.on_user_query("")
    reporter.send_snapshot(Snapshot(query="a", matches=["z"]))
    assert len(tx.events) == 1


def test_stale_reporter_token_is_ignored_and_free_functions_delegate() -> None:
    tx = Tx()
    manager = FileSearchManager.new("/repo", tx, session_factory=lambda *_: Session())
    manager.on_user_query("a")
    old_reporter = TuiSessionReporter(manager.state, manager._lock, tx, session_token=manager.state.session_token - 1)

    on_update(old_reporter, {"query": "a", "matches": ["old"]})
    on_complete(old_reporter)
    assert tx.events == []

def test_session_token_wraps_like_rust_wrapping_add() -> None:
    sessions = []

    def factory(_roots, _options, reporter, _cancel_flag):
        session = Session()
        sessions.append((session, reporter))
        return session

    manager = FileSearchManager.new("/repo", Tx(), session_factory=factory)
    manager.state.session_token = (2**64) - 1

    manager.on_user_query("wrap")

    assert manager.state.session_token == 0
    assert sessions[0][1].session_token == 0
    assert sessions[0][0].queries == ["wrap"]

