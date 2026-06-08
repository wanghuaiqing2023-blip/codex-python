"""Startup prewarm task resolution helpers.

Ported from the task-state and telemetry boundary portions of
``codex/codex-rs/core/src/session_startup_prewarm.rs``. Prompt construction,
tool building, model-client sessions, and websocket warmup remain injected
runtime responsibilities.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC = "codex.startup_prewarm.age_at_first_turn_ms"
STARTUP_PREWARM_DURATION_METRIC = "codex.startup_prewarm.duration_ms"


@dataclass(frozen=True)
class SessionStartupPrewarmResolution:
    type: str
    prewarmed_session: Any | None = None
    status: str | None = None
    prewarm_duration: float | None = None

    @classmethod
    def cancelled(cls) -> "SessionStartupPrewarmResolution":
        return cls("cancelled")

    @classmethod
    def ready(cls, prewarmed_session: Any) -> "SessionStartupPrewarmResolution":
        return cls("ready", prewarmed_session=prewarmed_session)

    @classmethod
    def unavailable(
        cls,
        status: str,
        prewarm_duration: float | None = None,
    ) -> "SessionStartupPrewarmResolution":
        return cls("unavailable", status=status, prewarm_duration=prewarm_duration)


@dataclass
class SessionTelemetryRecorder:
    startup_phases: list[tuple[str, float, str | None]]
    durations: list[tuple[str, float, tuple[tuple[str, str], ...]]]

    def __init__(self) -> None:
        self.startup_phases = []
        self.durations = []

    def record_startup_phase(self, name: str, duration: float, status: str | None = None) -> None:
        self.startup_phases.append((name, duration, status))

    def record_duration(
        self,
        metric: str,
        duration: float,
        tags: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    ) -> None:
        self.durations.append((metric, duration, tuple(tags)))


@dataclass
class SessionStartupPrewarmHandle:
    task: asyncio.Task[Any]
    started_at: float
    timeout: float

    @classmethod
    def new(
        cls,
        task: asyncio.Task[Any],
        started_at: float | None = None,
        timeout: float = 0.0,
    ) -> "SessionStartupPrewarmHandle":
        if not isinstance(task, asyncio.Task):
            raise TypeError("task must be an asyncio.Task")
        if timeout < 0:
            raise ValueError("timeout must be non-negative")
        return cls(task=task, started_at=time.monotonic() if started_at is None else started_at, timeout=timeout)

    async def resolve(
        self,
        session_telemetry: Any,
        cancellation_token: "CancellationToken | None" = None,
    ) -> SessionStartupPrewarmResolution:
        resolve_started_at = time.monotonic()
        age_at_first_turn = max(time.monotonic() - self.started_at, 0.0)
        remaining = max(self.timeout - age_at_first_turn, 0.0)

        if self.task.done():
            resolution = resolution_from_task_result(self.task, self.started_at)
        else:
            cancellation_task = None
            wait_tasks: set[asyncio.Task[Any]] = {self.task}
            if cancellation_token is not None:
                cancellation_task = asyncio.create_task(cancellation_token.cancelled())
                wait_tasks.add(cancellation_task)
            done, pending = await asyncio.wait(wait_tasks, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            if cancellation_task is not None and cancellation_task in done:
                self.task.cancel()
                await _drain_cancelled_task(self.task)
                for pending_task in pending:
                    pending_task.cancel()
                _record_startup_phase(session_telemetry, "startup_prewarm_resolve", time.monotonic() - resolve_started_at, "cancelled")
                _record_duration(session_telemetry, STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC, age_at_first_turn, (("status", "cancelled"),))
                _record_duration(session_telemetry, STARTUP_PREWARM_DURATION_METRIC, time.monotonic() - self.started_at, (("status", "cancelled"),))
                return SessionStartupPrewarmResolution.cancelled()
            if self.task in done:
                if cancellation_task is not None:
                    cancellation_task.cancel()
                resolution = resolution_from_task_result(self.task, self.started_at)
            else:
                self.task.cancel()
                await _drain_cancelled_task(self.task)
                if cancellation_task is not None:
                    cancellation_task.cancel()
                resolution = SessionStartupPrewarmResolution.unavailable("timed_out", time.monotonic() - self.started_at)

        status = _resolution_status(resolution)
        _record_startup_phase(session_telemetry, "startup_prewarm_resolve", time.monotonic() - resolve_started_at, status)

        if resolution.type == "ready":
            _record_duration(session_telemetry, STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC, age_at_first_turn, (("status", "consumed"),))
            return resolution
        if resolution.type == "unavailable":
            _record_duration(session_telemetry, STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC, age_at_first_turn, (("status", resolution.status or "unavailable"),))
            if resolution.prewarm_duration is not None:
                _record_duration(session_telemetry, STARTUP_PREWARM_DURATION_METRIC, resolution.prewarm_duration, (("status", resolution.status or "unavailable"),))
        return resolution


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    async def cancelled(self) -> None:
        await self._event.wait()


async def schedule_startup_prewarm(
    prewarm: Callable[[], Awaitable[Any]],
    session_telemetry: Any,
    timeout: float,
) -> SessionStartupPrewarmHandle:
    if not callable(prewarm):
        raise TypeError("prewarm must be callable")
    started_at = time.monotonic()

    async def run() -> Any:
        status: str | None = None
        try:
            result = await prewarm()
            status = "ready"
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            status = "failed"
            raise
        finally:
            if status is not None:
                elapsed = time.monotonic() - started_at
                _record_startup_phase(session_telemetry, "startup_prewarm_total", elapsed, status)
                _record_duration(session_telemetry, STARTUP_PREWARM_DURATION_METRIC, elapsed, (("status", status),))

    return SessionStartupPrewarmHandle.new(asyncio.create_task(run()), started_at, timeout)


async def _drain_cancelled_task(task: asyncio.Task[Any]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        return
    except Exception:
        return
    await asyncio.sleep(0)


def unavailable_startup_prewarm_not_scheduled() -> SessionStartupPrewarmResolution:
    return SessionStartupPrewarmResolution.unavailable("not_scheduled")


def resolution_from_task_result(
    task: asyncio.Task[Any],
    started_at: float,
) -> SessionStartupPrewarmResolution:
    if not isinstance(task, asyncio.Task):
        raise TypeError("task must be an asyncio.Task")
    if not task.done():
        raise ValueError("task must be done")
    if task.cancelled():
        return SessionStartupPrewarmResolution.unavailable("join_failed", time.monotonic() - started_at)
    try:
        return SessionStartupPrewarmResolution.ready(task.result())
    except Exception:
        return SessionStartupPrewarmResolution.unavailable("failed")


def _resolution_status(resolution: SessionStartupPrewarmResolution) -> str:
    if resolution.type == "cancelled":
        return "cancelled"
    if resolution.type == "ready":
        return "ready"
    return resolution.status or "unavailable"


def _record_startup_phase(telemetry: Any, name: str, duration: float, status: str | None) -> None:
    recorder = getattr(telemetry, "record_startup_phase", None)
    if callable(recorder):
        recorder(name, duration, status)


def _record_duration(telemetry: Any, metric: str, duration: float, tags: tuple[tuple[str, str], ...]) -> None:
    recorder = getattr(telemetry, "record_duration", None)
    if callable(recorder):
        recorder(metric, duration, tags)


__all__ = [
    "STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC",
    "STARTUP_PREWARM_DURATION_METRIC",
    "CancellationToken",
    "SessionStartupPrewarmHandle",
    "SessionStartupPrewarmResolution",
    "SessionTelemetryRecorder",
    "resolution_from_task_result",
    "schedule_startup_prewarm",
    "unavailable_startup_prewarm_not_scheduled",
]
