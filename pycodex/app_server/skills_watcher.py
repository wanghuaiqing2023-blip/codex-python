"""Skills watcher projections for ``codex-app-server/src/skills_watcher.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from inspect import isawaitable
from pathlib import Path
from typing import Any

from pycodex.app_server_protocol import ServerNotification, SkillsChangedNotification
from pycodex.core.skills import SkillsLoadInput

JsonValue = Any

WATCHER_THROTTLE_INTERVAL_SECONDS = 10
WATCHER_THROTTLE_INTERVAL_TEST_SECONDS = 0.05


@dataclass(frozen=True)
class WatchPathProjection:
    path: Path
    recursive: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if not isinstance(self.recursive, bool):
            raise TypeError("recursive must be a bool")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": str(self.path), "recursive": self.recursive}


@dataclass(frozen=True)
class WatchRegistrationProjection:
    paths: tuple[WatchPathProjection, ...] = ()

    @classmethod
    def default(cls) -> "WatchRegistrationProjection":
        return cls(())

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"paths": [path.to_mapping() for path in self.paths]}


@dataclass(frozen=True)
class SkillsWatcherProjection:
    file_watcher_kind: str
    subscriber_registered: bool
    event_loop_spawned: bool
    shutdown_token_created: bool
    shutdown_drop_guard_created: bool
    warning: str | None = None


@dataclass(frozen=True)
class RegisterThreadConfigProjection:
    registration: WatchRegistrationProjection
    reason: str
    warning: str | None = None
    skills_input: SkillsLoadInput | None = None
    environment_id: str | None = None


@dataclass(frozen=True)
class SkillsWatcherEventProjection:
    actions: tuple[str, ...]
    notification: ServerNotification | None = None


def skills_watcher_new_projection(*, file_watcher_error: str | None = None, tokio_runtime_available: bool = True) -> SkillsWatcherProjection:
    """Project Rust ``SkillsWatcher::new`` watcher fallback and spawn setup."""

    file_watcher_kind = "noop" if file_watcher_error else "real"
    return SkillsWatcherProjection(
        file_watcher_kind=file_watcher_kind,
        subscriber_registered=True,
        event_loop_spawned=tokio_runtime_available,
        shutdown_token_created=True,
        shutdown_drop_guard_created=True,
        warning=None if file_watcher_error is None else f"failed to initialize skills file watcher: {file_watcher_error}",
    )


def shutdown_projection() -> tuple[str, ...]:
    return ("cancel_shutdown_token",)


async def register_thread_config(
    config: Any,
    thread_manager: Any,
    environments: Iterable[Any],
) -> RegisterThreadConfigProjection:
    """Mirror Rust's local register-thread-config branch with duck-typed facades."""

    environments_tuple = tuple(environments)
    if not environments_tuple:
        return RegisterThreadConfigProjection(WatchRegistrationProjection.default(), "no_environment_selection")

    environment_id = _field(environments_tuple[0], "environment_id")
    environment = _get_environment(thread_manager, environment_id)
    if environment is None:
        return RegisterThreadConfigProjection(
            WatchRegistrationProjection.default(),
            "unknown_environment",
            warning=f"failed to register skills watcher for unknown environment `{environment_id}`",
            environment_id=str(environment_id),
        )
    if _is_remote_environment(environment):
        return RegisterThreadConfigProjection(
            WatchRegistrationProjection.default(),
            "remote_environment",
            environment_id=str(environment_id),
        )

    plugins_input = _call(config, "plugins_config_input")
    plugins_manager = _call(thread_manager, "plugins_manager")
    plugin_outcome = await _maybe_await(_call(plugins_manager, "plugins_for_config", plugins_input))
    plugin_skill_roots = _effective_plugin_skill_roots(plugin_outcome)
    skills_input = skills_load_input_from_config(config, plugin_skill_roots)
    filesystem = _call(environment, "get_filesystem")
    skills_manager = _call(thread_manager, "skills_manager")
    roots = await _maybe_await(_call(skills_manager, "skill_roots_for_config", skills_input, filesystem))
    registration = WatchRegistrationProjection(watch_paths_from_skill_roots(roots))
    return RegisterThreadConfigProjection(
        registration=registration,
        reason="registered",
        skills_input=skills_input,
        environment_id=str(environment_id),
    )


def skills_load_input_from_config(config: Any, effective_skill_roots: Iterable[Any]) -> SkillsLoadInput:
    return SkillsLoadInput(
        cwd=Path(_field(config, "cwd")),
        effective_skill_roots=tuple(effective_skill_roots),
        config_layer_stack=_field(config, "config_layer_stack"),
        bundled_skills_enabled=bool(_call(config, "bundled_skills_enabled")),
    )


def watch_paths_from_skill_roots(roots: Iterable[Any]) -> tuple[WatchPathProjection, ...]:
    return tuple(
        WatchPathProjection(path=_skill_root_path(root), recursive=True)
        for root in roots
    )


def event_loop_iteration_projection(event: Any) -> SkillsWatcherEventProjection:
    """Project one Rust event-loop iteration after throttled recv returns."""

    if event is None:
        return SkillsWatcherEventProjection(("break",), None)
    notification = ServerNotification("SkillsChanged", SkillsChangedNotification())
    return SkillsWatcherEventProjection(("clear_skills_cache", "send_skills_changed"), notification)


def event_loop_spawn_projection(*, tokio_runtime_available: bool) -> SkillsWatcherEventProjection:
    if tokio_runtime_available:
        return SkillsWatcherEventProjection(("spawn_event_loop",), None)
    return SkillsWatcherEventProjection(("warn_no_tokio_runtime", "return"), None)


def _get_environment(thread_manager: Any, environment_id: Any) -> Any:
    environment_manager = _call(thread_manager, "environment_manager")
    return _call(environment_manager, "get_environment", environment_id)


def _is_remote_environment(environment: Any) -> bool:
    remote = _call_optional(environment, "is_remote")
    if remote is not None:
        return bool(remote)
    return bool(_field(environment, "is_remote"))


def _effective_plugin_skill_roots(plugin_outcome: Any) -> tuple[Any, ...]:
    roots = _call_optional(plugin_outcome, "effective_plugin_skill_roots")
    if roots is None:
        roots = _field(plugin_outcome, "effective_plugin_skill_roots")
    return tuple(roots or ())


def _skill_root_path(root: Any) -> Path:
    path = _field(root, "path")
    if path is None:
        path = root
    return Path(path)


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


def _call(value: Any, name: str, *args: Any) -> Any:
    if value is None:
        return None
    attr = _field(value, name)
    if callable(attr):
        return attr(*args)
    if args:
        raise TypeError(f"{name} is not callable")
    return attr


def _call_optional(value: Any, name: str, *args: Any) -> Any:
    attr = _field(value, name)
    if not callable(attr):
        return None
    return attr(*args)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        camel = _snake_to_camel(name)
        if camel in value:
            return value[camel]
        return None
    return getattr(value, name, None)


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


__all__ = [
    "WATCHER_THROTTLE_INTERVAL_SECONDS",
    "WATCHER_THROTTLE_INTERVAL_TEST_SECONDS",
    "RegisterThreadConfigProjection",
    "SkillsWatcherEventProjection",
    "SkillsWatcherProjection",
    "WatchPathProjection",
    "WatchRegistrationProjection",
    "event_loop_iteration_projection",
    "event_loop_spawn_projection",
    "register_thread_config",
    "shutdown_projection",
    "skills_load_input_from_config",
    "skills_watcher_new_projection",
    "watch_paths_from_skill_roots",
]
