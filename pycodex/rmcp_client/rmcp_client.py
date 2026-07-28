"""MCP client lifecycle owned by ``codex-rmcp-client::rmcp_client``."""

from __future__ import annotations

import asyncio
import itertools
import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, TypeAlias

from pycodex.protocol import ElicitationAction

from .in_process_transport import InProcessTransportFactory
from .http_client_adapter import (
    StreamableHttpClientAdapter,
)
from .stdio_server_launcher import (
    StdioServerCommand,
    StdioServerLauncher,
    StdioServerTransport,
)
from .utils import build_default_headers

Elicitation: TypeAlias = Any
SendElicitation: TypeAlias = Callable[
    [Any, Elicitation],
    Awaitable["ElicitationResponse"],
]


@dataclass(frozen=True)
class ElicitationResponse:
    action: ElicitationAction
    content: Any | None = None
    meta: Any | None = None


@dataclass(frozen=True)
class ToolWithConnectorId:
    tool: Any
    connector_id: str | None = None
    connector_name: str | None = None
    connector_description: str | None = None


@dataclass(frozen=True)
class ListToolsWithConnectorIdResult:
    next_cursor: str | None = None
    tools: tuple[ToolWithConnectorId, ...] = ()


def _field(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _meta_string(meta: Any, *keys: str) -> str | None:
    for key in keys:
        value = _field(meta, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            str(key): _json_value(item)
            for key, item in asdict(value).items()
            if item is not None
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class _JsonRpcService:
    """MCP lifecycle adapter corresponding to rmcp ``serve_client``."""

    def __init__(self, transport: StdioServerTransport, client_service: Any) -> None:
        self._transport = transport
        self._client_service = client_service
        self._ids = itertools.count(1)
        self._request_lock = asyncio.Lock()

    async def initialize(self, params: Any) -> Any:
        result = await self._request("initialize", _json_value(params))
        await self.send_custom_notification("notifications/initialized")
        return result

    async def list_tools(self, params: Any = None) -> Any:
        return await self._request("tools/list", _json_value(params or {}))

    async def list_resources(self, params: Any = None) -> Any:
        return await self._request("resources/list", _json_value(params or {}))

    async def list_resource_templates(self, params: Any = None) -> Any:
        return await self._request(
            "resources/templates/list",
            _json_value(params or {}),
        )

    async def read_resource(self, params: Any) -> Any:
        return await self._request("resources/read", _json_value(params))

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None,
        meta: Mapping[str, Any] | None,
    ) -> Any:
        params: dict[str, Any] = {
            "name": str(name),
            "arguments": dict(arguments or {}),
        }
        if meta is not None:
            params["_meta"] = dict(meta)
        return await self._request("tools/call", params)

    async def send_custom_notification(
        self,
        method: str,
        params: Any = None,
    ) -> None:
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": str(method),
        }
        if params is not None:
            message["params"] = _json_value(params)
        await self._transport.send(message)

    async def send_custom_request(self, method: str, params: Any = None) -> Any:
        return await self._request(str(method), _json_value(params or {}))

    async def close(self) -> None:
        await self._transport.close()

    async def _request(self, method: str, params: Any) -> Any:
        async with self._request_lock:
            request_id = next(self._ids)
            await self._transport.send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            while True:
                response = await self._transport.receive()
                if response is None:
                    raise BrokenPipeError(
                        f"MCP transport closed while awaiting {method}"
                    )
                if not isinstance(response, Mapping):
                    continue
                if "method" in response:
                    await self._handle_server_message(response)
                    continue
                if response.get("id") != request_id:
                    continue
                if "error" in response:
                    error = response["error"]
                    raise RuntimeError(f"MCP request {method} failed: {error}")
                return response.get("result")

    async def _handle_server_message(self, message: Mapping[str, Any]) -> None:
        method = str(message.get("method"))
        params = message.get("params", {})
        request_id = message.get("id")
        if request_id is None:
            await self._client_service.handle_notification(method, params)
            return
        context_meta = (
            params.get("_meta", {})
            if isinstance(params, Mapping)
            else {}
        )
        lifted_message = dict(message)
        if isinstance(params, Mapping) and "_meta" in params:
            lifted_message["params"] = {
                key: value
                for key, value in params.items()
                if key != "_meta"
            }
        try:
            result = await self._client_service.handle_request(
                lifted_message,
                request_id=request_id,
                context_meta=context_meta,
            )
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(exc),
                },
            }
        await self._transport.send(response)


class _StreamableHttpRpcService:
    def __init__(
        self,
        adapter: StreamableHttpClientAdapter,
        url: str,
        auth_token: str | None,
    ) -> None:
        self._adapter = adapter
        self._url = str(url)
        self._auth_token = auth_token
        self._session_id: str | None = None
        self._ids = itertools.count(1)
        self._request_lock = asyncio.Lock()

    async def initialize(self, params: Any) -> Any:
        result = await self._request("initialize", _json_value(params))
        await self.send_custom_notification("notifications/initialized")
        return result

    async def list_tools(self, params: Any = None) -> Any:
        return await self._request("tools/list", _json_value(params or {}))

    async def list_resources(self, params: Any = None) -> Any:
        return await self._request("resources/list", _json_value(params or {}))

    async def list_resource_templates(self, params: Any = None) -> Any:
        return await self._request(
            "resources/templates/list",
            _json_value(params or {}),
        )

    async def read_resource(self, params: Any) -> Any:
        return await self._request("resources/read", _json_value(params))

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None,
        meta: Mapping[str, Any] | None,
    ) -> Any:
        params: dict[str, Any] = {
            "name": str(name),
            "arguments": dict(arguments or {}),
        }
        if meta is not None:
            params["_meta"] = dict(meta)
        return await self._request("tools/call", params)

    async def send_custom_notification(
        self,
        method: str,
        params: Any = None,
    ) -> None:
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": str(method),
        }
        if params is not None:
            message["params"] = _json_value(params)
        await self._post(message)

    async def send_custom_request(self, method: str, params: Any = None) -> Any:
        return await self._request(str(method), _json_value(params or {}))

    async def close(self) -> None:
        if self._session_id is not None:
            session = self._session_id
            self._session_id = None
            await self._adapter.delete_session(
                self._url,
                session,
                self._auth_token,
                {},
            )

    async def _request(self, method: str, params: Any) -> Any:
        async with self._request_lock:
            request_id = next(self._ids)
            response = await self._post(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            if not isinstance(response, Mapping):
                raise RuntimeError(f"MCP request {method} returned no response")
            if response.get("id") != request_id:
                raise RuntimeError(
                    f"MCP request {method} returned mismatched response id"
                )
            if "error" in response:
                raise RuntimeError(f"MCP request {method} failed: {response['error']}")
            return response.get("result")

    async def _post(self, message: Mapping[str, Any]) -> Any | None:
        result = await self._adapter.post_message(
            self._url,
            dict(message),
            self._session_id,
            self._auth_token,
            {},
        )
        if result.session_id is not None:
            self._session_id = result.session_id
        if result.kind == "accepted":
            return None
        if result.kind == "json":
            return result.message
        if result.kind == "sse" and result.stream is not None:
            async for event in result.stream:
                data = event.get("data")
                if data:
                    return __import__("json").loads(data)
        return None


class ElicitationPauseGuard:
    def __init__(self, pause_state: "ElicitationPauseState") -> None:
        self._pause_state = pause_state
        self._entered = False

    def __enter__(self) -> "ElicitationPauseGuard":
        if not self._entered:
            self._pause_state._increment()
            self._entered = True
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        if self._entered:
            self._pause_state._decrement()
            self._entered = False


class ElicitationPauseState:
    def __init__(self) -> None:
        self._active_count = 0
        self._lock = threading.Lock()

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._active_count > 0

    def enter(self) -> ElicitationPauseGuard:
        return ElicitationPauseGuard(self)

    def _increment(self) -> None:
        with self._lock:
            self._active_count += 1

    def _decrement(self) -> None:
        with self._lock:
            self._active_count = max(0, self._active_count - 1)


class RmcpClient:
    def __init__(
        self,
        *,
        transport: Any,
        transport_recipe: tuple[str, Any],
    ) -> None:
        self._transport = transport
        self._transport_recipe = transport_recipe
        self._service: Any | None = None
        self._state = "connecting"
        self._initialize_context: tuple[Any, float | None, Any] | None = None
        self._state_lock = asyncio.Lock()
        self._elicitation_pause_state = ElicitationPauseState()
        self._stdio_process = (
            transport.process_handle()
            if isinstance(transport, StdioServerTransport)
            else None
        )

    @classmethod
    async def new_in_process_client(
        cls,
        factory: InProcessTransportFactory,
    ) -> "RmcpClient":
        transport = await factory.open()
        return cls(
            transport=transport,
            transport_recipe=("in_process", factory),
        )

    @classmethod
    async def new_stdio_client(
        cls,
        program: str,
        args: tuple[str, ...] | list[str],
        env: Mapping[str, str] | None,
        env_vars: tuple[Any, ...] | list[Any],
        cwd: Any | None,
        launcher: StdioServerLauncher,
    ) -> "RmcpClient":
        command = StdioServerCommand(
            program=program,
            args=tuple(args),
            env=env,
            env_vars=tuple(env_vars),
            cwd=cwd,
        )
        transport = await launcher.launch(command)
        return cls(
            transport=transport,
            transport_recipe=("stdio", (command, launcher)),
        )

    @classmethod
    async def new_streamable_http_client(
        cls,
        server_name: str,
        url: str,
        bearer_token: str | None,
        http_headers: Mapping[str, str] | None,
        env_http_headers: Mapping[str, str] | None,
        store_mode: Any,
        http_client: Any,
        auth_provider: Any | None,
    ) -> "RmcpClient":
        default_headers = build_default_headers(
            http_headers,
            env_http_headers,
        )
        adapter = StreamableHttpClientAdapter(
            http_client,
            default_headers,
            auth_provider,
        )
        service = _StreamableHttpRpcService(
            adapter,
            url,
            bearer_token,
        )
        return cls(
            transport=service,
            transport_recipe=(
                "streamable_http",
                {
                    "server_name": str(server_name),
                    "url": str(url),
                    "bearer_token": bearer_token,
                    "http_headers": dict(http_headers or {}),
                    "env_http_headers": dict(env_http_headers or {}),
                    "store_mode": store_mode,
                    "http_client": http_client,
                    "auth_provider": auth_provider,
                },
            ),
        )

    async def initialize(
        self,
        params: Any,
        timeout: float | None = None,
        send_elicitation: SendElicitation | Any = None,
    ) -> Any:
        async with self._state_lock:
            if self._state == "ready":
                raise RuntimeError("client already initialized")
            if self._state == "closed":
                raise RuntimeError("MCP client is shut down")
            if self._state == "initializing":
                raise RuntimeError("client already initializing")
            self._state = "initializing"

        try:
            from .elicitation_client_service import ElicitationClientService

            async def default_send_elicitation(
                _request_id: Any,
                _request: Any,
            ) -> ElicitationResponse:
                return ElicitationResponse(ElicitationAction.CANCEL)

            client_service = ElicitationClientService(
                params,
                send_elicitation or default_send_elicitation,
                self._elicitation_pause_state,
            )
            service = (
                _JsonRpcService(self._transport, client_service)
                if isinstance(self._transport, StdioServerTransport)
                else self._transport
            )
            initializer = getattr(service, "initialize", None)
            if not callable(initializer):
                raise RuntimeError("MCP transport does not support initialization")
            result = await self._await_operation(
                initializer(params),
                timeout,
                "initialize",
            )
        except BaseException:
            async with self._state_lock:
                if self._state != "closed":
                    self._state = "connecting"
            raise

        async with self._state_lock:
            if self._state == "closed":
                raise RuntimeError("MCP client is shut down")
            self._service = service
            self._initialize_context = (params, timeout, send_elicitation)
            self._state = "ready"
        return result

    async def list_tools(
        self,
        params: Any = None,
        timeout: float | None = None,
    ) -> Any:
        return await self._run_service_operation("list_tools", params, timeout=timeout)

    async def list_tools_with_connector_ids(
        self,
        params: Any = None,
        timeout: float | None = None,
    ) -> ListToolsWithConnectorIdResult:
        result = await self.list_tools(params, timeout)
        tools = []
        for tool in tuple(_field(result, "tools", default=()) or ()):
            meta = _field(tool, "_meta", "meta", default={})
            tools.append(
                ToolWithConnectorId(
                    tool=tool,
                    connector_id=_meta_string(meta, "connector_id"),
                    connector_name=_meta_string(
                        meta,
                        "connector_name",
                        "connector_display_name",
                    ),
                    connector_description=_meta_string(
                        meta,
                        "connector_description",
                        "connectorDescription",
                    ),
                )
            )
        return ListToolsWithConnectorIdResult(
            next_cursor=_field(result, "next_cursor", "nextCursor"),
            tools=tuple(tools),
        )

    async def list_resources(
        self,
        params: Any = None,
        timeout: float | None = None,
    ) -> Any:
        return await self._run_service_operation(
            "list_resources",
            params,
            timeout=timeout,
        )

    async def list_resource_templates(
        self,
        params: Any = None,
        timeout: float | None = None,
    ) -> Any:
        return await self._run_service_operation(
            "list_resource_templates",
            params,
            timeout=timeout,
        )

    async def read_resource(
        self,
        params: Any,
        timeout: float | None = None,
    ) -> Any:
        return await self._run_service_operation(
            "read_resource",
            params,
            timeout=timeout,
        )

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None,
        meta: Mapping[str, Any] | None,
        timeout: float | None = None,
    ) -> Any:
        if arguments is not None and not isinstance(arguments, Mapping):
            raise ValueError(
                f"MCP tool arguments must be a JSON object, got {arguments!r}"
            )
        if meta is not None and not isinstance(meta, Mapping):
            raise ValueError(
                f"MCP tool request _meta must be a JSON object, got {meta!r}"
            )
        service = await self._ready_service()
        operation = getattr(service, "call_tool", None)
        if not callable(operation):
            raise RuntimeError("MCP service does not support call_tool")
        return await self._await_operation(
            operation(
                str(name),
                None if arguments is None else dict(arguments),
                None if meta is None else dict(meta),
            ),
            timeout,
            "tools/call",
        )

    async def send_custom_notification(
        self,
        method: str,
        params: Any = None,
    ) -> Any:
        return await self._run_service_operation(
            "send_custom_notification",
            str(method),
            params,
        )

    async def send_custom_request(
        self,
        method: str,
        params: Any = None,
    ) -> Any:
        return await self._run_service_operation(
            "send_custom_request",
            str(method),
            params,
        )

    async def shutdown(self) -> None:
        async with self._state_lock:
            if self._state == "closed":
                return
            service = self._service or self._transport
            self._service = None
            self._state = "closed"
        shutdown = getattr(service, "shutdown", None)
        if callable(shutdown):
            await shutdown()
            return
        close = getattr(service, "close", None)
        if callable(close):
            result = close()
            if isinstance(result, Awaitable):
                await result

    async def _ready_service(self) -> Any:
        async with self._state_lock:
            if self._state == "closed":
                raise RuntimeError("MCP client is shut down")
            if self._state != "ready" or self._service is None:
                raise RuntimeError("MCP client not initialized")
            return self._service

    async def _run_service_operation(
        self,
        method: str,
        *args: Any,
        timeout: float | None = None,
    ) -> Any:
        service = await self._ready_service()
        operation = getattr(service, method, None)
        if not callable(operation):
            raise RuntimeError(f"MCP service does not support {method}")
        return await self._await_operation(
            operation(*args),
            timeout,
            method,
        )

    @staticmethod
    async def _await_operation(
        operation: Awaitable[Any],
        timeout: float | None,
        label: str,
    ) -> Any:
        if timeout is None:
            return await operation
        try:
            return await asyncio.wait_for(operation, timeout)
        except TimeoutError as exc:
            raise TimeoutError(
                f"timed out awaiting {label} after {timeout} seconds"
            ) from exc


__all__ = [
    "Elicitation",
    "ElicitationResponse",
    "ElicitationPauseGuard",
    "ElicitationPauseState",
    "ListToolsWithConnectorIdResult",
    "RmcpClient",
    "SendElicitation",
    "ToolWithConnectorId",
]
