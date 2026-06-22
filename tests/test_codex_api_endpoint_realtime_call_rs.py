import asyncio
import json
import unittest
from dataclasses import dataclass

from pycodex.codex_api import Provider
from pycodex.codex_api import RealtimeCallClient
from pycodex.codex_api import RealtimeCallResponse
from pycodex.codex_api import RealtimeEventParser
from pycodex.codex_api import RealtimeSessionConfig
from pycodex.codex_api import RealtimeSessionMode
from pycodex.codex_api import RetryConfig
from pycodex.codex_api import session_update_session_json
from pycodex.codex_api.endpoint.realtime_call import MULTIPART_CONTENT_TYPE
from pycodex.codex_client import Request
from pycodex.codex_client import Response
from pycodex.protocol import RealtimeOutputModality
from pycodex.protocol import RealtimeVoice


class CapturingTransport:
    def __init__(self, location: str | None = "/v1/realtime/calls/rtc_test") -> None:
        self.last_request: Request | None = None
        self.location = location

    def execute(self, request: Request) -> Response:
        self.last_request = request
        headers = {} if self.location is None else {"location": self.location}
        return Response(status=200, headers=headers, body=b"v=0\r\n")

    def stream(self, _request: Request):  # pragma: no cover - realtime call uses execute.
        raise AssertionError("stream should not run")


@dataclass(frozen=True)
class DummyAuth:
    def add_auth_headers(self, headers: dict[str, str]) -> None:
        headers["authorization"] = "Bearer test-token"


def provider(base_url: str) -> Provider:
    return Provider(
        name="test",
        base_url=base_url,
        query_params=None,
        headers={},
        retry=RetryConfig(
            max_attempts=1,
            base_delay=0.001,
            retry_429=False,
            retry_5xx=True,
            retry_transport=True,
        ),
        stream_idle_timeout=1,
    )


def realtime_session_config(session_id: str) -> RealtimeSessionConfig:
    return RealtimeSessionConfig(
        instructions="hi",
        model="gpt-realtime",
        session_id=session_id,
        event_parser=RealtimeEventParser.REALTIME_V2,
        session_mode=RealtimeSessionMode.CONVERSATIONAL,
        output_modality=RealtimeOutputModality.AUDIO,
        voice=RealtimeVoice.MARIN,
    )


class RealtimeCallEndpointTests(unittest.TestCase):
    # Rust source: codex-api/src/endpoint/realtime_call.rs
    # Contract: SDP-only create sends application/sdp raw body and parses response.
    def test_sends_sdp_offer_as_raw_body(self) -> None:
        transport = CapturingTransport()
        client = RealtimeCallClient(transport, provider("https://api.openai.com/v1"), DummyAuth())

        response = asyncio.run(client.create("v=offer\r\n"))

        self.assertEqual(response, RealtimeCallResponse(sdp="v=0\r\n", call_id="rtc_test"))
        self.assertIsNotNone(transport.last_request)
        assert transport.last_request is not None
        self.assertEqual(transport.last_request.method, "POST")
        self.assertEqual(transport.last_request.url, "https://api.openai.com/v1/realtime/calls")
        self.assertEqual(transport.last_request.headers["content-type"], "application/sdp")
        self.assertEqual(transport.last_request.headers["authorization"], "Bearer test-token")
        self.assertIsNotNone(transport.last_request.body)
        assert transport.last_request.body is not None
        self.assertEqual(transport.last_request.body.kind, "raw")
        self.assertEqual(transport.last_request.body.value, b"v=offer\r\n")

    # Rust source: codex-api/src/endpoint/realtime_call.rs
    # Contract: create_with_headers forwards extra headers through EndpointSession.
    def test_create_with_headers_applies_extra_headers(self) -> None:
        transport = CapturingTransport()
        client = RealtimeCallClient(transport, provider("https://api.openai.com/v1"), DummyAuth())

        asyncio.run(client.create_with_headers("v=offer\r\n", {"x-extra": "yes"}))

        self.assertIsNotNone(transport.last_request)
        assert transport.last_request is not None
        self.assertEqual(transport.last_request.headers["x-extra"], "yes")
        self.assertEqual(transport.last_request.headers["content-type"], "application/sdp")
        self.assertEqual(transport.last_request.headers["authorization"], "Bearer test-token")

    # Rust source: codex-api/src/endpoint/realtime_call.rs
    # Contract: backend forwarded Locations still yield the rtc_* call id.
    def test_extracts_call_id_from_forwarded_backend_location(self) -> None:
        transport = CapturingTransport("/v1/realtime/calls/calls/rtc_backend_test")
        client = RealtimeCallClient(
            transport,
            provider("https://chatgpt.com/backend-api/codex"),
            DummyAuth(),
        )

        response = asyncio.run(client.create("v=offer\r\n"))

        self.assertEqual(response.call_id, "rtc_backend_test")
        self.assertIsNotNone(transport.last_request)
        assert transport.last_request is not None
        self.assertEqual(
            transport.last_request.url,
            "https://chatgpt.com/backend-api/codex/realtime/calls",
        )
        self.assertIsNotNone(transport.last_request.body)
        assert transport.last_request.body is not None
        self.assertEqual(transport.last_request.body.value, b"v=offer\r\n")

    # Rust source: codex-api/src/endpoint/realtime_call.rs
    # Contract: API session calls use multipart sdp/session body and omit session id.
    def test_sends_api_session_call_as_multipart_body(self) -> None:
        transport = CapturingTransport()
        client = RealtimeCallClient(transport, provider("https://api.openai.com/v1"), DummyAuth())

        response = asyncio.run(
            client.create_with_session("v=offer\r\n", realtime_session_config("sess-api"))
        )

        self.assertEqual(response.call_id, "rtc_test")
        self.assertIsNotNone(transport.last_request)
        assert transport.last_request is not None
        self.assertEqual(transport.last_request.headers["content-type"], MULTIPART_CONTENT_TYPE)
        self.assertIsNotNone(transport.last_request.body)
        assert transport.last_request.body is not None
        body = transport.last_request.body.value.decode("utf-8")
        session = session_update_session_json(realtime_session_config("sess-api"))
        session.pop("id", None)
        session_json = json.dumps(session, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(
            body,
            "--codex-realtime-call-boundary\r\n"
            'Content-Disposition: form-data; name="sdp"\r\n'
            "Content-Type: application/sdp\r\n"
            "\r\n"
            "v=offer\r\n"
            "\r\n"
            "--codex-realtime-call-boundary\r\n"
            'Content-Disposition: form-data; name="session"\r\n'
            "Content-Type: application/json\r\n"
            "\r\n"
            f"{session_json}\r\n"
            "--codex-realtime-call-boundary--\r\n",
        )
        self.assertNotIn('"id"', body)

    # Rust source: codex-api/src/endpoint/realtime_call.rs
    # Contract: backend session calls use JSON body with sdp and session.
    def test_sends_backend_session_call_as_json_body(self) -> None:
        transport = CapturingTransport()
        client = RealtimeCallClient(
            transport,
            provider("https://chatgpt.com/backend-api/codex"),
            DummyAuth(),
        )

        response = asyncio.run(
            client.create_with_session("v=offer\r\n", realtime_session_config("sess-backend"))
        )

        self.assertEqual(response.call_id, "rtc_test")
        self.assertIsNotNone(transport.last_request)
        assert transport.last_request is not None
        self.assertIsNotNone(transport.last_request.body)
        assert transport.last_request.body is not None
        expected_session = session_update_session_json(realtime_session_config("sess-backend"))
        expected_session.pop("id", None)
        self.assertEqual(
            transport.last_request.body.json_value(),
            {"sdp": "v=offer\r\n", "session": expected_session},
        )

    # Rust source: codex-api/src/endpoint/realtime_call.rs
    # Contract: Location is required to parse a call id.
    def test_errors_when_location_is_missing(self) -> None:
        client = RealtimeCallClient(
            CapturingTransport(location=None),
            provider("https://api.openai.com/v1"),
            DummyAuth(),
        )

        with self.assertRaisesRegex(Exception, "stream error: realtime call response missing Location"):
            asyncio.run(client.create("v=offer\r\n"))

    # Rust source: codex-api/src/endpoint/realtime_call.rs
    # Contract: Location must contain a non-empty rtc_* segment.
    def test_rejects_location_without_call_id(self) -> None:
        client = RealtimeCallClient(
            CapturingTransport(location="/v1/realtime/calls"),
            provider("https://api.openai.com/v1"),
            DummyAuth(),
        )

        with self.assertRaisesRegex(
            Exception,
            "stream error: realtime call Location does not contain a call id: /v1/realtime/calls",
        ):
            asyncio.run(client.create("v=offer\r\n"))

    # Rust source: codex-api/src/endpoint/realtime_call.rs
    # Contract: with_telemetry returns a new client with request telemetry configured.
    def test_with_telemetry_returns_new_client(self) -> None:
        transport = CapturingTransport()
        client = RealtimeCallClient(transport, provider("https://api.openai.com/v1"), DummyAuth())
        telemetry = object()

        updated = client.with_telemetry(telemetry)

        self.assertIsNone(client.request_telemetry)
        self.assertIs(updated.request_telemetry, telemetry)
        self.assertIs(updated.transport, client.transport)
        self.assertIs(updated.provider, client.provider)
        self.assertIs(updated.auth, client.auth)


if __name__ == "__main__":
    unittest.main()
