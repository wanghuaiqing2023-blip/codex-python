import unittest

from pycodex.core.tools.context import (
    AbortedToolOutput,
    ApplyPatchToolOutput,
    ExecCommandToolOutput,
    FunctionToolOutput,
    ToolPayload,
    ToolSearchOutput,
    function_tool_response,
    telemetry_preview,
    TELEMETRY_PREVIEW_MAX_BYTES,
    TELEMETRY_PREVIEW_MAX_LINES,
    TELEMETRY_PREVIEW_TRUNCATION_NOTICE,
)
from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ResponseInputItem,
    SearchToolCallParams,
    TruncationPolicyConfig,
)


class CoreToolsContextTests(unittest.TestCase):
    # Rust source contracts:
    # - codex/codex-rs/core/src/tools/context.rs
    # - codex/codex-rs/core/src/tools/context_tests.rs

    def test_custom_tool_calls_roundtrip_as_custom_outputs(self) -> None:
        # Rust test: custom_tool_calls_should_roundtrip_as_custom_outputs
        response = FunctionToolOutput.from_text("patched", True).to_response_item(
            "call-42",
            ToolPayload.custom("patch"),
        )

        self.assertEqual(response.type, "custom_tool_call_output")
        self.assertEqual(response.call_id, "call-42")
        self.assertIsInstance(response.output, FunctionCallOutputPayload)
        self.assertIsNone(response.output.content_items)
        self.assertEqual(response.output.to_text(), "patched")
        self.assertEqual(response.output.success, True)

    def test_function_payloads_remain_function_outputs(self) -> None:
        # Rust test: function_payloads_remain_function_outputs
        response = FunctionToolOutput.from_text("ok", True).to_response_item(
            "fn-1",
            ToolPayload.function("{}"),
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "fn-1")
        self.assertIsInstance(response.output, FunctionCallOutputPayload)
        self.assertIsNone(response.output.content_items)
        self.assertEqual(response.output.to_text(), "ok")
        self.assertEqual(response.output.success, True)

    def test_custom_tool_calls_can_derive_text_from_content_items(self) -> None:
        # Rust test: custom_tool_calls_can_derive_text_from_content_items
        body = (
            FunctionCallOutputContentItem.input_text("line 1"),
            FunctionCallOutputContentItem.input_image(
                "data:image/png;base64,AAA",
                DEFAULT_IMAGE_DETAIL,
            ),
            FunctionCallOutputContentItem.input_text("line 2"),
        )

        response = FunctionToolOutput.from_content(body, True).to_response_item(
            "call-99",
            ToolPayload.custom("patch"),
        )

        self.assertEqual(response.type, "custom_tool_call_output")
        self.assertEqual(response.call_id, "call-99")
        self.assertEqual(response.output.content_items, body)
        self.assertEqual(response.output.to_text(), "line 1\nline 2")
        self.assertEqual(response.output.success, True)

    def test_log_preview_uses_content_items_when_plain_text_is_missing(self) -> None:
        # Rust test: log_preview_uses_content_items_when_plain_text_is_missing
        output = FunctionToolOutput.from_content(
            (FunctionCallOutputContentItem.input_text("preview"),),
            True,
        )

        self.assertEqual(output.log_preview(), "preview")
        self.assertEqual(output.into_text(), "preview")

    def test_aborted_tool_search_returns_empty_completed_tool_search_output(self) -> None:
        # Rust source: AbortedToolOutput::to_response_item special-cases ToolSearch payloads.
        response = AbortedToolOutput("cancelled").to_response_item(
            "search-1",
            ToolPayload.tool_search(SearchToolCallParams("calendar")),
        )

        self.assertEqual(response.type, "tool_search_output")
        self.assertEqual(response.call_id, "search-1")
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.execution, "client")
        self.assertEqual(response.tools, ())

    def test_aborted_function_payload_returns_function_output_without_success(self) -> None:
        # Rust source: AbortedToolOutput::to_response_item uses function_tool_response for non-tool-search payloads.
        response = AbortedToolOutput("cancelled").to_response_item(
            "fn-1",
            ToolPayload.function("{}"),
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "fn-1")
        self.assertEqual(response.output.to_text(), "cancelled")
        self.assertIsNone(response.output.success)

    def test_apply_patch_tool_output_returns_successful_function_output_and_post_response(self) -> None:
        # Rust source: ApplyPatchToolOutput::to_response_item/post_tool_use_response/code_mode_result
        output = ApplyPatchToolOutput.from_text("patch applied")
        payload = ToolPayload.function("{}")

        response = output.to_response_item("patch-1", payload)

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "patch-1")
        self.assertEqual(response.output.to_text(), "patch applied")
        self.assertEqual(response.output.success, True)
        self.assertEqual(output.post_tool_use_response("patch-1", payload), "patch applied")
        self.assertEqual(output.code_mode_result(payload), {})

    def test_tool_search_payloads_roundtrip_as_tool_search_outputs(self) -> None:
        # Rust test: tool_search_payloads_roundtrip_as_tool_search_outputs
        tool = {
            "type": "function",
            "name": "create_event",
            "description": "",
            "strict": False,
            "defer_loading": True,
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }

        response = ToolSearchOutput((tool,)).to_response_item(
            "search-1",
            ToolPayload.tool_search(SearchToolCallParams("calendar")),
        )

        self.assertEqual(response.type, "tool_search_output")
        self.assertEqual(response.call_id, "search-1")
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.execution, "client")
        self.assertEqual(response.tools, (tool,))

    def test_telemetry_preview_returns_original_within_limits_and_truncates_by_bytes(self) -> None:
        # Rust tests: telemetry_preview_returns_original_within_limits and telemetry_preview_truncates_by_bytes
        self.assertEqual(telemetry_preview("short output"), "short output")

        preview = telemetry_preview("x" * (TELEMETRY_PREVIEW_MAX_BYTES + 8))

        self.assertIn(TELEMETRY_PREVIEW_TRUNCATION_NOTICE, preview)
        self.assertLessEqual(
            len(preview.encode("utf-8")),
            TELEMETRY_PREVIEW_MAX_BYTES + len(TELEMETRY_PREVIEW_TRUNCATION_NOTICE.encode("utf-8")) + 1,
        )

    def test_telemetry_preview_truncates_by_lines(self) -> None:
        # Rust test: telemetry_preview_truncates_by_lines
        content = "\n".join(f"line {idx}" for idx in range(TELEMETRY_PREVIEW_MAX_LINES + 5))

        preview = telemetry_preview(content)
        lines = preview.splitlines()

        self.assertLessEqual(len(lines), TELEMETRY_PREVIEW_MAX_LINES + 1)
        self.assertEqual(lines[-1], TELEMETRY_PREVIEW_TRUNCATION_NOTICE)

    def test_exec_command_tool_output_formats_truncated_response(self) -> None:
        # Rust test: exec_command_tool_output_formats_truncated_response
        response = ExecCommandToolOutput(
            event_call_id="call-42",
            chunk_id="abc123",
            wall_time_seconds=1.25,
            raw_output=b"token one token two token three token four token five",
            truncation_policy=TruncationPolicyConfig.tokens(10_000),
            max_output_tokens=4,
            process_id=None,
            exit_code=0,
            original_token_count=10,
            hook_command=None,
        ).to_response_item("call-42", ToolPayload.function("{}"))

        self.assertEqual(
            response.type,
            "function_call_output",
        )
        self.assertEqual(response.call_id, "call-42")
        self.assertEqual(response.output.success, True)
        text = response.output.to_text()
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("Chunk ID: abc123\n", text)
        self.assertIn("Wall time: 1.2500 seconds\n", text)
        self.assertIn("Process exited with code 0\n", text)
        self.assertIn("Original token count: 10\n", text)
        self.assertIn("\nOutput:\n", text)
        self.assertIn("tokens truncated", text)

    def test_function_tool_response_uses_content_items_for_multi_item_body(self) -> None:
        # Rust helper behavior: single text bodies become text payloads; mixed bodies remain content items.
        body = (
            FunctionCallOutputContentItem.input_text("line 1"),
            FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL),
        )

        response = function_tool_response("call-1", ToolPayload.function("{}"), body, True)

        self.assertEqual(
            response,
            ResponseInputItem.function_call_output(
                "call-1",
                FunctionCallOutputPayload.from_content_items(body, True),
            ),
        )


if __name__ == "__main__":
    unittest.main()
