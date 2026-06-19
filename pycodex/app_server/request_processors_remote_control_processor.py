"""Remote-control request processor projection.

Ported from ``codex-app-server/src/request_processors/remote_control_processor.rs``.
The Rust module is a small facade over an optional ``RemoteControlHandle``:
missing handles are internal errors, enable unavailability is mapped to
invalid-request, and successful handle status snapshots are projected into the
remote-control response payloads.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    RemoteControlDisableResponse,
    RemoteControlEnableResponse,
    RemoteControlStatusReadResponse,
)

JsonValue = Any


class RemoteControlRequestProcessorError(Exception):
    """Exception wrapper carrying Rust's JSON-RPC error payload."""

    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


class RemoteControlRequestProcessor:
    def __init__(self, remote_control_handle: Any | None) -> None:
        self.remote_control_handle = remote_control_handle

    @classmethod
    def new(cls, remote_control_handle: Any | None) -> "RemoteControlRequestProcessor":
        return cls(remote_control_handle)

    def enable(self) -> RemoteControlEnableResponse:
        handle = self._handle()
        try:
            status = handle.enable()
        except Exception as exc:
            raise RemoteControlRequestProcessorError(invalid_request(str(exc))) from exc
        return _enable_response(status)

    def disable(self) -> RemoteControlDisableResponse:
        return _disable_response(self._handle().disable())

    def status_read(self) -> RemoteControlStatusReadResponse:
        status = self._handle().status()
        return _status_read_response(status)

    def _handle(self) -> Any:
        if self.remote_control_handle is None:
            raise RemoteControlRequestProcessorError(
                internal_error("remote control is unavailable for this app-server")
            )
        return self.remote_control_handle


def _enable_response(value: Any) -> RemoteControlEnableResponse:
    if isinstance(value, RemoteControlEnableResponse):
        return value
    return RemoteControlEnableResponse(**_remote_control_kwargs(value))


def _disable_response(value: Any) -> RemoteControlDisableResponse:
    if isinstance(value, RemoteControlDisableResponse):
        return value
    return RemoteControlDisableResponse(**_remote_control_kwargs(value))


def _status_read_response(value: Any) -> RemoteControlStatusReadResponse:
    if isinstance(value, RemoteControlStatusReadResponse):
        return value
    return RemoteControlStatusReadResponse(**_remote_control_kwargs(value))


def _remote_control_kwargs(value: Any) -> dict[str, JsonValue]:
    if isinstance(value, Mapping):
        return {
            "status": _field(value, "status"),
            "server_name": _field(value, "server_name", "serverName"),
            "installation_id": _field(value, "installation_id", "installationId"),
            "environment_id": _field(value, "environment_id", "environmentId", default=None),
        }
    return {
        "status": getattr(value, "status"),
        "server_name": getattr(value, "server_name"),
        "installation_id": getattr(value, "installation_id"),
        "environment_id": getattr(value, "environment_id", None),
    }


def _field(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


__all__ = [
    "RemoteControlRequestProcessor",
    "RemoteControlRequestProcessorError",
]
