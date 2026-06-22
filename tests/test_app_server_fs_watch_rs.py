from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.app_server.fs_watch import (
    FS_CHANGED_NOTIFICATION_DEBOUNCE_MS,
    FsWatchManager,
    WatchKey,
    debounce_receiver_projection,
    fs_changed_notification_projection,
    is_duplicate_watch_error,
)
from pycodex.app_server_protocol import FsUnwatchParams, FsWatchParams, ServerNotification


def absolute(path: str) -> Path:
    return Path(path).resolve()


@pytest.mark.asyncio
async def test_watch_uses_client_id_and_tracks_owner_scoped_entry() -> None:
    # Rust source: watch_uses_client_id_and_tracks_the_owner_scoped_entry.
    manager = FsWatchManager.new_with_file_watcher(outgoing=None, file_watcher="noop")
    path = absolute("HEAD")

    response = await manager.watch(
        1,
        FsWatchParams(watch_id="watch-head", path=path),
    )

    assert response.path == path
    assert manager.active_watch_keys() == frozenset({WatchKey(1, "watch-head")})
    entry = manager.entries[WatchKey(1, "watch-head")]
    assert entry.watch_root == path
    assert entry.watch_path.path == path
    assert entry.watch_path.recursive is False


@pytest.mark.asyncio
async def test_unwatch_is_scoped_to_connection_that_created_watch() -> None:
    # Rust source: unwatch_is_scoped_to_the_connection_that_created_the_watch.
    manager = FsWatchManager.new_with_file_watcher(outgoing=None, file_watcher="noop")
    path = absolute("HEAD")
    await manager.watch(1, FsWatchParams(watch_id="watch-head", path=path))

    await manager.unwatch(2, FsUnwatchParams(watch_id="watch-head"))
    assert WatchKey(1, "watch-head") in manager.active_watch_keys()

    await manager.unwatch(1, FsUnwatchParams(watch_id="watch-head"))
    assert WatchKey(1, "watch-head") not in manager.active_watch_keys()


@pytest.mark.asyncio
async def test_watch_rejects_duplicate_id_for_same_connection() -> None:
    # Rust source: watch_rejects_duplicate_id_for_the_same_connection.
    manager = FsWatchManager.new_with_file_watcher(outgoing=None, file_watcher="noop")
    await manager.watch(1, FsWatchParams(watch_id="watch-head", path=absolute("HEAD")))

    with pytest.raises(Exception) as exc_info:
        await manager.watch(1, FsWatchParams(watch_id="watch-head", path=absolute("FETCH_HEAD")))

    assert is_duplicate_watch_error(exc_info.value)
    assert exc_info.value.message == "watchId already exists: watch-head"
    assert len(manager.entries) == 1


@pytest.mark.asyncio
async def test_same_watch_id_is_allowed_for_different_connections() -> None:
    # Rust contract: WatchKey includes both connection_id and watch_id.
    manager = FsWatchManager.new_with_file_watcher(outgoing=None, file_watcher="noop")

    await manager.watch(1, FsWatchParams(watch_id="watch-head", path=absolute("HEAD")))
    await manager.watch(2, FsWatchParams(watch_id="watch-head", path=absolute("FETCH_HEAD")))

    assert manager.active_watch_keys() == frozenset(
        {
            WatchKey(1, "watch-head"),
            WatchKey(2, "watch-head"),
        }
    )


@pytest.mark.asyncio
async def test_connection_closed_removes_only_that_connections_watches() -> None:
    # Rust source: connection_closed_removes_only_that_connections_watches.
    manager = FsWatchManager.new_with_file_watcher(outgoing=None, file_watcher="noop")
    await manager.watch(1, FsWatchParams(watch_id="watch-head", path=absolute("HEAD")))
    await manager.watch(1, FsWatchParams(watch_id="watch-fetch-head", path=absolute("FETCH_HEAD")))
    await manager.watch(2, FsWatchParams(watch_id="watch-packed-refs", path=absolute("packed-refs")))

    await manager.connection_closed(1)

    assert manager.active_watch_keys() == frozenset({WatchKey(2, "watch-packed-refs")})


def test_fs_changed_notification_joins_root_sorts_and_skips_empty_events() -> None:
    # Rust source: spawned watch task joins watch_root with changed paths, sorts them, and sends only non-empty events.
    root = absolute("repo")

    projection = fs_changed_notification_projection(
        "watch-head",
        root,
        [Path("z.txt"), Path("a.txt")],
    )

    assert projection.changed_paths == (root / "a.txt", root / "z.txt")
    assert isinstance(projection.notification, ServerNotification)
    assert projection.notification.type == "FsChanged"
    assert projection.notification.payload.watch_id == "watch-head"
    assert projection.notification.payload.changed_paths == (root / "a.txt", root / "z.txt")

    empty = fs_changed_notification_projection("watch-head", root, [])
    assert empty.changed_paths == ()
    assert empty.notification is None


def test_debounce_receiver_projection_accumulates_unique_paths() -> None:
    # Rust source: DebouncedReceiver accumulates changed paths across debounce window and drains one event.
    assert FS_CHANGED_NOTIFICATION_DEBOUNCE_MS == 200
    assert debounce_receiver_projection([]) is None
    assert debounce_receiver_projection([[Path("b")], [Path("a"), Path("b")]]) == (
        Path("a"),
        Path("b"),
    )


@pytest.mark.asyncio
async def test_watch_and_unwatch_accept_camel_case_mapping_params() -> None:
    # Rust protocol serde uses watchId; the app-server manager consumes the typed params after deserialization.
    manager = FsWatchManager.new_with_file_watcher(outgoing=None, file_watcher="noop")
    path = absolute("HEAD")

    response = await manager.watch(1, {"watchId": "watch-head", "path": str(path)})
    assert response.path == path

    await manager.unwatch(1, {"watchId": "watch-head"})
    assert manager.active_watch_keys() == frozenset()
