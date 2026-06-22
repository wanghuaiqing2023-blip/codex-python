"""Rust-derived tests for ``codex-client/src/sse.rs``.

Rust crate: ``codex-client``
Rust module: ``src/sse.rs``

Behavior contract:
- forward raw SSE ``data:`` frames as UTF-8 strings;
- convert transport/parser errors to ``StreamError::Stream``;
- report ``stream closed before completion`` when upstream ends;
- report ``StreamError::Timeout`` on idle timeout.
"""

from __future__ import annotations

import unittest

from pycodex.codex_client import IdleTimeout
from pycodex.codex_client import TransportError
from pycodex.codex_client import sse_stream


class CodexClientSseRsTests(unittest.TestCase):
    def test_sse_stream_forwards_raw_data_frames(self) -> None:
        results = list(
            sse_stream(
                [
                    b": comment\n",
                    b"data: first\n\n",
                    b"data: second line 1\n",
                    b"data: second line 2\n\n",
                ],
                idle_timeout=5.0,
            )
        )

        self.assertTrue(results[0].is_ok)
        self.assertEqual(results[0].data, "first")
        self.assertTrue(results[1].is_ok)
        self.assertEqual(results[1].data, "second line 1\nsecond line 2")
        self.assertFalse(results[2].is_ok)
        self.assertEqual(str(results[2].error), "stream failed: stream closed before completion")

    def test_sse_stream_handles_chunk_boundaries(self) -> None:
        results = list(sse_stream([b"data: hel", b"lo\n", b"\n"]))

        self.assertEqual([result.data for result in results if result.is_ok], ["hello"])
        self.assertEqual(str(results[-1].error), "stream failed: stream closed before completion")

    def test_sse_stream_maps_transport_error_to_stream_error_and_exits(self) -> None:
        results = list(sse_stream([TransportError.network("reset"), b"data: ignored\n\n"]))

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].is_ok)
        self.assertEqual(str(results[0].error), "stream failed: network error: reset")

    def test_sse_stream_maps_parser_error_to_stream_error_and_exits(self) -> None:
        results = list(sse_stream([b"data: \xff\n\n"]))

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].is_ok)
        self.assertIn("stream failed:", str(results[0].error))

    def test_sse_stream_reports_idle_timeout(self) -> None:
        results = list(sse_stream([IdleTimeout(), b"data: ignored\n\n"]))

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].is_ok)
        self.assertEqual(str(results[0].error), "timeout")

    def test_sse_stream_reports_close_before_completion_even_after_events(self) -> None:
        results = list(sse_stream([b"data: done\n\n"]))

        self.assertEqual(results[0].data, "done")
        self.assertFalse(results[1].is_ok)
        self.assertEqual(str(results[1].error), "stream failed: stream closed before completion")


if __name__ == "__main__":
    unittest.main()
