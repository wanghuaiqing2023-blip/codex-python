"""Rust integration parity for ``core/tests/suite/request_compression.rs``."""

from __future__ import annotations

import json
import unittest

from pycodex.core.http_transport import HttpTransportConfig, prepare_request_body_for_transport


class RequestCompressionSuiteParityTests(unittest.TestCase):
    def test_request_body_is_zstd_compressed_for_codex_backend_when_enabled(self) -> None:
        """Rust test: ``request_body_is_zstd_compressed_for_codex_backend_when_enabled``."""

        body = json.dumps({"input": "compress me"}, separators=(",", ":")).encode("utf-8")
        calls: list[bytes] = []

        def fake_zstd_compress(payload: bytes) -> bytes:
            calls.append(payload)
            return b"zstd:" + payload

        compressed, headers = prepare_request_body_for_transport(
            body,
            {"Content-Type": "application/json"},
            HttpTransportConfig(
                "https://example.test/backend-api/codex/v1/responses",
                enable_request_compression=True,
                use_codex_backend_auth=True,
            ),
            zstd_compress=fake_zstd_compress,
        )

        self.assertEqual(headers["Content-Encoding"], "zstd")
        self.assertEqual(calls, [body])
        decoded = json.loads(compressed.removeprefix(b"zstd:").decode("utf-8"))
        self.assertIn("input", decoded)
        self.assertEqual(decoded["input"], "compress me")

    def test_request_body_is_not_compressed_for_api_key_auth_even_when_enabled(self) -> None:
        """Rust test: ``request_body_is_not_compressed_for_api_key_auth_even_when_enabled``."""

        body = json.dumps({"input": "do not compress"}, separators=(",", ":")).encode("utf-8")

        def fail_if_called(_payload: bytes) -> bytes:
            raise AssertionError("API-key auth must not invoke request compression")

        prepared, headers = prepare_request_body_for_transport(
            body,
            {"Content-Type": "application/json"},
            HttpTransportConfig(
                "https://example.test/backend-api/codex/v1/responses",
                enable_request_compression=True,
                use_codex_backend_auth=False,
            ),
            zstd_compress=fail_if_called,
        )

        self.assertNotIn("Content-Encoding", headers)
        self.assertEqual(prepared, body)
        decoded = json.loads(prepared.decode("utf-8"))
        self.assertIn("input", decoded)
        self.assertEqual(decoded["input"], "do not compress")


if __name__ == "__main__":
    unittest.main()
