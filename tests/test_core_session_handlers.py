import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.session.handlers import (
    CompactTask,
    NoActiveTurnForUserInput,
    RegularTask,
    ResponseItemTurnInput,
    UserInputTurnInput,
    UserShellCommandTask,
    dispatch_session_op,
    thread_rollback,
)
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.protocol import (
    CodexErrorInfo,
    ConversationAudioParams,
    ConversationStartParams,
    ConversationTextParams,
    DynamicToolCallOutputContentItem,
    DynamicToolResponse,
    ElicitationAction,
    ErrorEvent,
    EventMsg,
    ExecPolicyAmendment,
    GuardianAssessmentAction,
    GuardianAssessmentEvent,
    GuardianAssessmentStatus,
    GuardianCommandSource,
    InterAgentCommunication,
    McpServerRefreshConfig,
    NetworkPermissions,
    Op,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsResponse,
    RealtimeAudioFrame,
    RealtimeConversationListVoicesResponseEvent,
    RealtimeOutputModality,
    RealtimeVoicesList,
    ReviewDecision,
    ReviewRequest,
    ReviewTarget,
    RequestId,
    RolloutItem,
    ThreadMemoryMode,
    ThreadSettingsOverrides,
    ThreadRolledBackEvent,
)
from pycodex.rollout import append_response_item_to_rollout


def _message_payload(role: str, text: str) -> dict[str, object]:
    content_type = "input_text" if role == "user" else "output_text"
    return {
        "type": "message",
        "role": role,
        "content": [{"type": content_type, "text": text}],
    }


def _append_turn(path: Path, index: int) -> None:
    append_response_item_to_rollout(path, _message_payload("user", f"turn {index} user"))
    append_response_item_to_rollout(path, _message_payload("assistant", f"turn {index} assistant"))


def _history_texts(session: InMemoryCodexSession) -> list[str]:
    return [item.content[0].text for item in session.history]


class SessionThreadRollbackHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_thread_rollback_requires_positive_num_turns(self) -> None:
        # Rust test: thread_rollback_fails_when_num_turns_is_zero
        session = InMemoryCodexSession(cwd="C:/work/project")

        await thread_rollback(session, "sub-1", 0)

        event = session.emitted_events[-1]
        self.assertEqual(event.type, "error")
        self.assertEqual(event.payload.message, "num_turns must be >= 1")
        self.assertEqual(event.payload.codex_error_info, CodexErrorInfo.thread_rollback_failed())

    async def test_thread_rollback_fails_when_turn_in_progress(self) -> None:
        # Rust test: thread_rollback_fails_when_turn_in_progress
        session = InMemoryCodexSession(cwd="C:/work/project")
        session.active_turn_in_progress = True

        await thread_rollback(session, "sub-1", 1)

        event = session.emitted_events[-1]
        self.assertEqual(event.type, "error")
        self.assertEqual(event.payload.message, "Cannot rollback while a turn is in progress.")
        self.assertEqual(event.payload.codex_error_info, CodexErrorInfo.thread_rollback_failed())

    async def test_thread_rollback_fails_without_persisted_thread_history(self) -> None:
        # Rust test: thread_rollback_fails_without_persisted_thread_history
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            history=[_message_payload("user", "existing")],
        )

        await thread_rollback(session, "sub-1", 1)

        event = session.emitted_events[-1]
        self.assertEqual(event.type, "error")
        self.assertEqual(event.payload.message, "thread rollback requires persisted thread history")
        self.assertEqual(event.payload.codex_error_info, CodexErrorInfo.thread_rollback_failed())
        self.assertEqual(session.history[0]["content"][0]["text"], "existing")

    async def test_thread_rollback_replays_with_marker_and_persists_marker(self) -> None:
        # Rust test: thread_rollback_drops_last_turn_from_history
        with tempfile.TemporaryDirectory() as temp_dir:
            rollout_path = Path(temp_dir) / "rollout.jsonl"
            _append_turn(rollout_path, 1)
            _append_turn(rollout_path, 2)
            session = InMemoryCodexSession(cwd=temp_dir)
            session.rollout_path = rollout_path

            await thread_rollback(session, "sub-1", 1)

            self.assertEqual(_history_texts(session), ["turn 1 user", "turn 1 assistant"])
            event = session.emitted_events[-1]
            self.assertEqual(event.type, "thread_rolled_back")
            self.assertEqual(event.payload, ThreadRolledBackEvent(1))
            self.assertEqual(
                session.persisted_rollout_items,
                [RolloutItem.event_msg(EventMsg.with_payload("thread_rolled_back", ThreadRolledBackEvent(1)))],
            )
            self.assertEqual(rollout_path.read_text(encoding="utf-8").count("thread_rolled_back"), 1)

    async def test_thread_rollback_replays_cumulatively_from_persisted_markers(self) -> None:
        # Rust test: thread_rollback_persists_marker_and_replays_cumulatively
        with tempfile.TemporaryDirectory() as temp_dir:
            rollout_path = Path(temp_dir) / "rollout.jsonl"
            _append_turn(rollout_path, 1)
            _append_turn(rollout_path, 2)
            _append_turn(rollout_path, 3)
            session = InMemoryCodexSession(cwd=temp_dir)
            session.rollout_path = rollout_path

            await thread_rollback(session, "sub-1", 1)
            await thread_rollback(session, "sub-1", 1)

            self.assertEqual(_history_texts(session), ["turn 1 user", "turn 1 assistant"])
            self.assertEqual(rollout_path.read_text(encoding="utf-8").count("thread_rolled_back"), 2)

    async def test_dispatch_session_op_routes_thread_rollback_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::submission_loop Op::ThreadRollback arm
        with tempfile.TemporaryDirectory() as temp_dir:
            rollout_path = Path(temp_dir) / "rollout.jsonl"
            _append_turn(rollout_path, 1)
            _append_turn(rollout_path, 2)
            session = InMemoryCodexSession(cwd=temp_dir)
            session.rollout_path = rollout_path

            should_exit = await dispatch_session_op(session, "sub-1", Op.thread_rollback(1))

            self.assertFalse(should_exit)
            self.assertEqual(_history_texts(session), ["turn 1 user", "turn 1 assistant"])
            self.assertEqual(session.emitted_events[-1].type, "thread_rolled_back")

    async def test_dispatch_session_op_accepts_mapping_thread_rollback(self) -> None:
        # Rust source: session::handlers::submission_loop Op::ThreadRollback arm
        with tempfile.TemporaryDirectory() as temp_dir:
            rollout_path = Path(temp_dir) / "rollout.jsonl"
            _append_turn(rollout_path, 1)
            session = InMemoryCodexSession(cwd=temp_dir)
            session.rollout_path = rollout_path

            should_exit = await dispatch_session_op(session, "sub-1", {"type": "thread_rollback", "num_turns": 1})

            self.assertFalse(should_exit)
            self.assertEqual(_history_texts(session), [])
            self.assertEqual(session.emitted_events[-1].payload, ThreadRolledBackEvent(1))

    async def test_dispatch_session_op_routes_request_permissions_response_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::submission_loop Op::RequestPermissionsResponse arm
        calls: list[tuple[str, object]] = []

        async def notify_request_permissions_response(call_id: str, response: object) -> None:
            calls.append((call_id, response))

        session = SimpleNamespace(notify_request_permissions_response=notify_request_permissions_response)
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op.request_permissions_response("perm-1", response))

        self.assertFalse(should_exit)
        self.assertEqual(calls, [("perm-1", response)])

    async def test_dispatch_session_op_accepts_mapping_request_permissions_response(self) -> None:
        # Rust source: session::handlers::submission_loop Op::RequestPermissionsResponse arm
        calls: list[tuple[str, object]] = []

        async def notify_request_permissions_response(call_id: str, response: object) -> None:
            calls.append((call_id, response))

        session = SimpleNamespace(notify_request_permissions_response=notify_request_permissions_response)
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op.request_permissions_response("perm-1", response).to_mapping())

        self.assertFalse(should_exit)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "perm-1")
        self.assertEqual(calls[0][1], response)

    async def test_dispatch_session_op_routes_patch_approval_abort_to_interrupt(self) -> None:
        # Rust source: session::handlers::patch_approval abort branch
        calls: list[tuple[str, object]] = []
        interrupts: list[str] = []

        async def interrupt_task() -> None:
            interrupts.append("interrupt")

        async def notify_approval(call_id: str, decision: object) -> None:
            calls.append((call_id, decision))

        session = SimpleNamespace(interrupt_task=interrupt_task, notify_approval=notify_approval)

        should_exit = await dispatch_session_op(session, "sub-1", Op.patch_approval("patch-1", ReviewDecision.abort()))

        self.assertFalse(should_exit)
        self.assertEqual(interrupts, ["interrupt"])
        self.assertEqual(calls, [])

    async def test_dispatch_session_op_routes_patch_approval_non_abort_to_notify(self) -> None:
        # Rust source: session::handlers::patch_approval non-abort branch
        calls: list[tuple[str, object]] = []
        interrupts: list[str] = []

        async def interrupt_task() -> None:
            interrupts.append("interrupt")

        async def notify_approval(call_id: str, decision: object) -> None:
            calls.append((call_id, decision))

        session = SimpleNamespace(interrupt_task=interrupt_task, notify_approval=notify_approval)

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op.patch_approval("patch-1", ReviewDecision.denied()).to_mapping(),
        )

        self.assertFalse(should_exit)
        self.assertEqual(interrupts, [])
        self.assertEqual(calls, [("patch-1", ReviewDecision.denied())])

    async def test_dispatch_session_op_routes_user_input_answer_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::submission_loop Op::UserInputAnswer arm
        calls: list[tuple[str, object]] = []

        async def notify_user_input_response(call_id: str, response: object) -> None:
            calls.append((call_id, response))

        session = SimpleNamespace(notify_user_input_response=notify_user_input_response)
        response = {"answers": {}}

        should_exit = await dispatch_session_op(session, "sub-1", Op.user_input_answer("input-1", response))

        self.assertFalse(should_exit)
        self.assertEqual(calls, [("input-1", response)])

    async def test_dispatch_session_op_accepts_legacy_request_user_input_response_mapping(self) -> None:
        # Rust source: protocol alias request_user_input_response -> Op::UserInputAnswer
        calls: list[tuple[str, object]] = []

        async def notify_user_input_response(call_id: str, response: object) -> None:
            calls.append((call_id, response))

        session = SimpleNamespace(notify_user_input_response=notify_user_input_response)

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            {"type": "request_user_input_response", "id": "input-1", "response": {"answers": {}}},
        )

        self.assertFalse(should_exit)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "input-1")
        self.assertEqual(calls[0][1].to_mapping(), {"answers": {}})

    async def test_dispatch_session_op_routes_dynamic_tool_response_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::submission_loop Op::DynamicToolResponse arm
        calls: list[tuple[str, object]] = []

        async def notify_dynamic_tool_response(call_id: str, response: object) -> None:
            calls.append((call_id, response))

        session = SimpleNamespace(notify_dynamic_tool_response=notify_dynamic_tool_response)
        response = DynamicToolResponse((DynamicToolCallOutputContentItem.input_text("done"),), True)

        should_exit = await dispatch_session_op(session, "sub-1", Op.dynamic_tool_response("dyn-1", response))

        self.assertFalse(should_exit)
        self.assertEqual(calls, [("dyn-1", response)])

    async def test_dispatch_session_op_accepts_mapping_dynamic_tool_response(self) -> None:
        # Rust source: session::handlers::submission_loop Op::DynamicToolResponse arm
        calls: list[tuple[str, object]] = []

        async def notify_dynamic_tool_response(call_id: str, response: object) -> None:
            calls.append((call_id, response))

        session = SimpleNamespace(notify_dynamic_tool_response=notify_dynamic_tool_response)
        response = DynamicToolResponse((DynamicToolCallOutputContentItem.input_text("done"),), True)

        should_exit = await dispatch_session_op(session, "sub-1", Op.dynamic_tool_response("dyn-1", response).to_mapping())

        self.assertFalse(should_exit)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "dyn-1")
        self.assertEqual(calls[0][1], response)

    async def test_dispatch_session_op_refresh_mcp_servers_records_pending_config_with_setter(self) -> None:
        # Rust source: session::handlers::refresh_mcp_servers and Op::RefreshMcpServers arm
        calls: list[object] = []
        config = McpServerRefreshConfig(mcp_servers={"local": {}}, mcp_oauth_credentials_store_mode="read_write")

        async def set_pending_mcp_server_refresh_config(value: object) -> None:
            calls.append(value)

        session = SimpleNamespace(set_pending_mcp_server_refresh_config=set_pending_mcp_server_refresh_config)

        should_exit = await dispatch_session_op(session, "sub-1", Op.refresh_mcp_servers(config))

        self.assertFalse(should_exit)
        self.assertEqual(calls, [config])

    async def test_dispatch_session_op_refresh_mcp_servers_accepts_mapping_and_sets_slot(self) -> None:
        # Rust source: session::handlers::submission_loop Op::RefreshMcpServers arm
        session = SimpleNamespace(pending_mcp_server_refresh_config=None)

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            {
                "type": "refresh_mcp_servers",
                "config": {
                    "mcp_servers": {"local": {}},
                    "mcp_oauth_credentials_store_mode": "read_write",
                },
            },
        )

        self.assertFalse(should_exit)
        self.assertEqual(
            session.pending_mcp_server_refresh_config,
            McpServerRefreshConfig(mcp_servers={"local": {}}, mcp_oauth_credentials_store_mode="read_write"),
        )

    async def test_dispatch_session_op_resolve_elicitation_accept_defaults_missing_content_to_empty_object(self) -> None:
        # Rust source: session::handlers::resolve_elicitation accept legacy fallback branch
        calls: list[tuple[str, object, object]] = []

        async def resolve_elicitation(server_name: str, request_id: object, response: object) -> None:
            calls.append((server_name, request_id, response))

        session = SimpleNamespace(resolve_elicitation=resolve_elicitation)

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op.resolve_elicitation("server-a", RequestId.string("request-1"), ElicitationAction.ACCEPT),
        )

        self.assertFalse(should_exit)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "server-a")
        self.assertEqual(calls[0][1], "request-1")
        self.assertEqual(calls[0][2].action, ElicitationAction.ACCEPT)
        self.assertEqual(calls[0][2].content, {})

    async def test_dispatch_session_op_resolve_elicitation_decline_drops_content_and_accepts_mapping(self) -> None:
        # Rust source: session::handlers::resolve_elicitation decline/cancel content branch
        calls: list[tuple[str, object, object]] = []

        async def resolve_elicitation(server_name: str, request_id: object, response: object) -> None:
            calls.append((server_name, request_id, response))

        session = SimpleNamespace(resolve_elicitation=resolve_elicitation)

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            {
                "type": "resolve_elicitation",
                "server_name": "server-a",
                "request_id": 7,
                "decision": "decline",
                "content": {"ignored": True},
                "meta": {"source": "test"},
            },
        )

        self.assertFalse(should_exit)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 7)
        self.assertEqual(calls[0][2].action, ElicitationAction.DECLINE)
        self.assertIsNone(calls[0][2].content)
        self.assertEqual(calls[0][2].meta, {"source": "test"})

    async def test_dispatch_session_op_resolve_elicitation_swallows_resolver_failure(self) -> None:
        # Rust source: session::handlers::resolve_elicitation warn-and-continue failure branch
        calls: list[tuple[str, object, object]] = []

        async def resolve_elicitation(server_name: str, request_id: object, response: object) -> None:
            calls.append((server_name, request_id, response))
            raise RuntimeError("missing pending request")

        session = SimpleNamespace(resolve_elicitation=resolve_elicitation)

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op.resolve_elicitation("server-a", RequestId.integer(9), ElicitationAction.CANCEL, content={"ignored": True}),
        )

        self.assertFalse(should_exit)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 9)
        self.assertEqual(calls[0][2].action, ElicitationAction.CANCEL)
        self.assertIsNone(calls[0][2].content)

    async def test_dispatch_session_op_review_resolves_request_and_spawns_review_thread(self) -> None:
        # Rust source: session::handlers::review success branch and Op::Review arm
        calls: list[object] = []
        request = ReviewRequest(ReviewTarget.custom("check the migration"))
        turn_context = SimpleNamespace(cwd=Path("C:/work/project"), sub_id="sub-1")
        config = SimpleNamespace(name="config")

        async def new_default_turn_with_sub_id(sub_id: str) -> object:
            calls.append(("new_default_turn_with_sub_id", sub_id))
            return turn_context

        async def maybe_emit_unknown_model_warning_for_turn(context: object) -> None:
            calls.append(("maybe_emit_unknown_model_warning_for_turn", context))

        async def mcp_elicitation_reviewer() -> str:
            return "reviewer"

        async def refresh_mcp_servers_if_requested(context: object, reviewer: object) -> None:
            calls.append(("refresh_mcp_servers_if_requested", context, reviewer))

        async def spawn_review_thread(config_value: object, context: object, sub_id: str, resolved: object) -> None:
            calls.append(("spawn_review_thread", config_value, context, sub_id, resolved))

        session = SimpleNamespace(
            config=config,
            new_default_turn_with_sub_id=new_default_turn_with_sub_id,
            maybe_emit_unknown_model_warning_for_turn=maybe_emit_unknown_model_warning_for_turn,
            mcp_elicitation_reviewer=mcp_elicitation_reviewer,
            refresh_mcp_servers_if_requested=refresh_mcp_servers_if_requested,
            spawn_review_thread=spawn_review_thread,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op("review", {"review_request": request}))

        self.assertFalse(should_exit)
        self.assertEqual(calls[0], ("new_default_turn_with_sub_id", "sub-1"))
        self.assertIn(("maybe_emit_unknown_model_warning_for_turn", turn_context), calls)
        self.assertIn(("refresh_mcp_servers_if_requested", turn_context, "reviewer"), calls)
        spawn = calls[-1]
        self.assertEqual(spawn[0], "spawn_review_thread")
        self.assertIs(spawn[1], config)
        self.assertIs(spawn[2], turn_context)
        self.assertEqual(spawn[3], "sub-1")
        self.assertEqual(spawn[4].target, request.target)

    async def test_dispatch_session_op_review_emits_error_when_request_resolution_fails(self) -> None:
        # Rust source: session::handlers::review resolve_review_request error branch
        events: list[tuple[object, object]] = []
        request = ReviewRequest(ReviewTarget.custom("check the migration"))
        turn_context = SimpleNamespace(sub_id="sub-1")

        async def new_default_turn_with_sub_id(_sub_id: str) -> object:
            return turn_context

        async def send_event(context: object, msg: object) -> None:
            events.append((context, msg))

        async def spawn_review_thread(_config: object, _context: object, _sub_id: str, _resolved: object) -> None:
            raise AssertionError("spawn_review_thread should not be called")

        session = SimpleNamespace(
            new_default_turn_with_sub_id=new_default_turn_with_sub_id,
            send_event=send_event,
            spawn_review_thread=spawn_review_thread,
        )

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            {"type": "review", "review_request": request.to_mapping()},
        )

        self.assertFalse(should_exit)
        self.assertEqual(len(events), 1)
        self.assertIs(events[0][0], turn_context)
        self.assertEqual(events[0][1].type, "error")
        self.assertEqual(events[0][1].payload.codex_error_info, CodexErrorInfo.other())

    async def test_dispatch_session_op_inter_agent_communication_queues_and_starts_pending_work(self) -> None:
        # Rust source: session::handlers::inter_agent_communication trigger_turn branch
        calls: list[object] = []
        communication = InterAgentCommunication("/root", "/root/worker", "hello worker", True)

        class InputQueue:
            async def enqueue_mailbox_communication(self, value: object) -> None:
                calls.append(("enqueue_mailbox_communication", value))

        async def maybe_start_turn_for_pending_work_with_sub_id(sub_id: str) -> None:
            calls.append(("maybe_start_turn_for_pending_work_with_sub_id", sub_id))

        session = SimpleNamespace(
            input_queue=InputQueue(),
            maybe_start_turn_for_pending_work_with_sub_id=maybe_start_turn_for_pending_work_with_sub_id,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op.inter_agent_communication(communication))

        self.assertFalse(should_exit)
        self.assertEqual(
            calls,
            [
                ("enqueue_mailbox_communication", communication),
                ("maybe_start_turn_for_pending_work_with_sub_id", "sub-1"),
            ],
        )

    async def test_dispatch_session_op_inter_agent_communication_mapping_without_trigger_only_queues(self) -> None:
        # Rust source: session::handlers::inter_agent_communication trigger_turn false branch
        calls: list[object] = []
        communication = InterAgentCommunication("/root", "/root/worker", "hello worker", False)

        async def enqueue_mailbox_communication(value: object) -> None:
            calls.append(("enqueue_mailbox_communication", value))

        async def maybe_start_turn_for_pending_work_with_sub_id(sub_id: str) -> None:
            calls.append(("maybe_start_turn_for_pending_work_with_sub_id", sub_id))

        session = SimpleNamespace(
            enqueue_mailbox_communication=enqueue_mailbox_communication,
            maybe_start_turn_for_pending_work_with_sub_id=maybe_start_turn_for_pending_work_with_sub_id,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op.inter_agent_communication(communication).to_mapping())

        self.assertFalse(should_exit)
        self.assertEqual(calls, [("enqueue_mailbox_communication", communication)])

    async def test_dispatch_session_op_approve_guardian_denied_action_injects_developer_approval(self) -> None:
        # Rust source: session::handlers::approve_guardian_denied_action denied branch
        injected: list[tuple[list[object], object]] = []
        event = GuardianAssessmentEvent(
            id="guardian-1",
            status=GuardianAssessmentStatus.DENIED,
            action=GuardianAssessmentAction.command_action(
                GuardianCommandSource.SHELL,
                "rm temp.txt",
                Path("C:/work/project"),
            ),
        )

        async def inject_no_new_turn(items: list[object], current_turn_context: object) -> None:
            injected.append((items, current_turn_context))

        session = SimpleNamespace(inject_no_new_turn=inject_no_new_turn)

        should_exit = await dispatch_session_op(session, "sub-1", Op.approve_guardian_denied_action(event))

        self.assertFalse(should_exit)
        self.assertEqual(len(injected), 1)
        self.assertIsNone(injected[0][1])
        item = injected[0][0][0]
        self.assertEqual(item.type, "message")
        self.assertEqual(item.role, "developer")
        text = item.content[0].text
        self.assertIn("The user has manually approved a specific action that was previously `Rejected`.", text)
        self.assertIn("Treat this as approval to perform that exact action", text)
        self.assertIn('"outcome": "allowed"', text)
        self.assertIn('"command": "rm temp.txt"', text)

    async def test_dispatch_session_op_approve_guardian_denied_action_ignores_non_denied_event(self) -> None:
        # Rust source: session::handlers::approve_guardian_denied_action non-denied guard branch
        injected: list[tuple[list[object], object]] = []
        event = GuardianAssessmentEvent(
            id="guardian-1",
            status=GuardianAssessmentStatus.APPROVED,
            action=GuardianAssessmentAction.command_action(
                GuardianCommandSource.SHELL,
                "rm temp.txt",
                Path("C:/work/project"),
            ),
        )

        async def inject_no_new_turn(items: list[object], current_turn_context: object) -> None:
            injected.append((items, current_turn_context))

        session = SimpleNamespace(inject_no_new_turn=inject_no_new_turn)

        should_exit = await dispatch_session_op(session, "sub-1", Op.approve_guardian_denied_action(event).to_mapping())

        self.assertFalse(should_exit)
        self.assertEqual(injected, [])

    async def test_dispatch_session_op_routes_exec_approval_abort_to_interrupt(self) -> None:
        # Rust source: session::handlers::exec_approval abort branch
        calls: list[tuple[str, object]] = []
        interrupts: list[str] = []

        async def interrupt_task() -> None:
            interrupts.append("interrupt")

        async def notify_approval(call_id: str, decision: object) -> None:
            calls.append((call_id, decision))

        session = SimpleNamespace(interrupt_task=interrupt_task, notify_approval=notify_approval)

        should_exit = await dispatch_session_op(session, "sub-1", Op.exec_approval("approval-1", ReviewDecision.abort()))

        self.assertFalse(should_exit)
        self.assertEqual(interrupts, ["interrupt"])
        self.assertEqual(calls, [])

    async def test_dispatch_session_op_routes_exec_approval_non_abort_to_notify(self) -> None:
        # Rust source: session::handlers::exec_approval non-abort branch
        calls: list[tuple[str, object]] = []
        interrupts: list[str] = []

        async def interrupt_task() -> None:
            interrupts.append("interrupt")

        async def notify_approval(call_id: str, decision: object) -> None:
            calls.append((call_id, decision))

        session = SimpleNamespace(interrupt_task=interrupt_task, notify_approval=notify_approval)

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op.exec_approval("approval-1", ReviewDecision.approved_for_session(), turn_id="turn-1").to_mapping(),
        )

        self.assertFalse(should_exit)
        self.assertEqual(interrupts, [])
        self.assertEqual(calls, [("approval-1", ReviewDecision.approved_for_session())])

    async def test_dispatch_session_op_exec_approval_persists_and_records_amendment(self) -> None:
        # Rust source: session::handlers::exec_approval approved execpolicy amendment branch
        persisted: list[object] = []
        recorded: list[tuple[str, object]] = []
        calls: list[tuple[str, object]] = []
        amendment = ExecPolicyAmendment.new(["npm", "test"])
        decision = ReviewDecision.approved_execpolicy_amendment(amendment)

        async def persist_execpolicy_amendment(value: object) -> None:
            persisted.append(value)

        async def record_execpolicy_amendment_message(turn_id: str, value: object) -> None:
            recorded.append((turn_id, value))

        async def notify_approval(call_id: str, value: object) -> None:
            calls.append((call_id, value))

        session = SimpleNamespace(
            persist_execpolicy_amendment=persist_execpolicy_amendment,
            record_execpolicy_amendment_message=record_execpolicy_amendment_message,
            notify_approval=notify_approval,
        )

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op.exec_approval("approval-1", decision, turn_id="turn-1"),
        )

        self.assertFalse(should_exit)
        self.assertEqual(persisted, [amendment])
        self.assertEqual(recorded, [("turn-1", amendment)])
        self.assertEqual(calls, [("approval-1", decision)])

    async def test_dispatch_session_op_exec_approval_warns_and_still_notifies_when_amendment_persist_fails(self) -> None:
        # Rust source: session::handlers::exec_approval warning-and-continue amendment failure branch
        recorded: list[tuple[str, object]] = []
        calls: list[tuple[str, object]] = []
        events: list[object] = []
        amendment = ExecPolicyAmendment.new(["npm", "test"])
        decision = ReviewDecision.approved_execpolicy_amendment(amendment)

        async def persist_execpolicy_amendment(_value: object) -> None:
            raise RuntimeError("disk full")

        async def record_execpolicy_amendment_message(turn_id: str, value: object) -> None:
            recorded.append((turn_id, value))

        async def notify_approval(call_id: str, value: object) -> None:
            calls.append((call_id, value))

        async def send_event_raw(event: object) -> None:
            events.append(event)

        session = SimpleNamespace(
            persist_execpolicy_amendment=persist_execpolicy_amendment,
            record_execpolicy_amendment_message=record_execpolicy_amendment_message,
            notify_approval=notify_approval,
            send_event_raw=send_event_raw,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op.exec_approval("approval-1", decision))

        self.assertFalse(should_exit)
        self.assertEqual(recorded, [])
        self.assertEqual(calls, [("approval-1", decision)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "approval-1")
        self.assertEqual(events[0].msg.type, "warning")
        self.assertIn("Failed to apply execpolicy amendment: disk full", events[0].msg.payload.message)

    async def test_dispatch_session_op_run_user_shell_command_uses_active_turn_auxiliary(self) -> None:
        # Rust source: session::handlers::run_user_shell_command active-turn branch
        calls: list[tuple[object, str, object, str]] = []

        async def active_turn_context_and_cancellation_token() -> tuple[str, str]:
            return ("turn-context", "cancel-token")

        async def execute_user_shell_command(turn_context: object, command: str, cancellation_token: object, mode: str) -> None:
            calls.append((turn_context, command, cancellation_token, mode))

        session = SimpleNamespace(
            active_turn_context_and_cancellation_token=active_turn_context_and_cancellation_token,
            execute_user_shell_command=execute_user_shell_command,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op.run_user_shell_command("echo hi"))

        self.assertFalse(should_exit)
        self.assertEqual(calls, [("turn-context", "echo hi", "cancel-token", "active_turn_auxiliary")])

    async def test_dispatch_session_op_run_user_shell_command_spawns_new_task_without_active_turn(self) -> None:
        # Rust source: session::handlers::run_user_shell_command no-active-turn branch
        turns: list[str] = []
        spawned: list[tuple[object, list[object], object]] = []

        async def active_turn_context_and_cancellation_token() -> None:
            return None

        async def new_default_turn_with_sub_id(sub_id: str) -> str:
            turns.append(sub_id)
            return "new-turn"

        async def spawn_task(turn_context: object, items: list[object], task: object) -> None:
            spawned.append((turn_context, items, task))

        session = SimpleNamespace(
            active_turn_context_and_cancellation_token=active_turn_context_and_cancellation_token,
            new_default_turn_with_sub_id=new_default_turn_with_sub_id,
            spawn_task=spawn_task,
        )

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            {"type": "run_user_shell_command", "command": "echo hi"},
        )

        self.assertFalse(should_exit)
        self.assertEqual(turns, ["sub-1"])
        self.assertEqual(len(spawned), 1)
        self.assertEqual(spawned[0][0], "new-turn")
        self.assertEqual(spawned[0][1], [])
        self.assertEqual(spawned[0][2], UserShellCommandTask("echo hi"))

    async def test_dispatch_session_op_compact_spawns_compact_task_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::compact and Op::Compact dispatch arm
        turns: list[str] = []
        spawned: list[tuple[object, list[object], object]] = []

        async def new_default_turn_with_sub_id(sub_id: str) -> str:
            turns.append(sub_id)
            return "compact-turn"

        async def spawn_task(turn_context: object, items: list[object], task: object) -> None:
            spawned.append((turn_context, items, task))

        session = SimpleNamespace(
            new_default_turn_with_sub_id=new_default_turn_with_sub_id,
            spawn_task=spawn_task,
        )

        should_exit = await dispatch_session_op(session, "sub-1", {"type": "compact"})

        self.assertFalse(should_exit)
        self.assertEqual(turns, ["sub-1"])
        self.assertEqual(spawned, [("compact-turn", [], CompactTask())])

    async def test_dispatch_session_op_interrupt_calls_interrupt_task_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::interrupt and Op::Interrupt dispatch arm
        calls: list[str] = []

        async def interrupt_task() -> None:
            calls.append("interrupt_task")

        session = SimpleNamespace(interrupt_task=interrupt_task)

        should_exit = await dispatch_session_op(session, "sub-1", Op("interrupt"))

        self.assertFalse(should_exit)
        self.assertEqual(calls, ["interrupt_task"])

    async def test_dispatch_session_op_clean_background_terminals_closes_unified_exec_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::clean_background_terminals and Op::CleanBackgroundTerminals dispatch arm
        calls: list[str] = []

        async def close_unified_exec_processes() -> None:
            calls.append("close_unified_exec_processes")

        session = SimpleNamespace(close_unified_exec_processes=close_unified_exec_processes)

        should_exit = await dispatch_session_op(session, "sub-1", Op("clean_background_terminals"))

        self.assertFalse(should_exit)
        self.assertEqual(calls, ["close_unified_exec_processes"])

    async def test_dispatch_session_op_realtime_conversation_list_voices_emits_builtin_voices(self) -> None:
        # Rust source: session::handlers::realtime_conversation_list_voices and Op::RealtimeConversationListVoices arm
        events: list[object] = []

        async def send_event_raw(event: object) -> None:
            events.append(event)

        session = SimpleNamespace(send_event_raw=send_event_raw)

        should_exit = await dispatch_session_op(session, "sub-1", Op.realtime_conversation_list_voices())

        self.assertFalse(should_exit)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "sub-1")
        self.assertEqual(events[0].msg.type, "realtime_conversation_list_voices_response")
        self.assertEqual(
            events[0].msg.payload,
            RealtimeConversationListVoicesResponseEvent(RealtimeVoicesList.builtin()),
        )

    async def test_dispatch_session_op_accepts_mapping_realtime_conversation_list_voices(self) -> None:
        # Rust source: session::handlers::submission_loop Op::RealtimeConversationListVoices arm
        events: list[object] = []

        async def send_event_raw(event: object) -> None:
            events.append(event)

        session = SimpleNamespace(send_event_raw=send_event_raw)

        should_exit = await dispatch_session_op(session, "sub-1", {"type": "realtime_conversation_list_voices"})

        self.assertFalse(should_exit)
        self.assertEqual(events[0].msg.to_mapping()["voices"], RealtimeVoicesList.builtin().to_mapping())

    async def test_dispatch_session_op_realtime_conversation_start_delegates_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::submission_loop Op::RealtimeConversationStart arm
        calls: list[tuple[str, object]] = []
        params = ConversationStartParams(output_modality=RealtimeOutputModality.TEXT)

        async def handle_realtime_conversation_start(sub_id: str, value: object) -> None:
            calls.append((sub_id, value))

        session = SimpleNamespace(handle_realtime_conversation_start=handle_realtime_conversation_start)

        should_exit = await dispatch_session_op(session, "sub-1", Op.realtime_conversation_start(params))

        self.assertFalse(should_exit)
        self.assertEqual(calls, [("sub-1", params)])

    async def test_dispatch_session_op_realtime_conversation_start_emits_error_on_failure(self) -> None:
        # Rust source: session::handlers::submission_loop Op::RealtimeConversationStart error branch
        events: list[object] = []
        params = ConversationStartParams(output_modality=RealtimeOutputModality.TEXT)

        async def handle_realtime_conversation_start(_sub_id: str, _value: object) -> None:
            raise RuntimeError("realtime unavailable")

        async def send_event_raw(event: object) -> None:
            events.append(event)

        session = SimpleNamespace(
            handle_realtime_conversation_start=handle_realtime_conversation_start,
            send_event_raw=send_event_raw,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op.realtime_conversation_start(params))

        self.assertFalse(should_exit)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "sub-1")
        self.assertEqual(events[0].msg.type, "error")
        self.assertEqual(events[0].msg.payload.message, "realtime unavailable")
        self.assertEqual(events[0].msg.payload.codex_error_info, CodexErrorInfo.other())

    async def test_dispatch_session_op_realtime_conversation_audio_text_and_close_delegate(self) -> None:
        # Rust source: session::handlers::submission_loop realtime audio/text/close arms
        calls: list[tuple[str, str, object | None]] = []
        audio = ConversationAudioParams(RealtimeAudioFrame(data="AA==", sample_rate=24000, num_channels=1))
        text = ConversationTextParams("hello")

        async def handle_realtime_conversation_audio(sub_id: str, value: object) -> None:
            calls.append(("audio", sub_id, value))

        async def handle_realtime_conversation_text(sub_id: str, value: object) -> None:
            calls.append(("text", sub_id, value))

        async def handle_realtime_conversation_close(sub_id: str) -> None:
            calls.append(("close", sub_id, None))

        session = SimpleNamespace(
            handle_realtime_conversation_audio=handle_realtime_conversation_audio,
            handle_realtime_conversation_text=handle_realtime_conversation_text,
            handle_realtime_conversation_close=handle_realtime_conversation_close,
        )

        audio_exit = await dispatch_session_op(session, "sub-1", Op.realtime_conversation_audio(audio).to_mapping())
        text_exit = await dispatch_session_op(session, "sub-2", Op.realtime_conversation_text(text))
        close_exit = await dispatch_session_op(session, "sub-3", {"type": "realtime_conversation_close"})

        self.assertFalse(audio_exit)
        self.assertFalse(text_exit)
        self.assertFalse(close_exit)
        self.assertEqual(
            calls,
            [
                ("audio", "sub-1", audio),
                ("text", "sub-2", text),
                ("close", "sub-3", None),
            ],
        )

    async def test_dispatch_session_op_reload_user_config_reloads_layer_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::reload_user_config and Op::ReloadUserConfig dispatch arm
        calls: list[str] = []

        async def reload_user_config_layer() -> None:
            calls.append("reload_user_config_layer")

        session = SimpleNamespace(reload_user_config_layer=reload_user_config_layer)

        should_exit = await dispatch_session_op(session, "sub-1", {"type": "reload_user_config"})

        self.assertFalse(should_exit)
        self.assertEqual(calls, ["reload_user_config_layer"])

    async def test_dispatch_session_op_user_input_steers_active_turn_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::user_input_or_turn_inner active-turn steer branch
        calls: list[object] = []
        items = ({"type": "text", "text": "hello"},)
        environments = ("env-1",)
        schema = {"type": "object"}
        metadata = {"client": "desktop"}
        additional_context = {"note": "nearby"}

        class Telemetry:
            def user_prompt(self, value: tuple[object, ...]) -> None:
                calls.append(("telemetry.user_prompt", value))

        turn_context = SimpleNamespace(session_telemetry=Telemetry())

        async def new_turn_with_sub_id(sub_id: str, updates: dict[str, object]) -> object:
            calls.append(("new_turn_with_sub_id", sub_id, updates))
            return turn_context

        async def maybe_emit_unknown_model_warning_for_turn(context: object) -> None:
            calls.append(("maybe_emit_unknown_model_warning_for_turn", context))

        async def steer_input(value: tuple[object, ...], context: object, expected_turn_id: object, client_metadata: object) -> None:
            calls.append(("steer_input", value, context, expected_turn_id, client_metadata))

        session = SimpleNamespace(
            new_turn_with_sub_id=new_turn_with_sub_id,
            maybe_emit_unknown_model_warning_for_turn=maybe_emit_unknown_model_warning_for_turn,
            steer_input=steer_input,
        )

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op(
                "user_input",
                {
                    "items": items,
                    "environments": environments,
                    "final_output_json_schema": schema,
                    "responsesapi_client_metadata": metadata,
                    "additional_context": additional_context,
                },
            ),
        )

        self.assertFalse(should_exit)
        self.assertEqual(calls[0][0], "new_turn_with_sub_id")
        self.assertEqual(calls[0][1], "sub-1")
        self.assertEqual(calls[0][2]["final_output_json_schema"], schema)
        self.assertEqual(calls[0][2]["environments"], environments)
        self.assertIn(("maybe_emit_unknown_model_warning_for_turn", turn_context), calls)
        self.assertIn(("steer_input", items, additional_context, None, metadata), calls)
        self.assertIn(("telemetry.user_prompt", items), calls)

    async def test_dispatch_session_op_user_input_spawns_regular_task_when_no_active_turn(self) -> None:
        # Rust source: session::handlers::user_input_or_turn_inner NoActiveTurn branch
        calls: list[object] = []
        events: list[object] = []
        spawned: list[tuple[object, list[object], object]] = []
        items = ({"type": "text", "text": "hello"},)

        class CurrentCollaborationMode:
            def with_updates(self, model: str | None, effort: object, developer_instructions: object) -> dict[str, object]:
                return {"model": model, "effort": effort, "developer_instructions": developer_instructions}

        class Telemetry:
            def user_prompt(self, value: tuple[object, ...]) -> None:
                calls.append(("telemetry.user_prompt", value))

        class TurnMetadataState:
            def set_responsesapi_client_metadata(self, metadata: object) -> None:
                calls.append(("metadata", metadata))

        turn_context = SimpleNamespace(
            session_telemetry=Telemetry(),
            turn_metadata_state=TurnMetadataState(),
        )

        async def current_collaboration_mode() -> CurrentCollaborationMode:
            return CurrentCollaborationMode()

        async def new_turn_with_sub_id(_sub_id: str, updates: dict[str, object]) -> object:
            calls.append(("new_turn_with_sub_id", updates))
            return turn_context

        async def thread_settings_applied_event() -> EventMsg:
            return EventMsg.with_payload("thread_settings_applied", {"thread_settings": {"model": "gpt-5"}})

        async def send_event_raw(event: object) -> None:
            events.append(event)

        async def maybe_emit_unknown_model_warning_for_turn(context: object) -> None:
            calls.append(("maybe_emit_unknown_model_warning_for_turn", context))

        async def steer_input(_items: tuple[object, ...], _additional_context: object, _expected_turn_id: object, _metadata: object) -> None:
            raise NoActiveTurnForUserInput(items)

        async def mcp_elicitation_reviewer() -> str:
            return "reviewer"

        async def refresh_mcp_servers_if_requested(context: object, reviewer: object) -> None:
            calls.append(("refresh_mcp_servers_if_requested", context, reviewer))

        async def merge_additional_context(context: object) -> list[object]:
            calls.append(("merge_additional_context", context))
            return ["ctx-item"]

        async def spawn_task(context: object, task_input: list[object], task: object) -> None:
            spawned.append((context, task_input, task))

        session = SimpleNamespace(
            current_collaboration_mode=current_collaboration_mode,
            new_turn_with_sub_id=new_turn_with_sub_id,
            thread_settings_applied_event=thread_settings_applied_event,
            send_event_raw=send_event_raw,
            maybe_emit_unknown_model_warning_for_turn=maybe_emit_unknown_model_warning_for_turn,
            steer_input=steer_input,
            mcp_elicitation_reviewer=mcp_elicitation_reviewer,
            refresh_mcp_servers_if_requested=refresh_mcp_servers_if_requested,
            merge_additional_context=merge_additional_context,
            spawn_task=spawn_task,
        )

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op(
                "user_input",
                {
                    "items": items,
                    "responsesapi_client_metadata": {"client": "desktop"},
                    "additional_context": {"note": "nearby"},
                    "thread_settings": ThreadSettingsOverrides(model="gpt-5"),
                },
            ),
        )

        self.assertFalse(should_exit)
        self.assertEqual(events[0].msg.type, "thread_settings_applied")
        self.assertEqual(calls[0][0], "new_turn_with_sub_id")
        self.assertEqual(calls[0][1]["collaboration_mode"]["model"], "gpt-5")
        self.assertIn(("metadata", {"client": "desktop"}), calls)
        self.assertIn(("telemetry.user_prompt", items), calls)
        self.assertIn(("refresh_mcp_servers_if_requested", turn_context, "reviewer"), calls)
        self.assertEqual(spawned, [(turn_context, [ResponseItemTurnInput("ctx-item"), UserInputTurnInput(items)], RegularTask())])

    async def test_dispatch_session_op_user_input_emits_error_when_steer_fails(self) -> None:
        # Rust source: session::handlers::user_input_or_turn_inner SteerInputError branch
        events: list[object] = []
        turn_context = SimpleNamespace()

        class SteerFailure(Exception):
            def to_error_event(self) -> ErrorEvent:
                return ErrorEvent(message="cannot steer", codex_error_info=CodexErrorInfo.other())

        async def new_turn_with_sub_id(_sub_id: str, _updates: dict[str, object]) -> object:
            return turn_context

        async def steer_input(_items: object, _additional_context: object, _expected_turn_id: object, _metadata: object) -> None:
            raise SteerFailure("cannot steer")

        async def send_event_raw(event: object) -> None:
            events.append(event)

        session = SimpleNamespace(
            new_turn_with_sub_id=new_turn_with_sub_id,
            steer_input=steer_input,
            send_event_raw=send_event_raw,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op.user_input(({"type": "text", "text": "hello"},)))

        self.assertFalse(should_exit)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "sub-1")
        self.assertEqual(events[0].msg.type, "error")
        self.assertEqual(events[0].msg.payload.message, "cannot steer")

    async def test_dispatch_session_op_thread_settings_updates_settings_and_emits_applied_event(self) -> None:
        # Rust source: session::handlers::update_thread_settings success branch
        updates_seen: list[dict[str, object]] = []
        events: list[object] = []

        class CurrentCollaborationMode:
            def with_updates(self, model: str | None, effort: object, developer_instructions: object) -> dict[str, object]:
                return {
                    "base": "current",
                    "model": model,
                    "effort": effort,
                    "developer_instructions": developer_instructions,
                }

        async def current_collaboration_mode() -> CurrentCollaborationMode:
            return CurrentCollaborationMode()

        async def update_settings(updates: dict[str, object]) -> None:
            updates_seen.append(updates)

        async def thread_settings_applied_event() -> object:
            return EventMsg.with_payload("thread_settings_applied", {"thread_settings": {"model": "gpt-5"}})

        async def send_event_raw(event: object) -> None:
            events.append(event)

        session = SimpleNamespace(
            current_collaboration_mode=current_collaboration_mode,
            update_settings=update_settings,
            thread_settings_applied_event=thread_settings_applied_event,
            send_event_raw=send_event_raw,
        )

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op.thread_settings(ThreadSettingsOverrides(model="gpt-5")),
        )

        self.assertFalse(should_exit)
        self.assertEqual(len(updates_seen), 1)
        self.assertEqual(updates_seen[0]["collaboration_mode"]["model"], "gpt-5")
        self.assertIsNone(updates_seen[0]["collaboration_mode"]["developer_instructions"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "sub-1")
        self.assertEqual(events[0].msg.type, "thread_settings_applied")

    async def test_dispatch_session_op_thread_settings_emits_bad_request_when_update_fails(self) -> None:
        # Rust source: session::handlers::update_thread_settings error branch
        events: list[object] = []

        async def update_settings(_updates: object) -> None:
            raise ValueError("bad cwd")

        async def send_event_raw(event: object) -> None:
            events.append(event)

        session = SimpleNamespace(
            update_settings=update_settings,
            send_event_raw=send_event_raw,
        )

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            {"type": "thread_settings", "model": "gpt-5"},
        )

        self.assertFalse(should_exit)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "sub-1")
        self.assertEqual(events[0].msg.type, "error")
        self.assertEqual(events[0].msg.payload.message, "invalid thread settings override: bad cwd")
        self.assertEqual(events[0].msg.payload.codex_error_info, CodexErrorInfo.bad_request())

    async def test_dispatch_session_op_set_thread_memory_mode_persists_mode_and_keeps_loop_running(self) -> None:
        # Rust source: session::handlers::set_thread_memory_mode success branch
        calls: list[object] = []

        class LiveThread:
            async def persist(self) -> None:
                calls.append("persist")

            async def flush(self) -> None:
                calls.append("flush")

            async def update_memory_mode(self, mode: ThreadMemoryMode, include_archived: bool) -> None:
                calls.append(("update_memory_mode", mode, include_archived))

        async def live_thread_for_persistence(reason: str) -> LiveThread:
            calls.append(("live_thread_for_persistence", reason))
            return LiveThread()

        session = SimpleNamespace(live_thread_for_persistence=live_thread_for_persistence)

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            Op.set_thread_memory_mode(ThreadMemoryMode.ENABLED),
        )

        self.assertFalse(should_exit)
        self.assertEqual(
            calls,
            [
                ("live_thread_for_persistence", "update thread memory mode"),
                "persist",
                "flush",
                ("update_memory_mode", ThreadMemoryMode.ENABLED, False),
                "flush",
            ],
        )

    async def test_dispatch_session_op_set_thread_memory_mode_emits_error_when_persist_fails(self) -> None:
        # Rust source: session::handlers::set_thread_memory_mode error branch
        events: list[object] = []

        async def live_thread_for_persistence(_reason: str) -> object:
            raise RuntimeError("missing live thread")

        async def send_event_raw(event: object) -> None:
            events.append(event)

        session = SimpleNamespace(
            live_thread_for_persistence=live_thread_for_persistence,
            send_event_raw=send_event_raw,
        )

        should_exit = await dispatch_session_op(
            session,
            "sub-1",
            {"type": "set_thread_memory_mode", "mode": "disabled"},
        )

        self.assertFalse(should_exit)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].id, "sub-1")
        self.assertEqual(events[0].msg.type, "error")
        self.assertEqual(events[0].msg.payload.message, "missing live thread")
        self.assertEqual(events[0].msg.payload.codex_error_info, CodexErrorInfo.other())

    async def test_dispatch_session_op_shutdown_runs_runtime_shutdown_and_exits(self) -> None:
        # Rust source: session::handlers::shutdown and shutdown_session_runtime
        calls: list[object] = []
        delivered_events: list[object] = []

        class Conversation:
            async def shutdown(self) -> None:
                calls.append("conversation.shutdown")

        class UnifiedExecManager:
            async def terminate_all_processes(self) -> None:
                calls.append("unified_exec.terminate_all_processes")

        class McpConnectionManager:
            async def write(self) -> object:
                calls.append("mcp.write")
                return self

            def begin_shutdown(self) -> object:
                calls.append("mcp.begin_shutdown")

                async def wait_for_shutdown() -> None:
                    calls.append("mcp.shutdown.awaited")

                return wait_for_shutdown()

        class GuardianReviewSession:
            async def shutdown(self) -> None:
                calls.append("guardian.shutdown")

        class History:
            def raw_items(self) -> list[dict[str, str]]:
                return [
                    {"type": "message", "role": "user"},
                    {"type": "message", "role": "assistant"},
                    {"type": "message", "role": "user"},
                ]

        class SessionTelemetry:
            def counter(self, name: str, value: int, labels: list[object]) -> None:
                calls.append(("telemetry.counter", name, value, labels))

        class RolloutThreadTrace:
            def record_protocol_event(self, msg: object) -> None:
                calls.append(("trace.protocol_event", msg.type))

            def record_ended(self, status: str) -> None:
                calls.append(("trace.ended", status))

        class LiveThread:
            async def shutdown(self) -> None:
                calls.append("live_thread.shutdown")

        async def abort_all_tasks(reason: str) -> None:
            calls.append(("abort_all_tasks", reason))

        async def clone_history() -> History:
            return History()

        async def emit_thread_stop_lifecycle() -> None:
            calls.append("thread_stop.lifecycle")

        async def deliver_event_raw(event: object) -> None:
            delivered_events.append(event)

        session = SimpleNamespace(
            abort_all_tasks=abort_all_tasks,
            conversation=Conversation(),
            services=SimpleNamespace(
                unified_exec_manager=UnifiedExecManager(),
                mcp_connection_manager=McpConnectionManager(),
                session_telemetry=SessionTelemetry(),
                rollout_thread_trace=RolloutThreadTrace(),
            ),
            guardian_review_session=GuardianReviewSession(),
            clone_history=clone_history,
            emit_thread_stop_lifecycle=emit_thread_stop_lifecycle,
            live_thread=lambda: LiveThread(),
            deliver_event_raw=deliver_event_raw,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op("shutdown"))

        self.assertTrue(should_exit)
        self.assertIn(("abort_all_tasks", "interrupted"), calls)
        self.assertIn("conversation.shutdown", calls)
        self.assertIn("unified_exec.terminate_all_processes", calls)
        self.assertIn("mcp.shutdown.awaited", calls)
        self.assertIn("guardian.shutdown", calls)
        self.assertIn(("telemetry.counter", "codex.conversation.turn.count", 2, []), calls)
        self.assertIn("thread_stop.lifecycle", calls)
        self.assertIn("live_thread.shutdown", calls)
        self.assertIn(("trace.protocol_event", "shutdown_complete"), calls)
        self.assertIn(("trace.ended", "completed"), calls)
        self.assertEqual(len(delivered_events), 1)
        self.assertEqual(delivered_events[0].id, "sub-1")
        self.assertEqual(delivered_events[0].msg.type, "shutdown_complete")

    async def test_dispatch_session_op_shutdown_warns_on_live_thread_failure_and_still_completes(self) -> None:
        # Rust source: session::handlers::shutdown live_thread shutdown error branch
        raw_events: list[object] = []

        class FailingLiveThread:
            async def shutdown(self) -> None:
                raise RuntimeError("flush failed")

        async def send_event_raw(event: object) -> None:
            raw_events.append(event)

        async def deliver_event_raw(event: object) -> None:
            raw_events.append(event)

        session = SimpleNamespace(
            live_thread=lambda: FailingLiveThread(),
            send_event_raw=send_event_raw,
            deliver_event_raw=deliver_event_raw,
        )

        should_exit = await dispatch_session_op(session, "sub-1", Op("shutdown"))

        self.assertTrue(should_exit)
        self.assertEqual([event.msg.type for event in raw_events], ["error", "shutdown_complete"])
        self.assertEqual(raw_events[0].id, "sub-1")
        self.assertEqual(raw_events[0].msg.payload.message, "Failed to shutdown thread persistence")
        self.assertEqual(raw_events[0].msg.payload.codex_error_info, CodexErrorInfo.other())
        self.assertEqual(raw_events[1].id, "sub-1")
