from pycodex.core import LastResponse, ModelClient
from pycodex.protocol import ContentItem, ResponseItem


def _message(role: str, text: str) -> ResponseItem:
    return ResponseItem.message(role, (ContentItem.output_text(text),))


def test_prepare_websocket_request_uses_full_payload_without_last_response():
    # Rust source: codex/codex-rs/core/src/client.rs::prepare_websocket_request.
    # Source contract: without a previous LastResponse, send a full ResponseCreate request.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = _message("user", "one")
    request = {"model": "m", "input": [first]}

    prepared, from_warmup = session.prepare_websocket_request(request, request)

    assert from_warmup is False
    assert prepared["type"] == "response.create"
    assert prepared["input"] == [first]
    assert "previous_response_id" not in prepared


def test_prepare_websocket_request_uses_incremental_delta_after_last_response_items():
    # Rust source: codex/codex-rs/core/src/client.rs::get_incremental_items.
    # Source contract: baseline is previous request input plus last response items_added.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = _message("user", "one")
    second = _message("assistant", "two")
    third = _message("user", "three")
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-prev", (second,))
    session.websocket_session.last_response_from_untraced_warmup = True
    request = {"model": "m", "input": [first, second, third]}

    prepared, from_warmup = session.prepare_websocket_request(request, request)

    assert from_warmup is True
    assert prepared["type"] == "response.create"
    assert prepared["previous_response_id"] == "resp-prev"
    assert prepared["input"] == [third]


def test_prepare_websocket_request_falls_back_when_non_input_fields_differ():
    # Rust source: codex/codex-rs/core/src/client.rs::get_incremental_items.
    # Source contract: non-input request fields must match exactly for incremental reuse.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = _message("user", "one")
    second = _message("user", "two")
    session.websocket_session.last_request = {"model": "m", "tool_choice": "auto", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-prev")
    request = {"model": "m", "tool_choice": "none", "input": [first, second]}

    prepared, from_warmup = session.prepare_websocket_request(request, request)

    assert from_warmup is False
    assert prepared["type"] == "response.create"
    assert prepared["input"] == [first, second]
    assert "previous_response_id" not in prepared


def test_prepare_websocket_request_falls_back_when_previous_response_id_is_empty():
    # Rust source: codex/codex-rs/core/src/client.rs::prepare_websocket_request.
    # Source contract: an empty previous response id disables incremental reuse.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = _message("user", "one")
    second = _message("user", "two")
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("")
    request = {"model": "m", "input": [first, second]}

    prepared, from_warmup = session.prepare_websocket_request(request, request)

    assert from_warmup is False
    assert prepared["type"] == "response.create"
    assert prepared["input"] == [first, second]
    assert "previous_response_id" not in prepared


def test_prepare_websocket_request_allows_empty_incremental_delta():
    # Rust source: codex/codex-rs/core/src/client.rs::prepare_websocket_request.
    # Source contract: prepare_websocket_request calls get_incremental_items with
    # allow_empty_delta=true.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = _message("user", "one")
    second = _message("assistant", "two")
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-prev", (second,))
    request = {"model": "m", "input": [first, second]}

    prepared, from_warmup = session.prepare_websocket_request(request, request)

    assert from_warmup is False
    assert prepared["type"] == "response.create"
    assert prepared["previous_response_id"] == "resp-prev"
    assert prepared["input"] == []
