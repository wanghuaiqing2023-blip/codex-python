import unittest

from pycodex.core.tools.handlers.multi_agents_v2 import (
    CloseAgentArgs,
    CloseAgentHandler,
    FollowupTaskArgs,
    FollowupTaskHandler,
    ListAgentsArgs,
    ListAgentsHandler,
    ListAgentsResult,
    MessageDeliveryMode,
    ResumeAgentArgs,
    ResumeAgentHandler,
    ResumeAgentResult,
    SendMessageArgs,
    SendMessageHandler,
    SpawnAgentArgs,
    SpawnAgentForkMode,
    SpawnAgentHandler,
    SpawnAgentResult,
    WaitAgentHandler,
    WaitAgentResult,
    WaitArgs,
    message_content,
    successful_empty_message_output,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import AgentStatus, ToolName


class CoreMultiAgentsV2HandlerTests(unittest.TestCase):
    def test_v2_args_deny_unknown_fields_and_require_strings(self) -> None:
        self.assertEqual(ListAgentsArgs.from_json('{"path_prefix":"root/a"}').path_prefix, "root/a")
        self.assertEqual(CloseAgentArgs.from_json('{"target":"agent-a"}').target, "agent-a")
        self.assertEqual(SendMessageArgs.from_json('{"target":"agent-a","message":"hi"}').message, "hi")
        self.assertEqual(FollowupTaskArgs.from_json('{"target":"agent-a","message":"next"}').target, "agent-a")
        with self.assertRaisesRegex(ValueError, "unknown field"):
            ListAgentsArgs.from_json('{"path_prefix":"root","extra":1}')

    def test_message_content_rejects_blank_message_like_rust(self) -> None:
        self.assertEqual(message_content(" hello "), " hello ")
        with self.assertRaises(FunctionCallError) as raised:
            message_content("   ")
        self.assertEqual(str(raised.exception), "Empty message can't be sent to an agent")

    def test_delivery_mode_controls_trigger_turn(self) -> None:
        communication = {"message": "hi", "trigger_turn": True}
        self.assertEqual(MessageDeliveryMode.QUEUE_ONLY.apply(communication)["trigger_turn"], False)
        self.assertEqual(MessageDeliveryMode.TRIGGER_TURN.apply(communication)["trigger_turn"], True)

    def test_spawn_args_parse_fork_modes_like_rust(self) -> None:
        default = SpawnAgentArgs.from_json('{"message":"do it","task_name":"task_1"}')
        self.assertEqual(default.fork_mode().mode, SpawnAgentForkMode.FULL_HISTORY)
        none = SpawnAgentArgs.from_json('{"message":"do it","task_name":"task_1","fork_turns":"none"}')
        self.assertIsNone(none.fork_mode())
        last = SpawnAgentArgs.from_json('{"message":"do it","task_name":"task_1","fork_turns":"3"}')
        self.assertEqual(last.fork_mode().to_mapping(), {"type": "last_n_turns", "turns": 3})

    def test_spawn_args_reject_fork_context_and_bad_fork_turns(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "fork_context is not supported"):
            SpawnAgentArgs.from_json('{"message":"do it","task_name":"task_1","fork_context":true}').fork_mode()
        with self.assertRaisesRegex(FunctionCallError, "fork_turns must be"):
            SpawnAgentArgs.from_json('{"message":"do it","task_name":"task_1","fork_turns":"0"}').fork_mode()
        with self.assertRaisesRegex(FunctionCallError, "fork_turns must be"):
            SpawnAgentArgs.from_json('{"message":"do it","task_name":"task_1","fork_turns":"recent"}').fork_mode()

    def test_spawn_full_history_rejects_role_model_reasoning_overrides(self) -> None:
        args = SpawnAgentArgs.from_json(
            '{"message":"do it","task_name":"task_1","agent_type":"reviewer","fork_turns":"all"}'
        )
        with self.assertRaisesRegex(FunctionCallError, "not supported"):
            args.validate_for_spawn()

    def test_spawn_result_hides_metadata_when_requested(self) -> None:
        visible = SpawnAgentResult.with_nickname("/root/task_1", "helper")
        hidden = SpawnAgentResult.hidden_metadata("/root/task_1")
        self.assertEqual(visible.to_mapping(), {"task_name": "/root/task_1", "nickname": "helper"})
        self.assertEqual(hidden.to_mapping(), {"task_name": "/root/task_1"})

    def test_spawn_handler_uses_callback_result(self) -> None:
        invocation = ToolInvocation(
            call_id="call-spawn",
            tool_name=ToolName.plain("spawn_agent"),
            payload=ToolPayload.function('{"message":"do it","task_name":"task_1","fork_turns":"none"}'),
        )
        seen = []

        def spawn_agent(args):
            seen.append(args.task_name)
            return SpawnAgentResult.hidden_metadata("/root/task_1")

        result = SpawnAgentHandler(spawn_agent=spawn_agent).handle(invocation)
        self.assertEqual(seen, ["task_1"])
        self.assertEqual(result.to_mapping(), {"task_name": "/root/task_1"})

    def test_wait_args_resolve_timeout_bounds(self) -> None:
        self.assertEqual(WaitArgs.from_json("{}").resolve_timeout_ms(1000, 30000, 600000), 30000)
        self.assertEqual(WaitArgs.from_json('{"timeout_ms":5000}').resolve_timeout_ms(), 5000)
        with self.assertRaisesRegex(FunctionCallError, "at least 1000"):
            WaitArgs.from_json('{"timeout_ms":999}').resolve_timeout_ms()
        with self.assertRaisesRegex(FunctionCallError, "at most 600000"):
            WaitArgs.from_json('{"timeout_ms":600001}').resolve_timeout_ms()

    def test_wait_agent_result_text_matches_rust(self) -> None:
        self.assertEqual(WaitAgentResult.from_timed_out(False).to_mapping(), {"message": "Wait completed.", "timed_out": False})
        self.assertEqual(WaitAgentResult.from_timed_out(True).to_mapping(), {"message": "Wait timed out.", "timed_out": True})

    def test_wait_agent_handler_uses_callback_completion(self) -> None:
        invocation = ToolInvocation(
            call_id="call-wait",
            tool_name=ToolName.plain("wait_agent"),
            payload=ToolPayload.function('{"timeout_ms":2000}'),
        )
        seen = []

        def wait_for_change(timeout_ms):
            seen.append(timeout_ms)
            return False

        result = WaitAgentHandler(wait_for_change=wait_for_change).handle(invocation)
        self.assertEqual(seen, [2000])
        self.assertEqual(result.to_mapping(), {"message": "Wait timed out.", "timed_out": True})

    def test_resume_agent_args_parse_thread_id_or_report_model_error(self) -> None:
        valid_id = "12345678-1234-5678-1234-567812345678"
        args = ResumeAgentArgs.from_json(f'{{"id":"{valid_id}"}}')
        self.assertEqual(str(args.thread_id()), valid_id)
        with self.assertRaisesRegex(FunctionCallError, "invalid agent id not-a-uuid"):
            ResumeAgentArgs.from_json('{"id":"not-a-uuid"}').thread_id()

    def test_resume_agent_result_serializes_status(self) -> None:
        self.assertEqual(ResumeAgentResult(AgentStatus.running()).to_mapping(), {"status": "running"})
        self.assertEqual(ResumeAgentResult({"completed": "done"}).to_mapping(), {"status": {"completed": "done"}})

    def test_resume_agent_handler_uses_namespace_and_callback(self) -> None:
        valid_id = "12345678-1234-5678-1234-567812345678"
        invocation = ToolInvocation(
            call_id="call-resume",
            tool_name=ToolName.namespaced("multi_agent_v1", "resume_agent"),
            payload=ToolPayload.function(f'{{"id":"{valid_id}"}}'),
        )
        seen = []

        def resume_agent(thread_id):
            seen.append(str(thread_id))
            return "running"

        handler = ResumeAgentHandler(resume_agent)
        result = handler.handle(invocation)
        self.assertEqual(handler.tool_name(), ToolName.namespaced("multi_agent_v1", "resume_agent"))
        self.assertEqual(seen, [valid_id])
        self.assertEqual(result.to_mapping(), {"status": "running"})
        self.assertIsNotNone(handler.search_info())

    def test_list_agents_handler_uses_callback_result(self) -> None:
        invocation = ToolInvocation(
            call_id="call-list",
            tool_name=ToolName.plain("list_agents"),
            payload=ToolPayload.function('{"path_prefix":"root/a"}'),
        )
        seen = []

        def list_agents(path_prefix):
            seen.append(path_prefix)
            return ({"thread_id": "thread-a", "status": "running"},)

        result = ListAgentsHandler(list_agents).handle(invocation)
        self.assertEqual(seen, ["root/a"])
        self.assertEqual(result.to_mapping(), {"agents": [{"thread_id": "thread-a", "status": "running"}]})
        self.assertTrue(result.success_for_logging())

    def test_close_agent_handler_returns_previous_status(self) -> None:
        invocation = ToolInvocation(
            call_id="call-close",
            tool_name=ToolName.plain("close_agent"),
            payload=ToolPayload.function('{"target":"agent-a"}'),
        )
        result = CloseAgentHandler(lambda target: AgentStatus.running()).handle(invocation)
        self.assertEqual(result.to_mapping(), {"previous_status": "running"})

    def test_message_handlers_parse_and_validate_blank_messages(self) -> None:
        payload = ToolPayload.function('{"target":"agent-a","message":"hello"}')
        self.assertEqual(SendMessageHandler().parse_args(payload).message, "hello")
        self.assertEqual(FollowupTaskHandler().parse_args(payload).target, "agent-a")
        with self.assertRaises(FunctionCallError):
            SendMessageHandler().parse_args(ToolPayload.function('{"target":"agent-a","message":""}'))

    def test_handler_specs_and_empty_success_output(self) -> None:
        self.assertEqual(ListAgentsHandler().tool_name(), ToolName.plain("list_agents"))
        self.assertEqual(CloseAgentHandler().spec()["name"], "close_agent")
        self.assertEqual(SendMessageHandler().spec()["name"], "send_message")
        self.assertEqual(FollowupTaskHandler().spec()["name"], "followup_task")
        self.assertEqual(SpawnAgentHandler().spec()["name"], "spawn_agent")
        self.assertEqual(WaitAgentHandler().spec()["name"], "wait_agent")
        self.assertEqual(ResumeAgentHandler().spec()["name"], "resume_agent")
        self.assertEqual(successful_empty_message_output().into_text(), "")

    def test_list_agents_result_serializes_like_tool_output(self) -> None:
        result = ListAgentsResult(({"thread_id": "thread-a"},))
        self.assertEqual(result.code_mode_result(ToolPayload.function("{}")), {"agents": [{"thread_id": "thread-a"}]})


if __name__ == "__main__":
    unittest.main()
