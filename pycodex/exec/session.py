"""App-server request parameter builders for ``codex exec``.

Ported from the request-construction portions of
``codex/codex-rs/exec/src/lib.rs`` and the v2 app-server protocol parameter
types.  These helpers are deliberately transport-agnostic: they produce the
same request payload shapes that a future Python app-server client will send.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
import errno
import ipaddress
import json
import os
from pathlib import Path
import socket
from typing import Any
from urllib.parse import urlparse

from pycodex.protocol import (
    ActivePermissionProfile,
    AdditionalPermissionProfile,
    ApprovalsReviewer,
    AskForApproval,
    EventMsg,
    PermissionProfile,
    ReviewRequest,
    ReviewTarget,
    SandboxMode,
    SessionConfiguredEvent,
    SessionId,
    ThreadSource,
    ThreadId,
    TurnContextItem,
    TurnItem,
    UserInput,
)

from .run import ExecRunPlan
from .websocket import StdlibWebSocket, encode_websocket_text_message, websocket_frame_event

JsonValue = Any
RESUME_LOOKUP_REQUEST_ID = 0
REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS = 10
REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS = 10
REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE = 128 << 20
REMOTE_APP_SERVER_SHUTDOWN_TIMEOUT_SECONDS = 5
UDS_WEBSOCKET_HANDSHAKE_URL = "ws://localhost/rpc"


class ThreadSourceKind(str, Enum):
    CLI = "cli"
    VSCODE = "vscode"
    EXEC = "exec"
    APP_SERVER = "appServer"
    SUB_AGENT = "subAgent"
    SUB_AGENT_REVIEW = "subAgentReview"
    SUB_AGENT_COMPACT = "subAgentCompact"
    SUB_AGENT_THREAD_SPAWN = "subAgentThreadSpawn"
    SUB_AGENT_OTHER = "subAgentOther"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RemoteAppServerEndpoint:
    kind: str
    websocket_url: str | None = None
    auth_token: str | None = None
    socket_path: Path | None = None

    @classmethod
    def websocket(cls, websocket_url: str, auth_token: str | None = None) -> "RemoteAppServerEndpoint":
        return cls("websocket", websocket_url=websocket_url, auth_token=auth_token)

    @classmethod
    def unix_socket(cls, socket_path: Path | str) -> "RemoteAppServerEndpoint":
        return cls("unix_socket", socket_path=Path(socket_path))

    def __post_init__(self) -> None:
        if self.kind == "websocket":
            if not self.websocket_url:
                raise ValueError("websocket endpoint requires websocket_url")
            if self.socket_path is not None:
                raise ValueError("websocket endpoint cannot include socket_path")
            return
        if self.kind == "unix_socket":
            if self.socket_path is None:
                raise ValueError("unix_socket endpoint requires socket_path")
            if not isinstance(self.socket_path, Path):
                object.__setattr__(self, "socket_path", Path(self.socket_path))
            if self.websocket_url is not None or self.auth_token is not None:
                raise ValueError("unix_socket endpoint cannot include websocket_url or auth_token")
            return
        raise ValueError(f"unsupported remote app-server endpoint kind `{self.kind}`")

    @property
    def endpoint(self) -> str:
        if self.kind == "websocket":
            return str(self.websocket_url)
        return f"unix://{self.socket_path}"

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.kind == "websocket":
            return _drop_none(
                {
                    "type": "WebSocket",
                    "websocketUrl": self.websocket_url,
                    "authToken": self.auth_token,
                }
            )
        return {"type": "UnixSocket", "socketPath": str(self.socket_path)}


def app_server_control_socket_path(codex_home: Path | str) -> Path:
    return Path(codex_home) / "app-server-control" / "app-server-control.sock"


def resolve_remote_addr(
    addr: str,
    *,
    codex_home: Path | str | None = None,
    cwd: Path | str | None = None,
) -> RemoteAppServerEndpoint:
    if addr.startswith("unix://"):
        socket_path = addr.removeprefix("unix://")
        if socket_path == "":
            if codex_home is None:
                from pycodex.core.paths import find_codex_home

                codex_home = find_codex_home()
            return RemoteAppServerEndpoint.unix_socket(app_server_control_socket_path(codex_home))
        path = Path(socket_path)
        if not path.is_absolute():
            path = Path.cwd() / path if cwd is None else Path(cwd) / path
        return RemoteAppServerEndpoint.unix_socket(path)

    parsed = urlparse(addr)
    path = parsed.path or "/"
    try:
        port = parsed.port
    except ValueError:
        port = None
    if (
        parsed.scheme in {"ws", "wss"}
        and parsed.hostname is not None
        and port is not None
        and parsed.username is None
        and parsed.password is None
        and path == "/"
        and parsed.query == ""
        and parsed.fragment == ""
    ):
        return RemoteAppServerEndpoint.websocket(_normalized_remote_websocket_url(parsed, port))

    raise ValueError(remote_addr_parse_error_message(addr))


def remote_addr_parse_error_message(addr: str) -> str:
    return (
        f"invalid remote address `{addr}`; expected `ws://host:port`, "
        "`wss://host:port`, `unix://`, or `unix://PATH`"
    )


def remote_addr_supports_auth_token(endpoint: RemoteAppServerEndpoint) -> bool:
    return endpoint.kind == "websocket" and websocket_url_supports_auth_token(str(endpoint.websocket_url))


def read_remote_auth_token_from_env_var_with(
    env_var_name: str,
    get_var: Callable[[str], str | None],
) -> str:
    try:
        auth_token = get_var(env_var_name)
    except KeyError as exc:
        raise ValueError(f"environment variable `{env_var_name}` is not set") from exc
    except Exception as exc:
        raise ValueError(f"environment variable `{env_var_name}` is not set") from exc
    if auth_token is None:
        raise ValueError(f"environment variable `{env_var_name}` is not set")
    auth_token = auth_token.strip()
    if auth_token == "":
        raise ValueError(f"environment variable `{env_var_name}` is empty")
    return auth_token


def read_remote_auth_token_from_env_var(
    env_var_name: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    source = os.environ if environ is None else environ
    return read_remote_auth_token_from_env_var_with(env_var_name, source.get)


def apply_remote_auth_token_env(
    endpoint: RemoteAppServerEndpoint | None,
    remote_auth_token_env: str | None,
    *,
    get_var: Callable[[str], str | None] | None = None,
) -> RemoteAppServerEndpoint | None:
    if remote_auth_token_env is None:
        return endpoint
    if endpoint is None:
        raise ValueError("`--remote-auth-token-env` requires `--remote`.")
    if not remote_addr_supports_auth_token(endpoint):
        raise ValueError("`--remote-auth-token-env` requires a `wss://` or loopback `ws://` remote.")
    auth_token = read_remote_auth_token_from_env_var_with(
        remote_auth_token_env,
        os.environ.get if get_var is None else get_var,
    )
    if endpoint.kind != "websocket":
        raise ValueError("`--remote-auth-token-env` requires a `wss://` or loopback `ws://` remote.")
    return RemoteAppServerEndpoint.websocket(str(endpoint.websocket_url), auth_token=auth_token)


def resolve_remote_endpoint(
    remote: str | None,
    *,
    remote_auth_token_env: str | None = None,
    codex_home: Path | str | None = None,
    cwd: Path | str | None = None,
    get_var: Callable[[str], str | None] | None = None,
) -> RemoteAppServerEndpoint | None:
    endpoint = None if remote is None else resolve_remote_addr(remote, codex_home=codex_home, cwd=cwd)
    return apply_remote_auth_token_env(endpoint, remote_auth_token_env, get_var=get_var)


def _normalized_remote_websocket_url(parsed: JsonValue, port: int) -> str:
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    url = f"{parsed.scheme}://{host}:{port}/"
    return url


@dataclass(frozen=True)
class RemoteClientInfo:
    name: str
    version: str
    title: str | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"name": self.name, "title": self.title, "version": self.version}


@dataclass(frozen=True)
class RemoteInitializeCapabilities:
    experimental_api: bool = False
    request_attestation: bool = False
    opt_out_notification_methods: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.opt_out_notification_methods is not None and not isinstance(self.opt_out_notification_methods, tuple):
            object.__setattr__(self, "opt_out_notification_methods", tuple(self.opt_out_notification_methods))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "experimentalApi": self.experimental_api,
            "requestAttestation": self.request_attestation,
            "optOutNotificationMethods": (
                list(self.opt_out_notification_methods) if self.opt_out_notification_methods is not None else None
            ),
        }


@dataclass(frozen=True)
class RemoteInitializeParams:
    client_info: RemoteClientInfo
    capabilities: RemoteInitializeCapabilities | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"clientInfo": self.client_info.to_mapping()}
        if self.capabilities is not None:
            data["capabilities"] = self.capabilities.to_mapping()
        return data


@dataclass(frozen=True)
class RemoteAppServerConnectArgs:
    endpoint: RemoteAppServerEndpoint
    client_name: str
    client_version: str
    experimental_api: bool = False
    opt_out_notification_methods: tuple[str, ...] = ()
    channel_capacity: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.opt_out_notification_methods, tuple):
            object.__setattr__(self, "opt_out_notification_methods", tuple(self.opt_out_notification_methods))

    @property
    def effective_channel_capacity(self) -> int:
        return max(self.channel_capacity, 1)

    def initialize_params(self) -> RemoteInitializeParams:
        return RemoteInitializeParams(
            client_info=RemoteClientInfo(
                name=self.client_name,
                title=None,
                version=self.client_version,
            ),
            capabilities=RemoteInitializeCapabilities(
                experimental_api=self.experimental_api,
                request_attestation=False,
                opt_out_notification_methods=(
                    self.opt_out_notification_methods if self.opt_out_notification_methods else None
                ),
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "endpoint": self.endpoint.to_mapping(),
            "clientName": self.client_name,
            "clientVersion": self.client_version,
            "experimentalApi": self.experimental_api,
            "optOutNotificationMethods": list(self.opt_out_notification_methods),
            "channelCapacity": self.channel_capacity,
            "effectiveChannelCapacity": self.effective_channel_capacity,
        }


@dataclass(frozen=True)
class ExecSessionConfig:
    """Subset of upstream ``Config`` needed by exec request construction."""

    model: str | None
    model_provider_id: str | None
    cwd: Path
    workspace_roots: tuple[Path, ...] = ()
    user_instructions: str | None = None
    instruction_sources: tuple[Path, ...] = ()
    startup_warnings: tuple[str, ...] = ()
    approval_policy: AskForApproval = AskForApproval.NEVER
    approvals_reviewer: ApprovalsReviewer = ApprovalsReviewer.USER
    permission_profile: PermissionProfile = PermissionProfile.read_only()
    active_permission_profile: ActivePermissionProfile | None = None
    ephemeral: bool = False
    reasoning_effort: JsonValue | None = None
    hide_agent_reasoning: bool = False
    show_raw_agent_reasoning: bool = False
    request_permissions_callback: Any = None
    granted_session_permissions: AdditionalPermissionProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(self, "workspace_roots", tuple(Path(root) for root in self.workspace_roots))
        object.__setattr__(self, "instruction_sources", tuple(Path(path) for path in self.instruction_sources))
        object.__setattr__(self, "startup_warnings", tuple(str(warning) for warning in self.startup_warnings))
        if self.request_permissions_callback is not None and not callable(self.request_permissions_callback):
            raise TypeError("request_permissions_callback must be callable or None")
        if self.granted_session_permissions is not None and not isinstance(
            self.granted_session_permissions,
            AdditionalPermissionProfile,
        ):
            raise TypeError("granted_session_permissions must be AdditionalPermissionProfile or None")


@dataclass(frozen=True)
class ThreadStartParams:
    model: str | None = None
    model_provider: str | None = None
    cwd: Path | str | None = None
    runtime_workspace_roots: tuple[Path, ...] | None = None
    approval_policy: AskForApproval | None = None
    approvals_reviewer: ApprovalsReviewer | None = None
    sandbox: SandboxMode | None = None
    permissions: str | None = None
    config: Mapping[str, JsonValue] | None = None
    ephemeral: bool | None = None
    thread_source: ThreadSource | None = None

    def __post_init__(self) -> None:
        if self.runtime_workspace_roots is not None and not isinstance(self.runtime_workspace_roots, tuple):
            object.__setattr__(self, "runtime_workspace_roots", tuple(Path(root) for root in self.runtime_workspace_roots))
        elif self.runtime_workspace_roots is not None:
            object.__setattr__(self, "runtime_workspace_roots", tuple(Path(root) for root in self.runtime_workspace_roots))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "model": self.model,
                "modelProvider": self.model_provider,
                "cwd": str(self.cwd) if self.cwd is not None else None,
                "runtimeWorkspaceRoots": _paths(self.runtime_workspace_roots),
                "approvalPolicy": _enum(self.approval_policy),
                "approvalsReviewer": _enum(self.approvals_reviewer),
                "sandbox": _enum(self.sandbox),
                "permissions": self.permissions,
                "config": _to_json(self.config),
                "ephemeral": self.ephemeral,
                "threadSource": _enum(self.thread_source),
            }
        )


@dataclass(frozen=True)
class ThreadResumeParams:
    thread_id: str
    model: str | None = None
    model_provider: str | None = None
    cwd: Path | str | None = None
    runtime_workspace_roots: tuple[Path, ...] | None = None
    approval_policy: AskForApproval | None = None
    approvals_reviewer: ApprovalsReviewer | None = None
    sandbox: SandboxMode | None = None
    permissions: str | None = None
    config: Mapping[str, JsonValue] | None = None
    exclude_turns: bool = False

    def __post_init__(self) -> None:
        if self.runtime_workspace_roots is not None and not isinstance(self.runtime_workspace_roots, tuple):
            object.__setattr__(self, "runtime_workspace_roots", tuple(Path(root) for root in self.runtime_workspace_roots))
        elif self.runtime_workspace_roots is not None:
            object.__setattr__(self, "runtime_workspace_roots", tuple(Path(root) for root in self.runtime_workspace_roots))

    def to_mapping(self) -> dict[str, JsonValue]:
        data = _drop_none(
            {
                "threadId": self.thread_id,
                "model": self.model,
                "modelProvider": self.model_provider,
                "cwd": str(self.cwd) if self.cwd is not None else None,
                "runtimeWorkspaceRoots": _paths(self.runtime_workspace_roots),
                "approvalPolicy": _enum(self.approval_policy),
                "approvalsReviewer": _enum(self.approvals_reviewer),
                "sandbox": _enum(self.sandbox),
                "permissions": self.permissions,
                "config": _to_json(self.config),
            }
        )
        if self.exclude_turns:
            data["excludeTurns"] = True
        return data


@dataclass(frozen=True)
class TurnStartParams:
    thread_id: str
    input: tuple[UserInput, ...]
    responsesapi_client_metadata: JsonValue | None = None
    additional_context: JsonValue | None = None
    environments: JsonValue | None = None
    cwd: Path | str | None = None
    runtime_workspace_roots: tuple[Path, ...] | None = None
    approval_policy: AskForApproval | None = None
    approvals_reviewer: ApprovalsReviewer | None = None
    sandbox_policy: JsonValue | None = None
    permissions: str | None = None
    model: str | None = None
    service_tier: str | None = None
    effort: JsonValue | None = None
    summary: JsonValue | None = None
    personality: JsonValue | None = None
    output_schema: JsonValue | None = None
    collaboration_mode: JsonValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.input, tuple):
            object.__setattr__(self, "input", tuple(self.input))
        if self.runtime_workspace_roots is not None and not isinstance(self.runtime_workspace_roots, tuple):
            object.__setattr__(self, "runtime_workspace_roots", tuple(Path(root) for root in self.runtime_workspace_roots))
        elif self.runtime_workspace_roots is not None:
            object.__setattr__(self, "runtime_workspace_roots", tuple(Path(root) for root in self.runtime_workspace_roots))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "threadId": self.thread_id,
                "input": [item.to_mapping() for item in self.input],
                "responsesapiClientMetadata": _to_json(self.responsesapi_client_metadata),
                "additionalContext": _to_json(self.additional_context),
                "environments": _to_json(self.environments),
                "cwd": str(self.cwd) if self.cwd is not None else None,
                "runtimeWorkspaceRoots": _paths(self.runtime_workspace_roots),
                "approvalPolicy": _enum(self.approval_policy),
                "approvalsReviewer": _enum(self.approvals_reviewer),
                "sandboxPolicy": _to_json(self.sandbox_policy),
                "permissions": self.permissions,
                "model": self.model,
                "serviceTier": self.service_tier,
                "effort": _to_json(self.effort),
                "summary": _to_json(self.summary),
                "personality": _to_json(self.personality),
                "outputSchema": _to_json(self.output_schema),
                "collaborationMode": _to_json(self.collaboration_mode),
            }
        )


@dataclass(frozen=True)
class ReviewStartParams:
    thread_id: str
    target: ReviewTarget
    delivery: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _clean_review_target_for_start(self.target))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "threadId": self.thread_id,
                "target": self.target.to_mapping(),
                "delivery": self.delivery,
            }
        )


def _clean_review_target_for_start(target: ReviewTarget) -> ReviewTarget:
    if target.type == "uncommittedChanges":
        return ReviewTarget.uncommitted_changes()
    if target.type == "baseBranch":
        branch = (target.branch or "").strip()
        if branch == "":
            raise ValueError("branch must not be empty")
        return ReviewTarget.base_branch(branch)
    if target.type == "commit":
        sha = (target.sha or "").strip()
        if sha == "":
            raise ValueError("sha must not be empty")
        title = None if target.title is None else target.title.strip()
        if title == "":
            title = None
        return ReviewTarget.commit(sha, title)
    if target.type == "custom":
        instructions = (target.instructions or "").strip()
        if instructions == "":
            raise ValueError("instructions must not be empty")
        return ReviewTarget.custom(instructions)
    raise ValueError(f"unknown review target type: {target.type}")


@dataclass(frozen=True)
class TurnInterruptParams:
    thread_id: str
    turn_id: str

    def to_mapping(self) -> dict[str, str]:
        return {"threadId": self.thread_id, "turnId": self.turn_id}


@dataclass(frozen=True)
class ThreadUnsubscribeParams:
    thread_id: str

    def to_mapping(self) -> dict[str, str]:
        return {"threadId": self.thread_id}


@dataclass(frozen=True)
class ThreadReadParams:
    thread_id: str
    include_turns: bool = True

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "includeTurns": self.include_turns}


@dataclass(frozen=True)
class ThreadListParams:
    cursor: str | None = None
    limit: int | None = 100
    sort_key: str | None = "updated_at"
    sort_direction: str | None = None
    model_providers: tuple[str, ...] | None = None
    source_kinds: tuple[ThreadSourceKind | str, ...] | None = None
    archived: bool | None = False
    cwd: JsonValue | None = None
    use_state_db_only: bool = False
    search_term: str | None = None

    def __post_init__(self) -> None:
        if self.model_providers is not None and not isinstance(self.model_providers, tuple):
            object.__setattr__(self, "model_providers", tuple(self.model_providers))
        if self.source_kinds is not None and not isinstance(self.source_kinds, tuple):
            object.__setattr__(self, "source_kinds", tuple(self.source_kinds))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "cursor": self.cursor,
                "limit": self.limit,
                "sortKey": self.sort_key,
                "sortDirection": self.sort_direction,
                "modelProviders": _to_json(self.model_providers),
                "sourceKinds": _to_json(self.source_kinds),
                "archived": self.archived,
                "cwd": _to_json(self.cwd),
                "useStateDbOnly": self.use_state_db_only,
                "searchTerm": self.search_term,
            }
        )


@dataclass(frozen=True)
class JsonRpcError:
    message: str
    code: int = -32000
    data: JsonValue | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"code": self.code, "message": self.message, "data": _to_json_preserve_none(self.data)}


@dataclass(frozen=True)
class TypedRequestError:
    kind: str
    method: str
    source: JsonValue

    @classmethod
    def transport(cls, method: str, source: object) -> "TypedRequestError":
        return cls("transport", method, source)

    @classmethod
    def server(cls, method: str, source: JsonRpcError) -> "TypedRequestError":
        return cls("server", method, source)

    @classmethod
    def deserialize(cls, method: str, source: object) -> "TypedRequestError":
        return cls("deserialize", method, source)

    def __str__(self) -> str:
        if self.kind == "transport":
            return f"{self.method} transport error: {self.source}"
        if self.kind == "server":
            error = self.source if isinstance(self.source, JsonRpcError) else json_rpc_error_from_mapping(self.source)
            text = f"{self.method} failed: {error.message} (code {error.code})"
            if error.data is not None:
                text += f", data: {_compact_json(error.data)}"
            return text
        if self.kind == "deserialize":
            return f"{self.method} response decode error: {self.source}"
        return f"{self.method} {self.kind} error: {self.source}"

    def to_mapping(self) -> dict[str, JsonValue]:
        data = {
            "kind": self.kind,
            "method": self.method,
            "message": str(self),
        }
        if self.kind == "server" and isinstance(self.source, JsonRpcError):
            data["source"] = self.source.to_mapping()
        else:
            data["source"] = str(self.source)
        return data


@dataclass(frozen=True)
class TypedRequestResult:
    value: JsonValue | None = None
    error: TypedRequestError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.error is not None:
            return {"ok": False, "error": self.error.to_mapping()}
        return {"ok": True, "value": _to_json_preserve_none(self.value)}


@dataclass(frozen=True)
class JsonRpcRequestEnvelope:
    id: str | int
    method: str
    params: JsonValue | None = None
    trace: JsonValue | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "id": self.id,
                "method": self.method,
                "params": _to_json(self.params),
                "trace": _to_json_preserve_none(self.trace) if self.trace is not None else None,
            }
        )


@dataclass(frozen=True)
class JsonRpcNotificationEnvelope:
    method: str
    params: JsonValue | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "method": self.method,
                "params": _to_json_preserve_none(self.params) if self.params is not None else None,
            }
        )


@dataclass(frozen=True)
class JsonRpcResponseEnvelope:
    id: str | int
    result: JsonValue

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id, "result": _to_json_preserve_none(self.result)}


@dataclass(frozen=True)
class JsonRpcErrorEnvelope:
    id: str | int
    error: JsonRpcError

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id, "error": json_rpc_error_wire_mapping(self.error)}


@dataclass(frozen=True)
class AppServerEvent:
    kind: str
    request: JsonValue | None = None
    notification: JsonValue | None = None
    skipped: int | None = None
    message: str | None = None

    @classmethod
    def server_request(cls, request: JsonValue) -> "AppServerEvent":
        return cls(kind="server_request", request=request)

    @classmethod
    def server_notification(cls, notification: JsonValue) -> "AppServerEvent":
        return cls(kind="server_notification", notification=notification)

    @classmethod
    def lagged(cls, skipped: int) -> "AppServerEvent":
        return cls(kind="lagged", skipped=skipped)

    @classmethod
    def disconnected(cls, message: str) -> "AppServerEvent":
        return cls(kind="disconnected", message=message)

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.kind == "server_request":
            return {"type": "ServerRequest", "request": _to_json_preserve_none(self.request)}
        if self.kind == "server_notification":
            return {"type": "ServerNotification", "notification": _to_json_preserve_none(self.notification)}
        if self.kind == "lagged":
            return {"type": "Lagged", "skipped": self.skipped or 0}
        if self.kind == "disconnected":
            return {"type": "Disconnected", "message": self.message or ""}
        return {"type": self.kind}


@dataclass(frozen=True)
class RemoteAppServerClientState:
    pending_requests: tuple[tuple[str | int, str], ...] = ()
    pending_events: tuple[AppServerEvent, ...] = ()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "pendingRequests": [
                {"id": request_id, "method": method} for request_id, method in self.pending_requests
            ],
            "pendingEvents": [event.to_mapping() for event in self.pending_events],
        }


@dataclass(frozen=True)
class RemoteInitializeState:
    request_id: str | int = "initialize"
    pending_events: tuple[AppServerEvent, ...] = ()
    complete: bool = False

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "requestId": self.request_id,
            "pendingEvents": [event.to_mapping() for event in self.pending_events],
            "complete": self.complete,
        }


@dataclass(frozen=True)
class RemoteInitializeStep:
    state: RemoteInitializeState
    outgoing: (
        JsonRpcRequestEnvelope
        | JsonRpcNotificationEnvelope
        | JsonRpcResponseEnvelope
        | JsonRpcErrorEnvelope
        | None
    ) = None
    event: AppServerEvent | None = None
    error_message: str | None = None
    ignored: bool = False

    def to_mapping(self) -> dict[str, JsonValue]:
        data = {
            "state": self.state.to_mapping(),
            "ignored": self.ignored,
        }
        if self.outgoing is not None:
            data["outgoing"] = self.outgoing.to_mapping()
        if self.event is not None:
            data["event"] = self.event.to_mapping()
        if self.error_message is not None:
            data["errorMessage"] = self.error_message
        return data


@dataclass(frozen=True)
class RemoteInitializeWebSocketResult:
    state: RemoteInitializeState
    pending_events: tuple[AppServerEvent, ...] = ()
    sent_payloads: tuple[str, ...] = ()
    error_message: str | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "state": self.state.to_mapping(),
            "pendingEvents": [event.to_mapping() for event in self.pending_events],
            "sentPayloads": list(self.sent_payloads),
        }
        if self.error_message is not None:
            data["errorMessage"] = self.error_message
        return data


@dataclass(frozen=True)
class RemoteAppServerClientStep:
    state: RemoteAppServerClientState
    outgoing: (
        JsonRpcRequestEnvelope
        | JsonRpcNotificationEnvelope
        | JsonRpcResponseEnvelope
        | JsonRpcErrorEnvelope
        | None
    ) = None
    event: AppServerEvent | None = None
    response_id: str | int | None = None
    response_result: JsonValue | None = None
    response_error: JsonRpcError | None = None
    error_kind: str | None = None
    error_message: str | None = None
    ignored: bool = False

    def to_mapping(self) -> dict[str, JsonValue]:
        data = {
            "state": self.state.to_mapping(),
            "ignored": self.ignored,
        }
        if self.outgoing is not None:
            data["outgoing"] = self.outgoing.to_mapping()
        if self.event is not None:
            data["event"] = self.event.to_mapping()
        if self.response_id is not None:
            data["responseId"] = self.response_id
            if self.response_error is None:
                data["responseResult"] = _to_json_preserve_none(self.response_result)
        if self.response_error is not None:
            data["responseError"] = self.response_error.to_mapping()
        if self.error_kind is not None:
            data["errorKind"] = self.error_kind
        if self.error_message is not None:
            data["errorMessage"] = self.error_message
        return data


@dataclass(frozen=True)
class RemoteAppServerConnectResult:
    endpoint: str
    client: "RemoteWebSocketClient | None" = None
    initialize_result: RemoteInitializeWebSocketResult | None = None
    error_kind: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.client is not None and self.error_message is None

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "endpoint": self.endpoint,
            "ok": self.ok,
        }
        if self.client is not None:
            data["clientState"] = self.client.state.to_mapping()
        if self.initialize_result is not None:
            data["initializeResult"] = self.initialize_result.to_mapping()
        if self.error_kind is not None:
            data["errorKind"] = self.error_kind
        if self.error_message is not None:
            data["errorMessage"] = self.error_message
        return data


@dataclass(frozen=True)
class RemotePendingRequestFailure:
    request_id: str | int
    method: str
    error_kind: str
    error_message: str

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "requestId": self.request_id,
            "method": self.method,
            "errorKind": self.error_kind,
            "errorMessage": self.error_message,
        }


@dataclass(frozen=True)
class RemoteWorkerExitResult:
    state: RemoteAppServerClientState
    failures: tuple[RemotePendingRequestFailure, ...]

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "state": self.state.to_mapping(),
            "failures": [failure.to_mapping() for failure in self.failures],
        }


@dataclass(frozen=True)
class RemoteClientShutdownPlan:
    state_after_shutdown: RemoteAppServerClientState
    pending_request_failures: tuple[RemotePendingRequestFailure, ...] = ()
    drop_event_consumer: bool = True
    send_shutdown_command: bool = True
    command_timeout_seconds: int = REMOTE_APP_SERVER_SHUTDOWN_TIMEOUT_SECONDS
    worker_timeout_seconds: int = REMOTE_APP_SERVER_SHUTDOWN_TIMEOUT_SECONDS
    abort_worker_on_timeout: bool = True

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "dropEventConsumer": self.drop_event_consumer,
            "sendShutdownCommand": self.send_shutdown_command,
            "commandTimeoutSeconds": self.command_timeout_seconds,
            "workerTimeoutSeconds": self.worker_timeout_seconds,
            "abortWorkerOnTimeout": self.abort_worker_on_timeout,
            "stateAfterShutdown": self.state_after_shutdown.to_mapping(),
            "pendingRequestFailures": [
                failure.to_mapping() for failure in self.pending_request_failures
            ],
        }


@dataclass(frozen=True)
class ServerRequestDecision:
    action: str
    request_id: str | int | None
    method: str
    value: JsonValue | None = None
    error: JsonRpcError | None = None

    @classmethod
    def resolve(cls, request_id: str | int | None, method: str, value: JsonValue) -> "ServerRequestDecision":
        return cls(action="resolve", request_id=request_id, method=method, value=value)

    @classmethod
    def reject(cls, request_id: str | int | None, method: str, reason: str) -> "ServerRequestDecision":
        return cls(action="reject", request_id=request_id, method=method, error=JsonRpcError(reason))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "action": self.action,
            "requestId": self.request_id,
            "method": self.method,
        }
        if self.value is not None:
            data["value"] = _to_json_preserve_none(self.value)
        if self.error is not None:
            data["error"] = self.error.to_mapping()
        return _drop_none(data)


@dataclass(frozen=True)
class ExecLoopNotificationDecision:
    notification: JsonValue
    event_indicates_error: bool
    should_process: bool
    needs_backfill: bool = False
    backfill_request: ClientRequest | None = None


@dataclass(frozen=True)
class ExecLoopServerEventDecision:
    kind: str
    event_indicates_error: bool = False
    server_request: ServerRequestDecision | None = None
    notification: ExecLoopNotificationDecision | None = None
    warning: str | None = None


@dataclass(frozen=True)
class ExecLoopState:
    thread_id: str
    turn_id: str
    thread_ephemeral: bool = False
    error_seen: bool = False
    interrupt_channel_open: bool = True


def _exec_loop_state_mapping(state: ExecLoopState) -> dict[str, JsonValue]:
    return {
        "threadId": state.thread_id,
        "turnId": state.turn_id,
        "threadEphemeral": state.thread_ephemeral,
        "errorSeen": state.error_seen,
        "interruptChannelOpen": state.interrupt_channel_open,
    }


def exec_session_config_mapping(config: ExecSessionConfig) -> dict[str, JsonValue]:
    return _drop_none(
        {
            "model": config.model,
            "modelProviderId": config.model_provider_id,
            "cwd": str(config.cwd),
            "workspaceRoots": [str(root) for root in config.workspace_roots],
            "userInstructions": config.user_instructions,
            "instructionSources": [str(path) for path in config.instruction_sources],
            "startupWarnings": list(config.startup_warnings),
            "approvalPolicy": _enum(config.approval_policy),
            "approvalsReviewer": _enum(config.approvals_reviewer),
            "permissionProfile": _to_json(config.permission_profile),
            "activePermissionProfile": _to_json(config.active_permission_profile),
            "ephemeral": config.ephemeral,
            "reasoningEffort": _to_json(config.reasoning_effort),
            "hideAgentReasoning": config.hide_agent_reasoning,
            "showRawAgentReasoning": config.show_raw_agent_reasoning,
        }
    )


@dataclass(frozen=True)
class ExecLoopStepResult:
    state: ExecLoopState
    decision: ExecLoopServerEventDecision
    server_request: ServerRequestDecision | None = None
    notification_to_process: JsonValue | None = None
    warning_to_process: str | None = None
    backfill_request: ClientRequest | None = None
    awaiting_backfill: bool = False
    shutdown_request: ClientRequest | None = None
    should_break: bool = False


@dataclass(frozen=True)
class ExecLoopInterruptResult:
    state: ExecLoopState
    interrupt_request: ClientRequest | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "state": _exec_loop_state_mapping(self.state),
                "interruptRequest": None
                if self.interrupt_request is None
                else self.interrupt_request.to_mapping(),
            }
        )


@dataclass(frozen=True)
class ExecLoopActionFailureResult:
    state: ExecLoopState
    warning: str | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "state": _exec_loop_state_mapping(self.state),
                "warning": self.warning,
            }
        )


@dataclass(frozen=True)
class ExecLoopCompletionResult:
    state: ExecLoopState
    actions: tuple["ExecLoopAction", ...]
    exit_code: int

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "state": _exec_loop_state_mapping(self.state),
            "actions": [action.to_mapping() for action in self.actions],
            "exitCode": self.exit_code,
        }


@dataclass(frozen=True)
class ExecLoopAction:
    kind: str
    server_request: ServerRequestDecision | None = None
    client_request: ClientRequest | None = None
    notification: JsonValue | None = None
    warning: str | None = None
    config: ExecSessionConfig | JsonValue | None = None
    prompt: str | None = None
    session_configured: SessionConfiguredEvent | JsonValue | None = None

    @classmethod
    def server_request_action(cls, decision: ServerRequestDecision) -> "ExecLoopAction":
        kind = "resolve_server_request" if decision.action == "resolve" else "reject_server_request"
        return cls(kind=kind, server_request=decision)

    @classmethod
    def send_request(cls, request: ClientRequest) -> "ExecLoopAction":
        return cls(kind="send_request", client_request=request)

    @classmethod
    def process_notification(cls, notification: JsonValue) -> "ExecLoopAction":
        return cls(kind="process_notification", notification=notification)

    @classmethod
    def process_warning(cls, warning: str) -> "ExecLoopAction":
        return cls(kind="process_warning", warning=warning)

    @classmethod
    def break_loop(cls) -> "ExecLoopAction":
        return cls(kind="break")

    @classmethod
    def shutdown_client(cls) -> "ExecLoopAction":
        return cls(kind="shutdown_client")

    @classmethod
    def print_final_output(cls) -> "ExecLoopAction":
        return cls(kind="print_final_output")

    @classmethod
    def print_config_summary(
        cls,
        config: ExecSessionConfig,
        prompt: str,
        session_configured: SessionConfiguredEvent,
    ) -> "ExecLoopAction":
        return cls(
            kind="print_config_summary",
            config=config,
            prompt=prompt,
            session_configured=session_configured,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "kind": self.kind,
                "serverRequest": None if self.server_request is None else self.server_request.to_mapping(),
                "clientRequest": None if self.client_request is None else self.client_request.to_mapping(),
                "notification": _to_json_preserve_none(self.notification) if self.notification is not None else None,
                "warning": self.warning,
                "config": None
                if self.config is None
                else (
                    exec_session_config_mapping(self.config)
                    if isinstance(self.config, ExecSessionConfig)
                    else _to_json_preserve_none(self.config)
                ),
                "prompt": self.prompt,
                "sessionConfigured": _to_json_preserve_none(self.session_configured)
                if self.session_configured is not None
                else None,
            }
        )


@dataclass(frozen=True)
class ExecLoopCycleResult:
    state: ExecLoopState
    actions: tuple[ExecLoopAction, ...]
    should_break: bool = False
    awaiting_backfill: bool = False

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "state": _exec_loop_state_mapping(self.state),
            "actions": [action.to_mapping() for action in self.actions],
            "shouldBreak": self.should_break,
            "awaitingBackfill": self.awaiting_backfill,
        }


@dataclass(frozen=True)
class ExecSessionStartupResult:
    bootstrap: ThreadBootstrapResult
    initial_operation: InitialOperationResult
    loop_state: ExecLoopState
    synthetic_notifications: tuple[JsonValue, ...] = ()


@dataclass(frozen=True)
class RemoteExecSessionStartupResult:
    bootstrap_request: "ThreadBootstrapRequest"
    bootstrap_step: RemoteAppServerClientStep | None = None
    bootstrap: ThreadBootstrapResult | None = None
    initial_request: "InitialOperationRequest | None" = None
    initial_step: RemoteAppServerClientStep | None = None
    initial_operation: InitialOperationResult | None = None
    startup: ExecSessionStartupResult | None = None
    error: TypedRequestError | None = None

    @property
    def ok(self) -> bool:
        return self.startup is not None and self.error is None

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "ok": self.ok,
            "bootstrapRequest": {
                "action": self.bootstrap_request.action,
                "request": self.bootstrap_request.request.to_mapping(),
            },
        }
        if self.bootstrap_step is not None:
            data["bootstrapStep"] = self.bootstrap_step.to_mapping()
        if self.bootstrap is not None:
            data["bootstrap"] = {
                "action": self.bootstrap.action,
                "threadId": self.bootstrap.thread_id,
                "sessionConfigured": self.bootstrap.session_configured.to_mapping(),
            }
        if self.initial_request is not None:
            data["initialRequest"] = {
                "method": self.initial_request.method,
                "request": self.initial_request.request.to_mapping(),
            }
        if self.initial_step is not None:
            data["initialStep"] = self.initial_step.to_mapping()
        if self.initial_operation is not None:
            data["initialOperation"] = {
                "taskId": self.initial_operation.task_id,
                "syntheticNotification": _to_json_preserve_none(
                    self.initial_operation.synthetic_notification
                )
                if self.initial_operation.synthetic_notification is not None
                else None,
            }
        if self.startup is not None:
            data["startup"] = {
                "loopState": _exec_loop_state_mapping(self.startup.loop_state),
                "syntheticNotifications": [
                    _to_json_preserve_none(notification)
                    for notification in self.startup.synthetic_notifications
                ],
            }
        if self.error is not None:
            data["error"] = self.error.to_mapping()
        return data


@dataclass(frozen=True)
class RemoteExecLoopActionOutcome:
    action: ExecLoopAction
    remote_step: RemoteAppServerClientStep | None = None
    close_result: "RemoteWebSocketClientCloseResult | None" = None
    response: JsonValue | None = None
    processor_status: JsonValue | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_message is None

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "action": self.action.to_mapping(),
                "remoteStep": None if self.remote_step is None else self.remote_step.to_mapping(),
                "closeResult": None if self.close_result is None else self.close_result.to_mapping(),
                "response": _to_json_preserve_none(self.response) if self.response is not None else None,
                "processorStatus": _enum(self.processor_status) if self.processor_status is not None else None,
                "errorMessage": self.error_message,
            }
        )


@dataclass(frozen=True)
class RemoteExecLoopCycleExecution:
    state: ExecLoopState
    event: JsonValue | None
    actions: tuple[ExecLoopAction, ...]
    outcomes: tuple[RemoteExecLoopActionOutcome, ...]
    should_break: bool = False
    awaiting_backfill: bool = False
    error_message: str | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "state": _exec_loop_state_mapping(self.state),
                "event": _to_json_preserve_none(self.event) if self.event is not None else None,
                "actions": [action.to_mapping() for action in self.actions],
                "outcomes": [outcome.to_mapping() for outcome in self.outcomes],
                "shouldBreak": self.should_break,
                "awaitingBackfill": self.awaiting_backfill,
                "errorMessage": self.error_message,
            }
        )


@dataclass(frozen=True)
class RemoteExecLoopRunResult:
    state: ExecLoopState
    cycles: tuple[RemoteExecLoopCycleExecution, ...]
    completion: ExecLoopCompletionResult
    completion_outcomes: tuple[RemoteExecLoopActionOutcome, ...] = ()
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_message is None

    @property
    def exit_code(self) -> int:
        return self.completion.exit_code

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "ok": self.ok,
                "state": _exec_loop_state_mapping(self.state),
                "cycles": [cycle.to_mapping() for cycle in self.cycles],
                "completion": self.completion.to_mapping(),
                "completionOutcomes": [
                    outcome.to_mapping() for outcome in self.completion_outcomes
                ],
                "exitCode": self.exit_code,
                "errorMessage": self.error_message,
            }
        )


@dataclass(frozen=True)
class RemoteExecSessionRunResult:
    startup: RemoteExecSessionStartupResult
    startup_actions: tuple[ExecLoopAction, ...] = ()
    startup_outcomes: tuple[RemoteExecLoopActionOutcome, ...] = ()
    loop: RemoteExecLoopRunResult | None = None
    close_result: "RemoteWebSocketClientCloseResult | None" = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.startup.ok and self.loop is not None and self.loop.ok and self.error_message is None

    @property
    def exit_code(self) -> int:
        if self.loop is not None:
            return self.loop.exit_code
        return 1 if self.error_message is not None or self.startup.error is not None else 0

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "ok": self.ok,
                "startup": self.startup.to_mapping(),
                "startupActions": [action.to_mapping() for action in self.startup_actions],
                "startupOutcomes": [outcome.to_mapping() for outcome in self.startup_outcomes],
                "loop": None if self.loop is None else self.loop.to_mapping(),
                "closeResult": None if self.close_result is None else self.close_result.to_mapping(),
                "exitCode": self.exit_code,
                "errorMessage": self.error_message,
            }
        )


@dataclass(frozen=True)
class RemoteExecSessionConnectRunResult:
    connect: RemoteAppServerConnectResult
    session: RemoteExecSessionRunResult | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.connect.ok and self.session is not None and self.session.ok and self.error_message is None

    @property
    def exit_code(self) -> int:
        if self.session is not None:
            return self.session.exit_code
        return 1

    def to_mapping(self) -> dict[str, JsonValue]:
        return _drop_none(
            {
                "ok": self.ok,
                "connect": self.connect.to_mapping(),
                "session": None if self.session is None else self.session.to_mapping(),
                "exitCode": self.exit_code,
                "errorMessage": self.error_message,
            }
        )


@dataclass(frozen=True)
class InitialOperationRequest:
    method: str
    request: "ClientRequest"

    @property
    def request_id(self) -> str | int:
        return self.request.request_id


@dataclass(frozen=True)
class InitialOperationResult:
    task_id: str
    synthetic_notification: JsonValue | None = None


@dataclass(frozen=True)
class ResumeThreadIdLookup:
    kind: str
    request: "ClientRequest" | None = None
    thread_id: str | None = None
    exact_name: str | None = None
    include_all: bool = False
    cursor: str | None = None


@dataclass(frozen=True)
class ResumeThreadIdListResult:
    thread_id: str | None
    next_cursor: str | None = None
    done: bool = True


@dataclass(frozen=True)
class ThreadBootstrapRequest:
    action: str
    request: "ClientRequest"

    @property
    def method(self) -> str:
        return self.request.method

    @property
    def request_id(self) -> str | int:
        return self.request.request_id


@dataclass(frozen=True)
class ThreadBootstrapResult:
    action: str
    thread_id: str
    session_configured: SessionConfiguredEvent


@dataclass(frozen=True)
class ClientRequest:
    method: str
    params: JsonValue
    request_id: str | int

    @classmethod
    def thread_start(cls, request_id: str | int, params: ThreadStartParams) -> "ClientRequest":
        return cls("thread/start", params, request_id)

    @classmethod
    def thread_resume(cls, request_id: str | int, params: ThreadResumeParams) -> "ClientRequest":
        return cls("thread/resume", params, request_id)

    @classmethod
    def turn_start(cls, request_id: str | int, params: TurnStartParams) -> "ClientRequest":
        return cls("turn/start", params, request_id)

    @classmethod
    def review_start(cls, request_id: str | int, params: ReviewStartParams) -> "ClientRequest":
        return cls("review/start", params, request_id)

    @classmethod
    def turn_interrupt(cls, request_id: str | int, params: TurnInterruptParams) -> "ClientRequest":
        return cls("turn/interrupt", params, request_id)

    @classmethod
    def thread_unsubscribe(cls, request_id: str | int, params: ThreadUnsubscribeParams) -> "ClientRequest":
        return cls("thread/unsubscribe", params, request_id)

    @classmethod
    def thread_read(cls, request_id: str | int, params: ThreadReadParams) -> "ClientRequest":
        return cls("thread/read", params, request_id)

    @classmethod
    def thread_list(cls, request_id: str | int, params: ThreadListParams) -> "ClientRequest":
        return cls("thread/list", params, request_id)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "method": self.method,
            "requestId": self.request_id,
            "params": _to_json(self.params),
        }


def jsonrpc_request_from_client_request(
    request: ClientRequest,
    *,
    trace: JsonValue | None = None,
) -> JsonRpcRequestEnvelope:
    return JsonRpcRequestEnvelope(
        id=request.request_id,
        method=request.method,
        params=request.params,
        trace=trace,
    )


def jsonrpc_notification(method: str, params: JsonValue | None = None) -> JsonRpcNotificationEnvelope:
    return JsonRpcNotificationEnvelope(method=method, params=params)


def jsonrpc_message_to_mapping(
    message: JsonRpcRequestEnvelope
    | JsonRpcNotificationEnvelope
    | JsonRpcResponseEnvelope
    | JsonRpcErrorEnvelope
    | Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    if hasattr(message, "to_mapping") and callable(message.to_mapping):
        data = message.to_mapping()
    else:
        data = dict(message)
    jsonrpc_message_kind(data)
    return data


def encode_jsonrpc_message(
    message: JsonRpcRequestEnvelope
    | JsonRpcNotificationEnvelope
    | JsonRpcResponseEnvelope
    | JsonRpcErrorEnvelope
    | Mapping[str, JsonValue],
) -> str:
    return json.dumps(
        jsonrpc_message_to_mapping(message),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def encode_jsonrpc_websocket_text_frame(
    message: JsonRpcRequestEnvelope
    | JsonRpcNotificationEnvelope
    | JsonRpcResponseEnvelope
    | JsonRpcErrorEnvelope
    | Mapping[str, JsonValue],
    *,
    mask: bool = True,
    mask_key: bytes | None = None,
    max_message_size: int = REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
) -> bytes:
    return encode_websocket_text_message(
        encode_jsonrpc_message(message),
        mask=mask,
        mask_key=mask_key,
        max_message_size=max_message_size,
    )


def remote_write_jsonrpc_websocket_message(websocket: JsonValue, message: JsonValue) -> str:
    payload = encode_jsonrpc_message(message)
    websocket.send_text(payload)
    return payload


def remote_read_websocket_frame_event(
    websocket: JsonValue,
    *,
    close_default: str = "connection closed",
) -> JsonValue:
    return websocket_frame_event(websocket.recv_frame(), close_default=close_default)


def decode_jsonrpc_message(text: str | bytes) -> dict[str, JsonValue]:
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    value = json.loads(text)
    if not isinstance(value, Mapping):
        raise TypeError("JSON-RPC message must be a mapping")
    message = dict(value)
    jsonrpc_message_kind(message)
    return message


def remote_initialize_request(
    params: JsonValue,
    *,
    request_id: str | int = "initialize",
    trace: JsonValue | None = None,
) -> JsonRpcRequestEnvelope:
    return jsonrpc_request_from_client_request(
        ClientRequest("initialize", params, request_id),
        trace=trace,
    )


def remote_initialized_notification() -> JsonRpcNotificationEnvelope:
    return jsonrpc_notification("initialized")


def json_rpc_error_wire_mapping(error: JsonRpcError) -> dict[str, JsonValue]:
    data = {"code": error.code, "message": error.message}
    if error.data is not None:
        data["data"] = _to_json_preserve_none(error.data)
    return data


def jsonrpc_message_from_server_request_decision(
    decision: ServerRequestDecision,
) -> JsonRpcResponseEnvelope | JsonRpcErrorEnvelope:
    request_id = decision.request_id
    if request_id is None:
        raise ValueError("server request decision is missing request_id")
    if decision.action == "resolve":
        return JsonRpcResponseEnvelope(request_id, decision.value)
    if decision.action == "reject":
        if decision.error is None:
            raise ValueError("reject server request decision is missing error")
        return JsonRpcErrorEnvelope(request_id, decision.error)
    raise ValueError(f"unsupported server request decision action `{decision.action}`")


def exec_loop_action_jsonrpc_message(
    action: ExecLoopAction,
    *,
    trace: JsonValue | None = None,
) -> JsonRpcRequestEnvelope | JsonRpcResponseEnvelope | JsonRpcErrorEnvelope | None:
    if action.client_request is not None:
        return jsonrpc_request_from_client_request(action.client_request, trace=trace)
    if action.server_request is not None:
        return jsonrpc_message_from_server_request_decision(action.server_request)
    return None


def remote_initialize_start(
    params: JsonValue,
    *,
    request_id: str | int = "initialize",
    trace: JsonValue | None = None,
) -> RemoteInitializeStep:
    state = RemoteInitializeState(request_id=request_id)
    return RemoteInitializeStep(
        state=state,
        outgoing=remote_initialize_request(params, request_id=request_id, trace=trace),
    )


def remote_initialize_handle_jsonrpc_message(
    state: RemoteInitializeState,
    message: JsonValue,
    *,
    endpoint: str | None = None,
) -> RemoteInitializeStep:
    kind = jsonrpc_message_kind(message)
    if kind == "response":
        if _field(message, "id") != state.request_id:
            return RemoteInitializeStep(state=state, ignored=True)
        return RemoteInitializeStep(
            state=replace(state, complete=True),
            outgoing=remote_initialized_notification(),
        )

    if kind == "error":
        if _field(message, "id") != state.request_id:
            return RemoteInitializeStep(state=state, ignored=True)
        error = json_rpc_error_from_mapping(_required_field(message, "error"))
        return RemoteInitializeStep(
            state=state,
            error_message=remote_initialize_rejected_message(endpoint, error.message)
            if endpoint is not None
            else f"remote app server rejected initialize: {error.message}",
        )

    if kind == "notification":
        event = AppServerEvent.server_notification(message)
        next_state = replace(state, pending_events=state.pending_events + (event,))
        return RemoteInitializeStep(state=next_state, event=event)

    if kind == "request":
        method = str(_required_field(message, "method"))
        request_id = _required_field(message, "id")
        if is_supported_remote_server_request_method(method):
            event = AppServerEvent.server_request(message)
            next_state = replace(state, pending_events=state.pending_events + (event,))
            return RemoteInitializeStep(state=next_state, event=event)
        return RemoteInitializeStep(
            state=state,
            outgoing=JsonRpcErrorEnvelope(
                request_id,
                unsupported_remote_server_request_error(method),
            ),
        )

    raise ValueError("invalid JSON-RPC message")


def remote_initialize_handle_jsonrpc_text(
    state: RemoteInitializeState,
    text: str | bytes,
    *,
    endpoint: str | None = None,
) -> RemoteInitializeStep:
    return remote_initialize_handle_jsonrpc_message(
        state,
        decode_jsonrpc_message(text),
        endpoint=endpoint,
    )


def _websocket_event_field(event: JsonValue, name: str, default: JsonValue | None = None) -> JsonValue:
    if isinstance(event, Mapping):
        if name in event:
            return event[name]
        parts = name.split("_")
        camel_name = parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
        return event.get(camel_name, default)
    return getattr(event, name, default)


def remote_initialize_handle_websocket_event(
    state: RemoteInitializeState,
    event: JsonValue,
    *,
    endpoint: str,
) -> RemoteInitializeStep:
    kind = _websocket_event_field(event, "kind")
    if kind == "text":
        try:
            return remote_initialize_handle_jsonrpc_text(
                state,
                _websocket_event_field(event, "text", ""),
                endpoint=endpoint,
            )
        except Exception as exc:
            return RemoteInitializeStep(
                state=state,
                error_message=remote_initialize_invalid_response_message(endpoint, exc),
            )
    if kind == "close":
        return RemoteInitializeStep(
            state=state,
            error_message=remote_initialize_closed_message(
                endpoint,
                _websocket_event_field(event, "close_reason"),
            ),
        )
    if kind == "ignored":
        return RemoteInitializeStep(state=state, ignored=True)
    raise ValueError(f"unsupported websocket frame event kind `{kind}`")


def _remote_initialize_write_outgoing(
    websocket: JsonValue,
    outgoing: JsonValue | None,
    sent_payloads: tuple[str, ...],
) -> tuple[str, ...]:
    if outgoing is None:
        return sent_payloads
    return sent_payloads + (remote_write_jsonrpc_websocket_message(websocket, outgoing),)


def remote_initialize_websocket_connection(
    websocket: JsonValue,
    params: JsonValue,
    *,
    endpoint: str,
    request_id: str | int = "initialize",
    trace: JsonValue | None = None,
    max_frames: int | None = None,
) -> RemoteInitializeWebSocketResult:
    step = remote_initialize_start(params, request_id=request_id, trace=trace)
    state = step.state
    sent_payloads: tuple[str, ...] = ()
    try:
        sent_payloads = _remote_initialize_write_outgoing(websocket, step.outgoing, sent_payloads)
    except Exception as exc:
        return RemoteInitializeWebSocketResult(
            state=state,
            sent_payloads=sent_payloads,
            error_message=remote_write_websocket_message_failed_message(endpoint, exc),
        )

    frames_read = 0
    while True:
        if max_frames is not None and frames_read >= max_frames:
            return RemoteInitializeWebSocketResult(
                state=state,
                pending_events=state.pending_events,
                sent_payloads=sent_payloads,
                error_message=remote_initialize_timeout_message(endpoint),
            )
        try:
            event = remote_read_websocket_frame_event(
                websocket,
                close_default="connection closed during initialize",
            )
        except (TimeoutError, socket.timeout):
            return RemoteInitializeWebSocketResult(
                state=state,
                pending_events=state.pending_events,
                sent_payloads=sent_payloads,
                error_message=remote_initialize_timeout_message(endpoint),
            )
        except EOFError:
            return RemoteInitializeWebSocketResult(
                state=state,
                pending_events=state.pending_events,
                sent_payloads=sent_payloads,
                error_message=remote_initialize_closed_eof_message(endpoint),
            )
        except Exception as exc:
            return RemoteInitializeWebSocketResult(
                state=state,
                pending_events=state.pending_events,
                sent_payloads=sent_payloads,
                error_message=remote_initialize_transport_failed_message(endpoint, exc),
            )

        frames_read += 1
        step = remote_initialize_handle_websocket_event(state, event, endpoint=endpoint)
        state = step.state
        try:
            sent_payloads = _remote_initialize_write_outgoing(websocket, step.outgoing, sent_payloads)
        except Exception as exc:
            return RemoteInitializeWebSocketResult(
                state=state,
                pending_events=state.pending_events,
                sent_payloads=sent_payloads,
                error_message=remote_write_websocket_message_failed_message(endpoint, exc),
            )
        if step.error_message is not None:
            return RemoteInitializeWebSocketResult(
                state=state,
                pending_events=state.pending_events,
                sent_payloads=sent_payloads,
                error_message=step.error_message,
            )
        if state.complete:
            return RemoteInitializeWebSocketResult(
                state=state,
                pending_events=state.pending_events,
                sent_payloads=sent_payloads,
            )


def remote_client_state_from_initialize(state: RemoteInitializeState) -> RemoteAppServerClientState:
    return RemoteAppServerClientState(pending_events=state.pending_events)


def remote_client_send_request(
    state: RemoteAppServerClientState,
    request: ClientRequest,
    *,
    trace: JsonValue | None = None,
) -> RemoteAppServerClientStep:
    pending = _pending_request_dict(state)
    if request.request_id in pending:
        return RemoteAppServerClientStep(
            state=state,
            error_kind="InvalidInput",
            error_message=remote_duplicate_request_id_message(request.request_id),
        )
    pending[request.request_id] = request.method
    next_state = replace(state, pending_requests=tuple(pending.items()))
    return RemoteAppServerClientStep(
        state=next_state,
        outgoing=jsonrpc_request_from_client_request(request, trace=trace),
    )


def remote_client_send_notification(
    state: RemoteAppServerClientState,
    method: str,
    params: JsonValue | None = None,
) -> RemoteAppServerClientStep:
    return RemoteAppServerClientStep(
        state=state,
        outgoing=jsonrpc_notification(method, params),
    )


def remote_client_send_initialized_notification(
    state: RemoteAppServerClientState,
) -> RemoteAppServerClientStep:
    return RemoteAppServerClientStep(
        state=state,
        outgoing=remote_initialized_notification(),
    )


def remote_client_resolve_or_reject_server_request(
    state: RemoteAppServerClientState,
    decision: ServerRequestDecision,
) -> RemoteAppServerClientStep:
    return RemoteAppServerClientStep(
        state=state,
        outgoing=jsonrpc_message_from_server_request_decision(decision),
    )


def remote_client_next_event(state: RemoteAppServerClientState) -> RemoteAppServerClientStep:
    if not state.pending_events:
        return RemoteAppServerClientStep(state=state, ignored=True)
    return RemoteAppServerClientStep(
        state=replace(state, pending_events=state.pending_events[1:]),
        event=state.pending_events[0],
    )


def remote_client_enqueue_event(
    state: RemoteAppServerClientState,
    event: AppServerEvent,
) -> RemoteAppServerClientState:
    return replace(state, pending_events=state.pending_events + (event,))


def remote_client_worker_exit(
    state: RemoteAppServerClientState,
    *,
    error_kind: str = "BrokenPipe",
    error_message: str | None = None,
) -> RemoteWorkerExitResult:
    message = error_message or remote_worker_channel_closed_message()
    failures = tuple(
        RemotePendingRequestFailure(request_id, method, error_kind, message)
        for request_id, method in state.pending_requests
    )
    return RemoteWorkerExitResult(
        state=replace(state, pending_requests=()),
        failures=failures,
    )


def remote_client_shutdown_plan(
    state: RemoteAppServerClientState,
    *,
    error_kind: str = "BrokenPipe",
    error_message: str | None = None,
) -> RemoteClientShutdownPlan:
    worker_exit = remote_client_worker_exit(
        state,
        error_kind=error_kind,
        error_message=error_message,
    )
    return RemoteClientShutdownPlan(
        state_after_shutdown=worker_exit.state,
        pending_request_failures=worker_exit.failures,
    )


def typed_request_transport_error(method: str, source: object) -> TypedRequestError:
    return TypedRequestError.transport(method, source)


def typed_request_server_error(method: str, source: JsonRpcError) -> TypedRequestError:
    return TypedRequestError.server(method, source)


def typed_request_deserialize_error(method: str, source: object) -> TypedRequestError:
    return TypedRequestError.deserialize(method, source)


def typed_request_result_from_response(
    method: str,
    *,
    transport_error: object | None = None,
    response_result: JsonValue | None = None,
    response_error: JsonRpcError | None = None,
    decoder: Callable[[JsonValue], JsonValue] | None = None,
) -> TypedRequestResult:
    if transport_error is not None:
        return TypedRequestResult(error=typed_request_transport_error(method, transport_error))
    if response_error is not None:
        return TypedRequestResult(error=typed_request_server_error(method, response_error))
    if decoder is None:
        return TypedRequestResult(value=response_result)
    try:
        return TypedRequestResult(value=decoder(response_result))
    except Exception as exc:
        return TypedRequestResult(error=typed_request_deserialize_error(method, exc))


def typed_request_result_from_remote_step(
    request: ClientRequest,
    step: RemoteAppServerClientStep,
    *,
    decoder: Callable[[JsonValue], JsonValue] | None = None,
) -> TypedRequestResult:
    return typed_request_result_from_response(
        request.method,
        transport_error=step.error_message,
        response_result=step.response_result,
        response_error=step.response_error,
        decoder=decoder,
    )


def remote_client_handle_jsonrpc_message(
    state: RemoteAppServerClientState,
    message: JsonValue,
) -> RemoteAppServerClientStep:
    kind = jsonrpc_message_kind(message)
    if kind == "response":
        request_id = _required_field(message, "id")
        pending = _pending_request_dict(state)
        if request_id not in pending:
            return RemoteAppServerClientStep(state=state, ignored=True)
        pending.pop(request_id)
        return RemoteAppServerClientStep(
            state=replace(state, pending_requests=tuple(pending.items())),
            response_id=request_id,
            response_result=_field(message, "result"),
        )

    if kind == "error":
        request_id = _required_field(message, "id")
        pending = _pending_request_dict(state)
        if request_id not in pending:
            return RemoteAppServerClientStep(state=state, ignored=True)
        pending.pop(request_id)
        return RemoteAppServerClientStep(
            state=replace(state, pending_requests=tuple(pending.items())),
            response_id=request_id,
            response_error=json_rpc_error_from_mapping(_required_field(message, "error")),
        )

    if kind == "notification":
        return RemoteAppServerClientStep(
            state=state,
            event=AppServerEvent.server_notification(message),
        )

    if kind == "request":
        method = str(_required_field(message, "method"))
        request_id = _required_field(message, "id")
        if is_supported_remote_server_request_method(method):
            return RemoteAppServerClientStep(
                state=state,
                event=AppServerEvent.server_request(message),
            )
        return RemoteAppServerClientStep(
            state=state,
            outgoing=JsonRpcErrorEnvelope(
                request_id,
                unsupported_remote_server_request_error(method),
            ),
        )

    raise ValueError("invalid JSON-RPC message")


def remote_client_handle_jsonrpc_text(
    state: RemoteAppServerClientState,
    text: str | bytes,
) -> RemoteAppServerClientStep:
    return remote_client_handle_jsonrpc_message(state, decode_jsonrpc_message(text))


def remote_client_handle_websocket_event(
    state: RemoteAppServerClientState,
    event: JsonValue,
    *,
    endpoint: str,
) -> RemoteAppServerClientStep:
    kind = _websocket_event_field(event, "kind")
    if kind == "text":
        try:
            return remote_client_handle_jsonrpc_text(
                state,
                _websocket_event_field(event, "text", ""),
            )
        except Exception as exc:
            message = remote_invalid_jsonrpc_message(endpoint, exc)
            return RemoteAppServerClientStep(
                state=state,
                event=remote_disconnected_event(message),
                error_kind="InvalidData",
                error_message=message,
            )
    if kind == "close":
        message = remote_disconnected_message(
            endpoint,
            _websocket_event_field(event, "close_reason"),
        )
        return RemoteAppServerClientStep(
            state=state,
            event=remote_disconnected_event(message),
            error_kind="ConnectionAborted",
            error_message=message,
        )
    if kind == "ignored":
        return RemoteAppServerClientStep(state=state, ignored=True)
    raise ValueError(f"unsupported websocket frame event kind `{kind}`")


def jsonrpc_message_kind(message: JsonValue) -> str:
    if not isinstance(message, Mapping):
        raise TypeError("JSON-RPC message must be a mapping")
    has_id = "id" in message
    has_method = "method" in message
    has_result = "result" in message
    has_error = "error" in message
    if has_method and not isinstance(message["method"], str):
        raise TypeError("JSON-RPC method must be a string")
    if has_id and has_method:
        return "request"
    if has_method:
        return "notification"
    if has_id and has_result:
        return "response"
    if has_id and has_error:
        return "error"
    raise ValueError("invalid JSON-RPC message")


def json_rpc_error_from_mapping(value: JsonValue) -> JsonRpcError:
    data = value["data"] if isinstance(value, Mapping) and "data" in value else None
    code = _field(value, "code")
    return JsonRpcError(
        message=str(_required_field(value, "message")),
        code=-32000 if code is None else int(code),
        data=data,
    )


def unsupported_remote_server_request_error(method: str) -> JsonRpcError:
    normalized_method = _SERVER_REQUEST_METHOD_ALIASES.get(str(method), str(method))
    return JsonRpcError(
        message=f"unsupported remote app-server request `{normalized_method}`",
        code=-32601,
        data=None,
    )


def is_supported_remote_server_request_method(method: str) -> bool:
    return _SERVER_REQUEST_METHOD_ALIASES.get(str(method), str(method)) in set(_SERVER_REQUEST_METHOD_ALIASES.values())


def remote_websocket_config_mapping() -> dict[str, int]:
    return {
        "maxFrameSize": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
        "maxMessageSize": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    }


def websocket_url_supports_auth_token(url: str) -> bool:
    try:
        parsed = urlparse(str(url))
        host = parsed.hostname
    except ValueError:
        return False
    scheme = parsed.scheme.lower()
    if scheme == "wss" and host is not None:
        return True
    if scheme != "ws" or host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def remote_auth_token_url_error_message(websocket_url: str) -> str:
    return (
        "remote auth tokens require `wss://` or loopback `ws://` URLs; "
        f"got `{websocket_url}`"
    )


def remote_endpoint_auth_token_error(endpoint: RemoteAppServerEndpoint) -> str | None:
    if endpoint.kind != "websocket" or endpoint.auth_token is None:
        return None
    if websocket_url_supports_auth_token(str(endpoint.websocket_url)):
        return None
    return remote_auth_token_url_error_message(str(endpoint.websocket_url))


def remote_duplicate_request_id_message(request_id: str | int) -> str:
    return f"duplicate remote app-server request id `{request_id}`"


def remote_worker_channel_closed_message() -> str:
    return "remote app-server worker channel is closed"


def remote_request_channel_closed_message() -> str:
    return "remote app-server request channel is closed"


def remote_notify_channel_closed_message() -> str:
    return "remote app-server notify channel is closed"


def remote_resolve_channel_closed_message() -> str:
    return "remote app-server resolve channel is closed"


def remote_reject_channel_closed_message() -> str:
    return "remote app-server reject channel is closed"


def remote_event_consumer_channel_closed_message() -> str:
    return "remote app-server event consumer channel is closed"


def remote_close_websocket_failed_message(endpoint: str, error: object) -> str:
    return f"failed to close websocket app server `{endpoint}`: {error}"


_REMOTE_WEBSOCKET_ALREADY_CLOSED_TOKENS = {
    "alreadyclosed",
    "brokenpipe",
    "connectionclosed",
    "connectionreset",
    "notconnected",
}


def _remote_error_token(value: object) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def websocket_close_error_is_already_closed(error: object) -> bool:
    if isinstance(error, (BrokenPipeError, ConnectionResetError)):
        return True
    if isinstance(error, OSError) and error.errno in {
        errno.EPIPE,
        errno.ECONNRESET,
        errno.ENOTCONN,
    }:
        return True

    candidates: list[object] = [type(error).__name__, error]
    for attr in ("kind", "code", "name"):
        value = getattr(error, attr, None)
        if value is not None:
            candidates.append(value() if callable(value) else value)
    return any(_remote_error_token(candidate) in _REMOTE_WEBSOCKET_ALREADY_CLOSED_TOKENS for candidate in candidates)


def remote_client_shutdown_close_error(endpoint: str, error: object | None) -> str | None:
    if error is None or websocket_close_error_is_already_closed(error):
        return None
    return remote_close_websocket_failed_message(endpoint, error)


def remote_write_websocket_message_failed_message(endpoint: str, error: object) -> str:
    return f"failed to write websocket message to `{endpoint}`: {error}"


def remote_invalid_authorization_header_message(error: object) -> str:
    return f"invalid remote authorization header value: {error}"


def remote_invalid_uds_handshake_url_message(error: object) -> str:
    return f"invalid UDS websocket handshake URL: {error}"


def remote_connect_timeout_message(endpoint: str) -> str:
    return f"timed out connecting to remote app server at `{endpoint}`"


def remote_connect_failed_message(endpoint: str, error: object) -> str:
    return f"failed to connect to remote app server at `{endpoint}`: {error}"


def remote_upgrade_timeout_message(endpoint: str) -> str:
    return f"timed out upgrading remote app server at `{endpoint}`"


def remote_upgrade_failed_message(endpoint: str, error: object) -> str:
    return f"failed to upgrade remote app server at `{endpoint}`: {error}"


def remote_write_failed_message(endpoint: str, error: object) -> str:
    return f"remote app server at `{endpoint}` write failed: {error}"


def remote_invalid_jsonrpc_message(endpoint: str, error: object) -> str:
    return f"remote app server at `{endpoint}` sent invalid JSON-RPC: {error}"


def remote_disconnected_message(endpoint: str, reason: str | None = None) -> str:
    reason_text = reason if reason else "connection closed"
    return f"remote app server at `{endpoint}` disconnected: {reason_text}"


def remote_transport_failed_message(endpoint: str, error: object) -> str:
    return f"remote app server at `{endpoint}` transport failed: {error}"


def remote_closed_connection_message(endpoint: str) -> str:
    return f"remote app server at `{endpoint}` closed the connection"


def remote_initialize_invalid_response_message(endpoint: str, error: object) -> str:
    return f"remote app server at `{endpoint}` sent invalid initialize response: {error}"


def remote_initialize_rejected_message(endpoint: str, message: str) -> str:
    return f"remote app server at `{endpoint}` rejected initialize: {message}"


def remote_initialize_closed_message(endpoint: str, reason: str | None = None) -> str:
    reason_text = reason if reason else "connection closed during initialize"
    return f"remote app server at `{endpoint}` closed during initialize: {reason_text}"


def remote_initialize_transport_failed_message(endpoint: str, error: object) -> str:
    return f"remote app server at `{endpoint}` transport failed during initialize: {error}"


def remote_initialize_closed_eof_message(endpoint: str) -> str:
    return f"remote app server at `{endpoint}` closed during initialize"


def remote_initialize_timeout_message(endpoint: str) -> str:
    return f"timed out waiting for initialize response from `{endpoint}`"


def remote_disconnected_event(message: str) -> AppServerEvent:
    return AppServerEvent.disconnected(message)


@dataclass(frozen=True)
class RemoteWebSocketClientCloseResult:
    shutdown_plan: RemoteClientShutdownPlan
    close_error_message: str | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        data = {"shutdownPlan": self.shutdown_plan.to_mapping()}
        if self.close_error_message is not None:
            data["closeErrorMessage"] = self.close_error_message
        return data


class RemoteWebSocketClient:
    """Blocking remote app-server client over a stdlib-compatible WebSocket.

    The lower-level helpers above remain pure reducers.  This facade owns the
    current client state and performs the actual write/read calls against a
    WebSocket-like object with ``send_text()``, ``recv_frame()``, and ``close()``.
    """

    def __init__(
        self,
        websocket: JsonValue,
        *,
        endpoint: str,
        state: RemoteAppServerClientState | None = None,
    ) -> None:
        self.websocket = websocket
        self.endpoint = endpoint
        self.state = state or RemoteAppServerClientState()

    @classmethod
    def from_initialize_result(
        cls,
        websocket: JsonValue,
        result: RemoteInitializeWebSocketResult,
        *,
        endpoint: str,
    ) -> "RemoteWebSocketClient":
        if result.error_message is not None:
            raise ValueError(result.error_message)
        if not result.state.complete:
            raise ValueError("remote initialize result is not complete")
        return cls(
            websocket,
            endpoint=endpoint,
            state=RemoteAppServerClientState(pending_events=result.pending_events),
        )

    def send_request(
        self,
        request: ClientRequest,
        *,
        trace: JsonValue | None = None,
    ) -> RemoteAppServerClientStep:
        previous_state = self.state
        step = remote_client_send_request(self.state, request, trace=trace)
        return self._write_outgoing_step(step, previous_state=previous_state)

    def request(
        self,
        request: ClientRequest,
        *,
        trace: JsonValue | None = None,
        max_frames: int | None = None,
    ) -> RemoteAppServerClientStep:
        sent = self.send_request(request, trace=trace)
        if sent.error_message is not None or sent.outgoing is None:
            return sent

        frames_read = 0
        while True:
            if max_frames is not None and frames_read >= max_frames:
                message = f"timed out waiting for `{request.method}` response from `{self.endpoint}`"
                return self._fail_pending_requests(
                    error_kind="TimedOut",
                    error_message=message,
                    event=remote_disconnected_event(message),
                )
            step = self._read_socket_step()
            frames_read += 1
            if step.error_message is not None:
                return self._fail_pending_requests(
                    error_kind=step.error_kind or "BrokenPipe",
                    error_message=step.error_message,
                    event=step.event,
                )
            if step.response_id == request.request_id:
                return step
            if step.event is not None:
                self.state = remote_client_enqueue_event(self.state, step.event)

    def request_typed(
        self,
        request: ClientRequest,
        *,
        decoder: Callable[[JsonValue], JsonValue] | None = None,
        trace: JsonValue | None = None,
        max_frames: int | None = None,
    ) -> TypedRequestResult:
        return typed_request_result_from_remote_step(
            request,
            self.request(request, trace=trace, max_frames=max_frames),
            decoder=decoder,
        )

    def send_notification(
        self,
        method: str,
        params: JsonValue | None = None,
    ) -> RemoteAppServerClientStep:
        return self._write_outgoing_step(
            remote_client_send_notification(self.state, method, params),
            previous_state=self.state,
        )

    def send_initialized_notification(self) -> RemoteAppServerClientStep:
        return self._write_outgoing_step(
            remote_client_send_initialized_notification(self.state),
            previous_state=self.state,
        )

    def resolve_or_reject_server_request(
        self,
        decision: ServerRequestDecision,
    ) -> RemoteAppServerClientStep:
        return self._write_outgoing_step(
            remote_client_resolve_or_reject_server_request(self.state, decision),
            previous_state=self.state,
        )

    def next_event(self) -> RemoteAppServerClientStep:
        if self.state.pending_events:
            step = remote_client_next_event(self.state)
            self.state = step.state
            return step

        return self._read_socket_step()

    def _read_socket_step(self) -> RemoteAppServerClientStep:
        try:
            event = remote_read_websocket_frame_event(self.websocket)
        except EOFError:
            message = remote_closed_connection_message(self.endpoint)
            return RemoteAppServerClientStep(
                state=self.state,
                event=remote_disconnected_event(message),
                error_kind="UnexpectedEof",
                error_message=message,
            )
        except (TimeoutError, socket.timeout) as exc:
            message = remote_transport_failed_message(self.endpoint, exc)
            return RemoteAppServerClientStep(
                state=self.state,
                event=remote_disconnected_event(message),
                error_kind="TimedOut",
                error_message=message,
            )
        except Exception as exc:
            message = remote_transport_failed_message(self.endpoint, exc)
            return RemoteAppServerClientStep(
                state=self.state,
                event=remote_disconnected_event(message),
                error_kind="InvalidData",
                error_message=message,
            )

        step = remote_client_handle_websocket_event(self.state, event, endpoint=self.endpoint)
        return self._write_outgoing_step(step, previous_state=self.state)

    def poll_event(self) -> RemoteAppServerClientStep:
        return self.next_event()

    def shutdown_plan(
        self,
        *,
        error_kind: str = "BrokenPipe",
        error_message: str | None = None,
    ) -> RemoteClientShutdownPlan:
        return remote_client_shutdown_plan(
            self.state,
            error_kind=error_kind,
            error_message=error_message,
        )

    def close(
        self,
        *,
        error_kind: str = "BrokenPipe",
        error_message: str | None = None,
    ) -> RemoteWebSocketClientCloseResult:
        plan = self.shutdown_plan(error_kind=error_kind, error_message=error_message)
        self.state = plan.state_after_shutdown
        close_error_message = None
        try:
            self.websocket.close()
        except Exception as exc:
            close_error_message = remote_client_shutdown_close_error(self.endpoint, exc)
        return RemoteWebSocketClientCloseResult(plan, close_error_message)

    def _write_outgoing_step(
        self,
        step: RemoteAppServerClientStep,
        *,
        previous_state: RemoteAppServerClientState,
    ) -> RemoteAppServerClientStep:
        if step.outgoing is None:
            self.state = step.state
            return step
        try:
            remote_write_jsonrpc_websocket_message(self.websocket, step.outgoing)
        except Exception as exc:
            message = remote_write_websocket_message_failed_message(self.endpoint, exc)
            return RemoteAppServerClientStep(
                state=previous_state,
                error_kind="BrokenPipe",
                error_message=message,
            )
        self.state = step.state
        return step

    def _fail_pending_requests(
        self,
        *,
        error_kind: str,
        error_message: str,
        event: AppServerEvent | None = None,
    ) -> RemoteAppServerClientStep:
        worker_exit = remote_client_worker_exit(
            self.state,
            error_kind=error_kind,
            error_message=error_message,
        )
        self.state = worker_exit.state
        return RemoteAppServerClientStep(
            state=self.state,
            event=event,
            error_kind=error_kind,
            error_message=error_message,
        )


def remote_app_server_client_connect(
    args: RemoteAppServerConnectArgs,
    *,
    websocket_connector: Callable[..., JsonValue] | None = None,
    unix_socket_connector: Callable[..., JsonValue] | None = None,
    trace: JsonValue | None = None,
    initialize_max_frames: int | None = None,
) -> RemoteAppServerConnectResult:
    endpoint = args.endpoint.endpoint
    websocket: JsonValue

    if args.endpoint.kind == "websocket":
        auth_error = remote_endpoint_auth_token_error(args.endpoint)
        if auth_error is not None:
            return RemoteAppServerConnectResult(
                endpoint=endpoint,
                error_kind="InvalidInput",
                error_message=auth_error,
            )
        connector = websocket_connector or StdlibWebSocket.connect
        try:
            websocket = connector(
                str(args.endpoint.websocket_url),
                auth_token=args.endpoint.auth_token,
                timeout=REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
                max_message_size=REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
            )
        except (TimeoutError, socket.timeout):
            return RemoteAppServerConnectResult(
                endpoint=endpoint,
                error_kind="TimedOut",
                error_message=remote_connect_timeout_message(endpoint),
            )
        except ValueError as exc:
            return RemoteAppServerConnectResult(
                endpoint=endpoint,
                error_kind="InvalidInput",
                error_message=str(exc),
            )
        except Exception as exc:
            return RemoteAppServerConnectResult(
                endpoint=endpoint,
                error_kind="Other",
                error_message=remote_connect_failed_message(endpoint, exc),
            )
    else:
        connector = unix_socket_connector or StdlibWebSocket.connect_unix_socket
        try:
            websocket = connector(
                args.endpoint.socket_path,
                websocket_url=UDS_WEBSOCKET_HANDSHAKE_URL,
                timeout=REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
                max_message_size=REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
            )
        except (TimeoutError, socket.timeout):
            return RemoteAppServerConnectResult(
                endpoint=endpoint,
                error_kind="TimedOut",
                error_message=remote_connect_timeout_message(endpoint),
            )
        except ValueError as exc:
            return RemoteAppServerConnectResult(
                endpoint=endpoint,
                error_kind="InvalidInput",
                error_message=str(exc),
            )
        except Exception as exc:
            return RemoteAppServerConnectResult(
                endpoint=endpoint,
                error_kind="Other",
                error_message=remote_connect_failed_message(endpoint, exc),
            )

    initialize_result = remote_initialize_websocket_connection(
        websocket,
        args.initialize_params().to_mapping(),
        endpoint=endpoint,
        trace=trace,
        max_frames=initialize_max_frames,
    )
    if initialize_result.error_message is not None:
        _remote_close_after_failed_connect(websocket)
        return RemoteAppServerConnectResult(
            endpoint=endpoint,
            initialize_result=initialize_result,
            error_kind=_remote_initialize_error_kind(initialize_result.error_message),
            error_message=initialize_result.error_message,
        )

    return RemoteAppServerConnectResult(
        endpoint=endpoint,
        client=RemoteWebSocketClient.from_initialize_result(
            websocket,
            initialize_result,
            endpoint=endpoint,
        ),
        initialize_result=initialize_result,
    )


def _remote_close_after_failed_connect(websocket: JsonValue) -> None:
    try:
        websocket.close()
    except Exception:
        pass


def _remote_initialize_error_kind(message: str) -> str:
    if message.startswith("failed to write websocket message"):
        return "BrokenPipe"
    if message.startswith("timed out waiting for initialize response"):
        return "TimedOut"
    if "sent invalid initialize response:" in message:
        return "InvalidData"
    if "transport failed during initialize:" in message:
        return "InvalidData"
    if "closed during initialize:" in message:
        return "ConnectionAborted"
    if "closed during initialize" in message:
        return "UnexpectedEof"
    return "Other"


class RequestIdSequencer:
    """Upstream ``codex exec`` request IDs start at integer 1."""

    def __init__(self, next_id: int = 1) -> None:
        self.next_id = next_id

    def next(self) -> int:
        request_id = self.next_id
        self.next_id += 1
        return request_id


def permissions_selection_from_config(config: ExecSessionConfig) -> str | None:
    if config.active_permission_profile is None:
        return None
    return permission_profile_id_from_active_profile(config.active_permission_profile)


def permission_profile_id_from_active_profile(active: ActivePermissionProfile) -> str:
    return active.id


def sandbox_mode_from_permission_profile(permission_profile: PermissionProfile, cwd: Path | str) -> SandboxMode | None:
    if permission_profile.type == "disabled":
        return SandboxMode.DANGER_FULL_ACCESS
    if permission_profile.type == "external":
        return None

    file_system_policy = permission_profile.file_system_sandbox_policy()
    if file_system_policy.has_full_disk_write_access():
        return SandboxMode.DANGER_FULL_ACCESS if permission_profile.network_sandbox_policy().is_enabled() else None
    if file_system_policy.can_write_path_with_cwd(cwd, cwd):
        return SandboxMode.WORKSPACE_WRITE
    return SandboxMode.READ_ONLY


def approvals_reviewer_override_from_config(config: ExecSessionConfig) -> ApprovalsReviewer:
    return config.approvals_reviewer


def _session_instruction_config(config: ExecSessionConfig, *, include_empty: bool = False) -> dict[str, JsonValue] | None:
    instruction_config = {}
    if config.user_instructions is not None:
        instruction_config["userInstructions"] = config.user_instructions
    if config.instruction_sources:
        instruction_config["instructionSources"] = [str(path) for path in config.instruction_sources]
    if config.startup_warnings:
        instruction_config["startupWarnings"] = list(config.startup_warnings)
    if include_empty:
        instruction_config.setdefault("instructionSources", [])
        instruction_config.setdefault("startupWarnings", [])
    if not instruction_config:
        return None
    return instruction_config


def thread_start_params_from_config(config: ExecSessionConfig) -> ThreadStartParams:
    permissions = permissions_selection_from_config(config)
    sandbox = None if permissions is not None else sandbox_mode_from_permission_profile(config.permission_profile, config.cwd)
    return ThreadStartParams(
        model=config.model,
        model_provider=config.model_provider_id,
        cwd=config.cwd,
        runtime_workspace_roots=config.workspace_roots,
        approval_policy=config.approval_policy,
        approvals_reviewer=approvals_reviewer_override_from_config(config),
        sandbox=sandbox,
        permissions=permissions,
        config=_session_instruction_config(config),
        ephemeral=config.ephemeral,
        thread_source=ThreadSource.USER,
    )


def thread_resume_params_from_config(config: ExecSessionConfig, thread_id: str) -> ThreadResumeParams:
    permissions = permissions_selection_from_config(config)
    sandbox = None if permissions is not None else sandbox_mode_from_permission_profile(config.permission_profile, config.cwd)
    return ThreadResumeParams(
        thread_id=thread_id,
        model=config.model,
        model_provider=config.model_provider_id,
        cwd=config.cwd,
        runtime_workspace_roots=config.workspace_roots,
        approval_policy=config.approval_policy,
        approvals_reviewer=approvals_reviewer_override_from_config(config),
        sandbox=sandbox,
        permissions=permissions,
        config=_session_instruction_config(config, include_empty=True),
    )


def thread_bootstrap_request(
    request_id: str | int,
    config: ExecSessionConfig,
    *,
    resume_args: JsonValue | None = None,
    resolved_thread_id: str | None = None,
) -> ThreadBootstrapRequest:
    if resume_args is not None and resolved_thread_id is not None:
        return ThreadBootstrapRequest(
            action="resume",
            request=ClientRequest.thread_resume(
                request_id,
                thread_resume_params_from_config(config, resolved_thread_id),
            ),
        )
    return ThreadBootstrapRequest(
        action="start",
        request=ClientRequest.thread_start(request_id, thread_start_params_from_config(config)),
    )


def thread_bootstrap_result_from_response(
    action: str,
    response: JsonValue,
    config: ExecSessionConfig,
) -> ThreadBootstrapResult:
    if action == "resume":
        configured = session_configured_from_thread_resume_response(response, config)
    elif action == "start":
        configured = session_configured_from_thread_start_response(response, config)
    else:
        raise ValueError(f"unsupported thread bootstrap action `{action}`")
    thread_id = configured.thread_id.to_json() if configured.thread_id is not None else configured.session_id.to_json()
    return ThreadBootstrapResult(action=action, thread_id=thread_id, session_configured=configured)


def next_thread_bootstrap_request(
    request_ids: RequestIdSequencer,
    config: ExecSessionConfig,
    *,
    resume_args: JsonValue | None = None,
    resolved_thread_id: str | None = None,
) -> ThreadBootstrapRequest:
    return thread_bootstrap_request(
        request_ids.next(),
        config,
        resume_args=resume_args,
        resolved_thread_id=resolved_thread_id,
    )


def turn_start_params_from_plan(config: ExecSessionConfig, thread_id: str, plan: ExecRunPlan) -> TurnStartParams:
    operation = plan.initial_operation
    if operation.kind != "user_turn":
        raise ValueError("turn/start can only be built for user_turn initial operations")
    return TurnStartParams(
        thread_id=thread_id,
        input=operation.items,
        cwd=config.cwd,
        approval_policy=config.approval_policy,
        effort=config.reasoning_effort,
        output_schema=operation.output_schema,
    )


def review_start_params_from_request(thread_id: str, review_request: ReviewRequest) -> ReviewStartParams:
    return ReviewStartParams(thread_id=thread_id, target=review_request.target, delivery=None)


def review_start_params_from_plan(thread_id: str, plan: ExecRunPlan) -> ReviewStartParams:
    operation = plan.initial_operation
    if operation.kind != "review" or operation.review_request is None:
        raise ValueError("review/start can only be built for review initial operations")
    return review_start_params_from_request(thread_id, operation.review_request)


def initial_operation_request_from_plan(
    request_id: str | int,
    config: ExecSessionConfig,
    thread_id: str,
    plan: ExecRunPlan,
) -> InitialOperationRequest:
    operation = plan.initial_operation
    if operation.kind == "user_turn":
        return InitialOperationRequest(
            method="turn/start",
            request=ClientRequest.turn_start(request_id, turn_start_params_from_plan(config, thread_id, plan)),
        )
    if operation.kind == "review":
        return InitialOperationRequest(
            method="review/start",
            request=ClientRequest.review_start(request_id, review_start_params_from_plan(thread_id, plan)),
        )
    raise ValueError(f"unsupported initial operation kind `{operation.kind}`")


def next_initial_operation_request(
    request_ids: RequestIdSequencer,
    config: ExecSessionConfig,
    bootstrap: ThreadBootstrapResult,
    plan: ExecRunPlan,
) -> InitialOperationRequest:
    return initial_operation_request_from_plan(request_ids.next(), config, bootstrap.thread_id, plan)


def initial_operation_result_from_response(method: str, response: JsonValue) -> InitialOperationResult:
    turn = _required_field(response, "turn")
    task_id = str(_required_field(turn, "id"))
    if method in {"turn/start", "thread/turn/start"}:
        return InitialOperationResult(task_id=task_id)
    if method == "review/start":
        review_thread_id = str(_required_field(response, "reviewThreadId", "review_thread_id"))
        return InitialOperationResult(
            task_id=task_id,
            synthetic_notification={
                "method": "turn/started",
                "params": {
                    "threadId": review_thread_id,
                    "turn": _to_json_preserve_none(turn),
                },
            },
        )
    raise ValueError(f"unsupported initial operation response method `{method}`")


def task_id_from_initial_operation_response(method: str, response: JsonValue) -> str:
    return initial_operation_result_from_response(method, response).task_id


def exec_session_startup_result(
    config: ExecSessionConfig,
    bootstrap: ThreadBootstrapResult,
    initial_operation: InitialOperationResult,
) -> ExecSessionStartupResult:
    synthetic = (initial_operation.synthetic_notification,) if initial_operation.synthetic_notification is not None else ()
    return ExecSessionStartupResult(
        bootstrap=bootstrap,
        initial_operation=initial_operation,
        loop_state=ExecLoopState(
            thread_id=bootstrap.thread_id,
            turn_id=initial_operation.task_id,
            thread_ephemeral=config.ephemeral,
            error_seen=False,
        ),
        synthetic_notifications=synthetic,
    )


def thread_bootstrap_processor_actions(
    config: ExecSessionConfig,
    prompt_summary: str,
    bootstrap: ThreadBootstrapResult,
    *,
    json_mode: bool = False,
    system_bwrap_warning: str | None = None,
) -> tuple[ExecLoopAction, ...]:
    actions = [
        ExecLoopAction.print_config_summary(
            config,
            prompt_summary,
            bootstrap.session_configured,
        ),
    ]
    if not json_mode and system_bwrap_warning is not None:
        actions.append(ExecLoopAction.process_warning(system_bwrap_warning))
    return tuple(actions)


def initial_operation_processor_actions(initial_operation: InitialOperationResult) -> tuple[ExecLoopAction, ...]:
    if initial_operation.synthetic_notification is None:
        return ()
    return (ExecLoopAction.process_notification(initial_operation.synthetic_notification),)


def exec_session_startup_processor_actions(
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    startup: ExecSessionStartupResult,
    *,
    json_mode: bool = False,
    system_bwrap_warning: str | None = None,
) -> tuple[ExecLoopAction, ...]:
    return thread_bootstrap_processor_actions(
        config,
        plan.prompt_summary,
        startup.bootstrap,
        json_mode=json_mode,
        system_bwrap_warning=system_bwrap_warning,
    ) + initial_operation_processor_actions(startup.initial_operation)


def remote_exec_session_startup(
    client: RemoteWebSocketClient,
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    *,
    request_ids: RequestIdSequencer | None = None,
    resume_args: JsonValue | None = None,
    resolved_thread_id: str | None = None,
    trace: JsonValue | None = None,
    max_frames: int | None = None,
) -> RemoteExecSessionStartupResult:
    ids = request_ids or RequestIdSequencer()
    bootstrap_request = next_thread_bootstrap_request(
        ids,
        config,
        resume_args=resume_args,
        resolved_thread_id=resolved_thread_id,
    )
    bootstrap_step = client.request(
        bootstrap_request.request,
        trace=trace,
        max_frames=max_frames,
    )
    bootstrap_typed = typed_request_result_from_remote_step(
        bootstrap_request.request,
        bootstrap_step,
        decoder=lambda response: thread_bootstrap_result_from_response(
            bootstrap_request.action,
            response,
            config,
        ),
    )
    if not bootstrap_typed.ok:
        return RemoteExecSessionStartupResult(
            bootstrap_request=bootstrap_request,
            bootstrap_step=bootstrap_step,
            error=bootstrap_typed.error,
        )

    bootstrap = bootstrap_typed.value
    initial_request = next_initial_operation_request(ids, config, bootstrap, plan)
    initial_step = client.request(
        initial_request.request,
        trace=trace,
        max_frames=max_frames,
    )
    initial_typed = typed_request_result_from_remote_step(
        initial_request.request,
        initial_step,
        decoder=lambda response: initial_operation_result_from_response(
            initial_request.method,
            response,
        ),
    )
    if not initial_typed.ok:
        return RemoteExecSessionStartupResult(
            bootstrap_request=bootstrap_request,
            bootstrap_step=bootstrap_step,
            bootstrap=bootstrap,
            initial_request=initial_request,
            initial_step=initial_step,
            error=initial_typed.error,
        )

    initial_operation = initial_typed.value
    startup = exec_session_startup_result(config, bootstrap, initial_operation)
    return RemoteExecSessionStartupResult(
        bootstrap_request=bootstrap_request,
        bootstrap_step=bootstrap_step,
        bootstrap=bootstrap,
        initial_request=initial_request,
        initial_step=initial_step,
        initial_operation=initial_operation,
        startup=startup,
    )


def remote_exec_loop_execute_action(
    client: RemoteWebSocketClient,
    action: ExecLoopAction,
    *,
    processor: JsonValue | None = None,
    trace: JsonValue | None = None,
    max_frames: int | None = None,
) -> RemoteExecLoopActionOutcome:
    if action.server_request is not None:
        step = client.resolve_or_reject_server_request(action.server_request)
        return RemoteExecLoopActionOutcome(
            action=action,
            remote_step=step,
            error_message=step.error_message,
        )

    if action.client_request is not None:
        step = client.request(action.client_request, trace=trace, max_frames=max_frames)
        typed = typed_request_result_from_remote_step(action.client_request, step)
        return RemoteExecLoopActionOutcome(
            action=action,
            remote_step=step,
            response=typed.value if typed.ok else None,
            error_message=None if typed.ok else str(typed.error),
        )

    if action.kind == "process_notification":
        try:
            status = _processor_call(
                processor,
                "process_server_notification",
                action.notification,
                default="running",
            )
        except Exception as exc:
            return RemoteExecLoopActionOutcome(action=action, error_message=str(exc))
        return RemoteExecLoopActionOutcome(action=action, processor_status=status)

    if action.kind == "process_warning":
        try:
            status = _processor_call(processor, "process_warning", action.warning, default="running")
        except Exception as exc:
            return RemoteExecLoopActionOutcome(action=action, error_message=str(exc))
        return RemoteExecLoopActionOutcome(action=action, processor_status=status)

    if action.kind == "print_config_summary":
        try:
            _processor_call(
                processor,
                "print_config_summary",
                action.config,
                action.prompt,
                action.session_configured,
                default=None,
            )
        except Exception as exc:
            return RemoteExecLoopActionOutcome(action=action, error_message=str(exc))
        return RemoteExecLoopActionOutcome(action=action)

    if action.kind == "shutdown_client":
        close_result = client.close()
        return RemoteExecLoopActionOutcome(
            action=action,
            close_result=close_result,
            error_message=close_result.close_error_message,
        )

    if action.kind == "print_final_output":
        try:
            _processor_call(processor, "print_final_output", default=None)
        except Exception as exc:
            return RemoteExecLoopActionOutcome(action=action, error_message=str(exc))
        return RemoteExecLoopActionOutcome(action=action)

    return RemoteExecLoopActionOutcome(action=action)


def remote_exec_loop_cycle(
    client: RemoteWebSocketClient,
    state: ExecLoopState,
    event: JsonValue,
    *,
    processor: JsonValue | None = None,
    request_ids: RequestIdSequencer | None = None,
    trace: JsonValue | None = None,
    max_frames: int | None = None,
) -> RemoteExecLoopCycleExecution:
    ids = request_ids or RequestIdSequencer()
    first_step = exec_loop_step(event, state, request_ids=ids)
    first_actions = exec_loop_actions_from_step(first_step)
    state_after, executed_actions, outcomes, should_break = _remote_exec_loop_execute_actions(
        client,
        first_step.state,
        first_actions,
        processor=processor,
        request_ids=ids,
        trace=trace,
        max_frames=max_frames,
    )

    if not first_step.awaiting_backfill or should_break:
        return RemoteExecLoopCycleExecution(
            state=state_after,
            event=event,
            actions=executed_actions,
            outcomes=outcomes,
            should_break=should_break,
            awaiting_backfill=first_step.awaiting_backfill,
        )

    backfill_outcome = next(
        (
            outcome
            for outcome in outcomes
            if outcome.action.client_request is first_step.backfill_request
        ),
        None,
    )
    thread_read_response = (
        backfill_outcome.response
        if backfill_outcome is not None and backfill_outcome.ok
        else {}
    )
    second_step = exec_loop_step(
        event,
        state_after,
        request_ids=ids,
        thread_read_response=thread_read_response,
    )
    state_after_second, second_actions, second_outcomes, should_break_second = (
        _remote_exec_loop_execute_actions(
            client,
            second_step.state,
            exec_loop_actions_from_step(second_step),
            processor=processor,
            request_ids=ids,
            trace=trace,
            max_frames=max_frames,
        )
    )

    return RemoteExecLoopCycleExecution(
        state=state_after_second,
        event=event,
        actions=executed_actions + second_actions,
        outcomes=outcomes + second_outcomes,
        should_break=should_break_second,
        awaiting_backfill=first_step.awaiting_backfill,
    )


def remote_exec_session_run_loop(
    client: RemoteWebSocketClient,
    state: ExecLoopState,
    *,
    processor: JsonValue | None = None,
    request_ids: RequestIdSequencer | None = None,
    trace: JsonValue | None = None,
    max_frames: int | None = None,
    max_events: int | None = None,
) -> RemoteExecLoopRunResult:
    ids = request_ids or RequestIdSequencer()
    cycles: list[RemoteExecLoopCycleExecution] = []
    current_state = state
    error_message = None
    events_seen = 0

    while True:
        if max_events is not None and events_seen >= max_events:
            error_message = f"remote exec loop stopped after {max_events} events without termination"
            current_state = replace(current_state, error_seen=True)
            break

        step = client.next_event()
        if step.event is None:
            cycle = exec_loop_cycle_from_stream_closed(current_state)
            current_state, actions, outcomes, should_break = _remote_exec_loop_execute_actions(
                client,
                cycle.state,
                cycle.actions,
                processor=processor,
                request_ids=ids,
                trace=trace,
                max_frames=max_frames,
            )
            cycles.append(
                RemoteExecLoopCycleExecution(
                    state=current_state,
                    event=None,
                    actions=actions,
                    outcomes=outcomes,
                    should_break=should_break or cycle.should_break,
                )
            )
            break

        event = step.event.to_mapping()
        if step.error_message is not None:
            error_message = step.error_message
            current_state = replace(current_state, error_seen=True)
            current_state, actions, outcomes, _ = _remote_exec_loop_execute_actions(
                client,
                current_state,
                (ExecLoopAction.process_warning(step.error_message), ExecLoopAction.break_loop()),
                processor=processor,
                request_ids=ids,
                trace=trace,
                max_frames=max_frames,
            )
            cycles.append(
                RemoteExecLoopCycleExecution(
                    state=current_state,
                    event=event,
                    actions=actions,
                    outcomes=outcomes,
                    should_break=True,
                    error_message=step.error_message,
                )
            )
            break

        cycle = remote_exec_loop_cycle(
            client,
            current_state,
            event,
            processor=processor,
            request_ids=ids,
            trace=trace,
            max_frames=max_frames,
        )
        cycles.append(cycle)
        current_state = cycle.state
        events_seen += 1
        if cycle.should_break:
            break

    completion = exec_loop_completion_result(current_state)
    current_state, completion_actions, completion_outcomes, _ = _remote_exec_loop_execute_actions(
        client,
        completion.state,
        completion.actions,
        processor=processor,
        request_ids=ids,
        trace=trace,
        max_frames=max_frames,
    )
    completion = ExecLoopCompletionResult(
        state=current_state,
        actions=completion_actions,
        exit_code=exec_loop_exit_code(current_state.error_seen),
    )
    return RemoteExecLoopRunResult(
        state=current_state,
        cycles=tuple(cycles),
        completion=completion,
        completion_outcomes=completion_outcomes,
        error_message=error_message,
    )


def remote_exec_session_run(
    client: RemoteWebSocketClient,
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    *,
    processor: JsonValue | None = None,
    request_ids: RequestIdSequencer | None = None,
    resume_args: JsonValue | None = None,
    resolved_thread_id: str | None = None,
    json_mode: bool = False,
    system_bwrap_warning: str | None = None,
    trace: JsonValue | None = None,
    startup_max_frames: int | None = None,
    loop_max_frames: int | None = None,
    max_events: int | None = None,
) -> RemoteExecSessionRunResult:
    ids = request_ids or RequestIdSequencer()
    startup = remote_exec_session_startup(
        client,
        config,
        plan,
        request_ids=ids,
        resume_args=resume_args,
        resolved_thread_id=resolved_thread_id,
        trace=trace,
        max_frames=startup_max_frames,
    )
    if not startup.ok or startup.startup is None:
        close_result = client.close()
        error_message = str(startup.error) if startup.error is not None else "remote exec startup failed"
        if close_result.close_error_message is not None:
            error_message = f"{error_message}; {close_result.close_error_message}"
        return RemoteExecSessionRunResult(
            startup=startup,
            close_result=close_result,
            error_message=error_message,
        )

    startup_actions = exec_session_startup_processor_actions(
        config,
        plan,
        startup.startup,
        json_mode=json_mode,
        system_bwrap_warning=system_bwrap_warning,
    )
    state, executed_startup_actions, startup_outcomes, should_break = _remote_exec_loop_execute_actions(
        client,
        startup.startup.loop_state,
        startup_actions,
        processor=processor,
        request_ids=ids,
        trace=trace,
        max_frames=loop_max_frames,
    )
    startup_error = next((outcome.error_message for outcome in startup_outcomes if outcome.error_message), None)
    if startup_error is not None:
        state = replace(state, error_seen=True)
        completion = exec_loop_completion_result(state)
        state, completion_actions, completion_outcomes, _ = _remote_exec_loop_execute_actions(
            client,
            completion.state,
            completion.actions,
            processor=processor,
            request_ids=ids,
            trace=trace,
            max_frames=loop_max_frames,
        )
        loop = RemoteExecLoopRunResult(
            state=state,
            cycles=(),
            completion=ExecLoopCompletionResult(
                state=state,
                actions=completion_actions,
                exit_code=exec_loop_exit_code(state.error_seen),
            ),
            completion_outcomes=completion_outcomes,
            error_message=startup_error,
        )
        return RemoteExecSessionRunResult(
            startup=startup,
            startup_actions=executed_startup_actions,
            startup_outcomes=startup_outcomes,
            loop=loop,
            error_message=startup_error,
        )

    if should_break:
        completion = exec_loop_completion_result(state)
        state, completion_actions, completion_outcomes, _ = _remote_exec_loop_execute_actions(
            client,
            completion.state,
            completion.actions,
            processor=processor,
            request_ids=ids,
            trace=trace,
            max_frames=loop_max_frames,
        )
        loop = RemoteExecLoopRunResult(
            state=state,
            cycles=(),
            completion=ExecLoopCompletionResult(
                state=state,
                actions=completion_actions,
                exit_code=exec_loop_exit_code(state.error_seen),
            ),
            completion_outcomes=completion_outcomes,
        )
    else:
        loop = remote_exec_session_run_loop(
            client,
            state,
            processor=processor,
            request_ids=ids,
            trace=trace,
            max_frames=loop_max_frames,
            max_events=max_events,
        )

    return RemoteExecSessionRunResult(
        startup=startup,
        startup_actions=executed_startup_actions,
        startup_outcomes=startup_outcomes,
        loop=loop,
        error_message=loop.error_message,
    )


def remote_exec_session_connect_and_run(
    args: RemoteAppServerConnectArgs,
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    *,
    processor: JsonValue | None = None,
    request_ids: RequestIdSequencer | None = None,
    resume_args: JsonValue | None = None,
    resolved_thread_id: str | None = None,
    json_mode: bool = False,
    system_bwrap_warning: str | None = None,
    trace: JsonValue | None = None,
    websocket_connector: Callable[..., JsonValue] | None = None,
    unix_socket_connector: Callable[..., JsonValue] | None = None,
    initialize_max_frames: int | None = None,
    startup_max_frames: int | None = None,
    loop_max_frames: int | None = None,
    max_events: int | None = None,
) -> RemoteExecSessionConnectRunResult:
    connect = remote_app_server_client_connect(
        args,
        websocket_connector=websocket_connector,
        unix_socket_connector=unix_socket_connector,
        trace=trace,
        initialize_max_frames=initialize_max_frames,
    )
    if not connect.ok or connect.client is None:
        return RemoteExecSessionConnectRunResult(
            connect=connect,
            error_message=connect.error_message or "failed to connect to remote app server",
        )

    session = remote_exec_session_run(
        connect.client,
        config,
        plan,
        processor=processor,
        request_ids=request_ids,
        resume_args=resume_args,
        resolved_thread_id=resolved_thread_id,
        json_mode=json_mode,
        system_bwrap_warning=system_bwrap_warning,
        trace=trace,
        startup_max_frames=startup_max_frames,
        loop_max_frames=loop_max_frames,
        max_events=max_events,
    )
    return RemoteExecSessionConnectRunResult(
        connect=connect,
        session=session,
        error_message=session.error_message,
    )


def session_configured_from_thread_start_response(
    response: JsonValue,
    config: ExecSessionConfig,
) -> SessionConfiguredEvent:
    return _session_configured_from_thread_response(response, config)


def session_configured_from_thread_resume_response(
    response: JsonValue,
    config: ExecSessionConfig,
) -> SessionConfiguredEvent:
    return _session_configured_from_thread_response(response, config)


def all_thread_source_kinds() -> tuple[ThreadSourceKind, ...]:
    return (
        ThreadSourceKind.CLI,
        ThreadSourceKind.VSCODE,
        ThreadSourceKind.EXEC,
        ThreadSourceKind.APP_SERVER,
        ThreadSourceKind.SUB_AGENT,
        ThreadSourceKind.SUB_AGENT_REVIEW,
        ThreadSourceKind.SUB_AGENT_COMPACT,
        ThreadSourceKind.SUB_AGENT_THREAD_SPAWN,
        ThreadSourceKind.SUB_AGENT_OTHER,
        ThreadSourceKind.UNKNOWN,
    )


def resume_lookup_model_providers(config: ExecSessionConfig, resume_args: JsonValue) -> tuple[str, ...] | None:
    return (config.model_provider_id,) if bool(_field(resume_args, "last")) else None


def thread_list_params_for_resume(
    config: ExecSessionConfig,
    resume_args: JsonValue,
    *,
    cursor: str | None = None,
    search_term: str | None = None,
) -> ThreadListParams:
    return ThreadListParams(
        cursor=cursor,
        limit=100,
        sort_key="updated_at",
        sort_direction=None,
        model_providers=resume_lookup_model_providers(config, resume_args),
        source_kinds=all_thread_source_kinds(),
        archived=False,
        cwd=None,
        use_state_db_only=False,
        search_term=search_term,
    )


def thread_list_request_for_resume(
    request_id: str | int,
    config: ExecSessionConfig,
    resume_args: JsonValue,
    *,
    cursor: str | None = None,
    search_term: str | None = None,
) -> ClientRequest:
    return ClientRequest.thread_list(
        request_id,
        thread_list_params_for_resume(config, resume_args, cursor=cursor, search_term=search_term),
    )


def resume_thread_id_lookup_step(
    request_id: str | int,
    config: ExecSessionConfig,
    resume_args: JsonValue,
    *,
    cursor: str | None = None,
) -> ResumeThreadIdLookup:
    include_all = bool(_field(resume_args, "all"))
    if bool(_field(resume_args, "last")):
        return ResumeThreadIdLookup(
            kind="list",
            request=thread_list_request_for_resume(request_id, config, resume_args, cursor=cursor),
            exact_name=None,
            include_all=include_all,
            cursor=cursor,
        )

    session_id = _field(resume_args, "sessionId", "session_id")
    if session_id is None:
        return ResumeThreadIdLookup(kind="none", include_all=include_all, cursor=cursor)

    session_id = str(session_id)
    direct = direct_resume_thread_id(session_id)
    if direct is not None:
        return ResumeThreadIdLookup(kind="direct", thread_id=direct, include_all=include_all, cursor=cursor)

    return ResumeThreadIdLookup(
        kind="list",
        request=thread_list_request_for_resume(request_id, config, resume_args, cursor=cursor, search_term=session_id),
        exact_name=session_id,
        include_all=include_all,
        cursor=cursor,
    )


def resume_thread_id_lookup_request(
    config: ExecSessionConfig,
    resume_args: JsonValue,
    *,
    cursor: str | None = None,
) -> ResumeThreadIdLookup:
    """Build Rust's resume lookup step with fixed request id 0."""

    return resume_thread_id_lookup_step(
        RESUME_LOOKUP_REQUEST_ID,
        config,
        resume_args,
        cursor=cursor,
    )


def resume_thread_id_from_list_response(
    response: JsonValue,
    config: ExecSessionConfig,
    resume_args: JsonValue,
) -> ResumeThreadIdListResult:
    exact_name = None if bool(_field(resume_args, "last")) else _optional_string(_field(resume_args, "sessionId", "session_id"))
    thread_id = pick_resume_thread_id_from_list_response(
        response,
        config.cwd,
        include_all=bool(_field(resume_args, "all")),
        exact_name=exact_name,
    )
    if thread_id is not None:
        return ResumeThreadIdListResult(thread_id=thread_id, done=True)
    next_cursor = _optional_string(_field(response, "nextCursor", "next_cursor"))
    return ResumeThreadIdListResult(thread_id=None, next_cursor=next_cursor, done=next_cursor is None)


def resume_thread_id_from_local_sources(
    config: ExecSessionConfig,
    resume_args: JsonValue,
    *,
    state_db_thread: JsonValue | None = None,
    rollout_meta: JsonValue | None = None,
) -> str | None:
    session_id = _optional_string(_field(resume_args, "sessionId", "session_id"))
    if bool(_field(resume_args, "last")) or session_id is None or direct_resume_thread_id(session_id) is not None:
        return None

    state_thread_id = _optional_string(_field(state_db_thread, "id", "threadId", "thread_id"))
    if state_thread_id is not None:
        if not bool(_field(resume_args, "all")):
            state_cwd = _field(state_db_thread, "cwd")
            if state_cwd is not None and not cwds_match(config.cwd, Path(str(state_cwd))):
                return None
        return state_thread_id

    meta = _field(rollout_meta, "meta") or rollout_meta
    meta_thread_id = _optional_string(_field(meta, "id", "threadId", "thread_id"))
    if meta_thread_id is None:
        return None
    if bool(_field(resume_args, "all")):
        return meta_thread_id
    meta_cwd = _field(meta, "cwd")
    if meta_cwd is not None and cwds_match(config.cwd, Path(str(meta_cwd))):
        return meta_thread_id
    return None


def parse_latest_turn_context_cwd(path: Path | str) -> Path | None:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for line in reversed(text.splitlines()):
        trimmed = line.strip()
        if not trimmed:
            continue
        try:
            data = json.loads(trimmed)
        except json.JSONDecodeError:
            continue
        if _field(data, "type") != "turn_context":
            continue
        try:
            item = TurnContextItem.from_mapping(_required_field(data, "payload"))
        except (KeyError, TypeError, ValueError):
            continue
        return item.cwd
    return None


def latest_thread_cwd(thread: JsonValue) -> Path:
    path = _field(thread, "path")
    if path is not None:
        parsed = parse_latest_turn_context_cwd(path)
        if parsed is not None:
            return parsed
    return Path(str(_required_field(thread, "cwd")))


def cwds_match(current_cwd: Path | str, session_cwd: Path | str) -> bool:
    left = Path(current_cwd)
    right = Path(session_cwd)
    try:
        return left.resolve(strict=True) == right.resolve(strict=True)
    except OSError:
        return left == right


def thread_matches_resume_cwd(thread: JsonValue, current_cwd: Path | str, include_all: bool = False) -> bool:
    return include_all or cwds_match(current_cwd, latest_thread_cwd(thread))


def pick_resume_thread_id_from_list_response(
    response: JsonValue,
    current_cwd: Path | str,
    *,
    include_all: bool = False,
    exact_name: str | None = None,
) -> str | None:
    data = _field(response, "data") or ()
    if not isinstance(data, list | tuple):
        return None
    for thread in data:
        if exact_name is not None and _field(thread, "name") != exact_name:
            continue
        if thread_matches_resume_cwd(thread, current_cwd, include_all):
            return str(_required_field(thread, "id"))
    return None


def direct_resume_thread_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None
    try:
        ThreadId.from_string(session_id)
    except ValueError:
        return None
    return session_id


def turn_interrupt_request(request_id: str | int, thread_id: str, turn_id: str) -> ClientRequest:
    return ClientRequest.turn_interrupt(request_id, TurnInterruptParams(thread_id=thread_id, turn_id=turn_id))


def thread_unsubscribe_request(request_id: str | int, thread_id: str) -> ClientRequest:
    return ClientRequest.thread_unsubscribe(request_id, ThreadUnsubscribeParams(thread_id=thread_id))


def thread_read_request(request_id: str | int, thread_id: str, include_turns: bool = True) -> ClientRequest:
    return ClientRequest.thread_read(request_id, ThreadReadParams(thread_id=thread_id, include_turns=include_turns))


def format_request_error(method: str, error: object) -> str:
    text = str(error)
    return text if method == "" else f"{method}: {text}"


def resolve_server_request_error(method: str, error: object) -> str:
    return f"failed to resolve `{method}` server request: {error}"


def reject_server_request_error(method: str, error: object) -> str:
    return f"failed to reject `{method}` server request: {error}"


def json_rpc_rejection_error(reason: str) -> JsonRpcError:
    return JsonRpcError(message=reason, code=-32000, data=None)


def canceled_mcp_server_elicitation_response() -> dict[str, JsonValue]:
    return {"action": "cancel", "content": None, "_meta": None}


def server_request_method_name(request: JsonValue) -> str:
    raw = _field(request, "method", "type", "kind")
    if raw is None:
        return "unknown"
    return _SERVER_REQUEST_METHOD_ALIASES.get(str(raw), str(raw))


def exec_mode_server_request_rejection_reason(method: str, params: JsonValue) -> str | None:
    if method == "item/commandExecution/requestApproval":
        return (
            "command execution approval is not supported in exec mode for thread "
            f"`{_field(params, 'threadId', 'thread_id')}`"
        )
    if method == "item/fileChange/requestApproval":
        return (
            "file change approval is not supported in exec mode for thread "
            f"`{_field(params, 'threadId', 'thread_id')}`"
        )
    if method == "item/tool/requestUserInput":
        return (
            "request_user_input is not supported in exec mode for thread "
            f"`{_field(params, 'threadId', 'thread_id')}`"
        )
    if method == "item/tool/call":
        return (
            "dynamic tool calls are not supported in exec mode for thread "
            f"`{_field(params, 'threadId', 'thread_id')}`"
        )
    if method == "account/chatgptAuthTokens/refresh":
        return "chatgpt auth token refresh is not supported in exec mode"
    if method == "attestation/generate":
        return "attestation generation is not supported in exec mode"
    if method == "applyPatchApproval":
        return (
            "apply_patch approval is not supported in exec mode for thread "
            f"`{_field(params, 'conversationId', 'conversation_id')}`"
        )
    if method == "execCommandApproval":
        return (
            "exec command approval is not supported in exec mode for thread "
            f"`{_field(params, 'conversationId', 'conversation_id')}`"
        )
    if method == "item/permissions/requestApproval":
        return (
            "permissions approval is not supported in exec mode for thread "
            f"`{_field(params, 'threadId', 'thread_id')}`"
        )
    return None


def exec_mode_server_request_decision(request: JsonValue) -> ServerRequestDecision:
    method = server_request_method_name(request)
    request_id = _field(request, "requestId", "request_id", "id")
    if method == "mcpServer/elicitation/request":
        return ServerRequestDecision.resolve(request_id, method, canceled_mcp_server_elicitation_response())

    params = _field(request, "params", "payload")
    if params is None:
        params = request
    reason = exec_mode_server_request_rejection_reason(method, params)
    if reason is None:
        reason = f"server request `{method}` is not supported in exec mode"
    return ServerRequestDecision.reject(request_id, method, reason)


def exec_loop_interrupt_request(request_id: str | int, thread_id: str, turn_id: str) -> ClientRequest:
    return turn_interrupt_request(request_id, thread_id, turn_id)


def exec_loop_shutdown_request(request_id: str | int, thread_id: str, processor_status: JsonValue) -> ClientRequest | None:
    if _enum(processor_status) in {"initiate_shutdown", "InitiateShutdown"}:
        return thread_unsubscribe_request(request_id, thread_id)
    return None


def exec_loop_notification_decision(
    notification: JsonValue,
    thread_id: str,
    turn_id: str,
    *,
    thread_ephemeral: bool = False,
    request_id: str | int | None = None,
) -> ExecLoopNotificationDecision:
    needs_backfill = should_backfill_turn_completed_items(thread_ephemeral, notification)
    backfill_request = None
    if needs_backfill and request_id is not None:
        payload = _notification_params(notification)
        notification_thread_id = _field(payload, "threadId", "thread_id")
        if notification_thread_id is not None:
            backfill_request = thread_read_request(request_id, str(notification_thread_id))

    return ExecLoopNotificationDecision(
        notification=notification,
        event_indicates_error=notification_indicates_exec_error(notification, thread_id, turn_id),
        should_process=should_process_notification(notification, thread_id, turn_id),
        needs_backfill=needs_backfill,
        backfill_request=backfill_request,
    )


def backfill_turn_completed_notification(
    thread_ephemeral: bool,
    notification: JsonValue,
    thread_read_response: JsonValue,
) -> JsonValue:
    if not should_backfill_turn_completed_items(thread_ephemeral, notification):
        return notification
    payload = _notification_params(notification)
    turn = _field(payload, "turn")
    turn_id = _field(turn, "id")
    if turn_id is None:
        return notification
    thread = _field(thread_read_response, "thread") or thread_read_response
    items = turn_items_for_thread(thread, str(turn_id))
    if items is None:
        return notification
    return _notification_with_turn_items(notification, items)


def exec_loop_server_event_decision(
    event: JsonValue,
    thread_id: str,
    turn_id: str,
    *,
    thread_ephemeral: bool = False,
    request_id: str | int | None = None,
) -> ExecLoopServerEventDecision:
    kind = _server_event_kind(event)
    if kind == "server_request":
        request = _field(event, "request", "serverRequest", "server_request", "payload")
        return ExecLoopServerEventDecision(
            kind=kind,
            server_request=exec_mode_server_request_decision(request),
        )
    if kind == "server_notification":
        notification = _field(event, "notification", "serverNotification", "server_notification", "payload")
        notification_decision = exec_loop_notification_decision(
            notification,
            thread_id,
            turn_id,
            thread_ephemeral=thread_ephemeral,
            request_id=request_id,
        )
        return ExecLoopServerEventDecision(
            kind=kind,
            event_indicates_error=notification_decision.event_indicates_error,
            notification=notification_decision,
        )
    if kind == "lagged":
        skipped = _field(event, "skipped")
        warning = lagged_event_warning_message(int(skipped or 0))
        return ExecLoopServerEventDecision(kind=kind, warning=warning)
    return ExecLoopServerEventDecision(kind=kind or "unknown")


def exec_loop_step(
    event: JsonValue,
    state: ExecLoopState,
    *,
    request_ids: RequestIdSequencer | None = None,
    processor_status: JsonValue = "running",
    thread_read_response: JsonValue | None = None,
) -> ExecLoopStepResult:
    kind = _server_event_kind(event)
    backfill_request_id = None
    if kind == "server_notification":
        notification = _field(event, "notification", "serverNotification", "server_notification", "payload")
        if (
            request_ids is not None
            and thread_read_response is None
            and should_backfill_turn_completed_items(state.thread_ephemeral, notification)
        ):
            backfill_request_id = request_ids.next()

    decision = exec_loop_server_event_decision(
        event,
        state.thread_id,
        state.turn_id,
        thread_ephemeral=state.thread_ephemeral,
        request_id=backfill_request_id,
    )
    next_state = replace(state, error_seen=state.error_seen or decision.event_indicates_error)

    if decision.server_request is not None:
        return ExecLoopStepResult(
            state=next_state,
            decision=decision,
            server_request=decision.server_request,
        )

    if decision.warning is not None:
        return ExecLoopStepResult(
            state=next_state,
            decision=decision,
            warning_to_process=decision.warning,
        )

    notification_decision = decision.notification
    if notification_decision is None:
        return ExecLoopStepResult(state=next_state, decision=decision)

    notification_to_process = None
    backfill_request = notification_decision.backfill_request
    awaiting_backfill = False
    if notification_decision.should_process:
        if notification_decision.needs_backfill and thread_read_response is None and backfill_request is not None:
            awaiting_backfill = True
        elif thread_read_response is not None:
            notification_to_process = backfill_turn_completed_notification(
                state.thread_ephemeral,
                notification_decision.notification,
                thread_read_response,
            )
        else:
            notification_to_process = notification_decision.notification

    shutdown_request = None
    should_break = False
    if notification_to_process is not None and _enum(processor_status) in {"initiate_shutdown", "InitiateShutdown"}:
        request_id = request_ids.next() if request_ids is not None else 0
        shutdown_request = exec_loop_shutdown_request(request_id, state.thread_id, processor_status)
        should_break = shutdown_request is not None
    elif (
        notification_to_process is not None
        and decision.event_indicates_error
        and _notification_method(notification_to_process) == "error"
    ):
        should_break = True

    return ExecLoopStepResult(
        state=next_state,
        decision=decision,
        notification_to_process=notification_to_process,
        backfill_request=backfill_request,
        awaiting_backfill=awaiting_backfill,
        shutdown_request=shutdown_request,
        should_break=should_break,
    )


def exec_loop_interrupt_step(
    state: ExecLoopState,
    interrupt_received: bool,
    *,
    request_ids: RequestIdSequencer | None = None,
) -> ExecLoopInterruptResult:
    if not state.interrupt_channel_open:
        return ExecLoopInterruptResult(state=state)

    if not interrupt_received:
        return ExecLoopInterruptResult(state=replace(state, interrupt_channel_open=False))

    request_id = request_ids.next() if request_ids is not None else 0
    return ExecLoopInterruptResult(
        state=state,
        interrupt_request=exec_loop_interrupt_request(request_id, state.thread_id, state.turn_id),
    )


def exec_loop_actions_from_step(step: ExecLoopStepResult) -> tuple[ExecLoopAction, ...]:
    actions: list[ExecLoopAction] = []
    if step.server_request is not None:
        actions.append(ExecLoopAction.server_request_action(step.server_request))
        return tuple(actions)

    if step.warning_to_process is not None:
        actions.append(ExecLoopAction.process_warning(step.warning_to_process))

    if step.awaiting_backfill and step.backfill_request is not None:
        actions.append(ExecLoopAction.send_request(step.backfill_request))
        return tuple(actions)

    if step.notification_to_process is not None:
        actions.append(ExecLoopAction.process_notification(step.notification_to_process))

    if step.shutdown_request is not None:
        actions.append(ExecLoopAction.send_request(step.shutdown_request))

    if step.should_break:
        actions.append(ExecLoopAction.break_loop())

    return tuple(actions)


def exec_loop_actions_from_interrupt(result: ExecLoopInterruptResult) -> tuple[ExecLoopAction, ...]:
    if result.interrupt_request is None:
        return ()
    return (ExecLoopAction.send_request(result.interrupt_request),)


def exec_loop_cycle_from_server_event(
    event: JsonValue,
    state: ExecLoopState,
    *,
    request_ids: RequestIdSequencer | None = None,
    processor_status: JsonValue = "running",
    thread_read_response: JsonValue | None = None,
) -> ExecLoopCycleResult:
    step = exec_loop_step(
        event,
        state,
        request_ids=request_ids,
        processor_status=processor_status,
        thread_read_response=thread_read_response,
    )
    return ExecLoopCycleResult(
        state=step.state,
        actions=exec_loop_actions_from_step(step),
        should_break=step.should_break,
        awaiting_backfill=step.awaiting_backfill,
    )


def exec_loop_cycle_from_interrupt(
    state: ExecLoopState,
    interrupt_received: bool,
    *,
    request_ids: RequestIdSequencer | None = None,
) -> ExecLoopCycleResult:
    result = exec_loop_interrupt_step(state, interrupt_received, request_ids=request_ids)
    return ExecLoopCycleResult(
        state=result.state,
        actions=exec_loop_actions_from_interrupt(result),
    )


def exec_loop_cycle_from_stream_closed(state: ExecLoopState) -> ExecLoopCycleResult:
    return ExecLoopCycleResult(
        state=state,
        actions=(ExecLoopAction.break_loop(),),
        should_break=True,
    )


def exec_loop_completion_result(state: ExecLoopState) -> ExecLoopCompletionResult:
    return ExecLoopCompletionResult(
        state=state,
        actions=(ExecLoopAction.shutdown_client(), ExecLoopAction.print_final_output()),
        exit_code=exec_loop_exit_code(state.error_seen),
    )


def exec_loop_client_shutdown_failure_warning(error: object) -> str:
    return f"in-process app-server shutdown failed: {error}"


def exec_loop_client_request_failure_warning(request: ClientRequest, error: object) -> str:
    if request.method == "turn/interrupt":
        return f"turn/interrupt failed: {error}"
    if request.method == "thread/read":
        return f"thread/read failed while backfilling turn items for turn completion: {error}"
    if request.method == "thread/unsubscribe":
        return f"thread/unsubscribe failed during shutdown: {error}"
    return format_request_error(request.method, error)


def exec_loop_action_failure_result(
    state: ExecLoopState,
    action: ExecLoopAction,
    error: object,
) -> ExecLoopActionFailureResult:
    if action.server_request is not None:
        if action.kind == "resolve_server_request":
            warning = resolve_server_request_error(action.server_request.method, error)
        else:
            warning = reject_server_request_error(action.server_request.method, error)
        return ExecLoopActionFailureResult(state=replace(state, error_seen=True), warning=warning)

    if action.client_request is not None:
        return ExecLoopActionFailureResult(
            state=state,
            warning=exec_loop_client_request_failure_warning(action.client_request, error),
        )

    if action.kind == "shutdown_client":
        return ExecLoopActionFailureResult(
            state=state,
            warning=exec_loop_client_shutdown_failure_warning(error),
        )

    return ExecLoopActionFailureResult(state=state)


def exec_loop_exit_code(error_seen: bool) -> int:
    return 1 if error_seen else 0


def lagged_event_warning_message(skipped: int) -> str:
    return f"in-process app-server event stream lagged; dropped {skipped} events"


def _processor_call(processor: JsonValue | None, method: str, *args: JsonValue, default: JsonValue) -> JsonValue:
    if processor is None:
        return default
    func = getattr(processor, method, None)
    if func is None:
        return default
    result = func(*args)
    return default if result is None else result


def _processor_status_requests_shutdown(status: JsonValue) -> bool:
    return _enum(status) in {"initiate_shutdown", "InitiateShutdown"}


def _remote_exec_loop_execute_actions(
    client: RemoteWebSocketClient,
    state: ExecLoopState,
    actions: tuple[ExecLoopAction, ...],
    *,
    processor: JsonValue | None,
    request_ids: RequestIdSequencer,
    trace: JsonValue | None,
    max_frames: int | None,
) -> tuple[ExecLoopState, tuple[ExecLoopAction, ...], tuple[RemoteExecLoopActionOutcome, ...], bool]:
    current_state = state
    executed_actions: list[ExecLoopAction] = []
    outcomes: list[RemoteExecLoopActionOutcome] = []
    should_break = False

    for action in actions:
        outcome = remote_exec_loop_execute_action(
            client,
            action,
            processor=processor,
            trace=trace,
            max_frames=max_frames,
        )
        executed_actions.append(action)
        outcomes.append(outcome)
        if outcome.error_message is not None:
            failure = exec_loop_action_failure_result(current_state, action, outcome.error_message)
            current_state = failure.state
            if failure.warning is not None:
                warning_action = ExecLoopAction.process_warning(failure.warning)
                warning_outcome = remote_exec_loop_execute_action(
                    client,
                    warning_action,
                    processor=processor,
                    trace=trace,
                    max_frames=max_frames,
                )
                executed_actions.append(warning_action)
                outcomes.append(warning_outcome)
            continue

        if (
            action.kind == "process_notification"
            and outcome.processor_status is not None
            and _processor_status_requests_shutdown(outcome.processor_status)
        ):
            shutdown_request = exec_loop_shutdown_request(
                request_ids.next(),
                current_state.thread_id,
                outcome.processor_status,
            )
            if shutdown_request is not None:
                shutdown_action = ExecLoopAction.send_request(shutdown_request)
                shutdown_outcome = remote_exec_loop_execute_action(
                    client,
                    shutdown_action,
                    processor=processor,
                    trace=trace,
                    max_frames=max_frames,
                )
                executed_actions.append(shutdown_action)
                outcomes.append(shutdown_outcome)
                if shutdown_outcome.error_message is not None:
                    failure = exec_loop_action_failure_result(
                        current_state,
                        shutdown_action,
                        shutdown_outcome.error_message,
                    )
                    current_state = failure.state
                    if failure.warning is not None:
                        warning_action = ExecLoopAction.process_warning(failure.warning)
                        warning_outcome = remote_exec_loop_execute_action(
                            client,
                            warning_action,
                            processor=processor,
                            trace=trace,
                            max_frames=max_frames,
                        )
                        executed_actions.append(warning_action)
                        outcomes.append(warning_outcome)

            break_action = ExecLoopAction.break_loop()
            break_outcome = remote_exec_loop_execute_action(
                client,
                break_action,
                processor=processor,
                trace=trace,
                max_frames=max_frames,
            )
            executed_actions.append(break_action)
            outcomes.append(break_outcome)
            should_break = True
            break

        if action.kind == "break":
            should_break = True
            break

    return current_state, tuple(executed_actions), tuple(outcomes), should_break


def should_process_notification(notification: JsonValue, thread_id: str, turn_id: str) -> bool:
    method = _notification_method(notification)
    params = _notification_params(notification)
    if method in {"configWarning", "deprecationNotice"}:
        return True
    if method == "error":
        return _field(params, "threadId", "thread_id") == thread_id and _field(params, "turnId", "turn_id") == turn_id
    if method in {"hook/started", "hook/completed"}:
        candidate_turn_id = _field(params, "turnId", "turn_id")
        return _field(params, "threadId", "thread_id") == thread_id and (
            candidate_turn_id is None or candidate_turn_id == turn_id
        )
    if method in {
        "item/started",
        "item/completed",
        "model/rerouted",
        "model/verification",
        "thread/tokenUsage/updated",
        "turn/diff/updated",
        "turn/plan/updated",
    }:
        return _field(params, "threadId", "thread_id") == thread_id and _field(params, "turnId", "turn_id") == turn_id
    if method in {"turn/started", "turn/completed"}:
        turn = _field(params, "turn")
        return _field(params, "threadId", "thread_id") == thread_id and _field(turn, "id") == turn_id
    return False


def notification_indicates_exec_error(notification: JsonValue, thread_id: str, turn_id: str) -> bool:
    method = _notification_method(notification)
    params = _notification_params(notification)
    if method == "error":
        return (
            _field(params, "threadId", "thread_id") == thread_id
            and _field(params, "turnId", "turn_id") == turn_id
            and not bool(_field(params, "willRetry", "will_retry"))
        )
    if method != "turn/completed":
        return False
    turn = _field(params, "turn")
    return (
        _field(params, "threadId", "thread_id") == thread_id
        and _field(turn, "id") == turn_id
        and _enum(_field(turn, "status")) in {"failed", "interrupted", "Failed", "Interrupted"}
    )


def should_backfill_turn_completed_items(thread_ephemeral: bool, notification: JsonValue) -> bool:
    if thread_ephemeral or _notification_method(notification) != "turn/completed":
        return False
    turn = _field(_notification_params(notification), "turn")
    items = _field(turn, "items")
    return isinstance(items, list | tuple) and len(items) == 0


def turn_items_for_thread(thread: JsonValue, turn_id: str) -> JsonValue | None:
    turns = _field(thread, "turns")
    if not isinstance(turns, list | tuple):
        return None
    for turn in turns:
        if _field(turn, "id") == turn_id:
            items = _field(turn, "items")
            if isinstance(items, list | tuple):
                return [_thread_turn_item_for_backfill(item) for item in items]
            return items
    return None


def _thread_turn_item_for_backfill(item: JsonValue) -> JsonValue:
    if isinstance(item, TurnItem):
        return item
    return _to_json_preserve_none(item)


def _session_configured_from_thread_response(
    response: JsonValue,
    config: ExecSessionConfig,
) -> SessionConfiguredEvent:
    thread = _required_field(response, "thread")
    session_id_raw = str(_required_field(thread, "sessionId", "session_id"))
    thread_id_raw = str(_required_field(thread, "id"))
    try:
        session_id = SessionId.from_string(session_id_raw)
    except ValueError as exc:
        raise ValueError(f"session id `{session_id_raw}` is invalid: {exc}") from exc
    try:
        thread_id = ThreadId.from_string(thread_id_raw)
    except ValueError as exc:
        raise ValueError(f"thread id `{thread_id_raw}` is invalid: {exc}") from exc

    active_permission_profile = _parse_active_permission_profile(
        _field(response, "activePermissionProfile", "active_permission_profile")
    )

    return SessionConfiguredEvent(
        session_id=session_id,
        thread_id=thread_id,
        forked_from_id=None,
        thread_source=_parse_thread_source(_field(thread, "threadSource", "thread_source")),
        thread_name=_field(thread, "name"),
        model=str(_required_field(response, "model")),
        model_provider_id=str(_required_field(response, "modelProvider", "model_provider")),
        service_tier=_optional_string(_field(response, "serviceTier", "service_tier")),
        approval_policy=_parse_approval_policy(_required_field(response, "approvalPolicy", "approval_policy")),
        approvals_reviewer=_parse_approvals_reviewer(_required_field(response, "approvalsReviewer", "approvals_reviewer")),
        permission_profile=config.permission_profile,
        active_permission_profile=active_permission_profile,
        cwd=Path(str(_required_field(response, "cwd"))),
        reasoning_effort=_field(response, "reasoningEffort", "reasoning_effort"),
        initial_messages=_parse_initial_messages(_field(response, "initialMessages", "initial_messages")),
        network_proxy=None,
        rollout_path=_optional_path(_field(thread, "path")),
    )


def _parse_initial_messages(value: JsonValue) -> tuple[EventMsg, ...] | None:
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise TypeError("initial_messages must be a list")
    return tuple(EventMsg.from_mapping(item) for item in value)


def _enum(value: JsonValue) -> JsonValue:
    return value.value if isinstance(value, Enum) else value


def _paths(paths: tuple[Path, ...] | None) -> list[str] | None:
    if paths is None:
        return None
    return [str(path) for path in paths]


def _drop_none(data: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: value for key, value in data.items() if value is not None}


def _to_json(value: JsonValue) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return value.to_mapping()
    if isinstance(value, Mapping):
        return {str(key): _to_json(item) for key, item in value.items() if item is not None}
    if isinstance(value, tuple | list):
        return [_to_json(item) for item in value]
    return value


def _to_json_preserve_none(value: JsonValue) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return _to_json_preserve_none(value.to_mapping())
    if isinstance(value, Mapping):
        return {str(key): _to_json_preserve_none(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json_preserve_none(item) for item in value]
    return value


def _turn_item_to_app_server_json(value: JsonValue) -> JsonValue:
    if isinstance(value, TurnItem):
        return value.to_app_server_mapping()
    if isinstance(value, Mapping):
        return _to_json_preserve_none(value)
    return _to_json_preserve_none(value)


def _turn_items_to_app_server_json(value: JsonValue) -> JsonValue:
    if isinstance(value, tuple | list):
        return [_turn_item_to_app_server_json(item) for item in value]
    return _to_json_preserve_none(value)


def _compact_json(value: JsonValue) -> str:
    return json.dumps(_to_json_preserve_none(value), ensure_ascii=False, separators=(",", ":"))


def _pending_request_dict(state: RemoteAppServerClientState) -> dict[str | int, str]:
    return {request_id: method for request_id, method in state.pending_requests}


def _server_event_kind(event: JsonValue) -> str | None:
    raw = _field(event, "type", "kind")
    if raw is None:
        if _field(event, "request", "serverRequest", "server_request") is not None:
            return "server_request"
        if _field(event, "notification", "serverNotification", "server_notification") is not None:
            return "server_notification"
        if _field(event, "skipped") is not None:
            return "lagged"
        return None
    aliases = {
        "ServerRequest": "server_request",
        "serverRequest": "server_request",
        "server_request": "server_request",
        "ServerNotification": "server_notification",
        "serverNotification": "server_notification",
        "server_notification": "server_notification",
        "Lagged": "lagged",
        "lagged": "lagged",
    }
    return aliases.get(str(raw), str(raw))


def _notification_with_turn_items(notification: JsonValue, items: JsonValue) -> JsonValue:
    params = _notification_params(notification)
    turn = _field(params, "turn")
    if not isinstance(params, Mapping) or not isinstance(turn, Mapping):
        return notification

    updated_turn = dict(turn)
    updated_turn["items"] = _turn_items_to_app_server_json(items)
    updated_params = dict(params)
    updated_params["turn"] = updated_turn

    if isinstance(notification, Mapping):
        if "params" in notification:
            updated_notification = dict(notification)
            updated_notification["params"] = updated_params
            return updated_notification
        if "payload" in notification:
            updated_notification = dict(notification)
            updated_notification["payload"] = updated_params
            return updated_notification
        return updated_params
    return notification


_SERVER_REQUEST_METHOD_ALIASES = {
    "CommandExecutionRequestApproval": "item/commandExecution/requestApproval",
    "command_execution_request_approval": "item/commandExecution/requestApproval",
    "FileChangeRequestApproval": "item/fileChange/requestApproval",
    "file_change_request_approval": "item/fileChange/requestApproval",
    "ToolRequestUserInput": "item/tool/requestUserInput",
    "tool_request_user_input": "item/tool/requestUserInput",
    "McpServerElicitationRequest": "mcpServer/elicitation/request",
    "mcp_server_elicitation_request": "mcpServer/elicitation/request",
    "PermissionsRequestApproval": "item/permissions/requestApproval",
    "permissions_request_approval": "item/permissions/requestApproval",
    "DynamicToolCall": "item/tool/call",
    "dynamic_tool_call": "item/tool/call",
    "ChatgptAuthTokensRefresh": "account/chatgptAuthTokens/refresh",
    "chatgpt_auth_tokens_refresh": "account/chatgptAuthTokens/refresh",
    "AttestationGenerate": "attestation/generate",
    "attestation_generate": "attestation/generate",
    "ApplyPatchApproval": "applyPatchApproval",
    "apply_patch_approval": "applyPatchApproval",
    "ExecCommandApproval": "execCommandApproval",
    "exec_command_approval": "execCommandApproval",
}


def _notification_method(notification: JsonValue) -> str | None:
    from .event_processor import notification_method

    return notification_method(notification)


def _notification_params(notification: JsonValue) -> JsonValue:
    params = _field(notification, "params", "payload")
    return notification if params is None else params


def _field(value: JsonValue, *names: str) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _required_field(value: JsonValue, *names: str) -> JsonValue:
    result = _field(value, *names)
    if result is None:
        raise ValueError(f"missing field `{names[0]}`")
    return result


def _optional_string(value: JsonValue) -> str | None:
    return None if value is None else str(value)


def _optional_path(value: JsonValue) -> Path | None:
    return None if value is None else Path(str(value))


def _parse_thread_source(value: JsonValue) -> ThreadSource | None:
    if value is None:
        return None
    if isinstance(value, ThreadSource):
        return value
    return ThreadSource.parse(str(value))


def _parse_approval_policy(value: JsonValue) -> AskForApproval:
    if isinstance(value, AskForApproval):
        return value
    return AskForApproval.parse(str(value))


def _parse_approvals_reviewer(value: JsonValue) -> ApprovalsReviewer:
    if isinstance(value, ApprovalsReviewer):
        return value
    return ApprovalsReviewer.parse(str(value))


def _parse_active_permission_profile(value: JsonValue) -> ActivePermissionProfile | None:
    if value is None:
        return None
    if isinstance(value, ActivePermissionProfile):
        return value
    return ActivePermissionProfile.from_mapping(value)


__all__ = [
    "REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS",
    "REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS",
    "REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE",
    "REMOTE_APP_SERVER_SHUTDOWN_TIMEOUT_SECONDS",
    "UDS_WEBSOCKET_HANDSHAKE_URL",
    "ClientRequest",
    "AppServerEvent",
    "ExecLoopAction",
    "ExecLoopActionFailureResult",
    "ExecLoopCompletionResult",
    "ExecLoopCycleResult",
    "ExecSessionConfig",
    "ExecLoopNotificationDecision",
    "ExecLoopServerEventDecision",
    "ExecLoopState",
    "ExecLoopStepResult",
    "ExecLoopInterruptResult",
    "ExecSessionStartupResult",
    "JsonRpcErrorEnvelope",
    "JsonRpcError",
    "JsonRpcNotificationEnvelope",
    "JsonRpcRequestEnvelope",
    "JsonRpcResponseEnvelope",
    "RemoteAppServerConnectResult",
    "RemoteAppServerConnectArgs",
    "RemoteAppServerClientState",
    "RemoteAppServerClientStep",
    "RemoteAppServerEndpoint",
    "RemoteClientInfo",
    "RemoteClientShutdownPlan",
    "RemoteExecLoopActionOutcome",
    "RemoteExecLoopCycleExecution",
    "RemoteExecLoopRunResult",
    "RemoteExecSessionConnectRunResult",
    "RemoteExecSessionRunResult",
    "RemoteExecSessionStartupResult",
    "RemoteInitializeCapabilities",
    "RemoteInitializeParams",
    "RemoteInitializeState",
    "RemoteInitializeStep",
    "RemoteInitializeWebSocketResult",
    "RemotePendingRequestFailure",
    "RemoteWebSocketClient",
    "RemoteWebSocketClientCloseResult",
    "RemoteWorkerExitResult",
    "InitialOperationRequest",
    "InitialOperationResult",
    "RESUME_LOOKUP_REQUEST_ID",
    "RequestIdSequencer",
    "ReviewStartParams",
    "ResumeThreadIdListResult",
    "ResumeThreadIdLookup",
    "ServerRequestDecision",
    "ThreadBootstrapRequest",
    "ThreadBootstrapResult",
    "ThreadListParams",
    "ThreadResumeParams",
    "ThreadReadParams",
    "ThreadSourceKind",
    "ThreadStartParams",
    "ThreadUnsubscribeParams",
    "TurnInterruptParams",
    "TurnStartParams",
    "TypedRequestError",
    "TypedRequestResult",
    "all_thread_source_kinds",
    "app_server_control_socket_path",
    "apply_remote_auth_token_env",
    "approvals_reviewer_override_from_config",
    "canceled_mcp_server_elicitation_response",
    "cwds_match",
    "decode_jsonrpc_message",
    "direct_resume_thread_id",
    "encode_jsonrpc_message",
    "encode_jsonrpc_websocket_text_frame",
    "backfill_turn_completed_notification",
    "exec_mode_server_request_decision",
    "exec_mode_server_request_rejection_reason",
    "exec_loop_exit_code",
    "exec_loop_action_failure_result",
    "exec_loop_actions_from_interrupt",
    "exec_loop_client_shutdown_failure_warning",
    "exec_loop_completion_result",
    "exec_loop_cycle_from_interrupt",
    "exec_loop_cycle_from_server_event",
    "exec_loop_cycle_from_stream_closed",
    "exec_loop_interrupt_request",
    "exec_loop_interrupt_step",
    "exec_loop_actions_from_step",
    "exec_loop_client_request_failure_warning",
    "exec_loop_action_jsonrpc_message",
    "exec_loop_notification_decision",
    "exec_loop_server_event_decision",
    "exec_loop_shutdown_request",
    "exec_loop_step",
    "format_request_error",
    "initial_operation_request_from_plan",
    "initial_operation_result_from_response",
    "json_rpc_rejection_error",
    "json_rpc_error_wire_mapping",
    "json_rpc_error_from_mapping",
    "jsonrpc_notification",
    "jsonrpc_message_to_mapping",
    "jsonrpc_message_kind",
    "jsonrpc_message_from_server_request_decision",
    "jsonrpc_request_from_client_request",
    "lagged_event_warning_message",
    "latest_thread_cwd",
    "notification_indicates_exec_error",
    "next_initial_operation_request",
    "next_thread_bootstrap_request",
    "parse_latest_turn_context_cwd",
    "permission_profile_id_from_active_profile",
    "permissions_selection_from_config",
    "pick_resume_thread_id_from_list_response",
    "review_start_params_from_plan",
    "review_start_params_from_request",
    "read_remote_auth_token_from_env_var",
    "read_remote_auth_token_from_env_var_with",
    "remote_addr_parse_error_message",
    "remote_addr_supports_auth_token",
    "remote_auth_token_url_error_message",
    "remote_app_server_client_connect",
    "remote_closed_connection_message",
    "remote_connect_failed_message",
    "remote_connect_timeout_message",
    "remote_client_state_from_initialize",
    "remote_client_enqueue_event",
    "remote_client_handle_jsonrpc_message",
    "remote_client_handle_jsonrpc_text",
    "remote_client_handle_websocket_event",
    "remote_client_next_event",
    "remote_client_resolve_or_reject_server_request",
    "remote_client_send_initialized_notification",
    "remote_client_send_notification",
    "remote_client_send_request",
    "remote_client_shutdown_close_error",
    "remote_client_shutdown_plan",
    "remote_client_worker_exit",
    "remote_close_websocket_failed_message",
    "remote_disconnected_event",
    "remote_disconnected_message",
    "remote_duplicate_request_id_message",
    "remote_endpoint_auth_token_error",
    "remote_exec_loop_cycle",
    "remote_exec_loop_execute_action",
    "remote_exec_session_connect_and_run",
    "remote_exec_session_run",
    "remote_exec_session_startup",
    "remote_exec_session_run_loop",
    "remote_event_consumer_channel_closed_message",
    "remote_invalid_authorization_header_message",
    "remote_invalid_jsonrpc_message",
    "remote_invalid_uds_handshake_url_message",
    "remote_initialized_notification",
    "remote_initialize_closed_eof_message",
    "remote_initialize_closed_message",
    "remote_initialize_handle_jsonrpc_message",
    "remote_initialize_handle_jsonrpc_text",
    "remote_initialize_handle_websocket_event",
    "remote_initialize_invalid_response_message",
    "remote_initialize_rejected_message",
    "remote_initialize_request",
    "remote_initialize_start",
    "remote_initialize_timeout_message",
    "remote_initialize_transport_failed_message",
    "remote_initialize_websocket_connection",
    "remote_notify_channel_closed_message",
    "remote_reject_channel_closed_message",
    "remote_request_channel_closed_message",
    "remote_resolve_channel_closed_message",
    "remote_read_websocket_frame_event",
    "remote_transport_failed_message",
    "remote_upgrade_failed_message",
    "remote_upgrade_timeout_message",
    "remote_websocket_config_mapping",
    "remote_worker_channel_closed_message",
    "remote_write_failed_message",
    "remote_write_jsonrpc_websocket_message",
    "remote_write_websocket_message_failed_message",
    "websocket_close_error_is_already_closed",
    "reject_server_request_error",
    "resume_lookup_model_providers",
    "resume_thread_id_from_local_sources",
    "resume_thread_id_from_list_response",
    "resume_thread_id_lookup_request",
    "resume_thread_id_lookup_step",
    "resolve_remote_addr",
    "resolve_remote_endpoint",
    "resolve_server_request_error",
    "sandbox_mode_from_permission_profile",
    "server_request_method_name",
    "session_configured_from_thread_resume_response",
    "session_configured_from_thread_start_response",
    "exec_session_startup_result",
    "exec_session_startup_processor_actions",
    "exec_session_config_mapping",
    "should_backfill_turn_completed_items",
    "should_process_notification",
    "thread_read_request",
    "thread_bootstrap_request",
    "thread_bootstrap_processor_actions",
    "thread_bootstrap_result_from_response",
    "thread_list_params_for_resume",
    "thread_list_request_for_resume",
    "thread_matches_resume_cwd",
    "thread_resume_params_from_config",
    "thread_start_params_from_config",
    "thread_unsubscribe_request",
    "task_id_from_initial_operation_response",
    "typed_request_deserialize_error",
    "typed_request_result_from_remote_step",
    "typed_request_result_from_response",
    "typed_request_server_error",
    "typed_request_transport_error",
    "initial_operation_processor_actions",
    "turn_interrupt_request",
    "turn_items_for_thread",
    "turn_start_params_from_plan",
    "unsupported_remote_server_request_error",
    "is_supported_remote_server_request_method",
    "websocket_url_supports_auth_token",
]
