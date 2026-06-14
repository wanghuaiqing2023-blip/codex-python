"""Python API boundary for Rust crate ``codex-app-server-client``.

The Rust crate is an async facade over in-process and remote app-server
transports.  This module defines the Python-side interfaces consumed by the TUI
port; transport behavior is intentionally not implemented until the matching
app-server runtime slice is ported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar


DEFAULT_IN_PROCESS_CHANNEL_CAPACITY = 1024
RequestResult = Any
T = TypeVar("T")


class AppServerClientNotImplementedError(NotImplementedError):
    """Raised when an app-server client transport method is not ported yet."""


class TypedRequestError(RuntimeError):
    """Python boundary for Rust ``TypedRequestError``."""

    def __init__(self, method: str, kind: str, source: BaseException | str | None = None) -> None:
        self.method = method
        self.kind = kind
        self.source = source
        super().__init__(f"{method} {kind} error" + (f": {source}" if source else ""))


@dataclass(frozen=True)
class InProcessServerEvent:
    """Placeholder for Rust ``InProcessServerEvent`` re-exported by this crate."""

    kind: str
    payload: Any = None


@dataclass(frozen=True)
class StateDbHandle:
    """Placeholder for Rust ``StateDbHandle`` re-exported by this crate."""

    inner: Any = None


@dataclass(frozen=True)
class EnvironmentManager:
    """Placeholder for Rust ``EnvironmentManager`` re-exported by this crate."""

    inner: Any = None


@dataclass(frozen=True)
class ExecServerRuntimePaths:
    """Placeholder for Rust ``ExecServerRuntimePaths`` re-exported by this crate."""

    inner: Any = None


def app_server_control_socket_path(*_args: Any, **_kwargs: Any) -> Any:
    """Python boundary for Rust ``app_server_control_socket_path``."""

    raise AppServerClientNotImplementedError("app_server_control_socket_path is not ported yet")


class AppServerEventKind(Enum):
    LAGGED = "Lagged"
    SERVER_NOTIFICATION = "ServerNotification"
    SERVER_REQUEST = "ServerRequest"
    DISCONNECTED = "Disconnected"


@dataclass(frozen=True)
class AppServerEvent:
    """Python boundary for Rust ``AppServerEvent``."""

    kind: AppServerEventKind
    payload: Any = None
    skipped: int | None = None
    message: str | None = None

    @classmethod
    def lagged(cls, skipped: int) -> "AppServerEvent":
        return cls(AppServerEventKind.LAGGED, skipped=skipped)

    @classmethod
    def server_notification(cls, notification: Any) -> "AppServerEvent":
        return cls(AppServerEventKind.SERVER_NOTIFICATION, payload=notification)

    @classmethod
    def server_request(cls, request: Any) -> "AppServerEvent":
        return cls(AppServerEventKind.SERVER_REQUEST, payload=request)

    @classmethod
    def disconnected(cls, message: str) -> "AppServerEvent":
        return cls(AppServerEventKind.DISCONNECTED, message=message)


@dataclass
class InProcessClientStartArgs:
    """Python boundary for Rust ``InProcessClientStartArgs``."""

    arg0_paths: Any
    config: Any
    cli_overrides: list[tuple[str, Any]] = field(default_factory=list)
    loader_overrides: Any = None
    strict_config: bool = False
    cloud_requirements: Any = None
    feedback: Any = None
    log_db: Any = None
    state_db: StateDbHandle | None = None
    environment_manager: EnvironmentManager | Any = None
    config_warnings: list[Any] = field(default_factory=list)
    session_source: Any = None
    enable_codex_api_key_env: bool = False
    client_name: str = "pycodex"
    client_version: str = "0"
    experimental_api: bool = False
    opt_out_notification_methods: list[str] = field(default_factory=list)
    channel_capacity: int = DEFAULT_IN_PROCESS_CHANNEL_CAPACITY

    def initialize_params(self) -> dict[str, Any]:
        return {
            "client_info": {"name": self.client_name, "title": None, "version": self.client_version},
            "capabilities": {
                "experimental_api": self.experimental_api,
                "request_attestation": False,
                "opt_out_notification_methods": self.opt_out_notification_methods or None,
            },
        }


class InProcessAppServerRequestHandle:
    """Python boundary for Rust ``InProcessAppServerRequestHandle``."""

    async def request(self, request: Any) -> RequestResult:
        raise AppServerClientNotImplementedError("InProcessAppServerRequestHandle.request is not ported yet")

    async def request_typed(self, request: Any) -> Any:
        raise AppServerClientNotImplementedError("InProcessAppServerRequestHandle.request_typed is not ported yet")


class InProcessAppServerClient:
    """Python boundary for Rust ``InProcessAppServerClient``."""

    @classmethod
    async def start(cls, args: InProcessClientStartArgs) -> "InProcessAppServerClient":
        raise AppServerClientNotImplementedError("InProcessAppServerClient.start is not ported yet")

    def request_handle(self) -> InProcessAppServerRequestHandle:
        return InProcessAppServerRequestHandle()

    async def request(self, request: Any) -> RequestResult:
        raise AppServerClientNotImplementedError("InProcessAppServerClient.request is not ported yet")

    async def request_typed(self, request: Any) -> Any:
        raise AppServerClientNotImplementedError("InProcessAppServerClient.request_typed is not ported yet")

    async def notify(self, notification: Any) -> None:
        raise AppServerClientNotImplementedError("InProcessAppServerClient.notify is not ported yet")

    async def resolve_server_request(self, request_id: Any, result: Any) -> None:
        raise AppServerClientNotImplementedError("InProcessAppServerClient.resolve_server_request is not ported yet")

    async def reject_server_request(self, request_id: Any, error: Any) -> None:
        raise AppServerClientNotImplementedError("InProcessAppServerClient.reject_server_request is not ported yet")

    async def next_event(self) -> InProcessServerEvent | None:
        raise AppServerClientNotImplementedError("InProcessAppServerClient.next_event is not ported yet")

    async def shutdown(self) -> None:
        raise AppServerClientNotImplementedError("InProcessAppServerClient.shutdown is not ported yet")


class RemoteAppServerEndpointKind(Enum):
    WEB_SOCKET = "WebSocket"
    UNIX_SOCKET = "UnixSocket"


@dataclass(frozen=True)
class RemoteAppServerEndpoint:
    """Python boundary for Rust ``RemoteAppServerEndpoint``."""

    kind: RemoteAppServerEndpointKind
    websocket_url: str | None = None
    auth_token: str | None = None
    socket_path: Any = None

    @classmethod
    def websocket(cls, websocket_url: str, auth_token: str | None = None) -> "RemoteAppServerEndpoint":
        return cls(RemoteAppServerEndpointKind.WEB_SOCKET, websocket_url=websocket_url, auth_token=auth_token)

    @classmethod
    def unix_socket(cls, socket_path: Any) -> "RemoteAppServerEndpoint":
        return cls(RemoteAppServerEndpointKind.UNIX_SOCKET, socket_path=socket_path)


@dataclass(frozen=True)
class RemoteAppServerConnectArgs:
    """Python boundary for Rust ``RemoteAppServerConnectArgs``."""

    endpoint: RemoteAppServerEndpoint
    client_name: str
    client_version: str
    experimental_api: bool = False
    opt_out_notification_methods: list[str] = field(default_factory=list)
    channel_capacity: int = DEFAULT_IN_PROCESS_CHANNEL_CAPACITY


class RemoteAppServerRequestHandle:
    """Python boundary for Rust ``RemoteAppServerRequestHandle``."""

    async def request(self, request: Any) -> RequestResult:
        raise AppServerClientNotImplementedError("RemoteAppServerRequestHandle.request is not ported yet")

    async def request_typed(self, request: Any) -> Any:
        raise AppServerClientNotImplementedError("RemoteAppServerRequestHandle.request_typed is not ported yet")


class RemoteAppServerClient:
    """Python boundary for Rust ``RemoteAppServerClient``."""

    @classmethod
    async def connect(cls, args: RemoteAppServerConnectArgs) -> "RemoteAppServerClient":
        raise AppServerClientNotImplementedError("RemoteAppServerClient.connect is not ported yet")

    def server_version(self) -> str | None:
        raise AppServerClientNotImplementedError("RemoteAppServerClient.server_version is not ported yet")

    def request_handle(self) -> RemoteAppServerRequestHandle:
        return RemoteAppServerRequestHandle()

    async def request(self, request: Any) -> RequestResult:
        raise AppServerClientNotImplementedError("RemoteAppServerClient.request is not ported yet")

    async def request_typed(self, request: Any) -> Any:
        raise AppServerClientNotImplementedError("RemoteAppServerClient.request_typed is not ported yet")

    async def notify(self, notification: Any) -> None:
        raise AppServerClientNotImplementedError("RemoteAppServerClient.notify is not ported yet")

    async def resolve_server_request(self, request_id: Any, result: Any) -> None:
        raise AppServerClientNotImplementedError("RemoteAppServerClient.resolve_server_request is not ported yet")

    async def reject_server_request(self, request_id: Any, error: Any) -> None:
        raise AppServerClientNotImplementedError("RemoteAppServerClient.reject_server_request is not ported yet")

    async def next_event(self) -> AppServerEvent | None:
        raise AppServerClientNotImplementedError("RemoteAppServerClient.next_event is not ported yet")

    async def shutdown(self) -> None:
        raise AppServerClientNotImplementedError("RemoteAppServerClient.shutdown is not ported yet")


@dataclass(frozen=True)
class AppServerRequestHandle:
    """Python boundary for Rust ``AppServerRequestHandle``."""

    inner: InProcessAppServerRequestHandle | RemoteAppServerRequestHandle

    async def request(self, request: Any) -> RequestResult:
        return await self.inner.request(request)

    async def request_typed(self, request: Any) -> Any:
        return await self.inner.request_typed(request)


@dataclass(frozen=True)
class AppServerClient:
    """Python boundary for Rust ``AppServerClient``."""

    inner: InProcessAppServerClient | RemoteAppServerClient

    def request_handle(self) -> AppServerRequestHandle:
        return AppServerRequestHandle(self.inner.request_handle())

    async def request(self, request: Any) -> RequestResult:
        return await self.inner.request(request)

    async def request_typed(self, request: Any) -> Any:
        return await self.inner.request_typed(request)

    async def notify(self, notification: Any) -> None:
        return await self.inner.notify(notification)

    async def resolve_server_request(self, request_id: Any, result: Any) -> None:
        return await self.inner.resolve_server_request(request_id, result)

    async def reject_server_request(self, request_id: Any, error: Any) -> None:
        return await self.inner.reject_server_request(request_id, error)

    async def next_event(self) -> AppServerEvent | None:
        event = await self.inner.next_event()
        if isinstance(event, InProcessServerEvent):
            return AppServerEvent(AppServerEventKind.SERVER_NOTIFICATION, payload=event)
        return event

    async def shutdown(self) -> None:
        return await self.inner.shutdown()


__all__ = [
    "AppServerClient",
    "AppServerClientNotImplementedError",
    "AppServerEvent",
    "AppServerEventKind",
    "AppServerRequestHandle",
    "DEFAULT_IN_PROCESS_CHANNEL_CAPACITY",
    "EnvironmentManager",
    "ExecServerRuntimePaths",
    "InProcessAppServerClient",
    "InProcessAppServerRequestHandle",
    "InProcessClientStartArgs",
    "InProcessServerEvent",
    "RemoteAppServerClient",
    "RemoteAppServerConnectArgs",
    "RemoteAppServerEndpoint",
    "RemoteAppServerEndpointKind",
    "RemoteAppServerRequestHandle",
    "RequestResult",
    "StateDbHandle",
    "TypedRequestError",
    "app_server_control_socket_path",
]
