import unittest

from pycodex.core import (
    CODEX_APPS_MCP_SERVER_NAME,
    MCP_IMAGE_CONTENT_OMITTED_TEXT,
    MCP_TOOL_CALL_EVENT_RESULT_MAX_BYTES,
    MCP_TOOL_CODEX_APPS_META_KEY,
    MCP_TOOL_PLUGIN_ID_META_KEY,
    MCP_TOOL_THREAD_ID_META_KEY,
    MCP_TOOL_UI_RESOURCE_URI_META_KEY,
    MCP_TOOL_OPENAI_OUTPUT_TEMPLATE_META_KEY,
    MCP_TOOL_OPENAI_FILE_PARAMS_META_KEY,
    MCP_TOOL_APPROVAL_ACCEPT,
    MCP_TOOL_APPROVAL_ACCEPT_AND_REMEMBER,
    MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION,
    MCP_TOOL_APPROVAL_CANCEL,
    MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC,
    MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX,
    MCP_TOOL_APPROVAL_PERSIST_VALUE,
    MCP_ELICITATION_DECLINE_MESSAGE_KEY,
    ApprovalStore,
    AppToolApproval,
    ElicitationResponse,
    GuardianElicitationReview,
    GuardianElicitationReviewKind,
    GuardianMcpAnnotations,
    GuardianMcpToolReviewRequest,
    MCP_CALL_COUNT_METRIC,
    MCP_CALL_DURATION_METRIC,
    McpAppInvocation,
    McpAppInvocationType,
    McpAppUsageMetadata,
    MCP_RESULT_TELEMETRY_DID_TRIGGER_SERVER_USER_FLOW_KEY,
    MCP_RESULT_TELEMETRY_META_KEY,
    MCP_RESULT_TELEMETRY_SERVER_USER_FLOW_SPAN_ATTR,
    MCP_RESULT_TELEMETRY_SPAN_KEY,
    MCP_RESULT_TELEMETRY_TARGET_ID_KEY,
    MCP_RESULT_TELEMETRY_TARGET_ID_MAX_CHARS,
    MCP_RESULT_TELEMETRY_TARGET_ID_SPAN_ATTR,
    McpInvocation,
    McpServerApprovalConfig,
    McpServerToolConfig,
    McpToolApprovalConfigEdit,
    McpToolApprovalDecision,
    McpToolApprovalKey,
    McpToolApprovalMetadata,
    RenderedMcpToolApprovalParam,
    ToolAnnotations,
    ToolInfo,
    apply_mcp_tool_approval_decision,
    build_guardian_mcp_tool_review_request,
    build_mcp_app_used_invocation,
    build_mcp_tool_approval_display_params,
    build_mcp_tool_approval_elicitation_meta,
    build_mcp_tool_approval_question,
    build_mcp_tool_call_request_meta,
    codex_app_tool_approval_config_edit,
    codex_apps_meta_from_tool_meta,
    custom_mcp_tool_approval_config_edit,
    custom_mcp_tool_approval_mode,
    custom_mcp_tool_approval_mode_from_config,
    declared_openai_file_input_param_names,
    get_mcp_app_resource_uri,
    guardian_elicitation_review_request,
    guardian_rejection_message,
    guardian_timeout_message,
    is_mcp_tool_approval_question_id,
    lookup_mcp_app_usage_metadata,
    lookup_mcp_tool_metadata,
    mcp_app_invocation_type,
    mcp_call_metric_tags,
    mcp_elicitation_auto_meta,
    mcp_elicitation_decline_without_message,
    mcp_elicitation_request_id,
    mcp_elicitation_response_from_guardian_decision_parts,
    mcp_result_span_telemetry_attributes,
    mcp_tool_approval_config_edit_for_key,
    mcp_tool_approval_decision_from_guardian,
    mcp_tool_approval_is_remembered,
    mcp_tool_approval_prompt_options,
    normalize_approval_decision_for_mode,
    openai_file_input_params_for_server,
    parse_mcp_tool_approval_elicitation_response,
    parse_mcp_tool_approval_response,
    persistent_mcp_tool_approval_key,
    plugin_mcp_tool_approval_config_edit,
    remember_mcp_tool_approval,
    requires_mcp_tool_approval,
    sanitize_metric_tag_value,
    sanitize_mcp_tool_result_for_model,
    session_mcp_tool_approval_key,
    truncate_str_to_char_boundary,
    truncate_mcp_tool_result_for_event,
    with_mcp_tool_call_thread_id_meta,
    X_CODEX_TURN_METADATA_HEADER,
)
from pycodex.protocol import (
    ApprovalsReviewer,
    CallToolResult,
    ElicitationAction,
    ElicitationRequest,
    ElicitationRequestEvent,
    ReviewDecision,
    Tool,
)
from pycodex.protocol.mcp_approval_meta import (
    APPROVALS_REVIEWER_KEY,
    APPROVAL_KIND_KEY,
    APPROVAL_KIND_MCP_TOOL_CALL,
    CONNECTOR_DESCRIPTION_KEY,
    CONNECTOR_ID_KEY,
    CONNECTOR_NAME_KEY,
    PERSIST_ALWAYS,
    PERSIST_KEY,
    PERSIST_SESSION,
    REQUEST_TYPE_APPROVAL_REQUEST,
    REQUEST_TYPE_KEY,
    SOURCE_CONNECTOR,
    SOURCE_KEY,
    TOOL_DESCRIPTION_KEY,
    TOOL_NAME_KEY,
    TOOL_PARAMS_DISPLAY_KEY,
    TOOL_PARAMS_KEY,
    TOOL_TITLE_KEY,
)
from pycodex.protocol.request_user_input import (
    RequestUserInputAnswer,
    RequestUserInputResponse,
)


class McpToolCallPolicyTests(unittest.TestCase):
    def test_mcp_app_resource_uri_reads_known_tool_meta_keys(self) -> None:
        self.assertEqual(
            get_mcp_app_resource_uri({"ui": {"resourceUri": "ui://widget/nested.html"}}),
            "ui://widget/nested.html",
        )
        self.assertEqual(
            get_mcp_app_resource_uri(
                {MCP_TOOL_UI_RESOURCE_URI_META_KEY: "ui://widget/flat.html"}
            ),
            "ui://widget/flat.html",
        )
        self.assertEqual(
            get_mcp_app_resource_uri(
                {MCP_TOOL_OPENAI_OUTPUT_TEMPLATE_META_KEY: "ui://widget/output-template.html"}
            ),
            "ui://widget/output-template.html",
        )
        self.assertIsNone(get_mcp_app_resource_uri({"ui": {"resourceUri": 3}}))

    def test_openai_file_params_are_only_honored_for_codex_apps(self) -> None:
        meta = {MCP_TOOL_OPENAI_FILE_PARAMS_META_KEY: ["file", "", 7, "attachments"]}

        self.assertEqual(
            declared_openai_file_input_param_names(meta),
            ("file", "attachments"),
        )
        self.assertEqual(
            openai_file_input_params_for_server(CODEX_APPS_MCP_SERVER_NAME, meta),
            ("file", "attachments"),
        )
        self.assertIsNone(openai_file_input_params_for_server("minimaltest", meta))
        self.assertIsNone(
            openai_file_input_params_for_server(
                CODEX_APPS_MCP_SERVER_NAME,
                {MCP_TOOL_OPENAI_FILE_PARAMS_META_KEY: []},
            )
        )

    def test_codex_apps_meta_from_tool_meta_reads_object_only(self) -> None:
        self.assertEqual(
            codex_apps_meta_from_tool_meta(
                {MCP_TOOL_CODEX_APPS_META_KEY: {"connector_id": "calendar"}}
            ),
            {"connector_id": "calendar"},
        )
        self.assertIsNone(codex_apps_meta_from_tool_meta({MCP_TOOL_CODEX_APPS_META_KEY: "bad"}))

    def test_mcp_tool_call_request_meta_includes_turn_metadata_for_custom_server(self) -> None:
        turn_metadata = {"model": "gpt-5", "reasoning_effort": "low"}

        self.assertEqual(
            build_mcp_tool_call_request_meta(
                "custom_server",
                "call-custom",
                turn_metadata=turn_metadata,
            ),
            {X_CODEX_TURN_METADATA_HEADER: turn_metadata},
        )

    def test_plugin_mcp_tool_call_request_meta_includes_plugin_id(self) -> None:
        metadata = McpToolApprovalMetadata(plugin_id="sample@test")
        turn_metadata = {"model": "gpt-5"}

        self.assertEqual(
            build_mcp_tool_call_request_meta(
                "sample",
                "call-plugin",
                metadata,
                turn_metadata,
            ),
            {
                X_CODEX_TURN_METADATA_HEADER: turn_metadata,
                MCP_TOOL_PLUGIN_ID_META_KEY: "sample@test",
            },
        )

    def test_codex_apps_tool_call_request_meta_includes_call_id_and_existing_meta(self) -> None:
        metadata = McpToolApprovalMetadata(
            codex_apps_meta={
                "resource_uri": "connector://calendar/tools/calendar_create_event",
                "contains_mcp_source": True,
                "connector_id": "calendar",
            }
        )
        turn_metadata = {"model": "gpt-5"}

        self.assertEqual(
            build_mcp_tool_call_request_meta(
                CODEX_APPS_MCP_SERVER_NAME,
                "call_abc123xyz789",
                metadata,
                turn_metadata,
            ),
            {
                X_CODEX_TURN_METADATA_HEADER: turn_metadata,
                MCP_TOOL_CODEX_APPS_META_KEY: {
                    "call_id": "call_abc123xyz789",
                    "resource_uri": "connector://calendar/tools/calendar_create_event",
                    "contains_mcp_source": True,
                    "connector_id": "calendar",
                },
            },
        )

    def test_codex_apps_tool_call_request_meta_includes_call_id_without_existing_meta(self) -> None:
        self.assertEqual(
            build_mcp_tool_call_request_meta(
                CODEX_APPS_MCP_SERVER_NAME,
                "call_abc123xyz789",
            ),
            {MCP_TOOL_CODEX_APPS_META_KEY: {"call_id": "call_abc123xyz789"}},
        )

    def test_mcp_tool_approval_metadata_rejects_non_rust_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "connector_id must be a string or None"):
            McpToolApprovalMetadata(connector_id=123)

        with self.assertRaisesRegex(TypeError, "codex_apps_meta must be a mapping or None"):
            McpToolApprovalMetadata(codex_apps_meta="meta")

        with self.assertRaisesRegex(TypeError, "openai_file_input_params must be a list or tuple of strings"):
            McpToolApprovalMetadata(openai_file_input_params="file")

        with self.assertRaisesRegex(TypeError, "openai_file_input_params entries must be strings"):
            McpToolApprovalMetadata(openai_file_input_params=("file", 123))

    def test_mcp_tool_approval_key_rejects_non_rust_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "server must be a string"):
            McpToolApprovalKey(123, None, "tool")

        with self.assertRaisesRegex(TypeError, "connector_id must be a string or None"):
            McpToolApprovalKey("server", 123, "tool")

        with self.assertRaisesRegex(TypeError, "tool_name must be a string"):
            McpToolApprovalKey("server", None, 123)

    def test_mcp_app_metadata_rejects_non_rust_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "connector_id must be a string or None"):
            McpAppUsageMetadata(connector_id=123)

        with self.assertRaisesRegex(TypeError, "app_name must be a string or None"):
            McpAppUsageMetadata(app_name=123)

        with self.assertRaisesRegex(TypeError, "connector_id must be a string or None"):
            McpAppInvocation(connector_id=123)

        with self.assertRaisesRegex(TypeError, "app_name must be a string or None"):
            McpAppInvocation(app_name=123)

    def test_mcp_tool_approval_decision_and_display_param_reject_non_rust_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "message must be a string or None"):
            McpToolApprovalDecision.decline(123)

        with self.assertRaisesRegex(TypeError, "name must be a string"):
            RenderedMcpToolApprovalParam(123, "value", "Name")

        with self.assertRaisesRegex(TypeError, "display_name must be a string"):
            RenderedMcpToolApprovalParam("name", "value", 123)

    def test_guardian_mcp_review_request_includes_invocation_metadata(self) -> None:
        invocation = McpInvocation(
            server=CODEX_APPS_MCP_SERVER_NAME,
            tool="browser_navigate",
            arguments={"url": "https://example.com"},
        )
        metadata = McpToolApprovalMetadata(
            connector_id="playwright",
            connector_name="Playwright",
            connector_description="Browser automation",
            tool_title="Navigate",
            tool_description="Open a page",
        )

        self.assertEqual(
            build_guardian_mcp_tool_review_request("call-1", invocation, metadata),
            GuardianMcpToolReviewRequest(
                id="call-1",
                server=CODEX_APPS_MCP_SERVER_NAME,
                tool_name="browser_navigate",
                arguments={"url": "https://example.com"},
                connector_id="playwright",
                connector_name="Playwright",
                connector_description="Browser automation",
                tool_title="Navigate",
                tool_description="Open a page",
            ),
        )

    def test_guardian_mcp_review_request_includes_annotations_when_present(self) -> None:
        invocation = McpInvocation(server="custom_server", tool="dangerous_tool")
        metadata = McpToolApprovalMetadata(
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,
                open_world_hint=True,
            )
        )

        request = build_guardian_mcp_tool_review_request(
            "call-1",
            invocation,
            metadata,
        )

        self.assertEqual(
            request,
            GuardianMcpToolReviewRequest(
                id="call-1",
                server="custom_server",
                tool_name="dangerous_tool",
                annotations=GuardianMcpAnnotations(
                    destructive_hint=True,
                    open_world_hint=True,
                    read_only_hint=False,
                ),
            ),
        )
        self.assertEqual(
            request.to_mapping()["annotations"],
            {
                "destructive_hint": True,
                "open_world_hint": True,
                "read_only_hint": False,
            },
        )

    def test_guardian_review_decision_maps_to_mcp_tool_decision(self) -> None:
        self.assertEqual(
            mcp_tool_approval_decision_from_guardian(ReviewDecision.approved()),
            McpToolApprovalDecision.accept(),
        )
        self.assertEqual(
            mcp_tool_approval_decision_from_guardian(ReviewDecision.approved_for_session()),
            McpToolApprovalDecision.accept_for_session(),
        )
        denial = mcp_tool_approval_decision_from_guardian(
            ReviewDecision.denied(),
            rejection_rationale="too risky",
        )
        self.assertEqual(
            denial,
            McpToolApprovalDecision.decline(guardian_rejection_message("too risky")),
        )
        self.assertIn("Reason: too risky", denial.message or "")
        self.assertIn(
            "The agent must not attempt to achieve the same outcome",
            denial.message or "",
        )
        timeout = mcp_tool_approval_decision_from_guardian(ReviewDecision.timed_out())
        self.assertEqual(
            timeout,
            McpToolApprovalDecision.decline(guardian_timeout_message()),
        )
        self.assertIn("did not finish before its deadline", timeout.message or "")
        self.assertNotIn("unacceptable risk", timeout.message or "")
        self.assertEqual(
            mcp_tool_approval_decision_from_guardian(ReviewDecision.abort()),
            McpToolApprovalDecision.decline(),
        )

    def test_guardian_elicitation_review_request_builds_mcp_tool_call(self) -> None:
        request = ElicitationRequestEvent(
            "browser-use",
            7,
            ElicitationRequest.form(
                "Allow origin?",
                {"type": "object", "properties": {}},
                meta={
                    APPROVAL_KIND_KEY: APPROVAL_KIND_MCP_TOOL_CALL,
                    REQUEST_TYPE_KEY: REQUEST_TYPE_APPROVAL_REQUEST,
                    CONNECTOR_ID_KEY: "browser-use",
                    CONNECTOR_NAME_KEY: "Browser Use",
                    TOOL_NAME_KEY: "access_browser_origin",
                    TOOL_TITLE_KEY: "Access browser origin",
                    TOOL_PARAMS_KEY: {"origin": "https://example.com"},
                },
            ),
        )

        review = guardian_elicitation_review_request(request)

        self.assertEqual(review.kind, GuardianElicitationReviewKind.APPROVAL_REQUEST)
        self.assertEqual(
            review.approval_request,
            GuardianMcpToolReviewRequest(
                id="mcp_elicitation:browser-use:7",
                server="browser-use",
                tool_name="access_browser_origin",
                arguments={"origin": "https://example.com"},
                connector_id="browser-use",
                connector_name="Browser Use",
                tool_title="Access browser origin",
            ),
        )

    def test_guardian_elicitation_review_request_defaults_missing_tool_params(self) -> None:
        request = ElicitationRequestEvent(
            "browser-use",
            "request-1",
            ElicitationRequest.form(
                "Allow origin?",
                {"type": "object", "properties": {}},
                meta={
                    APPROVAL_KIND_KEY: APPROVAL_KIND_MCP_TOOL_CALL,
                    REQUEST_TYPE_KEY: REQUEST_TYPE_APPROVAL_REQUEST,
                    TOOL_NAME_KEY: "access_browser_origin",
                },
            ),
        )

        review = guardian_elicitation_review_request(request)

        self.assertEqual(mcp_elicitation_request_id(request.id), "request-1")
        self.assertEqual(review.kind, GuardianElicitationReviewKind.APPROVAL_REQUEST)
        self.assertEqual(review.approval_request.arguments, {})

    def test_guardian_elicitation_review_request_declines_invalid_metadata(self) -> None:
        approval_meta = {
            APPROVAL_KIND_KEY: APPROVAL_KIND_MCP_TOOL_CALL,
            REQUEST_TYPE_KEY: REQUEST_TYPE_APPROVAL_REQUEST,
            TOOL_NAME_KEY: "access_browser_origin",
        }

        self.assertEqual(
            guardian_elicitation_review_request(
                ElicitationRequestEvent(
                    "browser-use",
                    7,
                    ElicitationRequest.url(
                        "Open",
                        "https://example.com",
                        "elicit-1",
                        meta=approval_meta,
                    ),
                )
            ).kind,
            GuardianElicitationReviewKind.DECLINE,
        )
        self.assertEqual(
            guardian_elicitation_review_request(
                ElicitationRequestEvent(
                    "browser-use",
                    7,
                    ElicitationRequest.form(
                        "Allow?",
                        {"type": "object", "properties": {"origin": {"type": "string"}}},
                        meta=approval_meta,
                    ),
                )
            ).kind,
            GuardianElicitationReviewKind.DECLINE,
        )
        self.assertEqual(
            guardian_elicitation_review_request(
                ElicitationRequestEvent(
                    "browser-use",
                    7,
                    ElicitationRequest.form(
                        "Allow?",
                        {"type": "object", "properties": {}},
                        meta={**approval_meta, TOOL_PARAMS_KEY: ["not", "object"]},
                    ),
                )
            ).kind,
            GuardianElicitationReviewKind.DECLINE,
        )
        self.assertEqual(
            guardian_elicitation_review_request(
                ElicitationRequestEvent(
                    "browser-use",
                    7,
                    ElicitationRequest.form(
                        "Allow?",
                        {"type": "object", "properties": {}},
                        meta={REQUEST_TYPE_KEY: REQUEST_TYPE_APPROVAL_REQUEST},
                    ),
                )
            ).kind,
            GuardianElicitationReviewKind.DECLINE,
        )

    def test_guardian_elicitation_review_request_ignores_unrelated_requests(self) -> None:
        self.assertEqual(
            guardian_elicitation_review_request(
                ElicitationRequestEvent(
                    "browser-use",
                    7,
                    ElicitationRequest.form("Fill", {"type": "object"}, meta=None),
                )
            ),
            GuardianElicitationReview.not_requested(),
        )

    def test_guardian_decisions_map_to_elicitation_responses(self) -> None:
        self.assertEqual(
            mcp_elicitation_response_from_guardian_decision_parts(
                ReviewDecision.approved()
            ),
            ElicitationResponse(
                action=ElicitationAction.ACCEPT,
                content={},
                meta={APPROVALS_REVIEWER_KEY: ApprovalsReviewer.AUTO_REVIEW.value},
            ),
        )
        self.assertEqual(
            mcp_elicitation_response_from_guardian_decision_parts(
                ReviewDecision.denied(),
                "Denied by Guardian",
            ),
            ElicitationResponse(
                action=ElicitationAction.DECLINE,
                meta={
                    APPROVALS_REVIEWER_KEY: ApprovalsReviewer.AUTO_REVIEW.value,
                    MCP_ELICITATION_DECLINE_MESSAGE_KEY: "Denied by Guardian",
                },
            ),
        )
        self.assertEqual(
            mcp_elicitation_response_from_guardian_decision_parts(
                ReviewDecision.timed_out()
            ),
            ElicitationResponse(
                action=ElicitationAction.DECLINE,
                meta={
                    APPROVALS_REVIEWER_KEY: ApprovalsReviewer.AUTO_REVIEW.value,
                    MCP_ELICITATION_DECLINE_MESSAGE_KEY: guardian_timeout_message(),
                },
            ),
        )
        self.assertEqual(
            mcp_elicitation_response_from_guardian_decision_parts(ReviewDecision.abort()),
            ElicitationResponse(
                action=ElicitationAction.CANCEL,
                meta=mcp_elicitation_auto_meta(),
            ),
        )
        self.assertEqual(
            mcp_elicitation_decline_without_message(),
            ElicitationResponse(
                action=ElicitationAction.DECLINE,
                meta=mcp_elicitation_auto_meta(),
            ),
        )

    def test_mcp_tool_call_thread_id_meta_is_added_to_request_meta(self) -> None:
        self.assertEqual(
            with_mcp_tool_call_thread_id_meta(
                {"source": "test-client", MCP_TOOL_THREAD_ID_META_KEY: "stale-thread"},
                "thread-live",
            ),
            {"source": "test-client", MCP_TOOL_THREAD_ID_META_KEY: "thread-live"},
        )
        self.assertEqual(
            with_mcp_tool_call_thread_id_meta(None, "thread-live"),
            {MCP_TOOL_THREAD_ID_META_KEY: "thread-live"},
        )
        self.assertEqual(
            with_mcp_tool_call_thread_id_meta("invalid-meta", "thread-live"),
            "invalid-meta",
        )

    def test_lookup_mcp_tool_metadata_preserves_tool_and_connector_fields(self) -> None:
        info = ToolInfo(
            server_name=CODEX_APPS_MCP_SERVER_NAME,
            callable_namespace="mcp__browser__",
            callable_name="browser_navigate",
            connector_id="playwright",
            connector_name="Playwright",
            tool=Tool(
                name="browser_navigate",
                title="Navigate",
                description="Open a page",
                input_schema={"type": "object"},
                annotations={"readOnlyHint": False, "openWorldHint": True},
                meta={
                    "ui": {"resourceUri": "ui://browser/navigate.html"},
                    MCP_TOOL_CODEX_APPS_META_KEY: {
                        "resource_uri": "connector://browser/tools/navigate"
                    },
                    MCP_TOOL_OPENAI_FILE_PARAMS_META_KEY: ["file", 7, "attachments"],
                },
            ),
        )

        metadata = lookup_mcp_tool_metadata(
            [info],
            CODEX_APPS_MCP_SERVER_NAME,
            "browser_navigate",
            plugin_id="browser@test",
            accessible_connectors=(
                {"id": "playwright", "description": "Browser automation"},
            ),
        )

        self.assertEqual(
            metadata,
            McpToolApprovalMetadata(
                annotations=ToolAnnotations(
                    read_only_hint=False,
                    open_world_hint=True,
                ),
                connector_id="playwright",
                connector_name="Playwright",
                connector_description="Browser automation",
                plugin_id="browser@test",
                tool_title="Navigate",
                tool_description="Open a page",
                mcp_app_resource_uri="ui://browser/navigate.html",
                codex_apps_meta={"resource_uri": "connector://browser/tools/navigate"},
                openai_file_input_params=("file", "attachments"),
            ),
        )

    def test_lookup_mcp_tool_metadata_uses_tool_name_not_callable_name(self) -> None:
        info = ToolInfo(
            server_name="docs",
            callable_namespace="mcp__docs__",
            callable_name="search_docs",
            tool=Tool(
                name="search",
                description="Search docs",
                input_schema={"type": "object"},
            ),
        )

        self.assertIsNone(lookup_mcp_tool_metadata([info], "docs", "search_docs"))
        self.assertEqual(
            lookup_mcp_tool_metadata([info], "docs", "search"),
            McpToolApprovalMetadata(tool_description="Search docs"),
        )

    def test_lookup_mcp_tool_metadata_disallows_file_params_for_custom_servers(self) -> None:
        info = ToolInfo(
            server_name="docs",
            callable_namespace="mcp__docs__",
            callable_name="search",
            connector_id="ignored",
            connector_name="Ignored",
            tool=Tool(
                name="search",
                input_schema={"type": "object"},
                meta={
                    MCP_TOOL_OPENAI_FILE_PARAMS_META_KEY: ["file"],
                    MCP_TOOL_OPENAI_OUTPUT_TEMPLATE_META_KEY: "ui://docs/search.html",
                },
            ),
        )

        metadata = lookup_mcp_tool_metadata(
            [info],
            "docs",
            "search",
            accessible_connectors=({"id": "ignored", "description": "Nope"},),
        )

        self.assertEqual(metadata.connector_id, "ignored")
        self.assertIsNone(metadata.connector_description)
        self.assertIsNone(metadata.openai_file_input_params)
        self.assertEqual(metadata.mcp_app_resource_uri, "ui://docs/search.html")

    def test_lookup_mcp_app_usage_metadata_uses_connector_fields(self) -> None:
        info = ToolInfo(
            server_name=CODEX_APPS_MCP_SERVER_NAME,
            callable_namespace="mcp__calendar__",
            callable_name="list_events",
            connector_id="calendar",
            connector_name="Calendar",
            tool=Tool(
                name="calendar/list_events",
                input_schema={"type": "object"},
            ),
        )

        self.assertEqual(
            lookup_mcp_app_usage_metadata(
                [info],
                CODEX_APPS_MCP_SERVER_NAME,
                "calendar/list_events",
            ),
            McpAppUsageMetadata(connector_id="calendar", app_name="Calendar"),
        )
        self.assertIsNone(
            lookup_mcp_app_usage_metadata(
                [info],
                CODEX_APPS_MCP_SERVER_NAME,
                "list_events",
            )
        )

    def test_mcp_app_invocation_type_uses_mentioned_connector_ids(self) -> None:
        self.assertEqual(
            mcp_app_invocation_type("calendar", ("gmail", "calendar")),
            McpAppInvocationType.EXPLICIT,
        )
        self.assertEqual(
            mcp_app_invocation_type("calendar", ("gmail",)),
            McpAppInvocationType.IMPLICIT,
        )
        self.assertEqual(
            mcp_app_invocation_type(None, ("calendar",)),
            McpAppInvocationType.IMPLICIT,
        )

    def test_build_mcp_app_used_invocation_only_tracks_codex_apps_server(self) -> None:
        info = ToolInfo(
            server_name=CODEX_APPS_MCP_SERVER_NAME,
            callable_namespace="mcp__calendar__",
            callable_name="list_events",
            connector_id="calendar",
            connector_name="Calendar",
            tool=Tool(
                name="calendar/list_events",
                input_schema={"type": "object"},
            ),
        )

        self.assertEqual(
            build_mcp_app_used_invocation(
                [info],
                CODEX_APPS_MCP_SERVER_NAME,
                "calendar/list_events",
                mentioned_connector_ids=("calendar",),
            ),
            McpAppInvocation(
                connector_id="calendar",
                app_name="Calendar",
                invocation_type=McpAppInvocationType.EXPLICIT,
            ),
        )
        self.assertEqual(
            build_mcp_app_used_invocation(
                [],
                CODEX_APPS_MCP_SERVER_NAME,
                "missing_tool",
            ),
            McpAppInvocation(invocation_type=McpAppInvocationType.IMPLICIT),
        )
        self.assertIsNone(
            build_mcp_app_used_invocation([info], "custom_server", "calendar/list_events")
        )

    def test_mcp_metric_names_match_upstream(self) -> None:
        self.assertEqual(MCP_CALL_COUNT_METRIC, "codex.mcp.call")
        self.assertEqual(MCP_CALL_DURATION_METRIC, "codex.mcp.call.duration_ms")

    def test_sanitize_metric_tag_value_matches_upstream_rules(self) -> None:
        self.assertEqual(sanitize_metric_tag_value("bad value!"), "bad_value")
        self.assertEqual(sanitize_metric_tag_value("___good/value___"), "good/value")
        self.assertEqual(sanitize_metric_tag_value("///"), "unspecified")
        self.assertEqual(sanitize_metric_tag_value("x" * 300), "x" * 256)

    def test_mcp_call_metric_tags_sanitize_and_skip_empty_connector_tags(self) -> None:
        self.assertEqual(
            mcp_call_metric_tags(
                "ok!",
                "calendar/list events",
                connector_id="",
                connector_name="Calendar App",
            ),
            (
                ("status", "ok"),
                ("tool", "calendar/list_events"),
                ("connector_name", "Calendar_App"),
            ),
        )

    def test_mcp_result_span_telemetry_attributes_promote_allowlisted_values(self) -> None:
        result = CallToolResult(
            content=(),
            meta={
                MCP_RESULT_TELEMETRY_META_KEY: {
                    MCP_RESULT_TELEMETRY_SPAN_KEY: {
                        MCP_RESULT_TELEMETRY_TARGET_ID_KEY: "com.apple.reminders",
                        MCP_RESULT_TELEMETRY_DID_TRIGGER_SERVER_USER_FLOW_KEY: False,
                        "not_promoted_sentinel_key": "not_promoted_sentinel_value",
                    }
                }
            },
        )

        self.assertEqual(
            mcp_result_span_telemetry_attributes(result),
            {
                MCP_RESULT_TELEMETRY_TARGET_ID_SPAN_ATTR: "com.apple.reminders",
                MCP_RESULT_TELEMETRY_SERVER_USER_FLOW_SPAN_ATTR: False,
            },
        )

    def test_mcp_result_span_telemetry_attributes_ignore_invalid_or_missing_values(self) -> None:
        invalid = CallToolResult(
            content=(),
            meta={
                MCP_RESULT_TELEMETRY_META_KEY: {
                    MCP_RESULT_TELEMETRY_SPAN_KEY: {
                        MCP_RESULT_TELEMETRY_TARGET_ID_KEY: 123,
                        MCP_RESULT_TELEMETRY_DID_TRIGGER_SERVER_USER_FLOW_KEY: "false",
                    }
                }
            },
        )

        self.assertEqual(mcp_result_span_telemetry_attributes(invalid), {})
        self.assertEqual(
            mcp_result_span_telemetry_attributes(
                CallToolResult(
                    content=(),
                    meta={MCP_RESULT_TELEMETRY_META_KEY: {}},
                )
            ),
            {},
        )
        self.assertEqual(mcp_result_span_telemetry_attributes(None), {})

    def test_mcp_result_span_telemetry_truncates_target_id_on_char_boundary(self) -> None:
        truncated = "\u00e1" * MCP_RESULT_TELEMETRY_TARGET_ID_MAX_CHARS
        result = CallToolResult(
            content=(),
            meta={
                MCP_RESULT_TELEMETRY_META_KEY: {
                    MCP_RESULT_TELEMETRY_SPAN_KEY: {
                        MCP_RESULT_TELEMETRY_TARGET_ID_KEY: f"{truncated}tail",
                    }
                }
            },
        )

        self.assertEqual(
            mcp_result_span_telemetry_attributes(result),
            {MCP_RESULT_TELEMETRY_TARGET_ID_SPAN_ATTR: truncated},
        )
        self.assertEqual(
            truncate_str_to_char_boundary("short", MCP_RESULT_TELEMETRY_TARGET_ID_MAX_CHARS),
            "short",
        )

    def test_requires_approval_when_read_only_false_and_destructive(self) -> None:
        annotations = ToolAnnotations(read_only_hint=False, destructive_hint=True)

        self.assertTrue(requires_mcp_tool_approval(annotations))

    def test_requires_approval_when_read_only_false_and_open_world(self) -> None:
        annotations = ToolAnnotations(read_only_hint=False, open_world_hint=True)

        self.assertTrue(requires_mcp_tool_approval(annotations))

    def test_requires_approval_when_destructive_even_if_read_only_true(self) -> None:
        annotations = ToolAnnotations(
            read_only_hint=True,
            destructive_hint=True,
            open_world_hint=True,
        )

        self.assertTrue(requires_mcp_tool_approval(annotations))

    def test_requires_approval_when_annotations_are_absent(self) -> None:
        self.assertTrue(requires_mcp_tool_approval(None))

    def test_approval_not_required_when_read_only_and_other_hints_absent(self) -> None:
        annotations = ToolAnnotations(read_only_hint=True)

        self.assertFalse(requires_mcp_tool_approval(annotations))

    def test_requires_approval_accepts_camel_case_annotation_mapping(self) -> None:
        self.assertFalse(requires_mcp_tool_approval({"readOnlyHint": True}))
        self.assertTrue(
            requires_mcp_tool_approval({"readOnlyHint": False, "openWorldHint": True})
        )

    def test_prompt_mode_does_not_allow_session_or_persistent_remember(self) -> None:
        self.assertEqual(
            normalize_approval_decision_for_mode(
                McpToolApprovalDecision.accept_for_session(),
                AppToolApproval.PROMPT,
            ),
            McpToolApprovalDecision.accept(),
        )
        self.assertEqual(
            normalize_approval_decision_for_mode(
                McpToolApprovalDecision.accept_and_remember(),
                AppToolApproval.PROMPT,
            ),
            McpToolApprovalDecision.accept(),
        )

    def test_non_prompt_mode_preserves_remember_decision(self) -> None:
        decision = McpToolApprovalDecision.accept_and_remember()

        self.assertEqual(
            normalize_approval_decision_for_mode(decision, AppToolApproval.AUTO),
            decision,
        )

    def test_custom_servers_support_session_and_persistent_approval_keys(self) -> None:
        invocation = McpInvocation(server="custom_server", tool="run_action")
        expected = McpToolApprovalKey(
            server="custom_server",
            connector_id=None,
            tool_name="run_action",
        )

        self.assertEqual(
            session_mcp_tool_approval_key(invocation, None, AppToolApproval.AUTO),
            expected,
        )
        self.assertEqual(
            persistent_mcp_tool_approval_key(invocation, None, AppToolApproval.AUTO),
            expected,
        )

    def test_codex_apps_connectors_support_persistent_approval_keys(self) -> None:
        invocation = McpInvocation(
            server=CODEX_APPS_MCP_SERVER_NAME,
            tool="calendar/list_events",
        )
        metadata = McpToolApprovalMetadata(
            connector_id="calendar",
            connector_name="Calendar",
        )
        expected = McpToolApprovalKey(
            server=CODEX_APPS_MCP_SERVER_NAME,
            connector_id="calendar",
            tool_name="calendar/list_events",
        )

        self.assertEqual(
            session_mcp_tool_approval_key(invocation, metadata, AppToolApproval.AUTO),
            expected,
        )
        self.assertEqual(
            persistent_mcp_tool_approval_key(invocation, metadata, AppToolApproval.AUTO),
            expected,
        )

    def test_codex_apps_without_connector_id_cannot_be_remembered(self) -> None:
        invocation = McpInvocation(server=CODEX_APPS_MCP_SERVER_NAME, tool="list_events")

        self.assertIsNone(
            session_mcp_tool_approval_key(invocation, None, AppToolApproval.AUTO)
        )

    def test_non_auto_approval_modes_disable_remember_keys(self) -> None:
        invocation = McpInvocation(server="custom_server", tool="run_action")

        self.assertIsNone(
            session_mcp_tool_approval_key(invocation, None, AppToolApproval.PROMPT)
        )
        self.assertIsNone(
            session_mcp_tool_approval_key(invocation, None, AppToolApproval.APPROVE)
        )

    def test_mcp_tool_approval_config_edit_paths_match_upstream_set_path(self) -> None:
        self.assertEqual(
            codex_app_tool_approval_config_edit("calendar", "calendar/list_events"),
            McpToolApprovalConfigEdit(
                (
                    "apps",
                    "calendar",
                    "tools",
                    "calendar/list_events",
                    "approval_mode",
                )
            ),
        )
        self.assertEqual(
            custom_mcp_tool_approval_config_edit("docs", "search").to_mapping(),
            {
                "segments": [
                    "mcp_servers",
                    "docs",
                    "tools",
                    "search",
                    "approval_mode",
                ],
                "value": MCP_TOOL_APPROVAL_PERSIST_VALUE,
            },
        )
        self.assertEqual(
            plugin_mcp_tool_approval_config_edit("sample@test", "sample", "search"),
            McpToolApprovalConfigEdit(
                (
                    "plugins",
                    "sample@test",
                    "mcp_servers",
                    "sample",
                    "tools",
                    "search",
                    "approval_mode",
                )
            ),
        )

    def test_mcp_tool_approval_config_edit_for_key_selects_target_shape(self) -> None:
        self.assertEqual(
            mcp_tool_approval_config_edit_for_key(
                McpToolApprovalKey(
                    CODEX_APPS_MCP_SERVER_NAME,
                    "calendar",
                    "calendar/list_events",
                )
            ),
            codex_app_tool_approval_config_edit("calendar", "calendar/list_events"),
        )
        self.assertIsNone(
            mcp_tool_approval_config_edit_for_key(
                McpToolApprovalKey(CODEX_APPS_MCP_SERVER_NAME, None, "run_action")
            )
        )
        self.assertEqual(
            mcp_tool_approval_config_edit_for_key(
                {"server": "docs", "connector_id": None, "tool_name": "search"}
            ),
            custom_mcp_tool_approval_config_edit("docs", "search"),
        )
        self.assertEqual(
            mcp_tool_approval_config_edit_for_key(
                McpToolApprovalKey("sample", None, "search"),
                plugin_config_name="sample@test",
            ),
            plugin_mcp_tool_approval_config_edit("sample@test", "sample", "search"),
        )

    def test_mcp_tool_approval_session_cache_helpers_use_approved_for_session(self) -> None:
        store = ApprovalStore()
        key = McpToolApprovalKey("custom_server", None, "run_action")

        self.assertFalse(mcp_tool_approval_is_remembered(store, key))
        store.put(key, ReviewDecision.denied())
        self.assertFalse(mcp_tool_approval_is_remembered(store, key))

        remember_mcp_tool_approval(store, key)

        self.assertTrue(mcp_tool_approval_is_remembered(store, key))
        self.assertEqual(store.get(key), ReviewDecision.approved_for_session())

    def test_apply_mcp_tool_approval_decision_remembers_session_acceptance(self) -> None:
        store = ApprovalStore()
        session_key = McpToolApprovalKey("custom_server", None, "run_action")

        apply_mcp_tool_approval_decision(
            store,
            McpToolApprovalDecision.accept_for_session(),
            session_approval_key=session_key,
        )

        self.assertTrue(mcp_tool_approval_is_remembered(store, session_key))

    def test_apply_mcp_tool_approval_decision_persists_then_remembers(self) -> None:
        store = ApprovalStore()
        session_key = McpToolApprovalKey("custom_server", None, "run_action")
        persistent_key = McpToolApprovalKey("custom_server", None, "run_action")
        persisted = []

        apply_mcp_tool_approval_decision(
            store,
            McpToolApprovalDecision.accept_and_remember(),
            session_approval_key=session_key,
            persistent_approval_key=persistent_key,
            persist_persistent_approval=persisted.append,
        )

        self.assertEqual(persisted, [persistent_key])
        self.assertTrue(mcp_tool_approval_is_remembered(store, persistent_key))

    def test_apply_mcp_tool_approval_decision_falls_back_to_session_memory(self) -> None:
        store = ApprovalStore()
        session_key = McpToolApprovalKey(CODEX_APPS_MCP_SERVER_NAME, None, "run_action")

        apply_mcp_tool_approval_decision(
            store,
            McpToolApprovalDecision.accept_and_remember(),
            session_approval_key=session_key,
            persistent_approval_key=None,
        )

        self.assertTrue(mcp_tool_approval_is_remembered(store, session_key))

    def test_apply_mcp_tool_approval_decision_remembers_after_persist_failure(self) -> None:
        store = ApprovalStore()
        persistent_key = McpToolApprovalKey("custom_server", None, "run_action")

        def fail(_key: McpToolApprovalKey) -> None:
            raise RuntimeError("disk full")

        apply_mcp_tool_approval_decision(
            store,
            McpToolApprovalDecision.accept_and_remember(),
            persistent_approval_key=persistent_key,
            persist_persistent_approval=fail,
        )

        self.assertTrue(mcp_tool_approval_is_remembered(store, persistent_key))

    def test_apply_mcp_tool_approval_decision_ignores_non_remember_decisions(self) -> None:
        for decision in (
            McpToolApprovalDecision.accept(),
            McpToolApprovalDecision.decline("no"),
            McpToolApprovalDecision.cancel(),
        ):
            store = ApprovalStore()
            key = McpToolApprovalKey("custom_server", None, "run_action")

            apply_mcp_tool_approval_decision(
                store,
                decision,
                session_approval_key=key,
                persistent_approval_key=key,
            )

            self.assertFalse(mcp_tool_approval_is_remembered(store, key))

    def test_prompt_options_reflect_available_keys_and_feature_gate(self) -> None:
        key = McpToolApprovalKey("server", None, "tool")

        self.assertEqual(
            mcp_tool_approval_prompt_options(key, key, True),
            type(mcp_tool_approval_prompt_options(key, key, True))(
                allow_session_remember=True,
                allow_persistent_approval=True,
            ),
        )
        self.assertFalse(
            mcp_tool_approval_prompt_options(key, key, False).allow_persistent_approval
        )
        self.assertFalse(
            mcp_tool_approval_prompt_options(None, key, True).allow_session_remember
        )

    def test_mcp_tool_approval_question_id_prefix(self) -> None:
        self.assertTrue(
            is_mcp_tool_approval_question_id(
                f"{MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX}_call_1"
            )
        )
        self.assertFalse(is_mcp_tool_approval_question_id(MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX))
        self.assertFalse(is_mcp_tool_approval_question_id("other_call_1"))

    def test_custom_mcp_tool_question_mentions_server_name(self) -> None:
        question = build_mcp_tool_approval_question(
            "q",
            "custom_server",
            "run_action",
            None,
            mcp_tool_approval_prompt_options(None, None, False),
        )

        self.assertEqual(question.header, "Approve app tool call?")
        self.assertEqual(
            question.question,
            'Allow the custom_server MCP server to run tool "run_action"?',
        )
        self.assertEqual(
            [option.label for option in question.options or ()],
            [MCP_TOOL_APPROVAL_ACCEPT, MCP_TOOL_APPROVAL_CANCEL],
        )

    def test_codex_apps_tool_question_uses_fallback_app_label(self) -> None:
        key = McpToolApprovalKey(CODEX_APPS_MCP_SERVER_NAME, "calendar", "run_action")
        question = build_mcp_tool_approval_question(
            "q",
            CODEX_APPS_MCP_SERVER_NAME,
            "run_action",
            None,
            mcp_tool_approval_prompt_options(key, key, True),
        )

        self.assertEqual(question.question, 'Allow this app to run tool "run_action"?')

    def test_tool_question_override_is_normalized_to_single_question_mark(self) -> None:
        question = build_mcp_tool_approval_question(
            "q",
            CODEX_APPS_MCP_SERVER_NAME,
            "run_action",
            "Calendar",
            mcp_tool_approval_prompt_options(None, None, False),
            question_override="Allow Calendar to run this??",
        )

        self.assertEqual(question.question, "Allow Calendar to run this?")

    def test_tool_question_options_follow_prompt_options(self) -> None:
        key = McpToolApprovalKey(CODEX_APPS_MCP_SERVER_NAME, "calendar", "run_action")
        question = build_mcp_tool_approval_question(
            "q",
            CODEX_APPS_MCP_SERVER_NAME,
            "run_action",
            "Calendar",
            mcp_tool_approval_prompt_options(key, key, True),
        )

        self.assertEqual(
            [option.label for option in question.options or ()],
            [
                MCP_TOOL_APPROVAL_ACCEPT,
                MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION,
                MCP_TOOL_APPROVAL_ACCEPT_AND_REMEMBER,
                MCP_TOOL_APPROVAL_CANCEL,
            ],
        )
        self.assertTrue(
            any(
                option.label == MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION
                and option.description
                == "Run the tool and remember this choice for this session."
                for option in question.options or ()
            )
        )

    def test_tool_question_without_elicitation_omits_always_allow(self) -> None:
        key = McpToolApprovalKey(CODEX_APPS_MCP_SERVER_NAME, "calendar", "run_action")
        question = build_mcp_tool_approval_question(
            "q",
            CODEX_APPS_MCP_SERVER_NAME,
            "run_action",
            "Calendar",
            mcp_tool_approval_prompt_options(key, key, False),
        )

        self.assertEqual(
            [option.label for option in question.options or ()],
            [
                MCP_TOOL_APPROVAL_ACCEPT,
                MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION,
                MCP_TOOL_APPROVAL_CANCEL,
            ],
        )

    def test_approval_display_params_are_sorted_by_name(self) -> None:
        self.assertEqual(
            build_mcp_tool_approval_display_params({"title": "Roadmap", "calendar_id": "primary"}),
            (
                RenderedMcpToolApprovalParam("calendar_id", "primary", "calendar_id"),
                RenderedMcpToolApprovalParam("title", "Roadmap", "title"),
            ),
        )
        self.assertIsNone(build_mcp_tool_approval_display_params(["not", "object"]))

    def test_approval_elicitation_meta_preserves_tool_params_keys(self) -> None:
        meta = build_mcp_tool_approval_elicitation_meta(
            CODEX_APPS_MCP_SERVER_NAME,
            McpToolApprovalMetadata(
                connector_id="calendar",
                connector_name="Calendar",
                connector_description="Manage events and schedules.",
                tool_title="Create Event",
                tool_description="Create a calendar event.",
            ),
            {"calendar_id": "primary", "title": "Roadmap review"},
            (
                RenderedMcpToolApprovalParam(
                    name="calendar_id",
                    value="primary",
                    display_name="Calendar",
                ),
                RenderedMcpToolApprovalParam(
                    name="title",
                    value="Roadmap review",
                    display_name="Title",
                ),
            ),
            mcp_tool_approval_prompt_options(
                McpToolApprovalKey(CODEX_APPS_MCP_SERVER_NAME, "calendar", "create_event"),
                McpToolApprovalKey(CODEX_APPS_MCP_SERVER_NAME, "calendar", "create_event"),
                True,
            ),
        )

        self.assertEqual(
            meta,
            {
                APPROVAL_KIND_KEY: APPROVAL_KIND_MCP_TOOL_CALL,
                PERSIST_KEY: [PERSIST_SESSION, PERSIST_ALWAYS],
                SOURCE_KEY: SOURCE_CONNECTOR,
                CONNECTOR_ID_KEY: "calendar",
                CONNECTOR_NAME_KEY: "Calendar",
                CONNECTOR_DESCRIPTION_KEY: "Manage events and schedules.",
                TOOL_TITLE_KEY: "Create Event",
                TOOL_DESCRIPTION_KEY: "Create a calendar event.",
                TOOL_PARAMS_KEY: {"calendar_id": "primary", "title": "Roadmap review"},
                TOOL_PARAMS_DISPLAY_KEY: [
                    {
                        "name": "calendar_id",
                        "value": "primary",
                        "display_name": "Calendar",
                    },
                    {
                        "name": "title",
                        "value": "Roadmap review",
                        "display_name": "Title",
                    },
                ],
            },
        )

    def test_parse_request_user_input_response_prioritizes_specific_answers(self) -> None:
        response = RequestUserInputResponse(
            {
                "approval": RequestUserInputAnswer(
                    (
                        MCP_TOOL_APPROVAL_ACCEPT,
                        MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION,
                    )
                )
            }
        )

        self.assertEqual(
            parse_mcp_tool_approval_response(response, "approval"),
            McpToolApprovalDecision.accept_for_session(),
        )
        self.assertEqual(
            parse_mcp_tool_approval_response(
                RequestUserInputResponse(
                    {
                        "approval": RequestUserInputAnswer(
                            (MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC,)
                        )
                    }
                ),
                "approval",
            ),
            McpToolApprovalDecision.decline(),
        )
        self.assertEqual(
            parse_mcp_tool_approval_response(response, "missing"),
            McpToolApprovalDecision.cancel(),
        )

    def test_parse_request_user_input_response_accepts_mapping(self) -> None:
        self.assertEqual(
            parse_mcp_tool_approval_response(
                {"answers": {"approval": {"answers": [MCP_TOOL_APPROVAL_ACCEPT_AND_REMEMBER]}}},
                "approval",
            ),
            McpToolApprovalDecision.accept_and_remember(),
        )

    def test_parse_elicitation_response_uses_persist_meta(self) -> None:
        self.assertEqual(
            parse_mcp_tool_approval_elicitation_response(
                ElicitationResponse(
                    action=ElicitationAction.ACCEPT,
                    meta={PERSIST_KEY: PERSIST_ALWAYS},
                ),
                "approval",
            ),
            McpToolApprovalDecision.accept_and_remember(),
        )
        self.assertEqual(
            parse_mcp_tool_approval_elicitation_response(
                ElicitationResponse(
                    action=ElicitationAction.ACCEPT,
                    meta={PERSIST_KEY: PERSIST_SESSION},
                ),
                "approval",
            ),
            McpToolApprovalDecision.accept_for_session(),
        )

    def test_parse_elicitation_response_accept_without_content_defaults_to_accept(self) -> None:
        self.assertEqual(
            parse_mcp_tool_approval_elicitation_response(
                ElicitationResponse(action=ElicitationAction.ACCEPT),
                "approval",
            ),
            McpToolApprovalDecision.accept(),
        )

    def test_parse_elicitation_response_converts_content_to_answers(self) -> None:
        self.assertEqual(
            parse_mcp_tool_approval_elicitation_response(
                ElicitationResponse(
                    action=ElicitationAction.ACCEPT,
                    content={"approval": [MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION, 3]},
                ),
                "approval",
            ),
            McpToolApprovalDecision.accept_for_session(),
        )

    def test_declined_elicitation_response_stays_decline(self) -> None:
        self.assertEqual(
            parse_mcp_tool_approval_elicitation_response(
                ElicitationResponse(
                    action=ElicitationAction.DECLINE,
                    content={"approval": MCP_TOOL_APPROVAL_ACCEPT},
                ),
                "approval",
            ),
            McpToolApprovalDecision.decline(),
        )

    def test_sanitize_mcp_tool_result_for_model_rewrites_image_content(self) -> None:
        result = CallToolResult(
            content=(
                {"type": "image", "data": "Zm9v", "mimeType": "image/png"},
                {"type": "text", "text": "hello"},
            ),
            structured_content={"ok": True},
            is_error=False,
            meta={"trace": 1},
        )

        got = sanitize_mcp_tool_result_for_model(False, result)

        self.assertEqual(
            got,
            CallToolResult(
                content=(
                    {"type": "text", "text": MCP_IMAGE_CONTENT_OMITTED_TEXT},
                    {"type": "text", "text": "hello"},
                ),
                structured_content={"ok": True},
                is_error=False,
                meta={"trace": 1},
            ),
        )

    def test_sanitize_mcp_tool_result_for_model_preserves_images_when_supported(self) -> None:
        result = CallToolResult(
            content=({"type": "image", "data": "Zm9v", "mimeType": "image/png"},),
            is_error=False,
        )

        self.assertEqual(sanitize_mcp_tool_result_for_model(True, result), result)
        self.assertEqual(sanitize_mcp_tool_result_for_model(False, "boom"), "boom")

    def test_truncate_mcp_tool_result_for_event_preserves_small_result(self) -> None:
        result = CallToolResult(
            content=({"type": "text", "text": "small"},),
            structured_content={"value": 1},
            is_error=False,
            meta={"debug": "ok"},
        )

        self.assertEqual(truncate_mcp_tool_result_for_event(result), result)

    def test_truncate_mcp_tool_result_for_event_bounds_large_result(self) -> None:
        result = CallToolResult(
            content=({"type": "text", "text": "large-mcp-content-" * 80_000},),
            structured_content={"large": "structured-value-" * 80_000},
            is_error=True,
            meta={"large": "meta-value-" * 80_000},
        )

        got = truncate_mcp_tool_result_for_event(result)

        self.assertIsInstance(got, CallToolResult)
        self.assertIsNone(got.structured_content)
        self.assertIsNone(got.meta)
        self.assertTrue(got.is_error)
        self.assertEqual(got.content[0]["type"], "text")
        self.assertIn("chars truncated", got.content[0]["text"])
        self.assertLess(
            len(str(got.to_mapping()).encode("utf-8")),
            MCP_TOOL_CALL_EVENT_RESULT_MAX_BYTES * 2 + 2048,
        )

    def test_truncate_mcp_tool_result_for_event_bounds_large_error(self) -> None:
        got = truncate_mcp_tool_result_for_event("error-message-" * 200_000)

        self.assertIsInstance(got, str)
        self.assertIn("chars truncated", got)
        self.assertLess(
            len(got.encode("utf-8")),
            MCP_TOOL_CALL_EVENT_RESULT_MAX_BYTES + 1024,
        )

    def test_custom_mcp_approval_mode_uses_server_default_with_tool_override(self) -> None:
        config = {
            "docs": McpServerApprovalConfig(
                default_tools_approval_mode=AppToolApproval.APPROVE,
                tools={
                    "search": McpServerToolConfig(
                        approval_mode=AppToolApproval.PROMPT,
                    )
                },
            )
        }

        self.assertEqual(
            custom_mcp_tool_approval_mode_from_config(config, "docs", "read"),
            AppToolApproval.APPROVE,
        )
        self.assertEqual(
            custom_mcp_tool_approval_mode_from_config(config, "docs", "search"),
            AppToolApproval.PROMPT,
        )
        self.assertIsNone(
            custom_mcp_tool_approval_mode_from_config(config, "unknown", "search")
        )

    def test_custom_mcp_approval_mode_accepts_mapping_config(self) -> None:
        config = {
            "docs": {
                "default_tools_approval_mode": "approve",
                "tools": {"search": {"approval_mode": "prompt"}},
            }
        }

        self.assertEqual(
            custom_mcp_tool_approval_mode_from_config(config, "docs", "search"),
            AppToolApproval.PROMPT,
        )

    def test_custom_mcp_approval_mode_uses_plugin_policy_after_user_config(self) -> None:
        plugin_config = {
            "sample": {
                "default_tools_approval_mode": "prompt",
                "tools": {"search": {"approval_mode": "approve"}},
            }
        }

        self.assertEqual(
            custom_mcp_tool_approval_mode(None, [plugin_config], "sample", "read"),
            AppToolApproval.PROMPT,
        )
        self.assertEqual(
            custom_mcp_tool_approval_mode(None, [plugin_config], "sample", "search"),
            AppToolApproval.APPROVE,
        )

    def test_custom_mcp_approval_mode_prefers_user_config_over_plugins(self) -> None:
        user_config = {"sample": {"default_tools_approval_mode": "auto"}}
        plugin_config = {"sample": {"default_tools_approval_mode": "approve"}}

        self.assertEqual(
            custom_mcp_tool_approval_mode(
                user_config,
                [plugin_config],
                "sample",
                "search",
            ),
            AppToolApproval.AUTO,
        )


if __name__ == "__main__":
    unittest.main()
