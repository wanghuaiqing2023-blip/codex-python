from pathlib import Path

from pycodex.protocol.approvals import FileChange
from pycodex.protocol.models import AdditionalPermissionProfile, FileSystemPermissions, NetworkPermissions
from pycodex.protocol.request_permissions import RequestPermissionProfile
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
    normalize_snapshot_paths,
    permissions_options,
    render_overlay_lines,
)
from pycodex.tui.app_event_sender import AppEventSender


# Rust source: codex/codex-rs/tui/src/bottom_pane/approval_overlay.rs
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

    assert view.emitted_events[0]["type"] == "InsertHistoryCell"
    assert view.emitted_events[1]["type"] == "ExecApproval"
    assert view.emitted_events[1]["decision"] == "Accept"
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
    assert view.emitted_events[0]["type"] == "InsertHistoryCell"
    assert view.emitted_events[1:] == [
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


def test_shortcuts_emit_typed_fullscreen_and_select_thread_app_events():
    # Fixed Rust commit 1c7832f: approval_overlay::try_handle_shortcut emits
    # FullScreenApprovalRequest and SelectAgentThread through AppEventSender.
    events = []
    sender = AppEventSender(events)
    request = ApprovalRequest.Exec(
        "side-thread",
        "approval",
        ["echo", "hello"],
        thread_label="worker [explorer]",
    )
    view = ApprovalOverlay.new(request, app_event_tx=sender)

    assert view.try_handle_shortcut("ctrl+shift+a")
    assert view.try_handle_shortcut("o")

    assert [event.kind for event in events] == [
        "FullScreenApprovalRequest",
        "SelectAgentThread",
    ]
    assert events[1].payload["thread_id"] == "side-thread"


def test_direction_keys_move_shared_list_highlight_before_enter() -> None:
    # Fixed Rust approval_overlay delegates navigation and selected-row state
    # to ListSelectionView before applying the chosen approval option.
    view = ApprovalOverlay.new(make_exec_request())

    assert view.selected_index() == 0
    view.handle_key_event("down")
    assert view.selected_index() == 1
    assert any(line.selected for line in view.terminal_lines(width=80))

    view.handle_key_event("enter")

    assert view.done is True
    assert view.emitted_events[-1]["decision"] == "Cancel"


def test_patch_and_permissions_selections_emit_typed_app_commands() -> None:
    # Fixed Rust approval_overlay routes every category through AppEventSender,
    # not terminal-owned callback dictionaries.
    events = []
    sender = AppEventSender(events)
    patch = ApprovalOverlay.new(
        ApprovalRequest.ApplyPatch(
            "thread",
            "patch-1",
            Path("/repo"),
            {Path("hello.txt"): FileChange.add("hello\n")},
        ),
        app_event_tx=sender,
    )
    patch.handle_key_event("enter")

    permissions = ApprovalOverlay.new(
        ApprovalRequest.Permissions(
            "thread",
            "perm-1",
            RequestPermissionProfile(),
        ),
        app_event_tx=sender,
    )
    permissions.handle_key_event("enter")

    assert [event.kind for event in events] == [
        "SubmitThreadOp",
        "InsertHistoryCell",
        "SubmitThreadOp",
    ]
    assert events[0].payload["op"].kind == "PatchApproval"
    assert events[0].payload["op"].payload["id"] == "patch-1"
    assert events[2].payload["op"].kind == "RequestPermissionsResponse"
    assert events[2].payload["op"].payload["id"] == "perm-1"


def test_exec_and_permission_options_use_expected_semantic_labels():
    network_options = exec_options(
        ["Accept", "AcceptForSession", "Cancel"],
        network_approval_context={"host": "example.com", "protocol": "Https"},
    )
    # Fixed Rust approval_events keeps AcceptForSession for network requests.
    assert [option.label for option in network_options] == [
        "Yes, just this once",
        "Yes, and allow this host for this conversation",
        "No, and tell Codex what to do differently",
    ]

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
    assert command_decision_to_review_decision("Accept").kind == "approved"
    assert command_decision_to_review_decision("AcceptForSession").kind == "approved_for_session"
    assert command_decision_to_review_decision("Cancel").kind == "abort"


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


def _snapshot_permission_profile() -> RequestPermissionProfile:
    return RequestPermissionProfile(
        network=NetworkPermissions(enabled=True),
        file_system=FileSystemPermissions.from_read_write_roots(
            read=["/tmp/readme.txt"],
            write=["/tmp/out.txt"],
        ),
    )


def test_permissions_prompt_projection_matches_fixed_rust_snapshot() -> None:
    # Fixed Rust commit 1c7832f snapshot:
    # approval_overlay__tests__approval_overlay_permissions_prompt.snap.
    request = ApprovalRequest.Permissions(
        "thread",
        "call",
        _snapshot_permission_profile(),
        reason="need workspace access",
    )

    assert normalize_snapshot_paths(render_overlay_lines(ApprovalOverlay.new(request), 120)) == """
  Would you like to grant these permissions?

  Reason: need workspace access

  Permission rule: network; read `/tmp/readme.txt`; write `/tmp/out.txt`

› 1. Yes, grant these permissions for this turn (y)
  2. Yes, grant for this turn with strict auto review (r)
  3. Yes, grant these permissions for this session (a)
  4. No, continue without permissions (d)

  Press enter to confirm or esc to cancel"""


def test_exec_prompt_projections_match_fixed_rust_snapshots() -> None:
    # Fixed Rust commit 1c7832f snapshots: cross-thread and additional
    # permissions approval-overlay prompts.
    cross_thread = ApprovalRequest.Exec(
        "thread",
        "test",
        ["echo", "hi"],
        thread_label="Robie [explorer]",
        available_decisions=["Accept", "Cancel"],
    )
    assert render_overlay_lines(ApprovalOverlay.new(cross_thread), 80) == """
  Would you like to run the following command?

  Thread: Robie [explorer]

  $ echo hi

› 1. Yes, proceed (y)
  2. No, and tell Codex what to do differently (esc)

  Press enter to confirm or esc to cancel or o to open thread"""

    additional = ApprovalRequest.Exec(
        "thread",
        "test",
        ["cat", "/tmp/readme.txt"],
        reason="need filesystem access",
        available_decisions=["Accept", "Cancel"],
        additional_permissions=AdditionalPermissionProfile(
            network=NetworkPermissions(enabled=True),
            file_system=_snapshot_permission_profile().file_system,
        ),
    )
    assert normalize_snapshot_paths(render_overlay_lines(ApprovalOverlay.new(additional), 120)) == """
  Would you like to run the following command?

  Reason: need filesystem access

  Permission rule: network; read `/tmp/readme.txt`; write `/tmp/out.txt`

  $ cat /tmp/readme.txt

› 1. Yes, proceed (y)
  2. No, and tell Codex what to do differently (esc)

  Press enter to confirm or esc to cancel"""


def test_patch_prompt_projection_matches_fixed_rust_snapshot() -> None:
    # Fixed Rust commit 1c7832f snapshot:
    # chatwidget::tests::approval_modal_patch. Patch paths are rendered in the
    # typed patch history cell, not repeated in the modal header.
    request = ApprovalRequest.ApplyPatch(
        "thread",
        "patch",
        Path("/repo"),
        {Path("hello.txt"): FileChange.add("hello\n")},
        reason="The model wants to apply changes",
    )

    assert render_overlay_lines(ApprovalOverlay.new(request), 80) == """
  Would you like to make the following edits?

  Reason: The model wants to apply changes

› 1. Yes, proceed (y)
  2. Yes, and don't ask again for these files (a)
  3. No, and tell Codex what to do differently (esc)

  Press enter to confirm or esc to cancel"""


def test_network_prompt_projection_matches_fixed_rust_snapshot_content() -> None:
    # Fixed Rust commit 1c7832f snapshot:
    # approval_overlay__tests__network_exec_prompt.snap.
    request = ApprovalRequest.Exec(
        "thread",
        "test",
        ["curl", "https://example.com"],
        reason="network request blocked",
        available_decisions=[
            "Accept",
            "AcceptForSession",
            {
                "kind": "ApplyNetworkPolicyAmendment",
                "network_policy_amendment": {"host": "example.com", "action": "Allow"},
            },
            "Cancel",
        ],
        network_approval_context={"host": "example.com", "protocol": "Https"},
    )

    assert render_overlay_lines(ApprovalOverlay.new(request), 100) == """
  Do you want to approve network access to "example.com"?

  Reason: network request blocked


› 1. Yes, just this once (y)
  2. Yes, and allow this host for this conversation (a)
  3. Yes, and allow this host in the future (p)
  4. No, and tell Codex what to do differently (esc)

  Press enter to confirm or esc to cancel"""


def test_network_decisions_roundtrip_through_shared_overlay() -> None:
    # Fixed Rust commit 1c7832f:
    # approval_overlay::handle_exec_decision maps one-time, session, policy
    # amendment, and cancel choices through the same AppCommand boundary.
    decisions = [
        "Accept",
        "AcceptForSession",
        {
            "kind": "ApplyNetworkPolicyAmendment",
            "network_policy_amendment": {"host": "example.com", "action": "Allow"},
        },
        "Cancel",
    ]

    for selected_index, expected in enumerate(decisions):
        view = ApprovalOverlay.new(
            ApprovalRequest.Exec(
                "thread",
                f"network-{selected_index}",
                ["network-access", "https://example.com"],
                available_decisions=decisions,
                network_approval_context={"host": "example.com", "protocol": "Https"},
            )
        )
        view.apply_selection(selected_index)

        assert view.done is True
        assert view.emitted_events[-1]["type"] == "ExecApproval"
        assert view.emitted_events[-1]["decision"] == expected
        assert view.emitted_events[0]["type"] == "InsertHistoryCell"


def test_approval_projection_wraps_long_content_at_narrow_width() -> None:
    # Rust owner: approval header Paragraph and ListSelectionView wrap inside
    # the menu surface rather than relying on the terminal adapter to clip it.
    request = ApprovalRequest.Exec(
        "thread",
        "test",
        ["powershell", "-NoProfile", "-Command", "Write-Output", "非常长的中文命令参数"],
        reason="需要在窄窗口中展示完整原因，而不是越过审批视图边界",
        available_decisions=["Accept", "Cancel"],
    )

    lines = ApprovalOverlay.new(request).terminal_lines(width=40)

    assert any("非常长" in line.text for line in lines)
    assert all(len(line.text) <= 40 for line in lines)
