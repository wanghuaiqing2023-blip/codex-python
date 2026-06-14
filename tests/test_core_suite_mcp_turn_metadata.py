"""Rust integration parity for ``core/tests/suite/mcp_turn_metadata.rs``.

The Rust tests assert that Apps MCP tool calls receive
``_meta.x-codex-turn-metadata.user_input_requested_during_turn == true`` after
either an MCP approval elicitation or a ``request_user_input`` tool asked the
user for input earlier in the same turn.
"""

from __future__ import annotations

from pathlib import Path

from pycodex.core import McpTurnMetadataContext, TurnMetadataState, USER_INPUT_REQUESTED_DURING_TURN_KEY
from pycodex.core.mcp_tool_call import (
    CODEX_APPS_MCP_SERVER_NAME,
    MCP_TOOL_CODEX_APPS_META_KEY,
    X_CODEX_TURN_METADATA_HEADER,
    McpToolApprovalMetadata,
    build_mcp_tool_call_request_meta,
)
from pycodex.protocol import PermissionProfile, ReasoningEffort, ThreadSource, WindowsSandboxLevel


def _turn_state_after_user_input_request(tmp_path: Path) -> TurnMetadataState:
    state = TurnMetadataState.new(
        session_id="session-a",
        thread_id="thread-a",
        forked_from_thread_id=None,
        thread_source=ThreadSource.USER,
        turn_id="turn-a",
        cwd=tmp_path,
        permission_profile=PermissionProfile.read_only(),
        windows_sandbox_level=WindowsSandboxLevel.DISABLED,
        enforce_managed_network=False,
    )
    state.mark_user_input_requested_during_turn()
    return state


def _codex_apps_request_meta(state: TurnMetadataState, call_id: str) -> dict[str, object]:
    turn_metadata = state.current_meta_value_for_mcp_request(
        McpTurnMetadataContext("gpt-5.4", ReasoningEffort.HIGH)
    )
    request_meta = build_mcp_tool_call_request_meta(
        CODEX_APPS_MCP_SERVER_NAME,
        call_id,
        McpToolApprovalMetadata(
            codex_apps_meta={
                "resource_uri": "connector://calendar/tools/calendar_create_event",
                "connector_id": "calendar",
            }
        ),
        turn_metadata,
    )
    assert request_meta is not None
    return request_meta


def test_approved_mcp_tool_call_metadata_records_prior_user_input_request(tmp_path: Path) -> None:
    """Rust: ``approved_mcp_tool_call_metadata_records_prior_user_input_request``."""

    request_meta = _codex_apps_request_meta(
        _turn_state_after_user_input_request(tmp_path),
        "calendar-call-approval",
    )

    turn_metadata = request_meta[X_CODEX_TURN_METADATA_HEADER]
    assert turn_metadata[USER_INPUT_REQUESTED_DURING_TURN_KEY] is True
    assert request_meta[MCP_TOOL_CODEX_APPS_META_KEY]["call_id"] == "calendar-call-approval"
    assert request_meta[MCP_TOOL_CODEX_APPS_META_KEY]["connector_id"] == "calendar"


def test_mcp_tool_call_metadata_records_prior_request_user_input_tool(tmp_path: Path) -> None:
    """Rust: ``mcp_tool_call_metadata_records_prior_request_user_input_tool``."""

    request_meta = _codex_apps_request_meta(
        _turn_state_after_user_input_request(tmp_path),
        "calendar-call-after-user-input",
    )

    turn_metadata = request_meta[X_CODEX_TURN_METADATA_HEADER]
    assert turn_metadata[USER_INPUT_REQUESTED_DURING_TURN_KEY] is True
    assert request_meta[MCP_TOOL_CODEX_APPS_META_KEY]["call_id"] == "calendar-call-after-user-input"
    assert request_meta[MCP_TOOL_CODEX_APPS_META_KEY]["resource_uri"] == "connector://calendar/tools/calendar_create_event"
