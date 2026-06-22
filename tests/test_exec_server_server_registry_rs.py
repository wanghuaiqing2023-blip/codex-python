"""Rust-derived tests for codex-exec-server/src/server/registry.rs."""

from __future__ import annotations

import asyncio

from pycodex.app_server_protocol import JSONRPCNotification, JSONRPCRequest
from pycodex.exec_server import (
    EXEC_METHOD,
    EXEC_READ_METHOD,
    EXEC_TERMINATE_METHOD,
    EXEC_WRITE_METHOD,
    FS_COPY_METHOD,
    FS_CREATE_DIRECTORY_METHOD,
    FS_GET_METADATA_METHOD,
    FS_READ_DIRECTORY_METHOD,
    FS_READ_FILE_METHOD,
    FS_REMOVE_METHOD,
    FS_WRITE_FILE_METHOD,
    HTTP_REQUEST_METHOD,
    HttpRequestParams,
    INITIALIZED_METHOD,
    INITIALIZE_METHOD,
    ByteChunk,
    ExecParams,
    ExecResponse,
    ProcessId,
    ReadParams,
    ReadResponse,
    InitializeParams,
    InitializeResponse,
    TerminateParams,
    TerminateResponse,
    WriteParams,
    WriteResponse,
    WriteStatus,
    RpcServerOutboundMessage,
    build_router,
)
from pycodex.protocol import RequestId


REQUEST_METHOD_TO_HANDLER = {
    INITIALIZE_METHOD: "initialize",
    EXEC_METHOD: "exec",
    EXEC_READ_METHOD: "exec_read",
    EXEC_WRITE_METHOD: "exec_write",
    EXEC_TERMINATE_METHOD: "terminate",
    FS_READ_FILE_METHOD: "fs_read_file",
    FS_WRITE_FILE_METHOD: "fs_write_file",
    FS_CREATE_DIRECTORY_METHOD: "fs_create_directory",
    FS_GET_METADATA_METHOD: "fs_get_metadata",
    FS_READ_DIRECTORY_METHOD: "fs_read_directory",
    FS_REMOVE_METHOD: "fs_remove",
    FS_COPY_METHOD: "fs_copy",
}


class FakeExecServerHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.notification_error: str | None = None

    def initialized(self) -> str | None:
        self.calls.append(("initialized", None))
        return self.notification_error

    async def initialize(self, params):
        self.calls.append(("initialize", params))
        return InitializeResponse(session_id="session-test")

    async def http_request(self, request_id, params):
        self.calls.append(("http_request", (request_id.to_json(), params)))
        return None

    async def exec(self, params):
        self.calls.append(("exec", params))
        return ExecResponse(process_id=params.process_id)

    async def exec_read(self, params):
        self.calls.append(("exec_read", params))
        return ReadResponse(chunks=[], next_seq=1, exited=False, exit_code=None, closed=False)

    async def exec_write(self, params):
        self.calls.append(("exec_write", params))
        return WriteResponse(status=WriteStatus.ACCEPTED)

    async def terminate(self, params):
        self.calls.append(("terminate", params))
        return TerminateResponse(running=False)

    async def fs_read_file(self, params):
        return await self._record("fs_read_file", params)

    async def fs_write_file(self, params):
        return await self._record("fs_write_file", params)

    async def fs_create_directory(self, params):
        return await self._record("fs_create_directory", params)

    async def fs_get_metadata(self, params):
        return await self._record("fs_get_metadata", params)

    async def fs_read_directory(self, params):
        return await self._record("fs_read_directory", params)

    async def fs_remove(self, params):
        return await self._record("fs_remove", params)

    async def fs_copy(self, params):
        return await self._record("fs_copy", params)

    async def _record(self, name: str, params):
        self.calls.append((name, params))
        return {"called": name, "params": params}


def test_build_router_registers_rust_methods():
    # Rust: codex-exec-server/src/server/registry.rs::build_router
    # Contract: the registry binds every protocol method in the Rust source to
    # a request or notification route.
    router = build_router()

    assert router.notification_route(INITIALIZED_METHOD) is not None
    assert router.notification_route("missing") is None
    for method in REQUEST_METHOD_TO_HANDLER:
        assert router.request_route(method) is not None
    assert router.request_route(HTTP_REQUEST_METHOD) is not None
    assert router.request_route("missing") is None


def test_build_router_dispatches_initialized_notification():
    # Rust: codex-exec-server/src/server/registry.rs initialized notification
    # Contract: initialized ignores params, calls handler.initialized, and
    # preserves the handler's Rust-style Result<(), String> error string.
    async def run():
        router = build_router()
        handler = FakeExecServerHandler()
        ok = await router.notification_route(INITIALIZED_METHOD)(
            handler,
            JSONRPCNotification(method=INITIALIZED_METHOD, params={"ignored": True}),
        )
        handler.notification_error = "not ready"
        error = await router.notification_route(INITIALIZED_METHOD)(
            handler,
            JSONRPCNotification(method=INITIALIZED_METHOD, params=None),
        )
        return handler.calls, ok, error

    calls, ok, error = asyncio.run(run())

    assert calls == [("initialized", None), ("initialized", None)]
    assert ok is None
    assert error == "not ready"


def test_build_router_dispatches_http_request_with_request_id():
    # Rust: codex-exec-server/src/server/registry.rs http/request route
    # Contract: http/request is registered with request_with_id and emits no
    # JSON-RPC response on success.
    async def run():
        router = build_router()
        handler = FakeExecServerHandler()
        response = await router.request_route(HTTP_REQUEST_METHOD)(
            handler,
            JSONRPCRequest(
                id="req-1",
                method=HTTP_REQUEST_METHOD,
                params={"method": "GET", "url": "https://example.test", "requestId": "http-1"},
            ),
        )
        return handler.calls, response

    calls, response = asyncio.run(run())

    assert calls == [
        (
            "http_request",
            (
                "req-1",
                HttpRequestParams(
                    method="GET",
                    url="https://example.test",
                    headers=[],
                    request_id="http-1",
                ),
            ),
        )
    ]
    assert response is None


def test_build_router_dispatches_requests_to_matching_handler_methods():
    # Rust: codex-exec-server/src/server/registry.rs request registrations
    # Contract: each registered method forwards decoded params to the handler
    # method named in the Rust source and returns its JSON-RPC response.
    async def run():
        router = build_router()
        handler = FakeExecServerHandler()
        results = {}
        for index, (method, handler_name) in enumerate(REQUEST_METHOD_TO_HANDLER.items(), start=1):
            if method == INITIALIZE_METHOD:
                params = {"clientName": "registry-test"}
                expected_params = InitializeParams(client_name="registry-test")
                expected_result = {"sessionId": "session-test"}
            elif method == EXEC_METHOD:
                params = {
                    "processId": "proc-registry",
                    "argv": ["cmd"],
                    "cwd": "/tmp",
                    "envPolicy": None,
                    "env": {},
                    "tty": False,
                    "pipeStdin": False,
                    "arg0": None,
                }
                expected_params = ExecParams(
                    process_id=ProcessId.new("proc-registry"),
                    argv=["cmd"],
                    cwd="/tmp",
                    env={},
                    tty=False,
                    env_policy=None,
                    pipe_stdin=False,
                    arg0=None,
                )
                expected_result = {"processId": "proc-registry"}
            elif method == EXEC_READ_METHOD:
                params = {"processId": "proc-registry", "afterSeq": None, "maxBytes": None, "waitMs": 5}
                expected_params = ReadParams(
                    process_id=ProcessId.new("proc-registry"),
                    after_seq=None,
                    max_bytes=None,
                    wait_ms=5,
                )
                expected_result = {
                    "chunks": [],
                    "nextSeq": 1,
                    "exited": False,
                    "exitCode": None,
                    "closed": False,
                    "failure": None,
                }
            elif method == EXEC_WRITE_METHOD:
                params = {"processId": "proc-registry", "chunk": "aGk="}
                expected_params = WriteParams(
                    process_id=ProcessId.new("proc-registry"),
                    chunk=ByteChunk(b"hi"),
                )
                expected_result = {"status": "accepted"}
            elif method == EXEC_TERMINATE_METHOD:
                params = {"processId": "proc-registry"}
                expected_params = TerminateParams(process_id=ProcessId.new("proc-registry"))
                expected_result = {"running": False}
            else:
                params = {"method": method}
                expected_params = params
                expected_result = {"called": handler_name, "params": params}
            results[method] = await router.request_route(method)(
                handler,
                JSONRPCRequest(id=index, method=method, params=params),
            )
            assert handler.calls[-1] == (handler_name, expected_params)
            assert results[method] == RpcServerOutboundMessage.response(
                RequestId.integer(index),
                expected_result,
            )
        return results

    results = asyncio.run(run())

    assert set(results) == set(REQUEST_METHOD_TO_HANDLER)
