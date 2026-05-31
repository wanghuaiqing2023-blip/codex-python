import unittest
import errno
import json
import tempfile
from pathlib import Path

from pycodex.exec import (
    AppServerEvent,
    ClientRequest,
    ExecLoopAction,
    ExecLoopActionFailureResult,
    ExecLoopCompletionResult,
    ExecLoopCycleResult,
    ExecLoopInterruptResult,
    ExecLoopState,
    ExecRunPlan,
    ExecSessionStartupResult,
    ExecSessionConfig,
    InitialOperation,
    JsonRpcError,
    REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
    REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS,
    REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    REMOTE_APP_SERVER_SHUTDOWN_TIMEOUT_SECONDS,
    RemoteAppServerConnectArgs,
    RemoteAppServerClientState,
    RemoteAppServerConnectResult,
    RemoteAppServerEndpoint,
    RemoteExecLoopActionOutcome,
    RemoteExecLoopCycleExecution,
    RemoteExecLoopRunResult,
    RemoteExecSessionConnectRunResult,
    RemoteExecSessionRunResult,
    RemoteExecSessionStartupResult,
    RemoteInitializeState,
    RemoteWebSocketClient,
    RemoteWebSocketClientCloseResult,
    RESUME_LOOKUP_REQUEST_ID,
    RequestIdSequencer,
    ReviewStartParams,
    ServerRequestDecision,
    ThreadSourceKind,
    ThreadStartParams,
    TurnStartParams,
    TypedRequestError,
    UDS_WEBSOCKET_HANDSHAKE_URL,
    all_thread_source_kinds,
    app_server_control_socket_path,
    apply_remote_auth_token_env,
    backfill_turn_completed_notification,
    canceled_mcp_server_elicitation_response,
    cwds_match,
    decode_jsonrpc_message,
    decode_websocket_text_message,
    direct_resume_thread_id,
    encode_jsonrpc_message,
    encode_jsonrpc_websocket_text_frame,
    exec_mode_server_request_decision,
    exec_mode_server_request_rejection_reason,
    exec_loop_exit_code,
    exec_loop_action_failure_result,
    exec_loop_actions_from_interrupt,
    exec_loop_actions_from_step,
    exec_loop_client_shutdown_failure_warning,
    exec_loop_client_request_failure_warning,
    exec_loop_completion_result,
    exec_loop_action_jsonrpc_message,
    exec_loop_cycle_from_interrupt,
    exec_loop_cycle_from_server_event,
    exec_loop_cycle_from_stream_closed,
    exec_loop_interrupt_request,
    exec_loop_interrupt_step,
    exec_loop_notification_decision,
    exec_loop_server_event_decision,
    exec_loop_shutdown_request,
    exec_loop_step,
    exec_session_config_mapping,
    exec_session_startup_processor_actions,
    format_request_error,
    initial_operation_request_from_plan,
    initial_operation_processor_actions,
    initial_operation_result_from_response,
    is_supported_remote_server_request_method,
    json_rpc_error_wire_mapping,
    json_rpc_error_from_mapping,
    json_rpc_rejection_error,
    jsonrpc_notification,
    jsonrpc_message_to_mapping,
    jsonrpc_message_kind,
    jsonrpc_message_from_server_request_decision,
    jsonrpc_request_from_client_request,
    lagged_event_warning_message,
    latest_thread_cwd,
    notification_indicates_exec_error,
    next_initial_operation_request,
    next_thread_bootstrap_request,
    parse_latest_turn_context_cwd,
    permissions_selection_from_config,
    pick_resume_thread_id_from_list_response,
    resume_lookup_model_providers,
    resume_thread_id_from_list_response,
    resume_thread_id_lookup_request,
    resume_thread_id_lookup_step,
    resolve_server_request_error,
    reject_server_request_error,
    review_start_params_from_plan,
    remote_app_server_client_connect,
    read_remote_auth_token_from_env_var_with,
    remote_addr_parse_error_message,
    remote_addr_supports_auth_token,
    remote_auth_token_url_error_message,
    remote_client_enqueue_event,
    remote_client_handle_jsonrpc_message,
    remote_client_handle_jsonrpc_text,
    remote_client_handle_websocket_event,
    remote_client_next_event,
    remote_client_resolve_or_reject_server_request,
    remote_client_send_initialized_notification,
    remote_client_send_notification,
    remote_client_send_request,
    remote_client_shutdown_close_error,
    remote_client_shutdown_plan,
    remote_client_state_from_initialize,
    remote_client_worker_exit,
    remote_close_websocket_failed_message,
    remote_closed_connection_message,
    remote_connect_failed_message,
    remote_connect_timeout_message,
    remote_disconnected_event,
    remote_disconnected_message,
    remote_duplicate_request_id_message,
    remote_endpoint_auth_token_error,
    remote_exec_loop_cycle,
    remote_exec_loop_execute_action,
    remote_exec_session_connect_and_run,
    remote_exec_session_run,
    remote_exec_session_startup,
    remote_exec_session_run_loop,
    remote_event_consumer_channel_closed_message,
    remote_invalid_authorization_header_message,
    remote_invalid_jsonrpc_message,
    remote_invalid_uds_handshake_url_message,
    remote_initialized_notification,
    remote_initialize_closed_eof_message,
    remote_initialize_closed_message,
    remote_initialize_handle_jsonrpc_message,
    remote_initialize_handle_jsonrpc_text,
    remote_initialize_handle_websocket_event,
    remote_initialize_invalid_response_message,
    remote_initialize_rejected_message,
    remote_initialize_request,
    remote_initialize_start,
    remote_initialize_timeout_message,
    remote_initialize_transport_failed_message,
    remote_initialize_websocket_connection,
    remote_notify_channel_closed_message,
    remote_reject_channel_closed_message,
    remote_request_channel_closed_message,
    remote_resolve_channel_closed_message,
    remote_read_websocket_frame_event,
    remote_transport_failed_message,
    remote_upgrade_failed_message,
    remote_upgrade_timeout_message,
    remote_websocket_config_mapping,
    remote_worker_channel_closed_message,
    remote_write_failed_message,
    remote_write_jsonrpc_websocket_message,
    remote_write_websocket_message_failed_message,
    sandbox_mode_from_permission_profile,
    server_request_method_name,
    session_configured_from_thread_resume_response,
    session_configured_from_thread_start_response,
    exec_session_startup_result,
    should_backfill_turn_completed_items,
    should_process_notification,
    task_id_from_initial_operation_response,
    thread_read_request,
    thread_bootstrap_request,
    thread_bootstrap_processor_actions,
    thread_bootstrap_result_from_response,
    thread_list_request_for_resume,
    thread_matches_resume_cwd,
    thread_resume_params_from_config,
    thread_start_params_from_config,
    thread_unsubscribe_request,
    turn_interrupt_request,
    turn_items_for_thread,
    turn_start_params_from_plan,
    typed_request_deserialize_error,
    typed_request_result_from_remote_step,
    typed_request_result_from_response,
    typed_request_server_error,
    typed_request_transport_error,
    resume_thread_id_from_local_sources,
    resolve_remote_addr,
    resolve_remote_endpoint,
    unsupported_remote_server_request_error,
    websocket_close_error_is_already_closed,
    websocket_url_supports_auth_token,
    WebSocketFrame,
)
from pycodex.protocol import (
    ActivePermissionProfile,
    AgentMessageContent,
    AgentMessageItem,
    ApprovalsReviewer,
    AskForApproval,
    FileSystemSandboxPolicy,
    ManagedFileSystemPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
    ReviewRequest,
    ReviewTarget,
    SandboxMode,
    ThreadSource,
    TurnItem,
    UserInput,
)


class FakeWebSocket:
    def __init__(
        self,
        frames: tuple[WebSocketFrame, ...] = (),
        *,
        send_error: Exception | None = None,
        recv_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.frames = list(frames)
        self.sent_text: list[str] = []
        self.send_error = send_error
        self.recv_error = recv_error
        self.close_error = close_error
        self.closed = False

    def send_text(self, text: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent_text.append(text)

    def recv_frame(self) -> WebSocketFrame:
        if self.recv_error is not None:
            raise self.recv_error
        if not self.frames:
            raise EOFError("no websocket frames")
        return self.frames.pop(0)

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def websocket_json_frame(value: object) -> WebSocketFrame:
    return WebSocketFrame(True, 1, json.dumps(value, separators=(",", ":")).encode())


class RecordingExecProcessor:
    def __init__(self) -> None:
        self.config_summaries: list[tuple[object, object, object]] = []
        self.notifications: list[object] = []
        self.warnings: list[str] = []
        self.final_output_count = 0

    def print_config_summary(self, config: object, prompt: object, session_configured: object) -> None:
        self.config_summaries.append((config, prompt, session_configured))

    def process_server_notification(self, notification: object) -> str:
        self.notifications.append(notification)
        if isinstance(notification, dict) and notification.get("method") == "turn/completed":
            return "initiate_shutdown"
        return "running"

    def process_warning(self, warning: object) -> str:
        self.warnings.append(str(warning))
        return "running"

    def print_final_output(self) -> None:
        self.final_output_count += 1


class ExecSessionRequestBuilderTests(unittest.TestCase):
    def test_thread_start_params_match_exec_config_shape(self) -> None:
        cwd = Path("C:/work/project")
        roots = (cwd, Path("C:/shared"))
        config = ExecSessionConfig(
            model="gpt-5.5",
            model_provider_id="openai",
            cwd=cwd,
            workspace_roots=roots,
            approval_policy=AskForApproval.ON_REQUEST,
            approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW,
            permission_profile=PermissionProfile.workspace_write((cwd,)),
            ephemeral=True,
        )

        params = thread_start_params_from_config(config)

        self.assertEqual(
            params.to_mapping(),
            {
                "model": "gpt-5.5",
                "modelProvider": "openai",
                "cwd": str(cwd),
                "runtimeWorkspaceRoots": [str(path) for path in roots],
                "approvalPolicy": "on-request",
                "approvalsReviewer": "guardian_subagent",
                "sandbox": "workspace-write",
                "ephemeral": True,
                "threadSource": "user",
            },
        )

    def test_thread_start_params_include_ephemeral_false_like_upstream(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"), ephemeral=False)

        params = thread_start_params_from_config(config).to_mapping()

        self.assertIn("ephemeral", params)
        self.assertIs(params["ephemeral"], False)

    def test_thread_resume_uses_active_permissions_profile_instead_of_legacy_sandbox(self) -> None:
        config = ExecSessionConfig(
            model="gpt-5.5",
            model_provider_id="openai",
            cwd=Path("C:/work/project"),
            active_permission_profile=ActivePermissionProfile.new("developer-profile"),
            permission_profile=PermissionProfile.disabled(),
        )

        params = thread_resume_params_from_config(config, "thread-1").to_mapping()

        self.assertEqual(params["threadId"], "thread-1")
        self.assertEqual(params["permissions"], "developer-profile")
        self.assertNotIn("sandbox", params)
        self.assertNotIn("ephemeral", params)
        self.assertNotIn("threadSource", params)
        self.assertEqual(permissions_selection_from_config(config), "developer-profile")

    def test_thread_params_carry_resolved_user_instructions(self) -> None:
        cwd = Path("C:/work/project")
        source = cwd / "AGENTS.md"
        config = ExecSessionConfig(
            model="gpt-5.5",
            model_provider_id="openai",
            cwd=cwd,
            user_instructions="project instructions",
            instruction_sources=(source,),
            startup_warnings=("warning",),
        )

        start = thread_start_params_from_config(config).to_mapping()
        resume = thread_resume_params_from_config(config, "thread-1").to_mapping()
        mapped = exec_session_config_mapping(config)

        expected = {
            "userInstructions": "project instructions",
            "instructionSources": [str(source)],
            "startupWarnings": ["warning"],
        }
        self.assertEqual(start["config"], expected)
        self.assertEqual(resume["config"], expected)
        self.assertEqual(mapped["userInstructions"], "project instructions")
        self.assertEqual(mapped["instructionSources"], [str(source)])
        self.assertEqual(mapped["startupWarnings"], ["warning"])

    def test_sandbox_mode_from_permission_profile_matches_upstream_legacy_mapping(self) -> None:
        cwd = Path("C:/work/project")
        full_write_restricted_network = PermissionProfile.managed(
            ManagedFileSystemPermissions.from_sandbox_policy(FileSystemSandboxPolicy.unrestricted()),
            NetworkSandboxPolicy.RESTRICTED,
        )
        full_write_enabled_network = PermissionProfile.managed(
            ManagedFileSystemPermissions.from_sandbox_policy(FileSystemSandboxPolicy.unrestricted()),
            NetworkSandboxPolicy.ENABLED,
        )

        self.assertEqual(sandbox_mode_from_permission_profile(PermissionProfile.disabled(), cwd), SandboxMode.DANGER_FULL_ACCESS)
        self.assertIsNone(sandbox_mode_from_permission_profile(PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED), cwd))
        self.assertEqual(sandbox_mode_from_permission_profile(PermissionProfile.read_only(), cwd), SandboxMode.READ_ONLY)
        self.assertEqual(
            sandbox_mode_from_permission_profile(PermissionProfile.workspace_write((cwd,)), cwd),
            SandboxMode.WORKSPACE_WRITE,
        )
        self.assertIsNone(sandbox_mode_from_permission_profile(full_write_restricted_network, cwd))
        self.assertEqual(sandbox_mode_from_permission_profile(full_write_enabled_network, cwd), SandboxMode.DANGER_FULL_ACCESS)

    def test_turn_start_params_from_user_turn_plan_match_exec_request_shape(self) -> None:
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),), output_schema=schema),
            prompt_summary="hello",
        )
        config = ExecSessionConfig(
            model="gpt-5.5",
            model_provider_id="openai",
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
            reasoning_effort={"effort": "high"},
        )

        params = turn_start_params_from_plan(config, "thread-1", plan).to_mapping()

        self.assertEqual(
            params,
            {
                "threadId": "thread-1",
                "input": [{"type": "text", "text": "hello", "text_elements": []}],
                "cwd": str(Path("C:/work/project")),
                "approvalPolicy": "never",
                "effort": {"effort": "high"},
                "outputSchema": schema,
            },
        )

    def test_turn_start_params_can_serialize_metadata_and_environments(self) -> None:
        params = TurnStartParams(
            thread_id="thread-1",
            input=(UserInput.text_input("hello"),),
            responsesapi_client_metadata={"session": "exec"},
            additional_context={"note": "from exec"},
            environments={"shell": {"os": "windows"}},
        )

        self.assertEqual(params.to_mapping()["responsesapiClientMetadata"], {"session": "exec"})
        self.assertEqual(params.to_mapping()["additionalContext"], {"note": "from exec"})
        self.assertEqual(params.to_mapping()["environments"], {"shell": {"os": "windows"}})

    def test_review_start_params_and_client_request_match_app_server_wire_shape(self) -> None:
        plan = ExecRunPlan(
            InitialOperation.review(ReviewRequest(ReviewTarget.commit("abc123456", "Fix"))),
            prompt_summary="commit abc1234: Fix",
        )

        params = review_start_params_from_plan("thread-1", plan)
        request = ClientRequest.review_start(7, params)

        self.assertIsInstance(params, ReviewStartParams)
        self.assertEqual(
            request.to_mapping(),
            {
                "method": "review/start",
                "requestId": 7,
                "params": {
                    "threadId": "thread-1",
                    "target": {"type": "commit", "sha": "abc123456", "title": "Fix"},
                },
            },
        )

    def test_initial_operation_request_from_plan_selects_turn_start_for_user_turn(self) -> None:
        plan = ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input("hello"),), output_schema={"type": "object"}),
            prompt_summary="hello",
        )
        config = ExecSessionConfig(
            model="gpt-5.5",
            model_provider_id="openai",
            cwd=Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
            reasoning_effort="medium",
        )

        operation = initial_operation_request_from_plan(41, config, "thread-1", plan)

        self.assertEqual(operation.method, "turn/start")
        self.assertEqual(operation.request_id, 41)
        self.assertEqual(
            operation.request.to_mapping(),
            {
                "method": "turn/start",
                "requestId": 41,
                "params": {
                    "threadId": "thread-1",
                    "input": [{"type": "text", "text": "hello", "text_elements": []}],
                    "cwd": str(Path("C:/work/project")),
                    "approvalPolicy": "never",
                    "effort": "medium",
                    "outputSchema": {"type": "object"},
                },
            },
        )

    def test_initial_operation_request_from_plan_selects_review_start_for_review(self) -> None:
        plan = ExecRunPlan(
            InitialOperation.review(ReviewRequest(ReviewTarget.base_branch("main"))),
            prompt_summary="review main",
        )
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))

        operation = initial_operation_request_from_plan(42, config, "thread-1", plan)

        self.assertEqual(operation.method, "review/start")
        self.assertEqual(
            operation.request.to_mapping(),
            {
                "method": "review/start",
                "requestId": 42,
                "params": {
                    "threadId": "thread-1",
                    "target": {"type": "baseBranch", "branch": "main"},
                },
            },
        )

    def test_initial_operation_result_extracts_user_turn_task_id(self) -> None:
        response = {"turn": {"id": "turn-1", "status": "running"}}

        result = initial_operation_result_from_response("turn/start", response)

        self.assertEqual(result.task_id, "turn-1")
        self.assertIsNone(result.synthetic_notification)
        self.assertEqual(task_id_from_initial_operation_response("turn/start", response), "turn-1")

    def test_initial_operation_result_rejects_unknown_method(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported initial operation response method"):
            initial_operation_result_from_response("thread/read", {"turn": {"id": "turn-1"}})

    def test_initial_operation_result_for_review_synthesizes_turn_started_notification(self) -> None:
        response = {
            "turn": {"id": "turn-review", "status": "running", "items": []},
            "reviewThreadId": "review-thread",
        }

        result = initial_operation_result_from_response("review/start", response)

        self.assertEqual(result.task_id, "turn-review")
        self.assertEqual(
            result.synthetic_notification,
            {
                "method": "turn/started",
                "params": {
                    "threadId": "review-thread",
                    "turn": {"id": "turn-review", "status": "running", "items": []},
                },
            },
        )
        self.assertTrue(should_process_notification(result.synthetic_notification, "review-thread", "turn-review"))

    def test_startup_helpers_sequence_bootstrap_initial_request_and_loop_state(self) -> None:
        config = ExecSessionConfig(
            "gpt-5.5",
            "openai",
            Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
            ephemeral=True,
        )
        request_ids = RequestIdSequencer()
        bootstrap_request = next_thread_bootstrap_request(request_ids, config)
        bootstrap_response = {
            "thread": {
                "id": "11111111-1111-1111-1111-111111111111",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "threadSource": None,
                "name": None,
                "cwd": str(config.cwd),
                "path": None,
            },
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "serviceTier": None,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "activePermissionProfile": None,
            "cwd": str(config.cwd),
            "reasoningEffort": None,
        }
        bootstrap = thread_bootstrap_result_from_response("start", bootstrap_response, config)
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        initial_request = next_initial_operation_request(request_ids, config, bootstrap, plan)
        initial_result = initial_operation_result_from_response("turn/start", {"turn": {"id": "turn-1"}})
        startup = exec_session_startup_result(config, bootstrap, initial_result)

        self.assertEqual(bootstrap_request.request_id, 1)
        self.assertEqual(bootstrap_request.method, "thread/start")
        self.assertEqual(initial_request.request_id, 2)
        self.assertEqual(initial_request.request.to_mapping()["params"]["threadId"], bootstrap.thread_id)
        self.assertIsInstance(startup, ExecSessionStartupResult)
        self.assertEqual(startup.loop_state, ExecLoopState(bootstrap.thread_id, "turn-1", thread_ephemeral=True))
        self.assertEqual(startup.synthetic_notifications, ())

    def test_remote_exec_session_startup_sends_bootstrap_then_initial_operation(self) -> None:
        config = ExecSessionConfig(
            "gpt-5.5",
            "openai",
            Path("C:/work/project"),
            approval_policy=AskForApproval.NEVER,
            ephemeral=True,
        )
        bootstrap_response = {
            "thread": {
                "id": "11111111-1111-1111-1111-111111111111",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "threadSource": None,
                "name": "Started",
                "cwd": str(config.cwd),
                "path": None,
            },
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "serviceTier": None,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "activePermissionProfile": None,
            "cwd": str(config.cwd),
            "reasoningEffort": None,
        }
        websocket = FakeWebSocket(
            (
                websocket_json_frame({"method": "configWarning", "params": {"message": "heads up"}}),
                websocket_json_frame({"id": 1, "result": bootstrap_response}),
                websocket_json_frame({"id": 2, "result": {"turn": {"id": "turn-1", "status": "running"}}}),
            )
        )
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        startup = remote_exec_session_startup(client, config, plan, request_ids=RequestIdSequencer())
        queued = client.next_event()
        sent = [decode_jsonrpc_message(payload) for payload in websocket.sent_text]

        self.assertIsInstance(startup, RemoteExecSessionStartupResult)
        self.assertTrue(startup.ok)
        self.assertEqual(startup.bootstrap_request.request_id, 1)
        self.assertEqual(startup.initial_request.request_id, 2)
        self.assertEqual(startup.bootstrap.thread_id, "11111111-1111-1111-1111-111111111111")
        self.assertEqual(startup.startup.loop_state, ExecLoopState(startup.bootstrap.thread_id, "turn-1", thread_ephemeral=True))
        self.assertEqual(queued.event.kind, "server_notification")
        self.assertEqual(queued.event.notification["params"]["message"], "heads up")
        self.assertEqual(sent[0]["method"], "thread/start")
        self.assertEqual(sent[0]["id"], 1)
        self.assertEqual(sent[0]["params"]["model"], "gpt-5.5")
        self.assertEqual(sent[1]["method"], "turn/start")
        self.assertEqual(sent[1]["id"], 2)
        self.assertEqual(sent[1]["params"]["threadId"], startup.bootstrap.thread_id)
        self.assertEqual(sent[1]["params"]["input"][0]["text"], "hello")
        self.assertEqual(startup.to_mapping()["ok"], True)

    def test_remote_exec_session_startup_stops_on_bootstrap_server_error(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        websocket = FakeWebSocket(
            (websocket_json_frame({"id": 1, "error": {"code": -32004, "message": "missing thread"}}),)
        )
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        startup = remote_exec_session_startup(client, config, plan, request_ids=RequestIdSequencer())
        sent = [decode_jsonrpc_message(payload) for payload in websocket.sent_text]

        self.assertFalse(startup.ok)
        self.assertIsNone(startup.startup)
        self.assertIsNone(startup.initial_request)
        self.assertEqual(startup.error.kind, "server")
        self.assertEqual(str(startup.error), "thread/start failed: missing thread (code -32004)")
        self.assertEqual([message["method"] for message in sent], ["thread/start"])

    def test_remote_exec_session_startup_reports_initial_operation_decode_error(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        bootstrap_response = {
            "thread": {
                "id": "11111111-1111-1111-1111-111111111111",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "threadSource": None,
                "name": None,
                "cwd": str(config.cwd),
                "path": None,
            },
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "serviceTier": None,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "activePermissionProfile": None,
            "cwd": str(config.cwd),
            "reasoningEffort": None,
        }
        websocket = FakeWebSocket(
            (
                websocket_json_frame({"id": 1, "result": bootstrap_response}),
                websocket_json_frame({"id": 2, "result": {"turn": {"status": "running"}}}),
            )
        )
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        startup = remote_exec_session_startup(client, config, plan, request_ids=RequestIdSequencer())

        self.assertFalse(startup.ok)
        self.assertIsNotNone(startup.bootstrap)
        self.assertEqual(startup.initial_request.method, "turn/start")
        self.assertIsNone(startup.startup)
        self.assertEqual(startup.error.kind, "deserialize")
        self.assertEqual(str(startup.error), "turn/start response decode error: missing field `id`")

    def test_remote_exec_session_run_loop_backfills_completion_and_shutdowns(self) -> None:
        turn_completed = {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {"id": "turn-1", "status": "completed", "items": []},
            },
        }
        thread_read_response = {
            "thread": {
                "turns": [
                    {
                        "id": "turn-1",
                        "items": [{"type": "AgentMessage", "text": "done"}],
                    }
                ]
            }
        }
        websocket = FakeWebSocket(
            (
                websocket_json_frame(turn_completed),
                websocket_json_frame({"id": 10, "result": thread_read_response}),
                websocket_json_frame({"id": 11, "result": {}}),
            )
        )
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        processor = RecordingExecProcessor()

        result = remote_exec_session_run_loop(
            client,
            ExecLoopState(thread_id="thread-1", turn_id="turn-1"),
            processor=processor,
            request_ids=RequestIdSequencer(10),
        )
        sent = [decode_jsonrpc_message(payload) for payload in websocket.sent_text]

        self.assertIsInstance(result, RemoteExecLoopRunResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(websocket.closed)
        self.assertEqual([message["method"] for message in sent], ["thread/read", "thread/unsubscribe"])
        self.assertEqual(sent[0]["id"], 10)
        self.assertEqual(sent[1]["id"], 11)
        self.assertEqual(processor.final_output_count, 1)
        self.assertEqual(
            processor.notifications[0]["params"]["turn"]["items"],
            [{"type": "AgentMessage", "text": "done"}],
        )
        self.assertEqual(
            [action.kind for action in result.cycles[0].actions],
            ["send_request", "process_notification", "send_request", "break"],
        )
        self.assertIsInstance(result.cycles[0], RemoteExecLoopCycleExecution)
        self.assertIsInstance(result.cycles[0].outcomes[0], RemoteExecLoopActionOutcome)
        self.assertEqual(result.to_mapping()["exitCode"], 0)

    def test_remote_exec_session_run_loop_failed_turn_exits_nonzero(self) -> None:
        turn_completed = {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {
                    "id": "turn-1",
                    "status": "failed",
                    "items": [{"type": "AgentMessage", "text": "partial"}],
                },
            },
        }
        websocket = FakeWebSocket(
            (
                websocket_json_frame(turn_completed),
                websocket_json_frame({"id": 20, "result": {}}),
            )
        )
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        processor = RecordingExecProcessor()

        result = remote_exec_session_run_loop(
            client,
            ExecLoopState(thread_id="thread-1", turn_id="turn-1"),
            processor=processor,
            request_ids=RequestIdSequencer(20),
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.state.error_seen)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(processor.final_output_count, 1)
        self.assertEqual([message["method"] for message in map(decode_jsonrpc_message, websocket.sent_text)], ["thread/unsubscribe"])

    def test_remote_exec_session_run_loop_final_server_error_exits_nonzero(self) -> None:
        server_error = {
            "method": "error",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "message": "synthetic server error",
                "willRetry": False,
            },
        }
        websocket = FakeWebSocket((websocket_json_frame(server_error),))
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        processor = RecordingExecProcessor()

        result = remote_exec_session_run_loop(
            client,
            ExecLoopState(thread_id="thread-1", turn_id="turn-1"),
            processor=processor,
            request_ids=RequestIdSequencer(40),
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.state.error_seen)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(processor.notifications, [server_error])
        self.assertEqual(processor.final_output_count, 1)
        self.assertTrue(websocket.closed)

    def test_remote_exec_session_run_loop_rejects_server_request_then_continues(self) -> None:
        server_request = {
            "id": "srv-1",
            "method": "item/tool/call",
            "params": {"threadId": "thread-1"},
        }
        turn_completed = {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {
                    "id": "turn-1",
                    "status": "completed",
                    "items": [{"type": "AgentMessage", "text": "done"}],
                },
            },
        }
        websocket = FakeWebSocket(
            (
                websocket_json_frame(server_request),
                websocket_json_frame(turn_completed),
                websocket_json_frame({"id": 30, "result": {}}),
            )
        )
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        processor = RecordingExecProcessor()

        result = remote_exec_session_run_loop(
            client,
            ExecLoopState(thread_id="thread-1", turn_id="turn-1"),
            processor=processor,
            request_ids=RequestIdSequencer(30),
        )
        sent = [decode_jsonrpc_message(payload) for payload in websocket.sent_text]

        self.assertTrue(result.ok)
        self.assertEqual(sent[0]["id"], "srv-1")
        self.assertIn("error", sent[0])
        self.assertEqual(sent[1]["method"], "thread/unsubscribe")
        self.assertEqual(processor.notifications[0], turn_completed)
        self.assertEqual(len(result.cycles), 2)
        self.assertEqual([action.kind for action in result.cycles[0].actions], ["reject_server_request"])

    def test_remote_exec_session_run_sequences_startup_actions_loop_and_completion(self) -> None:
        thread_id = "11111111-1111-1111-1111-111111111111"
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        bootstrap_response = {
            "thread": {
                "id": thread_id,
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "threadSource": None,
                "name": None,
                "cwd": str(config.cwd),
                "path": None,
            },
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "serviceTier": None,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "activePermissionProfile": None,
            "cwd": str(config.cwd),
            "reasoningEffort": None,
        }
        turn_completed = {
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {
                    "id": "turn-1",
                    "status": "completed",
                    "items": [{"type": "AgentMessage", "text": "done"}],
                },
            },
        }
        websocket = FakeWebSocket(
            (
                websocket_json_frame({"id": 1, "result": bootstrap_response}),
                websocket_json_frame({"id": 2, "result": {"turn": {"id": "turn-1", "status": "running"}}}),
                websocket_json_frame(turn_completed),
                websocket_json_frame({"id": 3, "result": {}}),
            )
        )
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        processor = RecordingExecProcessor()
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        result = remote_exec_session_run(
            client,
            config,
            plan,
            processor=processor,
            request_ids=RequestIdSequencer(),
        )
        sent = [decode_jsonrpc_message(payload) for payload in websocket.sent_text]

        self.assertIsInstance(result, RemoteExecSessionRunResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual([message["method"] for message in sent], ["thread/start", "turn/start", "thread/unsubscribe"])
        self.assertEqual([message["id"] for message in sent], [1, 2, 3])
        self.assertEqual([action.kind for action in result.startup_actions], ["print_config_summary"])
        self.assertEqual(len(processor.config_summaries), 1)
        self.assertEqual(processor.config_summaries[0][1], "hello")
        self.assertEqual(processor.notifications, [turn_completed])
        self.assertEqual(processor.final_output_count, 1)
        self.assertTrue(websocket.closed)
        self.assertEqual(result.to_mapping()["startup"]["ok"], True)

    def test_remote_exec_session_run_closes_client_on_startup_error(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        websocket = FakeWebSocket(
            (websocket_json_frame({"id": 1, "error": {"code": -32004, "message": "missing thread"}}),)
        )
        client = RemoteWebSocketClient(websocket, endpoint="ws://localhost/app")
        processor = RecordingExecProcessor()
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        result = remote_exec_session_run(
            client,
            config,
            plan,
            processor=processor,
            request_ids=RequestIdSequencer(),
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 1)
        self.assertIsNone(result.loop)
        self.assertIsNotNone(result.close_result)
        self.assertTrue(websocket.closed)
        self.assertEqual(str(result.startup.error), "thread/start failed: missing thread (code -32004)")
        self.assertIn("thread/start failed", result.error_message)
        self.assertEqual(processor.config_summaries, [])
        self.assertEqual([message["method"] for message in map(decode_jsonrpc_message, websocket.sent_text)], ["thread/start"])

    def test_remote_exec_session_connect_and_run_initializes_then_runs_session(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []
        thread_id = "11111111-1111-1111-1111-111111111111"
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        bootstrap_response = {
            "thread": {
                "id": thread_id,
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "threadSource": None,
                "name": None,
                "cwd": str(config.cwd),
                "path": None,
            },
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "serviceTier": None,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "activePermissionProfile": None,
            "cwd": str(config.cwd),
            "reasoningEffort": None,
        }
        websocket = FakeWebSocket(
            (
                websocket_json_frame({"id": "initialize", "result": {}}),
                websocket_json_frame({"id": 1, "result": bootstrap_response}),
                websocket_json_frame({"id": 2, "result": {"turn": {"id": "turn-1", "status": "running"}}}),
                websocket_json_frame(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": thread_id,
                            "turn": {
                                "id": "turn-1",
                                "status": "completed",
                                "items": [{"type": "AgentMessage", "text": "done"}],
                            },
                        },
                    }
                ),
                websocket_json_frame({"id": 3, "result": {}}),
            )
        )

        def connector(url: str, **kwargs: object) -> FakeWebSocket:
            calls.append((url, kwargs))
            return websocket

        args = RemoteAppServerConnectArgs(
            RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
            "codex-python",
            "0.1.0",
        )
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")
        processor = RecordingExecProcessor()

        result = remote_exec_session_connect_and_run(
            args,
            config,
            plan,
            processor=processor,
            request_ids=RequestIdSequencer(),
            websocket_connector=connector,
        )
        sent = [decode_jsonrpc_message(payload) for payload in websocket.sent_text]

        self.assertIsInstance(result, RemoteExecSessionConnectRunResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(calls[0][0], "ws://localhost/rpc")
        self.assertEqual(
            [message["method"] for message in sent],
            ["initialize", "initialized", "thread/start", "turn/start", "thread/unsubscribe"],
        )
        self.assertEqual([message.get("id") for message in sent], ["initialize", None, 1, 2, 3])
        self.assertTrue(websocket.closed)
        self.assertEqual(processor.final_output_count, 1)
        self.assertEqual(result.to_mapping()["connect"]["ok"], True)
        self.assertEqual(result.to_mapping()["session"]["startup"]["ok"], True)

    def test_remote_exec_session_connect_and_run_stops_on_connect_failure(self) -> None:
        calls = 0

        def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
            nonlocal calls
            calls += 1
            return FakeWebSocket()

        args = RemoteAppServerConnectArgs(
            RemoteAppServerEndpoint.websocket("ws://codex.example/rpc", auth_token="token-1"),
            "codex-python",
            "0.1.0",
        )
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        plan = ExecRunPlan(InitialOperation.user_turn((UserInput.text_input("hello"),)), "hello")

        result = remote_exec_session_connect_and_run(
            args,
            config,
            plan,
            websocket_connector=connector,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 1)
        self.assertIsNone(result.session)
        self.assertEqual(calls, 0)
        self.assertEqual(result.connect.error_kind, "InvalidInput")
        self.assertIn("remote auth tokens require", result.error_message)

    def test_startup_result_keeps_review_synthetic_notification_for_processor(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        bootstrap = thread_bootstrap_result_from_response(
            "start",
            {
                "thread": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "sessionId": "22222222-2222-2222-2222-222222222222",
                    "threadSource": None,
                    "name": None,
                    "cwd": str(config.cwd),
                    "path": None,
                },
                "model": "gpt-5.5",
                "modelProvider": "openai",
                "serviceTier": None,
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "activePermissionProfile": None,
                "cwd": str(config.cwd),
                "reasoningEffort": None,
            },
            config,
        )
        initial = initial_operation_result_from_response(
            "review/start",
            {"turn": {"id": "turn-review", "items": []}, "reviewThreadId": "review-thread"},
        )

        startup = exec_session_startup_result(config, bootstrap, initial)

        self.assertEqual(startup.loop_state.thread_id, bootstrap.thread_id)
        self.assertEqual(startup.loop_state.turn_id, "turn-review")
        self.assertEqual(startup.synthetic_notifications, (initial.synthetic_notification,))

    def test_bootstrap_processor_actions_print_config_summary_and_optional_warning_before_initial_operation(self) -> None:
        config = ExecSessionConfig(
            "gpt-5.5",
            "openai",
            Path("C:/work/project"),
            approval_policy=AskForApproval.ON_REQUEST,
            approvals_reviewer=ApprovalsReviewer.USER,
            ephemeral=True,
        )
        bootstrap = thread_bootstrap_result_from_response(
            "start",
            {
                "thread": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "sessionId": "22222222-2222-2222-2222-222222222222",
                    "threadSource": None,
                    "name": "Started",
                    "cwd": str(config.cwd),
                    "path": None,
                },
                "model": "gpt-5.5",
                "modelProvider": "openai",
                "serviceTier": None,
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "activePermissionProfile": None,
                "cwd": str(config.cwd),
                "reasoningEffort": None,
            },
            config,
        )

        actions = thread_bootstrap_processor_actions(
            config,
            "hello",
            bootstrap,
            system_bwrap_warning="bubblewrap warning",
        )
        mapped = actions[0].to_mapping()

        self.assertEqual([action.kind for action in actions], ["print_config_summary", "process_warning"])
        self.assertEqual(mapped["prompt"], "hello")
        self.assertEqual(mapped["config"], exec_session_config_mapping(config))
        self.assertEqual(mapped["config"]["approvalPolicy"], "on-request")
        self.assertEqual(mapped["sessionConfigured"]["thread_name"], "Started")
        self.assertEqual(actions[1].warning, "bubblewrap warning")

        json_actions = thread_bootstrap_processor_actions(
            config,
            "hello",
            bootstrap,
            json_mode=True,
            system_bwrap_warning="bubblewrap warning",
        )
        self.assertEqual([action.kind for action in json_actions], ["print_config_summary"])

    def test_initial_operation_processor_actions_preserve_review_turn_started(self) -> None:
        user_turn = initial_operation_result_from_response("turn/start", {"turn": {"id": "turn-1"}})
        review = initial_operation_result_from_response(
            "review/start",
            {"turn": {"id": "turn-review", "items": []}, "reviewThreadId": "review-thread"},
        )

        self.assertEqual(initial_operation_processor_actions(user_turn), ())
        actions = initial_operation_processor_actions(review)

        self.assertEqual([action.kind for action in actions], ["process_notification"])
        self.assertEqual(actions[0].notification, review.synthetic_notification)

    def test_startup_processor_actions_sequence_summary_then_review_synthetic_notification(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        bootstrap = thread_bootstrap_result_from_response(
            "start",
            {
                "thread": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "sessionId": "22222222-2222-2222-2222-222222222222",
                    "threadSource": None,
                    "name": None,
                    "cwd": str(config.cwd),
                    "path": None,
                },
                "model": "gpt-5.5",
                "modelProvider": "openai",
                "serviceTier": None,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "activePermissionProfile": None,
                "cwd": str(config.cwd),
                "reasoningEffort": None,
            },
            config,
        )
        initial = initial_operation_result_from_response(
            "review/start",
            {"turn": {"id": "turn-review", "items": []}, "reviewThreadId": "review-thread"},
        )
        startup = exec_session_startup_result(config, bootstrap, initial)
        plan = ExecRunPlan(InitialOperation.review(ReviewRequest(ReviewTarget.base_branch("main"))), "Review main")

        actions = exec_session_startup_processor_actions(
            config,
            plan,
            startup,
            system_bwrap_warning="bubblewrap warning",
        )

        self.assertEqual(
            [action.kind for action in actions],
            ["print_config_summary", "process_warning", "process_notification"],
        )
        self.assertEqual(actions[0].prompt, "Review main")
        self.assertEqual(actions[1].warning, "bubblewrap warning")
        self.assertEqual(actions[2].notification, initial.synthetic_notification)

    def test_manual_params_omit_none_and_preserve_enums(self) -> None:
        params = ThreadStartParams(
            model="gpt-5.5",
            approvals_reviewer=ApprovalsReviewer.USER,
            sandbox=SandboxMode.READ_ONLY,
            thread_source=ThreadSource.USER,
        )

        self.assertEqual(
            params.to_mapping(),
            {
                "model": "gpt-5.5",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "threadSource": "user",
            },
        )

    def test_request_id_sequencer_and_control_requests_match_exec_loop_shape(self) -> None:
        request_ids = RequestIdSequencer()

        interrupt = turn_interrupt_request(request_ids.next(), "thread-1", "turn-1")
        unsubscribe = thread_unsubscribe_request(request_ids.next(), "thread-1")
        read = thread_read_request(request_ids.next(), "thread-1")

        self.assertEqual(
            interrupt.to_mapping(),
            {
                "method": "turn/interrupt",
                "requestId": 1,
                "params": {"threadId": "thread-1", "turnId": "turn-1"},
            },
        )
        self.assertEqual(
            unsubscribe.to_mapping(),
            {
                "method": "thread/unsubscribe",
                "requestId": 2,
                "params": {"threadId": "thread-1"},
            },
        )
        self.assertEqual(
            read.to_mapping(),
            {
                "method": "thread/read",
                "requestId": 3,
                "params": {"threadId": "thread-1", "includeTurns": True},
            },
        )

    def test_request_error_formatting_matches_upstream(self) -> None:
        self.assertEqual(format_request_error("", RuntimeError("boom")), "boom")
        self.assertEqual(format_request_error("thread/start", "boom"), "thread/start: boom")
        self.assertEqual(
            resolve_server_request_error("mcpServer/elicitation/request", "lost"),
            "failed to resolve `mcpServer/elicitation/request` server request: lost",
        )
        self.assertEqual(
            reject_server_request_error("item/tool/call", "lost"),
            "failed to reject `item/tool/call` server request: lost",
        )

    def test_canceled_mcp_server_elicitation_response_matches_wire_shape(self) -> None:
        self.assertEqual(
            canceled_mcp_server_elicitation_response(),
            {"action": "cancel", "content": None, "_meta": None},
        )

        decision = ServerRequestDecision.resolve(
            9,
            "mcpServer/elicitation/request",
            canceled_mcp_server_elicitation_response(),
        )
        self.assertEqual(
            decision.to_mapping(),
            {
                "action": "resolve",
                "requestId": 9,
                "method": "mcpServer/elicitation/request",
                "value": {"action": "cancel", "content": None, "_meta": None},
            },
        )

    def test_remote_endpoint_and_connect_args_match_upstream_shape(self) -> None:
        endpoint = RemoteAppServerEndpoint.websocket("wss://codex.example/rpc", auth_token="token-1")
        unix_endpoint = RemoteAppServerEndpoint.unix_socket("codex.sock")
        args = RemoteAppServerConnectArgs(
            endpoint=endpoint,
            client_name="codex-python",
            client_version="0.1.0",
            experimental_api=True,
            opt_out_notification_methods=("thread/started", "turn/completed"),
            channel_capacity=0,
        )

        self.assertEqual(REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS, 10)
        self.assertEqual(REMOTE_APP_SERVER_INITIALIZE_TIMEOUT_SECONDS, 10)
        self.assertEqual(REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE, 128 << 20)
        self.assertEqual(UDS_WEBSOCKET_HANDSHAKE_URL, "ws://localhost/rpc")
        self.assertEqual(
            remote_websocket_config_mapping(),
            {
                "maxFrameSize": 128 << 20,
                "maxMessageSize": 128 << 20,
            },
        )
        self.assertEqual(endpoint.endpoint, "wss://codex.example/rpc")
        self.assertEqual(
            endpoint.to_mapping(),
            {
                "type": "WebSocket",
                "websocketUrl": "wss://codex.example/rpc",
                "authToken": "token-1",
            },
        )
        self.assertEqual(unix_endpoint.endpoint, "unix://codex.sock")
        self.assertEqual(unix_endpoint.to_mapping(), {"type": "UnixSocket", "socketPath": "codex.sock"})
        self.assertEqual(args.effective_channel_capacity, 1)
        self.assertEqual(
            args.initialize_params().to_mapping(),
            {
                "clientInfo": {"name": "codex-python", "title": None, "version": "0.1.0"},
                "capabilities": {
                    "experimentalApi": True,
                    "requestAttestation": False,
                    "optOutNotificationMethods": ["thread/started", "turn/completed"],
                },
            },
        )
        self.assertEqual(
            RemoteAppServerConnectArgs(endpoint, "codex-python", "0.1.0")
            .initialize_params()
            .to_mapping()["capabilities"]["optOutNotificationMethods"],
            None,
        )
        self.assertEqual(
            encode_jsonrpc_message(remote_initialize_request(args.initialize_params())),
            '{"id":"initialize","method":"initialize","params":{"clientInfo":{"name":"codex-python",'
            '"title":null,"version":"0.1.0"},"capabilities":{"experimentalApi":true,'
            '"requestAttestation":false,"optOutNotificationMethods":["thread/started","turn/completed"]}}}',
        )

    def test_resolve_remote_addr_and_auth_env_match_tui_rules(self) -> None:
        cwd = Path("C:/work/project")
        codex_home = Path("C:/Users/me/.codex")

        websocket = resolve_remote_addr("ws://127.0.0.1:4500")
        secure = resolve_remote_endpoint(
            "wss://codex.example:443",
            remote_auth_token_env="CODEX_REMOTE_AUTH_TOKEN",
            get_var=lambda name: "  bearer-token  ",
        )
        unix_default = resolve_remote_addr("unix://", codex_home=codex_home)
        unix_relative = resolve_remote_addr("unix://codex.sock", cwd=cwd)

        self.assertEqual(websocket.to_mapping(), {"type": "WebSocket", "websocketUrl": "ws://127.0.0.1:4500/"})
        self.assertTrue(remote_addr_supports_auth_token(websocket))
        self.assertEqual(
            secure.to_mapping(),
            {
                "type": "WebSocket",
                "websocketUrl": "wss://codex.example:443/",
                "authToken": "bearer-token",
            },
        )
        self.assertEqual(unix_default.socket_path, app_server_control_socket_path(codex_home))
        self.assertEqual(unix_relative.socket_path, cwd / "codex.sock")
        self.assertFalse(remote_addr_supports_auth_token(unix_default))
        self.assertEqual(
            remote_addr_parse_error_message("http://localhost:4500"),
            "invalid remote address `http://localhost:4500`; expected `ws://host:port`, "
            "`wss://host:port`, `unix://`, or `unix://PATH`",
        )

        for bad in ("ws://localhost", "ws://localhost:4500/rpc", "ws://user@localhost:4500"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "invalid remote address"):
                    resolve_remote_addr(bad)

        with self.assertRaisesRegex(ValueError, "requires `--remote`"):
            apply_remote_auth_token_env(None, "CODEX_REMOTE_AUTH_TOKEN", get_var=lambda name: "token")
        with self.assertRaisesRegex(ValueError, "requires a `wss://` or loopback"):
            apply_remote_auth_token_env(unix_default, "CODEX_REMOTE_AUTH_TOKEN", get_var=lambda name: "token")

    def test_read_remote_auth_token_from_env_var_reports_missing_and_empty(self) -> None:
        self.assertEqual(
            read_remote_auth_token_from_env_var_with("CODEX_REMOTE_AUTH_TOKEN", lambda name: "  token  "),
            "token",
        )
        with self.assertRaisesRegex(ValueError, "is not set"):
            read_remote_auth_token_from_env_var_with("CODEX_REMOTE_AUTH_TOKEN", lambda name: None)
        with self.assertRaisesRegex(ValueError, "is empty"):
            read_remote_auth_token_from_env_var_with("CODEX_REMOTE_AUTH_TOKEN", lambda name: " \n\t ")

    def test_websocket_url_supports_auth_token_matches_upstream_rules(self) -> None:
        allowed = [
            "wss://codex.example/rpc",
            "wss://127.0.0.1/rpc",
            "ws://localhost/rpc",
            "ws://LOCALHOST:8765/rpc",
            "ws://127.0.0.1/rpc",
            "ws://[::1]/rpc",
        ]
        denied = [
            "ws://codex.example/rpc",
            "ws://192.168.1.20/rpc",
            "http://localhost/rpc",
            "wss:///rpc",
            "not a url",
        ]

        for url in allowed:
            self.assertTrue(websocket_url_supports_auth_token(url), url)
        for url in denied:
            self.assertFalse(websocket_url_supports_auth_token(url), url)

        endpoint = RemoteAppServerEndpoint.websocket("ws://codex.example/rpc", auth_token="token-1")
        self.assertEqual(
            remote_auth_token_url_error_message("ws://codex.example/rpc"),
            "remote auth tokens require `wss://` or loopback `ws://` URLs; "
            "got `ws://codex.example/rpc`",
        )
        self.assertEqual(
            remote_endpoint_auth_token_error(endpoint),
            "remote auth tokens require `wss://` or loopback `ws://` URLs; "
            "got `ws://codex.example/rpc`",
        )
        self.assertIsNone(remote_endpoint_auth_token_error(RemoteAppServerEndpoint.websocket("ws://localhost/rpc")))
        self.assertIsNone(
            remote_endpoint_auth_token_error(
                RemoteAppServerEndpoint.websocket("ws://127.0.0.1/rpc", auth_token="token-1")
            )
        )

    def test_jsonrpc_wire_projection_matches_remote_app_server_client_shape(self) -> None:
        request = thread_read_request(3, "thread-1")
        envelope = jsonrpc_request_from_client_request(
            request,
            trace={"traceparent": "00-abcdef"},
        )

        self.assertEqual(
            envelope.to_mapping(),
            {
                "id": 3,
                "method": "thread/read",
                "params": {"threadId": "thread-1", "includeTurns": True},
                "trace": {"traceparent": "00-abcdef"},
            },
        )
        self.assertEqual(
            exec_loop_action_jsonrpc_message(ExecLoopAction.send_request(request)).to_mapping(),
            {
                "id": 3,
                "method": "thread/read",
                "params": {"threadId": "thread-1", "includeTurns": True},
            },
        )

        resolved = ServerRequestDecision.resolve(
            "req-1",
            "mcpServer/elicitation/request",
            canceled_mcp_server_elicitation_response(),
        )
        rejected = ServerRequestDecision.reject("req-2", "item/tool/call", "not supported")

        self.assertEqual(
            jsonrpc_message_from_server_request_decision(resolved).to_mapping(),
            {
                "id": "req-1",
                "result": {"action": "cancel", "content": None, "_meta": None},
            },
        )
        self.assertEqual(
            jsonrpc_message_from_server_request_decision(rejected).to_mapping(),
            {
                "id": "req-2",
                "error": {"code": -32000, "message": "not supported"},
            },
        )
        self.assertEqual(
            json_rpc_error_wire_mapping(JsonRpcError("custom", data={"details": None})),
            {"code": -32000, "message": "custom", "data": {"details": None}},
        )
        self.assertIsNone(exec_loop_action_jsonrpc_message(ExecLoopAction.process_warning("heads up")))

    def test_jsonrpc_wire_projection_rejects_unaddressable_server_decisions(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing request_id"):
            jsonrpc_message_from_server_request_decision(
                ServerRequestDecision.resolve(None, "mcpServer/elicitation/request", {})
            )

        with self.assertRaisesRegex(ValueError, "missing error"):
            jsonrpc_message_from_server_request_decision(
                ServerRequestDecision(action="reject", request_id="req-1", method="item/tool/call")
            )

    def test_jsonrpc_text_encoding_and_decoding_match_compact_transport_shape(self) -> None:
        request = remote_initialize_request({"clientInfo": {"name": "codex-python"}})
        notification = jsonrpc_notification("initialized")
        rejection = jsonrpc_message_from_server_request_decision(
            ServerRequestDecision.reject("server-1", "item/tool/call", "nope")
        )

        encoded_request = encode_jsonrpc_message(request)

        self.assertEqual(
            encoded_request,
            '{"id":"initialize","method":"initialize","params":{"clientInfo":{"name":"codex-python"}}}',
        )
        self.assertEqual(decode_jsonrpc_message(encoded_request), jsonrpc_message_to_mapping(request))
        self.assertEqual(encode_jsonrpc_message(notification), '{"method":"initialized"}')
        self.assertEqual(
            encode_jsonrpc_message(rejection),
            '{"id":"server-1","error":{"code":-32000,"message":"nope"}}',
        )
        self.assertEqual(decode_jsonrpc_message(b'{"id":7,"result":null}'), {"id": 7, "result": None})

    def test_jsonrpc_websocket_write_helpers_match_remote_text_frame_shape(self) -> None:
        request = remote_initialize_request({"clientInfo": {"name": "codex-python"}})
        frame = encode_jsonrpc_websocket_text_frame(
            request,
            mask_key=b"\x01\x02\x03\x04",
        )
        text, remaining = decode_websocket_text_message(frame, expect_masked=True)
        fake = FakeWebSocket()
        sent = remote_write_jsonrpc_websocket_message(fake, jsonrpc_notification("initialized"))

        self.assertEqual(
            text,
            '{"id":"initialize","method":"initialize","params":{"clientInfo":{"name":"codex-python"}}}',
        )
        self.assertEqual(remaining, b"")
        self.assertEqual(sent, '{"method":"initialized"}')
        self.assertEqual(fake.sent_text, ['{"method":"initialized"}'])

    def test_remote_read_websocket_event_feeds_client_reducer(self) -> None:
        endpoint = "ws://localhost/app"
        state = remote_client_send_request(
            RemoteAppServerClientState(),
            thread_read_request(4, "thread-1"),
        ).state
        text_event = remote_read_websocket_frame_event(
            FakeWebSocket((WebSocketFrame(True, 1, b'{"id":4,"result":{"thread":{"id":"thread-1"}}}'),))
        )
        close_event = remote_read_websocket_frame_event(
            FakeWebSocket((WebSocketFrame(True, 8, b""),)),
            close_default="connection closed during initialize",
        )
        step = remote_client_handle_websocket_event(state, text_event, endpoint=endpoint)

        self.assertEqual(text_event.to_mapping(), {"kind": "text", "text": '{"id":4,"result":{"thread":{"id":"thread-1"}}}'})
        self.assertEqual(step.response_id, 4)
        self.assertEqual(step.response_result, {"thread": {"id": "thread-1"}})
        self.assertEqual(
            close_event.to_mapping(),
            {"kind": "close", "closeReason": "connection closed during initialize"},
        )

    def test_jsonrpc_text_decoding_rejects_invalid_transport_messages(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            decode_jsonrpc_message("{")
        with self.assertRaisesRegex(TypeError, "must be a mapping"):
            decode_jsonrpc_message("[]")
        with self.assertRaisesRegex(TypeError, "method must be a string"):
            decode_jsonrpc_message('{"id":1,"method":7}')
        with self.assertRaisesRegex(ValueError, "invalid JSON-RPC message"):
            decode_jsonrpc_message("{}")

    def test_remote_text_handlers_feed_decoded_messages_into_initialize_and_client_state(self) -> None:
        started = remote_initialize_start({"clientInfo": {"name": "codex-python"}})
        warning = remote_initialize_handle_jsonrpc_text(
            started.state,
            '{"method":"configWarning","params":{"message":"during init"}}',
        )
        completed = remote_initialize_handle_jsonrpc_text(
            warning.state,
            b'{"id":"initialize","result":null}',
        )
        client_state = remote_client_state_from_initialize(completed.state)
        sent = remote_client_send_request(client_state, thread_read_request(9, "thread-1"))
        response = remote_client_handle_jsonrpc_text(
            sent.state,
            '{"id":9,"result":{"thread":{"id":"thread-1"}}}',
        )

        self.assertTrue(completed.state.complete)
        self.assertEqual(client_state.pending_events, warning.state.pending_events)
        self.assertEqual(response.response_id, 9)
        self.assertEqual(response.response_result, {"thread": {"id": "thread-1"}})
        self.assertEqual(response.state.pending_requests, ())

    def test_remote_websocket_events_feed_initialize_state_like_upstream_stream_branch(self) -> None:
        endpoint = "ws://localhost/app"
        state = RemoteInitializeState()
        ignored = remote_initialize_handle_websocket_event(
            state,
            {"kind": "ignored", "ignoredOpcode": 9},
            endpoint=endpoint,
        )
        warning = remote_initialize_handle_websocket_event(
            state,
            {"kind": "text", "text": '{"method":"configWarning","params":{"message":"during init"}}'},
            endpoint=endpoint,
        )
        completed = remote_initialize_handle_websocket_event(
            warning.state,
            {"kind": "text", "text": '{"id":"initialize","result":{}}'},
            endpoint=endpoint,
        )
        invalid = remote_initialize_handle_websocket_event(
            state,
            {"kind": "text", "text": "{"},
            endpoint=endpoint,
        )
        closed = remote_initialize_handle_websocket_event(
            state,
            {"kind": "close", "closeReason": "going away"},
            endpoint=endpoint,
        )

        self.assertTrue(ignored.ignored)
        self.assertEqual(warning.event.kind, "server_notification")
        self.assertTrue(completed.state.complete)
        self.assertEqual(completed.outgoing.to_mapping(), {"method": "initialized"})
        self.assertIn(
            "remote app server at `ws://localhost/app` sent invalid initialize response:",
            invalid.error_message,
        )
        self.assertEqual(
            closed.error_message,
            "remote app server at `ws://localhost/app` closed during initialize: going away",
        )

    def test_remote_initialize_websocket_connection_drives_upstream_handshake_order(self) -> None:
        endpoint = "ws://localhost/app"
        websocket = FakeWebSocket(
            (
                WebSocketFrame(True, 1, b'{"method":"configWarning","params":{"message":"during init"}}'),
                WebSocketFrame(True, 1, b'{"id":"server-2","method":"not/supported","params":{}}'),
                WebSocketFrame(True, 1, b'{"id":"initialize","result":{}}'),
            )
        )

        result = remote_initialize_websocket_connection(
            websocket,
            {"clientInfo": {"name": "codex-python"}},
            endpoint=endpoint,
        )

        self.assertIsNone(result.error_message)
        self.assertTrue(result.state.complete)
        self.assertEqual(len(result.pending_events), 1)
        self.assertEqual(result.pending_events[0].kind, "server_notification")
        self.assertEqual(
            websocket.sent_text,
            [
                '{"id":"initialize","method":"initialize","params":{"clientInfo":{"name":"codex-python"}}}',
                '{"id":"server-2","error":{"code":-32601,"message":"unsupported remote app-server request `not/supported`"}}',
                '{"method":"initialized"}',
            ],
        )
        self.assertEqual(result.sent_payloads, tuple(websocket.sent_text))

    def test_remote_initialize_websocket_connection_reports_timeout_eof_and_close(self) -> None:
        endpoint = "ws://localhost/app"

        timed_out = remote_initialize_websocket_connection(
            FakeWebSocket(()),
            {"clientInfo": {"name": "codex-python"}},
            endpoint=endpoint,
            max_frames=0,
        )
        eof = remote_initialize_websocket_connection(
            FakeWebSocket(()),
            {"clientInfo": {"name": "codex-python"}},
            endpoint=endpoint,
        )
        closed = remote_initialize_websocket_connection(
            FakeWebSocket((WebSocketFrame(True, 8, b""),)),
            {"clientInfo": {"name": "codex-python"}},
            endpoint=endpoint,
        )

        self.assertEqual(timed_out.error_message, "timed out waiting for initialize response from `ws://localhost/app`")
        self.assertEqual(eof.error_message, "remote app server at `ws://localhost/app` closed during initialize")
        self.assertEqual(
            closed.error_message,
            "remote app server at `ws://localhost/app` closed during initialize: connection closed during initialize",
        )

    def test_remote_initialize_start_and_completion_match_handshake_shape(self) -> None:
        started = remote_initialize_start(
            {"clientInfo": {"name": "codex-python"}},
            trace={"traceparent": "trace-1"},
        )

        self.assertIsInstance(started.state, RemoteInitializeState)
        self.assertEqual(
            started.outgoing.to_mapping(),
            {
                "id": "initialize",
                "method": "initialize",
                "params": {"clientInfo": {"name": "codex-python"}},
                "trace": {"traceparent": "trace-1"},
            },
        )
        self.assertEqual(
            remote_initialize_request({"capabilities": {}}, request_id="init-2").to_mapping(),
            {"id": "init-2", "method": "initialize", "params": {"capabilities": {}}},
        )
        self.assertEqual(remote_initialized_notification().to_mapping(), {"method": "initialized"})
        self.assertEqual(jsonrpc_notification("initialized").to_mapping(), {"method": "initialized"})

        completed = remote_initialize_handle_jsonrpc_message(started.state, {"id": "initialize", "result": {}})

        self.assertTrue(completed.state.complete)
        self.assertEqual(completed.outgoing.to_mapping(), {"method": "initialized"})
        self.assertEqual(remote_client_state_from_initialize(completed.state), RemoteAppServerClientState())

    def test_remote_initialize_buffers_events_and_rejects_unknown_requests(self) -> None:
        state = RemoteInitializeState()
        notification = remote_initialize_handle_jsonrpc_message(
            state,
            {"method": "configWarning", "params": {"message": "during init"}},
        )
        server_request = remote_initialize_handle_jsonrpc_message(
            notification.state,
            {
                "id": "server-1",
                "method": "mcpServer/elicitation/request",
                "params": {"threadId": "thread-1"},
            },
        )
        unknown = remote_initialize_handle_jsonrpc_message(
            server_request.state,
            {"id": "server-2", "method": "not/supported", "params": {}},
        )

        self.assertEqual(notification.event.kind, "server_notification")
        self.assertEqual(server_request.event.kind, "server_request")
        self.assertEqual(len(server_request.state.pending_events), 2)
        self.assertEqual(
            remote_client_state_from_initialize(server_request.state).pending_events,
            server_request.state.pending_events,
        )
        self.assertEqual(
            unknown.outgoing.to_mapping(),
            {
                "id": "server-2",
                "error": {
                    "code": -32601,
                    "message": "unsupported remote app-server request `not/supported`",
                },
            },
        )
        self.assertEqual(unknown.state.pending_events, server_request.state.pending_events)

    def test_remote_initialize_ignores_unrelated_responses_and_reports_rejection(self) -> None:
        state = RemoteInitializeState()
        ignored_response = remote_initialize_handle_jsonrpc_message(state, {"id": "other", "result": {}})
        ignored_error = remote_initialize_handle_jsonrpc_message(
            state,
            {"id": "other", "error": {"code": -32000, "message": "other failed"}},
        )
        rejected = remote_initialize_handle_jsonrpc_message(
            state,
            {"id": "initialize", "error": {"code": -32000, "message": "bad client"}},
            endpoint="ws://localhost/app",
        )

        self.assertTrue(ignored_response.ignored)
        self.assertTrue(ignored_error.ignored)
        self.assertFalse(rejected.state.complete)
        self.assertEqual(
            rejected.error_message,
            "remote app server at `ws://localhost/app` rejected initialize: bad client",
        )

    def test_remote_transport_error_messages_match_upstream(self) -> None:
        endpoint = "ws://localhost/app"
        closed = "remote app server at `ws://localhost/app` closed the connection"

        self.assertEqual(
            remote_invalid_authorization_header_message("bad header"),
            "invalid remote authorization header value: bad header",
        )
        self.assertEqual(
            remote_invalid_uds_handshake_url_message("bad url"),
            "invalid UDS websocket handshake URL: bad url",
        )
        self.assertEqual(
            remote_connect_timeout_message(endpoint),
            "timed out connecting to remote app server at `ws://localhost/app`",
        )
        self.assertEqual(
            remote_connect_failed_message(endpoint, "refused"),
            "failed to connect to remote app server at `ws://localhost/app`: refused",
        )
        self.assertEqual(
            remote_upgrade_timeout_message(endpoint),
            "timed out upgrading remote app server at `ws://localhost/app`",
        )
        self.assertEqual(
            remote_upgrade_failed_message(endpoint, "bad upgrade"),
            "failed to upgrade remote app server at `ws://localhost/app`: bad upgrade",
        )
        self.assertEqual(
            remote_write_failed_message(endpoint, "closed"),
            "remote app server at `ws://localhost/app` write failed: closed",
        )
        self.assertEqual(
            remote_invalid_jsonrpc_message(endpoint, "bad json"),
            "remote app server at `ws://localhost/app` sent invalid JSON-RPC: bad json",
        )
        self.assertEqual(
            remote_disconnected_message(endpoint),
            "remote app server at `ws://localhost/app` disconnected: connection closed",
        )
        self.assertEqual(
            remote_disconnected_message(endpoint, "going away"),
            "remote app server at `ws://localhost/app` disconnected: going away",
        )
        self.assertEqual(
            remote_transport_failed_message(endpoint, "reset"),
            "remote app server at `ws://localhost/app` transport failed: reset",
        )
        self.assertEqual(
            remote_close_websocket_failed_message(endpoint, "already gone"),
            "failed to close websocket app server `ws://localhost/app`: already gone",
        )
        self.assertEqual(
            remote_write_websocket_message_failed_message(endpoint, "reset"),
            "failed to write websocket message to `ws://localhost/app`: reset",
        )
        self.assertEqual(remote_closed_connection_message(endpoint), closed)
        self.assertEqual(
            remote_disconnected_event(closed).to_mapping(),
            {"type": "Disconnected", "message": closed},
        )

    def test_remote_initialize_error_messages_match_upstream(self) -> None:
        endpoint = "ws://localhost/app"

        self.assertEqual(
            remote_initialize_invalid_response_message(endpoint, "bad json"),
            "remote app server at `ws://localhost/app` sent invalid initialize response: bad json",
        )
        self.assertEqual(
            remote_initialize_rejected_message(endpoint, "bad client"),
            "remote app server at `ws://localhost/app` rejected initialize: bad client",
        )
        self.assertEqual(
            remote_initialize_closed_message(endpoint),
            "remote app server at `ws://localhost/app` closed during initialize: "
            "connection closed during initialize",
        )
        self.assertEqual(
            remote_initialize_closed_message(endpoint, "going away"),
            "remote app server at `ws://localhost/app` closed during initialize: going away",
        )
        self.assertEqual(
            remote_initialize_transport_failed_message(endpoint, "reset"),
            "remote app server at `ws://localhost/app` transport failed during initialize: reset",
        )
        self.assertEqual(
            remote_initialize_closed_eof_message(endpoint),
            "remote app server at `ws://localhost/app` closed during initialize",
        )
        self.assertEqual(
            remote_initialize_timeout_message(endpoint),
            "timed out waiting for initialize response from `ws://localhost/app`",
        )

    def test_remote_worker_channel_error_messages_match_upstream(self) -> None:
        self.assertEqual(remote_duplicate_request_id_message("req-1"), "duplicate remote app-server request id `req-1`")
        self.assertEqual(remote_worker_channel_closed_message(), "remote app-server worker channel is closed")
        self.assertEqual(remote_request_channel_closed_message(), "remote app-server request channel is closed")
        self.assertEqual(remote_notify_channel_closed_message(), "remote app-server notify channel is closed")
        self.assertEqual(remote_resolve_channel_closed_message(), "remote app-server resolve channel is closed")
        self.assertEqual(remote_reject_channel_closed_message(), "remote app-server reject channel is closed")
        self.assertEqual(
            remote_event_consumer_channel_closed_message(),
            "remote app-server event consumer channel is closed",
        )

    def test_remote_client_state_tracks_pending_requests_and_responses(self) -> None:
        state = RemoteAppServerClientState()
        request = thread_read_request(4, "thread-1")

        sent = remote_client_send_request(state, request, trace={"traceparent": "trace-1"})

        self.assertEqual(sent.state.pending_requests, ((4, "thread/read"),))
        self.assertEqual(
            sent.outgoing.to_mapping(),
            {
                "id": 4,
                "method": "thread/read",
                "params": {"threadId": "thread-1", "includeTurns": True},
                "trace": {"traceparent": "trace-1"},
            },
        )

        response = remote_client_handle_jsonrpc_message(sent.state, {"id": 4, "result": {"thread": {"id": "thread-1"}}})
        self.assertEqual(response.response_id, 4)
        self.assertEqual(response.response_result, {"thread": {"id": "thread-1"}})
        self.assertEqual(response.state.pending_requests, ())

        ignored = remote_client_handle_jsonrpc_message(response.state, {"id": 4, "result": {"late": True}})
        self.assertTrue(ignored.ignored)

        pending = remote_client_send_request(response.state, ClientRequest("custom/method", {}, "req-err")).state
        errored = remote_client_handle_jsonrpc_message(
            pending,
            {"id": "req-err", "error": {"code": -32099, "message": "boom", "data": None}},
        )
        self.assertEqual(errored.response_id, "req-err")
        self.assertEqual(errored.response_error, JsonRpcError("boom", code=-32099, data=None))
        self.assertEqual(
            json_rpc_error_from_mapping({"code": 0, "message": "zero", "data": {"x": None}}),
            JsonRpcError("zero", code=0, data={"x": None}),
        )

    def test_remote_client_websocket_events_match_upstream_stream_branch(self) -> None:
        endpoint = "ws://localhost/app"
        state = remote_client_send_request(
            RemoteAppServerClientState(),
            thread_read_request(4, "thread-1"),
        ).state

        response = remote_client_handle_websocket_event(
            state,
            {"kind": "text", "text": '{"id":4,"result":{"thread":{"id":"thread-1"}}}'},
            endpoint=endpoint,
        )
        invalid = remote_client_handle_websocket_event(
            state,
            {"kind": "text", "text": "{"},
            endpoint=endpoint,
        )
        closed = remote_client_handle_websocket_event(
            state,
            {"kind": "close", "close_reason": "going away"},
            endpoint=endpoint,
        )
        ignored = remote_client_handle_websocket_event(
            state,
            {"kind": "ignored", "ignoredOpcode": 10},
            endpoint=endpoint,
        )

        self.assertEqual(response.response_id, 4)
        self.assertEqual(response.response_result, {"thread": {"id": "thread-1"}})
        self.assertEqual(response.state.pending_requests, ())
        self.assertEqual(invalid.state, state)
        self.assertEqual(invalid.error_kind, "InvalidData")
        self.assertEqual(invalid.event.kind, "disconnected")
        self.assertIn(
            "remote app server at `ws://localhost/app` sent invalid JSON-RPC:",
            invalid.error_message,
        )
        self.assertEqual(closed.error_kind, "ConnectionAborted")
        self.assertEqual(
            closed.error_message,
            "remote app server at `ws://localhost/app` disconnected: going away",
        )
        self.assertEqual(closed.event.to_mapping(), {"type": "Disconnected", "message": closed.error_message})
        self.assertTrue(ignored.ignored)

    def test_remote_client_notification_command_matches_upstream_wire_shape(self) -> None:
        state = RemoteAppServerClientState(
            pending_requests=((4, "thread/read"),),
            pending_events=(AppServerEvent.lagged(2),),
        )

        initialized = remote_client_send_initialized_notification(state)
        custom = remote_client_send_notification(
            state,
            "client/custom",
            {"value": None, "ok": True},
        )

        self.assertEqual(initialized.state, state)
        self.assertEqual(initialized.outgoing.to_mapping(), {"method": "initialized"})
        self.assertEqual(
            initialized.to_mapping(),
            {
                "state": {
                    "pendingRequests": [{"id": 4, "method": "thread/read"}],
                    "pendingEvents": [{"type": "Lagged", "skipped": 2}],
                },
                "ignored": False,
                "outgoing": {"method": "initialized"},
            },
        )
        self.assertEqual(
            custom.outgoing.to_mapping(),
            {"method": "client/custom", "params": {"value": None, "ok": True}},
        )
        self.assertEqual(
            encode_jsonrpc_message(custom.outgoing),
            '{"method":"client/custom","params":{"value":null,"ok":true}}',
        )
        self.assertEqual(custom.state, state)

    def test_remote_client_duplicate_request_and_worker_exit_match_upstream(self) -> None:
        state = RemoteAppServerClientState()
        sent = remote_client_send_request(state, thread_read_request(4, "thread-1"))
        duplicate = remote_client_send_request(sent.state, thread_read_request(4, "thread-1"))
        second = remote_client_send_request(sent.state, ClientRequest("custom/method", {}, "req-2"))

        self.assertEqual(duplicate.state, sent.state)
        self.assertIsNone(duplicate.outgoing)
        self.assertEqual(duplicate.error_kind, "InvalidInput")
        self.assertEqual(duplicate.error_message, "duplicate remote app-server request id `4`")

        exited = remote_client_worker_exit(
            second.state,
            error_kind="InvalidData",
            error_message="remote app server at `ws://localhost/app` transport failed: reset",
        )
        self.assertEqual(exited.state.pending_requests, ())
        self.assertEqual(
            exited.to_mapping(),
            {
                "state": {"pendingRequests": [], "pendingEvents": []},
                "failures": [
                    {
                        "requestId": 4,
                        "method": "thread/read",
                        "errorKind": "InvalidData",
                        "errorMessage": "remote app server at `ws://localhost/app` transport failed: reset",
                    },
                    {
                        "requestId": "req-2",
                        "method": "custom/method",
                        "errorKind": "InvalidData",
                        "errorMessage": "remote app server at `ws://localhost/app` transport failed: reset",
                    },
                ],
            },
        )
        self.assertEqual(
            remote_client_worker_exit(sent.state).failures[0].to_mapping(),
            {
                "requestId": 4,
                "method": "thread/read",
                "errorKind": "BrokenPipe",
                "errorMessage": "remote app-server worker channel is closed",
            },
        )

    def test_remote_client_shutdown_plan_and_close_tolerance_match_upstream(self) -> None:
        state = RemoteAppServerClientState(
            pending_requests=((4, "thread/read"), ("req-2", "custom/method")),
            pending_events=(AppServerEvent.lagged(1),),
        )
        plan = remote_client_shutdown_plan(state)

        self.assertEqual(REMOTE_APP_SERVER_SHUTDOWN_TIMEOUT_SECONDS, 5)
        self.assertEqual(
            plan.to_mapping(),
            {
                "dropEventConsumer": True,
                "sendShutdownCommand": True,
                "commandTimeoutSeconds": 5,
                "workerTimeoutSeconds": 5,
                "abortWorkerOnTimeout": True,
                "stateAfterShutdown": {
                    "pendingRequests": [],
                    "pendingEvents": [{"type": "Lagged", "skipped": 1}],
                },
                "pendingRequestFailures": [
                    {
                        "requestId": 4,
                        "method": "thread/read",
                        "errorKind": "BrokenPipe",
                        "errorMessage": "remote app-server worker channel is closed",
                    },
                    {
                        "requestId": "req-2",
                        "method": "custom/method",
                        "errorKind": "BrokenPipe",
                        "errorMessage": "remote app-server worker channel is closed",
                    },
                ],
            },
        )

        endpoint = "ws://localhost/app"
        self.assertTrue(websocket_close_error_is_already_closed("ConnectionClosed"))
        self.assertTrue(websocket_close_error_is_already_closed("already closed"))
        self.assertTrue(websocket_close_error_is_already_closed(BrokenPipeError("broken pipe")))
        self.assertTrue(websocket_close_error_is_already_closed(ConnectionResetError("reset")))
        self.assertTrue(
            websocket_close_error_is_already_closed(OSError(errno.ENOTCONN, "not connected"))
        )
        self.assertFalse(websocket_close_error_is_already_closed(RuntimeError("tls alert")))
        self.assertIsNone(remote_client_shutdown_close_error(endpoint, BrokenPipeError("closed")))
        self.assertIsNone(remote_client_shutdown_close_error(endpoint, None))
        self.assertEqual(
            remote_client_shutdown_close_error(endpoint, RuntimeError("tls alert")),
            "failed to close websocket app server `ws://localhost/app`: tls alert",
        )

    def test_typed_request_error_display_matches_upstream_layers(self) -> None:
        transport = typed_request_transport_error("config/read", "closed")
        server = typed_request_server_error(
            "thread/read",
            JsonRpcError("internal", code=-32603, data={"detail": "config lock mismatch"}),
        )
        deserialize = typed_request_deserialize_error("thread/start", ValueError("invalid integer"))

        self.assertIsInstance(transport, TypedRequestError)
        self.assertEqual(str(transport), "config/read transport error: closed")
        self.assertEqual(
            str(server),
            'thread/read failed: internal (code -32603), data: {"detail":"config lock mismatch"}',
        )
        self.assertEqual(str(deserialize), "thread/start response decode error: invalid integer")
        self.assertEqual(
            server.to_mapping(),
            {
                "kind": "server",
                "method": "thread/read",
                "message": 'thread/read failed: internal (code -32603), data: {"detail":"config lock mismatch"}',
                "source": {
                    "code": -32603,
                    "message": "internal",
                    "data": {"detail": "config lock mismatch"},
                },
            },
        )

    def test_typed_request_result_from_response_and_remote_step(self) -> None:
        ok = typed_request_result_from_response(
            "thread/read",
            response_result={"thread": {"id": "thread-1"}},
            decoder=lambda value: value["thread"]["id"],
        )
        server = typed_request_result_from_response(
            "thread/read",
            response_error=JsonRpcError("missing", code=-32004),
        )
        transport = typed_request_result_from_response("thread/read", transport_error="closed")
        deserialize = typed_request_result_from_response(
            "thread/read",
            response_result={"thread": None},
            decoder=lambda value: value["thread"]["id"],
        )
        duplicate = remote_client_send_request(
            remote_client_send_request(RemoteAppServerClientState(), thread_read_request(4, "thread-1")).state,
            thread_read_request(4, "thread-1"),
        )

        self.assertTrue(ok.ok)
        self.assertEqual(ok.to_mapping(), {"ok": True, "value": "thread-1"})
        self.assertFalse(server.ok)
        self.assertEqual(str(server.error), "thread/read failed: missing (code -32004)")
        self.assertEqual(str(transport.error), "thread/read transport error: closed")
        self.assertEqual(
            str(deserialize.error),
            "thread/read response decode error: 'NoneType' object is not subscriptable",
        )
        self.assertEqual(
            typed_request_result_from_remote_step(thread_read_request(4, "thread-1"), duplicate).to_mapping(),
            {
                "ok": False,
                "error": {
                    "kind": "transport",
                    "method": "thread/read",
                    "message": "thread/read transport error: duplicate remote app-server request id `4`",
                    "source": "duplicate remote app-server request id `4`",
                },
            },
        )

    def test_remote_client_events_and_unknown_request_rejection_match_facade_rules(self) -> None:
        state = RemoteAppServerClientState()
        notification = {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {"id": "turn-1", "status": "completed", "items": [{"type": "message"}]},
            },
        }

        notification_step = remote_client_handle_jsonrpc_message(state, notification)

        self.assertEqual(jsonrpc_message_kind(notification), "notification")
        self.assertEqual(notification_step.event.kind, "server_notification")
        self.assertTrue(
            exec_loop_server_event_decision(
                notification_step.event.to_mapping(),
                "thread-1",
                "turn-1",
            ).notification.should_process
        )

        server_request = {
            "id": "server-1",
            "method": "mcpServer/elicitation/request",
            "params": {"threadId": "thread-1"},
        }
        request_step = remote_client_handle_jsonrpc_message(state, server_request)
        decision = exec_loop_server_event_decision(request_step.event.to_mapping(), "thread-1", "turn-1").server_request
        self.assertTrue(is_supported_remote_server_request_method("McpServerElicitationRequest"))
        self.assertEqual(request_step.event.kind, "server_request")
        self.assertEqual(decision.action, "resolve")
        self.assertEqual(
            remote_client_resolve_or_reject_server_request(state, decision).outgoing.to_mapping(),
            {
                "id": "server-1",
                "result": {"action": "cancel", "content": None, "_meta": None},
            },
        )

        unknown = remote_client_handle_jsonrpc_message(
            state,
            {"id": "server-2", "method": "unknown/request", "params": {}},
        )
        self.assertFalse(is_supported_remote_server_request_method("unknown/request"))
        self.assertEqual(unsupported_remote_server_request_error("unknown/request").code, -32601)
        self.assertEqual(
            unsupported_remote_server_request_error("SomeLegacyAlias").message,
            "unsupported remote app-server request `SomeLegacyAlias`",
        )
        self.assertEqual(
            unknown.outgoing.to_mapping(),
            {
                "id": "server-2",
                "error": {
                    "code": -32601,
                    "message": "unsupported remote app-server request `unknown/request`",
                },
            },
        )

    def test_remote_client_pending_event_queue_matches_next_event_order(self) -> None:
        queued = remote_client_enqueue_event(
            RemoteAppServerClientState(),
            AppServerEvent.server_notification({"method": "configWarning", "params": {"message": "one"}}),
        )
        queued = remote_client_enqueue_event(queued, AppServerEvent.lagged(2))

        first = remote_client_next_event(queued)
        second = remote_client_next_event(first.state)
        empty = remote_client_next_event(second.state)

        self.assertEqual(first.event.to_mapping(), {"type": "ServerNotification", "notification": {"method": "configWarning", "params": {"message": "one"}}})
        self.assertEqual(second.event.to_mapping(), {"type": "Lagged", "skipped": 2})
        self.assertEqual(second.state.pending_events, ())
        self.assertTrue(empty.ignored)
        self.assertEqual(AppServerEvent.disconnected("closed").to_mapping(), {"type": "Disconnected", "message": "closed"})

    def test_remote_websocket_client_facade_drains_startup_events_before_socket_responses(self) -> None:
        endpoint = "ws://localhost/app"
        websocket = FakeWebSocket(
            (
                WebSocketFrame(True, 1, b'{"method":"configWarning","params":{"message":"during init"}}'),
                WebSocketFrame(True, 1, b'{"id":"initialize","result":{}}'),
                WebSocketFrame(True, 1, b'{"id":4,"result":{"thread":{"id":"thread-1"}}}'),
            )
        )
        initialized = remote_initialize_websocket_connection(
            websocket,
            {"clientInfo": {"name": "codex-python"}},
            endpoint=endpoint,
        )

        client = RemoteWebSocketClient.from_initialize_result(websocket, initialized, endpoint=endpoint)
        startup_event = client.next_event()
        sent = client.send_request(thread_read_request(4, "thread-1"))
        response = client.poll_event()

        self.assertEqual(startup_event.event.kind, "server_notification")
        self.assertEqual(startup_event.event.notification["method"], "configWarning")
        self.assertEqual(sent.state.pending_requests, ((4, "thread/read"),))
        self.assertEqual(response.response_id, 4)
        self.assertEqual(response.response_result, {"thread": {"id": "thread-1"}})
        self.assertEqual(client.state.pending_requests, ())
        self.assertEqual(
            websocket.sent_text,
            [
                '{"id":"initialize","method":"initialize","params":{"clientInfo":{"name":"codex-python"}}}',
                '{"method":"initialized"}',
                '{"id":4,"method":"thread/read","params":{"threadId":"thread-1","includeTurns":true}}',
            ],
        )

    def test_remote_websocket_client_facade_writes_notifications_decisions_and_unknown_rejections(self) -> None:
        endpoint = "ws://localhost/app"
        websocket = FakeWebSocket(
            (WebSocketFrame(True, 1, b'{"id":"server-2","method":"unknown/request","params":{}}'),)
        )
        client = RemoteWebSocketClient(websocket, endpoint=endpoint)

        notification = client.send_notification("client/custom", {"ok": True})
        decision = ServerRequestDecision.resolve(
            "server-1",
            "mcpServer/elicitation/request",
            canceled_mcp_server_elicitation_response(),
        )
        resolved = client.resolve_or_reject_server_request(decision)
        unknown = client.next_event()

        self.assertEqual(notification.outgoing.to_mapping(), {"method": "client/custom", "params": {"ok": True}})
        self.assertEqual(
            resolved.outgoing.to_mapping(),
            {
                "id": "server-1",
                "result": {"action": "cancel", "content": None, "_meta": None},
            },
        )
        self.assertEqual(unknown.outgoing.to_mapping()["error"]["code"], -32601)
        self.assertEqual(
            websocket.sent_text,
            [
                '{"method":"client/custom","params":{"ok":true}}',
                '{"id":"server-1","result":{"action":"cancel","content":null,"_meta":null}}',
                '{"id":"server-2","error":{"code":-32601,"message":"unsupported remote app-server request `unknown/request`"}}',
            ],
        )

    def test_remote_websocket_client_facade_write_failure_keeps_previous_state(self) -> None:
        endpoint = "ws://localhost/app"
        websocket = FakeWebSocket(send_error=BrokenPipeError("closed"))
        client = RemoteWebSocketClient(websocket, endpoint=endpoint)

        sent = client.send_request(thread_read_request(4, "thread-1"))

        self.assertEqual(sent.error_kind, "BrokenPipe")
        self.assertEqual(sent.state.pending_requests, ())
        self.assertEqual(client.state.pending_requests, ())
        self.assertEqual(websocket.sent_text, [])
        self.assertEqual(
            sent.error_message,
            "failed to write websocket message to `ws://localhost/app`: closed",
        )

    def test_remote_websocket_client_facade_reports_read_eof_and_close_shutdown(self) -> None:
        endpoint = "ws://localhost/app"
        state = remote_client_send_request(
            RemoteAppServerClientState(),
            thread_read_request(4, "thread-1"),
        ).state
        websocket = FakeWebSocket()
        client = RemoteWebSocketClient(websocket, endpoint=endpoint, state=state)

        eof = client.next_event()
        closed = client.close()

        self.assertEqual(eof.error_kind, "UnexpectedEof")
        self.assertEqual(
            eof.error_message,
            "remote app server at `ws://localhost/app` closed the connection",
        )
        self.assertEqual(eof.event.to_mapping(), {"type": "Disconnected", "message": eof.error_message})
        self.assertIsInstance(closed, RemoteWebSocketClientCloseResult)
        self.assertTrue(websocket.closed)
        self.assertIsNone(closed.close_error_message)
        self.assertEqual(client.state.pending_requests, ())
        self.assertEqual(
            closed.shutdown_plan.pending_request_failures[0].to_mapping(),
            {
                "requestId": 4,
                "method": "thread/read",
                "errorKind": "BrokenPipe",
                "errorMessage": "remote app-server worker channel is closed",
            },
        )

    def test_remote_websocket_client_request_waits_for_response_and_queues_intervening_events(self) -> None:
        endpoint = "ws://localhost/app"
        websocket = FakeWebSocket(
            (
                WebSocketFrame(True, 1, b'{"method":"configWarning","params":{"message":"heads up"}}'),
                WebSocketFrame(True, 1, b'{"id":"server-1","method":"unknown/request","params":{}}'),
                WebSocketFrame(True, 1, b'{"id":4,"result":{"thread":{"id":"thread-1"}}}'),
            )
        )
        client = RemoteWebSocketClient(websocket, endpoint=endpoint)

        response = client.request(thread_read_request(4, "thread-1"))
        queued = client.next_event()

        self.assertEqual(response.response_id, 4)
        self.assertEqual(response.response_result, {"thread": {"id": "thread-1"}})
        self.assertEqual(client.state.pending_requests, ())
        self.assertEqual(queued.event.kind, "server_notification")
        self.assertEqual(queued.event.notification["params"]["message"], "heads up")
        self.assertEqual(
            websocket.sent_text,
            [
                '{"id":4,"method":"thread/read","params":{"threadId":"thread-1","includeTurns":true}}',
                '{"id":"server-1","error":{"code":-32601,"message":"unsupported remote app-server request `unknown/request`"}}',
            ],
        )

    def test_remote_websocket_client_request_typed_preserves_transport_server_and_decode_layers(self) -> None:
        endpoint = "ws://localhost/app"
        ok_client = RemoteWebSocketClient(
            FakeWebSocket((WebSocketFrame(True, 1, b'{"id":4,"result":{"thread":{"id":"thread-1"}}}'),)),
            endpoint=endpoint,
        )
        server_client = RemoteWebSocketClient(
            FakeWebSocket((WebSocketFrame(True, 1, b'{"id":5,"error":{"code":-32004,"message":"missing"}}'),)),
            endpoint=endpoint,
        )
        decode_client = RemoteWebSocketClient(
            FakeWebSocket((WebSocketFrame(True, 1, b'{"id":6,"result":{"thread":null}}'),)),
            endpoint=endpoint,
        )

        ok = ok_client.request_typed(
            thread_read_request(4, "thread-1"),
            decoder=lambda value: value["thread"]["id"],
        )
        server = server_client.request_typed(thread_read_request(5, "thread-missing"))
        decoded = decode_client.request_typed(
            thread_read_request(6, "thread-1"),
            decoder=lambda value: value["thread"]["id"],
        )

        self.assertEqual(ok.to_mapping(), {"ok": True, "value": "thread-1"})
        self.assertFalse(server.ok)
        self.assertEqual(server.error.kind, "server")
        self.assertEqual(str(server.error), "thread/read failed: missing (code -32004)")
        self.assertFalse(decoded.ok)
        self.assertEqual(decoded.error.kind, "deserialize")
        self.assertIn("response decode error", str(decoded.error))

    def test_remote_websocket_client_request_failure_clears_pending_requests(self) -> None:
        endpoint = "ws://localhost/app"
        invalid_client = RemoteWebSocketClient(
            FakeWebSocket((WebSocketFrame(True, 1, b"{"),)),
            endpoint=endpoint,
        )
        eof_client = RemoteWebSocketClient(FakeWebSocket(()), endpoint=endpoint)
        timeout_client = RemoteWebSocketClient(
            FakeWebSocket((WebSocketFrame(True, 9, b""),)),
            endpoint=endpoint,
        )

        invalid = invalid_client.request(thread_read_request(4, "thread-1"))
        eof = eof_client.request(thread_read_request(5, "thread-1"))
        timed_out = timeout_client.request(thread_read_request(6, "thread-1"), max_frames=1)

        self.assertEqual(invalid.error_kind, "InvalidData")
        self.assertIn("sent invalid JSON-RPC", invalid.error_message)
        self.assertEqual(invalid_client.state.pending_requests, ())
        self.assertEqual(eof.error_kind, "UnexpectedEof")
        self.assertEqual(eof_client.state.pending_requests, ())
        self.assertEqual(timed_out.error_kind, "TimedOut")
        self.assertEqual(
            timed_out.error_message,
            "timed out waiting for `thread/read` response from `ws://localhost/app`",
        )
        self.assertEqual(timeout_client.state.pending_requests, ())

    def test_remote_app_server_client_connect_websocket_initializes_and_returns_client(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []
        websocket = FakeWebSocket(
            (
                WebSocketFrame(True, 1, b'{"id":"initialize","result":{}}'),
                WebSocketFrame(True, 1, b'{"id":4,"result":{"thread":{"id":"thread-1"}}}'),
            )
        )

        def connector(url: str, **kwargs: object) -> FakeWebSocket:
            calls.append((url, kwargs))
            return websocket

        args = RemoteAppServerConnectArgs(
            RemoteAppServerEndpoint.websocket("ws://localhost/rpc", auth_token="token-1"),
            "codex-python",
            "0.1.0",
            experimental_api=True,
            opt_out_notification_methods=("turn/completed",),
            channel_capacity=0,
        )

        result = remote_app_server_client_connect(
            args,
            websocket_connector=connector,
            trace={"traceparent": "trace-1"},
        )
        sent = result.client.send_request(thread_read_request(4, "thread-1"))
        response = result.client.poll_event()

        self.assertIsInstance(result, RemoteAppServerConnectResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.endpoint, "ws://localhost/rpc")
        self.assertEqual(result.initialize_result.state.complete, True)
        self.assertEqual(
            calls,
            [
                (
                    "ws://localhost/rpc",
                    {
                        "auth_token": "token-1",
                        "timeout": REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
                        "max_message_size": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
                    },
                )
            ],
        )
        self.assertEqual(sent.state.pending_requests, ((4, "thread/read"),))
        self.assertEqual(response.response_id, 4)
        self.assertEqual(response.response_result, {"thread": {"id": "thread-1"}})
        self.assertEqual(
            websocket.sent_text,
            [
                '{"id":"initialize","method":"initialize","params":{"clientInfo":{"name":"codex-python",'
                '"version":"0.1.0"},"capabilities":{"experimentalApi":true,'
                '"requestAttestation":false,"optOutNotificationMethods":["turn/completed"]}},'
                '"trace":{"traceparent":"trace-1"}}',
                '{"method":"initialized"}',
                '{"id":4,"method":"thread/read","params":{"threadId":"thread-1","includeTurns":true}}',
            ],
        )
        self.assertEqual(result.to_mapping()["clientState"], {"pendingRequests": [], "pendingEvents": []})

    def test_remote_app_server_client_connect_unix_socket_uses_uds_handshake_url(self) -> None:
        calls: list[tuple[Path, dict[str, object]]] = []
        websocket = FakeWebSocket((WebSocketFrame(True, 1, b'{"id":"initialize","result":{}}'),))

        def connector(socket_path: Path, **kwargs: object) -> FakeWebSocket:
            calls.append((socket_path, kwargs))
            return websocket

        args = RemoteAppServerConnectArgs(
            RemoteAppServerEndpoint.unix_socket("codex.sock"),
            "codex-python",
            "0.1.0",
        )

        result = remote_app_server_client_connect(args, unix_socket_connector=connector)

        self.assertTrue(result.ok)
        self.assertEqual(result.endpoint, "unix://codex.sock")
        self.assertEqual(
            calls,
            [
                (
                    Path("codex.sock"),
                    {
                        "websocket_url": UDS_WEBSOCKET_HANDSHAKE_URL,
                        "timeout": REMOTE_APP_SERVER_CONNECT_TIMEOUT_SECONDS,
                        "max_message_size": REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
                    },
                )
            ],
        )
        self.assertEqual(
            websocket.sent_text,
            [
                '{"id":"initialize","method":"initialize","params":{"clientInfo":{"name":"codex-python",'
                '"version":"0.1.0"},"capabilities":{"experimentalApi":false,'
                '"requestAttestation":false}}}',
                '{"method":"initialized"}',
            ],
        )

    def test_remote_app_server_client_connect_rejects_unsafe_auth_and_maps_connect_failures(self) -> None:
        calls = 0

        def connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
            nonlocal calls
            calls += 1
            return FakeWebSocket()

        denied = remote_app_server_client_connect(
            RemoteAppServerConnectArgs(
                RemoteAppServerEndpoint.websocket("ws://codex.example/rpc", auth_token="token-1"),
                "codex-python",
                "0.1.0",
            ),
            websocket_connector=connector,
        )

        self.assertFalse(denied.ok)
        self.assertEqual(calls, 0)
        self.assertEqual(denied.error_kind, "InvalidInput")
        self.assertEqual(
            denied.error_message,
            "remote auth tokens require `wss://` or loopback `ws://` URLs; got `ws://codex.example/rpc`",
        )

        def timeout_connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
            raise TimeoutError("slow")

        timed_out = remote_app_server_client_connect(
            RemoteAppServerConnectArgs(
                RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                "codex-python",
                "0.1.0",
            ),
            websocket_connector=timeout_connector,
        )

        self.assertFalse(timed_out.ok)
        self.assertEqual(timed_out.error_kind, "TimedOut")
        self.assertEqual(
            timed_out.error_message,
            "timed out connecting to remote app server at `ws://localhost/rpc`",
        )

        def broken_connector(*_args: object, **_kwargs: object) -> FakeWebSocket:
            raise RuntimeError("refused")

        failed = remote_app_server_client_connect(
            RemoteAppServerConnectArgs(
                RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                "codex-python",
                "0.1.0",
            ),
            websocket_connector=broken_connector,
        )

        self.assertFalse(failed.ok)
        self.assertEqual(failed.error_kind, "Other")
        self.assertEqual(
            failed.error_message,
            "failed to connect to remote app server at `ws://localhost/rpc`: refused",
        )

    def test_remote_app_server_client_connect_closes_socket_on_initialize_failure(self) -> None:
        websocket = FakeWebSocket(())

        result = remote_app_server_client_connect(
            RemoteAppServerConnectArgs(
                RemoteAppServerEndpoint.websocket("ws://localhost/rpc"),
                "codex-python",
                "0.1.0",
            ),
            websocket_connector=lambda *_args, **_kwargs: websocket,
            initialize_max_frames=0,
        )

        self.assertFalse(result.ok)
        self.assertTrue(websocket.closed)
        self.assertEqual(result.error_kind, "TimedOut")
        self.assertEqual(
            result.error_message,
            "timed out waiting for initialize response from `ws://localhost/rpc`",
        )
        self.assertEqual(result.initialize_result.state.complete, False)

    def test_exec_mode_server_request_decision_resolves_mcp_elicitation_with_cancel(self) -> None:
        decision = exec_mode_server_request_decision(
            {
                "method": "mcpServer/elicitation/request",
                "requestId": "req-1",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "serverName": "demo",
                    "request": {"type": "form", "message": "Continue?"},
                },
            }
        )

        self.assertEqual(decision.action, "resolve")
        self.assertEqual(decision.request_id, "req-1")
        self.assertEqual(decision.method, "mcpServer/elicitation/request")
        self.assertEqual(decision.value, {"action": "cancel", "content": None, "_meta": None})
        self.assertIsNone(decision.error)

    def test_exec_mode_server_request_decision_rejects_unsupported_requests(self) -> None:
        cases = [
            (
                "item/commandExecution/requestApproval",
                {"threadId": "thread-1"},
                "command execution approval is not supported in exec mode for thread `thread-1`",
            ),
            (
                "item/fileChange/requestApproval",
                {"threadId": "thread-2"},
                "file change approval is not supported in exec mode for thread `thread-2`",
            ),
            (
                "item/tool/requestUserInput",
                {"threadId": "thread-3"},
                "request_user_input is not supported in exec mode for thread `thread-3`",
            ),
            (
                "item/tool/call",
                {"threadId": "thread-4"},
                "dynamic tool calls are not supported in exec mode for thread `thread-4`",
            ),
            (
                "account/chatgptAuthTokens/refresh",
                {},
                "chatgpt auth token refresh is not supported in exec mode",
            ),
            (
                "attestation/generate",
                {},
                "attestation generation is not supported in exec mode",
            ),
            (
                "applyPatchApproval",
                {"conversationId": "thread-5"},
                "apply_patch approval is not supported in exec mode for thread `thread-5`",
            ),
            (
                "execCommandApproval",
                {"conversationId": "thread-6"},
                "exec command approval is not supported in exec mode for thread `thread-6`",
            ),
            (
                "item/permissions/requestApproval",
                {"threadId": "thread-7"},
                "permissions approval is not supported in exec mode for thread `thread-7`",
            ),
        ]

        for index, (method, params, expected_reason) in enumerate(cases, start=1):
            with self.subTest(method=method):
                decision = exec_mode_server_request_decision(
                    {"method": method, "requestId": index, "params": params}
                )

                self.assertEqual(decision.action, "reject")
                self.assertEqual(decision.request_id, index)
                self.assertEqual(decision.method, method)
                self.assertIsInstance(decision.error, JsonRpcError)
                self.assertEqual(decision.value, None)
                self.assertEqual(
                    decision.error.to_mapping(),
                    {"code": -32000, "message": expected_reason, "data": None},
                )
                self.assertEqual(json_rpc_rejection_error(expected_reason), decision.error)
                self.assertEqual(exec_mode_server_request_rejection_reason(method, params), expected_reason)

    def test_server_request_method_name_uses_unknown_fallback_and_aliases(self) -> None:
        self.assertEqual(server_request_method_name({}), "unknown")
        self.assertEqual(
            server_request_method_name({"type": "CommandExecutionRequestApproval"}),
            "item/commandExecution/requestApproval",
        )
        self.assertEqual(
            server_request_method_name({"kind": "PermissionsRequestApproval"}),
            "item/permissions/requestApproval",
        )
        self.assertEqual(server_request_method_name({"type": "apply_patch_approval"}), "applyPatchApproval")
        self.assertEqual(
            unsupported_remote_server_request_error("apply_patch_approval").message,
            "unsupported remote app-server request `applyPatchApproval`",
        )

        decision = exec_mode_server_request_decision(
            {"type": "ExecCommandApproval", "request_id": "legacy-1", "payload": {"conversation_id": "thread-9"}}
        )
        self.assertEqual(decision.method, "execCommandApproval")
        self.assertEqual(decision.request_id, "legacy-1")
        self.assertEqual(
            decision.error.to_mapping(),
            {
                "code": -32000,
                "message": "exec command approval is not supported in exec mode for thread `thread-9`",
                "data": None,
            },
        )

    def test_exec_loop_interrupt_shutdown_and_exit_code_match_run_loop(self) -> None:
        interrupt = exec_loop_interrupt_request(10, "thread-1", "turn-1")
        shutdown = exec_loop_shutdown_request(11, "thread-1", "initiate_shutdown")

        self.assertEqual(
            interrupt.to_mapping(),
            {
                "method": "turn/interrupt",
                "requestId": 10,
                "params": {"threadId": "thread-1", "turnId": "turn-1"},
            },
        )
        self.assertEqual(
            shutdown.to_mapping(),
            {
                "method": "thread/unsubscribe",
                "requestId": 11,
                "params": {"threadId": "thread-1"},
            },
        )
        self.assertIsNone(exec_loop_shutdown_request(12, "thread-1", "running"))
        self.assertEqual(exec_loop_exit_code(False), 0)
        self.assertEqual(exec_loop_exit_code(True), 1)

    def test_exec_loop_interrupt_step_sends_interrupt_and_keeps_channel_open(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        result = exec_loop_interrupt_step(state, True, request_ids=RequestIdSequencer(10))
        actions = exec_loop_actions_from_interrupt(result)

        self.assertIsInstance(result, ExecLoopInterruptResult)
        self.assertIs(result.state, state)
        self.assertTrue(result.state.interrupt_channel_open)
        self.assertEqual(result.interrupt_request.method, "turn/interrupt")
        self.assertEqual(result.interrupt_request.request_id, 10)
        self.assertEqual([action.kind for action in actions], ["send_request"])
        self.assertEqual(actions[0].client_request, result.interrupt_request)
        self.assertEqual(
            result.to_mapping()["interruptRequest"],
            {
                "method": "turn/interrupt",
                "requestId": 10,
                "params": {"threadId": "thread-1", "turnId": "turn-1"},
            },
        )

    def test_exec_loop_interrupt_step_closes_channel_without_request(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        closed = exec_loop_interrupt_step(state, False, request_ids=RequestIdSequencer(10))
        ignored = exec_loop_interrupt_step(closed.state, True, request_ids=RequestIdSequencer(11))

        self.assertFalse(closed.state.interrupt_channel_open)
        self.assertIsNone(closed.interrupt_request)
        self.assertEqual(exec_loop_actions_from_interrupt(closed), ())
        self.assertFalse(ignored.state.interrupt_channel_open)
        self.assertIsNone(ignored.interrupt_request)

    def test_exec_loop_action_failure_marks_server_request_errors(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        resolve_action = ExecLoopAction.server_request_action(
            ServerRequestDecision.resolve(
                "req-1",
                "mcpServer/elicitation/request",
                canceled_mcp_server_elicitation_response(),
            )
        )
        reject_action = ExecLoopAction.server_request_action(
            ServerRequestDecision.reject("req-2", "item/tool/call", "not supported")
        )

        resolved = exec_loop_action_failure_result(state, resolve_action, "lost")
        rejected = exec_loop_action_failure_result(state, reject_action, "lost")

        self.assertIsInstance(resolved, ExecLoopActionFailureResult)
        self.assertTrue(resolved.state.error_seen)
        self.assertEqual(
            resolved.warning,
            "failed to resolve `mcpServer/elicitation/request` server request: lost",
        )
        self.assertTrue(rejected.state.error_seen)
        self.assertEqual(rejected.warning, "failed to reject `item/tool/call` server request: lost")
        self.assertEqual(rejected.to_mapping()["state"]["errorSeen"], True)

    def test_exec_loop_action_failure_warns_client_requests_without_error_seen(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        interrupt = exec_loop_action_failure_result(
            state,
            ExecLoopAction.send_request(turn_interrupt_request(1, "thread-1", "turn-1")),
            "closed",
        )
        backfill = exec_loop_action_failure_result(
            state,
            ExecLoopAction.send_request(thread_read_request(2, "thread-1")),
            "lost",
        )
        unsubscribe = exec_loop_action_failure_result(
            state,
            ExecLoopAction.send_request(thread_unsubscribe_request(3, "thread-1")),
            "lost",
        )

        self.assertFalse(interrupt.state.error_seen)
        self.assertEqual(interrupt.warning, "turn/interrupt failed: closed")
        self.assertEqual(
            backfill.warning,
            "thread/read failed while backfilling turn items for turn completion: lost",
        )
        self.assertEqual(unsubscribe.warning, "thread/unsubscribe failed during shutdown: lost")
        self.assertEqual(exec_loop_client_request_failure_warning(ClientRequest("custom/method", {}, 4), "bad"), "custom/method: bad")

    def test_exec_loop_completion_result_shutdowns_prints_and_returns_exit_code(self) -> None:
        clean = exec_loop_completion_result(ExecLoopState(thread_id="thread-1", turn_id="turn-1"))
        failed = exec_loop_completion_result(ExecLoopState(thread_id="thread-1", turn_id="turn-1", error_seen=True))

        self.assertIsInstance(clean, ExecLoopCompletionResult)
        self.assertEqual([action.kind for action in clean.actions], ["shutdown_client", "print_final_output"])
        self.assertEqual(clean.exit_code, 0)
        self.assertEqual(failed.exit_code, 1)
        self.assertEqual(
            failed.to_mapping(),
            {
                "state": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "threadEphemeral": False,
                    "errorSeen": True,
                    "interruptChannelOpen": True,
                },
                "actions": [{"kind": "shutdown_client"}, {"kind": "print_final_output"}],
                "exitCode": 1,
            },
        )

    def test_exec_loop_shutdown_client_failure_warns_without_error_seen(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        result = exec_loop_action_failure_result(state, ExecLoopAction.shutdown_client(), "lost")

        self.assertFalse(result.state.error_seen)
        self.assertEqual(result.warning, "in-process app-server shutdown failed: lost")
        self.assertEqual(exec_loop_client_shutdown_failure_warning("lost"), result.warning)

    def test_exec_loop_cycle_from_server_event_projects_select_event_branch(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        event = {
            "type": "ServerNotification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "failed", "items": []},
                },
            },
        }

        cycle = exec_loop_cycle_from_server_event(event, state, request_ids=RequestIdSequencer(10))

        self.assertIsInstance(cycle, ExecLoopCycleResult)
        self.assertTrue(cycle.state.error_seen)
        self.assertTrue(cycle.awaiting_backfill)
        self.assertFalse(cycle.should_break)
        self.assertEqual([action.kind for action in cycle.actions], ["send_request"])
        self.assertEqual(cycle.actions[0].client_request.method, "thread/read")

    def test_exec_loop_cycle_from_interrupt_projects_select_interrupt_branch(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        interrupt = exec_loop_cycle_from_interrupt(state, True, request_ids=RequestIdSequencer(10))
        closed = exec_loop_cycle_from_interrupt(state, False, request_ids=RequestIdSequencer(11))

        self.assertEqual([action.kind for action in interrupt.actions], ["send_request"])
        self.assertEqual(interrupt.actions[0].client_request.method, "turn/interrupt")
        self.assertFalse(interrupt.should_break)
        self.assertFalse(closed.state.interrupt_channel_open)
        self.assertEqual(closed.actions, ())

    def test_exec_loop_cycle_from_stream_closed_projects_select_none_branch(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1", error_seen=True)
        cycle = exec_loop_cycle_from_stream_closed(state)

        self.assertIs(cycle.state, state)
        self.assertTrue(cycle.should_break)
        self.assertEqual([action.kind for action in cycle.actions], ["break"])
        self.assertEqual(
            cycle.to_mapping(),
            {
                "state": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "threadEphemeral": False,
                    "errorSeen": True,
                    "interruptChannelOpen": True,
                },
                "actions": [{"kind": "break"}],
                "shouldBreak": True,
                "awaitingBackfill": False,
            },
        )

    def test_exec_loop_notification_decision_marks_errors_and_backfill_request(self) -> None:
        notification = {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {"id": "turn-1", "status": "failed", "items": []},
            },
        }

        decision = exec_loop_notification_decision(
            notification,
            "thread-1",
            "turn-1",
            thread_ephemeral=False,
            request_id=13,
        )
        ephemeral_decision = exec_loop_notification_decision(
            notification,
            "thread-1",
            "turn-1",
            thread_ephemeral=True,
            request_id=14,
        )

        self.assertTrue(decision.event_indicates_error)
        self.assertTrue(decision.should_process)
        self.assertTrue(decision.needs_backfill)
        self.assertEqual(
            decision.backfill_request.to_mapping(),
            {
                "method": "thread/read",
                "requestId": 13,
                "params": {"threadId": "thread-1", "includeTurns": True},
            },
        )
        self.assertTrue(ephemeral_decision.event_indicates_error)
        self.assertFalse(ephemeral_decision.needs_backfill)
        self.assertIsNone(ephemeral_decision.backfill_request)

    def test_backfill_turn_completed_notification_replaces_empty_turn_items(self) -> None:
        notification = {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {"id": "turn-1", "status": "completed", "items": []},
            },
        }
        response = {
            "thread": {
                "turns": [
                    {"id": "turn-0", "items": [{"type": "Reasoning"}]},
                    {"id": "turn-1", "items": [{"type": "AgentMessage", "text": "final"}]},
                ]
            }
        }

        backfilled = backfill_turn_completed_notification(False, notification, response)

        self.assertEqual(backfilled["params"]["turn"]["items"], [{"type": "AgentMessage", "text": "final"}])
        self.assertEqual(notification["params"]["turn"]["items"], [])
        self.assertIs(backfill_turn_completed_notification(True, notification, response), notification)

    def test_backfill_turn_completed_notification_serializes_turn_items_as_app_server_v2(self) -> None:
        notification = {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {"id": "turn-1", "status": "completed", "items": []},
            },
        }
        response = {
            "thread": {
                "turns": [
                    {
                        "id": "turn-1",
                        "items": [
                            TurnItem.agent_message(
                                AgentMessageItem(
                                    "msg-1",
                                    (AgentMessageContent.text_content("final"),),
                                )
                            )
                        ],
                    }
                ]
            }
        }

        backfilled = backfill_turn_completed_notification(False, notification, response)

        self.assertEqual(
            backfilled["params"]["turn"]["items"],
            [
                {
                    "type": "agentMessage",
                    "id": "msg-1",
                    "text": "final",
                    "phase": None,
                    "memoryCitation": None,
                }
            ],
        )

    def test_exec_loop_server_event_decision_dispatches_request_notification_and_lagged(self) -> None:
        server_request = exec_loop_server_event_decision(
            {
                "type": "ServerRequest",
                "request": {"method": "mcpServer/elicitation/request", "requestId": 21},
            },
            "thread-1",
            "turn-1",
        )
        server_notification = exec_loop_server_event_decision(
            {
                "type": "ServerNotification",
                "notification": {
                    "method": "error",
                    "params": {"threadId": "thread-1", "turnId": "turn-1", "willRetry": False},
                },
            },
            "thread-1",
            "turn-1",
        )
        lagged = exec_loop_server_event_decision({"type": "Lagged", "skipped": 3}, "thread-1", "turn-1")

        self.assertEqual(server_request.kind, "server_request")
        self.assertEqual(server_request.server_request.action, "resolve")
        self.assertEqual(server_request.server_request.request_id, 21)
        self.assertEqual(server_notification.kind, "server_notification")
        self.assertTrue(server_notification.event_indicates_error)
        self.assertTrue(server_notification.notification.should_process)
        self.assertEqual(lagged.kind, "lagged")
        self.assertEqual(lagged.warning, "in-process app-server event stream lagged; dropped 3 events")

        typed_notification = exec_loop_server_event_decision(
            {
                "type": "ServerNotification",
                "notification": {
                    "kind": "Error",
                    "payload": {"threadId": "thread-1", "turnId": "turn-1", "willRetry": False},
                },
            },
            "thread-1",
            "turn-1",
        )
        self.assertEqual(typed_notification.kind, "server_notification")
        self.assertTrue(typed_notification.event_indicates_error)
        self.assertTrue(typed_notification.notification.should_process)

    def test_exec_loop_step_handles_requests_warnings_and_shutdown(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")

        request_step = exec_loop_step(
            {
                "type": "ServerRequest",
                "request": {
                    "requestId": "req-1",
                    "method": "item/tool/call",
                    "params": {"threadId": "thread-1"},
                },
            },
            state,
        )
        lagged_step = exec_loop_step({"type": "Lagged", "skipped": 2}, state)

        self.assertEqual(request_step.server_request.action, "reject")
        self.assertEqual(request_step.server_request.request_id, "req-1")
        self.assertIsNone(request_step.notification_to_process)
        self.assertFalse(request_step.state.error_seen)
        self.assertEqual(lagged_step.warning_to_process, "in-process app-server event stream lagged; dropped 2 events")
        self.assertFalse(lagged_step.state.error_seen)

    def test_exec_loop_step_backfills_terminal_notification_and_unsubscribes(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        request_ids = RequestIdSequencer(10)
        event = {
            "type": "ServerNotification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "failed", "items": []},
                },
            },
        }

        awaiting = exec_loop_step(event, state, request_ids=request_ids)
        completed = exec_loop_step(
            event,
            awaiting.state,
            request_ids=request_ids,
            processor_status="initiate_shutdown",
            thread_read_response={
                "thread": {
                    "turns": [
                        {
                            "id": "turn-1",
                            "items": [{"type": "agentMessage", "id": "msg-1", "text": "partial"}],
                        }
                    ]
                }
            },
        )

        self.assertTrue(awaiting.state.error_seen)
        self.assertTrue(awaiting.awaiting_backfill)
        self.assertEqual(awaiting.backfill_request.method, "thread/read")
        self.assertEqual(awaiting.backfill_request.request_id, 10)
        self.assertIsNone(awaiting.notification_to_process)
        self.assertEqual(
            completed.notification_to_process["params"]["turn"]["items"],
            [{"type": "agentMessage", "id": "msg-1", "text": "partial"}],
        )
        self.assertEqual(completed.shutdown_request.method, "thread/unsubscribe")
        self.assertEqual(completed.shutdown_request.request_id, 11)
        self.assertTrue(completed.should_break)
        self.assertTrue(completed.state.error_seen)

    def test_exec_loop_actions_from_step_projects_ordered_client_and_processor_work(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        request_step = exec_loop_step(
            {
                "type": "ServerRequest",
                "request": {
                    "requestId": "req-1",
                    "method": "item/tool/call",
                    "params": {"threadId": "thread-1"},
                },
            },
            state,
        )
        lagged_step = exec_loop_step({"type": "Lagged", "skipped": 2}, state)

        request_actions = exec_loop_actions_from_step(request_step)
        warning_actions = exec_loop_actions_from_step(lagged_step)

        self.assertEqual([action.kind for action in request_actions], ["reject_server_request"])
        self.assertIsInstance(request_actions[0], ExecLoopAction)
        self.assertEqual(request_actions[0].server_request, request_step.server_request)
        self.assertEqual(request_actions[0].to_mapping()["serverRequest"]["requestId"], "req-1")
        self.assertEqual([action.kind for action in warning_actions], ["process_warning"])
        self.assertEqual(warning_actions[0].warning, "in-process app-server event stream lagged; dropped 2 events")

    def test_exec_loop_actions_from_step_orders_backfill_shutdown_and_break(self) -> None:
        state = ExecLoopState(thread_id="thread-1", turn_id="turn-1")
        request_ids = RequestIdSequencer(10)
        event = {
            "type": "ServerNotification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "failed", "items": []},
                },
            },
        }

        awaiting = exec_loop_step(event, state, request_ids=request_ids)
        awaiting_actions = exec_loop_actions_from_step(awaiting)
        completed = exec_loop_step(
            event,
            awaiting.state,
            request_ids=request_ids,
            processor_status="initiate_shutdown",
            thread_read_response={
                "thread": {
                    "turns": [
                        {
                            "id": "turn-1",
                            "items": [{"type": "agentMessage", "id": "msg-1", "text": "partial"}],
                        }
                    ]
                }
            },
        )
        completed_actions = exec_loop_actions_from_step(completed)

        self.assertEqual([action.kind for action in awaiting_actions], ["send_request"])
        self.assertEqual(awaiting_actions[0].client_request.method, "thread/read")
        self.assertEqual(awaiting_actions[0].to_mapping()["clientRequest"]["requestId"], 10)
        self.assertEqual([action.kind for action in completed_actions], ["process_notification", "send_request", "break"])
        self.assertEqual(
            completed_actions[0].notification["params"]["turn"]["items"],
            [{"type": "agentMessage", "id": "msg-1", "text": "partial"}],
        )
        self.assertEqual(completed_actions[1].client_request.method, "thread/unsubscribe")
        self.assertEqual(completed_actions[1].client_request.request_id, 11)

    def test_should_process_notification_matches_exec_thread_and_turn_filter(self) -> None:
        self.assertTrue(should_process_notification({"method": "configWarning", "params": {}}, "thread-1", "turn-1"))
        self.assertTrue(
            should_process_notification(
                {"method": "hook/started", "params": {"threadId": "thread-1", "turnId": None}},
                "thread-1",
                "turn-1",
            )
        )
        self.assertTrue(
            should_process_notification(
                {"method": "item/completed", "params": {"threadId": "thread-1", "turnId": "turn-1"}},
                "thread-1",
                "turn-1",
            )
        )
        self.assertTrue(
            should_process_notification(
                {"method": "turn/completed", "params": {"threadId": "thread-1", "turn": {"id": "turn-1"}}},
                "thread-1",
                "turn-1",
            )
        )
        self.assertFalse(
            should_process_notification(
                {"method": "item/completed", "params": {"threadId": "thread-2", "turnId": "turn-1"}},
                "thread-1",
                "turn-1",
            )
        )
        self.assertFalse(
            should_process_notification(
                {"method": "item/agentMessage/delta", "params": {"threadId": "thread-1", "turnId": "turn-1"}},
                "thread-1",
                "turn-1",
            )
        )

    def test_notification_indicates_exec_error_only_for_terminal_failures(self) -> None:
        retrying_error = {"method": "error", "params": {"threadId": "thread-1", "turnId": "turn-1", "willRetry": True}}
        final_error = {"method": "error", "params": {"threadId": "thread-1", "turnId": "turn-1", "willRetry": False}}
        typed_final_error = {
            "kind": "Error",
            "payload": {"threadId": "thread-1", "turnId": "turn-1", "willRetry": False},
        }
        failed_turn = {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "failed"}},
        }
        completed_turn = {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}},
        }

        self.assertFalse(notification_indicates_exec_error(retrying_error, "thread-1", "turn-1"))
        self.assertTrue(notification_indicates_exec_error(final_error, "thread-1", "turn-1"))
        self.assertTrue(notification_indicates_exec_error(typed_final_error, "thread-1", "turn-1"))
        self.assertTrue(notification_indicates_exec_error(failed_turn, "thread-1", "turn-1"))
        self.assertFalse(notification_indicates_exec_error(completed_turn, "thread-1", "turn-1"))

    def test_backfill_helpers_match_turn_completed_recovery_rules(self) -> None:
        notification = {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "items": []}},
        }
        thread = {
            "turns": [
                {"id": "turn-0", "items": ["old"]},
                {"id": "turn-1", "items": [{"type": "AgentMessage"}]},
            ]
        }

        self.assertTrue(should_backfill_turn_completed_items(False, notification))
        self.assertFalse(should_backfill_turn_completed_items(True, notification))
        self.assertEqual(turn_items_for_thread(thread, "turn-1"), [{"type": "AgentMessage"}])
        self.assertIsNone(turn_items_for_thread(thread, "missing"))
        items = turn_items_for_thread(thread, "turn-1")
        assert isinstance(items, list)
        items.append({"type": "mutated"})
        self.assertEqual(thread["turns"][0]["items"], [{"type": "AgentMessage"}])

    def test_lagged_event_warning_message_matches_upstream_text(self) -> None:
        self.assertEqual(lagged_event_warning_message(12), "in-process app-server event stream lagged; dropped 12 events")

    def test_resume_thread_list_request_matches_upstream_last_lookup_shape(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        resume_args = type("Resume", (), {"last": True})()

        request = thread_list_request_for_resume(0, config, resume_args, cursor="cursor-1")

        self.assertEqual(resume_lookup_model_providers(config, resume_args), ("openai",))
        self.assertEqual(all_thread_source_kinds()[0], ThreadSourceKind.CLI)
        self.assertEqual(
            request.to_mapping(),
            {
                "method": "thread/list",
                "requestId": 0,
                "params": {
                    "cursor": "cursor-1",
                    "limit": 100,
                    "sortKey": "updated_at",
                    "modelProviders": ["openai"],
                    "sourceKinds": [
                        "cli",
                        "vscode",
                        "exec",
                        "appServer",
                        "subAgent",
                        "subAgentReview",
                        "subAgentCompact",
                        "subAgentThreadSpawn",
                        "subAgentOther",
                        "unknown",
                    ],
                    "archived": False,
                    "useStateDbOnly": False,
                },
            },
        )

    def test_resume_search_request_omits_model_provider_filter_without_last(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        resume_args = {"last": False}

        request = thread_list_request_for_resume(0, config, resume_args, search_term="Daily work").to_mapping()

        self.assertNotIn("modelProviders", request["params"])
        self.assertEqual(request["params"]["searchTerm"], "Daily work")

    def test_resume_thread_id_lookup_step_matches_upstream_branches(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        thread_id = "55555555-5555-4555-8555-555555555555"

        last_lookup = resume_thread_id_lookup_step(0, config, {"last": True, "all": False}, cursor="cursor-1")
        direct_lookup = resume_thread_id_lookup_step(1, config, {"session_id": thread_id, "last": False})
        named_lookup = resume_thread_id_lookup_step(2, config, {"session_id": "Daily work", "last": False, "all": True})
        empty_lookup = resume_thread_id_lookup_step(3, config, {"last": False})

        self.assertEqual(last_lookup.kind, "list")
        self.assertIsNone(last_lookup.exact_name)
        self.assertFalse(last_lookup.include_all)
        self.assertEqual(last_lookup.request.to_mapping()["params"]["cursor"], "cursor-1")
        self.assertEqual(last_lookup.request.to_mapping()["params"]["modelProviders"], ["openai"])

        self.assertEqual(direct_lookup.kind, "direct")
        self.assertEqual(direct_lookup.thread_id, thread_id)
        self.assertIsNone(direct_lookup.request)

        self.assertEqual(named_lookup.kind, "list")
        self.assertEqual(named_lookup.exact_name, "Daily work")
        self.assertTrue(named_lookup.include_all)
        self.assertEqual(named_lookup.request.to_mapping()["params"]["searchTerm"], "Daily work")
        self.assertNotIn("modelProviders", named_lookup.request.to_mapping()["params"])

        self.assertEqual(empty_lookup.kind, "none")
        self.assertIsNone(empty_lookup.request)

    def test_resume_thread_id_lookup_request_uses_upstream_fixed_request_id(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))

        lookup = resume_thread_id_lookup_request(config, {"last": True, "all": False})

        self.assertEqual(RESUME_LOOKUP_REQUEST_ID, 0)
        self.assertEqual(lookup.kind, "list")
        self.assertEqual(lookup.request.request_id, 0)

    def test_resume_thread_id_from_list_response_tracks_match_or_next_cursor(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir) / "current"
            other = Path(tmpdir) / "other"
            current.mkdir()
            other.mkdir()
            config = ExecSessionConfig("gpt-5.5", "openai", current)

            miss = {
                "data": [{"id": "thread-old", "name": "Daily work", "cwd": str(other), "path": None}],
                "nextCursor": "next-page",
            }
            hit = {
                "data": [
                    {"id": "thread-skip", "name": "Other", "cwd": str(current), "path": None},
                    {"id": "thread-new", "name": "Daily work", "cwd": str(current), "path": None},
                ],
                "nextCursor": None,
            }

            miss_result = resume_thread_id_from_list_response(
                miss,
                config,
                {"session_id": "Daily work", "last": False, "all": False},
            )
            named_result = resume_thread_id_from_list_response(
                hit,
                config,
                {"session_id": "Daily work", "last": False, "all": False},
            )
            last_result = resume_thread_id_from_list_response(hit, config, {"last": True, "all": False})

            self.assertIsNone(miss_result.thread_id)
            self.assertEqual(miss_result.next_cursor, "next-page")
            self.assertFalse(miss_result.done)
            self.assertEqual(named_result.thread_id, "thread-new")
            self.assertTrue(named_result.done)
            self.assertEqual(last_result.thread_id, "thread-skip")

    def test_resume_thread_id_from_local_sources_matches_state_db_before_rollout_and_list(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        resume_args = {"session_id": "Daily work", "last": False, "all": False}

        self.assertEqual(
            resume_thread_id_from_local_sources(
                config,
                resume_args,
                state_db_thread={"id": "state-thread"},
                rollout_meta={"meta": {"id": "rollout-thread", "cwd": str(config.cwd)}},
            ),
            "state-thread",
        )
        self.assertIsNone(
            resume_thread_id_from_local_sources(
                config,
                {"session_id": "55555555-5555-4555-8555-555555555555", "last": False},
                state_db_thread={"id": "state-thread"},
            )
        )
        self.assertIsNone(
            resume_thread_id_from_local_sources(
                config,
                {"session_id": "Daily work", "last": True},
                state_db_thread={"id": "state-thread"},
            )
        )

    def test_resume_thread_id_from_local_sources_filters_state_db_cwd_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir) / "current"
            other = Path(tmpdir) / "other"
            current.mkdir()
            other.mkdir()
            config = ExecSessionConfig("gpt-5.5", "openai", current)
            resume_args = {"session_id": "Daily work", "last": False, "all": False}

            self.assertEqual(
                resume_thread_id_from_local_sources(
                    config,
                    resume_args,
                    state_db_thread={"id": "state-thread", "cwd": str(current)},
                ),
                "state-thread",
            )
            self.assertIsNone(
                resume_thread_id_from_local_sources(
                    config,
                    resume_args,
                    state_db_thread={"id": "state-thread", "cwd": str(other)},
                )
            )
            self.assertEqual(
                resume_thread_id_from_local_sources(
                    config,
                    {"session_id": "Daily work", "last": False, "all": True},
                    state_db_thread={"id": "state-thread", "cwd": str(other)},
                ),
                "state-thread",
            )

    def test_resume_thread_id_from_local_sources_applies_rollout_cwd_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir) / "current"
            other = Path(tmpdir) / "other"
            current.mkdir()
            other.mkdir()
            config = ExecSessionConfig("gpt-5.5", "openai", current)
            resume_args = {"session_id": "Daily work", "last": False, "all": False}

            self.assertEqual(
                resume_thread_id_from_local_sources(
                    config,
                    resume_args,
                    rollout_meta={"meta": {"id": "rollout-thread", "cwd": str(current)}},
                ),
                "rollout-thread",
            )
            self.assertIsNone(
                resume_thread_id_from_local_sources(
                    config,
                    resume_args,
                    rollout_meta={"meta": {"id": "rollout-thread", "cwd": str(other)}},
                )
            )
            self.assertEqual(
                resume_thread_id_from_local_sources(
                    config,
                    {"session_id": "Daily work", "last": False, "all": True},
                    rollout_meta={"id": "rollout-thread", "cwd": str(other)},
                ),
                "rollout-thread",
            )

    def test_latest_thread_cwd_reads_last_turn_context_from_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rollout = Path(tmpdir) / "thread.jsonl"
            first_cwd = str(Path(tmpdir) / "first")
            second_cwd = str(Path(tmpdir) / "second")
            rollout.write_text(
                "\n".join(
                    [
                        "{not json",
                        json.dumps(
                            {
                                "timestamp": "1",
                                "type": "turn_context",
                                "payload": {
                                    "cwd": first_cwd,
                                    "approval_policy": "never",
                                    "sandbox_policy": {"type": "read-only", "network_access": False},
                                    "model": "gpt-5.5",
                                },
                            }
                        ),
                        json.dumps({"timestamp": "2", "type": "event_msg", "payload": {"type": "noop"}}),
                        json.dumps(
                            {
                                "timestamp": "3",
                                "type": "turn_context",
                                "payload": {
                                    "cwd": second_cwd,
                                    "approval_policy": "never",
                                    "sandbox_policy": {"type": "read-only", "network_access": False},
                                    "model": "gpt-5.5",
                                },
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(parse_latest_turn_context_cwd(rollout), Path(second_cwd))
            self.assertEqual(latest_thread_cwd({"path": str(rollout), "cwd": "fallback"}), Path(second_cwd))

    def test_latest_thread_cwd_falls_back_to_thread_cwd(self) -> None:
        self.assertEqual(latest_thread_cwd({"path": "missing.jsonl", "cwd": "C:/fallback"}), Path("C:/fallback"))

    def test_latest_thread_cwd_falls_back_on_invalid_utf8_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rollout = Path(tmpdir) / "thread.jsonl"
            rollout.write_bytes(b"\xff")

            self.assertIsNone(parse_latest_turn_context_cwd(rollout))
            self.assertEqual(latest_thread_cwd({"path": str(rollout), "cwd": "C:/fallback"}), Path("C:/fallback"))

    def test_cwds_match_resolves_existing_paths_and_falls_back_to_direct_equality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            child = root / "child"
            child.mkdir()

            self.assertTrue(cwds_match(root, child / ".."))
            self.assertFalse(cwds_match("C:/does/not/exist", "C:/does/not/exist/.."))
            self.assertTrue(cwds_match("C:/does/not/exist", "C:/does/not/exist"))

    def test_pick_resume_thread_id_filters_by_cwd_and_exact_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir) / "current"
            other = Path(tmpdir) / "other"
            current.mkdir()
            other.mkdir()
            response = {
                "data": [
                    {"id": "thread-old", "name": "Daily work", "cwd": str(other), "path": None},
                    {"id": "thread-new", "name": "Daily work", "cwd": str(current), "path": None},
                    {"id": "thread-skip-name", "name": "Other", "cwd": str(current), "path": None},
                ]
            }

            self.assertEqual(pick_resume_thread_id_from_list_response(response, current), "thread-new")
            self.assertEqual(
                pick_resume_thread_id_from_list_response(response, current, exact_name="Daily work"),
                "thread-new",
            )
            self.assertEqual(pick_resume_thread_id_from_list_response(response, current, include_all=True), "thread-old")
            self.assertTrue(thread_matches_resume_cwd(response["data"][1], current))
            self.assertFalse(thread_matches_resume_cwd(response["data"][0], current))

    def test_direct_resume_thread_id_accepts_only_uuid_strings(self) -> None:
        thread_id = "55555555-5555-4555-8555-555555555555"
        self.assertEqual(direct_resume_thread_id(thread_id), thread_id)
        self.assertIsNone(direct_resume_thread_id("Daily work"))
        self.assertIsNone(direct_resume_thread_id(None))

    def test_thread_bootstrap_request_starts_or_resumes_like_run_exec_session(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        thread_id = "55555555-5555-4555-8555-555555555555"

        start = thread_bootstrap_request(1, config)
        fallback_start = thread_bootstrap_request(2, config, resume_args={"last": True}, resolved_thread_id=None)
        resume = thread_bootstrap_request(3, config, resume_args={"session_id": thread_id}, resolved_thread_id=thread_id)

        self.assertEqual(start.action, "start")
        self.assertEqual(start.method, "thread/start")
        self.assertEqual(start.request.to_mapping()["requestId"], 1)
        self.assertEqual(fallback_start.action, "start")
        self.assertEqual(fallback_start.method, "thread/start")
        self.assertEqual(resume.action, "resume")
        self.assertEqual(
            resume.request.to_mapping(),
            {
                "method": "thread/resume",
                "requestId": 3,
                "params": {
                    "threadId": thread_id,
                    "model": "gpt-5.5",
                    "modelProvider": "openai",
                    "cwd": str(Path("C:/work/project")),
                    "runtimeWorkspaceRoots": [],
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": "read-only",
                    "config": {"instructionSources": [], "startupWarnings": []},
                },
            },
        )

    def test_thread_bootstrap_result_uses_start_or_resume_response_mapping(self) -> None:
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))
        start_response = {
            "thread": {
                "sessionId": "11111111-1111-4111-8111-111111111111",
                "id": "22222222-2222-4222-8222-222222222222",
                "threadSource": "user",
                "name": "Started",
                "path": None,
            },
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "serviceTier": None,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "activePermissionProfile": None,
            "cwd": "C:/work/project",
            "reasoningEffort": None,
        }
        resume_response = {
            "thread": {
                "sessionId": "33333333-3333-4333-8333-333333333333",
                "id": "44444444-4444-4444-8444-444444444444",
                "threadSource": None,
                "name": "Resumed",
                "path": None,
            },
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "serviceTier": None,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "activePermissionProfile": None,
            "cwd": "C:/work/project",
            "reasoningEffort": None,
        }

        started = thread_bootstrap_result_from_response("start", start_response, config)
        resumed = thread_bootstrap_result_from_response("resume", resume_response, config)

        self.assertEqual(started.action, "start")
        self.assertEqual(started.thread_id, "22222222-2222-4222-8222-222222222222")
        self.assertEqual(started.session_configured.thread_name, "Started")
        self.assertEqual(resumed.action, "resume")
        self.assertEqual(resumed.thread_id, "44444444-4444-4444-8444-444444444444")
        self.assertEqual(resumed.session_configured.thread_name, "Resumed")

    def test_session_configured_from_thread_start_response_matches_exec_mapping(self) -> None:
        session_id = "11111111-1111-4111-8111-111111111111"
        thread_id = "22222222-2222-4222-8222-222222222222"
        config = ExecSessionConfig(
            model="ignored-model-from-config",
            model_provider_id="ignored-provider-from-config",
            cwd=Path("C:/work/project"),
            permission_profile=PermissionProfile.workspace_write((Path("C:/work/project"),)),
        )
        response = {
            "thread": {
                "sessionId": session_id,
                "id": thread_id,
                "threadSource": "user",
                "name": "My Thread",
                "path": "C:/work/project/thread.jsonl",
            },
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "serviceTier": "priority",
            "approvalPolicy": "on-request",
            "approvalsReviewer": "guardian_subagent",
            "activePermissionProfile": {"id": "workspace", "extends": ":workspace"},
            "cwd": "C:/work/project",
            "reasoningEffort": "high",
        }

        configured = session_configured_from_thread_start_response(response, config)
        payload = configured.to_mapping()

        self.assertEqual(payload["session_id"], session_id)
        self.assertEqual(payload["thread_id"], thread_id)
        self.assertEqual(payload["thread_source"], "user")
        self.assertEqual(payload["thread_name"], "My Thread")
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertEqual(payload["model_provider_id"], "openai")
        self.assertEqual(payload["service_tier"], "priority")
        self.assertEqual(payload["approval_policy"], "on-request")
        self.assertEqual(payload["approvals_reviewer"], "guardian_subagent")
        self.assertEqual(payload["active_permission_profile"], {"id": "workspace", "extends": ":workspace"})
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["rollout_path"], str(Path("C:/work/project/thread.jsonl")))
        self.assertEqual(configured.permission_profile, config.permission_profile)

    def test_session_configured_from_thread_resume_response_accepts_snake_case_response(self) -> None:
        session_id = "33333333-3333-4333-8333-333333333333"
        thread_id = "44444444-4444-4444-8444-444444444444"
        config = ExecSessionConfig(
            model="gpt-5.5",
            model_provider_id="openai",
            cwd=Path("C:/work/project"),
            permission_profile=PermissionProfile.read_only(),
        )
        response = {
            "thread": {
                "session_id": session_id,
                "id": thread_id,
                "thread_source": None,
                "name": None,
                "path": None,
            },
            "model": "gpt-5.5",
            "model_provider": "openai",
            "service_tier": None,
            "approval_policy": AskForApproval.NEVER,
            "approvals_reviewer": ApprovalsReviewer.USER,
            "active_permission_profile": None,
            "cwd": Path("C:/work/project"),
            "reasoning_effort": None,
        }

        configured = session_configured_from_thread_resume_response(response, config)

        self.assertEqual(configured.session_id.to_json(), session_id)
        self.assertEqual(configured.thread_id.to_json(), thread_id)
        self.assertIsNone(configured.thread_source)
        self.assertIsNone(configured.thread_name)
        self.assertIsNone(configured.rollout_path)
        self.assertEqual(configured.approval_policy, AskForApproval.NEVER)
        self.assertEqual(configured.approvals_reviewer, ApprovalsReviewer.USER)

    def test_session_configured_from_thread_response_validates_ids(self) -> None:
        base = {
            "thread": {"sessionId": "bad-session-id", "id": "22222222-2222-4222-8222-222222222222"},
            "model": "gpt-5.5",
            "modelProvider": "openai",
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "cwd": "C:/work/project",
        }
        config = ExecSessionConfig("gpt-5.5", "openai", Path("C:/work/project"))

        with self.assertRaisesRegex(ValueError, "session id `bad-session-id` is invalid"):
            session_configured_from_thread_start_response(base, config)

        bad_thread = dict(base)
        bad_thread["thread"] = {"sessionId": "11111111-1111-4111-8111-111111111111", "id": "bad-thread-id"}
        with self.assertRaisesRegex(ValueError, "thread id `bad-thread-id` is invalid"):
            session_configured_from_thread_start_response(bad_thread, config)


if __name__ == "__main__":
    unittest.main()
