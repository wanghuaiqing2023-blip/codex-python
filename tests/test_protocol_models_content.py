from pathlib import Path
import tempfile
import unittest

from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    BaseInstructions,
    ContentItem,
    FunctionCallOutputBody,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ImageDetail,
    LocalShellAction,
    LocalShellExecAction,
    MessagePhase,
    ReasoningItemContent,
    ReasoningItemReasoningSummary,
    ResponseInputItem,
    ResponseItem,
    SearchToolCallParams,
    ShellCommandToolCallParams,
    SandboxPermissions,
    UserInput,
    WebSearchAction,
    convert_mcp_content_to_items,
    format_allow_prefixes,
    function_call_output_content_items_to_text,
    image_close_tag_text,
    image_open_tag_text,
    is_image_close_tag_text,
    is_image_open_tag_text,
    is_local_image_close_tag_text,
    is_local_image_open_tag_text,
    local_image_label_text,
    local_image_open_tag_text,
    should_serialize_reasoning_content,
)
from pycodex.protocol.models import MAX_ALLOW_PREFIX_TEXT_BYTES, MAX_RENDERED_PREFIXES, TRUNCATED_MARKER


class ProtocolModelsContentTests(unittest.TestCase):
    def test_content_item_serialization_and_parsing(self):
        text = ContentItem.input_text("hello")
        image = ContentItem.input_image("https://example.com/a.png", detail=ImageDetail.ORIGINAL)
        output = ContentItem.output_text("done")

        self.assertEqual(ContentItem.from_mapping(text.to_mapping()), text)
        self.assertEqual(ContentItem.from_mapping(image.to_mapping()), image)
        self.assertEqual(output.to_mapping(), {"type": "output_text", "text": "done"})

    def test_image_detail_roundtrips_all_wire_values_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # image_detail_roundtrips_all_wire_values.
        self.assertEqual(ImageDetail("auto"), ImageDetail.AUTO)
        self.assertEqual(ImageDetail("low"), ImageDetail.LOW)
        self.assertEqual(ImageDetail.AUTO.to_json(), "auto")
        self.assertEqual(ImageDetail.LOW.to_json(), "low")

        content_item = ContentItem.from_mapping(
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,abc",
                "detail": "auto",
            }
        )

        self.assertEqual(
            content_item,
            ContentItem.input_image("data:image/png;base64,abc", detail=ImageDetail.AUTO),
        )
        self.assertEqual(content_item.to_mapping()["detail"], "auto")

    def test_convert_mcp_content_to_items_preserves_data_urls_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # convert_mcp_content_to_items_preserves_data_urls.
        items = convert_mcp_content_to_items(
            (
                {
                    "type": "image",
                    "data": "data:image/png;base64,Zm9v",
                    "mimeType": "image/png",
                },
            )
        )

        self.assertEqual(
            items,
            (
                FunctionCallOutputContentItem.input_image(
                    "data:image/png;base64,Zm9v",
                    DEFAULT_IMAGE_DETAIL,
                ),
            ),
        )

    def test_convert_mcp_content_to_items_builds_data_urls_when_missing_prefix_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # convert_mcp_content_to_items_builds_data_urls_when_missing_prefix.
        items = convert_mcp_content_to_items(
            (
                {
                    "type": "image",
                    "data": "Zm9v",
                    "mimeType": "image/png",
                },
            )
        )

        self.assertEqual(
            items,
            (
                FunctionCallOutputContentItem.input_image(
                    "data:image/png;base64,Zm9v",
                    DEFAULT_IMAGE_DETAIL,
                ),
            ),
        )

    def test_convert_mcp_content_to_items_preserves_image_detail_metadata_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # preserves_original_detail_metadata_on_mcp_images and
        # preserves_standard_detail_metadata_on_mcp_images.
        cases = (
            ("original", ImageDetail.ORIGINAL),
            ("high", ImageDetail.HIGH),
        )

        for wire_detail, expected_detail in cases:
            with self.subTest(wire_detail=wire_detail):
                items = convert_mcp_content_to_items(
                    (
                        {
                            "type": "image",
                            "data": "BASE64",
                            "mimeType": "image/png",
                            "_meta": {"codex/imageDetail": wire_detail},
                        },
                    )
                )

                self.assertEqual(
                    items,
                    (
                        FunctionCallOutputContentItem.input_image(
                            "data:image/png;base64,BASE64",
                            expected_detail,
                        ),
                    ),
                )

    def test_convert_mcp_content_to_items_returns_none_without_images_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # convert_mcp_content_to_items_returns_none_without_images.
        self.assertIsNone(
            convert_mcp_content_to_items(
                (
                    {
                        "type": "text",
                        "text": "hello",
                    },
                )
            )
        )

    def test_content_items_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            ContentItem.input_text(123)

        with self.assertRaisesRegex(TypeError, "image_url must be a string"):
            ContentItem.input_image(123)

        with self.assertRaisesRegex(TypeError, "detail must be a string"):
            ContentItem.from_mapping({"type": "input_image", "image_url": "https://example.com/a.png", "detail": 123})

        with self.assertRaisesRegex(ValueError, "input_text content item cannot include image_url"):
            ContentItem("input_text", text="hello", image_url="https://example.com/a.png")

        with self.assertRaisesRegex(ValueError, "unknown content item type"):
            ContentItem("unknown")

    def test_response_input_message_conversion_preserves_phase(self):
        # Rust parity: codex-protocol/src/models.rs
        # response_input_message_conversion_preserves_phase.
        item = ResponseItem.from_response_input_item(
            ResponseInputItem.message(
                "assistant",
                (ContentItem.output_text("still working"),),
                phase=MessagePhase.COMMENTARY,
            )
        )

        self.assertEqual(
            item,
            ResponseItem.message(
                "assistant",
                (ContentItem.output_text("still working"),),
                phase=MessagePhase.COMMENTARY,
            ),
        )
        self.assertEqual(item.to_mapping()["phase"], "commentary")

    def test_response_input_from_user_inputs_keeps_remote_images_direct(self):
        # Rust parity: codex-protocol/src/models.rs
        # serializes_image_user_input_without_tags.
        item = ResponseInputItem.from_user_inputs(
            (
                UserInput.text_input("look"),
                UserInput.image("https://example.com/a.png"),
            )
        )

        self.assertEqual(item.role, "user")
        self.assertEqual(
            item.content,
            (
                ContentItem.input_text("look"),
                ContentItem.input_image("https://example.com/a.png", detail=DEFAULT_IMAGE_DETAIL),
            ),
        )

    def test_response_input_from_user_inputs_preserves_remote_image_detail(self):
        # Rust parity: codex-protocol/src/models.rs
        # image_user_input_preserves_requested_detail.
        item = ResponseInputItem.from_user_inputs(
            (UserInput.image("data:image/png;base64,abc", detail=ImageDetail.ORIGINAL),)
        )

        self.assertEqual(
            item.content,
            (
                ContentItem.input_image(
                    "data:image/png;base64,abc",
                    detail=ImageDetail.ORIGINAL,
                ),
            ),
        )

    def test_response_input_from_user_inputs_matches_rust_image_sequence(self):
        item = ResponseInputItem.from_user_inputs(
            (
                UserInput.image("data:image/png;base64,AAA"),
                UserInput.local_image(Path("missing.png")),
                UserInput.skill("python", Path("SKILL.md")),
                UserInput.mention("github", "app://github"),
            )
        )

        self.assertEqual(item.content[0], ContentItem.input_image("data:image/png;base64,AAA", detail=DEFAULT_IMAGE_DETAIL))
        self.assertEqual(item.content[1].type, "input_text")
        self.assertIn("Codex could not read the local image", item.content[1].text)
        self.assertEqual(len(item.content), 2)

    def test_response_input_from_user_inputs_mixed_remote_and_local_images_share_label_sequence_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # mixed_remote_and_local_images_share_label_sequence.
        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "local.png"
            local_path.write_bytes(b"\x89PNG\r\n\x1a\n")

            item = ResponseInputItem.from_user_inputs(
                (
                    UserInput.image("data:image/png;base64,abc"),
                    UserInput.local_image(local_path),
                )
            )

        self.assertEqual(
            item.content[0],
            ContentItem.input_image("data:image/png;base64,abc", detail=DEFAULT_IMAGE_DETAIL),
        )
        self.assertEqual(item.content[1], ContentItem.input_text(local_image_open_tag_text(2)))
        self.assertEqual(item.content[2].type, "input_image")
        self.assertEqual(item.content[2].detail, DEFAULT_IMAGE_DETAIL)
        self.assertEqual(item.content[3], ContentItem.input_text(image_close_tag_text()))

    def test_response_input_from_user_inputs_local_image_preserves_requested_detail_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # local_image_user_input_preserves_requested_detail.
        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "local.png"
            local_path.write_bytes(b"\x89PNG\r\n\x1a\n")

            item = ResponseInputItem.from_user_inputs(
                (UserInput.local_image(local_path, detail=ImageDetail.ORIGINAL),)
            )

        self.assertEqual(item.content[0], ContentItem.input_text(local_image_open_tag_text(1)))
        self.assertEqual(item.content[1].type, "input_image")
        self.assertEqual(item.content[1].detail, ImageDetail.ORIGINAL)
        self.assertEqual(item.content[2], ContentItem.input_text(image_close_tag_text()))

    def test_response_input_from_user_inputs_reads_local_image_before_mime_check(self):
        # Rust parity: codex-protocol/src/models.rs
        # local_image_read_error_adds_placeholder.
        item = ResponseInputItem.from_user_inputs((UserInput.local_image(Path("missing.txt")),))

        self.assertEqual(item.content[0].type, "input_text")
        self.assertIn("Codex could not read the local image", item.content[0].text)

    def test_response_input_from_user_inputs_rejects_invalid_local_image_bytes(self):
        # Rust parity: codex-protocol/src/models.rs
        # local_image_unsupported_image_format_adds_placeholder.
        path = Path("not-an-image.png")
        path.write_text("not actually a png", encoding="utf-8")
        try:
            item = ResponseInputItem.from_user_inputs((UserInput.local_image(path),))
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(item.content[0].type, "input_text")
        self.assertIn("Image located at `not-an-image.png` is invalid", item.content[0].text)

    def test_response_input_from_user_inputs_rejects_non_image_mime(self):
        # Rust parity: codex-protocol/src/models.rs
        # local_image_non_image_adds_placeholder.
        path = Path("example.json")
        path.write_text('{"hello":"world"}', encoding="utf-8")
        try:
            item = ResponseInputItem.from_user_inputs((UserInput.local_image(path),))
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(item.content[0].type, "input_text")
        self.assertEqual(
            item.content[0].text,
            "Codex cannot attach image at `example.json`: unsupported image `application/json`.",
        )

    def test_response_input_from_user_inputs_rejects_svg_mime(self):
        # Rust parity: codex-protocol/src/models.rs
        # local_image_unsupported_image_format_adds_placeholder.
        path = Path("example.svg")
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>',
            encoding="utf-8",
        )
        try:
            item = ResponseInputItem.from_user_inputs((UserInput.local_image(path),))
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(item.content[0].type, "input_text")
        self.assertEqual(
            item.content[0].text,
            "Codex cannot attach image at `example.svg`: unsupported image `image/svg+xml`.",
        )

    def test_response_input_from_user_inputs_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "items must be a list or tuple"):
            ResponseInputItem.from_user_inputs("hello")

        with self.assertRaisesRegex(TypeError, "items entries must be UserInput-like values"):
            ResponseInputItem.from_user_inputs(({"type": "text", "text": "hello"},))

        with self.assertRaisesRegex(ValueError, "unknown user input type"):
            ResponseInputItem.from_user_inputs((type("BadInput", (), {"type": "unknown"})(),))

    def test_function_call_output_payload_wire_shapes(self):
        text_payload = FunctionCallOutputPayload.text("ok")
        structured_payload = FunctionCallOutputPayload.structured(({"type": "input_text", "text": "ok"},), success=True)

        self.assertEqual(text_payload.to_json(), "ok")
        self.assertEqual(structured_payload.to_json(), [{"type": "input_text", "text": "ok"}])
        self.assertTrue(structured_payload.success)
        self.assertEqual(FunctionCallOutputPayload.from_value("ok"), text_payload)
        self.assertEqual(
            FunctionCallOutputPayload.from_value([{"type": "input_text", "text": "ok"}]).to_json(),
            structured_payload.to_json(),
        )

    def test_function_call_output_payload_rejects_non_rust_wire_shapes(self):
        with self.assertRaisesRegex(TypeError, "function call output payload must be a string or content item list"):
            FunctionCallOutputPayload.from_value({"content": "ok"})

        with self.assertRaisesRegex(TypeError, "text must be a string"):
            FunctionCallOutputBody.text_body(123)

        with self.assertRaisesRegex(TypeError, "content_items must be a list or tuple"):
            FunctionCallOutputBody.content_items_body("not-items")

        with self.assertRaisesRegex(ValueError, "text function output body cannot include content_items"):
            FunctionCallOutputBody(type="text", text="ok", content_items=(FunctionCallOutputContentItem.input_text("extra"),))

        with self.assertRaisesRegex(ValueError, "content_items function output body cannot include text"):
            FunctionCallOutputBody(type="content_items", text="bad", content_items=())

        with self.assertRaisesRegex(TypeError, "success must be a bool or None"):
            FunctionCallOutputPayload.text("ok", success="true")

    def test_function_call_output_content_items_to_text_matches_upstream_lossy_rules(self):
        # Rust parity: codex-protocol/src/models.rs
        # function_call_output_content_items_to_text_joins_text_segments,
        # function_call_output_content_items_to_text_ignores_blank_text_and_images,
        # function_call_output_body_to_text_returns_plain_text_content, and
        # function_call_output_body_to_text_uses_content_item_fallback.
        content_items = (
            FunctionCallOutputContentItem.input_text("line 1"),
            FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL),
            FunctionCallOutputContentItem.input_text("line 2"),
        )
        blank_and_non_text = (
            FunctionCallOutputContentItem.input_text("   "),
            FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL),
            FunctionCallOutputContentItem.encrypted("enc_opaque"),
        )
        body_fallback_items = (
            FunctionCallOutputContentItem.input_text("line 1"),
            FunctionCallOutputContentItem.input_image("data:image/png;base64,AAA", DEFAULT_IMAGE_DETAIL),
        )

        self.assertEqual(function_call_output_content_items_to_text(content_items), "line 1\nline 2")
        self.assertIsNone(function_call_output_content_items_to_text(blank_and_non_text))
        self.assertEqual(FunctionCallOutputBody.text_body("ok").to_text(), "ok")
        self.assertEqual(FunctionCallOutputBody.content_items_body(body_fallback_items).to_text(), "line 1")

    def test_function_call_output_array_payloads_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # deserializes_array_payload_into_items and
        # deserializes_encrypted_array_payload_into_items.
        content_items = [
            {"type": "input_text", "text": "note"},
            {"type": "input_image", "image_url": "data:image/png;base64,XYZ"},
        ]
        encrypted_items = [{"type": "encrypted_content", "encrypted_content": "enc_opaque"}]

        payload = FunctionCallOutputPayload.from_value(content_items)
        encrypted_payload = FunctionCallOutputPayload.from_value(encrypted_items)

        self.assertIsNone(payload.success)
        self.assertEqual(
            payload.body,
            FunctionCallOutputBody.content_items_body(
                (
                    FunctionCallOutputContentItem.input_text("note"),
                    FunctionCallOutputContentItem.input_image("data:image/png;base64,XYZ"),
                )
            ),
        )
        self.assertEqual(payload.to_json(), content_items)
        self.assertEqual(
            encrypted_payload.body,
            FunctionCallOutputBody.content_items_body(
                (FunctionCallOutputContentItem.encrypted("enc_opaque"),)
            ),
        )
        self.assertEqual(encrypted_payload.to_json(), encrypted_items)

    def test_function_call_output_content_items_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            FunctionCallOutputContentItem.input_text(123)

        with self.assertRaisesRegex(TypeError, "image_url must be a string"):
            FunctionCallOutputContentItem.input_image(123)

        with self.assertRaisesRegex(TypeError, "encrypted_content must be a string"):
            FunctionCallOutputContentItem.encrypted(123)

        with self.assertRaisesRegex(TypeError, "detail must be a string"):
            FunctionCallOutputContentItem.from_mapping({"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": 123})

        with self.assertRaisesRegex(ValueError, "input_image function output item cannot include text"):
            FunctionCallOutputContentItem("input_image", text="bad", image_url="data:image/png;base64,AAA")

    def test_response_item_from_input_outputs(self):
        function_output = ResponseItem.from_response_input_item(ResponseInputItem.function_call_output("call-1", "ok"))
        custom_output = ResponseItem.from_response_input_item(ResponseInputItem.custom_tool_call_output("call-2", "ok", name="tool"))
        tool_search = ResponseItem.from_response_input_item(
            ResponseInputItem.tool_search_output("call-3", "completed", "done", ({"name": "lookup"},))
        )

        self.assertEqual(function_output.type, "function_call_output")
        self.assertEqual(function_output.to_mapping()["output"], "ok")
        self.assertEqual(custom_output.name, "tool")
        self.assertEqual(tool_search.to_mapping()["tools"], [{"name": "lookup"}])

    def test_response_item_function_call_output_keeps_success_internal_for_followup_requests(self):
        # Rust parity: codex-protocol/src/models.rs FunctionCallOutputPayload
        # serializes the payload body as function_call_output.output while
        # `success` remains internal metadata for downstream handling.
        item = ResponseItem(
            type="function_call_output",
            call_id="call-1",
            output=FunctionCallOutputPayload.text("failed", success=False),
        )

        self.assertEqual(item.output.success, False)
        self.assertEqual(
            item.to_mapping(),
            {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": "failed",
            },
        )

    def test_response_input_function_call_output_success_serializes_plain_string_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # serializes_success_as_plain_string.
        item = ResponseInputItem.function_call_output(
            "call1",
            FunctionCallOutputPayload.from_text("ok"),
        )

        self.assertEqual(
            item.to_mapping(),
            {
                "type": "function_call_output",
                "call_id": "call1",
                "output": "ok",
            },
        )

    def test_response_input_function_call_output_failure_serializes_string_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # serializes_failure_as_string.
        item = ResponseInputItem.function_call_output(
            "call1",
            FunctionCallOutputPayload.text("bad", success=False),
        )

        self.assertEqual(item.output.success, False)
        self.assertEqual(
            item.to_mapping(),
            {
                "type": "function_call_output",
                "call_id": "call1",
                "output": "bad",
            },
        )

    def test_response_input_function_call_output_image_outputs_serialize_array_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # serializes_image_outputs_as_array.
        payload = FunctionCallOutputPayload.from_content_items(
            (
                FunctionCallOutputContentItem.input_text("caption"),
                FunctionCallOutputContentItem.input_image(
                    "data:image/png;base64,BASE64",
                    DEFAULT_IMAGE_DETAIL,
                ),
            ),
            success=True,
        )
        item = ResponseInputItem.function_call_output("call1", payload)

        self.assertEqual(payload.success, True)
        self.assertEqual(
            item.to_mapping(),
            {
                "type": "function_call_output",
                "call_id": "call1",
                "output": [
                    {"type": "input_text", "text": "caption"},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,BASE64",
                        "detail": DEFAULT_IMAGE_DETAIL.to_json(),
                    },
                ],
            },
        )

    def test_response_input_custom_tool_call_output_image_outputs_serialize_array_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # serializes_custom_tool_image_outputs_as_array.
        payload = FunctionCallOutputPayload.from_content_items(
            (
                FunctionCallOutputContentItem.input_image(
                    "data:image/png;base64,BASE64",
                    DEFAULT_IMAGE_DETAIL,
                ),
            )
        )
        item = ResponseInputItem.custom_tool_call_output("call1", payload)

        self.assertEqual(
            item.to_mapping(),
            {
                "type": "custom_tool_call_output",
                "call_id": "call1",
                "output": [
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,BASE64",
                        "detail": DEFAULT_IMAGE_DETAIL.to_json(),
                    },
                ],
            },
        )

    def test_response_input_function_call_output_encrypted_content_serializes_array_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # serializes_encrypted_function_output_content_as_array.
        item = ResponseInputItem.function_call_output(
            "call1",
            FunctionCallOutputPayload.from_content_items(
                (FunctionCallOutputContentItem.encrypted("enc_opaque"),)
            ),
        )

        self.assertEqual(
            item.to_mapping(),
            {
                "type": "function_call_output",
                "call_id": "call1",
                "output": [
                    {
                        "type": "encrypted_content",
                        "encrypted_content": "enc_opaque",
                    },
                ],
            },
        )

    def test_function_call_deserializes_optional_namespace_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # function_call_deserializes_optional_namespace.
        payload = {
            "type": "function_call",
            "name": "mcp__codex_apps__gmail_get_recent_emails",
            "namespace": "mcp__codex_apps__gmail",
            "arguments": "{\"top_k\":5}",
            "call_id": "call-1",
        }

        item = ResponseItem.from_mapping(payload)

        self.assertEqual(
            item,
            ResponseItem.function_call(
                "mcp__codex_apps__gmail_get_recent_emails",
                "{\"top_k\":5}",
                "call-1",
                namespace="mcp__codex_apps__gmail",
            ),
        )
        self.assertEqual(item.to_mapping(), payload)

    def test_format_allow_prefixes_sorts_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # render_command_prefix_list_sorts_by_len_then_total_len_then_alphabetical.
        self.assertEqual(
            format_allow_prefixes(
                [
                    ["b", "zz"],
                    ["aa"],
                    ["b"],
                    ["a", "b", "c"],
                    ["a"],
                    ["b", "a"],
                ]
            ),
            '- ["a"]\n- ["b"]\n- ["aa"]\n- ["b", "a"]\n- ["b", "zz"]\n- ["a", "b", "c"]',
        )

    def test_format_allow_prefixes_limits_output_to_max_prefixes_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # render_command_prefix_list_limits_output_to_max_prefixes.
        output = format_allow_prefixes([[f"{i:03}"] for i in range(MAX_RENDERED_PREFIXES + 5)])

        self.assertTrue(output.endswith(TRUNCATED_MARKER))
        self.assertEqual(len(output.splitlines()), MAX_RENDERED_PREFIXES + 1)

    def test_format_allow_prefixes_limits_output_bytes_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # format_allow_prefixes_limits_output.
        output = format_allow_prefixes([[f"tool-{i:03}", "x" * 500] for i in range(200)])

        self.assertLessEqual(len(output), MAX_ALLOW_PREFIX_TEXT_BYTES + len(TRUNCATED_MARKER))
        self.assertTrue(output.endswith(TRUNCATED_MARKER))

    def test_response_item_tool_search_roundtrips_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # tool_search_call_roundtrips, tool_search_output_roundtrips, and
        # tool_search_server_items_allow_null_call_id.
        call_payload = {
            "type": "tool_search_call",
            "call_id": "search-1",
            "execution": "client",
            "arguments": {"query": "calendar create", "limit": 1},
        }
        output_payload = {
            "type": "tool_search_output",
            "call_id": "search-1",
            "status": "completed",
            "execution": "client",
            "tools": [
                {
                    "type": "function",
                    "name": "mcp__codex_apps__calendar_create_event",
                    "description": "Create a calendar event.",
                    "defer_loading": True,
                    "parameters": {"type": "object"},
                }
            ],
        }
        server_call = {
            "type": "tool_search_call",
            "execution": "server",
            "call_id": None,
            "status": "completed",
            "arguments": {"paths": ["crm"]},
        }
        server_output = {
            "type": "tool_search_output",
            "execution": "server",
            "call_id": None,
            "status": "completed",
            "tools": [],
        }

        self.assertEqual(ResponseItem.from_mapping(call_payload).to_mapping(), call_payload)
        self.assertEqual(ResponseItem.from_mapping(output_payload).to_mapping(), output_payload)
        self.assertEqual(ResponseItem.from_mapping(server_call).to_mapping(), server_call)
        self.assertEqual(ResponseItem.from_mapping(server_output).to_mapping(), server_output)
        self.assertIsNone(ResponseItem.from_mapping(server_call).call_id)
        self.assertIsNone(ResponseItem.from_mapping(server_output).call_id)

    def test_response_item_image_generation_call_matches_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # response_item_parses_image_generation_call and
        # response_item_parses_image_generation_call_without_revised_prompt.
        with_prompt = {
            "id": "ig_123",
            "type": "image_generation_call",
            "status": "completed",
            "revised_prompt": "A small blue square",
            "result": "Zm9v",
        }
        without_prompt = {
            "id": "ig_123",
            "type": "image_generation_call",
            "status": "completed",
            "result": "Zm9v",
        }

        self.assertEqual(
            ResponseItem.from_mapping(with_prompt),
            ResponseItem.image_generation_call("ig_123", "completed", "Zm9v", "A small blue square"),
        )
        self.assertEqual(ResponseItem.from_mapping(with_prompt).to_mapping(), with_prompt)
        self.assertEqual(
            ResponseItem.from_mapping(without_prompt),
            ResponseItem.image_generation_call("ig_123", "completed", "Zm9v"),
        )
        self.assertEqual(ResponseItem.from_mapping(without_prompt).to_mapping(), without_prompt)

    def test_response_input_items_reject_non_rust_shapes(self):
        empty_message = ResponseInputItem.message("user", ())
        self.assertEqual(empty_message.to_mapping(), {"type": "message", "role": "user", "content": []})
        self.assertEqual(
            ResponseInputItem.function_call_output("call-1", [{"type": "input_text", "text": "ok"}]).to_mapping()["output"],
            [{"type": "input_text", "text": "ok"}],
        )
        self.assertEqual(
            ResponseInputItem.tool_search_output("call-1", "completed", "done", ()).to_mapping()["tools"],
            [],
        )

        cases = (
            lambda: ResponseInputItem.message(123, ()),
            lambda: ResponseInputItem.message("user", "hello"),
            lambda: ResponseInputItem.message("user", ({"type": "input_text", "text": "hello"},)),
            lambda: ResponseInputItem.message("user", (), phase=123),
            lambda: ResponseInputItem.function_call_output(123, "ok"),
            lambda: ResponseInputItem.function_call_output("call-1", {"content": "ok"}),
            lambda: ResponseInputItem.mcp_tool_call_output("call-1", None),
            lambda: ResponseInputItem.custom_tool_call_output("call-1", "ok", name=123),
            lambda: ResponseInputItem.tool_search_output("call-1", 123, "done", ()),
            lambda: ResponseInputItem.tool_search_output("call-1", "completed", 123, ()),
            lambda: ResponseInputItem.tool_search_output("call-1", "completed", "done", "not-tools"),
        )

        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises((TypeError, ValueError)):
                    case()

    def test_search_tool_call_params_reject_non_rust_shapes(self):
        self.assertEqual(SearchToolCallParams.from_mapping({"query": "docs", "limit": 3}).to_mapping(), {"query": "docs", "limit": 3})

        with self.assertRaisesRegex(TypeError, "query must be a string"):
            SearchToolCallParams(123)

        with self.assertRaisesRegex(TypeError, "limit must be an integer"):
            SearchToolCallParams.from_mapping({"query": "docs", "limit": "3"})

        with self.assertRaisesRegex(TypeError, "limit must be an integer"):
            SearchToolCallParams.from_mapping({"query": "docs", "limit": True})

        with self.assertRaisesRegex(ValueError, "limit must be non-negative"):
            SearchToolCallParams.from_mapping({"query": "docs", "limit": -1})

        with self.assertRaisesRegex(TypeError, "limit must be an integer or None"):
            SearchToolCallParams("docs", limit=1.2)

    def test_shell_command_tool_call_params_parse_rust_shape(self):
        params = ShellCommandToolCallParams.from_mapping(
            {
                "command": "echo hi",
                "workdir": "C:/repo",
                "login": False,
                "timeout": 1000,
                "sandbox_permissions": "require_escalated",
                "prefix_rule": ["echo"],
                "additional_permissions": {"network": {"enabled": True}},
                "justification": "needs shell",
            }
        )

        self.assertEqual(params.command, "echo hi")
        self.assertEqual(params.timeout_ms, 1000)
        self.assertIs(params.sandbox_permissions, SandboxPermissions.REQUIRE_ESCALATED)
        self.assertEqual(params.prefix_rule, ("echo",))
        self.assertEqual(params.to_mapping()["timeout_ms"], 1000)

    def test_shell_command_tool_call_params_reject_non_rust_shapes(self):
        with self.assertRaises(KeyError):
            ShellCommandToolCallParams.from_mapping({"workdir": "C:/repo"})

        with self.assertRaisesRegex(TypeError, "command must be a string"):
            ShellCommandToolCallParams(123)

        with self.assertRaisesRegex(TypeError, "login must be a bool"):
            ShellCommandToolCallParams.from_mapping({"command": "echo hi", "login": "false"})

        with self.assertRaisesRegex(TypeError, "timeout_ms must be an integer"):
            ShellCommandToolCallParams.from_mapping({"command": "echo hi", "timeout_ms": "1000"})

        with self.assertRaisesRegex(ValueError, "timeout_ms must fit in u64"):
            ShellCommandToolCallParams.from_mapping({"command": "echo hi", "timeout_ms": -1})

        with self.assertRaisesRegex(TypeError, "prefix_rule entries must be strings"):
            ShellCommandToolCallParams.from_mapping({"command": "echo hi", "prefix_rule": ["echo", 1]})

        with self.assertRaisesRegex(TypeError, "additional_permissions must be AdditionalPermissionProfile or None"):
            ShellCommandToolCallParams("echo hi", additional_permissions={})

    def test_response_item_from_mapping_rejects_missing_rust_required_fields(self):
        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "message", "role": "assistant"})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "reasoning"})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "tool_search_call", "execution": "exec"})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "tool_search_call", "arguments": {}})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "function_call_output", "call_id": "call-1"})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "custom_tool_call_output", "call_id": "call-1"})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "tool_search_output", "call_id": "call-1", "status": "completed"})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "tool_search_output", "call_id": "call-1", "execution": "exec", "tools": []})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "tool_search_output", "call_id": "call-1", "status": "completed", "execution": "exec"})

        item = ResponseItem.from_mapping({"type": "tool_search_output", "status": "completed", "execution": "exec", "tools": []})
        self.assertIsNone(item.call_id)

    def test_response_item_from_mapping_preserves_optional_call_status_fields(self):
        tool_search = ResponseItem.from_mapping(
            {
                "type": "tool_search_call",
                "call_id": "search-1",
                "status": "completed",
                "execution": "server",
                "arguments": {"query": "lookup"},
            }
        )
        custom = ResponseItem.from_mapping(
            {
                "type": "custom_tool_call",
                "call_id": "custom-1",
                "status": "in_progress",
                "name": "freeform",
                "input": "hello",
            }
        )

        self.assertEqual(tool_search.status, "completed")
        self.assertEqual(tool_search.to_mapping()["status"], "completed")
        self.assertEqual(custom.status, "in_progress")
        self.assertEqual(custom.to_mapping()["status"], "in_progress")

        with self.assertRaisesRegex(TypeError, "status must be a string"):
            ResponseItem.from_mapping({"type": "tool_search_call", "status": 123, "execution": "server", "arguments": {}})

        with self.assertRaisesRegex(TypeError, "status must be a string"):
            ResponseItem.from_mapping({"type": "custom_tool_call", "status": 123, "call_id": "custom-1", "name": "freeform", "input": "hello"})

    def test_response_item_from_mapping_rejects_bad_optional_string_fields(self):
        cases = (
            {"type": "message", "role": "assistant", "content": [], "id": 123},
            {"type": "message", "role": "assistant", "content": [], "phase": 123},
            {"type": "reasoning", "summary": [], "encrypted_content": 123},
            {"type": "local_shell_call", "status": "completed", "call_id": 123, "action": {"type": "exec", "command": []}},
            {"type": "function_call", "name": "run", "arguments": "{}", "call_id": "call-1", "namespace": 123},
            {"type": "tool_search_call", "execution": "server", "arguments": {}, "call_id": 123},
            {"type": "custom_tool_call", "call_id": "custom-1", "name": "freeform", "input": "hello", "id": 123},
            {"type": "custom_tool_call_output", "call_id": "call-1", "output": "ok", "name": 123},
            {"type": "tool_search_output", "status": "completed", "execution": "exec", "tools": [], "call_id": 123},
            {"type": "web_search_call", "id": 123},
            {"type": "web_search_call", "action": "search"},
            {"type": "image_generation_call", "id": "ig", "status": "completed", "result": "ok", "revised_prompt": 123},
            {"type": "context_compaction", "encrypted_content": 123},
        )

        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(TypeError):
                    ResponseItem.from_mapping(payload)

    def test_response_item_from_mapping_parses_additional_rust_variants(self):
        reasoning = ResponseItem.from_mapping(
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "summary"}],
                "content": [{"type": "text", "text": "visible"}],
                "encrypted_content": "enc",
            }
        )
        image = ResponseItem.from_mapping(
            {
                "type": "image_generation_call",
                "id": "ig_123",
                "status": "completed",
                "revised_prompt": "A small blue square",
                "result": "Zm9v",
            }
        )
        compaction = ResponseItem.from_mapping({"type": "compaction_summary", "encrypted_content": "abc"})
        trigger = ResponseItem.from_mapping({"type": "compaction_trigger"})
        context = ResponseItem.from_mapping({"type": "context_compaction", "encrypted_content": "ctx"})

        self.assertEqual(reasoning.summary, (ReasoningItemReasoningSummary.summary_text("summary"),))
        self.assertEqual(reasoning.reasoning_content, (ReasoningItemContent.text_content("visible"),))
        self.assertEqual(reasoning.encrypted_content, "enc")
        self.assertEqual(image, ResponseItem.image_generation_call("ig_123", "completed", "Zm9v", "A small blue square"))
        self.assertEqual(compaction, ResponseItem.compaction("abc"))
        self.assertEqual(trigger, ResponseItem.compaction_trigger())
        self.assertEqual(context, ResponseItem.context_compaction("ctx"))

    def test_response_item_from_mapping_parses_local_shell_call(self):
        item = ResponseItem.from_mapping(
            {
                "type": "local_shell_call",
                "call_id": "call-1",
                "status": "in_progress",
                "action": {
                    "type": "exec",
                    "command": ["python", "--version"],
                    "timeout_ms": 1000,
                    "working_directory": "C:/repo",
                    "env": {"PYTHONUTF8": "1"},
                    "user": "runner",
                },
            }
        )

        self.assertEqual(item.type, "local_shell_call")
        self.assertEqual(item.call_id, "call-1")
        self.assertEqual(item.status, "in_progress")
        self.assertEqual(
            item.action,
            LocalShellAction.exec_action(
                LocalShellExecAction(
                    command=("python", "--version"),
                    timeout_ms=1000,
                    working_directory="C:/repo",
                    env={"PYTHONUTF8": "1"},
                    user="runner",
                )
            ),
        )
        self.assertEqual(item.to_mapping()["action"]["command"], ["python", "--version"])

    def test_local_shell_call_rejects_non_rust_shapes(self):
        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "local_shell_call", "status": "completed"})

        with self.assertRaises(KeyError):
            ResponseItem.from_mapping({"type": "local_shell_call", "action": {"type": "exec", "command": []}})

        with self.assertRaisesRegex(TypeError, "command must be a list or tuple of strings"):
            ResponseItem.from_mapping({"type": "local_shell_call", "status": "completed", "action": {"type": "exec", "command": "python"}})

        with self.assertRaisesRegex(ValueError, "timeout_ms must fit in u64"):
            ResponseItem.from_mapping({"type": "local_shell_call", "status": "completed", "action": {"type": "exec", "command": [], "timeout_ms": -1}})

        with self.assertRaisesRegex(TypeError, "env entries must be strings"):
            ResponseItem.from_mapping({"type": "local_shell_call", "status": "completed", "action": {"type": "exec", "command": [], "env": {"A": 1}}})

        with self.assertRaisesRegex(TypeError, "type must be a string"):
            LocalShellAction(123, LocalShellExecAction(command=()))

        with self.assertRaisesRegex(TypeError, "exec must be LocalShellExecAction"):
            LocalShellAction("exec", None)

        with self.assertRaisesRegex(ValueError, "unknown local shell action type"):
            LocalShellAction("other", LocalShellExecAction(command=()))

    def test_web_search_action_shapes(self):
        search = WebSearchAction.search(query="weather")
        multi = WebSearchAction.search(queries=("one", "two"))
        open_page = WebSearchAction.open_page("https://example.com")
        find = WebSearchAction.find_in_page("https://example.com", "needle")

        self.assertEqual(WebSearchAction.from_mapping(search.to_mapping()), search)
        self.assertEqual(multi.to_mapping()["queries"], ["one", "two"])
        self.assertEqual(open_page.to_mapping()["type"], "open_page")
        self.assertEqual(find.to_mapping()["pattern"], "needle")
        self.assertEqual(WebSearchAction.from_mapping({"type": "unknown"}), WebSearchAction.other())

    def test_legacy_ghost_snapshot_deserializes_as_other_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # deserializes_legacy_ghost_snapshot_as_other.
        item = ResponseItem.from_mapping(
            {
                "type": "ghost_snapshot",
                "ghost_commit": {
                    "id": "ghost-1",
                    "parent": None,
                    "preexisting_untracked_files": [],
                    "preexisting_untracked_dirs": [],
                },
            }
        )

        self.assertEqual(item, ResponseItem.other())
        self.assertEqual(item.to_mapping(), {"type": "other"})

    def test_response_item_roundtrips_web_search_call_actions(self):
        # Rust parity: codex-protocol/src/models.rs
        # roundtrips_web_search_call_actions.
        cases = (
            (
                {
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "query": "weather seattle",
                        "queries": ["weather seattle", "seattle weather now"],
                    },
                },
                ResponseItem.web_search_call(
                    status="completed",
                    action=WebSearchAction.search(
                        query="weather seattle",
                        queries=("weather seattle", "seattle weather now"),
                    ),
                ),
                True,
            ),
            (
                {
                    "type": "web_search_call",
                    "status": "open",
                    "action": {
                        "type": "open_page",
                        "url": "https://example.com",
                    },
                },
                ResponseItem.web_search_call(
                    status="open",
                    action=WebSearchAction.open_page("https://example.com"),
                ),
                True,
            ),
            (
                {
                    "type": "web_search_call",
                    "status": "in_progress",
                    "action": {
                        "type": "find_in_page",
                        "url": "https://example.com/docs",
                        "pattern": "installation",
                    },
                },
                ResponseItem.web_search_call(
                    status="in_progress",
                    action=WebSearchAction.find_in_page("https://example.com/docs", "installation"),
                ),
                True,
            ),
            (
                {
                    "type": "web_search_call",
                    "status": "in_progress",
                    "id": "ws_partial",
                },
                ResponseItem.web_search_call(
                    id="ws_partial",
                    status="in_progress",
                ),
                False,
            ),
        )

        for payload, expected, expect_roundtrip in cases:
            parsed = ResponseItem.from_mapping(payload)
            self.assertEqual(parsed, expected)
            serialized = parsed.to_mapping()
            expected_serialized = dict(payload)
            if not expect_roundtrip:
                expected_serialized.pop("id", None)
            self.assertEqual(serialized, expected_serialized)

    def test_response_item_compaction_aliases_and_trigger_match_rust(self):
        # Rust parity: codex-protocol/src/models.rs
        # deserializes_compaction_alias, deserializes_context_compaction,
        # serializes_compaction_trigger_without_payload, and
        # deserializes_compaction_trigger_without_payload.
        compaction = ResponseItem.from_mapping({"type": "compaction_summary", "encrypted_content": "abc"})
        context = ResponseItem.from_mapping({"type": "context_compaction", "encrypted_content": "ctx"})
        context_without_payload = ResponseItem.from_mapping({"type": "context_compaction"})
        trigger = ResponseItem.compaction_trigger()

        self.assertEqual(compaction, ResponseItem.compaction("abc"))
        self.assertEqual(context, ResponseItem.context_compaction("ctx"))
        self.assertEqual(context_without_payload, ResponseItem.context_compaction())
        self.assertEqual(trigger.to_mapping(), {"type": "compaction_trigger"})
        self.assertEqual(ResponseItem.from_mapping({"type": "compaction_trigger"}), trigger)

    def test_web_search_action_rejects_non_rust_field_shapes(self):
        with self.assertRaisesRegex(TypeError, "query must be a string"):
            WebSearchAction.from_mapping({"type": "search", "query": 123})

        with self.assertRaisesRegex(TypeError, "queries must be a list or tuple of strings"):
            WebSearchAction.from_mapping({"type": "search", "queries": "weather"})

        with self.assertRaisesRegex(TypeError, "queries entries must be strings"):
            WebSearchAction.from_mapping({"type": "search", "queries": ["weather", 123]})

        with self.assertRaisesRegex(TypeError, "url must be a string"):
            WebSearchAction.from_mapping({"type": "open_page", "url": 123})

        with self.assertRaisesRegex(TypeError, "pattern must be a string"):
            WebSearchAction.from_mapping({"type": "find_in_page", "pattern": 123})

        with self.assertRaisesRegex(TypeError, "query must be a string or None"):
            WebSearchAction.search(query=123)

        with self.assertRaisesRegex(TypeError, "queries entries must be strings"):
            WebSearchAction.search(queries=("weather", 123))

        with self.assertRaisesRegex(TypeError, "url must be a string or None"):
            WebSearchAction.open_page(123)

        with self.assertRaisesRegex(TypeError, "pattern must be a string or None"):
            WebSearchAction.find_in_page(pattern=123)

        with self.assertRaisesRegex(TypeError, "type must be a string"):
            WebSearchAction(123)

        with self.assertRaisesRegex(ValueError, "search web search action cannot include url or pattern"):
            WebSearchAction("search", query="weather", url="https://example.com")

        with self.assertRaisesRegex(ValueError, "open_page web search action cannot include"):
            WebSearchAction("open_page", url="https://example.com", query="weather")

        with self.assertRaisesRegex(ValueError, "find_in_page web search action cannot include"):
            WebSearchAction("find_in_page", url="https://example.com", queries=("weather",))

        with self.assertRaisesRegex(ValueError, "other web search action cannot include fields"):
            WebSearchAction("other", query="weather")

        with self.assertRaisesRegex(ValueError, "unknown web search action type"):
            WebSearchAction("unknown")

    def test_reasoning_content_serialization_filter_matches_upstream(self):
        reasoning = (ReasoningItemContent.reasoning_text("hidden"),)
        public = (ReasoningItemContent.text_content("visible"),)

        self.assertFalse(should_serialize_reasoning_content(None))
        self.assertFalse(should_serialize_reasoning_content(reasoning))
        self.assertTrue(should_serialize_reasoning_content(public))
        self.assertEqual(ReasoningItemReasoningSummary.summary_text("summary").to_mapping(), {"type": "summary_text", "text": "summary"})

    def test_reasoning_item_serializes_empty_summary_for_responses_followup(self):
        # Rust/Responses contract:
        # codex-rs core keeps ResponseItem::Reasoning { summary: Vec::new(), .. }
        # as `"summary": []` when replaying prior output items into a follow-up
        # request. The live Responses API rejects omitted reasoning summaries.
        self.assertEqual(
            ResponseItem.reasoning("rs-empty").to_mapping(),
            {"type": "reasoning", "id": "rs-empty", "summary": []},
        )

    def test_reasoning_tagged_variants_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "type must be a string"):
            ReasoningItemReasoningSummary(123, "summary")

        with self.assertRaisesRegex(ValueError, "unknown reasoning summary type"):
            ReasoningItemReasoningSummary("text", "summary")

        with self.assertRaisesRegex(TypeError, "text must be a string"):
            ReasoningItemReasoningSummary.summary_text(123)

        with self.assertRaisesRegex(TypeError, "type must be a string"):
            ReasoningItemContent(123, "hidden")

        with self.assertRaisesRegex(ValueError, "unknown reasoning content type"):
            ReasoningItemContent("summary_text", "hidden")

        with self.assertRaisesRegex(TypeError, "text must be a string"):
            ReasoningItemContent.text_content(123)

    def test_image_tag_helpers(self):
        self.assertEqual(image_open_tag_text(), "<image>")
        self.assertEqual(image_close_tag_text(), "</image>")
        self.assertEqual(local_image_label_text(2), "[Image #2]")
        self.assertEqual(local_image_open_tag_text(2), "<image name=[Image #2]>")
        self.assertTrue(is_image_open_tag_text("<image>"))
        self.assertTrue(is_image_close_tag_text("</image>"))
        self.assertTrue(is_local_image_open_tag_text("<image name=[Image #2]>"))
        self.assertTrue(is_local_image_close_tag_text("</image>"))

    def test_base_instructions_default_has_codex_identity(self):
        self.assertIn("Codex", BaseInstructions.default().text)


if __name__ == "__main__":
    unittest.main()
