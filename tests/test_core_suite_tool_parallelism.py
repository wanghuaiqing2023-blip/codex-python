import asyncio
import time
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.session.turn.runtime import run_user_turn_sampling_from_session
from pycodex.core.tools.context import FunctionToolOutput
from pycodex.core.tools.handlers.shell import ShellCommandHandler
from pycodex.core.tools.parallel import ToolCallRuntime
from pycodex.core.tools.registry import ToolRegistry
from pycodex.core.tools.router import ToolRouter, build_tool_call
from pycodex.protocol import ContentItem, ResponseItem, ToolName, UserInput

from test_core_turn_runtime import ParallelEchoHandler, Session


class ParallelBarrierHandler:
    def __init__(self, name: str, expected: int, *, delay: float = 0.01) -> None:
        self.name = ToolName.plain(name)
        self.expected = expected
        self.delay = delay
        self.started: list[str] = []
        self.started_at: list[float] = []
        self.timed_out_waiting_for_parallel_peer = False
        self.release = asyncio.Event()

    def tool_name(self) -> ToolName:
        return self.name

    def supports_parallel_tool_calls(self) -> bool:
        return True

    async def handle(self, invocation):
        self.started.append(invocation.call_id)
        self.started_at.append(time.monotonic())
        if len(self.started) >= self.expected:
            self.release.set()
        else:
            try:
                await asyncio.wait_for(self.release.wait(), timeout=0.3)
            except TimeoutError:
                self.timed_out_waiting_for_parallel_peer = True
        await asyncio.sleep(self.delay)
        return FunctionToolOutput.from_text(invocation.call_id, True)


class SharedParallelBarrierHandler:
    def __init__(self, name: str, shared) -> None:
        self.name = ToolName.plain(name)
        self.shared = shared

    def tool_name(self) -> ToolName:
        return self.name

    def supports_parallel_tool_calls(self) -> bool:
        return True

    async def handle(self, invocation):
        self.shared.started.append((str(self.name), invocation.call_id))
        if len(self.shared.started) >= self.shared.expected:
            self.shared.release.set()
        else:
            try:
                await asyncio.wait_for(self.shared.release.wait(), timeout=0.3)
            except TimeoutError:
                self.shared.timed_out = True
        return FunctionToolOutput.from_text(invocation.call_id, True)


def _router(*handlers) -> ToolRouter:
    return ToolRouter.from_parts(ToolRegistry.from_tools(handlers), ())


def _call(name: str, call_id: str):
    call = build_tool_call(ResponseItem.function_call(name, "{}", call_id))
    assert call is not None
    return call


async def _run_calls(runtime: ToolCallRuntime, calls):
    return await asyncio.gather(*(runtime.handle_tool_call(call) for call in calls))


def test_read_file_tools_run_in_parallel() -> None:
    # Rust: codex-rs/core/tests/suite/tool_parallelism.rs
    # Contract: read_file/test sync tools opt into parallel dispatch and overlap.
    async def run() -> None:
        handler = ParallelBarrierHandler("test_sync_tool", 2)
        runtime = ToolCallRuntime(_router(handler))

        outputs = await _run_calls(
            runtime,
            (_call("test_sync_tool", "call-1"), _call("test_sync_tool", "call-2")),
        )

        assert handler.started == ["call-1", "call-2"]
        assert not handler.timed_out_waiting_for_parallel_peer
        assert [item.call_id for item in outputs] == ["call-1", "call-2"]

    asyncio.run(run())


def test_shell_tools_run_in_parallel() -> None:
    # Rust: shell_tools_run_in_parallel.
    # Contract: shell_command advertises parallel execution and runtime does not serialize it.
    async def run() -> None:
        assert ShellCommandHandler().supports_parallel_tool_calls() is True
        handler = ParallelBarrierHandler("shell_command", 2)
        runtime = ToolCallRuntime(_router(handler))

        await _run_calls(
            runtime,
            (_call("shell_command", "call-1"), _call("shell_command", "call-2")),
        )

        assert handler.started == ["call-1", "call-2"]
        assert not handler.timed_out_waiting_for_parallel_peer

    asyncio.run(run())


def test_mixed_parallel_tools_run_in_parallel() -> None:
    # Rust: mixed_parallel_tools_run_in_parallel.
    # Contract: different parallel-capable tools share the parallel execution lane.
    async def run() -> None:
        shared = SimpleNamespace(
            expected=2,
            started=[],
            timed_out=False,
            release=asyncio.Event(),
        )
        runtime = ToolCallRuntime(
            _router(
                SharedParallelBarrierHandler("test_sync_tool", shared),
                SharedParallelBarrierHandler("shell_command", shared),
            )
        )

        await _run_calls(
            runtime,
            (_call("test_sync_tool", "call-1"), _call("shell_command", "call-2")),
        )

        assert [call_id for _tool, call_id in shared.started] == ["call-1", "call-2"]
        assert not shared.timed_out

    asyncio.run(run())


def test_tool_results_grouped() -> None:
    # Rust: tool_results_grouped.
    # Contract: follow-up model input lists all function calls before outputs, preserving call order.
    async def run() -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = ParallelEchoHandler()
        router = _router(handler)
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [
                    ResponseItem.function_call("parallel_echo", "{}", "call-1"),
                    ResponseItem.function_call("parallel_echo", "{}", "call-2"),
                    ResponseItem.function_call("parallel_echo", "{}", "call-3"),
                ]
            return [ResponseItem.message("assistant", (ContentItem.output_text("done after tools"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _session, _turn: router,
        )

        assert handler.started == ["call-1", "call-2", "call-3"]
        assert not handler.timed_out_waiting_for_parallel_peer
        assert [item.call_id for item in result.tool_response_items] == ["call-1", "call-2", "call-3"]
        follow_up_input = seen_requests[1].request_plan.request["input"]
        call_indexes = [index for index, item in enumerate(follow_up_input) if item.type == "function_call"]
        output_indexes = [index for index, item in enumerate(follow_up_input) if item.type == "function_call_output"]
        assert len(call_indexes) == 3
        assert len(output_indexes) == 3
        assert max(call_indexes) < min(output_indexes)
        assert [follow_up_input[index].call_id for index in call_indexes] == [
            follow_up_input[index].call_id for index in output_indexes
        ]

    asyncio.run(run())


def test_shell_tools_start_before_response_completed_when_stream_delayed() -> None:
    # Rust: shell_tools_start_before_response_completed_when_stream_delayed.
    # Contract: tool dispatch is not gated on response.completed once calls are available.
    async def run() -> None:
        handler = ParallelBarrierHandler("shell_command", 4, delay=0)
        runtime = ToolCallRuntime(_router(handler))
        calls = tuple(_call("shell_command", f"call-{index}") for index in range(1, 5))

        tasks = [asyncio.create_task(runtime.handle_tool_call(call)) for call in calls]
        await asyncio.wait_for(handler.release.wait(), timeout=0.3)
        completed_gate_time = time.monotonic()
        await asyncio.gather(*tasks)

        assert handler.started == ["call-1", "call-2", "call-3", "call-4"]
        assert max(handler.started_at) <= completed_gate_time
        assert not handler.timed_out_waiting_for_parallel_peer

    asyncio.run(run())
