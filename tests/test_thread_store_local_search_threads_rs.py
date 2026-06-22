from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pycodex.protocol import SessionSource, ThreadId
from pycodex.state.model.thread_metadata import ThreadMetadataBuilder
from pycodex.thread_store import (
    LocalThreadStore,
    LocalThreadStoreConfig,
    SearchThreadsParams,
    SortDirection,
    ThreadSortKey,
    ThreadStoreError,
)


def thread_id(hex_tail: str = "000000000601") -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{hex_tail}")


class FakeStateDb:
    def __init__(self) -> None:
        self.threads: dict[str, object] = {}

    async def get_thread(self, thread: ThreadId) -> object | None:
        return self.threads.get(str(thread))

    def upsert_thread(self, metadata: object) -> None:
        self.threads[str(getattr(metadata, "id"))] = metadata


def store(codex_home: Path, state_db: FakeStateDb | None = None) -> LocalThreadStore:
    return LocalThreadStore(
        LocalThreadStoreConfig(
            codex_home=codex_home,
            sqlite_home=codex_home,
            default_model_provider_id="test-provider",
        ),
        state_db,
    )


def search_params(**overrides: object) -> SearchThreadsParams:
    values: dict[str, object] = {
        "page_size": 10,
        "cursor": None,
        "sort_key": ThreadSortKey.CREATED_AT,
        "sort_direction": SortDirection.DESC,
        "allowed_sources": (),
        "archived": False,
        "search_term": "needle",
    }
    values.update(overrides)
    return SearchThreadsParams(**values)


def write_session_file(
    codex_home: Path,
    thread: ThreadId,
    *,
    message: str = "Hello needle from user",
    archived: bool = False,
    timestamp: str = "2025-01-03T12-00-00",
) -> Path:
    day_dir = codex_home / "archived_sessions" if archived else codex_home / "sessions" / "2025" / "01" / "03"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"rollout-{timestamp}-{thread}.jsonl"
    iso_timestamp = f"{timestamp[:13]}:{timestamp[14:16]}:{timestamp[17:19]}Z"
    lines = [
        {
            "timestamp": iso_timestamp,
            "type": "session_meta",
            "payload": {
                "id": str(thread),
                "timestamp": iso_timestamp,
                "cwd": str(codex_home),
                "originator": "test_originator",
                "cli_version": "test_version",
                "source": "cli",
                "model_provider": "test-provider",
            },
        },
        {
            "timestamp": iso_timestamp,
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": message,
                "kind": "plain",
            },
        },
    ]
    path.write_text("".join(json.dumps(line, separators=(",", ":")) + "\n" for line in lines), encoding="utf-8")
    return path


def state_metadata(thread: ThreadId, rollout_path: Path, *, title: str, preview: str) -> object:
    builder = ThreadMetadataBuilder.new(
        thread,
        rollout_path,
        datetime(2025, 1, 3, 12, 0, 0, tzinfo=timezone.utc),
        SessionSource.cli(),
    )
    builder.model_provider = "test-provider"
    builder.cwd = rollout_path.parent
    builder.cli_version = "test_version"
    metadata = builder.build("test-provider")
    metadata.title = title
    metadata.first_user_message = preview
    metadata.preview = preview
    return metadata


def test_search_threads_rejects_empty_search_term(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/source contract: src/local/search_threads.rs::search_threads
    # Contract: empty search_term is an invalid request before rollout scanning.
    async def run() -> None:
        with pytest.raises(ThreadStoreError) as err:
            await store(tmp_path / "codex-home").search_threads(search_params(search_term=""))

        assert err.value.kind == "invalid_request"
        assert err.value.fields["message"] == "thread/search requires search_term"

    asyncio.run(run())


def test_search_threads_rejects_invalid_cursor(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/source contract: src/local/search_threads.rs::search_threads parse_cursor boundary.
    # Contract: invalid cursor strings fail as invalid_request before listing pages.
    async def run() -> None:
        with pytest.raises(ThreadStoreError) as err:
            await store(tmp_path / "codex-home").search_threads(search_params(cursor="not-a-cursor"))

        assert err.value.kind == "invalid_request"
        assert err.value.fields["message"] == "invalid cursor: not-a-cursor"

    asyncio.run(run())


def test_search_threads_returns_empty_page_when_no_rollout_matches(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/source contract: src/local/search_threads.rs::search_threads matching_paths.is_empty branch.
    # Contract: no content matches returns an empty ThreadSearchPage with no next cursor.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        write_session_file(codex_home, thread_id("000000000602"), message="ordinary text")

        page = await store(codex_home).search_threads(search_params())

        assert page.items == ()
        assert page.next_cursor is None

    asyncio.run(run())


def test_search_threads_returns_snippet_and_rollout_summary(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/source contract: src/local/search_threads.rs::search_threads with rollout search/snippet helpers.
    # Contract: matching rollout content yields StoredThreadSearchResult summary and first content snippet.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        thread = thread_id("000000000603")
        path = write_session_file(codex_home, thread, message="before Needle after")

        page = await store(codex_home).search_threads(search_params(allowed_sources=(SessionSource.cli(),)))

        assert len(page.items) == 1
        result = page.items[0]
        assert result.thread.thread_id == thread
        assert result.thread.rollout_path == path
        assert result.thread.model_provider == "test-provider"
        assert result.thread.cli_version == "test_version"
        assert result.thread.source == SessionSource.cli()
        assert result.snippet == "before Needle after"

    asyncio.run(run())


def test_search_threads_paginates_by_matching_sorted_rollouts(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/source contract: src/local/search_threads.rs::cursor_from_thread_search_item.
    # Contract: search scans list order, returns one extra match to decide next_cursor, then resumes after cursor.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        older = thread_id("000000000604")
        newer = thread_id("000000000605")
        write_session_file(codex_home, older, message="older needle", timestamp="2025-01-03T12-00-00")
        write_session_file(codex_home, newer, message="newer needle", timestamp="2025-01-03T13-00-00")
        local_store = store(codex_home)

        first_page = await local_store.search_threads(search_params(page_size=1))
        second_page = await local_store.search_threads(search_params(page_size=1, cursor=first_page.next_cursor))

        assert [item.thread.thread_id for item in first_page.items] == [newer]
        assert first_page.next_cursor is not None
        assert [item.thread.thread_id for item in second_page.items] == [older]
        assert second_page.next_cursor is None

    asyncio.run(run())


def test_search_threads_applies_sqlite_title_to_result_name(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/source contract: src/local/search_threads.rs::set_thread_search_result_names.
    # Contract: search results receive distinct state-db titles without replacing the first message snippet.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        state_db = FakeStateDb()
        thread = thread_id("000000000606")
        path = write_session_file(codex_home, thread, message="plain needle preview")
        state_db.upsert_thread(state_metadata(thread, path, title="state title", preview="plain needle preview"))

        page = await store(codex_home, state_db).search_threads(search_params())

        assert [item.thread.thread_id for item in page.items] == [thread]
        assert page.items[0].thread.name == "state title"
        assert page.items[0].thread.first_user_message == "plain needle preview"
        assert page.items[0].snippet == "plain needle preview"

    asyncio.run(run())
