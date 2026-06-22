"""Rust-derived tests for ``codex-client/src/request.rs``.

Rust crate: ``codex-client``
Rust module: ``src/request.rs``

Rust tests mirrored where possible:
- ``prepare_body_for_send_serializes_json_and_sets_content_type``
- ``prepare_body_for_send_rejects_existing_content_encoding_when_compressing``

Rust zstd byte production uses ``zstd::stream::encode_all(..., 3)``. The
Python port preserves dependency-light behavior by producing a valid Zstandard
frame with raw blocks rather than byte-identical level-3 compressed blocks.
"""

from __future__ import annotations

import unittest

from pycodex.codex_client import PreparedRequestBody
from pycodex.codex_client import Request
from pycodex.codex_client import RequestBody
from pycodex.codex_client import RequestCompression
from pycodex.codex_client import Response


def _decode_single_segment_raw_zstd_frame(frame: bytes) -> bytes:
    """Small test decoder for the raw-block zstd frame shape emitted by PyCodex."""

    assert frame.startswith(b"\x28\xb5\x2f\xfd")
    descriptor = frame[4]
    assert descriptor & 0x20
    size_flag = descriptor & 0x03
    offset = 5
    if size_flag == 0:
        expected_size = frame[offset]
        offset += 1
    elif size_flag == 1:
        expected_size = int.from_bytes(frame[offset : offset + 2], "little") + 256
        offset += 2
    elif size_flag == 2:
        expected_size = int.from_bytes(frame[offset : offset + 4], "little")
        offset += 4
    else:
        expected_size = int.from_bytes(frame[offset : offset + 8], "little")
        offset += 8

    decoded = bytearray()
    while True:
        header = int.from_bytes(frame[offset : offset + 3], "little")
        offset += 3
        is_last = header & 1
        block_type = (header >> 1) & 0b11
        block_size = header >> 3
        assert block_type == 0
        decoded.extend(frame[offset : offset + block_size])
        offset += block_size
        if is_last:
            break

    assert offset == len(frame)
    assert len(decoded) == expected_size
    return bytes(decoded)


class CodexClientRequestRsTests(unittest.TestCase):
    def test_prepare_body_for_send_serializes_json_and_sets_content_type(self) -> None:
        request = Request.new("POST", "https://example.com/v1/responses").with_json(
            {"model": "test-model"}
        )

        prepared = request.prepare_body_for_send()

        self.assertEqual(prepared.body, b'{"model":"test-model"}')
        self.assertEqual(prepared.headers.get("content-type"), "application/json")
        self.assertEqual(request.body, RequestBody.json({"model": "test-model"}))
        self.assertEqual(request.compression, RequestCompression.NONE)

    def test_prepare_body_for_send_rejects_existing_content_encoding_when_compressing(self) -> None:
        request = (
            Request.new("POST", "https://example.com/v1/responses")
            .with_json({"model": "test-model"})
            .with_compression(RequestCompression.ZSTD)
            .with_headers({"content-encoding": "gzip"})
        )

        with self.assertRaisesRegex(
            ValueError,
            "request compression was requested but content-encoding is already set",
        ):
            request.prepare_body_for_send()

    def test_raw_body_cannot_be_compressed_and_is_not_content_typed(self) -> None:
        raw = Request.new("POST", "https://example.com/upload").with_raw_body(b"abc")

        prepared = raw.prepare_body_for_send()

        self.assertEqual(prepared.body, b"abc")
        self.assertEqual(prepared.headers, {})
        with self.assertRaisesRegex(
            ValueError, "request compression cannot be used with raw bodies"
        ):
            raw.with_compression(RequestCompression.ZSTD).prepare_body_for_send()

    def test_prepare_body_for_send_does_not_mutate_request_headers_or_body(self) -> None:
        headers = {"x-test": "1"}
        request = (
            Request.new("POST", "https://example.com/v1/responses")
            .with_headers(headers)
            .with_json({"model": "test-model"})
        )

        prepared = request.prepare_body_for_send()
        prepared.headers["x-test"] = "changed"

        self.assertEqual(headers, {"x-test": "1"})
        self.assertEqual(request.headers, {"x-test": "1"})
        self.assertEqual(request.body, RequestBody.json({"model": "test-model"}))

    def test_body_bytes_returns_empty_bytes_for_absent_body(self) -> None:
        self.assertEqual(PreparedRequestBody(headers={}, body=None).body_bytes(), b"")
        self.assertEqual(PreparedRequestBody(headers={}, body=b"abc").body_bytes(), b"abc")

    def test_response_shape_matches_rust_public_struct_fields(self) -> None:
        response = Response(status=200, headers={"x-test": "1"}, body=b"ok")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers, {"x-test": "1"})
        self.assertEqual(response.body, b"ok")

    def test_zstd_byte_production_returns_valid_zstd_raw_frame(self) -> None:
        # Rust crate/module: codex-client/src/request.rs
        # Contract: RequestCompression::Zstd serializes JSON, sets
        # content-encoding: zstd, and returns bytes that are actually a zstd
        # encoded payload. Python uses a standard-library raw-block frame.
        request = (
            Request.new("POST", "https://example.com/v1/responses")
            .with_json({"model": "test-model"})
            .with_compression(RequestCompression.ZSTD)
        )

        prepared = request.prepare_body_for_send()

        self.assertEqual(prepared.headers["content-encoding"], "zstd")
        self.assertEqual(prepared.headers["content-type"], "application/json")
        self.assertNotEqual(prepared.body, b'{"model":"test-model"}')
        self.assertEqual(
            _decode_single_segment_raw_zstd_frame(prepared.body or b""),
            b'{"model":"test-model"}',
        )

    def test_zstd_raw_frame_uses_multiple_raw_blocks_for_large_json(self) -> None:
        # Rust crate/module: codex-client/src/request.rs
        # Contract: compressed request body production handles arbitrary JSON
        # byte payload sizes through the zstd stream boundary.
        text = "x" * (130 * 1024)
        request = (
            Request.new("POST", "https://example.com/v1/responses")
            .with_json({"payload": text})
            .with_compression(RequestCompression.ZSTD)
        )

        prepared = request.prepare_body_for_send()
        decoded = _decode_single_segment_raw_zstd_frame(prepared.body or b"")

        self.assertEqual(decoded, (b'{"payload":"' + text.encode() + b'"}'))


if __name__ == "__main__":
    unittest.main()
