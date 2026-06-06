import asyncio
import unittest

from pycodex.core import (
    ExtensionToolCallSource,
    ToolCallOutcome,
    ToolCallSource,
    ToolFinishInput,
    ToolInvocation,
    ToolPayload,
    ToolStartInput,
    extension_tool_call_source,
    notify_tool_aborted,
    notify_tool_aborted_parts,
    notify_tool_finish,
    notify_tool_finish_parts,
    notify_tool_start,
    tool_finish_input,
    tool_finish_input_parts,
    tool_start_input,
)
from pycodex.core.tools.lifecycle import lifecycle_store_context
from pycodex.protocol import ToolName


class RecordingContributor:
    def __init__(self) -> None:
        self.started = []
        self.finished = []

    async def on_tool_start(self, value):
        self.started.append(value)

    def on_tool_finish(self, value):
        self.finished.append(value)


class ToolLifecycleTests(unittest.TestCase):
    def test_extension_tool_call_source_maps_direct_and_code_mode(self) -> None:
        # Rust parity: codex-core::tools::lifecycle
        # lifecycle.rs::extension_tool_call_source.
        self.assertEqual(
            extension_tool_call_source(ToolCallSource.direct()),
            ExtensionToolCallSource.direct(),
        )
        self.assertEqual(
            extension_tool_call_source(ToolCallSource.code_mode("cell-1", "tool-1")),
            ExtensionToolCallSource.code_mode("cell-1", "tool-1"),
        )

    def test_tool_call_outcome_variants_match_extension_api_shape(self) -> None:
        self.assertEqual(ToolCallOutcome.completed(True).success, True)
        self.assertEqual(ToolCallOutcome.failed(False).handler_executed, False)
        self.assertEqual(ToolCallOutcome.blocked().type, "blocked")
        self.assertEqual(ToolCallOutcome.aborted().type, "aborted")
        with self.assertRaises(TypeError):
            ToolCallOutcome.completed(1)
        with self.assertRaises(TypeError):
            ToolCallOutcome.failed("yes")
        with self.assertRaises(ValueError):
            ToolCallOutcome("other")

    def test_start_and_finish_inputs_copy_invocation_fields(self) -> None:
        # Rust parity: codex-core::tools::lifecycle
        # lifecycle.rs::notify_tool_start and notify_tool_finish payload fields.
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.namespaced("mcp__server__", "query"),
            payload=ToolPayload.function("{}"),
            source=ToolCallSource.code_mode("cell-1", "tool-1"),
        )
        start = tool_start_input(
            invocation,
            session_store={"session": True},
            thread_store={"thread": True},
            turn_store={"turn": True},
            turn_id="turn-1",
        )
        finish = tool_finish_input(invocation, ToolCallOutcome.completed(False), turn_id="turn-1")

        self.assertEqual(
            start,
            ToolStartInput(
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
                call_id="call-1",
                tool_name=ToolName.namespaced("mcp__server__", "query"),
                source=ExtensionToolCallSource.code_mode("cell-1", "tool-1"),
            ),
        )
        self.assertEqual(finish.call_id, "call-1")
        self.assertEqual(finish.outcome, ToolCallOutcome.completed(False))

    def test_finish_parts_match_rust_aborted_notification_boundary(self) -> None:
        # Rust parity: codex-core::tools::lifecycle
        # lifecycle.rs::notify_tool_aborted delegates to notify_tool_finish_parts
        # with ToolCallOutcome::Aborted.
        finish = tool_finish_input_parts(
            call_id="call-2",
            tool_name=ToolName.plain("lookup"),
            source=ToolCallSource.direct(),
            outcome=ToolCallOutcome.aborted(),
            session_store={"session": True},
            thread_store={"thread": True},
            turn_store={"turn": True},
            turn_id="turn-2",
        )

        self.assertEqual(
            finish,
            ToolFinishInput(
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-2",
                call_id="call-2",
                tool_name=ToolName.plain("lookup"),
                source=ExtensionToolCallSource.direct(),
                outcome=ToolCallOutcome.aborted(),
            ),
        )

    def test_notify_helpers_call_sync_and_async_contributors(self) -> None:
        # Rust source: codex-core/src/tools/lifecycle.rs
        # Rust contract: notify_tool_start/notify_tool_finish forward invocation
        # fields and extension source to every lifecycle contributor.
        contributor = RecordingContributor()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("lookup"),
            payload=ToolPayload.function("{}"),
            source=ToolCallSource.code_mode("cell-1", "runtime-1"),
        )

        asyncio.run(notify_tool_start([contributor], invocation, turn_id="turn-1"))
        asyncio.run(notify_tool_finish([contributor], invocation, ToolCallOutcome.blocked(), turn_id="turn-1"))
        asyncio.run(notify_tool_aborted([contributor], invocation, turn_id="turn-1"))

        self.assertEqual(contributor.started[0].turn_id, "turn-1")
        self.assertEqual(
            contributor.started[0].source,
            ExtensionToolCallSource.code_mode("cell-1", "runtime-1"),
        )
        self.assertEqual(contributor.finished[0].outcome, ToolCallOutcome.blocked())
        self.assertEqual(
            contributor.finished[0].source,
            ExtensionToolCallSource.code_mode("cell-1", "runtime-1"),
        )
        self.assertEqual(contributor.finished[1].outcome, ToolCallOutcome.aborted())
        self.assertEqual(
            contributor.finished[1].source,
            ExtensionToolCallSource.code_mode("cell-1", "runtime-1"),
        )

    def test_lifecycle_store_context_supplies_rust_session_turn_store_fields(self) -> None:
        # Rust source: codex-core/src/tools/lifecycle.rs
        # Rust contract: ToolStartInput/ToolFinishInput include session_store,
        # thread_store, turn_store, and turn_id from session/turn state.
        contributor = RecordingContributor()
        invocation = ToolInvocation(
            call_id="call-store",
            tool_name=ToolName.plain("lookup"),
            payload=ToolPayload.function("{}"),
        )

        with lifecycle_store_context(
            {
                "session_store": {"session": True},
                "thread_store": {"thread": True},
                "turn_store": {"turn": True},
                "turn_id": "turn-store",
            }
        ):
            asyncio.run(notify_tool_start([contributor], invocation))
            asyncio.run(notify_tool_finish([contributor], invocation, ToolCallOutcome.completed(True)))

        self.assertEqual(contributor.started[0].session_store, {"session": True})
        self.assertEqual(contributor.started[0].thread_store, {"thread": True})
        self.assertEqual(contributor.started[0].turn_store, {"turn": True})
        self.assertEqual(contributor.started[0].turn_id, "turn-store")
        self.assertEqual(contributor.finished[0].session_store, {"session": True})
        self.assertEqual(contributor.finished[0].thread_store, {"thread": True})
        self.assertEqual(contributor.finished[0].turn_store, {"turn": True})
        self.assertEqual(contributor.finished[0].turn_id, "turn-store")

    def test_notify_helpers_support_keyword_only_contributor_signatures(self) -> None:
        called = {"start": False, "finish": False}

        async def on_tool_start(self, *, input):
            called["start"] = input.call_id == "call-1"
            self.called = called

        async def on_tool_finish(self, *, input):
            called["finish"] = input.outcome == ToolCallOutcome.blocked()
            self.finished = called

        contributor = type("Contributor", (), {"on_tool_start": on_tool_start, "on_tool_finish": on_tool_finish})()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("lookup"),
            payload=ToolPayload.function("{}"),
        )
        self.called = False
        self.finished = False

        asyncio.run(notify_tool_start([contributor], invocation, turn_id="turn-1"))
        asyncio.run(notify_tool_finish([contributor], invocation, ToolCallOutcome.blocked(), turn_id="turn-1"))

        self.assertTrue(called["start"])
        self.assertTrue(called["finish"])

    def test_notify_helpers_support_mapping_contributors(self) -> None:
        started = []
        finished = []

        async def on_tool_start(input):
            started.append(input)

        def on_tool_finish(input):
            finished.append(input)

        contributor = {"on_tool_start": on_tool_start, "on_tool_finish": on_tool_finish}
        invocation = ToolInvocation(
            call_id="call-map",
            tool_name=ToolName.plain("lookup"),
            payload=ToolPayload.function("{}"),
        )

        asyncio.run(notify_tool_start([contributor], invocation, turn_id="turn-map"))
        asyncio.run(notify_tool_finish([contributor], invocation, ToolCallOutcome.aborted(), turn_id="turn-map"))

        self.assertEqual(len(started), 1)
        self.assertEqual(len(finished), 1)
        self.assertEqual(started[0].call_id, "call-map")
        self.assertEqual(finished[0].outcome, ToolCallOutcome.aborted())

    def test_notify_helpers_ignore_missing_contributors_and_callbacks(self) -> None:
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("lookup"),
            payload=ToolPayload.function("{}"),
        )

        asyncio.run(notify_tool_start(None, invocation, turn_id="turn-1"))
        asyncio.run(notify_tool_finish((), invocation, ToolCallOutcome.completed(True), turn_id="turn-1"))
        asyncio.run(notify_tool_aborted([object()], invocation, turn_id="turn-1"))

    def test_notify_parts_helpers_call_finish_contributors_without_invocation(self) -> None:
        contributor = RecordingContributor()

        asyncio.run(
            notify_tool_finish_parts(
                [contributor],
                call_id="call-2",
                tool_name=ToolName.plain("lookup"),
                source=ToolCallSource.direct(),
                outcome=ToolCallOutcome.completed(True),
                turn_id="turn-2",
            )
        )
        asyncio.run(
            notify_tool_aborted_parts(
                [contributor],
                call_id="call-3",
                tool_name=ToolName.plain("lookup"),
                source=ToolCallSource.code_mode("cell-1", "runtime-1"),
                turn_id="turn-3",
            )
        )

        self.assertEqual(contributor.finished[0].call_id, "call-2")
        self.assertEqual(contributor.finished[0].outcome, ToolCallOutcome.completed(True))
        self.assertEqual(contributor.finished[1].call_id, "call-3")
        self.assertEqual(contributor.finished[1].outcome, ToolCallOutcome.aborted())
        self.assertEqual(
            contributor.finished[1].source,
            ExtensionToolCallSource.code_mode("cell-1", "runtime-1"),
        )

    def test_lifecycle_inputs_reject_non_rust_shapes(self) -> None:
        with self.assertRaises(TypeError):
            extension_tool_call_source(object())
        with self.assertRaises(TypeError):
            ToolStartInput(None, None, None, "turn", "call", "tool", ExtensionToolCallSource.direct())
        with self.assertRaises(TypeError):
            ToolFinishInput(
                None,
                None,
                None,
                "turn",
                "call",
                ToolName.plain("tool"),
                ExtensionToolCallSource.direct(),
                "completed",
            )


if __name__ == "__main__":
    unittest.main()
