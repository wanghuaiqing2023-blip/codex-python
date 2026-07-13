import json
import unittest

import pycodex.codex_api.endpoint.realtime_websocket.methods as methods_module
from pycodex.codex_api import ApiError
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeBinaryMessage
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeCloseMessage
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeEvent
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeEventParser
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeFrameMessage
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeHandoffRequested
from pycodex.codex_api.endpoint.realtime_websocket import RealtimePingMessage
from pycodex.codex_api.endpoint.realtime_websocket import RealtimePongMessage
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeSessionConfig
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeSessionMode
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeTextMessage
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeTranscriptDelta
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeTranscriptEntry
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeWebsocketAlreadyClosed
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeWebsocketClient
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeWebsocketConnection
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeWebsocketConnectionClosed
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeWebsocketEvents
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeWebsocketMemoryStream
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeWebsocketWriter
from pycodex.codex_api.endpoint.realtime_websocket import merge_request_headers
from pycodex.codex_api.endpoint.realtime_websocket import with_session_id_header
from pycodex.codex_api.provider import Provider
from pycodex.codex_api.provider import RetryConfig
from pycodex.protocol import RealtimeAudioFrame
from pycodex.protocol import RealtimeOutputModality
from pycodex.protocol import RealtimeVoice


class RealtimeWebsocketRuntimeTests(unittest.TestCase):
    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust tests: e2e_connect_and_exchange_events_against_mock_ws_server.
    # Contract: writer helper methods serialize the same outbound request messages.
    def test_writer_serializes_outbound_messages(self) -> None:
        stream = RealtimeWebsocketMemoryStream()
        writer = RealtimeWebsocketWriter(stream, RealtimeEventParser.REALTIME_V2)

        writer.send_audio_frame(RealtimeAudioFrame(data="AAAA", sample_rate=24_000, num_channels=1))
        writer.send_conversation_item_create("hello")
        writer.send_conversation_function_call_output("call_1", "done")
        writer.send_response_create()

        payloads = [json.loads(payload) for payload in stream.sent_payloads]
        self.assertEqual(payloads[0], {"type": "input_audio_buffer.append", "audio": "AAAA"})
        self.assertEqual(
            payloads[1],
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                },
            },
        )
        self.assertEqual(
            payloads[2],
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": "call_1", "output": "done"},
            },
        )
        self.assertEqual(payloads[3], {"type": "response.create"})

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: send_session_update normalizes V1 to conversational/quicksilver and emits session.update.
    def test_writer_session_update_uses_parser_specific_session_shape(self) -> None:
        stream = RealtimeWebsocketMemoryStream()
        writer = RealtimeWebsocketWriter(stream, RealtimeEventParser.V1)

        writer.send_session_update(
            "instructions",
            RealtimeSessionMode.TRANSCRIPTION,
            RealtimeOutputModality.TEXT,
            RealtimeVoice.BREEZE,
        )

        self.assertEqual(
            json.loads(stream.sent_payloads[0]),
            {
                "type": "session.update",
                "session": {
                    "type": "quicksilver",
                    "instructions": "instructions",
                    "audio": {
                        "input": {"format": {"type": "audio/pcm", "rate": 24_000}},
                        "output": {"voice": "breeze"},
                    },
                },
            },
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: close is idempotent, ignores already-closed websocket errors, and blocks later sends.
    def test_writer_close_is_idempotent_and_blocks_later_send(self) -> None:
        stream = RealtimeWebsocketMemoryStream()
        writer = RealtimeWebsocketWriter(stream, RealtimeEventParser.REALTIME_V2)

        writer.close()
        stream.close_error = RealtimeWebsocketAlreadyClosed("already closed")
        writer.close()

        with self.assertRaises(ApiError) as ctx:
            writer.send_payload("{}")
        self.assertEqual(ctx.exception.kind, "stream")
        self.assertEqual(ctx.exception.message, "realtime websocket connection is closed")

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: close maps non-closed websocket close errors to ApiError::Stream.
    def test_writer_close_maps_unexpected_close_error(self) -> None:
        stream = RealtimeWebsocketMemoryStream()
        stream.close_error = RuntimeError("boom")
        writer = RealtimeWebsocketWriter(stream, RealtimeEventParser.REALTIME_V2)

        with self.assertRaises(ApiError) as ctx:
            writer.close()

        self.assertEqual(ctx.exception.kind, "stream")
        self.assertEqual(ctx.exception.message, "failed to close websocket: boom")

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: stream send failures become ApiError::Stream with the Rust message prefix.
    def test_writer_send_maps_transport_error(self) -> None:
        stream = RealtimeWebsocketMemoryStream()
        stream.send_error = RuntimeError("send failed")
        writer = RealtimeWebsocketWriter(stream, RealtimeEventParser.REALTIME_V2)

        with self.assertRaises(ApiError) as ctx:
            writer.send_payload("{}")

        self.assertEqual(ctx.exception.kind, "stream")
        self.assertEqual(ctx.exception.message, "failed to send realtime request: send failed")

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: events ignore unsupported text/ping/pong/frame, parse text, and update active transcript.
    def test_events_skip_ignored_frames_and_update_active_transcript(self) -> None:
        events = RealtimeWebsocketEvents(
            [
                RealtimeTextMessage('{"type":"unknown.event"}'),
                RealtimePingMessage(),
                RealtimePongMessage(),
                RealtimeFrameMessage(),
                RealtimeTextMessage('{"type":"response.created","response":{"id":"resp_1"}}'),
                RealtimeTextMessage(
                    '{"type":"response.output_text.delta","delta":"hello ","item_id":"item_1"}'
                ),
                RealtimeTextMessage(
                    '{"type":"response.output_text.delta","delta":"again","item_id":"item_1"}'
                ),
                RealtimeTextMessage(
                    '{"type":"conversation.item.done","item":{"type":"function_call",'
                    '"name":"background_agent","call_id":"call_1","id":"item_2",'
                    '"arguments":"{\\"prompt\\":\\"delegate\\"}"}}'
                ),
            ],
            RealtimeEventParser.REALTIME_V2,
        )

        self.assertEqual(events.next_event().kind, "ResponseCreated")
        self.assertEqual(
            events.next_event(),
            RealtimeEvent.output_transcript_delta(RealtimeTranscriptDelta("hello ")),
        )
        self.assertEqual(
            events.next_event(),
            RealtimeEvent.output_transcript_delta(RealtimeTranscriptDelta("again")),
        )
        event = events.next_event()

        self.assertEqual(
            event,
            RealtimeEvent.handoff_requested(
                RealtimeHandoffRequested(
                    "call_1",
                    "item_2",
                    "delegate",
                    (
                        RealtimeTranscriptEntry("assistant", "hello again"),
                        RealtimeTranscriptEntry("user", "delegate"),
                    ),
                )
            ),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: binary websocket messages surface as RealtimeEvent::Error.
    def test_events_binary_message_returns_error_event(self) -> None:
        events = RealtimeWebsocketEvents([RealtimeBinaryMessage(b"\x00")], RealtimeEventParser.REALTIME_V2)

        self.assertEqual(
            events.next_event(),
            RealtimeEvent.error("unexpected binary realtime websocket event"),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: read errors close the event stream and map to ApiError::Stream.
    def test_events_read_error_closes_stream(self) -> None:
        events = RealtimeWebsocketEvents([RuntimeError("read failed")], RealtimeEventParser.REALTIME_V2)

        with self.assertRaises(ApiError) as ctx:
            events.next_event()

        self.assertEqual(ctx.exception.kind, "stream")
        self.assertEqual(ctx.exception.message, "failed to read websocket message: read failed")
        self.assertIsNone(events.next_event())

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: close frames mark the shared connection closed.
    def test_connection_delegates_and_shares_closed_state(self) -> None:
        stream = RealtimeWebsocketMemoryStream()
        connection = RealtimeWebsocketConnection.new(
            stream,
            [RealtimeCloseMessage()],
            RealtimeEventParser.REALTIME_V2,
        )

        connection.send_audio_frame(RealtimeAudioFrame("BBBB", 24_000, 1))
        self.assertEqual(json.loads(stream.sent_payloads[0])["audio"], "BBBB")
        self.assertIsNone(connection.next_event())

        with self.assertRaises(ApiError) as ctx:
            connection.send_conversation_item_create("after close")
        self.assertEqual(ctx.exception.message, "realtime websocket connection is closed")

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: close ignores websocket ConnectionClosed errors too.
    def test_writer_close_ignores_connection_closed_error(self) -> None:
        stream = RealtimeWebsocketMemoryStream()
        stream.close_error = RealtimeWebsocketConnectionClosed("connection closed")
        writer = RealtimeWebsocketWriter(stream, RealtimeEventParser.REALTIME_V2)

        writer.close()
        writer.close()

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust tests: e2e_connect_and_exchange_events_against_mock_ws_server.
    # Contract: RealtimeWebsocketClient::connect builds the URL/header set,
    # opens the websocket, and sends session.update before event reads.
    def test_client_connect_builds_headers_url_and_sends_session_update(self) -> None:
        captured = {}
        stream = _ClientStream(
            [
                RealtimeTextMessage(
                    '{"type":"session.updated","session":{"id":"sess_mock",'
                    '"instructions":"backend prompt"}}'
                )
            ]
        )

        def connector(url, headers):
            captured["url"] = url
            captured["headers"] = dict(headers)
            return stream

        client = RealtimeWebsocketClient.new(
            _provider("http://127.0.0.1:1", {"api-version": "2025-04-01"}),
            connector,
        )
        connection = client.connect(
            _config(event_parser=RealtimeEventParser.V1),
            extra_headers={"x-extra": "2", "x-provider": "override"},
            default_headers={"x-extra": "default", "x-default": "3"},
        )

        first_payload = json.loads(stream.sent_payloads[0])
        self.assertEqual(
            captured["url"],
            "ws://127.0.0.1:1/v1/realtime?intent=quicksilver&model=realtime-test-model&api-version=2025-04-01",
        )
        self.assertEqual(captured["headers"]["x-provider"], "override")
        self.assertEqual(captured["headers"]["x-extra"], "2")
        self.assertEqual(captured["headers"]["x-default"], "3")
        self.assertEqual(captured["headers"]["x-session-id"], "conv_1")
        self.assertEqual(first_payload["type"], "session.update")
        self.assertEqual(first_payload["session"]["type"], "quicksilver")
        self.assertEqual(first_payload["session"]["instructions"], "backend prompt")
        self.assertEqual(
            connection.next_event(),
            RealtimeEvent.session_updated("sess_mock", "backend prompt"),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust test: e2e_connect_and_exchange_events_against_mock_ws_server.
    # Contract slice: RealtimeWebsocketClient::connect sends session.update
    # before user messages, parses V1 events, updates the active transcript,
    # and closes without surfacing errors. Transport handshake behavior is
    # covered by the responses_websocket owner tests.
    def test_connect_and_exchange_events_against_mock_stream(self) -> None:
        stream = _ClientStream(
            [
                RealtimeTextMessage(
                    '{"type":"session.updated","session":{"id":"sess_mock","instructions":"backend prompt"}}'
                ),
                RealtimeTextMessage(
                    '{"type":"conversation.output_audio.delta","delta":"AQID","sample_rate":48000,"channels":1}'
                ),
                RealtimeTextMessage('{"type":"conversation.input_transcript.delta","delta":"delegate "}'),
                RealtimeTextMessage('{"type":"conversation.input_transcript.delta","delta":"now"}'),
                RealtimeTextMessage('{"type":"conversation.output_transcript.delta","delta":"working"}'),
                RealtimeTextMessage(
                    '{"type":"conversation.handoff.requested","handoff_id":"handoff_1",'
                    '"item_id":"item_2","input_transcript":"delegate now"}'
                ),
            ]
        )
        client = RealtimeWebsocketClient.new(
            _provider("http://127.0.0.1:1", {}),
            lambda _url, _headers: stream,
        )
        connection = client.connect(_config(event_parser=RealtimeEventParser.V1))

        connection.send_audio_frame(RealtimeAudioFrame("AQID", 48_000, 1))
        connection.send_conversation_item_create("hello agent")
        connection.send_conversation_function_call_output(
            "handoff_1",
            "hello from background agent",
        )

        self.assertEqual(
            connection.next_event(),
            RealtimeEvent.session_updated("sess_mock", "backend prompt"),
        )
        self.assertEqual(
            connection.next_event(),
            RealtimeEvent.audio_out(RealtimeAudioFrame("AQID", 48_000, 1)),
        )
        self.assertEqual(
            connection.next_event(),
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("delegate ")),
        )
        self.assertEqual(
            connection.next_event(),
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("now")),
        )
        self.assertEqual(
            connection.next_event(),
            RealtimeEvent.output_transcript_delta(RealtimeTranscriptDelta("working")),
        )
        self.assertEqual(
            connection.next_event(),
            RealtimeEvent.handoff_requested(
                RealtimeHandoffRequested(
                    "handoff_1",
                    "item_2",
                    "delegate now",
                    (
                        RealtimeTranscriptEntry("user", "delegate now"),
                        RealtimeTranscriptEntry("assistant", "working"),
                    ),
                )
            ),
        )

        connection.close()

        payloads = [json.loads(payload) for payload in stream.sent_payloads]
        self.assertEqual(payloads[0]["type"], "session.update")
        self.assertEqual(payloads[0]["session"]["type"], "quicksilver")
        self.assertEqual(payloads[0]["session"]["instructions"], "backend prompt")
        self.assertEqual(payloads[0]["session"]["audio"]["input"]["format"]["type"], "audio/pcm")
        self.assertEqual(payloads[0]["session"]["audio"]["input"]["format"]["rate"], 24_000)
        self.assertEqual(payloads[0]["session"]["audio"]["output"]["voice"], "breeze")
        self.assertEqual(payloads[1]["type"], "input_audio_buffer.append")
        self.assertEqual(payloads[2]["type"], "conversation.item.create")
        self.assertEqual(payloads[2]["item"]["content"][0]["type"], "input_text")
        self.assertEqual(payloads[2]["item"]["content"][0]["text"], "hello agent")
        self.assertEqual(payloads[3]["type"], "conversation.handoff.append")
        self.assertEqual(payloads[3]["handoff_id"], "handoff_1")
        self.assertEqual(
            payloads[3]["output_text"],
            '"Agent Final Message":\n\nhello from background agent',
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: connect_webrtc_sideband joins an existing call by appending
    # call_id and uses the same connection/session.update path.
    def test_client_connect_webrtc_sideband_uses_call_id_url(self) -> None:
        captured = {}
        stream = _ClientStream([])

        def connector(url, headers):
            captured["url"] = url
            captured["headers"] = dict(headers)
            return stream

        client = RealtimeWebsocketClient(
            _provider("https://example.test/v1", {"model": "ignored"}),
            connector,
            sleeper=lambda _delay: None,
        )
        connection = client.connect_webrtc_sideband(
            _config(event_parser=RealtimeEventParser.REALTIME_V2),
            "call_123",
        )

        self.assertEqual(
            captured["url"],
            "wss://example.test/v1/realtime?model=ignored&call_id=call_123",
        )
        self.assertEqual(json.loads(stream.sent_payloads[0])["type"], "session.update")
        self.assertIsNone(connection.next_event())

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: connect_webrtc_sideband retries 0..=max_attempts and sleeps
    # codex_client::retry::backoff(base_delay, attempt + 1) between failures.
    def test_client_connect_webrtc_sideband_retry_uses_retry_backoff(self) -> None:
        attempts = []
        sleeps = []
        backoff_calls = []
        stream = _ClientStream(
            [RealtimeTextMessage('{"type":"session.updated","session":{"id":"sess_retry"}}')]
        )

        def connector(url, headers):
            attempts.append((url, dict(headers)))
            if len(attempts) < 3:
                raise ApiError.stream(f"refused {len(attempts)}")
            return stream

        def fake_backoff(base_delay, attempt):
            backoff_calls.append((base_delay, attempt))
            return 10.0 + attempt

        previous_backoff = methods_module.backoff
        methods_module.backoff = fake_backoff
        try:
            client = RealtimeWebsocketClient(
                Provider(
                    name="test",
                    base_url="http://127.0.0.1:1",
                    query_params=None,
                    headers={"x-provider": "1"},
                    retry=RetryConfig(
                        max_attempts=2,
                        base_delay=0.25,
                        retry_429=False,
                        retry_5xx=False,
                        retry_transport=False,
                    ),
                    stream_idle_timeout=5,
                ),
                connector,
                sleeps.append,
            )

            connection = client.connect_webrtc_sideband(_config(), "call_retry")
        finally:
            methods_module.backoff = previous_backoff

        self.assertEqual(len(attempts), 3)
        self.assertEqual(backoff_calls, [(0.25, 1), (0.25, 2)])
        self.assertEqual(sleeps, [11.0, 12.0])
        self.assertIn("call_id=call_retry", attempts[-1][0])
        self.assertEqual(connection.next_event(), RealtimeEvent.session_updated("sess_retry", None))

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: connector failures map to ApiError::Stream with the realtime
    # websocket connect prefix.
    def test_client_connect_maps_connector_error(self) -> None:
        def connector(_url, _headers):
            raise RuntimeError("refused")

        client = RealtimeWebsocketClient.new(_provider("http://127.0.0.1:1"), connector)

        with self.assertRaises(ApiError) as ctx:
            client.connect(_config())

        self.assertEqual(ctx.exception.kind, "stream")
        self.assertEqual(
            ctx.exception.message,
            "failed to connect realtime websocket: refused",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: connect_realtime_websocket_url calls
    # maybe_build_rustls_client_config_with_custom_ca() before
    # connect_async_tls_with_config, so wss realtime websocket connections
    # honor the same custom-CA policy as the rest of Codex traffic.
    def test_connect_realtime_websocket_url_wss_uses_custom_ca_ssl_context(self) -> None:
        captures: dict[str, object] = {}
        fake_bundle = _FakeCaBundle("C:/ca/realtime.pem")
        expected_stream = object()

        class FakeSslContext:
            pass

        def fake_connect(url, headers, *, ssl_context=None, timeout=None, max_message_size=None):
            captures.update(
                {
                    "url": url,
                    "headers": headers,
                    "ssl_context": ssl_context,
                    "timeout": timeout,
                    "max_message_size": max_message_size,
                }
            )
            return expected_stream, 101, {}

        from pycodex.codex_api.endpoint import responses_websocket as responses_module

        original_connect = responses_module.connect_vendored_websocket
        original_configured_ca_bundle = responses_module.configured_ca_bundle
        original_create_default_context = responses_module.ssl.create_default_context
        try:
            responses_module.connect_vendored_websocket = fake_connect
            responses_module.configured_ca_bundle = lambda env_source: fake_bundle
            responses_module.ssl.create_default_context = (
                lambda cafile=None: captures.update({"cafile": cafile}) or FakeSslContext()
            )

            stream = methods_module.connect_realtime_websocket_url(
                "wss://api.example.test/v1/realtime",
                {},
            )
        finally:
            responses_module.connect_vendored_websocket = original_connect
            responses_module.configured_ca_bundle = original_configured_ca_bundle
            responses_module.ssl.create_default_context = original_create_default_context

        self.assertIs(stream, expected_stream)
        self.assertTrue(fake_bundle.loaded)
        self.assertEqual(captures["cafile"], "C:/ca/realtime.pem")
        self.assertEqual(captures["url"], "wss://api.example.test/v1/realtime")
        self.assertIsInstance(captures["ssl_context"], FakeSslContext)

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: custom-CA connector construction failures map to
    # ApiError::Stream("failed to configure websocket TLS: ...").
    def test_connect_realtime_websocket_custom_ca_error_is_stream_error(self) -> None:
        from pycodex.codex_api.endpoint import responses_websocket as responses_module

        original_configured_ca_bundle = responses_module.configured_ca_bundle
        original_create_connection = responses_module.socket.create_connection
        try:
            responses_module.configured_ca_bundle = lambda env_source: _FailingCaBundle()
            responses_module.socket.create_connection = lambda address, timeout=None: self.fail(
                "socket connection should not be attempted"
            )

            with self.assertRaises(ApiError) as caught:
                methods_module.connect_realtime_websocket_url(
                    "wss://api.example.test/v1/realtime",
                    {},
                )
        finally:
            responses_module.configured_ca_bundle = original_configured_ca_bundle
            responses_module.socket.create_connection = original_create_connection

        self.assertEqual(caught.exception.kind, "stream")
        self.assertEqual(
            caught.exception.message,
            "failed to configure websocket TLS: bad ca",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust test: merge_request_headers_matches_http_precedence.
    # Contract: HeaderMap merge is case-insensitive: extra headers replace
    # provider values and defaults only fill absent names.
    def test_merge_request_headers_is_case_insensitive_like_headermap(self) -> None:
        merged = merge_request_headers(
            {"Originator": "provider", "X-Priority": "provider"},
            {"x-priority": "extra"},
            {
                "originator": "default",
                "X-Priority": "default",
                "X-Default-Only": "default-only",
            },
        )

        self.assertEqual(
            merged,
            {
                "Originator": "provider",
                "x-priority": "extra",
                "X-Default-Only": "default-only",
            },
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: with_session_id_header uses HeaderMap::insert("x-session-id",
    # ...), replacing any existing header of the same name regardless of case.
    def test_with_session_id_header_replaces_existing_case_variant(self) -> None:
        headers = with_session_id_header(
            {"X-Session-ID": "old", "x-other": "1"},
            "conv_2",
        )

        self.assertEqual(headers, {"x-other": "1", "x-session-id": "conv_2"})

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: with_session_id_header converts the session id with
    # HeaderValue::from_str, so invalid header values return ApiError::Stream.
    def test_with_session_id_header_rejects_invalid_header_values(self) -> None:
        for session_id in ("bad\nvalue", "bad\0value", "snowman-\u2603"):
            with self.subTest(session_id=repr(session_id)):
                with self.assertRaises(ApiError) as ctx:
                    with_session_id_header({}, session_id)
                self.assertEqual(ctx.exception.kind, "stream")
                self.assertEqual(
                    ctx.exception.message,
                    "invalid realtime session id header: invalid header value",
                )


class _ClientStream(RealtimeWebsocketMemoryStream):
    def __init__(self, messages):
        super().__init__()
        self._messages = iter(messages)

    def next(self):
        try:
            return next(self._messages)
        except StopIteration:
            raise RealtimeWebsocketConnectionClosed("connection closed") from None


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


def _provider(base_url: str, query_params=None) -> Provider:
    return Provider(
        name="test",
        base_url=base_url,
        query_params=query_params,
        headers={"x-provider": "1"},
        retry=RetryConfig(
            max_attempts=1,
            base_delay=0,
            retry_429=False,
            retry_5xx=False,
            retry_transport=False,
        ),
        stream_idle_timeout=5,
    )


def _config(event_parser: RealtimeEventParser = RealtimeEventParser.V1) -> RealtimeSessionConfig:
    return RealtimeSessionConfig(
        instructions="backend prompt",
        model="realtime-test-model",
        session_id="conv_1",
        event_parser=event_parser,
        session_mode=RealtimeSessionMode.CONVERSATIONAL,
        output_modality=RealtimeOutputModality.AUDIO,
        voice=RealtimeVoice.BREEZE,
    )


if __name__ == "__main__":
    unittest.main()
