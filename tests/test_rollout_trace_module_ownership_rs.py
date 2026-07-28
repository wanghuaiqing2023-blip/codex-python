import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("bundle", "REDUCED_STATE_FILE_NAME"),
        ("code_cell", "CodeCellTraceContext"),
        ("compaction", "CompactionTraceAttempt"),
        ("inference", "InferenceTraceAttempt"),
        ("mcp", "McpCallTraceContext"),
        ("model", "RolloutTrace"),
        ("model.conversation", "ConversationItem"),
        ("model.runtime", "ToolCall"),
        ("model.session", "AgentThread"),
        ("payload", "RawPayloadRef"),
        ("protocol_event", "wrapped_protocol_event_type"),
        ("raw_event", "RawTraceEvent"),
        ("reducer", "replay_bundle"),
        ("reducer.code_cell", "push_unique"),
        ("reducer.compaction", "start_compaction_request"),
        ("reducer.conversation", "reconcile_conversation_items"),
        ("reducer.conversation.normalize", "normalize_model_item"),
        ("reducer.inference", "start_inference_call"),
        ("reducer.thread", "task_name_from_agent_path"),
        ("reducer.tool", "start_tool_call"),
        ("reducer.tool.agents", "extend_unique"),
        ("reducer.tool.terminal", "terminal_operation_kind"),
        ("thread", "ThreadTraceContext"),
        ("tool_dispatch", "ToolDispatchTraceContext"),
        ("writer", "TraceWriter"),
    ],
)
def test_rollout_trace_item_has_rust_aligned_owner(
    module_name: str,
    symbol: str,
) -> None:
    """Rust source: codex-rollout-trace module graph rooted at src/lib.rs."""
    module = importlib.import_module(f"pycodex.rollout_trace.{module_name}")
    item = getattr(module, symbol)
    if callable(item):
        assert item.__module__ == module.__name__
