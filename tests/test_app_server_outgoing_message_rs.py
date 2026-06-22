from __future__ import annotations

import asyncio

import pytest

from pycodex.app_server.error_code import internal_error
from pycodex.app_server.outgoing_message import (
    ConnectionRequestId,
    OutgoingEnvelope,
    OutgoingMessageKind,
    OutgoingMessageSender,
    RequestContext,
    ThreadScopedOutgoingMessageSender,
)
from pycodex.app_server.server_request_error import TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON
from pycodex.app_server_protocol import JSONRPCErrorError, ServerNotification, ServerRequest, ThreadStatus
from pycodex.protocol import RequestId


async def receive(queue: asyncio.Queue[OutgoingEnvelope]) -> OutgoingEnvelope:
    return await asyncio.wait_for(queue.get(), timeout=1.0)


def notification(type_name: str = "ThreadStatusChanged") -> ServerNotification:
    return ServerNotification(
        type_name,
        {"threadId": "thread-1", "status": ThreadStatus.active().to_mapping()},
    )


@pytest.mark.asyncio
async def test_send_response_routes_to_target_connection() -> None:
    # Rust source: send_response_routes_to_target_connection.
    queue: asyncio.Queue[OutgoingEnvelope] = asyncio.Queue()
    outgoing = OutgoingMessageSender.new(queue)
    request_id = ConnectionRequestId(connection_id=42, request_id=RequestId.integer(7))

    await outgoing.send_response(request_id, {})

    envelope = await receive(queue)
    assert envelope.kind == "ToConnection"
    assert envelope.connection_id == 42
    assert envelope.message.kind is OutgoingMessageKind.RESPONSE
    assert envelope.message.payload.id == RequestId.integer(7)
    assert envelope.message.payload.result == {}


@pytest.mark.asyncio
async def test_send_response_clears_registered_request_context() -> None:
    # Rust source: send_response_clears_registered_request_context.
    queue: asyncio.Queue[OutgoingEnvelope] = asyncio.Queue()
    outgoing = OutgoingMessageSender.new(queue)
    request_id = ConnectionRequestId(connection_id=42, request_id=RequestId.integer(7))

    await outgoing.register_request_context(RequestContext.new(request_id))
    assert await outgoing.request_context_count() == 1

    await outgoing.send_response(request_id, {})

    assert await outgoing.request_context_count() == 0


@pytest.mark.asyncio
async def test_send_error_routes_to_target_connection() -> None:
    # Rust source: send_error_routes_to_target_connection.
    queue: asyncio.Queue[OutgoingEnvelope] = asyncio.Queue()
    outgoing = OutgoingMessageSender.new(queue)
    request_id = ConnectionRequestId(connection_id=9, request_id=RequestId.integer(3))
    error = internal_error("boom")

    await outgoing.send_error(request_id, error)

    envelope = await receive(queue)
    assert envelope.kind == "ToConnection"
    assert envelope.connection_id == 9
    assert envelope.message.kind is OutgoingMessageKind.ERROR
    assert envelope.message.payload.id == RequestId.integer(3)
    assert envelope.message.payload.error == error


@pytest.mark.asyncio
async def test_send_server_notification_to_connection_and_wait_tracks_write_completion() -> None:
    # Rust source: send_server_notification_to_connection_and_wait_tracks_write_completion.
    queue: asyncio.Queue[OutgoingEnvelope] = asyncio.Queue()
    outgoing = OutgoingMessageSender.new(queue)

    send_task = asyncio.create_task(
        outgoing.send_server_notification_to_connection_and_wait(42, notification("ConfigWarning"))
    )

    envelope = await receive(queue)
    assert envelope.kind == "ToConnection"
    assert envelope.connection_id == 42
    assert envelope.message.kind is OutgoingMessageKind.APP_SERVER_NOTIFICATION
    assert envelope.write_complete is not None
    assert not send_task.done()

    envelope.write_complete.set_result(None)

    await asyncio.wait_for(send_task, timeout=1.0)


@pytest.mark.asyncio
async def test_connection_closed_clears_registered_request_contexts() -> None:
    # Rust source: connection_closed_clears_registered_request_contexts.
    outgoing = OutgoingMessageSender.new()
    closed_request = ConnectionRequestId(connection_id=9, request_id=RequestId.integer(3))
    open_request = ConnectionRequestId(connection_id=10, request_id=RequestId.integer(4))

    await outgoing.register_request_context(RequestContext.new(closed_request))
    await outgoing.register_request_context(RequestContext.new(open_request))
    assert await outgoing.request_context_count() == 2

    await outgoing.connection_closed(9)

    assert await outgoing.request_context_count() == 1
    assert await outgoing.request_trace_context(open_request) is None


@pytest.mark.asyncio
async def test_notify_client_error_forwards_error_to_waiter() -> None:
    # Rust source: notify_client_error_forwards_error_to_waiter.
    outgoing = OutgoingMessageSender.new()
    request_id, waiter = await outgoing.send_request(("ApplyPatchApproval", {"callId": "call-id"}))
    error = internal_error("refresh failed")

    await outgoing.notify_client_error(request_id, error)

    assert await asyncio.wait_for(waiter, timeout=1.0) == error


@pytest.mark.asyncio
async def test_pending_requests_for_thread_returns_thread_requests_in_request_id_order() -> None:
    # Rust source: pending_requests_for_thread_returns_thread_requests_in_request_id_order.
    queue: asyncio.Queue[OutgoingEnvelope] = asyncio.Queue()
    outgoing = OutgoingMessageSender.new(queue)
    thread_id = "thread-1"
    thread_outgoing = ThreadScopedOutgoingMessageSender.new(outgoing, [1], thread_id)

    dynamic_tool_request_id, _dynamic_tool_waiter = await thread_outgoing.send_request(
        ("DynamicToolCall", {"threadId": thread_id, "callId": "call-0"})
    )
    first_request_id, _first_waiter = await thread_outgoing.send_request(
        ("ToolRequestUserInput", {"threadId": thread_id, "itemId": "call-1", "questions": []})
    )
    second_request_id, _second_waiter = await thread_outgoing.send_request(
        ("FileChangeRequestApproval", {"threadId": thread_id, "itemId": "call-2"})
    )

    pending_requests = await outgoing.pending_requests_for_thread(thread_id)

    assert [RequestId.from_value(request.request_id) for request in pending_requests] == [
        dynamic_tool_request_id,
        first_request_id,
        second_request_id,
    ]


@pytest.mark.asyncio
async def test_cancel_requests_for_thread_cancels_all_thread_requests() -> None:
    # Rust source: cancel_requests_for_thread_cancels_all_thread_requests.
    outgoing = OutgoingMessageSender.new()
    thread_id = "thread-1"
    thread_outgoing = ThreadScopedOutgoingMessageSender.new(outgoing, [1], thread_id)

    _dynamic_tool_request_id, dynamic_tool_waiter = await thread_outgoing.send_request(
        ("DynamicToolCall", {"threadId": thread_id, "callId": "call-0"})
    )
    _request_id, user_input_waiter = await thread_outgoing.send_request(
        ("ToolRequestUserInput", {"threadId": thread_id, "itemId": "call-1", "questions": []})
    )
    error = internal_error("tracked request cancelled")

    await outgoing.cancel_requests_for_thread(thread_id, error)

    assert await asyncio.wait_for(dynamic_tool_waiter, timeout=1.0) == error
    assert await asyncio.wait_for(user_input_waiter, timeout=1.0) == error
    assert await outgoing.pending_requests_for_thread(thread_id) == []


@pytest.mark.asyncio
async def test_thread_scoped_abort_pending_server_requests_uses_turn_transition_error_reason() -> None:
    # Rust source: ThreadScopedOutgoingMessageSender::abort_pending_server_requests.
    outgoing = OutgoingMessageSender.new()
    thread_outgoing = ThreadScopedOutgoingMessageSender.new(outgoing, [1], "thread-1")
    _request_id, waiter = await thread_outgoing.send_request(("ToolRequestUserInput", {"questions": []}))

    await thread_outgoing.abort_pending_server_requests()

    error = await asyncio.wait_for(waiter, timeout=1.0)
    assert isinstance(error, JSONRPCErrorError)
    assert error.data == {"reason": TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON}


@pytest.mark.asyncio
async def test_replay_requests_to_connection_for_thread_routes_pending_requests() -> None:
    # Rust source: replay_requests_to_connection_for_thread.
    queue: asyncio.Queue[OutgoingEnvelope] = asyncio.Queue()
    outgoing = OutgoingMessageSender.new(queue)
    thread_outgoing = ThreadScopedOutgoingMessageSender.new(outgoing, [1], "thread-1")
    await thread_outgoing.send_request(ServerRequest(type="ToolRequestUserInput", request_id=99, params={}))

    await outgoing.replay_requests_to_connection_for_thread(7, "thread-1")

    await receive(queue)
    replayed = await receive(queue)
    assert replayed.kind == "ToConnection"
    assert replayed.connection_id == 7
    assert replayed.message.kind is OutgoingMessageKind.REQUEST
