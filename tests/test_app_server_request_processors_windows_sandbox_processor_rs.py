"""Rust parity tests for ``request_processors/windows_sandbox_processor.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from pycodex.app_server.outgoing_message import ConnectionRequestId, OutgoingMessageKind, OutgoingMessageSender
from pycodex.app_server.request_processors_windows_sandbox_processor import (
    WindowsSandboxRequestProcessor,
    WindowsSandboxSetupRequest,
    determine_windows_sandbox_readiness_from_state,
)
from pycodex.app_server_protocol import WindowsSandboxReadiness, WindowsSandboxSetupMode, WindowsSandboxSetupStartParams
from pycodex.protocol import RequestId, WindowsSandboxLevel


@dataclass(frozen=True)
class Permissions:
    profile: str = "trusted"

    def effective_permission_profile(self) -> str:
        return self.profile


@dataclass(frozen=True)
class Config:
    cwd: Path
    codex_home: Path
    permissions: Permissions = Permissions()


class ConfigManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.calls: list[tuple[object, object, object]] = []

    async def load_for_cwd(self, request_overrides: object, overrides: object, cwd: object) -> Config:
        self.calls.append((request_overrides, overrides, cwd))
        return self.config


async def receive(queue: asyncio.Queue) -> object:
    return await asyncio.wait_for(queue.get(), timeout=1.0)


def test_determine_windows_sandbox_readiness_reports_not_configured_when_disabled() -> None:
    response = determine_windows_sandbox_readiness_from_state(
        WindowsSandboxLevel.DISABLED,
        False,
    )

    assert response.status is WindowsSandboxReadiness.NOT_CONFIGURED


def test_determine_windows_sandbox_readiness_reports_ready_for_unelevated_mode() -> None:
    response = determine_windows_sandbox_readiness_from_state(
        WindowsSandboxLevel.RESTRICTED_TOKEN,
        False,
    )

    assert response.status is WindowsSandboxReadiness.READY


def test_determine_windows_sandbox_readiness_reports_ready_for_complete_elevated_mode() -> None:
    response = determine_windows_sandbox_readiness_from_state(
        WindowsSandboxLevel.ELEVATED,
        True,
    )

    assert response.status is WindowsSandboxReadiness.READY


def test_determine_windows_sandbox_readiness_reports_update_required_when_elevated_setup_is_stale() -> None:
    response = determine_windows_sandbox_readiness_from_state(
        WindowsSandboxLevel.ELEVATED,
        False,
    )

    assert response.status is WindowsSandboxReadiness.UPDATE_REQUIRED


@pytest.mark.asyncio
async def test_windows_sandbox_setup_start_sends_started_response_then_completion_notification() -> None:
    # Rust: setup_start_inner sends started response before spawned setup work
    # later sends WindowsSandboxSetupCompleted to the request connection.
    queue: asyncio.Queue = asyncio.Queue()
    outgoing = OutgoingMessageSender.new(queue)
    config = Config(cwd=Path("C:/repo"), codex_home=Path("C:/codex"))
    config_manager = ConfigManager(config)
    setup_requests: list[WindowsSandboxSetupRequest] = []
    spawned: list[object] = []

    async def setup_runner(request: WindowsSandboxSetupRequest) -> None:
        setup_requests.append(request)

    def task_spawner(awaitable: object) -> None:
        spawned.append(awaitable)

    processor = WindowsSandboxRequestProcessor(
        outgoing,
        config,
        config_manager,
        setup_runner=setup_runner,
        task_spawner=task_spawner,
        env_map={"A": "B"},
    )
    request_id = ConnectionRequestId(connection_id=42, request_id=RequestId.integer(7))

    await processor.windows_sandbox_setup_start(
        request_id,
        WindowsSandboxSetupStartParams(mode=WindowsSandboxSetupMode.ELEVATED, cwd=Path("C:/work")),
    )

    response = await receive(queue)
    assert response.kind == "ToConnection"
    assert response.connection_id == 42
    assert response.message.kind is OutgoingMessageKind.RESPONSE
    assert response.message.payload.id == RequestId.integer(7)
    assert response.message.payload.result == {"started": True}
    assert len(spawned) == 1

    await spawned[0]

    completed = await receive(queue)
    assert completed.kind == "ToConnection"
    assert completed.connection_id == 42
    assert completed.message.kind is OutgoingMessageKind.APP_SERVER_NOTIFICATION
    assert completed.message.payload.type == "WindowsSandboxSetupCompleted"
    assert completed.message.payload.payload.mode is WindowsSandboxSetupMode.ELEVATED
    assert completed.message.payload.payload.success is True
    assert completed.message.payload.payload.error is None
    assert config_manager.calls == [(None, {"cwd": Path("C:/work")}, Path("C:/work"))]
    assert setup_requests == [
        WindowsSandboxSetupRequest(
            mode=WindowsSandboxSetupMode.ELEVATED,
            permission_profile="trusted",
            permission_profile_cwd=Path("C:/repo"),
            command_cwd=Path("C:/work"),
            env_map={"A": "B"},
            codex_home=Path("C:/codex"),
        )
    ]


@pytest.mark.asyncio
async def test_windows_sandbox_setup_start_completion_notification_reports_error() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    outgoing = OutgoingMessageSender.new(queue)
    config = Config(cwd=Path("C:/repo"), codex_home=Path("C:/codex"))

    async def setup_runner(_request: WindowsSandboxSetupRequest) -> None:
        raise RuntimeError("setup failed")

    spawned: list[object] = []

    processor = WindowsSandboxRequestProcessor(
        outgoing,
        config,
        ConfigManager(config),
        setup_runner=setup_runner,
        task_spawner=lambda awaitable: spawned.append(awaitable),
    )
    request_id = ConnectionRequestId(connection_id=5, request_id=RequestId.integer(11))

    await processor.windows_sandbox_setup_start(
        request_id,
        {"mode": "unelevated", "cwd": "C:/repo"},
    )
    await receive(queue)
    spawned[0].close()
    await processor._run_setup_task(5, WindowsSandboxSetupStartParams(mode="unelevated", cwd=Path("C:/repo")))

    completed = await receive(queue)
    assert completed.message.payload.type == "WindowsSandboxSetupCompleted"
    assert completed.message.payload.payload.mode is WindowsSandboxSetupMode.UNELEVATED
    assert completed.message.payload.payload.success is False
    assert completed.message.payload.payload.error == "setup failed"
