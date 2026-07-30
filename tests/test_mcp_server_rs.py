from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pycodex.mcp_server.codex_tool_config import (
    CodexToolCallParam,
    CodexToolCallReplyParam,
    create_tool_for_codex_tool_call_param,
    create_tool_for_codex_tool_call_reply_param,
)
from pycodex.mcp_server.codex_tool_runner import (
    create_call_tool_result_with_thread_id,
)
from pycodex.mcp_server.exec_approval import ExecApprovalElicitRequestParams
from pycodex.mcp_server.message_processor import MessageProcessor
from pycodex.mcp_server.outgoing_message import OutgoingMessageSender
from pycodex.mcp_server.patch_approval import PatchApprovalElicitRequestParams
from pycodex.core.thread_manager import NewThread
from pycodex.protocol import Event, EventMsg, ReviewDecision


def test_codex_tool_schemas_match_fixed_rust_baseline() -> None:
    # Rust: codex-mcp-server/src/codex_tool_config.rs.
    codex_tool = create_tool_for_codex_tool_call_param()
    reply_tool = create_tool_for_codex_tool_call_reply_param()

    assert codex_tool["name"] == "codex"
    assert codex_tool["inputSchema"]["required"] == ["prompt"]
    assert codex_tool["inputSchema"]["additionalProperties"] is False
    assert codex_tool["outputSchema"]["required"] == ["threadId", "content"]
    assert reply_tool["name"] == "codex-reply"
    assert reply_tool["inputSchema"]["required"] == ["prompt"]


def test_tool_params_parse_rust_field_names_and_reject_unknowns(tmp_path: Path) -> None:
    parsed = CodexToolCallParam.from_mapping(
        {
            "prompt": "hello",
            "cwd": str(tmp_path),
            "approval-policy": "on-request",
            "sandbox": "read-only",
        }
    )
    assert parsed.prompt == "hello"
    assert parsed.approval_policy == "on-request"

    reply = CodexToolCallReplyParam.from_mapping(
        {"conversationId": "thread-1", "prompt": "continue"}
    )
    assert reply.get_thread_id() == "thread-1"

    try:
        CodexToolCallParam.from_mapping({"prompt": "hello", "profile": "work"})
    except ValueError as exc:
        assert "unknown field `profile`" in str(exc)
    else:
        raise AssertionError("removed profile field must be rejected")


def test_call_tool_result_contains_thread_id_and_mirrored_content() -> None:
    # Rust: codex_tool_runner::create_call_tool_result_with_thread_id.
    result = create_call_tool_result_with_thread_id("thread-1", "done", None)
    assert result == {
        "content": [{"type": "text", "text": "done"}],
        "structuredContent": {"threadId": "thread-1", "content": "done"},
    }


def test_approval_params_use_mcp_correlation_fields(tmp_path: Path) -> None:
    exec_params = ExecApprovalElicitRequestParams(
        message="Allow?",
        requested_schema={"type": "object", "properties": {}},
        thread_id="thread-1",
        codex_elicitation="exec-approval",
        codex_mcp_tool_call_id="request-1",
        codex_event_id="event-1",
        codex_call_id="call-1",
        codex_command=("echo", "ok"),
        codex_cwd=tmp_path,
        codex_parsed_cmd=(),
    )
    assert exec_params.to_mapping()["threadId"] == "thread-1"
    assert exec_params.to_mapping()["codex_command"] == ["echo", "ok"]

    patch_params = PatchApprovalElicitRequestParams(
        message="Allow patch?",
        requested_schema={"type": "object", "properties": {}},
        thread_id="thread-1",
        codex_elicitation="patch-approval",
        codex_mcp_tool_call_id="request-1",
        codex_event_id="event-1",
        codex_call_id="call-1",
        codex_reason=None,
        codex_grant_root=None,
        codex_changes={},
    )
    assert patch_params.to_mapping()["codex_elicitation"] == "patch-approval"


def test_message_processor_initializes_and_lists_tools() -> None:
    # Rust: message_processor::handle_initialize and handle_list_tools.
    async def exercise() -> None:
        outgoing = OutgoingMessageSender()
        processor = MessageProcessor(
            outgoing,
            thread_manager=SimpleNamespace(),
            config_factory=lambda value: value,
        )
        await processor.process_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "clientInfo": {"name": "test", "version": "1"},
                },
            }
        )
        await processor.process_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )

        initialized = await outgoing.receive()
        listed = await outgoing.receive()
        assert initialized["result"]["protocolVersion"] == "2025-06-18"
        assert initialized["result"]["serverInfo"]["name"] == "codex-mcp-server"
        assert [tool["name"] for tool in listed["result"]["tools"]] == [
            "codex",
            "codex-reply",
        ]

    asyncio.run(exercise())


def test_codex_tool_call_uses_thread_manager_and_streams_completion() -> None:
    # Rust: message_processor::handle_tool_call_codex ->
    # codex_tool_runner::run_codex_tool_session.
    class FakeThread:
        def __init__(self) -> None:
            self.submissions = []
            self.events = asyncio.Queue()

        async def submit_with_id(self, submission) -> None:
            self.submissions.append(submission)
            await self.events.put(
                Event(
                    id="turn-1",
                    msg=EventMsg.with_payload(
                        "task_complete",
                        {"last_agent_message": "finished"},
                    ),
                )
            )

        async def next_event(self):
            return await self.events.get()

    class FakeThreadManager:
        def __init__(self) -> None:
            self.thread = FakeThread()
            self.configs = []

        async def start_thread(self, config):
            self.configs.append(config)
            return NewThread(
                thread_id="thread-1",
                thread=self.thread,
                session_configured={"type": "session_configured", "model": "test"},
            )

    async def exercise() -> None:
        outgoing = OutgoingMessageSender()
        manager = FakeThreadManager()
        processor = MessageProcessor(
            outgoing,
            thread_manager=manager,
            config_factory=lambda value: ("hello", {"model": value.model}),
        )
        await processor.process_request(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "codex",
                    "arguments": {"prompt": "hello", "model": "test"},
                },
            }
        )
        await processor.wait_pending()

        notification = await outgoing.receive()
        completion_notification = await outgoing.receive()
        response = await outgoing.receive()
        assert notification["method"] == "codex/event"
        assert completion_notification["method"] == "codex/event"
        assert notification["params"]["_meta"] == {
            "requestId": 7,
            "threadId": "thread-1",
        }
        assert manager.configs == [{"model": "test"}]
        assert manager.thread.submissions[0].id == "7"
        assert manager.thread.submissions[0].op.type == "user_input"
        assert response["result"]["structuredContent"] == {
            "threadId": "thread-1",
            "content": "finished",
        }

    asyncio.run(exercise())


def test_outgoing_request_response_correlation_and_conservative_approval() -> None:
    # Rust: outgoing_message::send_request/notify_client_response and
    # exec_approval::on_exec_approval_response.
    class FakeThread:
        def __init__(self) -> None:
            self.ops = []

        async def submit(self, op) -> None:
            self.ops.append(op)

    async def exercise() -> None:
        outgoing = OutgoingMessageSender()
        response = await outgoing.send_request(
            "elicitation/create",
            {"message": "Allow?"},
        )
        request = await outgoing.receive()
        assert request == {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "elicitation/create",
            "params": {"message": "Allow?"},
        }
        await outgoing.notify_client_response(0, {"decision": "approved"})
        assert await response == {"decision": "approved"}

        thread = FakeThread()
        pending = asyncio.get_running_loop().create_future()
        from pycodex.mcp_server.exec_approval import _on_exec_approval_response

        task = asyncio.create_task(
            _on_exec_approval_response("approval-1", "turn-1", pending, thread)
        )
        pending.set_result({"unexpected": True})
        await task
        assert thread.ops[0].type == "exec_approval"
        assert thread.ops[0].fields["decision"] == ReviewDecision.denied()

    asyncio.run(exercise())
