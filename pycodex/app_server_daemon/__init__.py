from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import time
from typing import Any

from pycodex import __version__
from pycodex.app_server_protocol import RemoteControlConnectionStatus
from pycodex.app_server_transport import app_server_control_socket_path
from pycodex.utils.home_dir import find_codex_home

from . import backend
from . import client
from . import remote_control_client
from .backend import BackendKind
from .backend import BackendPaths
from .managed_install import managed_codex_bin
from .managed_install import managed_codex_version
from .settings import DaemonSettings


START_POLL_INTERVAL = 0.05
START_TIMEOUT = 10.0
OPERATION_LOCK_TIMEOUT = 75.0
PID_FILE_NAME = "app-server.pid"
UPDATE_PID_FILE_NAME = "app-server-updater.pid"
OPERATION_LOCK_FILE_NAME = "daemon.lock"
SETTINGS_FILE_NAME = "settings.json"
STATE_DIR_NAME = "app-server-daemon"


class LifecycleCommand(str, Enum):
    START = "start"
    RESTART = "restart"
    STOP = "stop"
    VERSION = "version"


class LifecycleStatus(str, Enum):
    ALREADY_RUNNING = "alreadyRunning"
    STARTED = "started"
    RESTARTED = "restarted"
    STOPPED = "stopped"
    NOT_RUNNING = "notRunning"
    RUNNING = "running"


@dataclass(frozen=True)
class LifecycleOutput:
    status: LifecycleStatus
    backend: BackendKind | None
    pid: int | None
    managed_codex_path: Path
    managed_codex_version: str | None
    socket_path: Path
    cli_version: str | None
    app_server_version: str | None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "status": self.status.value,
            "managedCodexPath": str(self.managed_codex_path),
            "socketPath": str(self.socket_path),
        }
        _optional(value, "backend", None if self.backend is None else self.backend.value)
        _optional(value, "pid", self.pid)
        _optional(value, "managedCodexVersion", self.managed_codex_version)
        _optional(value, "cliVersion", self.cli_version)
        _optional(value, "appServerVersion", self.app_server_version)
        return value


@dataclass(frozen=True)
class BootstrapOptions:
    remote_control_enabled: bool


class BootstrapStatus(str, Enum):
    BOOTSTRAPPED = "bootstrapped"


@dataclass(frozen=True)
class BootstrapOutput:
    status: BootstrapStatus
    backend: BackendKind
    auto_update_enabled: bool
    remote_control_enabled: bool
    managed_codex_path: Path
    managed_codex_version: str | None
    socket_path: Path
    cli_version: str
    app_server_version: str

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "status": self.status.value,
            "backend": self.backend.value,
            "autoUpdateEnabled": self.auto_update_enabled,
            "remoteControlEnabled": self.remote_control_enabled,
            "managedCodexPath": str(self.managed_codex_path),
            "socketPath": str(self.socket_path),
            "cliVersion": self.cli_version,
            "appServerVersion": self.app_server_version,
        }
        _optional(value, "managedCodexVersion", self.managed_codex_version)
        return value


RemoteControlStartOutput = BootstrapOutput | LifecycleOutput


@dataclass(frozen=True)
class RemoteControlReadyStatus:
    status: RemoteControlConnectionStatus | str
    server_name: str
    environment_id: str | None
    timed_out: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "status",
            RemoteControlConnectionStatus.parse(self.status),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "serverName": self.server_name,
            "environmentId": self.environment_id,
            "timedOut": self.timed_out,
        }


@dataclass(frozen=True)
class RemoteControlReadyOutput:
    daemon: RemoteControlStartOutput
    remote_control: RemoteControlReadyStatus


class RemoteControlMode(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"

    def is_enabled(self) -> bool:
        return self is RemoteControlMode.ENABLED


class RemoteControlStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    ALREADY_ENABLED = "alreadyEnabled"
    ALREADY_DISABLED = "alreadyDisabled"


@dataclass(frozen=True)
class RemoteControlOutput:
    status: RemoteControlStatus
    backend: BackendKind | None
    remote_control_enabled: bool
    socket_path: Path
    cli_version: str
    app_server_version: str | None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "status": self.status.value,
            "remoteControlEnabled": self.remote_control_enabled,
            "socketPath": str(self.socket_path),
            "cliVersion": self.cli_version,
        }
        _optional(value, "backend", None if self.backend is None else self.backend.value)
        _optional(value, "appServerVersion", self.app_server_version)
        return value


class RestartIfRunningOutcome(str, Enum):
    BUSY = "busy"
    NOT_RUNNING = "notRunning"
    NOT_READY = "notReady"
    ALREADY_CURRENT = "alreadyCurrent"
    RESTARTED = "restarted"


class RestartMode(str, Enum):
    IF_VERSION_CHANGED = "ifVersionChanged"
    ALWAYS = "always"


class UpdaterRefreshMode(str, Enum):
    NONE = "none"
    REEXEC_IF_MANAGED_BINARY_CHANGED = "reexecIfManagedBinaryChanged"


class RestartDecision(str, Enum):
    NOT_READY = "notReady"
    ALREADY_CURRENT = "alreadyCurrent"
    RESTART = "restart"


def ensure_supported_platform() -> None:
    if os.name == "nt":
        raise RuntimeError(
            "codex app-server daemon lifecycle is only supported on Unix platforms"
        )


async def probe_app_server_version(socket_path: Path) -> str:
    return (await client.probe(socket_path)).app_server_version


async def run(command: LifecycleCommand) -> LifecycleOutput:
    ensure_supported_platform()
    return await Daemon.from_environment().run(command)


async def bootstrap(options: BootstrapOptions) -> BootstrapOutput:
    ensure_supported_platform()
    return await Daemon.from_environment().bootstrap(options)


async def ensure_remote_control_started() -> RemoteControlStartOutput:
    ensure_supported_platform()
    return await Daemon.from_environment().ensure_remote_control_started()


async def ensure_remote_control_ready() -> RemoteControlReadyOutput:
    ensure_supported_platform()
    return await Daemon.from_environment().ensure_remote_control_ready()


async def enable_remote_control_on_socket(
    socket_path: Path,
    connect_timeout: float,
    connect_retry_delay: float,
) -> RemoteControlReadyStatus:
    ensure_supported_platform()
    return await remote_control_client.enable_remote_control_with_connect_retry(
        socket_path,
        connect_timeout,
        connect_retry_delay,
    )


async def set_remote_control(mode: RemoteControlMode) -> RemoteControlOutput:
    ensure_supported_platform()
    return await Daemon.from_environment().set_remote_control(mode)


async def run_pid_update_loop() -> None:
    ensure_supported_platform()
    from . import update_loop

    await update_loop.run()


class Daemon:
    def __init__(
        self,
        *,
        socket_path: Path,
        pid_file: Path,
        update_pid_file: Path,
        operation_lock_file: Path,
        settings_file: Path,
        managed_codex_path: Path,
    ) -> None:
        self.socket_path = socket_path
        self.pid_file = pid_file
        self.update_pid_file = update_pid_file
        self.operation_lock_file = operation_lock_file
        self.settings_file = settings_file
        self.managed_codex_bin = managed_codex_path

    @classmethod
    def from_environment(cls) -> "Daemon":
        try:
            codex_home = Path(find_codex_home())
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"failed to resolve CODEX_HOME: {exc}") from exc
        state_dir = codex_home / STATE_DIR_NAME
        return cls(
            socket_path=app_server_control_socket_path(codex_home),
            pid_file=state_dir / PID_FILE_NAME,
            update_pid_file=state_dir / UPDATE_PID_FILE_NAME,
            operation_lock_file=state_dir / OPERATION_LOCK_FILE_NAME,
            settings_file=state_dir / SETTINGS_FILE_NAME,
            managed_codex_path=managed_codex_bin(codex_home),
        )

    async def run(self, command: LifecycleCommand) -> LifecycleOutput:
        if command is LifecycleCommand.VERSION:
            return await self.version()
        lock = await _OperationLock.acquire(
            self.operation_lock_file,
            OPERATION_LOCK_TIMEOUT,
        )
        try:
            if command is LifecycleCommand.START:
                return await self.start()
            if command is LifecycleCommand.RESTART:
                return await self.restart()
            if command is LifecycleCommand.STOP:
                return await self.stop()
        finally:
            lock.close()
        raise ValueError(f"unsupported lifecycle command: {command}")

    async def start(self) -> LifecycleOutput:
        settings = await self.load_settings()
        info = await _probe_or_none(self.socket_path)
        if info is not None:
            return await self.output(
                LifecycleStatus.ALREADY_RUNNING,
                await self.running_backend(settings),
                None,
                info.app_server_version,
            )
        running = await self.running_backend_instance(settings)
        if running is not None:
            info = await self.wait_until_ready()
            return await self.output(
                LifecycleStatus.ALREADY_RUNNING,
                BackendKind.PID,
                None,
                info.app_server_version,
            )
        self.ensure_managed_codex_bin()
        pid = await self.start_managed_backend(settings)
        info = await self.wait_until_ready()
        return await self.output(
            LifecycleStatus.STARTED,
            BackendKind.PID,
            pid,
            info.app_server_version,
        )

    async def restart(self) -> LifecycleOutput:
        settings = await self.load_settings()
        probe = await _probe_or_none(self.socket_path)
        running = await self.running_backend_instance(settings)
        if probe is not None and running is None:
            raise RuntimeError(
                "app server is running but is not managed by codex app-server daemon"
            )
        self.ensure_managed_codex_bin()
        if running is not None:
            await running.stop()
        pid = await self.start_managed_backend(settings)
        info = await self.wait_until_ready()
        return await self.output(
            LifecycleStatus.RESTARTED,
            BackendKind.PID,
            pid,
            info.app_server_version,
        )

    async def stop(self) -> LifecycleOutput:
        settings = await self.load_settings()
        running = await self.running_backend_instance(settings)
        if running is not None:
            await running.stop()
            return await self.output(
                LifecycleStatus.STOPPED,
                BackendKind.PID,
                None,
                None,
            )
        if await _probe_or_none(self.socket_path) is not None:
            raise RuntimeError(
                "app server is running but is not managed by codex app-server daemon"
            )
        return await self.output(
            LifecycleStatus.NOT_RUNNING,
            None,
            None,
            None,
        )

    async def version(self) -> LifecycleOutput:
        settings = await self.load_settings()
        info = await client.probe(self.socket_path)
        return await self.output(
            LifecycleStatus.RUNNING,
            await self.running_backend(settings),
            None,
            info.app_server_version,
        )

    async def bootstrap(self, options: BootstrapOptions) -> BootstrapOutput:
        lock = await _OperationLock.acquire(
            self.operation_lock_file,
            OPERATION_LOCK_TIMEOUT,
        )
        try:
            return await self.bootstrap_locked(options)
        finally:
            lock.close()

    async def bootstrap_locked(self, options: BootstrapOptions) -> BootstrapOutput:
        self.ensure_managed_codex_bin()
        settings = DaemonSettings(options.remote_control_enabled)
        probe = await _probe_or_none(self.socket_path)
        if probe is not None and await self.running_backend(settings) is None:
            raise RuntimeError(
                "app server is running but is not managed by codex app-server daemon"
            )
        await settings.save(self.settings_file)
        running = await self.running_backend_instance(settings)
        if running is not None:
            await running.stop()
        await backend.pid_backend(self.backend_paths(settings)).start()
        updater = backend.pid_update_loop_backend(self.backend_paths(settings))
        if await updater.is_starting_or_running():
            await updater.stop()
        await updater.start()
        info = await self.wait_until_ready()
        return BootstrapOutput(
            status=BootstrapStatus.BOOTSTRAPPED,
            backend=BackendKind.PID,
            auto_update_enabled=True,
            remote_control_enabled=settings.remote_control_enabled,
            managed_codex_path=self.managed_codex_bin,
            managed_codex_version=await self.managed_codex_version_best_effort(),
            socket_path=self.socket_path,
            cli_version=__version__,
            app_server_version=info.app_server_version,
        )

    async def ensure_remote_control_started(self) -> RemoteControlStartOutput:
        lock = await _OperationLock.acquire(
            self.operation_lock_file,
            OPERATION_LOCK_TIMEOUT,
        )
        try:
            settings = await self.load_settings()
            updater = backend.pid_update_loop_backend(self.backend_paths(settings))
            if await updater.is_starting_or_running():
                await self.set_remote_control_locked(RemoteControlMode.ENABLED)
                return await self.start()
            return await self.bootstrap_locked(BootstrapOptions(True))
        finally:
            lock.close()

    async def ensure_remote_control_ready(self) -> RemoteControlReadyOutput:
        daemon_output = await self.ensure_remote_control_started()
        ready = await remote_control_client.enable_remote_control(self.socket_path)
        return RemoteControlReadyOutput(daemon=daemon_output, remote_control=ready)

    async def set_remote_control(
        self,
        mode: RemoteControlMode,
    ) -> RemoteControlOutput:
        lock = await _OperationLock.acquire(
            self.operation_lock_file,
            OPERATION_LOCK_TIMEOUT,
        )
        try:
            return await self.set_remote_control_locked(mode)
        finally:
            lock.close()

    async def set_remote_control_locked(
        self,
        mode: RemoteControlMode,
    ) -> RemoteControlOutput:
        previous = await self.load_settings()
        running = await self.running_backend_instance(previous)
        if running is None and await _probe_or_none(self.socket_path) is not None:
            raise RuntimeError(
                "app server is running but is not managed by codex app-server daemon"
            )
        enabled = mode.is_enabled()
        if previous.remote_control_enabled == enabled:
            info = await self.wait_until_ready() if running is not None else None
            return self.remote_control_output(
                _already_remote_control_status(mode),
                BackendKind.PID if running is not None else None,
                enabled,
                None if info is None else info.app_server_version,
            )
        settings = DaemonSettings(enabled)
        await settings.save(self.settings_file)
        app_server_version: str | None = None
        if running is not None:
            self.ensure_managed_codex_bin()
            await running.stop()
            await self.start_managed_backend(settings)
            app_server_version = (await self.wait_until_ready()).app_server_version
        return self.remote_control_output(
            _remote_control_status(mode),
            BackendKind.PID if app_server_version is not None else None,
            enabled,
            app_server_version,
        )

    async def try_restart_if_running(
        self,
        mode: RestartMode,
        refresh_mode: UpdaterRefreshMode,
        managed_binary: Path,
    ) -> RestartIfRunningOutcome:
        lock = await _OperationLock.try_acquire(self.operation_lock_file)
        if lock is None:
            return RestartIfRunningOutcome.BUSY
        try:
            settings = await self.load_settings()
            running = await self.running_backend_instance(settings)
            if running is None:
                if await _probe_or_none(self.socket_path) is not None:
                    raise RuntimeError(
                        "app server is running but is not managed by "
                        "codex app-server daemon"
                    )
                return RestartIfRunningOutcome.NOT_RUNNING
            info = await _probe_or_none(self.socket_path)
            version = (
                await managed_codex_version(managed_binary)
                if info is not None
                else None
            )
            decision = restart_decision(mode, info, version)
            if decision is RestartDecision.NOT_READY:
                return RestartIfRunningOutcome.NOT_READY
            if decision is RestartDecision.ALREADY_CURRENT:
                return RestartIfRunningOutcome.ALREADY_CURRENT
            await running.stop()
            replacement = backend.pid_backend(
                self.backend_paths_with_bin(settings, managed_binary)
            )
            await replacement.start()
            await self.wait_until_ready()
            outcome = RestartIfRunningOutcome.RESTARTED
            if should_reexec_updater(refresh_mode, outcome):
                from .update_loop import reexec_managed_updater

                reexec_managed_updater(managed_binary)
            return outcome
        finally:
            lock.close()

    async def wait_until_ready(self) -> client.ProbeInfo:
        deadline = time.monotonic() + START_TIMEOUT
        while True:
            try:
                return await client.probe(self.socket_path)
            except Exception as exc:
                if time.monotonic() >= deadline:
                    context = await self.app_server_not_ready_context()
                    raise RuntimeError(f"{context}: {exc}") from exc
                await asyncio.sleep(START_POLL_INTERVAL)

    async def app_server_not_ready_context(self) -> str:
        version = await self.managed_codex_version_best_effort() or "unknown"
        context = (
            f"app server did not become ready on {self.socket_path}\n\n"
            "Daemon used app-server:\n"
            f"  path: {self.managed_codex_bin}\n"
            f"  version: {version}"
        )
        return await backend.append_stderr_log_tail_context(self.pid_file, context)

    async def running_backend(
        self,
        settings: DaemonSettings,
    ) -> BackendKind | None:
        instance = await self.running_backend_instance(settings)
        return BackendKind.PID if instance is not None else None

    async def running_backend_instance(
        self,
        settings: DaemonSettings,
    ) -> backend.PidBackend | None:
        instance = backend.pid_backend(self.backend_paths(settings))
        return instance if await instance.is_starting_or_running() else None

    async def start_managed_backend(self, settings: DaemonSettings) -> int | None:
        return await backend.pid_backend(self.backend_paths(settings)).start()

    def ensure_managed_codex_bin(self) -> None:
        if self.managed_codex_bin.is_file():
            return
        raise RuntimeError(
            "managed standalone Codex install not found at "
            f"{self.managed_codex_bin}\n\n"
            "This command requires the standalone install managed by the Codex "
            "installer, because the daemon starts and updates app-server from "
            "that fixed path.\n\n"
            "Install it with:\n  curl -fsSL https://chatgpt.com/codex/install.sh | sh\n\n"
            "Then rerun the command you just tried."
        )

    async def managed_codex_version_best_effort(self) -> str | None:
        try:
            return await managed_codex_version(self.managed_codex_bin)
        except Exception:
            return None

    def backend_paths(self, settings: DaemonSettings) -> BackendPaths:
        return self.backend_paths_with_bin(settings, self.managed_codex_bin)

    def backend_paths_with_bin(
        self,
        settings: DaemonSettings,
        managed_binary: Path,
    ) -> BackendPaths:
        return BackendPaths(
            codex_bin=managed_binary,
            pid_file=self.pid_file,
            update_pid_file=self.update_pid_file,
            remote_control_enabled=settings.remote_control_enabled,
        )

    async def load_settings(self) -> DaemonSettings:
        return await DaemonSettings.load(self.settings_file)

    async def output(
        self,
        status: LifecycleStatus,
        backend_kind: BackendKind | None,
        pid: int | None,
        app_server_version: str | None,
    ) -> LifecycleOutput:
        return LifecycleOutput(
            status=status,
            backend=backend_kind,
            pid=pid,
            managed_codex_path=self.managed_codex_bin,
            managed_codex_version=await self.managed_codex_version_best_effort(),
            socket_path=self.socket_path,
            cli_version=__version__,
            app_server_version=app_server_version,
        )

    def remote_control_output(
        self,
        status: RemoteControlStatus,
        backend_kind: BackendKind | None,
        enabled: bool,
        app_server_version: str | None,
    ) -> RemoteControlOutput:
        return RemoteControlOutput(
            status=status,
            backend=backend_kind,
            remote_control_enabled=enabled,
            socket_path=self.socket_path,
            cli_version=__version__,
            app_server_version=app_server_version,
        )


def restart_decision(
    mode: RestartMode,
    info: client.ProbeInfo | None,
    managed_version: str | None,
) -> RestartDecision:
    if mode is RestartMode.IF_VERSION_CHANGED and info is None:
        return RestartDecision.NOT_READY
    if (
        mode is RestartMode.IF_VERSION_CHANGED
        and info is not None
        and managed_version is not None
        and info.app_server_version == managed_version
    ):
        return RestartDecision.ALREADY_CURRENT
    return RestartDecision.RESTART


def should_reexec_updater(
    refresh_mode: UpdaterRefreshMode,
    outcome: RestartIfRunningOutcome,
) -> bool:
    return (
        refresh_mode is UpdaterRefreshMode.REEXEC_IF_MANAGED_BINARY_CHANGED
        and outcome is RestartIfRunningOutcome.RESTARTED
    )


def _remote_control_status(mode: RemoteControlMode) -> RemoteControlStatus:
    return (
        RemoteControlStatus.ENABLED
        if mode is RemoteControlMode.ENABLED
        else RemoteControlStatus.DISABLED
    )


def _already_remote_control_status(mode: RemoteControlMode) -> RemoteControlStatus:
    return (
        RemoteControlStatus.ALREADY_ENABLED
        if mode is RemoteControlMode.ENABLED
        else RemoteControlStatus.ALREADY_DISABLED
    )


async def _probe_or_none(socket_path: Path) -> client.ProbeInfo | None:
    try:
        return await client.probe(socket_path)
    except Exception:
        return None


class _OperationLock:
    def __init__(self, file: Any) -> None:
        self._file = file

    @classmethod
    async def acquire(cls, path: Path, timeout: float) -> "_OperationLock":
        deadline = time.monotonic() + timeout
        while True:
            lock = await cls.try_acquire(path)
            if lock is not None:
                return lock
            if time.monotonic() >= deadline:
                raise RuntimeError(f"timed out waiting for daemon operation lock {path}")
            await asyncio.sleep(START_POLL_INTERVAL)

    @classmethod
    async def try_acquire(cls, path: Path) -> "_OperationLock | None":
        return await asyncio.to_thread(cls._try_acquire_sync, path)

    @classmethod
    def _try_acquire_sync(cls, path: Path) -> "_OperationLock | None":
        if os.name == "nt":
            raise RuntimeError(
                "codex app-server daemon lifecycle is only supported on Unix platforms"
            )
        import fcntl

        path.parent.mkdir(parents=True, exist_ok=True)
        file = path.open("a+b")
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            file.close()
            return None
        return cls(file)

    def close(self) -> None:
        import fcntl

        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()


def _optional(target: dict[str, object], key: str, value: object | None) -> None:
    if value is not None:
        target[key] = value


__all__ = [
    "BackendKind",
    "BootstrapOptions",
    "BootstrapOutput",
    "BootstrapStatus",
    "Daemon",
    "LifecycleCommand",
    "LifecycleOutput",
    "LifecycleStatus",
    "RemoteControlMode",
    "RemoteControlOutput",
    "RemoteControlReadyOutput",
    "RemoteControlReadyStatus",
    "RemoteControlStartOutput",
    "RemoteControlStatus",
    "RestartDecision",
    "RestartIfRunningOutcome",
    "RestartMode",
    "UpdaterRefreshMode",
    "bootstrap",
    "enable_remote_control_on_socket",
    "ensure_remote_control_ready",
    "ensure_remote_control_started",
    "ensure_supported_platform",
    "probe_app_server_version",
    "restart_decision",
    "run",
    "run_pid_update_loop",
    "set_remote_control",
    "should_reexec_updater",
]
