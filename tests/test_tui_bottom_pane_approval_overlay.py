from pycodex.tui.bottom_pane.approval_overlay import (
    ApprovalKeymap,
    ApprovalOverlay,
    ApprovalRequest,
    PermissionsDecision,
    command_decision_to_review_decision,
    exec_options,
    format_additional_permissions_rule,
    make_elicitation_request,
    make_exec_request,
    make_permissions_request,
    network_approval_command_target,
    network_approval_target,
    permissions_options,
)


def test_request_matches_resolved_request_variants():
    assert make_exec_request().matches_resolved_request({"kind": "ExecApproval", "id": "test"})
    assert make_permissions_request().matches_resolved_request({"kind": "PermissionsApproval", "id": "call"})
    assert make_elicitation_request().matches_resolved_request(
        {"kind": "McpElicitation", "server_name": "server", "request_id": "req"}
    )
    assert not make_elicitation_request().matches_resolved_request(
        {"kind": "McpElicitation", "server_name": "other", "request_id": "req"}
    )
    assert not make_elicitation_request().matches_resolved_request(
        {"kind": "McpElicitation", "server_name": "server", "request_id": "other"}
    )
    assert not make_exec_request().matches_resolved_request({"kind": "FileChangeApproval", "id": "test"})


def test_overlay_selection_emits_decision_and_advances_queue_lifo_like_rust_pop():
    first = make_exec_request()
    second = ApprovalRequest.Exec("thread", "second", ["pwd"], available_decisions=["Accept", "Cancel"])
    view = ApprovalOverlay.new(first)
    view.enqueue_request(second)

    view.apply_selection(0)

    assert view.emitted_events[0]["type"] == "ExecApproval"
    assert view.emitted_events[0]["decision"] == "Accept"
    assert view.current_request.id == "second"
    assert not view.done

    view.apply_selection(1)
    assert view.done
    assert view.emitted_events[-1]["decision"] == "Cancel"


def test_cancel_current_request_emits_request_specific_cancel_and_clears_queue():
    view = ApprovalOverlay.new(make_permissions_request())
    view.enqueue_request(make_exec_request())

    view.cancel_current_request()

    assert view.done
    assert view.queue == []
    assert view.emitted_events == [
        {
            "type": "RequestPermissionsResponse",
            "thread_id": "thread",
            "id": "call",
            "permissions": {},
            "scope": "Turn",
            "strict_auto_review": False,
        }
    ]


def test_dismiss_resolved_request_removes_current_without_abort_event():
    view = ApprovalOverlay.new(make_exec_request())
    assert view.dismiss_resolved_request({"kind": "ExecApproval", "id": "test"})
    assert view.done
    assert view.emitted_events == []


def test_esc_cancels_mcp_elicitation_even_with_custom_decline_overlap():
    keymap = ApprovalKeymap(deny=("Esc", "n"), cancel=("x",))
    view = ApprovalOverlay.new(make_elicitation_request(), approval_keymap=keymap)

    view.handle_key_event("Esc")

    assert view.done
    assert view.emitted_events[-1]["type"] == "ResolveElicitation"
    assert view.emitted_events[-1]["decision"] == "Cancel"

    view = ApprovalOverlay.new(make_elicitation_request(), approval_keymap=keymap)
    view.handle_key_event("n")
    assert view.emitted_events[-1]["decision"] == "Decline"


def test_shortcuts_trigger_selection_and_fullscreen_open():
    view = ApprovalOverlay.new(make_exec_request())
    assert view.try_handle_shortcut("ctrl+shift+a")
    assert view.emitted_events[-1]["type"] == "FullScreenApprovalRequest"

    assert view.try_handle_shortcut("y")
    assert view.emitted_events[-1]["type"] == "ExecApproval"


def test_exec_and_permission_options_use_expected_semantic_labels():
    network_options = exec_options(
        ["Accept", "AcceptForSession", "Cancel"],
        network_approval_context={"host": "example.com", "protocol": "Https"},
    )
    assert [option.label for option in network_options] == ["Yes, allow once", "No, cancel"]

    generic_options = exec_options(["Accept", "AcceptForSession", "Cancel"])
    assert [option.decision for option in generic_options] == ["Accept", "AcceptForSession", "Cancel"]

    perms = permissions_options()
    assert [option.decision for option in perms] == [
        PermissionsDecision.GRANT_FOR_TURN,
        PermissionsDecision.GRANT_FOR_TURN_WITH_STRICT_AUTO_REVIEW,
        PermissionsDecision.GRANT_FOR_SESSION,
        PermissionsDecision.DENY,
    ]


def test_network_targets_and_review_decision_mapping():
    assert network_approval_command_target(["network-access", "https://example.com:8443"]) == "https://example.com:8443"
    assert network_approval_target({"host": "example.com", "protocol": "Https"}, ["curl"]) == "https://example.com"
    assert command_decision_to_review_decision("Accept") == "Approved"
    assert command_decision_to_review_decision("AcceptForSession") == "ApprovedForSession"
    assert command_decision_to_review_decision("Cancel") == "Denied"


def test_permission_rule_formatting_covers_special_and_path_entries():
    assert (
        format_additional_permissions_rule(
            {
                "network": {"enabled": True},
                "file_system": {"read": [{"special": "WorkspaceRoots"}, "/tmp/readme.txt"]},
            }
        )
        == "network; read :workspace_roots, `/tmp/readme.txt`"
    )
