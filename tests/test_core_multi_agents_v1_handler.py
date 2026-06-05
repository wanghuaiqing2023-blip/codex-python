import unittest

from pycodex.core.tools.handlers.multi_agents import (
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

    def test_v1_close_args_result_and_handler(self) -> None:
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

    def test_v1_wait_args_require_targets_and_clamp_timeout(self) -> None:
        args = V1WaitArgs.from_json(f'{{"targets":["{VALID_A}"],"timeout_ms":999999}}')
        self.assertEqual(tuple(str(target) for target in args.receiver_thread_ids()), (VALID_A,))
        self.assertEqual(args.resolve_timeout_ms(1000, 30000, 600000), 600000)
        self.assertEqual(V1WaitArgs.from_json(f'{{"targets":["{VALID_A}"],"timeout_ms":1}}').resolve_timeout_ms(), 1000)
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
        self.assertEqual(seen, [((VALID_A,), 2000)])
        self.assertIsNotNone(handler.search_info())


if __name__ == "__main__":
    unittest.main()
