"""Apps request processor ported from ``app-server/src/request_processors/apps_processor.rs``."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server_protocol import (
    AppInfo,
    AppListUpdatedNotification,
    AppsListParams,
    AppsListResponse,
    JSONRPCErrorError,
)
from pycodex.core.connectors import with_app_enabled_state as core_with_app_enabled_state

JsonValue = Any
TaskRunner = Callable[[Any], Any]


@dataclass(frozen=True)
class AccessibleConnectorsStatus:
    connectors: tuple[AppInfo, ...]
    codex_apps_ready: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "connectors", _apps_tuple(self.connectors))
        object.__setattr__(self, "codex_apps_ready", bool(self.codex_apps_ready))


@dataclass
class AppsRequestProcessorError(Exception):
    error: JSONRPCErrorError

    def __post_init__(self) -> None:
        Exception.__init__(self, self.error.message)


@dataclass
class AppsRequestProcessor:
    auth_manager: Any
    thread_manager: Any
    outgoing: Any
    config_manager: Any
    workspace_settings_cache: Any
    shutdown_token: Any
    connector_loader: Any | None = None
    task_runner: TaskRunner | None = None
    shutdown_requested: bool = False

    @classmethod
    def new(
        cls,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        config_manager: Any,
        workspace_settings_cache: Any,
        shutdown_token: Any,
    ) -> "AppsRequestProcessor":
        return cls(
            auth_manager,
            thread_manager,
            outgoing,
            config_manager,
            workspace_settings_cache,
            shutdown_token,
        )

    async def apps_list(
        self,
        request_id: Any,
        params: AppsListParams | Mapping[str, JsonValue] | None = None,
    ) -> AppsListResponse | None:
        parsed = params if isinstance(params, AppsListParams) else AppsListParams.from_mapping(params or {})
        return await self.apps_list_inner(request_id, parsed)

    async def apps_list_inner(self, request_id: Any, params: AppsListParams) -> AppsListResponse | None:
        thread = None
        if params.thread_id is not None:
            _thread_id, thread = await self.load_thread(params.thread_id)

        fallback_cwd = None
        if thread is not None:
            snapshot = await _maybe_await(_call_or_get(thread, "config_snapshot"))
            fallback_cwd = _path_or_none(_get(snapshot, "cwd"))

        config = await self.load_latest_config(fallback_cwd)
        auth = await _maybe_await(_call_or_get(self.auth_manager, "auth"))
        if not _apps_enabled_for_auth(config, auth, thread):
            return AppsListResponse(data=())

        if not await self.workspace_codex_plugins_enabled(config, auth):
            return AppsListResponse(data=())

        coroutine = self.apps_list_task(self.outgoing, request_id, params, config, self._environment_manager())
        if self.task_runner is not None:
            self.task_runner(coroutine)
        else:
            # Rust spawns the load task and returns no immediate payload. Tests can
            # inject a runner to make the task deterministic.
            import asyncio

            asyncio.create_task(coroutine)
        return None

    def shutdown(self) -> None:
        self.shutdown_requested = True
        _call_or_get(self.shutdown_token, "cancel")

    async def apps_list_task(
        self,
        outgoing: Any,
        request_id: Any,
        params: AppsListParams,
        config: Any,
        environment_manager: Any,
    ) -> None:
        retry_params = replace(params)
        result = await self.apps_list_response(outgoing, params, config, environment_manager)
        response, codex_apps_ready = result
        await _send_result(outgoing, request_id, response)

        if not codex_apps_ready and not retry_params.force_refetch:
            retry_params = replace(retry_params, force_refetch=True)
            try:
                await self.apps_list_response(outgoing, retry_params, config, environment_manager)
            except Exception:
                return

    async def apps_list_response(
        self,
        outgoing: Any,
        params: AppsListParams,
        config: Any,
        environment_manager: Any,
    ) -> tuple[AppsListResponse, bool]:
        start = parse_apps_cursor(params.cursor)
        loader = self.connector_loader or NullAppsConnectorLoader()

        accessible_connectors = _optional_apps_tuple(await _call_loader(loader, "cached_accessible", config))
        all_connectors = _optional_apps_tuple(await _call_loader(loader, "cached_all", config))
        cached_all_connectors = all_connectors

        accessible_loaded = False
        all_loaded = False
        codex_apps_ready = True
        last_notified_apps: tuple[AppInfo, ...] | None = None

        if accessible_connectors is not None or all_connectors is not None:
            merged = with_app_enabled_state(merge_loaded_apps(all_connectors, accessible_connectors), config)
            if should_send_app_list_updated_notification(merged, accessible_loaded, all_loaded):
                await send_app_list_updated_notification(outgoing, merged)
                last_notified_apps = merged

        accessible_status = await _call_loader(
            loader,
            "load_accessible",
            config,
            params.force_refetch,
            environment_manager,
        )
        accessible_status = _accessible_status(accessible_status)
        accessible_connectors = accessible_status.connectors
        accessible_loaded = True
        codex_apps_ready = accessible_status.codex_apps_ready

        showing_interim_force_refetch = params.force_refetch and not all_loaded
        all_for_update = cached_all_connectors if showing_interim_force_refetch and cached_all_connectors is not None else all_connectors
        merged = with_app_enabled_state(merge_loaded_apps(all_for_update, accessible_connectors), config)
        if (
            should_send_app_list_updated_notification(merged, accessible_loaded, all_loaded)
            and last_notified_apps != merged
        ):
            await send_app_list_updated_notification(outgoing, merged)
            last_notified_apps = merged

        all_connectors = _apps_tuple(await _call_loader(loader, "load_all", config, params.force_refetch))
        all_loaded = True
        merged = with_app_enabled_state(merge_loaded_apps(all_connectors, accessible_connectors), config)
        if (
            should_send_app_list_updated_notification(merged, accessible_loaded, all_loaded)
            and last_notified_apps != merged
        ):
            await send_app_list_updated_notification(outgoing, merged)

        return paginate_apps(merged, start, params.limit), codex_apps_ready

    async def load_thread(self, thread_id: str) -> tuple[str, Any]:
        parsed = _parse_thread_id(thread_id)
        if parsed is None:
            raise AppsRequestProcessorError(invalid_request("invalid thread id: empty thread id"))
        try:
            thread = await _maybe_await(self.thread_manager.get_thread(parsed))
        except Exception:
            raise AppsRequestProcessorError(invalid_request(f"thread not found: {parsed}"))
        return parsed, thread

    async def load_latest_config(self, fallback_cwd: Path | None) -> Any:
        try:
            return await _maybe_await(self.config_manager.load_latest_config(fallback_cwd))
        except Exception as exc:
            raise AppsRequestProcessorError(internal_error(f"failed to reload config: {exc}"))

    async def workspace_codex_plugins_enabled(self, config: Any, auth: Any | None) -> bool:
        checker = _callable(self.workspace_settings_cache, "codex_plugins_enabled_for_workspace")
        if checker is not None:
            try:
                return bool(await _maybe_await(checker(config, auth)))
            except Exception:
                return True
        checker = _callable(self.workspace_settings_cache, "enabled")
        if checker is not None:
            try:
                return bool(await _maybe_await(checker(config, auth)))
            except Exception:
                return True
        return bool(_get(self.workspace_settings_cache, "enabled", True))

    def _environment_manager(self) -> Any:
        return _call_or_get(self.thread_manager, "environment_manager")


class NullAppsConnectorLoader:
    async def cached_accessible(self, _config: Any) -> tuple[AppInfo, ...] | None:
        return None

    async def cached_all(self, _config: Any) -> tuple[AppInfo, ...] | None:
        return None

    async def load_accessible(
        self,
        _config: Any,
        _force_refetch: bool,
        _environment_manager: Any,
    ) -> AccessibleConnectorsStatus:
        return AccessibleConnectorsStatus(())

    async def load_all(self, _config: Any, _force_refetch: bool) -> tuple[AppInfo, ...]:
        return ()


def merge_loaded_apps(
    all_connectors: Sequence[AppInfo | Mapping[str, JsonValue]] | None,
    accessible_connectors: Sequence[AppInfo | Mapping[str, JsonValue]] | None,
) -> tuple[AppInfo, ...]:
    all_loaded = all_connectors is not None
    all_items = _apps_tuple(all_connectors or ())
    accessible_items = _apps_tuple(accessible_connectors or ())
    if not all_loaded:
        return tuple(_accessible_app(item) for item in accessible_items)

    accessible_by_id = {item.id: _accessible_app(item) for item in accessible_items}
    merged: list[AppInfo] = []
    seen: set[str] = set()
    for item in all_items:
        if item.id in accessible_by_id:
            merged.append(_merge_app_info(item, accessible_by_id[item.id]))
        else:
            merged.append(item)
        seen.add(item.id)
    for item in accessible_by_id.values():
        if item.id not in seen:
            merged.append(item)
    return tuple(merged)


def should_send_app_list_updated_notification(
    connectors: Sequence[AppInfo],
    accessible_loaded: bool,
    all_loaded: bool,
) -> bool:
    return any(connector.is_accessible for connector in connectors) or (accessible_loaded and all_loaded)


def paginate_apps(
    connectors: Sequence[AppInfo],
    start: int,
    limit: int | None,
) -> AppsListResponse:
    total = len(connectors)
    if start > total:
        raise AppsRequestProcessorError(invalid_request(f"cursor {start} exceeds total apps {total}"))
    effective_limit = max(limit if limit is not None else total, 1)
    end = min(start + effective_limit, total)
    next_cursor = str(end) if end < total else None
    return AppsListResponse(data=tuple(connectors[start:end]), next_cursor=next_cursor)


def parse_apps_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        start = int(cursor)
    except ValueError:
        raise AppsRequestProcessorError(invalid_request(f"invalid cursor: {cursor}"))
    if start < 0:
        raise AppsRequestProcessorError(invalid_request(f"invalid cursor: {cursor}"))
    return start


async def send_app_list_updated_notification(outgoing: Any, data: Sequence[AppInfo]) -> None:
    notification = AppListUpdatedNotification(data=tuple(data))
    sender = _callable(outgoing, "send_server_notification")
    if sender is not None:
        await _maybe_await(sender(notification))


def with_app_enabled_state(connectors: Iterable[AppInfo], config: Any) -> tuple[AppInfo, ...]:
    apps_config = _get(config, "apps", _get(config, "apps_config"))
    requirements = _get(config, "requirements_apps_config", _get(config, "apps_requirements"))
    try:
        return tuple(core_with_app_enabled_state(connectors, apps_config, requirements))
    except Exception:
        return tuple(connectors)


def _apps_enabled_for_auth(config: Any, auth: Any | None, thread: Any | None) -> bool:
    features = _get(config, "features")
    thread_enabled = None if thread is None else _call_or_get(thread, "enabled", "apps")
    if thread_enabled is not None:
        _set_feature_enabled(features, "apps", bool(thread_enabled))
    uses_backend = bool(_call_or_get(auth, "uses_codex_backend")) if auth is not None else False
    enabled_for_auth = _call_or_get(features, "apps_enabled_for_auth", uses_backend)
    if enabled_for_auth is not None:
        return bool(enabled_for_auth)
    enabled = _call_or_get(features, "enabled", "apps")
    if enabled is not None:
        return bool(enabled) and uses_backend
    if isinstance(features, Mapping):
        return bool(features.get("apps", False)) and uses_backend
    return bool(_get(config, "apps_enabled", False)) and uses_backend


def _set_feature_enabled(features: Any, name: str, enabled: bool) -> None:
    setter = _callable(features, "set_enabled")
    if setter is not None:
        setter(name, enabled)
    elif isinstance(features, dict):
        features[name] = enabled


async def _send_result(outgoing: Any, request_id: Any, response: AppsListResponse) -> None:
    sender = _callable(outgoing, "send_result")
    if sender is not None:
        await _maybe_await(sender(request_id, response))


async def _call_loader(loader: Any, method: str, *args: Any) -> Any:
    func = _callable(loader, method)
    if func is None:
        if method.startswith("cached_"):
            return None
        return ()
    try:
        return await _maybe_await(func(*args))
    except Exception as exc:
        if method == "load_accessible":
            raise AppsRequestProcessorError(internal_error(f"failed to load accessible apps: {exc}"))
        if method == "load_all":
            raise AppsRequestProcessorError(internal_error(f"failed to list apps: {exc}"))
        return None


def _accessible_status(value: Any) -> AccessibleConnectorsStatus:
    if isinstance(value, AccessibleConnectorsStatus):
        return value
    connectors = _get(value, "connectors", value if value is not None else ())
    ready = _get(value, "codex_apps_ready", True)
    return AccessibleConnectorsStatus(_apps_tuple(connectors), bool(ready))


def _accessible_app(value: AppInfo) -> AppInfo:
    return replace(value, is_accessible=True)


def _merge_app_info(directory: AppInfo, accessible: AppInfo) -> AppInfo:
    return replace(
        directory,
        is_accessible=True,
        plugin_display_names=accessible.plugin_display_names or directory.plugin_display_names,
    )


def _apps_tuple(values: Iterable[AppInfo | Mapping[str, JsonValue]]) -> tuple[AppInfo, ...]:
    return tuple(value if isinstance(value, AppInfo) else AppInfo.from_mapping(value) for value in values)


def _optional_apps_tuple(values: Any) -> tuple[AppInfo, ...] | None:
    if values is None:
        return None
    return _apps_tuple(values)


def _parse_thread_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _path_or_none(value: Any) -> Path | None:
    if value is None:
        return None
    return value if isinstance(value, Path) else Path(value)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _callable(target: Any, name: str) -> Any:
    if target is None:
        return None
    value = _get(target, name)
    return value if callable(value) else None


def _call_or_get(target: Any, name: str, *args: Any) -> Any:
    value = _get(target, name)
    if callable(value):
        return value(*args)
    return value


def _get(target: Any, name: str, default: Any = None) -> Any:
    if target is None:
        return default
    if isinstance(target, Mapping):
        if name in target:
            return target[name]
        camel = _snake_to_camel(name)
        return target.get(camel, default)
    return getattr(target, name, default)


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


__all__ = [
    "AccessibleConnectorsStatus",
    "AppsRequestProcessorError",
    "AppsRequestProcessor",
    "NullAppsConnectorLoader",
    "merge_loaded_apps",
    "paginate_apps",
    "parse_apps_cursor",
    "send_app_list_updated_notification",
    "should_send_app_list_updated_notification",
    "with_app_enabled_state",
]
