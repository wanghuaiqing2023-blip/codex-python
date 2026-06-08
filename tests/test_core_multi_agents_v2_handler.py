import unittest
from types import SimpleNamespace

from pycodex.core.tools.handlers import multi_agents_v2 as multi_agents_v2_module
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
    handle_message_string_tool,
    message_content,
    successful_empty_message_output,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import AgentPath, AgentStatus, InterAgentCommunication, SessionSource, ToolName


class CoreMultiAgentsV2HandlerTests(unittest.TestCase):
    def test_root_module_reexports_v2_handlers(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/multi_agents_v2.rs
        # exports Handler aliases for close/followup/list/send/spawn/wait child modules.
        expected = {
            "CloseAgentHandler",
            "FollowupTaskHandler",
            "ListAgentsHandler",
            "SendMessageHandler",
            "SpawnAgentHandler",
            "WaitAgentHandler",
        }
        self.assertTrue(expected.issubset(set(multi_agents_v2_module.__all__)))
        self.assertIs(multi_agents_v2_module.CloseAgentHandler, CloseAgentHandler)
        self.assertIs(multi_agents_v2_module.FollowupTaskHandler, FollowupTaskHandler)
        self.assertIs(multi_agents_v2_module.ListAgentsHandler, ListAgentsHandler)
        self.assertIs(multi_agents_v2_module.SendMessageHandler, SendMessageHandler)
        self.assertIs(multi_agents_v2_module.SpawnAgentHandler, SpawnAgentHandler)
        self.assertIs(multi_agents_v2_module.WaitAgentHandler, WaitAgentHandler)

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
        typed = InterAgentCommunication(
            author=AgentPath.root(),
            recipient=AgentPath.from_string("/root/agent_a"),
            content="hi",
            trigger_turn=False,
        )
        self.assertFalse(MessageDeliveryMode.QUEUE_ONLY.apply(typed).trigger_turn)
        self.assertTrue(MessageDeliveryMode.TRIGGER_TURN.apply(typed).trigger_turn)

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

    def test_spawn_handler_hides_metadata_from_turn_config_like_rust(self) -> None:
        # Rust source: spawn.rs reads turn.config.multi_agent_v2.hide_spawn_agent_metadata.
        invocation = ToolInvocation(
            call_id="call-spawn",
            tool_name=ToolName.plain("spawn_agent"),
            payload=ToolPayload.function('{"message":"do it","task_name":"task_1","fork_turns":"none"}'),
            turn=SimpleNamespace(
                config=SimpleNamespace(
                    multi_agent_v2=SimpleNamespace(hide_spawn_agent_metadata=True)
                )
            ),
        )

        result = SpawnAgentHandler(
            spawn_agent=lambda args: SpawnAgentResult.with_nickname("/root/task_1", "helper")
        ).handle(invocation)

        self.assertEqual(result.to_mapping(), {"task_name": "/root/task_1"})

    def test_spawn_handler_reports_missing_canonical_task_name_like_rust(self) -> None:
        # Rust source: spawn.rs reports a model-visible error when new_agent_path is absent.
        invocation = ToolInvocation(
            call_id="call-spawn",
            tool_name=ToolName.plain("spawn_agent"),
            payload=ToolPayload.function('{"message":"do it","task_name":"task_1","fork_turns":"none"}'),
        )

        with self.assertRaisesRegex(FunctionCallError, "spawned agent is missing a canonical task name"):
            SpawnAgentHandler(spawn_agent=lambda args: {}).handle(invocation)

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

    def test_wait_agent_handler_uses_turn_config_timeout_bounds(self) -> None:
        # Rust source: tools/handlers/multi_agents_v2/wait.rs reads timeout bounds from turn config.
        turn = SimpleNamespace(
            config=SimpleNamespace(
                multi_agent_v2=SimpleNamespace(
                    min_wait_timeout_ms=1500,
                    default_wait_timeout_ms=2500,
                    max_wait_timeout_ms=4500,
                )
            )
        )
        invocation = ToolInvocation(
            call_id="call-wait",
            tool_name=ToolName.plain("wait_agent"),
            payload=ToolPayload.function("{}"),
            turn=turn,
        )
        seen = []

        result = WaitAgentHandler(wait_for_change=lambda timeout_ms: seen.append(timeout_ms) or True).handle(invocation)

        self.assertEqual(seen, [2500])
        self.assertEqual(result.to_mapping(), {"message": "Wait completed.", "timed_out": False})

    def test_wait_agent_handler_reports_turn_config_min_and_max_errors(self) -> None:
        # Rust source: wait.rs error text is based on turn config bounds.
        turn = SimpleNamespace(
            config=SimpleNamespace(
                multi_agent_v2=SimpleNamespace(
                    min_wait_timeout_ms=1500,
                    default_wait_timeout_ms=2500,
                    max_wait_timeout_ms=4500,
                )
            )
        )
        handler = WaitAgentHandler(wait_for_change=lambda timeout_ms: True)
        too_low = ToolInvocation(
            call_id="call-wait-low",
            tool_name=ToolName.plain("wait_agent"),
            payload=ToolPayload.function('{"timeout_ms":1499}'),
            turn=turn,
        )
        too_high = ToolInvocation(
            call_id="call-wait-high",
            tool_name=ToolName.plain("wait_agent"),
            payload=ToolPayload.function('{"timeout_ms":4501}'),
            turn=turn,
        )

        with self.assertRaisesRegex(FunctionCallError, "timeout_ms must be at least 1500"):
            handler.handle(too_low)
        with self.assertRaisesRegex(FunctionCallError, "timeout_ms must be at most 4500"):
            handler.handle(too_high)

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

    def test_list_agents_handler_registers_root_and_passes_session_source(self) -> None:
        # Rust source: tools/handlers/multi_agents_v2/list_agents.rs registers root then calls list_agents.
        session_source = SessionSource.exec()
        invocation = ToolInvocation(
            call_id="call-list",
            tool_name=ToolName.plain("list_agents"),
            payload=ToolPayload.function('{"path_prefix":"root/a"}'),
            session=SimpleNamespace(conversation_id="thread-root"),
            turn=SimpleNamespace(session_source=session_source),
        )
        registered = []
        listed = []

        def register_session_root(conversation_id, source):
            registered.append((conversation_id, source))

        def list_agents(source, path_prefix):
            listed.append((source, path_prefix))
            return ({"thread_id": "thread-a", "status": "running"},)

        result = ListAgentsHandler(
            list_agents=list_agents,
            register_session_root=register_session_root,
        ).handle(invocation)

        self.assertEqual(registered, [("thread-root", session_source)])
        self.assertEqual(listed, [(session_source, "root/a")])
        self.assertEqual(result.to_mapping(), {"agents": [{"thread_id": "thread-a", "status": "running"}]})

    def test_close_agent_handler_returns_previous_status(self) -> None:
        invocation = ToolInvocation(
            call_id="call-close",
            tool_name=ToolName.plain("close_agent"),
            payload=ToolPayload.function('{"target":"agent-a"}'),
        )
        result = CloseAgentHandler(lambda target: AgentStatus.running()).handle(invocation)
        self.assertEqual(result.to_mapping(), {"previous_status": "running"})

    def test_close_agent_handler_rejects_root_agent_like_rust(self) -> None:
        # Rust source: tools/handlers/multi_agents_v2/close_agent.rs rejects root agent_path.
        invocation = ToolInvocation(
            call_id="call-close",
            tool_name=ToolName.plain("close_agent"),
            payload=ToolPayload.function('{"target":"root"}'),
        )

        handler = CloseAgentHandler(
            close_agent=lambda target: AgentStatus.running(),
            get_agent_metadata=lambda target: {"agent_path": AgentPath.root()},
        )

        with self.assertRaisesRegex(FunctionCallError, "root is not a spawned agent"):
            handler.handle(invocation)

    def test_close_agent_handler_allows_non_root_metadata_and_returns_previous_status(self) -> None:
        # Rust source: close_agent captures previous status before closing and returns it.
        invocation = ToolInvocation(
            call_id="call-close",
            tool_name=ToolName.plain("close_agent"),
            payload=ToolPayload.function('{"target":"agent-a"}'),
        )
        seen = []

        def close_agent(target):
            seen.append(target)
            return AgentStatus.completed("done")

        handler = CloseAgentHandler(
            close_agent=close_agent,
            get_agent_metadata=lambda target: SimpleNamespace(agent_path="/root/agent_a"),
        )

        result = handler.handle(invocation)

        self.assertEqual(seen, ["agent-a"])
        self.assertEqual(result.to_mapping(), {"previous_status": {"completed": "done"}})

    def test_message_handlers_parse_and_validate_blank_messages(self) -> None:
        payload = ToolPayload.function('{"target":"agent-a","message":"hello"}')
        self.assertEqual(SendMessageHandler().parse_args(payload).message, "hello")
        self.assertEqual(FollowupTaskHandler().parse_args(payload).target, "agent-a")
        with self.assertRaises(FunctionCallError):
            SendMessageHandler().parse_args(ToolPayload.function('{"target":"agent-a","message":""}'))

    def test_send_message_handler_dispatches_queue_only_mode(self) -> None:
        # Rust source: tools/handlers/multi_agents_v2/send_message.rs uses MessageDeliveryMode::QueueOnly.
        invocation = ToolInvocation(
            call_id="call-send",
            tool_name=ToolName.plain("send_message"),
            payload=ToolPayload.function('{"target":"agent-a","message":"hello"}'),
        )
        seen = []

        def send_message(mode, target, message):
            seen.append((mode, target, message))
            return None

        output = SendMessageHandler(send_message).handle(invocation)

        self.assertEqual(seen, [(MessageDeliveryMode.QUEUE_ONLY, "agent-a", "hello")])
        self.assertEqual(output.into_text(), "")
        self.assertTrue(output.success_for_logging())

    def test_followup_task_handler_dispatches_trigger_turn_mode(self) -> None:
        # Rust source: tools/handlers/multi_agents_v2/followup_task.rs uses MessageDeliveryMode::TriggerTurn.
        invocation = ToolInvocation(
            call_id="call-followup",
            tool_name=ToolName.plain("followup_task"),
            payload=ToolPayload.function('{"target":"agent-a","message":"next"}'),
        )
        seen = []

        def send_message(mode, target, message):
            seen.append((mode, target, message))
            return None

        output = FollowupTaskHandler(send_message).handle(invocation)

        self.assertEqual(seen, [(MessageDeliveryMode.TRIGGER_TURN, "agent-a", "next")])
        self.assertEqual(output.into_text(), "")
        self.assertTrue(output.success_for_logging())

    def test_message_tool_rejects_missing_agent_path_like_rust(self) -> None:
        # Rust source: message_tool.rs requires receiver metadata to contain agent_path.
        seen = []

        with self.assertRaisesRegex(FunctionCallError, "target agent is missing an agent_path"):
            handle_message_string_tool(
                mode=MessageDeliveryMode.QUEUE_ONLY,
                target="agent-a",
                message="hello",
                send_message=lambda mode, target, message: seen.append((mode, target, message)),
                get_agent_metadata=lambda target: {},
            )

        self.assertEqual(seen, [])

    def test_followup_task_rejects_root_agent_like_rust(self) -> None:
        # Rust source: message_tool.rs rejects TriggerTurn delivery to the root agent.
        invocation = ToolInvocation(
            call_id="call-followup",
            tool_name=ToolName.plain("followup_task"),
            payload=ToolPayload.function('{"target":"root","message":"next"}'),
        )
        seen = []
        handler = FollowupTaskHandler(
            send_message=lambda mode, target, message: seen.append((mode, target, message)),
            get_agent_metadata=lambda target: {"agent_path": AgentPath.root()},
        )

        with self.assertRaisesRegex(FunctionCallError, "Tasks can't be assigned to the root agent"):
            handler.handle(invocation)

        self.assertEqual(seen, [])

    def test_send_message_allows_root_agent_queue_only_like_rust(self) -> None:
        # Rust source: only TriggerTurn followup_task rejects the root target.
        invocation = ToolInvocation(
            call_id="call-send",
            tool_name=ToolName.plain("send_message"),
            payload=ToolPayload.function('{"target":"root","message":"hello"}'),
        )
        seen = []
        handler = SendMessageHandler(
            send_message=lambda mode, target, message: seen.append((mode, target, message)),
            get_agent_metadata=lambda target: {"agent_path": AgentPath.root()},
        )

        output = handler.handle(invocation)

        self.assertEqual(seen, [(MessageDeliveryMode.QUEUE_ONLY, "root", "hello")])
        self.assertEqual(output.into_text(), "")

    def test_handler_specs_and_empty_success_output(self) -> None:
        self.assertEqual(ListAgentsHandler().tool_name(), ToolName.plain("list_agents"))
        self.assertEqual(CloseAgentHandler().spec()["name"], "close_agent")
        self.assertEqual(SendMessageHandler().spec()["name"], "send_message")
        self.assertEqual(FollowupTaskHandler().spec()["name"], "followup_task")
        self.assertEqual(SpawnAgentHandler().spec()["name"], "spawn_agent")
        self.assertEqual(WaitAgentHandler().spec()["name"], "wait_agent")
        resume_spec = ResumeAgentHandler().spec()
        self.assertEqual(resume_spec["type"], "namespace")
        self.assertEqual(resume_spec["tools"][0]["name"], "resume_agent")
        self.assertEqual(successful_empty_message_output().into_text(), "")

    def test_list_agents_result_serializes_like_tool_output(self) -> None:
        result = ListAgentsResult(({"thread_id": "thread-a"},))
        self.assertEqual(result.code_mode_result(ToolPayload.function("{}")), {"agents": [{"thread_id": "thread-a"}]})


if __name__ == "__main__":
    unittest.main()
