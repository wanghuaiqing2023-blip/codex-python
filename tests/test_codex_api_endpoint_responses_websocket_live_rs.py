"""Live integration gate for ``codex-api/src/endpoint/responses_websocket.rs``.

Rust crate: ``codex-api``
Rust module: ``src/endpoint/responses_websocket.rs``
Contract: the Python standard-library websocket connector can perform a real
``wss://`` TLS websocket upgrade against a non-local endpoint. This file is
intentionally skipped unless explicit live endpoint credentials are provided.
"""

from __future__ import annotations

import json
import os
import unittest
from urllib.parse import urlsplit

from pycodex.codex_api.error import ApiError
from pycodex.codex_api.endpoint.responses_websocket import connect_websocket
from pycodex.codex_client import TransportError


LIVE_URL_ENV = "PYCODEX_LIVE_RESPONSES_WS_URL"
LIVE_HEADERS_ENV = "PYCODEX_LIVE_RESPONSES_WS_HEADERS_JSON"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
UNSUPPORTED_COUNTRY_REGION_CODE = "unsupported_country_region_territory"


def _live_url() -> str | None:
    value = os.environ.get(LIVE_URL_ENV)
    if value:
        return value
    return None


def _live_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    headers_json = os.environ.get(LIVE_HEADERS_ENV)
    if headers_json:
        decoded = json.loads(headers_json)
        if not isinstance(decoded, dict):
            raise AssertionError(f"{LIVE_HEADERS_ENV} must decode to a JSON object")
        headers.update({str(key): str(value) for key, value in decoded.items()})
    api_key = os.environ.get(OPENAI_API_KEY_ENV)
    if api_key and "authorization" not in {key.lower() for key in headers}:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _assert_real_wss_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "wss":
        raise AssertionError(f"{LIVE_URL_ENV} must use wss://, got {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    local_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    if host in local_hosts or host.endswith(".localhost"):
        raise AssertionError(f"{LIVE_URL_ENV} must target a non-local websocket endpoint")


def _live_environment_skip_reason(exc: ApiError) -> str | None:
    transport = exc.transport
    if exc.kind != "transport" or not isinstance(transport, TransportError):
        return None
    if transport.kind != "http" or transport.status != 403 or not transport.body:
        return None
    try:
        body = json.loads(transport.body)
    except json.JSONDecodeError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None
    if error.get("code") != UNSUPPORTED_COUNTRY_REGION_CODE:
        return None
    return "live OpenAI endpoint is unavailable from this account/region"


def test_unsupported_country_region_live_error_is_environment_skip() -> None:
    # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
    # Contract: live-test environment unavailability is separated from
    # websocket/TLS/header implementation failures. This does not make a fake
    # websocket pass; it only classifies a real remote HTTP 403 response whose
    # body explicitly says the account/region cannot use the service.
    error = ApiError.transport_error(
        TransportError.http(
            403,
            body=json.dumps(
                {
                    "error": {
                        "code": UNSUPPORTED_COUNTRY_REGION_CODE,
                        "message": "Country, region, or territory not supported",
                    }
                }
            ),
        )
    )
    assert _live_environment_skip_reason(error) is not None


@unittest.skipUnless(
    _live_url(),
    f"set {LIVE_URL_ENV} to run the real codex-api responses websocket live test",
)
class CodexApiEndpointResponsesWebsocketLiveRsTests(unittest.TestCase):
    def test_live_wss_upgrade_returns_real_status_and_metadata(self) -> None:
        # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
        # Contract: connect_websocket uses the real TLS websocket connector
        # boundary, validates HTTP 101/Sec-WebSocket-Accept, and projects
        # successful response metadata from the server. Unlike the unit tests in
        # test_codex_api_endpoint_responses_websocket_rs.py, this test must hit
        # a user-provided non-local wss:// endpoint and does not install a fake
        # socket or local websocket server.
        url = _live_url()
        assert url is not None
        _assert_real_wss_url(url)
        headers = _live_headers()
        turn_state: dict[str, str] = {}

        try:
            stream, status, reasoning_included, models_etag, server_model = connect_websocket(
                url,
                headers,
                turn_state,
            )
        except ApiError as exc:
            skip_reason = _live_environment_skip_reason(exc)
            if skip_reason is not None:
                raise unittest.SkipTest(skip_reason) from exc
            raise

        self.assertIsNotNone(stream)
        self.assertEqual(status, 101)
        self.assertIsInstance(reasoning_included, bool)
        self.assertTrue(models_etag is None or isinstance(models_etag, str))
        self.assertTrue(server_model is None or isinstance(server_model, str))
        self.assertTrue("value" not in turn_state or isinstance(turn_state["value"], str))
