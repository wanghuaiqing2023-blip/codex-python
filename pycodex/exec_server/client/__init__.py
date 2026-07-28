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
from pycodex.exec_server.process import (
    ExecProcess,
    ExecProcessEvent,
    ExecProcessEventLog,
    ExecProcessEventReceiver,
)


class ExecServerError(Exception):
    def __init__(self, message: str, kind: str | None = None, **attrs: Any) -> None:
        self.message = message
        self.kind = kind
        for key, value in attrs.items():
            setattr(self, key, value)
        super().__init__(str(self))

    @classmethod
    def protocol(cls, message: str) -> "ExecServerError":
        return cls(message, "protocol")

    @classmethod
    def environment_registry_config(cls, message: str) -> "ExecServerError":
        return cls(message, "environment_registry_config")

    @classmethod
    def environment_registry_auth(cls, message: str) -> "ExecServerError":
        return cls(message, "environment_registry_auth")

    @classmethod
    def environment_registry_http(
        cls,
        status: int,
        code: str | None,
        message: str,
    ) -> "ExecServerError":
        return cls(message, "environment_registry_http", status=status, code=code)

    @classmethod
    def http_request(cls, message: str) -> "ExecServerError":
        return cls(message, "http_request")

    @classmethod
    def websocket_connect_timeout(cls, url: str, timeout: int | float) -> "ExecServerError":
        timeout_display = _rust_duration_debug(timeout)
        return cls(
            f"timed out connecting to exec-server websocket `{url}` after {timeout_display}",
            "websocket_connect_timeout",
            url=url,
            timeout=timeout,
        )

    @classmethod
    def websocket_connect(cls, url: str, source: BaseException) -> "ExecServerError":
        return cls(
            f"failed to connect to exec-server websocket `{url}`: {source}",
            "websocket_connect",
            url=url,
            source=source,
        )

    def __str__(self) -> str:
        if self.kind == "protocol":
            return f"exec-server protocol error: {self.message}"
        return self.message


PROCESS_EVENT_CHANNEL_CAPACITY = 256


PROCESS_EVENT_RETAINED_BYTES = 1024 * 1024


class ClientSessionState:
    def __init__(self) -> None:
        self.wake_queue: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
        self.wake_value = 0
        self.events = ExecProcessEventLog.new(PROCESS_EVENT_CHANNEL_CAPACITY, PROCESS_EVENT_RETAINED_BYTES)
        self.last_published_seq = 0
        self.pending_events: dict[int, ExecProcessEvent] = {}
        self.failure: str | None = None

    def subscribe_wake(self) -> asyncio.Queue[int]:
        return self.wake_queue

    def subscribe_events(self) -> ExecProcessEventReceiver:
        return self.events.subscribe()

    def note_change(self, seq: int) -> None:
        self.wake_value = max(self.wake_value, seq)
        _put_latest_nowait(self.wake_queue, self.wake_value)

    def publish_ordered_event(self, event: ExecProcessEvent) -> bool:
        seq = event.seq()
        if seq is None:
            self.events.publish(event)
            return False
        if seq <= self.last_published_seq:
            return False
        self.pending_events.setdefault(seq, event)
        ready: list[ExecProcessEvent] = []
        while True:
            next_seq = self.last_published_seq + 1
            next_event = self.pending_events.pop(next_seq, None)
            if next_event is None:
                break
            self.last_published_seq = next_seq
            ready.append(next_event)
        published_closed = False
        for ready_event in ready:
            published_closed = published_closed or ready_event.kind == "closed"
            self.events.publish(ready_event)
        return published_closed

    def set_failure(self, message: str) -> None:
        should_publish = self.failure is None
        if should_publish:
            self.failure = message
        self.wake_value += 1
        _put_latest_nowait(self.wake_queue, self.wake_value)
        if should_publish:
            self.publish_ordered_event(ExecProcessEvent.failed(message))

    def failed_response(self) -> ReadResponse | None:
        if self.failure is None:
            return None
        return self.synthesized_failure(self.failure)

    def synthesized_failure(self, message: str) -> ReadResponse:
        return ReadResponse(
            chunks=[],
            next_seq=self.wake_value + 1,
            exited=True,
            exit_code=None,
            closed=True,
            failure=message,
        )


class ClientSession(ExecProcess):
    def __init__(self, client: "ExecServerClient", process_id: ProcessId, state: ClientSessionState) -> None:
        self.client = client
        self._process_id = process_id
        self.state = state

    def process_id(self) -> ProcessId:
        return self._process_id

    def subscribe_wake(self) -> asyncio.Queue[int]:
        return self.state.subscribe_wake()

    def subscribe_events(self) -> ExecProcessEventReceiver:
        return self.state.subscribe_events()

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        failed = self.state.failed_response()
        if failed is not None:
            return failed
        return await self.client.read(ReadParams(self._process_id, after_seq, max_bytes, wait_ms))

    async def write(self, chunk: bytes) -> WriteResponse:
        return await self.client.write(self._process_id, chunk)

    async def terminate(self) -> None:
        await self.client.terminate(self._process_id)

    async def unregister(self) -> None:
        await self.client.unregister_session(self._process_id)


@dataclass
class LazyRemoteExecServerClient:
    transport_params: ExecServerTransportParams
    client: Any | None = None
    connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get(self) -> Any:
        client = self.connected_client()
        if client is not None:
            return client
        async with self.connect_lock:
            client = self.connected_client()
            if client is not None:
                return client
            cached_client = self.client
            if cached_client is not None and self.transport_params.kind is not ExecServerTransportKind.WEBSOCKET_URL:
                return cached_client
            next_client = await ExecServerClient.connect_for_transport(self.transport_params)
            self.client = next_client
            return next_client

    def cached_client(self) -> Any | None:
        return self.client

    def connected_client(self) -> Any | None:
        client = self.cached_client()
        if client is None:
            return None
        is_disconnected = getattr(client, "is_disconnected", None)
        if callable(is_disconnected) and is_disconnected():
            return None
        return client

    async def http_request(self, params: "HttpRequestParams") -> "HttpRequestResponse":
        return await (await self.get()).http_request(params)

    async def http_request_stream(
        self,
        params: "HttpRequestParams",
    ) -> tuple["HttpRequestResponse", "HttpResponseBodyStream"]:
        return await (await self.get()).http_request_stream(params)


class ExecServerClient:
    def __init__(
        self,
        connection: JsonRpcConnection,
        options: ExecServerClientConnectOptions,
        session_id: str | None = None,
        *,
        start_reader: bool = True,
    ) -> None:
        self.connection = connection
        self.options = options
        self._session_id = session_id
        self.sessions: dict[ProcessId, ClientSessionState] = {}
        self.http_body_streams: dict[str, asyncio.Queue[HttpRequestBodyDeltaNotification | None]] = {}
        self.http_body_stream_failures: dict[str, str] = {}
        self.http_body_stream_next_id = 1
        self.pending_calls: dict[RequestId, asyncio.Future[Any]] = {}
        self.next_request_id = 1
        self.disconnected_message: str | None = None
        self.reader_task: asyncio.Task[Any] | None = None
        if start_reader:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self.reader_task = None
            else:
                self.reader_task = loop.create_task(self._reader_loop())

    def session_id(self) -> str | None:
        return self._session_id

    def is_disconnected(self) -> bool:
        return self.disconnected_message is not None or self.connection.disconnected.is_set()

    async def register_session(self, process_id: ProcessId | str) -> ClientSession:
        process_id = ProcessId.new(process_id) if isinstance(process_id, str) else process_id
        if self.disconnected_message is not None:
            raise ExecServerError(self.disconnected_message, "disconnected")
        if process_id in self.sessions:
            raise ExecServerError.protocol(f"session already registered for process {process_id}")
        state = ClientSessionState()
        self.sessions[process_id] = state
        return ClientSession(self, process_id, state)

    async def unregister_session(self, process_id: ProcessId | str) -> None:
        process_id = ProcessId.new(process_id) if isinstance(process_id, str) else process_id
        self.sessions.pop(process_id, None)

    async def read(self, params: ReadParams) -> ReadResponse:
        result = await self.call(EXEC_READ_METHOD, encode_read_params(params))
        return decode_read_response(result)

    async def write(self, process_id: ProcessId, chunk: bytes) -> WriteResponse:
        params = WriteParams(process_id=process_id, chunk=ByteChunk(chunk))
        result = await self.call(EXEC_WRITE_METHOD, encode_write_params(params))
        return decode_write_response(result)

    async def terminate(self, process_id: ProcessId) -> TerminateResponse:
        result = await self.call(EXEC_TERMINATE_METHOD, encode_terminate_params(TerminateParams(process_id)))
        return decode_terminate_response(result)

    async def call(self, method: str, params: Any) -> Any:
        call_impl = getattr(self, "call_impl", None)
        if call_impl is not None:
            result = call_impl(method, params)
            if inspect.isawaitable(result):
                return await result
            return result
        if self.disconnected_message is not None or self.connection.disconnected.is_set():
            raise ExecServerError(self.disconnected_message or _disconnected_message(), "disconnected")
        request_id = RequestId.integer(self.next_request_id)
        self.next_request_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self.pending_calls[request_id] = future
        await self.connection.outgoing_tx.put(
            JSONRPCMessage(JSONRPCRequest(id=request_id, method=method, params=params, trace=None))
        )
        try:
            return await future
        except RpcCallError as exc:
            if exc.kind == "server":
                error = getattr(exc, "error")
                raise ExecServerError(
                    f"exec-server rejected request ({error.code}): {error.message}",
                    "server",
                    code=error.code,
                    server_message=error.message,
                ) from exc
            if exc.kind == "closed":
                message = _disconnected_message()
                self.disconnected_message = self.disconnected_message or message
                raise ExecServerError(self.disconnected_message, "disconnected") from exc
            raise ExecServerError(f"failed to serialize or deserialize exec-server JSON: {exc}", "json") from exc
        finally:
            self.pending_calls.pop(request_id, None)

    async def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
        params = replace(params, stream_response=False)
        return await self.call(HTTP_REQUEST_METHOD, params)

    async def http_request_stream(
        self,
        params: HttpRequestParams,
    ) -> tuple[HttpRequestResponse, HttpResponseBodyStream]:
        request_id = self.next_http_body_stream_request_id()
        params = replace(params, stream_response=True, request_id=request_id)
        queue: asyncio.Queue[HttpRequestBodyDeltaNotification | None] = asyncio.Queue(
            maxsize=HTTP_BODY_DELTA_CHANNEL_CAPACITY
        )
        await self.insert_http_body_stream(request_id, queue)
        try:
            response = await self.call(HTTP_REQUEST_METHOD, params)
        except Exception:
            await self.remove_http_body_stream(request_id)
            raise
        return response, HttpResponseBodyStream.remote(self, request_id, queue)

    def next_http_body_stream_request_id(self) -> str:
        request_id = f"http-{self.http_body_stream_next_id}"
        self.http_body_stream_next_id += 1
        return request_id

    async def insert_http_body_stream(
        self,
        request_id: str,
        queue: asyncio.Queue[HttpRequestBodyDeltaNotification | None],
    ) -> None:
        if request_id in self.http_body_streams:
            raise ExecServerError.protocol(f"http response stream already registered for request {request_id}")
        self.http_body_streams[request_id] = queue
        self.http_body_stream_failures.pop(request_id, None)

    async def remove_http_body_stream(
        self,
        request_id: str,
    ) -> asyncio.Queue[HttpRequestBodyDeltaNotification | None] | None:
        return self.http_body_streams.pop(request_id, None)

    def take_http_body_stream_failure(self, request_id: str) -> str | None:
        return self.http_body_stream_failures.pop(request_id, None)

    async def handle_http_body_delta_notification(self, params: Any) -> None:
        notification = decode_http_request_body_delta_notification(params)
        queue = self.http_body_streams.get(notification.request_id)
        if queue is None:
            return
        terminal_delta = notification.done or notification.error is not None
        try:
            queue.put_nowait(notification)
            if terminal_delta:
                await self.remove_http_body_stream(notification.request_id)
        except asyncio.QueueFull:
            self.http_body_stream_failures[
                notification.request_id
            ] = "body delta channel filled before delivery"
            await self.remove_http_body_stream(notification.request_id)
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def fail_all_http_body_streams(self, message: str) -> None:
        streams = list(self.http_body_streams.items())
        self.http_body_streams.clear()
        for request_id, queue in streams:
            delta = HttpRequestBodyDeltaNotification(
                request_id=request_id,
                seq=1,
                delta=ByteChunk(b""),
                done=True,
                error=message,
            )
            try:
                queue.put_nowait(delta)
            except asyncio.QueueFull:
                self.http_body_stream_failures[request_id] = message

    async def _reader_loop(self) -> None:
        while True:
            event = await self.connection.incoming_rx.get()
            if event.kind == "disconnected":
                message = _disconnected_message(event.reason)
                self._fail_all_sessions(message)
                self._fail_pending_calls(message)
                return
            if event.kind == "malformed":
                message = f"exec-server notification handling failed: {event.reason}"
                self._fail_all_sessions(message)
                self._fail_pending_calls(message)
                return
            if event.message is None:
                continue
            value = event.message.value
            if isinstance(value, JSONRPCNotification):
                try:
                    await self._handle_server_notification(value)
                except Exception as exc:
                    message = f"exec-server notification handling failed: {exc}"
                    self._fail_all_sessions(message)
                    self._fail_pending_calls(message)
                    return
            elif isinstance(value, JSONRPCResponse):
                future = self.pending_calls.get(value.id)
                if future is not None and not future.done():
                    future.set_result(value.result)
            elif isinstance(value, JSONRPCError):
                future = self.pending_calls.get(value.id)
                if future is not None and not future.done():
                    future.set_exception(RpcCallError.server(value.error))

    async def _handle_server_notification(self, notification: JSONRPCNotification) -> None:
        params = notification.params or {}
        if notification.method == EXEC_OUTPUT_DELTA_METHOD:
            process_id = _decode_process_id(params.get("processId") if isinstance(params, Mapping) else None)
            state = self.sessions.get(process_id)
            if state is None:
                return
            stream_value = params.get("stream")
            chunk_value = params.get("chunk")
            if not isinstance(stream_value, str) or not isinstance(chunk_value, str):
                raise ValueError("process/output requires stream and chunk")
            seq = _decode_optional_int(params.get("seq"), "seq")
            if seq is None:
                raise ValueError("seq must be an integer")
            state.note_change(seq)
            published_closed = state.publish_ordered_event(
                ExecProcessEvent.output(
                    ProcessOutputChunk(
                        seq=seq,
                        stream=ExecOutputStream(stream_value),
                        chunk=ByteChunk.from_base64(chunk_value),
                    )
                )
            )
            if published_closed:
                self.sessions.pop(process_id, None)
            return
        if notification.method == EXEC_EXITED_METHOD:
            process_id = _decode_process_id(params.get("processId") if isinstance(params, Mapping) else None)
            state = self.sessions.get(process_id)
            if state is None:
                return
            seq = _decode_optional_int(params.get("seq"), "seq")
            exit_code = _decode_optional_int(params.get("exitCode"), "exitCode")
            if seq is None or exit_code is None:
                raise ValueError("process/exited requires seq and exitCode")
            state.note_change(seq)
            published_closed = state.publish_ordered_event(ExecProcessEvent.exited(seq=seq, exit_code=exit_code))
            if published_closed:
                self.sessions.pop(process_id, None)
            return
        if notification.method == EXEC_CLOSED_METHOD:
            process_id = _decode_process_id(params.get("processId") if isinstance(params, Mapping) else None)
            state = self.sessions.get(process_id)
            if state is None:
                return
            seq = _decode_optional_int(params.get("seq"), "seq")
            if seq is None:
                raise ValueError("process/closed requires seq")
            state.note_change(seq)
            published_closed = state.publish_ordered_event(ExecProcessEvent.closed(seq=seq))
            if published_closed:
                self.sessions.pop(process_id, None)
            return
        if notification.method == HTTP_REQUEST_BODY_DELTA_METHOD:
            await self.handle_http_body_delta_notification(params)

    def _fail_all_sessions(self, message: str) -> None:
        if self.disconnected_message is None:
            self.disconnected_message = message
        for state in list(self.sessions.values()):
            state.set_failure(self.disconnected_message)
        self.sessions.clear()
        if self.http_body_streams:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self.http_body_streams.clear()
            else:
                loop.create_task(self.fail_all_http_body_streams(self.disconnected_message))

    def _fail_pending_calls(self, message: str) -> None:
        self.disconnected_message = self.disconnected_message or message
        for future in list(self.pending_calls.values()):
            if not future.done():
                future.set_exception(ExecServerError(self.disconnected_message, "disconnected"))
        self.pending_calls.clear()

    @classmethod
    async def connect_for_transport(
        cls,
        transport_params: ExecServerTransportParams,
        *,
        websocket_connector: Any | None = None,
        stdio_connector: Any | None = None,
        initializer: Any | None = None,
    ) -> "ExecServerClient":
        if transport_params.kind is ExecServerTransportKind.WEBSOCKET_URL:
            return await cls.connect_websocket(
                RemoteExecServerConnectArgs(
                    websocket_url=transport_params.websocket_url or "",
                    client_name=ENVIRONMENT_CLIENT_NAME,
                    connect_timeout=transport_params.connect_timeout
                    or DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT,
                    initialize_timeout=transport_params.initialize_timeout,
                    resume_session_id=None,
                ),
                websocket_connector=websocket_connector,
                initializer=initializer,
            )
        return await cls.connect_stdio_command(
            StdioExecServerConnectArgs(
                command=transport_params.command,
                client_name=ENVIRONMENT_CLIENT_NAME,
                initialize_timeout=transport_params.initialize_timeout,
                resume_session_id=None,
            ),
            stdio_connector=stdio_connector,
            initializer=initializer,
        )

    @classmethod
    async def connect_websocket(
        cls,
        args: RemoteExecServerConnectArgs,
        *,
        websocket_connector: Any | None = None,
        initializer: Any | None = None,
    ) -> "ExecServerClient":
        connect = _connect_websocket_url if websocket_connector is None else websocket_connector
        try:
            connection = await asyncio.wait_for(
                _maybe_await(connect(args.websocket_url) if websocket_connector is None else connect(args)),
                timeout=args.connect_timeout,
            )
        except TimeoutError as exc:
            raise ExecServerError.websocket_connect_timeout(
                args.websocket_url,
                args.connect_timeout,
            ) from exc
        except Exception as exc:
            raise ExecServerError.websocket_connect(args.websocket_url, exc) from exc
        if not isinstance(connection, JsonRpcConnection):
            connection_label = f"exec-server websocket {args.websocket_url}"
            if is_rendezvous_harness_url(args.websocket_url):
                connection = harness_connection_from_websocket(connection, connection_label)
            else:
                connection = JsonRpcConnection.from_websocket(connection, connection_label)
        return await cls.connect(connection, args.to_client_connect_options(), initializer=initializer)

    @classmethod
    async def connect_stdio_command(
        cls,
        args: StdioExecServerConnectArgs,
        *,
        stdio_connector: Any | None = None,
        initializer: Any | None = None,
    ) -> "ExecServerClient":
        if stdio_connector is None:
            connection = await _spawn_stdio_command_connection(args.command)
        else:
            connection = await _maybe_await(stdio_connector(args.command))
        if not isinstance(connection, JsonRpcConnection):
            raise TypeError("stdio_connector must return JsonRpcConnection")
        return await cls.connect(connection, args.to_client_connect_options(), initializer=initializer)

    @classmethod
    async def connect(
        cls,
        connection: JsonRpcConnection,
        options: ExecServerClientConnectOptions,
        *,
        initializer: Any | None = None,
    ) -> "ExecServerClient":
        if initializer is None:
            session_id = await _initialize_exec_server_connection(connection, options)
        else:
            session_id = await _maybe_await(initializer(connection, options))
        return cls(connection=connection, options=options, session_id=session_id)


async def _initialize_exec_server_connection(
    connection: JsonRpcConnection,
    options: ExecServerClientConnectOptions,
) -> str:
    request_id = RequestId.integer(1)
    params: dict[str, Any] = {"clientName": options.client_name}
    if options.resume_session_id is not None:
        params["resumeSessionId"] = options.resume_session_id
    await connection.outgoing_tx.put(
        JSONRPCMessage(
            JSONRPCRequest(
                id=request_id,
                method=INITIALIZE_METHOD,
                params=params,
                trace=None,
            )
        )
    )
    while True:
        event = await asyncio.wait_for(connection.incoming_rx.get(), timeout=options.initialize_timeout)
        if event.kind == "disconnected":
            raise ExecServerError.protocol("exec-server transport disconnected")
        if event.kind == "malformed":
            raise ExecServerError.protocol(event.reason or "malformed JSON-RPC message")
        if event.message is None:
            continue
        value = event.message.value
        if isinstance(value, JSONRPCResponse) and value.id == request_id:
            result = value.result
            if not isinstance(result, Mapping) or not isinstance(result.get("sessionId"), str):
                raise ExecServerError.protocol("initialize response missing sessionId")
            await connection.outgoing_tx.put(
                JSONRPCMessage(JSONRPCNotification(method=INITIALIZED_METHOD, params=None))
            )
            return result["sessionId"]
        if isinstance(value, JSONRPCError) and value.id == request_id:
            raise ExecServerError.protocol(value.error.message)


def _disconnected_message(reason: str | None = None) -> str:
    if reason:
        return f"exec-server transport disconnected: {reason}"
    return "exec-server transport disconnected"


from pycodex.exec_server.client.http_client.response_body_stream import HttpResponseBodyStream
from pycodex.exec_server.client.http_client.rpc_http_client import HTTP_BODY_DELTA_CHANNEL_CAPACITY
from pycodex.exec_server.client_api import DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT, ExecServerClientConnectOptions, ExecServerTransportKind, ExecServerTransportParams, RemoteExecServerConnectArgs, StdioExecServerConnectArgs
from pycodex.exec_server.client_transport import ENVIRONMENT_CLIENT_NAME, _spawn_stdio_command_connection, is_rendezvous_harness_url
from pycodex.exec_server.connection import JsonRpcConnection
from pycodex.exec_server.local_process import _put_latest_nowait
from pycodex.exec_server.process_id import ProcessId
from pycodex.exec_server.protocol import ByteChunk, EXEC_CLOSED_METHOD, EXEC_EXITED_METHOD, EXEC_OUTPUT_DELTA_METHOD, EXEC_READ_METHOD, EXEC_TERMINATE_METHOD, EXEC_WRITE_METHOD, ExecOutputStream, HTTP_REQUEST_BODY_DELTA_METHOD, HTTP_REQUEST_METHOD, HttpRequestBodyDeltaNotification, HttpRequestParams, HttpRequestResponse, INITIALIZED_METHOD, INITIALIZE_METHOD, ProcessOutputChunk, ReadParams, ReadResponse, TerminateParams, TerminateResponse, WriteParams, WriteResponse, _decode_optional_int, _decode_process_id, decode_http_request_body_delta_notification, decode_read_response, decode_terminate_response, decode_write_response, encode_read_params, encode_terminate_params, encode_write_params
from pycodex.exec_server.relay import harness_connection_from_websocket
from pycodex.exec_server.rpc import RpcCallError, _maybe_await
from pycodex.exec_server.server.transport import _connect_websocket_url, _rust_duration_debug
