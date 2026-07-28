"""macOS sleep inhibitor owned by ``macos.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

ASSERTION_REASON = "Codex is running an active turn"
ASSERTION_TYPE_PREVENT_USER_IDLE_SYSTEM_SLEEP = "PreventUserIdleSystemSleep"


@dataclass(frozen=True)
class MacSleepAssertion:
    id: int

    @classmethod
    def create(cls, name: str) -> "MacSleepAssertion":
        del name
        raise OSError(
            "macOS IOKit sleep assertions are not available in this Python backend"
        )

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


SleepInhibitor = MacSleepInhibitor

__all__ = [
    "ASSERTION_REASON",
    "ASSERTION_TYPE_PREVENT_USER_IDLE_SYSTEM_SLEEP",
    "MacSleepAssertion",
    "MacSleepInhibitor",
    "SleepInhibitor",
]
