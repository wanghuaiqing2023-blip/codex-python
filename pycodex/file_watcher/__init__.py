"""Dependency-light port of Rust `codex-file-watcher`.

The Rust crate uses `notify` and Tokio for live filesystem integration. This
module preserves the subscription, matching, coalescing, and synthetic event
contracts with Python standard-library primitives.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class FileWatcherEvent:
    paths: list[Path]


@dataclass(frozen=True)
class WatchPath:
    path: Path
    recursive: bool = False

    def __init__(self, path: str | Path, recursive: bool = False) -> None:
        object.__setattr__(self, "path", Path(path))
        object.__setattr__(self, "recursive", bool(recursive))


@dataclass
class _ReceiverInner:
    changed_paths: set[Path] = field(default_factory=set)
    sender_count: int = 1
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)


class Receiver:
    def __init__(self, inner: _ReceiverInner) -> None:
        self._inner = inner

    async def recv(self) -> FileWatcherEvent | None:
        while True:
            async with self._inner.condition:
                if self._inner.changed_paths:
                    paths = sorted(self._inner.changed_paths)
                    self._inner.changed_paths.clear()
                    return FileWatcherEvent(paths)
                if self._inner.sender_count == 0:
                    return None
                await self._inner.condition.wait()


class _WatchSender:
    def __init__(self, inner: _ReceiverInner) -> None:
        self._inner = inner
        self._closed = False

    def clone(self) -> "_WatchSender":
        self._inner.sender_count += 1
        return _WatchSender(self._inner)

    async def add_changed_paths(self, paths: Iterable[Path]) -> None:
        paths = [Path(path) for path in paths]
        if not paths:
            return
        async with self._inner.condition:
            previous_len = len(self._inner.changed_paths)
            self._inner.changed_paths.update(paths)
            if len(self._inner.changed_paths) != previous_len:
                self._inner.condition.notify(1)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inner.sender_count = max(self._inner.sender_count - 1, 0)

        async def _notify() -> None:
            async with self._inner.condition:
                self._inner.condition.notify_all()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_notify())
        else:
            loop.create_task(_notify())


def watch_channel() -> tuple[_WatchSender, Receiver]:
    inner = _ReceiverInner()
    return _WatchSender(inner), Receiver(inner)


class ThrottledWatchReceiver:
    def __init__(self, rx: Receiver, interval: float) -> None:
        self._rx = rx
        self._interval = float(interval)
        self._next_allowed: float | None = None

    async def recv(self) -> FileWatcherEvent | None:
        if self._next_allowed is not None:
            delay = self._next_allowed - asyncio.get_running_loop().time()
            if delay > 0:
                await asyncio.sleep(delay)
        event = await self._rx.recv()
        if event is not None:
            self._next_allowed = asyncio.get_running_loop().time() + self._interval
        return event


@dataclass
class _PathWatchCounts:
    non_recursive: int = 0
    recursive: int = 0

    def increment(self, recursive: bool, amount: int) -> None:
        if recursive:
            self.recursive += amount
        else:
            self.non_recursive += amount

    def decrement(self, recursive: bool, amount: int) -> None:
        if recursive:
            self.recursive = max(self.recursive - amount, 0)
        else:
            self.non_recursive = max(self.non_recursive - amount, 0)

    def is_empty(self) -> bool:
        return self.non_recursive == 0 and self.recursive == 0


@dataclass(frozen=True)
class _SubscriberWatchKey:
    requested: WatchPath
    matched: WatchPath


@dataclass
class _SubscriberWatchState:
    actual: WatchPath
    count: int
    last_exists: bool
    fallback: bool


@dataclass(frozen=True)
class _SubscriberWatchRegistration:
    key: _SubscriberWatchKey
    actual: WatchPath
    fallback: bool


@dataclass
class _SubscriberState:
    watched_paths: dict[_SubscriberWatchKey, _SubscriberWatchState]
    tx: _WatchSender


class _LiveWatcherInner:
    pass


class WatchRegistration:
    def __init__(
        self,
        file_watcher: "FileWatcher | None" = None,
        subscriber_id: int = 0,
        watched_paths: Iterable[_SubscriberWatchKey] = (),
    ) -> None:
        self._file_watcher = file_watcher
        self._subscriber_id = subscriber_id
        self._watched_paths = list(watched_paths)
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._file_watcher is not None:
            self._file_watcher._unregister_paths(self._subscriber_id, self._watched_paths)

    def __enter__(self) -> "WatchRegistration":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best-effort RAII parity
        self.close()


class FileWatcherSubscriber:
    def __init__(self, subscriber_id: int, file_watcher: "FileWatcher") -> None:
        self.id = subscriber_id
        self._file_watcher = file_watcher
        self._closed = False

    def register_paths(self, watched_paths: Iterable[WatchPath]) -> WatchRegistration:
        registrations = []
        for requested in _dedupe_watched_paths(watched_paths):
            actual, matched, fallback = _actual_watch_path(requested)
            key = _SubscriberWatchKey(requested=requested, matched=matched)
            registrations.append(_SubscriberWatchRegistration(key=key, actual=actual, fallback=fallback))
        self._file_watcher._register_paths(self.id, registrations)
        return WatchRegistration(self._file_watcher, self.id, (registration.key for registration in registrations))

    def register_path(self, path: str | Path, recursive: bool) -> WatchRegistration:
        return self.register_paths([WatchPath(path, recursive)])

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._file_watcher._remove_subscriber(self.id)

    def __del__(self) -> None:  # pragma: no cover - best-effort RAII parity
        self.close()


class FileWatcher:
    def __init__(self, *, live: bool = False) -> None:
        self.live = live
        self._inner = _LiveWatcherInner() if live else None
        self._inner_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._next_subscriber_id = 0
        self._path_ref_counts: dict[Path, _PathWatchCounts] = {}
        self._subscribers: dict[int, _SubscriberState] = {}
        self._watched_modes: dict[Path, str] = {}
        self._event_loop_tasks: list[asyncio.Task[None]] = []

    @classmethod
    def new(cls) -> "FileWatcher":
        return cls(live=True)

    @classmethod
    def noop(cls) -> "FileWatcher":
        return cls(live=False)

    def add_subscriber(self) -> tuple[FileWatcherSubscriber, Receiver]:
        tx, rx = watch_channel()
        with self._state_lock:
            subscriber_id = self._next_subscriber_id
            self._next_subscriber_id += 1
            self._subscribers[subscriber_id] = _SubscriberState(watched_paths={}, tx=tx)
        return FileWatcherSubscriber(subscriber_id, self), rx

    def _register_paths(self, subscriber_id: int, watched_paths: list[_SubscriberWatchRegistration]) -> None:
        with self._state_lock:
            subscriber = self._subscribers.get(subscriber_id)
            if subscriber is None:
                return
            for registration in watched_paths:
                state = subscriber.watched_paths.get(registration.key)
                if state is None:
                    state = _SubscriberWatchState(
                        actual=registration.actual,
                        count=1,
                        last_exists=registration.key.matched.path.exists(),
                        fallback=registration.fallback,
                    )
                    subscriber.watched_paths[registration.key] = state
                    actual = registration.actual
                else:
                    state.count += 1
                    actual = state.actual
                counts = self._path_ref_counts.setdefault(actual.path, _PathWatchCounts())
                previous_mode = _effective_mode(counts)
                counts.increment(actual.recursive, 1)
                self._reconfigure_watch(actual.path, previous_mode, _effective_mode(counts))

    def _unregister_paths(self, subscriber_id: int, watched_paths: list[_SubscriberWatchKey]) -> None:
        with self._state_lock:
            subscriber = self._subscribers.get(subscriber_id)
            if subscriber is None:
                return
            for key in watched_paths:
                state = subscriber.watched_paths.get(key)
                if state is None:
                    continue
                actual = state.actual
                state.count = max(state.count - 1, 0)
                if state.count == 0:
                    del subscriber.watched_paths[key]
                self._decrement_path_count(actual, 1)

    def _remove_subscriber(self, subscriber_id: int) -> None:
        with self._state_lock:
            subscriber = self._subscribers.pop(subscriber_id, None)
            if subscriber is None:
                return
            for state in subscriber.watched_paths.values():
                self._decrement_path_count(state.actual, state.count)
            subscriber.tx.close()

    def _decrement_path_count(self, actual: WatchPath, amount: int) -> None:
        counts = self._path_ref_counts.get(actual.path)
        if counts is None:
            return
        previous_mode = _effective_mode(counts)
        counts.decrement(actual.recursive, amount)
        if counts.is_empty():
            del self._path_ref_counts[actual.path]
            next_mode = None
        else:
            next_mode = _effective_mode(counts)
        self._reconfigure_watch(actual.path, previous_mode, next_mode)

    def _reconfigure_watch(self, path: Path, previous_mode: str | None, next_mode: str | None) -> None:
        if not self.live or previous_mode == next_mode:
            return
        with self._inner_lock:
            self._watched_modes.pop(path, None)
            if next_mode is not None and path.exists():
                self._watched_modes[path] = next_mode

    async def send_paths_for_test(self, paths: Iterable[str | Path]) -> None:
        await self._notify_subscribers([Path(path) for path in paths])

    async def _notify_subscribers(self, event_paths: list[Path]) -> None:
        subscribers_to_notify: list[tuple[_WatchSender, list[Path]]] = []
        actual_watch_moves: list[tuple[WatchPath, WatchPath, int]] = []
        with self._state_lock:
            for subscriber in self._subscribers.values():
                changed_paths: list[Path] = []
                for event_path in event_paths:
                    for key, watch_state in list(subscriber.watched_paths.items()):
                        changed = _changed_path_for_event(key, watch_state, event_path)
                        if changed is not None:
                            changed_paths.append(changed)
                        new_actual, _new_matched, fallback = _actual_watch_path(key.requested)
                        watch_state.fallback = watch_state.fallback or fallback
                        if watch_state.actual != new_actual:
                            old_actual = watch_state.actual
                            watch_state.actual = new_actual
                            actual_watch_moves.append((old_actual, new_actual, watch_state.count))
                if changed_paths:
                    subscribers_to_notify.append((subscriber.tx.clone(), changed_paths))

            for old_actual, new_actual, count in actual_watch_moves:
                self._decrement_path_count(old_actual, count)
                counts = self._path_ref_counts.setdefault(new_actual.path, _PathWatchCounts())
                previous_mode = _effective_mode(counts)
                counts.increment(new_actual.recursive, count)
                self._reconfigure_watch(new_actual.path, previous_mode, _effective_mode(counts))

        for sender, changed_paths in subscribers_to_notify:
            await sender.add_changed_paths(changed_paths)
            sender.close()

    def spawn_event_loop_for_test(self, raw_rx: "asyncio.Queue[Any]") -> None:
        async def _run() -> None:
            while True:
                item = await raw_rx.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    continue
                if not is_mutating_event(item):
                    continue
                paths = getattr(item, "paths", None)
                if not paths:
                    continue
                await self._notify_subscribers([Path(path) for path in paths])

        self._event_loop_tasks.append(asyncio.create_task(_run()))

    def watch_counts_for_test(self, path: str | Path) -> tuple[int, int] | None:
        with self._state_lock:
            counts = self._path_ref_counts.get(Path(path))
            if counts is None:
                return None
            return counts.non_recursive, counts.recursive

    def watched_mode_for_test(self, path: str | Path) -> str | None:
        with self._inner_lock:
            return self._watched_modes.get(Path(path))

    def close(self) -> None:
        self._event_loop_tasks.clear()
        with self._inner_lock:
            self._inner = None
            self._watched_modes.clear()


def is_mutating_event(event: object) -> bool:
    kind = getattr(event, "kind", event)
    if isinstance(kind, str):
        return kind.lower() in {"create", "modify", "remove"}
    return kind in {"create", "modify", "remove"}


def _dedupe_watched_paths(watched_paths: Iterable[WatchPath]) -> list[WatchPath]:
    return sorted(set(watched_paths), key=lambda item: (str(item.path), item.recursive))


def _effective_mode(counts: _PathWatchCounts) -> str | None:
    if counts.recursive > 0:
        return "recursive"
    if counts.non_recursive > 0:
        return "non_recursive"
    return None


def _canonical_or_self(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError:
        return path


def _actual_watch_path(requested: WatchPath) -> tuple[WatchPath, WatchPath, bool]:
    if requested.path.exists():
        return requested, WatchPath(_canonical_or_self(requested.path), requested.recursive), False

    ancestor = requested.path.parent
    while ancestor != ancestor.parent:
        if ancestor.is_dir():
            actual_path = _canonical_or_self(ancestor)
            try:
                suffix = requested.path.relative_to(ancestor)
                matched_path = actual_path / suffix
            except ValueError:
                matched_path = requested.path
            return WatchPath(ancestor, False), WatchPath(matched_path, requested.recursive), True
        ancestor = ancestor.parent
    return requested, requested, False


def _changed_path_for_event(
    key: _SubscriberWatchKey,
    watch_state: _SubscriberWatchState,
    event_path: Path,
) -> Path | None:
    changed = _changed_path_for_matched_path(key, watch_state, key.matched, event_path)
    if changed is not None:
        return changed
    if key.matched.path == key.requested.path:
        return None
    return _changed_path_for_matched_path(key, watch_state, key.requested, event_path)


def _changed_path_for_matched_path(
    key: _SubscriberWatchKey,
    watch_state: _SubscriberWatchState,
    matched: WatchPath,
    event_path: Path,
) -> Path | None:
    requested = key.requested
    if event_path == matched.path:
        watch_state.last_exists = matched.path.exists()
        return requested.path
    try:
        matched.path.relative_to(event_path)
        matched_starts_with_event = True
    except ValueError:
        matched_starts_with_event = False
    if matched_starts_with_event:
        now_exists = matched.path.exists()
        if watch_state.fallback or watch_state.actual.path != matched.path:
            should_notify = now_exists or watch_state.last_exists
            watch_state.last_exists = now_exists
            return requested.path if should_notify else None
        watch_state.last_exists = now_exists
        return event_path

    try:
        suffix = event_path.relative_to(matched.path)
        event_starts_with_matched = True
    except ValueError:
        event_starts_with_matched = False
        suffix = None
    if not event_starts_with_matched:
        return None
    if not (matched.recursive or event_path.parent == matched.path):
        return None
    watch_state.last_exists = matched.path.exists()
    return requested.path / suffix if suffix is not None else event_path


__all__ = [
    "FileWatcher",
    "FileWatcherEvent",
    "FileWatcherSubscriber",
    "Receiver",
    "ThrottledWatchReceiver",
    "WatchPath",
    "WatchRegistration",
    "is_mutating_event",
    "watch_channel",
]
