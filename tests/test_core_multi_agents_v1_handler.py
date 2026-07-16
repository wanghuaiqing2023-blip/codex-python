import unittest

from pycodex.core.tools.handlers.multi_agents import (
    ResumeAgentArgs,
    ResumeAgentHandler,
    ResumeAgentResult,
    SendInputArgs,
    SendInputHandler,
    SendInputResult,
    V1CloseAgentArgs,
    V1CloseAgentHandler,
    V1CloseAgentResult,
    V1SpawnAgentArgs,
    V1SpawnAgentHandler,
    V1SpawnAgentResult,
    V1WaitAgentHandler,
    V1WaitAgentResult,
    V1WaitArgs,
    parse_agent_id_target,
    parse_agent_id_targets,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import AgentStatus, ToolName


VALID_A = "12345678-1234-5678-1234-567812345678"
VALID_B = "87654321-4321-8765-4321-876543218765"


class CoreMultiAgentsV1HandlerTests(unittest.TestCase):
    def test_parse_agent_id_targets_match_rust_errors(self) -> None:
        self.assertEqual(str(parse_agent_id_target(VALID_A)), VALID_A)
        self.assertEqual(tuple(str(target) for target in parse_agent_id_targets([VALID_A, VALID_B])), (VALID_A, VALID_B))
        with self.assertRaisesRegex(FunctionCallError, "agent ids must be non-empty"):
            parse_agent_id_targets([])
        with self.assertRaisesRegex(FunctionCallError, "invalid agent id not-a-uuid"):
            parse_agent_id_target("not-a-uuid")

    def test_v1_spawn_args_parse_collab_input_and_role_name(self) -> None:
        args = V1SpawnAgentArgs.from_json('{"message":"hello","agent_type":" reviewer ","fork_context":false}')
        self.assertEqual(args.role_name(), "reviewer")
        self.assertEqual(args.input_items()[0].to_mapping(), {"type": "text", "text": "hello"})
        self.assertFalse(args.fork_context)

    def test_v1_spawn_args_reject_invalid_input_and_full_fork_overrides(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "Provide one of"):
            V1SpawnAgentArgs.from_json("{}").validate_for_spawn()
        with self.assertRaisesRegex(FunctionCallError, "Empty message"):
            V1SpawnAgentArgs.from_json('{"message":"   "}').validate_for_spawn()
        with self.assertRaisesRegex(FunctionCallError, "Full-history forked agents inherit"):
            V1SpawnAgentArgs.from_json(
                '{"message":"hello","fork_context":true,"model":"gpt-x"}'
            ).validate_for_spawn()

    def test_v1_spawn_result_keeps_agent_id_and_nickname_shape(self) -> None:
        self.assertEqual(
            V1SpawnAgentResult(VALID_A, "helper").to_mapping(),
            {"agent_id": VALID_A, "nickname": "helper"},
        )
        self.assertEqual(
            V1SpawnAgentResult(VALID_A).to_mapping(),
            {"agent_id": VALID_A, "nickname": None},
        )

    def test_v1_spawn_handler_uses_namespace_search_and_callback(self) -> None:
        # Rust source: tools/handlers/multi_agents/spawn.rs.
        invocation = ToolInvocation(
            call_id="call-spawn",
            tool_name=ToolName.namespaced("multi_agent_v1", "spawn_agent"),
            payload=ToolPayload.function('{"message":"hello","fork_context":false}'),
        )
        seen = []

        def spawn_agent(args):
            seen.append((args.input_items()[0].to_mapping(), args.fork_context))
            return {"agent_id": VALID_A, "nickname": "helper"}

        handler = V1SpawnAgentHandler(spawn_agent=spawn_agent)
        result = handler.handle(invocation)
        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "spawn_agent"))
        self.assertEqual(handler.spec()["tools"][0]["name"], "spawn_agent")
        self.assertIsNotNone(handler.search_info())
        self.assertEqual(seen, [({"type": "text", "text": "hello"}, False)])
        self.assertEqual(result.to_mapping(), {"agent_id": VALID_A, "nickname": "helper"})

    def test_v1_spawn_agent_wrapper_surface_matches_rust(self) -> None:
        # Rust source: spawn.rs ToolExecutor/CoreToolRuntime/ToolOutput impls.
        payload = ToolPayload.function('{"message":"hello","agent_type":" reviewer ","fork_context":false}')
        handler = V1SpawnAgentHandler(spawn_agent=lambda args: V1SpawnAgentResult(VALID_A, args.role_name()))

        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "spawn_agent"))
        self.assertTrue(handler.matches_kind(payload))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(handler.spec()["tools"][0]["name"], "spawn_agent")
        self.assertIn("agent_id", handler.spec()["tools"][0]["output_schema"]["properties"])

        result = handler.handle(
            ToolInvocation(
                call_id="call-spawn",
                tool_name=handler.tool_name(),
                payload=payload,
            )
        )
        self.assertTrue(result.success_for_logging())
        self.assertIn('"agent_id"', result.log_preview())
        self.assertEqual(result.code_mode_result(payload), {"agent_id": VALID_A, "nickname": "reviewer"})
        response = result.to_response_item("call-spawn", payload)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), f'{{"agent_id":"{VALID_A}","nickname":"reviewer"}}')

    def test_send_input_args_parse_message_items_and_interrupt(self) -> None:
        args = SendInputArgs.from_json(f'{{"target":"{VALID_A}","message":"hello","interrupt":true}}')
        self.assertEqual(str(args.receiver_thread_id()), VALID_A)
        self.assertTrue(args.interrupt)
        self.assertEqual(args.input_items()[0].to_mapping(), {"type": "text", "text": "hello"})

    def test_send_input_args_reuse_collab_input_validation(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "Provide one of"):
            SendInputArgs.from_json(f'{{"target":"{VALID_A}"}}').input_items()
        with self.assertRaisesRegex(FunctionCallError, "Empty message"):
            SendInputArgs.from_json(f'{{"target":"{VALID_A}","message":" "}}').input_items()

    def test_send_input_result_serializes_submission_id(self) -> None:
        result = SendInputResult("submission-1")
        self.assertEqual(result.to_mapping(), {"submission_id": "submission-1"})
        self.assertTrue(result.success_for_logging())

    def test_send_input_handler_uses_namespace_search_and_callback(self) -> None:
        # Rust source: tools/handlers/multi_agents/send_input.rs.
        invocation = ToolInvocation(
            call_id="call-send",
            tool_name=ToolName.namespaced("multi_agent_v1", "send_input"),
            payload=ToolPayload.function(f'{{"target":"{VALID_A}","message":"hello","interrupt":true}}'),
        )
        seen = []

        def send_input(thread_id, items, interrupt):
            seen.append((str(thread_id), items[0].to_mapping(), interrupt))
            return "submission-1"

        handler = SendInputHandler(send_input)
        result = handler.handle(invocation)
        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "send_input"))
        self.assertIsNotNone(handler.search_info())
        self.assertEqual(seen, [(VALID_A, {"type": "text", "text": "hello"}, True)])
        self.assertEqual(result.to_mapping(), {"submission_id": "submission-1"})

    def test_send_input_tool_runtime_surface_matches_rust(self) -> None:
        # Rust source: send_input.rs ToolExecutor/CoreToolRuntime/ToolOutput impls.
        payload = ToolPayload.function(f'{{"target":"{VALID_A}","message":"hello"}}')
        handler = SendInputHandler(lambda thread_id, items, interrupt: "submission-2")

        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "send_input"))
        self.assertTrue(handler.matches_kind(payload))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(handler.spec()["tools"][0]["name"], "send_input")
        self.assertIn("submission_id", handler.spec()["tools"][0]["output_schema"]["properties"])

        result = handler.handle(
            ToolInvocation(
                call_id="call-send",
                tool_name=handler.tool_name(),
                payload=payload,
            )
        )
        self.assertTrue(result.success_for_logging())
        self.assertIn('"submission_id"', result.log_preview())
        self.assertEqual(result.code_mode_result(payload), {"submission_id": "submission-2"})
        response = result.to_response_item("call-send", payload)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), '{"submission_id":"submission-2"}')

    def test_v1_close_args_result_and_handler(self) -> None:
        # Rust source: tools/handlers/multi_agents/close_agent.rs.
        args = V1CloseAgentArgs.from_json(f'{{"target":"{VALID_A}"}}')
        self.assertEqual(str(args.agent_id()), VALID_A)
        self.assertEqual(V1CloseAgentResult(AgentStatus.running()).to_mapping(), {"previous_status": "running"})
        invocation = ToolInvocation(
            call_id="call-close",
            tool_name=ToolName.namespaced("multi_agent_v1", "close_agent"),
            payload=ToolPayload.function(f'{{"target":"{VALID_A}"}}'),
        )
        handler = V1CloseAgentHandler(lambda thread_id: "shutdown")
        self.assertEqual(handler.handle(invocation).to_mapping(), {"previous_status": "shutdown"})
        self.assertIsNotNone(handler.search_info())

    def test_v1_close_agent_tool_runtime_surface_matches_rust(self) -> None:
        # Rust source: close_agent.rs ToolExecutor/CoreToolRuntime/ToolOutput impls.
        payload = ToolPayload.function(f'{{"target":"{VALID_A}"}}')
        handler = V1CloseAgentHandler(lambda thread_id: AgentStatus.completed("done"))

        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "close_agent"))
        self.assertTrue(handler.matches_kind(payload))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(handler.spec()["tools"][0]["name"], "close_agent")
        self.assertIn("previous_status", handler.spec()["tools"][0]["output_schema"]["properties"])

        result = handler.handle(
            ToolInvocation(
                call_id="call-close",
                tool_name=handler.tool_name(),
                payload=payload,
            )
        )
        self.assertTrue(result.success_for_logging())
        self.assertIn('"previous_status"', result.log_preview())
        self.assertEqual(result.code_mode_result(payload)["previous_status"], {"completed": "done"})
        response = result.to_response_item("call-close", payload)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), '{"previous_status":{"completed":"done"}}')

    def test_v1_resume_agent_is_exported_from_v1_coordinate(self) -> None:
        # Rust source: tools/handlers/multi_agents.rs pub-uses resume_agent::Handler.
        args = ResumeAgentArgs.from_json(f'{{"id":"{VALID_A}"}}')
        self.assertEqual(str(args.thread_id()), VALID_A)
        self.assertEqual(ResumeAgentResult(AgentStatus.running()).to_mapping(), {"status": "running"})
        invocation = ToolInvocation(
            call_id="call-resume",
            tool_name=ToolName.namespaced("multi_agent_v1", "resume_agent"),
            payload=ToolPayload.function(f'{{"id":"{VALID_A}"}}'),
        )
        seen = []

        def resume_agent(thread_id):
            seen.append(str(thread_id))
            return AgentStatus.completed("done")

        handler = ResumeAgentHandler(resume_agent)
        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "resume_agent"))
        self.assertEqual(handler.handle(invocation).to_mapping(), {"status": {"completed": "done"}})
        self.assertEqual(seen, [VALID_A])
        self.assertIsNotNone(handler.search_info())

    def test_v1_resume_agent_wrapper_surface_matches_rust(self) -> None:
        # Rust source: tools/handlers/multi_agents/resume_agent.rs ToolExecutor/CoreToolRuntime/ToolOutput impls.
        payload = ToolPayload.function(f'{{"id":"{VALID_A}"}}')
        handler = ResumeAgentHandler(lambda thread_id: AgentStatus.interrupted())

        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "resume_agent"))
        self.assertTrue(handler.matches_kind(payload))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(handler.spec()["tools"][0]["name"], "resume_agent")
        self.assertIn("status", handler.spec()["tools"][0]["output_schema"]["properties"])

        result = handler.handle(
            ToolInvocation(
                call_id="call-resume",
                tool_name=handler.tool_name(),
                payload=payload,
            )
        )
        self.assertTrue(result.success_for_logging())
        self.assertIn('"status"', result.log_preview())
        self.assertEqual(result.code_mode_result(payload), {"status": "interrupted"})
        response = result.to_response_item("call-resume", payload)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), '{"status":"interrupted"}')

    def test_v1_wait_args_require_targets_and_clamp_timeout(self) -> None:
        args = V1WaitArgs.from_json(f'{{"targets":["{VALID_A}"],"timeout_ms":999999}}')
        self.assertEqual(tuple(str(target) for target in args.receiver_thread_ids()), (VALID_A,))
        self.assertEqual(args.resolve_timeout_ms(1000, 30000, 600000), 600000)
        self.assertEqual(
            V1WaitArgs.from_json(f'{{"targets":["{VALID_A}"],"timeout_ms":1}}').resolve_timeout_ms(),
            10000,
        )
        with self.assertRaisesRegex(FunctionCallError, "greater than zero"):
            V1WaitArgs.from_json(f'{{"targets":["{VALID_A}"],"timeout_ms":0}}').resolve_timeout_ms()
        with self.assertRaisesRegex(FunctionCallError, "agent ids must be non-empty"):
            V1WaitArgs.from_json('{"targets":[]}').receiver_thread_ids()

    def test_v1_wait_result_and_handler(self) -> None:
        result = V1WaitAgentResult({VALID_A: AgentStatus.completed("done")}, False)
        self.assertEqual(result.to_mapping(), {"status": {VALID_A: {"completed": "done"}}, "timed_out": False})
        invocation = ToolInvocation(
            call_id="call-wait",
            tool_name=ToolName.namespaced("multi_agent_v1", "wait_agent"),
            payload=ToolPayload.function(f'{{"targets":["{VALID_A}"],"timeout_ms":2000}}'),
        )
        seen = []

        def wait_agent(targets, timeout_ms):
            seen.append((tuple(str(target) for target in targets), timeout_ms))
            return {}

        handler = V1WaitAgentHandler(wait_agent=wait_agent)
        self.assertEqual(handler.handle(invocation).to_mapping(), {"status": {}, "timed_out": True})
        self.assertEqual(seen, [((VALID_A,), 10000)])
        self.assertIsNotNone(handler.search_info())

    def test_v1_wait_agent_wrapper_surface_matches_rust(self) -> None:
        # Rust source: tools/handlers/multi_agents/wait.rs ToolExecutor/CoreToolRuntime/ToolOutput impls.
        payload = ToolPayload.function(f'{{"targets":["{VALID_A}"],"timeout_ms":2000}}')
        handler = V1WaitAgentHandler(wait_agent=lambda targets, timeout_ms: {VALID_A: AgentStatus.shutdown()})

        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "wait_agent"))
        self.assertTrue(handler.matches_kind(payload))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(handler.spec()["tools"][0]["name"], "wait_agent")
        self.assertIn("timed_out", handler.spec()["tools"][0]["output_schema"]["properties"])

        result = handler.handle(
            ToolInvocation(
                call_id="call-wait",
                tool_name=handler.tool_name(),
                payload=payload,
            )
        )
        self.assertTrue(result.success_for_logging())
        self.assertIn('"timed_out"', result.log_preview())
        self.assertEqual(result.code_mode_result(payload), {"status": {VALID_A: "shutdown"}, "timed_out": False})
        response = result.to_response_item("call-wait", payload)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), f'{{"status":{{"{VALID_A}":"shutdown"}},"timed_out":false}}')


if __name__ == "__main__":
    unittest.main()
