from pycodex.rollout_trace import (
    ExecutionStatus,
    ToolDispatchInvocation,
    ToolDispatchPayload,
    ToolDispatchRequester,
    ToolDispatchResult,
)
from test_rollout_trace_thread_rs import metadata, read_json, read_jsonl, single_bundle_dir
from pycodex.rollout_trace import ThreadTraceContext


def invocation(
    tool_name: str,
    *,
    tool_namespace: str | None,
    requester: ToolDispatchRequester,
    payload: ToolDispatchPayload,
) -> ToolDispatchInvocation:
    return ToolDispatchInvocation(
        thread_id="thread-root",
        codex_turn_id="turn-1",
        tool_call_id="tool-call-1",
        tool_name=tool_name,
        tool_namespace=tool_namespace,
        requester=requester,
        payload=payload,
    )


def test_suppresses_only_noncanonical_dispatch_boundaries(tmp_path):
    # Rust test: tool_dispatch.rs suppresses_only_noncanonical_dispatch_boundaries
    # Contract: the public code-mode exec custom tool is suppressed only when it
    # is unnamespaced; other custom tools and namespaced exec dispatches remain
    # traceable.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    suppressed = trace.start_tool_dispatch_trace(
        invocation(
            "exec",
            tool_namespace=None,
            requester=ToolDispatchRequester.Model("call-exec"),
            payload=ToolDispatchPayload.Custom("1 + 1"),
        )
    )
    custom = trace.start_tool_dispatch_trace(
        invocation(
            "custom_tool",
            tool_namespace=None,
            requester=ToolDispatchRequester.Model("call-custom"),
            payload=ToolDispatchPayload.Custom("payload"),
        )
    )
    namespaced = trace.start_tool_dispatch_trace(
        invocation(
            "exec",
            tool_namespace="mcp__server",
            requester=ToolDispatchRequester.Model("call-namespaced"),
            payload=ToolDispatchPayload.Custom("payload"),
        )
    )

    assert not suppressed.is_enabled()
    assert custom.is_enabled()
    assert namespaced.is_enabled()


def test_enabled_dispatch_records_started_and_completed_payloads(tmp_path):
    # Rust source: tool_dispatch.rs ToolDispatchTraceContext::start and
    # record_completed. Contract: enabled dispatch writes ToolInvocation and
    # ToolResult payloads and appends ToolCallStarted/ToolCallEnded with the
    # dispatch thread/turn context, requester fields, kind, and generic summary.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    dispatch = trace.start_tool_dispatch_trace(
        invocation(
            "shell",
            tool_namespace=None,
            requester=ToolDispatchRequester.Model("call-shell"),
            payload=ToolDispatchPayload.Function('{"cmd":"echo hi"}'),
        )
    )
    dispatch.record_completed(
        ExecutionStatus.COMPLETED,
        ToolDispatchResult.DirectResponse(
            {
                "type": "function_call_output",
                "call_id": "call-shell",
                "output": "hi\n",
            }
        ),
    )

    bundle = single_bundle_dir(tmp_path)
    events = read_jsonl(bundle / "trace.jsonl")
    started = events[-2]
    ended = events[-1]

    assert started["thread_id"] == "thread-root"
    assert started["codex_turn_id"] == "turn-1"
    assert started["payload"]["type"] == "tool_call_started"
    assert started["payload"]["tool_call_id"] == "tool-call-1"
    assert started["payload"]["model_visible_call_id"] == "call-shell"
    assert started["payload"]["requester"] == {"type": "model"}
    assert started["payload"]["kind"] == {"type": "exec_command"}
    # Rust source: model/runtime.rs ToolCallSummary::Generic derives serde
    # without skip_serializing_if, so the active variant's Option fields are
    # emitted as null even when the dispatch boundary did not provide output.
    assert started["payload"]["summary"] == {
        "type": "generic",
        "label": "shell",
        "input_preview": '{"cmd":"echo hi"}',
        "output_preview": None,
    }
    request_payload = read_json(bundle / started["payload"]["invocation_payload"]["path"])
    assert request_payload == {
        "tool_name": "shell",
        "tool_namespace": None,
        "payload": {"type": "function", "arguments": '{"cmd":"echo hi"}'},
    }

    assert ended["thread_id"] == "thread-root"
    assert ended["codex_turn_id"] == "turn-1"
    assert ended["payload"]["type"] == "tool_call_ended"
    assert ended["payload"]["tool_call_id"] == "tool-call-1"
    assert ended["payload"]["status"] == "completed"
    result_payload = read_json(bundle / ended["payload"]["result_payload"]["path"])
    assert result_payload == {
        "type": "direct_response",
        "response_item": {
            "type": "function_call_output",
            "call_id": "call-shell",
            "output": "hi\n",
        },
    }


def test_dispatch_preview_truncates_by_rust_char_boundary(tmp_path):
    # Rust source: tool_dispatch.rs ToolDispatchPayload::log_payload_preview
    # and truncate_preview. Contract: previews keep the first 160 Rust chars
    # and append "..." only when more input remains; UTF-8 multi-byte chars are
    # counted as chars, not bytes.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    payload_text = ("λ" * 160) + "tail"

    dispatch = trace.start_tool_dispatch_trace(
        invocation(
            "custom_tool",
            tool_namespace="tools",
            requester=ToolDispatchRequester.Model("call-custom"),
            payload=ToolDispatchPayload.Custom(payload_text),
        )
    )

    assert dispatch.is_enabled()
    bundle = single_bundle_dir(tmp_path)
    started = read_jsonl(bundle / "trace.jsonl")[-1]
    assert started["payload"]["summary"] == {
        "type": "generic",
        "label": "tools.custom_tool",
        "input_preview": ("λ" * 160) + "...",
        "output_preview": None,
    }
    assert len(started["payload"]["summary"]["input_preview"]) == 163


def test_dispatch_kind_aliases_and_namespaced_labels_follow_tool_dispatch_rs(tmp_path):
    # Rust source: tool_dispatch.rs dispatched_tool_kind and
    # dispatched_tool_label. Contract: known tool-name aliases reduce to stable
    # ToolCallKind variants, unknown tools become Other{name}, and labels are
    # namespace-qualified only when a namespace is present.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    cases = [
        ("exec_command", None, {"type": "exec_command"}, "exec_command"),
        ("local_shell", None, {"type": "exec_command"}, "local_shell"),
        ("shell_command", None, {"type": "exec_command"}, "shell_command"),
        ("web_search_preview", None, {"type": "web"}, "web_search_preview"),
        ("image_query", None, {"type": "image_generation"}, "image_query"),
        ("spawn_agent", None, {"type": "spawn_agent"}, "spawn_agent"),
        ("send_message", None, {"type": "send_message"}, "send_message"),
        ("followup_task", None, {"type": "assign_agent_task"}, "followup_task"),
        ("wait_agent", None, {"type": "wait_agent"}, "wait_agent"),
        ("close_agent", None, {"type": "close_agent"}, "close_agent"),
        ("unknown_tool", "mcp__server", {"type": "other", "name": "unknown_tool"}, "mcp__server.unknown_tool"),
    ]

    for tool_name, namespace, expected_kind, expected_label in cases:
        dispatch = trace.start_tool_dispatch_trace(
            invocation(
                tool_name,
                tool_namespace=namespace,
                requester=ToolDispatchRequester.Model(f"call-{tool_name}"),
                payload=ToolDispatchPayload.Function("{}"),
            )
        )
        assert dispatch.is_enabled()
        started = read_jsonl(single_bundle_dir(tmp_path) / "trace.jsonl")[-1]
        assert started["payload"]["kind"] == expected_kind
        assert started["payload"]["summary"]["label"] == expected_label


def test_dispatch_payload_json_variants_follow_tool_dispatch_rs(tmp_path):
    # Rust source: tool_dispatch.rs ToolDispatchPayload::into_json_payload and
    # record_started. Contract: the raw ToolInvocation payload embeds the
    # selected payload variant under its Rust-shaped `type` tag and preserves
    # LocalShell optional fields as JSON null.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    cases = [
        (
            "tool_search",
            ToolDispatchPayload.ToolSearch({"query": "needle", "limit": 5}),
            {"type": "tool_search", "arguments": {"query": "needle", "limit": 5}},
        ),
        (
            "custom_tool",
            ToolDispatchPayload.Custom("return 1;"),
            {"type": "custom", "input": "return 1;"},
        ),
        (
            "local_shell",
            ToolDispatchPayload.LocalShell(
                command=["echo", "ok"],
                workdir=None,
                timeout_ms=250,
                sandbox_permissions={"mode": "read_only"},
                prefix_rule=None,
                additional_permissions=["network"],
                justification=None,
            ),
            {
                "type": "local_shell",
                "command": ["echo", "ok"],
                "workdir": None,
                "timeout_ms": 250,
                "sandbox_permissions": {"mode": "read_only"},
                "prefix_rule": None,
                "additional_permissions": ["network"],
                "justification": None,
            },
        ),
    ]

    for index, (tool_name, payload, expected_payload) in enumerate(cases):
        dispatch = trace.start_tool_dispatch_trace(
            invocation(
                tool_name,
                tool_namespace=None,
                requester=ToolDispatchRequester.Model(f"call-payload-{index}"),
                payload=payload,
            )
        )
        assert dispatch.is_enabled()
        bundle = single_bundle_dir(tmp_path)
        started = read_jsonl(bundle / "trace.jsonl")[-1]
        invocation_payload = read_json(bundle / started["payload"]["invocation_payload"]["path"])
        assert invocation_payload == {
            "tool_name": tool_name,
            "tool_namespace": None,
            "payload": expected_payload,
        }


def test_dispatch_result_json_variants_follow_tool_dispatch_rs(tmp_path):
    # Rust source: tool_dispatch.rs ToolDispatchResult and
    # DispatchedToolTraceResponse. Contract: record_completed serializes the
    # caller-facing result using Rust's internally tagged snake_case enum shape,
    # including the code-mode response value arm.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    dispatch = trace.start_tool_dispatch_trace(
        invocation(
            "exec",
            tool_namespace="code_mode",
            requester=ToolDispatchRequester.CodeCell(
                runtime_cell_id="cell-1",
                runtime_tool_call_id="runtime-tool-1",
            ),
            payload=ToolDispatchPayload.Custom("print('ok')"),
        )
    )
    dispatch.record_completed(
        ExecutionStatus.COMPLETED,
        ToolDispatchResult.CodeModeResponse(
            {
                "type": "exec_result",
                "exit_code": 0,
                "output": "ok\n",
                "num_output_tokens": 1,
            }
        ),
    )

    bundle = single_bundle_dir(tmp_path)
    ended = read_jsonl(bundle / "trace.jsonl")[-1]

    assert ended["payload"]["type"] == "tool_call_ended"
    assert ended["payload"]["tool_call_id"] == "tool-call-1"
    assert ended["payload"]["status"] == "completed"
    assert read_json(bundle / ended["payload"]["result_payload"]["path"]) == {
        "type": "code_mode_response",
        "value": {
            "type": "exec_result",
            "exit_code": 0,
            "output": "ok\n",
            "num_output_tokens": 1,
        },
    }


def test_enabled_dispatch_records_code_cell_requester_and_failed_result(tmp_path):
    # Rust source: tool_dispatch.rs requester_fields and record_failed.
    # Contract: code-cell dispatches record runtime cell/tool ids and failed
    # dispatches produce an error ToolResult payload with failed status.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    dispatch = trace.start_tool_dispatch_trace(
        invocation(
            "write_stdin",
            tool_namespace=None,
            requester=ToolDispatchRequester.CodeCell(
                runtime_cell_id="cell-1",
                runtime_tool_call_id="runtime-tool-1",
            ),
            payload=ToolDispatchPayload.Function('{"session_id":"1","chars":"x"}'),
        )
    )
    dispatch.record_failed("boom")

    bundle = single_bundle_dir(tmp_path)
    events = read_jsonl(bundle / "trace.jsonl")
    started = events[-2]
    ended = events[-1]

    assert started["payload"]["model_visible_call_id"] is None
    assert started["payload"]["code_mode_runtime_tool_id"] == "runtime-tool-1"
    assert started["payload"]["requester"] == {
        "type": "code_cell",
        "runtime_cell_id": "cell-1",
    }
    assert started["payload"]["kind"] == {"type": "write_stdin"}
    assert ended["payload"]["status"] == "failed"
    assert read_json(bundle / ended["payload"]["result_payload"]["path"]) == {
        "type": "error",
        "error": "boom",
    }
