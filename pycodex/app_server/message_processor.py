"""Message processing facade ported from ``app-server/src/message_processor.rs``.

The Rust module owns connection session gating, initialize-vs-initialized
request routing, response/error forwarding, and shutdown cleanup ordering.
Python keeps child processors injectable so this module can be verified without
starting the full app-server runtime.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

from pycodex.app_server.error_code import invalid_request
from pycodex.app_server.outgoing_message import ConnectionRequestId, RequestContext
from pycodex.app_server_protocol import (
    ClientNotification,
    ClientRequest,
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    experimental_reason,
    experimental_required_message,
)

EXTERNAL_AUTH_REFRESH_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class InitializedConnectionSessionState:
    experimental_api_enabled: bool = False
    opted_out_notification_methods: frozenset[str] = field(default_factory=frozenset)
    app_server_client_name: str = ""
    client_version: str = ""
    request_attestation: bool = False


class ConnectionRpcGate:
    def __init__(self) -> None:
        self.shutdown_called = False

    async def shutdown(self) -> None:
        self.shutdown_called = True


class ConnectionSessionState:
    def __init__(self, rpc_gate: Any | None = None) -> None:
        self.rpc_gate = rpc_gate if rpc_gate is not None else ConnectionRpcGate()
        self._initialized: InitializedConnectionSessionState | None = None

    @classmethod
    def new(cls) -> "ConnectionSessionState":
        return cls()

    def initialized(self) -> bool:
        return self._initialized is not None

    def experimental_api_enabled(self) -> bool:
        return bool(self._initialized and self._initialized.experimental_api_enabled)

    def opted_out_notification_methods(self) -> set[str]:
        if self._initialized is None:
            return set()
        return set(self._initialized.opted_out_notification_methods)

    def app_server_client_name(self) -> str | None:
        if self._initialized is None:
            return None
        return self._initialized.app_server_client_name

    def client_version(self) -> str | None:
        if self._initialized is None:
            return None
        return self._initialized.client_version

    def request_attestation(self) -> bool:
        return bool(self._initialized and self._initialized.request_attestation)

    def initialize(self, session: InitializedConnectionSessionState) -> bool:
        if self._initialized is not None:
            return False
        self._initialized = session
        return True


@dataclass(frozen=True)
class ExternalAuthTokens:
    access_token: str
    chatgpt_account_id: str | None = None
    chatgpt_plan_type: str | None = None


class ExternalAuthRefreshBridge:
    def __init__(self, outgoing: Any, *, timeout_seconds: float = EXTERNAL_AUTH_REFRESH_TIMEOUT_SECONDS) -> None:
        self.outgoing = outgoing
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def map_reason(reason: Any) -> str:
        return "Unauthorized" if str(reason).split(".")[-1] == "Unauthorized" else str(reason)

    def auth_mode(self) -> str:
        return "Chatgpt"

    async def refresh(self, context: Any) -> ExternalAuthTokens:
        params = {
            "reason": self.map_reason(getattr(context, "reason", "Unauthorized")),
            "previousAccountId": getattr(context, "previous_account_id", None),
        }
        request_id, waiter = await _maybe_await(
            self.outgoing.send_request({"type": "ChatgptAuthTokensRefresh", "params": params})
        )
        try:
            result = await asyncio.wait_for(_future_or_value(waiter), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            await _maybe_await(self.outgoing.cancel_request(request_id))
            raise OSError(f"auth refresh request timed out after {int(self.timeout_seconds)}s") from exc
        except Exception as exc:
            raise OSError(f"auth refresh request canceled: {exc}") from exc

        if isinstance(result, JSONRPCErrorError):
            raise OSError(f"auth refresh request failed: code={result.code} message={result.message}")
        if isinstance(result, Mapping) and "error" in result:
            error = JSONRPCErrorError.from_mapping(result["error"])
            raise OSError(f"auth refresh request failed: code={error.code} message={error.message}")
        if not isinstance(result, Mapping):
            raise OSError("auth refresh response must be a mapping")
        return ExternalAuthTokens(
            access_token=str(result["accessToken"] if "accessToken" in result else result["access_token"]),
            chatgpt_account_id=_optional_str(result.get("chatgptAccountId", result.get("chatgpt_account_id"))),
            chatgpt_plan_type=_optional_str(result.get("chatgptPlanType", result.get("chatgpt_plan_type"))),
        )


@dataclass(frozen=True)
class MessageProcessorArgs:
    outgoing: Any
    analytics_events_client: Any = None
    arg0_paths: Any = None
    config: Any = None
    config_manager: Any = None
    environment_manager: Any = None
    feedback: Any = None
    log_db: Any = None
    state_db: Any = None
    config_warnings: tuple[Any, ...] = ()
    session_source: Any = None
    auth_manager: Any = None
    installation_id: str = ""
    rpc_transport: Any = None
    remote_control_handle: Any = None
    plugin_startup_tasks: Any = None
    processors: Mapping[str, Any] = field(default_factory=dict)
    skills_watcher: Any = None
    request_serialization_queues: Any = None


@dataclass(frozen=True)
class ProcessorResult:
    response: Any = None
    send_response: bool = True

    @classmethod
    def no_response(cls) -> "ProcessorResult":
        return cls(response=None, send_response=False)


class MessageProcessorRequestError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


DEFAULT_REQUEST_ROUTES: dict[str, tuple[str, str]] = {
    "ConfigRead": ("config_processor", "read"),
    "WindowsSandboxReadiness": ("windows_sandbox_processor", "windows_sandbox_readiness"),
    "RemoteControlEnable": ("remote_control_processor", "enable"),
    "RemoteControlDisable": ("remote_control_processor", "disable"),
    "RemoteControlStatusRead": ("remote_control_processor", "status_read"),
    "EnvironmentAdd": ("environment_processor", "environment_add"),
    "FsReadFile": ("fs_processor", "read_file"),
    "FsWriteFile": ("fs_processor", "write_file"),
    "FsCreateDirectory": ("fs_processor", "create_directory"),
    "FsGetMetadata": ("fs_processor", "get_metadata"),
    "FsReadDirectory": ("fs_processor", "read_directory"),
    "FsRemove": ("fs_processor", "remove"),
    "FsCopy": ("fs_processor", "copy"),
    "FsWatch": ("fs_processor", "watch"),
    "FsUnwatch": ("fs_processor", "unwatch"),
    "ThreadStart": ("thread_processor", "thread_start"),
    "ThreadResume": ("thread_processor", "thread_resume"),
    "ThreadFork": ("thread_processor", "thread_fork"),
    "ThreadList": ("thread_processor", "thread_list"),
    "ThreadRead": ("thread_processor", "thread_read"),
    "TurnStart": ("turn_processor", "turn_start"),
    "TurnSteer": ("turn_processor", "turn_steer"),
    "TurnInterrupt": ("turn_processor", "turn_interrupt"),
    "McpServerOauthLogin": ("mcp_processor", "mcp_server_oauth_login"),
    "McpServerRefresh": ("mcp_processor", "mcp_server_refresh"),
    "McpServerStatusList": ("mcp_processor", "mcp_server_status_list"),
    "McpResourceRead": ("mcp_processor", "mcp_resource_read"),
    "McpServerToolCall": ("mcp_processor", "mcp_server_tool_call"),
    "LoginAccount": ("account_processor", "login_account"),
    "LogoutAccount": ("account_processor", "logout_account"),
    "CancelLoginAccount": ("account_processor", "cancel_login_account"),
    "GetAccount": ("account_processor", "get_account"),
    "GetAuthStatus": ("account_processor", "get_auth_status"),
    "GetAccountRateLimits": ("account_processor", "get_account_rate_limits"),
    "GitDiffToRemote": ("git_processor", "git_diff_to_remote"),
    "FuzzyFileSearch": ("search_processor", "fuzzy_file_search"),
    "OneOffCommandExec": ("command_exec_processor", "one_off_command_exec"),
    "CommandExecWrite": ("command_exec_processor", "command_exec_write"),
    "CommandExecResize": ("command_exec_processor", "command_exec_resize"),
    "CommandExecTerminate": ("command_exec_processor", "command_exec_terminate"),
    "ProcessSpawn": ("process_exec_processor", "process_spawn"),
    "ProcessWriteStdin": ("process_exec_processor", "process_write_stdin"),
    "ProcessKill": ("process_exec_processor", "process_kill"),
    "ProcessResizePty": ("process_exec_processor", "process_resize_pty"),
    "FeedbackUpload": ("feedback_processor", "feedback_upload"),
}


class MessageProcessor:
    def __init__(
        self,
        args: MessageProcessorArgs,
        *,
        request_routes: Mapping[str, tuple[str, str] | Callable[..., Any]] | None = None,
    ) -> None:
        self.outgoing = args.outgoing
        self.skills_watcher = args.skills_watcher
        self.request_serialization_queues = args.request_serialization_queues
        self.request_routes = dict(DEFAULT_REQUEST_ROUTES if request_routes is None else request_routes)
        for name, processor in args.processors.items():
            setattr(self, name, processor)
        if args.auth_manager is not None and hasattr(args.auth_manager, "set_external_auth"):
            args.auth_manager.set_external_auth(ExternalAuthRefreshBridge(args.outgoing))

    @classmethod
    def new(cls, args: MessageProcessorArgs) -> "MessageProcessor":
        return cls(args)

    def clear_runtime_references(self) -> None:
        _call_no_wait(getattr(getattr(self, "account_processor", None), "clear_external_auth", None))
        _call_no_wait(getattr(getattr(self, "apps_processor", None), "shutdown", None))
        _call_no_wait(getattr(self.skills_watcher, "shutdown", None))

    async def process_request(
        self,
        connection_id: Any,
        request: JSONRPCRequest | Mapping[str, Any],
        transport: Any = None,
        session: ConnectionSessionState | None = None,
    ) -> None:
        jsonrpc_request = request if isinstance(request, JSONRPCRequest) else JSONRPCRequest.from_mapping(request)
        request_id = ConnectionRequestId(connection_id=connection_id, request_id=jsonrpc_request.id)
        request_context = RequestContext.new(request_id, getattr(transport, "span", None), getattr(jsonrpc_request, "trace", None))
        await _maybe_await(self.outgoing.register_request_context(request_context))
        try:
            client_request = ClientRequest.from_jsonrpc(jsonrpc_request)
            await self.handle_client_request(request_id, client_request, session or ConnectionSessionState(), None, request_context)
        except MessageProcessorRequestError as exc:
            await _maybe_await(self.outgoing.send_error(request_id, exc.error))
        except Exception as exc:
            await _maybe_await(self.outgoing.send_error(request_id, invalid_request(f"Invalid request: {exc}")))

    async def process_client_request(
        self,
        connection_id: Any,
        request: ClientRequest,
        session: ConnectionSessionState,
        outbound_initialized: Any | None = None,
    ) -> None:
        request_id = ConnectionRequestId(connection_id=connection_id, request_id=request.id())
        request_context = RequestContext.new(request_id)
        await _maybe_await(self.outgoing.register_request_context(request_context))
        try:
            await self.handle_client_request(request_id, request, session, outbound_initialized, request_context)
        except MessageProcessorRequestError as exc:
            await _maybe_await(self.outgoing.send_error(request_id, exc.error))

    async def process_notification(self, notification: JSONRPCNotification | Mapping[str, Any]) -> None:
        _ = notification if isinstance(notification, JSONRPCNotification) else JSONRPCNotification.from_mapping(notification)

    async def process_client_notification(self, notification: ClientNotification) -> None:
        _ = notification

    async def process_response(self, response: JSONRPCResponse | Mapping[str, Any]) -> None:
        parsed = response if isinstance(response, JSONRPCResponse) else JSONRPCResponse.from_mapping(response)
        await _maybe_await(self.outgoing.notify_client_response(parsed.id, parsed.result))

    async def process_error(self, err: JSONRPCError | Mapping[str, Any]) -> None:
        parsed = err if isinstance(err, JSONRPCError) else JSONRPCError.from_mapping(err)
        await _maybe_await(self.outgoing.notify_client_error(parsed.id, parsed.error))

    async def handle_client_request(
        self,
        connection_request_id: ConnectionRequestId,
        codex_request: ClientRequest,
        session: ConnectionSessionState,
        outbound_initialized: Any | None,
        request_context: RequestContext,
    ) -> None:
        if codex_request.type == "Initialize":
            processor = getattr(self, "initialize_processor")
            initialized = await _call_processor(
                processor.initialize,
                connection_request_id.connection_id,
                connection_request_id.request_id,
                codex_request.params,
                session,
                outbound_initialized,
            )
            if initialized:
                thread_processor = getattr(self, "thread_processor", None)
                connection_initialized = getattr(thread_processor, "connection_initialized", None)
                if callable(connection_initialized):
                    await _call_processor(
                        connection_initialized,
                        connection_request_id.connection_id,
                        {"request_attestation": session.request_attestation()},
                    )
            return

        await self.dispatch_initialized_client_request(connection_request_id, codex_request, session, request_context)

    async def dispatch_initialized_client_request(
        self,
        connection_request_id: ConnectionRequestId,
        codex_request: ClientRequest,
        session: ConnectionSessionState,
        request_context: RequestContext | None = None,
    ) -> None:
        if not session.initialized():
            raise MessageProcessorRequestError(invalid_request("Not initialized"))

        reason = experimental_reason(codex_request.params)
        if reason and not session.experimental_api_enabled():
            raise MessageProcessorRequestError(invalid_request(experimental_required_message(reason)))

        initialize_processor = getattr(self, "initialize_processor", None)
        tracker = getattr(initialize_processor, "track_initialized_request", None)
        if callable(tracker):
            tracker(connection_request_id.connection_id, _request_id_value(connection_request_id.request_id), codex_request)

        await self.handle_initialized_client_request(
            connection_request_id,
            codex_request,
            request_context or RequestContext.new(connection_request_id),
            session.app_server_client_name(),
            session.client_version(),
        )

    async def handle_initialized_client_request(
        self,
        connection_request_id: ConnectionRequestId,
        codex_request: ClientRequest,
        request_context: RequestContext,
        app_server_client_name: str | None = None,
        client_version: str | None = None,
    ) -> None:
        if codex_request.type == "Initialize":
            raise RuntimeError("Initialize should be handled before initialized request dispatch")

        result = await self._dispatch_to_child_processor(
            connection_request_id,
            codex_request,
            request_context,
            app_server_client_name,
            client_version,
        )
        if isinstance(result, JSONRPCErrorError):
            await _maybe_await(self.outgoing.send_error(connection_request_id, result))
            return
        if isinstance(result, ProcessorResult):
            if result.send_response:
                await _maybe_await(self.outgoing.send_response_as(connection_request_id, result.response))
            return
        if result is not None:
            await _maybe_await(self.outgoing.send_response_as(connection_request_id, result))

    async def _dispatch_to_child_processor(
        self,
        connection_request_id: ConnectionRequestId,
        codex_request: ClientRequest,
        request_context: RequestContext,
        app_server_client_name: str | None,
        client_version: str | None,
    ) -> Any:
        route = self.request_routes.get(codex_request.type)
        if route is None:
            raise MessageProcessorRequestError(invalid_request(f"Unhandled request: {codex_request.type}"))
        if callable(route):
            return await _call_processor(
                route,
                connection_request_id,
                codex_request.params,
                request_context,
                app_server_client_name,
                client_version,
            )
        processor_name, method_name = route
        processor = getattr(self, processor_name)
        handler = getattr(processor, method_name)
        return await _call_processor(handler, connection_request_id, codex_request.params, codex_request)

    async def connection_closed(self, connection_id: Any, session_state: ConnectionSessionState) -> None:
        await _maybe_await(session_state.rpc_gate.shutdown())
        await _maybe_await(self.outgoing.connection_closed(connection_id))
        for processor_name in (
            "fs_processor",
            "command_exec_processor",
            "process_exec_processor",
            "thread_processor",
        ):
            processor = getattr(self, processor_name, None)
            close = getattr(processor, "connection_closed", None)
            if callable(close):
                await _call_processor(close, connection_id)


async def _call_processor(func: Callable[..., Any], *args: Any) -> Any:
    try:
        return await _maybe_await(func(*args))
    except TypeError:
        signature = inspect.signature(func)
        accepted = len(
            [
                parameter
                for parameter in signature.parameters.values()
                if parameter.kind
                in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
        )
        return await _maybe_await(func(*args[:accepted]))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _call_no_wait(func: Any) -> None:
    if callable(func):
        result = func()
        if inspect.isawaitable(result):
            result.close()


async def _future_or_value(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _request_id_value(value: Any) -> Any:
    if hasattr(value, "to_json") and callable(value.to_json):
        return value.to_json()
    return value


__all__ = [
    "ConnectionRpcGate",
    "ConnectionSessionState",
    "EXTERNAL_AUTH_REFRESH_TIMEOUT_SECONDS",
    "ExternalAuthRefreshBridge",
    "ExternalAuthTokens",
    "InitializedConnectionSessionState",
    "MessageProcessorRequestError",
    "MessageProcessor",
    "MessageProcessorArgs",
    "ProcessorResult",
]
