"""Rust-derived tests for ``codex-api/src/endpoint/responses_websocket.rs``.

Rust crate: ``codex-api``
Rust module: ``src/endpoint/responses_websocket.rs``
Contract: Responses WebSocket helper behavior for wrapped errors, header
mapping, request-header precedence, and websocket config projection.
"""

from __future__ import annotations

import base64
import hashlib
import json
import unittest

from pycodex.codex_api.endpoint.responses_websocket import (
    WEBSOCKET_CONNECTION_LIMIT_REACHED_MESSAGE,
)
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketBinaryMessage
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketCloseMessage
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketClient
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketConnection
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketFrameMessage
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketIdleTimeout
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketMemoryStream
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketPingMessage
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketPongMessage
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketTextMessage
from pycodex.codex_api.endpoint.responses_websocket import connect_websocket
from pycodex.codex_api.endpoint.responses_websocket import json_headers_to_http_headers
from pycodex.codex_api.endpoint.responses_websocket import json_header_value
from pycodex.codex_api.endpoint.responses_websocket import (
    map_wrapped_websocket_error_event,
)
from pycodex.codex_api.endpoint.responses_websocket import merge_request_headers
from pycodex.codex_api.endpoint.responses_websocket import (
    parse_wrapped_websocket_error_event,
)
from pycodex.codex_api.endpoint.responses_websocket import run_websocket_response_stream
from pycodex.codex_api.endpoint.responses_websocket import send_websocket_request
from pycodex.codex_api.endpoint.responses_websocket import websocket_config
from pycodex.codex_api.common import ResponseCreateWsRequest
from pycodex.codex_api.common import ResponsesWsRequest
from pycodex.codex_api.error import ApiError
from pycodex.codex_api.provider import Provider
from pycodex.codex_api.provider import RetryConfig


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


class CodexApiEndpointResponsesWebsocketRsTests(unittest.TestCase):
    def test_websocket_config_enables_permessage_deflate(self) -> None:
        config = websocket_config()

        self.assertTrue(config.permessage_deflate)

    def test_parse_wrapped_websocket_error_event_maps_to_transport_http(self) -> None:
        payload = _json(
            {
                "type": "error",
                "status": 429,
                "error": {
                    "type": "usage_limit_reached",
                    "message": "The usage limit has been reached",
                    "plan_type": "pro",
                    "resets_at": 1738888888,
                },
                "headers": {
                    "x-codex-primary-used-percent": "100.0",
                    "x-codex-primary-window-minutes": 15,
                },
            }
        )

        wrapped_error = parse_wrapped_websocket_error_event(payload)
        api_error = map_wrapped_websocket_error_event(wrapped_error, payload)

        self.assertEqual(api_error.kind, "transport")
        self.assertEqual(api_error.transport.kind, "http")
        self.assertEqual(api_error.transport.status, 429)
        self.assertEqual(api_error.transport.headers["x-codex-primary-used-percent"], "100.0")
        self.assertEqual(api_error.transport.headers["x-codex-primary-window-minutes"], "15")
        self.assertIn("usage_limit_reached", api_error.transport.body)
        self.assertIn("The usage limit has been reached", api_error.transport.body)

    def test_parse_wrapped_websocket_error_event_ignores_non_error_payloads(self) -> None:
        payload = _json({"type": "response.created", "response": {"id": "resp-1"}})

        wrapped_error = parse_wrapped_websocket_error_event(payload)

        self.assertIsNone(wrapped_error)

    def test_parse_wrapped_websocket_error_event_with_status_maps_invalid_request(self) -> None:
        payload = _json(
            {
                "type": "error",
                "status": 400,
                "error": {
                    "type": "invalid_request_error",
                    "message": "Model does not support image inputs",
                },
            }
        )

        wrapped_error = parse_wrapped_websocket_error_event(payload)
        api_error = map_wrapped_websocket_error_event(wrapped_error, payload)

        self.assertEqual(api_error.kind, "transport")
        self.assertEqual(api_error.transport.status, 400)
        self.assertIn("invalid_request_error", api_error.transport.body)
        self.assertIn("Model does not support image inputs", api_error.transport.body)

    def test_parse_wrapped_websocket_error_event_with_connection_limit_maps_retryable(self) -> None:
        payload = _json(
            {
                "type": "error",
                "status": 400,
                "error": {
                    "type": "invalid_request_error",
                    "code": "websocket_connection_limit_reached",
                    "message": WEBSOCKET_CONNECTION_LIMIT_REACHED_MESSAGE,
                },
            }
        )

        wrapped_error = parse_wrapped_websocket_error_event(payload)
        api_error = map_wrapped_websocket_error_event(wrapped_error, payload)

        self.assertEqual(api_error.kind, "retryable")
        self.assertEqual(api_error.message, WEBSOCKET_CONNECTION_LIMIT_REACHED_MESSAGE)
        self.assertIsNone(api_error.delay)

    def test_parse_wrapped_websocket_error_event_with_connection_limit_uses_fallback(self) -> None:
        payload = _json(
            {
                "type": "error",
                "error": {"code": "websocket_connection_limit_reached"},
            }
        )

        wrapped_error = parse_wrapped_websocket_error_event(payload)
        api_error = map_wrapped_websocket_error_event(wrapped_error, payload)

        self.assertEqual(api_error.kind, "retryable")
        self.assertEqual(api_error.message, WEBSOCKET_CONNECTION_LIMIT_REACHED_MESSAGE)

    def test_parse_wrapped_websocket_error_event_without_status_is_not_mapped(self) -> None:
        payload = _json(
            {
                "type": "error",
                "error": {
                    "type": "usage_limit_reached",
                    "message": "The usage limit has been reached",
                },
                "headers": {
                    "x-codex-primary-used-percent": "100.0",
                    "x-codex-primary-window-minutes": 15,
                },
            }
        )

        wrapped_error = parse_wrapped_websocket_error_event(payload)
        api_error = map_wrapped_websocket_error_event(wrapped_error, payload)

        self.assertIsNone(api_error)

    def test_parse_wrapped_websocket_error_event_accepts_status_code_alias(self) -> None:
        payload = _json({"type": "error", "status_code": 503})

        wrapped_error = parse_wrapped_websocket_error_event(payload)
        api_error = map_wrapped_websocket_error_event(wrapped_error, payload)

        self.assertEqual(api_error.transport.status, 503)

    def test_parse_wrapped_websocket_error_event_rejects_status_outside_u16(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: WrappedWebsocketErrorEvent.status is Option<u16>, so JSON
        # statuses outside u16 range fail deserialization before mapping.
        payload = _json({"type": "error", "status": 70000})

        self.assertIsNone(parse_wrapped_websocket_error_event(payload))

    def test_parse_wrapped_websocket_error_event_rejects_invalid_status_type(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: WrappedWebsocketErrorEvent.status is Option<u16>, so wrong
        # JSON types fail serde deserialization for the whole wrapped error
        # event instead of being treated as a missing status.
        for status in ("429", True, 429.5):
            with self.subTest(status=status):
                payload = _json(
                    {
                        "type": "error",
                        "status": status,
                        "error": {"code": "websocket_connection_limit_reached"},
                    }
                )

                self.assertIsNone(parse_wrapped_websocket_error_event(payload))

    def test_map_wrapped_websocket_error_event_ignores_invalid_status_code(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: map_wrapped_websocket_error_event applies
        # StatusCode::from_u16(status?).ok()? before constructing the HTTP
        # transport error.
        payload = _json({"type": "error", "status": 0})
        wrapped_error = parse_wrapped_websocket_error_event(payload)

        api_error = map_wrapped_websocket_error_event(wrapped_error, payload)

        self.assertIsNone(api_error)

    def test_merge_request_headers_matches_http_precedence(self) -> None:
        provider_headers = {
            "originator": "provider-originator",
            "x-priority": "provider",
        }
        extra_headers = {"x-priority": "extra"}
        default_headers = {
            "originator": "default-originator",
            "x-priority": "default",
            "x-default-only": "default-only",
        }

        merged = merge_request_headers(provider_headers, extra_headers, default_headers)

        self.assertEqual(merged["originator"], "provider-originator")
        self.assertEqual(merged["x-priority"], "extra")
        self.assertEqual(merged["x-default-only"], "default-only")

    def test_merge_request_headers_uses_headermap_case_insensitive_precedence(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Rust item: merge_request_headers
        # Contract: Rust HeaderMap extension/retrieval is case-insensitive:
        # extra headers replace provider headers with the same logical name,
        # while default headers do not replace an existing provider/extra name.
        provider_headers = {
            "Originator": "provider-originator",
            "X-Priority": "provider",
        }
        extra_headers = {
            "x-priority": "extra",
        }
        default_headers = {
            "originator": "default-originator",
            "X-Priority": "default",
            "X-Default-Only": "default-only",
        }

        merged = merge_request_headers(provider_headers, extra_headers, default_headers)
        lower = {key.lower(): value for key, value in merged.items()}

        self.assertEqual(lower["originator"], "provider-originator")
        self.assertEqual(lower["x-priority"], "extra")
        self.assertEqual(lower["x-default-only"], "default-only")
        self.assertNotIn("X-Priority", merged)

    def test_json_header_value_accepts_scalar_strings_numbers_and_bools(self) -> None:
        self.assertEqual(json_header_value("x"), "x")
        self.assertEqual(json_header_value(15), "15")
        self.assertEqual(json_header_value(True), "true")
        self.assertIsNone(json_header_value(["not", "scalar"]))

    def test_json_headers_to_http_headers_filters_invalid_names_and_values(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: json_headers_to_http_headers only inserts entries when
        # HeaderName::from_bytes and HeaderValue::from_str both succeed.
        mapped = json_headers_to_http_headers(
            {
                "x-ok": "yes",
                "bad:name": "ignored",
                "x-newline": "line\nbreak",
                "x-nul": "bad\0value",
                "x-nonascii": "snowman \u2603",
                "x-number": 15,
                "x-bool": False,
                "x-array": ["ignored"],
            }
        )

        self.assertEqual(
            mapped,
            {
                "x-ok": "yes",
                "x-number": "15",
                "x-bool": "false",
            },
        )

    def test_send_websocket_request_serializes_compact_json_and_records_telemetry(self) -> None:
        telemetry = _Telemetry()
        stream = ResponsesWebsocketMemoryStream()

        send_websocket_request(
            stream,
            {"type": "response.create", "model": "gpt-5.3-codex"},
            telemetry=telemetry,
            connection_reused=True,
        )

        self.assertEqual(
            stream.sent_payloads,
            ['{"type":"response.create","model":"gpt-5.3-codex"}'],
        )
        self.assertEqual(telemetry.requests, [(None, True)])

    def test_send_websocket_request_maps_send_error(self) -> None:
        telemetry = _Telemetry()
        stream = ResponsesWebsocketMemoryStream(send_error=RuntimeError("send failed"))

        with self.assertRaises(ApiError) as caught:
            send_websocket_request(stream, {"type": "response.create"}, telemetry=telemetry)

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, "failed to send websocket request: send failed")
        self.assertEqual(telemetry.requests, [("failed to send websocket request: send failed", False)])

    def test_send_websocket_request_uses_idle_timeout_boundary(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: send_websocket_request wraps ws_stream.send(...) in
        # tokio::time::timeout(idle_timeout, ...), so the send boundary observes
        # idle_timeout and timeout errors map to the Rust stream message.
        telemetry = _Telemetry()
        stream = _TimeoutAwareSendStream(ResponsesWebsocketIdleTimeout("send"))

        with self.assertRaises(ApiError) as caught:
            send_websocket_request(
                stream,
                {"type": "response.create"},
                idle_timeout=7.5,
                telemetry=telemetry,
                connection_reused=True,
            )

        self.assertEqual(stream.calls, [('{"type":"response.create"}', 7.5)])
        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, "idle timeout sending websocket request")
        self.assertEqual(telemetry.requests, [("idle timeout sending websocket request", True)])

    def test_stdlib_stream_send_with_timeout_restores_socket_timeout(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: send_websocket_request wraps the concrete WsStream send in
        # tokio::time::timeout, so the real stdlib stream projection also
        # observes the idle_timeout send boundary and restores socket state.
        from pycodex.codex_api.endpoint import responses_websocket as module

        fake_socket = _FakeHandshakeSocket(b"", send_error=TimeoutError("send timed out"))
        fake_socket.timeout = 12.0
        stream = module._StdlibResponsesWebsocketStream(fake_socket)
        telemetry = _Telemetry()

        with self.assertRaises(ApiError) as caught:
            send_websocket_request(
                stream,
                {"type": "response.create"},
                idle_timeout=0.125,
                telemetry=telemetry,
                connection_reused=True,
            )

        self.assertEqual(fake_socket.timeout_history, [0.125, 12.0])
        self.assertEqual(fake_socket.gettimeout(), 12.0)
        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, "idle timeout sending websocket request")
        self.assertEqual(telemetry.requests, [("idle timeout sending websocket request", True)])

    def test_run_websocket_response_stream_maps_events_until_completed(self) -> None:
        stream = ResponsesWebsocketMemoryStream(
            [
                ResponsesWebsocketPingMessage(),
                ResponsesWebsocketPongMessage(),
                ResponsesWebsocketFrameMessage(),
                ResponsesWebsocketTextMessage("{not json"),
                ResponsesWebsocketTextMessage(
                    _json(
                        {
                            "type": "codex.rate_limits",
                            "rate_limits": {"primary": {"used_percent": 42.5}},
                            "credits": {"has_credits": True, "unlimited": False},
                        }
                    )
                ),
                ResponsesWebsocketTextMessage(
                    _json(
                        {
                            "type": "response.created",
                            "headers": {"openai-model": "gpt-5.3-codex"},
                            "response": {},
                        }
                    )
                ),
                ResponsesWebsocketTextMessage(
                    _json(
                        {
                            "type": "response.metadata",
                            "metadata": {
                                "openai_verification_recommendation": [
                                    "trusted_access_for_cyber"
                                ]
                            },
                        }
                    )
                ),
                ResponsesWebsocketTextMessage(
                    _json(
                        {
                            "type": "response.output_text.delta",
                            "delta": "hi",
                        }
                    )
                ),
                ResponsesWebsocketTextMessage(
                    _json(
                        {
                            "type": "response.completed",
                            "response": {"id": "resp-1", "end_turn": True},
                        }
                    )
                ),
            ]
        )

        events = run_websocket_response_stream(
            stream,
            {"type": "response.create", "model": "gpt-5.3-codex"},
            connection_reused=False,
        )

        self.assertEqual(json.loads(stream.sent_payloads[0])["type"], "response.create")
        self.assertEqual([event.kind for event in events], [
            "rate_limits",
            "server_model",
            "created",
            "model_verifications",
            "output_text_delta",
            "completed",
        ])
        self.assertEqual(events[0].value.primary.used_percent, 42.5)
        self.assertEqual(events[1].value, "gpt-5.3-codex")
        self.assertEqual(events[3].value, ["trusted_access_for_cyber"])
        self.assertEqual(events[-1].value["response_id"], "resp-1")

    def test_run_websocket_response_stream_maps_wrapped_error_before_event_parse(self) -> None:
        payload = _json(
            {
                "type": "error",
                "status": 429,
                "error": {"message": "limit"},
            }
        )
        stream = ResponsesWebsocketMemoryStream([payload])

        with self.assertRaises(ApiError) as caught:
            run_websocket_response_stream(stream, {"type": "response.create"})

        self.assertEqual(caught.exception.kind, "transport")
        self.assertEqual(caught.exception.transport.status, 429)

    def test_run_websocket_response_stream_terminal_errors(self) -> None:
        cases = [
            (
                [ResponsesWebsocketBinaryMessage(b"\x00")],
                "unexpected binary websocket event",
            ),
            (
                [ResponsesWebsocketCloseMessage()],
                "websocket closed by server before response.completed",
            ),
            (
                [],
                "stream closed before response.completed",
            ),
            (
                [ResponsesWebsocketIdleTimeout("read")],
                "idle timeout waiting for websocket",
            ),
            (
                [RuntimeError("read failed")],
                "read failed",
            ),
        ]
        for messages, expected in cases:
            with self.subTest(expected=expected):
                stream = ResponsesWebsocketMemoryStream(messages)
                with self.assertRaises(ApiError) as caught:
                    run_websocket_response_stream(stream, {"type": "response.create"})
                self.assertEqual(caught.exception.kind, "stream")
                self.assertEqual(caught.exception.message, expected)

    def test_run_websocket_response_stream_uses_read_idle_timeout(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs.
        # Contract: websocket stream reads are bounded by the provider stream
        # idle timeout and surface an idle-timeout stream error instead of
        # blocking the caller indefinitely.
        class TimeoutReadStream(ResponsesWebsocketMemoryStream):
            def __init__(self) -> None:
                super().__init__()
                self.observed_timeouts: list[float | None] = []

            def next_with_timeout(self, timeout: float | None):
                self.observed_timeouts.append(timeout)
                raise ResponsesWebsocketIdleTimeout("read")

        stream = TimeoutReadStream()

        with self.assertRaises(ApiError) as caught:
            run_websocket_response_stream(stream, {"type": "response.create"}, idle_timeout=0.25)

        self.assertEqual(stream.observed_timeouts, [0.25])
        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, "idle timeout waiting for websocket")

    def test_connection_stream_request_prepends_server_metadata_and_closes_on_error(self) -> None:
        connection = ResponsesWebsocketConnection(
            ResponsesWebsocketMemoryStream([ResponsesWebsocketBinaryMessage(b"\x00")]),
            server_reasoning_included=True,
            models_etag="etag-1",
            server_model="gpt-5.3-codex",
        )
        request = ResponsesWsRequest.response_create(ResponseCreateWsRequest(model="gpt"))

        stream = connection.stream_request(request, connection_reused=True)
        events = list(stream)

        self.assertEqual([event.kind for event in events[:3]], [
            "server_model",
            "models_etag",
            "server_reasoning_included",
        ])
        self.assertIsInstance(events[-1], ApiError)
        self.assertEqual(events[-1].message, "unexpected binary websocket event")
        self.assertTrue(connection.is_closed())

    def test_connection_stream_request_is_lazy_for_live_deltas(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs.
        # Contract: websocket response events are yielded as frames arrive; the
        # caller does not wait for response.completed before observing deltas.
        class CountingStream:
            def __init__(self):
                self.sent_payloads = []
                self.messages = iter([
                    ResponsesWebsocketTextMessage(
                        json.dumps({"type": "response.output_text.delta", "delta": "live"})
                    ),
                    ResponsesWebsocketTextMessage(
                        json.dumps(
                            {
                                "type": "response.completed",
                                "response": {"id": "resp-lazy", "end_turn": True, "usage": {}},
                            }
                        )
                    ),
                ])
                self.next_calls = 0

            def send(self, payload: str) -> None:
                self.sent_payloads.append(payload)

            def next(self):
                self.next_calls += 1
                return next(self.messages, None)

        memory = CountingStream()
        connection = ResponsesWebsocketConnection(memory)
        request = ResponsesWsRequest.response_create(ResponseCreateWsRequest(model="gpt"))

        stream = connection.stream_request(request, connection_reused=False)
        first = next(iter(stream))

        self.assertEqual(first.kind, "output_text_delta")
        self.assertEqual(first.value, "live")
        self.assertEqual(memory.next_calls, 1)

    def test_connection_send_response_processed_and_closed_error(self) -> None:
        memory = ResponsesWebsocketMemoryStream()
        connection = ResponsesWebsocketConnection(memory)

        connection.send_response_processed("resp-1")

        self.assertEqual(json.loads(memory.sent_payloads[0]), {
            "response_id": "resp-1",
            "type": "response.processed",
        })

        connection.stream = None
        with self.assertRaises(ApiError) as caught:
            connection.send_response_processed("resp-2")
        self.assertEqual(caught.exception.message, "websocket connection is closed")

    def test_client_connect_builds_url_headers_auth_and_turn_state(self) -> None:
        captures: list[tuple[str, dict[str, str], object]] = []

        def connector(url: str, headers: dict[str, str], turn_state: object):
            captures.append((url, dict(headers), turn_state))
            if isinstance(turn_state, dict):
                turn_state["value"] = "turn-1"
            return (
                ResponsesWebsocketMemoryStream(),
                101,
                True,
                "etag-1",
                "gpt-5.3-codex",
            )

        turn_state: dict[str, str] = {}
        client = ResponsesWebsocketClient.new(
            _provider(),
            _Auth("token-1"),
            connector,
        )

        connection = client.connect(
            extra_headers={"x-priority": "extra"},
            default_headers={"originator": "default", "x-default-only": "yes"},
            turn_state=turn_state,
            telemetry="telemetry",
        )

        self.assertEqual(captures[0][0], "wss://api.example.test/v1/responses?api-version=1")
        self.assertEqual(captures[0][1]["x-priority"], "extra")
        self.assertEqual(captures[0][1]["originator"], "provider")
        self.assertEqual(captures[0][1]["x-default-only"], "yes")
        self.assertEqual(captures[0][1]["authorization"], "Bearer token-1")
        self.assertEqual(turn_state["value"], "turn-1")
        self.assertFalse(connection.is_closed())
        self.assertTrue(connection.server_reasoning_included)
        self.assertEqual(connection.models_etag, "etag-1")
        self.assertEqual(connection.server_model, "gpt-5.3-codex")
        self.assertEqual(connection.telemetry, "telemetry")

    def test_client_connect_passes_optional_timeout_to_connector(self) -> None:
        # Rust crate/modules:
        # - codex-core/src/client.rs::ModelClient::connect_websocket wraps the
        #   codex-api connect future in provider.websocket_connect_timeout().
        # - codex-api/src/endpoint/responses_websocket.rs owns the concrete
        #   websocket connector boundary.
        # Contract: Python's codex-api client must expose the connect timeout
        # to the concrete connector so core can enforce the Rust timeout.
        seen: dict[str, float | None] = {}

        def connector(
            url: str,
            headers: dict[str, str],
            turn_state: object,
            *,
            timeout: float | None = None,
        ):
            del url, headers, turn_state
            seen["timeout"] = timeout
            return (ResponsesWebsocketMemoryStream(), 101, False, None, None)

        client = ResponsesWebsocketClient.new(_provider(), _Auth("token-1"), connector)

        client.connect(timeout=15.0)

        self.assertEqual(seen["timeout"], 15.0)

    def test_client_probe_reports_upgrade_metadata_and_immediate_close(self) -> None:
        def connector(url: str, headers: dict[str, str], turn_state: object):
            del headers, turn_state
            self.assertEqual(url, "wss://api.example.test/v1/responses?api-version=1")
            return (
                ResponsesWebsocketMemoryStream(
                    [ResponsesWebsocketCloseMessage("4000", "policy")]
                ),
                101,
                True,
                "etag-1",
                "gpt-5.3-codex",
            )

        client = ResponsesWebsocketClient.new(_provider(), _Auth("token-1"), connector)

        probe = client.probe_handshake(immediate_close_timeout=0.01)

        self.assertEqual(probe.url, "wss://api.example.test/v1/responses?api-version=1")
        self.assertEqual(probe.status, 101)
        self.assertTrue(probe.reasoning_included)
        self.assertTrue(probe.models_etag_present)
        self.assertTrue(probe.server_model_present)
        self.assertEqual(probe.immediate_close.code, "4000")
        self.assertEqual(probe.immediate_close.reason, "policy")

    def test_client_probe_timeout_without_close_is_not_an_error(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: probe_handshake wraps the immediate-close read in
        # tokio::time::timeout(...).await.ok().flatten().transpose(), so a
        # timeout while waiting for an immediate close frame is reported as
        # immediate_close=None rather than an ApiError.
        class TimeoutProbeStream(ResponsesWebsocketMemoryStream):
            def next_with_timeout(self, timeout: float | None):
                self.observed_timeout = timeout
                raise ResponsesWebsocketIdleTimeout("probe")

        probe_stream = TimeoutProbeStream()

        def connector(url: str, headers: dict[str, str], turn_state: object):
            del url, headers, turn_state
            return (probe_stream, 101, False, None, None)

        client = ResponsesWebsocketClient.new(_provider(), _Auth("token-1"), connector)

        probe = client.probe_handshake(immediate_close_timeout=0.25)

        self.assertEqual(probe.status, 101)
        self.assertFalse(probe.reasoning_included)
        self.assertFalse(probe.models_etag_present)
        self.assertFalse(probe.server_model_present)
        self.assertIsNone(probe.immediate_close)
        self.assertEqual(probe_stream.observed_timeout, 0.25)

    def test_client_probe_maps_probe_read_error(self) -> None:
        def connector(url: str, headers: dict[str, str], turn_state: object):
            del url, headers, turn_state
            return (ResponsesWebsocketMemoryStream([RuntimeError("boom")]), 101, False, None, None)

        client = ResponsesWebsocketClient.new(_provider(), _Auth("token-1"), connector)

        with self.assertRaises(ApiError) as caught:
            client.probe_handshake()

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(caught.exception.message, "failed to read websocket probe event: boom")

    def test_connect_websocket_formats_ipv6_host_header_and_request_target(
        self,
    ) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: connect_websocket builds the request through
        # url.as_str().into_client_request(), so the HTTP request target uses
        # path + query without a fragment and IPv6 Host authorities remain
        # bracketed.
        fixed_nonce = b"\x01" * 16
        key = base64.b64encode(fixed_nonce).decode("ascii")
        accept = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
            ).digest()
        ).decode("ascii")
        fake_socket = _FakeHandshakeSocket(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            ).encode("ascii")
        )

        from pycodex.codex_api.endpoint import responses_websocket as module

        original_create_connection = module.socket.create_connection
        original_urandom = module.os.urandom
        try:
            module.socket.create_connection = lambda address, timeout=None: fake_socket
            module.os.urandom = lambda size: fixed_nonce

            stream, status, reasoning, models_etag, server_model = module._connect_websocket_stdlib(
                "ws://[::1]:9000/v1/responses?api-version=1#ignored",
                {"x-test": "1"},
            )
        finally:
            module.socket.create_connection = original_create_connection
            module.os.urandom = original_urandom

        self.assertEqual(status, 101)
        self.assertFalse(reasoning)
        self.assertIsNone(models_etag)
        self.assertIsNone(server_model)
        self.assertIsNotNone(stream)
        request_text = fake_socket.sent.decode("ascii")
        self.assertTrue(request_text.startswith("GET /v1/responses?api-version=1 HTTP/1.1\r\n"))
        self.assertIn("Host: [::1]:9000\r\n", request_text)
        self.assertIn("x-test: 1\r\n", request_text)
        self.assertNotIn("ignored", request_text)

    def test_connect_websocket_101_metadata_headers_and_turn_state(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: connect_websocket reads successful upgrade headers for
        # x-codex-turn-state, x-reasoning-included, x-models-etag, and
        # openai-model. HeaderMap lookup is case-insensitive and valid string
        # values are projected into the connection metadata tuple.
        fixed_nonce = b"\x04" * 16
        key = base64.b64encode(fixed_nonce).decode("ascii")
        accept = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
            ).digest()
        ).decode("ascii")
        fake_socket = _FakeHandshakeSocket(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "X-Codex-Turn-State: turn-updated\r\n"
                "X-Reasoning-Included: true\r\n"
                "X-Models-Etag: models-v7\r\n"
                "OpenAI-Model: gpt-5.3-codex\r\n"
                "\r\n"
            ).encode("ascii")
        )
        turn_state: dict[str, str] = {}

        from pycodex.codex_api.endpoint import responses_websocket as module

        original_create_connection = module.socket.create_connection
        original_urandom = module.os.urandom
        try:
            module.socket.create_connection = lambda address, timeout=None: fake_socket
            module.os.urandom = lambda size: fixed_nonce

            stream, status, reasoning, models_etag, server_model = module._connect_websocket_stdlib(
                "ws://api.example.test/v1/responses",
                {},
                turn_state,
            )
        finally:
            module.socket.create_connection = original_create_connection
            module.os.urandom = original_urandom

        self.assertIsNotNone(stream)
        self.assertEqual(status, 101)
        self.assertTrue(reasoning)
        self.assertEqual(models_etag, "models-v7")
        self.assertEqual(server_model, "gpt-5.3-codex")
        self.assertEqual(turn_state, {"value": "turn-updated"})

    def test_connect_websocket_101_requires_upgrade_and_connection_headers(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Rust item: connect_websocket
        # Contract: Rust delegates successful HTTP 101 validation to
        # tungstenite, which requires both the websocket Upgrade token and the
        # Connection: Upgrade token before accepting the stream.
        fixed_nonce = b"\x03" * 16
        key = base64.b64encode(fixed_nonce).decode("ascii")
        accept = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
            ).digest()
        ).decode("ascii")
        cases = [
            (
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n"
                    "\r\n"
                ).encode("ascii"),
                "invalid websocket upgrade header",
            ),
            (
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n"
                    "\r\n"
                ).encode("ascii"),
                "invalid websocket connection header",
            ),
        ]

        from pycodex.codex_api.endpoint import responses_websocket as module

        original_create_connection = module.socket.create_connection
        original_urandom = module.os.urandom
        try:
            module.os.urandom = lambda size: fixed_nonce
            for response, expected in cases:
                with self.subTest(expected=expected):
                    fake_socket = _FakeHandshakeSocket(response)
                    module.socket.create_connection = lambda address, timeout=None: fake_socket
                    with self.assertRaises(ApiError) as caught:
                        module._connect_websocket_stdlib("ws://api.example.test/v1/responses", {})
                    self.assertEqual(caught.exception.kind, "stream")
                    self.assertIn(expected, caught.exception.message)
        finally:
            module.socket.create_connection = original_create_connection
            module.os.urandom = original_urandom

    def test_connect_websocket_wss_uses_custom_ca_ssl_context(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: connect_websocket calls
        # maybe_build_rustls_client_config_with_custom_ca() and supplies the
        # resulting TLS connector to connect_async_tls_with_config, so secure
        # websocket connections honor the same custom-CA policy as HTTPS.
        captures: dict[str, object] = {}
        fake_bundle = _FakeCaBundle("C:/ca/custom.pem")

        class FakeSslContext:
            pass

        def fake_connect_vendored(url, headers, *, ssl_context=None, timeout=None, max_message_size=None):
            captures["url"] = url
            captures["headers"] = headers
            captures["ssl_context"] = ssl_context
            captures["timeout"] = timeout
            captures["max_message_size"] = max_message_size
            return (
                ResponsesWebsocketMemoryStream(),
                101,
                {"x-reasoning-included": "true", "x-models-etag": "models", "openai-model": "gpt"},
            )

        from pycodex.codex_api.endpoint import responses_websocket as module

        original_configured_ca_bundle = module.configured_ca_bundle
        original_create_default_context = module.ssl.create_default_context
        original_connect_vendored = module.connect_vendored_websocket
        try:
            module.configured_ca_bundle = lambda env_source: fake_bundle
            module.ssl.create_default_context = lambda cafile=None: captures.update(
                {"cafile": cafile}
            ) or FakeSslContext()
            module.connect_vendored_websocket = fake_connect_vendored

            stream, status, reasoning, models_etag, server_model = connect_websocket(
                "wss://api.example.test/v1/responses",
                {},
                timeout=4.0,
            )
        finally:
            module.configured_ca_bundle = original_configured_ca_bundle
            module.ssl.create_default_context = original_create_default_context
            module.connect_vendored_websocket = original_connect_vendored

        self.assertEqual(status, 101)
        self.assertTrue(reasoning)
        self.assertEqual(models_etag, "models")
        self.assertEqual(server_model, "gpt")
        self.assertIsNotNone(stream)
        self.assertTrue(fake_bundle.loaded)
        self.assertEqual(captures["cafile"], "C:/ca/custom.pem")
        self.assertEqual(captures["timeout"], 4.0)
        self.assertEqual(captures["url"], "wss://api.example.test/v1/responses")
        self.assertIsInstance(captures["ssl_context"], FakeSslContext)

    def test_connect_websocket_custom_ca_error_is_stream_error(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: custom-CA connector construction failures map to
        # ApiError::Stream("failed to configure websocket TLS: ...").
        from pycodex.codex_api.endpoint import responses_websocket as module

        original_configured_ca_bundle = module.configured_ca_bundle
        original_create_connection = module.socket.create_connection
        try:
            module.configured_ca_bundle = lambda env_source: _FailingCaBundle()
            module.socket.create_connection = lambda address, timeout=None: self.fail(
                "socket connection should not be attempted"
            )

            with self.assertRaises(ApiError) as caught:
                connect_websocket("wss://api.example.test/v1/responses", {})
        finally:
            module.configured_ca_bundle = original_configured_ca_bundle
            module.socket.create_connection = original_create_connection

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(
            caught.exception.message,
            "failed to configure websocket TLS: bad ca",
        )

    def test_connect_websocket_non_101_invalid_utf8_body_is_none(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: map_ws_error(WsError::Http) projects the HTTP error body
        # through String::from_utf8(...).ok(), so invalid UTF-8 clears the
        # optional TransportError::Http body instead of decoding lossily.
        fake_socket = _FakeHandshakeSocket(
            (
                b"HTTP/1.1 403 Forbidden\r\n"
                b"content-type: text/plain\r\n"
                b"\r\n"
                b"denied:\xff"
            )
        )

        from pycodex.codex_api.endpoint import responses_websocket as module

        original_create_connection = module.socket.create_connection
        try:
            module.socket.create_connection = lambda address, timeout=None: fake_socket

            with self.assertRaises(ApiError) as caught:
                module._connect_websocket_stdlib("ws://api.example.test/v1/responses", {})
        finally:
            module.socket.create_connection = original_create_connection

        err = caught.exception
        self.assertEqual(err.kind, "transport")
        self.assertEqual(err.transport.kind, "http")
        self.assertEqual(err.transport.status, 403)
        self.assertEqual(err.transport.url, "ws://api.example.test/v1/responses")
        self.assertEqual(err.transport.headers, {"content-type": "text/plain"})
        self.assertIsNone(err.transport.body)

    def test_connect_websocket_non_101_valid_utf8_body_is_preserved(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: map_ws_error(WsError::Http) preserves status, URL,
        # headers, and a valid UTF-8 body when constructing
        # TransportError::Http for a websocket upgrade HTTP response.
        fake_socket = _FakeHandshakeSocket(
            (
                b"HTTP/1.1 429 Too Many Requests\r\n"
                b"retry-after: 7\r\n"
                b"\r\n"
                b"slow down"
            )
        )

        from pycodex.codex_api.endpoint import responses_websocket as module

        original_create_connection = module.socket.create_connection
        try:
            module.socket.create_connection = lambda address, timeout=None: fake_socket

            with self.assertRaises(ApiError) as caught:
                module._connect_websocket_stdlib("ws://api.example.test/v1/responses?api-version=1", {})
        finally:
            module.socket.create_connection = original_create_connection

        err = caught.exception
        self.assertEqual(err.kind, "transport")
        self.assertEqual(err.transport.kind, "http")
        self.assertEqual(err.transport.status, 429)
        self.assertEqual(
            err.transport.url,
            "ws://api.example.test/v1/responses?api-version=1",
        )
        self.assertEqual(err.transport.headers, {"retry-after": "7"})
        self.assertEqual(err.transport.body, "slow down")

    def test_connect_websocket_non_101_reads_content_length_body_after_headers(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: map_ws_error(WsError::Http) receives tungstenite's full
        # HTTP response body, so valid UTF-8 bodies remain available even when
        # they arrive after the header read boundary.
        fake_socket = _FakeChunkedHandshakeSocket(
            [
                (
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"content-length: 9\r\n"
                    b"x-reason: retry\r\n"
                    b"\r\n"
                ),
                b"try ",
                b"later",
                b"extra bytes for a following response",
            ]
        )

        from pycodex.codex_api.endpoint import responses_websocket as module

        original_create_connection = module.socket.create_connection
        try:
            module.socket.create_connection = lambda address, timeout=None: fake_socket

            with self.assertRaises(ApiError) as caught:
                module._connect_websocket_stdlib("ws://api.example.test/v1/responses", {})
        finally:
            module.socket.create_connection = original_create_connection

        err = caught.exception
        self.assertEqual(err.kind, "transport")
        self.assertEqual(err.transport.kind, "http")
        self.assertEqual(err.transport.status, 503)
        self.assertEqual(err.transport.headers["content-length"], "9")
        self.assertEqual(err.transport.headers["x-reason"], "retry")
        self.assertEqual(err.transport.body, "try later")

    def test_stdlib_stream_auto_pongs_and_filters_ping_pong_frames(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: WsStream::new responds to Message::Ping with Pong, drops
        # Message::Pong, and only forwards text/binary/close/frame messages to
        # callers.
        from pycodex.codex_api.endpoint import responses_websocket as module

        fake_socket = _FakeHandshakeSocket(
            _server_frame(0x9, b"hi")
            + _server_frame(0xA, b"ignored")
            + _server_frame(0x1, b'{"type":"response.created"}')
        )
        stream = module._StdlibResponsesWebsocketStream(fake_socket)

        message = stream.next()

        self.assertIsInstance(message, ResponsesWebsocketTextMessage)
        self.assertEqual(message.text, '{"type":"response.created"}')
        self.assertEqual(_masked_client_frame_payload(fake_socket.sent), (0xA, b"hi"))

    def test_immediate_close_from_message_ignores_non_close_or_empty_close(self) -> None:
        from pycodex.codex_api.endpoint.responses_websocket import immediate_close_from_message

        self.assertIsNone(immediate_close_from_message(ResponsesWebsocketTextMessage("{}")))
        self.assertIsNone(immediate_close_from_message(ResponsesWebsocketCloseMessage()))
        self.assertEqual(
            immediate_close_from_message(ResponsesWebsocketCloseMessage("1000", "")).code,
            "1000",
        )


class _Telemetry:
    def __init__(self) -> None:
        self.requests: list[tuple[str | None, bool]] = []
        self.events: list[str | None] = []

    def on_ws_request(
        self,
        elapsed: float,
        error: ApiError | None,
        connection_reused: bool,
    ) -> None:
        del elapsed
        self.requests.append((None if error is None else error.message, connection_reused))

    def on_ws_event(self, error: ApiError | None, elapsed: float) -> None:
        del elapsed
        self.events.append(None if error is None else error.message)


class _TimeoutAwareSendStream:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, float | None]] = []

    def send_with_timeout(self, payload: str, timeout: float | None) -> None:
        self.calls.append((payload, timeout))
        if self.error is not None:
            raise self.error


class _FakeHandshakeSocket:
    def __init__(self, response: bytes, send_error: Exception | None = None) -> None:
        self._response = bytearray(response)
        self.sent = b""
        self.send_error = send_error
        self.timeout = None
        self.timeout_history: list[float | None] = []

    def sendall(self, data: bytes) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent += data

    def recv(self, size: int) -> bytes:
        if not self._response:
            return b""
        chunk = bytes(self._response[:size])
        del self._response[:size]
        return chunk

    def gettimeout(self):
        return self.timeout

    def settimeout(self, timeout):
        self.timeout = timeout
        self.timeout_history.append(timeout)


class _FakeChunkedHandshakeSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.sent = b""

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        del size
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    def gettimeout(self):
        return None

    def settimeout(self, timeout):
        del timeout


def _server_frame(opcode: int, payload: bytes) -> bytes:
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        return bytes([first, length]) + payload
    if length <= 0xFFFF:
        return bytes([first, 126]) + length.to_bytes(2, "big") + payload
    return bytes([first, 127]) + length.to_bytes(8, "big") + payload


def _masked_client_frame_payload(frame: bytes) -> tuple[int, bytes]:
    first, second = frame[:2]
    opcode = first & 0x0F
    self_masked = bool(second & 0x80)
    if not self_masked:
        raise AssertionError("client websocket frames must be masked")
    length = second & 0x7F
    offset = 2
    if length == 126:
        length = int.from_bytes(frame[offset : offset + 2], "big")
        offset += 2
    elif length == 127:
        length = int.from_bytes(frame[offset : offset + 8], "big")
        offset += 8
    mask = frame[offset : offset + 4]
    offset += 4
    masked = frame[offset : offset + length]
    payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(masked))
    return opcode, payload


class _FakeCaBundle:
    def __init__(self, path: str) -> None:
        self.path = path
        self.loaded = False

    def load_certificates(self):
        self.loaded = True
        return [b"cert"]


class _FailingCaBundle:
    path = "C:/ca/bad.pem"

    def load_certificates(self):
        raise RuntimeError("bad ca")


class _Auth:
    def __init__(self, token: str) -> None:
        self.token = token

    def add_auth_headers(self, headers: dict[str, str]) -> None:
        headers["authorization"] = f"Bearer {self.token}"


def _provider() -> Provider:
    return Provider(
        name="openai",
        base_url="https://api.example.test/v1",
        query_params={"api-version": "1"},
        headers={"originator": "provider", "x-priority": "provider"},
        retry=RetryConfig(
            max_attempts=1,
            base_delay=0.0,
            retry_429=False,
            retry_5xx=False,
            retry_transport=False,
        ),
        stream_idle_timeout=3.0,
    )


if __name__ == "__main__":
    unittest.main()
