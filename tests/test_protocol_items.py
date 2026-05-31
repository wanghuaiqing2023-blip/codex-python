import unittest
from pathlib import Path

import pycodex.protocol as protocol
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageEvent,
    AgentMessageItem,
    AgentReasoningEvent,
    AgentReasoningRawContentEvent,
    ByteRange,
    CallToolResult,
    CollabAgentState,
    CollabAgentStatus,
    CollabAgentTool,
    CollabAgentToolCallItem,
    CollabAgentToolCallStatus,
    CommandExecutionItem,
    CommandExecutionSource,
    CommandExecutionStatus,
    ContextCompactionItem,
    DynamicToolCallItem,
    DynamicToolCallStatus,
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
    MemoryCitation,
    MemoryCitationEntry,
    McpToolCallError,
    McpToolCallItem,
    McpToolCallStatus,
    PatchApplyBeginEvent,
    PatchApplyEndEvent,
    PatchApplyStatus,
    PlanItem,
    ReasoningItem,
    ReasoningEffort,
    ReviewModeItem,
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
    turn_completed_notification,
    turn_started_notification,
    turn_to_app_server_mapping,
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

    def test_user_message_app_server_mapping_matches_v2_shape(self):
        item = TurnItem.user_message(
            UserMessageItem(
                "user-1",
                (
                    UserInput.text_input("hello", (TextElement.new(ByteRange(0, 5), "hello"),)),
                    UserInput.image("https://example.com/image.png", detail=ImageDetail.ORIGINAL),
                    UserInput.local_image(Path("local/image.png"), detail=ImageDetail.ORIGINAL),
                    UserInput.skill("skill-creator", Path("/repo/.codex/skills/skill-creator/SKILL.md")),
                    UserInput.mention("Demo App", "app://demo-app"),
                ),
            )
        )

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "userMessage",
                "id": "user-1",
                "content": [
                    {
                        "type": "text",
                        "text": "hello",
                        "text_elements": [
                            {
                                "byteRange": {"start": 0, "end": 5},
                                "placeholder": "hello",
                            }
                        ],
                    },
                    {
                        "type": "image",
                        "url": "https://example.com/image.png",
                        "detail": "original",
                    },
                    {
                        "type": "localImage",
                        "path": "local/image.png",
                        "detail": "original",
                    },
                    {
                        "type": "skill",
                        "name": "skill-creator",
                        "path": "/repo/.codex/skills/skill-creator/SKILL.md",
                    },
                    {
                        "type": "mention",
                        "name": "Demo App",
                        "path": "app://demo-app",
                    },
                ],
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)

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

    def test_hook_prompt_app_server_mapping_matches_v2_shape(self):
        fragment = HookPromptFragment.from_single_hook("Retry with care", "hook-run-1")
        item = TurnItem.hook_prompt(HookPromptItem.from_fragments("hook-1", (fragment,)))

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "hookPrompt",
                "id": "hook-1",
                "fragments": [
                    {
                        "text": "Retry with care",
                        "hookRunId": "hook-run-1",
                    }
                ],
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)

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

    def test_agent_message_app_server_mapping_matches_v2_shape(self):
        item = TurnItem.agent_message(
            AgentMessageItem(
                "agent-1",
                (AgentMessageContent.text_content("Hello "), AgentMessageContent.text_content("world")),
                phase=None,
            )
        )
        cited = TurnItem.agent_message(
            AgentMessageItem(
                "agent-2",
                (AgentMessageContent.text_content("final"),),
                phase="final_answer",
                memory_citation=MemoryCitation(
                    entries=(MemoryCitationEntry("MEMORY.md", 1, 2, "summary"),),
                    rollout_ids=("rollout-1",),
                ),
            )
        )

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "agentMessage",
                "id": "agent-1",
                "text": "Hello world",
                "phase": None,
                "memoryCitation": None,
            },
        )
        self.assertEqual(
            cited.to_app_server_mapping(),
            {
                "type": "agentMessage",
                "id": "agent-2",
                "text": "final",
                "phase": "final_answer",
                "memoryCitation": {
                    "entries": [
                        {
                            "path": "MEMORY.md",
                            "lineStart": 1,
                            "lineEnd": 2,
                            "note": "summary",
                        }
                    ],
                    "threadIds": ["rollout-1"],
                },
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)
        self.assertEqual(TurnItem.from_mapping(cited.to_app_server_mapping()).item, cited.item)

    def test_reasoning_app_server_mapping_matches_v2_shape(self):
        item = TurnItem.reasoning(
            ReasoningItem(
                "reasoning-1",
                ("line one", "line two"),
                raw_content=("raw one",),
            )
        )

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "reasoning",
                "id": "reasoning-1",
                "summary": ["line one", "line two"],
                "content": ["raw one"],
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)
        self.assertEqual(
            TurnItem.from_mapping(
                {
                    "type": "reasoning",
                    "id": "reasoning-2",
                    "summary": [],
                    "content": [],
                }
            ).item,
            ReasoningItem("reasoning-2", (), raw_content=()),
        )

    def test_plan_app_server_mapping_matches_v2_shape(self):
        item = TurnItem.plan(PlanItem("plan-1", "Check files"))

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "plan",
                "id": "plan-1",
                "text": "Check files",
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)

    def test_context_compaction_app_server_mapping_matches_v2_shape(self):
        item = TurnItem.context_compaction(ContextCompactionItem("compact-1"))

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "contextCompaction",
                "id": "compact-1",
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)

    def test_web_search_app_server_mapping_matches_v2_shape(self):
        item = TurnItem.web_search(WebSearchItem("search-1", "docs", WebSearchAction.search(query="docs")))
        open_page = TurnItem.web_search(WebSearchItem("search-2", "docs", WebSearchAction.open_page("https://example.com")))
        find_in_page = TurnItem.web_search(
            WebSearchItem("search-3", "docs", WebSearchAction.find_in_page("https://example.com", "needle"))
        )

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "webSearch",
                "id": "search-1",
                "query": "docs",
                "action": {
                    "type": "search",
                    "query": "docs",
                    "queries": None,
                },
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)
        self.assertEqual(open_page.to_app_server_mapping()["action"], {"type": "openPage", "url": "https://example.com"})
        self.assertEqual(find_in_page.to_app_server_mapping()["action"], {"type": "findInPage", "url": "https://example.com", "pattern": "needle"})
        self.assertEqual(TurnItem.from_mapping(open_page.to_app_server_mapping()).item, open_page.item)
        self.assertEqual(TurnItem.from_mapping(find_in_page.to_app_server_mapping()).item, find_in_page.item)

    def test_web_search_app_server_mapping_accepts_optional_v2_action(self):
        absent = TurnItem.from_mapping({"type": "webSearch", "id": "search-1", "query": "docs"})
        explicit_null = TurnItem.from_mapping({"type": "webSearch", "id": "search-2", "query": "docs", "action": None})

        self.assertEqual(absent.item.action, WebSearchAction.other())
        self.assertEqual(explicit_null.item.action, WebSearchAction.other())
        self.assertEqual(absent.to_app_server_mapping()["action"], {"type": "other"})

    def test_image_view_app_server_mapping_matches_v2_shape(self):
        item = TurnItem.image_view(ImageViewItem("image-1", "/tmp/image.png"))

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "imageView",
                "id": "image-1",
                "path": str(Path("/tmp/image.png")),
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)

    def test_image_generation_app_server_mapping_matches_v2_shape(self):
        item = TurnItem.image_generation(
            ImageGenerationItem(
                "image-gen-1",
                "completed",
                "ok",
                revised_prompt="draw a cat",
                saved_path="/tmp/cat.png",
            )
        )
        without_path = TurnItem.image_generation(ImageGenerationItem("image-gen-2", "inProgress", "pending"))

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "imageGeneration",
                "id": "image-gen-1",
                "status": "completed",
                "revisedPrompt": "draw a cat",
                "result": "ok",
                "savedPath": str(Path("/tmp/cat.png")),
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_app_server_mapping()).item, item.item)
        self.assertEqual(
            without_path.to_app_server_mapping(),
            {
                "type": "imageGeneration",
                "id": "image-gen-2",
                "status": "inProgress",
                "revisedPrompt": None,
                "result": "pending",
            },
        )
        self.assertEqual(TurnItem.from_mapping(without_path.to_app_server_mapping()).item, without_path.item)

    def test_turn_to_app_server_mapping_matches_v2_turn_shape(self):
        user = TurnItem.user_message(UserMessageItem("user-1", (UserInput.text_input("hi"),)))
        agent = TurnItem.agent_message(AgentMessageItem("agent-1", (AgentMessageContent.text_content("done"),)))

        self.assertEqual(
            turn_to_app_server_mapping(
                "turn-1",
                (user, agent),
                status="completed",
                started_at=10,
                completed_at=12,
                duration_ms=2000,
            ),
            {
                "id": "turn-1",
                "items": [
                    user.to_app_server_mapping(),
                    agent.to_app_server_mapping(),
                ],
                "itemsView": "full",
                "status": "completed",
                "error": None,
                "startedAt": 10,
                "completedAt": 12,
                "durationMs": 2000,
            },
        )
        self.assertIn("turn_to_app_server_mapping", protocol.__all__)

        with self.assertRaisesRegex(ValueError, "unknown turn status"):
            turn_to_app_server_mapping("turn-1", (), status="done")
        with self.assertRaisesRegex(ValueError, "unknown turn items view"):
            turn_to_app_server_mapping("turn-1", (), items_view="partial")
        with self.assertRaisesRegex(TypeError, "items entries must be TurnItem"):
            turn_to_app_server_mapping("turn-1", ({"type": "plan"},))

    def test_turn_notifications_match_app_server_v2_envelopes(self):
        agent = TurnItem.agent_message(AgentMessageItem("agent-1", (AgentMessageContent.text_content("done"),)))
        started = turn_started_notification("thread-1", "turn-1", started_at=10)
        completed = turn_completed_notification(
            "thread-1",
            "turn-1",
            (agent,),
            completed_at=12,
            duration_ms=2000,
        )

        self.assertEqual(started["method"], "turn/started")
        self.assertEqual(started["params"]["threadId"], "thread-1")
        self.assertEqual(started["params"]["turn"]["status"], "inProgress")
        self.assertEqual(started["params"]["turn"]["startedAt"], 10)
        self.assertEqual(completed["method"], "turn/completed")
        self.assertEqual(completed["params"]["threadId"], "thread-1")
        self.assertEqual(completed["params"]["turn"]["status"], "completed")
        self.assertEqual(completed["params"]["turn"]["items"], [agent.to_app_server_mapping()])
        self.assertEqual(completed["params"]["turn"]["completedAt"], 12)
        self.assertEqual(completed["params"]["turn"]["durationMs"], 2000)
        self.assertIn("turn_started_notification", protocol.__all__)
        self.assertIn("turn_completed_notification", protocol.__all__)

        with self.assertRaisesRegex(ValueError, "completed turn status must be terminal"):
            turn_completed_notification("thread-1", "turn-1", (), status="inProgress")

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

    def test_file_change_item_app_server_mapping_matches_v2_shape(self):
        item = FileChangeItem(
            "patch-1",
            {
                Path("b.txt"): FileChange.update("--- old\n+++ new", move_path=Path("c.txt")),
                Path("a.txt"): FileChange.add("hello"),
            },
            status=PatchApplyStatus.COMPLETED,
        )

        self.assertEqual(
            item.to_app_server_mapping(),
            {
                "type": "fileChange",
                "id": "patch-1",
                "changes": [
                    {"path": "a.txt", "kind": {"type": "add"}, "diff": "hello"},
                    {
                        "path": "b.txt",
                        "kind": {"type": "update", "move_path": "c.txt"},
                        "diff": "--- old\n+++ new\n\nMoved to: c.txt",
                    },
                ],
                "status": "completed",
            },
        )
        self.assertEqual(FileChangeItem("patch-2", {}, status=None).to_app_server_mapping()["status"], "inProgress")

    def test_file_change_item_parses_app_server_v2_changes_list(self):
        item = TurnItem.from_mapping(
            {
                "type": "fileChange",
                "id": "patch-1",
                "changes": [
                    {"path": "a.txt", "kind": {"type": "add"}, "diff": "hello"},
                    {
                        "path": "b.txt",
                        "kind": {"type": "update", "move_path": "c.txt"},
                        "diff": "--- old\n+++ new\n\nMoved to: c.txt",
                    },
                ],
                "status": "completed",
            }
        )

        self.assertEqual(
            item.item.changes,
            {
                Path("a.txt"): FileChange.add("hello"),
                Path("b.txt"): FileChange.update("--- old\n+++ new", move_path=Path("c.txt")),
            },
        )
        self.assertEqual(item.item.status, PatchApplyStatus.COMPLETED)

        in_progress = TurnItem.from_mapping(
            {
                "type": "fileChange",
                "id": "patch-2",
                "changes": [{"path": "a.txt", "kind": {"type": "add"}, "diff": "hello"}],
                "status": "inProgress",
            }
        )
        self.assertIsNone(in_progress.item.status)
        self.assertEqual(in_progress.item.to_app_server_mapping()["status"], "inProgress")

    def test_turn_item_app_server_mapping_bridges_supported_v2_items(self):
        command = TurnItem.command_execution(
            CommandExecutionItem(
                "cmd-1",
                "pwd",
                "C:/work",
                CommandExecutionStatus.COMPLETED,
                source=CommandExecutionSource.AGENT,
                command_actions=({"type": "unknown", "command": "pwd"},),
                aggregated_output="C:/work\n",
                exit_code=0,
                duration_ms=3,
            )
        )
        file_change = TurnItem.file_change(
            FileChangeItem("patch-1", {Path("a.txt"): FileChange.add("hello")}, status=PatchApplyStatus.COMPLETED)
        )

        self.assertEqual(command.to_app_server_mapping()["type"], "commandExecution")
        self.assertEqual(command.to_app_server_mapping()["commandActions"], [{"type": "unknown", "command": "pwd"}])
        self.assertEqual(TurnItem.from_mapping(command.to_app_server_mapping()).item, command.item)
        self.assertEqual(file_change.to_app_server_mapping()["type"], "fileChange")
        self.assertEqual(TurnItem.from_mapping(file_change.to_app_server_mapping()).item, file_change.item)
        self.assertEqual(
            TurnItem.plan(PlanItem("plan-1", "next")).to_app_server_mapping(),
            {"type": "plan", "id": "plan-1", "text": "next"},
        )

    def test_turn_item_app_server_mapping_bridges_lightweight_v2_extension_items(self):
        dynamic = TurnItem.from_mapping(
            {
                "type": "dynamicToolCall",
                "id": "dyn-1",
                "namespace": "browser",
                "tool": "open",
                "arguments": {"url": "https://example.com"},
                "status": "completed",
                "contentItems": [{"type": "inputText", "text": "ok"}],
                "success": True,
                "durationMs": 7,
            }
        )
        entered = TurnItem.from_mapping({"type": "enteredReviewMode", "id": "review-1", "review": "review text"})
        exited = TurnItem.exited_review_mode(ReviewModeItem("review-2", "done"))
        collab = TurnItem.from_mapping(
            {
                "type": "collabAgentToolCall",
                "id": "collab-1",
                "tool": "spawnAgent",
                "status": "inProgress",
                "senderThreadId": "thread-a",
                "receiverThreadIds": ["thread-b"],
                "prompt": "help",
                "model": "gpt-5",
                "reasoningEffort": "medium",
                "agentsStates": {"thread-b": {"status": "running", "message": None}},
            }
        )

        self.assertIsInstance(dynamic.item, DynamicToolCallItem)
        self.assertEqual(dynamic.item.status, DynamicToolCallStatus.COMPLETED)
        self.assertEqual(dynamic.item.content_items, ({"type": "inputText", "text": "ok"},))
        self.assertEqual(dynamic.to_app_server_mapping()["type"], "dynamicToolCall")
        self.assertEqual(dynamic.to_app_server_mapping()["contentItems"], [{"type": "inputText", "text": "ok"}])
        self.assertEqual(TurnItem.from_mapping(dynamic.to_app_server_mapping()).item, dynamic.item)
        self.assertEqual(entered.to_app_server_mapping(), {"type": "enteredReviewMode", "id": "review-1", "review": "review text"})
        self.assertEqual(exited.to_app_server_mapping(), {"type": "exitedReviewMode", "id": "review-2", "review": "done"})
        self.assertIsInstance(collab.item, CollabAgentToolCallItem)
        self.assertEqual(collab.item.tool, CollabAgentTool.SPAWN_AGENT)
        self.assertEqual(collab.item.status, CollabAgentToolCallStatus.IN_PROGRESS)
        self.assertEqual(collab.item.reasoning_effort, ReasoningEffort.MEDIUM)
        self.assertEqual(collab.item.agents_states["thread-b"], CollabAgentState(CollabAgentStatus.RUNNING))
        self.assertEqual(collab.to_app_server_mapping()["receiverThreadIds"], ["thread-b"])
        self.assertEqual(collab.to_app_server_mapping()["reasoningEffort"], "medium")
        self.assertEqual(TurnItem.from_mapping(collab.to_app_server_mapping()).item, collab.item)
        self.assertIn("DynamicToolCallItem", protocol.__all__)
        self.assertIn("CollabAgentToolCallItem", protocol.__all__)
        self.assertIn("ReviewModeItem", protocol.__all__)

    def test_command_execution_item_parses_app_server_thread_item_shape(self):
        self.assertIn("CommandExecutionItem", protocol.__all__)

        item = TurnItem.from_mapping(
            {
                "type": "commandExecution",
                "id": "cmd-1",
                "command": "python -m unittest",
                "cwd": "C:/work",
                "processId": "pty-1",
                "source": "userShell",
                "status": "inProgress",
                "commandActions": ({"kind": "run"},),
                "aggregatedOutput": None,
                "exitCode": None,
                "durationMs": 12,
            }
        )

        self.assertIsInstance(item.item, CommandExecutionItem)
        self.assertEqual(item.item.id, "cmd-1")
        self.assertEqual(item.item.command, "python -m unittest")
        self.assertEqual(item.item.cwd, Path("C:/work"))
        direct = CommandExecutionItem("cmd-direct", "pwd", "C:/work", CommandExecutionStatus.COMPLETED)
        self.assertEqual(direct.cwd, Path("C:/work"))
        self.assertEqual(item.item.process_id, "pty-1")
        self.assertEqual(item.item.source, CommandExecutionSource.USER_SHELL)
        self.assertEqual(item.item.status, "inProgress")
        self.assertEqual(item.item.command_actions, ({"kind": "run"},))
        self.assertIsNone(item.item.aggregated_output)
        self.assertIsNone(item.item.exit_code)
        self.assertEqual(item.item.duration_ms, 12)
        self.assertEqual(item.item.status, CommandExecutionStatus.IN_PROGRESS)
        self.assertEqual(
            item.item.to_mapping(),
            {
                "id": "cmd-1",
                "command": "python -m unittest",
                "cwd": "C:/work",
                "processId": "pty-1",
                "source": "userShell",
                "status": "inProgress",
                "commandActions": [{"kind": "run"}],
                "aggregatedOutput": None,
                "exitCode": None,
                "durationMs": 12,
            },
        )
        self.assertEqual(TurnItem.from_mapping(item.to_mapping()).item, item.item)

        with self.assertRaisesRegex(ValueError, "unknown command execution status"):
            CommandExecutionItem("cmd-2", "pwd", Path("C:/work"), "done")
        with self.assertRaisesRegex(ValueError, "unknown command execution source"):
            CommandExecutionItem("cmd-3", "pwd", Path("C:/work"), CommandExecutionStatus.COMPLETED, source="shell")
        with self.assertRaisesRegex(TypeError, "cwd must be a string or Path"):
            CommandExecutionItem("cmd-4", "pwd", 123, CommandExecutionStatus.COMPLETED)
        with self.assertRaisesRegex(TypeError, "exit_code must be an int or None"):
            CommandExecutionItem("cmd-5", "pwd", Path("C:/work"), CommandExecutionStatus.COMPLETED, exit_code=True)
        with self.assertRaisesRegex(TypeError, "duration_ms must be an int or None"):
            CommandExecutionItem("cmd-6", "pwd", Path("C:/work"), CommandExecutionStatus.COMPLETED, duration_ms=False)
        with self.assertRaisesRegex(TypeError, "command_actions must be a list or tuple"):
            CommandExecutionItem("cmd-actions", "pwd", Path("C:/work"), CommandExecutionStatus.COMPLETED, command_actions="run")
        with self.assertRaisesRegex(ValueError, "exit_code must fit in i32"):
            CommandExecutionItem("cmd-7", "pwd", Path("C:/work"), CommandExecutionStatus.COMPLETED, exit_code=2**31)
        with self.assertRaisesRegex(ValueError, "duration_ms must fit in i64"):
            CommandExecutionItem("cmd-8", "pwd", Path("C:/work"), CommandExecutionStatus.COMPLETED, duration_ms=2**63)
        with self.assertRaisesRegex(TypeError, "exitCode must be an int or None"):
            TurnItem.from_mapping(
                {
                    "type": "CommandExecution",
                    "id": "cmd-9",
                    "command": "pwd",
                    "cwd": "C:/work",
                    "status": CommandExecutionStatus.COMPLETED,
                    "exitCode": True,
                }
            )
        with self.assertRaisesRegex(TypeError, "commandActions must be a list or tuple"):
            TurnItem.from_mapping(
                {
                    "type": "CommandExecution",
                    "id": "cmd-actions",
                    "command": "pwd",
                    "cwd": "C:/work",
                    "status": CommandExecutionStatus.COMPLETED,
                    "commandActions": "run",
                }
            )
        with self.assertRaisesRegex(ValueError, "exit_code must fit in i32"):
            TurnItem.from_mapping(
                {
                    "type": "CommandExecution",
                    "id": "cmd-10",
                    "command": "pwd",
                    "cwd": "C:/work",
                    "status": CommandExecutionStatus.COMPLETED,
                    "exitCode": -(2**31) - 1,
                }
            )

    def test_mcp_tool_call_item_legacy_events_and_success(self):
        ok_result = CallToolResult(
            content=({"type": "text", "text": "ok"},),
            structured_content={"ok": True},
            is_error=False,
            meta={"trace": "1"},
        )
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

        self.assertEqual(
            TurnItem.mcp_tool_call(item).to_app_server_mapping(),
            {
                "type": "mcpToolCall",
                "id": "mcp-1",
                "server": "server",
                "tool": "tool",
                "status": "completed",
                "arguments": {"arg": "value"},
                "mcpAppResourceUri": "app://connector",
                "pluginId": "sample@test",
                "result": {
                    "content": [{"type": "text", "text": "ok"}],
                    "structuredContent": {"ok": True},
                    "_meta": {"trace": "1"},
                },
                "error": None,
                "durationMs": 42,
            },
        )
        parsed = TurnItem.from_mapping(TurnItem.mcp_tool_call(item).to_app_server_mapping())
        self.assertEqual(parsed.type, "McpToolCall")
        self.assertEqual(parsed.item.id, item.id)
        self.assertEqual(parsed.item.server, item.server)
        self.assertEqual(parsed.item.tool, item.tool)
        self.assertEqual(parsed.item.arguments, item.arguments)
        self.assertEqual(parsed.item.status, item.status)
        self.assertEqual(parsed.item.mcp_app_resource_uri, item.mcp_app_resource_uri)
        self.assertEqual(parsed.item.plugin_id, item.plugin_id)
        self.assertEqual(parsed.item.result.content, ok_result.content)
        self.assertEqual(parsed.item.result.structured_content, ok_result.structured_content)
        self.assertEqual(parsed.item.result.meta, ok_result.meta)
        self.assertIsNone(parsed.item.result.is_error)
        self.assertIsNone(parsed.item.error)
        self.assertEqual(parsed.item.duration, 42)
        self.assertIsNone(
            TurnItem.mcp_tool_call(
                McpToolCallItem("mcp-3", "server", "tool", {}, McpToolCallStatus.IN_PROGRESS)
            ).to_app_server_mapping()["pluginId"]
        )

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

        with self.assertRaisesRegex(TypeError, "duration must be a duration mapping"):
            TurnItem.mcp_tool_call(
                McpToolCallItem("mcp-1", "server", "tool", {}, McpToolCallStatus.COMPLETED, duration=True)
            ).to_app_server_mapping()

        with self.assertRaisesRegex(TypeError, "duration must be a duration mapping"):
            TurnItem.mcp_tool_call(
                McpToolCallItem("mcp-1", "server", "tool", {}, McpToolCallStatus.COMPLETED, duration="42ms")
            ).to_app_server_mapping()

        with self.assertRaisesRegex(TypeError, "durationMs must be an int or None"):
            TurnItem.from_mapping(
                {
                    "type": "mcpToolCall",
                    "id": "mcp-1",
                    "server": "server",
                    "tool": "tool",
                    "arguments": {},
                    "status": "completed",
                    "durationMs": True,
                }
            )

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
