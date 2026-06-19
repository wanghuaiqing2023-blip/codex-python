"""App-server process client for Rust ``codex-debug-client/src/client.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import json
import subprocess
from typing import Any, TextIO

from .output import Output
from .reader import (
    COMMAND_APPROVAL_METHOD,
    DECLINE,
    FILE_CHANGE_APPROVAL_METHOD,
    start_reader as spawn_reader,
)
from .state import PendingRequest, State


class AppServerClient:
    def __init__(
        self,
        *,
        child: Any | None = None,
        stdin: TextIO | None = None,
        stdout: Iterable[str] | None = None,
        output: Output | None = None,
        filtered_output: bool = False,
    ) -> None:
        self.child = child
        self.stdin = stdin
        self.stdout = stdout
        self.next_request_id_value = 1
        self.state = State()
        self.output = output if output is not None else Output.new()
        self.filtered_output = filtered_output

    @classmethod
    def spawn(
        cls,
        codex_bin: str,
        config_overrides: Sequence[str] = (),
        output: Output | None = None,
        filtered_output: bool = False,
    ) -> "AppServerClient":
        command = [codex_bin]
        for override in config_overrides:
            command.extend(["--config", str(override)])
        command.append("app-server")

        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        if child.stdin is None:
            raise RuntimeError("codex app-server stdin unavailable")
        if child.stdout is None:
            raise RuntimeError("codex app-server stdout unavailable")
        return cls(
            child=child,
            stdin=child.stdin,
            stdout=child.stdout,
            output=output,
            filtered_output=filtered_output,
        )

    def initialize(self) -> None:
        request_id = self.next_request_id()
        self.send(
            {
                "method": "initialize",
                "id": request_id,
                "params": {
                    "clientInfo": {
                        "name": "debug-client",
                        "title": "Debug Client",
                        "version": "0.0.0",
                    },
                    "capabilities": {
                        "experimentalApi": True,
                        "requestAttestation": False,
                        "optOutNotificationMethods": None,
                    },
                },
            }
        )
        response = self.read_until_response(request_id)
        if not isinstance(response.get("result"), Mapping):
            raise ValueError("decode initialize response")
        self.send({"method": "initialized"})

    def start_thread(self, params: Mapping[str, Any]) -> str:
        request_id = self.next_request_id()
        self.send({"method": "thread/start", "id": request_id, "params": dict(params)})
        response = self.read_until_response(request_id)
        thread_id = _thread_id_from_response(response, "decode thread/start response")
        self.set_thread_id(thread_id)
        return thread_id

    def resume_thread(self, params: Mapping[str, Any]) -> str:
        request_id = self.next_request_id()
        self.send({"method": "thread/resume", "id": request_id, "params": dict(params)})
        response = self.read_until_response(request_id)
        thread_id = _thread_id_from_response(response, "decode thread/resume response")
        self.set_thread_id(thread_id)
        return thread_id

    def request_thread_start(self, params: Mapping[str, Any]) -> int:
        request_id = self.next_request_id()
        self.track_pending(request_id, PendingRequest.START)
        self.send({"method": "thread/start", "id": request_id, "params": dict(params)})
        return request_id

    def request_thread_resume(self, params: Mapping[str, Any]) -> int:
        request_id = self.next_request_id()
        self.track_pending(request_id, PendingRequest.RESUME)
        self.send({"method": "thread/resume", "id": request_id, "params": dict(params)})
        return request_id

    def request_thread_list(self, cursor: str | None = None) -> int:
        request_id = self.next_request_id()
        self.track_pending(request_id, PendingRequest.LIST)
        self.send(
            {
                "method": "thread/list",
                "id": request_id,
                "params": {
                    "cursor": cursor,
                    "limit": None,
                    "sortKey": None,
                    "sortDirection": None,
                    "modelProviders": None,
                    "sourceKinds": None,
                    "archived": None,
                    "cwd": None,
                    "useStateDbOnly": False,
                    "searchTerm": None,
                },
            }
        )
        return request_id

    def send_turn(self, thread_id: str, text: str) -> int:
        request_id = self.next_request_id()
        self.send(
            {
                "method": "turn/start",
                "id": request_id,
                "params": {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": text, "textElements": []}],
                },
            }
        )
        return request_id

    def start_reader(self, events: Any, auto_approve: bool, filtered_output: bool) -> None:
        if self.stdout is None:
            raise RuntimeError("reader already started")
        stdout = self.stdout
        self.stdout = None
        spawn_reader(
            stdout,
            self.stdin,
            self.state,
            events,
            self.output,
            auto_approve=auto_approve,
            filtered_output=filtered_output,
        )

    def thread_id(self) -> str | None:
        return self.state.thread_id

    def set_thread_id(self, thread_id: str) -> None:
        self.state.thread_id = str(thread_id)
        self._remember_thread()

    def use_thread(self, thread_id: str) -> bool:
        known = str(thread_id) in self.state.known_threads
        self.state.thread_id = str(thread_id)
        self._remember_thread()
        return known

    def shutdown(self) -> None:
        self.stdin = None
        if self.child is not None and hasattr(self.child, "wait"):
            self.child.wait()

    def track_pending(self, request_id: int | str, kind: PendingRequest) -> None:
        self.state.pending[str(request_id)] = kind

    def next_request_id(self) -> int:
        request_id = self.next_request_id_value
        self.next_request_id_value += 1
        return request_id

    def send(self, value: Mapping[str, Any]) -> None:
        send_with_stdin(self.stdin, value)

    def read_until_response(self, request_id: int | str) -> dict[str, Any]:
        if self.stdout is None:
            raise RuntimeError("stdout missing")
        target_id = request_id

        for raw_line in self.stdout:
            line = str(raw_line).rstrip("\r\n")
            if line:
                self.output.server_json_line(line, self.filtered_output)
            try:
                message = json.loads(line)
            except (TypeError, ValueError):
                continue
            if not isinstance(message, Mapping):
                continue
            if message.get("id") == target_id and "result" in message:
                return dict(message)
            if "method" in message and "id" in message:
                handle_server_request(message, self.stdin)

        raise EOFError(f"server closed stdout while awaiting response {request_id!r}")

    def _remember_thread(self) -> None:
        if self.state.thread_id is not None and self.state.thread_id not in self.state.known_threads:
            self.state.known_threads.append(self.state.thread_id)


def handle_server_request(request: Mapping[str, Any], stdin: TextIO | None) -> None:
    method = request.get("method")
    request_id = request.get("id")
    if method == COMMAND_APPROVAL_METHOD:
        send_jsonrpc_response(stdin, request_id, {"decision": {"type": DECLINE}})
    elif method == FILE_CHANGE_APPROVAL_METHOD:
        send_jsonrpc_response(stdin, request_id, {"decision": DECLINE})


def send_jsonrpc_response(stdin: TextIO | None, request_id: Any, response: Mapping[str, Any]) -> None:
    send_with_stdin(stdin, {"id": request_id, "result": dict(response)})


def send_with_stdin(stdin: TextIO | None, value: Mapping[str, Any]) -> None:
    if stdin is None:
        raise RuntimeError("stdin already closed")
    stdin.write(json.dumps(dict(value), separators=(",", ":"), ensure_ascii=False))
    stdin.write("\n")
    stdin.flush()


def build_thread_start_params(
    approval_policy: Any,
    model: str | None = None,
    model_provider: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "modelProvider": model_provider,
        "cwd": cwd,
        "approvalPolicy": _approval_policy_value(approval_policy),
        "experimentalRawEvents": False,
    }


def build_thread_resume_params(
    thread_id: str,
    approval_policy: Any,
    model: str | None = None,
    model_provider: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "model": model,
        "modelProvider": model_provider,
        "cwd": cwd,
        "approvalPolicy": _approval_policy_value(approval_policy),
    }


def _approval_policy_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _thread_id_from_response(response: Mapping[str, Any], error_context: str) -> str:
    result = response.get("result")
    if not isinstance(result, Mapping):
        raise ValueError(error_context)
    thread = result.get("thread")
    if not isinstance(thread, Mapping):
        raise ValueError(error_context)
    thread_id = thread.get("id")
    if thread_id is None:
        raise ValueError(error_context)
    return str(thread_id)


__all__ = [
    "AppServerClient",
    "build_thread_resume_params",
    "build_thread_start_params",
    "handle_server_request",
    "send_jsonrpc_response",
    "send_with_stdin",
]
