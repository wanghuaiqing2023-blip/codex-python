import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.core.codex_delegate import (
    CancellationToken,
    GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT,
    MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION,
    MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC,
    MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX,
    RunCodexThreadOptions,
    SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS,
    await_approval_with_cancel,
    await_request_permissions_with_cancel,
    event_kind,
    forward_events,
    handle_exec_approval,
    handle_patch_approval,
    handle_request_permissions,
    mcp_selected_label_for_decision,
    maybe_auto_review_mcp_request_user_input,
    run_codex_thread_interactive,
)
from pycodex.core.guardian.review import routes_approval_to_guardian
from pycodex.protocol import (
    ApprovalsReviewer,
    AskForApproval,
    Event,
    EventMsg,
    FileChange,
    FileSystemPermissions,
    GranularApprovalConfig,
    NetworkPermissions,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsResponse,
    ReviewDecision,
)


class DummyCodex:
    def __init__(self, events=()):
        self.events = asyncio.Queue()
        for event in events:
            self.events.put_nowait(event)
        self.submitted = []

    async def next_event(self):
        return await self.events.get()

    async def submit(self, op):
        self.submitted.append(op)


def test_event_kind_reads_protocol_event_msg():
    event = Event("1", EventMsg.with_payload("task_complete", {"ok": True}))

    assert event_kind(event) == "task_complete"


def test_mcp_selected_label_prefers_session_approval_when_available():
    options = [
        SimpleNamespace(label="Allow"),
        SimpleNamespace(label=MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION),
    ]

    assert mcp_selected_label_for_decision(ReviewDecision.approved_for_session(), options) == MCP_TOOL_APPROVAL_ACCEPT_FOR_SESSION
    assert mcp_selected_label_for_decision(ReviewDecision.denied(), options) == MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC


@pytest.mark.asyncio
async def test_await_approval_with_cancel_notifies_abort():
    token = CancellationToken()
    notifications = []
    parent_session = SimpleNamespace(notify_approval=lambda approval_id, decision: notifications.append((approval_id, decision)))

    async def never():
        await asyncio.sleep(1)

    token.cancel()
    decision = await await_approval_with_cancel(never(), parent_session, "approval-1", token)

    assert decision == ReviewDecision.abort()
    assert notifications == [("approval-1", ReviewDecision.abort())]


@pytest.mark.asyncio
async def test_forward_events_routes_exec_approval_to_parent_and_submits_decision():
    event = Event(
        "turn-1",
        EventMsg.with_payload(
            "exec_approval_request",
            SimpleNamespace(
                call_id="call-1",
                approval_id=None,
                command=("echo", "hi"),
                cwd="/tmp",
                reason=None,
                network_approval_context=None,
                proposed_execpolicy_amendment=None,
                additional_permissions=None,
                available_decisions=None,
            ),
        ),
    )
    codex = DummyCodex([event])

    async def approve(*args):
        return ReviewDecision.approved()

    parent_session = SimpleNamespace(request_command_approval=approve)
    token = CancellationToken()
    task = asyncio.create_task(forward_events(codex, asyncio.Queue(), parent_session, SimpleNamespace(), {}, token))

    while not codex.submitted:
        await asyncio.sleep(0)
    token.cancel()
    await asyncio.wait_for(task, timeout=0.1)

    assert codex.submitted[0].type == "exec_approval"
    assert codex.submitted[0].fields["id"] == "call-1"
    assert codex.submitted[0].fields["decision"] == ReviewDecision.approved()


@pytest.mark.asyncio
async def test_handle_exec_approval_uses_call_id_for_parent_request_and_approval_id_for_reply():
    # Rust source:
    # codex/codex-rs/core/src/codex_delegate.rs::handle_exec_approval
    # Rust test:
    # codex/codex-rs/core/src/codex_delegate_tests.rs::
    # handle_exec_approval_uses_call_id_for_guardian_review_and_approval_id_for_reply
    codex = DummyCodex()
    observed = []
    available_decisions = (ReviewDecision.approved(), ReviewDecision.abort())

    async def request_command_approval(
        parent_ctx,
        call_id,
        approval_id,
        command,
        cwd,
        reason,
        network_approval_context,
        proposed_execpolicy_amendment,
        additional_permissions,
        available_decisions_arg,
    ):
        observed.append(
            (
                parent_ctx,
                call_id,
                approval_id,
                command,
                cwd,
                reason,
                network_approval_context,
                proposed_execpolicy_amendment,
                additional_permissions,
                available_decisions_arg,
            )
        )
        return ReviewDecision.abort()

    parent_ctx = SimpleNamespace()
    parent_session = SimpleNamespace(request_command_approval=request_command_approval)
    event = SimpleNamespace(
        call_id="command-item-1",
        approval_id="callback-approval-1",
        command=("rm", "-rf", "tmp"),
        cwd="/tmp",
        reason="unsafe subcommand",
        network_approval_context=None,
        proposed_execpolicy_amendment=None,
        additional_permissions=None,
        available_decisions=available_decisions,
    )

    decision = await handle_exec_approval(codex, "child-turn-1", parent_session, parent_ctx, event, CancellationToken())

    assert decision == ReviewDecision.abort()
    assert observed == [
        (
            parent_ctx,
            "command-item-1",
            "callback-approval-1",
            ("rm", "-rf", "tmp"),
            "/tmp",
            "unsafe subcommand",
            None,
            None,
            None,
            available_decisions,
        )
    ]
    assert codex.submitted[0].type == "exec_approval"
    assert codex.submitted[0].fields["id"] == "callback-approval-1"
    assert codex.submitted[0].fields["turn_id"] == "child-turn-1"
    assert codex.submitted[0].fields["decision"] == ReviewDecision.abort()


def test_routes_approval_to_guardian_matches_rust_policy_and_reviewer_gate():
    # Rust source: codex/codex-rs/core/src/guardian/review.rs::routes_approval_to_guardian
    assert routes_approval_to_guardian(
        SimpleNamespace(
            approval_policy=AskForApproval.ON_REQUEST,
            config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW),
        )
    )
    assert routes_approval_to_guardian(
        SimpleNamespace(
            approval_policy=GranularApprovalConfig(
                sandbox_approval=True,
                rules=False,
                mcp_elicitations=False,
            ),
            config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW),
        )
    )
    assert not routes_approval_to_guardian(
        SimpleNamespace(
            approval_policy=AskForApproval.ON_FAILURE,
            config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW),
        )
    )
    assert not routes_approval_to_guardian(
        SimpleNamespace(
            approval_policy=AskForApproval.ON_REQUEST,
            config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.USER),
        )
    )


@pytest.mark.asyncio
async def test_handle_exec_approval_routes_auto_review_to_guardian_hook():
    # Rust source:
    # codex/codex-rs/core/src/codex_delegate.rs::handle_exec_approval guardian branch
    # Rust behavior source:
    # codex/codex-rs/core/src/guardian/review.rs::routes_approval_to_guardian
    codex = DummyCodex()
    observed = []
    review_cancel_seen = []
    additional_permissions = {"network": {"enabled": True}}

    async def review_command_approval(parent_ctx, request, reason, source, review_cancel):
        observed.append((parent_ctx, request, reason, source))
        review_cancel_seen.append(review_cancel)
        return ReviewDecision.abort()

    async def request_command_approval(*_args):
        raise AssertionError("guardian-routed exec approval must not surface to request_command_approval")

    parent_ctx = SimpleNamespace(
        approval_policy=AskForApproval.ON_REQUEST,
        config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW),
    )
    parent_session = SimpleNamespace(
        review_command_approval=review_command_approval,
        request_command_approval=request_command_approval,
    )
    event = SimpleNamespace(
        call_id="command-item-1",
        approval_id="callback-approval-1",
        command=("rm", "-rf", "tmp"),
        cwd="/tmp",
        reason="unsafe subcommand",
        additional_permissions=additional_permissions,
    )

    decision = await handle_exec_approval(codex, "child-turn-1", parent_session, parent_ctx, event, CancellationToken())

    assert decision == ReviewDecision.abort()
    assert len(observed) == 1
    observed_ctx, request, reason, source = observed[0]
    assert observed_ctx is parent_ctx
    assert request.id == "command-item-1"
    assert request.command == ("rm", "-rf", "tmp")
    assert request.cwd == "/tmp"
    assert request.sandbox_permissions == SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS
    assert request.additional_permissions is additional_permissions
    assert request.justification is None
    assert reason == "unsafe subcommand"
    assert source == GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT
    assert review_cancel_seen and isinstance(review_cancel_seen[0], CancellationToken)
    assert codex.submitted[0].type == "exec_approval"
    assert codex.submitted[0].fields["id"] == "callback-approval-1"
    assert codex.submitted[0].fields["turn_id"] == "child-turn-1"
    assert codex.submitted[0].fields["decision"] == ReviewDecision.abort()


@pytest.mark.asyncio
async def test_handle_patch_approval_routes_auto_review_to_guardian_hook():
    # Rust source:
    # codex/codex-rs/core/src/codex_delegate.rs::handle_patch_approval guardian branch
    # Rust behavior source:
    # codex/codex-rs/core/src/guardian/review.rs::routes_approval_to_guardian
    codex = DummyCodex()
    observed = []
    review_cancel_seen = []
    changes = {
        "new.txt": FileChange.add("hello"),
        "old.txt": FileChange.delete("bye"),
        "src/app.py": FileChange.update("@@ -1 +1 @@\n-old\n+new"),
        "move.txt": FileChange.update("@@ -0,0 +1 @@\n+line", move_path=Path("moved.txt")),
    }

    async def review_patch_approval(parent_ctx, request, reason, source, review_cancel):
        observed.append((parent_ctx, request, reason, source))
        review_cancel_seen.append(review_cancel)
        return ReviewDecision.abort()

    async def request_patch_approval(*_args):
        raise AssertionError("guardian-routed patch approval must not surface to request_patch_approval")

    parent_ctx = SimpleNamespace(
        cwd=Path("/repo"),
        approval_policy=AskForApproval.ON_REQUEST,
        config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW),
    )
    parent_session = SimpleNamespace(
        review_patch_approval=review_patch_approval,
        request_patch_approval=request_patch_approval,
    )
    event = SimpleNamespace(
        call_id="patch-call-1",
        changes=changes,
        reason="review patch",
        grant_root=Path("/repo"),
    )

    decision = await handle_patch_approval(codex, "child-turn-1", parent_session, parent_ctx, event, CancellationToken())

    assert decision == ReviewDecision.abort()
    assert len(observed) == 1
    observed_ctx, request, reason, source = observed[0]
    assert observed_ctx is parent_ctx
    assert request.id == "patch-call-1"
    assert request.cwd == Path("/repo")
    assert request.files == tuple(Path("/repo") / Path(path) for path in changes)
    assert request.patch == "\n".join(
        [
            "*** Add File: new.txt\nhello",
            "*** Delete File: old.txt\nbye",
            "*** Update File: src/app.py\n@@ -1 +1 @@\n-old\n+new",
            "*** Update File: move.txt\n*** Move to: moved.txt\n@@ -0,0 +1 @@\n+line",
        ]
    )
    assert reason == "review patch"
    assert source == GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT
    assert review_cancel_seen and isinstance(review_cancel_seen[0], CancellationToken)
    assert codex.submitted[0].type == "patch_approval"
    assert codex.submitted[0].fields["id"] == "patch-call-1"
    assert codex.submitted[0].fields["decision"] == ReviewDecision.abort()


@pytest.mark.asyncio
async def test_delegated_mcp_guardian_abort_returns_synthetic_decline_answer():
    # Rust source:
    # codex/codex-rs/core/src/codex_delegate.rs::maybe_auto_review_mcp_request_user_input
    # Rust test:
    # codex/codex-rs/core/src/codex_delegate_tests.rs::
    # delegated_mcp_guardian_abort_returns_synthetic_decline_answer
    question_id = f"{MCP_TOOL_APPROVAL_QUESTION_ID_PREFIX}_call-1"
    notifications = []

    async def review_mcp_tool_invocation(parent_ctx, call_id, invocation):
        await asyncio.sleep(1)

    async def notify_approval(approval_id, decision):
        notifications.append((approval_id, decision))

    parent_ctx = SimpleNamespace(
        approval_policy=AskForApproval.ON_REQUEST,
        config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW),
    )
    parent_session = SimpleNamespace(
        review_mcp_tool_invocation=review_mcp_tool_invocation,
        notify_approval=notify_approval,
    )
    event = SimpleNamespace(
        call_id="call-1",
        turn_id="child-turn-1",
        questions=[
            SimpleNamespace(
                id=question_id,
                header="Approve app tool call?",
                question="Allow this app tool?",
                is_other=False,
                is_secret=False,
                options=None,
            )
        ],
    )
    cancel_token = CancellationToken()
    cancel_token.cancel()

    response = await maybe_auto_review_mcp_request_user_input(
        parent_session,
        parent_ctx,
        {"call-1": SimpleNamespace(server="custom_server", tool="dangerous_tool", arguments=None)},
        event,
        cancel_token,
    )

    assert response is not None
    assert response.answers[question_id].answers == (MCP_TOOL_APPROVAL_DECLINE_SYNTHETIC,)
    assert notifications == [("call-1", ReviewDecision.abort())]


@pytest.mark.asyncio
async def test_handle_request_permissions_normalizes_parent_response():
    codex = DummyCodex()
    requested_child = "/tmp/requested-child"

    async def request_permissions_for_cwd(parent_ctx, call_id, args, cwd, cancel_token):
        return RequestPermissionsResponse(
            RequestPermissionProfile(
                network=NetworkPermissions(enabled=True),
                file_system=FileSystemPermissions.from_read_write_roots(None, ("/tmp",)),
            ),
            scope=PermissionGrantScope.SESSION,
        )

    parent_session = SimpleNamespace(request_permissions_for_cwd=request_permissions_for_cwd)
    event = SimpleNamespace(
        call_id="perm-1",
        permissions=RequestPermissionProfile(
            network=NetworkPermissions(enabled=True),
            file_system=FileSystemPermissions.from_read_write_roots(None, (requested_child,)),
        ),
        reason=None,
        cwd="/tmp",
    )

    response = await handle_request_permissions(
        codex,
        parent_session,
        SimpleNamespace(cwd="/tmp"),
        event,
        CancellationToken(),
    )

    assert response.permissions.network == NetworkPermissions(enabled=True)
    assert response.permissions.file_system is None
    assert codex.submitted[0].fields["response"] == response


@pytest.mark.asyncio
async def test_handle_request_permissions_rejects_strict_auto_review_session_scope():
    codex = DummyCodex()

    async def request_permissions_for_cwd(parent_ctx, call_id, args, cwd, cancel_token):
        return RequestPermissionsResponse(
            args.permissions,
            scope=PermissionGrantScope.SESSION,
            strict_auto_review=True,
        )

    parent_session = SimpleNamespace(request_permissions_for_cwd=request_permissions_for_cwd)
    event = SimpleNamespace(
        call_id="perm-1",
        permissions=RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
        reason=None,
        cwd="/tmp",
    )

    response = await handle_request_permissions(
        codex,
        parent_session,
        SimpleNamespace(cwd="/tmp"),
        event,
        CancellationToken(),
    )

    assert response == RequestPermissionsResponse(RequestPermissionProfile())
    assert codex.submitted[0].fields["response"] == response


@pytest.mark.asyncio
async def test_handle_request_permissions_uses_tool_call_id_for_round_trip():
    # Rust test source:
    # codex/codex-rs/core/src/codex_delegate_tests.rs
    # handle_request_permissions_uses_tool_call_id_for_round_trip
    codex = DummyCodex()
    captured = {}
    expected_response = RequestPermissionsResponse(
        RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
        scope=PermissionGrantScope.TURN,
    )

    async def request_permissions_for_cwd(parent_ctx, call_id, args, cwd, cancel_token):
        captured["parent_ctx"] = parent_ctx
        captured["call_id"] = call_id
        captured["args"] = args
        captured["cwd"] = cwd
        captured["cancel_token"] = cancel_token
        return expected_response

    parent_session = SimpleNamespace(request_permissions_for_cwd=request_permissions_for_cwd)
    parent_ctx = SimpleNamespace(cwd="/parent-cwd")
    event = SimpleNamespace(
        call_id="tool-call-1",
        permissions=RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
        reason="need access",
        cwd="/delegated-cwd",
    )
    cancel_token = CancellationToken()

    response = await handle_request_permissions(
        codex,
        parent_session,
        parent_ctx,
        event,
        cancel_token,
    )

    assert captured["parent_ctx"] is parent_ctx
    assert captured["call_id"] == "tool-call-1"
    assert captured["args"].reason == "need access"
    assert captured["args"].permissions == event.permissions
    assert captured["cwd"] == "/delegated-cwd"
    assert captured["cancel_token"] is cancel_token
    assert response == expected_response
    assert codex.submitted[0].type == "request_permissions_response"
    assert codex.submitted[0].fields["id"] == "tool-call-1"
    assert codex.submitted[0].fields["response"] == expected_response


@pytest.mark.asyncio
async def test_await_request_permissions_with_cancel_notifies_empty_response():
    # Rust behavior source:
    # codex/codex-rs/core/src/codex_delegate.rs await_request_permissions_with_cancel
    captured = {}

    class ParentSession:
        async def notify_request_permissions_response(self, call_id, response):
            captured["call_id"] = call_id
            captured["response"] = response

    token = CancellationToken()
    token.cancel()
    pending = asyncio.Future()

    response = await await_request_permissions_with_cancel(
        pending,
        ParentSession(),
        "tool-call-cancel",
        token,
    )

    empty = RequestPermissionsResponse(
        RequestPermissionProfile(),
        PermissionGrantScope.TURN,
        False,
    )
    assert response == empty
    assert captured["call_id"] == "tool-call-cancel"
    assert captured["response"] == empty


@pytest.mark.asyncio
async def test_run_codex_thread_interactive_uses_injected_spawn():
    spawned = DummyCodex()

    async def spawn_codex(**kwargs):
        return spawned

    io = await run_codex_thread_interactive(RunCodexThreadOptions(config={"model": "test"}, spawn_codex=spawn_codex))

    await io.submit("op")
    while not spawned.submitted:
        await asyncio.sleep(0)
    io.ops_task.cancel()
    io.event_task.cancel()

    assert io.codex is spawned
    assert spawned.submitted == ["op"]
