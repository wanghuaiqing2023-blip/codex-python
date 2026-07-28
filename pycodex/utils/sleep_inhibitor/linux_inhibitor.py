"""Linux sleep inhibitor owned by ``linux_inhibitor.rs``."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum

ASSERTION_REASON = "Codex is running an active turn"
APP_ID = "codex"
BLOCKER_SLEEP_SECONDS = str(2**31 - 1)


class LinuxBackend(Enum):
    SYSTEMD_INHIBIT = "systemd-inhibit"
    GNOME_SESSION_INHIBIT = "gnome-session-inhibit"


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
        for backend in self._backend_order():
            try:
                child = subprocess.Popen(
                    _backend_command(backend),
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
            return [
                LinuxBackend.GNOME_SESSION_INHIBIT,
                LinuxBackend.SYSTEMD_INHIBIT,
            ]
        return [
            LinuxBackend.SYSTEMD_INHIBIT,
            LinuxBackend.GNOME_SESSION_INHIBIT,
        ]

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


def _backend_command(backend: LinuxBackend) -> list[str]:
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


SleepInhibitor = LinuxSleepInhibitor

__all__ = [
    "APP_ID",
    "ASSERTION_REASON",
    "BLOCKER_SLEEP_SECONDS",
    "LinuxBackend",
    "LinuxSleepInhibitor",
    "SleepInhibitor",
]
