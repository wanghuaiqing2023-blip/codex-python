from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Any

from pycodex.app_server_protocol import RemoteControlConnectionStatus
from pycodex.app_server_protocol import RemoteControlEnableResponse
from pycodex.app_server_protocol import RemoteControlStatusChangedNotification

from . import client


REMOTE_CONTROL_READY_TIMEOUT = 10.0
REMOTE_CONTROL_ENABLE_REQUEST_ID = 2


async def enable_remote_control(socket_path: Path) -> Any:
    websocket = await client.connect(socket_path)
    return await enable_remote_control_with_timeout(
        websocket,
        ready_timeout=REMOTE_CONTROL_READY_TIMEOUT,
    )


async def enable_remote_control_with_connect_retry(
    socket_path: Path,
    connect_timeout: float,
    connect_retry_delay: float,
) -> Any:
    websocket = await connect_with_retry(
        socket_path,
        connect_timeout,
        connect_retry_delay,
    )
    return await enable_remote_control_with_timeout(
        websocket,
        ready_timeout=REMOTE_CONTROL_READY_TIMEOUT,
    )


async def connect_with_retry(
    socket_path: Path,
    connect_timeout: float,
    connect_retry_delay: float,
) -> Any:
    deadline = time.monotonic() + connect_timeout
    while True:
        try:
            return await client.connect(socket_path)
        except Exception as exc:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"app server did not become ready on {socket_path}: {exc}"
                ) from exc
            await asyncio.sleep(connect_retry_delay)


async def enable_remote_control_with_timeout(
    websocket: Any,
    ready_timeout: float,
) -> Any:
    from . import RemoteControlReadyStatus

    await client.initialize(websocket, experimental_api=True)
    await client.send_message(websocket, {"method": "initialized"})
    await client.send_message(
        websocket,
        {
            "id": REMOTE_CONTROL_ENABLE_REQUEST_ID,
            "method": "remoteControl/enable",
        },
    )

    latest = await _read_enable_response(websocket)
    if latest.status is RemoteControlConnectionStatus.CONNECTING:
        latest = await _wait_for_remote_control_status(
            websocket,
            latest,
            ready_timeout,
        )
    await _close(websocket)
    if not isinstance(latest, RemoteControlReadyStatus):
        raise AssertionError("remote-control state conversion failed")
    return latest


async def _read_enable_response(websocket: Any) -> Any:
    while True:
        try:
            message = await asyncio.wait_for(
                client.read_message(websocket),
                timeout=client.CONTROL_SOCKET_RESPONSE_TIMEOUT,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                "timed out waiting for remoteControl/enable response"
            ) from exc
        if (
            message.get("id") == REMOTE_CONTROL_ENABLE_REQUEST_ID
            and "error" in message
        ):
            error = message["error"]
            detail = error.get("message") if isinstance(error, dict) else error
            raise RuntimeError(f"remoteControl/enable failed: {detail}")
        if (
            message.get("id") == REMOTE_CONTROL_ENABLE_REQUEST_ID
            and "result" in message
        ):
            result = message["result"]
            if not isinstance(result, dict):
                raise RuntimeError("failed to parse remoteControl/enable response")
            try:
                return _ready_status(
                    RemoteControlEnableResponse.from_mapping(result)
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise RuntimeError(
                    f"failed to parse remoteControl/enable response: {exc}"
                ) from exc


async def _wait_for_remote_control_status(
    websocket: Any,
    latest: Any,
    ready_timeout: float,
) -> Any:
    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            message = await asyncio.wait_for(
                client.read_message(websocket),
                timeout=remaining,
            )
        except TimeoutError:
            return _with_timeout(latest)
        notification = _remote_control_status_notification(message)
        if notification is None:
            continue
        latest = _ready_status(notification)
        if latest.status is not RemoteControlConnectionStatus.CONNECTING:
            return latest
    return _with_timeout(latest)


def _remote_control_status_notification(
    message: dict[str, object],
) -> RemoteControlStatusChangedNotification | None:
    if message.get("method") != "remoteControl/status/changed":
        return None
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    try:
        return RemoteControlStatusChangedNotification.from_mapping(params)
    except (TypeError, ValueError, KeyError):
        return None


def _ready_status(
    value: RemoteControlEnableResponse | RemoteControlStatusChangedNotification,
) -> Any:
    from . import RemoteControlReadyStatus

    return RemoteControlReadyStatus(
        status=value.status,
        server_name=value.server_name,
        environment_id=value.environment_id,
        timed_out=False,
    )


def _with_timeout(value: Any) -> Any:
    from . import RemoteControlReadyStatus

    return RemoteControlReadyStatus(
        status=value.status,
        server_name=value.server_name,
        environment_id=value.environment_id,
        timed_out=True,
    )


async def _close(websocket: Any) -> None:
    try:
        result = websocket.close()
        if hasattr(result, "__await__"):
            await result
    except Exception:
        pass


__all__ = [
    "REMOTE_CONTROL_ENABLE_REQUEST_ID",
    "REMOTE_CONTROL_READY_TIMEOUT",
    "connect_with_retry",
    "enable_remote_control",
    "enable_remote_control_with_connect_retry",
    "enable_remote_control_with_timeout",
]
