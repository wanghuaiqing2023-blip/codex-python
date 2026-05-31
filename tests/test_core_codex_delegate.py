import asyncio
from types import SimpleNamespace

import pytest

from pycodex.core.codex_delegate import (
    CancellationToken,
    RunCodexThreadOptions,
    await_approval_with_cancel,
    event_kind,
    forward_events,
    handle_request_permissions,
    mcp_selected_label_for_decision,
    run_codex_thread_interactive,
)
from pycodex.protocol import (
    Event,
    EventMsg,
    FileSystemPermissions,
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
    options = [SimpleNamespace(label="Yes"), SimpleNamespace(label="Yes, for this session")]

    assert mcp_selected_label_for_decision(ReviewDecision.approved_for_session(), options) == "Yes, for this session"
    assert mcp_selected_label_for_decision(ReviewDecision.denied(), options) == "No"


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
