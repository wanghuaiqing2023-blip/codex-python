"""Rust-derived tests for ``codex-api/src/files.rs``."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pycodex.codex_api import OPENAI_FILE_FINALIZE_RETRY_DELAY
from pycodex.codex_api import OPENAI_FILE_REQUEST_TIMEOUT
from pycodex.codex_api import OPENAI_FILE_USE_CASE
from pycodex.codex_api import OpenAiFileError
from pycodex.codex_api import OpenAiFileResponse
from pycodex.codex_api import openai_file_uri
from pycodex.codex_api import upload_local_file


class _Auth:
    def add_auth_headers(self, headers: dict[str, str]) -> None:
        headers["authorization"] = "Bearer token"
        headers["chatgpt-account-id"] = "account_id"

    def to_auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        self.add_auth_headers(headers)
        return headers


class _Transport:
    def __init__(self, *, finalize_payloads: list[dict[str, object]] | None = None) -> None:
        self.calls: list[tuple[str, str, object, object]] = []
        self.finalize_payloads = finalize_payloads or [
            {
                "status": "success",
                "download_url": "https://download.test/file_123",
                "file_name": "hello.txt",
                "mime_type": "text/plain",
            }
        ]

    def create_file(self, url: str, headers: object, body: object, timeout: float) -> OpenAiFileResponse:
        self.calls.append(("create", url, headers, body))
        self.create_timeout = timeout
        return OpenAiFileResponse(
            200,
            json.dumps({"file_id": "file_123", "upload_url": "https://upload.test/file_123"}),
        )

    def upload_file(self, url: str, headers: object, body: bytes, timeout: float) -> OpenAiFileResponse:
        self.calls.append(("upload", url, headers, body))
        self.upload_timeout = timeout
        return OpenAiFileResponse(200, "")

    def finalize_file(self, url: str, headers: object, body: object, timeout: float) -> OpenAiFileResponse:
        self.calls.append(("finalize", url, headers, body))
        self.finalize_timeout = timeout
        payload = self.finalize_payloads.pop(0)
        return OpenAiFileResponse(200, json.dumps(payload))


class CodexApiFilesRsTests(unittest.TestCase):
    def test_openai_file_uri_uses_sediment_prefix(self) -> None:
        # Rust crate/module: codex-api/src/files.rs
        # Contract: openai_file_uri prefixes file ids with sediment://.
        self.assertEqual(openai_file_uri("file_123"), "sediment://file_123")

    def test_upload_local_file_returns_canonical_uri_and_records_request_shapes(self) -> None:
        # Rust test: upload_local_file_returns_canonical_uri.
        # Contract: create, upload, retry finalize, and success payload produce
        # the UploadedOpenAiFile shape with the canonical sediment URI.
        transport = _Transport(
            finalize_payloads=[
                {"status": "retry"},
                {
                    "status": "success",
                    "download_url": "https://download.test/file_123",
                    "file_name": "hello.txt",
                    "mime_type": "text/plain",
                },
            ]
        )
        sleeps: list[float] = []
        clock_values = iter([0.0, 0.1])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hello.txt"
            path.write_bytes(b"hello")

            uploaded = asyncio.run(
                upload_local_file(
                    "https://api.test/backend-api/",
                    _Auth(),
                    path,
                    transport=transport,
                    monotonic=lambda: next(clock_values),
                    sleep=lambda delay: sleeps.append(delay),
                )
            )

        self.assertEqual(uploaded.file_id, "file_123")
        self.assertEqual(uploaded.uri, "sediment://file_123")
        self.assertEqual(uploaded.download_url, "https://download.test/file_123")
        self.assertEqual(uploaded.file_name, "hello.txt")
        self.assertEqual(uploaded.file_size_bytes, 5)
        self.assertEqual(uploaded.mime_type, "text/plain")
        self.assertEqual(sleeps, [OPENAI_FILE_FINALIZE_RETRY_DELAY])

        create = transport.calls[0]
        self.assertEqual(create[0], "create")
        self.assertEqual(create[1], "https://api.test/backend-api/files")
        self.assertEqual(create[2], {"authorization": "Bearer token", "chatgpt-account-id": "account_id"})
        self.assertEqual(create[3], {"file_name": "hello.txt", "file_size": 5, "use_case": OPENAI_FILE_USE_CASE})

        upload = transport.calls[1]
        self.assertEqual(upload[0], "upload")
        self.assertEqual(upload[1], "https://upload.test/file_123")
        self.assertEqual(upload[2], {"x-ms-blob-type": "BlockBlob", "content-length": "5"})
        self.assertEqual(upload[3], b"hello")
        self.assertEqual(transport.create_timeout, OPENAI_FILE_REQUEST_TIMEOUT)

    def test_upload_local_file_preflight_errors_match_rust_variants(self) -> None:
        # Rust crate/module: codex-api/src/files.rs
        # Contract: missing paths, directories, and over-limit files produce
        # the corresponding OpenAiFileError variants before any request.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.txt"
            with self.assertRaises(OpenAiFileError) as missing_error:
                asyncio.run(upload_local_file("https://api.test", _Auth(), missing, transport=_Transport()))
            self.assertEqual(missing_error.exception.kind, "missing_path")
            self.assertIn("does not exist", str(missing_error.exception))

            with self.assertRaises(OpenAiFileError) as dir_error:
                asyncio.run(upload_local_file("https://api.test", _Auth(), root, transport=_Transport()))
            self.assertEqual(dir_error.exception.kind, "not_a_file")

            large = root / "large.bin"
            large.write_bytes(b"hello")
            with self.assertRaises(OpenAiFileError) as large_error:
                asyncio.run(
                    upload_local_file(
                        "https://api.test",
                        _Auth(),
                        large,
                        transport=_Transport(),
                        upload_limit_bytes=4,
                    )
                )
            self.assertEqual(large_error.exception.kind, "file_too_large")
            self.assertEqual(large_error.exception.size_bytes, 5)
            self.assertEqual(large_error.exception.limit_bytes, 4)

    def test_upload_local_file_maps_status_decode_and_finalize_failures(self) -> None:
        # Rust crate/module: codex-api/src/files.rs
        # Contract: non-success responses, invalid JSON, retry timeout, missing
        # download_url, and error finalize status map to local error variants.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hello.txt"
            path.write_text("hello", encoding="utf-8")

            class StatusTransport(_Transport):
                def create_file(self, url: str, headers: object, body: object, timeout: float) -> OpenAiFileResponse:
                    return OpenAiFileResponse(500, "boom")

            with self.assertRaises(OpenAiFileError) as status_error:
                asyncio.run(upload_local_file("https://api.test", _Auth(), path, transport=StatusTransport()))
            self.assertEqual(status_error.exception.kind, "unexpected_status")

            class DecodeTransport(_Transport):
                def create_file(self, url: str, headers: object, body: object, timeout: float) -> OpenAiFileResponse:
                    return OpenAiFileResponse(200, "{")

            with self.assertRaises(OpenAiFileError) as decode_error:
                asyncio.run(upload_local_file("https://api.test", _Auth(), path, transport=DecodeTransport()))
            self.assertEqual(decode_error.exception.kind, "decode")

            with self.assertRaises(OpenAiFileError) as not_ready_error:
                asyncio.run(
                    upload_local_file(
                        "https://api.test",
                        _Auth(),
                        path,
                        transport=_Transport(finalize_payloads=[{"status": "retry"}]),
                        monotonic=lambda: 1.0,
                        sleep=lambda _delay: None,
                        finalize_timeout=0.0,
                    )
                )
            self.assertEqual(not_ready_error.exception.kind, "upload_not_ready")

            with self.assertRaises(OpenAiFileError) as missing_url_error:
                asyncio.run(
                    upload_local_file(
                        "https://api.test",
                        _Auth(),
                        path,
                        transport=_Transport(finalize_payloads=[{"status": "success"}]),
                    )
                )
            self.assertEqual(missing_url_error.exception.kind, "upload_failed")
            self.assertEqual(missing_url_error.exception.message, "missing download_url")

            with self.assertRaises(OpenAiFileError) as failed_error:
                asyncio.run(
                    upload_local_file(
                        "https://api.test",
                        _Auth(),
                        path,
                        transport=_Transport(finalize_payloads=[{"status": "failed", "error_message": "bad"}]),
                    )
                )
            self.assertEqual(failed_error.exception.kind, "upload_failed")
            self.assertEqual(failed_error.exception.message, "bad")

    def test_finalize_response_rejects_present_non_string_optional_fields(self) -> None:
        # Rust crate/module: codex-api/src/files.rs
        # Contract: DownloadLinkResponse deserializes optional fields as
        # Option<String>; present non-string values fail serde decode before
        # success/failure branch handling.
        cases = [
            {"status": "success", "download_url": 123},
            {
                "status": "success",
                "download_url": "https://download.test/file_123",
                "file_name": 123,
            },
            {
                "status": "success",
                "download_url": "https://download.test/file_123",
                "mime_type": 123,
            },
            {"status": "failed", "error_message": 123},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hello.txt"
            path.write_text("hello", encoding="utf-8")

            for payload in cases:
                with self.subTest(payload=payload):
                    with self.assertRaises(OpenAiFileError) as caught:
                        asyncio.run(
                            upload_local_file(
                                "https://api.test",
                                _Auth(),
                                path,
                                transport=_Transport(finalize_payloads=[payload]),
                            )
                        )
                    self.assertEqual(caught.exception.kind, "decode")

    def test_finalize_success_missing_file_name_uses_local_file_name(self) -> None:
        # Rust crate/module: codex-api/src/files.rs
        # Contract: successful finalize responses use file_name.unwrap_or(local
        # file_name), while mime_type remains optional.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hello.txt"
            path.write_text("hello", encoding="utf-8")

            uploaded = asyncio.run(
                upload_local_file(
                    "https://api.test",
                    _Auth(),
                    path,
                    transport=_Transport(
                        finalize_payloads=[
                            {
                                "status": "success",
                                "download_url": "https://download.test/file_123",
                            }
                        ]
                    ),
                )
            )

        self.assertEqual(uploaded.file_name, "hello.txt")
        self.assertIsNone(uploaded.mime_type)


if __name__ == "__main__":
    unittest.main()
