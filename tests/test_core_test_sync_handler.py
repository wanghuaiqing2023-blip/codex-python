import json
import threading
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


class TestSyncHandlerTests(unittest.TestCase):
    def test_test_sync_tool_matches_expected_spec(self) -> None:
        spec = create_test_sync_tool()

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], TEST_SYNC_TOOL_NAME)
        self.assertFalse(spec["strict"])
        self.assertIn("sleep_before_ms", spec["parameters"]["properties"])
        self.assertIn("sleep_after_ms", spec["parameters"]["properties"])
        self.assertEqual(
            spec["parameters"]["properties"]["barrier"]["required"],
            ["id", "participants"],
        )

    def test_parse_test_sync_arguments(self) -> None:
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

    def test_handler_returns_ok_and_supports_parallel(self) -> None:
        handler = TestSyncHandler()

        output = handler.handle(
            ToolPayload.function(
                json.dumps({"barrier": {"id": "handler-single", "participants": 1}})
            )
        )

        self.assertEqual(handler.tool_name(), ToolName.plain("test_sync_tool"))
        self.assertTrue(handler.supports_parallel_tool_calls())
        self.assertTrue(handler.matches_kind(ToolPayload.function("{}")))
        self.assertEqual(output.into_text(), "ok")

    def test_barrier_validation_matches_rust_messages(self) -> None:
        with self.assertRaises(FunctionCallError) as zero_participants:
            wait_on_barrier(BarrierArgs("zero-participants", 0))
        self.assertIn("participants must be greater than zero", str(zero_participants.exception))

        with self.assertRaises(FunctionCallError) as zero_timeout:
            wait_on_barrier(BarrierArgs("zero-timeout", 1, 0))
        self.assertIn("timeout must be greater than zero", str(zero_timeout.exception))

        with self.assertRaises(FunctionCallError) as timeout:
            wait_on_barrier(BarrierArgs("timeout", 2, 1))
        self.assertEqual(str(timeout.exception), "test_sync_tool barrier wait timed out")

        with self.assertRaises(FunctionCallError) as mismatch:
            wait_on_barrier(BarrierArgs("mismatch", 2, 50))
        self.assertEqual(str(mismatch.exception), "test_sync_tool barrier wait timed out")
        with self.assertRaises(FunctionCallError) as existing:
            wait_on_barrier(BarrierArgs("mismatch", 3, 50))
        self.assertIn("already registered with 2 participants", str(existing.exception))

    def test_barrier_timeout_does_not_break_registered_barrier(self) -> None:
        with self.assertRaises(FunctionCallError) as timeout:
            wait_on_barrier(BarrierArgs("reusable-after-timeout", 2, 1))
        self.assertEqual(str(timeout.exception), "test_sync_tool barrier wait timed out")

        results: list[str] = []
        errors: list[BaseException] = []

        def wait_later() -> None:
            try:
                wait_on_barrier(BarrierArgs("reusable-after-timeout", 2, 100))
                results.append("ok")
            except BaseException as err:
                errors.append(err)

        worker = threading.Thread(target=wait_later)
        worker.start()
        wait_on_barrier(BarrierArgs("reusable-after-timeout", 2, 100))
        worker.join()

        self.assertEqual(results, ["ok"])
        self.assertEqual(errors, [])

    def test_rejects_bad_payloads_and_non_rust_shapes(self) -> None:
        handler = TestSyncHandler()

        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.custom("raw"))
        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.function("{not json"))
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
