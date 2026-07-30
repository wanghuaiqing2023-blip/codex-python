from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pycodex.app_server_daemon import (
    BackendKind,
    BootstrapOutput,
    BootstrapStatus,
    LifecycleOutput,
    LifecycleStatus,
    RemoteControlMode,
    RemoteControlReadyStatus,
    RemoteControlStatus,
    ensure_supported_platform,
)
from pycodex.app_server_daemon.backend.pid import PidBackend
from pycodex.app_server_daemon.backend.pid import read_stderr_log_tail
from pycodex.app_server_daemon.client import parse_version_from_user_agent
from pycodex.app_server_daemon.managed_install import executable_identity_from_bytes
from pycodex.app_server_daemon.managed_install import managed_codex_bin
from pycodex.app_server_daemon.remote_control_client import (
    enable_remote_control_with_timeout,
)
from pycodex.app_server_daemon.settings import DaemonSettings
from pycodex.app_server_protocol import RemoteControlConnectionStatus


def test_lib_outputs_match_rust_untagged_camel_case_contract() -> None:
    lifecycle = LifecycleOutput(
        status=LifecycleStatus.ALREADY_RUNNING,
        backend=BackendKind.PID,
        pid=None,
        managed_codex_path=Path("codex"),
        managed_codex_version="1.2.3",
        socket_path=Path("codex.sock"),
        cli_version="1.2.3",
        app_server_version="1.2.4",
    )
    assert lifecycle.to_dict() == {
        "status": "alreadyRunning",
        "backend": "pid",
        "managedCodexPath": "codex",
        "managedCodexVersion": "1.2.3",
        "socketPath": "codex.sock",
        "cliVersion": "1.2.3",
        "appServerVersion": "1.2.4",
    }

    bootstrap = BootstrapOutput(
        status=BootstrapStatus.BOOTSTRAPPED,
        backend=BackendKind.PID,
        auto_update_enabled=True,
        remote_control_enabled=True,
        managed_codex_path=Path("codex"),
        managed_codex_version="1.2.3",
        socket_path=Path("codex.sock"),
        cli_version="1.2.3",
        app_server_version="1.2.4",
    )
    assert bootstrap.to_dict()["status"] == "bootstrapped"
    assert bootstrap.to_dict()["autoUpdateEnabled"] is True
    assert RemoteControlStatus.ALREADY_ENABLED.value == "alreadyEnabled"
    assert RemoteControlMode.ENABLED.is_enabled()


@pytest.mark.asyncio
async def test_settings_round_trip_uses_rust_camel_case_json(tmp_path: Path) -> None:
    path = tmp_path / "state" / "settings.json"
    settings = DaemonSettings(remote_control_enabled=True)

    await settings.save(path)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "remoteControlEnabled": True
    }
    assert await DaemonSettings.load(path) == settings
    assert await DaemonSettings.load(tmp_path / "missing.json") == DaemonSettings()


def test_managed_install_path_version_identity_and_client_user_agent() -> None:
    expected_name = "codex.exe" if os.name == "nt" else "codex"
    assert managed_codex_bin(Path("/codex-home")) == (
        Path("/codex-home") / "packages" / "standalone" / "current" / expected_name
    )
    assert executable_identity_from_bytes(b"same") == executable_identity_from_bytes(
        b"same"
    )
    assert executable_identity_from_bytes(b"same") != executable_identity_from_bytes(
        b"different"
    )
    assert (
        parse_version_from_user_agent(
            "codex_app_server_daemon/1.2.3 (Linux) codex_cli_rs/1.2.3"
        )
        == "1.2.3"
    )
    with pytest.raises(ValueError, match="omitted version separator"):
        parse_version_from_user_agent("codex_app_server_daemon")


@pytest.mark.asyncio
async def test_pid_backend_command_args_and_stderr_tail_match_rust(
    tmp_path: Path,
) -> None:
    backend = PidBackend.new(
        Path("codex"),
        tmp_path / "app-server.pid",
        remote_control_enabled=True,
    )
    updater = PidBackend.new_update_loop(
        Path("codex"),
        tmp_path / "app-server-updater.pid",
    )

    assert backend.command_args() == (
        "app-server",
        "--remote-control",
        "--listen",
        "unix://",
    )
    assert updater.command_args() == (
        "app-server",
        "daemon",
        "pid-update-loop",
    )

    log_path = (tmp_path / "app-server.pid").with_suffix(".stderr.log")
    log_path.write_bytes(f"{'x' * 4100}\nrecent error\nusage".encode())
    tail = await read_stderr_log_tail(tmp_path / "app-server.pid")
    assert tail is not None
    assert tail.path == log_path
    assert tail.contents == "recent error\nusage"


class _FakeWebSocket:
    def __init__(self, incoming: list[dict[str, object]]) -> None:
        self.incoming = list(incoming)
        self.sent: list[dict[str, object]] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def recv(self) -> str:
        if not self.incoming:
            raise RuntimeError("no incoming message")
        return json.dumps(self.incoming.pop(0))

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_remote_control_client_waits_for_connected_notification() -> None:
    websocket = _FakeWebSocket(
        [
            {
                "id": 1,
                "result": {
                    "userAgent": "codex_app_server/1.2.3",
                    "codexHome": "/tmp/codex-home",
                    "platformFamily": "unix",
                    "platformOs": "linux",
                },
            },
            {
                "id": 2,
                "result": {
                    "status": "connecting",
                    "serverName": "test-host",
                    "installationId": "test-installation",
                    "environmentId": None,
                },
            },
            {
                "method": "remoteControl/status/changed",
                "params": {
                    "status": "connected",
                    "serverName": "test-host",
                    "installationId": "test-installation",
                    "environmentId": "env-test",
                },
            },
        ]
    )

    status = await enable_remote_control_with_timeout(websocket, ready_timeout=1.0)

    assert status == RemoteControlReadyStatus(
        status=RemoteControlConnectionStatus.CONNECTED,
        server_name="test-host",
        environment_id="env-test",
        timed_out=False,
    )
    assert [message.get("method") for message in websocket.sent] == [
        "initialize",
        "initialized",
        "remoteControl/enable",
    ]
    assert websocket.sent[0]["params"]["capabilities"]["experimentalApi"] is True
    assert websocket.closed


def test_lifecycle_platform_gate_matches_rust_cfg() -> None:
    if os.name == "nt":
        with pytest.raises(
            RuntimeError,
            match="codex app-server daemon lifecycle is only supported on Unix platforms",
        ):
            ensure_supported_platform()
    else:
        ensure_supported_platform()
