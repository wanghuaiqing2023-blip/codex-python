from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pycodex.protocol import EventMsg, RolloutItem, SessionSource, ThreadId, ThreadMemoryMode, ThreadSource, UserMessageEvent
from pycodex.protocol import AskForApproval, ReasoningEffort, SandboxPolicy
from pycodex.rollout import find_thread_name_by_id
from pycodex.state.model.thread_metadata import ThreadMetadataBuilder
from pycodex.thread_store import (
    AppendThreadItemsParams,
    CreateThreadParams,
    GitInfoPatch,
    ListThreadsParams,
    LocalThreadStore,
    LocalThreadStoreConfig,
    ResumeThreadParams,
    SortDirection,
    ThreadEventPersistenceMode,
    ThreadMetadataPatch,
    ThreadPersistenceMetadata,
    ThreadSortKey,
    ThreadStoreError,
    UpdateThreadMetadataParams,
    clear_field,
)


def thread_id(hex_tail: str = "000000000301") -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{hex_tail}")


class FakeStateDb:
    def __init__(self) -> None:
        self.threads: dict[str, object] = {}
        self.memory_modes: dict[str, str | None] = {}

    async def get_thread(self, thread: ThreadId) -> object | None:
        return self.threads.get(str(thread))

    def upsert_thread(self, metadata: object) -> None:
        self.threads[str(getattr(metadata, "id"))] = metadata

    async def get_thread_memory_mode(self, thread: ThreadId) -> str | None:
        return self.memory_modes.get(str(thread))

    async def update_thread_git_info(
        self,
        thread: ThreadId,
        sha: str | None,
        branch: str | None,
        origin_url: str | None,
    ) -> bool:
        metadata = self.threads.get(str(thread))
        if metadata is None:
            return False
        metadata.git_sha = sha
        metadata.git_branch = branch
        metadata.git_origin_url = origin_url
        return True

    async def update_thread_title(self, thread: ThreadId, title: str) -> bool:
        metadata = self.threads.get(str(thread))
        if metadata is None:
            return False
        metadata.title = title
        return True


class FailingStateDb(FakeStateDb):
    def __init__(self, *, fail_upsert: bool = False, fail_title: bool = False, fail_git: bool = False) -> None:
        super().__init__()
        self.fail_upsert = fail_upsert
        self.fail_title = fail_title
        self.fail_git = fail_git

    def upsert_thread(self, metadata: object) -> None:
        if self.fail_upsert:
            raise RuntimeError("state db upsert failed")
        super().upsert_thread(metadata)

    async def update_thread_title(self, thread: ThreadId, title: str) -> bool:
        if self.fail_title:
            raise RuntimeError("state db title update failed")
        return await super().update_thread_title(thread, title)

    async def update_thread_git_info(
        self,
        thread: ThreadId,
        sha: str | None,
        branch: str | None,
        origin_url: str | None,
    ) -> bool:
        if self.fail_git:
            raise RuntimeError("state db git update failed")
        return await super().update_thread_git_info(thread, sha, branch, origin_url)


class TokenUsage:
    def __init__(self, total_tokens: int) -> None:
        self.total_tokens = total_tokens


def store(tmp_path: Path, state_db: FakeStateDb | None = None) -> LocalThreadStore:
    return LocalThreadStore(
        LocalThreadStoreConfig(
            codex_home=tmp_path / "codex-home",
            sqlite_home=tmp_path / "sqlite-home",
            default_model_provider_id="test-provider",
        ),
        state_db,
    )


def create_params(thread: ThreadId, tmp_path: Path) -> CreateThreadParams:
    return CreateThreadParams(
        thread_id=thread,
        forked_from_id=None,
        source=SessionSource.exec(),
        thread_source=ThreadSource.USER,
        base_instructions=None,
        dynamic_tools=(),
        metadata=ThreadPersistenceMetadata(
            cwd=tmp_path,
            model_provider="test-provider",
            memory_mode=ThreadMemoryMode.ENABLED,
        ),
        event_persistence_mode=ThreadEventPersistenceMode.LIMITED,
    )


def last_rollout_item(path: Path) -> dict[str, object]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1])


def write_session_file(
    codex_home: Path,
    thread: ThreadId,
    *,
    archived: bool = False,
    timestamp: str = "2025-01-03T16-00-00",
    message: str = "Hello from archived thread",
) -> Path:
    folder = codex_home / "archived_sessions" if archived else codex_home / "sessions" / "2025" / "01" / "03"
    folder.mkdir(parents=True, exist_ok=True)
    rollout_path = folder / f"rollout-{timestamp}-{thread}.jsonl"
    session_meta = {
        "type": "session_meta",
        "payload": {
            "id": str(thread),
            "timestamp": f"{timestamp}Z",
            "source": "cli",
            "cwd": str(codex_home),
            "originator": "codex_cli_rs",
            "cli_version": "test_version",
            "instructions": None,
            "git": None,
            "model_provider": "test-provider",
        },
    }
    user_event = {
        "type": "event_msg",
        "payload": {
            "type": "user_message",
            "message": message,
        },
    }
    rollout_path.write_text(json.dumps(session_meta) + "\n" + json.dumps(user_event) + "\n", encoding="utf-8")
    return rollout_path


def user_item(message: str) -> RolloutItem:
    return RolloutItem.event_msg(EventMsg.with_payload("user_message", UserMessageEvent(message=message)))


def state_metadata(
    thread: ThreadId,
    rollout_path: Path,
    *,
    git_sha: str | None = None,
    git_branch: str | None = None,
    git_origin_url: str | None = None,
    archived: bool = False,
) -> object:
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
    metadata.git_sha = git_sha
    metadata.git_branch = git_branch
    metadata.git_origin_url = git_origin_url
    if archived:
        metadata.archived_at = metadata.updated_at
    return metadata


def test_update_thread_metadata_sets_name_on_active_rollout_and_indexes_name(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::update_thread_metadata_sets_name_on_active_rollout_and_indexes_name
    # Contract: explicit name patches update returned thread metadata and append the local thread-name index entry.
    async def run() -> None:
        local_store = store(tmp_path)
        thread = thread_id()
        await local_store.create_thread(create_params(thread, tmp_path))
        await local_store.persist_thread(thread)

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(name="A sharper name"),
                include_archived=False,
            )
        )

        assert stored.name == "A sharper name"
        assert find_thread_name_by_id(tmp_path / "codex-home", thread) == "A sharper name"

    asyncio.run(run())


def test_update_thread_metadata_sets_memory_mode_on_active_rollout(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::update_thread_metadata_sets_memory_mode_on_active_rollout
    # Contract: memory-mode patches append a new session_meta marker for the same thread with memory_mode disabled.
    async def run() -> None:
        local_store = store(tmp_path)
        thread = thread_id("000000000302")
        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(memory_mode=ThreadMemoryMode.DISABLED),
                include_archived=False,
            )
        )

        appended = last_rollout_item(rollout_path)
        assert stored.thread_id == thread
        assert appended["type"] == "session_meta"
        assert appended["payload"]["id"] == str(thread)
        assert appended["payload"]["memory_mode"] == "disabled"

    asyncio.run(run())


def test_metadata_patch_applies_title_over_existing_name(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::metadata_patch_applies_title_over_existing_name
    # Contract: observed title metadata can replace an earlier explicit thread name on returned thread summaries.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000308")
        await local_store.create_thread(create_params(thread, tmp_path))
        await local_store.append_items(AppendThreadItemsParams(thread, (user_item("Hello from user"),)))
        await local_store.persist_thread(thread)

        await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(name="User chosen name"),
                include_archived=False,
            )
        )

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(title="Derived first message", preview="Derived first message"),
                include_archived=False,
            )
        )

        assert stored.name == "Derived first message"
        assert stored.preview == "Hello from user"

    asyncio.run(run())


def test_metadata_patch_applies_latest_preview_and_first_user_message(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::metadata_patch_applies_latest_preview_and_first_user_message
    # Contract: observed preview/first_user_message updates latest state metadata while returned summary keeps rollout preview.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000309")
        await local_store.create_thread(create_params(thread, tmp_path))
        await local_store.append_items(AppendThreadItemsParams(thread, (user_item("Hello from user"),)))
        await local_store.persist_thread(thread)

        await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(
                    preview="Original preview",
                    first_user_message="Original first message",
                ),
                include_archived=False,
            )
        )

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(
                    preview="Later preview",
                    first_user_message="Later first message",
                ),
                include_archived=False,
            )
        )

        metadata = await state_db.get_thread(thread)
        assert stored.preview == "Hello from user"
        assert stored.first_user_message == "Hello from user"
        assert metadata.preview == "Later preview"
        assert metadata.first_user_message == "Later first message"

    asyncio.run(run())


def test_observed_metadata_normalizes_cwd_for_list_filters(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::observed_metadata_normalizes_cwd_for_list_filters
    # Contract: observed cwd is normalized in state metadata and state-db-only cwd filters match the normalized path.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000310")
        await local_store.create_thread(create_params(thread, tmp_path))
        await local_store.append_items(AppendThreadItemsParams(thread, (user_item("Hello from user"),)))
        await local_store.persist_thread(thread)
        workspace = tmp_path / "workspace"
        child = workspace / "child"
        child.mkdir(parents=True)
        unnormalized_cwd = child / ".."
        normalized_cwd = workspace.resolve(strict=False)

        await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(cwd=unnormalized_cwd, preview="cwd preview"),
                include_archived=False,
            )
        )

        metadata = await state_db.get_thread(thread)
        page = await local_store.list_threads(
            ListThreadsParams(
                page_size=10,
                cursor=None,
                sort_key=ThreadSortKey.UPDATED_AT,
                sort_direction=SortDirection.DESC,
                allowed_sources=(),
                model_providers=(),
                cwd_filters=(workspace,),
                archived=False,
                search_term=None,
                use_state_db_only=True,
            )
        )
        assert metadata.cwd == normalized_cwd
        assert [item.thread_id for item in page.items] == [thread]

    asyncio.run(run())


def test_observed_metadata_updates_remaining_state_fields(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/source: src/local/update_thread_metadata.rs::apply_metadata_update
    # Contract: observed metadata patches update state-row provider/model/reasoning/source/agent/policy/token fields.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000318")
        await local_store.create_thread(create_params(thread, tmp_path))
        await local_store.append_items(AppendThreadItemsParams(thread, (user_item("Hello from user"),)))
        await local_store.persist_thread(thread)
        created_at = datetime(2025, 1, 3, 13, 0, 0, tzinfo=timezone.utc)
        updated_at = datetime(2025, 1, 3, 14, 0, 0, tzinfo=timezone.utc)

        await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(
                    model_provider="observed-provider",
                    model="gpt-observed",
                    reasoning_effort=ReasoningEffort.HIGH,
                    created_at=created_at,
                    updated_at=updated_at,
                    source=SessionSource.exec(),
                    thread_source=ThreadSource.SUBAGENT,
                    agent_nickname="navigator",
                    agent_role="reviewer",
                    agent_path="agents/reviewer.md",
                    cli_version="9.9.9",
                    approval_mode=AskForApproval.ON_REQUEST,
                    sandbox_policy=SandboxPolicy.workspace_write(network_access=True),
                    token_usage=TokenUsage(-7),
                ),
                include_archived=False,
            )
        )

        metadata = await state_db.get_thread(thread)
        assert metadata.model_provider == "observed-provider"
        assert metadata.model == "gpt-observed"
        assert metadata.reasoning_effort == ReasoningEffort.HIGH
        assert metadata.created_at == created_at
        assert metadata.updated_at == updated_at
        assert metadata.source == "exec"
        assert metadata.thread_source == ThreadSource.SUBAGENT
        assert metadata.agent_nickname == "navigator"
        assert metadata.agent_role == "reviewer"
        assert metadata.agent_path == "agents/reviewer.md"
        assert metadata.cli_version == "9.9.9"
        assert metadata.approval_mode == "on-request"
        assert metadata.sandbox_policy == "workspace-write"
        assert metadata.tokens_used == 0

    asyncio.run(run())


def test_update_thread_metadata_recreates_missing_archived_state_row_as_archived(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::update_thread_metadata_recreates_missing_archived_sqlite_row_as_archived
    # Contract: updating archived rollout metadata without an existing state row recreates the row as archived.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000315")
        write_session_file(tmp_path / "codex-home", thread, archived=True, timestamp="2025-01-03T19-30-00")

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(preview="Archived missing state row"),
                include_archived=True,
            )
        )

        metadata = await state_db.get_thread(thread)
        assert stored.archived_at is not None
        assert metadata.archived_at is not None
        assert metadata.preview == "Archived missing state row"

    asyncio.run(run())


def test_update_thread_metadata_keeps_archived_thread_archived_in_state_db(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::update_thread_metadata_keeps_archived_thread_archived_in_sqlite
    # Contract: explicit metadata updates preserve archived_at for an already archived state row and returned summary.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000316")
        rollout_path = write_session_file(
            tmp_path / "codex-home",
            thread,
            archived=True,
            timestamp="2025-01-03T16-00-00",
        )
        state_db.upsert_thread(state_metadata(thread, rollout_path, archived=True))

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(name="Archived title"),
                include_archived=True,
            )
        )

        metadata = await state_db.get_thread(thread)
        assert stored.archived_at is not None
        assert stored.name == "Archived title"
        assert metadata.archived_at is not None
        assert metadata.title == "Archived title"

    asyncio.run(run())


def test_update_thread_metadata_keeps_live_archived_thread_archived_in_state_db(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::update_thread_metadata_keeps_live_archived_thread_archived_in_sqlite
    # Contract: name updates on a resumed archived live thread preserve archived_at in state metadata and returned summary.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000317")
        codex_home = tmp_path / "codex-home"
        rollout_path = write_session_file(
            codex_home,
            thread,
            archived=True,
            timestamp="2025-01-03T16-30-00",
        )
        state_db.upsert_thread(state_metadata(thread, rollout_path, archived=True))

        await local_store.resume_thread(
            ResumeThreadParams(
                thread_id=thread,
                rollout_path=rollout_path,
                history=None,
                include_archived=True,
                metadata=ThreadPersistenceMetadata(
                    cwd=tmp_path,
                    model_provider="test-provider",
                    memory_mode=ThreadMemoryMode.ENABLED,
                ),
                event_persistence_mode=ThreadEventPersistenceMode.LIMITED,
            )
        )

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(name="Live archived title"),
                include_archived=True,
            )
        )

        metadata = await state_db.get_thread(thread)
        assert stored.archived_at is not None
        assert stored.name == "Live archived title"
        assert metadata.archived_at is not None
        assert metadata.title == "Live archived title"

    asyncio.run(run())


def test_update_thread_metadata_sets_git_info_on_active_rollout_and_state_db(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::update_thread_metadata_applies_combined_explicit_patch
    # Contract: explicit git patches resolve unspecified fields from SQLite, append git session_meta, and update state DB.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000306")
        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)
        state_db.upsert_thread(
            state_metadata(
                thread,
                rollout_path,
                git_sha="a" * 40,
                git_branch="main",
                git_origin_url="https://example.invalid/repo.git",
            )
        )
        state_db.memory_modes[str(thread)] = "disabled"

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(git_info=GitInfoPatch(branch="feature")),
                include_archived=False,
            )
        )

        appended = last_rollout_item(rollout_path)
        metadata = await state_db.get_thread(thread)
        assert stored.git_info.sha == "a" * 40
        assert stored.git_info.branch == "feature"
        assert stored.git_info.origin_url == "https://example.invalid/repo.git"
        assert appended["type"] == "session_meta"
        assert appended["payload"]["memory_mode"] == "disabled"
        assert appended["payload"]["git"]["commit_hash"] == "a" * 40
        assert appended["payload"]["git"]["branch"] == "feature"
        assert appended["payload"]["git"]["repository_url"] == "https://example.invalid/repo.git"
        assert metadata.git_sha == "a" * 40
        assert metadata.git_branch == "feature"
        assert metadata.git_origin_url == "https://example.invalid/repo.git"

    asyncio.run(run())


def test_update_thread_metadata_clears_git_origin_url(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/source: src/local/update_thread_metadata.rs::resolve_git_info_patch
    # Contract: clearable git fields resolve to None while unspecified fields preserve existing SQLite values.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000307")
        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)
        state_db.upsert_thread(
            state_metadata(
                thread,
                rollout_path,
                git_sha="b" * 40,
                git_branch="main",
                git_origin_url="https://example.invalid/repo.git",
            )
        )

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(git_info=GitInfoPatch(origin_url=clear_field())),
                include_archived=False,
            )
        )

        appended = last_rollout_item(rollout_path)
        metadata = await state_db.get_thread(thread)
        assert stored.git_info.sha == "b" * 40
        assert stored.git_info.branch == "main"
        assert stored.git_info.origin_url is None
        assert appended["payload"]["git"]["commit_hash"] == "b" * 40
        assert appended["payload"]["git"]["branch"] == "main"
        assert "repository_url" not in appended["payload"]["git"]
        assert metadata.git_sha == "b" * 40
        assert metadata.git_branch == "main"
        assert metadata.git_origin_url is None

    asyncio.run(run())


def test_update_thread_metadata_partial_git_rebuilds_missing_state_row(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::update_thread_metadata_clears_git_info_fields
    # Contract: after SQLite metadata disappears, a partial git patch rebuilds state metadata from rollout and applies the patch.
    async def run() -> None:
        state_db = FakeStateDb()
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000322")
        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)

        state_db.threads.pop(str(thread), None)
        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(git_info=GitInfoPatch(branch="feature")),
                include_archived=False,
            )
        )

        appended = last_rollout_item(rollout_path)
        metadata = await state_db.get_thread(thread)
        assert stored.git_info.sha is None
        assert stored.git_info.branch == "feature"
        assert stored.git_info.origin_url is None
        assert appended["type"] == "session_meta"
        assert "commit_hash" not in appended["payload"]["git"]
        assert appended["payload"]["git"]["branch"] == "feature"
        assert "repository_url" not in appended["payload"]["git"]
        assert metadata is not None
        assert metadata.git_sha is None
        assert metadata.git_branch == "feature"
        assert metadata.git_origin_url is None

    asyncio.run(run())


def test_update_thread_metadata_applies_combined_explicit_patch(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::update_thread_metadata_applies_combined_explicit_patch
    # Contract: name and memory-mode compatibility updates can be applied in one explicit patch.
    async def run() -> None:
        local_store = store(tmp_path)
        thread = thread_id("000000000305")
        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(
                    name="Combined metadata",
                    memory_mode=ThreadMemoryMode.DISABLED,
                ),
                include_archived=False,
            )
        )

        appended = last_rollout_item(rollout_path)
        assert stored.name == "Combined metadata"
        assert find_thread_name_by_id(tmp_path / "codex-home", thread) == "Combined metadata"
        assert appended["type"] == "session_meta"
        assert appended["payload"]["memory_mode"] == "disabled"

    asyncio.run(run())


def test_sqlite_failures_are_best_effort_for_legacy_rollout_compat_updates(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::sqlite_failures_are_best_effort_for_legacy_rollout_compat_updates
    # Contract: internal state-db failures during legacy name updates do not block rollout compatibility updates.
    async def run() -> None:
        state_db = FailingStateDb(fail_title=True)
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000319")
        await local_store.create_thread(create_params(thread, tmp_path))
        await local_store.persist_thread(thread)

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(name="Best effort name"),
                include_archived=False,
            )
        )

        assert stored.name == "Best effort name"
        assert find_thread_name_by_id(tmp_path / "codex-home", thread) == "Best effort name"

    asyncio.run(run())


def test_sqlite_failures_are_best_effort_for_observed_metadata_updates(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::sqlite_failures_are_best_effort_for_observed_metadata_updates
    # Contract: internal state-db failures during observed metadata updates do not block rollout summary reads.
    async def run() -> None:
        state_db = FailingStateDb(fail_upsert=True)
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000320")
        write_session_file(tmp_path / "codex-home", thread, message="Hello from user")

        stored = await local_store.update_thread_metadata(
            UpdateThreadMetadataParams(
                thread_id=thread,
                patch=ThreadMetadataPatch(preview="Observed preview", memory_mode=ThreadMemoryMode.ENABLED),
                include_archived=False,
            )
        )

        assert stored.thread_id == thread
        assert stored.preview == "Hello from user"

    asyncio.run(run())


def test_sqlite_failures_still_block_for_explicit_git_only_updates(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/update_thread_metadata.rs::sqlite_failures_still_block_for_explicit_git_only_updates
    # Contract: explicit git-only updates still require state DB because omitted git fields merge from SQLite metadata.
    async def run() -> None:
        state_db = FailingStateDb(fail_git=True)
        local_store = store(tmp_path, state_db)
        thread = thread_id("000000000321")
        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)
        state_db.upsert_thread(state_metadata(thread, rollout_path, git_branch="main"))

        with pytest.raises(ThreadStoreError) as err:
            await local_store.update_thread_metadata(
                UpdateThreadMetadataParams(
                    thread_id=thread,
                    patch=ThreadMetadataPatch(git_info=GitInfoPatch(branch="feature")),
                    include_archived=False,
                )
            )

        assert err.value.kind == "internal"
        assert "failed to update git metadata" in str(err.value)

    asyncio.run(run())
