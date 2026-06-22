from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pycodex.protocol import SessionSource, ThreadId
from pycodex.rollout import append_thread_name
from pycodex.state.model.thread_metadata import ThreadMetadataBuilder
from pycodex.thread_store import (
    LocalThreadStore,
    LocalThreadStoreConfig,
    ReadThreadByRolloutPathParams,
    ReadThreadParams,
    ThreadStoreError,
)


def thread_id(hex_tail: str = "000000000401") -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{hex_tail}")


def store(codex_home: Path) -> LocalThreadStore:
    return LocalThreadStore(
        LocalThreadStoreConfig(
            codex_home=codex_home,
            sqlite_home=codex_home,
            default_model_provider_id="test-provider",
        )
    )


class FakeStateDb:
    def __init__(self) -> None:
        self.threads: dict[str, object] = {}

    async def get_thread(self, thread: ThreadId) -> object | None:
        return self.threads.get(str(thread))

    def upsert_thread(self, metadata: object) -> None:
        self.threads[str(getattr(metadata, "id"))] = metadata


def store_with_state(codex_home: Path, state_db: FakeStateDb) -> LocalThreadStore:
    return LocalThreadStore(
        LocalThreadStoreConfig(
            codex_home=codex_home,
            sqlite_home=codex_home,
            default_model_provider_id="test-provider",
        ),
        state_db,
    )


def state_metadata(
    thread: ThreadId,
    rollout_path: Path,
    *,
    source: SessionSource | None = None,
    provider: str = "sqlite-provider",
    cwd: Path | None = None,
    title: str = "",
    preview: str | None = None,
    first_user_message: str | None = None,
    git_sha: str | None = None,
    git_branch: str | None = None,
    git_origin_url: str | None = None,
    archived_at: datetime | None = None,
) -> object:
    builder = ThreadMetadataBuilder.new(
        thread,
        rollout_path,
        datetime(2025, 1, 3, 12, 0, 0, tzinfo=timezone.utc),
        source or SessionSource.cli(),
    )
    builder.model_provider = provider
    builder.cwd = cwd or rollout_path.parent
    builder.cli_version = "sqlite-cli"
    builder.git_sha = git_sha
    builder.git_branch = git_branch
    builder.git_origin_url = git_origin_url
    builder.archived_at = archived_at
    metadata = builder.build("test-provider")
    metadata.title = title
    metadata.preview = preview
    metadata.first_user_message = first_user_message
    return metadata


def write_session_file(
    codex_home: Path,
    thread: ThreadId,
    *,
    message: str = "Hello from user",
    provider: str | None = "test-provider",
    forked_from_id: ThreadId | None = None,
    only_meta: bool = False,
    archived: bool = False,
) -> Path:
    day_dir = codex_home / "archived_sessions" if archived else codex_home / "sessions" / "2025" / "01" / "03"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"rollout-2025-01-03T12-00-00-{thread}.jsonl"
    lines: list[dict[str, object]] = [
        {
            "timestamp": "2025-01-03T12:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": str(thread),
                "forked_from_id": str(forked_from_id) if forked_from_id is not None else None,
                "timestamp": "2025-01-03T12:00:00Z",
                "cwd": str(codex_home),
                "originator": "test_originator",
                "cli_version": "test_version",
                "source": "cli",
                "model_provider": provider,
                "git": {
                    "commit_hash": "abcdef",
                    "branch": "main",
                    "repository_url": "https://example.com/repo.git",
                },
            },
        }
    ]
    if not only_meta:
        lines.append(
            {
                "timestamp": "2025-01-03T12:00:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": message,
                    "kind": "plain",
                },
            }
        )
    path.write_text("".join(json.dumps(line, separators=(",", ":")) + "\n" for line in lines), encoding="utf-8")
    return path


def test_read_thread_returns_active_rollout_summary(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_returns_active_rollout_summary
    # Contract: read_thread locates an active rollout by id, builds a summary from the first user event, and loads history.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        local_store = store(codex_home)
        thread = thread_id()
        active_path = write_session_file(codex_home, thread)

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=False, include_history=True)
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == active_path
        assert stored.archived_at is None
        assert stored.preview == "Hello from user"
        assert stored.first_user_message == "Hello from user"
        assert stored.history is not None
        assert stored.history.thread_id == thread
        assert len(stored.history.items) == 2

    asyncio.run(run())


def test_read_thread_returns_rollout_path_summary(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_returns_rollout_path_summary
    # Contract: read_thread_by_rollout_path accepts paths relative to codex_home and canonicalizes the stored path.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        local_store = store(codex_home)
        thread = thread_id("000000000402")
        active_path = write_session_file(codex_home, thread)
        relative_path = active_path.relative_to(codex_home)

        stored = await local_store.read_thread_by_rollout_path(
            ReadThreadByRolloutPathParams(
                rollout_path=relative_path,
                include_archived=False,
                include_history=False,
            )
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == active_path.resolve()
        assert stored.preview == "Hello from user"
        assert stored.history is None

    asyncio.run(run())


def test_read_thread_by_rollout_path_prefers_sqlite_git_info(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_by_rollout_path_prefers_sqlite_git_info
    # Contract: read_thread_by_rollout_path overlays SQLite git fields while preserving missing fields from rollout git.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        state_db = FakeStateDb()
        local_store = store_with_state(codex_home, state_db)
        thread = thread_id("000000000416")
        active_path = write_session_file(codex_home, thread)
        state_db.upsert_thread(
            state_metadata(
                thread,
                active_path,
                provider="test-provider",
                git_branch="sqlite-branch",
            )
        )

        stored = await local_store.read_thread_by_rollout_path(
            ReadThreadByRolloutPathParams(
                rollout_path=active_path,
                include_archived=False,
                include_history=False,
            )
        )

        assert stored.git_info is not None
        assert stored.git_info.branch == "sqlite-branch"
        assert stored.git_info.sha == "abcdef"
        assert stored.git_info.origin_url == "https://example.com/repo.git"

    asyncio.run(run())


def test_read_thread_returns_forked_from_id(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_returns_forked_from_id
    # Contract: read_thread overlays forked_from_id from session_meta when building the rollout summary.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        local_store = store(codex_home)
        thread = thread_id("000000000403")
        parent = thread_id("000000000404")
        write_session_file(codex_home, thread, message="Forked user message", forked_from_id=parent)

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=False, include_history=False)
        )

        assert stored.forked_from_id == parent

    asyncio.run(run())


def test_read_thread_returns_archived_rollout_when_requested(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_returns_archived_rollout_when_requested
    # Contract: active-only lookup ignores archived rollouts; include_archived resolves them and marks archived_at.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        local_store = store(codex_home)
        thread = thread_id("000000000407")
        archived_path = write_session_file(
            codex_home,
            thread,
            message="Archived user message",
            archived=True,
        )

        with pytest.raises(ThreadStoreError) as active_only_err:
            await local_store.read_thread(
                ReadThreadParams(thread_id=thread, include_archived=False, include_history=False)
            )
        assert active_only_err.value.kind == "invalid_request"
        assert active_only_err.value.fields["message"] == f"no rollout found for thread id {thread}"

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=True, include_history=False)
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == archived_path
        assert stored.archived_at is not None
        assert stored.preview == "Archived user message"
        assert stored.history is None

    asyncio.run(run())


def test_read_thread_uses_legacy_thread_name_when_sqlite_title_is_missing(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_uses_legacy_thread_name_when_sqlite_title_is_missing
    # Contract: rollout-backed reads apply the legacy thread-name index when SQLite metadata has no title.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        local_store = store(codex_home)
        thread = thread_id("000000000409")
        write_session_file(codex_home, thread)
        append_thread_name(codex_home, thread, "Legacy title")

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=False, include_history=False)
        )

        assert stored.name == "Legacy title"

    asyncio.run(run())


def test_read_thread_uses_sqlite_metadata_for_rollout_without_user_preview(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_uses_sqlite_metadata_for_rollout_without_user_preview
    # Contract: when a rollout can load history but has no preview, read_thread returns SQLite metadata fields and history.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        state_db = FakeStateDb()
        local_store = store_with_state(codex_home, state_db)
        thread = thread_id("000000000410")
        rollout_path = write_session_file(codex_home, thread, provider="rollout-provider", only_meta=True)
        state_db.upsert_thread(
            state_metadata(
                thread,
                rollout_path,
                provider="sqlite-provider",
                cwd=codex_home / "workspace",
                title="Command-only thread",
            )
        )

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=False, include_history=True)
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == rollout_path
        assert stored.preview == ""
        assert stored.name == "Command-only thread"
        assert stored.model_provider == "sqlite-provider"
        assert stored.cwd == codex_home / "workspace"
        assert stored.cli_version == "sqlite-cli"
        assert stored.history is not None
        assert stored.history.thread_id == thread
        assert len(stored.history.items) == 1

    asyncio.run(run())


def test_read_thread_applies_sqlite_thread_name(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_applies_sqlite_thread_name
    # Contract: read_thread may use rollout preview while preserving a distinct SQLite title as StoredThread.name.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        state_db = FakeStateDb()
        local_store = store_with_state(codex_home, state_db)
        thread = thread_id("000000000414")
        rollout_path = write_session_file(codex_home, thread)
        state_db.upsert_thread(
            state_metadata(
                thread,
                rollout_path,
                provider="sqlite-provider",
                cwd=codex_home / "sqlite-workspace",
                title="Saved title",
                first_user_message="Hello from user",
            )
        )

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=False, include_history=False)
        )

        assert stored.preview == "Hello from user"
        assert stored.name == "Saved title"
        assert stored.model_provider == "test-provider"
        assert stored.cwd == codex_home

    asyncio.run(run())


def test_read_thread_falls_back_to_sqlite_summary(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_falls_back_to_sqlite_summary
    # Contract: without requested history, valid SQLite metadata can be returned even when rollout_path is external/missing.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        external = tmp_path / "external"
        state_db = FakeStateDb()
        local_store = store_with_state(codex_home, state_db)
        thread = thread_id("000000000415")
        rollout_path = external / f"rollout-2025-01-03T12-00-00-{thread}.jsonl"
        metadata = state_metadata(
            thread,
            rollout_path,
            source=SessionSource.exec(),
            provider="sqlite-provider",
            cwd=external / "workspace",
            title="next normal prompt",
            preview="optimize the benchmark",
            first_user_message="next normal prompt",
        )
        metadata.model = "sqlite-model"
        state_db.upsert_thread(metadata)

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=False, include_history=False)
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == rollout_path
        assert stored.preview == "optimize the benchmark"
        assert stored.first_user_message == "next normal prompt"
        assert stored.name is None
        assert stored.model_provider == "sqlite-provider"
        assert stored.model == "sqlite-model"
        assert stored.cwd == external / "workspace"
        assert stored.cli_version == "sqlite-cli"
        assert stored.source == SessionSource.exec()
        assert stored.archived_at is None
        assert stored.history is None

    asyncio.run(run())


def test_read_thread_sqlite_fallback_respects_include_archived(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_sqlite_fallback_respects_include_archived
    # Contract: archived SQLite metadata is hidden from active-only reads and returned when include_archived is true.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        external = tmp_path / "external"
        state_db = FakeStateDb()
        local_store = store_with_state(codex_home, state_db)
        thread = thread_id("000000000417")
        rollout_path = external / f"rollout-2025-01-03T12-00-00-{thread}.jsonl"
        archived_at = datetime(2025, 1, 4, 12, 0, 0, tzinfo=timezone.utc)
        state_db.upsert_thread(
            state_metadata(
                thread,
                rollout_path,
                archived_at=archived_at,
                first_user_message="Archived SQLite preview",
            )
        )

        with pytest.raises(ThreadStoreError) as active_only_err:
            await local_store.read_thread(
                ReadThreadParams(thread_id=thread, include_archived=False, include_history=False)
            )
        assert active_only_err.value.kind == "invalid_request"
        assert active_only_err.value.fields["message"] == f"no rollout found for thread id {thread}"

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=True, include_history=False)
        )

        assert stored.thread_id == thread
        assert stored.preview == "Archived SQLite preview"
        assert stored.archived_at == archived_at

    asyncio.run(run())


def test_read_thread_sqlite_fallback_loads_archived_history(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_sqlite_fallback_loads_archived_history
    # Contract: archived SQLite metadata can load archived rollout history when include_archived and include_history are true.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        state_db = FakeStateDb()
        local_store = store_with_state(codex_home, state_db)
        thread = thread_id("000000000418")
        archived_path = write_session_file(
            codex_home,
            thread,
            message="Archived user message",
            archived=True,
        )
        archived_at = datetime(2025, 1, 4, 12, 0, 0, tzinfo=timezone.utc)
        state_db.upsert_thread(
            state_metadata(
                thread,
                archived_path,
                archived_at=archived_at,
                first_user_message="Archived SQLite preview",
            )
        )

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=True, include_history=True)
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == archived_path
        assert stored.preview == "Archived SQLite preview"
        assert stored.archived_at == archived_at
        assert stored.history is not None
        assert stored.history.thread_id == thread
        assert len(stored.history.items) == 2

    asyncio.run(run())


def test_read_thread_falls_back_to_rollout_search_when_sqlite_path_is_stale(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_falls_back_to_rollout_search_when_sqlite_path_is_stale
    # Contract: include_history verifies SQLite rollout_path before trusting it and falls back to filesystem search if stale.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        state_db = FakeStateDb()
        local_store = store_with_state(codex_home, state_db)
        thread = thread_id("000000000411")
        rollout_path = write_session_file(codex_home, thread)
        stale_path = tmp_path / "external" / "missing-rollout.jsonl"
        state_db.upsert_thread(
            state_metadata(
                thread,
                stale_path,
                provider="stale-sqlite-provider",
                first_user_message="stale sqlite preview",
            )
        )

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=True, include_history=True)
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == rollout_path
        assert stored.preview == "Hello from user"
        assert stored.model_provider == "test-provider"
        assert stored.history is not None
        assert len(stored.history.items) == 2

    asyncio.run(run())


def test_read_thread_falls_back_when_sqlite_path_points_to_another_thread(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_falls_back_when_sqlite_path_points_to_another_thread
    # Contract: include_history verifies the SQLite path belongs to the requested thread before trusting it.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        external = tmp_path / "external"
        state_db = FakeStateDb()
        local_store = store_with_state(codex_home, state_db)
        thread = thread_id("000000000412")
        other = thread_id("000000000413")
        rollout_path = write_session_file(codex_home, thread)
        stale_path = write_session_file(external, other)
        state_db.upsert_thread(
            state_metadata(
                thread,
                stale_path,
                provider="wrong-sqlite-provider",
                first_user_message="wrong sqlite preview",
            )
        )

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=True, include_history=True)
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == rollout_path
        assert stored.preview == "Hello from user"
        assert stored.model_provider == "test-provider"
        assert stored.history is not None
        assert len(stored.history.items) == 2

    asyncio.run(run())


def test_read_thread_prefers_active_rollout_over_archived(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_prefers_active_rollout_over_archived
    # Contract: include_archived still prefers the active rollout when active and archived files share an id.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        local_store = store(codex_home)
        thread = thread_id("000000000408")
        active_path = write_session_file(codex_home, thread)
        write_session_file(codex_home, thread, message="Archived user message", archived=True)

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=True, include_history=False)
        )

        assert stored.rollout_path == active_path
        assert stored.archived_at is None
        assert stored.preview == "Hello from user"

    asyncio.run(run())


def test_read_thread_uses_session_meta_when_rollout_has_no_user_preview(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_uses_session_meta_for_rollout_without_user_preview_or_sqlite_metadata
    # Contract: read_thread falls back to session_meta when no user preview exists and can still load one-item history.
    async def run() -> None:
        codex_home = tmp_path / "codex-home"
        local_store = store(codex_home)
        thread = thread_id("000000000405")
        active_path = write_session_file(codex_home, thread, provider="rollout-provider", only_meta=True)

        stored = await local_store.read_thread(
            ReadThreadParams(thread_id=thread, include_archived=False, include_history=True)
        )

        assert stored.thread_id == thread
        assert stored.rollout_path == active_path
        assert stored.preview == ""
        assert stored.name is None
        assert stored.model_provider == "rollout-provider"
        assert stored.created_at.isoformat().startswith("2025-01-03T12:00:00")
        assert stored.updated_at >= stored.created_at
        assert stored.archived_at is None
        assert stored.cwd == codex_home
        assert stored.cli_version == "test_version"
        assert stored.source == SessionSource.cli()
        assert stored.history is not None
        assert stored.history.thread_id == thread
        assert len(stored.history.items) == 1

    asyncio.run(run())


def test_read_thread_fails_without_rollout(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/read_thread.rs::read_thread_fails_without_rollout
    # Contract: missing rollout lookup returns InvalidRequest with the Rust no-rollout message shape.
    async def run() -> None:
        missing = thread_id("000000000406")

        with pytest.raises(ThreadStoreError) as err:
            await store(tmp_path / "codex-home").read_thread(
                ReadThreadParams(thread_id=missing, include_archived=False, include_history=False)
            )

        assert err.value.kind == "invalid_request"
        assert err.value.fields["message"] == f"no rollout found for thread id {missing}"

    asyncio.run(run())
