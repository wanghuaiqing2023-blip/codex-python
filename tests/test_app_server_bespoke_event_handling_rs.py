from __future__ import annotations

from pycodex.app_server.bespoke_event_handling import (
    REVIEW_FALLBACK_MESSAGE,
    TurnCompletionMetadata,
    hook_prompt_item_completed_payload,
    map_file_change_approval_decision,
    mcp_server_elicitation_response_from_client_result,
    render_review_output_text,
    request_permissions_response_from_client_result,
    turn_completed_notification,
    turn_diff_updated_notification,
    turn_plan_updated_notification,
)
from pycodex.app_server_protocol import (
    FileChangeApprovalDecision,
    McpServerElicitationAction,
    PermissionGrantScope,
    TurnItemsView,
    TurnStatus,
)
from pycodex.protocol import HookPromptFragment, ReviewDecision, build_hook_prompt_message


def test_turn_diff_updated_notification_matches_rust_payload_shape() -> None:
    # Rust: handle_turn_diff builds TurnDiffUpdatedNotification.
    notification = turn_diff_updated_notification("thread-1", "turn-1", "@@ diff")

    assert notification.to_camel_mapping() == {
        "threadId": "thread-1",
        "turnId": "turn-1",
        "diff": "@@ diff",
    }


def test_turn_plan_updated_notification_maps_update_plan_steps() -> None:
    # Rust: handle_turn_plan_update maps UpdatePlanArgs to TurnPlanStep.
    notification = turn_plan_updated_notification(
        "thread-1",
        "turn-1",
        {
            "explanation": "next",
            "plan": [
                {"step": "inspect", "status": "completed"},
                {"step": "patch", "status": "inProgress"},
            ],
        },
    )

    assert notification.thread_id == "thread-1"
    assert notification.turn_id == "turn-1"
    assert notification.explanation == "next"
    assert [(step.step, step.status.value) for step in notification.plan] == [
        ("inspect", "completed"),
        ("patch", "inProgress"),
    ]


def test_turn_completed_notification_uses_not_loaded_empty_turn() -> None:
    # Rust: emit_turn_completed_with_status emits an empty NotLoaded turn.
    notification = turn_completed_notification(
        "thread-1",
        "turn-1",
        TurnCompletionMetadata(
            status=TurnStatus.INTERRUPTED,
            started_at=10,
            completed_at=25,
            duration_ms=15,
        ),
    )

    assert notification.thread_id == "thread-1"
    assert notification.turn.id == "turn-1"
    assert notification.turn.items == ()
    assert notification.turn.items_view is TurnItemsView.NOT_LOADED
    assert notification.turn.status is TurnStatus.INTERRUPTED
    assert notification.turn.duration_ms == 15


def test_hook_prompt_item_completed_payload_only_for_user_hook_prompt_messages() -> None:
    # Rust: maybe_emit_hook_prompt_item_completed ignores non-user/non-hook items.
    message = build_hook_prompt_message(
        [
            HookPromptFragment.from_single_hook("Retry with tests.", "hook-run-1"),
            HookPromptFragment.from_single_hook("Then summarize.", "hook-run-2"),
        ]
    )
    payload = hook_prompt_item_completed_payload("thread-1", "turn-1", message, completed_at_ms=123)

    assert payload is not None
    assert payload["thread_id"] == "thread-1"
    assert payload["turn_id"] == "turn-1"
    assert payload["completed_at_ms"] == 123
    assert payload["item"].type == "hookPrompt"
    assert [fragment.text for fragment in payload["item"].fields["fragments"]] == [
        "Retry with tests.",
        "Then summarize.",
    ]
    assert hook_prompt_item_completed_payload("thread-1", "turn-1", {"role": "assistant"}) is None


def test_mcp_server_elicitation_response_fallbacks_match_rust() -> None:
    # Rust: mcp_server_elicitation_response_from_client_result cancels on turn transition,
    # declines on client/deserialization errors, and forwards valid client responses.
    valid = mcp_server_elicitation_response_from_client_result(
        {"action": "accept", "content": {"answer": 1}, "_meta": {"trace": "x"}}
    )
    cancelled = mcp_server_elicitation_response_from_client_result({}, turn_transition_error=True)
    declined = mcp_server_elicitation_response_from_client_result({"error": "client failed"})

    assert valid.action is McpServerElicitationAction.ACCEPT
    assert valid.content == {"answer": 1}
    assert valid.meta == {"trace": "x"}
    assert cancelled.action is McpServerElicitationAction.CANCEL
    assert declined.action is McpServerElicitationAction.DECLINE


def test_request_permissions_response_fallbacks_and_strict_scope_guard() -> None:
    # Rust: request_permissions_response_from_client_result drops turn transitions,
    # returns default Turn grants on errors, and rejects session-scoped strict auto review.
    assert request_permissions_response_from_client_result({}, turn_transition_error=True) is None

    failed = request_permissions_response_from_client_result({"error": "client failed"})
    assert failed == {"permissions": {}, "scope": "turn", "strict_auto_review": False}

    strict_session = request_permissions_response_from_client_result(
        {
            "permissions": {},
            "scope": PermissionGrantScope.SESSION.value,
            "strictAutoReview": True,
        }
    )
    assert strict_session == {"permissions": {}, "scope": "turn", "strict_auto_review": False}


def test_render_review_output_text_joins_explanation_and_findings_with_fallback() -> None:
    # Rust: render_review_output_text trims explanation, formats findings, and falls back if empty.
    assert render_review_output_text({"overall_explanation": "  Looks risky.  ", "findings": []}) == "Looks risky."
    assert (
        render_review_output_text(
            {
                "overall_explanation": "Summary",
                "findings": [{"title": "Bug one"}, {"message": "Bug two"}],
            }
        )
        == "Summary\n\n1. Bug one\n2. Bug two"
    )
    assert render_review_output_text({"overall_explanation": " ", "findings": []}) == REVIEW_FALLBACK_MESSAGE


def test_map_file_change_approval_decision_matches_review_decision_variants() -> None:
    # Rust: map_file_change_approval_decision maps Accept/Session/Decline/Cancel.
    assert map_file_change_approval_decision(FileChangeApprovalDecision.ACCEPT) == ReviewDecision.approved()
    assert map_file_change_approval_decision("acceptForSession") == ReviewDecision.approved_for_session()
    assert map_file_change_approval_decision("decline") == ReviewDecision.denied()
    assert map_file_change_approval_decision("cancel") == ReviewDecision.abort()
