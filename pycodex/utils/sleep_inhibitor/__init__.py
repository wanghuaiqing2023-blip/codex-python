"""Cross-platform helper for preventing idle sleep while a turn is running."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

ASSERTION_REASON = "Codex is running an active turn"
APP_ID = "codex"
BLOCKER_SLEEP_SECONDS = str(2**31 - 1)
ASSERTION_TYPE_PREVENT_USER_IDLE_SYSTEM_SLEEP = "PreventUserIdleSystemSleep"
K_IO_RETURN_SUCCESS = 0
K_IOPM_ASSERTION_LEVEL_OFF = 0
K_IOPM_ASSERTION_LEVEL_ON = 255
POWER_REQUEST_SYSTEM_REQUIRED = "PowerRequestSystemRequired"


class SleepInhibitorBackend(Protocol):
    def acquire(self) -> None: ...
    def release(self) -> None: ...


class LinuxBackend(Enum):
    SYSTEMD_INHIBIT = "systemd-inhibit"
    GNOME_SESSION_INHIBIT = "gnome-session-inhibit"


class DummySleepInhibitor:
    def acquire(self) -> None:
        return None

    def release(self) -> None:
        return None


class UnsupportedSleepInhibitor:
    def __init__(self, platform: str) -> None:
        self.platform = platform

    def acquire(self) -> None:
        raise NotImplementedError(f"sleep inhibitor backend is not implemented for {self.platform}")

    def release(self) -> None:
        return None


@dataclass(frozen=True)
class MacSleepAssertion:
    id: int

    @classmethod
    def create(cls, name: str) -> "MacSleepAssertion":
        del name
        raise OSError("macOS IOKit sleep assertions are not available in this Python backend")

    def release(self) -> None:
        return None


class MacSleepInhibitor:
    def __init__(
        self,
        assertion_factory: Callable[[str], MacSleepAssertion] | None = None,
    ) -> None:
        self.assertion: MacSleepAssertion | None = None
        self.assertion_factory = assertion_factory or MacSleepAssertion.create
        self.last_error: BaseException | None = None

    def acquire(self) -> None:
        if self.assertion is not None:
            return
        try:
            self.assertion = self.assertion_factory(ASSERTION_REASON)
            self.last_error = None
        except BaseException as exc:
            self.last_error = exc

    def release(self) -> None:
        assertion = self.assertion
        self.assertion = None
        if assertion is None:
            return
        try:
            assertion.release()
        except BaseException as exc:
            self.last_error = exc


@dataclass
class PowerRequest:
    handle: object
    request_type: str = POWER_REQUEST_SYSTEM_REQUIRED

    @classmethod
    def new_system_required(cls, reason: str) -> "PowerRequest":
        del reason
        raise OSError("Windows power requests are not available in this Python backend")

    def release(self) -> None:
        return None


class WindowsSleepInhibitor:
    def __init__(
        self,
        request_factory: Callable[[str], PowerRequest] | None = None,
    ) -> None:
        self.request: PowerRequest | None = None
        self.request_factory = request_factory or PowerRequest.new_system_required
        self.last_error: BaseException | None = None

    def acquire(self) -> None:
        if self.request is not None:
            return
        try:
            self.request = self.request_factory(ASSERTION_REASON)
            self.last_error = None
        except BaseException as exc:
            self.last_error = exc

    def release(self) -> None:
        request = self.request
        self.request = None
        if request is None:
            return
        try:
            request.release()
        except BaseException as exc:
            self.last_error = exc


@dataclass
class LinuxSleepInhibitor:
    preferred_backend: LinuxBackend | None = None
    missing_backend_logged: bool = False
    _child: subprocess.Popen[bytes] | None = None
    _active_backend: LinuxBackend | None = None

    def acquire(self) -> None:
        if self._child is not None and self._child.poll() is None:
            return
        self.release()
        backends = self._backend_order()
        for backend in backends:
            try:
                child = subprocess.Popen(
                    _linux_backend_command(backend),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                continue
            if child.poll() is None:
                self._child = child
                self._active_backend = backend
                self.preferred_backend = backend
                self.missing_backend_logged = False
                return
        self.missing_backend_logged = True

    def release(self) -> None:
        child = self._child
        self._child = None
        self._active_backend = None
        if child is None:
            return
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

    def _backend_order(self) -> list[LinuxBackend]:
        if self.preferred_backend is LinuxBackend.GNOME_SESSION_INHIBIT:
            return [LinuxBackend.GNOME_SESSION_INHIBIT, LinuxBackend.SYSTEMD_INHIBIT]
        return [LinuxBackend.SYSTEMD_INHIBIT, LinuxBackend.GNOME_SESSION_INHIBIT]

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


def _linux_backend_command(backend: LinuxBackend) -> list[str]:
    if backend is LinuxBackend.SYSTEMD_INHIBIT:
        return [
            "systemd-inhibit",
            "--what=idle",
            "--mode=block",
            "--who",
            APP_ID,
            "--why",
            ASSERTION_REASON,
            "--",
            "sleep",
            BLOCKER_SLEEP_SECONDS,
        ]
    return [
        "gnome-session-inhibit",
        "--inhibit",
        "idle",
        "--reason",
        ASSERTION_REASON,
        "sleep",
        BLOCKER_SLEEP_SECONDS,
    ]


class SleepInhibitor:
    def __init__(self, enabled: bool, platform_backend: SleepInhibitorBackend | None = None) -> None:
        self.enabled = bool(enabled)
        self.turn_running = False
        self.platform = platform_backend if platform_backend is not None else default_platform_backend()

    def set_turn_running(self, turn_running: bool) -> None:
        self.turn_running = bool(turn_running)
        if not self.enabled:
            self.release()
            return
        if self.turn_running:
            self.acquire()
        else:
            self.release()

    def acquire(self) -> None:
        self.platform.acquire()

    def release(self) -> None:
        self.platform.release()

    def is_turn_running(self) -> bool:
        return self.turn_running


def default_platform_backend() -> SleepInhibitorBackend:
    if sys.platform.startswith("linux"):
        return LinuxSleepInhibitor()
    if sys.platform == "darwin":
        return MacSleepInhibitor()
    if sys.platform.startswith("win"):
        return WindowsSleepInhibitor()
    return DummySleepInhibitor()


__all__ = [
    "APP_ID",
    "ASSERTION_REASON",
    "ASSERTION_TYPE_PREVENT_USER_IDLE_SYSTEM_SLEEP",
    "BLOCKER_SLEEP_SECONDS",
    "DummySleepInhibitor",
    "K_IOPM_ASSERTION_LEVEL_OFF",
    "K_IOPM_ASSERTION_LEVEL_ON",
    "K_IO_RETURN_SUCCESS",
    "LinuxBackend",
    "LinuxSleepInhibitor",
    "MacSleepAssertion",
    "MacSleepInhibitor",
    "POWER_REQUEST_SYSTEM_REQUIRED",
    "PowerRequest",
    "SleepInhibitor",
    "SleepInhibitorBackend",
    "UnsupportedSleepInhibitor",
    "WindowsSleepInhibitor",
    "default_platform_backend",
]
