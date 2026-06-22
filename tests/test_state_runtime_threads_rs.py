import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pycodex.protocol import SessionSource, SubAgentSource, ThreadId
from pycodex.state.model import (
    Anchor,
    DirectionalThreadSpawnEdgeStatus,
    SortDirection,
    SortKey,
    ThreadMetadata,
    ThreadMetadataBuilder,
    datetime_to_epoch_millis,
)
from pycodex.state.runtime.threads import (
    RuntimeThreadStore,
    ThreadFilterOptions,
    UNSET_GIT_FIELD,
    extract_memory_mode,
    metadata_preview,
    thread_spawn_parent_thread_id_from_source_str,
)


def _run(coro):
    return asyncio.run(coro)


def _thread_id(value: int) -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{value:012d}")


def _dt(seconds: int, millis: int = 0) -> datetime:
    return datetime.fromtimestamp(seconds + millis / 1000, tz=timezone.utc)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            rollout_path TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            created_at_ms INTEGER,
            updated_at_ms INTEGER,
            source TEXT NOT NULL,
            thread_source TEXT,
            agent_nickname TEXT,
            agent_role TEXT,
            agent_path TEXT,
            model_provider TEXT NOT NULL,
            model TEXT,
            reasoning_effort TEXT,
            cwd TEXT NOT NULL,
            cli_version TEXT NOT NULL,
            title TEXT NOT NULL,
            preview TEXT NOT NULL,
            sandbox_policy TEXT NOT NULL,
            approval_mode TEXT NOT NULL,
            tokens_used INTEGER NOT NULL,
            first_user_message TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            archived_at INTEGER,
            git_sha TEXT,
            git_branch TEXT,
            git_origin_url TEXT,
            memory_mode TEXT NOT NULL DEFAULT 'enabled'
        );

        CREATE TABLE thread_spawn_edges (
            parent_thread_id TEXT NOT NULL,
            child_thread_id TEXT PRIMARY KEY,
            status TEXT NOT NULL
        );
        """
    )
    return connection


def _metadata(
    value: int,
    *,
    created: int = 1_700_000_000,
    updated: int | None = None,
    source: str = "cli",
    model_provider: str = "test-provider",
    cwd: Path | str | None = None,
    title: str | None = None,
    preview: str | None = None,
    first_user_message: str | None = "first user message",
    archived_at: datetime | None = None,
    git_sha: str | None = None,
    git_branch: str | None = None,
    git_origin_url: str | None = None,
    agent_path: str | None = None,
) -> ThreadMetadata:
    thread_id = _thread_id(value)
    return ThreadMetadata(
        id=thread_id,
        rollout_path=Path("rollouts") / f"{thread_id}.jsonl",
        created_at=_dt(created),
        updated_at=_dt(updated if updated is not None else created),
        source=source,
        thread_source=None,
        agent_nickname=None,
        agent_role=None,
        agent_path=agent_path,
        model_provider=model_provider,
        model="gpt-test",
        reasoning_effort=None,
        cwd=Path(cwd) if cwd is not None else Path.cwd(),
        cli_version="pycodex-test",
        title=title if title is not None else f"title-{value}",
        preview=preview,
        sandbox_policy="workspace-write",
        approval_mode="on-request",
        tokens_used=10 + value,
        first_user_message=first_user_message,
        archived_at=archived_at,
        git_sha=git_sha,
        git_branch=git_branch,
        git_origin_url=git_origin_url,
    )


def test_upsert_preserves_creation_memory_mode_preview_and_existing_git_fields():
    # Rust: upsert_thread_keeps_creation_memory_mode_for_existing_rows and
    # upsert_thread_preserves_existing_preview_when_incoming_preview_is_empty.
    connection = _connect()
    store = RuntimeThreadStore(connection)
    thread_id = _thread_id(1)
    original = _metadata(
        1,
        preview="persisted preview",
        git_sha="sha-old",
        git_branch="main",
        git_origin_url="https://example.invalid/repo",
    )

    _run(store.upsert_thread_with_creation_memory_mode(original, "disabled"))
    assert _run(store.get_thread_memory_mode(thread_id)) == "disabled"

    incoming = _metadata(
        1,
        updated=1_700_000_100,
        title="updated title",
        preview=None,
        first_user_message=None,
        git_sha="sha-new",
        git_branch="feature",
        git_origin_url="https://example.invalid/new",
    )
    _run(store.upsert_thread(incoming))

    persisted = _run(store.get_thread(thread_id))
    assert persisted is not None
    assert persisted.title == "updated title"
    assert persisted.preview == "persisted preview"
    assert persisted.git_sha == "sha-old"
    assert persisted.git_branch == "main"
    assert persisted.git_origin_url == "https://example.invalid/repo"
    assert _run(store.get_thread_memory_mode(thread_id)) == "disabled"


def test_insert_if_absent_update_title_preview_git_and_touch_updated_at():
    # Rust: insert_thread_if_absent_preserves_existing_metadata,
    # set_thread_preview_if_empty_only_fills_blank_preview, update_thread_git_info_can_clear_fields,
    # and touch_thread_updated_at_updates_only_updated_at.
    connection = _connect()
    store = RuntimeThreadStore(connection)
    thread_id = _thread_id(2)
    blank = _metadata(2, title="initial", preview=None, first_user_message=None, git_sha="sha", git_branch="main", git_origin_url="origin")

    assert _run(store.insert_thread_if_absent(blank)) is True
    assert _run(store.insert_thread_if_absent(_metadata(2, title="ignored", preview="ignored"))) is False
    assert _run(store.set_thread_preview_if_empty(thread_id, "filled preview")) is True
    assert _run(store.set_thread_preview_if_empty(thread_id, "second preview")) is False
    assert _run(store.update_thread_title(thread_id, "renamed")) is True
    assert _run(store.update_thread_git_info(thread_id, git_sha=None, git_branch=None, git_origin_url=UNSET_GIT_FIELD)) is True
    touched_at = _dt(1_700_001_111)
    assert _run(store.touch_thread_updated_at(thread_id, touched_at)) is True

    persisted = _run(store.get_thread(thread_id))
    assert persisted is not None
    assert persisted.title == "renamed"
    assert persisted.preview == "filled preview"
    assert persisted.git_sha is None
    assert persisted.git_branch is None
    assert persisted.git_origin_url == "origin"
    assert persisted.updated_at == touched_at
    assert persisted.first_user_message is None


def test_allocate_thread_updated_at_unique_millis_and_legacy_seconds_read():
    # Rust: thread_updated_at_uses_unique_epoch_millis_and_reads_legacy_seconds.
    connection = _connect()
    store = RuntimeThreadStore(connection)
    first = _metadata(3, updated=1_700_001_111)
    first.updated_at = _dt(1_700_001_111, 123)
    second = _metadata(4, updated=1_700_001_111)
    second.updated_at = _dt(1_700_001_111, 123)

    _run(store.upsert_thread(first))
    _run(store.upsert_thread(second))
    persisted_first = _run(store.get_thread(first.id))
    persisted_second = _run(store.get_thread(second.id))
    assert datetime_to_epoch_millis(persisted_first.updated_at) == 1_700_001_111_123
    assert datetime_to_epoch_millis(persisted_second.updated_at) == 1_700_001_111_124

    connection.execute("UPDATE threads SET updated_at_ms = NULL, updated_at = ? WHERE id = ?", (1_700_001_112, str(first.id)))
    connection.commit()
    legacy = _run(store.get_thread(first.id))
    assert datetime_to_epoch_millis(legacy.updated_at) == 1_700_001_112_000


def test_list_threads_filters_search_sort_anchor_and_exact_title_lookup():
    # Rust: list_threads/list_thread_ids apply visible filters, search, CWD/provider/source filters, and anchor pagination.
    connection = _connect()
    store = RuntimeThreadStore(connection)
    cwd_a = Path("workspace-a")
    cwd_b = Path("workspace-b")
    _run(store.upsert_thread(_metadata(5, updated=1_700_000_005, title="alpha task", preview="visible alpha", cwd=cwd_a, source="cli", model_provider="provider-a")))
    _run(store.upsert_thread(_metadata(6, updated=1_700_000_006, title="beta task", preview="visible beta", cwd=cwd_b, source="exec", model_provider="provider-a")))
    _run(store.upsert_thread(_metadata(7, updated=1_700_000_007, title="gamma task", preview="", first_user_message=None, cwd=cwd_a, source="cli", model_provider="provider-b")))
    _run(store.upsert_thread(_metadata(8, updated=1_700_000_008, title="archived task", preview="archived", cwd=cwd_a, archived_at=_dt(1_700_000_010))))

    page = _run(
        store.list_threads(
            1,
            ThreadFilterOptions(
                allowed_sources=("cli",),
                model_providers=("provider-a",),
                cwd_filters=(cwd_a,),
                search_term="alpha",
                sort_key=SortKey.UPDATED_AT,
                sort_direction=SortDirection.DESC,
            ),
        )
    )
    assert [item.id for item in page.items] == [_thread_id(5)]
    assert page.next_anchor is None

    desc_page = _run(store.list_threads(1, ThreadFilterOptions(sort_key=SortKey.UPDATED_AT, sort_direction=SortDirection.DESC)))
    assert [item.id for item in desc_page.items] == [_thread_id(6)]
    assert desc_page.next_anchor is not None
    ids_after_anchor = _run(store.list_thread_ids(10, anchor=desc_page.next_anchor, sort_key=SortKey.UPDATED_AT))
    assert ids_after_anchor == [_thread_id(5)]

    found = _run(store.find_thread_by_exact_title("beta task", allowed_sources=("exec",), model_providers=("provider-a",), cwd=cwd_b))
    assert found is not None and found.id == _thread_id(6)
    archived = _run(store.find_rollout_path_by_id(_thread_id(8), archived_only=True))
    assert archived == Path("rollouts") / f"{_thread_id(8)}.jsonl"


def test_spawn_edges_track_status_descendants_source_parsing_and_duplicate_path_errors():
    # Rust: thread_spawn_edges_track_directional_status and child/descendant path lookup helpers.
    connection = _connect()
    store = RuntimeThreadStore(connection)
    parent = _thread_id(9)
    child = _thread_id(10)
    grandchild = _thread_id(11)
    duplicate = _thread_id(12)
    _run(store.upsert_thread(_metadata(9, agent_path="root")))
    _run(store.upsert_thread(_metadata(10, agent_path="agent/a")))
    _run(store.upsert_thread(_metadata(11, agent_path="agent/b")))
    _run(store.upsert_thread(_metadata(12, agent_path="agent/b")))

    _run(store.upsert_thread_spawn_edge(parent, child, DirectionalThreadSpawnEdgeStatus.OPEN))
    _run(store.upsert_thread_spawn_edge(child, grandchild, DirectionalThreadSpawnEdgeStatus.OPEN))
    assert _run(store.list_thread_spawn_children(parent)) == [child]
    assert _run(store.list_thread_spawn_descendants(parent)) == [child, grandchild]
    assert _run(store.set_thread_spawn_edge_status(child, DirectionalThreadSpawnEdgeStatus.CLOSED)) is True
    assert _run(store.list_thread_spawn_children(parent, DirectionalThreadSpawnEdgeStatus.OPEN)) == []
    assert _run(store.list_thread_spawn_children(parent, DirectionalThreadSpawnEdgeStatus.CLOSED)) == [child]
    assert _run(store.find_thread_spawn_child_by_path(parent, "agent/a")) == child
    assert _run(store.find_thread_spawn_descendant_by_path(parent, "agent/b")) == grandchild

    _run(store.upsert_thread_spawn_edge(parent, duplicate, DirectionalThreadSpawnEdgeStatus.OPEN))
    with pytest.raises(ValueError, match="multiple agents found"):
        _run(store.find_thread_spawn_descendant_by_path(parent, "agent/b"))

    source = str(SubAgentSource.thread_spawn(parent, 2))
    assert thread_spawn_parent_thread_id_from_source_str(source) == parent
    assert _run(store.insert_thread_spawn_edge_from_source_if_absent(_thread_id(13), source)) is True
    assert _run(store.insert_thread_spawn_edge_from_source_if_absent(_thread_id(13), source)) is False
    assert _run(store.insert_thread_spawn_edge_from_source_if_absent(_thread_id(14), "cli")) is False


def test_apply_rollout_items_restores_memory_mode_and_preserves_existing_git_fields():
    # Rust: apply_rollout_items_restores_memory_mode_from_session_meta and preserves existing git fields.
    connection = _connect()
    store = RuntimeThreadStore(connection, default_provider="fallback-provider")
    thread = _thread_id(15)
    existing = _metadata(15, title="", preview=None, first_user_message=None, git_branch="existing-branch", git_sha="existing-sha")
    _run(store.upsert_thread(existing))
    builder = ThreadMetadataBuilder.new(thread, "rollouts/15.jsonl", _dt(1_700_000_015), SessionSource.cli())
    override_updated_at = _dt(1_700_001_234)
    items = [
        {
            "type": "session_meta",
            "payload": {
                "meta": {
                    "id": thread,
                    "source": SessionSource.cli(),
                    "memory_mode": "disabled",
                    "model_provider": "provider-from-meta",
                    "cli_version": "codex-rs-test",
                    "cwd": str(Path("workspace-meta")),
                },
                "git": {
                    "commit_hash": "new-sha",
                    "branch": "new-branch",
                    "repository_url": "https://example.invalid/new",
                },
            },
        },
        {"type": "event_msg", "payload": {"type": "user_message", "message": "hello from rollout"}},
    ]

    assert extract_memory_mode(items) == "disabled"
    _run(store.apply_rollout_items(builder, items, updated_at_override=override_updated_at))

    persisted = _run(store.get_thread(thread))
    assert persisted is not None
    assert persisted.updated_at == override_updated_at
    assert persisted.title == "hello from rollout"
    assert persisted.preview == "hello from rollout"
    assert persisted.git_branch == "existing-branch"
    assert persisted.git_sha == "existing-sha"
    assert persisted.git_origin_url == "https://example.invalid/new"
    assert _run(store.get_thread_memory_mode(thread)) == "disabled"


def test_archive_unarchive_delete_hooks_and_preview_fallback():
    # Rust: archive/unarchive mutate archive flags; delete_thread removes row and runs dependent cleanup hooks.
    connection = _connect()
    memory_deleted: list[ThreadId] = []
    goal_deleted: list[ThreadId] = []

    class Memories:
        async def delete_thread_memory(self, thread_id: ThreadId) -> None:
            memory_deleted.append(thread_id)

    class Goals:
        def delete_thread_goal(self, thread_id: ThreadId) -> None:
            goal_deleted.append(thread_id)

    store = RuntimeThreadStore(connection, memories=Memories(), thread_goals=Goals())
    thread = _thread_id(16)
    metadata = _metadata(16, preview=None, first_user_message="fallback preview")
    assert metadata_preview(metadata) == "fallback preview"
    _run(store.upsert_thread(metadata))

    _run(store.mark_archived(thread, "archive/16.jsonl", _dt(1_700_000_500)))
    assert _run(store.find_rollout_path_by_id(thread, archived_only=True)) == Path("archive/16.jsonl")
    _run(store.mark_unarchived(thread, "rollouts/16.jsonl"))
    assert _run(store.find_rollout_path_by_id(thread, archived_only=False)) == Path("rollouts/16.jsonl")

    assert _run(store.delete_thread(thread)) == 1
    assert _run(store.delete_thread(thread)) == 0
    assert memory_deleted == [thread]
    assert goal_deleted == [thread]
