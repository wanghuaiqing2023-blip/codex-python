"""Rust-derived tests for codex-exec-server/src/server/handler.rs."""

from __future__ import annotations

import asyncio

from pycodex.app_server.error_code import INVALID_REQUEST_ERROR_CODE
from pycodex.app_server_protocol.jsonrpc_lite import JSONRPCErrorError
from pycodex.exec_server import (
    ExecServerHandler,
    ExecServerRuntimePaths,
    FsReadFileParams,
    FsReadFileResponse,
    InitializeParams,
    InitializeResponse,
    RpcNotificationSender,
    SessionRegistry,
)


class FakeFileSystemHandler:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def read_file(self, params: FsReadFileParams) -> FsReadFileResponse:
        self.calls.append(params)
        return FsReadFileResponse(data_base64="b2s=")


def _runtime_paths(tmp_path) -> ExecServerRuntimePaths:
    return ExecServerRuntimePaths.new(tmp_path / "codex", None)


def _notifications() -> RpcNotificationSender:
    return RpcNotificationSender.new(asyncio.Queue())


def test_handler_initialize_and_initialized_state_machine(tmp_path):
    # Rust: codex-exec-server/src/server/handler.rs::ExecServerHandler
    # Contract: initialized before initialize returns a protocol string error;
    # initialize attaches a session; duplicate initialize is rejected; and a
    # later initialized notification marks the connection initialized.
    async def run():
        handler = ExecServerHandler.new(SessionRegistry.new(), _notifications(), _runtime_paths(tmp_path))
        early_initialized = handler.initialized()
        first = await handler.initialize(InitializeParams(client_name="exec-server-test"))
        duplicate = await handler.initialize(InitializeParams(client_name="exec-server-test"))
        initialized = handler.initialized()
        return handler, early_initialized, first, duplicate, initialized

    handler, early_initialized, first, duplicate, initialized = asyncio.run(run())

    assert early_initialized == "received `initialized` notification before `initialize`"
    assert isinstance(first, InitializeResponse)
    assert first.session_id in handler.session_registry.sessions
    assert handler.is_session_attached() is True
    assert isinstance(duplicate, JSONRPCErrorError)
    assert duplicate.code == INVALID_REQUEST_ERROR_CODE
    assert duplicate.message == "initialize may only be sent once per connection"
    assert initialized is None
    assert handler.initialized_flag is True


def test_handler_active_session_resume_is_rejected(tmp_path):
    # Rust: codex-exec-server/src/server/handler/tests.rs
    # Test: active_session_resume_is_rejected
    # Contract: a second handler cannot initialize against a session id that is
    # still attached to another connection.
    async def run():
        registry = SessionRegistry.new()
        first = ExecServerHandler.new(registry, _notifications(), _runtime_paths(tmp_path))
        initialize_response = await first.initialize(InitializeParams(client_name="first"))
        second = ExecServerHandler.new(registry, _notifications(), _runtime_paths(tmp_path))
        error = await second.initialize(
            InitializeParams(client_name="second", resume_session_id=initialize_response.session_id)
        )
        return initialize_response, error

    initialize_response, error = asyncio.run(run())

    assert isinstance(error, JSONRPCErrorError)
    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert error.message == f"session {initialize_response.session_id} is already attached to another connection"


def test_handler_filesystem_methods_require_initialize_and_initialized(tmp_path):
    # Rust: ExecServerHandler::require_initialized_for used by fs_* methods
    # Contract: filesystem methods first require initialize, then initialized.
    async def run():
        fake_fs = FakeFileSystemHandler()
        handler = ExecServerHandler(
            SessionRegistry.new(),
            _notifications(),
            _runtime_paths(tmp_path),
            file_system=fake_fs,
        )
        before_initialize = await handler.fs_read_file(FsReadFileParams(path="/tmp/file"))
        await handler.initialize(InitializeParams(client_name="exec-server-test"))
        before_initialized = await handler.fs_read_file(FsReadFileParams(path="/tmp/file"))
        handler.initialized()
        success = await handler.fs_read_file(FsReadFileParams(path="/tmp/file"))
        return fake_fs, before_initialize, before_initialized, success

    fake_fs, before_initialize, before_initialized, success = asyncio.run(run())

    assert before_initialize.code == INVALID_REQUEST_ERROR_CODE
    assert before_initialize.message == "client must call initialize before using filesystem methods"
    assert before_initialized.code == INVALID_REQUEST_ERROR_CODE
    assert before_initialized.message == "client must send initialized before using filesystem methods"
    assert success == FsReadFileResponse(data_base64="b2s=")
    assert fake_fs.calls == [FsReadFileParams(path="/tmp/file")]


def test_handler_shutdown_detaches_session(tmp_path):
    # Rust: ExecServerHandler::shutdown
    # Contract: shutdown detaches the current session and clears the process
    # notification sender through SessionHandle::detach.
    async def run():
        registry = SessionRegistry.new(detached_session_ttl=10)
        handler = ExecServerHandler.new(registry, _notifications(), _runtime_paths(tmp_path))
        response = await handler.initialize(InitializeParams(client_name="exec-server-test"))
        handler.initialized()
        await handler.shutdown()
        entry = registry.sessions[response.session_id]
        return handler, entry

    handler, entry = asyncio.run(run())

    assert handler.shutdown_called is True
    assert handler.is_session_attached() is False
    assert entry.attachment.current_connection_id is None
    assert entry.attachment.detached_connection_id is not None
    assert entry.process.notifications is None
