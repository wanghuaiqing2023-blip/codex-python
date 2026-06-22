from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from pycodex.protocol import SessionSource, ThreadId
from pycodex.state.model.thread_metadata import ThreadMetadataBuilder
from pycodex.thread_store import (
    ArchiveThreadParams,
    ListThreadsParams,
    LocalThreadStore,
    LocalThreadStoreConfig,
    SortDirection,
    ThreadSortKey,
)


def thread_id(hex_tail: str = "000000000701") -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{hex_tail}")


class FakeStateDb:
    def __init__(self) -> None:
        self.threads: dict[str, object] = {}

    async def get_thread(self, thread: ThreadId) -> object | None:
        return self.threads.get(str(thread))

    def upsert_thread(self, metadata: object) -> None:
        self.threads[str(getattr(metadata, "id"))] = metadata

    async def mark_archived(self, thread: ThreadId, archived_path: Path, archived_at: datetime) -> None:
        metadata = self.threads[str(thread)]
        metadata.rollout_path = archived_path
        metadata.archived_at = archived_at

    async def mark_unarchived(self, thread: ThreadId, restored_path: Path) -> None:
        metadata = self.threads[str(thread)]
        metadata.rollout_path = restored_path
        metadata.archived_at = None


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
    message: str = "User message",
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


def state_metadata(thread: ThreadId, rollout_path: Path, *, archived: bool = False) -> object:
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
    if archived:
        metadata.archived_at = metadata.updated_at
    return metadata


def test_archive_thread_moves_rollout_to_archived_collection(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/archive_thread.rs::archive_thread_moves_rollout_to_archived_collection
    # Contract: archive_thread moves an active rollout to archived_sessions and archived list marks archived_at.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        thread = thread_id("000000000701")
        active_path = write_session_file(codex_home, thread)

        await store(codex_home).archive_thread(ArchiveThreadParams(thread))

        archived_path = codex_home / "archived_sessions" / active_path.name
        assert not active_path.exists()
        assert archived_path.exists()

        archived = await store(codex_home).list_threads(list_params(archived=True))
        assert len(archived.items) == 1
        assert archived.items[0].thread_id == thread
        assert archived.items[0].rollout_path == archived_path
        assert archived.items[0].archived_at == archived.items[0].updated_at

    asyncio.run(run())


def test_archive_thread_updates_sqlite_metadata_when_present(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/archive_thread.rs::archive_thread_updates_sqlite_metadata_when_present
    # Contract: archive_thread calls state_db.mark_archived with the archived rollout path.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        thread = thread_id("000000000702")
        active_path = write_session_file(codex_home, thread)
        state_db = FakeStateDb()
        state_db.upsert_thread(state_metadata(thread, active_path))

        await store(codex_home, state_db).archive_thread(ArchiveThreadParams(thread))

        archived_path = codex_home / "archived_sessions" / active_path.name
        updated = await state_db.get_thread(thread)
        assert updated.rollout_path == archived_path
        assert updated.archived_at is not None

    asyncio.run(run())


def test_unarchive_thread_restores_rollout_and_returns_updated_thread(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/unarchive_thread.rs::unarchive_thread_restores_rollout_and_returns_updated_thread
    # Contract: unarchive_thread restores archived rollout into dated sessions dir and returns an active thread summary.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        thread = thread_id("000000000703")
        archived_path = write_session_file(
            codex_home,
            thread,
            archived=True,
            timestamp="2025-01-03T13-00-00",
            message="Archived user message",
        )

        restored = await store(codex_home).unarchive_thread(ArchiveThreadParams(thread))

        restored_path = codex_home / "sessions" / "2025" / "01" / "03" / archived_path.name
        assert not archived_path.exists()
        assert restored_path.exists()
        assert restored.thread_id == thread
        assert restored.rollout_path == restored_path
        assert restored.archived_at is None
        assert restored.preview == "Archived user message"
        assert restored.first_user_message == "Archived user message"

    asyncio.run(run())


def test_unarchive_thread_updates_sqlite_metadata_when_present(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/unarchive_thread.rs::unarchive_thread_updates_sqlite_metadata_when_present
    # Contract: unarchive_thread calls state_db.mark_unarchived with the restored rollout path.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        thread = thread_id("000000000704")
        archived_path = write_session_file(codex_home, thread, archived=True, timestamp="2025-01-03T13-00-00")
        state_db = FakeStateDb()
        state_db.upsert_thread(state_metadata(thread, archived_path, archived=True))

        await store(codex_home, state_db).unarchive_thread(ArchiveThreadParams(thread))

        restored_path = codex_home / "sessions" / "2025" / "01" / "03" / archived_path.name
        updated = await state_db.get_thread(thread)
        assert updated.rollout_path == restored_path
        assert updated.archived_at is None

    asyncio.run(run())
