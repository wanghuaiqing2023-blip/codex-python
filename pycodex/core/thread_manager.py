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
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping, MutableMapping, Sequence

from pycodex.core.environment_selection import (
    default_thread_environment_selections as _default_environment_selections_from_manager,
    resolve_environment_selections as _resolve_environment_selections_from_manager,
)
from pycodex.core.tasks import InterruptedTurnHistoryMarker, interrupted_turn_history_marker
from pycodex.core.thread_rollout_truncation import (
    truncate_rollout_before_nth_user_message_from_start,
    user_message_positions_in_rollout,
)
from pycodex.protocol import (
    CodexErr,
    EventMsg,
    InitialHistory,
    ResumedHistory,
    RolloutItem,
    ThreadId,
    TurnAbortedEvent,
    TurnAbortReason,
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
class SnapshotTurnState:
    """State inferred from a persisted fork snapshot."""

    ends_mid_turn: bool
    active_turn_id: str | None = None
    active_turn_start_index: int | None = None


@dataclass(frozen=True, slots=True)
class StartThreadOptions:
    """Subset of Rust's ``StartThreadOptions`` with runtime dependencies opaque."""

    config: Any
    initial_history: Any = None
    session_source: Any = None
    thread_source: Any = None
    agent_control: Any = None
    auth_manager: Any = None
    dynamic_tools: Sequence[Any] = ()
    persist_extended_history: bool = False
    metrics_service_name: str | None = None
    parent_trace: Any = None
    environments: Sequence[Any] = ()
    inherited_shell_snapshot: Any = None
    inherited_exec_policy: Any = None
    user_shell_override: Any = None


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
    initial_history: Any = None
    session_source: Any = None
    dynamic_tools: Sequence[Any] = ()
    environments: Sequence[Any] = ()

    async def shutdown_and_wait(self) -> None:
        return None


ThreadFactory = Callable[[StartThreadOptions], NewThread | Any | Awaitable[NewThread | Any]]


def thread_store_from_config(config: Any, state_db: Any = None) -> Any:
    """Build the thread store selected by config, matching Rust's helper."""

    from pycodex.core.config import ThreadStoreConfig, thread_store_config
    from pycodex.thread_store import InMemoryThreadStore, LocalThreadStore, LocalThreadStoreConfig

    configured = getattr(config, "experimental_thread_store", None)
    if configured is None:
        configured = getattr(config, "thread_store", None)
    store_config = thread_store_config(configured)
    if store_config.kind == ThreadStoreConfig.local().kind:
        return LocalThreadStore(LocalThreadStoreConfig.from_config(config))
    if store_config.kind == "in_memory":
        if store_config.id is None:
            raise TypeError("in_memory thread store requires string id")
        return InMemoryThreadStore.for_id(store_config.id)
    raise ValueError(f"unknown thread store type: {store_config.kind}")


def build_models_manager(config: Any, auth_manager: Any) -> Any:
    """Build the shared models manager selected by config."""

    from pycodex.model_provider import create_model_provider

    provider = create_model_provider(getattr(config, "model_provider"), auth_manager)
    return provider.models_manager(
        Path(getattr(config, "codex_home")),
        getattr(config, "model_catalog", None),
    )


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
        agent_control: Any = None,
        environment_manager: Any = None,
        models_manager: Any = None,
        state_db: Any = None,
        thread_store: Any = None,
        default_environment_selections: Mapping[str, Any] | None = None,
    ) -> None:
        self._thread_factory = thread_factory
        self._session_source = session_source
        self._auth_manager = auth_manager
        self._skills_manager = skills_manager
        self._plugins_manager = plugins_manager
        self._mcp_manager = mcp_manager
        self._agent_control = agent_control
        self._environment_manager = environment_manager
        self._models_manager = models_manager
        self._state_db = state_db
        self._thread_store = thread_store
        self._default_environment_selections = dict(default_environment_selections or {})
        self._threads: MutableMapping[str, Any] = {}
        self._thread_metadata: MutableMapping[str, dict[str, Any]] = {}
        self._thread_created_subscribers: list[asyncio.Queue[str]] = []
        self._ops_log: list[tuple[str, Any]] | None = [] if should_use_test_thread_manager_behavior() else None

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

    def agent_control(self) -> Any:
        return self._agent_control

    def environment_manager(self) -> Any:
        return self._environment_manager

    def models_manager(self) -> Any:
        return self._models_manager

    def get_models_manager(self) -> Any:
        return self._models_manager

    def state_db(self) -> Any:
        return self._state_db

    async def list_models(self, refresh_strategy: Any = None) -> list[Any]:
        if self._models_manager is None:
            return []
        list_models = getattr(self._models_manager, "list_models", None)
        if not callable(list_models):
            return []
        try:
            result = list_models(refresh_strategy)
        except TypeError:
            result = list_models()
        result = await _maybe_await(result)
        return list(result or [])

    def list_collaboration_modes(self) -> list[Any]:
        if self._models_manager is None:
            return []
        list_modes = getattr(self._models_manager, "list_collaboration_modes", None)
        if not callable(list_modes):
            return []
        return list(list_modes() or [])

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
            return await self.start_thread_with_tools(
                options,
                dynamic_tools=(),
                persist_extended_history=False,
            )

        return await self.start_thread_with_options(options)

    async def start_thread_with_options(self, options: StartThreadOptions) -> NewThread:
        if not isinstance(options, StartThreadOptions):
            raise TypeError("options must be StartThreadOptions")
        return await self.start_thread_with_options_and_fork_source(
            options,
            forked_from_thread_id=None,
        )

    async def start_thread_with_options_and_fork_source(
        self,
        options: StartThreadOptions,
        forked_from_thread_id: str | None = None,
    ) -> NewThread:
        if not isinstance(options, StartThreadOptions):
            raise TypeError("options must be StartThreadOptions")
        if (
            options.session_source is None
            or options.thread_source is None
            or options.agent_control is None
            or options.auth_manager is None
            or not options.environments
        ):
            environments = options.environments
            cwd = getattr(options.config, "cwd", None)
            if not environments and self._environment_manager is not None and cwd is not None:
                environments = tuple(self.default_environment_selections(cwd))
            options = replace(
                options,
                session_source=options.session_source
                if options.session_source is not None
                else self._session_source,
                thread_source=options.thread_source
                if options.thread_source is not None
                else _initial_history_thread_source(options.initial_history),
                agent_control=options.agent_control
                if options.agent_control is not None
                else self._agent_control,
                auth_manager=options.auth_manager
                if options.auth_manager is not None
                else self._auth_manager,
                environments=environments,
            )
        resumed_history = _resumed_initial_history(options.initial_history)
        if resumed_history is not None:
            resumed_thread_id = str(resumed_history.conversation_id)
            existing_thread = self._threads.get(resumed_thread_id)
            if existing_thread is not None:
                if await _thread_is_running(existing_thread):
                    requested_rollout_path = getattr(resumed_history, "rollout_path", None)
                    existing_rollout_path = _thread_rollout_path(existing_thread)
                    if (
                        requested_rollout_path is not None
                        and existing_rollout_path is not None
                        and Path(requested_rollout_path) != Path(existing_rollout_path)
                    ):
                        raise CodexErr.invalid_request(
                            f"thread {resumed_thread_id} is already running with a different rollout path"
                        )
                    return NewThread(
                        thread_id=resumed_thread_id,
                        thread=existing_thread,
                        session_configured=_thread_session_configured(existing_thread),
                    )
                self.remove_thread(resumed_thread_id)
        created = await self._create_thread(options, forked_from_thread_id=forked_from_thread_id)
        thread_id = str(created.thread_id)
        if forked_from_thread_id is not None:
            self._thread_metadata.setdefault(thread_id, {})["forked_from_thread_id"] = str(
                forked_from_thread_id
            )
        self.add_thread(created)
        if resumed_history is not None:
            await _apply_resumed_thread_runtime_effects(created.thread)
        return created

    async def spawn_subagent(
        self,
        forked_from_thread_id: str,
        options: StartThreadOptions,
    ) -> NewThread:
        """Spawn a subagent by forking persisted history from a live thread."""

        if not isinstance(options, StartThreadOptions):
            raise TypeError("options must be StartThreadOptions")
        forked_from_thread_id = str(forked_from_thread_id)
        fork_source = self.get_thread(forked_from_thread_id)

        ensure_rollout_materialized = getattr(fork_source, "ensure_rollout_materialized", None)
        if not callable(ensure_rollout_materialized):
            raise TypeError(f"thread {forked_from_thread_id} does not provide ensure_rollout_materialized")
        await _maybe_await(ensure_rollout_materialized())

        flush_rollout = getattr(fork_source, "flush_rollout", None)
        if not callable(flush_rollout):
            raise TypeError(f"thread {forked_from_thread_id} does not provide flush_rollout")
        await _maybe_await(flush_rollout())

        read_thread = getattr(fork_source, "read_thread", None)
        if not callable(read_thread):
            raise TypeError(f"thread {forked_from_thread_id} does not provide read_thread")
        stored_thread = _call_read_thread(
            read_thread,
            forked_from_thread_id,
            include_archived=True,
            include_history=True,
        )
        stored_thread = await _maybe_await(stored_thread)

        rollout_path = getattr(fork_source, "rollout_path", None)
        if callable(rollout_path):
            rollout_path = rollout_path()
        history = stored_thread_to_initial_history(stored_thread, rollout_path)
        marker_from_config = getattr(InterruptedTurnHistoryMarker, "from_config", None)
        interrupted_marker = (
            marker_from_config(options.config)
            if callable(marker_from_config)
            else InterruptedTurnHistoryMarker.CONTEXTUAL_USER
        )
        options = replace(
            options,
            initial_history=fork_history_from_snapshot(
                ForkSnapshot.interrupted(),
                history,
                interrupted_marker,
            ),
            session_source=options.session_source
            if options.session_source is not None
            else _thread_spawn_session_source(forked_from_thread_id),
        )
        return await self.start_thread_with_options_and_fork_source(
            options,
            forked_from_thread_id=forked_from_thread_id,
        )

    async def fork_thread_from_history(
        self,
        snapshot: ForkSnapshot | int,
        config: Any,
        history: InitialHistory | Mapping[str, Any] | str,
        thread_source: Any = None,
        persist_extended_history: bool = False,
        parent_trace: Any = None,
    ) -> NewThread:
        """Fork an existing thread from already-loaded store history."""

        return await self._fork_thread_with_initial_history(
            ForkSnapshot.from_value(snapshot),
            config,
            history,
            thread_source,
            persist_extended_history,
            parent_trace,
        )

    async def _fork_thread_with_initial_history(
        self,
        snapshot: ForkSnapshot,
        config: Any,
        history: InitialHistory | Mapping[str, Any] | str,
        thread_source: Any = None,
        persist_extended_history: bool = False,
        parent_trace: Any = None,
    ) -> NewThread:
        history = InitialHistory.from_mapping(history)
        if history.type == "Resumed" and history.resumed is not None:
            forked_from_thread_id = str(history.resumed.conversation_id)
        elif history.type == "Forked":
            forked_from_id = getattr(history, "forked_from_id", None)
            forked_from_thread_id = str(forked_from_id()) if callable(forked_from_id) else None
        else:
            forked_from_thread_id = None

        marker_from_config = getattr(InterruptedTurnHistoryMarker, "from_config", None)
        interrupted_marker = (
            marker_from_config(config)
            if callable(marker_from_config)
            else InterruptedTurnHistoryMarker.CONTEXTUAL_USER
        )
        forked_history = fork_history_from_snapshot(snapshot, history, interrupted_marker)
        environments: Sequence[Any] = ()
        cwd = getattr(config, "cwd", None)
        if self._environment_manager is not None and cwd is not None:
            environments = tuple(self.default_environment_selections(cwd))
        options = StartThreadOptions(
            config=config,
            initial_history=forked_history,
            session_source=self._session_source,
            thread_source=thread_source,
            persist_extended_history=persist_extended_history,
            parent_trace=parent_trace,
            environments=environments,
        )
        return await self.start_thread_with_options_and_fork_source(
            options,
            forked_from_thread_id=forked_from_thread_id,
        )

    async def start_thread_with_tools(
        self,
        config: Any,
        dynamic_tools: Sequence[Any] = (),
        persist_extended_history: bool = False,
    ) -> NewThread:
        if not isinstance(persist_extended_history, bool):
            raise TypeError("persist_extended_history must be a bool")
        return await self.start_thread_with_options(
            StartThreadOptions(
                config=config,
                session_source=self._session_source,
                auth_manager=self._auth_manager,
                dynamic_tools=tuple(dynamic_tools),
                persist_extended_history=persist_extended_history,
            )
        )

    async def resume_thread_with_history(
        self,
        config: Any,
        initial_history: InitialHistory | Mapping[str, Any] | str,
        *,
        auth_manager: Any = None,
        session_source: Any = None,
        inherited_shell_snapshot: Any = None,
        inherited_exec_policy: Any = None,
        persist_extended_history: bool = False,
        parent_trace: Any = None,
    ) -> NewThread:
        options = StartThreadOptions(
            config=config,
            initial_history=InitialHistory.from_mapping(initial_history),
            auth_manager=auth_manager if auth_manager is not None else self._auth_manager,
            session_source=session_source if session_source is not None else self._session_source,
            persist_extended_history=persist_extended_history,
            parent_trace=parent_trace,
            inherited_shell_snapshot=inherited_shell_snapshot,
            inherited_exec_policy=inherited_exec_policy,
        )
        created = await self.start_thread_with_options(options)
        metadata = self._thread_metadata.setdefault(str(created.thread_id), {})
        if inherited_shell_snapshot is not None:
            metadata["inherited_shell_snapshot"] = inherited_shell_snapshot
        if inherited_exec_policy is not None:
            metadata["inherited_exec_policy"] = inherited_exec_policy
        return created

    async def resume_thread_from_rollout(
        self,
        config: Any,
        rollout_path: str | Path,
        auth_manager: Any = None,
        parent_trace: Any = None,
    ) -> NewThread:
        """Resume a stored thread located by rollout path."""

        initial_history = await self.initial_history_from_rollout_path(rollout_path)
        return await self.resume_thread_with_history(
            config,
            initial_history,
            auth_manager=auth_manager,
            persist_extended_history=False,
            parent_trace=parent_trace,
        )

    async def start_thread_with_user_shell_override_for_tests(
        self,
        config: Any,
        user_shell_override: Any,
    ) -> NewThread:
        """Test-only Rust-shaped start facade carrying a user shell override."""

        environments: Sequence[Any] = ()
        cwd = getattr(config, "cwd", None)
        if self._environment_manager is not None and cwd is not None:
            environments = tuple(self.default_environment_selections(cwd))
        return await self.start_thread_with_options(
            StartThreadOptions(
                config=config,
                initial_history=InitialHistory.new(),
                session_source=self._session_source,
                auth_manager=self._auth_manager,
                agent_control=self._agent_control,
                environments=environments,
                user_shell_override=user_shell_override,
            )
        )

    async def resume_thread_from_rollout_with_user_shell_override_for_tests(
        self,
        config: Any,
        rollout_path: str | Path,
        auth_manager: Any = None,
        user_shell_override: Any = None,
    ) -> NewThread:
        """Test-only Rust-shaped rollout resume facade carrying a shell override."""

        initial_history = await self.initial_history_from_rollout_path(rollout_path)
        environments: Sequence[Any] = ()
        cwd = getattr(config, "cwd", None)
        if self._environment_manager is not None and cwd is not None:
            environments = tuple(self.default_environment_selections(cwd))
        return await self.start_thread_with_options(
            StartThreadOptions(
                config=config,
                initial_history=initial_history,
                session_source=self._session_source,
                thread_source=_initial_history_thread_source(initial_history),
                auth_manager=auth_manager if auth_manager is not None else self._auth_manager,
                agent_control=self._agent_control,
                environments=environments,
                user_shell_override=user_shell_override,
            )
        )

    async def fork_thread_from_rollout(
        self,
        snapshot: ForkSnapshot | int,
        config: Any,
        rollout_path: str | Path,
        thread_source: Any = None,
        persist_extended_history: bool = False,
        parent_trace: Any = None,
    ) -> NewThread:
        """Fork a stored thread located by rollout path."""

        initial_history = await self.initial_history_from_rollout_path(rollout_path)
        return await self.fork_thread_from_history(
            snapshot,
            config,
            initial_history,
            thread_source=thread_source,
            persist_extended_history=persist_extended_history,
            parent_trace=parent_trace,
        )

    async def fork_thread(
        self,
        snapshot: ForkSnapshot | int,
        config: Any,
        path: str | Path,
        thread_source: Any = None,
        persist_extended_history: bool = False,
        parent_trace: Any = None,
    ) -> NewThread:
        """Fork an existing thread by snapshotting rollout history."""

        history = await self.initial_history_from_rollout_path(path)
        return await self.fork_thread_from_history(
            ForkSnapshot.from_value(snapshot),
            config,
            history,
            thread_source=thread_source,
            persist_extended_history=persist_extended_history,
            parent_trace=parent_trace,
        )

    async def initial_history_from_rollout_path(self, rollout_path: str | Path) -> InitialHistory:
        """Read a stored thread by rollout path and convert it to resumed history."""

        if self._thread_store is None:
            raise TypeError("thread_store is not configured")
        requested_rollout_path = Path(rollout_path)
        read_by_rollout_path = getattr(self._thread_store, "read_thread_by_rollout_path", None)
        if callable(read_by_rollout_path):
            stored_thread = _call_read_thread_by_rollout_path(read_by_rollout_path, requested_rollout_path)
            return stored_thread_to_initial_history(
                await _maybe_await(stored_thread),
                requested_rollout_path,
            )

        read_by_rollout_path = getattr(self._thread_store, "read_by_rollout_path", None)
        if callable(read_by_rollout_path):
            stored_thread = _call_read_thread_by_rollout_path(read_by_rollout_path, requested_rollout_path)
            return stored_thread_to_initial_history(
                await _maybe_await(stored_thread),
                requested_rollout_path,
            )
        raise TypeError("thread_store does not provide read_thread_by_rollout_path")

    def add_thread(self, new_thread: NewThread) -> None:
        thread_id = str(new_thread.thread_id)
        self._threads[thread_id] = new_thread.thread
        self._thread_metadata.setdefault(thread_id, {})
        self._notify_thread_created(thread_id)

    def notify_thread_created(self, thread_id: str) -> None:
        self._notify_thread_created(str(thread_id))

    def list_thread_ids(self) -> list[str]:
        return [
            thread_id
            for thread_id, thread in self._threads.items()
            if not _thread_session_source_is_internal(thread)
        ]

    def list_live_thread_spawn_edges(self) -> list[tuple[str, str]]:
        """Return live ``(parent_thread_id, child_thread_id)`` spawn edges."""

        edges: list[tuple[str, str]] = []
        for child_thread_id, thread in self._threads.items():
            if _thread_session_source_is_internal(thread):
                continue
            parent_thread_id = _thread_spawn_parent_thread_id(thread)
            if parent_thread_id is None:
                continue
            parent_thread_id = str(parent_thread_id)
            if parent_thread_id in self._threads:
                edges.append((parent_thread_id, child_thread_id))
        return edges

    async def list_live_agent_subtree_thread_ids(self, thread_id: str) -> list[str]:
        """Return live descendant thread ids reachable from ``thread_id``."""

        root_thread_id = str(thread_id)
        self.get_thread(root_thread_id)
        children_by_parent: dict[str, list[str]] = {}
        for parent_thread_id, child_thread_id in self.list_live_thread_spawn_edges():
            children_by_parent.setdefault(parent_thread_id, []).append(child_thread_id)

        subtree_thread_ids: list[str] = []
        seen: set[str] = {root_thread_id}
        queue: list[str] = list(children_by_parent.get(root_thread_id, ()))
        while queue:
            descendant_id = queue.pop(0)
            if descendant_id in seen:
                continue
            seen.add(descendant_id)
            subtree_thread_ids.append(descendant_id)
            queue.extend(children_by_parent.get(descendant_id, ()))
        return subtree_thread_ids

    async def list_agent_subtree_thread_ids(self, thread_id: str) -> list[str]:
        """Return known live agent descendant thread ids for ``thread_id``."""

        root_thread_id = str(thread_id)
        self.get_thread(root_thread_id)
        subtree_thread_ids: list[str] = []
        seen_thread_ids: set[str] = {root_thread_id}
        for descendant_id in await _list_state_thread_spawn_descendants(
            self._state_db,
            root_thread_id,
        ):
            descendant_id = str(descendant_id)
            if descendant_id in seen_thread_ids:
                continue
            seen_thread_ids.add(descendant_id)
            subtree_thread_ids.append(descendant_id)
        for descendant_id in await self.list_live_agent_subtree_thread_ids(root_thread_id):
            descendant_id = str(descendant_id)
            if descendant_id in seen_thread_ids:
                continue
            seen_thread_ids.add(descendant_id)
            subtree_thread_ids.append(descendant_id)
        return subtree_thread_ids

    def get_thread(self, thread_id: str) -> Any:
        thread_id = str(thread_id)
        try:
            thread = self._threads[thread_id]
        except KeyError as exc:
            raise ThreadNotFoundError(thread_id) from exc
        if _thread_session_source_is_internal(thread):
            raise ThreadNotFoundError(thread_id)
        return thread

    async def send_op(self, thread_id: str, op: Any) -> Any:
        thread_id = str(thread_id)
        thread = self.get_thread(thread_id)
        if self._ops_log is not None:
            self._ops_log.append((thread_id, op))
        submit = getattr(thread, "submit", None)
        if not callable(submit):
            raise TypeError(f"thread {thread_id} does not provide submit")
        return await _maybe_await(submit(op))

    def captured_ops(self) -> list[tuple[str, Any]] | None:
        if self._ops_log is None:
            return None
        return list(self._ops_log)

    async def read_stored_thread(
        self,
        thread_id: str,
        *,
        include_archived: bool = True,
        include_history: bool = True,
    ) -> Any:
        thread_id = str(thread_id)
        if self._thread_store is None:
            raise TypeError("thread_store is not configured")
        read_stored_thread = getattr(self._thread_store, "read_stored_thread", None)
        if callable(read_stored_thread):
            try:
                return await _maybe_await(
                    _call_read_thread(
                        read_stored_thread,
                        thread_id,
                        include_archived,
                        include_history,
                    )
                )
            except Exception as exc:
                raise _thread_store_read_error(thread_id, exc) from exc
        read_thread = getattr(self._thread_store, "read_thread", None)
        if callable(read_thread):
            try:
                return await _maybe_await(
                    _call_read_thread(
                        read_thread,
                        thread_id,
                        include_archived,
                        include_history,
                    )
                )
            except Exception as exc:
                raise _thread_store_read_error(thread_id, exc) from exc
        raise TypeError("thread_store does not provide read_stored_thread or read_thread")

    def remove_thread(self, thread_id: str) -> bool:
        thread_id = str(thread_id)
        existed = thread_id in self._threads
        self._threads.pop(thread_id, None)
        self._thread_metadata.pop(thread_id, None)
        return existed

    def update_thread_metadata(self, thread_id: str, metadata: Mapping[str, Any]) -> None:
        thread_id = str(thread_id)
        if thread_id not in self._threads:
            raise ThreadNotFoundError(thread_id)
        self._thread_metadata[thread_id] = dict(metadata)

    async def update_thread_metadata_with_store(
        self,
        thread_id: str,
        patch: Mapping[str, Any],
        include_archived: bool = False,
    ) -> Any:
        """Update metadata for live or stored threads through one entrypoint."""

        thread_id = str(thread_id)
        try:
            thread = self.get_thread(thread_id)
        except ThreadNotFoundError:
            thread = None
        if thread is not None:
            config_snapshot = getattr(thread, "config_snapshot", None)
            if callable(config_snapshot):
                config_snapshot = await _maybe_await(config_snapshot())
            if bool(getattr(config_snapshot, "ephemeral", False)):
                raise CodexErr.invalid_request(
                    f"thread {thread_id} is ephemeral and cannot be updated"
                )
            update_metadata = getattr(thread, "update_thread_metadata", None)
            if callable(update_metadata):
                try:
                    return await _maybe_await(
                        update_metadata(patch, include_archived=include_archived)
                    )
                except TypeError:
                    return await _maybe_await(update_metadata(patch, include_archived))
            self._thread_metadata[thread_id] = {
                **self._thread_metadata.get(thread_id, {}),
                **dict(patch),
            }
            return self.get_thread_metadata(thread_id)

        if self._thread_store is None:
            raise ThreadNotFoundError(thread_id)
        update_metadata = getattr(self._thread_store, "update_thread_metadata", None)
        if callable(update_metadata):
            return await _maybe_await(
                _call_update_thread_metadata(
                    update_metadata,
                    thread_id,
                    patch,
                    include_archived,
                )
            )
        raise TypeError("thread_store does not provide update_thread_metadata")

    def get_thread_metadata(self, thread_id: str) -> dict[str, Any]:
        thread_id = str(thread_id)
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
        for thread_id in report.completed:
            self._threads.pop(thread_id, None)
            self._thread_metadata.pop(thread_id, None)
        report.completed.sort()
        report.submit_failed.sort()
        report.timed_out.sort()
        return report

    async def shutdown_all_threads_bounded(self, timeout: Any) -> ThreadShutdownReport:
        """Rust-named bounded shutdown facade for all managed threads."""

        return await self.shutdown_all(timeout=_timeout_seconds(timeout))

    async def _create_thread(
        self,
        options: StartThreadOptions,
        forked_from_thread_id: str | None = None,
    ) -> NewThread:
        if self._thread_factory is not None:
            result = self._thread_factory(options)
            if inspect.isawaitable(result):
                result = await result
            return _coerce_new_thread(result)

        thread_id = _new_thread_id_from_options(options)
        thread = ManagedThread(
            thread_id=thread_id,
            config=options.config,
            initial_history=_thread_initial_history_value(options.initial_history),
            session_source=options.session_source,
            dynamic_tools=tuple(options.dynamic_tools),
            environments=tuple(options.environments),
        )
        if self._thread_store is not None:
            await _persist_thread_start(
                self._thread_store,
                thread_id,
                options,
                forked_from_id=forked_from_thread_id,
            )
        session_configured = {
            "thread_id": thread_id,
            "config": options.config,
            "initial_history": _thread_initial_history_value(options.initial_history),
            "forked_from_thread_id": forked_from_thread_id,
            "session_source": options.session_source,
            "thread_source": options.thread_source,
            "agent_control": options.agent_control,
            "auth_manager": options.auth_manager,
            "dynamic_tools": tuple(options.dynamic_tools),
            "environments": tuple(options.environments),
            "persist_extended_history": options.persist_extended_history,
            "metrics_service_name": options.metrics_service_name,
            "parent_trace": options.parent_trace,
            "inherited_shell_snapshot": options.inherited_shell_snapshot,
            "inherited_exec_policy": options.inherited_exec_policy,
            "user_shell_override": options.user_shell_override,
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


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _thread_initial_history_value(initial_history: Any) -> Any:
    if initial_history is None:
        return InitialHistory.new()
    if isinstance(initial_history, (InitialHistory, Mapping, str)):
        return InitialHistory.from_mapping(initial_history)
    return tuple(initial_history)


def _new_thread_id_from_options(options: StartThreadOptions) -> str:
    resumed = _resumed_initial_history(options.initial_history)
    if resumed is not None:
        return str(resumed.conversation_id)
    return str(uuid.uuid4())


async def _persist_thread_start(
    thread_store: Any,
    thread_id: str,
    options: StartThreadOptions,
    forked_from_id: str | None,
) -> None:
    history = _initial_history_for_persistence(options.initial_history)
    if history.type == "Resumed" and history.resumed is not None:
        resume_thread = getattr(thread_store, "resume_thread", None)
        if not callable(resume_thread):
            return
        await _maybe_await(_call_resume_thread(resume_thread, thread_id, history.resumed, options))
        return
    create_thread = getattr(thread_store, "create_thread", None)
    if not callable(create_thread):
        return
    await _maybe_await(_call_create_thread(create_thread, thread_id, options, forked_from_id))


def _initial_history_for_persistence(initial_history: Any) -> InitialHistory:
    if initial_history is None:
        return InitialHistory.new()
    if isinstance(initial_history, (InitialHistory, Mapping, str)):
        return InitialHistory.from_mapping(initial_history)
    return InitialHistory.forked(tuple(initial_history))


def _call_create_thread(
    create_thread: Callable[..., Any],
    thread_id: str,
    options: StartThreadOptions,
    forked_from_id: str | None,
) -> Any:
    from pycodex.thread_store import CreateThreadParams

    return create_thread(
        CreateThreadParams(
            thread_id=ThreadId.from_string(str(thread_id)),
            forked_from_id=ThreadId.from_string(str(forked_from_id)) if forked_from_id is not None else None,
            source=options.session_source,
            thread_source=options.thread_source,
            base_instructions=getattr(options.config, "base_instructions", None),
            dynamic_tools=tuple(options.dynamic_tools),
            metadata=_thread_persistence_metadata(options.config),
            event_persistence_mode=_thread_event_persistence_mode(options.persist_extended_history),
        )
    )


def _call_resume_thread(
    resume_thread: Callable[..., Any],
    thread_id: str,
    resumed: Any,
    options: StartThreadOptions,
) -> Any:
    from pycodex.thread_store import ResumeThreadParams

    return resume_thread(
        ResumeThreadParams(
            thread_id=ThreadId.from_string(str(thread_id)),
            rollout_path=getattr(resumed, "rollout_path", None),
            history=tuple(getattr(resumed, "history", ()) or ()),
            include_archived=True,
            metadata=_thread_persistence_metadata(options.config),
            event_persistence_mode=_thread_event_persistence_mode(options.persist_extended_history),
        )
    )


def _thread_persistence_metadata(config: Any) -> Any:
    from pycodex.thread_store import ThreadPersistenceMetadata

    return ThreadPersistenceMetadata(
        cwd=getattr(config, "cwd", None),
        model_provider=_config_model_provider_id(config),
        memory_mode=getattr(config, "memory_mode", None),
    )


def _config_model_provider_id(config: Any) -> str:
    provider_id = getattr(config, "model_provider_id", None)
    if provider_id is not None:
        return str(provider_id)
    provider = getattr(config, "model_provider", None)
    for attr in ("id", "provider_id", "name"):
        value = getattr(provider, attr, None)
        if value is not None:
            return str(value)
    if isinstance(provider, Mapping):
        for key in ("id", "provider_id", "name"):
            value = provider.get(key)
            if value is not None:
                return str(value)
    return str(provider or "")


def _thread_event_persistence_mode(persist_extended_history: bool) -> Any:
    from pycodex.thread_store import ThreadEventPersistenceMode

    return (
        ThreadEventPersistenceMode.EXTENDED
        if persist_extended_history
        else ThreadEventPersistenceMode.LIMITED
    )


def _resumed_initial_history(initial_history: Any) -> Any | None:
    if initial_history is None:
        return None
    history = InitialHistory.from_mapping(initial_history)
    if history.type == "Resumed" and history.resumed is not None:
        return history.resumed
    return None


def _initial_history_thread_source(initial_history: Any) -> Any:
    if initial_history is None:
        return None
    history = InitialHistory.from_mapping(initial_history)
    get_resumed_thread_source = getattr(history, "get_resumed_thread_source", None)
    if callable(get_resumed_thread_source):
        return get_resumed_thread_source()
    resumed = history.resumed if history.type == "Resumed" else None
    if resumed is None:
        return None
    thread_source = getattr(resumed, "thread_source", None)
    if thread_source is not None:
        return thread_source
    return {
        "type": "resumed",
        "conversation_id": str(resumed.conversation_id),
    }


async def _thread_is_running(thread: Any) -> bool:
    is_running = getattr(thread, "is_running", None)
    if callable(is_running):
        return bool(await _maybe_await(is_running()))
    if is_running is not None:
        return bool(is_running)
    return True


def _thread_rollout_path(thread: Any) -> Path | None:
    rollout_path = getattr(thread, "rollout_path", None)
    if callable(rollout_path):
        rollout_path = rollout_path()
    return Path(rollout_path) if rollout_path is not None else None


def _thread_session_configured(thread: Any) -> Any:
    session_configured = getattr(thread, "session_configured", None)
    if callable(session_configured):
        return session_configured()
    return session_configured


def _thread_session_source_is_internal(thread: Any) -> bool:
    session_source = getattr(thread, "session_source", None)
    if callable(session_source):
        session_source = session_source()
    is_internal = getattr(session_source, "is_internal", None)
    if callable(is_internal):
        return bool(is_internal())
    if is_internal is not None:
        return bool(is_internal)
    if isinstance(session_source, Mapping):
        return bool(session_source.get("is_internal"))
    return False


def _thread_spawn_parent_thread_id(thread: Any) -> str | None:
    session_source = getattr(thread, "session_source", None)
    if callable(session_source):
        session_source = session_source()
    parent_thread_id = _field_or_item(session_source, "parent_thread_id")
    if parent_thread_id is not None and _session_source_is_thread_spawn(session_source):
        return str(parent_thread_id)
    for source_field in ("source", "subagent_source", "sub_agent_source"):
        subagent_source = _field_or_item(session_source, source_field)
        parent_thread_id = _field_or_item(subagent_source, "parent_thread_id")
        if parent_thread_id is not None and _session_source_is_thread_spawn(subagent_source):
            return str(parent_thread_id)
    return None


def _thread_spawn_session_source(parent_thread_id: str) -> dict[str, Any]:
    return {
        "type": "subagent",
        "source": {
            "type": "thread_spawn",
            "parent_thread_id": str(parent_thread_id),
        },
    }


def _session_source_is_thread_spawn(value: Any) -> bool:
    kind = _field_or_item(value, "type")
    if kind is None:
        kind = _field_or_item(value, "kind")
    variant = _field_or_item(value, "variant")
    text = " ".join(str(item).lower() for item in (kind, variant, value.__class__.__name__) if item is not None)
    return "threadspawn" in text.replace("_", "") or "thread spawn" in text or "thread_spawn" in text


def _field_or_item(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _timeout_seconds(timeout: Any) -> float | None:
    if timeout is None:
        return None
    total_seconds = getattr(timeout, "total_seconds", None)
    if callable(total_seconds):
        return float(total_seconds())
    return float(timeout)


def _call_read_thread_by_rollout_path(read_by_rollout_path: Callable[..., Any], rollout_path: Path) -> Any:
    try:
        from pycodex.thread_store import ReadThreadByRolloutPathParams

        return read_by_rollout_path(
            ReadThreadByRolloutPathParams(
                rollout_path=rollout_path,
                include_archived=True,
                include_history=True,
            )
        )
    except TypeError:
        pass
    try:
        return read_by_rollout_path(
            rollout_path,
            include_archived=True,
            include_history=True,
        )
    except TypeError:
        return read_by_rollout_path(rollout_path, True, True)


def _call_read_thread(
    read_thread: Callable[..., Any],
    thread_id: str,
    include_archived: bool,
    include_history: bool,
) -> Any:
    try:
        from pycodex.thread_store import ReadThreadParams

        return read_thread(
            ReadThreadParams(
                thread_id=ThreadId.from_string(str(thread_id)),
                include_archived=include_archived,
                include_history=include_history,
            )
        )
    except TypeError:
        pass
    try:
        return read_thread(
            thread_id,
            include_archived=include_archived,
            include_history=include_history,
        )
    except TypeError:
        return read_thread(thread_id, include_archived, include_history)


def _call_update_thread_metadata(
    update_metadata: Callable[..., Any],
    thread_id: str,
    patch: Mapping[str, Any],
    include_archived: bool,
) -> Any:
    try:
        from pycodex.thread_store import ThreadMetadataPatch, UpdateThreadMetadataParams

        patch_value = patch if isinstance(patch, ThreadMetadataPatch) else ThreadMetadataPatch(**dict(patch))
        return update_metadata(
            UpdateThreadMetadataParams(
                thread_id=ThreadId.from_string(str(thread_id)),
                patch=patch_value,
                include_archived=include_archived,
            )
        )
    except TypeError:
        pass
    try:
        return update_metadata(
            thread_id,
            patch,
            include_archived=include_archived,
        )
    except TypeError:
        return update_metadata(thread_id, patch, include_archived)


def _thread_store_read_error(thread_id: str, err: Exception) -> CodexErr:
    kind = getattr(err, "kind", None)
    fields = getattr(err, "fields", {})
    if kind == "thread_not_found":
        missing_id = fields.get("thread_id", thread_id) if isinstance(fields, Mapping) else thread_id
        return CodexErr.thread_not_found(str(missing_id))
    if kind == "invalid_request":
        message = fields.get("message", str(err)) if isinstance(fields, Mapping) else str(err)
        if str(message).startswith("no rollout found for thread id "):
            return CodexErr.thread_not_found(str(thread_id))
        return CodexErr.fatal(
            f"failed to read stored thread {thread_id}: invalid thread-store request: {message}"
        )
    return CodexErr.fatal(f"failed to read stored thread {thread_id}: {err}")


async def _apply_resumed_thread_runtime_effects(thread: Any) -> None:
    emit_resume_lifecycle = getattr(thread, "emit_thread_resume_lifecycle", None)
    if callable(emit_resume_lifecycle):
        await _maybe_await(emit_resume_lifecycle())
    apply_goal_resume = getattr(thread, "apply_goal_resume_runtime_effects", None)
    if callable(apply_goal_resume):
        await _maybe_await(apply_goal_resume())


async def _list_state_thread_spawn_descendants(state_db: Any, thread_id: str) -> list[str]:
    if state_db is None:
        return []
    list_descendants = getattr(state_db, "list_thread_spawn_descendants_with_status", None)
    if not callable(list_descendants):
        return []
    descendants: list[str] = []
    for status in ("completed", "failed", "cancelled"):
        result = list_descendants(thread_id, status)
        for descendant_id in await _maybe_await(result) or ():
            descendants.append(str(descendant_id))
    return descendants


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


def truncate_before_nth_user_message(
    history: InitialHistory | Mapping[str, Any] | str,
    n: int,
    snapshot_state: SnapshotTurnState,
) -> InitialHistory:
    """Return a fork snapshot cut strictly before the nth user message."""

    history = InitialHistory.from_mapping(history)
    items = list(history.get_rollout_items())
    user_positions = user_message_positions_in_rollout(items)
    if snapshot_state.ends_mid_turn and n >= len(user_positions):
        cut_idx = snapshot_state.active_turn_start_index
        if cut_idx is None and user_positions:
            cut_idx = user_positions[-1]
        rolled = items[:cut_idx] if cut_idx is not None else items
    else:
        rolled = truncate_rollout_before_nth_user_message_from_start(items, n)
    return InitialHistory.new() if not rolled else InitialHistory.forked(rolled)


def snapshot_turn_state(history: InitialHistory | Mapping[str, Any] | str) -> SnapshotTurnState:
    """Infer whether persisted history ends inside an active turn."""

    history = InitialHistory.from_mapping(history)
    rollout_items = list(history.get_rollout_items())
    active_turn_id: str | None = None
    active_turn_start_index: int | None = None
    for idx, item in enumerate(rollout_items):
        event = _event_msg_from_rollout_item(item)
        if event is None:
            continue
        event_type = event.type
        if event_type in {"turn_started", "task_started"}:
            active_turn_id = _event_turn_id(event)
            active_turn_start_index = idx
            continue
        if event_type in {"turn_complete", "task_complete", "turn_aborted", "task_aborted"}:
            active_turn_id = None
            active_turn_start_index = None

    if active_turn_id is not None:
        return SnapshotTurnState(
            ends_mid_turn=True,
            active_turn_id=active_turn_id,
            active_turn_start_index=active_turn_start_index,
        )

    user_positions = user_message_positions_in_rollout(rollout_items)
    if not user_positions:
        return SnapshotTurnState(False)
    last_user_position = user_positions[-1]
    has_terminating_boundary = any(
        _is_turn_terminal_event(item) for item in rollout_items[last_user_position + 1 :]
    )
    return SnapshotTurnState(ends_mid_turn=not has_terminating_boundary)


def fork_history_from_snapshot(
    snapshot: ForkSnapshot | int,
    history: InitialHistory | Mapping[str, Any] | str,
    interrupted_marker: InterruptedTurnHistoryMarker | str = InterruptedTurnHistoryMarker.CONTEXTUAL_USER,
) -> InitialHistory:
    """Derive fork history using Rust's ``ForkSnapshot`` semantics."""

    snapshot = ForkSnapshot.from_value(snapshot)
    history = InitialHistory.from_mapping(history)
    snapshot_state = snapshot_turn_state(history)
    if snapshot.kind is ForkSnapshotKind.TRUNCATE_BEFORE_NTH_USER_MESSAGE:
        nth = snapshot.nth_user_message
        if nth is None:
            raise ValueError("truncate snapshot requires nth_user_message")
        return truncate_before_nth_user_message(history, nth, snapshot_state)

    if history.type in {"New", "Cleared"}:
        forkable = history
    elif history.type == "Forked":
        forkable = InitialHistory.forked(history.items)
    elif history.type == "Resumed" and history.resumed is not None:
        forkable = InitialHistory.forked(history.resumed.history)
    else:
        raise ValueError(f"unknown initial history variant: {history.type}")

    if snapshot_state.ends_mid_turn:
        return append_interrupted_boundary(
            forkable,
            snapshot_state.active_turn_id,
            interrupted_marker,
        )
    return forkable


def append_interrupted_boundary(
    history: InitialHistory | Mapping[str, Any] | str,
    turn_id: str | None,
    interrupted_marker: InterruptedTurnHistoryMarker | str,
) -> InitialHistory:
    """Append the persisted interrupt boundary used by live interruption."""

    history = InitialHistory.from_mapping(history)
    aborted_event = RolloutItem.event_msg(
        EventMsg.with_payload(
            "turn_aborted",
            TurnAbortedEvent(
                turn_id=turn_id,
                reason=TurnAbortReason.INTERRUPTED,
                completed_at=None,
                duration_ms=None,
            ),
        )
    )
    items: list[RolloutItem] = []
    if history.type == "Forked":
        items.extend(history.items)
    elif history.type == "Resumed" and history.resumed is not None:
        items.extend(history.resumed.history)
    marker = interrupted_turn_history_marker(interrupted_marker)
    if marker is not None:
        items.append(RolloutItem.response_item(marker))
    items.append(aborted_event)
    return InitialHistory.forked(items)


def _event_msg_from_rollout_item(item: RolloutItem | Mapping[str, Any]) -> EventMsg | None:
    rollout_item = item if isinstance(item, RolloutItem) else RolloutItem.from_mapping(item)
    if rollout_item.type != "event_msg":
        return None
    return rollout_item.payload if isinstance(rollout_item.payload, EventMsg) else EventMsg.from_mapping(rollout_item.payload)


def _event_turn_id(event: EventMsg) -> str | None:
    payload = event.payload
    value = getattr(payload, "turn_id", None)
    if value is None and isinstance(payload, Mapping):
        value = payload.get("turn_id")
    return str(value) if value is not None else None


def _is_turn_terminal_event(item: RolloutItem | Mapping[str, Any]) -> bool:
    event = _event_msg_from_rollout_item(item)
    return event is not None and event.type in {"turn_complete", "task_complete", "turn_aborted", "task_aborted"}


__all__ = [
    "THREAD_CREATED_CHANNEL_CAPACITY",
    "ForkSnapshot",
    "ForkSnapshotKind",
    "ManagedThread",
    "NewThread",
    "SnapshotTurnState",
    "StartThreadOptions",
    "StoredThread",
    "StoredThreadHistory",
    "ThreadFactory",
    "ThreadManager",
    "ThreadNotFoundError",
    "ThreadShutdownReport",
    "ThreadStoreError",
    "append_interrupted_boundary",
    "build_models_manager",
    "fork_history_from_snapshot",
    "set_thread_manager_test_mode_for_tests",
    "should_use_test_thread_manager_behavior",
    "snapshot_turn_state",
    "stored_thread_to_initial_history",
    "thread_store_from_config",
    "thread_store_metadata_update_error",
    "thread_store_rollout_read_error",
    "truncate_before_nth_user_message",
]

