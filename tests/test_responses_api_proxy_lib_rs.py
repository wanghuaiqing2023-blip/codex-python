import json
import tempfile
import unittest
from pathlib import Path

from pycodex.responses_api_proxy import (
    DEFAULT_UPSTREAM_URL,
    ResponsesApiProxyError,
    build_forward_config,
    is_allowed_proxy_request,
    is_allowed_shutdown_request,
    response_headers_for_downstream,
    server_info_payload,
    upstream_headers_from_request,
    write_server_info,
)


class ResponsesApiProxyLibRsTests(unittest.TestCase):
    # Rust crate/module: codex-responses-api-proxy::lib.
    # Source contract: Args default upstream URL is OpenAI /v1/responses.
    def test_default_forward_config_uses_openai_responses_url(self) -> None:
        config = build_forward_config()

        self.assertEqual(config.upstream_url, DEFAULT_UPSTREAM_URL)
        self.assertEqual(config.host_header, "api.openai.com")

    # Rust crate/module: codex-responses-api-proxy::lib.
    # Source contract: ForwardConfig host header includes explicit upstream port.
    def test_forward_config_host_header_preserves_explicit_port(self) -> None:
        config = build_forward_config("https://example.com:8443/v1/responses")

        self.assertEqual(config.host_header, "example.com:8443")

    # Rust crate/module: codex-responses-api-proxy::lib.
    # Source contract: upstream URL parsing rejects missing host.
    def test_forward_config_rejects_upstream_without_host(self) -> None:
        with self.assertRaisesRegex(ResponsesApiProxyError, "invalid url|must include a host"):
            build_forward_config("file:/v1/responses")

    # Rust crate/module: codex-responses-api-proxy::lib.
    # Source contract: forward_request allows only exact POST /v1/responses.
    def test_proxy_request_allowlist_is_exact_post_responses_without_query(self) -> None:
        self.assertTrue(is_allowed_proxy_request("POST", "/v1/responses"))
        self.assertFalse(is_allowed_proxy_request("GET", "/v1/responses"))
        self.assertFalse(is_allowed_proxy_request("POST", "/v1/responses?debug=1"))
        self.assertFalse(is_allowed_proxy_request("POST", "/v1/responses/extra"))

    # Rust crate/module: codex-responses-api-proxy::lib.
    # Source contract: GET /shutdown is accepted only when http shutdown is enabled and queryless.
    def test_shutdown_request_allowlist_requires_flag_and_no_query(self) -> None:
        self.assertTrue(is_allowed_shutdown_request("GET", "/shutdown", http_shutdown=True))
        self.assertFalse(is_allowed_shutdown_request("GET", "/shutdown", http_shutdown=False))
        self.assertFalse(is_allowed_shutdown_request("POST", "/shutdown", http_shutdown=True))
        self.assertFalse(is_allowed_shutdown_request("GET", "/shutdown?now=1", http_shutdown=True))

    # Rust crate/module: codex-responses-api-proxy::lib.
    # Source contract: incoming Authorization and Host are replaced before upstream forwarding.
    def test_upstream_headers_replace_auth_and_host(self) -> None:
        headers = [
            ("Authorization", "Bearer caller"),
            ("Host", "127.0.0.1:1234"),
            ("Content-Type", "application/json"),
            ("X-Codex-Window-Id", "thread-1:0"),
        ]

        forwarded = upstream_headers_from_request(
            headers,
            auth_header="Bearer secret",
            host_header="api.openai.com",
        )

        self.assertEqual(forwarded["Authorization"], "Bearer secret")
        self.assertEqual(forwarded["Host"], "api.openai.com")
        self.assertEqual(forwarded["Content-Type"], "application/json")
        self.assertEqual(forwarded["X-Codex-Window-Id"], "thread-1:0")

    # Rust crate/module: codex-responses-api-proxy::lib.
    # Source contract: tiny_http-managed response headers are skipped downstream.
    def test_response_headers_filter_server_managed_headers(self) -> None:
        headers = [
            ("content-length", "100"),
            ("transfer-encoding", "chunked"),
            ("connection", "close"),
            ("trailer", "x"),
            ("upgrade", "websocket"),
            ("content-type", "application/json"),
            ("date", "kept-by-rust"),
        ]

        self.assertEqual(
            response_headers_for_downstream(headers),
            [("content-type", "application/json"), ("date", "kept-by-rust")],
        )

    # Rust crate/module: codex-responses-api-proxy::lib.
    # Source contract: write_server_info writes one JSON line with port and pid.
    def test_write_server_info_writes_single_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "server-info.json"

            write_server_info(path, 60001, pid=12345)

            self.assertEqual(path.read_text(encoding="utf-8"), '{"port":60001,"pid":12345}\n')
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), server_info_payload(60001, pid=12345))


if __name__ == "__main__":
    unittest.main()
