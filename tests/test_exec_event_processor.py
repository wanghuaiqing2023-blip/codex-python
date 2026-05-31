import io
import json
import tempfile
import unittest
from pathlib import Path

from pycodex.exec import (
    CollabAgentStatus,
    CollabTool,
    CollabToolCallStatus,
    CodexStatus,
    ExecSessionConfig,
    HumanEventProcessor,
    JsonEventProcessor,
    ThreadEvent,
    Usage,
    blended_total,
    collab_tool_call_item,
    command_execution_item,
    config_summary_entries,
    config_summary_lines,
    exec_item_from_turn_item,
    exec_item_from_app_server_item,
    exec_turn_completed_notification,
    exec_turn_started_notification,
    format_with_separators,
    final_message_from_turn_items,
    handle_last_message,
    human_item_completed_lines,
    human_item_started_lines,
    human_notification_lines,
    map_todo_items,
    notification_method,
    notification_params,
    should_print_final_message_to_stdout,
    should_print_final_message_to_tty,
    summarize_permission_profile,
    usage_from_notification,
    web_search_item,
)
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageItem,
    CallToolResult,
    CollabAgentState as ProtocolCollabAgentState,
    CollabAgentStatus as ProtocolCollabAgentStatus,
    CollabAgentTool as ProtocolCollabAgentTool,
    CollabAgentToolCallItem,
    CollabAgentToolCallStatus as ProtocolCollabAgentToolCallStatus,
    CommandExecutionItem,
    DynamicToolCallItem,
    DynamicToolCallStatus,
    FileChange,
    FileChangeItem,
    McpToolCallItem,
    McpToolCallStatus,
    PatchApplyStatus,
    PermissionProfile,
    PlanItem,
    ReasoningItem,
    TurnItem,
    WebSearchAction,
    WebSearchItem,
)


class ExecEventProcessorTests(unittest.TestCase):
    def test_thread_event_serializes_upstream_tagged_json_shape(self):
        event = ThreadEvent.thread_started("thread-1")

        self.assertEqual(event.to_mapping(), {"type": "thread.started", "thread_id": "thread-1"})
        self.assertEqual(json.loads(event.to_json_line()), event.to_mapping())

    def test_mcp_tool_call_result_preserves_meta_as_underscore_meta(self):
        processor = JsonEventProcessor()
        item = TurnItem.mcp_tool_call(
            McpToolCallItem(
                id="mcp-1",
                server="search service",
                tool="web_run",
                arguments={"search_query": [{"q": "OpenAI Codex CLI documentation"}]},
                status=McpToolCallStatus.COMPLETED,
                result=CallToolResult(
                    content=({"type": "text", "text": "search result"},),
                    meta={"raw_messages": [{"ref_id": "turn0search0"}]},
                ),
            )
        )

        collected = processor.collect_item_completed(item)

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        serialized = collected.events[0].to_mapping()
        self.assertEqual(
            serialized["item"]["result"]["_meta"],
            {"raw_messages": [{"ref_id": "turn0search0"}]},
        )
        self.assertNotIn("meta", serialized["item"]["result"])
        self.assertIsNone(serialized["item"]["result"]["structured_content"])

    def test_started_and_completed_tool_call_reuses_exec_item_id(self):
        processor = JsonEventProcessor()
        started_item = TurnItem.mcp_tool_call(
            McpToolCallItem(
                id="mcp-1",
                server="server",
                tool="tool",
                arguments={},
                status=McpToolCallStatus.IN_PROGRESS,
            )
        )
        completed_item = TurnItem.mcp_tool_call(
            McpToolCallItem(
                id="mcp-1",
                server="server",
                tool="tool",
                arguments={},
                status=McpToolCallStatus.COMPLETED,
                result=CallToolResult(content=()),
            )
        )

        started = processor.collect_item_started(started_item)
        completed = processor.collect_item_completed(completed_item)

        self.assertEqual(started.events[0].to_mapping()["item"]["id"], "item_0")
        self.assertEqual(completed.events[0].to_mapping()["item"]["id"], "item_0")

    def test_json_processor_mcp_tool_call_begin_and_end_emit_item_events(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "mcpToolCall",
                        "id": "mcp-1",
                        "server": "server_a",
                        "tool": "tool_x",
                        "status": "inProgress",
                        "arguments": {"key": "value"},
                        "result": None,
                        "error": None,
                    }
                },
            }
        )
        completed = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "mcpToolCall",
                        "id": "mcp-1",
                        "server": "server_a",
                        "tool": "tool_x",
                        "status": "completed",
                        "arguments": {"key": "value"},
                        "result": {"content": [], "structuredContent": None},
                        "error": None,
                    }
                },
            }
        )

        self.assertEqual(started.status, CodexStatus.RUNNING)
        self.assertEqual(completed.status, CodexStatus.RUNNING)
        self.assertEqual(
            started.events[0].to_mapping()["item"],
            {
                "id": "item_0",
                "type": "mcp_tool_call",
                "server": "server_a",
                "tool": "tool_x",
                "arguments": {"key": "value"},
                "result": None,
                "error": None,
                "status": "in_progress",
            },
        )
        self.assertEqual(
            completed.events[0].to_mapping()["item"],
            {
                "id": "item_0",
                "type": "mcp_tool_call",
                "server": "server_a",
                "tool": "tool_x",
                "arguments": {"key": "value"},
                "result": {"content": [], "structured_content": None},
                "error": None,
                "status": "completed",
            },
        )

    def test_json_processor_mcp_tool_call_failure_sets_failed_status(self):
        processor = JsonEventProcessor()

        collected = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "mcpToolCall",
                        "id": "mcp-2",
                        "server": "server_b",
                        "tool": "tool_y",
                        "status": "failed",
                        "arguments": {"param": 42},
                        "result": None,
                        "error": {"message": "tool exploded"},
                    }
                },
            }
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(
            collected.events[0].to_mapping()["item"],
            {
                "id": "item_0",
                "type": "mcp_tool_call",
                "server": "server_b",
                "tool": "tool_y",
                "arguments": {"param": 42},
                "result": None,
                "error": {"message": "tool exploded"},
                "status": "failed",
            },
        )

    def test_json_processor_mcp_tool_call_null_arguments_and_structured_content(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "mcpToolCall",
                        "id": "mcp-3",
                        "server": "server_c",
                        "tool": "tool_z",
                        "status": "inProgress",
                        "arguments": None,
                        "result": None,
                        "error": None,
                    }
                },
            }
        )
        completed = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "mcpToolCall",
                        "id": "mcp-3",
                        "server": "server_c",
                        "tool": "tool_z",
                        "status": "completed",
                        "arguments": None,
                        "result": {
                            "content": [{"type": "text", "text": "done"}],
                            "structuredContent": {"status": "ok"},
                        },
                        "error": None,
                    }
                },
            }
        )

        started_item = started.events[0].to_mapping()["item"]
        completed_item = completed.events[0].to_mapping()["item"]
        self.assertEqual(started_item["id"], "item_0")
        self.assertIsNone(started_item["arguments"])
        self.assertEqual(completed_item["id"], "item_0")
        self.assertIsNone(completed_item["arguments"])
        self.assertEqual(completed_item["result"]["content"], [{"type": "text", "text": "done"}])
        self.assertEqual(completed_item["result"]["structured_content"], {"status": "ok"})

    def test_failed_turn_does_not_overwrite_output_last_message_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "last-message.txt"
            output_path.write_text("keep existing contents", encoding="utf-8")
            processor = JsonEventProcessor(output_path)
            agent_item = TurnItem.agent_message(
                AgentMessageItem("msg-1", (AgentMessageContent.text_content("partial answer"),))
            )

            processor.collect_item_completed(agent_item)
            collected = processor.collect_turn_completed(status="failed", error="turn failed")
            processor.print_final_output(stderr=io.StringIO())

            self.assertEqual(collected.status, CodexStatus.INITIATE_SHUTDOWN)
            self.assertIsNone(processor.final_message)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "keep existing contents")

    def test_interrupted_turn_clears_stale_final_message_state(self):
        processor = HumanEventProcessor()
        stderr = io.StringIO()
        agent_item = TurnItem.agent_message(
            AgentMessageItem("msg-1", (AgentMessageContent.text_content("partial answer"),))
        )

        processor.collect_item_completed(agent_item, stderr=io.StringIO())
        status = processor.collect_turn_completed(status="interrupted", items=(), stderr=stderr)

        self.assertEqual(status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertIsNone(processor.final_message)
        self.assertFalse(processor.final_message_rendered)
        self.assertFalse(processor.emit_final_message_on_shutdown)
        self.assertEqual(stderr.getvalue(), "turn interrupted\n")

    def test_human_processor_typed_failed_turn_prints_error(self):
        processor = HumanEventProcessor()
        stderr = io.StringIO()

        status = processor.collect_turn_completed(status="Failed", error="turn failed", stderr=stderr)

        self.assertEqual(status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(stderr.getvalue(), "ERROR: turn failed\n")

    def test_json_processor_typed_turn_completed_normalizes_status_aliases(self):
        processor = JsonEventProcessor()
        agent_item = TurnItem.agent_message(
            AgentMessageItem("msg-1", (AgentMessageContent.text_content("final answer"),))
        )

        completed = processor.collect_turn_completed(status="Completed", items=(agent_item,))

        self.assertEqual(completed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")
        self.assertEqual(processor.final_message, "final answer")

    def test_json_processor_typed_turn_completed_closes_running_todo_list(self):
        processor = JsonEventProcessor()
        processor.collect_thread_events(
            {
                "method": "turn/plan/updated",
                "params": {"plan": [{"step": "ship", "status": "inProgress"}]},
            }
        )

        completed = processor.collect_turn_completed(status="completed")

        self.assertEqual(completed.events[0].to_mapping()["type"], "item.completed")
        self.assertEqual(completed.events[0].to_mapping()["item"]["type"], "todo_list")
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")
        self.assertIsNone(processor.running_todo_list)

    def test_completed_turn_writes_last_agent_message_on_final_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "last-message.txt"
            processor = JsonEventProcessor(output_path)
            agent_item = TurnItem.agent_message(
                AgentMessageItem("msg-1", (AgentMessageContent.text_content("final answer"),))
            )

            collected = processor.collect_turn_completed(status="completed", items=(agent_item,))
            processor.print_final_output(stderr=io.StringIO())

            self.assertEqual(collected.status, CodexStatus.INITIATE_SHUTDOWN)
            self.assertEqual(collected.events[-1].to_mapping()["type"], "turn.completed")
            self.assertEqual(output_path.read_text(encoding="utf-8"), "final answer")

    def test_last_message_write_failure_warns_without_raising(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "missing" / "last-message.txt"
            stderr = io.StringIO()

            handle_last_message("final answer", output_path, stderr=stderr)

            self.assertIn("Failed to write last message file", stderr.getvalue())
            self.assertIn(json.dumps(str(output_path)), stderr.getvalue())
            self.assertNotIn("Path(", stderr.getvalue())

    def test_missing_last_message_write_failure_still_warns_about_empty_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "missing" / "last-message.txt"
            stderr = io.StringIO()

            handle_last_message(None, output_path, stderr=stderr)

            self.assertIn("Failed to write last message file", stderr.getvalue())
            self.assertIn("Warning: no last agent message; wrote empty content", stderr.getvalue())

    def test_warning_collects_error_item_and_json_lines_emit(self):
        processor = JsonEventProcessor()
        output = io.StringIO()

        collected = processor.collect_warning("config warning")
        processor.emit_json_lines(collected.events, output)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["type"], "item.completed")
        self.assertEqual(payload["item"]["type"], "error")
        self.assertEqual(payload["item"]["message"], "config warning")

    def test_warning_notifications_fall_back_to_legacy_message_field(self):
        json_processor = JsonEventProcessor()
        human_stderr = io.StringIO()

        collected = json_processor.collect_thread_events(
            {"method": "configWarning", "params": {"message": "legacy warning"}}
        )
        HumanEventProcessor().process_server_notification(
            {"method": "deprecationNotice", "params": {"message": "legacy deprecated"}},
            stderr=human_stderr,
        )

        self.assertEqual(collected.events[0].to_mapping()["item"]["message"], "legacy warning")
        self.assertEqual(human_stderr.getvalue(), "deprecated: legacy deprecated\n")

    def test_json_processor_ignores_guardian_auto_approval_review_notifications(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "item/autoApprovalReview/started",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "reviewId": "review-1",
                    "startedAtMs": 10,
                    "targetItemId": "cmd-1",
                    "review": {"status": "inProgress"},
                    "action": {"type": "command", "command": "pwd", "cwd": "C:/work"},
                },
            }
        )
        completed = processor.collect_thread_events(
            {
                "kind": "ItemGuardianApprovalReviewCompleted",
                "payload": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "reviewId": "review-1",
                    "startedAtMs": 10,
                    "completedAtMs": 12,
                    "targetItemId": "cmd-1",
                    "decisionSource": "agent",
                    "review": {"status": "denied"},
                    "action": {"type": "command", "command": "pwd", "cwd": "C:/work"},
                },
            }
        )

        self.assertEqual(started.status, CodexStatus.RUNNING)
        self.assertEqual(started.events, ())
        self.assertEqual(completed.status, CodexStatus.RUNNING)
        self.assertEqual(completed.events, ())

    def test_json_processor_command_execution_declined_status_matches_upstream_enum(self):
        processor = JsonEventProcessor()

        collected = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "id": "cmd-1",
                        "command": "rm -rf /",
                        "aggregatedOutput": None,
                        "exitCode": None,
                        "status": "declined",
                    }
                },
            }
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        item = collected.events[0].to_mapping()["item"]
        self.assertEqual(item["type"], "command_execution")
        self.assertEqual(item["command"], "rm -rf /")
        self.assertEqual(item["aggregated_output"], "")
        self.assertIsNone(item["exit_code"])
        self.assertEqual(item["status"], "declined")

    def test_json_processor_empty_reasoning_items_are_ignored(self):
        processor = JsonEventProcessor()
        reasoning = TurnItem.reasoning(ReasoningItem("reasoning-1", (), ("raw reasoning",)))

        collected = processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": reasoning.to_app_server_mapping()}}
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(collected.events, ())

    def test_json_processor_unsupported_completed_items_do_not_consume_synthetic_ids(self):
        processor = JsonEventProcessor()
        ignored = TurnItem.plan(PlanItem("plan-1", "ignored plan"))
        message = TurnItem.agent_message(AgentMessageItem("message-1", (AgentMessageContent.text_content("hello"),)))

        ignored_collected = processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": ignored.to_app_server_mapping()}}
        )
        message_collected = processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": message.to_app_server_mapping()}}
        )

        self.assertEqual(ignored_collected.status, CodexStatus.RUNNING)
        self.assertEqual(ignored_collected.events, ())
        self.assertEqual(message_collected.events[0].to_mapping()["item"]["id"], "item_0")
        self.assertEqual(message_collected.events[0].to_mapping()["item"]["text"], "hello")

    def test_json_processor_agent_message_item_updates_final_message(self):
        processor = JsonEventProcessor()
        message = TurnItem.agent_message(AgentMessageItem("msg-1", (AgentMessageContent.text_content("hello"),)))

        collected = processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": message.to_app_server_mapping()}}
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(
            collected.events[0].to_mapping()["item"],
            {"id": "item_0", "type": "agent_message", "text": "hello"},
        )
        self.assertEqual(processor.final_message, "hello")

    def test_json_processor_agent_message_item_started_is_ignored(self):
        processor = JsonEventProcessor()
        message = TurnItem.agent_message(AgentMessageItem("msg-1", (AgentMessageContent.text_content("hello"),)))

        collected = processor.collect_thread_events(
            {"method": "item/started", "params": {"item": message.to_app_server_mapping()}}
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(collected.events, ())
        self.assertIsNone(processor.final_message)

    def test_json_processor_reasoning_items_emit_summary_not_raw_content(self):
        processor = JsonEventProcessor()
        reasoning = TurnItem.reasoning(ReasoningItem("reasoning-1", ("safe summary",), ("raw reasoning",)))

        collected = processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": reasoning.to_app_server_mapping()}}
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        item = collected.events[0].to_mapping()["item"]
        self.assertEqual(item["id"], "item_0")
        self.assertEqual(item["type"], "reasoning")
        self.assertEqual(item["text"], "safe summary")
        self.assertNotIn("raw reasoning", json.dumps(item))

    def test_json_processor_reasoning_item_completed_uses_synthetic_id(self):
        processor = JsonEventProcessor()
        reasoning = TurnItem.reasoning(ReasoningItem("rs-1", ("thinking...",), ("raw",)))

        collected = processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": reasoning.to_app_server_mapping()}}
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(
            collected.events[0].to_mapping()["item"],
            {"id": "item_0", "type": "reasoning", "text": "thinking..."},
        )

    def test_json_processor_warning_event_produces_error_item(self):
        processor = JsonEventProcessor()
        message = (
            "Heads up: Long conversations and multiple compactions can cause the model "
            "to be less accurate. Start a new conversation when possible to keep "
            "conversations small and targeted."
        )

        collected = processor.collect_warning(message)

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(
            collected.events[0].to_mapping(),
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "error", "message": message},
            },
        )

    def test_json_processor_web_search_completion_preserves_query_and_search_action(self):
        processor = JsonEventProcessor()
        web_search = TurnItem.web_search(
            WebSearchItem(
                "search-1",
                "rust async await",
                WebSearchAction.search(query="rust async await"),
            )
        )

        collected = processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": web_search.to_app_server_mapping()}}
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        item = collected.events[0].to_mapping()["item"]
        self.assertEqual(item["id"], "item_0")
        self.assertEqual(item["type"], "web_search")
        self.assertEqual(item["query"], "rust async await")
        self.assertEqual(item["action"], {"type": "search", "query": "rust async await"})

    def test_exec_json_status_mappings_preserve_unknown_values(self):
        command = command_execution_item("item-1", command="tool", status="paused")
        mcp = TurnItem.mcp_tool_call(
            McpToolCallItem(
                id="mcp-1",
                server="server",
                tool="tool",
                arguments={},
                status=McpToolCallStatus.COMPLETED,
                result=CallToolResult(content=()),
            )
        )

        self.assertEqual(command.to_mapping()["status"], "paused")
        self.assertEqual(exec_item_from_turn_item(mcp, "item-2").to_mapping()["status"], "completed")
        raw_mcp = exec_item_from_app_server_item(
            {
                "type": "mcpToolCall",
                "server": "server",
                "tool": "tool",
                "arguments": {},
                "status": "paused",
            },
            lambda: "item-3",
        )
        self.assertEqual(raw_mcp.to_mapping()["status"], "paused")

    def test_exec_json_file_change_mappings_preserve_unknown_values(self):
        raw_file_change = exec_item_from_app_server_item(
            {
                "type": "fileChange",
                "changes": [{"path": "a.txt", "kind": {"type": "renameOnly"}}],
                "status": "paused",
            },
            lambda: "item-1",
        )
        declined_file_change = exec_item_from_app_server_item(
            {
                "type": "fileChange",
                "changes": [{"path": "b.txt", "kind": {"type": "delete"}}],
                "status": "declined",
            },
            lambda: "item-2",
        )

        self.assertEqual(
            raw_file_change.to_mapping(),
            {
                "id": "item-1",
                "type": "file_change",
                "changes": [{"path": "a.txt", "kind": "renameOnly"}],
                "status": "paused",
            },
        )
        self.assertEqual(declined_file_change.to_mapping()["status"], "failed")

    def test_json_processor_file_change_completion_maps_change_kinds(self):
        processor = JsonEventProcessor()

        collected = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "fileChange",
                        "id": "patch-1",
                        "changes": [
                            {"path": "a/added.txt", "kind": {"type": "add"}, "diff": ""},
                            {"path": "b/deleted.txt", "kind": {"type": "delete"}, "diff": ""},
                            {"path": "c/modified.txt", "kind": {"type": "update"}, "diff": "@@ -1 +1 @@"},
                        ],
                        "status": "completed",
                    }
                },
            }
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(
            collected.events[0].to_mapping()["item"],
            {
                "id": "item_0",
                "type": "file_change",
                "changes": [
                    {"path": "a/added.txt", "kind": "add"},
                    {"path": "b/deleted.txt", "kind": "delete"},
                    {"path": "c/modified.txt", "kind": "update"},
                ],
                "status": "completed",
            },
        )

    def test_json_processor_file_change_declined_maps_to_failed_status(self):
        processor = JsonEventProcessor()

        collected = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "fileChange",
                        "id": "patch-2",
                        "changes": [
                            {"path": "file.txt", "kind": {"type": "update"}, "diff": "@@ -1 +1 @@"}
                        ],
                        "status": "declined",
                    }
                },
            }
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(
            collected.events[0].to_mapping()["item"],
            {
                "id": "item_0",
                "type": "file_change",
                "changes": [{"path": "file.txt", "kind": "update"}],
                "status": "failed",
            },
        )

    def test_exec_json_web_search_action_matches_rust_deserialization_boundary(self):
        typed = web_search_item(
            "item-1",
            WebSearchItem("search-1", "docs", WebSearchAction.open_page("https://example.com")),
        )
        raw_app_server = exec_item_from_app_server_item(
            {
                "type": "webSearch",
                "id": "search-2",
                "query": "docs",
                "action": {"type": "openPage", "url": "https://example.com"},
            },
            lambda: "item-2",
        )

        self.assertEqual(
            typed.to_mapping()["action"],
            {"type": "open_page", "url": "https://example.com"},
        )
        self.assertEqual(raw_app_server.to_mapping()["action"], {"type": "other"})

    def test_json_processor_web_search_notifications_keep_raw_app_server_action_boundary(self):
        processor = JsonEventProcessor()
        started = processor.collect_thread_events(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "webSearch",
                        "id": "search-1",
                        "query": "docs",
                        "action": {"type": "openPage", "url": "https://example.com"},
                    }
                },
            }
        )
        completed = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "webSearch",
                        "id": "search-1",
                        "query": "docs",
                        "action": {"type": "openPage", "url": "https://example.com"},
                    }
                },
            }
        )

        self.assertEqual(started.events[0].to_mapping()["item"]["action"], {"type": "other"})
        self.assertEqual(completed.events[0].to_mapping()["item"]["id"], "item_0")
        self.assertEqual(completed.events[0].to_mapping()["item"]["action"], {"type": "other"})

    def test_json_processor_web_search_start_and_completion_reuse_item_id(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "webSearch",
                        "id": "search-1",
                        "query": "",
                        "action": None,
                    }
                },
            }
        )
        completed = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "webSearch",
                        "id": "search-1",
                        "query": "rust async await",
                        "action": {
                            "type": "search",
                            "query": "rust async await",
                            "queries": None,
                        },
                    }
                },
            }
        )

        started_item = started.events[0].to_mapping()["item"]
        completed_item = completed.events[0].to_mapping()["item"]
        self.assertEqual(started.status, CodexStatus.RUNNING)
        self.assertEqual(completed.status, CodexStatus.RUNNING)
        self.assertEqual(started_item["id"], "item_0")
        self.assertEqual(started_item["query"], "")
        self.assertEqual(started_item["action"], {"type": "other"})
        self.assertEqual(completed_item["id"], "item_0")
        self.assertEqual(completed_item["query"], "rust async await")
        self.assertEqual(completed_item["action"], {"type": "search", "query": "rust async await"})

    def test_json_processor_maps_typed_command_execution_turn_item(self):
        processor = JsonEventProcessor()
        turn_item = TurnItem.command_execution(
            CommandExecutionItem(
                id="cmd-1",
                command="python -m unittest",
                cwd=Path("C:/work"),
                process_id=None,
                source="userShell",
                status="completed",
                command_actions=(),
                aggregated_output="OK",
                exit_code=0,
                duration_ms=12,
            )
        )

        collected = processor.collect_item_completed(turn_item)

        item = collected.events[0].to_mapping()["item"]
        self.assertEqual(item["type"], "command_execution")
        self.assertEqual(item["command"], "python -m unittest")
        self.assertEqual(item["aggregated_output"], "OK")
        self.assertEqual(item["exit_code"], 0)
        self.assertEqual(item["status"], "completed")

    def test_human_completed_lines_render_typed_command_execution_item(self):
        turn_item = TurnItem.command_execution(
            CommandExecutionItem(
                id="cmd-1",
                command="python -m unittest",
                cwd=Path("C:/work"),
                status="failed",
                aggregated_output="FAILED",
                exit_code=1,
            )
        )

        self.assertEqual(
            human_item_completed_lines(turn_item),
            ("exec: failed (exit 1)", "FAILED"),
        )

    def test_json_processor_dispatches_app_server_notifications(self):
        processor = JsonEventProcessor()
        output = io.StringIO()

        status = processor.process_server_notification(
            {"method": "configWarning", "params": {"summary": "bad config", "details": "ignored key"}},
            output=output,
        )
        processor.process_server_notification({"method": "turn/started", "params": {"turn": {"id": "turn-1"}}}, output=output)
        processor.process_server_notification(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "id": "cmd-1",
                        "command": "python -m unittest",
                        "aggregatedOutput": None,
                        "exitCode": None,
                        "status": "inProgress",
                    }
                },
            },
            output=output,
        )
        processor.process_server_notification(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "id": "cmd-1",
                        "command": "python -m unittest",
                        "aggregatedOutput": "OK",
                        "exitCode": 0,
                        "status": "completed",
                    }
                },
            },
            output=output,
        )
        processor.process_server_notification(
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "tokenUsage": {
                        "total": {
                            "inputTokens": 11,
                            "cachedInputTokens": 3,
                            "outputTokens": 5,
                            "reasoningOutputTokens": 2,
                        }
                    }
                },
            },
            output=output,
        )
        completed = processor.process_server_notification(
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                    }
                },
            },
            output=output,
        )

        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(status, CodexStatus.RUNNING)
        self.assertEqual(completed, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(events[0]["item"], {"id": "item_0", "type": "error", "message": "bad config (ignored key)"})
        self.assertEqual(events[1], {"type": "turn.started"})
        self.assertEqual(events[2]["item"]["id"], "item_1")
        self.assertEqual(events[2]["item"]["type"], "command_execution")
        self.assertEqual(events[3]["item"]["id"], "item_1")
        self.assertEqual(events[3]["item"]["aggregated_output"], "OK")
        self.assertEqual(events[-1]["type"], "turn.completed")
        self.assertEqual(events[-1]["usage"]["input_tokens"], 11)
        self.assertEqual(processor.final_message, "done")

    def test_json_processor_token_usage_update_is_emitted_on_turn_completion(self):
        processor = JsonEventProcessor()

        usage_update = processor.collect_thread_events(
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "tokenUsage": {
                        "total": {
                            "totalTokens": 42,
                            "inputTokens": 10,
                            "cachedInputTokens": 3,
                            "outputTokens": 29,
                            "reasoningOutputTokens": 7,
                        },
                        "last": {
                            "totalTokens": 42,
                            "inputTokens": 10,
                            "cachedInputTokens": 3,
                            "outputTokens": 29,
                            "reasoningOutputTokens": 7,
                        },
                        "modelContextWindow": 128000,
                    }
                },
            }
        )
        completed = processor.collect_thread_events(
            {"method": "turn/completed", "params": {"turn": {"status": "completed", "items": []}}}
        )

        self.assertEqual(usage_update.status, CodexStatus.RUNNING)
        self.assertEqual(usage_update.events, ())
        self.assertEqual(completed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(
            completed.events[-1].to_mapping(),
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 3,
                    "output_tokens": 29,
                    "reasoning_output_tokens": 7,
                },
            },
        )

    def test_json_processor_tracks_plan_todo_lifecycle(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "turn/plan/updated",
                "params": {
                    "plan": [
                        {"step": "inspect", "status": "completed"},
                        {"step": "patch", "status": "inProgress"},
                    ]
                },
            }
        )
        updated = processor.collect_thread_events(
            {
                "method": "turn/plan/updated",
                "params": {"plan": [{"step": "patch", "status": "completed"}]},
            }
        )
        completed = processor.collect_thread_events(
            {"method": "turn/completed", "params": {"turn": {"status": "completed", "items": []}}}
        )

        self.assertEqual(started.events[0].to_mapping()["type"], "item.started")
        self.assertEqual(started.events[0].to_mapping()["item"]["type"], "todo_list")
        self.assertEqual(started.events[0].to_mapping()["item"]["items"][0], {"text": "inspect", "completed": True})
        self.assertEqual(updated.events[0].to_mapping()["type"], "item.updated")
        self.assertEqual(updated.events[0].to_mapping()["item"]["id"], started.events[0].to_mapping()["item"]["id"])
        self.assertEqual(completed.events[0].to_mapping()["type"], "item.completed")
        self.assertEqual(completed.events[0].to_mapping()["item"]["type"], "todo_list")
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")

    def test_json_processor_plan_update_emits_started_then_updated_then_completed(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "turn/plan/updated",
                "params": {
                    "plan": [
                        {"step": "step one", "status": "pending"},
                        {"step": "step two", "status": "inProgress"},
                    ]
                },
            }
        )
        updated = processor.collect_thread_events(
            {
                "method": "turn/plan/updated",
                "params": {
                    "plan": [
                        {"step": "step one", "status": "completed"},
                        {"step": "step two", "status": "inProgress"},
                    ]
                },
            }
        )
        completed = processor.collect_thread_events(
            {"method": "turn/completed", "params": {"turn": {"status": "completed", "items": []}}}
        )

        self.assertEqual(
            started.events[0].to_mapping(),
            {
                "type": "item.started",
                "item": {
                    "id": "item_0",
                    "type": "todo_list",
                    "items": [
                        {"text": "step one", "completed": False},
                        {"text": "step two", "completed": False},
                    ],
                },
            },
        )
        self.assertEqual(
            updated.events[0].to_mapping(),
            {
                "type": "item.updated",
                "item": {
                    "id": "item_0",
                    "type": "todo_list",
                    "items": [
                        {"text": "step one", "completed": True},
                        {"text": "step two", "completed": False},
                    ],
                },
            },
        )
        self.assertEqual(completed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(
            completed.events[0].to_mapping(),
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "todo_list",
                    "items": [
                        {"text": "step one", "completed": True},
                        {"text": "step two", "completed": False},
                    ],
                },
            },
        )
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")

    def test_json_processor_plan_update_after_completion_starts_new_todo_list_with_new_id(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "turn/plan/updated",
                "params": {"plan": [{"step": "inspect", "status": "inProgress"}]},
            }
        )
        completed = processor.collect_thread_events(
            {"method": "turn/completed", "params": {"turn": {"status": "completed", "items": []}}}
        )
        restarted = processor.collect_thread_events(
            {
                "method": "turn/plan/updated",
                "params": {"plan": [{"step": "continue", "status": "inProgress"}]},
            }
        )

        self.assertEqual(started.events[0].to_mapping()["item"]["id"], "item_0")
        self.assertEqual(completed.events[0].to_mapping()["item"]["id"], "item_0")
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")
        self.assertEqual(restarted.events[0].to_mapping()["type"], "item.started")
        self.assertEqual(restarted.events[0].to_mapping()["item"]["id"], "item_1")

    def test_json_processor_turn_completion_reconciles_started_items_from_turn_items(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "id": "cmd-1",
                        "command": "ls",
                        "cwd": "/tmp/project",
                        "status": "inProgress",
                        "aggregatedOutput": None,
                        "exitCode": None,
                    }
                },
            }
        )
        completed = processor.collect_thread_events(
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "status": "completed",
                        "items": [
                            {
                                "type": "commandExecution",
                                "id": "cmd-1",
                                "command": "ls",
                                "cwd": "/tmp/project",
                                "status": "completed",
                                "aggregatedOutput": "a.txt\n",
                                "exitCode": 0,
                            }
                        ],
                    }
                },
            }
        )

        self.assertEqual(started.events[0].to_mapping()["item"]["id"], "item_0")
        self.assertEqual(started.events[0].to_mapping()["item"]["status"], "in_progress")
        self.assertEqual(completed.events[0].to_mapping()["type"], "item.completed")
        self.assertEqual(completed.events[0].to_mapping()["item"]["id"], "item_0")
        self.assertEqual(completed.events[0].to_mapping()["item"]["status"], "completed")
        self.assertEqual(completed.events[0].to_mapping()["item"]["aggregated_output"], "a.txt\n")
        self.assertEqual(completed.events[0].to_mapping()["item"]["exit_code"], 0)
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")

    def test_human_processor_dispatches_notifications_and_failed_turns(self):
        processor = HumanEventProcessor()
        stderr = io.StringIO()

        self.assertEqual(
            processor.process_server_notification(
                {"method": "deprecationNotice", "params": {"summary": "old flag", "details": "use new flag"}},
                stderr=stderr,
            ),
            CodexStatus.RUNNING,
        )
        processor.process_server_notification(
            {"method": "model/rerouted", "params": {"fromModel": "gpt-a", "toModel": "gpt-b"}},
            stderr=stderr,
        )
        processor.process_server_notification(
            {"method": "turn/diff/updated", "params": {"diff": "diff --git a/a b/a"}},
            stderr=stderr,
        )
        status = processor.process_server_notification(
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "status": "failed",
                        "error": {"message": "boom", "additionalDetails": "retry later"},
                        "items": [],
                    }
                },
            },
            stderr=stderr,
        )

        self.assertEqual(status, CodexStatus.INITIATE_SHUTDOWN)
        output = stderr.getvalue()
        self.assertIn("deprecated: old flag\nuse new flag\n", output)
        self.assertIn("model rerouted: gpt-a -> gpt-b\n", output)
        self.assertIn("diff --git a/a b/a\n", output)
        self.assertIn("ERROR: boom (retry later)\n", output)

    def test_json_processor_model_reroute_reason_matches_upstream_debug_name(self):
        processor = JsonEventProcessor()

        collected = processor.collect_thread_events(
            {
                "method": "model/rerouted",
                "params": {
                    "fromModel": "gpt-5",
                    "toModel": "gpt-5-mini",
                    "reason": "highRiskCyberActivity",
                },
            }
        )

        self.assertEqual(collected.status, CodexStatus.RUNNING)
        self.assertEqual(
            collected.events[0].to_mapping(),
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "error",
                    "message": "model rerouted: gpt-5 -> gpt-5-mini (HighRiskCyberActivity)",
                },
            },
        )

    def test_human_item_started_lines_match_plain_upstream_labels(self):
        self.assertEqual(
            human_item_started_lines(
                {"type": "commandExecution", "id": "cmd-1", "command": "echo hi", "cwd": "C:/work"}
            ),
            ("exec", "echo hi in C:/work"),
        )
        self.assertEqual(
            human_item_started_lines({"type": "mcpToolCall", "server": "srv", "tool": "lookup"}),
            ("mcp: srv/lookup started",),
        )
        self.assertEqual(human_item_started_lines({"type": "webSearch", "query": "codex"}), ("web search: codex",))
        self.assertEqual(human_item_started_lines({"type": "fileChange"}), ("apply patch",))
        self.assertEqual(
            human_item_started_lines({"type": "collabAgentToolCall", "tool": "spawnAgent"}),
            ("collab: SpawnAgent",),
        )
        self.assertEqual(
            human_item_started_lines(
                TurnItem.command_execution(
                    CommandExecutionItem("cmd-typed", "pwd", "C:/work", "inProgress")
                )
            ),
            ("exec", "pwd in C:/work"),
        )

    def test_human_item_completed_lines_render_core_item_types(self):
        self.assertEqual(
            human_item_completed_lines(
                {
                    "type": "commandExecution",
                    "status": "failed",
                    "exitCode": 2,
                    "durationMs": 7,
                    "aggregatedOutput": "stderr text",
                }
            ),
            (" exited 2 in 7ms:", "stderr text"),
        )
        self.assertEqual(
            human_item_completed_lines(
                {
                    "type": "fileChange",
                    "status": "declined",
                    "changes": [{"path": "src/app.py", "kind": {"type": "add"}, "diff": "after"}],
                }
            ),
            ("patch: declined", "src/app.py"),
        )
        self.assertEqual(
            human_item_completed_lines(
                {"type": "mcpToolCall", "server": "srv", "tool": "lookup", "status": "failed", "error": {"message": "bad"}}
            ),
            ("mcp: srv/lookup (failed)", "bad"),
        )
        self.assertEqual(human_item_completed_lines({"type": "webSearch", "query": "codex"}), ("web search: codex",))
        self.assertEqual(human_item_completed_lines({"type": "contextCompaction", "id": "compact-1"}), ("context compacted",))

    def test_human_item_completed_lines_render_reasoning_items(self):
        item = TurnItem.reasoning(ReasoningItem("reason-1", ("summary",), ("raw",)))

        self.assertEqual(human_item_completed_lines(item), ("summary",))
        self.assertEqual(human_item_completed_lines(item, show_raw_agent_reasoning=True), ("raw",))
        self.assertEqual(
            human_item_completed_lines(
                TurnItem.reasoning(ReasoningItem("reason-2", ("summary",), ())),
                show_raw_agent_reasoning=True,
            ),
            ("summary",),
        )
        self.assertEqual(human_item_completed_lines(item, show_agent_reasoning=False), ())

    def test_human_item_completed_lines_uses_turn_item_app_server_mapping(self):
        item = TurnItem.file_change(
            FileChangeItem("patch-1", {Path("a.txt"): FileChange.add("after")}, status=PatchApplyStatus.COMPLETED)
        )
        mcp_item = TurnItem.mcp_tool_call(
            McpToolCallItem(
                "mcp-1",
                "server",
                "lookup",
                {},
                McpToolCallStatus.COMPLETED,
                duration={"secs": 0, "nanos": 1_000_000},
            )
        )

        self.assertEqual(human_item_completed_lines(item), ("patch: completed", "a.txt"))
        self.assertEqual(human_item_completed_lines(mcp_item), ("mcp: server/lookup (completed)",))
        self.assertEqual(
            exec_item_from_app_server_item(item.to_app_server_mapping(), lambda: "item-1").to_mapping(),
            {
                "id": "item-1",
                "type": "file_change",
                "changes": [{"path": "a.txt", "kind": "add"}],
                "status": "completed",
            },
        )

    def test_human_processor_renders_item_notifications(self):
        processor = HumanEventProcessor()
        stderr = io.StringIO()

        processor.process_server_notification(
            {
                "method": "item/started",
                "params": {"item": {"type": "commandExecution", "command": "pwd", "cwd": "C:/work"}},
            },
            stderr=stderr,
        )
        processor.process_server_notification(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "command": "pwd",
                        "cwd": "C:/work",
                        "status": "completed",
                        "durationMs": 3,
                        "aggregatedOutput": "C:/work",
                    }
                },
            },
            stderr=stderr,
        )

        self.assertEqual(stderr.getvalue(), "exec\npwd in C:/work\n succeeded in 3ms:\nC:/work\n")

    def test_human_processor_renders_typed_started_and_completed_items(self):
        processor = HumanEventProcessor()
        stderr = io.StringIO()
        command = TurnItem.command_execution(
            CommandExecutionItem(
                "cmd-1",
                "pwd",
                "C:/work",
                "completed",
                aggregated_output="C:/work",
                exit_code=0,
                duration_ms=3,
            )
        )

        self.assertEqual(processor.collect_item_started(command, stderr=stderr), CodexStatus.RUNNING)
        self.assertEqual(processor.collect_item_completed(command, stderr=stderr), CodexStatus.RUNNING)

        self.assertEqual(stderr.getvalue(), "exec\npwd in C:/work\n succeeded in 3ms:\nC:/work\n")

    def test_notification_helpers_parse_aliases_usage_plan_and_app_server_items(self):
        self.assertEqual(notification_method({"method": "TurnCompleted"}), "turn/completed")
        self.assertEqual(
            map_todo_items([{"step": "ship", "status": "completed"}, {"step": "wait", "status": "pending"}]),
            (("ship", True), ("wait", False)),
        )
        self.assertEqual(
            usage_from_notification(
                {
                    "tokenUsage": {
                        "total": {
                            "inputTokens": 20,
                            "cachedInputTokens": 5,
                            "outputTokens": 7,
                            "reasoningOutputTokens": 3,
                        }
                    }
                }
            ),
            Usage(input_tokens=20, cached_input_tokens=5, output_tokens=7, reasoning_output_tokens=3),
        )
        item = exec_item_from_app_server_item(
            {
                "type": "mcpToolCall",
                "id": "mcp-1",
                "server": "srv",
                "tool": "lookup",
                "arguments": {"q": "codex"},
                "result": {"content": [], "structuredContent": {"ok": True}, "_meta": {"raw": 1}},
                "status": "completed",
            },
            lambda: "item-1",
        )
        self.assertEqual(
            item.to_mapping(),
            {
                "id": "item-1",
                "type": "mcp_tool_call",
                "server": "srv",
                "tool": "lookup",
                "arguments": {"q": "codex"},
                "result": {"content": [], "structured_content": {"ok": True}, "_meta": {"raw": 1}},
                "status": "completed",
            },
        )
        minimal_item = exec_item_from_app_server_item(
            {
                "type": "mcpToolCall",
                "id": "mcp-2",
                "server": "srv",
                "tool": "lookup",
                "arguments": {},
                "result": {"content": []},
                "status": "completed",
            },
            lambda: "item-2",
        )
        self.assertEqual(minimal_item.to_mapping()["result"], {"content": [], "structured_content": None})
        self.assertEqual(
            human_notification_lines(
                {
                    "method": "turn/plan/updated",
                    "params": {"explanation": "plan", "plan": [{"step": "ship", "status": "inProgress"}]},
                }
            ),
            ("plan", "  [>] ship"),
        )

    def test_collab_tool_call_item_matches_exec_json_shape(self):
        item = collab_tool_call_item(
            "item-1",
            tool="resumeAgent",
            sender_thread_id="thread-main",
            receiver_thread_ids=("thread-worker",),
            prompt="continue",
            agents_states={"thread-worker": {"status": "pendingInit", "message": "starting"}},
            status="inProgress",
        )

        self.assertEqual(
            item.to_mapping(),
            {
                "id": "item-1",
                "type": "collab_tool_call",
                "tool": "wait",
                "sender_thread_id": "thread-main",
                "receiver_thread_ids": ["thread-worker"],
                "prompt": "continue",
                "agents_states": {"thread-worker": {"status": "pending_init", "message": "starting"}},
                "status": "in_progress",
            },
        )
        self.assertEqual(CollabTool.SPAWN_AGENT.value, "spawn_agent")
        self.assertEqual(CollabToolCallStatus.COMPLETED.value, "completed")
        self.assertEqual(CollabAgentStatus.NOT_FOUND.value, "not_found")
        self.assertEqual(
            collab_tool_call_item(
                "item-2",
                tool="unknownTool",
                sender_thread_id="thread-main",
                receiver_thread_ids=(),
            ).to_mapping()["tool"],
            "unknownTool",
        )
        self.assertEqual(
            collab_tool_call_item(
                "item-3",
                tool="wait",
                sender_thread_id="thread-main",
                receiver_thread_ids=(),
                status="paused",
            ).to_mapping()["status"],
            "paused",
        )

    def test_app_server_collab_tool_notifications_reuse_item_id(self):
        processor = JsonEventProcessor()
        output = io.StringIO()
        started = {
            "method": "item/started",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "collab-1",
                    "tool": "spawnAgent",
                    "senderThreadId": "thread-main",
                    "receiverThreadIds": ["thread-worker"],
                    "prompt": "help",
                    "agentsStates": {"thread-worker": {"status": "running", "message": "booted"}},
                    "status": "inProgress",
                }
            },
        }
        completed = {
            "method": "item/completed",
            "params": {
                "item": {
                    **started["params"]["item"],
                    "agentsStates": {"thread-worker": {"status": "completed", "message": "done"}},
                    "status": "completed",
                }
            },
        }

        processor.process_server_notification(started, output=output)
        processor.process_server_notification(completed, output=output)

        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[0]["type"], "item.started")
        self.assertEqual(events[0]["item"]["id"], "item_0")
        self.assertEqual(events[0]["item"]["type"], "collab_tool_call")
        self.assertEqual(events[0]["item"]["tool"], "spawn_agent")
        self.assertEqual(events[1]["type"], "item.completed")
        self.assertEqual(events[1]["item"]["id"], "item_0")
        self.assertEqual(events[1]["item"]["status"], "completed")
        self.assertEqual(events[1]["item"]["agents_states"]["thread-worker"]["status"], "completed")

    def test_json_processor_collab_spawn_begin_and_end_emit_item_events(self):
        processor = JsonEventProcessor()

        started = processor.collect_thread_events(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "collabAgentToolCall",
                        "id": "collab-1",
                        "tool": "spawnAgent",
                        "senderThreadId": "thread-parent",
                        "receiverThreadIds": [],
                        "prompt": "draft a plan",
                        "agentsStates": {},
                        "status": "inProgress",
                    }
                },
            }
        )
        completed = processor.collect_thread_events(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "collabAgentToolCall",
                        "id": "collab-1",
                        "tool": "spawnAgent",
                        "senderThreadId": "thread-parent",
                        "receiverThreadIds": ["thread-child"],
                        "prompt": "draft a plan",
                        "agentsStates": {"thread-child": {"status": "running", "message": None}},
                        "status": "completed",
                    }
                },
            }
        )

        self.assertEqual(started.status, CodexStatus.RUNNING)
        self.assertEqual(completed.status, CodexStatus.RUNNING)
        self.assertEqual(
            started.events[0].to_mapping()["item"],
            {
                "id": "item_0",
                "type": "collab_tool_call",
                "tool": "spawn_agent",
                "sender_thread_id": "thread-parent",
                "receiver_thread_ids": [],
                "prompt": "draft a plan",
                "agents_states": {},
                "status": "in_progress",
            },
        )
        self.assertEqual(
            completed.events[0].to_mapping()["item"],
            {
                "id": "item_0",
                "type": "collab_tool_call",
                "tool": "spawn_agent",
                "sender_thread_id": "thread-parent",
                "receiver_thread_ids": ["thread-child"],
                "prompt": "draft a plan",
                "agents_states": {"thread-child": {"status": "running", "message": None}},
                "status": "completed",
            },
        )

    def test_json_processor_unsupported_started_turn_items_do_not_consume_item_ids(self):
        processor = JsonEventProcessor()
        dynamic = TurnItem.dynamic_tool_call(
            DynamicToolCallItem("dyn-1", None, "tool", {}, DynamicToolCallStatus.IN_PROGRESS)
        )
        command = TurnItem.command_execution(
            CommandExecutionItem("cmd-1", "pwd", "C:/work", "inProgress")
        )

        ignored = processor.collect_item_started(dynamic)
        started = processor.collect_item_started(command)

        self.assertEqual(ignored.events, ())
        self.assertEqual(started.events[0].to_mapping()["item"]["id"], "item_0")

    def test_exec_item_from_app_server_item_does_not_allocate_id_for_unsupported_turn_items(self):
        allocated: list[str] = []

        dynamic_item = exec_item_from_app_server_item(
            {
                "type": "dynamicToolCall",
                "id": "dyn-1",
                "namespace": None,
                "tool": "tool",
                "arguments": {},
                "status": "inProgress",
                "contentItems": None,
                "success": None,
                "durationMs": None,
            },
            lambda: allocated.append("item-1") or "item-1",
        )
        reasoning_item = exec_item_from_app_server_item(
            {
                "type": "reasoning",
                "id": "reason-1",
                "summary": [],
                "content": [],
            },
            lambda: allocated.append("item-2") or "item-2",
        )

        self.assertIsNone(dynamic_item)
        self.assertIsNone(reasoning_item)
        self.assertEqual(allocated, [])

    def test_app_server_collab_tool_item_keeps_raw_exec_json_boundary_after_protocol_bridge(self):
        item = exec_item_from_app_server_item(
            {
                "type": "collabAgentToolCall",
                "id": "collab-1",
                "tool": "spawnAgent",
                "senderThreadId": "thread-main",
                "receiverThreadIds": ["thread-worker"],
                "prompt": "help",
                "agentsStates": {"thread-worker": {"status": "running", "message": None}},
                "status": "inProgress",
            },
            lambda: "item-1",
        )

        self.assertEqual(item.type, "collab_tool_call")
        self.assertEqual(item.payload["tool"], "spawn_agent")
        self.assertEqual(item.payload["sender_thread_id"], "thread-main")
        self.assertEqual(item.payload["agents_states"]["thread-worker"]["status"], "running")

    def test_exec_json_maps_typed_collab_agent_tool_call_turn_item(self):
        turn_item = TurnItem.collab_agent_tool_call(
            CollabAgentToolCallItem(
                "collab-1",
                ProtocolCollabAgentTool.RESUME_AGENT,
                ProtocolCollabAgentToolCallStatus.COMPLETED,
                "thread-main",
                ("thread-worker",),
                prompt="continue",
                agents_states={"thread-worker": ProtocolCollabAgentState(ProtocolCollabAgentStatus.COMPLETED, "done")},
            )
        )

        item = exec_item_from_turn_item(turn_item, "item-1")

        self.assertEqual(item.type, "collab_tool_call")
        self.assertEqual(item.payload["tool"], "wait")
        self.assertEqual(item.payload["sender_thread_id"], "thread-main")
        self.assertEqual(item.payload["receiver_thread_ids"], ["thread-worker"])
        self.assertEqual(item.payload["agents_states"]["thread-worker"]["status"], "completed")

    def test_config_summary_entries_match_upstream_order_and_sandbox_summary(self):
        cwd = Path("C:/work/project")
        cache_root = Path("C:/cache")
        config = ExecSessionConfig(
            model="ignored",
            model_provider_id="ignored",
            cwd=cwd,
            workspace_roots=(cwd, cache_root),
            permission_profile=PermissionProfile.workspace_write((cwd,)),
            reasoning_effort="high",
        )
        session = {
            "session_id": "session-1",
            "thread_id": "thread-1",
            "model": "gpt-5.5",
            "model_provider_id": "openai",
            "approval_policy": "never",
            "permission_profile": config.permission_profile,
            "cwd": cwd,
        }

        entries = config_summary_entries(config, session)

        self.assertEqual([key for key, _ in entries], [
            "workdir",
            "model",
            "provider",
            "approval",
            "sandbox",
            "reasoning effort",
            "reasoning summaries",
            "session id",
        ])
        self.assertEqual(dict(entries)["workdir"], str(cwd))
        self.assertEqual(dict(entries)["model"], "gpt-5.5")
        self.assertEqual(dict(entries)["provider"], "openai")
        self.assertEqual(dict(entries)["approval"], "never")
        self.assertEqual(dict(entries)["sandbox"], f"workspace-write [workdir, /tmp, $TMPDIR, {cache_root}]")
        self.assertEqual(dict(entries)["reasoning effort"], "high")
        self.assertEqual(dict(entries)["reasoning summaries"], "none")
        self.assertEqual(dict(entries)["session id"], "session-1")

    def test_config_summary_lines_match_human_output_shape(self):
        config = {
            "cwd": "C:/work/project",
            "permission_profile": PermissionProfile.disabled(),
            "approval_policy": "never",
            "wire_api": "chat",
        }
        session = {
            "session_id": "session-1",
            "thread_id": "thread-1",
            "model": "gpt-5.5",
            "model_provider_id": "openai",
            "cwd": "C:/work/project",
        }

        lines = config_summary_lines(config, "hello", session, version="9.9.9")

        self.assertEqual(
            lines,
            (
                "OpenAI Codex v9.9.9",
                "--------",
                f"workdir: {Path('C:/work/project')}",
                "model: gpt-5.5",
                "provider: openai",
                "approval: never",
                "sandbox: danger-full-access",
                "session id: session-1",
                "--------",
                "user",
                "hello",
            ),
        )

    def test_human_and_json_processors_print_config_summary(self):
        config = {
            "cwd": "C:/work/project",
            "permission_profile": PermissionProfile.read_only(),
            "approval_policy": "never",
            "wire_api": "chat",
        }
        session = {
            "session_id": "session-1",
            "thread_id": "thread-1",
            "model": "gpt-5.5",
            "model_provider_id": "openai",
            "cwd": "C:/work/project",
        }
        human_stderr = io.StringIO()
        json_stdout = io.StringIO()

        HumanEventProcessor().print_config_summary(config, "hi", session, stderr=human_stderr, version="1.2.3")
        JsonEventProcessor().print_config_summary(config, "hi", session, output=json_stdout)

        self.assertIn("OpenAI Codex v1.2.3\n--------\n", human_stderr.getvalue())
        self.assertIn("sandbox: read-only\n", human_stderr.getvalue())
        self.assertEqual(json.loads(json_stdout.getvalue()), {"type": "thread.started", "thread_id": "thread-1"})

    def test_notification_method_accepts_rust_variant_kind_aliases(self):
        self.assertEqual(notification_method({"kind": "TurnCompleted"}), "turn/completed")
        self.assertEqual(notification_method({"kind": "turn_plan_updated"}), "turn/plan/updated")

    def test_notification_method_accepts_more_upstream_server_notification_variants(self):
        self.assertEqual(notification_method({"kind": "ThreadStarted"}), "thread/started")
        self.assertEqual(notification_method({"kind": "thread_goal_updated"}), "thread/goal/updated")
        self.assertEqual(notification_method({"kind": "ThreadUnarchived"}), "thread/unarchived")
        self.assertEqual(
            notification_method({"kind": "ItemGuardianApprovalReviewStarted"}),
            "item/autoApprovalReview/started",
        )
        self.assertEqual(
            notification_method({"kind": "ItemGuardianApprovalReviewCompleted"}),
            "item/autoApprovalReview/completed",
        )
        self.assertEqual(notification_method({"kind": "RawResponseItemCompleted"}), "rawResponseItem/completed")
        self.assertEqual(notification_method({"kind": "AgentMessageDelta"}), "item/agentMessage/delta")
        self.assertEqual(notification_method({"kind": "command_exec_output_delta"}), "command/exec/outputDelta")
        self.assertEqual(notification_method({"kind": "McpServerStatusUpdated"}), "mcpServer/startupStatus/updated")
        self.assertEqual(notification_method({"kind": "ReasoningSummaryTextDelta"}), "item/reasoning/summaryTextDelta")
        self.assertEqual(notification_method({"kind": "ThreadRealtimeTranscriptDone"}), "thread/realtime/transcript/done")
        self.assertEqual(notification_method({"kind": "WindowsSandboxSetupCompleted"}), "windowsSandbox/setupCompleted")

    def test_notification_params_follows_upstream_method_params_shape(self):
        params = {"turn": {"status": "completed"}}

        self.assertIs(notification_params({"method": "turn/completed", "params": params}), params)

    def test_sandbox_summary_and_number_format_helpers(self):
        self.assertEqual(summarize_permission_profile(PermissionProfile.read_only(), "C:/work", ()), "read-only")
        self.assertEqual(summarize_permission_profile(PermissionProfile.disabled(), "C:/work", ()), "danger-full-access")
        self.assertEqual(format_with_separators(1234567), "1,234,567")

    def test_final_message_from_turn_items_falls_back_to_plan_text(self):
        self.assertEqual(final_message_from_turn_items((TurnItem.plan(PlanItem("plan-1", "ship it")),)), "ship it")

    def test_final_message_from_turn_items_prefers_latest_agent_message(self):
        first = TurnItem.agent_message(AgentMessageItem("msg-1", (AgentMessageContent.text_content("first"),)))
        plan = TurnItem.plan(PlanItem("plan-1", "plan"))
        second = TurnItem.agent_message(AgentMessageItem("msg-2", (AgentMessageContent.text_content("second"),)))

        self.assertEqual(final_message_from_turn_items((first, plan, second)), "second")

    def test_json_processor_turn_completion_recovers_final_message_from_turn_items(self):
        processor = JsonEventProcessor()
        final = TurnItem.agent_message(AgentMessageItem("msg-1", (AgentMessageContent.text_content("final answer"),)))

        completed = processor.collect_thread_events(
            {
                "method": "turn/completed",
                "params": {"turn": {"status": "completed", "items": [final.to_app_server_mapping()]}},
            }
        )

        self.assertEqual(completed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(
            completed.events[-1].to_mapping(),
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_output_tokens": 0,
                },
            },
        )
        self.assertEqual(processor.final_message, "final answer")

    def test_json_processor_turn_completion_overwrites_stale_final_message_from_turn_items(self):
        processor = JsonEventProcessor()
        stale = TurnItem.agent_message(AgentMessageItem("msg-stale", (AgentMessageContent.text_content("stale answer"),)))
        final = TurnItem.agent_message(AgentMessageItem("msg-1", (AgentMessageContent.text_content("final answer"),)))

        processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": stale.to_app_server_mapping()}}
        )
        completed = processor.collect_thread_events(
            {
                "method": "turn/completed",
                "params": {"turn": {"status": "completed", "items": [final.to_app_server_mapping()]}},
            }
        )

        self.assertEqual(completed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")
        self.assertEqual(processor.final_message, "final answer")

    def test_json_processor_turn_completion_preserves_streamed_final_message_when_turn_items_are_empty(self):
        processor = JsonEventProcessor()
        streamed = TurnItem.agent_message(
            AgentMessageItem("msg-streamed", (AgentMessageContent.text_content("streamed answer"),))
        )

        processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": streamed.to_app_server_mapping()}}
        )
        completed = processor.collect_thread_events(
            {"method": "turn/completed", "params": {"turn": {"status": "completed", "items": []}}}
        )

        self.assertEqual(completed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")
        self.assertEqual(processor.final_message, "streamed answer")

    def test_json_processor_failed_turn_clears_stale_final_message(self):
        processor = JsonEventProcessor()
        partial = TurnItem.agent_message(
            AgentMessageItem("msg-1", (AgentMessageContent.text_content("partial answer"),))
        )

        processor.collect_thread_events(
            {"method": "item/completed", "params": {"item": partial.to_app_server_mapping()}}
        )
        failed = processor.collect_thread_events(
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "status": "failed",
                        "items": [],
                        "error": {"message": "turn failed"},
                    }
                },
            }
        )

        self.assertEqual(failed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(failed.events[-1].to_mapping()["type"], "turn.failed")
        self.assertIsNone(processor.final_message)

    def test_json_processor_turn_completion_falls_back_to_final_plan_text(self):
        processor = JsonEventProcessor()
        plan = TurnItem.plan(PlanItem("plan-1", "ship the typed adapter"))

        completed = processor.collect_thread_events(
            {
                "method": "turn/completed",
                "params": {"turn": {"status": "completed", "items": [plan.to_app_server_mapping()]}},
            }
        )

        self.assertEqual(completed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(completed.events[-1].to_mapping()["type"], "turn.completed")
        self.assertEqual(processor.final_message, "ship the typed adapter")

    def test_json_processor_turn_failure_prefers_structured_error_message(self):
        processor = JsonEventProcessor()

        error = processor.collect_thread_events(
            {
                "method": "error",
                "params": {"error": {"message": "backend failed", "additionalDetails": "request id abc"}},
            }
        )
        failed = processor.collect_thread_events(
            {"method": "turn/completed", "params": {"turn": {"status": "failed", "items": [], "error": None}}}
        )

        self.assertEqual(error.events[0].to_mapping(), {"type": "error", "message": "backend failed (request id abc)"})
        self.assertEqual(failed.status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(failed.events[0].to_mapping()["error"]["message"], "backend failed (request id abc)")

    def test_human_processor_final_output_decisions_match_upstream(self):
        self.assertTrue(should_print_final_message_to_stdout("answer", False, True))
        self.assertFalse(should_print_final_message_to_stdout("answer", True, True))
        self.assertTrue(should_print_final_message_to_tty("answer", False, True, True))
        self.assertFalse(should_print_final_message_to_tty("answer", True, True, True))

    def test_human_processor_prints_final_message_to_stdout_when_not_tty(self):
        processor = HumanEventProcessor()
        stdout = io.StringIO()
        stderr = io.StringIO()
        agent_item = TurnItem.agent_message(
            AgentMessageItem("msg-1", (AgentMessageContent.text_content("final answer"),))
        )

        processor.collect_turn_completed(status="completed", items=(agent_item,))
        processor.print_final_output(
            stdout=stdout,
            stderr=stderr,
            stdout_is_terminal=False,
            stderr_is_terminal=True,
        )

        self.assertEqual(stdout.getvalue(), "final answer\n")

    def test_exec_turn_notifications_use_protocol_v2_envelopes(self):
        processor = JsonEventProcessor()
        agent_item = TurnItem.agent_message(
            AgentMessageItem("msg-1", (AgentMessageContent.text_content("final answer"),))
        )
        started = exec_turn_started_notification("thread-1", "turn-1", started_at=10)
        completed = exec_turn_completed_notification("thread-1", "turn-1", (agent_item,), completed_at=12)

        self.assertEqual(started["method"], "turn/started")
        self.assertEqual(started["params"]["turn"]["status"], "inProgress")
        self.assertEqual(completed["method"], "turn/completed")
        self.assertEqual(completed["params"]["turn"]["items"], [agent_item.to_app_server_mapping()])

        self.assertEqual(processor.process_server_notification(started).status, CodexStatus.RUNNING)
        self.assertEqual(processor.process_server_notification(completed).status, CodexStatus.INITIATE_SHUTDOWN)
        self.assertEqual(stderr.getvalue(), "")

    def test_blended_total_matches_exec_human_output_total(self):
        self.assertEqual(
            blended_total(Usage(input_tokens=20, cached_input_tokens=5, output_tokens=7)),
            22,
        )
        self.assertEqual(
            blended_total(Usage(input_tokens=3, cached_input_tokens=10, output_tokens=-1)),
            0,
        )


if __name__ == "__main__":
    unittest.main()
