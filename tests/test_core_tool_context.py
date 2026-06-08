import unittest

from pycodex.core import (
    AbortedToolOutput,
    ApplyPatchToolOutput,
    ExecCommandToolOutput,
    FunctionToolOutput,
    JsonToolOutput,
    McpToolOutput,
    PostToolUseFeedbackOutput,
    TELEMETRY_PREVIEW_MAX_BYTES,
    TELEMETRY_PREVIEW_MAX_LINES,
    TELEMETRY_PREVIEW_TRUNCATION_NOTICE,
    ToolCallSource,
    ToolInvocation,
    ToolOutput,
    ToolPayload,
    ToolSearchOutput,
    approx_tokens_from_byte_count_i64,
    boxed_tool_output,
    formatted_truncate_text,
    formatted_truncate_text_content_items_with_policy,
    telemetry_preview,
    truncate_function_output_items_with_policy,
    truncate_text,
)
from pycodex.protocol import (
    CallToolResult,
    DEFAULT_IMAGE_DETAIL,
    FunctionCallOutputContentItem,
    ImageDetail,
    SearchToolCallParams,
    ToolName,
    TruncationPolicyConfig,
)


class ToolContextTests(unittest.TestCase):
    def test_tool_call_source_matches_rust_direct_and_code_mode_variants(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::ToolCallSource
        # Rust contract: tool calls originate either directly from the model or from code-mode runtime cells.
        direct = ToolCallSource.direct()
        code_mode = ToolCallSource.code_mode("cell-1", "runtime-call-2")

        self.assertTrue(direct.is_direct)
        self.assertFalse(direct.is_code_mode)
        self.assertTrue(code_mode.is_code_mode)
        self.assertEqual(code_mode.cell_id, "cell-1")
        self.assertEqual(code_mode.runtime_tool_call_id, "runtime-call-2")

    def test_tool_call_source_rejects_mixed_or_missing_variant_fields(self) -> None:
        with self.assertRaises(ValueError):
            ToolCallSource("direct", cell_id="cell")
        empty = ToolCallSource.code_mode("", "")
        self.assertEqual(empty.cell_id, "")
        self.assertEqual(empty.runtime_tool_call_id, "")
        with self.assertRaises(TypeError):
            ToolCallSource.code_mode(1, "runtime")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            ToolCallSource.code_mode("cell", 1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ToolCallSource("other")

    def test_tool_invocation_wraps_runtime_context_and_payload(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::ToolInvocation
        # Rust contract: invocation carries session, turn, tracker, call id, tool name, source, and payload.
        invocation = ToolInvocation(
            session=object(),
            turn=object(),
            cancellation_token=object(),
            tracker=object(),
            call_id="call-1",
            tool_name="shell",
            source=ToolCallSource.code_mode("cell", "runtime"),
            payload=ToolPayload.function("{}"),
        )

        self.assertTrue(invocation.is_code_mode)
        self.assertEqual(invocation.call_id, "call-1")
        self.assertEqual(invocation.tool_name, ToolName.plain("shell"))

        named_invocation = ToolInvocation(
            session=object(),
            turn=object(),
            cancellation_token=object(),
            tracker=object(),
            call_id="call-2",
            tool_name=ToolName.namespaced("mcp__", "search"),
            source=ToolCallSource.direct(),
            payload=ToolPayload.function("{}"),
        )
        self.assertEqual(named_invocation.tool_name, ToolName.namespaced("mcp__", "search"))

    def test_tool_invocation_rejects_non_rust_context_shapes(self) -> None:
        with self.assertRaises(TypeError):
            ToolInvocation(
                session=None,
                turn=None,
                cancellation_token=None,
                tracker=None,
                call_id="",
                tool_name="shell",
                source=ToolCallSource.direct(),
                payload=ToolPayload.function("{}"),
            )
        with self.assertRaises(TypeError):
            ToolInvocation(
                session=None,
                turn=None,
                cancellation_token=None,
                tracker=None,
                call_id="call",
                tool_name=object(),
                source=ToolCallSource.direct(),
                payload=ToolPayload.function("{}"),
            )
        with self.assertRaises(TypeError):
            ToolInvocation(
                session=None,
                turn=None,
                cancellation_token=None,
                tracker=None,
                call_id="call",
                tool_name="",
                source=ToolCallSource.direct(),
                payload=ToolPayload.function("{}"),
            )
        with self.assertRaises(TypeError):
            ToolInvocation(
                session=None,
                turn=None,
                cancellation_token=None,
                tracker=None,
                call_id="call",
                tool_name="shell",
                source="direct",  # type: ignore[arg-type]
                payload=ToolPayload.function("{}"),
            )
        with self.assertRaises(TypeError):
            ToolInvocation(
                session=None,
                turn=None,
                cancellation_token=None,
                tracker=None,
                call_id="call",
                tool_name="shell",
                source=ToolCallSource.direct(),
                payload="{}",  # type: ignore[arg-type]
            )

    def test_boxed_tool_output_preserves_trait_like_output_boundary(self) -> None:
        output = FunctionToolOutput.from_text("ok", True)

        self.assertIs(boxed_tool_output(output), output)
        self.assertIsInstance(output, ToolOutput)
        with self.assertRaises(TypeError):
            boxed_tool_output(object())  # type: ignore[arg-type]

    def test_custom_tool_calls_should_roundtrip_as_custom_outputs(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::function_tool_response
        # Rust test: custom_tool_calls_should_roundtrip_as_custom_outputs
        response = FunctionToolOutput.from_text("patched", True).to_response_item(
            "call-42",
            ToolPayload.custom("patch"),
        )

        self.assertEqual(response.type, "custom_tool_call_output")
        self.assertEqual(response.call_id, "call-42")
        self.assertEqual(response.output.to_text(), "patched")
        self.assertTrue(response.output.success)

    def test_tool_payload_log_payload_matches_upstream_variants(self) -> None:
        self.assertEqual(ToolPayload.function('{"ok":true}').log_payload(), '{"ok":true}')
        self.assertEqual(ToolPayload.custom("*** Begin Patch").log_payload(), "*** Begin Patch")
        self.assertEqual(
            ToolPayload.tool_search(SearchToolCallParams("calendar", limit=2)).log_payload(),
            "calendar",
        )

    def test_tool_payload_rejects_non_rust_variant_shapes(self) -> None:
        with self.assertRaises(TypeError):
            ToolPayload(1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ToolPayload("unknown")
        with self.assertRaises(TypeError):
            ToolPayload.function(1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            ToolPayload.custom(1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            ToolPayload.tool_search("calendar")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ToolPayload("function", arguments="{}", input="extra")
        with self.assertRaises(ValueError):
            ToolPayload("custom", input="raw", arguments="{}")
        with self.assertRaises(ValueError):
            ToolPayload(
                "tool_search",
                input="raw",
                search_arguments=SearchToolCallParams("calendar"),
            )

    def test_function_payloads_remain_function_outputs(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::function_tool_response
        # Rust test: function_payloads_remain_function_outputs
        response = FunctionToolOutput.from_text("ok", True).to_response_item(
            "fn-1",
            ToolPayload.function("{}"),
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "fn-1")
        self.assertEqual(response.output.to_text(), "ok")
        self.assertTrue(response.output.success)

    def test_json_tool_output_preserves_json_value_for_hooks_and_code_mode(self) -> None:
        output = JsonToolOutput.with_success({"ok": True, "items": [1, 2]}, None)
        response = output.to_response_item("json-call", ToolPayload.function("{}"))

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "json-call")
        self.assertEqual(response.output.to_text(), '{"ok":true,"items":[1,2]}')
        self.assertIsNone(response.output.success)
        self.assertTrue(output.success_for_logging())
        self.assertEqual(
            output.post_tool_use_response("json-call", ToolPayload.function("{}")),
            {"ok": True, "items": [1, 2]},
        )
        self.assertEqual(
            output.code_mode_result(ToolPayload.function("{}")),
            {"ok": True, "items": [1, 2]},
        )

    def test_json_tool_output_can_return_custom_tool_output_and_log_failure(self) -> None:
        output = JsonToolOutput.with_success(["failed"], False)
        response = output.to_response_item("custom-json", ToolPayload.custom("raw"))

        self.assertEqual(response.type, "custom_tool_call_output")
        self.assertEqual(response.output.to_text(), '["failed"]')
        self.assertFalse(response.output.success)
        self.assertFalse(output.success_for_logging())
        self.assertEqual(output.log_preview(), '["failed"]')

    def test_function_tool_output_log_preview_uses_content_items_when_plain_text_missing(self) -> None:
        # Rust source: codex-core/src/tools/context_tests.rs
        # Rust test: log_preview_uses_content_items_when_plain_text_is_missing
        output = FunctionToolOutput.from_content(
            (
                FunctionCallOutputContentItem.input_text("preview"),
            ),
            True,
        )

        self.assertEqual(output.log_preview(), "preview")
        self.assertEqual(output.into_text(), "preview")

    def test_custom_tool_calls_can_derive_text_from_content_items(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::function_tool_response
        # Rust test: custom_tool_calls_can_derive_text_from_content_items
        content = (
            FunctionCallOutputContentItem.input_text("line 1"),
            FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL),
            FunctionCallOutputContentItem.input_text("line 2"),
        )
        response = FunctionToolOutput.from_content(content, True).to_response_item(
            "call-99",
            ToolPayload.custom("patch"),
        )

        self.assertEqual(response.type, "custom_tool_call_output")
        self.assertEqual(response.call_id, "call-99")
        self.assertEqual(response.output.content_items, content)
        self.assertEqual(response.output.to_text(), "line 1\nline 2")
        self.assertTrue(response.output.success)

    def test_tool_search_payloads_roundtrip_as_tool_search_outputs(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::ToolSearchOutput::to_response_item
        # Rust test: tool_search_payloads_roundtrip_as_tool_search_outputs
        payload = ToolPayload.tool_search(SearchToolCallParams("calendar"))
        response = ToolSearchOutput(
            (
                {
                    "type": "function",
                    "name": "create_event",
                    "description": "",
                    "strict": False,
                    "defer_loading": True,
                    "parameters": {"type": "object", "properties": {}},
                },
            )
        ).to_response_item("search-1", payload)

        self.assertEqual(response.type, "tool_search_output")
        self.assertEqual(response.call_id, "search-1")
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.execution, "client")
        self.assertEqual(response.tools[0]["name"], "create_event")

    def test_post_tool_use_feedback_output_replaces_model_visible_only(self) -> None:
        original = JsonToolOutput.with_success({"raw": True}, False)
        feedback = PostToolUseFeedbackOutput(
            original=original,
            model_visible=FunctionToolOutput.from_text("hook feedback", None),
        )
        response = feedback.to_response_item("call-feedback", ToolPayload.function("{}"))

        self.assertEqual(response.output.to_text(), "hook feedback")
        self.assertIsNone(response.output.success)
        self.assertEqual(feedback.log_preview(), '{"raw":true}')
        self.assertFalse(feedback.success_for_logging())
        self.assertEqual(feedback.code_mode_result(ToolPayload.function("{}")), {"raw": True})

    def test_post_tool_use_feedback_code_mode_falls_back_to_original_response_body(self) -> None:
        feedback = PostToolUseFeedbackOutput(
            original=FunctionToolOutput.from_text("original", True),
            model_visible=FunctionToolOutput.from_text("hook feedback", None),
        )

        self.assertEqual(feedback.to_response_item("call-feedback", ToolPayload.function("{}")).output.to_text(), "hook feedback")
        self.assertEqual(feedback.code_mode_result(ToolPayload.function("{}")), "original")

    def test_mcp_tool_output_response_item_includes_wall_time(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::McpToolOutput::response_payload
        # Rust test: mcp_tool_output_response_item_includes_wall_time
        output = McpToolOutput(
            result=CallToolResult(
                content=({"type": "text", "text": "done"},),
                structured_content=None,
                is_error=False,
            ),
            tool_input={},
            wall_time_seconds=1.25,
            original_image_detail_supported=False,
            truncation_policy=TruncationPolicyConfig.bytes(1024),
        )

        response = output.to_response_item("mcp-call-1", ToolPayload.function("{}"))

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "mcp-call-1")
        self.assertTrue(response.output.success)
        text = response.output.to_text()
        self.assertTrue(text.startswith("Wall time: 1.2500 seconds\nOutput:\n"))
        self.assertEqual(
            text.removeprefix("Wall time: 1.2500 seconds\nOutput:\n"),
            '[{"type":"text","text":"done"}]',
        )

    def test_mcp_code_mode_result_serializes_full_call_tool_result(self) -> None:
        # Rust source: codex-core/src/tools/context_tests.rs
        # Rust test: mcp_code_mode_result_serializes_full_call_tool_result
        output = McpToolOutput(
            result=CallToolResult(
                content=({"type": "text", "text": "ignored"},),
                structured_content={"threadId": "thread_123", "content": "done"},
                is_error=False,
                meta={"source": "mcp"},
            ),
            tool_input={},
            wall_time_seconds=1.25,
            original_image_detail_supported=False,
            truncation_policy=TruncationPolicyConfig.bytes(64),
        )

        self.assertEqual(
            output.code_mode_result(ToolPayload.function("{}")),
            {
                "content": [{"type": "text", "text": "ignored"}],
                "structuredContent": {
                    "threadId": "thread_123",
                    "content": "done",
                },
                "isError": False,
                "_meta": {"source": "mcp"},
            },
        )

    def test_mcp_tool_output_prefers_structured_content_and_truncates(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::McpToolOutput::response_payload
        # Rust test: mcp_tool_output_response_item_truncates_large_structured_content
        output = McpToolOutput(
            result=CallToolResult(
                content=({"type": "text", "text": "ignored when structured content is present"},),
                structured_content={"items": "large structured value " * 100},
                is_error=False,
            ),
            tool_input={},
            wall_time_seconds=1.25,
            original_image_detail_supported=False,
            truncation_policy=TruncationPolicyConfig.bytes(128),
        )

        text = output.to_response_item("mcp-call-large", ToolPayload.function("{}")).output.to_text()

        self.assertTrue(text.startswith("Wall time: 1.2500 seconds\nOutput:\n"))
        self.assertIn("chars truncated", text)
        self.assertNotIn("ignored when structured content is present", text)

    def test_mcp_tool_output_preserves_image_content_items(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::McpToolOutput::response_payload
        # Rust test: mcp_tool_output_response_item_preserves_content_items
        output = McpToolOutput(
            result=CallToolResult(
                content=(
                    {"type": "text", "text": "screenshot"},
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": "AAA",
                        "_meta": {"codex/imageDetail": "original"},
                    },
                ),
                structured_content=None,
                is_error=False,
            ),
            tool_input={},
            wall_time_seconds=0.5,
            original_image_detail_supported=False,
            truncation_policy=TruncationPolicyConfig.bytes(1024),
        )

        response = output.to_response_item("mcp-call-2", ToolPayload.function("{}"))

        self.assertEqual(
            response.output.content_items,
            (
                FunctionCallOutputContentItem.input_text("Wall time: 0.5000 seconds\nOutput:"),
                FunctionCallOutputContentItem.input_text("screenshot"),
                FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL),
            ),
        )

    def test_mcp_tool_output_image_only_content_items_get_wall_time_header(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::McpToolOutput::response_payload
        # Rust test: mcp_tool_output_response_item_preserves_content_items
        output = McpToolOutput(
            result=CallToolResult(
                content=(
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": "AAA",
                    },
                ),
                structured_content=None,
                is_error=False,
            ),
            tool_input={},
            wall_time_seconds=0.5,
            original_image_detail_supported=False,
            truncation_policy=TruncationPolicyConfig.bytes(1024),
        )

        response = output.to_response_item("mcp-call-image-only", ToolPayload.function("{}"))

        self.assertEqual(
            response.output.content_items,
            (
                FunctionCallOutputContentItem.input_text("Wall time: 0.5000 seconds\nOutput:"),
                FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL),
            ),
        )
        self.assertEqual(response.output.to_text(), "Wall time: 0.5000 seconds\nOutput:")

    def test_mcp_tool_output_truncates_content_items_after_header(self) -> None:
        image = FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL)
        output = McpToolOutput(
            result=CallToolResult(
                content=(
                    {"type": "text", "text": "x" * 240},
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": "AAA",
                    },
                ),
                structured_content=None,
                is_error=False,
            ),
            tool_input={},
            wall_time_seconds=0.5,
            original_image_detail_supported=False,
            truncation_policy=TruncationPolicyConfig.bytes(80),
        )

        response = output.to_response_item("mcp-call-truncated-items", ToolPayload.function("{}"))
        content_items = response.output.content_items or ()
        text_items = tuple(item for item in content_items if item.type == "input_text")

        self.assertEqual(text_items[0].text, "Wall time: 0.5000 seconds\nOutput:")
        self.assertTrue(any("chars truncated" in (item.text or "") for item in text_items[1:]))
        self.assertNotIn("x" * 100, response.output.to_text() or "")
        self.assertIn(image, content_items)

    def test_mcp_tool_output_keeps_original_image_detail_when_supported(self) -> None:
        output = McpToolOutput(
            result=CallToolResult(
                content=(
                    {
                        "type": "image",
                        "mime_type": "image/png",
                        "data": "BBB",
                        "_meta": {"codex/imageDetail": "original"},
                    },
                ),
                is_error=False,
            ),
            tool_input={"path": "image.png"},
            wall_time_seconds=0.5,
            original_image_detail_supported=True,
            truncation_policy=TruncationPolicyConfig.bytes(1024),
        )

        response = output.to_response_item("mcp-call-original", ToolPayload.function("{}"))

        self.assertEqual(response.output.content_items[1].detail, ImageDetail.ORIGINAL)
        self.assertEqual(output.code_mode_result(ToolPayload.function("{}"))["content"][0]["data"], "BBB")
        self.assertEqual(output.post_tool_use_input(ToolPayload.function("{}")), {"path": "image.png"})
        self.assertEqual(output.post_tool_use_response("mcp-call-original", ToolPayload.function("{}"))["isError"], False)

    def test_mcp_code_mode_result_stays_raw_when_model_response_is_truncated(self) -> None:
        # Rust source: codex-core/src/tools/context_tests.rs
        # Rust test: mcp_tool_output_code_mode_result_stays_raw_call_tool_result
        large_content = "large structured value " * 1_000
        output = McpToolOutput(
            result=CallToolResult(
                content=({"type": "text", "text": "ignored"},),
                structured_content={"content": large_content},
                is_error=False,
            ),
            tool_input={},
            wall_time_seconds=1.25,
            original_image_detail_supported=False,
            truncation_policy=TruncationPolicyConfig.bytes(64),
        )

        model_text = output.to_response_item("mcp-large", ToolPayload.function("{}")).output.to_text()
        code_mode_result = output.code_mode_result(ToolPayload.function("{}"))

        self.assertIn("chars truncated", model_text)
        self.assertEqual(code_mode_result["structuredContent"]["content"], large_content)
        self.assertNotIn("chars truncated", code_mode_result["structuredContent"]["content"])

    def test_mcp_image_detail_meta_accepts_all_upstream_detail_values(self) -> None:
        for raw_detail, expected_detail in (
            ("auto", ImageDetail.AUTO),
            ("low", ImageDetail.LOW),
            ("high", ImageDetail.HIGH),
        ):
            output = McpToolOutput(
                result=CallToolResult(
                    content=(
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": "AAA",
                            "_meta": {"codex/imageDetail": raw_detail},
                        },
                    ),
                    is_error=False,
                ),
                tool_input={},
                wall_time_seconds=0.5,
                original_image_detail_supported=True,
                truncation_policy=TruncationPolicyConfig.bytes(1024),
            )

            response = output.to_response_item("mcp-call-detail", ToolPayload.function("{}"))

            self.assertEqual(response.output.content_items[1].detail, expected_detail)

    def test_aborted_tool_search_returns_empty_completed_search_output(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::AbortedToolOutput::to_response_item
        # Rust contract: aborted tool-search calls still return a completed client search output with no tools.
        response = AbortedToolOutput("cancelled").to_response_item(
            "search-abort",
            ToolPayload.tool_search(SearchToolCallParams("calendar")),
        )

        self.assertEqual(response.type, "tool_search_output")
        self.assertEqual(response.tools, ())

    def test_apply_patch_tool_output_keeps_model_and_hook_payloads(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::ApplyPatchToolOutput
        # Rust contract: apply_patch model output succeeds, post-tool-use response is text, code-mode value is empty object.
        output = ApplyPatchToolOutput.from_text("Done!")
        response = output.to_response_item("patch-call", ToolPayload.function("{}"))

        self.assertEqual(response.output.to_text(), "Done!")
        self.assertTrue(response.output.success)
        self.assertEqual(output.post_tool_use_response("patch-call", ToolPayload.function("{}")), "Done!")
        self.assertEqual(output.code_mode_result(ToolPayload.function("{}")), {})

    def test_telemetry_preview_returns_original_within_limits(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::telemetry_preview
        # Rust test: telemetry_preview_returns_original_within_limits
        self.assertEqual(telemetry_preview("short output"), "short output")

    def test_telemetry_preview_truncates_by_bytes(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::telemetry_preview
        # Rust test: telemetry_preview_truncates_by_bytes
        preview = telemetry_preview("x" * (TELEMETRY_PREVIEW_MAX_BYTES + 8))

        self.assertIn(TELEMETRY_PREVIEW_TRUNCATION_NOTICE, preview)
        self.assertLessEqual(
            len(preview),
            TELEMETRY_PREVIEW_MAX_BYTES + len(TELEMETRY_PREVIEW_TRUNCATION_NOTICE) + 1,
        )

    def test_telemetry_preview_truncates_by_lines(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::telemetry_preview
        # Rust test: telemetry_preview_truncates_by_lines
        preview = telemetry_preview("\n".join(f"line {idx}" for idx in range(TELEMETRY_PREVIEW_MAX_LINES + 5)))

        lines = preview.splitlines()
        self.assertLessEqual(len(lines), TELEMETRY_PREVIEW_MAX_LINES + 1)
        self.assertEqual(lines[-1], TELEMETRY_PREVIEW_TRUNCATION_NOTICE)

    def test_telemetry_preview_preserves_line_boundary_newline_before_notice(self) -> None:
        content = "".join(f"line {idx}\n" for idx in range(TELEMETRY_PREVIEW_MAX_LINES + 1))

        preview = telemetry_preview(content)

        self.assertTrue(preview.endswith(f"\n{TELEMETRY_PREVIEW_TRUNCATION_NOTICE}"))
        self.assertIn(f"line {TELEMETRY_PREVIEW_MAX_LINES - 1}\n", preview)

    def test_formatted_truncate_text_matches_output_truncation_policy(self) -> None:
        self.assertEqual(
            formatted_truncate_text("example output", TruncationPolicyConfig.bytes(1)),
            "Total output lines: 1\n\n\u202613 chars truncated\u2026t",
        )
        self.assertEqual(
            formatted_truncate_text("example output", TruncationPolicyConfig.tokens(1)),
            "Total output lines: 1\n\nex\u20263 tokens truncated\u2026ut",
        )
        self.assertEqual(
            truncate_text("\U0001f600" * 5, TruncationPolicyConfig.bytes(8)),
            "\U0001f600\u20263 chars truncated\u2026\U0001f600",
        )

    def test_formatted_truncate_text_content_items_merges_text_and_appends_media(self) -> None:
        image_one = FunctionCallOutputContentItem.input_image(
            "img:one",
            DEFAULT_IMAGE_DETAIL,
        )
        image_two = FunctionCallOutputContentItem.input_image(
            "img:two",
            DEFAULT_IMAGE_DETAIL,
        )
        items = (
            FunctionCallOutputContentItem.input_text("abcd"),
            image_one,
            FunctionCallOutputContentItem.input_text("efgh"),
            FunctionCallOutputContentItem.input_text("ijkl"),
            image_two,
        )

        output, original_token_count = formatted_truncate_text_content_items_with_policy(
            items,
            TruncationPolicyConfig.bytes(8),
        )

        self.assertEqual(
            output,
            (
                FunctionCallOutputContentItem.input_text(
                    "Total output lines: 3\n\nabcd\u20266 chars truncated\u2026ijkl"
                ),
                image_one,
                image_two,
            ),
        )
        self.assertEqual(original_token_count, 4)

    def test_content_item_truncation_preserves_encrypted_content(self) -> None:
        encrypted = FunctionCallOutputContentItem.encrypted("enc_opaque")
        items = (FunctionCallOutputContentItem.input_text("abcdefgh"), encrypted)

        formatted, original_token_count = formatted_truncate_text_content_items_with_policy(
            items,
            TruncationPolicyConfig.bytes(2),
        )
        truncated = truncate_function_output_items_with_policy(
            items,
            TruncationPolicyConfig.bytes(2),
        )

        self.assertEqual(
            formatted,
            (
                FunctionCallOutputContentItem.input_text(
                    "Total output lines: 1\n\na\u20266 chars truncated\u2026h"
                ),
                encrypted,
            ),
        )
        self.assertEqual(original_token_count, 2)
        self.assertEqual(
            truncated,
            (
                FunctionCallOutputContentItem.input_text("a\u20266 chars truncated\u2026h"),
                encrypted,
            ),
        )

    def test_truncate_function_output_items_tracks_omitted_text_items(self) -> None:
        image = FunctionCallOutputContentItem.input_image("img:mid", DEFAULT_IMAGE_DETAIL)
        output = truncate_function_output_items_with_policy(
            (
                FunctionCallOutputContentItem.input_text("abc"),
                image,
                FunctionCallOutputContentItem.input_text("def"),
                FunctionCallOutputContentItem.input_text("ghi"),
            ),
            TruncationPolicyConfig.bytes(4),
        )

        self.assertEqual(
            output,
            (
                FunctionCallOutputContentItem.input_text("abc"),
                image,
                FunctionCallOutputContentItem.input_text("\u20262 chars truncated\u2026f"),
                FunctionCallOutputContentItem.input_text("[omitted 1 text items ...]"),
            ),
        )

    def test_approx_tokens_from_byte_count_i64_clamps_non_positive_values(self) -> None:
        self.assertEqual(approx_tokens_from_byte_count_i64(-1), 0)
        self.assertEqual(approx_tokens_from_byte_count_i64(0), 0)
        self.assertEqual(approx_tokens_from_byte_count_i64(5), 2)

    def test_exec_command_tool_output_formats_truncated_response(self) -> None:
        # Rust source: codex-rs/core/src/tools/context.rs::ExecCommandToolOutput::response_text
        # Rust test: exec_command_tool_output_formats_truncated_response
        output = ExecCommandToolOutput(
            event_call_id="call-42",
            chunk_id="abc123",
            wall_time_seconds=1.25,
            raw_output=b"token one token two token three token four token five",
            truncation_policy=TruncationPolicyConfig.tokens(10_000),
            max_output_tokens=4,
            exit_code=0,
            original_token_count=10,
        )
        response = output.to_response_item("call-42", ToolPayload.function("{}"))
        text = response.output.to_text()

        self.assertIn("Chunk ID: abc123", text)
        self.assertIn("Wall time: 1.2500 seconds", text)
        self.assertIn("Process exited with code 0", text)
        self.assertIn("Original token count: 10", text)
        self.assertIn("tokens truncated", text)


if __name__ == "__main__":
    unittest.main()
