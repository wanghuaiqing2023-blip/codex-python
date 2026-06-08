import asyncio
from pathlib import Path
import uuid

import pytest

from pycodex.exec_server import EnvironmentManager
from pycodex.core.thread_manager import (
    ForkSnapshot,
    ForkSnapshotKind,
    NewThread,
    StartThreadOptions,
    StoredThread,
    StoredThreadHistory,
    ThreadManager,
    ThreadNotFoundError,
    ThreadStoreError,
    set_thread_manager_test_mode_for_tests,
    should_use_test_thread_manager_behavior,
    stored_thread_to_initial_history,
    thread_store_metadata_update_error,
    thread_store_rollout_read_error,
)
from pycodex.protocol import CodexErr, RolloutItem, TurnEnvironmentSelection, ThreadId


def test_thread_manager_test_mode_flag_round_trips():
    set_thread_manager_test_mode_for_tests(True)
    assert should_use_test_thread_manager_behavior() is True

    set_thread_manager_test_mode_for_tests(False)
    assert should_use_test_thread_manager_behavior() is False


def test_fork_snapshot_from_integer_matches_truncation_variant():
    snapshot = ForkSnapshot.from_value(2)

    assert snapshot.kind is ForkSnapshotKind.TRUNCATE_BEFORE_NTH_USER_MESSAGE
    assert snapshot.nth_user_message == 2


def test_fork_snapshot_interrupted_has_no_index():
    snapshot = ForkSnapshot.interrupted()

    assert snapshot.kind is ForkSnapshotKind.INTERRUPTED
    assert snapshot.nth_user_message is None


@pytest.mark.asyncio
async def test_start_thread_registers_default_thread_and_notifies_subscriber():
    manager = ThreadManager()
    created = manager.subscribe_thread_created()

    new_thread = await manager.start_thread({"model": "gpt-5"})

    assert manager.get_thread(new_thread.thread_id) is new_thread.thread
    assert manager.list_thread_ids() == [new_thread.thread_id]
    assert await asyncio.wait_for(created.get(), timeout=0.1) == new_thread.thread_id


@pytest.mark.asyncio
async def test_start_thread_accepts_injected_factory_result():
    async def factory(options: StartThreadOptions):
        return NewThread(
            thread_id="thread-1",
            thread={"config": options.config},
            session_configured={"ok": True},
        )

    manager = ThreadManager(thread_factory=factory)

    new_thread = await manager.start_thread(StartThreadOptions(config={"profile": "test"}))

    assert new_thread.thread_id == "thread-1"
    assert new_thread.thread == {"config": {"profile": "test"}}
    assert new_thread.session_configured == {"ok": True}


def test_default_environment_selections_uses_environment_manager_defaults():
    manager = ThreadManager(environment_manager=EnvironmentManager.default_for_tests())

    selections = manager.default_environment_selections(Path("/tmp"))

    assert selections == [TurnEnvironmentSelection(environment_id="local", cwd=Path("/tmp"))]


def test_validate_environment_selections_rejects_duplicate_selection_ids():
    manager = ThreadManager(environment_manager=EnvironmentManager.default_for_tests())

    with pytest.raises(CodexErr) as exc:
        manager.validate_environment_selections(
            (
                TurnEnvironmentSelection(environment_id="local", cwd=Path("/tmp")),
                TurnEnvironmentSelection(environment_id="local", cwd=Path("/tmp")),
            )
        )
    assert exc.value.kind == "invalid_request"
    assert "duplicate turn environment id" in exc.value.message


def test_validate_environment_selections_rejects_unknown_environment_id():
    manager = ThreadManager(environment_manager=EnvironmentManager.default_for_tests())

    with pytest.raises(CodexErr) as exc:
        manager.validate_environment_selections((TurnEnvironmentSelection(environment_id="missing", cwd=Path("/tmp")),))
    assert exc.value.kind == "invalid_request"
    assert "unknown turn environment id `missing`" in exc.value.message


def test_thread_lookup_metadata_and_removal_are_in_memory():
    manager = ThreadManager()
    manager.add_thread(NewThread("thread-1", object(), {"configured": True}))

    manager.update_thread_metadata("thread-1", {"name": "scratch"})

    assert manager.list_thread_ids() == ["thread-1"]
    assert manager.get_thread_metadata("thread-1") == {"name": "scratch"}
    assert manager.remove_thread("thread-1") is True
    assert manager.remove_thread("thread-1") is False
    with pytest.raises(ThreadNotFoundError):
        manager.get_thread("thread-1")


def test_stored_thread_to_initial_history_builds_resumed_history_and_prefers_explicit_rollout_path():
    # Rust: codex-rs/core/src/thread_manager.rs::stored_thread_to_initial_history.
    thread_id = ThreadId.from_string(str(uuid.uuid4()))
    item = RolloutItem.response_item(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "output_text", "text": "hello"}],
        }
    )
    stored = StoredThread(
        thread_id=thread_id,
        history=StoredThreadHistory((item,)),
        rollout_path=Path("stored.jsonl"),
    )

    history = stored_thread_to_initial_history(stored, rollout_path=Path("explicit.jsonl"))

    assert history.type == "Resumed"
    assert history.resumed is not None
    assert history.resumed.conversation_id == thread_id
    assert history.resumed.history == (item,)
    assert history.resumed.rollout_path == Path("explicit.jsonl")


def test_stored_thread_to_initial_history_uses_stored_rollout_path_and_errors_without_history():
    # Rust: missing persisted history becomes CodexErr::Fatal with the thread id.
    thread_id = ThreadId.from_string(str(uuid.uuid4()))
    item = RolloutItem.response_item({"type": "message", "role": "assistant", "content": []})
    mapped = {
        "thread_id": str(thread_id),
        "history": {"items": [item.to_mapping()]},
        "rollout_path": "stored.jsonl",
    }

    history = stored_thread_to_initial_history(mapped)

    assert history.resumed is not None
    assert history.resumed.rollout_path == Path("stored.jsonl")
    with pytest.raises(CodexErr) as exc:
        stored_thread_to_initial_history(StoredThread(thread_id=thread_id))
    assert exc.value.kind == "fatal"
    assert f"thread {thread_id} did not include persisted history" in str(exc.value)


def test_thread_store_rollout_read_error_maps_rust_variants():
    # Rust: codex-rs/core/src/thread_manager.rs::thread_store_rollout_read_error.
    thread_id = ThreadId.from_string(str(uuid.uuid4()))

    not_found = thread_store_rollout_read_error(ThreadStoreError.thread_not_found(thread_id))
    invalid = thread_store_rollout_read_error(ThreadStoreError.invalid_request("bad rollout path"))
    other = thread_store_rollout_read_error(ThreadStoreError.other("io failed"))

    assert not_found == CodexErr.thread_not_found(str(thread_id))
    assert invalid == CodexErr.invalid_request("bad rollout path")
    assert other.kind == "fatal"
    assert "failed to read thread by rollout path: io failed" in str(other)


def test_thread_store_metadata_update_error_maps_rust_variants():
    # Rust: codex-rs/core/src/thread_manager.rs::thread_store_metadata_update_error.
    thread_id = ThreadId.from_string(str(uuid.uuid4()))
    missing_id = ThreadId.from_string(str(uuid.uuid4()))

    not_found = thread_store_metadata_update_error(thread_id, ThreadStoreError.thread_not_found(missing_id))
    invalid = thread_store_metadata_update_error(thread_id, ThreadStoreError.invalid_request("bad patch"))
    unsupported = thread_store_metadata_update_error(thread_id, ThreadStoreError.unsupported("update_metadata"))
    other = thread_store_metadata_update_error(thread_id, ThreadStoreError.other("disk failed"))

    assert not_found == CodexErr.thread_not_found(str(missing_id))
    assert invalid == CodexErr.invalid_request("bad patch")
    assert unsupported == CodexErr.unsupported_operation(
        "thread metadata update is not supported by this store: update_metadata"
    )
    assert other.kind == "fatal"
    assert f"failed to update thread metadata {thread_id}: disk failed" in str(other)


@pytest.mark.asyncio
async def test_shutdown_all_categorizes_completion_failure_and_timeout():
    class CompleteThread:
        async def shutdown_and_wait(self):
            return None

    class FailedThread:
        async def shutdown_and_wait(self):
            raise RuntimeError("submit failed")

    class SlowThread:
        async def shutdown_and_wait(self):
            await asyncio.sleep(1)

    manager = ThreadManager()
    manager.add_thread(NewThread("complete", CompleteThread(), None))
    manager.add_thread(NewThread("failed", FailedThread(), None))
    manager.add_thread(NewThread("slow", SlowThread(), None))

    report = await manager.shutdown_all(timeout=0.01)

    assert report.completed == ["complete"]
    assert report.submit_failed == ["failed"]
    assert report.timed_out == ["slow"]
