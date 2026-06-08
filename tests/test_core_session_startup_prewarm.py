import asyncio
import time
import unittest

from pycodex.core.session_startup_prewarm import (
    STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC,
    STARTUP_PREWARM_DURATION_METRIC,
    CancellationToken,
    SessionStartupPrewarmHandle,
    SessionTelemetryRecorder,
    schedule_startup_prewarm,
    unavailable_startup_prewarm_not_scheduled,
)


class SessionStartupPrewarmTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_ready_consumes_completed_task(self) -> None:
        telemetry = SessionTelemetryRecorder()
        task = asyncio.create_task(_return("session"))
        await task
        handle = SessionStartupPrewarmHandle.new(task, started_at=time.monotonic(), timeout=1.0)

        resolution = await handle.resolve(telemetry)

        self.assertEqual(resolution.type, "ready")
        self.assertEqual(resolution.prewarmed_session, "session")
        self.assertIn(("startup_prewarm_resolve", telemetry.startup_phases[0][1], "ready"), telemetry.startup_phases)
        self.assertEqual(telemetry.durations[0][0], STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC)
        self.assertEqual(telemetry.durations[0][2], (("status", "consumed"),))

    async def test_resolve_failed_task_reports_failed_unavailable(self) -> None:
        telemetry = SessionTelemetryRecorder()
        task = asyncio.create_task(_raise())
        with self.assertRaises(RuntimeError):
            await task
        handle = SessionStartupPrewarmHandle.new(task, started_at=time.monotonic(), timeout=1.0)

        resolution = await handle.resolve(telemetry)

        self.assertEqual(resolution.type, "unavailable")
        self.assertEqual(resolution.status, "failed")
        self.assertEqual(telemetry.startup_phases[0][2], "failed")

    async def test_resolve_timeout_aborts_task_and_records_duration(self) -> None:
        telemetry = SessionTelemetryRecorder()
        task = asyncio.create_task(asyncio.sleep(10))
        handle = SessionStartupPrewarmHandle.new(task, started_at=time.monotonic(), timeout=0.001)

        resolution = await handle.resolve(telemetry)

        self.assertEqual(resolution.type, "unavailable")
        self.assertEqual(resolution.status, "timed_out")
        self.assertTrue(task.cancelled())
        self.assertEqual(telemetry.durations[-1][0], STARTUP_PREWARM_DURATION_METRIC)
        self.assertEqual(telemetry.durations[-1][2], (("status", "timed_out"),))

    async def test_resolve_cancelled_token_aborts_task_and_returns_cancelled(self) -> None:
        telemetry = SessionTelemetryRecorder()
        token = CancellationToken()
        task = asyncio.create_task(asyncio.sleep(10))
        handle = SessionStartupPrewarmHandle.new(task, started_at=time.monotonic(), timeout=1.0)
        token.cancel()

        resolution = await handle.resolve(telemetry, token)

        self.assertEqual(resolution.type, "cancelled")
        self.assertTrue(task.cancelled())
        self.assertEqual(telemetry.startup_phases[0][2], "cancelled")

    async def test_schedule_startup_prewarm_records_total_ready_status(self) -> None:
        telemetry = SessionTelemetryRecorder()

        handle = await schedule_startup_prewarm(lambda: _return("session"), telemetry, timeout=1.0)
        resolution = await handle.resolve(telemetry)

        self.assertEqual(resolution.type, "ready")
        self.assertTrue(any(phase[0] == "startup_prewarm_total" and phase[2] == "ready" for phase in telemetry.startup_phases))
        self.assertTrue(any(duration[0] == STARTUP_PREWARM_DURATION_METRIC for duration in telemetry.durations))

    async def test_scheduled_prewarm_timeout_aborts_without_total_phase(self) -> None:
        # Rust source: codex-rs/core/src/session_startup_prewarm.rs
        # Behavior anchor: resolve timeout aborts the prewarm task and records
        # timed_out resolve telemetry; the aborted startup task does not record
        # a startup_prewarm_total ready/failed phase.
        telemetry = SessionTelemetryRecorder()
        handle = await schedule_startup_prewarm(lambda: asyncio.sleep(10), telemetry, timeout=0.001)

        resolution = await handle.resolve(telemetry)

        self.assertEqual(resolution.type, "unavailable")
        self.assertEqual(resolution.status, "timed_out")
        self.assertTrue(handle.task.cancelled())
        self.assertFalse(any(phase[0] == "startup_prewarm_total" for phase in telemetry.startup_phases))
        self.assertTrue(any(phase[0] == "startup_prewarm_resolve" and phase[2] == "timed_out" for phase in telemetry.startup_phases))

    async def test_unavailable_not_scheduled_helper(self) -> None:
        resolution = unavailable_startup_prewarm_not_scheduled()

        self.assertEqual(resolution.type, "unavailable")
        self.assertEqual(resolution.status, "not_scheduled")


async def _return(value: object) -> object:
    return value


async def _raise() -> object:
    raise RuntimeError("boom")


if __name__ == "__main__":
    unittest.main()
