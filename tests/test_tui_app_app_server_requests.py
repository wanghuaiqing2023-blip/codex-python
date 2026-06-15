from pycodex.tui.app.app_server_requests import (
    AppServerRequestResolution,
    PendingAppServerRequests,
    ResolvedAppServerRequest,
    UnsupportedAppServerRequest,
    correlates_mcp_elicitation_server_request_with_resolution,
    does_not_mark_chatgpt_auth_refresh_as_unsupported,
    rejects_dynamic_tool_calls_as_unsupported,
    resolve_notification_returns_resolved_exec_request,
    resolve_notification_returns_resolved_mcp_request,
    resolve_notification_returns_resolved_user_input_item_id,
    resolves_exec_approval_through_app_server_request_id,
    resolves_patch_approval_through_app_server_request_id,
    resolves_permissions_and_user_input_through_app_server_request_id,
    same_turn_user_input_answers_resolve_app_server_requests_fifo,
)


def test_resolves_exec_approval_through_app_server_request_id():
    """Rust codex-tui app::app_server_requests::resolves_exec_approval_through_app_server_request_id."""

    assert resolves_exec_approval_through_app_server_request_id()


def test_resolves_permissions_and_user_input_through_app_server_request_id():
    """Rust codex-tui app::app_server_requests::resolves_permissions_and_user_input_through_app_server_request_id."""

    assert resolves_permissions_and_user_input_through_app_server_request_id()


def test_correlates_mcp_elicitation_server_request_with_resolution():
    """Rust codex-tui app::app_server_requests::correlates_mcp_elicitation_server_request_with_resolution."""

    assert correlates_mcp_elicitation_server_request_with_resolution()


def test_rejects_dynamic_tool_calls_as_unsupported():
    """Rust codex-tui app::app_server_requests::rejects_dynamic_tool_calls_as_unsupported."""

    assert rejects_dynamic_tool_calls_as_unsupported()


def test_does_not_mark_chatgpt_auth_refresh_as_unsupported():
    """Rust codex-tui app::app_server_requests::does_not_mark_chatgpt_auth_refresh_as_unsupported."""

    assert does_not_mark_chatgpt_auth_refresh_as_unsupported()


def test_resolves_patch_approval_through_app_server_request_id():
    """Rust codex-tui app::app_server_requests::resolves_patch_approval_through_app_server_request_id."""

    assert resolves_patch_approval_through_app_server_request_id()


def test_resolve_notification_returns_resolved_exec_request():
    """Rust codex-tui app::app_server_requests::resolve_notification_returns_resolved_exec_request."""

    assert resolve_notification_returns_resolved_exec_request()


def test_resolve_notification_returns_resolved_mcp_request():
    """Rust codex-tui app::app_server_requests::resolve_notification_returns_resolved_mcp_request."""

    assert resolve_notification_returns_resolved_mcp_request()


def test_mcp_elicitation_resolution_requires_matching_server_name_and_request_id():
    """Rust McpRequestKey includes both server_name and request_id."""

    pending = PendingAppServerRequests()
    pending.note_server_request(
        {"McpServerElicitationRequest": {"request_id": 12, "server_name": "example"}}
    )

    assert pending.take_resolution(
        {
            "type": "ResolveElicitation",
            "server_name": "other",
            "request_id": 12,
            "decision": "accept",
            "content": {"answer": "yes"},
            "meta": None,
        }
    ) is None
    assert pending.take_resolution(
        {
            "type": "ResolveElicitation",
            "server_name": "example",
            "request_id": 12,
            "decision": "accept",
            "content": {"answer": "yes"},
            "meta": None,
        }
    ) == AppServerRequestResolution(12, {"action": "accept", "content": {"answer": "yes"}})


def test_resolve_notification_returns_resolved_user_input_item_id():
    """Rust codex-tui app::app_server_requests::resolve_notification_returns_resolved_user_input_item_id."""

    assert resolve_notification_returns_resolved_user_input_item_id()


def test_same_turn_user_input_answers_resolve_app_server_requests_fifo():
    """Rust codex-tui app::app_server_requests::same_turn_user_input_answers_resolve_app_server_requests_fifo."""

    assert same_turn_user_input_answers_resolve_app_server_requests_fifo()


def test_approval_id_falls_back_to_item_id_when_missing():
    """Rust note_server_request uses approval_id.unwrap_or_else(item_id)."""

    pending = PendingAppServerRequests()
    pending.note_server_request(
        {"CommandExecutionRequestApproval": {"request_id": 41, "item_id": "call-1"}}
    )

    assert pending.take_resolution(
        {"type": "ExecApproval", "id": "call-1", "decision": "accept"}
    ) == AppServerRequestResolution(41, {"decision": "accept"})


def test_contains_server_request_tracks_pending_and_unsupported_requests():
    """Rust contains_server_request map membership and unsupported always-true branches."""

    pending = PendingAppServerRequests()
    request = {"FileChangeRequestApproval": {"request_id": 13, "item_id": "patch-1"}}
    pending.note_server_request(request)

    assert pending.contains_server_request(request) is True
    assert pending.contains_server_request({"FileChangeRequestApproval": {"request_id": 99, "item_id": "patch-1"}}) is False
    assert pending.contains_server_request({"DynamicToolCall": {"request_id": 99}}) is True
    assert pending.contains_server_request({"ExecCommandApproval": {"request_id": 100}}) is True


def test_unsupported_legacy_and_attestation_messages_match_rust():
    """Rust note_server_request unsupported request messages for non-TUI server requests."""

    pending = PendingAppServerRequests()

    assert pending.note_server_request({"AttestationGenerate": {"request_id": 1}}) == UnsupportedAppServerRequest(
        1,
        "Attestation generation is not available in TUI.",
    )
    assert pending.note_server_request({"ApplyPatchApproval": {"request_id": 2}}) == UnsupportedAppServerRequest(
        2,
        "Legacy patch approval requests are not available in TUI yet.",
    )
    assert pending.note_server_request({"ExecCommandApproval": {"request_id": 3}}) == UnsupportedAppServerRequest(
        3,
        "Legacy command approval requests are not available in TUI yet.",
    )


def test_resolve_notification_removes_all_supported_pending_request_kinds():
    """Rust resolve_notification removes exec/file/permissions/user-input/MCP pending state."""

    pending = PendingAppServerRequests()
    pending.note_server_request({"FileChangeRequestApproval": {"request_id": 13, "item_id": "patch-1"}})
    pending.note_server_request({"PermissionsRequestApproval": {"request_id": 7, "item_id": "perm-1"}})
    pending.note_server_request({"ToolRequestUserInput": {"request_id": 8, "turn_id": "turn-1", "item_id": "tool-1"}})
    pending.note_server_request({"McpServerElicitationRequest": {"request_id": 12, "server_name": "example"}})

    assert pending.resolve_notification(13) == ResolvedAppServerRequest.FileChangeApproval("patch-1")
    assert pending.resolve_notification(7) == ResolvedAppServerRequest.PermissionsApproval("perm-1")
    assert pending.resolve_notification(8) == ResolvedAppServerRequest.UserInput("tool-1")
    assert pending.resolve_notification(12) == ResolvedAppServerRequest.McpElicitation("example", 12)
    assert pending.resolve_notification(12) is None


def test_clear_drops_every_pending_request_map():
    """Rust PendingAppServerRequests::clear clears all pending request stores."""

    pending = PendingAppServerRequests()
    pending.note_server_request({"CommandExecutionRequestApproval": {"request_id": 41, "item_id": "call-1"}})
    pending.note_server_request({"FileChangeRequestApproval": {"request_id": 13, "item_id": "patch-1"}})
    pending.note_server_request({"PermissionsRequestApproval": {"request_id": 7, "item_id": "perm-1"}})
    pending.note_server_request({"ToolRequestUserInput": {"request_id": 8, "turn_id": "turn-1", "item_id": "tool-1"}})
    pending.note_server_request({"McpServerElicitationRequest": {"request_id": 12, "server_name": "example"}})

    pending.clear()

    assert pending.resolve_notification(41) is None
    assert pending.resolve_notification(13) is None
    assert pending.resolve_notification(7) is None
    assert pending.resolve_notification(8) is None
    assert pending.resolve_notification(12) is None
