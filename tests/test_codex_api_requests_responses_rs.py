"""Rust-derived tests for ``codex-api/src/requests/responses.rs``."""

from __future__ import annotations

import unittest

from pycodex.codex_api import Compression
from pycodex.codex_api import attach_item_ids
from pycodex.protocol import ContentItem
from pycodex.protocol import ResponseItem


class CodexApiRequestsResponsesRsTests(unittest.TestCase):
    def test_compression_variants_match_public_request_surface(self) -> None:
        # Rust crate/module: codex-api/src/requests/responses.rs
        # Contract: Compression exposes the public None and Zstd variants, with
        # None as the default request-compression mode at call sites.
        self.assertEqual(Compression.NONE.value, "none")
        self.assertEqual(Compression.ZSTD.value, "zstd")

    def test_attach_item_ids_copies_non_empty_ids_for_matching_response_items(self) -> None:
        # Rust crate/module: codex-api/src/requests/responses.rs
        # Contract: attach_item_ids zips payload input items with original
        # ResponseItem values and inserts non-empty ids for the variants in
        # Rust's or-pattern.
        payload = {
            "input": [
                {"type": "reasoning"},
                {"type": "message"},
                {"type": "web_search_call"},
                {"type": "function_call"},
                {"type": "tool_search_call"},
                {"type": "local_shell_call"},
                {"type": "custom_tool_call"},
            ]
        }
        original_items = [
            ResponseItem.reasoning("rs_1"),
            ResponseItem.message("assistant", [ContentItem.output_text("hello")], id="msg_1"),
            ResponseItem.web_search_call(id="ws_1"),
            ResponseItem.function_call("tool", "{}", "call_1", id="fc_1"),
            ResponseItem.tool_search_call({"query": "needle"}, execution="client", id="ts_1"),
            ResponseItem(type="local_shell_call", id="sh_1"),
            ResponseItem.custom_tool_call("apply_patch", "***", "call_2", id="ct_1"),
        ]

        attach_item_ids(payload, original_items)

        self.assertEqual(
            [item["id"] for item in payload["input"]],
            ["rs_1", "msg_1", "ws_1", "fc_1", "ts_1", "sh_1", "ct_1"],
        )

    def test_attach_item_ids_skips_empty_missing_non_objects_and_non_matching_variants(self) -> None:
        # Rust crate/module: codex-api/src/requests/responses.rs
        # Contract: empty ids, absent optional ids, non-object payload entries,
        # and variants outside Rust's or-pattern do not modify the payload.
        payload = {
            "input": [
                {"type": "message"},
                {"type": "message"},
                {"type": "image_generation_call"},
                "not-an-object",
                {"type": "custom_tool_call"},
            ]
        }
        original_items = [
            ResponseItem.reasoning(""),
            ResponseItem.message("assistant", [ContentItem.output_text("hello")]),
            ResponseItem.image_generation_call("ig_1", "completed", "b64"),
            ResponseItem.function_call("tool", "{}", "call_1", id="fc_1"),
            ResponseItem.custom_tool_call("apply_patch", "***", "call_2", id=""),
        ]

        attach_item_ids(payload, original_items)

        self.assertEqual(
            payload,
            {
                "input": [
                    {"type": "message"},
                    {"type": "message"},
                    {"type": "image_generation_call"},
                    "not-an-object",
                    {"type": "custom_tool_call"},
                ]
            },
        )

    def test_attach_item_ids_returns_when_input_absent_or_not_array(self) -> None:
        # Rust crate/module: codex-api/src/requests/responses.rs
        # Contract: non-array or absent input fields are ignored.
        for payload in ({}, {"input": None}, {"input": {"type": "message"}}):
            with self.subTest(payload=payload):
                before = dict(payload)
                attach_item_ids(payload, [ResponseItem.reasoning("rs_1")])
                self.assertEqual(payload, before)

    def test_attach_item_ids_uses_zip_truncation(self) -> None:
        # Rust crate/module: codex-api/src/requests/responses.rs
        # Contract: iter_mut().zip(original_items.iter()) mutates only pairs
        # present in both lists.
        payload = {"input": [{"type": "reasoning"}, {"type": "message"}]}

        attach_item_ids(payload, [ResponseItem.reasoning("rs_1")])

        self.assertEqual(payload["input"], [{"type": "reasoning", "id": "rs_1"}, {"type": "message"}])

    def test_attach_item_ids_replaces_existing_payload_id(self) -> None:
        # Rust crate/module: codex-api/src/requests/responses.rs
        # Contract: obj.insert("id", Value::String(id.clone())) replaces any
        # existing serialized id on matching object entries.
        payload = {"input": [{"type": "reasoning", "id": "stale"}]}

        attach_item_ids(payload, [ResponseItem.reasoning("rs_fresh")])

        self.assertEqual(payload["input"], [{"type": "reasoning", "id": "rs_fresh"}])


if __name__ == "__main__":
    unittest.main()
