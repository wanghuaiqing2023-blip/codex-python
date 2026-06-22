import asyncio
from dataclasses import dataclass
from pathlib import Path

from pycodex import file_search
from pycodex.app_server.fuzzy_file_search import (
    MATCH_LIMIT,
    CancellationFlag,
    collect_files,
    run_fuzzy_file_search,
    start_fuzzy_file_search_session,
)
from pycodex.app_server_protocol import FuzzyFileSearchMatchType


@dataclass
class Match:
    root: Path
    path: Path
    score: int
    indices: list[int]
    match_type: file_search.MatchType = file_search.MatchType.FILE


@dataclass
class Snapshot:
    query: str
    matches: list[Match]


class Outgoing:
    def __init__(self) -> None:
        self.notifications = []

    async def send_server_notification(self, notification):
        self.notifications.append(notification)


def test_run_fuzzy_file_search_empty_roots_returns_empty_without_runner() -> None:
    # Rust: codex-app-server/src/fuzzy_file_search.rs run_fuzzy_file_search returns Vec::new for empty roots.
    def runner(*_args):
        raise AssertionError("runner should not be called")

    assert asyncio.run(run_fuzzy_file_search("main", [], runner=runner)) == []


def test_run_fuzzy_file_search_maps_and_sorts_matches() -> None:
    # Rust: one-shot results map root/path/match_type/file_name/score/indices, sorted score desc then path asc.
    root = Path("/repo")

    def runner(query, roots, options, cancellation_flag):
        assert query == "cfg"
        assert roots == [root]
        assert options.limit == MATCH_LIMIT
        assert options.compute_indices is True
        assert cancellation_flag.canceled is False
        return file_search.FileSearchResults(
            matches=[
                Match(root, root / "zeta.py", 10, [0]),
                Match(root, root / "alpha.py", 10, [1, 2]),
                Match(root, root / "src", 3, [], file_search.MatchType.DIRECTORY),
            ]
        )

    files = asyncio.run(run_fuzzy_file_search("cfg", [str(root)], CancellationFlag(), runner=runner))

    assert [file.path for file in files] == [str(root / "alpha.py"), str(root / "zeta.py"), str(root / "src")]
    assert files[0].root == str(root)
    assert files[0].file_name == "alpha.py"
    assert files[0].match_type is FuzzyFileSearchMatchType.FILE
    assert files[0].indices == [1, 2]
    assert files[2].match_type is FuzzyFileSearchMatchType.DIRECTORY


def test_run_fuzzy_file_search_failure_returns_empty() -> None:
    # Rust: file_search error or join error warns and returns Vec::new.
    def runner(*_args):
        raise RuntimeError("search failed")

    assert asyncio.run(run_fuzzy_file_search("main", ["/repo"], runner=runner)) == []


def test_collect_files_sorts_snapshot_matches_and_preserves_payload_fields() -> None:
    # Rust: collect_files maps snapshot matches and sorts by score desc, path asc.
    root = Path("/repo")
    files = collect_files(
        Snapshot(
            query="a",
            matches=[
                Match(root, root / "b.py", 42, [2]),
                Match(root, root / "a.py", 42, [1]),
            ],
        )
    )

    assert [file.to_camel_mapping() for file in files] == [
        {
            "root": str(root),
            "path": str(root / "a.py"),
            "matchType": "file",
            "fileName": "a.py",
            "score": 42,
            "indices": [1],
        },
        {
            "root": str(root),
            "path": str(root / "b.py"),
            "matchType": "file",
            "fileName": "b.py",
            "score": 42,
            "indices": [2],
        },
    ]


def test_session_update_records_latest_query_and_forwards_to_inner_session() -> None:
    # Rust: FuzzyFileSearchSession::update_query stores latest_query then calls session.update_query.
    class InnerSession:
        def __init__(self) -> None:
            self.queries = []

        def update_query(self, query: str) -> None:
            self.queries.append(query)

    captured = {}

    def factory(roots, options, reporter, cancellation_flag):
        captured.update(roots=roots, options=options, reporter=reporter, cancellation_flag=cancellation_flag)
        return InnerSession()

    session = start_fuzzy_file_search_session("s1", ["/repo"], Outgoing(), create_session=factory)
    session.update_query("main")

    assert captured["roots"] == [Path("/repo")]
    assert captured["options"].limit == MATCH_LIMIT
    assert captured["options"].compute_indices is True
    assert session._session.queries == ["main"]


def test_session_snapshot_sends_only_matching_latest_query_and_empty_query_has_no_files() -> None:
    # Rust: reporter ignores stale snapshots and sends empty files for an empty query.
    root = Path("/repo")
    outgoing = Outgoing()
    captured = {}

    class InnerSession:
        def update_query(self, _query: str) -> None:
            pass

    def factory(_roots, _options, reporter, _cancellation_flag):
        captured["reporter"] = reporter
        return InnerSession()

    session = start_fuzzy_file_search_session("s1", [str(root)], outgoing, create_session=factory)
    session.update_query("main")
    captured["reporter"].on_update(Snapshot("other", [Match(root, root / "main.py", 7, [0])]))
    captured["reporter"].on_update(Snapshot("main", [Match(root, root / "main.py", 7, [0])]))
    session.update_query("")
    captured["reporter"].on_update(Snapshot("", [Match(root, root / "hidden.py", 99, [0])]))

    assert len(outgoing.notifications) == 2
    first = outgoing.notifications[0].payload
    assert first.session_id == "s1"
    assert first.query == "main"
    assert [file.file_name for file in first.files] == ["main.py"]
    second = outgoing.notifications[1].payload
    assert second.query == ""
    assert second.files == []


def test_session_complete_and_close_respect_canceled_flag() -> None:
    # Rust: Drop marks canceled; update/complete reporters stop sending after cancellation.
    outgoing = Outgoing()
    captured = {}

    class InnerSession:
        def __init__(self) -> None:
            self.queries = []

        def update_query(self, query: str) -> None:
            self.queries.append(query)

    def factory(_roots, _options, reporter, _cancellation_flag):
        captured["reporter"] = reporter
        return InnerSession()

    session = start_fuzzy_file_search_session("s1", ["/repo"], outgoing, create_session=factory)
    captured["reporter"].on_complete()
    session.close()
    session.update_query("late")
    captured["reporter"].on_complete()

    assert [notification.type for notification in outgoing.notifications] == ["FuzzyFileSearchSessionCompleted"]
    assert session._session.queries == []
