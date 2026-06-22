from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pycodex.protocol import SessionSource, ThreadId
from pycodex.state.model.thread_metadata import ThreadMetadataBuilder
from pycodex.thread_store import (
    ListThreadsParams,
    LocalThreadStore,
    LocalThreadStoreConfig,
    SortDirection,
    ThreadSortKey,
    ThreadStoreError,
)


def thread_id(hex_tail: str = "000000000501") -> ThreadId:
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


def list_params(**overrides: object) -> ListThreadsParams:
    values: dict[str, object] = {
        "page_size": 10,
        "cursor": None,
        "sort_key": ThreadSortKey.CREATED_AT,
        "sort_direction": SortDirection.DESC,
        "allowed_sources": (),
        "model_providers": None,
        "cwd_filters": None,
        "archived": False,
        "search_term": None,
        "use_state_db_only": False,
    }
    values.update(overrides)
    return ListThreadsParams(**values)


def write_session_file(
    codex_home: Path,
    thread: ThreadId,
    *,
    message: str = "Hello from user",
    provider: str | None = "test-provider",
    archived: bool = False,
    timestamp: str = "2025-01-03T12-00-00",
) -> Path:
    day_dir = codex_home / "archived_sessions" if archived else codex_home / "sessions" / "2025" / "01" / "03"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"rollout-{timestamp}-{thread}.jsonl"
    lines = [
        {
            "timestamp": "2025-01-03T12:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": str(thread),
                "timestamp": "2025-01-03T12:00:00Z",
                "cwd": str(codex_home),
                "originator": "test_originator",
                "cli_version": "test_version",
                "source": "cli",
                "model_provider": provider,
            },
        },
        {
            "timestamp": "2025-01-03T12:00:00Z",
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


def test_list_threads_uses_default_provider_when_rollout_omits_provider(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/list_threads.rs::list_threads_uses_default_provider_when_rollout_omits_provider
    # Contract: list_threads fills missing rollout model_provider from LocalThreadStoreConfig.default_model_provider_id.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        write_session_file(codex_home, thread_id("000000000502"), provider=None)

        page = await store(codex_home).list_threads(list_params())

        assert len(page.items) == 1
        assert page.items[0].model_provider == "test-provider"

    asyncio.run(run())


def test_list_threads_selects_active_or_archived_collection(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/list_threads.rs::list_threads_selects_active_or_archived_collection
    # Contract: active listings scan sessions; archived listings scan archived_sessions and mark archived_at.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        active = thread_id("000000000503")
        archived = thread_id("000000000504")
        write_session_file(codex_home, active, timestamp="2025-01-03T12-00-00")
        write_session_file(codex_home, archived, archived=True, timestamp="2025-01-03T13-00-00")
        local_store = store(codex_home)

        active_page = await local_store.list_threads(list_params())
        archived_page = await local_store.list_threads(list_params(archived=True))

        assert [item.thread_id for item in active_page.items] == [active]
        assert [item.thread_id for item in archived_page.items] == [archived]
        assert active_page.items[0].archived_at is None
        assert archived_page.items[0].archived_at == archived_page.items[0].updated_at

    asyncio.run(run())


def test_list_threads_returns_local_rollout_summary(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/list_threads.rs::list_threads_returns_local_rollout_summary
    # Contract: list_threads returns rollout id/path/preview/provider/version/source summary with filters applied.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        thread = thread_id()
        path = write_session_file(codex_home, thread)

        page = await store(codex_home).list_threads(
            list_params(
                allowed_sources=(SessionSource.cli(),),
                model_providers=("test-provider",),
            )
        )

        assert page.next_cursor is None
        assert len(page.items) == 1
        assert page.items[0].thread_id == thread
        assert page.items[0].rollout_path == path
        assert page.items[0].preview == "Hello from user"
        assert page.items[0].first_user_message == "Hello from user"
        assert page.items[0].model_provider == "test-provider"
        assert page.items[0].cli_version == "test_version"
        assert page.items[0].source == SessionSource.cli()

    asyncio.run(run())


def test_list_threads_rejects_invalid_cursor(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/list_threads.rs::list_threads_rejects_invalid_cursor
    # Contract: invalid cursor strings fail with InvalidRequest before listing.
    async def run() -> None:
        with pytest.raises(ThreadStoreError) as err:
            await store(tmp_path / "codex-home").list_threads(list_params(cursor="not-a-cursor"))

        assert err.value.kind == "invalid_request"
        assert err.value.fields["message"] == "invalid cursor: not-a-cursor"

    asyncio.run(run())


def test_list_threads_preserves_sqlite_title_search_results(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/list_threads.rs::list_threads_preserves_sqlite_title_search_results
    # Contract: state-db-only search matches SQLite title and preserves the first user message preview.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        state_db = FakeStateDb()
        thread = thread_id("000000000505")
        rollout_path = codex_home / "rollout-title-search.jsonl"
        state_db.upsert_thread(state_metadata(thread, rollout_path, title="needle title", preview="plain preview"))

        page = await store(codex_home, state_db).list_threads(
            list_params(search_term="needle", use_state_db_only=True)
        )

        assert [item.thread_id for item in page.items] == [thread]
        assert page.items[0].first_user_message == "plain preview"
        assert page.items[0].name == "needle title"

    asyncio.run(run())
