"""Rust-derived tests for ``codex-api/src/common.rs``."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from pycodex.codex_api import CompactionInput
from pycodex.codex_api import MemorySummarizeInput
from pycodex.codex_api import MemorySummarizeOutput
from pycodex.codex_api import OpenAiVerbosity
from pycodex.codex_api import RawMemory
from pycodex.codex_api import RawMemoryMetadata
from pycodex.codex_api import Reasoning
from pycodex.codex_api import ResponseCreateWsRequest
from pycodex.codex_api import ResponseProcessedWsRequest
from pycodex.codex_api import ResponseStream
from pycodex.codex_api import ResponsesApiRequest
from pycodex.codex_api import ResponsesWsRequest
from pycodex.codex_api import TextFormatType
from pycodex.codex_api import WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY
from pycodex.codex_api import WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY
from pycodex.codex_api import create_text_param_for_request
from pycodex.codex_api import response_create_client_metadata


@dataclass(frozen=True)
class _Trace:
    traceparent: str | None = None
    tracestate: str | None = None


class CodexApiCommonRsTests(unittest.TestCase):
    def test_response_create_client_metadata_merges_trace_headers(self) -> None:
        # Rust crate/module: codex-api/src/common.rs
        # Contract: response_create_client_metadata merges optional W3C trace
        # fields into existing client_metadata and returns None when empty.
        self.assertIsNone(response_create_client_metadata(None, None))

        metadata = response_create_client_metadata(
            {"existing": "1"},
            _Trace(traceparent="00-abc-def-01", tracestate="state"),
        )

        self.assertEqual(
            metadata,
            {
                "existing": "1",
                WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY: "00-abc-def-01",
                WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY: "state",
            },
        )

    def test_create_text_param_for_request_matches_rust_branches(self) -> None:
        # Rust crate/module: codex-api/src/common.rs
        # Contract: no verbosity/schema returns None; otherwise verbosity maps
        # lower-case and schema creates a strict json_schema format named
        # codex_output_schema.
        self.assertIsNone(create_text_param_for_request(None, None, False))

        text = create_text_param_for_request("High", {"type": "object"}, True)

        self.assertEqual(text.verbosity, OpenAiVerbosity.HIGH)
        self.assertEqual(text.to_json_dict()["verbosity"], "high")
        self.assertEqual(
            text.format.to_json_dict(),
            {
                "type": "json_schema",
                "strict": True,
                "schema": {"type": "object"},
                "name": "codex_output_schema",
            },
        )
        self.assertEqual(text.format.type, TextFormatType.JSON_SCHEMA)

    def test_responses_api_request_converts_to_ws_create_request(self) -> None:
        # Rust crate/module: codex-api/src/common.rs
        # Contract: From<&ResponsesApiRequest> for ResponseCreateWsRequest
        # clones all shared fields, sets previous_response_id/generate to None,
        # and preserves client_metadata.
        request = ResponsesApiRequest(
            model="gpt",
            instructions="be terse",
            input=[{"role": "user"}],
            tools=[{"type": "function"}],
            tool_choice="auto",
            parallel_tool_calls=True,
            reasoning=Reasoning(effort="medium"),
            store=True,
            stream=True,
            include=["reasoning.encrypted_content"],
            service_tier="priority",
            prompt_cache_key="cache-key",
            text=create_text_param_for_request("low", None, False),
            client_metadata={"trace": "1"},
        )

        ws = ResponseCreateWsRequest.from_api_request(request)

        self.assertEqual(ws.previous_response_id, None)
        self.assertEqual(ws.generate, None)
        self.assertEqual(ws.to_json_dict()["model"], "gpt")
        self.assertEqual(ws.to_json_dict()["instructions"], "be terse")
        self.assertEqual(ws.to_json_dict()["parallel_tool_calls"], True)
        self.assertEqual(ws.to_json_dict()["reasoning"], {"effort": "medium"})
        self.assertEqual(ws.to_json_dict()["client_metadata"], {"trace": "1"})

    def test_responses_api_request_preserves_empty_client_metadata(self) -> None:
        # Rust crate/module: codex-api/src/common.rs
        # Contract: From<&ResponsesApiRequest> clones Option<HashMap>; Some({})
        # remains Some({}) instead of becoming None.
        request = ResponsesApiRequest(model="gpt", client_metadata={})

        ws = ResponseCreateWsRequest.from_api_request(request)

        self.assertEqual(ws.client_metadata, {})
        self.assertEqual(ws.to_json_dict()["client_metadata"], {})

    def test_serde_skip_and_rename_shapes_for_payloads(self) -> None:
        # Rust crate/module: codex-api/src/common.rs
        # Contract: serde skip_serializing_if and rename attributes for
        # compaction and memory summarize payloads.
        compaction = CompactionInput(
            model="gpt",
            input=[],
            instructions="",
            tools=[],
            parallel_tool_calls=False,
            reasoning=None,
        )
        memory = MemorySummarizeInput(
            model="gpt",
            raw_memories=[
                RawMemory(
                    id="m1",
                    metadata=RawMemoryMetadata(source_path="/tmp/m1.json"),
                    items=[{"kind": "note"}],
                )
            ],
        )

        self.assertNotIn("instructions", compaction.to_json_dict())
        self.assertEqual(
            memory.to_json_dict(),
            {
                "model": "gpt",
                "traces": [
                    {
                        "id": "m1",
                        "metadata": {"source_path": "/tmp/m1.json"},
                        "items": [{"kind": "note"}],
                    }
                ],
            },
        )

    def test_memory_summarize_output_accepts_trace_summary_and_raw_memory(self) -> None:
        # Rust crate/module: codex-api/src/common.rs
        # Contract: MemorySummarizeOutput renames trace_summary to raw_memory
        # and accepts raw_memory as an alias when deserializing.
        self.assertEqual(
            MemorySummarizeOutput.from_json_dict(
                {"trace_summary": "raw", "memory_summary": "summary"}
            ),
            MemorySummarizeOutput(raw_memory="raw", memory_summary="summary"),
        )
        self.assertEqual(
            MemorySummarizeOutput.from_json_dict(
                {"raw_memory": "alias", "memory_summary": "summary"}
            ).raw_memory,
            "alias",
        )
        with self.assertRaises(KeyError):
            MemorySummarizeOutput.from_json_dict({"memory_summary": "summary"})

    def test_responses_ws_request_tagged_shapes(self) -> None:
        # Rust crate/module: codex-api/src/common.rs
        # Contract: ResponsesWsRequest is tagged by type with response.create
        # and response.processed wire names.
        create = ResponsesWsRequest.response_create(
            ResponseCreateWsRequest(model="gpt", input=[], tools=[])
        )
        processed = ResponsesWsRequest.response_processed(
            ResponseProcessedWsRequest(response_id="resp_1")
        )

        self.assertEqual(create.to_json_dict()["type"], "response.create")
        self.assertEqual(processed.to_json_dict(), {
            "type": "response.processed",
            "response_id": "resp_1",
        })

    def test_response_stream_iterates_events_and_keeps_upstream_request_id(self) -> None:
        # Rust crate/module: codex-api/src/common.rs
        # Contract: ResponseStream carries an event stream and optional
        # upstream request id.
        stream = ResponseStream.from_iterable(["created", "done"], "req_1")

        self.assertEqual(stream.upstream_request_id, "req_1")
        self.assertEqual(list(stream), ["created", "done"])


if __name__ == "__main__":
    unittest.main()
