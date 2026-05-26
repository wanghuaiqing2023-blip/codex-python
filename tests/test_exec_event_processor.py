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
    config_summary_entries,
    config_summary_lines,
    exec_item_from_app_server_item,
    format_with_separators,
    final_message_from_turn_items,
    human_item_completed_lines,
    human_item_started_lines,
    human_notification_lines,
    map_todo_items,
    notification_method,
    should_print_final_message_to_stdout,
    should_print_final_message_to_tty,
    summarize_permission_profile,
    usage_from_notification,
)
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageItem,
    CallToolResult,
    McpToolCallItem,
    McpToolCallStatus,
    PermissionProfile,
    PlanItem,
    ReasoningItem,
    TurnItem,
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

    def test_warning_collects_error_item_and_json_lines_emit(self):
        processor = JsonEventProcessor()
        output = io.StringIO()

        collected = processor.collect_warning("config warning")
        processor.emit_json_lines(collected.events, output)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["type"], "item.completed")
        self.assertEqual(payload["item"]["type"], "error")
        self.assertEqual(payload["item"]["message"], "config warning")

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
                    "changes": [{"path": "src/app.py", "kind": "update"}],
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
        self.assertEqual(human_item_completed_lines(item, show_raw_agent_reasoning=True), ("summary\nraw",))
        self.assertEqual(human_item_completed_lines(item, show_agent_reasoning=False), ())

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

    def test_sandbox_summary_and_number_format_helpers(self):
        self.assertEqual(summarize_permission_profile(PermissionProfile.read_only(), "C:/work", ()), "read-only")
        self.assertEqual(summarize_permission_profile(PermissionProfile.disabled(), "C:/work", ()), "danger-full-access")
        self.assertEqual(format_with_separators(1234567), "1,234,567")

    def test_final_message_from_turn_items_falls_back_to_plan_text(self):
        self.assertEqual(final_message_from_turn_items((TurnItem.plan(PlanItem("plan-1", "ship it")),)), "ship it")

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
