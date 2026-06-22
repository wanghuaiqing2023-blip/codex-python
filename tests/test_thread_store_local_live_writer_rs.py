from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pycodex.protocol import EventMsg, SessionSource, ThreadId, ThreadMemoryMode, ThreadSource, UserMessageEvent
from pycodex.thread_store import (
    AppendThreadItemsParams,
    CreateThreadParams,
    LocalThreadStore,
    LocalThreadStoreConfig,
    ResumeThreadParams,
    ThreadEventPersistenceMode,
    ThreadPersistenceMetadata,
    ThreadStoreError,
)


def thread_id(hex_tail: str = "000000000201") -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{hex_tail}")


def store(tmp_path: Path) -> LocalThreadStore:
    return LocalThreadStore(
        LocalThreadStoreConfig(
            codex_home=tmp_path / "codex-home",
            sqlite_home=tmp_path / "sqlite-home",
            default_model_provider_id="test-provider",
        )
    )


def metadata(tmp_path: Path | None, *, provider: str = "test-provider") -> ThreadPersistenceMetadata:
    return ThreadPersistenceMetadata(
        cwd=tmp_path,
        model_provider=provider,
        memory_mode=ThreadMemoryMode.ENABLED,
    )


def create_params(thread: ThreadId, tmp_path: Path | None) -> CreateThreadParams:
    return CreateThreadParams(
        thread_id=thread,
        forked_from_id=None,
        source=SessionSource.exec(),
        thread_source=ThreadSource.USER,
        base_instructions=None,
        dynamic_tools=(),
        metadata=metadata(tmp_path),
        event_persistence_mode=ThreadEventPersistenceMode.LIMITED,
    )


def user_item(message: str) -> dict[str, object]:
    return {
        "type": "event_msg",
        "payload": EventMsg.with_payload("user_message", UserMessageEvent(message=message)).to_mapping(),
    }


def rollout_contains_message(path: Path, expected: str) -> bool:
    text = path.read_text(encoding="utf-8")
    return any(expected in json.dumps(json.loads(line), ensure_ascii=False) for line in text.splitlines() if line)


def test_local_live_writer_lifecycle_writes_and_closes(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/mod.rs::live_writer_lifecycle_writes_and_closes
    # Contract: local create opens a live rollout writer; append/persist/flush write JSONL; shutdown removes the writer.
    async def run() -> None:
        local_store = store(tmp_path)
        thread = thread_id()

        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)

        await local_store.append_items(AppendThreadItemsParams(thread_id=thread, items=(user_item("first live write"),)))
        await local_store.persist_thread(thread)
        await local_store.flush_thread(thread)

        assert rollout_path.exists()
        assert rollout_contains_message(rollout_path, "first live write")

        await local_store.shutdown_thread(thread)
        with pytest.raises(ThreadStoreError) as err:
            await local_store.append_items(
                AppendThreadItemsParams(thread_id=thread, items=(user_item("write after shutdown"),))
            )
        assert err.value.kind == "thread_not_found"

    asyncio.run(run())


def test_local_create_thread_rejects_missing_cwd(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/mod.rs::create_thread_rejects_missing_cwd
    # Contract: local thread creation requires `metadata.cwd` and returns InvalidRequest with the Rust message.
    async def run() -> None:
        local_store = store(tmp_path)

        with pytest.raises(ThreadStoreError) as err:
            await local_store.create_thread(create_params(thread_id("000000000202"), None))

        assert err.value.kind == "invalid_request"
        assert err.value.fields["message"] == "local thread store requires a cwd"

    asyncio.run(run())


def test_local_discard_thread_drops_unmaterialized_live_writer(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/local/mod.rs::discard_thread_drops_unmaterialized_live_writer
    # Contract: discarding a never-materialized live writer removes it without creating the rollout file.
    async def run() -> None:
        local_store = store(tmp_path)
        thread = thread_id("000000000203")

        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)
        await local_store.discard_thread(thread)

        assert not rollout_path.exists()
        with pytest.raises(ThreadStoreError) as err:
            await local_store.append_items(
                AppendThreadItemsParams(thread_id=thread, items=(user_item("write after discard"),))
            )
        assert err.value.kind == "thread_not_found"

    asyncio.run(run())


def test_local_create_and_resume_reject_duplicate_live_writer(tmp_path: Path) -> None:
    # Rust crate: codex-thread-store
    # Rust module/tests: src/local/mod.rs::create_thread_rejects_duplicate_live_writer and resume_thread_rejects_duplicate_live_writer
    # Contract: local create/resume both reject a second live writer for the same thread id.
    async def run() -> None:
        local_store = store(tmp_path)
        thread = thread_id("000000000204")

        await local_store.create_thread(create_params(thread, tmp_path))
        rollout_path = await local_store.live_rollout_path(thread)

        with pytest.raises(ThreadStoreError) as create_err:
            await local_store.create_thread(create_params(thread, tmp_path))
        assert create_err.value.kind == "invalid_request"
        assert "already has a live local writer" in str(create_err.value)

        with pytest.raises(ThreadStoreError) as resume_err:
            await local_store.resume_thread(
                ResumeThreadParams(
                    thread_id=thread,
                    rollout_path=rollout_path,
                    history=None,
                    include_archived=True,
                    metadata=metadata(tmp_path),
                    event_persistence_mode=ThreadEventPersistenceMode.LIMITED,
                )
            )
        assert resume_err.value.kind == "invalid_request"
        assert "already has a live local writer" in str(resume_err.value)

    asyncio.run(run())
