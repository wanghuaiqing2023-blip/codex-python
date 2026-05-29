import unittest
from pathlib import Path

from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageEvent,
    AgentMessageItem,
    AgentReasoningEvent,
    AgentReasoningRawContentEvent,
    ByteRange,
    CallToolResult,
    ContextCompactionItem,
    EventMsg,
    FileChange,
    FileChangeItem,
    HookPromptFragment,
    HookPromptItem,
    ImageDetail,
    ImageGenerationItem,
    ImageViewItem,
    ItemCompletedEvent,
    ItemStartedEvent,
    McpToolCallError,
    McpToolCallItem,
    McpToolCallStatus,
    PatchApplyBeginEvent,
    PatchApplyEndEvent,
    PatchApplyStatus,
    PlanItem,
    ReasoningItem,
    TextElement,
    ThreadId,
    TurnItem,
    UserInput,
    UserMessageEvent,
    UserMessageItem,
    WebSearchAction,
    WebSearchBeginEvent,
    WebSearchEndEvent,
    WebSearchItem,
    build_hook_prompt_message,
    parse_hook_prompt_fragment,
    parse_hook_prompt_message,
    serialize_hook_prompt_fragment,
)


class ProtocolItemsTests(unittest.TestCase):
    def test_user_message_legacy_event_flattens_text_and_offsets_elements_by_utf8_bytes(self):
        first_element = TextElement.new(ByteRange(0, 3), None)
        second_element = TextElement.new(ByteRange(0, 1), None)
        item = UserMessageItem(
            "user-1",
            (
                UserInput.text_input("你a", (first_element,)),
                UserInput.image("https://example.com/a.png", detail=ImageDetail.HIGH),
                UserInput.image("https://example.com/b.png"),
                UserInput.local_image(Path("/tmp/local.png"), detail=ImageDetail.ORIGINAL),
                UserInput.text_input("bc", (second_element,)),
            ),
        )

        event = item.as_legacy_event()

        self.assertEqual(item.message(), "你abc")
        self.assertEqual(event.payload.message, "你abc")
        self.assertEqual(event.payload.images, ("https://example.com/a.png", "https://example.com/b.png"))
        self.assertEqual(event.payload.image_details, (ImageDetail.HIGH,))
        self.assertEqual(event.payload.local_images, (Path("/tmp/local.png"),))
        self.assertEqual(event.payload.local_image_details, (ImageDetail.ORIGINAL,))
        self.assertEqual(event.payload.text_elements[0].byte_range, ByteRange(0, 3))
        self.assertEqual(event.payload.text_elements[0].placeholder_for_conversion_only(), "你")
        self.assertEqual(event.payload.text_elements[1].byte_range, ByteRange(4, 5))
        self.assertEqual(event.payload.text_elements[1].placeholder_for_conversion_only(), "b")

    def test_user_message_item_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "id must be a string"):
            UserMessageItem(123, ())

        with self.assertRaisesRegex(TypeError, "content must be a list or tuple"):
            UserMessageItem("user-1", "hello")

        with self.assertRaisesRegex(TypeError, "content entries must be UserInput"):
            UserMessageItem("user-1", ({"type": "text", "text": "hello"},))

    def test_hook_prompt_fragment_roundtrip_uses_xml_and_rejects_empty_ids(self):
        fragment = HookPromptFragment.from_single_hook("Retry with care & tests.", "hook-run-1")
        serialized = serialize_hook_prompt_fragment(fragment.text, fragment.hook_run_id)
        parsed = parse_hook_prompt_fragment(serialized)
        message = build_hook_prompt_message((fragment,))
        parsed_message = parse_hook_prompt_message(None, message.content)

        self.assertIn("&amp;", serialized)
        self.assertEqual(parsed, fragment)
        self.assertEqual(parsed_message.fragments, (fragment,))
        self.assertIsNone(serialize_hook_prompt_fragment("ignored", " "))
        self.assertIsNone(parse_hook_prompt_fragment("<hook_prompt hook_run_id=''>x</hook_prompt>"))

    def test_hook_prompt_from_fragments_only_generates_id_for_none(self):
        fragment = HookPromptFragment.from_single_hook("Retry", "hook-run-1")

        self.assertEqual(HookPromptItem.from_fragments("", (fragment,)).id, "")
        self.assertNotEqual(HookPromptItem.from_fragments(None, (fragment,)).id, "")

    def test_hook_prompt_items_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            HookPromptFragment(123, "hook-run-1")

        with self.assertRaisesRegex(TypeError, "hook_run_id must be a string"):
            HookPromptFragment("text", 123)

        with self.assertRaisesRegex(TypeError, "id must be a string"):
            HookPromptItem(123, ())

        with self.assertRaisesRegex(TypeError, "fragments must be a list or tuple"):
            HookPromptItem("hook-1", "fragment")

        with self.assertRaisesRegex(TypeError, "fragments entries must be HookPromptFragment"):
            HookPromptItem("hook-1", ({"text": "x", "hookRunId": "run"},))

    def test_agent_message_and_reasoning_legacy_events(self):
        agent = AgentMessageItem(
            "agent-1",
            (AgentMessageContent.text_content("hello"), AgentMessageContent.text_content("again")),
            phase="commentary",
        )
        reasoning = ReasoningItem("reason-1", ("summary",), raw_content=("raw",))

        agent_events = agent.as_legacy_events()
        summary_events = reasoning.as_legacy_events(show_raw_agent_reasoning=False)
        raw_events = reasoning.as_legacy_events(show_raw_agent_reasoning=True)

        self.assertEqual(agent_events[0].payload, AgentMessageEvent("hello", phase="commentary"))
        self.assertEqual(agent_events[1].payload, AgentMessageEvent("again", phase="commentary"))
        self.assertEqual(summary_events, [EventMsg.with_payload("agent_reasoning", AgentReasoningEvent("summary"))])
        self.assertEqual(raw_events[-1], EventMsg.with_payload("agent_reasoning_raw_content", AgentReasoningRawContentEvent("raw")))

    def test_agent_plan_and_reasoning_items_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            AgentMessageContent.text_content(123)

        with self.assertRaisesRegex(ValueError, "unknown agent message content type"):
            AgentMessageContent("Image", "x")

        with self.assertRaisesRegex(TypeError, "id must be a string"):
            AgentMessageItem(123, ())

        with self.assertRaisesRegex(TypeError, "content must be a list or tuple"):
            AgentMessageItem("agent-1", "hello")

        with self.assertRaisesRegex(TypeError, "content entries must be AgentMessageContent"):
            AgentMessageItem("agent-1", ({"type": "Text", "text": "hello"},))

        with self.assertRaisesRegex(TypeError, "phase must be a MessagePhase, string, or None"):
            AgentMessageItem("agent-1", (), phase=123)

        with self.assertRaises(ValueError):
            AgentMessageItem("agent-1", (), phase="thinking")

        with self.assertRaisesRegex(TypeError, "memory_citation must be a MemoryCitation or None"):
            AgentMessageItem("agent-1", (), memory_citation={})

        with self.assertRaisesRegex(TypeError, "text must be a string"):
            PlanItem("plan-1", 123)

        with self.assertRaisesRegex(TypeError, "summary_text must be a list or tuple of strings"):
            ReasoningItem("reason-1", "summary")

        with self.assertRaisesRegex(TypeError, "raw_content must be a list or tuple of strings"):
            ReasoningItem("reason-1", ("summary",), raw_content="raw")

        with self.assertRaisesRegex(TypeError, "summary_text entries must be strings"):
            ReasoningItem("reason-1", (123,))

        with self.assertRaisesRegex(TypeError, "summary_text must be a list or tuple of strings"):
            TurnItem.from_mapping({"type": "Reasoning", "id": "reason-1", "summary_text": "summary"})

        with self.assertRaises(KeyError):
            TurnItem.from_mapping({"type": "Reasoning", "id": "reason-1"})

    def test_file_change_item_legacy_begin_and_end(self):
        changes = {Path("new.txt"): FileChange.add("hello")}
        item = FileChangeItem(
            "patch-1",
            changes,
            status=PatchApplyStatus.COMPLETED,
            auto_approved=True,
            stdout="Done!",
            stderr="",
        )

        begin = item.as_legacy_begin_event("turn-1")
        end = item.as_legacy_end_event("turn-1")

        self.assertEqual(begin.payload, PatchApplyBeginEvent("patch-1", True, changes, turn_id="turn-1"))
        self.assertEqual(end.payload, PatchApplyEndEvent("patch-1", "Done!", "", True, PatchApplyStatus.COMPLETED, turn_id="turn-1", changes=changes))
        self.assertIsNone(FileChangeItem("patch-2", changes).as_legacy_end_event("turn-1"))

    def test_mcp_tool_call_item_legacy_events_and_success(self):
        ok_result = CallToolResult(content=({"type": "text", "text": "ok"},), is_error=False)
        item = McpToolCallItem(
            id="mcp-1",
            server="server",
            tool="tool",
            arguments={"arg": "value"},
            mcp_app_resource_uri="app://connector",
            plugin_id="sample@test",
            status=McpToolCallStatus.COMPLETED,
            result=ok_result,
            duration={"secs": 0, "nanos": 42_000_000},
        )
        failed = McpToolCallItem(
            id="mcp-2",
            server="server",
            tool="tool",
            arguments=None,
            status=McpToolCallStatus.FAILED,
            error=McpToolCallError("boom"),
            duration={"secs": 0, "nanos": 1},
        )

        begin = item.as_legacy_begin_event()
        end = item.as_legacy_end_event()
        failed_end = failed.as_legacy_end_event()

        self.assertEqual(begin.payload.invocation.arguments, {"arg": "value"})
        self.assertTrue(end.payload.is_success())
        self.assertEqual(failed_end.payload.result, "boom")
        self.assertFalse(failed_end.payload.is_success())
        self.assertIsNone(McpToolCallItem("mcp-3", "s", "t", {}, McpToolCallStatus.COMPLETED, result=ok_result).as_legacy_end_event())

    def test_turn_item_id_and_legacy_events(self):
        search = TurnItem.web_search(WebSearchItem("search-1", "query", {"type": "search"}))
        compacted = TurnItem.context_compaction(ContextCompactionItem("compact-1"))

        self.assertEqual(search.id(), "search-1")
        self.assertEqual(search.as_legacy_events(False), [EventMsg.with_payload("web_search_end", WebSearchEndEvent("search-1", "query", WebSearchAction.search()))])
        self.assertEqual(compacted.as_legacy_events(False)[0].type, "context_compacted")

    def test_remaining_turn_items_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "query must be a string"):
            WebSearchItem("search-1", 123, {})

        with self.assertRaisesRegex(TypeError, "action must be a WebSearchAction or mapping"):
            WebSearchItem("search-1", "query", "search")

        with self.assertRaises(KeyError):
            TurnItem.from_mapping({"type": "UserMessage", "id": "user-1"})

        with self.assertRaises(KeyError):
            TurnItem.from_mapping({"type": "AgentMessage", "id": "agent-1"})

        with self.assertRaises(KeyError):
            TurnItem.from_mapping({"type": "HookPrompt", "id": "hook-1"})

        with self.assertRaises(KeyError):
            TurnItem.from_mapping({"type": "WebSearch", "id": "search-1", "query": "q"})

        with self.assertRaisesRegex(TypeError, "action must be a WebSearchAction or mapping"):
            TurnItem.from_mapping({"type": "WebSearch", "id": "search-1", "query": "q", "action": "search"})

        with self.assertRaisesRegex(TypeError, "path must be a string or Path"):
            ImageViewItem("image-1", 123)

        self.assertEqual(ImageViewItem("image-1", "image.png").path, Path("image.png"))

        with self.assertRaisesRegex(TypeError, "status must be a string"):
            ImageGenerationItem("image-gen-1", 123, "ok")

        with self.assertRaisesRegex(TypeError, "saved_path must be a string, Path, or None"):
            ImageGenerationItem("image-gen-1", "completed", "ok", saved_path=123)

        with self.assertRaisesRegex(TypeError, "changes must be a mapping"):
            FileChangeItem("patch-1", "not-a-map")

        with self.assertRaisesRegex(TypeError, "changes keys must be strings or Path"):
            FileChangeItem("patch-1", {123: FileChange.add("hello")})

        with self.assertRaisesRegex(TypeError, "changes values must be FileChange"):
            FileChangeItem("patch-1", {Path("a.txt"): "add"})

        with self.assertRaisesRegex(TypeError, "auto_approved must be a bool or None"):
            FileChangeItem("patch-1", {Path("a.txt"): FileChange.add("hello")}, auto_approved=1)

        with self.assertRaisesRegex(TypeError, "saved_path must be a string, Path, or None"):
            TurnItem.from_mapping({"type": "ImageGeneration", "id": "image-gen-1", "status": "completed", "result": "ok", "saved_path": 123})

        with self.assertRaisesRegex(TypeError, "auto_approved must be a bool or None"):
            TurnItem.from_mapping({"type": "FileChange", "id": "patch-1", "changes": {}, "auto_approved": "yes"})

        with self.assertRaises(KeyError):
            TurnItem.from_mapping({"type": "FileChange", "id": "patch-1"})

        with self.assertRaisesRegex(TypeError, "message must be a string"):
            McpToolCallError(123)

        with self.assertRaisesRegex(TypeError, "server must be a string"):
            McpToolCallItem("mcp-1", 123, "tool", {}, McpToolCallStatus.COMPLETED)

        with self.assertRaisesRegex(ValueError, "unknown mcp tool call status"):
            McpToolCallItem("mcp-1", "server", "tool", {}, "done")

        with self.assertRaisesRegex(TypeError, "result must be a CallToolResult or None"):
            McpToolCallItem("mcp-1", "server", "tool", {}, McpToolCallStatus.COMPLETED, result={})

        with self.assertRaisesRegex(TypeError, "error must be a McpToolCallError or None"):
            McpToolCallItem("mcp-1", "server", "tool", {}, McpToolCallStatus.FAILED, error={"message": "boom"})

        with self.assertRaisesRegex(TypeError, "mcp tool call result must be a mapping"):
            TurnItem.from_mapping({"type": "McpToolCall", "id": "mcp-1", "server": "server", "tool": "tool", "arguments": {}, "status": "completed", "result": "ok"})

        with self.assertRaisesRegex(TypeError, "mcp tool call error must be a mapping"):
            TurnItem.from_mapping({"type": "McpToolCall", "id": "mcp-1", "server": "server", "tool": "tool", "arguments": {}, "status": "failed", "error": "boom"})

        with self.assertRaises(KeyError):
            TurnItem.from_mapping({"type": "McpToolCall", "id": "mcp-1", "server": "server", "tool": "tool", "status": "completed"})

        with self.assertRaises(KeyError):
            TurnItem.from_mapping({"type": "McpToolCall", "id": "mcp-1", "server": "server", "tool": "tool", "arguments": {}})

        with self.assertRaisesRegex(TypeError, "id must be a string"):
            ContextCompactionItem(123)

        with self.assertRaisesRegex(ValueError, "unknown turn item type"):
            TurnItem("Unknown", object())

        with self.assertRaisesRegex(TypeError, "WebSearch item must be WebSearchItem"):
            TurnItem.web_search(ContextCompactionItem("compact-1"))

    def test_item_started_and_completed_events_emit_legacy_events(self):
        thread_id = ThreadId.from_string("33333333-3333-3333-3333-333333333333")
        started = ItemStartedEvent(thread_id, "turn-1", TurnItem.web_search(WebSearchItem("search-1", "q", {})), 123)
        completed = ItemCompletedEvent(
            thread_id,
            "turn-1",
            TurnItem.user_message(UserMessageItem("user-1", (UserInput.text_input("hi"),))),
        )

        self.assertEqual(started.as_legacy_events(), [EventMsg.with_payload("web_search_begin", WebSearchBeginEvent("search-1"))])
        self.assertEqual(completed.completed_at_ms, 0)
        self.assertEqual(completed.as_legacy_events()[0].payload, UserMessageEvent("hi", images=()))

    def test_turn_item_from_mapping_parses_tagged_shapes(self):
        item = TurnItem.from_mapping(
            {
                "type": "McpToolCall",
                "id": "mcp-1",
                "server": "server",
                "tool": "tool",
                "arguments": {"arg": "value"},
                "status": "completed",
                "result": {"content": [], "isError": False},
                "duration": {"secs": 0, "nanos": 1},
            }
        )

        self.assertEqual(item.type, "McpToolCall")
        self.assertTrue(item.item.as_legacy_end_event().payload.is_success())

    def test_mcp_tool_call_parser_preserves_empty_camel_case_optional_strings(self):
        item = TurnItem.from_mapping(
            {
                "type": "McpToolCall",
                "id": "mcp-1",
                "server": "server",
                "tool": "tool",
                "arguments": {},
                "status": "completed",
                "mcpAppResourceUri": "",
                "mcp_app_resource_uri": "ignored",
                "pluginId": "",
                "plugin_id": "ignored",
            }
        )

        self.assertEqual(item.item.mcp_app_resource_uri, "")
        self.assertEqual(item.item.plugin_id, "")


if __name__ == "__main__":
    unittest.main()
