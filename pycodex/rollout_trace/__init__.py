"""Trace bundle format, writer, and reducer for Codex rollouts."""

from __future__ import annotations

from pycodex.rollout_trace.bundle import REDUCED_STATE_FILE_NAME
from pycodex.rollout_trace.code_cell import CodeCellTraceContext
from pycodex.rollout_trace.compaction import CompactionCheckpointTracePayload, CompactionTraceAttempt, CompactionTraceContext
from pycodex.rollout_trace.inference import INFERENCE_CALL_ID_HEADER, InferenceTraceAttempt, InferenceTraceContext, trace_response_item_json
from pycodex.rollout_trace.mcp import MCP_CALL_ID_META_KEY, McpCallTraceContext
from pycodex.rollout_trace.model import AgentPath, AgentThreadId, CodeCellId, CodeModeRuntimeToolId, CodexTurnId, CompactionId, CompactionRequestId, ConversationItemId, CorrelationId, EdgeId, InferenceCallId, McpCallId, ModelVisibleCallId, RolloutTrace, TerminalId, TerminalOperationId, ToolCallId
from pycodex.rollout_trace.model.conversation import ConversationBody, ConversationChannel, ConversationItem, ConversationItemKind, ConversationPart, ConversationRole, InferenceCall, ProducerRef, TokenUsage
from pycodex.rollout_trace.model.runtime import CodeCell, CodeCellRuntimeStatus, Compaction, CompactionRequest, InteractionEdge, InteractionEdgeKind, TerminalModelObservation, TerminalObservationSource, TerminalOperation, TerminalOperationKind, TerminalRequest, TerminalResult, TerminalSession, ToolCall, ToolCallKind, ToolCallRequester, ToolCallSummary, TraceAnchor
from pycodex.rollout_trace.model.session import AgentOrigin, AgentThread, CodexTurn, ExecutionStatus, ExecutionWindow, RolloutStatus
from pycodex.rollout_trace.payload import RawPayloadId, RawPayloadKind, RawPayloadRef
from pycodex.rollout_trace.raw_event import RawEventSeq, RawToolCallRequester, RawTraceEvent, RawTraceEventContext, RawTraceEventPayload
from pycodex.rollout_trace.reducer import replay_bundle
from pycodex.rollout_trace.thread import AgentResultTracePayload, CODEX_ROLLOUT_TRACE_ROOT_ENV, ThreadStartedTraceMetadata, ThreadTraceContext
from pycodex.rollout_trace.tool_dispatch import ToolDispatchInvocation, ToolDispatchPayload, ToolDispatchRequester, ToolDispatchResult, ToolDispatchTraceContext
from pycodex.rollout_trace.writer import TraceWriter

__all__ = [
    "AgentOrigin",
    "AgentPath",
    "AgentResultTracePayload",
    "AgentThread",
    "AgentThreadId",
    "CODEX_ROLLOUT_TRACE_ROOT_ENV",
    "CodeCell",
    "CodeCellId",
    "CodeCellRuntimeStatus",
    "CodeCellTraceContext",
    "CodeModeRuntimeToolId",
    "CodexTurn",
    "CodexTurnId",
    "Compaction",
    "CompactionCheckpointTracePayload",
    "CompactionId",
    "CompactionRequest",
    "CompactionRequestId",
    "CompactionTraceAttempt",
    "CompactionTraceContext",
    "ConversationBody",
    "ConversationChannel",
    "ConversationItem",
    "ConversationItemId",
    "ConversationItemKind",
    "ConversationPart",
    "ConversationRole",
    "CorrelationId",
    "EdgeId",
    "ExecutionStatus",
    "ExecutionWindow",
    "INFERENCE_CALL_ID_HEADER",
    "InferenceCall",
    "InferenceCallId",
    "InferenceTraceAttempt",
    "InferenceTraceContext",
    "InteractionEdge",
    "InteractionEdgeKind",
    "MCP_CALL_ID_META_KEY",
    "McpCallId",
    "McpCallTraceContext",
    "ModelVisibleCallId",
    "ProducerRef",
    "REDUCED_STATE_FILE_NAME",
    "RawEventSeq",
    "RawPayloadId",
    "RawPayloadKind",
    "RawPayloadRef",
    "RawToolCallRequester",
    "RawTraceEvent",
    "RawTraceEventContext",
    "RawTraceEventPayload",
    "RolloutStatus",
    "RolloutTrace",
    "TerminalId",
    "TerminalModelObservation",
    "TerminalObservationSource",
    "TerminalOperation",
    "TerminalOperationId",
    "TerminalOperationKind",
    "TerminalRequest",
    "TerminalResult",
    "TerminalSession",
    "ThreadStartedTraceMetadata",
    "ThreadTraceContext",
    "TokenUsage",
    "ToolCall",
    "ToolCallId",
    "ToolCallKind",
    "ToolCallRequester",
    "ToolCallSummary",
    "ToolDispatchInvocation",
    "ToolDispatchPayload",
    "ToolDispatchRequester",
    "ToolDispatchResult",
    "ToolDispatchTraceContext",
    "TraceAnchor",
    "TraceWriter",
    "replay_bundle",
    "trace_response_item_json"
]
