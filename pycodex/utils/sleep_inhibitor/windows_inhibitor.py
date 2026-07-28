"""Windows sleep inhibitor owned by ``windows_inhibitor.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

ASSERTION_REASON = "Codex is running an active turn"
POWER_REQUEST_SYSTEM_REQUIRED = "PowerRequestSystemRequired"


@dataclass
class PowerRequest:
    handle: object
    request_type: str = POWER_REQUEST_SYSTEM_REQUIRED

    @classmethod
    def new_system_required(cls, reason: str) -> "PowerRequest":
        del reason
        raise OSError(
            "Windows power requests are not available in this Python backend"
        )

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


SleepInhibitor = WindowsSleepInhibitor

__all__ = [
    "ASSERTION_REASON",
    "POWER_REQUEST_SYSTEM_REQUIRED",
    "PowerRequest",
    "SleepInhibitor",
    "WindowsSleepInhibitor",
]
