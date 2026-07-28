"""Cross-platform helper for preventing idle sleep while a turn is running."""

from __future__ import annotations

import sys
from typing import Protocol


class SleepInhibitorBackend(Protocol):
    def acquire(self) -> None: ...
    def release(self) -> None: ...


class SleepInhibitor:
    def __init__(
        self,
        enabled: bool,
        platform_backend: SleepInhibitorBackend | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.turn_running = False
        self.platform = (
            platform_backend
            if platform_backend is not None
            else _default_platform_backend()
        )

    def set_turn_running(self, turn_running: bool) -> None:
        self.turn_running = bool(turn_running)
        if not self.enabled:
            self.release()
        elif self.turn_running:
            self.acquire()
        else:
            self.release()

    def acquire(self) -> None:
        self.platform.acquire()

    def release(self) -> None:
        self.platform.release()

    def is_turn_running(self) -> bool:
        return self.turn_running


def _default_platform_backend() -> SleepInhibitorBackend:
    if sys.platform.startswith("linux"):
        from .linux_inhibitor import SleepInhibitor as PlatformSleepInhibitor
    elif sys.platform == "darwin":
        from .macos import SleepInhibitor as PlatformSleepInhibitor
    elif sys.platform.startswith("win"):
        from .windows_inhibitor import SleepInhibitor as PlatformSleepInhibitor
    else:
        from .dummy import SleepInhibitor as PlatformSleepInhibitor
    return PlatformSleepInhibitor()


__all__ = ["SleepInhibitor"]
