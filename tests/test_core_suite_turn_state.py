import json

from pycodex.core import (
    ModelClient,
    TurnState,
    X_CODEX_TURN_METADATA_HEADER,
    X_CODEX_TURN_STATE_HEADER,
    build_responses_headers,
)
from pycodex.core.http_transport import _record_turn_state_from_headers


def _turn_metadata(turn_id: str) -> str:
    return json.dumps({"turn_id": turn_id}, separators=(",", ":"))


def _turn_id_from_header(headers: dict[str, str]) -> str:
    return json.loads(headers[X_CODEX_TURN_METADATA_HEADER])["turn_id"]


def test_responses_turn_state_persists_within_turn_and_resets_after() -> None:
    # Rust: core/tests/suite/turn_state.rs::responses_turn_state_persists_within_turn_and_resets_after.
    first_turn_state = TurnState()
    first_request = build_responses_headers(None, first_turn_state, _turn_metadata("turn-1"))

    _record_turn_state_from_headers(first_turn_state, {X_CODEX_TURN_STATE_HEADER: "ts-1"})
    followup_request = build_responses_headers(None, first_turn_state, _turn_metadata("turn-1"))

    second_turn_state = TurnState()
    next_turn_request = build_responses_headers(None, second_turn_state, _turn_metadata("turn-2"))

    assert X_CODEX_TURN_STATE_HEADER not in first_request
    assert followup_request[X_CODEX_TURN_STATE_HEADER] == "ts-1"
    assert X_CODEX_TURN_STATE_HEADER not in next_turn_request
    assert _turn_id_from_header(first_request) == _turn_id_from_header(followup_request)
    assert _turn_id_from_header(followup_request) != _turn_id_from_header(next_turn_request)


def test_websocket_turn_state_persists_within_turn_and_resets_after() -> None:
    # Rust: core/tests/suite/turn_state.rs::websocket_turn_state_persists_within_turn_and_resets_after.
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    first_turn_state = TurnState()
    first_handshake = client.build_websocket_headers(first_turn_state, _turn_metadata("turn-1"))

    _record_turn_state_from_headers(first_turn_state, {X_CODEX_TURN_STATE_HEADER: "ts-1"})
    followup_handshake = client.build_websocket_headers(first_turn_state, _turn_metadata("turn-1"))

    second_turn_state = TurnState()
    next_turn_handshake = client.build_websocket_headers(second_turn_state, _turn_metadata("turn-2"))

    assert X_CODEX_TURN_STATE_HEADER not in first_handshake
    assert followup_handshake[X_CODEX_TURN_STATE_HEADER] == "ts-1"
    assert X_CODEX_TURN_STATE_HEADER not in next_turn_handshake
    assert _turn_id_from_header(first_handshake) == _turn_id_from_header(followup_handshake)
    assert _turn_id_from_header(followup_handshake) != _turn_id_from_header(next_turn_handshake)
