"""Rust parity tests for ``codex-app-server/src/request_processors/command_exec_processor.rs``."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.app_server.command_exec import CommandExecManager
from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server.request_processors_command_exec_processor import (
    CommandExecRequestProcessor,
    CommandExecRequestProcessorError,
)
from pycodex.app_server_protocol import (
    CommandExecParams,
    CommandExecTerminalSize,
    CommandExecWriteParams,
)


class EnvironmentManager:
    def __init__(self, local=True) -> None:
        self.local = local

    def try_local_environment(self):
        return object() if self.local else None


class ConfigManager:
    def __init__(self) -> None:
        self.overrides = None
        self.loaded_config = SimpleNamespace(
            permissions={
                "effective_permission_profile": "loaded-profile",
                "network": None,
                "permission_profile": "loaded-permission-profile",
            },
            startup_warnings=[],
            managed_network_requirements_enabled=False,
        )

    def load_for_cwd(self, request_overrides, overrides, fallback_cwd):
        self.overrides = (request_overrides, overrides, fallback_cwd)
        return self.loaded_config


def make_processor(**overrides):
    config = SimpleNamespace(
        cwd=Path("C:/work"),
        env={"KEEP": "1", "DROP": "old"},
        permissions={
            "effective_permission_profile": "profile",
            "network": None,
            "permission_profile": "permission-profile",
        },
        managed_network_requirements_enabled=False,
    )
    return CommandExecRequestProcessor(
        arg0_paths=SimpleNamespace(codex_linux_sandbox_exe="sandbox"),
        config=overrides.get("config", config),
        outgoing=object(),
        config_manager=overrides.get("config_manager", ConfigManager()),
        environment_manager=overrides.get("environment_manager", EnvironmentManager()),
        command_exec_manager=overrides.get("manager", CommandExecManager()),
        exec_request_builder=overrides.get("exec_request_builder"),
    )


def request_id() -> ConnectionRequestId:
    return ConnectionRequestId(connection_id=7, request_id=1)


def raw_params(**overrides):
    values = {
        "command": ("echo",),
        "process_id": None,
        "tty": False,
        "stream_stdin": False,
        "stream_stdout_stderr": False,
        "output_bytes_cap": None,
        "disable_output_cap": False,
        "disable_timeout": False,
        "timeout_ms": None,
        "cwd": None,
        "env": None,
        "size": None,
        "sandbox_policy": None,
        "permission_profile": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def assert_error(excinfo, message: str) -> None:
    assert excinfo.value.error.message == message


def test_one_off_requires_local_environment_like_rust() -> None:
    processor = make_processor(environment_manager=EnvironmentManager(local=False))

    with pytest.raises(CommandExecRequestProcessorError) as excinfo:
        asyncio.run(processor.one_off_command_exec(request_id(), CommandExecParams(command=("echo",))))

    assert_error(excinfo, "local environment is not configured")


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (raw_params(command=()), "command must not be empty"),
        (
            CommandExecParams(command=("echo",), sandbox_policy={"type": "read-only"}, permission_profile="workspace"),
            "`permissionProfile` cannot be combined with `sandboxPolicy`",
        ),
        (
            CommandExecParams(command=("echo",), size=CommandExecTerminalSize(rows=24, cols=80)),
            "command/exec size requires tty: true",
        ),
        (
            CommandExecParams(command=("echo",), output_bytes_cap=10, disable_output_cap=True),
            "command/exec cannot set both outputBytesCap and disableOutputCap",
        ),
        (
            CommandExecParams(command=("echo",), timeout_ms=10, disable_timeout=True),
            "command/exec cannot set both timeoutMs and disableTimeout",
        ),
        (
            CommandExecParams(command=("echo",), timeout_ms=-1),
            "command/exec timeoutMs must be non-negative, got -1",
        ),
    ],
)
def test_one_off_validates_rust_request_conflicts(params, message) -> None:
    processor = make_processor()

    with pytest.raises(CommandExecRequestProcessorError) as excinfo:
        asyncio.run(processor.one_off_command_exec(request_id(), params))

    assert_error(excinfo, message)


def test_one_off_projects_cwd_env_timeout_capture_and_manager_start() -> None:
    manager = CommandExecManager()
    processor = make_processor(manager=manager)

    projection = asyncio.run(
        processor.exec_one_off_command_inner(
            request_id(),
            CommandExecParams(
                command=("python", "--version"),
                process_id="proc-1",
                cwd="subdir",
                env={"DROP": None, "NEW": "2"},
                timeout_ms=500,
                output_bytes_cap=42,
            ),
        )
    )

    assert projection.cwd == Path("C:/work") / "subdir"
    assert projection.env == {"KEEP": "1", "NEW": "2"}
    assert projection.expiration.kind == "Timeout"
    assert projection.expiration.timeout_ms == 500
    assert projection.capture_policy == "ShellTool"
    assert projection.output_bytes_cap == 42
    assert manager.session_for(7, "proc-1") is not None


def test_disable_output_and_timeout_project_full_buffer_and_cancellation() -> None:
    processor = make_processor()

    projection = asyncio.run(
        processor.build_one_off_projection(
            CommandExecParams(command=("cat",), disable_output_cap=True, disable_timeout=True)
        )
    )

    assert projection.output_bytes_cap is None
    assert projection.capture_policy == "FullBuffer"
    assert projection.expiration.kind == "Cancellation"


def test_permission_profile_loads_cwd_config_and_maps_disallowed_warning() -> None:
    config_manager = ConfigManager()
    processor = make_processor(config_manager=config_manager)

    projection = asyncio.run(
        processor.build_one_off_projection(
            CommandExecParams(command=("echo",), cwd="nested", permission_profile="workspace")
        )
    )

    assert config_manager.overrides[1].default_permissions == "workspace"
    assert config_manager.overrides[1].cwd == Path("C:/work") / "nested"
    assert projection.sandbox_cwd == Path("C:/work") / "nested"
    assert projection.effective_permission_profile == "loaded-profile"

    config_manager.loaded_config.startup_warnings = [
        "Configured value for `permission_profile` is disallowed by policy",
    ]
    with pytest.raises(CommandExecRequestProcessorError) as excinfo:
        asyncio.run(
            processor.build_one_off_projection(
                CommandExecParams(command=("echo",), permission_profile="danger-full-access")
            )
        )

    assert "invalid permission profile: Configured value" in excinfo.value.error.message


def test_sandbox_policy_validation_errors_are_invalid_request() -> None:
    class Permissions:
        network = None

        def can_set_legacy_sandbox_policy(self, _policy, _cwd):
            raise ValueError("blocked")

    config = SimpleNamespace(cwd=Path("C:/work"), env={}, permissions=Permissions())
    processor = make_processor(config=config)

    with pytest.raises(CommandExecRequestProcessorError) as excinfo:
        asyncio.run(
            processor.build_one_off_projection(
                CommandExecParams(command=("echo",), sandbox_policy={"type": "read-only"})
            )
        )

    assert_error(excinfo, "invalid sandbox policy: blocked")


def test_network_proxy_and_exec_builder_errors_map_to_internal_error() -> None:
    class Network:
        def start_proxy(self, *_args):
            raise RuntimeError("proxy down")

    config = SimpleNamespace(
        cwd=Path("C:/work"),
        env={},
        permissions={"effective_permission_profile": "profile", "network": Network(), "permission_profile": "profile"},
    )
    processor = make_processor(config=config)

    with pytest.raises(CommandExecRequestProcessorError) as excinfo:
        asyncio.run(processor.build_one_off_projection(CommandExecParams(command=("echo",))))

    assert_error(excinfo, "failed to start managed network proxy: proxy down")

    processor = make_processor(exec_request_builder=lambda *_args: (_ for _ in ()).throw(RuntimeError("bad exec")))
    with pytest.raises(CommandExecRequestProcessorError) as excinfo:
        asyncio.run(processor.one_off_command_exec(request_id(), CommandExecParams(command=("echo",))))

    assert_error(excinfo, "exec failed: bad exec")


def test_control_methods_delegate_to_command_exec_manager_errors() -> None:
    processor = make_processor()

    with pytest.raises(CommandExecRequestProcessorError) as excinfo:
        asyncio.run(
            processor.command_exec_write(
                request_id(),
                CommandExecWriteParams(process_id="missing", close_stdin=True),
            )
        )

    assert_error(excinfo, 'command/exec "missing" is no longer running')
