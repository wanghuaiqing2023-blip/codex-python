"""Thread manager boundary port from ``codex-rs/core/src/thread_manager.rs``.

The Rust implementation owns a large amount of runtime wiring: auth, MCP,
plugins, environments, Codex sessions, metrics, and UI-facing broadcast
channels. This Python module preserves the stable manager-facing API surface
that can be expressed without that runtime, while keeping session creation
injectable so higher layers can provide the concrete Codex thread object.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping, MutableMapping, Sequence

from pycodex.core.environment_selection import (
    default_thread_environment_selections as _default_environment_selections_from_manager,
    resolve_environment_selections as _resolve_environment_selections_from_manager,
)
from pycodex.protocol import (
    CodexErr,
    InitialHistory,
    ResumedHistory,
    RolloutItem,
    ThreadId,
    TurnEnvironmentSelection,
)


THREAD_CREATED_CHANNEL_CAPACITY = 1024

_FORCE_TEST_THREAD_MANAGER_BEHAVIOR = False


def set_thread_manager_test_mode_for_tests(enabled: bool) -> None:
    """Force test behavior for thread-manager paths."""

    global _FORCE_TEST_THREAD_MANAGER_BEHAVIOR
    _FORCE_TEST_THREAD_MANAGER_BEHAVIOR = bool(enabled)


def should_use_test_thread_manager_behavior() -> bool:
    """Return whether thread-manager test behavior is forced."""

    return _FORCE_TEST_THREAD_MANAGER_BEHAVIOR


class ForkSnapshotKind(str, Enum):
    """Fork snapshot modes used when deriving a new thread from history."""

    TRUNCATE_BEFORE_NTH_USER_MESSAGE = "truncate_before_nth_user_message"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class ForkSnapshot:
    """Python representation of Rust's ``ForkSnapshot`` enum."""

    kind: ForkSnapshotKind
    nth_user_message: int | None = None

    @classmethod
    def truncate_before_nth_user_message(cls, nth_user_message: int) -> "ForkSnapshot":
        if isinstance(nth_user_message, bool) or nth_user_message < 0:
            raise ValueError("nth_user_message must be a non-negative integer")
        return cls(
            kind=ForkSnapshotKind.TRUNCATE_BEFORE_NTH_USER_MESSAGE,
            nth_user_message=int(nth_user_message),
        )

    @classmethod
    def interrupted(cls) -> "ForkSnapshot":
        return cls(kind=ForkSnapshotKind.INTERRUPTED)

    @classmethod
    def from_value(cls, value: int | "ForkSnapshot") -> "ForkSnapshot":
        if isinstance(value, ForkSnapshot):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return cls.truncate_before_nth_user_message(value)
        raise TypeError("ForkSnapshot.from_value expects an integer or ForkSnapshot")


@dataclass(slots=True)
class NewThread:
    """Thread creation result returned by ``ThreadManager.start_thread``."""

    thread_id: str
    thread: Any
    session_configured: Any


@dataclass(slots=True)
class ThreadShutdownReport:
    """Shutdown categorization for managed threads."""

    completed: list[str] = field(default_factory=list)
    submit_failed: list[str] = field(default_factory=list)
    timed_out: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StartThreadOptions:
    """Subset of Rust's ``StartThreadOptions`` with runtime dependencies opaque."""

    config: Any
    initial_history: Sequence[Any] = ()
    session_source: Any = None
    thread_source: Any = None
    dynamic_tools: Sequence[Any] = ()
    persist_extended_history: bool = False
    metrics_service_name: str | None = None
    parent_trace: Any = None
    environments: Sequence[Any] = ()


class ThreadNotFoundError(KeyError):
    """Raised when a requested thread id is not managed by this instance."""


@dataclass(frozen=True, slots=True)
class StoredThreadHistory:
    items: tuple[RolloutItem, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "items",
            tuple(RolloutItem.from_mapping(item) for item in self.items),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "StoredThreadHistory":
        items = value.get("items")
        if isinstance(items, str) or not isinstance(items, Iterable) or isinstance(items, Mapping):
            raise TypeError("stored thread history items must be a list")
        return cls(tuple(RolloutItem.from_mapping(item) for item in items))


@dataclass(frozen=True, slots=True)
class StoredThread:
    thread_id: ThreadId
    history: StoredThreadHistory | None = None
    rollout_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.thread_id, ThreadId):
            object.__setattr__(self, "thread_id", ThreadId.from_string(str(self.thread_id)))
        if self.history is not None and not isinstance(self.history, StoredThreadHistory):
            if isinstance(self.history, Mapping):
                object.__setattr__(self, "history", StoredThreadHistory.from_mapping(self.history))
            else:
                object.__setattr__(self, "history", StoredThreadHistory(tuple(self.history)))
        if self.rollout_path is not None and not isinstance(self.rollout_path, Path):
            object.__setattr__(self, "rollout_path", Path(str(self.rollout_path)))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "StoredThread":
        history = value.get("history")
        return cls(
            thread_id=ThreadId.from_string(str(value["thread_id"])),
            history=StoredThreadHistory.from_mapping(history) if isinstance(history, Mapping) else history,
            rollout_path=value.get("rollout_path"),
        )


@dataclass(frozen=True, slots=True)
class ThreadStoreError:
    kind: str
    thread_id: ThreadId | None = None
    message: str | None = None
    operation: str | None = None

    @classmethod
    def thread_not_found(cls, thread_id: ThreadId | str) -> "ThreadStoreError":
        return cls("thread_not_found", thread_id=thread_id if isinstance(thread_id, ThreadId) else ThreadId.from_string(str(thread_id)))

    @classmethod
    def invalid_request(cls, message: str) -> "ThreadStoreError":
        return cls("invalid_request", message=message)

    @classmethod
    def unsupported(cls, operation: str) -> "ThreadStoreError":
        return cls("unsupported", operation=operation)

    @classmethod
    def other(cls, message: str) -> "ThreadStoreError":
        return cls("other", message=message)

    def __str__(self) -> str:
        if self.kind == "thread_not_found" and self.thread_id is not None:
            return f"thread not found: {self.thread_id}"
        if self.kind == "invalid_request" and self.message is not None:
            return self.message
        if self.kind == "unsupported" and self.operation is not None:
            return f"unsupported operation: {self.operation}"
        return self.message or self.kind


@dataclass(slots=True)
class ManagedThread:
    """Default lightweight thread object used when no factory is provided."""

    thread_id: str
    config: Any
    initial_history: Sequence[Any] = ()
    dynamic_tools: Sequence[Any] = ()
    environments: Sequence[Any] = ()

    async def shutdown_and_wait(self) -> None:
        return None


ThreadFactory = Callable[[StartThreadOptions], NewThread | Any | Awaitable[NewThread | Any]]


class ThreadManager:
    """In-memory thread registry with broadcast-style creation notifications."""

    def __init__(
        self,
        *,
        thread_factory: ThreadFactory | None = None,
        session_source: Any = None,
        auth_manager: Any = None,
        skills_manager: Any = None,
        plugins_manager: Any = None,
        mcp_manager: Any = None,
        environment_manager: Any = None,
        models_manager: Any = None,
        default_environment_selections: Mapping[str, Any] | None = None,
    ) -> None:
        self._thread_factory = thread_factory
        self._session_source = session_source
        self._auth_manager = auth_manager
        self._skills_manager = skills_manager
        self._plugins_manager = plugins_manager
        self._mcp_manager = mcp_manager
        self._environment_manager = environment_manager
        self._models_manager = models_manager
        self._default_environment_selections = dict(default_environment_selections or {})
        self._threads: MutableMapping[str, Any] = {}
        self._thread_metadata: MutableMapping[str, dict[str, Any]] = {}
        self._thread_created_subscribers: list[asyncio.Queue[str]] = []

    @classmethod
    def new(cls, **kwargs: Any) -> "ThreadManager":
        """Rust-style constructor alias."""

        return cls(**kwargs)

    def session_source(self) -> Any:
        return self._session_source

    def auth_manager(self) -> Any:
        return self._auth_manager

    def skills_manager(self) -> Any:
        return self._skills_manager

    def plugins_manager(self) -> Any:
        return self._plugins_manager

    def mcp_manager(self) -> Any:
        return self._mcp_manager

    def environment_manager(self) -> Any:
        return self._environment_manager

    def models_manager(self) -> Any:
        return self._models_manager

    def default_environment_selections(self, cwd: Path | str) -> list[TurnEnvironmentSelection]:
        """Resolve default environment selections for a given working directory."""

        if self._environment_manager is None:
            raise TypeError("environment_manager must be available to resolve defaults")
        return _default_environment_selections_from_manager(self._environment_manager, cwd)

    def validate_environment_selections(self, environment_ids: Iterable[TurnEnvironmentSelection]) -> None:
        """Validate selections through the manager-owned environment catalog."""

        if self._environment_manager is None:
            raise TypeError("environment_manager must be available to validate selections")
        _resolve_environment_selections_from_manager(self._environment_manager, environment_ids)
        return None

    def subscribe_thread_created(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=THREAD_CREATED_CHANNEL_CAPACITY)
        self._thread_created_subscribers.append(queue)
        return queue

    async def start_thread(self, options: StartThreadOptions | Any) -> NewThread:
        if not isinstance(options, StartThreadOptions):
            options = StartThreadOptions(config=options, session_source=self._session_source)

        created = await self._create_thread(options)
        self.add_thread(created)
        return created

    def add_thread(self, new_thread: NewThread) -> None:
        self._threads[new_thread.thread_id] = new_thread.thread
        self._thread_metadata.setdefault(new_thread.thread_id, {})
        self._notify_thread_created(new_thread.thread_id)

    def list_thread_ids(self) -> list[str]:
        return list(self._threads)

    def get_thread(self, thread_id: str) -> Any:
        try:
            return self._threads[thread_id]
        except KeyError as exc:
            raise ThreadNotFoundError(thread_id) from exc

    def remove_thread(self, thread_id: str) -> bool:
        existed = thread_id in self._threads
        self._threads.pop(thread_id, None)
        self._thread_metadata.pop(thread_id, None)
        return existed

    def update_thread_metadata(self, thread_id: str, metadata: Mapping[str, Any]) -> None:
        if thread_id not in self._threads:
            raise ThreadNotFoundError(thread_id)
        self._thread_metadata[thread_id] = dict(metadata)

    def get_thread_metadata(self, thread_id: str) -> dict[str, Any]:
        if thread_id not in self._threads:
            raise ThreadNotFoundError(thread_id)
        return dict(self._thread_metadata.get(thread_id, {}))

    async def shutdown_all(self, *, timeout: float | None = None) -> ThreadShutdownReport:
        report = ThreadShutdownReport()
        for thread_id, thread in list(self._threads.items()):
            shutdown = getattr(thread, "shutdown_and_wait", None)
            if shutdown is None:
                report.completed.append(thread_id)
                continue
            try:
                result = shutdown()
                if inspect.isawaitable(result):
                    if timeout is None:
                        await result
                    else:
                        await asyncio.wait_for(result, timeout=timeout)
                report.completed.append(thread_id)
            except (TimeoutError, asyncio.TimeoutError):
                report.timed_out.append(thread_id)
            except Exception:
                report.submit_failed.append(thread_id)
        return report

    async def _create_thread(self, options: StartThreadOptions) -> NewThread:
        if self._thread_factory is not None:
            result = self._thread_factory(options)
            if inspect.isawaitable(result):
                result = await result
            return _coerce_new_thread(result)

        thread_id = str(uuid.uuid4())
        thread = ManagedThread(
            thread_id=thread_id,
            config=options.config,
            initial_history=tuple(options.initial_history),
            dynamic_tools=tuple(options.dynamic_tools),
            environments=tuple(options.environments),
        )
        session_configured = {
            "thread_id": thread_id,
            "config": options.config,
            "session_source": options.session_source,
            "thread_source": options.thread_source,
            "persist_extended_history": options.persist_extended_history,
            "metrics_service_name": options.metrics_service_name,
        }
        return NewThread(
            thread_id=thread_id,
            thread=thread,
            session_configured=session_configured,
        )

    def _notify_thread_created(self, thread_id: str) -> None:
        for queue in list(self._thread_created_subscribers):
            try:
                queue.put_nowait(thread_id)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(thread_id)


def _coerce_new_thread(value: Any) -> NewThread:
    if isinstance(value, NewThread):
        return value

    thread_id = getattr(value, "thread_id", None)
    thread = getattr(value, "thread", value)
    session_configured = getattr(value, "session_configured", None)
    if thread_id is None:
        thread_id = getattr(thread, "thread_id", None)
    if thread_id is None:
        raise TypeError("thread factory must return NewThread or an object with thread_id")
    return NewThread(
        thread_id=str(thread_id),
        thread=thread,
        session_configured=session_configured,
    )


def stored_thread_to_initial_history(stored_thread: StoredThread | Mapping[str, Any], rollout_path: str | Path | None = None) -> InitialHistory:
    """Convert a thread-store row into Rust's ``InitialHistory::Resumed``."""

    if isinstance(stored_thread, Mapping):
        stored_thread = StoredThread.from_mapping(stored_thread)
    if not isinstance(stored_thread, StoredThread):
        raise TypeError("stored_thread must be StoredThread or mapping")
    if stored_thread.history is None:
        raise CodexErr.fatal(f"thread {stored_thread.thread_id} did not include persisted history")
    resolved_rollout_path = Path(rollout_path) if rollout_path is not None else stored_thread.rollout_path
    return InitialHistory.resumed_history(
        ResumedHistory(
            conversation_id=stored_thread.thread_id,
            history=stored_thread.history.items,
            rollout_path=resolved_rollout_path,
        )
    )


def thread_store_rollout_read_error(err: ThreadStoreError) -> CodexErr:
    """Map thread-store rollout reads to Rust-shaped ``CodexErr`` values."""

    if not isinstance(err, ThreadStoreError):
        raise TypeError("err must be ThreadStoreError")
    if err.kind == "thread_not_found" and err.thread_id is not None:
        return CodexErr.thread_not_found(str(err.thread_id))
    if err.kind == "invalid_request" and err.message is not None:
        return CodexErr.invalid_request(err.message)
    return CodexErr.fatal(f"failed to read thread by rollout path: {err}")


def thread_store_metadata_update_error(thread_id: ThreadId | str, err: ThreadStoreError) -> CodexErr:
    """Map thread metadata update failures like Rust ``thread_store_metadata_update_error``."""

    if not isinstance(thread_id, ThreadId):
        thread_id = ThreadId.from_string(str(thread_id))
    if not isinstance(err, ThreadStoreError):
        raise TypeError("err must be ThreadStoreError")
    if err.kind == "thread_not_found" and err.thread_id is not None:
        return CodexErr.thread_not_found(str(err.thread_id))
    if err.kind == "invalid_request" and err.message is not None:
        return CodexErr.invalid_request(err.message)
    if err.kind == "unsupported" and err.operation is not None:
        return CodexErr.unsupported_operation(
            f"thread metadata update is not supported by this store: {err.operation}"
        )
    return CodexErr.fatal(f"failed to update thread metadata {thread_id}: {err}")


__all__ = [
    "THREAD_CREATED_CHANNEL_CAPACITY",
    "ForkSnapshot",
    "ForkSnapshotKind",
    "ManagedThread",
    "NewThread",
    "StartThreadOptions",
    "StoredThread",
    "StoredThreadHistory",
    "ThreadFactory",
    "ThreadManager",
    "ThreadNotFoundError",
    "ThreadShutdownReport",
    "ThreadStoreError",
    "set_thread_manager_test_mode_for_tests",
    "should_use_test_thread_manager_behavior",
    "stored_thread_to_initial_history",
    "thread_store_metadata_update_error",
    "thread_store_rollout_read_error",
]
