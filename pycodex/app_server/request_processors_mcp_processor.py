"""MCP request processor projection.

Ported from ``codex-app-server/src/request_processors/mcp_processor.rs``.
This module owns the app-server JSON-RPC facade for MCP refresh, OAuth login,
status listing, resource reads, and tool calls. Concrete MCP runtime work stays
behind injectable callables so this module can preserve Rust's request/response
contract without implementing the full MCP stack.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server.mcp_refresh import queue_strict_refresh
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    ListMcpServerStatusParams,
    ListMcpServerStatusResponse,
    McpAuthStatus,
    McpResourceReadParams,
    McpResourceReadResponse,
    McpServerOauthLoginCompletedNotification,
    McpServerOauthLoginParams,
    McpServerOauthLoginResponse,
    McpServerRefreshResponse,
    McpServerStatus,
    McpServerStatusDetail,
    McpServerToolCallParams,
    McpServerToolCallResponse,
)

JsonValue = Any
MCP_TOOL_THREAD_ID_META_KEY = "threadId"


class McpRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class McpRuntimeContext:
    environment_manager: Any
    cwd: Path


@dataclass(frozen=True)
class McpServerStatusSnapshot:
    tools_by_server: Mapping[str, Mapping[str, JsonValue]]
    resources: Mapping[str, tuple[JsonValue, ...]]
    resource_templates: Mapping[str, tuple[JsonValue, ...]]
    auth_statuses: Mapping[str, McpAuthStatus | str]
    server_names: tuple[str, ...]


class McpRequestProcessor:
    def __init__(
        self,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        config_manager: Any,
        *,
        queue_refresh: Any = queue_strict_refresh,
        oauth_login: Any | None = None,
        discover_scopes: Any | None = None,
        status_snapshot: Any | None = None,
        read_resource_without_thread: Any | None = None,
    ) -> None:
        self.auth_manager = auth_manager
        self.thread_manager = thread_manager
        self.outgoing = outgoing
        self.config_manager = config_manager
        self.queue_refresh = queue_refresh
        self.oauth_login = oauth_login
        self.discover_scopes = discover_scopes
        self.status_snapshot = status_snapshot
        self.read_resource_without_thread = read_resource_without_thread

    @classmethod
    def new(
        cls,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        config_manager: Any,
        **kwargs: Any,
    ) -> "McpRequestProcessor":
        return cls(auth_manager, thread_manager, outgoing, config_manager, **kwargs)

    async def mcp_server_oauth_login(
        self,
        params: McpServerOauthLoginParams | Mapping[str, JsonValue],
    ) -> McpServerOauthLoginResponse:
        return await self.mcp_server_oauth_login_response(_params(McpServerOauthLoginParams, params))

    async def mcp_server_refresh(self, params: Any = None) -> McpServerRefreshResponse:
        return await self.mcp_server_refresh_response(params)

    async def mcp_server_status_list(
        self,
        request_id: Any,
        params: ListMcpServerStatusParams | Mapping[str, JsonValue],
    ) -> None:
        await self.list_mcp_server_status(request_id, _params(ListMcpServerStatusParams, params))
        return None

    async def mcp_resource_read(
        self,
        request_id: Any,
        params: McpResourceReadParams | Mapping[str, JsonValue],
    ) -> None:
        await self.read_mcp_resource(request_id, _params(McpResourceReadParams, params))
        return None

    async def mcp_server_tool_call(
        self,
        request_id: Any,
        params: McpServerToolCallParams | Mapping[str, JsonValue],
    ) -> None:
        await self.call_mcp_server_tool(request_id, _params(McpServerToolCallParams, params))
        return None

    async def mcp_server_refresh_response(self, _params: Any = None) -> McpServerRefreshResponse:
        try:
            await _maybe_await(self.queue_refresh(self.thread_manager, self.config_manager))
        except Exception as exc:
            raise McpRequestProcessorError(internal_error(f"failed to refresh MCP servers: {exc}")) from exc
        return McpServerRefreshResponse()

    async def load_latest_config(self, fallback_cwd: str | Path | None = None) -> Any:
        try:
            if fallback_cwd is None:
                return await _maybe_await(_call(self.config_manager, "load_latest_config"))
            return await _maybe_await(_call(self.config_manager, "load_latest_config", fallback_cwd))
        except Exception as exc:
            raise McpRequestProcessorError(internal_error(f"failed to reload config: {exc}")) from exc

    async def load_thread(self, thread_id: str) -> tuple[str, Any]:
        try:
            parsed = str(UUID(str(thread_id)))
        except Exception as exc:
            raise McpRequestProcessorError(invalid_request(f"invalid thread id: {exc}")) from exc
        try:
            thread = await _maybe_await(_call(self.thread_manager, "get_thread", parsed))
        except Exception as exc:
            raise McpRequestProcessorError(invalid_request(f"thread not found: {parsed}")) from exc
        return parsed, thread

    async def mcp_server_oauth_login_response(
        self,
        params: McpServerOauthLoginParams,
    ) -> McpServerOauthLoginResponse:
        config = await self.load_latest_config(None)
        configured_servers = await _maybe_await(_call(_call(self.thread_manager, "mcp_manager"), "configured_servers", config))
        server = _field(configured_servers, params.name, None)
        if server is None:
            raise McpRequestProcessorError(invalid_request(f"No MCP server named '{params.name}' found."))

        transport = _field(server, "transport")
        parts = _streamable_http_transport_parts(transport)
        if parts is None:
            raise McpRequestProcessorError(
                invalid_request("OAuth login is only supported for streamable HTTP servers.")
            )

        if params.scopes is None and _field(server, "scopes", None) is None and self.discover_scopes is not None:
            discovered_scopes = await _maybe_await(self.discover_scopes(transport))
        else:
            discovered_scopes = None
        resolved_scopes = resolve_oauth_scopes(params.scopes, _field(server, "scopes", None), discovered_scopes)

        if self.oauth_login is None:
            raise McpRequestProcessorError(internal_error("MCP OAuth login runtime is not configured"))
        try:
            handle = await _maybe_await(
                self.oauth_login(
                    name=params.name,
                    url=parts["url"],
                    credentials_store_mode=_field(config, "mcp_oauth_credentials_store_mode", None),
                    http_headers=parts.get("http_headers"),
                    env_http_headers=parts.get("env_http_headers"),
                    scopes=resolved_scopes,
                    oauth_client_id=_call(server, "oauth_client_id") if callable(_field(server, "oauth_client_id", None)) else _field(server, "oauth_client_id", None),
                    oauth_resource=_field(server, "oauth_resource", None),
                    timeout_secs=params.timeout_secs,
                    callback_port=_field(config, "mcp_oauth_callback_port", None),
                    callback_url=_field(config, "mcp_oauth_callback_url", None),
                )
            )
        except Exception as exc:
            raise McpRequestProcessorError(
                internal_error(f"failed to login to MCP server '{params.name}': {exc}")
            ) from exc

        await self._notify_oauth_completion_when_available(params.name, handle)
        return McpServerOauthLoginResponse(authorization_url=str(_authorization_url(handle)))

    async def list_mcp_server_status(self, request_id: Any, params: ListMcpServerStatusParams) -> None:
        config = await self._config_for_optional_thread(params.thread_id)
        mcp_config = await _maybe_await(_call(config, "to_mcp_config", _call(self.thread_manager, "plugins_manager")))
        auth = await _maybe_await(_call(self.auth_manager, "auth")) if self.auth_manager is not None else None
        runtime_context = McpRuntimeContext(_call(self.thread_manager, "environment_manager"), Path(_field(config, "cwd")))
        if self.status_snapshot is None:
            raise McpRequestProcessorError(internal_error("MCP status snapshot runtime is not configured"))
        snapshot = await _maybe_await(self.status_snapshot(mcp_config, auth, str(_request_id_value(request_id)), runtime_context, _detail(params)))
        result = list_mcp_server_status_response(str(_request_id_value(request_id)), params, snapshot)
        await _send_result(self.outgoing, request_id, result)

    async def read_mcp_resource(self, request_id: Any, params: McpResourceReadParams) -> None:
        if params.thread_id is not None:
            _, thread = await self.load_thread(params.thread_id)
            try:
                result = await _maybe_await(_call(thread, "read_mcp_resource", params.server, params.uri))
            except Exception as exc:
                await _send_result(self.outgoing, request_id, internal_error(str(exc)))
                return
            await send_mcp_resource_read_response(self.outgoing, request_id, result)
            return

        config = await self.load_latest_config(None)
        mcp_config = await _maybe_await(_call(config, "to_mcp_config", _call(self.thread_manager, "plugins_manager")))
        auth = await _maybe_await(_call(self.auth_manager, "auth")) if self.auth_manager is not None else None
        runtime_context = McpRuntimeContext(_call(self.thread_manager, "environment_manager"), Path(_field(config, "cwd")))
        if self.read_resource_without_thread is None:
            raise McpRequestProcessorError(internal_error("MCP resource read runtime is not configured"))
        try:
            result = await _maybe_await(
                self.read_resource_without_thread(mcp_config, auth, runtime_context, params.server, params.uri)
            )
        except Exception as exc:
            await _send_result(self.outgoing, request_id, internal_error(str(exc)))
            return
        await send_mcp_resource_read_response(self.outgoing, request_id, result)

    async def call_mcp_server_tool(self, request_id: Any, params: McpServerToolCallParams) -> None:
        _, thread = await self.load_thread(params.thread_id)
        meta = with_mcp_tool_call_thread_id_meta(params.meta, params.thread_id)
        try:
            result = await _maybe_await(
                _call(thread, "call_mcp_tool", params.server, params.tool, params.arguments, meta)
            )
            response = McpServerToolCallResponse.from_core(result)
        except Exception as exc:
            await _send_result(self.outgoing, request_id, internal_error(str(exc)))
            return
        await _send_result(self.outgoing, request_id, response)

    async def _config_for_optional_thread(self, thread_id: str | None) -> Any:
        if thread_id is None:
            return await self.load_latest_config(None)
        _, thread = await self.load_thread(thread_id)
        thread_config = await _maybe_await(_call(thread, "config"))
        try:
            return await _maybe_await(_call(self.config_manager, "load_latest_config_for_thread", thread_config))
        except Exception as exc:
            raise McpRequestProcessorError(internal_error(f"failed to reload config: {exc}")) from exc

    async def _notify_oauth_completion_when_available(self, name: str, handle: Any) -> None:
        wait = _field(handle, "wait", None)
        if not callable(wait):
            return
        try:
            await _maybe_await(wait())
            notification = McpServerOauthLoginCompletedNotification(name=name, success=True, error=None)
        except Exception as exc:
            notification = McpServerOauthLoginCompletedNotification(name=name, success=False, error=str(exc))
        sender = _field(self.outgoing, "send_server_notification", None)
        if callable(sender):
            await _maybe_await(sender(notification))


def list_mcp_server_status_response(
    _request_id: str,
    params: ListMcpServerStatusParams,
    snapshot: McpServerStatusSnapshot | Mapping[str, JsonValue],
) -> ListMcpServerStatusResponse:
    detail = _detail(params)
    _ = detail
    tools_by_server = _field(snapshot, "tools_by_server", {})
    resources = _field(snapshot, "resources", {})
    resource_templates = _field(snapshot, "resource_templates", {})
    auth_statuses = _field(snapshot, "auth_statuses", {})
    names = set(_field(snapshot, "server_names", ()) or ())
    names.update(str(name) for name in auth_statuses)
    names.update(str(name) for name in resources)
    names.update(str(name) for name in resource_templates)
    server_names = sorted(names)

    total = len(server_names)
    limit = max(params.limit if params.limit is not None else total, 1)
    effective_limit = min(limit, total)
    if params.cursor is None:
        start = 0
    else:
        try:
            start = int(params.cursor)
        except ValueError as exc:
            raise McpRequestProcessorError(invalid_request(f"invalid cursor: {params.cursor}")) from exc
    if start > total:
        raise McpRequestProcessorError(invalid_request(f"cursor {start} exceeds total MCP servers {total}"))

    end = min(start + effective_limit, total)
    data = tuple(
        McpServerStatus(
            name=name,
            tools=dict(_field(tools_by_server, name, {}) or {}),
            resources=tuple(_field(resources, name, ()) or ()),
            resource_templates=tuple(_field(resource_templates, name, ()) or ()),
            auth_status=_field(auth_statuses, name, McpAuthStatus.UNSUPPORTED),
        )
        for name in server_names[start:end]
    )
    next_cursor = str(end) if end < total else None
    return ListMcpServerStatusResponse(data=data, next_cursor=next_cursor)


async def send_mcp_resource_read_response(outgoing: Any, request_id: Any, result: Any) -> None:
    if isinstance(result, JSONRPCErrorError):
        response = result
    else:
        try:
            response = result if isinstance(result, McpResourceReadResponse) else McpResourceReadResponse.from_mapping(result)
        except Exception as exc:
            response = internal_error(f"failed to deserialize MCP resource read response: {exc}")
    await _send_result(outgoing, request_id, response)


def with_mcp_tool_call_thread_id_meta(meta: JsonValue | None, thread_id: str) -> JsonValue | None:
    if meta is None:
        return {MCP_TOOL_THREAD_ID_META_KEY: thread_id}
    if isinstance(meta, Mapping):
        result = dict(meta)
        result[MCP_TOOL_THREAD_ID_META_KEY] = thread_id
        return result
    return meta


def resolve_oauth_scopes(
    requested_scopes: tuple[str, ...] | None,
    server_scopes: tuple[str, ...] | list[str] | None,
    discovered_scopes: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if requested_scopes is not None:
        return tuple(requested_scopes)
    if server_scopes is not None:
        return tuple(server_scopes)
    if discovered_scopes is not None:
        return tuple(discovered_scopes)
    return ()


def _detail(params: ListMcpServerStatusParams) -> str:
    detail = params.detail or McpServerStatusDetail.FULL
    if detail == McpServerStatusDetail.TOOLS_AND_AUTH_ONLY:
        return "ToolsAndAuthOnly"
    return "Full"


def _streamable_http_transport_parts(transport: Any) -> dict[str, Any] | None:
    kind = _field(transport, "type", _field(transport, "kind", None))
    if kind not in {"streamable_http", "streamableHttp", "StreamableHttp"}:
        return None
    return {
        "url": _field(transport, "url"),
        "http_headers": _field(transport, "http_headers", _field(transport, "httpHeaders", {})),
        "env_http_headers": _field(transport, "env_http_headers", _field(transport, "envHttpHeaders", {})),
    }


def _authorization_url(handle: Any) -> Any:
    value = _field(handle, "authorization_url")
    return value() if callable(value) else value


def _params(cls: type, value: Any) -> Any:
    if isinstance(value, cls):
        return value
    if isinstance(value, Mapping):
        return cls.from_mapping(value)
    if value is None:
        return cls.from_mapping(None)
    return cls(**dict(value))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _call(obj: Any, name: str, *args: Any) -> Any:
    target = _field(obj, name, None)
    if target is None or not callable(target):
        raise AttributeError(name)
    return target(*args)


def _field(value: Any, name: str, default: Any = ...):
    if isinstance(value, Mapping):
        if default is ...:
            return value[name]
        return value.get(name, default)
    if default is ...:
        return getattr(value, name)
    return getattr(value, name, default)


def _request_id_value(request_id: Any) -> Any:
    return _field(request_id, "request_id", request_id)


async def _send_result(outgoing: Any, request_id: Any, result: Any) -> None:
    sender = _field(outgoing, "send_result", None)
    if not callable(sender):
        raise AttributeError("send_result")
    await _maybe_await(sender(request_id, result))


__all__ = [
    "MCP_TOOL_THREAD_ID_META_KEY",
    "McpRequestProcessor",
    "McpRequestProcessorError",
    "McpRuntimeContext",
    "McpServerStatusSnapshot",
    "list_mcp_server_status_response",
    "resolve_oauth_scopes",
    "send_mcp_resource_read_response",
    "with_mcp_tool_call_thread_id_meta",
]
