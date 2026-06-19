"""Filesystem watch manager projections for ``codex-app-server/src/fs_watch.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import invalid_request
from pycodex.app_server_protocol import (
    FsChangedNotification,
    FsUnwatchParams,
    FsUnwatchResponse,
    FsWatchParams,
    FsWatchResponse,
    JSONRPCErrorError,
    ServerNotification,
)

FS_CHANGED_NOTIFICATION_DEBOUNCE_MS = 200


class FsWatchError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error
        self.code = error.code
        self.message = error.message
        self.data = error.data


@dataclass(frozen=True)
class WatchPathProjection:
    path: Path
    recursive: bool = False


@dataclass(frozen=True)
class WatchKey:
    connection_id: Any
    watch_id: str


@dataclass(frozen=True)
class WatchEntryProjection:
    watch_root: Path
    watch_path: WatchPathProjection
    subscriber_registered: bool = True
    terminate_sender_present: bool = True


@dataclass(frozen=True)
class FsWatchNotificationProjection:
    watch_id: str
    changed_paths: tuple[Path, ...]
    notification: ServerNotification | None


@dataclass
class FsWatchManager:
    """App-server-owned watch bookkeeping without a concrete file watcher.

    The Rust module delegates actual filesystem observation to
    ``codex-file-watcher``. This Python class keeps the local app-server
    ownership and response/error behavior concrete.
    """

    outgoing: Any | None = None
    file_watcher: Any | None = None
    entries: dict[WatchKey, WatchEntryProjection] = field(default_factory=dict)

    @classmethod
    def new(cls, outgoing: Any) -> "FsWatchManager":
        return cls(outgoing=outgoing, file_watcher=None)

    @classmethod
    def new_with_file_watcher(cls, outgoing: Any, file_watcher: Any) -> "FsWatchManager":
        return cls(outgoing=outgoing, file_watcher=file_watcher)

    async def watch(self, connection_id: Any, params: FsWatchParams | Mapping[str, Any]) -> FsWatchResponse:
        if isinstance(params, Mapping):
            params = FsWatchParams.from_mapping(params)
        watch_id = params.watch_id
        watch_key = WatchKey(connection_id=connection_id, watch_id=watch_id)
        if watch_key in self.entries:
            raise FsWatchError(invalid_request(f"watchId already exists: {watch_id}"))
        watch_path = WatchPathProjection(path=Path(params.path), recursive=False)
        self.entries[watch_key] = WatchEntryProjection(
            watch_root=Path(params.path),
            watch_path=watch_path,
        )
        return FsWatchResponse(path=params.path)

    async def unwatch(self, connection_id: Any, params: FsUnwatchParams | Mapping[str, Any]) -> FsUnwatchResponse:
        if isinstance(params, Mapping):
            params = FsUnwatchParams.from_mapping(params)
        self.entries.pop(WatchKey(connection_id=connection_id, watch_id=params.watch_id), None)
        return FsUnwatchResponse()

    async def connection_closed(self, connection_id: Any) -> None:
        self.entries = {
            key: entry
            for key, entry in self.entries.items()
            if key.connection_id != connection_id
        }

    def active_watch_keys(self) -> frozenset[WatchKey]:
        return frozenset(self.entries)


def fs_changed_notification_projection(
    watch_id: str,
    watch_root: Path | str,
    changed_relative_paths: Iterable[Path | str],
) -> FsWatchNotificationProjection:
    """Mirror the Rust task's changed-path join/sort/empty-notification gate."""

    root = Path(watch_root)
    changed_paths = tuple(
        sorted(
            (root / Path(path) for path in changed_relative_paths),
            key=lambda path: str(path),
        )
    )
    notification = None
    if changed_paths:
        notification = ServerNotification(
            "FsChanged",
            FsChangedNotification(watch_id=watch_id, changed_paths=changed_paths),
        )
    return FsWatchNotificationProjection(
        watch_id=str(watch_id),
        changed_paths=changed_paths,
        notification=notification,
    )


def debounce_receiver_projection(
    event_batches: Sequence[Sequence[Path | str]],
) -> tuple[Path, ...] | None:
    """Project Rust ``DebouncedReceiver::recv`` path accumulation.

    Rust waits for at least one event, accumulates additional paths until the
    debounce allowance elapses, and then drains all changed paths into one
    ``FileWatcherEvent``. Time and Tokio select behavior remain runtime
    details; this helper preserves the deterministic accumulation shape.
    """

    changed: set[Path] = set()
    for batch in event_batches:
        changed.update(Path(path) for path in batch)
    if not changed:
        return None
    return tuple(sorted(changed, key=lambda path: str(path)))


def is_duplicate_watch_error(error: BaseException) -> bool:
    if isinstance(error, FsWatchError):
        error = error.error
    return (
        isinstance(error, JSONRPCErrorError)
        and error.code == -32600
        and error.message.startswith("watchId already exists: ")
    )


__all__ = [
    "FS_CHANGED_NOTIFICATION_DEBOUNCE_MS",
    "FsWatchError",
    "FsWatchManager",
    "FsWatchNotificationProjection",
    "WatchEntryProjection",
    "WatchKey",
    "WatchPathProjection",
    "debounce_receiver_projection",
    "fs_changed_notification_projection",
    "is_duplicate_watch_error",
]
