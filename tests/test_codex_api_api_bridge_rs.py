"""Rust-derived tests for ``codex-api/src/api_bridge.rs``.

Rust crate: ``codex-api``
Rust module: ``src/api_bridge.rs``
Contract: API/transport errors map to protocol ``CodexErr`` variants.
"""

from __future__ import annotations

import base64
import json
import unittest
from datetime import datetime
from datetime import timezone

from pycodex.codex_api.api_bridge import ACTIVE_LIMIT_HEADER
from pycodex.codex_api.api_bridge import CF_RAY_HEADER
from pycodex.codex_api.api_bridge import CYBER_POLICY_FALLBACK_MESSAGE
from pycodex.codex_api.api_bridge import OAI_REQUEST_ID_HEADER
from pycodex.codex_api.api_bridge import REQUEST_ID_HEADER
from pycodex.codex_api.api_bridge import X_ERROR_JSON_HEADER
from pycodex.codex_api.api_bridge import X_OPENAI_AUTHORIZATION_ERROR_HEADER
from pycodex.codex_api.api_bridge import map_api_error
from pycodex.codex_api.error import ApiError
from pycodex.codex_client import TransportError
from pycodex.protocol.auth import KnownPlan
from pycodex.protocol import UsageLimitReachedError


def _json_body(value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


def _http_error(
    status: int,
    body: str,
    *,
    headers: dict[str, object] | None = None,
    url: str | None = "http://example.com/v1/responses",
) -> ApiError:
    return ApiError.transport_error(
        TransportError.http(status, url=url, headers=headers, body=body)
    )


class CodexApiApiBridgeRsTests(unittest.TestCase):
    def test_map_api_error_maps_direct_variants(self) -> None:
        cases = [
            (ApiError.context_window_exceeded(), "context_window_exceeded"),
            (ApiError.quota_exceeded(), "quota_exceeded"),
            (ApiError.usage_not_included(), "usage_not_included"),
            (ApiError.server_overloaded(), "server_overloaded"),
            (ApiError.invalid_request("bad"), "invalid_request"),
            (ApiError.cyber_policy("flagged"), "cyber_policy"),
        ]

        for error, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(map_api_error(error).kind, expected)

    def test_map_api_error_maps_stream_and_retryable(self) -> None:
        stream = map_api_error(ApiError.stream("dropped"))
        retryable = map_api_error(ApiError.retryable("slow down", delay=1.25))
        rate_limit = map_api_error(ApiError.rate_limit("wait"))

        self.assertEqual(stream.kind, "stream")
        self.assertEqual(stream.message, "dropped")
        self.assertIsNone(stream.payload)
        self.assertEqual(retryable.kind, "stream")
        self.assertEqual(retryable.message, "slow down")
        self.assertEqual(retryable.payload, 1.25)
        self.assertEqual(rate_limit.kind, "stream")
        self.assertEqual(rate_limit.message, "wait")

    def test_map_api_error_maps_api_status_to_unexpected_response(self) -> None:
        # Source: codex-api/src/api_bridge.rs map_api_error ApiError::Api arm.
        # Contract: direct API status errors become CodexErr::UnexpectedStatus
        # with no transport header metadata.
        err = map_api_error(ApiError.api(418, "teapot"))

        self.assertEqual(err.kind, "unexpected_status")
        self.assertEqual(err.payload.status, 418)
        self.assertEqual(err.payload.body, "teapot")
        self.assertIsNone(err.payload.url)
        self.assertIsNone(err.payload.cf_ray)
        self.assertIsNone(err.payload.request_id)

    def test_map_api_error_maps_server_overloaded_from_503_body(self) -> None:
        body = _json_body({"error": {"code": "server_is_overloaded"}})

        err = map_api_error(_http_error(503, body))

        self.assertEqual(err.kind, "server_overloaded")

    def test_map_api_error_maps_slow_down_503_body_to_server_overloaded(self) -> None:
        # Source: codex-api/src/api_bridge.rs HTTP 503 body-code branch.
        # Contract: both server_is_overloaded and slow_down are overloaded.
        body = _json_body({"error": {"code": "slow_down"}})

        err = map_api_error(_http_error(503, body))

        self.assertEqual(err.kind, "server_overloaded")

    def test_map_api_error_maps_cyber_policy_from_400_body(self) -> None:
        message = "This request has been flagged for potentially high-risk cyber activity."
        body = _json_body(
            {
                "error": {
                    "message": message,
                    "type": "invalid_request",
                    "param": None,
                    "code": "cyber_policy",
                }
            }
        )

        err = map_api_error(_http_error(400, body))

        self.assertEqual(err.kind, "cyber_policy")
        self.assertEqual(err.message, message)

    def test_map_api_error_maps_wrapped_websocket_cyber_policy_from_400_body(self) -> None:
        body = _json_body(
            {
                "type": "error",
                "status": 400,
                "error": {
                    "message": "This websocket request was flagged.",
                    "type": "invalid_request",
                    "code": "cyber_policy",
                },
            }
        )

        err = map_api_error(_http_error(400, body, url="ws://example.com/v1/responses"))

        self.assertEqual(err.kind, "cyber_policy")
        self.assertEqual(err.message, "This websocket request was flagged.")

    def test_map_api_error_uses_cyber_policy_fallback_for_missing_message(self) -> None:
        body = _json_body({"error": {"code": "cyber_policy"}})

        err = map_api_error(_http_error(400, body))

        self.assertEqual(err.kind, "cyber_policy")
        self.assertEqual(err.message, CYBER_POLICY_FALLBACK_MESSAGE)

    def test_map_api_error_keeps_unknown_400_errors_generic(self) -> None:
        body = _json_body(
            {"error": {"message": "Some other bad request.", "code": "some_other_policy"}}
        )

        err = map_api_error(_http_error(400, body))

        self.assertEqual(err.kind, "invalid_request")
        self.assertEqual(err.message, body)

    def test_map_api_error_maps_valid_image_400_to_invalid_image_request(self) -> None:
        body = "The image data you provided does not represent a valid image"

        err = map_api_error(_http_error(400, body))

        self.assertEqual(err.kind, "invalid_image_request")

    def test_map_api_error_maps_usage_limit_limit_name_header(self) -> None:
        headers = {
            ACTIVE_LIMIT_HEADER: "codex_other",
            "x-codex-other-limit-name": "codex_other",
        }
        body = _json_body(
            {"error": {"type": "usage_limit_reached", "plan_type": "pro"}}
        )

        err = map_api_error(_http_error(429, body, headers=headers))

        self.assertEqual(err.kind, "usage_limit_reached")
        self.assertIsInstance(err.payload, UsageLimitReachedError)
        self.assertEqual(err.payload.rate_limits.limit_name, "codex_other")

    def test_map_api_error_maps_usage_limit_plan_and_reset_timestamp(self) -> None:
        # Source: codex-api/src/api_bridge.rs UsageErrorBody deserialize arm.
        # Contract: usage-limit body plan_type and resets_at are projected into
        # UsageLimitReachedError, with resets_at interpreted as Unix seconds UTC.
        body = _json_body(
            {
                "error": {
                    "type": "usage_limit_reached",
                    "plan_type": "plus",
                    "resets_at": 1_700_000_000,
                }
            }
        )

        err = map_api_error(_http_error(429, body))

        self.assertEqual(err.kind, "usage_limit_reached")
        self.assertIsInstance(err.payload, UsageLimitReachedError)
        self.assertEqual(err.payload.plan_type.known, KnownPlan.PLUS)
        self.assertEqual(
            err.payload.resets_at,
            datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        )

    def test_map_api_error_does_not_fallback_limit_name_to_limit_id(self) -> None:
        headers = {ACTIVE_LIMIT_HEADER: "codex_other"}
        body = _json_body(
            {"error": {"type": "usage_limit_reached", "plan_type": "pro"}}
        )

        err = map_api_error(_http_error(429, body, headers=headers))

        self.assertEqual(err.kind, "usage_limit_reached")
        self.assertIsNone(err.payload.rate_limits.limit_name)

    def test_map_api_error_ignores_unparseable_rate_limit_reached_type_headers(self) -> None:
        for value in ["future_rate_limit_reached_type", b"\xff"]:
            headers = {"x-codex-rate-limit-reached-type": value}
            body = _json_body(
                {"error": {"type": "usage_limit_reached", "plan_type": "pro"}}
            )

            err = map_api_error(_http_error(429, body, headers=headers))

            self.assertEqual(err.kind, "usage_limit_reached")
            self.assertIsNone(err.payload.rate_limit_reached_type)

    def test_map_api_error_maps_usage_not_included_429(self) -> None:
        body = _json_body({"error": {"type": "usage_not_included"}})

        err = map_api_error(_http_error(429, body))

        self.assertEqual(err.kind, "usage_not_included")

    def test_map_api_error_maps_retry_limit_request_tracking_id(self) -> None:
        err = map_api_error(
            _http_error(
                429,
                _json_body({"error": {"type": "other"}}),
                headers={CF_RAY_HEADER: "ray-429"},
            )
        )

        self.assertEqual(err.kind, "retry_limit")
        self.assertEqual(err.payload.request_id, "ray-429")

    def test_map_api_error_maps_retry_limit_transport_without_request_id(self) -> None:
        # Source: codex-api/src/api_bridge.rs TransportError::RetryLimit arm.
        # Contract: synthetic retry-limit transport errors use HTTP 500 and no
        # request id.
        err = map_api_error(ApiError.transport_error(TransportError.retry_limit()))

        self.assertEqual(err.kind, "retry_limit")
        self.assertEqual(err.payload.status, 500)
        self.assertIsNone(err.payload.request_id)

    def test_map_api_error_maps_timeout_network_build_and_internal_server_error(self) -> None:
        # Source: codex-api/src/api_bridge.rs TransportError matching arms.
        # Contract: timeout becomes RequestTimeout, network/build become stream,
        # and HTTP 500 becomes InternalServerError.
        timeout = map_api_error(ApiError.transport_error(TransportError.timeout()))
        network = map_api_error(
            ApiError.transport_error(TransportError.network("dns failed"))
        )
        build = map_api_error(
            ApiError.transport_error(TransportError.build("bad header"))
        )
        internal = map_api_error(_http_error(500, "oops"))

        self.assertEqual(timeout.kind, "request_timeout")
        self.assertEqual(network.kind, "stream")
        self.assertEqual(network.message, "dns failed")
        self.assertEqual(build.kind, "stream")
        self.assertEqual(build.message, "bad header")
        self.assertEqual(internal.kind, "internal_server_error")

    def test_map_api_error_extracts_identity_auth_details_from_headers(self) -> None:
        x_error_json = base64.b64encode(
            b'{"error":{"code":"token_expired"}}'
        ).decode()
        headers = {
            REQUEST_ID_HEADER: "req-401",
            CF_RAY_HEADER: "ray-401",
            X_OPENAI_AUTHORIZATION_ERROR_HEADER: "missing_authorization_header",
            X_ERROR_JSON_HEADER: x_error_json,
        }

        err = map_api_error(
            _http_error(
                401,
                '{"detail":"Unauthorized"}',
                headers=headers,
                url="https://chatgpt.com/backend-api/codex/models",
            )
        )

        self.assertEqual(err.kind, "unexpected_status")
        payload = err.payload
        self.assertEqual(payload.request_id, "req-401")
        self.assertEqual(payload.cf_ray, "ray-401")
        self.assertEqual(
            payload.identity_authorization_error,
            "missing_authorization_header",
        )
        self.assertEqual(payload.identity_error_code, "token_expired")

    def test_map_api_error_uses_request_id_before_oai_request_id_and_cf_ray(self) -> None:
        # Source: codex-api/src/api_bridge.rs extract_request_id and
        # extract_request_tracking_id helpers.
        # Contract: x-request-id wins over x-oai-request-id for unexpected
        # status; retry-limit tracking falls back from request id to cf-ray.
        headers = {
            REQUEST_ID_HEADER: "req-primary",
            OAI_REQUEST_ID_HEADER: "req-oai",
            CF_RAY_HEADER: "ray-fallback",
        }

        unexpected = map_api_error(_http_error(401, "nope", headers=headers))
        retry_limit = map_api_error(
            _http_error(
                429,
                _json_body({"error": {"type": "other"}}),
                headers={OAI_REQUEST_ID_HEADER: "req-oai", CF_RAY_HEADER: "ray"},
            )
        )

        self.assertEqual(unexpected.kind, "unexpected_status")
        self.assertEqual(unexpected.payload.request_id, "req-primary")
        self.assertEqual(retry_limit.kind, "retry_limit")
        self.assertEqual(retry_limit.payload.request_id, "req-oai")

    def test_map_api_error_ignores_invalid_x_error_json_identity_code(self) -> None:
        # Source: codex-api/src/api_bridge.rs extract_x_error_json_code helper.
        # Contract: invalid base64/JSON/code shapes are ignored instead of
        # changing UnexpectedStatus classification.
        for encoded in ["not-base64", base64.b64encode(b'{"error":{}}').decode()]:
            with self.subTest(encoded=encoded):
                err = map_api_error(
                    _http_error(
                        401,
                        "unauthorized",
                        headers={X_ERROR_JSON_HEADER: encoded},
                    )
                )

                self.assertEqual(err.kind, "unexpected_status")
                self.assertIsNone(err.payload.identity_error_code)


if __name__ == "__main__":
    unittest.main()
