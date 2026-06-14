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


def test_resolves_exec_approval_through_app_server_request_id_matches_rust() -> None:
    # Rust: app/app_server_requests.rs resolves_exec_approval_through_app_server_request_id
    assert resolves_exec_approval_through_app_server_request_id()


def test_resolves_permissions_and_user_input_through_app_server_request_id_matches_rust() -> None:
    # Rust: resolves_permissions_and_user_input_through_app_server_request_id
    assert resolves_permissions_and_user_input_through_app_server_request_id()


def test_correlates_mcp_elicitation_server_request_with_resolution_matches_rust() -> None:
    # Rust: correlates_mcp_elicitation_server_request_with_resolution
    assert correlates_mcp_elicitation_server_request_with_resolution()


def test_rejects_dynamic_tool_calls_as_unsupported_matches_rust() -> None:
    # Rust: rejects_dynamic_tool_calls_as_unsupported
    assert rejects_dynamic_tool_calls_as_unsupported()


def test_does_not_mark_chatgpt_auth_refresh_as_unsupported_matches_rust() -> None:
    # Rust: does_not_mark_chatgpt_auth_refresh_as_unsupported
    assert does_not_mark_chatgpt_auth_refresh_as_unsupported()


def test_resolves_patch_approval_through_app_server_request_id_matches_rust() -> None:
    # Rust: resolves_patch_approval_through_app_server_request_id
    assert resolves_patch_approval_through_app_server_request_id()


def test_resolve_notification_returns_resolved_exec_request_matches_rust() -> None:
    # Rust: resolve_notification_returns_resolved_exec_request
    assert resolve_notification_returns_resolved_exec_request()


def test_resolve_notification_returns_resolved_mcp_request_matches_rust() -> None:
    # Rust: resolve_notification_returns_resolved_mcp_request
    assert resolve_notification_returns_resolved_mcp_request()


def test_resolve_notification_returns_resolved_user_input_item_id_matches_rust() -> None:
    # Rust: resolve_notification_returns_resolved_user_input_item_id
    assert resolve_notification_returns_resolved_user_input_item_id()


def test_same_turn_user_input_answers_resolve_app_server_requests_fifo_matches_rust() -> None:
    # Rust: same_turn_user_input_answers_resolve_app_server_requests_fifo
    assert same_turn_user_input_answers_resolve_app_server_requests_fifo()


def test_contains_server_request_and_clear_semantics() -> None:
    pending = PendingAppServerRequests()
    request = {"FileChangeRequestApproval": {"request_id": 13, "item_id": "patch-1"}}

    assert not pending.contains_server_request(request)
    pending.note_server_request(request)
    assert pending.contains_server_request(request)
    assert pending.contains_server_request({"DynamicToolCall": {"request_id": 99}})

    pending.clear()
    assert not pending.contains_server_request(request)


def test_approval_id_falls_back_to_item_id() -> None:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {
            "CommandExecutionRequestApproval": {
                "request_id": 41,
                "approval_id": None,
                "item_id": "call-1",
            }
        }
    )

    assert pending.take_resolution(
        {"type": "ExecApproval", "id": "call-1", "decision": "accept"}
    ) == AppServerRequestResolution(41, {"decision": "accept"})


def test_remove_user_input_request_deletes_empty_turn_queue() -> None:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {
            "ToolRequestUserInput": {
                "request_id": 8,
                "turn_id": "turn-1",
                "item_id": "tool-1",
            }
        }
    )

    assert pending.remove_user_input_request(8).item_id == "tool-1"
    assert pending.user_inputs == {}


def test_unsupported_legacy_requests_use_rust_messages() -> None:
    pending = PendingAppServerRequests()

    assert pending.note_server_request(
        {"AttestationGenerate": {"request_id": 1}}
    ) == UnsupportedAppServerRequest(1, "Attestation generation is not available in TUI.")
    assert pending.note_server_request(
        {"ApplyPatchApproval": {"request_id": 2}}
    ) == UnsupportedAppServerRequest(
        2,
        "Legacy patch approval requests are not available in TUI yet.",
    )
    assert pending.note_server_request(
        {"ExecCommandApproval": {"request_id": 3}}
    ) == UnsupportedAppServerRequest(
        3,
        "Legacy command approval requests are not available in TUI yet.",
    )


def test_resolve_notification_removes_permission_request() -> None:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {"PermissionsRequestApproval": {"request_id": 7, "item_id": "perm-1"}}
    )

    assert pending.resolve_notification(7) == ResolvedAppServerRequest.PermissionsApproval(
        "perm-1"
    )
    assert pending.resolve_notification(7) is None
