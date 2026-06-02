import unittest
from pathlib import Path

from pycodex.protocol import (
    USER_INSTRUCTIONS_CLOSE_TAG,
    USER_INSTRUCTIONS_OPEN_TAG,
    AgentPath,
    AccountPlanType,
    ActivePermissionProfile,
    AdditionalPermissionProfile,
    ApplyPatchApprovalRequestEvent,
    approval_policy_display_value,
    ApprovalsReviewer,
    AskForApproval,
    AgentStatus,
    CollabAgentInteractionBeginEvent,
    CollabAgentInteractionEndEvent,
    CollabAgentRef,
    CollabAgentSpawnBeginEvent,
    CollabAgentSpawnEndEvent,
    CollabAgentStatusEntry,
    CollabCloseBeginEvent,
    CollabCloseEndEvent,
    CollabResumeBeginEvent,
    CollabResumeEndEvent,
    CollabWaitingBeginEvent,
    CollabWaitingEndEvent,
    CollaborationMode,
    CompactedItem,
    ConversationAudioParams,
    ConversationPathResponseEvent,
    ConversationStartParams,
    ConversationStartTransport,
    ConversationTextParams,
    ContextCompactedEvent,
    CreditsSnapshot,
    DynamicToolCallOutputContentItem,
    DynamicToolCallRequest,
    DynamicToolResponse,
    ElicitationAction,
    ElicitationRequest,
    ElicitationRequestEvent,
    Event,
    EventMsg,
    ExecApprovalRequestEvent,
    ExecCommandBeginEvent,
    ExecCommandEndEvent,
    ExecCommandOutputDeltaEvent,
    ExecCommandSource,
    ExecCommandStatus,
    ExecPolicyAmendment,
    ExecOutputStream,
    ExitedReviewModeEvent,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FinalOutput,
    FileChange,
    GranularApprovalConfig,
    GitInfo,
    GuardianAssessmentAction,
    GuardianAssessmentDecisionSource,
    GuardianAssessmentEvent,
    GuardianAssessmentStatus,
    GuardianCommandSource,
    GuardianRiskLevel,
    GuardianUserAuthorization,
    HookCompletedEvent,
    HookEventName,
    HookExecutionMode,
    HookHandlerType,
    HookOutputEntry,
    HookOutputEntryKind,
    HookRunStatus,
    HookRunSummary,
    HookScope,
    HookSource,
    HookStartedEvent,
    InitialHistory,
    InterAgentCommunication,
    McpAuthStatus,
    McpInvocation,
    McpServerRefreshConfig,
    McpStartupCompleteEvent,
    McpStartupFailure,
    McpStartupStatus,
    McpStartupUpdateEvent,
    McpToolCallBeginEvent,
    McpToolCallEndEvent,
    InternalSessionSource,
    ModeKind,
    ModelRerouteEvent,
    ModelRerouteReason,
    ModelVerification,
    ModelVerificationEvent,
    AgentReasoningSectionBreakEvent,
    NetworkApprovalContext,
    NetworkApprovalProtocol,
    NetworkPermissions,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    NetworkSandboxPolicy,
    NetworkAccess,
    Op,
    PatchApplyBeginEvent,
    PatchApplyEndEvent,
    PatchApplyStatus,
    ParsedCommand,
    PermissionProfile,
    Personality,
    ReviewCodeLocation,
    ReviewFinding,
    ReviewLineRange,
    ReviewOutputEvent,
    ReviewRequest,
    ReviewTarget,
    ReviewDecision,
    Product,
    CallToolResult,
    RateLimitReachedType,
    RateLimitSnapshot,
    RateLimitWindow,
    RealtimeAudioFrame,
    RealtimeConversationClosedEvent,
    RealtimeConversationListVoicesResponseEvent,
    RealtimeConversationRealtimeEvent,
    RealtimeConversationSdpEvent,
    RealtimeConversationStartedEvent,
    RealtimeConversationVersion,
    RealtimeOutputModality,
    RealtimeVoice,
    RealtimeVoicesList,
    ReasoningEffort,
    ReasoningSummary,
    ResumedHistory,
    RolloutItem,
    RequestId,
    RequestUserInputAnswer,
    RequestUserInputArgs,
    RequestUserInputEvent,
    RequestUserInputQuestion,
    RequestUserInputQuestionOption,
    RequestUserInputResponse,
    RequestPermissionProfile,
    RequestPermissionsEvent,
    RequestPermissionsResponse,
    SandboxPolicy,
    SessionConfiguredEvent,
    SessionId,
    SessionMeta,
    SessionMetaLine,
    SessionNetworkProxyRuntime,
    SessionSource,
    Settings,
    SubAgentSource,
    Submission,
    ThreadGoal,
    ThreadGoalStatus,
    ThreadGoalUpdatedEvent,
    ThreadId,
    ThreadMemoryMode,
    ThreadSource,
    ThreadSettingsAppliedEvent,
    ThreadSettingsOverrides,
    ThreadSettingsSnapshot,
    TokenCountEvent,
    TokenUsage,
    TokenUsageInfo,
    TurnAbortedEvent,
    TurnAbortReason,
    TurnContextItem,
    TurnContextNetworkItem,
    TurnEnvironmentSelection,
    TurnStartedEvent,
    UserInput,
    W3cTraceContext,
    WindowsSandboxLevel,
    validate_thread_goal_objective,
)


class ProtocolProtocolTests(unittest.TestCase):
    def test_request_user_input_shapes_and_defaults(self):
        question = RequestUserInputQuestion.from_mapping(
            {
                "id": "choice",
                "header": "Pick",
                "question": "Which one?",
                "options": [{"label": "A", "description": "Use A"}],
            }
        )
        args = RequestUserInputArgs((question,))
        response = RequestUserInputResponse({"choice": RequestUserInputAnswer(("A",))})
        event = RequestUserInputEvent("call-1", (question,))

        self.assertEqual(question.is_other, False)
        self.assertEqual(question.is_secret, False)
        self.assertEqual(question.options, (RequestUserInputQuestionOption("A", "Use A"),))
        self.assertEqual(args.to_mapping()["questions"][0]["isOther"], False)
        self.assertEqual(response.to_mapping(), {"answers": {"choice": {"answers": ["A"]}}})
        self.assertEqual(event.to_mapping()["turn_id"], "")

    def test_request_user_input_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "label must be a string"):
            RequestUserInputQuestionOption(123, "description")

        with self.assertRaisesRegex(TypeError, "id must be a string"):
            RequestUserInputQuestion(123, "Header", "Question")

        with self.assertRaisesRegex(TypeError, "is_other must be a bool"):
            RequestUserInputQuestion("id", "Header", "Question", is_other=1)

        with self.assertRaisesRegex(TypeError, "options entries must be RequestUserInputQuestionOption"):
            RequestUserInputQuestion("id", "Header", "Question", options=({"label": "A", "description": "Use A"},))

        with self.assertRaisesRegex(TypeError, "questions entries must be RequestUserInputQuestion"):
            RequestUserInputArgs(({"id": "choice"},))

        with self.assertRaisesRegex(TypeError, "answer keys must be strings"):
            RequestUserInputResponse({1: RequestUserInputAnswer(("A",))})

        with self.assertRaisesRegex(TypeError, "answer values must be RequestUserInputAnswer"):
            RequestUserInputResponse({"choice": {"answers": ["A"]}})

        with self.assertRaisesRegex(TypeError, "answer keys must be strings"):
            RequestUserInputResponse.from_mapping({"answers": {1: {"answers": ["A"]}}})

        with self.assertRaisesRegex(TypeError, "call_id must be a string"):
            RequestUserInputEvent(123, ())

        with self.assertRaisesRegex(TypeError, "turn_id must be a string"):
            RequestUserInputEvent("call-1", (), turn_id=123)

        with self.assertRaisesRegex(TypeError, "turn_id must be a string"):
            RequestUserInputEvent.from_mapping({"call_id": "call-1", "turn_id": 123, "questions": []})

    def test_session_source_from_startup_arg_maps_known_and_custom_values(self):
        self.assertEqual(SessionSource.from_startup_arg("vscode"), SessionSource.vscode())
        self.assertEqual(SessionSource.from_startup_arg("app-server"), SessionSource.mcp())
        self.assertEqual(SessionSource.from_startup_arg(" Atlas "), SessionSource.custom_source("atlas"))

        with self.assertRaisesRegex(ValueError, "must not be empty"):
            SessionSource.from_startup_arg(" ")

    def test_session_source_product_restrictions_match_upstream(self):
        self.assertEqual(SessionSource.cli().restriction_product(), Product.CODEX)
        self.assertEqual(SessionSource.vscode().restriction_product(), Product.CODEX)
        self.assertEqual(SessionSource.exec().restriction_product(), Product.CODEX)
        self.assertEqual(SessionSource.mcp().restriction_product(), Product.CODEX)
        self.assertEqual(SessionSource.unknown().restriction_product(), Product.CODEX)
        self.assertIsNone(SessionSource.subagent(SubAgentSource.review()).restriction_product())
        self.assertIsNone(SessionSource.internal(InternalSessionSource.MEMORY_CONSOLIDATION).restriction_product())
        self.assertEqual(SessionSource.custom_source("chatgpt").restriction_product(), Product.CHATGPT)
        self.assertEqual(SessionSource.custom_source("ATLAS").restriction_product(), Product.ATLAS)
        self.assertIsNone(SessionSource.custom_source("atlas-dev").restriction_product())

        self.assertTrue(SessionSource.custom_source("chatgpt").matches_product_restriction((Product.CHATGPT,)))
        self.assertFalse(SessionSource.custom_source("chatgpt").matches_product_restriction((Product.CODEX,)))
        self.assertTrue(SessionSource.vscode().matches_product_restriction((Product.CODEX,)))
        self.assertFalse(SessionSource.custom_source("atlas-dev").matches_product_restriction((Product.ATLAS,)))
        self.assertTrue(SessionSource.custom_source("atlas-dev").matches_product_restriction(()))

    def test_subagent_source_display_and_accessors(self):
        parent = ThreadId.from_string("11111111-1111-1111-1111-111111111111")
        agent_path = AgentPath.root().join("worker")
        subagent = SubAgentSource.thread_spawn(
            parent,
            2,
            agent_path=agent_path,
            agent_nickname="worker-one",
            agent_role="reviewer",
        )
        source = SessionSource.subagent(subagent)

        self.assertEqual(str(subagent), f"thread_spawn_{parent}_d2")
        self.assertEqual(str(source), f"subagent_thread_spawn_{parent}_d2")
        self.assertTrue(source.is_non_root_agent())
        self.assertEqual(source.get_nickname(), "worker-one")
        self.assertEqual(source.get_agent_role(), "reviewer")
        self.assertEqual(source.get_agent_path(), agent_path)

    def test_thread_source_and_product_helpers(self):
        self.assertEqual(str(ThreadSource.parse("memory_consolidation")), "memory_consolidation")
        self.assertEqual(Product.parse("CHATGPT").to_app_platform(), "chat")
        self.assertTrue(Product.ATLAS.matches_product_restriction((Product.ATLAS,)))

        with self.assertRaisesRegex(ValueError, "unknown thread source"):
            ThreadSource.parse("other")

    def test_granular_approval_config_defaults_and_accessors(self):
        decoded = GranularApprovalConfig.from_mapping(
            {
                "sandbox_approval": True,
                "rules": False,
                "mcp_elicitations": True,
            }
        )

        self.assertTrue(decoded.allows_sandbox_approval())
        self.assertFalse(decoded.allows_rules_approval())
        self.assertFalse(decoded.allows_skill_approval())
        self.assertFalse(decoded.allows_request_permissions())
        self.assertTrue(decoded.allows_mcp_elicitations())
        self.assertEqual(
            decoded.to_mapping(),
            {
                "sandbox_approval": True,
                "rules": False,
                "skill_approval": False,
                "request_permissions": False,
                "mcp_elicitations": True,
            },
        )

    def test_approval_policy_display_value_matches_rust_labels(self):
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=False,
            request_permissions=True,
            mcp_elicitations=False,
        )

        self.assertEqual(approval_policy_display_value(AskForApproval.ON_REQUEST), "on-request")
        self.assertEqual(approval_policy_display_value("never"), "never")
        self.assertEqual(approval_policy_display_value(granular), "granular")
        self.assertEqual(approval_policy_display_value({"granular": granular.to_mapping()}), "granular")

    def test_op_transport_shape_and_kind_aliases(self):
        op = Op.from_mapping({"type": "request_user_input_response", "id": "turn", "response": {"answers": {}}})
        self.assertEqual(op.kind(), "user_input_answer")
        self.assertEqual(op.to_mapping()["type"], "user_input_answer")

        user_input = Op.user_input([{"type": "text", "text": "hello"}], final_output_json_schema={"type": "object"})
        self.assertEqual(user_input.kind(), "user_input")
        self.assertEqual(user_input.to_mapping()["items"][0]["text"], "hello")

        elicitation = Op.resolve_elicitation("server", RequestId.integer(7), "accept", content={"ok": True})
        self.assertEqual(elicitation.to_mapping()["request_id"], 7)

    def test_realtime_conversation_ops_serialize_as_unnested_variants(self):
        start = Op.realtime_conversation_start(
            ConversationStartParams(
                output_modality=RealtimeOutputModality.AUDIO,
                prompt="be helpful",
                realtime_session_id="conv_1",
            )
        )
        default_prompt_start = Op.realtime_conversation_start(
            ConversationStartParams(output_modality=RealtimeOutputModality.AUDIO)
        )
        null_prompt_start = Op.realtime_conversation_start(
            ConversationStartParams(output_modality=RealtimeOutputModality.AUDIO, prompt=None)
        )
        webrtc_start = Op.realtime_conversation_start(
            ConversationStartParams(
                output_modality=RealtimeOutputModality.AUDIO,
                prompt="be helpful",
                realtime_session_id="conv_1",
                transport=ConversationStartTransport.webrtc("v=offer\r\n"),
                voice=RealtimeVoice.COVE,
            )
        )
        audio = Op.realtime_conversation_audio(
            ConversationAudioParams(
                RealtimeAudioFrame(
                    data="AQID",
                    sample_rate=24_000,
                    num_channels=1,
                    samples_per_channel=480,
                )
            )
        )
        text = Op.realtime_conversation_text(ConversationTextParams("hello"))
        close = Op.realtime_conversation_close()
        list_voices = Op.realtime_conversation_list_voices()

        self.assertEqual(
            start.to_mapping(),
            {
                "type": "realtime_conversation_start",
                "output_modality": "audio",
                "prompt": "be helpful",
                "realtime_session_id": "conv_1",
            },
        )
        self.assertEqual(default_prompt_start.to_mapping(), {"type": "realtime_conversation_start", "output_modality": "audio"})
        self.assertEqual(null_prompt_start.to_mapping(), {"type": "realtime_conversation_start", "output_modality": "audio", "prompt": None})
        self.assertEqual(
            audio.to_mapping(),
            {
                "type": "realtime_conversation_audio",
                "frame": {
                    "data": "AQID",
                    "sample_rate": 24_000,
                    "num_channels": 1,
                    "samples_per_channel": 480,
                },
            },
        )
        self.assertEqual(text.to_mapping(), {"type": "realtime_conversation_text", "text": "hello"})
        self.assertEqual(close.to_mapping(), {"type": "realtime_conversation_close"})
        self.assertEqual(list_voices.to_mapping(), {"type": "realtime_conversation_list_voices"})
        self.assertEqual(
            webrtc_start.to_mapping(),
            {
                "type": "realtime_conversation_start",
                "output_modality": "audio",
                "prompt": "be helpful",
                "realtime_session_id": "conv_1",
                "transport": {"type": "webrtc", "sdp": "v=offer\r\n"},
                "voice": "cove",
            },
        )

        for op in (default_prompt_start, null_prompt_start, audio, text, close, list_voices, webrtc_start):
            with self.subTest(op=op.kind()):
                self.assertEqual(Op.from_mapping(op.to_mapping()), op)

    def test_user_input_op_matches_upstream_optional_field_rules(self):
        empty = Op.user_input(())
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
        with_schema = Op.user_input((), final_output_json_schema=schema)
        with_metadata = Op.user_input((), responsesapi_client_metadata={"fiber_run_id": "fiber-123"})
        with_additional_context = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context"}},
        )

        self.assertEqual(empty.to_mapping(), {"type": "user_input", "items": []})
        self.assertEqual(Op.from_mapping({"type": "user_input", "items": []}), empty)
        self.assertEqual(
            with_schema.to_mapping(),
            {"type": "user_input", "items": [], "final_output_json_schema": schema},
        )
        self.assertEqual(
            with_metadata.to_mapping(),
            {
                "type": "user_input",
                "items": [],
                "responsesapi_client_metadata": {"fiber_run_id": "fiber-123"},
            },
        )
        self.assertEqual(
            with_additional_context.to_mapping(),
            {
                "type": "user_input",
                "items": [],
                "additional_context": {"app": {"kind": "application", "value": "context"}},
            },
        )
        self.assertEqual(Op.from_mapping(with_metadata.to_mapping()), with_metadata)
        self.assertEqual(Op.from_mapping(with_additional_context.to_mapping()), with_additional_context)

    def test_user_input_op_flattens_thread_settings_overrides(self):
        thread_settings = ThreadSettingsOverrides(
            cwd=Path("/repo"),
            workspace_roots=(Path("/repo"), Path("/other")),
            profile_workspace_roots=(Path("/repo/profile"),),
            approval_policy=AskForApproval.ON_FAILURE,
            approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW,
            sandbox_policy=SandboxPolicy.read_only(network_access=True),
            permission_profile=PermissionProfile.disabled(),
            active_permission_profile=ActivePermissionProfile("dev", ":workspace"),
            windows_sandbox_level=WindowsSandboxLevel.RESTRICTED_TOKEN,
            model="gpt-5.2-codex",
            effort=None,
            summary=ReasoningSummary.DETAILED,
            service_tier=None,
            collaboration_mode=CollaborationMode(
                mode=ModeKind.DEFAULT,
                settings=Settings("gpt-5.2-codex", ReasoningEffort.HIGH, "ship it"),
            ),
            personality=Personality.PRAGMATIC,
        )
        op = Op.user_input(
            (UserInput.text_input("hello"),),
            environments=(TurnEnvironmentSelection("env-1", Path("/repo")),),
            thread_settings=thread_settings,
        )
        payload = op.to_mapping()
        settings_op = Op.thread_settings(thread_settings)

        self.assertEqual(payload["type"], "user_input")
        self.assertEqual(payload["items"], [{"type": "text", "text": "hello", "text_elements": []}])
        self.assertEqual(payload["environments"], [{"environment_id": "env-1", "cwd": str(Path("/repo"))}])
        self.assertEqual(payload["cwd"], str(Path("/repo")))
        self.assertEqual(payload["workspace_roots"], [str(Path("/repo")), str(Path("/other"))])
        self.assertEqual(payload["profile_workspace_roots"], [str(Path("/repo/profile"))])
        self.assertEqual(payload["approval_policy"], "on-failure")
        self.assertEqual(payload["approvals_reviewer"], "guardian_subagent")
        self.assertEqual(payload["sandbox_policy"], {"type": "read-only", "network_access": True})
        self.assertEqual(payload["permission_profile"], {"type": "disabled"})
        self.assertEqual(payload["active_permission_profile"], {"id": "dev", "extends": ":workspace"})
        self.assertEqual(payload["windows_sandbox_level"], "restricted-token")
        self.assertEqual(payload["model"], "gpt-5.2-codex")
        self.assertIsNone(payload["effort"])
        self.assertEqual(payload["summary"], "detailed")
        self.assertIsNone(payload["service_tier"])
        self.assertEqual(payload["collaboration_mode"]["settings"]["developer_instructions"], "ship it")
        self.assertEqual(payload["personality"], "pragmatic")
        self.assertEqual(Op.from_mapping(payload), op)
        self.assertEqual(Op.from_mapping(settings_op.to_mapping()), settings_op)

    def test_response_ops_parse_structured_payloads(self):
        exec_approval = Op.exec_approval("approval-1", ReviewDecision.approved_for_session(), turn_id="turn-1")
        patch_approval = Op.patch_approval("patch-1", ReviewDecision.denied())
        elicitation = Op.resolve_elicitation(
            "server",
            RequestId.integer(9),
            ElicitationAction.ACCEPT,
            content={"choice": "yes"},
            meta={"trace": "t"},
        )
        user_answer = Op.user_input_answer(
            "turn-1",
            RequestUserInputResponse({"choice": RequestUserInputAnswer(("A", "B"))}),
        )
        permission_response = Op.request_permissions_response(
            "perm-1",
            RequestPermissionsResponse(
                RequestPermissionProfile(
                    network=NetworkPermissions(enabled=True),
                    file_system=FileSystemPermissions.from_read_write_roots((Path("/repo"),), None),
                ),
                scope="session",
            ),
        )
        dynamic_response = Op.dynamic_tool_response(
            "dyn-1",
            DynamicToolResponse((DynamicToolCallOutputContentItem.input_text("done"),), True),
        )

        self.assertEqual(
            exec_approval.to_mapping(),
            {"type": "exec_approval", "id": "approval-1", "decision": "approved_for_session", "turn_id": "turn-1"},
        )
        self.assertEqual(patch_approval.to_mapping(), {"type": "patch_approval", "id": "patch-1", "decision": "denied"})
        self.assertEqual(
            elicitation.to_mapping(),
            {
                "type": "resolve_elicitation",
                "server_name": "server",
                "request_id": 9,
                "decision": "accept",
                "content": {"choice": "yes"},
                "meta": {"trace": "t"},
            },
        )
        self.assertEqual(
            user_answer.to_mapping(),
            {
                "type": "user_input_answer",
                "id": "turn-1",
                "response": {"answers": {"choice": {"answers": ["A", "B"]}}},
            },
        )
        self.assertEqual(
            permission_response.to_mapping()["response"],
            {
                "permissions": {
                    "network": {"enabled": True},
                    "file_system": {"read": [str(Path("/repo"))]},
                },
                "scope": "session",
            },
        )
        self.assertEqual(
            dynamic_response.to_mapping(),
            {
                "type": "dynamic_tool_response",
                "id": "dyn-1",
                "response": {"contentItems": [{"type": "inputText", "text": "done"}], "success": True},
            },
        )

        for op in (exec_approval, patch_approval, elicitation, user_answer, permission_response, dynamic_response):
            with self.subTest(op=op.kind()):
                self.assertEqual(Op.from_mapping(op.to_mapping()), op)

    def test_control_ops_parse_structured_payloads(self):
        guardian_event = GuardianAssessmentEvent(
            id="guardian-1",
            turn_id="turn-1",
            status=GuardianAssessmentStatus.DENIED,
            action=GuardianAssessmentAction.command_action(GuardianCommandSource.SHELL, "rm -rf tmp", Path("/repo")),
        )
        communication = InterAgentCommunication(
            author=AgentPath.root(),
            recipient=AgentPath.from_string("/root/reviewer"),
            other_recipients=(AgentPath.from_string("/root/observer"),),
            content="please review",
            trigger_turn=True,
        )
        refresh = McpServerRefreshConfig(
            mcp_servers={"github": {"command": "gh"}},
            mcp_oauth_credentials_store_mode={"mode": "memory"},
        )

        ops = (
            Op.inter_agent_communication(communication),
            Op.refresh_mcp_servers(refresh),
            Op.simple("reload_user_config"),
            Op.set_thread_memory_mode(ThreadMemoryMode.DISABLED),
            Op.thread_rollback(2),
            Op.approve_guardian_denied_action(guardian_event),
            Op.simple("clean_background_terminals"),
            Op.simple("compact"),
            Op.simple("shutdown"),
            Op.run_user_shell_command("echo hi"),
        )

        self.assertEqual(
            ops[0].to_mapping(),
            {
                "type": "inter_agent_communication",
                "communication": {
                    "author": "/root",
                    "recipient": "/root/reviewer",
                    "other_recipients": ["/root/observer"],
                    "content": "please review",
                    "trigger_turn": True,
                },
            },
        )
        self.assertEqual(
            ops[1].to_mapping(),
            {
                "type": "refresh_mcp_servers",
                "config": {
                    "mcp_servers": {"github": {"command": "gh"}},
                    "mcp_oauth_credentials_store_mode": {"mode": "memory"},
                },
            },
        )
        self.assertEqual(ops[3].to_mapping(), {"type": "set_thread_memory_mode", "mode": "disabled"})
        self.assertEqual(ops[4].to_mapping(), {"type": "thread_rollback", "num_turns": 2})
        self.assertEqual(ops[6].to_mapping(), {"type": "clean_background_terminals"})
        self.assertEqual(ops[9].to_mapping(), {"type": "run_user_shell_command", "command": "echo hi"})

        for op in ops:
            with self.subTest(op=op.kind()):
                self.assertEqual(Op.from_mapping(op.to_mapping()), op)

    def test_request_event_payloads_parse_structured_payloads(self):
        repo = Path("/repo")
        exec_payload = {
            "type": "exec_approval_request",
            "call_id": "call-1",
            "approval_id": "approval-1",
            "turn_id": "turn-1",
            "started_at_ms": 10,
            "command": ["git", "status"],
            "cwd": str(repo),
            "reason": "need approval",
            "network_approval_context": {"host": "api.example.com", "protocol": "https"},
            "proposed_execpolicy_amendment": {"command": ["git", "status"]},
            "proposed_network_policy_amendments": [{"host": "api.example.com", "action": "allow"}],
            "additional_permissions": {"network": {"enabled": True}},
            "available_decisions": [
                "approved",
                {
                    "network_policy_amendment": {
                        "network_policy_amendment": {"host": "api.example.com", "action": "allow"}
                    }
                },
                "abort",
            ],
            "parsed_cmd": [{"type": "unknown", "cmd": "git status"}],
        }
        exec_msg = EventMsg.from_mapping(exec_payload)

        self.assertEqual(exec_msg.payload.command, ("git", "status"))
        self.assertEqual(exec_msg.payload.cwd, repo)
        self.assertEqual(
            exec_msg.payload.network_approval_context,
            NetworkApprovalContext("api.example.com", NetworkApprovalProtocol.HTTPS),
        )
        self.assertEqual(exec_msg.payload.proposed_execpolicy_amendment, ExecPolicyAmendment.new(["git", "status"]))
        self.assertEqual(
            exec_msg.payload.proposed_network_policy_amendments,
            (NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW),),
        )
        self.assertEqual(exec_msg.payload.additional_permissions, AdditionalPermissionProfile(network=NetworkPermissions(True)))
        self.assertEqual(exec_msg.payload.parsed_cmd, (ParsedCommand.unknown("git status"),))
        self.assertEqual(exec_msg.to_mapping(), exec_payload)

        app_server_exec_payload = {
            "type": "exec_approval_request",
            "itemId": "call-2",
            "approvalId": "approval-2",
            "turnId": "turn-2",
            "startedAtMs": 11,
            "command": "cat README.md",
            "cwd": str(repo),
            "networkApprovalContext": {"host": "api.example.com", "protocol": "https"},
            "availableDecisions": ["accept", "acceptForSession", "Cancel"],
            "commandActions": [
                {"type": "read", "command": "cat README.md", "name": "README.md", "path": str(repo / "README.md")}
            ],
        }
        app_server_exec_msg = EventMsg.from_mapping(app_server_exec_payload)

        self.assertEqual(app_server_exec_msg.payload.call_id, "call-2")
        self.assertEqual(app_server_exec_msg.payload.effective_approval_id(), "approval-2")
        self.assertEqual(app_server_exec_msg.payload.turn_id, "turn-2")
        self.assertEqual(app_server_exec_msg.payload.started_at_ms, 11)
        self.assertEqual(app_server_exec_msg.payload.command, ("cat README.md",))
        self.assertEqual(app_server_exec_msg.payload.parsed_cmd, (ParsedCommand.read("cat README.md", "README.md", repo / "README.md"),))
        self.assertEqual(
            app_server_exec_msg.payload.available_decisions,
            (ReviewDecision.approved(), ReviewDecision.approved_for_session(), ReviewDecision.abort()),
        )

        app_server_file_change_payload = {
            "type": "apply_patch_approval_request",
            "itemId": "patch-1",
            "turnId": "turn-1",
            "startedAtMs": 12,
            "reason": "need write access",
            "grantRoot": str(repo),
        }
        app_server_file_change_msg = EventMsg.from_mapping(app_server_file_change_payload)

        self.assertEqual(app_server_file_change_msg.payload.call_id, "patch-1")
        self.assertEqual(app_server_file_change_msg.payload.turn_id, "turn-1")
        self.assertEqual(app_server_file_change_msg.payload.started_at_ms, 12)
        self.assertEqual(app_server_file_change_msg.payload.changes, {})
        self.assertEqual(app_server_file_change_msg.payload.reason, "need write access")
        self.assertEqual(app_server_file_change_msg.payload.grant_root, repo)

        request_permissions_payload = {
            "type": "request_permissions",
            "call_id": "perm-1",
            "turn_id": "turn-1",
            "started_at_ms": 11,
            "reason": "need network",
            "permissions": {"network": {"enabled": True}},
            "cwd": str(repo),
        }
        request_permissions_msg = EventMsg.from_mapping(request_permissions_payload)
        self.assertEqual(
            request_permissions_msg.payload,
            RequestPermissionsEvent(
                call_id="perm-1",
                turn_id="turn-1",
                started_at_ms=11,
                reason="need network",
                permissions=RequestPermissionProfile(network=NetworkPermissions(True)),
                cwd=repo,
            ),
        )
        self.assertEqual(request_permissions_msg.to_mapping(), request_permissions_payload)

        app_server_request_permissions_payload = {
            "type": "request_permissions",
            "itemId": "perm-2",
            "turnId": "turn-2",
            "startedAtMs": 12,
            "reason": "need network",
            "permissions": {"network": {"enabled": True}},
            "cwd": str(repo),
        }
        app_server_request_permissions_msg = EventMsg.from_mapping(app_server_request_permissions_payload)
        self.assertEqual(
            app_server_request_permissions_msg.payload,
            RequestPermissionsEvent(
                call_id="perm-2",
                turn_id="turn-2",
                started_at_ms=12,
                reason="need network",
                permissions=RequestPermissionProfile(network=NetworkPermissions(True)),
                cwd=repo,
            ),
        )

        request_user_input_payload = {
            "type": "request_user_input",
            "call_id": "input-1",
            "turn_id": "turn-1",
            "questions": [
                {
                    "id": "choice",
                    "header": "Choice",
                    "question": "Pick one",
                    "isOther": False,
                    "isSecret": False,
                    "options": [{"label": "A", "description": "First"}],
                }
            ],
        }
        request_user_input_msg = EventMsg.from_mapping(request_user_input_payload)
        self.assertEqual(
            request_user_input_msg.payload,
            RequestUserInputEvent(
                call_id="input-1",
                turn_id="turn-1",
                questions=(
                    RequestUserInputQuestion(
                        id="choice",
                        header="Choice",
                        question="Pick one",
                        options=(RequestUserInputQuestionOption("A", "First"),),
                    ),
                ),
            ),
        )
        self.assertEqual(request_user_input_msg.to_mapping(), request_user_input_payload)

    def test_tool_elicitation_and_patch_request_events_roundtrip(self):
        dynamic_request_payload = {
            "type": "dynamic_tool_call_request",
            "callId": "dyn-1",
            "turnId": "turn-1",
            "startedAtMs": 12,
            "namespace": "support",
            "tool": "lookup_ticket",
            "arguments": {"id": "T-1"},
        }
        dynamic_request_msg = EventMsg.from_mapping(dynamic_request_payload)
        self.assertEqual(
            dynamic_request_msg.payload,
            DynamicToolCallRequest("dyn-1", "turn-1", "lookup_ticket", {"id": "T-1"}, 12, "support"),
        )
        self.assertEqual(dynamic_request_msg.to_mapping(), dynamic_request_payload)

        dynamic_response_payload = {
            "type": "dynamic_tool_call_response",
            "call_id": "dyn-1",
            "turn_id": "turn-1",
            "completed_at_ms": 13,
            "namespace": "support",
            "tool": "lookup_ticket",
            "arguments": {"id": "T-1"},
            "content_items": [{"type": "inputText", "text": "done"}],
            "success": True,
            "error": None,
            "duration": "1s",
        }
        dynamic_response_msg = EventMsg.from_mapping(dynamic_response_payload)
        self.assertEqual(dynamic_response_msg.payload.content_items, (DynamicToolCallOutputContentItem.input_text("done"),))
        self.assertEqual(dynamic_response_msg.to_mapping(), dynamic_response_payload)

        elicitation_payload = {
            "type": "elicitation_request",
            "turn_id": "turn-1",
            "server_name": "server",
            "id": 7,
            "request": {
                "mode": "form",
                "_meta": {"trace": "t"},
                "message": "Fill this",
                "requested_schema": {"type": "object"},
            },
        }
        elicitation_msg = EventMsg.from_mapping(elicitation_payload)
        self.assertEqual(
            elicitation_msg.payload,
            ElicitationRequestEvent(
                turn_id="turn-1",
                server_name="server",
                id=RequestId.integer(7),
                request=ElicitationRequest.form("Fill this", {"type": "object"}, meta={"trace": "t"}),
            ),
        )
        self.assertEqual(elicitation_msg.to_mapping(), elicitation_payload)

        patch_payload = {
            "type": "apply_patch_approval_request",
            "call_id": "patch-1",
            "turn_id": "turn-1",
            "started_at_ms": 14,
            "changes": {"new.py": {"type": "add", "content": "print('hi')"}},
            "reason": "write outside workspace",
            "grant_root": str(Path("/repo")),
        }
        patch_msg = EventMsg.from_mapping(patch_payload)
        self.assertEqual(
            patch_msg.payload,
            ApplyPatchApprovalRequestEvent(
                call_id="patch-1",
                turn_id="turn-1",
                started_at_ms=14,
                changes={Path("new.py"): FileChange.add("print('hi')")},
                reason="write outside workspace",
                grant_root=Path("/repo"),
            ),
        )
        self.assertEqual(patch_msg.to_mapping(), patch_payload)

    def test_model_guardrail_events_parse_structured_payloads(self):
        reroute_payload = {
            "type": "model_reroute",
            "from_model": "gpt-5",
            "to_model": "gpt-5-safe",
            "reason": "high_risk_cyber_activity",
        }
        verification_payload = {
            "type": "model_verification",
            "verifications": ["trusted_access_for_cyber"],
        }
        compacted_payload = {"type": "context_compacted"}
        reasoning_section_break_payload = {
            "type": "agent_reasoning_section_break",
            "item_id": "reason-1",
            "summary_index": 2,
        }
        reasoning_section_break_legacy_payload = {"type": "agent_reasoning_section_break"}

        self.assertEqual(
            EventMsg.from_mapping(reroute_payload).payload,
            ModelRerouteEvent("gpt-5", "gpt-5-safe", ModelRerouteReason.HIGH_RISK_CYBER_ACTIVITY),
        )
        self.assertEqual(
            EventMsg.from_mapping(verification_payload).payload,
            ModelVerificationEvent((ModelVerification.TRUSTED_ACCESS_FOR_CYBER,)),
        )
        self.assertEqual(EventMsg.from_mapping(compacted_payload).payload, ContextCompactedEvent())
        self.assertEqual(
            EventMsg.from_mapping(reasoning_section_break_payload).payload,
            AgentReasoningSectionBreakEvent(item_id="reason-1", summary_index=2),
        )
        self.assertEqual(
            EventMsg.from_mapping(reasoning_section_break_legacy_payload).payload,
            AgentReasoningSectionBreakEvent(),
        )
        self.assertEqual(EventMsg.from_mapping(reroute_payload).to_mapping(), reroute_payload)
        self.assertEqual(EventMsg.from_mapping(verification_payload).to_mapping(), verification_payload)
        self.assertEqual(EventMsg.from_mapping(compacted_payload).to_mapping(), compacted_payload)
        self.assertEqual(
            EventMsg.from_mapping(reasoning_section_break_payload).to_mapping(),
            reasoning_section_break_payload,
        )

    def test_guardian_assessment_event_roundtrips(self):
        payload = {
            "type": "guardian_assessment",
            "id": "guardian-1",
            "target_item_id": "call-1",
            "turn_id": "turn-1",
            "started_at_ms": 10,
            "completed_at_ms": 20,
            "status": "approved",
            "risk_level": "medium",
            "user_authorization": "high",
            "rationale": "safe enough",
            "decision_source": "agent",
            "action": {
                "type": "execve",
                "source": "unified_exec",
                "program": "/bin/echo",
                "argv": ["echo", "hi"],
                "cwd": str(Path("/repo")),
            },
        }

        msg = EventMsg.from_mapping(payload)

        self.assertEqual(
            msg.payload,
            GuardianAssessmentEvent(
                id="guardian-1",
                target_item_id="call-1",
                turn_id="turn-1",
                started_at_ms=10,
                completed_at_ms=20,
                status=GuardianAssessmentStatus.APPROVED,
                risk_level=GuardianRiskLevel.MEDIUM,
                user_authorization=GuardianUserAuthorization.HIGH,
                rationale="safe enough",
                decision_source=GuardianAssessmentDecisionSource.AGENT,
                action=GuardianAssessmentAction.execve(
                    GuardianCommandSource.UNIFIED_EXEC,
                    "/bin/echo",
                    ("echo", "hi"),
                    Path("/repo"),
                ),
            ),
        )
        self.assertEqual(msg.to_mapping(), payload)

    def test_collab_agent_status_round_trips_upstream_json_shape(self):
        self.assertEqual(AgentStatus.from_mapping("running"), AgentStatus.running())
        self.assertEqual(AgentStatus.running().to_mapping(), "running")
        self.assertEqual(AgentStatus.from_mapping({"completed": "done"}), AgentStatus.completed("done"))
        self.assertEqual(AgentStatus.completed(None).to_mapping(), {"completed": None})
        self.assertEqual(AgentStatus.from_mapping({"errored": "boom"}), AgentStatus.errored("boom"))
        self.assertEqual(AgentStatus.errored("boom").to_mapping(), {"errored": "boom"})

    def test_collab_event_payloads_roundtrip(self):
        sender = "11111111-1111-4111-8111-111111111111"
        receiver = "22222222-2222-4222-8222-222222222222"
        spawned = "33333333-3333-4333-8333-333333333333"

        payloads = [
            {
                "type": "collab_agent_spawn_begin",
                "call_id": "spawn-1",
                "started_at_ms": 1,
                "sender_thread_id": sender,
                "prompt": "start",
                "model": "gpt-5",
                "reasoning_effort": "medium",
            },
            {
                "type": "collab_agent_spawn_end",
                "call_id": "spawn-1",
                "completed_at_ms": 2,
                "sender_thread_id": sender,
                "new_thread_id": spawned,
                "new_agent_nickname": "worker",
                "new_agent_role": "reviewer",
                "prompt": "start",
                "model": "gpt-5",
                "reasoning_effort": "medium",
                "status": {"completed": "ready"},
            },
            {
                "type": "collab_agent_interaction_begin",
                "call_id": "ask-1",
                "started_at_ms": 3,
                "sender_thread_id": sender,
                "receiver_thread_id": receiver,
                "prompt": "check this",
            },
            {
                "type": "collab_agent_interaction_end",
                "call_id": "ask-1",
                "completed_at_ms": 4,
                "sender_thread_id": sender,
                "receiver_thread_id": receiver,
                "receiver_agent_nickname": "worker",
                "receiver_agent_role": "reviewer",
                "prompt": "check this",
                "status": "running",
            },
            {
                "type": "collab_waiting_begin",
                "started_at_ms": 5,
                "sender_thread_id": sender,
                "receiver_thread_ids": [receiver],
                "receiver_agents": [
                    {
                        "thread_id": receiver,
                        "agent_nickname": "worker",
                        "agent_role": "reviewer",
                    }
                ],
                "call_id": "wait-1",
            },
            {
                "type": "collab_waiting_end",
                "sender_thread_id": sender,
                "call_id": "wait-1",
                "completed_at_ms": 6,
                "agent_statuses": [
                    {
                        "thread_id": receiver,
                        "agent_nickname": "worker",
                        "agent_role": "reviewer",
                        "status": {"completed": None},
                    }
                ],
                "statuses": {receiver: {"completed": None}},
            },
            {
                "type": "collab_close_begin",
                "call_id": "close-1",
                "started_at_ms": 7,
                "sender_thread_id": sender,
                "receiver_thread_id": receiver,
            },
            {
                "type": "collab_close_end",
                "call_id": "close-1",
                "completed_at_ms": 8,
                "sender_thread_id": sender,
                "receiver_thread_id": receiver,
                "receiver_agent_nickname": "worker",
                "receiver_agent_role": "reviewer",
                "status": "shutdown",
            },
            {
                "type": "collab_resume_begin",
                "call_id": "resume-1",
                "started_at_ms": 9,
                "sender_thread_id": sender,
                "receiver_thread_id": receiver,
                "receiver_agent_nickname": "worker",
                "receiver_agent_role": "reviewer",
            },
            {
                "type": "collab_resume_end",
                "call_id": "resume-1",
                "completed_at_ms": 10,
                "sender_thread_id": sender,
                "receiver_thread_id": receiver,
                "receiver_agent_nickname": "worker",
                "receiver_agent_role": "reviewer",
                "status": "interrupted",
            },
        ]

        expected_payload_types = (
            CollabAgentSpawnBeginEvent,
            CollabAgentSpawnEndEvent,
            CollabAgentInteractionBeginEvent,
            CollabAgentInteractionEndEvent,
            CollabWaitingBeginEvent,
            CollabWaitingEndEvent,
            CollabCloseBeginEvent,
            CollabCloseEndEvent,
            CollabResumeBeginEvent,
            CollabResumeEndEvent,
        )

        for payload, expected_type in zip(payloads, expected_payload_types, strict=True):
            with self.subTest(event=payload["type"]):
                msg = EventMsg.from_mapping(payload)
                self.assertIsInstance(msg.payload, expected_type)
                self.assertEqual(msg.to_mapping(), payload)

        waiting_begin = EventMsg.from_mapping(payloads[4]).payload
        self.assertEqual(
            waiting_begin.receiver_agents,
            (
                CollabAgentRef(
                    ThreadId.from_string(receiver),
                    agent_nickname="worker",
                    agent_role="reviewer",
                ),
            ),
        )
        waiting_end = EventMsg.from_mapping(payloads[5]).payload
        self.assertEqual(
            waiting_end.agent_statuses,
            (
                CollabAgentStatusEntry(
                    ThreadId.from_string(receiver),
                    AgentStatus.completed(None),
                    agent_nickname="worker",
                    agent_role="reviewer",
                ),
            ),
        )

    def test_submission_and_event_transport_shape(self):
        submission = Submission(
            "sub-1",
            Op.simple("compact"),
            trace=W3cTraceContext(traceparent="00-abc-def-01"),
        )
        event = Event("sub-1", EventMsg.with_payload("warning", {"message": "careful"}))

        self.assertEqual(submission.to_mapping()["op"]["type"], "compact")
        self.assertEqual(submission.to_mapping()["trace"]["traceparent"], "00-abc-def-01")
        self.assertEqual(event.to_mapping(), {"id": "sub-1", "msg": {"type": "warning", "message": "careful"}})

    def test_event_msg_aliases_and_payload_parsing(self):
        msg = EventMsg.from_mapping(
            {
                "type": "turn_started",
                "turn_id": "turn-1",
                "trace_id": "trace",
                "started_at": 123,
                "model_context_window": 200000,
            }
        )

        self.assertEqual(msg.kind(), "task_started")
        self.assertEqual(
            msg.payload,
            TurnStartedEvent(
                turn_id="turn-1",
                trace_id="trace",
                started_at=123,
                model_context_window=200000,
                collaboration_mode_kind="default",
            ),
        )
        self.assertEqual(msg.to_mapping()["type"], "task_started")

    def test_token_usage_helpers_and_final_output_display(self):
        usage = TokenUsage(
            input_tokens=15000,
            cached_input_tokens=5000,
            output_tokens=1200,
            reasoning_output_tokens=200,
            total_tokens=18000,
        )
        info = TokenUsageInfo.new_or_append(None, usage, 20000)

        self.assertEqual(usage.cached_input(), 5000)
        self.assertEqual(usage.non_cached_input(), 10000)
        self.assertEqual(usage.blended_total(), 11200)
        self.assertEqual(usage.percent_of_context_window_remaining(20000), 25)
        self.assertEqual(info.last_token_usage, usage)
        self.assertEqual(str(FinalOutput(usage)), "Token usage: total=11,200 input=10,000 (+ 5,000 cached) output=1,200 (reasoning 200)")

    def test_token_count_event_parses_rate_limit_snapshot(self):
        payload = {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 3,
                    "reasoning_output_tokens": 1,
                    "total_tokens": 13,
                },
                "last_token_usage": {
                    "input_tokens": 4,
                    "cached_input_tokens": 1,
                    "output_tokens": 2,
                    "reasoning_output_tokens": 0,
                    "total_tokens": 6,
                },
                "model_context_window": None,
            },
            "rate_limits": {
                "limit_id": "rl-1",
                "limit_name": "primary",
                "primary": {"used_percent": 87.5, "window_minutes": 300, "resets_at": 1_700_000_000},
                "secondary": {"used_percent": 12, "window_minutes": None, "resets_at": None},
                "credits": {"has_credits": True, "unlimited": False, "balance": "42"},
                "plan_type": "team",
                "rate_limit_reached_type": "workspace_owner_usage_limit_reached",
            },
        }

        msg = EventMsg.from_mapping(payload)
        event = msg.payload

        self.assertEqual(event.info.total_token_usage.total_tokens, 13)
        self.assertEqual(event.rate_limits.plan_type, AccountPlanType.TEAM)
        self.assertEqual(event.rate_limits.primary, RateLimitWindow(87.5, 300, 1_700_000_000))
        self.assertEqual(event.rate_limits.secondary.used_percent, 12.0)
        self.assertEqual(event.rate_limits.credits, CreditsSnapshot(True, False, "42"))
        self.assertEqual(
            event.rate_limits.rate_limit_reached_type,
            RateLimitReachedType.WORKSPACE_OWNER_USAGE_LIMIT_REACHED,
        )
        self.assertEqual(msg.to_mapping(), payload)

    def test_token_count_event_serializes_null_optional_fields(self):
        event = TokenCountEvent(
            info=TokenUsageInfo(TokenUsage(total_tokens=1), TokenUsage(total_tokens=1), None),
            rate_limits=RateLimitSnapshot(),
        )

        payload = event.to_mapping()

        self.assertIsNone(payload["info"]["model_context_window"])
        self.assertEqual(
            payload["rate_limits"],
            {
                "limit_id": None,
                "limit_name": None,
                "primary": None,
                "secondary": None,
                "credits": None,
                "plan_type": None,
                "rate_limit_reached_type": None,
            },
        )
        self.assertEqual(TokenCountEvent.from_mapping(payload), event)

    def test_thread_goal_validation_and_mapping(self):
        thread_id = ThreadId.from_string("22222222-2222-2222-2222-222222222222")
        goal = ThreadGoal(
            thread_id=thread_id,
            objective="port codex",
            status=ThreadGoalStatus.ACTIVE,
            token_budget=1000,
            tokens_used=12,
            time_used_seconds=3,
            created_at=1,
            updated_at=2,
        )
        event = ThreadGoalUpdatedEvent(thread_id, goal, turn_id="turn")
        event_payload = {"type": "thread_goal_updated", **event.to_mapping()}

        self.assertEqual(goal.to_mapping()["tokenBudget"], 1000)
        self.assertEqual(ThreadGoal.from_mapping(goal.to_mapping()), goal)
        self.assertEqual(event.to_mapping()["goal"]["status"], "active")
        self.assertEqual(ThreadGoalUpdatedEvent.from_mapping(event.to_mapping()), event)
        self.assertEqual(EventMsg.from_mapping(event_payload).payload, event)
        self.assertEqual(EventMsg.from_mapping(event_payload).to_mapping(), event_payload)
        self.assertEqual(ThreadGoalStatus.USAGE_LIMITED.value, "usageLimited")
        validate_thread_goal_objective("x" * 4000)
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            validate_thread_goal_objective("")
        with self.assertRaisesRegex(ValueError, "at most 4000"):
            validate_thread_goal_objective("x" * 4001)

    def test_initial_history_and_conversation_path_roundtrip(self):
        thread_id = ThreadId.from_string("22222222-2222-4222-8222-222222222222")
        forked_from_id = ThreadId.from_string("33333333-3333-4333-8333-333333333333")
        session_meta_item = {
            "type": "session_meta",
            "payload": {
                "id": thread_id.to_json(),
                "forked_from_id": forked_from_id.to_json(),
                "timestamp": "2025-01-01T00:00:00Z",
                "cwd": str(Path("/repo")),
                "originator": "test",
                "cli_version": "0.0.0",
                "source": "cli",
                "thread_source": "user",
                "base_instructions": {"kind": "default"},
                "dynamic_tools": [{"name": "lookup"}],
                "model_provider": None,
            },
        }
        user_message_item = {
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "hello", "local_images": [], "text_elements": []},
        }
        resumed_payload = {
            "conversation_id": thread_id.to_json(),
            "history": [session_meta_item, user_message_item],
            "rollout_path": str(Path("/repo/rollout.jsonl")),
        }

        conversation_path = ConversationPathResponseEvent(thread_id, Path("/repo/rollout.jsonl"))
        resumed = ResumedHistory.from_mapping(resumed_payload)
        initial = InitialHistory.resumed_history(resumed)

        self.assertEqual(conversation_path.to_mapping(), {"conversation_id": thread_id.to_json(), "path": str(Path("/repo/rollout.jsonl"))})
        self.assertEqual(ConversationPathResponseEvent.from_mapping(conversation_path.to_mapping()), conversation_path)
        self.assertEqual(resumed.to_mapping(), resumed_payload)
        self.assertEqual(InitialHistory.new().to_mapping(), "New")
        self.assertEqual(InitialHistory.cleared().to_mapping(), "Cleared")
        self.assertEqual(InitialHistory.from_mapping({"Resumed": resumed_payload}), initial)
        self.assertEqual(initial.to_mapping(), {"Resumed": resumed_payload})
        self.assertTrue(initial.scan_rollout_items(lambda item: item.type == "event_msg"))
        self.assertEqual(initial.forked_from_id(), forked_from_id)
        self.assertEqual(initial.session_cwd(), Path("/repo"))
        self.assertEqual(initial.get_base_instructions(), {"kind": "default"})
        self.assertEqual(initial.get_dynamic_tools(), [{"name": "lookup"}])
        self.assertIs(initial.get_resumed_thread_source(), ThreadSource.USER)
        self.assertEqual(initial.get_event_msgs(), (EventMsg.from_mapping(user_message_item["payload"]),))

        forked = InitialHistory.forked((session_meta_item,))
        self.assertEqual(forked.to_mapping(), {"Forked": [session_meta_item]})
        self.assertEqual(InitialHistory.from_mapping(forked.to_mapping()), forked)
        self.assertEqual(forked.forked_from_id(), thread_id)
        self.assertIsNone(InitialHistory.new().get_event_msgs())

    def test_rollout_item_models_roundtrip(self):
        thread_id = ThreadId.from_string("44444444-4444-4444-8444-444444444444")
        meta_payload = {
            "id": thread_id.to_json(),
            "timestamp": "2025-01-01T00:00:00Z",
            "cwd": str(Path("/repo")),
            "originator": "test",
            "cli_version": "0.0.0",
            "source": "cli",
            "thread_source": "user",
            "model_provider": None,
            "base_instructions": {"kind": "default"},
            "dynamic_tools": [{"name": "lookup"}],
            "git": {
                "commit_hash": "abc123",
                "branch": "main",
                "repository_url": "https://example.test/repo.git",
            },
        }
        session_meta_item = {"type": "session_meta", "payload": meta_payload}
        compacted_item = {
            "type": "compacted",
            "payload": {
                "message": "summary",
                "replacement_history": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
            },
        }
        event_msg_item = {
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": "turn-1", "last_agent_message": "done"},
        }

        self.assertEqual(GitInfo.from_mapping(meta_payload["git"]).to_mapping(), meta_payload["git"])
        self.assertEqual(SessionMetaLine.from_mapping(meta_payload).to_mapping(), meta_payload)
        self.assertEqual(RolloutItem.from_mapping(session_meta_item).to_mapping(), session_meta_item)
        self.assertEqual(RolloutItem.from_mapping(compacted_item).to_mapping(), compacted_item)
        self.assertEqual(RolloutItem.from_mapping(event_msg_item).to_mapping(), event_msg_item)
        self.assertEqual(
            RolloutItem.session_meta(
                SessionMetaLine(SessionMeta.from_mapping(meta_payload), GitInfo.from_mapping(meta_payload["git"]))
            ).to_mapping(),
            session_meta_item,
        )
        self.assertEqual(
            RolloutItem.compacted(CompactedItem.from_mapping(compacted_item["payload"])).to_mapping(),
            compacted_item,
        )

    def test_protocol_constants_and_network_access(self):
        self.assertEqual(USER_INSTRUCTIONS_OPEN_TAG, "<user_instructions>")
        self.assertEqual(USER_INSTRUCTIONS_CLOSE_TAG, "</user_instructions>")
        self.assertIs(NetworkAccess.default(), NetworkAccess.RESTRICTED)
        self.assertFalse(NetworkAccess.RESTRICTED.is_enabled())
        self.assertTrue(NetworkAccess.ENABLED.is_enabled())

    def test_turn_context_item_deserializes_legacy_sandbox_policy(self):
        cwd = Path("/repo")
        item = TurnContextItem.from_mapping(
            {
                "cwd": str(cwd),
                "approval_policy": "never",
                "sandbox_policy": {"type": "danger-full-access"},
                "model": "gpt-5",
                "summary": "auto",
            }
        )

        self.assertIsNone(item.network)
        self.assertIsNone(item.file_system_sandbox_policy)
        self.assertEqual(item.permission_profile(), PermissionProfile.disabled())
        self.assertEqual(item.to_mapping()["sandbox_policy"], {"type": "danger-full-access"})

    def test_turn_context_item_serializes_network_and_filesystem_policy(self):
        deny_env = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/.env"),
            FileSystemAccessMode.DENY,
        )
        fs_policy = FileSystemSandboxPolicy.restricted((deny_env,))
        item = TurnContextItem(
            cwd=Path("/repo"),
            approval_policy=AskForApproval.ON_REQUEST,
            sandbox_policy=SandboxPolicy.read_only(),
            model="gpt-5",
            network=TurnContextNetworkItem(("api.openai.com",), ("example.invalid",)),
            file_system_sandbox_policy=fs_policy,
        )

        payload = item.to_mapping()

        self.assertEqual(
            payload["network"],
            {"allowed_domains": ["api.openai.com"], "denied_domains": ["example.invalid"]},
        )
        self.assertEqual(payload["file_system_sandbox_policy"]["entries"][0]["access"], "deny")
        self.assertEqual(payload["file_system_sandbox_policy"]["entries"][0]["path"]["type"], "glob_pattern")
        self.assertEqual(TurnContextItem.from_mapping(payload).file_system_sandbox_policy, fs_policy)

    def test_turn_context_item_round_trips_granular_approval_policy(self):
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=True,
            request_permissions=False,
            mcp_elicitations=True,
        )
        item = TurnContextItem(
            cwd=Path("/repo"),
            approval_policy=granular,
            sandbox_policy=SandboxPolicy.read_only(),
            model="gpt-5",
        )

        payload = item.to_mapping()
        reparsed = TurnContextItem.from_mapping(payload)

        self.assertEqual(payload["approval_policy"], {"granular": granular.to_mapping()})
        self.assertEqual(reparsed.approval_policy, granular)

    def test_session_configured_event_deserializes_legacy_sandbox_policy(self):
        session_uuid = "11111111-1111-4111-8111-111111111111"
        payload = {
            "session_id": session_uuid,
            "model": "gpt-5",
            "model_provider_id": "openai",
            "approval_policy": "never",
            "sandbox_policy": {"type": "read-only", "network_access": False},
            "cwd": str(Path("/repo")),
        }

        configured = SessionConfiguredEvent.from_mapping(payload)
        msg = EventMsg.from_mapping({"type": "session_configured", **payload})

        self.assertEqual(configured.thread_id, ThreadId.from_string(session_uuid))
        self.assertEqual(configured.permission_profile, PermissionProfile.read_only())
        self.assertIsInstance(msg.payload, SessionConfiguredEvent)
        self.assertEqual(msg.payload.permission_profile, PermissionProfile.read_only())

    def test_session_configured_event_serializes_permission_profile(self):
        session_id = SessionId.from_string("22222222-2222-4222-8222-222222222222")
        configured = SessionConfiguredEvent(
            session_id=session_id,
            model="gpt-5",
            model_provider_id="openai",
            approval_policy=AskForApproval.ON_REQUEST,
            approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW,
            permission_profile=PermissionProfile.external(NetworkSandboxPolicy.ENABLED),
            cwd=Path("/repo"),
            network_proxy=SessionNetworkProxyRuntime("HTTPS_PROXY", "http://127.0.0.1:8080"),
            rollout_path=Path("/repo/rollout.jsonl"),
        )

        payload = configured.to_mapping()
        reparsed = SessionConfiguredEvent.from_mapping(payload)

        self.assertEqual(payload["thread_id"], session_id.to_json())
        self.assertIn("permission_profile", payload)
        self.assertNotIn("sandbox_policy", payload)
        self.assertEqual(payload["approvals_reviewer"], "guardian_subagent")
        self.assertEqual(payload["network_proxy"], {"env_var": "HTTPS_PROXY", "value": "http://127.0.0.1:8080"})
        self.assertEqual(reparsed.network_proxy, configured.network_proxy)
        self.assertEqual(reparsed.permission_profile, configured.permission_profile)

    def test_session_configured_event_round_trips_granular_approval_policy(self):
        session_id = SessionId.from_string("33333333-3333-4333-8333-333333333333")
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=True,
            request_permissions=True,
            mcp_elicitations=False,
        )
        configured = SessionConfiguredEvent(
            session_id=session_id,
            model="gpt-5",
            model_provider_id="openai",
            approval_policy=granular,
            permission_profile=PermissionProfile.read_only(),
            cwd=Path("/repo"),
        )

        payload = configured.to_mapping()
        msg = EventMsg.from_mapping({"type": "session_configured", **payload})

        self.assertEqual(payload["approval_policy"], {"granular": granular.to_mapping()})
        self.assertEqual(SessionConfiguredEvent.from_mapping(payload).approval_policy, granular)
        self.assertIsInstance(msg.payload, SessionConfiguredEvent)
        self.assertEqual(msg.payload.approval_policy, granular)

    def test_thread_settings_applied_event_parses_snapshot(self):
        cwd = Path("/repo")
        payload = {
            "type": "thread_settings_applied",
            "thread_settings": {
                "model": "gpt-5.2-codex",
                "model_provider_id": "openai",
                "service_tier": "priority",
                "approval_policy": "on-request",
                "approvals_reviewer": "guardian_subagent",
                "permission_profile": PermissionProfile.read_only().to_mapping(),
                "active_permission_profile": {"id": "dev", "extends": ":workspace"},
                "cwd": str(cwd),
                "reasoning_effort": "high",
                "reasoning_summary": "concise",
                "personality": "friendly",
                "collaboration_mode": {
                    "mode": "plan",
                    "settings": {
                        "model": "gpt-5.2-codex",
                        "reasoning_effort": "medium",
                        "developer_instructions": None,
                    },
                },
            },
        }

        msg = EventMsg.from_mapping(payload)
        snapshot = msg.payload.thread_settings

        self.assertEqual(snapshot.model, "gpt-5.2-codex")
        self.assertEqual(snapshot.approvals_reviewer, ApprovalsReviewer.AUTO_REVIEW)
        self.assertEqual(snapshot.active_permission_profile, ActivePermissionProfile("dev", ":workspace"))
        self.assertEqual(snapshot.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(snapshot.reasoning_summary, ReasoningSummary.CONCISE)
        self.assertEqual(snapshot.personality, Personality.FRIENDLY)
        self.assertEqual(
            snapshot.collaboration_mode,
            CollaborationMode(
                mode=ModeKind.PLAN,
                settings=Settings("gpt-5.2-codex", ReasoningEffort.MEDIUM, None),
            ),
        )
        self.assertEqual(msg.to_mapping(), payload)

    def test_thread_settings_snapshot_serializes_without_optional_fields(self):
        snapshot = ThreadSettingsSnapshot(
            model="gpt-5",
            model_provider_id="openai",
            approval_policy=AskForApproval.NEVER,
            approvals_reviewer=ApprovalsReviewer.USER,
            permission_profile=PermissionProfile.disabled(),
            cwd=Path("/repo"),
            collaboration_mode=CollaborationMode(
                mode=ModeKind.DEFAULT,
                settings=Settings("gpt-5", None, None),
            ),
        )
        event = ThreadSettingsAppliedEvent(snapshot)
        payload = event.to_mapping()["thread_settings"]

        self.assertNotIn("service_tier", payload)
        self.assertNotIn("active_permission_profile", payload)
        self.assertNotIn("reasoning_effort", payload)
        self.assertNotIn("reasoning_summary", payload)
        self.assertNotIn("personality", payload)
        self.assertEqual(
            payload["collaboration_mode"]["settings"],
            {"model": "gpt-5", "reasoning_effort": None, "developer_instructions": None},
        )
        self.assertEqual(ThreadSettingsAppliedEvent.from_mapping(event.to_mapping()), event)

    def test_thread_settings_round_trips_granular_approval_policy(self):
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=False,
            request_permissions=True,
            mcp_elicitations=False,
        )
        overrides = ThreadSettingsOverrides(approval_policy=granular)
        self.assertEqual(
            ThreadSettingsOverrides.from_mapping(overrides.to_mapping()).approval_policy,
            granular,
        )
        snapshot = ThreadSettingsSnapshot(
            model="gpt-5",
            model_provider_id="openai",
            approval_policy=granular,
            approvals_reviewer=ApprovalsReviewer.USER,
            permission_profile=PermissionProfile.disabled(),
            cwd=Path("/repo"),
            collaboration_mode=CollaborationMode(
                mode=ModeKind.DEFAULT,
                settings=Settings("gpt-5", None, None),
            ),
        )
        event = ThreadSettingsAppliedEvent(snapshot)
        payload = event.to_mapping()

        self.assertEqual(
            payload["thread_settings"]["approval_policy"],
            {"granular": granular.to_mapping()},
        )
        self.assertEqual(ThreadSettingsAppliedEvent.from_mapping(payload), event)

    def test_turn_aborted_and_review_mode_events_parse(self):
        aborted = EventMsg.from_mapping(
            {
                "type": "turn_aborted",
                "turn_id": "turn-1",
                "reason": "budget_limited",
                "completed_at": 123,
                "duration_ms": 456,
            }
        )
        entered = EventMsg.from_mapping(
            {
                "type": "entered_review_mode",
                "target": {"type": "baseBranch", "branch": "main"},
                "user_facing_hint": "review main",
            }
        )
        review_output = {
            "findings": [
                {
                    "title": "Bug",
                    "body": "Bad branch",
                    "confidence_score": 0.8,
                    "priority": 1,
                    "code_location": {
                        "absolute_file_path": str(Path("/repo/app.py")),
                        "line_range": {"start": 10, "end": 12},
                    },
                }
            ],
            "overall_correctness": "patch is incorrect",
            "overall_explanation": "because",
            "overall_confidence_score": 0.9,
        }
        exited = EventMsg.from_mapping({"type": "exited_review_mode", "review_output": review_output})
        shutdown = EventMsg.from_mapping({"type": "shutdown_complete"})

        self.assertEqual(aborted.payload, TurnAbortedEvent("turn-1", TurnAbortReason.BUDGET_LIMITED, 123, 456))
        self.assertEqual(aborted.to_mapping()["reason"], "budget_limited")
        self.assertEqual(entered.payload, ReviewRequest(ReviewTarget.base_branch("main"), "review main"))
        self.assertIsInstance(exited.payload, ExitedReviewModeEvent)
        self.assertEqual(exited.payload.review_output.findings[0].code_location.line_range, ReviewLineRange(10, 12))
        self.assertEqual(exited.to_mapping()["review_output"], review_output)
        self.assertEqual(shutdown.to_mapping(), {"type": "shutdown_complete"})

    def test_hook_lifecycle_events_parse_run_summary(self):
        run = {
            "id": "hook-1",
            "event_name": "pre_tool_use",
            "handler_type": "command",
            "execution_mode": "sync",
            "scope": "turn",
            "source_path": str(Path("/repo/.codex/hooks.toml")),
            "source": "project",
            "display_order": 2,
            "status": "completed",
            "status_message": None,
            "started_at": 100,
            "completed_at": 110,
            "duration_ms": 10,
            "entries": [{"kind": "warning", "text": "Careful"}],
        }

        started = EventMsg.from_mapping({"type": "hook_started", "turn_id": "turn-1", "run": run})
        completed = EventMsg.from_mapping({"type": "hook_completed", "turn_id": None, "run": run})

        self.assertEqual(
            started.payload.run,
            HookRunSummary(
                id="hook-1",
                event_name=HookEventName.PRE_TOOL_USE,
                handler_type=HookHandlerType.COMMAND,
                execution_mode=HookExecutionMode.SYNC,
                scope=HookScope.TURN,
                source_path=Path("/repo/.codex/hooks.toml"),
                source=HookSource.PROJECT,
                display_order=2,
                status=HookRunStatus.COMPLETED,
                status_message=None,
                started_at=100,
                completed_at=110,
                duration_ms=10,
                entries=(HookOutputEntry(HookOutputEntryKind.WARNING, "Careful"),),
            ),
        )
        self.assertIsInstance(started.payload, HookStartedEvent)
        self.assertIsInstance(completed.payload, HookCompletedEvent)
        self.assertEqual(started.to_mapping()["run"], run)

    def test_realtime_conversation_events_and_builtin_voices(self):
        builtin = RealtimeVoicesList.builtin()
        voices_payload = {
            "v1": ["juniper", "maple", "spruce", "ember", "vale", "breeze", "arbor", "sol", "cove"],
            "v2": ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "marin", "cedar"],
            "defaultV1": "cove",
            "defaultV2": "marin",
        }

        started = EventMsg.from_mapping(
            {"type": "realtime_conversation_started", "realtime_session_id": "conv_1", "version": "v2"}
        )
        realtime = EventMsg.from_mapping(
            {"type": "realtime_conversation_realtime", "payload": {"error": "connection closed"}}
        )
        closed = EventMsg.from_mapping({"type": "realtime_conversation_closed"})
        sdp = EventMsg.from_mapping({"type": "realtime_conversation_sdp", "sdp": "v=offer\r\n"})
        listed = EventMsg.from_mapping(
            {"type": "realtime_conversation_list_voices_response", "voices": voices_payload}
        )

        self.assertEqual(started.payload, RealtimeConversationStartedEvent("conv_1", RealtimeConversationVersion.V2))
        self.assertEqual(realtime.payload, RealtimeConversationRealtimeEvent({"error": "connection closed"}))
        self.assertEqual(closed.payload, RealtimeConversationClosedEvent())
        self.assertEqual(closed.to_mapping(), {"type": "realtime_conversation_closed"})
        self.assertEqual(sdp.payload, RealtimeConversationSdpEvent("v=offer\r\n"))
        self.assertEqual(listed.payload, RealtimeConversationListVoicesResponseEvent(builtin))
        self.assertEqual(builtin.to_mapping(), voices_payload)
        self.assertEqual(RealtimeVoice.COVE.wire_name(), "cove")

    def test_review_request_and_output_shapes(self):
        target = ReviewTarget.commit("abc123", title="Fix bug")
        request = ReviewRequest(target, user_facing_hint="review commit")
        finding = ReviewFinding(
            title="Bug",
            body="The branch can fail.",
            confidence_score=0.9,
            priority=1,
            code_location=ReviewCodeLocation(Path("/repo/app.py"), ReviewLineRange(10, 12)),
        )
        output = ReviewOutputEvent((finding,), "patch is incorrect", "because", 0.8)

        self.assertEqual(ReviewTarget.from_mapping(target.to_mapping()), target)
        self.assertEqual(request.to_mapping()["target"]["type"], "commit")
        self.assertEqual(output.findings[0].code_location.to_mapping()["absolute_file_path"], str(Path("/repo/app.py")))
        self.assertEqual(ReviewOutputEvent().overall_confidence_score, 0.0)

    def test_exec_command_events_and_base64_output_delta(self):
        begin = ExecCommandBeginEvent(
            call_id="call-1",
            process_id="pty-1",
            turn_id="turn-1",
            command=("git", "status"),
            cwd=Path("/repo"),
            parsed_cmd=({"cmd": "git"},),
            source=ExecCommandSource.UNIFIED_EXEC_STARTUP,
        )
        end = ExecCommandEndEvent(
            call_id="call-1",
            process_id="pty-1",
            turn_id="turn-1",
            command=("git", "status"),
            cwd=Path("/repo"),
            parsed_cmd=(),
            stdout="ok",
            stderr="",
            exit_code=0,
            duration={"secs": 0, "nanos": 42_000_000},
            formatted_output="ok",
            status=ExecCommandStatus.COMPLETED,
        )
        delta = ExecCommandOutputDeltaEvent("call21", ExecOutputStream.STDOUT, bytes([1, 2, 3, 4, 5]))

        self.assertEqual(begin.to_mapping()["source"], "unified_exec_startup")
        self.assertEqual(end.to_mapping()["aggregated_output"], "")
        self.assertEqual(delta.to_mapping(), {"call_id": "call21", "stream": "stdout", "chunk": "AQIDBAU="})
        self.assertEqual(ExecCommandOutputDeltaEvent.from_mapping(delta.to_mapping()), delta)

    def test_event_msg_parses_exec_command_payloads(self):
        msg = EventMsg.from_mapping(
            {
                "type": "exec_command_begin",
                "call_id": "call-1",
                "turn_id": "turn-1",
                "command": ["git", "status"],
                "cwd": "/repo",
                "parsed_cmd": [],
                "source": "user_shell",
            }
        )

        self.assertEqual(msg.payload, ExecCommandBeginEvent("call-1", "turn-1", ("git", "status"), Path("/repo"), source=ExecCommandSource.USER_SHELL))
        self.assertEqual(msg.to_mapping()["source"], "user_shell")

    def test_patch_apply_events_reuse_file_change_shapes(self):
        changes = {Path("new.txt"): FileChange.add("hello")}
        begin = PatchApplyBeginEvent("patch-1", True, changes, turn_id="turn-1")
        end = PatchApplyEndEvent(
            call_id="patch-1",
            turn_id="turn-1",
            stdout="Done!",
            stderr="",
            success=True,
            changes=changes,
            status=PatchApplyStatus.COMPLETED,
        )

        self.assertEqual(begin.to_mapping()["changes"]["new.txt"]["type"], "add")
        self.assertEqual(begin.to_mapping()["changes"]["new.txt"]["content"], "hello")
        self.assertEqual(end.to_mapping()["status"], "completed")

        parsed = EventMsg.from_mapping(
            {
                "type": "patch_apply_end",
                "call_id": "patch-1",
                "turn_id": "turn-1",
                "stdout": "Done!",
                "stderr": "",
                "success": True,
                "changes": {"new.txt": {"type": "add", "content": "hello"}},
                "status": "completed",
            }
        )
        self.assertEqual(parsed.payload, end)

    def test_mcp_tool_call_events_and_success_logic(self):
        invocation = McpInvocation("server", "tool", {"arg": "value"})
        begin = McpToolCallBeginEvent("mcp-1", invocation, mcp_app_resource_uri="app://connector", plugin_id="sample@test")
        ok_result = CallToolResult(content=({"type": "text", "text": "ok"},), is_error=False)
        err_result = CallToolResult(content=({"type": "text", "text": "bad"},), is_error=True)

        self.assertEqual(begin.to_mapping()["invocation"]["arguments"], {"arg": "value"})
        self.assertTrue(McpToolCallEndEvent("mcp-1", invocation, {"secs": 0, "nanos": 42_000_000}, ok_result).is_success())
        self.assertFalse(McpToolCallEndEvent("mcp-1", invocation, {"secs": 0, "nanos": 42_000_000}, err_result).is_success())
        self.assertFalse(McpToolCallEndEvent("mcp-1", invocation, {"secs": 0, "nanos": 42_000_000}, "boom").is_success())

        msg = EventMsg.from_mapping(
            {
                "type": "mcp_tool_call_end",
                "call_id": "mcp-1",
                "invocation": {"server": "server", "tool": "tool", "arguments": {"arg": "value"}},
                "duration": {"secs": 0, "nanos": 42_000_000},
                "result": {"Ok": ok_result.to_mapping()},
            }
        )
        self.assertTrue(msg.payload.is_success())
        self.assertEqual(msg.to_mapping()["result"]["Ok"]["isError"], False)

    def test_mcp_startup_events_and_auth_status_display(self):
        update = Event(
            "init",
            EventMsg.with_payload("mcp_startup_update", McpStartupUpdateEvent("srv", McpStartupStatus.failed("boom"))),
        )
        complete = Event(
            "init",
            EventMsg.with_payload(
                "mcp_startup_complete",
                McpStartupCompleteEvent(ready=("a",), failed=(McpStartupFailure("b", "bad"),), cancelled=("c",)),
            ),
        )

        self.assertEqual(update.to_mapping()["msg"]["status"]["state"], "failed")
        self.assertEqual(update.to_mapping()["msg"]["status"]["error"], "boom")
        self.assertEqual(complete.to_mapping()["msg"]["failed"][0]["server"], "b")
        self.assertEqual(str(McpAuthStatus.NOT_LOGGED_IN), "Not logged in")
        self.assertEqual(McpStartupStatus.from_mapping({"state": "ready"}), McpStartupStatus.ready())


if __name__ == "__main__":
    unittest.main()
