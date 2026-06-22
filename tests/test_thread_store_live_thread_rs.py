from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.protocol import (
    EventMsg,
    RolloutItem,
    SessionMeta,
    SessionMetaLine,
    SessionSource,
    ThreadId,
    ThreadMemoryMode,
    UserMessageEvent,
)
from pycodex.thread_store import (
    AppendThreadItemsParams,
    CreateThreadParams,
    InMemoryThreadStore,
    LiveThread,
    ReadThreadParams,
    ResumeThreadParams,
    ThreadEventPersistenceMode,
    ThreadMetadataPatch,
    ThreadPersistenceMetadata,
    ThreadSource,
)


def thread_id(hex_tail: str) -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{hex_tail}")


def metadata(*, provider: str = "test-provider", cwd: Path | None = None) -> ThreadPersistenceMetadata:
    return ThreadPersistenceMetadata(cwd=cwd, model_provider=provider, memory_mode=ThreadMemoryMode.ENABLED)


def create_params(thread: ThreadId, *, provider: str = "test-provider", cwd: Path | None = None) -> CreateThreadParams:
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


def resume_params(
    thread: ThreadId,
    *,
    history: tuple[RolloutItem, ...] | None,
    provider: str = "different-provider",
) -> ResumeThreadParams:
    return ResumeThreadParams(
        thread_id=thread,
        rollout_path=None,
        history=history,
        include_archived=False,
        metadata=metadata(provider=provider),
        event_persistence_mode=ThreadEventPersistenceMode.LIMITED,
    )


def user_item(message: str) -> RolloutItem:
    return RolloutItem.event_msg(EventMsg.with_payload("user_message", UserMessageEvent(message=message)))


def warning_item(message: str) -> RolloutItem:
    return RolloutItem.event_msg(EventMsg.with_payload("warning", {"message": message}))


def session_meta(thread: ThreadId, *, timestamp: str = "2025-01-03T17:00:00Z") -> RolloutItem:
    return RolloutItem.session_meta(
        SessionMetaLine(
            meta=SessionMeta(
                id=thread,
                timestamp=timestamp,
                cwd=Path(),
                originator="",
                cli_version="",
                source=SessionSource.exec(),
                model_provider="test-provider",
            ),
            git=None,
        )
    )


def test_live_thread_observes_appended_items_into_store_metadata() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/live_thread.rs plus src/local/mod.rs::live_thread_observes_appended_items_into_sqlite_metadata
    # Contract: LiveThread appends persisted rollout items, observes metadata, applies the pending patch, and flushes.
    async def run() -> None:
        store = InMemoryThreadStore()
        thread = thread_id("000000000101")
        live_thread = await LiveThread.create(store, create_params(thread))

        await live_thread.append_items([user_item("observed append")])
        await live_thread.flush()

        stored = await store.read_thread(ReadThreadParams(thread, include_archived=True, include_history=True))
        calls = await store.calls()
        assert stored.first_user_message == "observed append"
        assert stored.preview == "observed append"
        assert stored.name is None
        assert stored.history is not None
        assert len(stored.history.items) == 1
        assert calls.create_thread == 1
        assert calls.append_items == 1
        assert calls.update_thread_metadata == 1
        assert calls.flush_thread == 1

    asyncio.run(run())


def test_live_thread_skips_non_persisted_append_items() -> None:
    # Rust crate: codex-thread-store
    # Rust module/source: src/live_thread.rs::append_items
    # Contract: empty canonical `persisted_rollout_items` output returns without appending or updating metadata.
    async def run() -> None:
        store = InMemoryThreadStore()
        thread = thread_id("000000000102")
        live_thread = await LiveThread.create(store, create_params(thread))

        await live_thread.append_items([warning_item("not persisted")])

        stored = await store.read_thread(ReadThreadParams(thread, include_archived=True, include_history=True))
        calls = await store.calls()
        assert stored.history is not None
        assert stored.history.items == ()
        assert calls.append_items == 0
        assert calls.update_thread_metadata == 0

    asyncio.run(run())


def test_live_thread_resume_loads_history_before_observing_metadata() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/live_thread.rs plus src/local/mod.rs::live_thread_resume_loads_history_before_observing_metadata
    # Contract: resume with no history loads store history before metadata sync, so old session facts win over resume params and later appends.
    async def run() -> None:
        store = InMemoryThreadStore()
        thread = thread_id("000000000103")
        await store.create_thread(create_params(thread))
        await store.append_items(
            AppendThreadItemsParams(
                thread_id=thread,
                items=(session_meta(thread), user_item("Hello from user")),
            )
        )

        live_thread = await LiveThread.resume(store, resume_params(thread, history=None))
        await live_thread.append_items([user_item("new live append")])

        stored = await store.read_thread(ReadThreadParams(thread, include_archived=True, include_history=False))
        assert stored.created_at.isoformat() == "2025-01-03T17:00:00+00:00"
        assert stored.model_provider == "test-provider"
        assert stored.first_user_message == "Hello from user"
        assert stored.preview == "Hello from user"

    asyncio.run(run())


def test_live_thread_update_metadata_flushes_pending_metadata_first() -> None:
    # Rust crate: codex-thread-store
    # Rust module/source: src/live_thread.rs::update_metadata
    # Contract: explicit metadata updates flush pending append/create metadata before applying the caller's patch.
    async def run() -> None:
        store = InMemoryThreadStore()
        thread = thread_id("000000000104")
        live_thread = await LiveThread.create(store, create_params(thread))

        stored = await live_thread.update_metadata(ThreadMetadataPatch(preview="manual preview"), include_archived=True)
        calls = await store.calls()

        assert stored.preview == "manual preview"
        assert stored.model_provider == "test-provider"
        assert calls.update_thread_metadata == 2

    asyncio.run(run())
