"""Python interface for Rust ``codex-exec-server``."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
import binascii
import errno
import hashlib
from functools import total_ordering
import inspect
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import struct
import sys
import time
import tomllib
from typing import Any
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pycodex.app_server.error_code import internal_error, invalid_params, invalid_request, method_not_found
from pycodex.app_server_protocol.jsonrpc_lite import (
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    PermissionProfile,
    RequestId,
    WindowsSandboxLevel,
)
from pycodex.sandboxing import (
    SandboxCommand,
    SandboxManager,
    SandboxTransformRequest,
    SandboxablePreference,
)
from pycodex.protocol.shell_environment import create_env as create_shell_env
from pycodex.utils.absolute_path import AbsolutePathBuf



from pycodex.file_system import (
    CopyOptions,
    CreateDirectoryOptions,
    ExecutorFileSystem,
    FileMetadata,
    FileSystemSandboxContext,
    ReadDirectoryEntry,
    RemoveOptions,
)
from pycodex.file_system import FileSystemResult


class RpcCallError(Exception):
    kind: str

    @classmethod
    def closed(cls) -> "RpcCallError":
        return cls("closed")

    @classmethod
    def json(cls, message: Any) -> "RpcCallError":
        return cls("json", str(message))

    @classmethod
    def server(cls, error: JSONRPCErrorError) -> "RpcCallError":
        err = cls("server", error.message)
        err.error = error
        return err

    def __init__(self, kind: str, message: str | None = None) -> None:
        self.kind = kind
        self.message = message
        super().__init__(message or kind)


@dataclass(frozen=True)
class RpcClientEvent:
    kind: str
    notification: JSONRPCNotification | None = None
    reason: str | None = None

    @classmethod
    def notification_event(cls, notification: JSONRPCNotification) -> "RpcClientEvent":
        return cls("notification", notification=notification)

    @classmethod
    def disconnected(cls, reason: str | None = None) -> "RpcClientEvent":
        return cls("disconnected", reason=reason)


@dataclass(frozen=True)
class RpcServerOutboundMessage:
    kind: str
    request_id: RequestId | str | int | None = None
    result: Any | None = None
    error: JSONRPCErrorError | None = None
    notification: JSONRPCNotification | None = None

    @classmethod
    def response(cls, request_id: RequestId | str | int, result: Any) -> "RpcServerOutboundMessage":
        return cls("response", request_id=RequestId.from_value(request_id), result=result)

    @classmethod
    def error_message(
        cls,
        request_id: RequestId | str | int,
        error: JSONRPCErrorError,
    ) -> "RpcServerOutboundMessage":
        return cls("error", request_id=RequestId.from_value(request_id), error=error)

    @classmethod
    def notification_message(cls, notification: JSONRPCNotification) -> "RpcServerOutboundMessage":
        return cls("notification", notification=notification)


def encode_server_message(message: RpcServerOutboundMessage) -> JSONRPCMessage:
    if message.kind == "response":
        if message.request_id is None:
            raise ValueError("response requires request_id")
        return JSONRPCMessage(JSONRPCResponse(id=message.request_id, result=message.result))
    if message.kind == "error":
        if message.request_id is None or message.error is None:
            raise ValueError("error requires request_id and error")
        return JSONRPCMessage(JSONRPCError(id=message.request_id, error=message.error))
    if message.kind == "notification":
        if message.notification is None:
            raise ValueError("notification requires notification")
        return JSONRPCMessage(message.notification)
    raise ValueError(f"unknown RPC outbound message kind: {message.kind}")


class RpcNotificationSender:
    def __init__(self, outgoing_tx: asyncio.Queue[RpcServerOutboundMessage]) -> None:
        self.outgoing_tx = outgoing_tx

    @classmethod
    def new(cls, outgoing_tx: asyncio.Queue[RpcServerOutboundMessage]) -> "RpcNotificationSender":
        return cls(outgoing_tx)

    async def response(self, request_id: RequestId | str | int, result: Any) -> None | JSONRPCErrorError:
        try:
            self.outgoing_tx.put_nowait(RpcServerOutboundMessage.response(request_id, result))
        except asyncio.QueueFull:
            return internal_error("RPC connection closed while sending response")
        return None

    async def notify(self, method: str, params: Any) -> None | JSONRPCErrorError:
        try:
            self.outgoing_tx.put_nowait(
                RpcServerOutboundMessage.notification_message(JSONRPCNotification(method=method, params=params))
            )
        except asyncio.QueueFull:
            return internal_error("RPC connection closed while sending notification")
        return None


class RpcRouter:
    def __init__(self) -> None:
        self.request_routes: dict[str, Any] = {}
        self.notification_routes: dict[str, Any] = {}

    @classmethod
    def new(cls) -> "RpcRouter":
        return cls()

    def request(self, method: str, handler: Any, decoder: Any | None = None, encoder: Any | None = None) -> None:
        async def route(state: Any, request: JSONRPCRequest) -> RpcServerOutboundMessage:
            params_or_error = decode_request_params(request.params, decoder)
            if isinstance(params_or_error, JSONRPCErrorError):
                return RpcServerOutboundMessage.error_message(request.id, params_or_error)
            try:
                result = await _maybe_await(handler(state, params_or_error))
            except Exception as exc:
                return RpcServerOutboundMessage.error_message(request.id, internal_error(exc))
            if isinstance(result, JSONRPCErrorError):
                return RpcServerOutboundMessage.error_message(request.id, result)
            if encoder is not None:
                try:
                    result = encoder(result)
                except Exception as exc:
                    return RpcServerOutboundMessage.error_message(request.id, internal_error(exc))
            return RpcServerOutboundMessage.response(request.id, result)

        self.request_routes[method] = route

    def request_with_id(self, method: str, handler: Any, decoder: Any | None = None) -> None:
        async def route(state: Any, request: JSONRPCRequest) -> RpcServerOutboundMessage | None:
            params_or_error = decode_request_params(request.params, decoder)
            if isinstance(params_or_error, JSONRPCErrorError):
                return RpcServerOutboundMessage.error_message(request.id, params_or_error)
            try:
                result = await _maybe_await(handler(state, request.id, params_or_error))
            except Exception as exc:
                return RpcServerOutboundMessage.error_message(request.id, internal_error(exc))
            if isinstance(result, JSONRPCErrorError):
                return RpcServerOutboundMessage.error_message(request.id, result)
            return None

        self.request_routes[method] = route

    def notification(self, method: str, handler: Any, decoder: Any | None = None) -> None:
        async def route(state: Any, notification: JSONRPCNotification) -> None | str:
            params_or_error = decode_notification_params(notification.params, decoder)
            if isinstance(params_or_error, str):
                return params_or_error
            try:
                result = await _maybe_await(handler(state, params_or_error))
            except Exception as exc:
                return str(exc)
            if isinstance(result, JSONRPCErrorError):
                return result.message
            if isinstance(result, str):
                return result
            return None

        self.notification_routes[method] = route

    def request_route(self, method: str) -> Any | None:
        return self.request_routes.get(method)

    def notification_route(self, method: str) -> Any | None:
        return self.notification_routes.get(method)


class RpcClient:
    def __init__(self, outgoing_tx: asyncio.Queue[JSONRPCMessage] | None = None) -> None:
        self.outgoing_tx = outgoing_tx or asyncio.Queue()
        self.events: asyncio.Queue[RpcClientEvent] = asyncio.Queue()
        self.pending: dict[RequestId, asyncio.Future[Any]] = {}
        self.next_request_id = 1
        self.disconnected = False

    @classmethod
    def new_for_tests(cls) -> "RpcClient":
        return cls()

    async def notify(self, method: str, params: Any) -> None:
        if self.disconnected:
            raise RpcCallError.closed()
        await self.outgoing_tx.put(JSONRPCMessage(JSONRPCNotification(method=method, params=params)))

    def is_disconnected(self) -> bool:
        return self.disconnected

    async def call(self, method: str, params: Any) -> Any:
        if self.disconnected:
            raise RpcCallError.closed()
        request_id = RequestId.integer(self.next_request_id)
        self.next_request_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self.pending[request_id] = future
        await self.outgoing_tx.put(
            JSONRPCMessage(JSONRPCRequest(id=request_id, method=method, params=params, trace=None))
        )
        try:
            return await future
        finally:
            self.pending.pop(request_id, None)

    async def receive_server_message(self, message: JSONRPCMessage) -> None:
        await handle_server_message(self.pending, self.events, message)

    async def disconnect(self, reason: str | None = None) -> None:
        self.disconnected = True
        await self.events.put(RpcClientEvent.disconnected(reason))
        await drain_pending(self.pending)

    def pending_request_count(self) -> int:
        return len(self.pending)


def not_found(message: Any) -> JSONRPCErrorError:
    return JSONRPCErrorError(code=-32004, message=str(message), data=None)


def decode_request_params(params: Any | None, decoder: Any | None = None) -> Any | JSONRPCErrorError:
    result = decode_params(params, decoder)
    if isinstance(result, Exception):
        return invalid_params(str(result))
    return result


def decode_notification_params(params: Any | None, decoder: Any | None = None) -> Any | str:
    result = decode_params(params, decoder)
    if isinstance(result, Exception):
        return str(result)
    return result


def decode_params(params: Any | None, decoder: Any | None = None) -> Any | Exception:
    decoder = decoder or (lambda value: value)
    value = None if params is None else params
    try:
        return decoder(value)
    except Exception as original_error:
        if value == {}:
            try:
                return decoder(None)
            except Exception:
                return original_error
        return original_error


async def handle_server_message(
    pending: dict[RequestId, asyncio.Future[Any]],
    event_tx: asyncio.Queue[RpcClientEvent],
    message: JSONRPCMessage,
) -> None:
    value = message.value
    if isinstance(value, JSONRPCResponse):
        future = pending.pop(value.id, None)
        if future is not None and not future.done():
            future.set_result(value.result)
        return
    if isinstance(value, JSONRPCError):
        future = pending.pop(value.id, None)
        if future is not None and not future.done():
            future.set_exception(RpcCallError.server(value.error))
        return
    if isinstance(value, JSONRPCNotification):
        await event_tx.put(RpcClientEvent.notification_event(value))
        return
    if isinstance(value, JSONRPCRequest):
        raise ValueError(f"unexpected JSON-RPC request from remote server: {value.method}")


async def drain_pending(pending: dict[RequestId, asyncio.Future[Any]]) -> None:
    futures = list(pending.values())
    pending.clear()
    for future in futures:
        if not future.done():
            future.set_exception(RpcCallError.closed())


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
