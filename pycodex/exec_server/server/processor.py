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


class ConnectionProcessor:
    def __init__(
        self,
        runtime_paths: "ExecServerRuntimePaths",
        session_registry: "SessionRegistry | None" = None,
        router: RpcRouter | None = None,
    ) -> None:
        self.session_registry = session_registry or SessionRegistry.new()
        self.runtime_paths = runtime_paths
        self.router = router or build_router()

    @classmethod
    def new(cls, runtime_paths: "ExecServerRuntimePaths") -> "ConnectionProcessor":
        return cls(runtime_paths)

    async def run_stdio(self, reader: Any, writer: Any) -> None:
        await self.run_connection(JsonRpcConnection.from_stdio(reader, writer, "exec-server stdio"))

    async def run_connection(self, connection: JsonRpcConnection) -> None:
        outgoing_tx: asyncio.Queue[RpcServerOutboundMessage] = asyncio.Queue()
        notifications = RpcNotificationSender.new(outgoing_tx)
        handler = ExecServerHandler.new(self.session_registry, notifications, self.runtime_paths)
        try:
            while handler.is_session_attached():
                event = await connection.incoming_rx.get()
                if event.kind == "disconnected":
                    break
                if event.kind == "malformed":
                    await connection.outgoing_tx.put(
                        encode_server_message(
                            RpcServerOutboundMessage.error_message(
                                RequestId.integer(-1),
                                invalid_request(event.reason or "malformed JSON-RPC message"),
                            )
                        )
                    )
                    await _drain_outbound_connection(connection.outgoing_tx, outgoing_tx)
                    continue
                if event.message is None:
                    break
                should_continue = await _process_server_connection_message(
                    handler,
                    self.router,
                    event.message,
                    connection.outgoing_tx,
                    connection.disconnected,
                )
                await _drain_outbound_connection(connection.outgoing_tx, outgoing_tx)
                if not should_continue:
                    break
        finally:
            await handler.shutdown()
            try:
                await asyncio.wait_for(connection.outgoing_tx.join(), timeout=0.1)
            except TimeoutError:
                pass
            await connection.close()


async def _process_server_connection_message(
    handler: "ExecServerHandler",
    router: RpcRouter,
    message: JSONRPCMessage,
    outgoing_tx: "asyncio.Queue[JSONRPCMessage]",
    disconnected: asyncio.Event | None = None,
) -> bool:
    value = message.value
    if isinstance(value, JSONRPCRequest):
        route = router.request_route(value.method)
        if route is None:
            outbound = RpcServerOutboundMessage.error_message(
                value.id,
                method_not_found(f"exec-server stub does not implement `{value.method}` yet"),
            )
        else:
            outbound = await _run_server_route_until_disconnect(route(handler, value), disconnected)
            if outbound is _SERVER_ROUTE_DISCONNECTED:
                return False
        if outbound is not None:
            await outgoing_tx.put(encode_server_message(outbound))
        return True
    if isinstance(value, JSONRPCNotification):
        route = router.notification_route(value.method)
        if route is None:
            return False
        result = await _run_server_route_until_disconnect(route(handler, value), disconnected)
        if result is _SERVER_ROUTE_DISCONNECTED:
            return False
        return result is None
    return False


_SERVER_ROUTE_DISCONNECTED = object()


from pycodex.exec_server.connection import JsonRpcConnection, _drain_outbound_connection, _run_server_route_until_disconnect
from pycodex.exec_server.rpc import RpcNotificationSender, RpcRouter, RpcServerOutboundMessage, encode_server_message
from pycodex.exec_server.server.handler import ExecServerHandler
from pycodex.exec_server.server.registry import build_router
from pycodex.exec_server.server.session_registry import SessionRegistry
