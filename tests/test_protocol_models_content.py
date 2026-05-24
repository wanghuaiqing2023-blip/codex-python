import unittest

from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    BaseInstructions,
    ContentItem,
    FunctionCallOutputBody,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ImageDetail,
    MessagePhase,
    ReasoningItemContent,
    ReasoningItemReasoningSummary,
    ResponseInputItem,
    ResponseItem,
    UserInput,
    WebSearchAction,
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


class ProtocolModelsContentTests(unittest.TestCase):
    def test_content_item_serialization_and_parsing(self):
        text = ContentItem.input_text("hello")
        image = ContentItem.input_image("https://example.com/a.png", detail=ImageDetail.ORIGINAL)
        output = ContentItem.output_text("done")

        self.assertEqual(ContentItem.from_mapping(text.to_mapping()), text)
        self.assertEqual(ContentItem.from_mapping(image.to_mapping()), image)
        self.assertEqual(output.to_mapping(), {"type": "output_text", "text": "done"})

    def test_response_input_message_conversion_preserves_phase(self):
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

    def test_response_input_from_user_inputs_wraps_remote_images_with_tags(self):
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
                ContentItem.input_text("<image>"),
                ContentItem.input_image("https://example.com/a.png", detail=DEFAULT_IMAGE_DETAIL),
                ContentItem.input_text("</image>"),
            ),
        )

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

    def test_function_call_output_content_items_to_text_matches_upstream_lossy_rules(self):
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

        self.assertEqual(function_call_output_content_items_to_text(content_items), "line 1\nline 2")
        self.assertIsNone(function_call_output_content_items_to_text(blank_and_non_text))
        self.assertEqual(FunctionCallOutputBody.text_body("ok").to_text(), "ok")
        self.assertEqual(FunctionCallOutputBody.content_items_body(content_items).to_text(), "line 1\nline 2")

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

    def test_reasoning_content_serialization_filter_matches_upstream(self):
        reasoning = (ReasoningItemContent.reasoning_text("hidden"),)
        public = (ReasoningItemContent.text_content("visible"),)

        self.assertFalse(should_serialize_reasoning_content(None))
        self.assertFalse(should_serialize_reasoning_content(reasoning))
        self.assertTrue(should_serialize_reasoning_content(public))
        self.assertEqual(ReasoningItemReasoningSummary.summary_text("summary").to_mapping(), {"type": "summary_text", "text": "summary"})

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
