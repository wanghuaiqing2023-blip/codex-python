from types import SimpleNamespace

from pycodex.core import ModelClient
from pycodex.core.responses_retry import (
    ResponsesStreamRequest,
    RetryableResponseStreamAction,
    response_stream_retry_decision,
)
from pycodex.protocol import CodexErr


def _retryable_stream_error() -> CodexErr:
    return CodexErr.stream("websocket dropped", retry_after=0)


def test_websocket_fallback_switches_to_http_on_upgrade_required_connect() -> None:
    # Rust: core/tests/suite/websocket_fallback.rs::websocket_fallback_switches_to_http_on_upgrade_required_connect.
    decision = response_stream_retry_decision(
        retries=0,
        max_retries=0,
        err=CodexErr.unexpected_status(SimpleNamespace(status=426)),
        request=ResponsesStreamRequest.SAMPLING,
        fallback_transport_available=True,
        responses_websocket_enabled=True,
    )

    assert decision.action is RetryableResponseStreamAction.FALLBACK_TRANSPORT
    assert decision.retries == 0
    assert "Falling back from WebSockets to HTTPS transport." in (decision.warning_message or "")


def test_websocket_fallback_switches_to_http_after_retries_exhausted() -> None:
    # Rust: core/tests/suite/websocket_fallback.rs::websocket_fallback_switches_to_http_after_retries_exhausted.
    first = response_stream_retry_decision(
        retries=0,
        max_retries=2,
        err=_retryable_stream_error(),
        request=ResponsesStreamRequest.SAMPLING,
        fallback_transport_available=True,
        responses_websocket_enabled=True,
        debug_assertions=True,
    )
    second = response_stream_retry_decision(
        retries=1,
        max_retries=2,
        err=_retryable_stream_error(),
        request=ResponsesStreamRequest.SAMPLING,
        fallback_transport_available=True,
        responses_websocket_enabled=True,
        debug_assertions=True,
    )
    fallback = response_stream_retry_decision(
        retries=2,
        max_retries=2,
        err=_retryable_stream_error(),
        request=ResponsesStreamRequest.SAMPLING,
        fallback_transport_available=True,
        responses_websocket_enabled=True,
        debug_assertions=True,
    )

    assert first.action is RetryableResponseStreamAction.RETRY
    assert second.action is RetryableResponseStreamAction.RETRY
    assert fallback.action is RetryableResponseStreamAction.FALLBACK_TRANSPORT
    assert fallback.retries == 0


def test_websocket_fallback_hides_first_websocket_retry_stream_error() -> None:
    # Rust: core/tests/suite/websocket_fallback.rs::websocket_fallback_hides_first_websocket_retry_stream_error.
    first_release_retry = response_stream_retry_decision(
        retries=0,
        max_retries=2,
        err=_retryable_stream_error(),
        request=ResponsesStreamRequest.SAMPLING,
        fallback_transport_available=True,
        responses_websocket_enabled=True,
        debug_assertions=False,
    )
    second_release_retry = response_stream_retry_decision(
        retries=1,
        max_retries=2,
        err=_retryable_stream_error(),
        request=ResponsesStreamRequest.SAMPLING,
        fallback_transport_available=True,
        responses_websocket_enabled=True,
        debug_assertions=False,
    )

    assert first_release_retry.action is RetryableResponseStreamAction.RETRY
    assert first_release_retry.report_error is False
    assert first_release_retry.notify_message is None
    assert second_release_retry.action is RetryableResponseStreamAction.RETRY
    assert second_release_retry.report_error is True
    assert second_release_retry.notify_message == "Reconnecting... 2/2"


def test_websocket_fallback_is_sticky_across_turns() -> None:
    # Rust: core/tests/suite/websocket_fallback.rs::websocket_fallback_is_sticky_across_turns.
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)

    first_turn_session = client.new_session()
    assert client.responses_websocket_enabled() is True
    assert first_turn_session.force_http_fallback() is True
    assert client.responses_websocket_enabled() is False

    second_turn_session = client.new_session()
    assert second_turn_session.preconnect_websocket(connection=object()) == {
        "preconnected": False,
        "reason": "websocket_disabled",
    }
    assert second_turn_session.force_http_fallback() is False
