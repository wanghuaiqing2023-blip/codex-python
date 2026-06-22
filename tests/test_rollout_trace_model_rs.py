from pycodex import rollout_trace as rt
from pycodex.rollout_trace import (
    AgentOrigin,
    AgentThread,
    CodeCell,
    CodeCellRuntimeStatus,
    CodexTurn,
    Compaction,
    CompactionRequest,
    ConversationBody,
    ConversationItem,
    ConversationPart,
    ConversationChannel,
    ConversationItemKind,
    ConversationRole,
    ExecutionStatus,
    ExecutionWindow,
    InferenceCall,
    InteractionEdge,
    InteractionEdgeKind,
    ProducerRef,
    RawPayloadKind,
    RawPayloadRef,
    RolloutTrace,
    RolloutStatus,
    TerminalModelObservation,
    TerminalObservationSource,
    TerminalOperationKind,
    TerminalOperation,
    TerminalRequest,
    TerminalResult,
    TerminalSession,
    TokenUsage,
    ToolCall,
    ToolCallKind,
    ToolCallRequester,
    ToolCallSummary,
    TraceAnchor,
)


def test_producer_ref_variants_follow_model_conversation_rs_serde_shape():
    # Rust source: model/conversation.rs ProducerRef
    # Contract: ProducerRef is an internally tagged enum with snake_case
    # variant names and only the variant-owned payload fields.
    cases = [
        (ProducerRef.UserInput(), {"type": "user_input"}),
        (ProducerRef.Inference("inference-1"), {"type": "inference", "inference_call_id": "inference-1"}),
        (ProducerRef.Tool("tool-1"), {"type": "tool", "tool_call_id": "tool-1"}),
        (ProducerRef.CodeCell("code-cell-1"), {"type": "code_cell", "code_cell_id": "code-cell-1"}),
        (ProducerRef.InteractionEdge("edge-1"), {"type": "interaction_edge", "edge_id": "edge-1"}),
        (ProducerRef.Compaction("compaction-1"), {"type": "compaction", "compaction_id": "compaction-1"}),
        (ProducerRef.Harness(), {"type": "harness"}),
    ]

    for producer, expected in cases:
        assert rt._jsonable(producer) == expected


def test_tagged_model_variants_omit_unrelated_optional_fields():
    # Rust source: model/conversation.rs, model/runtime.rs, model/session.rs
    # Contract: tagged model enums serialize with snake_case type names and
    # only the fields owned by the active variant.
    cases = [
        (ConversationPart.Text("hello"), {"type": "text", "text": "hello"}),
        (ConversationPart.Summary("short"), {"type": "summary", "text": "short"}),
        (ConversationPart.Encoded("encrypted_content", "blob"), {"type": "encoded", "label": "encrypted_content", "value": "blob"}),
        (ConversationPart.Json("{}", "raw_payload:1"), {"type": "json", "summary": "{}", "raw_payload_id": "raw_payload:1"}),
        (ConversationPart.Code("javascript", "1 + 1"), {"type": "code", "language": "javascript", "source": "1 + 1"}),
        (ConversationPart.PayloadRef("payload", "raw_payload:2"), {"type": "payload_ref", "label": "payload", "raw_payload_id": "raw_payload:2"}),
        (AgentOrigin.Root(), {"type": "root"}),
        (
            AgentOrigin.Spawned(
                parent_thread_id="thread-root",
                spawn_edge_id="edge-1",
                task_name="child",
                agent_role="worker",
            ),
            {
                "type": "spawned",
                "parent_thread_id": "thread-root",
                "spawn_edge_id": "edge-1",
                "task_name": "child",
                "agent_role": "worker",
            },
        ),
        (
            TerminalRequest.ExecCommand(command=["echo", "ok"], display_command="echo ok", cwd="/tmp"),
            {
                "type": "exec_command",
                "command": ["echo", "ok"],
                "display_command": "echo ok",
                "cwd": "/tmp",
                "yield_time_ms": None,
                "max_output_tokens": None,
            },
        ),
        (
            TerminalRequest.WriteStdin(stdin="q"),
            {"type": "write_stdin", "stdin": "q", "yield_time_ms": None, "max_output_tokens": None},
        ),
        (TraceAnchor.ToolCall("tool-1"), {"type": "tool_call", "tool_call_id": "tool-1"}),
        (TraceAnchor.Thread("thread-root"), {"type": "thread", "thread_id": "thread-root"}),
        (TraceAnchor.ConversationItem("item-1"), {"type": "conversation_item", "item_id": "item-1"}),
    ]

    for value, expected in cases:
        assert rt._jsonable(value) == expected


def test_runtime_tool_model_variants_follow_model_runtime_rs_serde_shape():
    # Rust source: model/runtime.rs ToolCallRequester, ToolCallKind, ToolCallSummary
    # Contract: tool runtime enums are internally tagged with snake_case type
    # names and only serialize fields owned by the selected variant. Variant-
    # owned Option fields are emitted as null by Rust's derived serde impl.
    cases = [
        (ToolCallRequester.Model(), {"type": "model"}),
        (ToolCallRequester.CodeCell("code-cell-1"), {"type": "code_cell", "code_cell_id": "code-cell-1"}),
        (ToolCallKind.ExecCommand(), {"type": "exec_command"}),
        (ToolCallKind.WriteStdin(), {"type": "write_stdin"}),
        (ToolCallKind.ApplyPatch(), {"type": "apply_patch"}),
        (ToolCallKind.Mcp(server="filesystem", tool="read_file"), {"type": "mcp", "server": "filesystem", "tool": "read_file"}),
        (ToolCallKind.Web(), {"type": "web"}),
        (ToolCallKind.ImageGeneration(), {"type": "image_generation"}),
        (ToolCallKind.SpawnAgent(), {"type": "spawn_agent"}),
        (ToolCallKind.AssignAgentTask(), {"type": "assign_agent_task"}),
        (ToolCallKind.SendMessage(), {"type": "send_message"}),
        (ToolCallKind.WaitAgent(), {"type": "wait_agent"}),
        (ToolCallKind.CloseAgent(), {"type": "close_agent"}),
        (ToolCallKind.Other(name="custom"), {"type": "other", "name": "custom"}),
        (ToolCallSummary.Terminal(operation_id="terminal-op-1"), {"type": "terminal", "operation_id": "terminal-op-1"}),
        (
            ToolCallSummary.Agent(
                target_agent_path="/root/child",
                task_name=None,
                message_preview="hello",
            ),
            {
                "type": "agent",
                "target_agent_path": "/root/child",
                "task_name": None,
                "message_preview": "hello",
            },
        ),
        (
            ToolCallSummary.WaitAgent(target_agent_path="/root/child", timeout_ms=1000),
            {"type": "wait_agent", "target_agent_path": "/root/child", "timeout_ms": 1000},
        ),
        (ToolCallSummary.WaitAgent(), {"type": "wait_agent", "target_agent_path": None, "timeout_ms": None}),
        (
            ToolCallSummary.Generic(label="tool", input_preview="in", output_preview="out"),
            {"type": "generic", "label": "tool", "input_preview": "in", "output_preview": "out"},
        ),
        (
            ToolCallSummary.Generic(label="tool"),
            {"type": "generic", "label": "tool", "input_preview": None, "output_preview": None},
        ),
    ]

    for value, expected in cases:
        assert rt._jsonable(value) == expected


def test_interaction_edge_kind_follows_model_runtime_rs_serde_shape():
    # Rust source: model/runtime.rs InteractionEdgeKind
    # Contract: edge kinds are snake_case enum values.
    cases = [
        (InteractionEdgeKind.SPAWN_AGENT, "spawn_agent"),
        (InteractionEdgeKind.ASSIGN_AGENT_TASK, "assign_agent_task"),
        (InteractionEdgeKind.SEND_MESSAGE, "send_message"),
        (InteractionEdgeKind.AGENT_RESULT, "agent_result"),
        (InteractionEdgeKind.CLOSE_AGENT, "close_agent"),
    ]

    for value, expected in cases:
        assert rt._jsonable(value) == expected


def test_plain_model_enums_follow_snake_case_serde_values():
    # Rust source: model/session.rs, model/conversation.rs, model/runtime.rs
    # Contract: plain serde enums use rename_all = "snake_case" and serialize
    # directly as snake_case string values.
    cases = [
        (RolloutStatus.RUNNING, "running"),
        (RolloutStatus.COMPLETED, "completed"),
        (RolloutStatus.FAILED, "failed"),
        (RolloutStatus.ABORTED, "aborted"),
        (ExecutionStatus.RUNNING, "running"),
        (ExecutionStatus.COMPLETED, "completed"),
        (ExecutionStatus.FAILED, "failed"),
        (ExecutionStatus.CANCELLED, "cancelled"),
        (ExecutionStatus.ABORTED, "aborted"),
        (ConversationRole.SYSTEM, "system"),
        (ConversationRole.DEVELOPER, "developer"),
        (ConversationRole.USER, "user"),
        (ConversationRole.ASSISTANT, "assistant"),
        (ConversationRole.TOOL, "tool"),
        (ConversationChannel.ANALYSIS, "analysis"),
        (ConversationChannel.COMMENTARY, "commentary"),
        (ConversationChannel.FINAL, "final"),
        (ConversationChannel.SUMMARY, "summary"),
        (ConversationItemKind.MESSAGE, "message"),
        (ConversationItemKind.REASONING, "reasoning"),
        (ConversationItemKind.FUNCTION_CALL, "function_call"),
        (ConversationItemKind.FUNCTION_CALL_OUTPUT, "function_call_output"),
        (ConversationItemKind.CUSTOM_TOOL_CALL, "custom_tool_call"),
        (ConversationItemKind.CUSTOM_TOOL_CALL_OUTPUT, "custom_tool_call_output"),
        (ConversationItemKind.COMPACTION_MARKER, "compaction_marker"),
        (CodeCellRuntimeStatus.STARTING, "starting"),
        (CodeCellRuntimeStatus.RUNNING, "running"),
        (CodeCellRuntimeStatus.YIELDED, "yielded"),
        (CodeCellRuntimeStatus.COMPLETED, "completed"),
        (CodeCellRuntimeStatus.FAILED, "failed"),
        (CodeCellRuntimeStatus.TERMINATED, "terminated"),
        (TerminalOperationKind.EXEC_COMMAND, "exec_command"),
        (TerminalOperationKind.WRITE_STDIN, "write_stdin"),
        (TerminalObservationSource.DIRECT_TOOL_CALL, "direct_tool_call"),
        (TerminalObservationSource.CODE_CELL_OUTPUT, "code_cell_output"),
    ]

    for value, expected in cases:
        assert rt._jsonable(value) == expected


def test_runtime_tagged_option_fields_emit_null_for_active_variant():
    # Rust source: model/runtime.rs TerminalRequest and ToolCallSummary
    # Contract: Rust derives Serialize without skip_serializing_if, so active
    # variant Option fields serialize as null while unrelated variant fields are
    # omitted.
    assert rt._jsonable(TerminalRequest.ExecCommand(command=["pwd"], display_command="pwd", cwd="/repo")) == {
        "type": "exec_command",
        "command": ["pwd"],
        "display_command": "pwd",
        "cwd": "/repo",
        "yield_time_ms": None,
        "max_output_tokens": None,
    }
    assert rt._jsonable(TerminalRequest.WriteStdin(stdin="")) == {
        "type": "write_stdin",
        "stdin": "",
        "yield_time_ms": None,
        "max_output_tokens": None,
    }
    assert "stdin" not in rt._jsonable(TerminalRequest.ExecCommand(command=["pwd"], display_command="pwd", cwd="/repo"))
    assert "command" not in rt._jsonable(TerminalRequest.WriteStdin(stdin=""))


def test_rollout_trace_projection_omits_python_reducer_internal_fields():
    # Rust source: model/mod.rs RolloutTrace
    # Contract: reduced trace serialization includes only the public Rust model
    # graph maps and scalar fields, not Python reducer caches or counters.
    rollout = RolloutTrace(
        schema_version=1,
        trace_id="trace-1",
        rollout_id="rollout-1",
        started_at_unix_ms=10,
        ended_at_unix_ms=None,
        status=RolloutStatus.RUNNING,
        root_thread_id="thread-root",
    )
    rollout.threads["thread-root"] = AgentThread(
        thread_id="thread-root",
        agent_path="/root",
        nickname=None,
        origin=AgentOrigin.Root(),
        execution=ExecutionWindow(started_at_unix_ms=10, started_seq=1),
        default_model="gpt-test",
        conversation_item_ids=[],
    )
    rollout.raw_payloads["raw_payload:1"] = RawPayloadRef(
        "raw_payload:1",
        RawPayloadKind.SESSION_METADATA,
        "payloads/1.json",
    )
    rollout.thread_conversation_snapshots["thread-root"] = ["item-hidden"]
    rollout.pending_compaction_replacement_item_ids["thread-root"] = ["item-hidden"]
    rollout._next_conversation_item_ordinal = 42

    projected = rt._jsonable(rollout)

    assert list(projected) == [
        "schema_version",
        "trace_id",
        "rollout_id",
        "started_at_unix_ms",
        "ended_at_unix_ms",
        "status",
        "root_thread_id",
        "threads",
        "codex_turns",
        "conversation_items",
        "inference_calls",
        "code_cells",
        "tool_calls",
        "terminal_sessions",
        "terminal_operations",
        "compactions",
        "compaction_requests",
        "interaction_edges",
        "raw_payloads",
    ]
    assert projected["status"] == "running"
    assert projected["threads"]["thread-root"]["origin"] == {"type": "root"}
    assert projected["threads"]["thread-root"]["execution"]["status"] == "running"
    assert projected["raw_payloads"]["raw_payload:1"] == {
        "raw_payload_id": "raw_payload:1",
        "kind": {"type": "session_metadata"},
        "path": "payloads/1.json",
    }
    assert "thread_conversation_snapshots" not in projected
    assert "pending_compaction_replacement_item_ids" not in projected
    assert "_next_conversation_item_ordinal" not in projected


def test_session_and_conversation_model_structs_follow_public_field_shape():
    # Rust source: model/session.rs, model/conversation.rs, model/runtime.rs
    # Contract: public session/conversation graph structs serialize with Rust
    # public field names, include nullable Option fields as null, and preserve
    # nested enum/dataclass serde shapes.
    running = ExecutionWindow(started_at_unix_ms=10, started_seq=1)
    completed = ExecutionWindow(
        started_at_unix_ms=10,
        started_seq=1,
        ended_at_unix_ms=20,
        ended_seq=2,
        status=ExecutionStatus.COMPLETED,
    )

    agent_thread = AgentThread(
        thread_id="thread-root",
        agent_path="/root",
        nickname=None,
        origin=AgentOrigin.Root(),
        execution=running,
        default_model=None,
        conversation_item_ids=["item-1"],
    )
    assert rt._jsonable(agent_thread) == {
        "thread_id": "thread-root",
        "agent_path": "/root",
        "nickname": None,
        "origin": {"type": "root"},
        "execution": {
            "started_at_unix_ms": 10,
            "started_seq": 1,
            "ended_at_unix_ms": None,
            "ended_seq": None,
            "status": "running",
        },
        "default_model": None,
        "conversation_item_ids": ["item-1"],
    }

    codex_turn = CodexTurn(
        codex_turn_id="turn-1",
        thread_id="thread-root",
        execution=completed,
        input_item_ids=["item-1"],
    )
    assert rt._jsonable(codex_turn) == {
        "codex_turn_id": "turn-1",
        "thread_id": "thread-root",
        "execution": {
            "started_at_unix_ms": 10,
            "started_seq": 1,
            "ended_at_unix_ms": 20,
            "ended_seq": 2,
            "status": "completed",
        },
        "input_item_ids": ["item-1"],
    }

    conversation_item = ConversationItem(
        item_id="item-1",
        thread_id="thread-root",
        codex_turn_id=None,
        first_seen_at_unix_ms=10,
        role=ConversationRole.ASSISTANT,
        channel=ConversationChannel.FINAL,
        kind=ConversationItemKind.MESSAGE,
        body=ConversationBody([ConversationPart.Text("done")]),
        call_id=None,
        produced_by=[ProducerRef.Inference("inference-1")],
    )
    assert rt._jsonable(conversation_item) == {
        "item_id": "item-1",
        "thread_id": "thread-root",
        "codex_turn_id": None,
        "first_seen_at_unix_ms": 10,
        "role": "assistant",
        "channel": "final",
        "kind": "message",
        "body": {"parts": [{"type": "text", "text": "done"}]},
        "call_id": None,
        "produced_by": [{"type": "inference", "inference_call_id": "inference-1"}],
    }

    usage = TokenUsage(
        input_tokens=11,
        cached_input_tokens=3,
        output_tokens=5,
        reasoning_output_tokens=2,
    )
    assert rt._jsonable(usage) == {
        "input_tokens": 11,
        "cached_input_tokens": 3,
        "output_tokens": 5,
        "reasoning_output_tokens": 2,
    }

    inference_call = InferenceCall(
        inference_call_id="inference-1",
        thread_id="thread-root",
        codex_turn_id="turn-1",
        execution=completed,
        model="gpt-test",
        provider_name="test-provider",
        response_id=None,
        upstream_request_id="req-1",
        request_item_ids=["item-1"],
        response_item_ids=["item-2"],
        tool_call_ids_started_by_response=["tool-1"],
        usage=usage,
        raw_request_payload_id="raw_payload:1",
        raw_response_payload_id=None,
    )
    assert rt._jsonable(inference_call) == {
        "inference_call_id": "inference-1",
        "thread_id": "thread-root",
        "codex_turn_id": "turn-1",
        "execution": {
            "started_at_unix_ms": 10,
            "started_seq": 1,
            "ended_at_unix_ms": 20,
            "ended_seq": 2,
            "status": "completed",
        },
        "model": "gpt-test",
        "provider_name": "test-provider",
        "response_id": None,
        "upstream_request_id": "req-1",
        "request_item_ids": ["item-1"],
        "response_item_ids": ["item-2"],
        "tool_call_ids_started_by_response": ["tool-1"],
        "usage": {
            "input_tokens": 11,
            "cached_input_tokens": 3,
            "output_tokens": 5,
            "reasoning_output_tokens": 2,
        },
        "raw_request_payload_id": "raw_payload:1",
        "raw_response_payload_id": None,
    }

    compaction_request = CompactionRequest(
        compaction_request_id="compaction-request-1",
        compaction_id="compaction-1",
        thread_id="thread-root",
        codex_turn_id="turn-1",
        execution=completed,
        model="gpt-test",
        provider_name="test-provider",
        raw_request_payload_id="raw_payload:3",
        raw_response_payload_id=None,
    )
    assert rt._jsonable(compaction_request) == {
        "compaction_request_id": "compaction-request-1",
        "compaction_id": "compaction-1",
        "thread_id": "thread-root",
        "codex_turn_id": "turn-1",
        "execution": {
            "started_at_unix_ms": 10,
            "started_seq": 1,
            "ended_at_unix_ms": 20,
            "ended_seq": 2,
            "status": "completed",
        },
        "model": "gpt-test",
        "provider_name": "test-provider",
        "raw_request_payload_id": "raw_payload:3",
        "raw_response_payload_id": None,
    }

    compaction = Compaction(
        compaction_id="compaction-1",
        thread_id="thread-root",
        codex_turn_id="turn-1",
        installed_at_unix_ms=25,
        marker_item_id="item-marker",
        request_ids=["compaction-request-1"],
        input_item_ids=["item-1"],
        replacement_item_ids=["item-2"],
    )
    assert rt._jsonable(compaction) == {
        "compaction_id": "compaction-1",
        "thread_id": "thread-root",
        "codex_turn_id": "turn-1",
        "installed_at_unix_ms": 25,
        "marker_item_id": "item-marker",
        "request_ids": ["compaction-request-1"],
        "input_item_ids": ["item-1"],
        "replacement_item_ids": ["item-2"],
    }


def test_runtime_model_structs_follow_model_runtime_rs_field_shape():
    # Rust source: model/runtime.rs CodeCell, ToolCall, TerminalSession,
    # TerminalOperation, TerminalResult, TerminalModelObservation, and
    # InteractionEdge.
    # Contract: runtime/debug graph structs serialize with Rust public field
    # names, include nullable Option fields as null, and preserve nested enum
    # serde shapes.
    running = ExecutionWindow(started_at_unix_ms=100, started_seq=7)
    completed = ExecutionWindow(
        started_at_unix_ms=100,
        started_seq=7,
        ended_at_unix_ms=120,
        ended_seq=9,
        status=ExecutionStatus.COMPLETED,
    )

    code_cell = CodeCell(
        code_cell_id="code-cell-1",
        model_visible_call_id="call-code-1",
        thread_id="thread-root",
        codex_turn_id="turn-1",
        source_item_id="item-source",
        output_item_ids=["item-output"],
        runtime_cell_id=None,
        execution=running,
        runtime_status=CodeCellRuntimeStatus.RUNNING,
        initial_response_at_unix_ms=None,
        initial_response_seq=None,
        yielded_at_unix_ms=None,
        yielded_seq=None,
        source_js="console.log(1)",
        nested_tool_call_ids=["tool-nested"],
        wait_tool_call_ids=["tool-wait"],
    )
    assert rt._jsonable(code_cell) == {
        "code_cell_id": "code-cell-1",
        "model_visible_call_id": "call-code-1",
        "thread_id": "thread-root",
        "codex_turn_id": "turn-1",
        "source_item_id": "item-source",
        "output_item_ids": ["item-output"],
        "runtime_cell_id": None,
        "execution": {
            "started_at_unix_ms": 100,
            "started_seq": 7,
            "ended_at_unix_ms": None,
            "ended_seq": None,
            "status": "running",
        },
        "runtime_status": "running",
        "initial_response_at_unix_ms": None,
        "initial_response_seq": None,
        "yielded_at_unix_ms": None,
        "yielded_seq": None,
        "source_js": "console.log(1)",
        "nested_tool_call_ids": ["tool-nested"],
        "wait_tool_call_ids": ["tool-wait"],
    }

    tool_call = ToolCall(
        tool_call_id="tool-1",
        mcp_call_id=None,
        model_visible_call_id="call-1",
        code_mode_runtime_tool_id=None,
        thread_id="thread-root",
        started_by_codex_turn_id="turn-1",
        execution=completed,
        requester=ToolCallRequester.Model(),
        kind=ToolCallKind.Mcp(server="filesystem", tool="read_file"),
        model_visible_call_item_ids=["item-call"],
        model_visible_output_item_ids=["item-output"],
        terminal_operation_id=None,
        summary=ToolCallSummary.Generic(label="read_file", input_preview=None, output_preview="ok"),
        raw_invocation_payload_id="raw_payload:2",
        raw_result_payload_id=None,
        raw_runtime_payload_ids=["raw_payload:3"],
    )
    assert rt._jsonable(tool_call) == {
        "tool_call_id": "tool-1",
        "mcp_call_id": None,
        "model_visible_call_id": "call-1",
        "code_mode_runtime_tool_id": None,
        "thread_id": "thread-root",
        "started_by_codex_turn_id": "turn-1",
        "execution": {
            "started_at_unix_ms": 100,
            "started_seq": 7,
            "ended_at_unix_ms": 120,
            "ended_seq": 9,
            "status": "completed",
        },
        "requester": {"type": "model"},
        "kind": {"type": "mcp", "server": "filesystem", "tool": "read_file"},
        "model_visible_call_item_ids": ["item-call"],
        "model_visible_output_item_ids": ["item-output"],
        "terminal_operation_id": None,
        "summary": {"type": "generic", "label": "read_file", "input_preview": None, "output_preview": "ok"},
        "raw_invocation_payload_id": "raw_payload:2",
        "raw_result_payload_id": None,
        "raw_runtime_payload_ids": ["raw_payload:3"],
    }

    terminal_result = TerminalResult(
        exit_code=0,
        stdout="out",
        stderr="",
        formatted_output=None,
        original_token_count=3,
        chunk_id="chunk-1",
    )
    terminal_observation = TerminalModelObservation(
        call_item_ids=["item-call"],
        output_item_ids=["item-output"],
        source=TerminalObservationSource.DIRECT_TOOL_CALL,
    )
    terminal_operation = TerminalOperation(
        operation_id="terminal-op-1",
        terminal_id="terminal-1",
        tool_call_id="tool-1",
        kind=TerminalOperationKind.EXEC_COMMAND,
        execution=completed,
        request=TerminalRequest.ExecCommand(
            command=["echo", "ok"],
            display_command="echo ok",
            cwd="/workspace",
            yield_time_ms=1000,
            max_output_tokens=None,
        ),
        result=terminal_result,
        model_observations=[terminal_observation],
        raw_payload_ids=["raw_payload:4"],
    )
    assert rt._jsonable(terminal_operation) == {
        "operation_id": "terminal-op-1",
        "terminal_id": "terminal-1",
        "tool_call_id": "tool-1",
        "kind": "exec_command",
        "execution": {
            "started_at_unix_ms": 100,
            "started_seq": 7,
            "ended_at_unix_ms": 120,
            "ended_seq": 9,
            "status": "completed",
        },
        "request": {
            "type": "exec_command",
            "command": ["echo", "ok"],
            "display_command": "echo ok",
            "cwd": "/workspace",
            "yield_time_ms": 1000,
            "max_output_tokens": None,
        },
        "result": {
            "exit_code": 0,
            "stdout": "out",
            "stderr": "",
            "formatted_output": None,
            "original_token_count": 3,
            "chunk_id": "chunk-1",
        },
        "model_observations": [
            {
                "call_item_ids": ["item-call"],
                "output_item_ids": ["item-output"],
                "source": "direct_tool_call",
            }
        ],
        "raw_payload_ids": ["raw_payload:4"],
    }

    terminal_session = TerminalSession(
        terminal_id="terminal-1",
        thread_id="thread-root",
        created_by_operation_id="terminal-op-1",
        operation_ids=["terminal-op-1"],
        execution=running,
    )
    assert rt._jsonable(terminal_session)["created_by_operation_id"] == "terminal-op-1"

    edge = InteractionEdge(
        edge_id="edge-1",
        kind=InteractionEdgeKind.SEND_MESSAGE,
        source=TraceAnchor.ToolCall("tool-1"),
        target=TraceAnchor.Thread("thread-child"),
        started_at_unix_ms=100,
        ended_at_unix_ms=None,
        carried_item_ids=["item-output"],
        carried_raw_payload_ids=["raw_payload:5"],
    )
    assert rt._jsonable(edge) == {
        "edge_id": "edge-1",
        "kind": "send_message",
        "source": {"type": "tool_call", "tool_call_id": "tool-1"},
        "target": {"type": "thread", "thread_id": "thread-child"},
        "started_at_unix_ms": 100,
        "ended_at_unix_ms": None,
        "carried_item_ids": ["item-output"],
        "carried_raw_payload_ids": ["raw_payload:5"],
    }
