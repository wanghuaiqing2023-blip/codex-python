"""Rust integration parity for ``core/tests/suite/hooks_mcp.rs``.

Rust drives an rmcp echo server through Codex and verifies that MCP tool calls
are surfaced to PreToolUse/PostToolUse hooks with the canonical MCP hook tool
name, original tool input, structured tool response, and materialized transcript
path. Python keeps the same contract at the hook-runtime/tool-payload boundary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.core.hook_runtime import (
    HookRequestContext,
    PostToolUseHookOutcome,
    additional_context_messages,
    build_post_tool_use_request,
    build_pre_tool_use_request,
    post_tool_use_replacement_text,
    pre_tool_use_result_from_outcome,
)
from pycodex.core.tools.hook_names import HookToolName

RMCP_SERVER = "rmcp"
RMCP_PREFIXED_NAMESPACE = "mcp__rmcp"
RMCP_UNPREFIXED_NAMESPACE = "rmcp"
RMCP_ECHO_TOOL_NAME = "mcp__rmcp__echo"
RMCP_ECHO_MESSAGE = "hook e2e ping"
RMCP_REWRITTEN_MESSAGE = "rewritten mcp hook input"
POST_CONTEXT = "Remember the MCP post-tool note."


@pytest.fixture()
def hook_context(tmp_path: Path) -> HookRequestContext:
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    return HookRequestContext(
        session_id="session-1",
        turn_id="turn-1",
        cwd=str(tmp_path),
        transcript_path=str(transcript),
        model="gpt-test",
        permission_mode="default",
    )


def canonical_mcp_hook_tool_name(_namespace: str, server: str, tool: str) -> HookToolName:
    # Rust hooks_mcp.rs keeps the hook matcher/tool name canonical as
    # mcp__{server}__{tool}, even when model-visible MCP namespaces are not
    # legacy-prefixed.
    return HookToolName.new(f"mcp__{server}__{tool}")


@pytest.mark.parametrize("namespace", [RMCP_PREFIXED_NAMESPACE, RMCP_UNPREFIXED_NAMESPACE])
def test_pre_tool_use_blocks_mcp_tool_before_execution_for_prefixed_and_non_prefixed_names(
    hook_context: HookRequestContext,
    namespace: str,
) -> None:
    # Rust tests:
    # - pre_tool_use_blocks_mcp_tool_before_execution_with_legacy_prefixed_names
    # - pre_tool_use_blocks_mcp_tool_before_execution_with_non_prefixed_names
    tool_name = canonical_mcp_hook_tool_name(namespace, RMCP_SERVER, "echo")
    tool_input = {"message": RMCP_ECHO_MESSAGE}
    request = build_pre_tool_use_request(
        hook_context,
        tool_use_id="pretooluse-rmcp-echo",
        tool_name=tool_name,
        tool_input=tool_input,
    )
    blocked = pre_tool_use_result_from_outcome(
        {"should_block": True, "block_reason": "blocked mcp pre hook"},
        tool_name=tool_name,
        tool_input=tool_input,
    )

    assert request.tool_name == RMCP_ECHO_TOOL_NAME
    assert request.matcher_aliases == ()
    assert request.tool_use_id == "pretooluse-rmcp-echo"
    assert request.tool_input == {"message": RMCP_ECHO_MESSAGE}
    assert request.transcript_path is not None
    assert Path(request.transcript_path).exists()
    assert blocked.type == "blocked"
    assert blocked.message == (
        "Tool call blocked by PreToolUse hook: blocked mcp pre hook. "
        f"Tool: {RMCP_ECHO_TOOL_NAME}"
    )


def test_pre_tool_use_rewrites_mcp_tool_before_execution(hook_context: HookRequestContext) -> None:
    # Rust test: pre_tool_use_rewrites_mcp_tool_before_execution.
    tool_name = canonical_mcp_hook_tool_name(RMCP_PREFIXED_NAMESPACE, RMCP_SERVER, "echo")
    original = {"message": RMCP_ECHO_MESSAGE}
    request = build_pre_tool_use_request(
        hook_context,
        tool_use_id="pretooluse-rmcp-echo-rewrite",
        tool_name=tool_name,
        tool_input=original,
    )
    rewritten = pre_tool_use_result_from_outcome(
        {"should_block": False, "updated_input": {"message": RMCP_REWRITTEN_MESSAGE}},
        tool_name=tool_name,
        tool_input=original,
    )

    assert request.tool_input == original
    assert rewritten.type == "continue"
    assert rewritten.updated_input == {"message": RMCP_REWRITTEN_MESSAGE}
    assert rewritten.updated_input != original


@pytest.mark.parametrize("namespace", [RMCP_PREFIXED_NAMESPACE, RMCP_UNPREFIXED_NAMESPACE])
def test_post_tool_use_records_mcp_tool_payload_and_context_for_prefixed_and_non_prefixed_names(
    hook_context: HookRequestContext,
    namespace: str,
) -> None:
    # Rust tests:
    # - post_tool_use_records_mcp_tool_payload_and_context_with_legacy_prefixed_names
    # - post_tool_use_records_mcp_tool_payload_and_context_with_non_prefixed_names
    tool_name = canonical_mcp_hook_tool_name(namespace, RMCP_SERVER, "echo")
    tool_response = {
        "content": [],
        "structuredContent": {
            "echo": f"ECHOING: {RMCP_ECHO_MESSAGE}",
            "env": None,
        },
        "isError": False,
    }
    request = build_post_tool_use_request(
        hook_context,
        tool_use_id="posttooluse-rmcp-echo",
        tool_name=tool_name,
        tool_input={"message": RMCP_ECHO_MESSAGE},
        tool_response=tool_response,
    )
    context_items = additional_context_messages([POST_CONTEXT])

    assert request.tool_name == RMCP_ECHO_TOOL_NAME
    assert request.tool_use_id == "posttooluse-rmcp-echo"
    assert request.tool_input == {"message": RMCP_ECHO_MESSAGE}
    assert request.tool_response == tool_response
    assert request.tool_response["structuredContent"]["echo"] == f"ECHOING: {RMCP_ECHO_MESSAGE}"
    assert request.transcript_path is not None
    assert Path(request.transcript_path).exists()
    assert POST_CONTEXT in context_items[0].content[0].text
    assert post_tool_use_replacement_text(PostToolUseHookOutcome(additional_contexts=(POST_CONTEXT,))) is None
