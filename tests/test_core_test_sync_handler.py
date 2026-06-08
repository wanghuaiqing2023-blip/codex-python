import asyncio
import json
import unittest

from pycodex.core import (
    FunctionCallError,
    ToolPayload,
)
from pycodex.core.tools.handlers.test_sync import (
    BarrierArgs,
    DEFAULT_TEST_SYNC_TIMEOUT_MS,
    TEST_SYNC_TOOL_NAME,
    TestSyncArgs,
    TestSyncHandler,
    create_test_sync_tool,
    parse_test_sync_arguments,
    wait_on_barrier,
)
from pycodex.protocol import ToolName


class TestSyncHandlerTests(unittest.IsolatedAsyncioTestCase):
    def test_test_sync_tool_matches_expected_spec(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/test_sync_spec.rs
        # Rust test: test_sync_tool_matches_expected_spec
        spec = create_test_sync_tool()

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], TEST_SYNC_TOOL_NAME)
        self.assertEqual(
            spec["description"],
            "Internal synchronization helper used by Codex integration tests.",
        )
        self.assertFalse(spec["strict"])
        self.assertFalse(spec["parameters"]["additionalProperties"])
        self.assertIsNone(spec["parameters"].get("required"))
        self.assertEqual(
            spec["parameters"]["properties"]["sleep_before_ms"],
            {
                "type": "number",
                "description": "Optional delay in milliseconds before any other action",
            },
        )
        self.assertEqual(
            spec["parameters"]["properties"]["sleep_after_ms"],
            {
                "type": "number",
                "description": "Optional delay in milliseconds after completing the barrier",
            },
        )
        barrier = spec["parameters"]["properties"]["barrier"]
        self.assertEqual(barrier["type"], "object")
        self.assertFalse(barrier["additionalProperties"])
        self.assertEqual(
            barrier["required"],
            ["id", "participants"],
        )
        self.assertEqual(
            barrier["properties"],
            {
                "id": {
                    "type": "string",
                    "description": "Identifier shared by concurrent calls that should rendezvous",
                },
                "participants": {
                    "type": "number",
                    "description": "Number of tool calls that must arrive before the barrier opens",
                },
                "timeout_ms": {
                    "type": "number",
                    "description": "Maximum time in milliseconds to wait at the barrier",
                },
            },
        )

    def test_parse_test_sync_arguments(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/test_sync.rs
        # Rust contract: omitted barrier timeout defaults to DEFAULT_TEST_SYNC_TIMEOUT_MS.
        args = parse_test_sync_arguments(
            json.dumps(
                {
                    "sleep_before_ms": 1,
                    "sleep_after_ms": 2,
                    "barrier": {"id": "single", "participants": 1},
                }
            )
        )

        self.assertEqual(args.sleep_before_ms, 1)
        self.assertEqual(args.sleep_after_ms, 2)
        self.assertEqual(
            args.barrier,
            BarrierArgs("single", 1, DEFAULT_TEST_SYNC_TIMEOUT_MS),
        )

    async def test_handler_returns_ok_and_supports_parallel(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/test_sync.rs
        # Rust contract: handler returns successful "ok" output and supports parallel tool calls.
        handler = TestSyncHandler()

        output = await handler.handle(
            ToolPayload.function(
                json.dumps({"barrier": {"id": "handler-single", "participants": 1}})
            )
        )

        self.assertEqual(handler.tool_name(), ToolName.plain("test_sync_tool"))
        self.assertTrue(handler.supports_parallel_tool_calls())
        self.assertTrue(handler.matches_kind(ToolPayload.function("{}")))
        self.assertEqual(output.into_text(), "ok")

    async def test_barrier_validation_matches_rust_messages(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/test_sync.rs
        # Rust contract: invalid barrier participants/timeouts surface model-visible FunctionCallError messages.
        with self.assertRaises(FunctionCallError) as zero_participants:
            await wait_on_barrier(BarrierArgs("zero-participants", 0))
        self.assertIn("participants must be greater than zero", str(zero_participants.exception))

        with self.assertRaises(FunctionCallError) as zero_timeout:
            await wait_on_barrier(BarrierArgs("zero-timeout", 1, 0))
        self.assertIn("timeout must be greater than zero", str(zero_timeout.exception))

        with self.assertRaises(FunctionCallError) as timeout:
            await wait_on_barrier(BarrierArgs("timeout", 2, 1))
        self.assertEqual(str(timeout.exception), "test_sync_tool barrier wait timed out")

        waiting = asyncio.create_task(wait_on_barrier(BarrierArgs("mismatch", 2, 50)))
        await asyncio.sleep(0)
        with self.assertRaises(FunctionCallError) as existing:
            await wait_on_barrier(BarrierArgs("mismatch", 3, 50))
        self.assertIn("already registered with 2 participants", str(existing.exception))
        with self.assertRaises(FunctionCallError) as mismatch:
            await waiting
        self.assertEqual(str(mismatch.exception), "test_sync_tool barrier wait timed out")

    async def test_barrier_timeout_does_not_break_registered_barrier(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/test_sync.rs
        # Rust contract: timed-out waiters do not permanently poison a reusable barrier id.
        with self.assertRaises(FunctionCallError) as timeout:
            await wait_on_barrier(BarrierArgs("reusable-after-timeout", 2, 1))
        self.assertEqual(str(timeout.exception), "test_sync_tool barrier wait timed out")

        worker = asyncio.create_task(
            wait_on_barrier(BarrierArgs("reusable-after-timeout", 2, 100))
        )
        await asyncio.sleep(0)
        await wait_on_barrier(BarrierArgs("reusable-after-timeout", 2, 100))
        await worker

    async def test_handler_releases_concurrent_barrier_waiters(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/test_sync.rs
        # Rust contract: concurrent calls with the same id/participant count rendezvous and each returns "ok".
        handler = TestSyncHandler()
        payload = ToolPayload.function(
            json.dumps({"barrier": {"id": "handler-concurrent", "participants": 2}})
        )

        outputs = await asyncio.gather(handler.handle(payload), handler.handle(payload))

        self.assertEqual([output.into_text() for output in outputs], ["ok", "ok"])

    async def test_rejects_bad_payloads_and_non_rust_shapes(self) -> None:
        handler = TestSyncHandler()

        with self.assertRaises(FunctionCallError):
            await handler.handle(ToolPayload.custom("raw"))
        with self.assertRaises(FunctionCallError):
            await handler.handle(ToolPayload.function("{not json"))
        with self.assertRaises(TypeError):
            handler.matches_kind(object())
        with self.assertRaises(TypeError):
            parse_test_sync_arguments({})
        with self.assertRaises(TypeError):
            TestSyncArgs(sleep_before_ms=True)
        with self.assertRaises(ValueError):
            BarrierArgs("negative", -1)
        with self.assertRaises(TypeError):
            BarrierArgs(1, 1)


if __name__ == "__main__":
    unittest.main()
