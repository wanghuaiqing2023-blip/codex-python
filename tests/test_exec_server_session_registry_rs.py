"""Rust-derived tests for codex-exec-server/src/server/session_registry.rs."""

from __future__ import annotations

import asyncio
import time

from pycodex.app_server.error_code import INVALID_REQUEST_ERROR_CODE
from pycodex.app_server_protocol import JSONRPCErrorError
from pycodex.exec_server import (
    ConnectionId,
    ProcessHandler,
    SessionEntry,
    SessionHandle,
    SessionRegistry,
)


def test_session_registry_attach_creates_new_session():
    # Rust: codex-exec-server/src/server/session_registry.rs::SessionRegistry::attach
    # Contract: missing resume_session_id creates a new session with an active
    # connection and a ProcessHandler wired to the notification sender.
    async def run():
        registry = SessionRegistry.new(detached_session_ttl=0.05)
        handle = await registry.attach(None, "notifications")
        return registry, handle

    registry, handle = asyncio.run(run())

    assert isinstance(handle, SessionHandle)
    assert handle.session_id() in registry.sessions
    assert handle.is_session_attached() is True
    assert handle.process().notifications == "notifications"
    assert handle.connection_id()


def test_session_registry_rejects_unknown_resume_session_id():
    # Rust: codex-exec-server/src/server/session_registry.rs::SessionRegistry::attach
    # Contract: resuming an unknown session id returns invalid_request with the
    # Rust message shape.
    async def run():
        registry = SessionRegistry.new()
        return await registry.attach("missing", "notifications")

    error = asyncio.run(run())

    assert isinstance(error, JSONRPCErrorError)
    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert error.message == "unknown session id missing"


def test_session_registry_rejects_already_attached_resume():
    # Rust: codex-exec-server/src/server/session_registry.rs::SessionRegistry::attach
    # Contract: a session with an active connection cannot be attached by a
    # second connection.
    async def run():
        registry = SessionRegistry.new()
        first = await registry.attach(None, "first")
        error = await registry.attach(first.session_id(), "second")
        return first, error

    first, error = asyncio.run(run())

    assert first.is_session_attached() is True
    assert isinstance(error, JSONRPCErrorError)
    assert error.code == INVALID_REQUEST_ERROR_CODE
    assert error.message == f"session {first.session_id()} is already attached to another connection"


def test_session_handle_detach_marks_session_detached_and_clears_notifications():
    # Rust: codex-exec-server/src/server/session_registry.rs::SessionHandle::detach
    # Contract: detach only affects the handle's active connection, clears the
    # process notification sender, and leaves the session resumable until TTL.
    async def run():
        registry = SessionRegistry.new(detached_session_ttl=10)
        handle = await registry.attach(None, "notifications")
        await handle.detach()
        return registry, handle

    registry, handle = asyncio.run(run())

    assert handle.is_session_attached() is False
    assert handle.process().notifications is None
    entry = registry.sessions[handle.session_id()]
    assert entry.attachment.current_connection_id is None
    assert entry.attachment.detached_connection_id == handle.connection_id_value
    assert entry.attachment.detached_expires_at is not None


def test_session_registry_resume_detached_session_reattaches_and_reuses_process():
    # Rust: codex-exec-server/src/server/session_registry.rs::SessionRegistry::attach
    # Contract: resuming a detached non-expired session reuses the existing
    # process, sets the new notification sender, and clears detached state.
    async def run():
        registry = SessionRegistry.new(detached_session_ttl=10)
        first = await registry.attach(None, "first")
        process = first.process()
        await first.detach()
        second = await registry.attach(first.session_id(), "second")
        return first, second, process

    first, second, process = asyncio.run(run())

    assert first.session_id() == second.session_id()
    assert second.process() is process
    assert second.process().notifications == "second"
    assert second.is_session_attached() is True
    assert first.is_session_attached() is False


def test_session_registry_expired_resume_shuts_down_process_and_removes_session():
    # Rust: codex-exec-server/src/server/session_registry.rs::SessionRegistry::attach
    # Contract: resuming an expired detached session removes it, shuts down its
    # process, and returns the same unknown-session invalid_request shape.
    async def run():
        registry = SessionRegistry.new(detached_session_ttl=10)
        handle = await registry.attach(None, "notifications")
        process = handle.process()
        await handle.detach()
        entry = registry.sessions[handle.session_id()]
        entry.attachment.detached_expires_at = time.monotonic() - 1
        error = await registry.attach(handle.session_id(), "new")
        return registry, handle, process, error

    registry, handle, process, error = asyncio.run(run())

    assert handle.session_id() not in registry.sessions
    assert process.shutdown_called is True
    assert isinstance(error, JSONRPCErrorError)
    assert error.message == f"unknown session id {handle.session_id()}"


def test_session_registry_expire_if_detached_removes_only_matching_expired_connection():
    # Rust: codex-exec-server/src/server/session_registry.rs::expire_if_detached
    # Contract: expiry removes only a still-detached session whose detached
    # connection id matches the scheduled connection.
    async def run():
        registry = SessionRegistry.new(detached_session_ttl=0)
        handle = await registry.attach(None, "notifications")
        process = handle.process()
        await handle.detach()
        await registry.expire_if_detached(handle.session_id(), ConnectionId.new())
        still_present_after_wrong_connection = handle.session_id() in registry.sessions
        await registry.expire_if_detached(handle.session_id(), handle.connection_id_value)
        return still_present_after_wrong_connection, handle.session_id() in registry.sessions, process

    still_present, present_after_match, process = asyncio.run(run())

    assert still_present is True
    assert present_after_match is False
    assert process.shutdown_called is True


def test_session_entry_attach_detach_helpers_match_rust_state_transitions():
    # Rust: codex-exec-server/src/server/session_registry.rs::SessionEntry
    # Contract: attach resets detached state; detach with a stale connection id
    # is ignored.
    first = ConnectionId.new()
    second = ConnectionId.new()
    entry = SessionEntry.new("session", ProcessHandler.new("notifications"), first)

    assert entry.has_active_connection() is True
    assert entry.detach(second) is False
    assert entry.is_attached_to(first) is True
    assert entry.detach(first, ttl=10) is True
    assert entry.has_active_connection() is False
    assert entry.is_detached_connection_expired(first, now=time.monotonic() - 1) is False
    entry.attach(second)
    assert entry.is_attached_to(second) is True
    assert entry.attachment.detached_connection_id is None
    assert entry.attachment.detached_expires_at is None
