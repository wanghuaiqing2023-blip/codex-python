"""Rust-derived tests for codex-exec-server/src/rpc.rs."""

from __future__ import annotations

import asyncio

import pytest

from pycodex.app_server.error_code import (
    INTERNAL_ERROR_CODE,
    INVALID_PARAMS_ERROR_CODE,
    INVALID_REQUEST_ERROR_CODE,
    METHOD_NOT_FOUND_ERROR_CODE,
)
from pycodex.app_server_protocol import (
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from pycodex.exec_server import (
    RpcCallError,
    RpcClient,
    RpcClientEvent,
    RpcNotificationSender,
    RpcRouter,
    RpcServerOutboundMessage,
    decode_notification_params,
    decode_request_params,
    drain_pending,
    encode_server_message,
    handle_server_message,
    internal_error,
    invalid_params,
    invalid_request,
    method_not_found,
    not_found,
)
from pycodex.protocol import RequestId


def test_rpc_error_helpers_match_rust_codes():
    # Rust: codex-exec-server/src/rpc.rs error helpers
    # Contract: exec-server RPC helpers use JSON-RPC standard codes plus the
    # crate-local not_found code.
    assert invalid_request("bad").code == INVALID_REQUEST_ERROR_CODE
    assert method_not_found("missing").code == METHOD_NOT_FOUND_ERROR_CODE
    assert invalid_params("bad params").code == INVALID_PARAMS_ERROR_CODE
    assert not_found("gone").code == -32004
    assert internal_error("boom").code == INTERNAL_ERROR_CODE
    assert invalid_request("bad").data is None


def test_encode_server_message_matches_jsonrpc_envelopes():
    # Rust: codex-exec-server/src/rpc.rs::encode_server_message
    # Contract: outbound response/error/notification messages project to the
    # corresponding lite JSON-RPC envelope.
    response = encode_server_message(RpcServerOutboundMessage.response(RequestId.integer(1), {"ok": True}))
    error = encode_server_message(
        RpcServerOutboundMessage.error_message(RequestId.integer(2), invalid_request("nope"))
    )
    notification = encode_server_message(
        RpcServerOutboundMessage.notification_message(JSONRPCNotification(method="n", params={"x": 1}))
    )

    assert isinstance(response.value, JSONRPCResponse)
    assert response.to_mapping() == {"id": 1, "result": {"ok": True}}
    assert isinstance(error.value, JSONRPCError)
    assert error.to_mapping() == {"id": 2, "error": {"code": -32600, "message": "nope"}}
    assert notification.to_mapping() == {"method": "n", "params": {"x": 1}}


def test_decode_params_falls_back_empty_object_to_null():
    # Rust: codex-exec-server/src/rpc.rs::decode_params
    # Contract: failed `{}` decoding retries against JSON null so unit-like
    # params can be accepted, while non-empty bad params keep the original
    # invalid_params shape for requests.
    def none_only(value):
        if value is None:
            return "unit"
        raise ValueError("expected null")

    assert decode_request_params({}, none_only) == "unit"
    assert decode_notification_params({}, none_only) == "unit"

    error = decode_request_params({"x": 1}, none_only)
    assert error.code == INVALID_PARAMS_ERROR_CODE
    assert error.message == "expected null"
    assert decode_notification_params({"x": 1}, none_only) == "expected null"


def test_rpc_router_request_and_request_with_id_routes():
    # Rust: codex-exec-server/src/rpc.rs::RpcRouter::request/request_with_id
    # Contract: request routes decode params, call handlers, serialize results,
    # and request_with_id returns no response on success.
    router = RpcRouter.new()
    router.request("add", lambda _state, params: {"sum": params["a"] + params["b"]})
    router.request_with_id("defer", lambda state, request_id, params: state.append((request_id.to_json(), params)))

    async def run():
        response = await router.request_route("add")(
            None,
            JSONRPCRequest(id=1, method="add", params={"a": 2, "b": 3}),
        )
        state = []
        no_response = await router.request_route("defer")(
            state,
            JSONRPCRequest(id="abc", method="defer", params={"ok": True}),
        )
        return response, state, no_response

    response, state, no_response = asyncio.run(run())

    assert response == RpcServerOutboundMessage.response(RequestId.integer(1), {"sum": 5})
    assert state == [("abc", {"ok": True})]
    assert no_response is None


def test_rpc_router_request_decode_error_returns_error_message():
    # Rust: codex-exec-server/src/rpc.rs::RpcRouter::request
    # Contract: request param decode errors become outbound JSON-RPC errors.
    router = RpcRouter.new()
    router.request("unit", lambda _state, params: {"ok": params}, decoder=lambda value: (_ for _ in ()).throw(ValueError("bad")))

    async def run():
        return await router.request_route("unit")(None, JSONRPCRequest(id=7, method="unit", params={"x": 1}))

    response = asyncio.run(run())

    assert response.kind == "error"
    assert response.request_id == RequestId.integer(7)
    assert response.error.code == INVALID_PARAMS_ERROR_CODE
    assert response.error.message == "bad"


def test_rpc_router_notification_route_reports_decode_errors():
    # Rust: codex-exec-server/src/rpc.rs::RpcRouter::notification
    # Contract: notification decode failures return plain error strings.
    router = RpcRouter.new()
    calls = []
    router.notification("note", lambda _state, params: calls.append(params))
    router.notification("bad", lambda _state, params: calls.append(params), decoder=lambda value: (_ for _ in ()).throw(ValueError("bad note")))

    async def run():
        ok = await router.notification_route("note")(None, JSONRPCNotification(method="note", params={"x": 1}))
        bad = await router.notification_route("bad")(None, JSONRPCNotification(method="bad", params={"x": 1}))
        return ok, bad

    ok, bad = asyncio.run(run())

    assert ok is None
    assert bad == "bad note"
    assert calls == [{"x": 1}]


def test_handle_server_message_routes_responses_errors_and_notifications():
    # Rust: codex-exec-server/src/rpc.rs::handle_server_message
    # Contract: responses/errors resolve matching pending requests and
    # notifications are forwarded as client events.
    async def run():
        pending = {}
        events = asyncio.Queue()
        loop = asyncio.get_running_loop()
        ok_future = loop.create_future()
        err_future = loop.create_future()
        pending[RequestId.integer(1)] = ok_future
        pending[RequestId.integer(2)] = err_future
        await handle_server_message(
            pending,
            events,
            JSONRPCMessage(JSONRPCResponse(id=1, result={"ok": True})),
        )
        await handle_server_message(
            pending,
            events,
            JSONRPCMessage(JSONRPCError(id=2, error=invalid_request("server said no"))),
        )
        await handle_server_message(
            pending,
            events,
            JSONRPCMessage(JSONRPCNotification(method="tick", params={"n": 1})),
        )
        return ok_future.result(), err_future, await events.get(), pending

    ok_result, err_future, event, pending = asyncio.run(run())

    assert ok_result == {"ok": True}
    assert err_future.done()
    with pytest.raises(RpcCallError) as exc_info:
        err_future.result()
    assert exc_info.value.kind == "server"
    assert exc_info.value.error.message == "server said no"
    assert event == RpcClientEvent.notification_event(JSONRPCNotification(method="tick", params={"n": 1}))
    assert pending == {}


def test_rpc_client_matches_out_of_order_responses_by_request_id():
    # Rust: codex-exec-server/src/rpc.rs
    # Test: rpc_client_matches_out_of_order_responses_by_request_id
    # Contract: concurrent calls are matched by JSON-RPC request id, not by
    # response arrival order.
    async def run():
        client = RpcClient.new_for_tests()
        slow_task = asyncio.create_task(client.call("slow", {"n": 1}))
        fast_task = asyncio.create_task(client.call("fast", {"n": 2}))

        first = await client.outgoing_tx.get()
        second = await client.outgoing_tx.get()
        requests = {first.value.method: first.value, second.value.method: second.value}
        assert set(requests) == {"slow", "fast"}

        await client.receive_server_message(
            JSONRPCMessage(JSONRPCResponse(id=requests["fast"].id, result={"value": "fast"}))
        )
        await client.receive_server_message(
            JSONRPCMessage(JSONRPCResponse(id=requests["slow"].id, result={"value": "slow"}))
        )
        return await slow_task, await fast_task, client.pending_request_count()

    slow, fast, pending_count = asyncio.run(run())

    assert slow == {"value": "slow"}
    assert fast == {"value": "fast"}
    assert pending_count == 0


def test_drain_pending_fails_unresolved_calls_as_closed():
    # Rust: codex-exec-server/src/rpc.rs::drain_pending
    # Contract: pending calls are failed with RpcCallError::Closed when the
    # transport closes.
    async def run():
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pending = {RequestId.integer(1): future}
        await drain_pending(pending)
        return future, pending

    future, pending = asyncio.run(run())

    assert pending == {}
    with pytest.raises(RpcCallError) as exc_info:
        future.result()
    assert exc_info.value.kind == "closed"
