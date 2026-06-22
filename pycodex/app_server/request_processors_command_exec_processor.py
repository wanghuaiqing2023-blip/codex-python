"""Command exec request processor projection.

Ported from ``codex-app-server/src/request_processors/command_exec_processor.rs``.
The Rust module owns request-level validation and dependency assembly for
``command/exec`` before delegating process control to ``CommandExecManager``.
Python keeps actual exec request construction, network proxy startup, and
runtime process execution injectable at this boundary.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.command_exec import (
    DEFAULT_OUTPUT_BYTES_CAP,
    CommandExecError,
    CommandExecManager,
    StartCommandExecParams,
    terminal_size_from_protocol,
)
from pycodex.app_server.error_code import internal_error, invalid_params, invalid_request
from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server_protocol import (
    CommandExecParams,
    CommandExecResizeParams,
    CommandExecResizeResponse,
    CommandExecTerminateParams,
    CommandExecTerminateResponse,
    CommandExecWriteParams,
    CommandExecWriteResponse,
    JSONRPCErrorError,
)

JsonValue = Any


class CommandExecRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class ConfigOverridesProjection:
    cwd: Path
    default_permissions: str
    fallback_cwd: Path


@dataclass(frozen=True)
class ExecExpirationProjection:
    kind: str
    timeout_ms: int | None = None


@dataclass(frozen=True)
class ExecOneOffCommandProjection:
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    expiration: ExecExpirationProjection
    capture_policy: str
    output_bytes_cap: int | None
    sandbox_cwd: Path
    effective_permission_profile: Any
    network_proxy: Any
    tty: bool
    stream_stdin: bool
    stream_stdout_stderr: bool
    size: Any


class CommandExecRequestProcessor:
    def __init__(
        self,
        arg0_paths: Any,
        config: Any,
        outgoing: Any,
        config_manager: Any,
        environment_manager: Any,
        *,
        command_exec_manager: CommandExecManager | None = None,
        env_provider: Any = None,
        exec_request_builder: Any = None,
    ) -> None:
        self.arg0_paths = arg0_paths
        self.config = config
        self.outgoing = outgoing
        self.config_manager = config_manager
        self.environment_manager = environment_manager
        self.command_exec_manager = command_exec_manager or CommandExecManager()
        self.env_provider = env_provider
        self.exec_request_builder = exec_request_builder

    @classmethod
    def new(
        cls,
        arg0_paths: Any,
        config: Any,
        outgoing: Any,
        config_manager: Any,
        environment_manager: Any,
    ) -> "CommandExecRequestProcessor":
        return cls(arg0_paths, config, outgoing, config_manager, environment_manager)

    async def one_off_command_exec(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecParams | Mapping[str, JsonValue],
    ) -> None:
        self.require_local_environment()
        await self.exec_one_off_command(request_id, _params(CommandExecParams, params))
        return None

    async def command_exec_write(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecWriteParams | Mapping[str, JsonValue],
    ) -> CommandExecWriteResponse:
        try:
            return await self.command_exec_manager.write(request_id, _params(CommandExecWriteParams, params))
        except CommandExecError as exc:
            raise CommandExecRequestProcessorError(exc.error) from exc

    async def command_exec_resize(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecResizeParams | Mapping[str, JsonValue],
    ) -> CommandExecResizeResponse:
        try:
            return await self.command_exec_manager.resize(request_id, _params(CommandExecResizeParams, params))
        except CommandExecError as exc:
            raise CommandExecRequestProcessorError(exc.error) from exc

    async def command_exec_terminate(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecTerminateParams | Mapping[str, JsonValue],
    ) -> CommandExecTerminateResponse:
        try:
            return await self.command_exec_manager.terminate(request_id, _params(CommandExecTerminateParams, params))
        except CommandExecError as exc:
            raise CommandExecRequestProcessorError(exc.error) from exc

    async def connection_closed(self, connection_id: Any) -> None:
        await self.command_exec_manager.connection_closed(connection_id)

    def require_local_environment(self) -> None:
        local = _optional_call(self.environment_manager, "try_local_environment")
        if local is None:
            raise CommandExecRequestProcessorError(internal_error("local environment is not configured"))

    async def exec_one_off_command(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecParams,
    ) -> ExecOneOffCommandProjection:
        return await self.exec_one_off_command_inner(request_id, params)

    async def exec_one_off_command_inner(
        self,
        request_id: ConnectionRequestId,
        params: CommandExecParams,
    ) -> ExecOneOffCommandProjection:
        projection = await self.build_one_off_projection(params)
        exec_request = await self._build_exec_request(projection)
        try:
            await self.command_exec_manager.start(
                StartCommandExecParams(
                    request_id=request_id,
                    command=projection.command,
                    process_id=params.process_id,
                    sandbox=exec_request,
                    tty=params.tty,
                    stream_stdin=params.stream_stdin,
                    stream_stdout_stderr=params.stream_stdout_stderr,
                    output_bytes_cap=projection.output_bytes_cap,
                )
            )
        except CommandExecError as exc:
            raise CommandExecRequestProcessorError(exc.error) from exc
        return projection

    async def build_one_off_projection(self, params: CommandExecParams) -> ExecOneOffCommandProjection:
        if not params.command:
            raise CommandExecRequestProcessorError(invalid_request("command must not be empty"))
        if params.sandbox_policy is not None and params.permission_profile is not None:
            raise CommandExecRequestProcessorError(
                invalid_request("`permissionProfile` cannot be combined with `sandboxPolicy`")
            )
        if params.size is not None and not params.tty:
            raise CommandExecRequestProcessorError(invalid_params("command/exec size requires tty: true"))
        if params.disable_output_cap and params.output_bytes_cap is not None:
            raise CommandExecRequestProcessorError(
                invalid_params("command/exec cannot set both outputBytesCap and disableOutputCap")
            )
        if params.disable_timeout and params.timeout_ms is not None:
            raise CommandExecRequestProcessorError(
                invalid_params("command/exec cannot set both timeoutMs and disableTimeout")
            )
        if params.timeout_ms is not None and params.timeout_ms < 0:
            raise CommandExecRequestProcessorError(
                invalid_params(f"command/exec timeoutMs must be non-negative, got {params.timeout_ms}")
            )

        cwd = _command_cwd(_config_cwd(self.config), params.cwd)
        env = self._create_env()
        if params.env is not None:
            for key, value in params.env.items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value

        output_bytes_cap = None if params.disable_output_cap else params.output_bytes_cap or DEFAULT_OUTPUT_BYTES_CAP
        expiration = _expiration(params.disable_timeout, params.timeout_ms)
        capture_policy = "FullBuffer" if params.disable_output_cap else "ShellTool"
        sandbox_cwd = cwd if params.permission_profile is not None else _config_cwd(self.config)
        effective_permission_profile, network_spec, network_profile, managed_network = await self._permission_branch(
            params,
            cwd,
            sandbox_cwd,
        )
        network_proxy = await self._start_network_proxy(network_spec, network_profile, managed_network)
        size = None
        if params.size is not None:
            try:
                size = terminal_size_from_protocol(params.size)
            except CommandExecError as exc:
                raise CommandExecRequestProcessorError(exc.error) from exc

        return ExecOneOffCommandProjection(
            command=params.command,
            cwd=cwd,
            env=env,
            expiration=expiration,
            capture_policy=capture_policy,
            output_bytes_cap=output_bytes_cap,
            sandbox_cwd=sandbox_cwd,
            effective_permission_profile=effective_permission_profile,
            network_proxy=network_proxy,
            tty=params.tty,
            stream_stdin=params.stream_stdin,
            stream_stdout_stderr=params.stream_stdout_stderr,
            size=size,
        )

    def _create_env(self) -> dict[str, str]:
        if self.env_provider is not None:
            return dict(self.env_provider(self.config))
        provider = _callable(self.config, "create_env")
        if provider is not None:
            return dict(provider())
        value = _get(self.config, "env", default={})
        return dict(value or {})

    async def _permission_branch(
        self,
        params: CommandExecParams,
        cwd: Path,
        sandbox_cwd: Path,
    ) -> tuple[Any, Any, Any, bool]:
        permissions = _get(self.config, "permissions", default={})
        if params.permission_profile is not None:
            overrides = ConfigOverridesProjection(
                cwd=cwd,
                default_permissions=params.permission_profile,
                fallback_cwd=_config_cwd(self.config),
            )
            try:
                config = await _maybe_await(_call(self.config_manager, "load_for_cwd", None, overrides, overrides.fallback_cwd))
            except Exception as exc:
                raise CommandExecRequestProcessorError(invalid_request(f"invalid permission profile: {exc}")) from exc
            for warning in _get(config, "startup_warnings", default=()):
                if "Configured value for `permission_profile` is disallowed" in str(warning):
                    raise CommandExecRequestProcessorError(
                        invalid_request(f"invalid permission profile: {warning}")
                    )
            return _permission_tuple(config)

        if params.sandbox_policy is not None:
            checker = _callable(permissions, "can_set_legacy_sandbox_policy")
            if checker is not None:
                try:
                    checker(params.sandbox_policy, sandbox_cwd)
                except Exception as exc:
                    raise CommandExecRequestProcessorError(invalid_request(f"invalid sandbox policy: {exc}")) from exc
            profile = _legacy_permission_profile(params.sandbox_policy, sandbox_cwd)
            profile_checker = _callable(permissions, "can_set_permission_profile")
            if profile_checker is not None:
                try:
                    profile_checker(profile)
                except Exception as exc:
                    raise CommandExecRequestProcessorError(invalid_request(f"invalid sandbox policy: {exc}")) from exc
            return (
                profile,
                _get(permissions, "network", default=None),
                _permission_profile(permissions),
                _managed_network_requirements_enabled(self.config),
            )

        return _permission_tuple(self.config)

    async def _start_network_proxy(self, spec: Any, permission_profile: Any, managed_enabled: bool) -> Any:
        if spec is None:
            return None
        starter = _callable(spec, "start_proxy")
        if starter is None:
            return spec
        try:
            return await _maybe_await(starter(permission_profile, None, None, managed_enabled, {}))
        except Exception as exc:
            raise CommandExecRequestProcessorError(
                internal_error(f"failed to start managed network proxy: {exc}")
            ) from exc

    async def _build_exec_request(self, projection: ExecOneOffCommandProjection) -> Any:
        if self.exec_request_builder is None:
            return _get(projection.effective_permission_profile, "sandbox", default=None)
        try:
            return await _maybe_await(self.exec_request_builder(projection, self.arg0_paths, self.config))
        except Exception as exc:
            raise CommandExecRequestProcessorError(internal_error(f"exec failed: {exc}")) from exc


def _expiration(disable_timeout: bool, timeout_ms: int | None) -> ExecExpirationProjection:
    if disable_timeout:
        return ExecExpirationProjection("Cancellation")
    if timeout_ms is not None:
        return ExecExpirationProjection("Timeout", timeout_ms=timeout_ms)
    return ExecExpirationProjection("DefaultTimeout")


def _permission_tuple(config: Any) -> tuple[Any, Any, Any, bool]:
    permissions = _get(config, "permissions", default={})
    return (
        _effective_permission_profile(permissions),
        _get(permissions, "network", default=None),
        _permission_profile(permissions),
        _managed_network_requirements_enabled(config),
    )


def _effective_permission_profile(permissions: Any) -> Any:
    getter = _callable(permissions, "effective_permission_profile")
    if getter is not None:
        return getter()
    return _get(permissions, "effective_permission_profile", default=_permission_profile(permissions))


def _permission_profile(permissions: Any) -> Any:
    getter = _callable(permissions, "permission_profile")
    if getter is not None:
        return getter()
    return _get(permissions, "permission_profile", default=None)


def _legacy_permission_profile(policy: Any, sandbox_cwd: Path) -> dict[str, Any]:
    return {"legacy_sandbox_policy": policy, "sandbox_cwd": sandbox_cwd}


def _managed_network_requirements_enabled(config: Any) -> bool:
    getter = _callable(config, "managed_network_requirements_enabled")
    if getter is not None:
        return bool(getter())
    return bool(_get(config, "managed_network_requirements_enabled", default=False))


def _config_cwd(config: Any) -> Path:
    return Path(_get(config, "cwd", default=Path.cwd()))


def _command_cwd(config_cwd: Path, cwd: str | Path | None) -> Path:
    if cwd is None:
        return config_cwd
    path = Path(cwd)
    return path if path.is_absolute() else config_cwd / path


def _params(cls: type, value: Any) -> Any:
    if isinstance(value, cls):
        return value
    if isinstance(value, Mapping):
        return cls.from_mapping(value)
    return value


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _optional_call(obj: Any, name: str, *args: Any) -> Any:
    method = _callable(obj, name)
    if method is None:
        return None
    return method(*args)


def _call(obj: Any, name: str, *args: Any) -> Any:
    method = _callable(obj, name)
    if method is None:
        raise AttributeError(name)
    return method(*args)


def _callable(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    value = getattr(obj, name, None)
    return value if callable(value) else None


def _get(obj: Any, name: str, *, default: Any = ...):
    if isinstance(obj, Mapping):
        if name in obj:
            return obj[name]
        camel = _snake_to_camel(name)
        if camel in obj:
            return obj[camel]
    elif hasattr(obj, name):
        return getattr(obj, name)
    if default is not ...:
        return default
    raise AttributeError(name)


def _snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


__all__ = [
    "CommandExecRequestProcessor",
    "CommandExecRequestProcessorError",
    "ConfigOverridesProjection",
    "ExecExpirationProjection",
    "ExecOneOffCommandProjection",
]
