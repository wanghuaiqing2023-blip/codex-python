import asyncio

import pytest

from pycodex.core.thread_manager import (
    ForkSnapshot,
    ForkSnapshotKind,
    NewThread,
    StartThreadOptions,
    ThreadManager,
    ThreadNotFoundError,
    set_thread_manager_test_mode_for_tests,
    should_use_test_thread_manager_behavior,
)


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
