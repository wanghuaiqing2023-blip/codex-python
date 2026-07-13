"""Windows sandbox request processor projection.

Ported from ``codex-app-server/src/request_processors/windows_sandbox_processor.rs``.
The Rust module owns the app-server processor boundary around Windows sandbox
readiness and setup-start requests. Python mirrors the status mapping, immediate
``started: true`` response, setup request construction, and completion
notification shape while keeping concrete Windows setup execution injectable.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server_protocol import (
    ServerNotification,
    WindowsSandboxReadiness,
    WindowsSandboxReadinessResponse,
    WindowsSandboxSetupCompletedNotification,
    WindowsSandboxSetupMode,
    WindowsSandboxSetupStartParams,
    WindowsSandboxSetupStartResponse,
)
from pycodex.core.windows_sandbox import sandbox_setup_is_complete
from pycodex.protocol import WindowsSandboxLevel

JsonValue = Any
ConfigLoader = Callable[[Path], Awaitable[Any] | Any]
SetupRunner = Callable[["WindowsSandboxSetupRequest"], Awaitable[None] | None]
TaskSpawner = Callable[[Awaitable[None]], Any]


@dataclass(frozen=True)
class WindowsSandboxSetupRequest:
    """Minimal core setup request shape assembled by the app-server processor."""

    mode: WindowsSandboxSetupMode
    permission_profile: Any
    permission_profile_cwd: Path
    command_cwd: Path
    env_map: dict[str, str]
    codex_home: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", WindowsSandboxSetupMode.parse(self.mode))
        object.__setattr__(self, "permission_profile_cwd", Path(self.permission_profile_cwd))
        object.__setattr__(self, "command_cwd", Path(self.command_cwd))
        object.__setattr__(self, "codex_home", Path(self.codex_home))
        object.__setattr__(self, "env_map", dict(self.env_map))


class WindowsSandboxRequestProcessor:
    def __init__(
        self,
        outgoing: Any,
        config: Any,
        config_manager: Any,
        *,
        setup_runner: SetupRunner | None = None,
        task_spawner: TaskSpawner | None = None,
        env_map: Mapping[str, str] | None = None,
    ) -> None:
        self.outgoing = outgoing
        self.config = config
        self.config_manager = config_manager
        self._setup_runner = setup_runner or _native_setup_runner
        self._task_spawner = task_spawner or _spawn_task
        self._env_map = dict(os.environ if env_map is None else env_map)

    @classmethod
    def new(cls, outgoing: Any, config: Any, config_manager: Any) -> "WindowsSandboxRequestProcessor":
        return cls(outgoing, config, config_manager)

    async def windows_sandbox_readiness(self) -> WindowsSandboxReadinessResponse:
        return determine_windows_sandbox_readiness(self.config)

    async def windows_sandbox_setup_start(
        self,
        request_id: ConnectionRequestId,
        params: WindowsSandboxSetupStartParams | Mapping[str, JsonValue],
    ) -> None:
        await self.windows_sandbox_setup_start_inner(request_id, _setup_start_params(params))
        return None

    async def windows_sandbox_setup_start_inner(
        self,
        request_id: ConnectionRequestId,
        params: WindowsSandboxSetupStartParams,
    ) -> None:
        await self.outgoing.send_response(request_id, WindowsSandboxSetupStartResponse(started=True))
        self._task_spawner(self._run_setup_task(request_id.connection_id, params))

    async def _run_setup_task(self, connection_id: Any, params: WindowsSandboxSetupStartParams) -> None:
        mode = _core_mode(params.mode)
        command_cwd = Path(params.cwd) if params.cwd is not None else Path(_attr(self.config, "cwd"))
        try:
            derived_config = await _maybe_await(_load_config_for_cwd(self.config_manager, command_cwd))
            setup_request = WindowsSandboxSetupRequest(
                mode=mode,
                permission_profile=_effective_permission_profile(derived_config),
                permission_profile_cwd=Path(_attr(derived_config, "cwd")),
                command_cwd=command_cwd,
                env_map=self._env_map,
                codex_home=Path(_attr(derived_config, "codex_home")),
            )
            await _maybe_await(self._setup_runner(setup_request))
        except Exception as exc:
            notification = WindowsSandboxSetupCompletedNotification(
                mode=_protocol_mode(mode),
                success=False,
                error=str(exc),
            )
        else:
            notification = WindowsSandboxSetupCompletedNotification(
                mode=_protocol_mode(mode),
                success=True,
                error=None,
            )
        await self.outgoing.send_server_notification_to_connections(
            [connection_id],
            ServerNotification("WindowsSandboxSetupCompleted", notification),
        )


def determine_windows_sandbox_readiness(config: Any) -> WindowsSandboxReadinessResponse:
    if sys.platform != "win32":
        return WindowsSandboxReadinessResponse(status=WindowsSandboxReadiness.NOT_CONFIGURED)
    return determine_windows_sandbox_readiness_from_state(
        _windows_sandbox_level_from_config(config),
        sandbox_setup_is_complete(str(_attr(config, "codex_home"))),
    )


def determine_windows_sandbox_readiness_from_state(
    windows_sandbox_level: WindowsSandboxLevel | str,
    sandbox_setup_is_complete_: bool,
) -> WindowsSandboxReadinessResponse:
    level = _windows_sandbox_level(windows_sandbox_level)
    if level is WindowsSandboxLevel.DISABLED:
        status = WindowsSandboxReadiness.NOT_CONFIGURED
    elif level is WindowsSandboxLevel.RESTRICTED_TOKEN:
        status = WindowsSandboxReadiness.READY
    elif sandbox_setup_is_complete_:
        status = WindowsSandboxReadiness.READY
    else:
        status = WindowsSandboxReadiness.UPDATE_REQUIRED
    return WindowsSandboxReadinessResponse(status=status)


def _setup_start_params(params: WindowsSandboxSetupStartParams | Mapping[str, JsonValue]) -> WindowsSandboxSetupStartParams:
    if isinstance(params, WindowsSandboxSetupStartParams):
        return params
    if not isinstance(params, Mapping):
        raise TypeError("WindowsSandboxSetupStartParams mapping must be a mapping")
    return WindowsSandboxSetupStartParams.from_mapping(params)


def _windows_sandbox_level(value: WindowsSandboxLevel | str) -> WindowsSandboxLevel:
    if isinstance(value, WindowsSandboxLevel):
        return value
    return WindowsSandboxLevel.parse(str(value))


def _windows_sandbox_level_from_config(config: Any) -> WindowsSandboxLevel:
    value = _maybe_attr(config, "windows_sandbox_level")
    if value is not None:
        return _windows_sandbox_level(value)
    permissions = _maybe_attr(config, "permissions")
    value = _maybe_attr(permissions, "windows_sandbox_level")
    if value is not None:
        return _windows_sandbox_level(value)
    return WindowsSandboxLevel.DISABLED


def _core_mode(mode: WindowsSandboxSetupMode) -> WindowsSandboxSetupMode:
    if mode is WindowsSandboxSetupMode.ELEVATED:
        return WindowsSandboxSetupMode.ELEVATED
    return WindowsSandboxSetupMode.UNELEVATED


def _protocol_mode(mode: WindowsSandboxSetupMode) -> WindowsSandboxSetupMode:
    if mode is WindowsSandboxSetupMode.ELEVATED:
        return WindowsSandboxSetupMode.ELEVATED
    return WindowsSandboxSetupMode.UNELEVATED


def _load_config_for_cwd(config_manager: Any, cwd: Path) -> Any:
    loader = getattr(config_manager, "load_for_cwd", None)
    if not callable(loader):
        raise TypeError("config_manager must provide load_for_cwd")
    try:
        return loader(None, {"cwd": cwd}, cwd)
    except TypeError:
        return loader(cwd)


def _effective_permission_profile(config: Any) -> Any:
    permissions = _attr(config, "permissions")
    getter = getattr(permissions, "effective_permission_profile", None)
    if callable(getter):
        return getter()
    if isinstance(permissions, Mapping) and "effective_permission_profile" in permissions:
        value = permissions["effective_permission_profile"]
        return value() if callable(value) else value
    return _attr(permissions, "effective_permission_profile")


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


async def _native_setup_runner(request: WindowsSandboxSetupRequest) -> None:
    from pycodex.core.windows_sandbox import (
        WindowsSandboxSetupMode as CoreWindowsSandboxSetupMode,
        WindowsSandboxSetupRequest as CoreWindowsSandboxSetupRequest,
        run_windows_sandbox_setup,
    )

    mode = (
        CoreWindowsSandboxSetupMode.ELEVATED
        if request.mode is WindowsSandboxSetupMode.ELEVATED
        else CoreWindowsSandboxSetupMode.UNELEVATED
    )
    await run_windows_sandbox_setup(
        CoreWindowsSandboxSetupRequest(
            mode=mode,
            permission_profile=request.permission_profile,
            permission_profile_cwd=request.permission_profile_cwd,
            command_cwd=request.command_cwd,
            env_map=request.env_map,
            codex_home=request.codex_home,
        )
    )


def _spawn_task(awaitable: Awaitable[None]) -> asyncio.Task[None]:
    return asyncio.create_task(awaitable)


def _attr(value: Any, name: str) -> Any:
    result = _maybe_attr(value, name)
    if result is None:
        raise AttributeError(name)
    return result


def _maybe_attr(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


__all__ = [
    "WindowsSandboxRequestProcessor",
    "WindowsSandboxSetupRequest",
    "determine_windows_sandbox_readiness",
    "determine_windows_sandbox_readiness_from_state",
]
