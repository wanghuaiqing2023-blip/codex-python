from __future__ import annotations

import asyncio
import threading
import time
import weakref
from types import SimpleNamespace
from pathlib import Path

from pycodex.file_watcher import (
    FileWatcher,
    FileWatcherEvent,
    ThrottledWatchReceiver,
    WatchPath,
    is_mutating_event,
    watch_channel,
)


TEST_THROTTLE_INTERVAL = 0.05


def path(name: str) -> Path:
    return Path(name)


async def expect_timeout(awaitable, timeout: float = TEST_THROTTLE_INTERVAL / 2) -> None:
    try:
        await asyncio.wait_for(awaitable, timeout)
    except TimeoutError:
        return
    raise AssertionError("expected timeout")


def test_throttled_receiver_coalesces_within_interval() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: throttled_receiver_coalesces_within_interval
    # Contract: changed paths are emitted sorted/deduped and the next batch waits for the throttle interval.
    async def scenario() -> None:
        tx, rx = watch_channel()
        throttled = ThrottledWatchReceiver(rx, TEST_THROTTLE_INTERVAL)

        await tx.add_changed_paths([path("a")])
        first = await asyncio.wait_for(throttled.recv(), 1)
        assert first == FileWatcherEvent([path("a")])

        await tx.add_changed_paths([path("c"), path("b")])
        await expect_timeout(throttled.recv())

        second = await asyncio.wait_for(throttled.recv(), TEST_THROTTLE_INTERVAL * 3)
        assert second == FileWatcherEvent([path("b"), path("c")])

    asyncio.run(scenario())


def test_throttled_receiver_flushes_pending_on_shutdown() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: throttled_receiver_flushes_pending_on_shutdown
    # Contract: pending paths flush before the receiver closes after the sender count reaches zero.
    async def scenario() -> None:
        tx, rx = watch_channel()
        throttled = ThrottledWatchReceiver(rx, TEST_THROTTLE_INTERVAL)

        await tx.add_changed_paths([path("a")])
        assert await asyncio.wait_for(throttled.recv(), 1) == FileWatcherEvent([path("a")])

        await tx.add_changed_paths([path("b")])
        tx.close()

        assert await asyncio.wait_for(throttled.recv(), 1) == FileWatcherEvent([path("b")])
        assert await asyncio.wait_for(throttled.recv(), 1) is None

    asyncio.run(scenario())


def test_is_mutating_event_filters_non_mutating_event_kinds() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: is_mutating_event_filters_non_mutating_event_kinds
    # Contract: only create/modify/remove notify events are treated as mutating.
    assert is_mutating_event("create") is True
    assert is_mutating_event("modify") is True
    assert is_mutating_event("remove") is True
    assert is_mutating_event("access") is False


def test_register_dedupes_by_path_and_scope(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: register_dedupes_by_path_and_scope
    # Contract: duplicate path/scope registrations share subscriber state while recursive and non-recursive counts stay separate.
    skills = tmp_path / "skills"
    other_skills = tmp_path / "other-skills"
    skills.mkdir()
    other_skills.mkdir()

    watcher = FileWatcher.noop()
    subscriber, _rx = watcher.add_subscriber()
    first = subscriber.register_path(skills, recursive=False)
    second = subscriber.register_path(skills, recursive=False)
    third = subscriber.register_path(skills, recursive=True)
    fourth = subscriber.register_path(other_skills, recursive=True)

    assert watcher.watch_counts_for_test(skills) == (2, 1)
    assert watcher.watch_counts_for_test(other_skills) == (0, 1)

    first.close()
    second.close()
    third.close()
    fourth.close()
    subscriber.close()


def test_watch_registration_and_subscriber_close_unregister_paths(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust tests: watch_registration_drop_unregisters_paths, subscriber_drop_unregisters_paths
    # Contract: registration close removes its watches, and subscriber close removes all remaining watches.
    skills = tmp_path / "skills"
    skills.mkdir()

    watcher = FileWatcher.noop()
    subscriber, _rx = watcher.add_subscriber()
    registration = subscriber.register_path(skills, recursive=True)
    registration.close()
    assert watcher.watch_counts_for_test(skills) is None

    registration = subscriber.register_path(skills, recursive=True)
    assert watcher.watch_counts_for_test(skills) == (0, 1)
    subscriber.close()
    assert watcher.watch_counts_for_test(skills) is None
    registration.close()


def test_missing_paths_register_nearest_existing_directory_ancestor(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust tests: missing_path_registers_nearest_existing_parent, deeply_missing_path_registers_nearest_existing_directory_ancestor
    # Contract: missing targets watch the nearest existing directory ancestor non-recursively.
    missing_file = tmp_path / "FETCH_HEAD"

    watcher = FileWatcher.noop()
    subscriber, _rx = watcher.add_subscriber()
    registration = subscriber.register_path(missing_file, recursive=False)

    assert watcher.watch_counts_for_test(tmp_path) == (1, 0)
    assert watcher.watch_counts_for_test(missing_file) is None
    registration.close()
    assert watcher.watch_counts_for_test(tmp_path) is None

    refs = tmp_path / "refs"
    refs.write_text("not a dir")
    deeply_missing = refs / "heads" / "main"
    registration = subscriber.register_path(deeply_missing, recursive=False)
    assert watcher.watch_counts_for_test(tmp_path) == (1, 0)
    registration.close()
    subscriber.close()


def test_receiver_closes_when_subscriber_closes() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: receiver_closes_when_subscriber_drops
    # Contract: dropping the subscriber closes its receiver when no senders remain.
    async def scenario() -> None:
        watcher = FileWatcher.noop()
        subscriber, rx = watcher.add_subscriber()
        subscriber.close()
        assert await asyncio.wait_for(rx.recv(), 1) is None

    asyncio.run(scenario())


def test_recursive_registration_downgrades_to_non_recursive_after_drop(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: recursive_registration_downgrades_to_non_recursive_after_drop
    # Contract: live watch configuration prefers recursive mode while any
    # recursive registration remains, then downgrades to non-recursive.
    root = tmp_path / "watched-dir"
    root.mkdir()

    watcher = FileWatcher.new()
    subscriber, _rx = watcher.add_subscriber()
    non_recursive = subscriber.register_path(root, recursive=False)
    recursive = subscriber.register_path(root, recursive=True)

    assert watcher.watched_mode_for_test(root) == "recursive"

    recursive.close()
    assert watcher.watched_mode_for_test(root) == "non_recursive"

    non_recursive.close()
    subscriber.close()
    watcher.close()


def test_matching_subscribers_are_notified() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: matching_subscribers_are_notified
    # Contract: recursive watches receive matching descendants while unrelated subscribers stay quiet.
    async def scenario() -> None:
        watcher = FileWatcher.noop()
        skills_subscriber, skills_rx = watcher.add_subscriber()
        plugins_subscriber, plugins_rx = watcher.add_subscriber()
        skills_reg = skills_subscriber.register_path(path("/tmp/skills"), recursive=True)
        plugins_reg = plugins_subscriber.register_path(path("/tmp/plugins"), recursive=True)
        skills_rx = ThrottledWatchReceiver(skills_rx, TEST_THROTTLE_INTERVAL)
        plugins_rx = ThrottledWatchReceiver(plugins_rx, TEST_THROTTLE_INTERVAL)

        await watcher.send_paths_for_test([path("/tmp/skills/rust/SKILL.md")])

        assert await asyncio.wait_for(skills_rx.recv(), 1) == FileWatcherEvent(
            [path("/tmp/skills/rust/SKILL.md")]
        )
        await expect_timeout(plugins_rx.recv())

        skills_reg.close()
        plugins_reg.close()
        skills_subscriber.close()
        plugins_subscriber.close()

    asyncio.run(scenario())


def test_ancestor_events_notify_child_watches(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: ancestor_events_notify_child_watches
    # Contract: an ancestor event for an existing child watch reports the
    # changed ancestor path in subscriber-visible coordinates.
    async def scenario() -> None:
        skills_dir = tmp_path / "skills"
        rust_dir = skills_dir / "rust"
        skill_file = rust_dir / "SKILL.md"
        rust_dir.mkdir(parents=True)
        skill_file.write_text("name: rust\n")

        watcher = FileWatcher.noop()
        subscriber, rx = watcher.add_subscriber()
        registration = subscriber.register_path(skill_file, recursive=False)
        rx = ThrottledWatchReceiver(rx, TEST_THROTTLE_INTERVAL)

        await watcher.send_paths_for_test([skills_dir])
        assert await asyncio.wait_for(rx.recv(), 1) == FileWatcherEvent([skills_dir])

        registration.close()
        subscriber.close()

    asyncio.run(scenario())


def test_non_recursive_watch_ignores_grandchildren() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: non_recursive_watch_ignores_grandchildren
    # Contract: non-recursive watches match direct children but not grandchildren.
    async def scenario() -> None:
        watcher = FileWatcher.noop()
        subscriber, rx = watcher.add_subscriber()
        registration = subscriber.register_path(path("/tmp/skills"), recursive=False)
        rx = ThrottledWatchReceiver(rx, TEST_THROTTLE_INTERVAL)

        await watcher.send_paths_for_test([path("/tmp/skills/nested/SKILL.md")])
        await expect_timeout(rx.recv())

        registration.close()
        subscriber.close()

    asyncio.run(scenario())


def test_missing_file_watch_reports_requested_path_when_parent_delete_event_arrives(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: missing_file_watch_reports_requested_path_when_parent_delete_event_arrives
    # Contract: fallback parent events report both creation and deletion of the
    # originally requested missing file.
    async def scenario() -> None:
        missing_file = tmp_path / "FETCH_HEAD"
        watcher = FileWatcher.noop()
        subscriber, rx = watcher.add_subscriber()
        registration = subscriber.register_path(missing_file, recursive=False)
        rx = ThrottledWatchReceiver(rx, TEST_THROTTLE_INTERVAL)

        missing_file.write_text("origin/main\n")
        await watcher.send_paths_for_test([tmp_path])
        assert await asyncio.wait_for(rx.recv(), 1) == FileWatcherEvent([missing_file])

        missing_file.unlink()
        await watcher.send_paths_for_test([tmp_path])
        assert await asyncio.wait_for(rx.recv(), 1) == FileWatcherEvent([missing_file])

        registration.close()
        subscriber.close()

    asyncio.run(scenario())


def test_missing_file_watch_reports_requested_path_when_parent_changes(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: missing_file_watch_reports_requested_path_when_parent_changes
    # Contract: parent events report the requested missing file only once it exists.
    async def scenario() -> None:
        missing_file = tmp_path / "FETCH_HEAD"
        watcher = FileWatcher.noop()
        subscriber, rx = watcher.add_subscriber()
        registration = subscriber.register_path(missing_file, recursive=False)
        rx = ThrottledWatchReceiver(rx, TEST_THROTTLE_INTERVAL)

        await watcher.send_paths_for_test([tmp_path / "FETCH_HEAD.lock"])
        await expect_timeout(rx.recv())

        missing_file.write_text("origin/main\n")
        await watcher.send_paths_for_test([tmp_path])
        assert await asyncio.wait_for(rx.recv(), 1) == FileWatcherEvent([missing_file])

        registration.close()
        subscriber.close()

    asyncio.run(scenario())


def test_spawn_event_loop_filters_non_mutating_events() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: spawn_event_loop_filters_non_mutating_events
    # Contract: event-loop bridge ignores non-mutating raw events and forwards
    # create/modify/remove events to the same subscriber matcher.
    async def scenario() -> None:
        watcher = FileWatcher.noop()
        subscriber, rx = watcher.add_subscriber()
        registration = subscriber.register_path(path("/tmp/skills"), recursive=True)
        rx = ThrottledWatchReceiver(rx, TEST_THROTTLE_INTERVAL)
        raw_rx: asyncio.Queue = asyncio.Queue()
        watcher.spawn_event_loop_for_test(raw_rx)

        await raw_rx.put(SimpleNamespace(kind="access", paths=[path("/tmp/skills/SKILL.md")]))
        await expect_timeout(rx.recv())

        await raw_rx.put(SimpleNamespace(kind="create", paths=[path("/tmp/skills/SKILL.md")]))
        assert await asyncio.wait_for(rx.recv(), 1) == FileWatcherEvent(
            [path("/tmp/skills/SKILL.md")]
        )
        await raw_rx.put(None)

        registration.close()
        subscriber.close()

    asyncio.run(scenario())


def test_missing_directory_watch_moves_to_created_directory_for_child_events(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: missing_directory_watch_moves_to_created_directory_for_child_events
    # Contract: a missing directory watch moves from the parent fallback to the created directory.
    async def scenario() -> None:
        skills_dir = tmp_path / "skills"
        skill_file = skills_dir / "SKILL.md"
        watcher = FileWatcher.noop()
        subscriber, rx = watcher.add_subscriber()
        registration = subscriber.register_path(skills_dir, recursive=False)
        rx = ThrottledWatchReceiver(rx, TEST_THROTTLE_INTERVAL)

        assert watcher.watch_counts_for_test(tmp_path) == (1, 0)
        assert watcher.watch_counts_for_test(skills_dir) is None

        skills_dir.mkdir()
        await watcher.send_paths_for_test([tmp_path])
        assert await asyncio.wait_for(rx.recv(), 1) == FileWatcherEvent([skills_dir])
        assert watcher.watch_counts_for_test(tmp_path) is None
        assert watcher.watch_counts_for_test(skills_dir) == (1, 0)

        skill_file.write_text("name: rust\n")
        await watcher.send_paths_for_test([skill_file])
        assert await asyncio.wait_for(rx.recv(), 1) == FileWatcherEvent([skill_file])

        registration.close()
        subscriber.close()

    asyncio.run(scenario())


def test_dropping_live_watcher_releases_inner_watcher() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: dropping_live_watcher_releases_inner_watcher
    # Contract: dropping/closing the public live watcher releases its inner
    # native-watcher holder.
    watcher = FileWatcher.new()
    weak_inner = weakref.ref(watcher._inner)

    watcher.close()

    assert weak_inner() is None


def test_unregister_holds_state_lock_until_unwatch_finishes(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-file-watcher
    # Rust module: src/lib.rs
    # Rust test: unregister_holds_state_lock_until_unwatch_finishes
    # Contract: unregister keeps the state lock while live unwatch/reconfigure
    # is blocked on the inner watcher lock, so a concurrent registration cannot
    # mutate watch counts until unwatch finishes.
    root = tmp_path / "watched-dir"
    root.mkdir()

    watcher = FileWatcher.new()
    unregister_subscriber, _unregister_rx = watcher.add_subscriber()
    register_subscriber, _register_rx = watcher.add_subscriber()
    registration = unregister_subscriber.register_path(root, recursive=True)

    watcher._inner_lock.acquire()
    try:
        unregister_thread = threading.Thread(target=registration.close)
        unregister_thread.start()

        state_lock_observed = False
        for _ in range(100):
            acquired = watcher._state_lock.acquire(blocking=False)
            if acquired:
                watcher._state_lock.release()
                time.sleep(0.01)
            else:
                state_lock_observed = True
                break
        assert state_lock_observed is True

        registered: dict[str, object] = {}

        def register_non_recursive() -> None:
            non_recursive = register_subscriber.register_path(root, recursive=False)
            registered["registration"] = non_recursive

        register_thread = threading.Thread(target=register_non_recursive)
        register_thread.start()
        time.sleep(0.02)
        assert register_thread.is_alive()
    finally:
        watcher._inner_lock.release()

    unregister_thread.join(timeout=1)
    register_thread.join(timeout=1)
    assert not unregister_thread.is_alive()
    assert not register_thread.is_alive()

    assert watcher.watch_counts_for_test(root) == (1, 0)
    assert watcher.watched_mode_for_test(root) == "non_recursive"

    assert "registration" in registered
    registered_registration = registered["registration"]
    registered_registration.close()
    register_subscriber.close()
    watcher.close()
