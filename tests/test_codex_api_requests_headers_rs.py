"""Rust-derived tests for ``codex-api/src/requests/headers.rs``."""

from __future__ import annotations

import unittest

from pycodex.codex_api import SessionSource
from pycodex.codex_api import SubAgentSource
from pycodex.codex_api import build_session_headers
from pycodex.codex_api import insert_header
from pycodex.codex_api import subagent_header


class CodexApiRequestsHeadersRsTests(unittest.TestCase):
    def test_build_session_headers_inserts_present_ids_only(self) -> None:
        # Rust crate/module: codex-api/src/requests/headers.rs
        # Contract: build_session_headers inserts optional session-id and
        # thread-id through insert_header.
        self.assertEqual(
            build_session_headers("sess_123", "thread_456"),
            {"session-id": "sess_123", "thread-id": "thread_456"},
        )
        self.assertEqual(build_session_headers(None, "thread_456"), {"thread-id": "thread_456"})
        self.assertEqual(build_session_headers(None, None), {})

    def test_subagent_header_maps_known_subagent_sources(self) -> None:
        # Rust crate/module: codex-api/src/requests/headers.rs
        # Contract: subagent_header maps known SubAgentSource variants to the
        # exact header strings used by responses endpoint code.
        cases = {
            SubAgentSource.REVIEW: "review",
            SubAgentSource.COMPACT: "compact",
            SubAgentSource.MEMORY_CONSOLIDATION: "memory_consolidation",
            SubAgentSource.THREAD_SPAWN: "collab_spawn",
        }

        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(subagent_header(SessionSource.sub_agent(source)), expected)

    def test_subagent_header_uses_other_label_and_ignores_non_subagent(self) -> None:
        # Rust crate/module: codex-api/src/requests/headers.rs
        # Contract: Other(label) returns the label, while non-subagent session
        # sources return None.
        self.assertEqual(
            subagent_header(SessionSource.sub_agent("custom-label")),
            "custom-label",
        )
        self.assertIsNone(subagent_header(SessionSource.other()))
        self.assertIsNone(subagent_header(None))

    def test_insert_header_skips_invalid_name_or_value(self) -> None:
        # Rust crate/module: codex-api/src/requests/headers.rs
        # Contract: insert_header only inserts when both HeaderName parsing and
        # HeaderValue::from_str succeed.
        headers: dict[str, str] = {}

        insert_header(headers, "X-Test", "ok")
        insert_header(headers, "bad header", "blocked")
        insert_header(headers, "x-bad", "line\nbreak")

        self.assertEqual(headers, {"x-test": "ok"})

    def test_insert_header_value_validation_matches_header_value_from_str(self) -> None:
        # Rust crate/module: codex-api/src/requests/headers.rs
        # Contract: HeaderValue::from_str accepts visible ASCII and HTAB, but
        # rejects other controls, DEL, and non-ASCII text.
        headers: dict[str, str] = {}

        insert_header(headers, "x-tab", "a\tb")
        insert_header(headers, "x-nul", "bad\0value")
        insert_header(headers, "x-del", "bad\x7fvalue")
        insert_header(headers, "x-nonascii", "snowman \u2603")

        self.assertEqual(headers, {"x-tab": "a\tb"})


if __name__ == "__main__":
    unittest.main()
