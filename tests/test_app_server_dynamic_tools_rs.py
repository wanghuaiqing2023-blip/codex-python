from pycodex.app_server.dynamic_tools import (
    DYNAMIC_TOOL_INVALID_RESPONSE_MESSAGE,
    DYNAMIC_TOOL_REQUEST_FAILED_MESSAGE,
    core_response_from_app_server_response,
    decode_response,
    fallback_response,
    on_call_response_projection,
)
from pycodex.app_server_protocol.item import DynamicToolCallOutputContentItem, DynamicToolCallResponse


def test_decode_response_accepts_camel_case_dynamic_tool_response() -> None:
    # Rust: codex-app-server/src/dynamic_tools.rs decode_response serde path.
    response, error = decode_response(
        {
            "contentItems": [
                {"type": "inputText", "text": "hello"},
                {"type": "inputImage", "imageUrl": "https://example.test/img.png"},
            ],
            "success": True,
        }
    )

    assert error is None
    assert response.success is True
    assert [item.to_mapping() for item in response.content_items] == [
        {"type": "inputText", "text": "hello"},
        {"type": "inputImage", "imageUrl": "https://example.test/img.png"},
    ]


def test_decode_response_invalid_value_uses_rust_fallback_message() -> None:
    # Rust: failed serde_json::from_value logs and falls back to invalid response text.
    response, error = decode_response({"contentItems": [], "success": "yes"})

    assert error == DYNAMIC_TOOL_INVALID_RESPONSE_MESSAGE
    assert response.to_camel_mapping() == {
        "contentItems": [{"type": "inputText", "text": DYNAMIC_TOOL_INVALID_RESPONSE_MESSAGE}],
        "success": False,
    }


def test_fallback_response_uses_input_text_and_failure_success_flag() -> None:
    # Rust: fallback_response creates a failed DynamicToolCallResponse with one InputText item.
    response, error = fallback_response("dynamic tool request failed")

    assert error == "dynamic tool request failed"
    assert response.to_camel_mapping() == {
        "contentItems": [{"type": "inputText", "text": "dynamic tool request failed"}],
        "success": False,
    }


def test_core_response_from_app_server_response_preserves_items_and_success() -> None:
    # Rust: on_call_response maps app-server content items into core dynamic_tools items.
    response = DynamicToolCallResponse(
        content_items=(
            DynamicToolCallOutputContentItem.input_text("text"),
            DynamicToolCallOutputContentItem.input_image("https://example.test/1.png"),
        ),
        success=True,
    )

    core = core_response_from_app_server_response(response)

    assert core.to_mapping() == {
        "contentItems": [
            {"type": "inputText", "text": "text"},
            {"type": "inputImage", "imageUrl": "https://example.test/1.png"},
        ],
        "success": True,
    }


def test_on_call_response_projection_success_builds_dynamic_tool_response_op() -> None:
    # Rust: Ok(Ok(value)) decodes, converts to core response, and submits Op::DynamicToolResponse.
    projection = on_call_response_projection(
        "call-1",
        {"value": {"contentItems": [{"type": "inputText", "text": "done"}], "success": True}},
    )

    assert projection.ignored_turn_transition is False
    assert projection.fallback_error is None
    assert projection.should_submit is True
    assert projection.op is not None
    assert projection.op.to_mapping() == {
        "type": "dynamic_tool_response",
        "id": "call-1",
        "response": {
            "contentItems": [{"type": "inputText", "text": "done"}],
            "success": True,
        },
    }


def test_on_call_response_projection_turn_transition_error_returns_without_submit() -> None:
    # Rust: turn-transition server request errors are ignored without fallback response submission.
    projection = on_call_response_projection(
        "call-2",
        {"error": {"data": {"reason": "turnTransition"}}},
    )

    assert projection.ignored_turn_transition is True
    assert projection.should_submit is False
    assert projection.app_server_response is None
    assert projection.core_response is None


def test_on_call_response_projection_client_error_uses_request_failed_fallback() -> None:
    # Rust: non-turn-transition client errors log and submit the request-failed fallback.
    projection = on_call_response_projection("call-3", {"error": {"code": -32000}})

    assert projection.ignored_turn_transition is False
    assert projection.fallback_error == DYNAMIC_TOOL_REQUEST_FAILED_MESSAGE
    assert projection.log_error == "request failed with client error"
    assert projection.op is not None
    assert projection.op.to_mapping()["response"] == {
        "contentItems": [{"type": "inputText", "text": DYNAMIC_TOOL_REQUEST_FAILED_MESSAGE}],
        "success": False,
    }


def test_on_call_response_projection_receiver_canceled_uses_request_failed_fallback() -> None:
    # Rust: canceled oneshot receiver logs request failure and submits the same fallback.
    projection = on_call_response_projection("call-4", None, receiver_canceled=True)

    assert projection.fallback_error == DYNAMIC_TOOL_REQUEST_FAILED_MESSAGE
    assert projection.log_error == "request failed"
    assert projection.op is not None
    assert projection.op.to_mapping()["response"]["success"] is False
