from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, replace
from typing import Any

from pycodex.app_server_protocol import (
    RemoteControlConnectionStatus,
    RemoteControlStatusChangedNotification,
)

from .protocol import ClientId, ServerEvent, StreamId, normalize_remote_control_url


@dataclass(frozen=True)
class RemoteControlStartConfig:
    remote_control_url: str
    installation_id: str


@dataclass
class QueuedServerEnvelope:
    event: ServerEvent
    client_id: ClientId
    stream_id: StreamId
    write_complete_tx: asyncio.Future[None] | None = None


class RemoteControlUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "remote control cannot be enabled because sqlite state db is unavailable"
        )


class RemoteControlHandle:
    def __init__(
        self,
        *,
        enabled_event: asyncio.Event,
        initial_status: RemoteControlStatusChangedNotification,
        state_db_available: bool,
    ) -> None:
        self._enabled_event = enabled_event
        self._status = initial_status
        self._state_db_available = state_db_available
        self._status_receivers: set[asyncio.Queue[RemoteControlStatusChangedNotification]] = set()

    def enable(self) -> RemoteControlStatusChangedNotification:
        if not self._state_db_available:
            raise RemoteControlUnavailable()
        self._enabled_event.set()
        if self._status.status in {
            RemoteControlConnectionStatus.CONNECTED,
            RemoteControlConnectionStatus.CONNECTING,
        }:
            return self._status
        return self.publish_status(RemoteControlConnectionStatus.CONNECTING)

    def disable(self) -> RemoteControlStatusChangedNotification:
        self._enabled_event.clear()
        return self.publish_status(RemoteControlConnectionStatus.DISABLED)

    def status(self) -> RemoteControlStatusChangedNotification:
        return self._status

    def status_receiver(
        self,
    ) -> asyncio.Queue[RemoteControlStatusChangedNotification]:
        receiver: asyncio.Queue[RemoteControlStatusChangedNotification] = asyncio.Queue()
        receiver.put_nowait(self._status)
        self._status_receivers.add(receiver)
        return receiver

    def publish_status(
        self,
        connection_status: RemoteControlConnectionStatus,
        *,
        environment_id: str | None | object = ...,
    ) -> RemoteControlStatusChangedNotification:
        next_environment_id = (
            self._status.environment_id if environment_id is ... else environment_id
        )
        if connection_status is RemoteControlConnectionStatus.DISABLED:
            next_environment_id = None
        next_status = replace(
            self._status,
            status=connection_status,
            environment_id=next_environment_id,
        )
        if next_status != self._status:
            self._status = next_status
            for receiver in tuple(self._status_receivers):
                try:
                    receiver.put_nowait(next_status)
                except asyncio.QueueFull:
                    self._status_receivers.discard(receiver)
        return self._status


async def start_remote_control(
    config: RemoteControlStartConfig,
    state_db: Any | None,
    auth_manager: Any,
    transport_event_tx: asyncio.Queue[Any],
    shutdown_token: Any,
    app_server_client_name_rx: Any | None,
    initial_enabled: bool,
) -> tuple[asyncio.Task[None], RemoteControlHandle]:
    state_db_available = state_db is not None
    enabled = initial_enabled and state_db_available
    target = normalize_remote_control_url(config.remote_control_url) if enabled else None
    enabled_event = asyncio.Event()
    if enabled:
        enabled_event.set()
    initial_status = RemoteControlStatusChangedNotification(
        status=(
            RemoteControlConnectionStatus.CONNECTING
            if enabled
            else RemoteControlConnectionStatus.DISABLED
        ),
        server_name=socket.gethostname().strip(),
        installation_id=config.installation_id,
        environment_id=None,
    )
    handle = RemoteControlHandle(
        enabled_event=enabled_event,
        initial_status=initial_status,
        state_db_available=state_db_available,
    )

    from .websocket import (
        RemoteControlChannels,
        RemoteControlStatusPublisher,
        RemoteControlWebsocket,
        RemoteControlWebsocketConfig,
    )

    websocket = RemoteControlWebsocket(
        RemoteControlWebsocketConfig(
            remote_control_url=config.remote_control_url,
            installation_id=config.installation_id,
            remote_control_target=target,
            server_name=initial_status.server_name,
        ),
        state_db=state_db,
        auth_manager=auth_manager,
        channels=RemoteControlChannels(
            transport_event_tx=transport_event_tx,
            status_publisher=RemoteControlStatusPublisher(handle),
        ),
        shutdown_token=shutdown_token,
        enabled_event=enabled_event,
    )
    task = asyncio.create_task(websocket.run(app_server_client_name_rx))
    return task, handle


__all__ = [
    "ClientId",
    "QueuedServerEnvelope",
    "RemoteControlHandle",
    "RemoteControlStartConfig",
    "RemoteControlUnavailable",
    "start_remote_control",
]
