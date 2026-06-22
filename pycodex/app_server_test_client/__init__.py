"""Python package for Rust crate ``codex-app-server-test-client``.

Current coverage focuses on the public facade, command orchestration, JSON-RPC
state handling, stdio/websocket client construction, default live command
runner wiring, and live elicitation harness from Rust ``src/lib.rs``. Tracing
provider side effects remain pending.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pycodex.exec.websocket import StdlibWebSocket

DEFAULT_WEBSOCKET_URL = "ws://127.0.0.1:4222"
NOTIFICATIONS_TO_OPT_OUT = [
    "command/exec/outputDelta",
    "item/agentMessage/delta",
    "item/plan/delta",
    "item/fileChange/outputDelta",
    "item/reasoning/summaryTextDelta",
    "item/reasoning/textDelta",
]
DEFAULT_ANALYTICS_ENABLED = True
OTEL_SERVICE_NAME = "codex-app-server-test-client"
RUNTIME_DIR = Path("/tmp/codex-app-server-test-client")
TRACE_DISABLED_MESSAGE = (
    "Not enabled - enable tracing in $CODEX_HOME/config.toml to get a trace URL!"
)
ON_REQUEST_APPROVAL_POLICY = "on-request"
TRIGGER_CMD_APPROVAL_PROMPT = (
    "Run `touch /tmp/should-trigger-approval` so I can confirm the file exists."
)
TRIGGER_PATCH_APPROVAL_PROMPT = (
    "Create a file named APPROVAL_DEMO.txt containing a short hello message using apply_patch."
)
NO_TRIGGER_CMD_APPROVAL_PROMPT = "Run `touch should_not_trigger_approval.txt`"
TRIGGER_ZSH_FORK_MULTI_CMD_APPROVAL_PROMPT = (
    "Run this exact command using shell command execution without rewriting or splitting it: "
    "/usr/bin/true && /usr/bin/true"
)

ClientRunner = Any


class AppServerTestClientError(RuntimeError):
    pass


class CommandApprovalBehavior(Enum):
    ALWAYS_ACCEPT = "always_accept"
    ABORT_ON = "abort_on"


@dataclass(frozen=True)
class DynamicToolSpec:
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] | None = None

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "DynamicToolSpec":
        if not isinstance(value.get("name"), str) or not value["name"]:
            raise AppServerTestClientError("decode dynamic tool")
        schema = value.get("inputSchema")
        if schema is not None and not isinstance(schema, dict):
            raise AppServerTestClientError("decode dynamic tool")
        description = value.get("description")
        if description is not None and not isinstance(description, str):
            raise AppServerTestClientError("decode dynamic tool")
        return cls(name=value["name"], description=description, inputSchema=schema)


@dataclass(frozen=True)
class SpawnCodex:
    codex_bin: Path


@dataclass(frozen=True)
class ConnectWs:
    url: str


Endpoint = SpawnCodex | ConnectWs


@dataclass(frozen=True)
class JSONRPCRequest:
    id: str
    method: str
    params: Any = None

    def to_message(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id, "method": self.method}
        if self.params is not None:
            payload["params"] = self.params
        return payload


@dataclass(frozen=True)
class JSONRPCResponse:
    id: str
    result: Any

    def to_message(self) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": self.id, "result": self.result}


@dataclass(frozen=True)
class JSONRPCError:
    id: str | None
    error: Any


@dataclass(frozen=True)
class JSONRPCNotification:
    method: str
    params: Any = None

    def to_message(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": self.method}
        if self.params is not None:
            payload["params"] = self.params
        return payload


class MemoryTransport:
    def __init__(self, incoming: list[str | dict[str, Any]] | None = None) -> None:
        self.incoming: deque[str] = deque()
        self.written: list[str] = []
        for item in incoming or []:
            self.queue(item)

    def queue(self, item: str | dict[str, Any]) -> None:
        self.incoming.append(item if isinstance(item, str) else json.dumps(item))

    def write_payload(self, payload: str) -> None:
        self.written.append(payload)

    def read_payload(self) -> str:
        if not self.incoming:
            raise AppServerTestClientError("codex app-server closed stdout")
        return self.incoming.popleft()


class StdioTransport:
    def __init__(self, child: subprocess.Popen[str]) -> None:
        self.child = child
        if child.stdin is None:
            raise AppServerTestClientError("codex app-server stdin unavailable")
        if child.stdout is None:
            raise AppServerTestClientError("codex app-server stdout unavailable")
        self.stdin = child.stdin
        self.stdout = child.stdout

    @classmethod
    def spawn(cls, codex_bin: str | Path, config_overrides: list[str] | None = None) -> "StdioTransport":
        codex_path = Path(codex_bin)
        args = [str(codex_path)]
        for override_kv in config_overrides or []:
            args.extend(["--config", override_kv])
        args.append("app-server")
        try:
            child = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,
                text=True,
                encoding="utf-8",
                env=_command_env_with_bin_parent(codex_path),
            )
        except OSError as exc:
            raise AppServerTestClientError(
                f"failed to start `{codex_path}` app-server"
            ) from exc
        return cls(child)

    def write_payload(self, payload: str) -> None:
        self.stdin.write(payload + "\n")
        self.stdin.flush()

    def read_payload(self) -> str:
        line = self.stdout.readline()
        if line == "":
            raise AppServerTestClientError("codex app-server closed stdout")
        return line.rstrip("\r\n")

    def close(self) -> None:
        try:
            self.stdin.close()
        except OSError:
            pass
        if self.child.poll() is None:
            self.child.terminate()


class WebSocketTransport:
    def __init__(self, websocket: Any, url: str) -> None:
        self.websocket = websocket
        self.url = url

    @classmethod
    def connect(cls, url: str) -> "WebSocketTransport":
        try:
            return cls(StdlibWebSocket.connect(url), url)
        except Exception as exc:
            raise AppServerTestClientError(
                f"failed to connect to `{url}` app-server websocket"
            ) from exc

    def write_payload(self, payload: str) -> None:
        try:
            self.websocket.send_text(payload)
        except Exception as exc:
            raise AppServerTestClientError(
                f"failed to write websocket message to `{self.url}`"
            ) from exc

    def read_payload(self) -> str:
        try:
            return self.websocket.recv_text()
        except Exception as exc:
            raise AppServerTestClientError(
                f"failed to read websocket message from `{self.url}`"
            ) from exc

    def close(self) -> None:
        close = getattr(self.websocket, "close", None)
        if callable(close):
            close()


def _command_env_with_bin_parent(codex_bin: str | Path) -> dict[str, str]:
    codex_path = Path(codex_bin)
    env = os.environ.copy()
    if codex_path.parent != Path("."):
        existing_path = env.get("PATH", "")
        env["PATH"] = str(codex_path.parent) + (
            os.pathsep + existing_path if existing_path else ""
        )
    return env


class BackgroundAppServer:
    def __init__(self, process: Any, url: str) -> None:
        self.process = process
        self.url = url

    @classmethod
    def spawn(
        cls,
        codex_bin: str | Path,
        config_overrides: list[str] | None = None,
        *,
        popen: Any = subprocess.Popen,
    ) -> "BackgroundAppServer":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            host, port = listener.getsockname()
        url = f"ws://{host}:{port}"
        codex_path = Path(codex_bin)
        args = [str(codex_path)]
        for override_kv in config_overrides or []:
            args.extend(["--config", override_kv])
        args.extend(["app-server", "--listen", url])
        try:
            process = popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=None,
                env=_command_env_with_bin_parent(codex_path),
            )
        except OSError as exc:
            raise AppServerTestClientError(
                f"failed to start `{codex_path}` app-server"
            ) from exc
        return cls(process, url)

    def close(self) -> None:
        poll = getattr(self.process, "poll", None)
        if callable(poll) and poll() is not None:
            return
        terminate = getattr(self.process, "terminate", None)
        if callable(terminate):
            terminate()
        wait = getattr(self.process, "wait", None)
        if callable(wait):
            wait()

    def __enter__(self) -> "BackgroundAppServer":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()


class CodexClient:
    def __init__(self, transport: Any | None = None, *, output: Any | None = None) -> None:
        self.transport = transport or MemoryTransport()
        self.output = output
        self.pending_notifications: deque[JSONRPCNotification] = deque()
        self.command_approval_behavior: tuple[CommandApprovalBehavior, int | None] = (
            CommandApprovalBehavior.ALWAYS_ACCEPT,
            None,
        )
        self.command_approval_count = 0
        self.command_approval_item_ids: list[str] = []
        self.command_execution_statuses: list[str] = []
        self.command_execution_outputs: list[str] = []
        self.command_output_stream = ""
        self.command_item_started = False
        self.helper_done_seen = False
        self.turn_completed_before_helper_done = False
        self.unexpected_items_before_helper_done: list[Any] = []
        self.last_turn_status: str | None = None
        self.last_turn_error_message: str | None = None

    @classmethod
    def connect(
        cls,
        endpoint: Endpoint,
        config_overrides: list[str] | None = None,
        *,
        transport: Any | None = None,
    ) -> "CodexClient":
        if transport is not None:
            return cls(transport)
        if isinstance(endpoint, SpawnCodex):
            return cls(StdioTransport.spawn(endpoint.codex_bin, config_overrides))
        if isinstance(endpoint, ConnectWs):
            return cls(WebSocketTransport.connect(endpoint.url))
        raise AppServerTestClientError(f"unsupported endpoint: {endpoint!r}")

    def note_helper_output(self, output: str) -> None:
        self.command_output_stream += output
        if "[elicitation-hold] done" in self.command_output_stream:
            self.helper_done_seen = True

    def emit_output(self, payload: str) -> None:
        if self.output is not None:
            self.output(payload)
            return
        sys.stdout.write(payload)
        sys.stdout.flush()

    def emit_line(self, payload: str = "") -> None:
        self.emit_output(payload + "\n")

    def initialize(self) -> Any:
        return self.initialize_with_experimental_api(True)

    def initialize_with_experimental_api(self, experimental_api: bool) -> Any:
        request_id = self.request_id()
        response = self.send_request(
            JSONRPCRequest(
                id=request_id,
                method="initialize",
                params={
                    "clientInfo": {
                        "name": "codex-toy-app-server",
                        "title": "Codex Toy App Server",
                        "version": "pycodex",
                    },
                    "capabilities": {
                        "experimentalApi": experimental_api,
                        "requestAttestation": False,
                        "optOutNotificationMethods": list(NOTIFICATIONS_TO_OPT_OUT),
                    },
                },
            ),
            request_id,
            "initialize",
        )
        self.write_jsonrpc_message(JSONRPCNotification("initialized"))
        return response

    def thread_start(self, params: Any) -> Any:
        return self._method_request("thread/start", params)

    def thread_resume(self, params: Any) -> Any:
        return self._method_request("thread/resume", params)

    def turn_start(self, params: Any) -> Any:
        return self._method_request("turn/start", params)

    def login_account_chatgpt(self) -> Any:
        return self._method_request(
            "account/login/start",
            {"type": "chatgpt", "codexStreamlinedLogin": False},
        )

    def login_account_chatgpt_device_code(self) -> Any:
        return self._method_request(
            "account/login/start",
            {"type": "chatgptDeviceCode"},
        )

    def model_list(self, params: Any = None) -> Any:
        return self._method_request("model/list", model_list_params() if params is None else params)

    def thread_list(self, params: Any = None, *, limit: int = 20) -> Any:
        return self._method_request(
            "thread/list", thread_list_params(limit=limit) if params is None else params
        )

    def get_account_rate_limits(self) -> Any:
        return self._method_request("account/rateLimits/read", None)

    def thread_increment_elicitation(self, params: Any) -> Any:
        return self._method_request("thread/increment_elicitation", params)

    def thread_decrement_elicitation(self, params: Any) -> Any:
        return self._method_request("thread/decrement_elicitation", params)

    def wait_for_account_login_completion(self, expected_login_id: str) -> Any:
        while True:
            notification = self.next_notification()
            params = notification.params if isinstance(notification.params, dict) else {}
            if notification.method != "account/login/completed":
                continue
            login_id = params.get("loginId")
            if login_id is None:
                login_id = params.get("login_id")
            if login_id == expected_login_id:
                return params

    def _method_request(self, method: str, params: Any) -> Any:
        request_id = self.request_id()
        return self.send_request(JSONRPCRequest(request_id, method, params), request_id, method)

    def stream_turn(self, thread_id: str, turn_id: str) -> None:
        while True:
            notification = self.next_notification()
            method = notification.method
            params = notification.params if isinstance(notification.params, dict) else {}

            if method == "thread/started":
                thread = _payload_child(params, "thread")
                if _payload_id(thread) == thread_id:
                    self.emit_line(f"< thread/started notification: {thread!r}")
                    continue
            elif method == "turn/started":
                turn = _payload_child(params, "turn")
                if _payload_id(turn) == turn_id:
                    status = _payload_get(turn, "status")
                    self.emit_line(f"< turn/started notification: {status!r}")
                    continue
            elif method == "item/agentMessage/delta":
                delta = params.get("delta")
                if isinstance(delta, str):
                    self.emit_output(delta)
                continue
            elif method in (
                "item/commandExecution/outputDelta",
                "command/exec/outputDelta",
            ):
                delta = params.get("delta")
                if isinstance(delta, str):
                    self.note_helper_output(delta)
                    self.emit_output(delta)
            elif method == "item/commandExecution/terminalInteraction":
                stdin = params.get("stdin")
                if isinstance(stdin, str):
                    self.emit_line(f"[stdin sent: {stdin}]")
                continue
            elif method == "item/started":
                item = _payload_child(params, "item")
                if _is_command_execution_item(item):
                    if self.command_item_started and not self.helper_done_seen:
                        self.unexpected_items_before_helper_done.append(item)
                    self.command_item_started = True
                elif item_started_before_helper_done_is_unexpected(
                    item, self.command_item_started, self.helper_done_seen
                ):
                    self.unexpected_items_before_helper_done.append(item)
                self.emit_line(f"\n< item started: {item!r}")
            elif method == "item/completed":
                item = _payload_child(params, "item")
                if _is_command_execution_item(item):
                    status = _payload_get(item, "status")
                    if isinstance(status, str):
                        self.command_execution_statuses.append(status)
                    aggregated_output = _payload_get(item, "aggregatedOutput")
                    if aggregated_output is None:
                        aggregated_output = _payload_get(item, "aggregated_output")
                    if isinstance(aggregated_output, str):
                        self.note_helper_output(aggregated_output)
                        self.command_execution_outputs.append(aggregated_output)
                self.emit_line(f"< item completed: {item!r}")
            elif method == "turn/completed":
                turn = _payload_child(params, "turn")
                if _payload_id(turn) == turn_id:
                    status = _payload_get(turn, "status")
                    if isinstance(status, str):
                        self.last_turn_status = status
                    if self.command_item_started and not self.helper_done_seen:
                        self.turn_completed_before_helper_done = True
                    error = _payload_get(turn, "error")
                    message = _payload_get(error, "message")
                    self.last_turn_error_message = message if isinstance(message, str) else None
                    self.emit_line(f"\n< turn/completed notification: {status!r}")
                    if self.last_turn_error_message is not None:
                        self.emit_line(f"[turn error] {self.last_turn_error_message}")
                    return
            elif method == "item/mcpToolCall/progress":
                message = params.get("message")
                if isinstance(message, str):
                    self.emit_line(f"< MCP tool progress: {message}")
                continue
            else:
                self.emit_line(f"[UNKNOWN SERVER NOTIFICATION] {notification!r}")

    def stream_notifications_forever(self, max_notifications: int | None = None) -> int:
        count = 0
        while max_notifications is None or count < max_notifications:
            self.next_notification()
            count += 1
        return count

    def send_request(self, request: JSONRPCRequest, request_id: str, method: str) -> Any:
        self.write_request(request)
        return self.wait_for_response(request_id, method)

    def write_request(self, request: JSONRPCRequest) -> None:
        self.write_jsonrpc_message(request)

    def wait_for_response(self, request_id: str, method: str) -> Any:
        while True:
            message = self.read_jsonrpc_message()
            kind = _jsonrpc_kind(message)
            if kind == "response" and message.get("id") == request_id:
                return message.get("result")
            if kind == "error" and message.get("id") == request_id:
                raise AppServerTestClientError(f"{method} failed: {message.get('error')!r}")
            if kind == "notification":
                self.pending_notifications.append(
                    JSONRPCNotification(message["method"], message.get("params"))
                )
            elif kind == "request":
                self.handle_server_request(message)

    def next_notification(self) -> JSONRPCNotification:
        if self.pending_notifications:
            return self.pending_notifications.popleft()
        while True:
            message = self.read_jsonrpc_message()
            kind = _jsonrpc_kind(message)
            if kind == "notification":
                return JSONRPCNotification(message["method"], message.get("params"))
            if kind == "request":
                self.handle_server_request(message)

    def read_jsonrpc_message(self) -> dict[str, Any]:
        while True:
            raw = self.read_payload().strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception as exc:
                raise AppServerTestClientError("response was not valid JSON-RPC") from exc
            if not isinstance(parsed, dict):
                raise AppServerTestClientError("response was not a valid JSON-RPC message")
            return parsed

    def request_id(self) -> str:
        return str(uuid.uuid4())

    def handle_server_request(self, request: dict[str, Any]) -> None:
        method = request.get("method")
        if method == "commandExecution/requestApproval":
            self.handle_command_execution_request_approval(
                str(request.get("id")), request.get("params") or {}
            )
        elif method == "fileChange/requestApproval":
            self.approve_file_change_request(str(request.get("id")), request.get("params") or {})
        else:
            raise AppServerTestClientError(f"received unsupported server request: {method!r}")

    def handle_command_execution_request_approval(
        self, request_id: str, params: dict[str, Any]
    ) -> None:
        self.command_approval_count += 1
        item_id = str(params.get("item_id") or params.get("itemId") or "")
        self.command_approval_item_ids.append(item_id)
        behavior, abort_on = self.command_approval_behavior
        decision = (
            "cancel"
            if behavior is CommandApprovalBehavior.ABORT_ON
            and abort_on == self.command_approval_count
            else "accept"
        )
        self.send_server_request_response(request_id, {"decision": decision})

    def approve_file_change_request(self, request_id: str, _params: dict[str, Any]) -> None:
        self.send_server_request_response(request_id, {"decision": "accept"})

    def send_server_request_response(self, request_id: str, response: Any) -> None:
        self.write_jsonrpc_message(JSONRPCResponse(request_id, response))

    def write_jsonrpc_message(
        self, message: JSONRPCRequest | JSONRPCResponse | JSONRPCNotification | dict[str, Any]
    ) -> None:
        if isinstance(message, (JSONRPCRequest, JSONRPCResponse, JSONRPCNotification)):
            payload = message.to_message()
        else:
            payload = message
        self.write_payload(json.dumps(payload, separators=(",", ":")))

    def write_payload(self, payload: str) -> None:
        self.transport.write_payload(payload)

    def read_payload(self) -> str:
        return self.transport.read_payload()


def resolve_endpoint(codex_bin: str | Path | None, url: str | None) -> Endpoint:
    if codex_bin is not None and url is not None:
        raise AppServerTestClientError("--codex-bin and --url are mutually exclusive")
    if codex_bin is not None:
        return SpawnCodex(Path(codex_bin))
    if url is not None:
        return ConnectWs(url)
    return ConnectWs(DEFAULT_WEBSOCKET_URL)


def model_list_params(
    *, cursor: str | None = None, limit: int | None = None, include_hidden: bool | None = None
) -> dict[str, Any]:
    return {"cursor": cursor, "limit": limit, "includeHidden": include_hidden}


def thread_list_params(
    *,
    limit: int = 20,
    cursor: str | None = None,
    sort_key: str | None = None,
    sort_direction: str | None = None,
    model_providers: list[str] | None = None,
    source_kinds: list[str] | None = None,
    archived: bool | None = None,
    cwd: str | list[str] | None = None,
    use_state_db_only: bool = False,
    search_term: str | None = None,
) -> dict[str, Any]:
    return {
        "cursor": cursor,
        "limit": limit,
        "sortKey": sort_key,
        "sortDirection": sort_direction,
        "modelProviders": model_providers,
        "sourceKinds": source_kinds,
        "archived": archived,
        "cwd": cwd,
        "useStateDbOnly": use_state_db_only,
        "searchTerm": search_term,
    }


def dynamic_tool_spec_to_json(tool: DynamicToolSpec | dict[str, Any]) -> dict[str, Any]:
    if isinstance(tool, dict):
        return dict(tool)
    payload: dict[str, Any] = {"name": tool.name}
    if tool.description is not None:
        payload["description"] = tool.description
    if tool.inputSchema is not None:
        payload["inputSchema"] = tool.inputSchema
    return payload


def text_user_input(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text, "text_elements": []}


def read_only_sandbox_policy(*, network_access: bool = False) -> dict[str, Any]:
    return {"type": "readOnly", "networkAccess": network_access}


def danger_full_access_sandbox_policy() -> dict[str, Any]:
    return {"type": "dangerFullAccess"}


def thread_start_params(
    *,
    dynamic_tools: list[DynamicToolSpec | dict[str, Any]] | None = None,
    model: str | None = None,
    model_provider: str | None = None,
    cwd: str | None = None,
    approval_policy: str | None = None,
    sandbox: dict[str, Any] | None = None,
    experimental_raw_events: bool | None = None,
    mock_experimental_field: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "modelProvider": model_provider,
        "cwd": cwd,
        "approvalPolicy": approval_policy,
        "sandbox": sandbox,
        "dynamicTools": (
            None if dynamic_tools is None else [dynamic_tool_spec_to_json(tool) for tool in dynamic_tools]
        ),
        "mockExperimentalField": mock_experimental_field,
        "experimentalRawEvents": experimental_raw_events,
    }


def turn_start_params(
    thread_id: str,
    user_message: str,
    *,
    approval_policy: str | None = None,
    sandbox_policy: dict[str, Any] | None = None,
    cwd: str | None = None,
    model: str | None = None,
    service_tier: str | None = None,
    effort: str | None = None,
    summary: str | None = None,
    personality: str | None = None,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "input": [text_user_input(user_message)],
        "cwd": cwd,
        "approvalPolicy": approval_policy,
        "sandboxPolicy": sandbox_policy,
        "model": model,
        "serviceTier": service_tier,
        "effort": effort,
        "summary": summary,
        "personality": personality,
        "outputSchema": output_schema,
    }


def thread_elicitation_params(thread_id: str) -> dict[str, Any]:
    return {"threadId": thread_id}


def _jsonrpc_kind(message: dict[str, Any]) -> str:
    if "method" in message and "id" in message:
        return "request"
    if "method" in message:
        return "notification"
    if "error" in message:
        return "error"
    if "result" in message:
        return "response"
    raise AppServerTestClientError("response was not a valid JSON-RPC message")


def _payload_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _payload_child(value: Any, key: str) -> Any:
    child = _payload_get(value, key)
    return {} if child is None else child


def _payload_id(value: Any) -> str | None:
    item_id = _payload_get(value, "id")
    return item_id if isinstance(item_id, str) else None


def _required_payload_id(value: Any, label: str) -> str:
    item_id = _payload_id(value)
    if item_id is None:
        raise AppServerTestClientError(f"{label} id missing from app-server response")
    return item_id


def _is_command_execution_item(item: Any) -> bool:
    return _payload_get(item, "type") in {"commandExecution", "command_execution"}


def resolve_shared_websocket_url(
    codex_bin: str | Path | None, url: str | None, command: str
) -> str:
    if codex_bin is not None:
        raise AppServerTestClientError(
            f"{command} requires --url or an already-running websocket app-server; "
            "--codex-bin would spawn a private stdio app-server instead"
        )
    return url or DEFAULT_WEBSOCKET_URL


def shell_quote(input: str) -> str:
    return "'" + input.replace("'", "'\\''") + "'"


def serve_command_line(
    codex_bin: str | Path, config_overrides: list[str] | None, listen: str
) -> str:
    cmdline = (
        "tail -f /dev/null | RUST_BACKTRACE=full RUST_LOG=warn,codex_=trace "
        + shell_quote(str(codex_bin))
    )
    for override_kv in config_overrides or []:
        cmdline += " --config " + shell_quote(override_kv)
    cmdline += " app-server --listen " + shell_quote(listen)
    return cmdline


def _listen_port(listen: str) -> int:
    parsed = urlparse(listen)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "ws":
        return 80
    if parsed.scheme == "wss":
        return 443
    raise AppServerTestClientError(f"unable to infer port from --listen URL `{listen}`")


def kill_listeners_on_same_port(
    listen: str,
    *,
    run: Any = subprocess.run,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    try:
        port = _listen_port(listen)
    except ValueError as exc:
        raise AppServerTestClientError(f"invalid --listen URL `{listen}`") from exc

    output = run(
        ["lsof", "-nP", f"-tiTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    if output.returncode != 0:
        return {"port": port, "terminated": [], "forceKilled": []}

    pids = [line.strip() for line in output.stdout.splitlines() if line.strip().isdigit()]
    for pid in pids:
        run(["kill", pid])

    sleep(0.3)
    output = run(
        ["lsof", "-nP", f"-tiTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    remaining = []
    if output.returncode == 0:
        remaining = [line.strip() for line in output.stdout.splitlines() if line.strip().isdigit()]
    for pid in remaining:
        run(["kill", "-9", pid])
    return {"port": port, "terminated": pids, "forceKilled": remaining}


def serve(
    codex_bin: str | Path,
    config_overrides: list[str] | None = None,
    *,
    listen: str = DEFAULT_WEBSOCKET_URL,
    kill: bool = False,
    popen: Any = subprocess.Popen,
    runtime_dir: Path = RUNTIME_DIR,
) -> dict[str, Any]:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path = runtime_dir / "app-server.log"
    kill_result = kill_listeners_on_same_port(listen) if kill else None
    cmdline = serve_command_line(codex_bin, config_overrides, listen)
    log_file = log_path.open("a", encoding="utf-8")
    log_file_stderr = log_path.open("a", encoding="utf-8")
    try:
        child = popen(
            ["nohup", "sh", "-c", cmdline],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file_stderr,
        )
    except OSError as exc:
        log_file.close()
        log_file_stderr.close()
        raise AppServerTestClientError(f"failed to start `{codex_bin}` app-server") from exc
    return {
        "listen": listen,
        "pid": child.pid,
        "log": str(log_path),
        "cmdline": cmdline,
        "kill": kill_result,
    }


def ensure_dynamic_tools_unused(
    dynamic_tools: list[DynamicToolSpec] | None, command: str
) -> None:
    if dynamic_tools is not None:
        raise AppServerTestClientError(
            "dynamic tools are only supported for v2 thread/start; "
            f"remove --dynamic-tools for {command} or use send-message-v2"
        )


def parse_dynamic_tools_arg(dynamic_tools: str | None) -> list[DynamicToolSpec] | None:
    if dynamic_tools is None:
        return None
    if dynamic_tools.startswith("@"):
        path = dynamic_tools[1:]
        try:
            raw_json = Path(path).read_text()
        except OSError as exc:
            raise AppServerTestClientError(f"read dynamic tools file {path}") from exc
    else:
        raw_json = dynamic_tools
    try:
        value = json.loads(raw_json)
    except Exception as exc:
        raise AppServerTestClientError("parse dynamic tools JSON") from exc
    if isinstance(value, list):
        return [DynamicToolSpec.from_json(item) for item in value]
    if isinstance(value, dict):
        return [DynamicToolSpec.from_json(value)]
    raise AppServerTestClientError("dynamic tools JSON must be an object or array")


def item_started_before_helper_done_is_unexpected(
    item: Any, command_item_started: bool, helper_done_seen: bool
) -> bool:
    if not command_item_started or helper_done_seen:
        return False
    kind = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
    return kind not in {"userMessage", "user_message"}


def trace_url_from_context(trace: Any) -> str | None:
    traceparent = trace.get("traceparent") if isinstance(trace, dict) else getattr(trace, "traceparent", None)
    if not isinstance(traceparent, str):
        return None
    parts = traceparent.split("-")
    if len(parts) >= 4 and len(parts[1]) == 32:
        return f"go/trace/{parts[1]}"
    return None


def current_span_w3c_trace_context(env: dict[str, str] | None = None) -> dict[str, str] | None:
    source = os.environ if env is None else env
    traceparent = source.get("TRACEPARENT") or source.get("traceparent")
    if not traceparent:
        return None
    context = {"traceparent": traceparent}
    tracestate = source.get("TRACESTATE") or source.get("tracestate")
    if tracestate:
        context["tracestate"] = tracestate
    return context


def trace_summary_capture(traces_enabled: bool, trace: Any | None = None) -> dict[str, str] | None:
    if not traces_enabled:
        return None
    if trace is None:
        trace = current_span_w3c_trace_context()
    url = trace_url_from_context(trace) if trace is not None else None
    return {"url": url} if url is not None else None


def print_trace_summary(trace_summary: dict[str, str] | None) -> str:
    if trace_summary and trace_summary.get("url"):
        return f"\n[Datadog trace]\n{trace_summary['url']}\n"
    return f"\n[Datadog trace]\n{TRACE_DISABLED_MESSAGE}\n"


def print_multiline_with_prefix(prefix: str, payload: str) -> str:
    return "".join(f"{prefix}{line}\n" for line in payload.splitlines())


@dataclass
class TestClientTracing:
    otel_provider: Any | None
    traces_enabled: bool

    @classmethod
    def initialize(
        cls,
        config_overrides: list[str],
        *,
        config_loader: Any | None = None,
        provider_builder: Any | None = None,
        subscriber_init: Any | None = None,
        version: str | None = None,
    ) -> "TestClientTracing":
        try:
            config = (
                {"configOverrides": list(config_overrides)}
                if config_loader is None
                else config_loader(list(config_overrides))
            )
        except Exception as exc:
            raise AppServerTestClientError("error loading config") from exc

        try:
            if provider_builder is None:
                provider = _default_otel_provider_from_config(config, config_overrides)
            else:
                provider = provider_builder(
                    config,
                    version=version or "python-port",
                    service_name=OTEL_SERVICE_NAME,
                    analytics_enabled=DEFAULT_ANALYTICS_ENABLED,
                )
        except Exception as exc:
            raise AppServerTestClientError(f"error loading otel config: {exc}") from exc

        traces_enabled = _otel_provider_traces_enabled(provider)
        if provider is not None and traces_enabled and subscriber_init is not None:
            try:
                subscriber_init(provider)
            except Exception:
                pass
        return cls(otel_provider=provider, traces_enabled=traces_enabled)


TestClientTracing.__test__ = False


def _default_otel_provider_from_config(config: Any, config_overrides: list[str]) -> Any | None:
    override_text = "\n".join(config_overrides).lower()
    config_text = json.dumps(config, sort_keys=True, default=str).lower()
    enabled = (
        "otel" in override_text
        and ("trace" in override_text or "tracing" in override_text)
        and "true" in override_text
    ) or (
        "otel" in config_text
        and ("trace" in config_text or "tracing" in config_text)
        and "true" in config_text
    )
    if not enabled:
        return None
    return {
        "serviceName": OTEL_SERVICE_NAME,
        "analyticsEnabled": DEFAULT_ANALYTICS_ENABLED,
        "tracerProvider": object(),
    }


def _otel_provider_traces_enabled(provider: Any | None) -> bool:
    if provider is None:
        return False
    if isinstance(provider, dict):
        return bool(provider.get("tracerProvider") or provider.get("tracer_provider"))
    return bool(
        getattr(provider, "tracer_provider", None)
        or getattr(provider, "tracerProvider", None)
    )


def _emit_text(output: Any, text: str) -> None:
    if hasattr(output, "write"):
        output.write(text)
    elif isinstance(output, list):
        output.append(text)
    elif output is None:
        sys.stdout.write(text)


def with_client(
    command_name: str,
    endpoint: Endpoint,
    config_overrides: list[str],
    callback: Any,
    *,
    client_factory: Any | None = None,
    tracing_factory: Any = TestClientTracing.initialize,
    trace_context_factory: Any = current_span_w3c_trace_context,
    output: Any = None,
) -> Any:
    if client_factory is None:
        client_factory = CodexClient.connect
    tracing = tracing_factory(list(config_overrides))
    trace_summary = trace_summary_capture(
        getattr(tracing, "traces_enabled", False),
        trace_context_factory(),
    )
    client = client_factory(endpoint, list(config_overrides))
    result = callback(client)
    _emit_text(output, print_trace_summary(trace_summary))
    return result


def send_message_v2_with_policies(
    client: Any,
    user_message: str,
    *,
    experimental_api: bool,
    approval_policy: str | None = None,
    sandbox_policy: dict[str, Any] | None = None,
    dynamic_tools: list[DynamicToolSpec | dict[str, Any]] | None = None,
) -> Any:
    initialize_response = client.initialize_with_experimental_api(experimental_api)
    thread_response = client.thread_start(thread_start_params(dynamic_tools=dynamic_tools))
    thread_id = _required_payload_id(_payload_get(thread_response, "thread"), "thread")
    turn_response = client.turn_start(
        turn_start_params(
            thread_id,
            user_message,
            approval_policy=approval_policy,
            sandbox_policy=sandbox_policy,
        )
    )
    turn_id = _required_payload_id(_payload_get(turn_response, "turn"), "turn")
    client.stream_turn(thread_id, turn_id)
    return {
        "initialize": initialize_response,
        "thread": thread_response,
        "turn": turn_response,
    }


def trigger_cmd_approval(
    client: Any,
    user_message: str | None = None,
    *,
    dynamic_tools: list[DynamicToolSpec | dict[str, Any]] | None = None,
) -> Any:
    return send_message_v2_with_policies(
        client,
        user_message or TRIGGER_CMD_APPROVAL_PROMPT,
        experimental_api=True,
        approval_policy=ON_REQUEST_APPROVAL_POLICY,
        sandbox_policy=read_only_sandbox_policy(network_access=False),
        dynamic_tools=dynamic_tools,
    )


def trigger_patch_approval(
    client: Any,
    user_message: str | None = None,
    *,
    dynamic_tools: list[DynamicToolSpec | dict[str, Any]] | None = None,
) -> Any:
    return send_message_v2_with_policies(
        client,
        user_message or TRIGGER_PATCH_APPROVAL_PROMPT,
        experimental_api=True,
        approval_policy=ON_REQUEST_APPROVAL_POLICY,
        sandbox_policy=read_only_sandbox_policy(network_access=False),
        dynamic_tools=dynamic_tools,
    )


def no_trigger_cmd_approval(
    client: Any,
    *,
    dynamic_tools: list[DynamicToolSpec | dict[str, Any]] | None = None,
) -> Any:
    return send_message_v2_with_policies(
        client,
        NO_TRIGGER_CMD_APPROVAL_PROMPT,
        experimental_api=True,
        dynamic_tools=dynamic_tools,
    )


def send_follow_up_v2(
    client: Any,
    first_message: str,
    follow_up_message: str,
    *,
    dynamic_tools: list[DynamicToolSpec | dict[str, Any]] | None = None,
) -> Any:
    initialize_response = client.initialize()
    thread_response = client.thread_start(thread_start_params(dynamic_tools=dynamic_tools))
    thread_id = _required_payload_id(_payload_get(thread_response, "thread"), "thread")

    first_turn_response = client.turn_start(turn_start_params(thread_id, first_message))
    first_turn_id = _required_payload_id(_payload_get(first_turn_response, "turn"), "turn")
    client.stream_turn(thread_id, first_turn_id)

    follow_up_response = client.turn_start(turn_start_params(thread_id, follow_up_message))
    follow_up_id = _required_payload_id(_payload_get(follow_up_response, "turn"), "turn")
    client.stream_turn(thread_id, follow_up_id)
    return {
        "initialize": initialize_response,
        "thread": thread_response,
        "firstTurn": first_turn_response,
        "followUpTurn": follow_up_response,
    }


def resume_message_v2(
    client: Any,
    thread_id: str,
    user_message: str,
    *,
    dynamic_tools: list[DynamicToolSpec | dict[str, Any]] | None = None,
) -> Any:
    ensure_dynamic_tools_unused(dynamic_tools, "resume-message-v2")
    initialize_response = client.initialize()
    resume_response = client.thread_resume({"threadId": thread_id})
    resumed_thread_id = _required_payload_id(_payload_get(resume_response, "thread"), "thread")
    turn_response = client.turn_start(turn_start_params(resumed_thread_id, user_message))
    turn_id = _required_payload_id(_payload_get(turn_response, "turn"), "turn")
    client.stream_turn(resumed_thread_id, turn_id)
    return {
        "initialize": initialize_response,
        "thread": resume_response,
        "turn": turn_response,
    }


def trigger_zsh_fork_multi_cmd_approval(
    client: Any,
    user_message: str | None = None,
    *,
    min_approvals: int = 2,
    abort_on: int | None = None,
    dynamic_tools: list[DynamicToolSpec | dict[str, Any]] | None = None,
) -> Any:
    if abort_on is not None and abort_on < 1:
        raise AppServerTestClientError("--abort-on must be >= 1 when provided")

    initialize_response = client.initialize()
    thread_response = client.thread_start(thread_start_params(dynamic_tools=dynamic_tools))
    thread_id = _required_payload_id(_payload_get(thread_response, "thread"), "thread")

    client.command_approval_behavior = (
        (CommandApprovalBehavior.ABORT_ON, abort_on)
        if abort_on is not None
        else (CommandApprovalBehavior.ALWAYS_ACCEPT, None)
    )
    client.command_approval_count = 0
    client.command_approval_item_ids.clear()
    client.command_execution_statuses.clear()
    client.last_turn_status = None

    turn_response = client.turn_start(
        turn_start_params(
            thread_id,
            user_message or TRIGGER_ZSH_FORK_MULTI_CMD_APPROVAL_PROMPT,
            approval_policy=ON_REQUEST_APPROVAL_POLICY,
            sandbox_policy=read_only_sandbox_policy(network_access=False),
        )
    )
    turn_id = _required_payload_id(_payload_get(turn_response, "turn"), "turn")
    client.stream_turn(thread_id, turn_id)

    if client.command_approval_count < min_approvals:
        raise AppServerTestClientError(
            f"expected at least {min_approvals} command approvals, got "
            f"{client.command_approval_count}"
        )

    approvals_per_item: dict[str, int] = {}
    for item_id in client.command_approval_item_ids:
        approvals_per_item[item_id] = approvals_per_item.get(item_id, 0) + 1
    max_approvals_for_one_item = max(approvals_per_item.values(), default=0)
    if max_approvals_for_one_item < min_approvals:
        raise AppServerTestClientError(
            f"expected at least {min_approvals} approvals for one command item, got max "
            f"{max_approvals_for_one_item} with map {approvals_per_item!r}"
        )

    last_command_status = (
        client.command_execution_statuses[-1] if client.command_execution_statuses else None
    )
    if abort_on is None:
        if last_command_status != "completed":
            raise AppServerTestClientError(
                f"expected completed command execution, got {last_command_status!r}"
            )
        if client.last_turn_status != "completed":
            raise AppServerTestClientError(
                f"expected completed turn in all-accept flow, got {client.last_turn_status!r}"
            )
    elif last_command_status == "completed":
        raise AppServerTestClientError(
            "expected non-completed command execution in mixed approval/decline flow, "
            f"got {last_command_status!r}"
        )

    return {
        "initialize": initialize_response,
        "thread": thread_response,
        "turn": turn_response,
        "approvals": client.command_approval_count,
        "approvalsPerItem": approvals_per_item,
        "commandStatuses": list(client.command_execution_statuses),
        "turnStatus": client.last_turn_status,
    }


def test_login(client: Any, *, device_code: bool = False) -> Any:
    initialize_response = client.initialize()
    login_response = (
        client.login_account_chatgpt_device_code()
        if device_code
        else client.login_account_chatgpt()
    )
    login_id = _payload_get(login_response, "loginId")
    if login_id is None:
        login_id = _payload_get(login_response, "login_id")
    if not isinstance(login_id, str):
        raise AppServerTestClientError("expected chatgpt login response")
    completion = client.wait_for_account_login_completion(login_id)
    error = _payload_get(completion, "error")
    if error:
        message = _payload_get(error, "message") or "unknown error from account/login/completed"
        raise AppServerTestClientError(f"login failed: {message}")
    return {
        "initialize": initialize_response,
        "login": login_response,
        "completion": completion,
    }


test_login.__test__ = False


def get_account_rate_limits(client: Any) -> Any:
    initialize_response = client.initialize()
    response = client.get_account_rate_limits()
    return {"initialize": initialize_response, "rateLimits": response}


def model_list(client: Any) -> Any:
    initialize_response = client.initialize()
    response = client.model_list(model_list_params())
    return {"initialize": initialize_response, "models": response}


def thread_list(client: Any, *, limit: int = 20) -> Any:
    initialize_response = client.initialize()
    response = client.thread_list(thread_list_params(limit=limit))
    return {"initialize": initialize_response, "threads": response}


def watch(client: Any, *, max_notifications: int | None = None) -> Any:
    initialize_response = client.initialize()
    streamed = client.stream_notifications_forever(max_notifications=max_notifications)
    return {"initialize": initialize_response, "streamed": streamed}


def thread_resume_follow(
    client: Any, thread_id: str, *, max_notifications: int | None = None
) -> Any:
    initialize_response = client.initialize()
    resume_response = client.thread_resume({"threadId": thread_id})
    streamed = client.stream_notifications_forever(max_notifications=max_notifications)
    return {
        "initialize": initialize_response,
        "thread": resume_response,
        "streamed": streamed,
    }


def thread_increment_elicitation(client: Any, thread_id: str) -> Any:
    response = client.thread_increment_elicitation(thread_elicitation_params(thread_id))
    return {"threadId": thread_id, "response": response}


def thread_decrement_elicitation(client: Any, thread_id: str) -> Any:
    response = client.thread_decrement_elicitation(thread_elicitation_params(thread_id))
    return {"threadId": thread_id, "response": response}


def default_live_elicitation_script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "codex"
        / "codex-rs"
        / "app-server-test-client"
        / "scripts"
        / "live_elicitation_hold.sh"
    )


def live_elicitation_timeout_pause(
    *,
    codex_bin: Path | None,
    url: str | None,
    config_overrides: list[str],
    model: str,
    workspace: Path,
    script: Path | None,
    hold_seconds: int,
    client_factory: Any = CodexClient.connect,
    background_server_factory: Any = BackgroundAppServer.spawn,
    monotonic: Any = time.monotonic,
    platform_name: str = os.name,
    current_exe: Path | None = None,
) -> dict[str, Any]:
    if platform_name == "nt":
        raise AppServerTestClientError(
            "live-elicitation-timeout-pause currently requires a POSIX shell"
        )
    if hold_seconds <= 10:
        raise AppServerTestClientError(
            "--hold-seconds must be greater than 10 to exceed the unified exec timeout"
        )
    if codex_bin is not None and url is not None:
        raise AppServerTestClientError("--codex-bin and --url are mutually exclusive")

    background_server = None
    if codex_bin is not None:
        background_server = background_server_factory(codex_bin, list(config_overrides))
        websocket_url = background_server.url
    else:
        websocket_url = url or DEFAULT_WEBSOCKET_URL

    script_path = Path(script) if script is not None else default_live_elicitation_script_path()
    if not script_path.is_file():
        if background_server is not None:
            background_server.close()
        raise AppServerTestClientError(f"helper script not found: {script_path}")

    try:
        workspace_path = Path(workspace).resolve(strict=True)
    except OSError as exc:
        if background_server is not None:
            background_server.close()
        raise AppServerTestClientError(f"failed to resolve workspace `{workspace}`") from exc

    exe_path = current_exe or Path(sys.argv[0]).resolve()
    client = client_factory(ConnectWs(websocket_url), [])
    initialize_response = client.initialize()
    client.emit_line(f"< initialize response: {initialize_response!r}") if hasattr(client, "emit_line") else None

    thread_response = client.thread_start(thread_start_params(model=model))
    client.emit_line(f"< thread/start response: {thread_response!r}") if hasattr(client, "emit_line") else None
    thread_id = _required_payload_id(_payload_get(thread_response, "thread"), "thread")
    command = (
        f"APP_SERVER_URL={shell_quote(websocket_url)} "
        f"APP_SERVER_TEST_CLIENT_BIN={shell_quote(str(exe_path))} "
        f"ELICITATION_HOLD_SECONDS={hold_seconds} sh {shell_quote(str(script_path))}"
    )
    prompt = (
        "Use the `exec_command` tool exactly once. Set its `cmd` field to the exact "
        "shell command below. Do not rewrite it, do not split it, do not call any "
        "other tool, do not set `yield_time_ms`, and wait for the command to finish "
        "before replying.\n\n"
        f"{command}\n\n"
        "After the command finishes, reply with exactly `DONE`."
    )

    started_at = monotonic()
    turn_response = client.turn_start(
        turn_start_params(
            thread_id,
            prompt,
            approval_policy="never",
            sandbox_policy=danger_full_access_sandbox_policy(),
            effort="high",
            cwd=str(workspace_path),
        )
    )
    client.emit_line(f"< turn/start response: {turn_response!r}") if hasattr(client, "emit_line") else None
    turn_id = _required_payload_id(_payload_get(turn_response, "turn"), "turn")

    stream_error: BaseException | None = None
    try:
        client.stream_turn(thread_id, turn_id)
    except BaseException as exc:
        stream_error = exc
    elapsed = monotonic() - started_at

    cleanup_response: Any = None
    cleanup_error: BaseException | None = None
    try:
        cleanup_response = client.thread_decrement_elicitation(
            thread_elicitation_params(thread_id)
        )
    except BaseException as exc:
        cleanup_error = exc
    finally:
        if background_server is not None:
            background_server.close()

    if cleanup_response is not None and hasattr(client, "emit_line"):
        client.emit_line(
            f"[cleanup] thread/decrement_elicitation response after harness: {cleanup_response!r}"
        )
    if cleanup_error is not None and hasattr(client, "emit_line"):
        client.emit_line(f"[cleanup] thread/decrement_elicitation ignored: {cleanup_error}")

    if stream_error is not None:
        raise AppServerTestClientError("stream_turn failed during live elicitation harness") from stream_error

    helper_output = next(
        (
            output
            for output in getattr(client, "command_execution_outputs", [])
            if "[elicitation-hold]" in output
        ),
        None,
    )
    if helper_output is None:
        raise AppServerTestClientError("expected helper script markers in command output")
    minimum_elapsed = max(int(hold_seconds) - 1, 0)
    if getattr(client, "last_turn_status", None) != "completed":
        raise AppServerTestClientError(
            "expected completed turn, got "
            f"{getattr(client, 'last_turn_status', None)!r} "
            f"(last error: {getattr(client, 'last_turn_error_message', None)!r})"
        )
    if "completed" not in getattr(client, "command_execution_statuses", []):
        raise AppServerTestClientError(
            "expected a completed command execution, got "
            f"{getattr(client, 'command_execution_statuses', [])!r}"
        )
    if not getattr(client, "helper_done_seen", False) or "[elicitation-hold] done" not in helper_output:
        raise AppServerTestClientError(
            f"expected helper script completion marker in command output, got: {helper_output!r}"
        )
    unexpected_items = getattr(client, "unexpected_items_before_helper_done", [])
    if unexpected_items:
        raise AppServerTestClientError(
            f"turn started new items before helper completion: {unexpected_items!r}"
        )
    if getattr(client, "turn_completed_before_helper_done", False):
        raise AppServerTestClientError("turn completed before helper script finished")
    if elapsed < minimum_elapsed:
        raise AppServerTestClientError(
            "turn completed too quickly to prove timeout pause worked: "
            f"elapsed={elapsed!r}, expected at least {minimum_elapsed!r}"
        )

    summary = {
        "threadId": thread_id,
        "turnId": turn_id,
        "elapsed": elapsed,
        "commandStatuses": list(getattr(client, "command_execution_statuses", [])),
        "cleanup": cleanup_response,
    }
    if hasattr(client, "emit_line"):
        client.emit_line(
            "[live elicitation timeout pause summary] "
            f"thread_id={thread_id}, turn_id={turn_id}, elapsed={elapsed!r}, "
            f"command_statuses={summary['commandStatuses']!r}"
        )
    return summary


class DefaultClientRunner:
    def __init__(
        self,
        *,
        client_factory: Any | None = None,
        serve_factory: Any = serve,
        tracing_factory: Any = TestClientTracing.initialize,
        trace_context_factory: Any = current_span_w3c_trace_context,
        output: Any = None,
    ) -> None:
        self.client_factory = client_factory or CodexClient.connect
        self.serve_factory = serve_factory
        self.tracing_factory = tracing_factory
        self.trace_context_factory = trace_context_factory
        self.output = output

    def _client(self, endpoint: Endpoint, config_overrides: list[str] | None = None) -> Any:
        return self.client_factory(endpoint, list(config_overrides or []))

    def _with_client(
        self,
        command_name: str,
        endpoint: Endpoint,
        config_overrides: list[str],
        callback: Any,
    ) -> Any:
        return with_client(
            command_name,
            endpoint,
            config_overrides,
            callback,
            client_factory=self.client_factory,
            tracing_factory=self.tracing_factory,
            trace_context_factory=self.trace_context_factory,
            output=self.output,
        )

    async def send_message_v2_endpoint(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        user_message: str,
        experimental_api: bool,
        dynamic_tools: list[DynamicToolSpec] | None,
    ) -> Any:
        return self._with_client(
            "send-message-v2",
            endpoint,
            config_overrides,
            lambda client: send_message_v2_with_policies(
                client,
                user_message,
                experimental_api=experimental_api,
                dynamic_tools=dynamic_tools,
            ),
        )

    async def send_message(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        user_message: str,
    ) -> Any:
        return self._with_client(
            "send-message",
            endpoint,
            config_overrides,
            lambda client: send_message_v2_with_policies(
                client,
                user_message,
                experimental_api=False,
            ),
        )

    async def resume_message_v2(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        thread_id: str,
        user_message: str,
        dynamic_tools: list[DynamicToolSpec] | None,
    ) -> Any:
        return self._with_client(
            "resume-message-v2",
            endpoint,
            config_overrides,
            lambda client: resume_message_v2(
                client,
                thread_id,
                user_message,
                dynamic_tools=dynamic_tools,
            ),
        )

    async def thread_resume_follow(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        thread_id: str,
    ) -> Any:
        return self._with_client(
            "thread-resume",
            endpoint,
            config_overrides,
            lambda client: thread_resume_follow(client, thread_id),
        )

    async def watch(self, *, endpoint: Endpoint, config_overrides: list[str]) -> Any:
        return self._with_client("watch", endpoint, config_overrides, watch)

    async def trigger_cmd_approval(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        user_message: str | None,
        dynamic_tools: list[DynamicToolSpec] | None,
    ) -> Any:
        return self._with_client(
            "trigger-cmd-approval",
            endpoint,
            config_overrides,
            lambda client: trigger_cmd_approval(
                client,
                user_message,
                dynamic_tools=dynamic_tools,
            ),
        )

    async def trigger_patch_approval(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        user_message: str | None,
        dynamic_tools: list[DynamicToolSpec] | None,
    ) -> Any:
        return self._with_client(
            "trigger-patch-approval",
            endpoint,
            config_overrides,
            lambda client: trigger_patch_approval(
                client,
                user_message,
                dynamic_tools=dynamic_tools,
            ),
        )

    async def no_trigger_cmd_approval(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        dynamic_tools: list[DynamicToolSpec] | None,
    ) -> Any:
        return self._with_client(
            "no-trigger-cmd-approval",
            endpoint,
            config_overrides,
            lambda client: no_trigger_cmd_approval(
                client,
                dynamic_tools=dynamic_tools,
            ),
        )

    async def send_follow_up_v2(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        first_message: str,
        follow_up_message: str,
        dynamic_tools: list[DynamicToolSpec] | None,
    ) -> Any:
        return self._with_client(
            "send-follow-up-v2",
            endpoint,
            config_overrides,
            lambda client: send_follow_up_v2(
                client,
                first_message,
                follow_up_message,
                dynamic_tools=dynamic_tools,
            ),
        )

    async def trigger_zsh_fork_multi_cmd_approval(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        user_message: str | None,
        min_approvals: int,
        abort_on: int | None,
        dynamic_tools: list[DynamicToolSpec] | None,
    ) -> Any:
        return self._with_client(
            "trigger-zsh-fork-multi-cmd-approval",
            endpoint,
            config_overrides,
            lambda client: trigger_zsh_fork_multi_cmd_approval(
                client,
                user_message,
                min_approvals=min_approvals,
                abort_on=abort_on,
                dynamic_tools=dynamic_tools,
            ),
        )

    async def test_login(
        self,
        *,
        endpoint: Endpoint,
        config_overrides: list[str],
        device_code: bool,
    ) -> Any:
        return self._with_client(
            "test-login",
            endpoint,
            config_overrides,
            lambda client: test_login(
                client,
                device_code=device_code,
            ),
        )

    async def get_account_rate_limits(
        self, *, endpoint: Endpoint, config_overrides: list[str]
    ) -> Any:
        return self._with_client(
            "get-account-rate-limits",
            endpoint,
            config_overrides,
            get_account_rate_limits,
        )

    async def model_list(self, *, endpoint: Endpoint, config_overrides: list[str]) -> Any:
        return self._with_client("model-list", endpoint, config_overrides, model_list)

    async def thread_list(
        self, *, endpoint: Endpoint, config_overrides: list[str], limit: int
    ) -> Any:
        return self._with_client(
            "thread-list",
            endpoint,
            config_overrides,
            lambda client: thread_list(client, limit=limit),
        )

    async def thread_increment_elicitation(self, *, url: str, thread_id: str) -> Any:
        return thread_increment_elicitation(self._client(ConnectWs(url), []), thread_id)

    async def thread_decrement_elicitation(self, *, url: str, thread_id: str) -> Any:
        return thread_decrement_elicitation(self._client(ConnectWs(url), []), thread_id)

    async def serve(
        self,
        *,
        codex_bin: Path,
        config_overrides: list[str],
        listen: str,
        kill: bool,
    ) -> Any:
        return self.serve_factory(
            codex_bin,
            config_overrides,
            listen=listen,
            kill=kill,
        )

    async def live_elicitation_timeout_pause(
        self,
        *,
        codex_bin: Path | None,
        url: str | None,
        config_overrides: list[str],
        model: str,
        workspace: Path,
        script: Path | None,
        hold_seconds: int,
    ) -> Any:
        return live_elicitation_timeout_pause(
            codex_bin=codex_bin,
            url=url,
            config_overrides=config_overrides,
            model=model,
            workspace=workspace,
            script=script,
            hold_seconds=hold_seconds,
            client_factory=self.client_factory,
        )


async def send_message_v2(
    codex_bin: str | Path,
    config_overrides: list[str],
    user_message: str,
    dynamic_tools: list[DynamicToolSpec] | None,
    *,
    runner: ClientRunner | None = None,
) -> Any:
    endpoint = SpawnCodex(Path(codex_bin))
    if runner is None:
        runner = DefaultClientRunner()
    return await runner.send_message_v2_endpoint(
        endpoint=endpoint,
        config_overrides=list(config_overrides),
        user_message=user_message,
        experimental_api=True,
        dynamic_tools=dynamic_tools,
    )


async def run(argv: list[str] | None = None, *, runner: ClientRunner | None = None) -> Any:
    parser = argparse.ArgumentParser(prog="codex-app-server-test-client")
    parser.add_argument("--codex-bin")
    parser.add_argument("--url")
    parser.add_argument("-c", "--config", action="append", default=[])
    parser.add_argument("--dynamic-tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve")
    serve.add_argument("--listen", default=DEFAULT_WEBSOCKET_URL)
    serve.add_argument("--kill", action="store_true")
    send = subparsers.add_parser("send-message")
    send.add_argument("user_message")
    subparsers.add_parser("model-list")
    resume_v2 = subparsers.add_parser("resume-message-v2")
    resume_v2.add_argument("thread_id")
    resume_v2.add_argument("user_message")
    thread_resume = subparsers.add_parser("thread-resume")
    thread_resume.add_argument("thread_id")
    send_v2 = subparsers.add_parser("send-message-v2")
    send_v2.add_argument("--experimental-api", action="store_true")
    send_v2.add_argument("user_message")
    trigger_cmd = subparsers.add_parser("trigger-cmd-approval")
    trigger_cmd.add_argument("user_message", nargs="?")
    trigger_patch = subparsers.add_parser("trigger-patch-approval")
    trigger_patch.add_argument("user_message", nargs="?")
    subparsers.add_parser("no-trigger-cmd-approval")
    follow_up = subparsers.add_parser("send-follow-up-v2")
    follow_up.add_argument("first_message")
    follow_up.add_argument("follow_up_message")
    zsh_fork = subparsers.add_parser("trigger-zsh-fork-multi-cmd-approval")
    zsh_fork.add_argument("user_message", nargs="?")
    zsh_fork.add_argument("--min-approvals", type=int, default=2)
    zsh_fork.add_argument("--abort-on", type=int)
    test_login = subparsers.add_parser("test-login")
    test_login.add_argument("--device-code", action="store_true")
    subparsers.add_parser("get-account-rate-limits")
    thread_list_parser = subparsers.add_parser("thread-list")
    thread_list_parser.add_argument("--limit", type=int, default=20)
    thread_increment = subparsers.add_parser("thread-increment-elicitation")
    thread_increment.add_argument("thread_id")
    thread_decrement = subparsers.add_parser("thread-decrement-elicitation")
    thread_decrement.add_argument("thread_id")
    live = subparsers.add_parser("live-elicitation-timeout-pause")
    live.add_argument("--model", default="gpt-5")
    live.add_argument("--workspace", default=".")
    live.add_argument("--script")
    live.add_argument("--hold-seconds", type=int, default=15)
    watch = subparsers.add_parser("watch")
    watch.set_defaults(command="watch")
    args = parser.parse_args(argv)
    dynamic_tools = parse_dynamic_tools_arg(args.dynamic_tools)
    if runner is None:
        runner = DefaultClientRunner()

    if args.command == "send-message-v2":
        if dynamic_tools is not None and not args.experimental_api:
            raise AppServerTestClientError(
                "--dynamic-tools requires --experimental-api for send-message-v2"
            )
        endpoint = resolve_endpoint(args.codex_bin, args.url)
        return await runner.send_message_v2_endpoint(
            endpoint=endpoint,
            config_overrides=args.config,
            user_message=args.user_message,
            experimental_api=args.experimental_api,
            dynamic_tools=dynamic_tools,
        )

    if args.command == "serve":
        ensure_dynamic_tools_unused(dynamic_tools, "serve")
        return await _call_runner(
            runner,
            "serve",
            codex_bin=Path(args.codex_bin or "codex"),
            config_overrides=args.config,
            listen=args.listen,
            kill=args.kill,
        )
    if args.command == "thread-increment-elicitation":
        ensure_dynamic_tools_unused(dynamic_tools, args.command)
        return await _call_runner(
            runner,
            "thread_increment_elicitation",
            url=resolve_shared_websocket_url(args.codex_bin, args.url, args.command),
            thread_id=args.thread_id,
        )
    if args.command == "thread-decrement-elicitation":
        ensure_dynamic_tools_unused(dynamic_tools, args.command)
        return await _call_runner(
            runner,
            "thread_decrement_elicitation",
            url=resolve_shared_websocket_url(args.codex_bin, args.url, args.command),
            thread_id=args.thread_id,
        )
    if args.command == "live-elicitation-timeout-pause":
        ensure_dynamic_tools_unused(dynamic_tools, args.command)
        return await _call_runner(
            runner,
            "live_elicitation_timeout_pause",
            codex_bin=Path(args.codex_bin) if args.codex_bin is not None else None,
            url=args.url,
            config_overrides=args.config,
            model=args.model,
            workspace=Path(args.workspace),
            script=Path(args.script) if args.script is not None else None,
            hold_seconds=args.hold_seconds,
        )

    endpoint = resolve_endpoint(args.codex_bin, args.url)
    if args.command in {
        "send-message",
        "thread-resume",
        "watch",
        "test-login",
        "get-account-rate-limits",
        "model-list",
        "thread-list",
    }:
        ensure_dynamic_tools_unused(dynamic_tools, args.command)

    if args.command == "send-message":
        return await _call_runner(
            runner,
            "send_message",
            endpoint=endpoint,
            config_overrides=args.config,
            user_message=args.user_message,
        )
    if args.command == "resume-message-v2":
        return await _call_runner(
            runner,
            "resume_message_v2",
            endpoint=endpoint,
            config_overrides=args.config,
            thread_id=args.thread_id,
            user_message=args.user_message,
            dynamic_tools=dynamic_tools,
        )
    if args.command == "thread-resume":
        return await _call_runner(
            runner,
            "thread_resume_follow",
            endpoint=endpoint,
            config_overrides=args.config,
            thread_id=args.thread_id,
        )
    if args.command == "watch":
        return await _call_runner(runner, "watch", endpoint=endpoint, config_overrides=args.config)
    if args.command == "trigger-cmd-approval":
        return await _call_runner(
            runner,
            "trigger_cmd_approval",
            endpoint=endpoint,
            config_overrides=args.config,
            user_message=args.user_message,
            dynamic_tools=dynamic_tools,
        )
    if args.command == "trigger-patch-approval":
        return await _call_runner(
            runner,
            "trigger_patch_approval",
            endpoint=endpoint,
            config_overrides=args.config,
            user_message=args.user_message,
            dynamic_tools=dynamic_tools,
        )
    if args.command == "no-trigger-cmd-approval":
        return await _call_runner(
            runner,
            "no_trigger_cmd_approval",
            endpoint=endpoint,
            config_overrides=args.config,
            dynamic_tools=dynamic_tools,
        )
    if args.command == "send-follow-up-v2":
        return await _call_runner(
            runner,
            "send_follow_up_v2",
            endpoint=endpoint,
            config_overrides=args.config,
            first_message=args.first_message,
            follow_up_message=args.follow_up_message,
            dynamic_tools=dynamic_tools,
        )
    if args.command == "trigger-zsh-fork-multi-cmd-approval":
        return await _call_runner(
            runner,
            "trigger_zsh_fork_multi_cmd_approval",
            endpoint=endpoint,
            config_overrides=args.config,
            user_message=args.user_message,
            min_approvals=args.min_approvals,
            abort_on=args.abort_on,
            dynamic_tools=dynamic_tools,
        )
    if args.command == "test-login":
        return await _call_runner(
            runner,
            "test_login",
            endpoint=endpoint,
            config_overrides=args.config,
            device_code=args.device_code,
        )
    if args.command == "get-account-rate-limits":
        return await _call_runner(
            runner, "get_account_rate_limits", endpoint=endpoint, config_overrides=args.config
        )
    if args.command == "model-list":
        return await _call_runner(runner, "model_list", endpoint=endpoint, config_overrides=args.config)
    if args.command == "thread-list":
        return await _call_runner(
            runner,
            "thread_list",
            endpoint=endpoint,
            config_overrides=args.config,
            limit=args.limit,
        )

    raise AppServerTestClientError(f"unsupported command: {args.command}")


async def _call_runner(runner: ClientRunner, method_name: str, **kwargs: Any) -> Any:
    method = getattr(runner, method_name)
    result = method(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


__all__ = [
    "AppServerTestClientError",
    "BackgroundAppServer",
    "CodexClient",
    "CommandApprovalBehavior",
    "ConnectWs",
    "DEFAULT_ANALYTICS_ENABLED",
    "DEFAULT_WEBSOCKET_URL",
    "DefaultClientRunner",
    "DynamicToolSpec",
    "Endpoint",
    "JSONRPCError",
    "JSONRPCNotification",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "MemoryTransport",
    "NO_TRIGGER_CMD_APPROVAL_PROMPT",
    "NOTIFICATIONS_TO_OPT_OUT",
    "ON_REQUEST_APPROVAL_POLICY",
    "OTEL_SERVICE_NAME",
    "SpawnCodex",
    "StdioTransport",
    "TRACE_DISABLED_MESSAGE",
    "TRIGGER_CMD_APPROVAL_PROMPT",
    "TRIGGER_PATCH_APPROVAL_PROMPT",
    "TRIGGER_ZSH_FORK_MULTI_CMD_APPROVAL_PROMPT",
    "TestClientTracing",
    "WebSocketTransport",
    "current_span_w3c_trace_context",
    "danger_full_access_sandbox_policy",
    "default_live_elicitation_script_path",
    "dynamic_tool_spec_to_json",
    "ensure_dynamic_tools_unused",
    "get_account_rate_limits",
    "item_started_before_helper_done_is_unexpected",
    "kill_listeners_on_same_port",
    "live_elicitation_timeout_pause",
    "model_list",
    "model_list_params",
    "no_trigger_cmd_approval",
    "parse_dynamic_tools_arg",
    "print_multiline_with_prefix",
    "print_trace_summary",
    "resume_message_v2",
    "resolve_endpoint",
    "resolve_shared_websocket_url",
    "run",
    "serve",
    "serve_command_line",
    "send_follow_up_v2",
    "send_message_v2",
    "send_message_v2_with_policies",
    "shell_quote",
    "test_login",
    "thread_decrement_elicitation",
    "thread_elicitation_params",
    "thread_increment_elicitation",
    "thread_list",
    "thread_list_params",
    "thread_resume_follow",
    "thread_start_params",
    "read_only_sandbox_policy",
    "text_user_input",
    "trace_url_from_context",
    "trace_summary_capture",
    "trigger_cmd_approval",
    "trigger_patch_approval",
    "trigger_zsh_fork_multi_cmd_approval",
    "turn_start_params",
    "watch",
    "with_client",
]
