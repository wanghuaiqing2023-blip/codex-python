from __future__ import annotations

import pytest

from pycodex.rollout_trace import (
    ExecutionStatus,
    MCP_CALL_ID_META_KEY,
    McpCallTraceContext,
    RawPayloadKind,
    RawToolCallRequester,
    RawTraceEventContext,
    RawTraceEventPayload,
    ThreadTraceContext,
    replay_bundle,
)
from test_rollout_trace_thread_rs import metadata, read_jsonl, single_bundle_dir


def test_disabled_mcp_trace_leaves_request_meta_unchanged() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/mcp.rs
    # Rust test: disabled_mcp_trace_leaves_request_meta_unchanged
    # Contract: disabled MCP trace context records nothing and preserves metadata exactly.
    meta = {"source": "test"}

    assert McpCallTraceContext.disabled().add_request_meta(meta.copy()) == meta
    assert McpCallTraceContext.disabled().add_request_meta(None) is None


def test_enabled_mcp_trace_adds_bridge_correlation_meta() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/mcp.rs
    # Rust test: enabled_mcp_trace_adds_bridge_correlation_meta
    # Contract: enabled MCP trace context adds bridge-private correlation metadata to object metadata.
    trace = McpCallTraceContext.enabled("mcp-call-id")
    meta = trace.add_request_meta({"source": "test"})

    assert meta == {
        "source": "test",
        MCP_CALL_ID_META_KEY: "mcp-call-id",
    }


def test_enabled_mcp_trace_creates_meta_object_and_preserves_non_object_meta() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-rollout-trace
    # Rust module: src/mcp.rs
    # Rust item: McpCallTraceContext::add_request_meta
    # Contract: None becomes a metadata object; non-object JSON metadata is best-effort left unchanged.
    trace = McpCallTraceContext.enabled("mcp-call-id")

    assert trace.add_request_meta(None) == {MCP_CALL_ID_META_KEY: "mcp-call-id"}
    assert trace.add_request_meta(["not", "object"]) == ["not", "object"]


def test_start_mcp_call_trace_records_correlation_and_request_meta(tmp_path) -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-rollout-trace
    # Rust modules: src/thread.rs, src/mcp.rs
    # Rust items: ThreadTraceContext::start_mcp_call_trace, RawTraceEventPayload::McpToolCallCorrelationAssigned
    # Contract: enabled thread tracing emits a correlation event and returns a
    # McpCallTraceContext whose request metadata contains the same trace-owned
    # UUID.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    mcp_trace = trace.start_mcp_call_trace("tool-1")

    event = read_jsonl(single_bundle_dir(tmp_path) / "trace.jsonl")[-1]
    assert event["payload"]["type"] == "mcp_tool_call_correlation_assigned"
    assert event["payload"]["tool_call_id"] == "tool-1"
    assert mcp_trace.mcp_call_id == event["payload"]["mcp_call_id"]
    assert mcp_trace.add_request_meta({}) == {
        MCP_CALL_ID_META_KEY: event["payload"]["mcp_call_id"]
    }


def test_disabled_thread_mcp_trace_records_nothing(tmp_path) -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-rollout-trace
    # Rust module: src/thread.rs
    # Rust item: ThreadTraceContext::start_mcp_call_trace
    # Contract: disabled thread trace returns a disabled MCP context and does
    # not evaluate or write trace output.
    trace = ThreadTraceContext.disabled()

    mcp_trace = trace.start_mcp_call_trace("tool-1")

    assert mcp_trace.add_request_meta({"source": "test"}) == {"source": "test"}
    assert list(tmp_path.iterdir()) == []


def test_mcp_correlation_replays_onto_tool_call(tmp_path) -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-rollout-trace
    # Rust modules: src/reducer/mod.rs, src/reducer/tool.rs
    # Rust item: TraceReducer::assign_mcp_tool_call_correlation
    # Contract: McpToolCallCorrelationAssigned sets ToolCall.mcp_call_id on an
    # existing reduced tool call.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    invocation = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_INVOCATION,
        {
            "tool_name": "mcp_tool",
            "tool_namespace": "mcp__server",
            "payload": {"type": "function", "arguments": "{}"},
        },
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-1",
            model_visible_call_id=None,
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind={"type": "mcp", "server": "server", "tool": "mcp_tool"},
            summary={
                "type": "generic",
                "label": "mcp__server.mcp_tool",
                "input_preview": "{}",
                "output_preview": None,
            },
            invocation_payload=invocation,
        ),
    )
    trace.writer.append(
        RawTraceEventPayload.variant(
            "McpToolCallCorrelationAssigned",
            tool_call_id="tool-1",
            mcp_call_id="mcp-call-id",
        )
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id="tool-1",
            status=ExecutionStatus.COMPLETED,
            result_payload=None,
        ),
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))

    assert rollout.tool_calls["tool-1"].mcp_call_id == "mcp-call-id"


def test_mcp_correlation_rejects_unknown_and_duplicate_tool_calls(tmp_path) -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-rollout-trace
    # Rust module: src/reducer/tool.rs
    # Rust item: TraceReducer::assign_mcp_tool_call_correlation
    # Contract: correlation events fail if they reference an unknown tool call
    # or assign a second MCP id to the same tool call.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.writer.append(
        RawTraceEventPayload.variant(
            "McpToolCallCorrelationAssigned",
            tool_call_id="missing-tool",
            mcp_call_id="mcp-call-id",
        )
    )

    with pytest.raises(ValueError, match="MCP correlation referenced unknown tool call"):
        replay_bundle(single_bundle_dir(tmp_path))

    duplicate_root = tmp_path / "duplicate"
    duplicate_root.mkdir()
    trace = ThreadTraceContext.start_root_in_root_for_test(duplicate_root, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-1",
            model_visible_call_id=None,
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind={"type": "mcp", "server": "server", "tool": "mcp_tool"},
            summary={"type": "generic", "label": "mcp_tool", "input_preview": None, "output_preview": None},
            invocation_payload=None,
        ),
    )
    for mcp_call_id in ("first", "second"):
        trace.writer.append(
            RawTraceEventPayload.variant(
                "McpToolCallCorrelationAssigned",
                tool_call_id="tool-1",
                mcp_call_id=mcp_call_id,
            )
        )

    with pytest.raises(ValueError, match="duplicate MCP correlation"):
        replay_bundle(single_bundle_dir(duplicate_root))
