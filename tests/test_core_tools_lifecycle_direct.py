import pytest

from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.lifecycle import (
    ExtensionToolCallSource,
    ToolCallOutcome,
    extension_tool_call_source,
    lifecycle_store_context,
    notify_tool_finish,
    notify_tool_start,
    tool_finish_input,
    tool_start_input,
)
from pycodex.core.tools.registry import ToolCallSource, ToolInvocation
from pycodex.protocol import ToolName


def _invocation(source: ToolCallSource | None = None) -> ToolInvocation:
    return ToolInvocation(
        call_id="call-1",
        tool_name=ToolName.plain("demo_tool"),
        payload=ToolPayload.function("{}"),
        source=source or ToolCallSource.direct(),
    )


def test_extension_tool_call_source_maps_direct_and_code_mode():
    # Rust source: codex-rs/core/src/tools/lifecycle.rs::extension_tool_call_source.
    assert extension_tool_call_source(ToolCallSource.direct()) == ExtensionToolCallSource.direct()

    source = extension_tool_call_source(ToolCallSource.code_mode("cell-1", "runtime-1"))

    assert source == ExtensionToolCallSource.code_mode("cell-1", "runtime-1")


def test_tool_start_and_finish_inputs_include_lifecycle_stores():
    invocation = _invocation(ToolCallSource.code_mode("cell-1", "runtime-1"))

    start = tool_start_input(
        invocation,
        session_store={"session": True},
        thread_store={"thread": True},
        turn_store={"turn": True},
        turn_id="turn-1",
    )
    finish = tool_finish_input(
        invocation,
        ToolCallOutcome.completed(True),
        session_store=start.session_store,
        thread_store=start.thread_store,
        turn_store=start.turn_store,
        turn_id=start.turn_id,
    )

    assert start.call_id == "call-1"
    assert start.tool_name == ToolName.plain("demo_tool")
    assert start.source == ExtensionToolCallSource.code_mode("cell-1", "runtime-1")
    assert finish.outcome == ToolCallOutcome.completed(True)
    assert finish.turn_id == "turn-1"


@pytest.mark.asyncio
async def test_notify_tool_start_and_finish_use_context_stores():
    records = []

    class Contributor:
        async def on_tool_start(self, input):
            records.append(("start", input.session_store, input.turn_id, input.call_id))

        async def on_tool_finish(self, input):
            records.append(("finish", input.thread_store, input.outcome.type, input.call_id))

    invocation = _invocation()
    with lifecycle_store_context(
        {
            "session_store": "session-store",
            "thread_store": "thread-store",
            "turn_store": "turn-store",
            "turn_id": "turn-1",
        }
    ):
        await notify_tool_start((Contributor(),), invocation)
        await notify_tool_finish((Contributor(),), invocation, ToolCallOutcome.aborted())

    assert records == [
        ("start", "session-store", "turn-1", "call-1"),
        ("finish", "thread-store", "aborted", "call-1"),
    ]
