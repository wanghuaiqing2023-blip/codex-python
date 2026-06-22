from pycodex.app_server.server_request_error import (
    TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON,
    is_turn_transition_server_request_error,
)
from pycodex.app_server_protocol import JSONRPCErrorError


def test_turn_transition_error_is_detected() -> None:
    # Rust: server_request_error.rs::tests::turn_transition_error_is_detected.
    error = JSONRPCErrorError(
        code=-1,
        message="client request resolved because the turn state was changed",
        data={"reason": TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON},
    )

    assert is_turn_transition_server_request_error(error) is True


def test_unrelated_error_is_not_detected() -> None:
    # Rust: server_request_error.rs::tests::unrelated_error_is_not_detected.
    error = JSONRPCErrorError(
        code=-1,
        message="boom",
        data={"reason": "other"},
    )

    assert is_turn_transition_server_request_error(error) is False


def test_missing_or_non_string_reason_is_not_detected() -> None:
    assert is_turn_transition_server_request_error(JSONRPCErrorError(code=-1, message="boom")) is False
    assert is_turn_transition_server_request_error({"data": {"reason": 123}}) is False
    assert is_turn_transition_server_request_error({"data": None}) is False
