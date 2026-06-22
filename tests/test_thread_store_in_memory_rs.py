from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pycodex.protocol import AskForApproval, SandboxPolicy, SessionSource, ThreadId, ThreadMemoryMode, ThreadSource
from pycodex.thread_store import (
    AppendThreadItemsParams,
    ArchiveThreadParams,
    CreateThreadParams,
    InMemoryThreadStore,
    ListItemsParams,
    ListThreadsParams,
    ListTurnsParams,
    LoadThreadHistoryParams,
    ReadThreadByRolloutPathParams,
    ReadThreadParams,
    ResumeThreadParams,
    SortDirection,
    StoredTurnItemsView,
    ThreadEventPersistenceMode,
    ThreadMetadataPatch,
    ThreadPersistenceMetadata,
    ThreadSortKey,
    ThreadStoreError,
    UpdateThreadMetadataParams,
)


def thread_id(hex_tail: str) -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{hex_tail}")


def metadata(*, provider: str = "openai", cwd: Path | None = None) -> ThreadPersistenceMetadata:
    return ThreadPersistenceMetadata(cwd=cwd, model_provider=provider, memory_mode=ThreadMemoryMode.ENABLED)


def create_params(thread: ThreadId, *, provider: str = "openai", cwd: Path | None = None) -> CreateThreadParams:
    return CreateThreadParams(
        thread_id=thread,
        forked_from_id=None,
        source=SessionSource.exec(),
        thread_source=ThreadSource.USER,
        base_instructions=None,
        dynamic_tools=(),
        metadata=metadata(provider=provider, cwd=cwd),
        event_persistence_mode=ThreadEventPersistenceMode.LIMITED,
    )


def list_params() -> ListThreadsParams:
    return ListThreadsParams(
        page_size=20,
        cursor=None,
        sort_key=ThreadSortKey.CREATED_AT,
        sort_direction=SortDirection.DESC,
    )


def test_in_memory_default_turn_pagination_methods_return_unsupported() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/in_memory.rs::default_turn_pagination_methods_return_unsupported
    # Contract: in-memory stores do not implement turn/item pagination and return Unsupported with the Rust operation names.
    store = InMemoryThreadStore()
    tid = ThreadId.default()

    with pytest.raises(ThreadStoreError) as turns_err:
        asyncio.run(
            store.list_turns(
                ListTurnsParams(
                    thread_id=tid,
                    include_archived=True,
                    cursor=None,
                    page_size=10,
                    sort_direction=SortDirection.ASC,
                    items_view=StoredTurnItemsView.SUMMARY,
                )
            )
        )
    assert turns_err.value.kind == "unsupported"
    assert turns_err.value.fields["operation"] == "list_turns"

    with pytest.raises(ThreadStoreError) as items_err:
        asyncio.run(
            store.list_items(
                ListItemsParams(
                    thread_id=tid,
                    turn_id="turn_1",
                    include_archived=True,
                    cursor=None,
                    page_size=10,
                    sort_direction=SortDirection.ASC,
                )
            )
        )
    assert items_err.value.kind == "unsupported"
    assert items_err.value.fields["operation"] == "list_items"


def test_in_memory_for_id_remove_id_and_call_counts_are_shared() -> None:
    # Rust crate: codex-thread-store
    # Rust module/source: src/in_memory.rs::{for_id,remove_id,calls}
    # Contract: stores are globally shared by id until removed, and observed call counts are cloned from store state.
    InMemoryThreadStore.remove_id("shared")
    first = InMemoryThreadStore.for_id("shared")
    second = InMemoryThreadStore.for_id("shared")
    tid = thread_id("000000000001")

    asyncio.run(first.create_thread(create_params(tid)))
    asyncio.run(second.persist_thread(tid))

    assert first is second
    assert asyncio.run(first.calls()).create_thread == 1
    assert asyncio.run(second.calls()).persist_thread == 1
    assert InMemoryThreadStore.remove_id("shared") is first
    assert InMemoryThreadStore.for_id("shared") is not first
    InMemoryThreadStore.remove_id("shared")


def test_in_memory_resume_tracks_rollout_path_without_preloading_history() -> None:
    # Rust crate: codex-thread-store
    # Rust module/source: src/in_memory.rs::resume_thread/read_thread_by_rollout_path/load_history
    # Contract: resume initializes an empty history and records rollout_path lookup; the caller-provided history field is not imported.
    store = InMemoryThreadStore()
    tid = thread_id("000000000002")
    rollout_path = Path("rollouts/thread.jsonl")

    asyncio.run(
        store.resume_thread(
            ResumeThreadParams(
                thread_id=tid,
                rollout_path=rollout_path,
                history=("already-loaded",),
                include_archived=True,
                metadata=metadata(),
                event_persistence_mode=ThreadEventPersistenceMode.EXTENDED,
            )
        )
    )

    history = asyncio.run(store.load_history(LoadThreadHistoryParams(tid, include_archived=True)))
    assert history.items == ()

    with pytest.raises(ThreadStoreError) as read_err:
        asyncio.run(store.read_thread(ReadThreadParams(tid, include_archived=True, include_history=False)))
    assert read_err.value.kind == "thread_not_found"

    asyncio.run(store.create_thread(create_params(tid)))
    found = asyncio.run(
        store.read_thread_by_rollout_path(
            ReadThreadByRolloutPathParams(rollout_path, include_archived=True, include_history=True)
        )
    )
    assert found.thread_id == tid
    assert found.rollout_path == rollout_path
    assert found.history is not None
    assert found.history.items == ()


def test_in_memory_create_append_read_list_and_metadata_defaults_match_rust() -> None:
    # Rust crate: codex-thread-store
    # Rust module/source: src/in_memory.rs::create_thread/append_items/read_thread/list_threads/stored_thread_from_state
    # Contract: created threads get empty histories, appended items are replayed, list_threads sorts by thread_id string,
    # and unpatched StoredThread fields use Rust's test defaults instead of CreateThreadParams.metadata values.
    store = InMemoryThreadStore()
    later = thread_id("0000000000ff")
    earlier = thread_id("000000000001")

    asyncio.run(store.create_thread(create_params(later, provider="provider-from-create", cwd=Path("/ignored"))))
    asyncio.run(store.create_thread(create_params(earlier)))
    asyncio.run(store.append_items(AppendThreadItemsParams(later, ("item-1", "item-2"))))

    read = asyncio.run(store.read_thread(ReadThreadParams(later, include_archived=False, include_history=True)))
    assert read.history is not None
    assert read.history.items == ("item-1", "item-2")
    assert read.model_provider == "test"
    assert read.cwd == Path()
    assert read.cli_version == "test"
    assert read.approval_mode == AskForApproval.NEVER
    assert read.sandbox_policy == SandboxPolicy.new_read_only_policy()

    page = asyncio.run(store.list_threads(list_params()))
    assert [item.thread_id for item in page.items] == [earlier, later]
    assert page.next_cursor is None


def test_in_memory_metadata_patch_merges_and_archive_unarchive_call_paths() -> None:
    # Rust crate: codex-thread-store
    # Rust module/source: src/in_memory.rs::update_thread_metadata/archive_thread/unarchive_thread
    # Contract: metadata patches merge by field presence, archive is a call-count no-op, and unarchive returns the stored thread.
    store = InMemoryThreadStore()
    tid = thread_id("000000000003")
    asyncio.run(store.create_thread(create_params(tid)))

    first = ThreadMetadataPatch(preview="old preview", model_provider="anthropic", name="Old")
    second = ThreadMetadataPatch(model="gpt-test", preview=None, name="New")
    asyncio.run(store.update_thread_metadata(UpdateThreadMetadataParams(tid, first, include_archived=False)))
    updated = asyncio.run(store.update_thread_metadata(UpdateThreadMetadataParams(tid, second, include_archived=False)))

    assert updated.preview == "old preview"
    assert updated.name == "New"
    assert updated.model_provider == "anthropic"
    assert updated.model == "gpt-test"

    asyncio.run(store.archive_thread(ArchiveThreadParams(tid)))
    unarchived = asyncio.run(store.unarchive_thread(ArchiveThreadParams(tid)))
    assert unarchived.thread_id == tid

    calls = asyncio.run(store.calls())
    assert calls.update_thread_metadata == 2
    assert calls.archive_thread == 1
    assert calls.unarchive_thread == 1
