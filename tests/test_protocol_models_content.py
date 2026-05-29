from pathlib import Path
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

    def test_response_input_from_user_inputs_reads_local_image_before_mime_check(self):
        item = ResponseInputItem.from_user_inputs((UserInput.local_image(Path("missing.txt")),))

        self.assertEqual(item.content[0].type, "input_text")
        self.assertIn("Codex could not read the local image", item.content[0].text)

    def test_response_input_from_user_inputs_rejects_invalid_local_image_bytes(self):
        path = Path("not-an-image.png")
        path.write_text("not actually a png", encoding="utf-8")
        try:
            item = ResponseInputItem.from_user_inputs((UserInput.local_image(path),))
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(item.content[0].type, "input_text")
        self.assertIn("Image located at `not-an-image.png` is invalid", item.content[0].text)

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
