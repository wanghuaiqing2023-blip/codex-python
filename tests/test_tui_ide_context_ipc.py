from __future__ import annotations

import io

import pytest

from pycodex.tui.ide_context.ipc import (
    TUI_SOURCE_CLIENT_ID,
    IdeContextError,
    answer_unsupported_request,
    extract_ide_context,
    read_frame,
    read_response_frame,
    write_frame,
    write_ide_context_request,
)


def test_error_hints_match_user_facing_branches() -> None:
    assert IdeContextError("Connect", OSError("no socket")).user_facing_hint().startswith(
        "Open this project"
    )
    assert IdeContextError("RequestFailed", "no-client-found").prompt_skip_hint().startswith(
        "Open this project"
    )
    assert "too large" in IdeContextError("ResponseTooLarge").prompt_skip_hint()
    assert "keep trying" in IdeContextError("RequestFailed", "client-disconnected").prompt_skip_hint()
    assert "not compatible" in IdeContextError("RequestFailed", "request-version-mismatch").prompt_skip_hint()


def test_write_ide_context_request_uses_unregistered_route_shape() -> None:
    stream = io.BytesIO()

    write_ide_context_request(stream, "request-1", "/repo")
    stream.seek(0)
    request = read_frame(stream)

    assert request == {
        "type": "request",
        "requestId": "request-1",
        "sourceClientId": TUI_SOURCE_CLIENT_ID,
        "version": 0,
        "method": "ide-context",
        "params": {"workspaceRoot": "/repo"},
    }


def test_answer_unsupported_request_writes_no_handler_response() -> None:
    stream = io.BytesIO()

    answer_unsupported_request(stream, {"type": "request", "requestId": "inbound-request"})
    stream.seek(0)

    assert read_frame(stream) == {
        "type": "response",
        "requestId": "inbound-request",
        "resultType": "error",
        "error": "no-handler-for-request",
    }


def test_read_response_frame_ignores_broadcast_and_answers_discovery_and_requests() -> None:
    stream = io.BytesIO()
    write_frame(stream, {"type": "broadcast", "params": "large ignored data"})
    write_frame(stream, {"type": "client-discovery-request", "requestId": "discovery-request"})
    write_frame(stream, {"type": "request", "requestId": "inbound-request"})
    write_frame(
        stream,
        {
            "type": "response",
            "requestId": "wanted",
            "resultType": "success",
            "result": {"ideContext": {"activeFile": None, "openTabs": []}},
        },
    )
    stream.seek(0)

    response = read_response_frame(stream, "wanted")

    assert response["requestId"] == "wanted"
    stream.seek(0)
    frames = []
    while True:
        try:
            frames.append(read_frame(stream))
        except Exception:
            break
    assert {
        "type": "client-discovery-response",
        "requestId": "discovery-request",
        "response": {"canHandle": False},
    } in frames
    assert {
        "type": "response",
        "requestId": "inbound-request",
        "resultType": "error",
        "error": "no-handler-for-request",
    } in frames


def test_extract_ide_context_success_and_error_shapes() -> None:
    assert extract_ide_context(
        {"resultType": "success", "result": {"ideContext": {"activeFile": None}}}
    ) == {"activeFile": None}
    with pytest.raises(IdeContextError) as excinfo:
        extract_ide_context({"resultType": "error", "error": "request-timeout"})
    assert excinfo.value.kind == "RequestFailed"
    assert excinfo.value.detail == "request-timeout"
