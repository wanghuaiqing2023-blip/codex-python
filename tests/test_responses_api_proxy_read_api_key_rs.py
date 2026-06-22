import collections
import io
import unittest

from pycodex.responses_api_proxy import (
    AUTH_HEADER_PREFIX,
    BUFFER_SIZE,
    ResponsesApiProxyError,
    read_auth_header_with,
)


class ResponsesApiProxyReadApiKeyRsTests(unittest.TestCase):
    # Rust crate/module: codex-responses-api-proxy::read_api_key.
    # Rust test: reads_key_with_no_newlines.
    def test_reads_key_with_no_newlines(self) -> None:
        sent = False

        def reader(buf: bytearray) -> int:
            nonlocal sent
            if sent:
                return 0
            data = b"sk-abc123"
            buf[: len(data)] = data
            sent = True
            return len(data)

        self.assertEqual(read_auth_header_with(reader), "Bearer sk-abc123")

    # Rust crate/module: codex-responses-api-proxy::read_api_key.
    # Rust test: reads_key_with_short_reads.
    def test_reads_key_with_short_reads(self) -> None:
        chunks = collections.deque([b"sk-", b"abc", b"123\n"])

        def reader(buf: bytearray) -> int:
            if not chunks:
                return 0
            data = chunks.popleft()
            buf[: len(data)] = data
            return len(data)

        self.assertEqual(read_auth_header_with(reader), "Bearer sk-abc123")

    # Rust crate/module: codex-responses-api-proxy::read_api_key.
    # Rust test: reads_key_and_trims_newlines.
    def test_reads_key_and_trims_newlines(self) -> None:
        sent = False

        def reader(buf: bytearray) -> int:
            nonlocal sent
            if sent:
                return 0
            data = b"sk-abc123\r\n"
            buf[: len(data)] = data
            sent = True
            return len(data)

        self.assertEqual(read_auth_header_with(reader), "Bearer sk-abc123")

    # Rust crate/module: codex-responses-api-proxy::read_api_key.
    # Rust test: errors_when_no_input_provided.
    def test_errors_when_no_input_provided(self) -> None:
        with self.assertRaisesRegex(ResponsesApiProxyError, "must be provided"):
            read_auth_header_with(lambda _buf: 0)

    # Rust crate/module: codex-responses-api-proxy::read_api_key.
    # Rust test: errors_when_buffer_filled.
    def test_errors_when_buffer_filled(self) -> None:
        def reader(buf: bytearray) -> int:
            data = b"a" * (BUFFER_SIZE - len(AUTH_HEADER_PREFIX))
            buf[: len(data)] = data
            return len(data)

        with self.assertRaisesRegex(ResponsesApiProxyError, "too large to fit"):
            read_auth_header_with(reader)

    # Rust crate/module: codex-responses-api-proxy::read_api_key.
    # Rust test: propagates_io_error.
    def test_propagates_io_error(self) -> None:
        with self.assertRaisesRegex(OSError, "boom"):
            read_auth_header_with(lambda _buf: (_ for _ in ()).throw(OSError("boom")))

    # Rust crate/module: codex-responses-api-proxy::read_api_key.
    # Rust tests: errors_on_invalid_utf8 and errors_on_invalid_characters.
    def test_errors_on_invalid_key_bytes_or_characters(self) -> None:
        for data in (b"sk-abc\xff", b"sk-abc!23"):
            sent = False

            def reader(buf: bytearray, payload: bytes = data) -> int:
                nonlocal sent
                if sent:
                    return 0
                buf[: len(payload)] = payload
                sent = True
                return len(payload)

            with self.assertRaisesRegex(ResponsesApiProxyError, "ASCII letters"):
                read_auth_header_with(reader)


if __name__ == "__main__":
    unittest.main()
