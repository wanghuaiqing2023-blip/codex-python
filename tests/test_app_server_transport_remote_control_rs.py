from __future__ import annotations

import asyncio

import pytest
from websockets.asyncio.server import serve

from pycodex.app_server_protocol import RemoteControlConnectionStatus
from pycodex.app_server_transport.transport.remote_control import (
    RemoteControlStartConfig,
    RemoteControlUnavailable,
    start_remote_control,
)
from pycodex.app_server_transport.transport.remote_control.enroll import (
    RemoteControlEnrollment,
    update_persisted_remote_control_enrollment,
)
from pycodex.app_server_transport.transport.remote_control.protocol import (
    normalize_remote_control_url,
)
from pycodex.state import StateRuntime


class _Cancellation:
    def __init__(self) -> None:
        self.event = asyncio.Event()

    def cancel(self) -> None:
        self.event.set()

    def is_cancelled(self) -> bool:
        return self.event.is_set()

    async def cancelled(self) -> None:
        await self.event.wait()


class _Auth:
    def uses_codex_backend(self) -> bool:
        return True

    def get_account_id(self) -> str:
        return "account"

    def get_token(self) -> str:
        return "token"

    def is_fedramp_account(self) -> bool:
        return False


class _AuthManager:
    async def auth(self):
        return _Auth()

    async def reload(self) -> None:
        return None


async def _wait_for_status(handle, expected: RemoteControlConnectionStatus) -> None:
    receiver = handle.status_receiver()
    while True:
        status = await asyncio.wait_for(receiver.get(), timeout=2)
        if status.status is expected:
            return


@pytest.mark.asyncio
async def test_disabled_start_defers_remote_control_url_validation() -> None:
    cancellation = _Cancellation()
    task, handle = await start_remote_control(
        RemoteControlStartConfig(
            remote_control_url="https://internal.example.com/backend-api/",
            installation_id="installation",
        ),
        None,
        _AuthManager(),
        asyncio.Queue(maxsize=128),
        cancellation,
        None,
        False,
    )
    assert handle.status().status is RemoteControlConnectionStatus.DISABLED
    cancellation.cancel()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_missing_state_db_forces_disabled_and_rejects_enable() -> None:
    cancellation = _Cancellation()
    task, handle = await start_remote_control(
        RemoteControlStartConfig(
            remote_control_url="http://localhost/backend-api/",
            installation_id="installation",
        ),
        None,
        _AuthManager(),
        asyncio.Queue(maxsize=128),
        cancellation,
        None,
        True,
    )
    assert handle.status().status is RemoteControlConnectionStatus.DISABLED
    with pytest.raises(RemoteControlUnavailable):
        handle.enable()
    cancellation.cancel()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_handle_disable_and_enable_restarts_real_connection(tmp_path) -> None:
    connections: asyncio.Queue[int] = asyncio.Queue()
    disconnected: asyncio.Queue[int] = asyncio.Queue()
    connection_number = 0

    async def remote_server(connection) -> None:
        nonlocal connection_number
        connection_number += 1
        current = connection_number
        await connections.put(current)
        try:
            await connection.wait_closed()
        finally:
            await disconnected.put(current)

    runtime = await StateRuntime.init(tmp_path, "test-provider")
    cancellation = _Cancellation()
    task: asyncio.Task[None] | None = None
    try:
        async with serve(remote_server, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            remote_url = f"http://127.0.0.1:{port}/backend-api/"
            target = normalize_remote_control_url(remote_url)
            await update_persisted_remote_control_enrollment(
                runtime,
                target,
                "account",
                None,
                RemoteControlEnrollment(
                    account_id="account",
                    environment_id="environment",
                    server_id="server-id",
                    server_name="server",
                ),
            )
            task, handle = await start_remote_control(
                RemoteControlStartConfig(
                    remote_control_url=remote_url,
                    installation_id="installation",
                ),
                runtime,
                _AuthManager(),
                asyncio.Queue(maxsize=128),
                cancellation,
                None,
                True,
            )
            assert await asyncio.wait_for(connections.get(), timeout=2) == 1
            await _wait_for_status(handle, RemoteControlConnectionStatus.CONNECTED)

            disabled = handle.disable()
            assert disabled.status is RemoteControlConnectionStatus.DISABLED
            assert disabled.environment_id is None
            assert await asyncio.wait_for(disconnected.get(), timeout=2) == 1

            connecting = handle.enable()
            assert connecting.status is RemoteControlConnectionStatus.CONNECTING
            assert await asyncio.wait_for(connections.get(), timeout=2) == 2
            await _wait_for_status(handle, RemoteControlConnectionStatus.CONNECTED)

            cancellation.cancel()
            await asyncio.wait_for(task, timeout=2)
            task = None
    finally:
        cancellation.cancel()
        if task is not None:
            await asyncio.wait_for(task, timeout=2)
        await runtime.close()
