"""Rust-derived tests for ``codex-hooks/src/events/post_tool_use.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/events/post_tool_use.rs``

Rust tests mirrored:
- ``command_input_uses_request_tool_name``
- ``block_decision_stops_normal_processing``
- ``additional_context_is_recorded``
- ``unsupported_updated_mcp_tool_output_fails_open``
- ``exit_two_surfaces_feedback_to_model_without_blocking``
- ``continue_false_stops_with_reason``
- ``plain_stdout_is_ignored_for_post_tool_use``
- ``preview_and_completed_run_ids_include_tool_use_id``
- ``serialization_failure_run_ids_include_tool_use_id``
"""

from __future__ import annotations

import json
from pathlib import Path
from pathlib import PurePosixPath
from types import SimpleNamespace

from pycodex.hooks import PostToolUseHandlerData
from pycodex.hooks import PostToolUseRequest
from pycodex.hooks import SubagentHookContext
from pycodex.hooks import _running_summary
from pycodex.hooks import hook_completed_for_tool_use
from pycodex.hooks import hook_run_for_tool_use
from pycodex.hooks import parse_post_tool_use_completed
from pycodex.hooks import post_tool_use_command_input_json
from pycodex.hooks import post_tool_use_feedback_message
from pycodex.hooks import serialization_failure_hook_events_for_tool_use
from pycodex.protocol import HookEventName
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookSource


def _handler() -> SimpleNamespace:
    return SimpleNamespace(
        event_name=HookEventName.POST_TOOL_USE,
        matcher="^Bash$",
        command="python3 post_tool_use_hook.py",
        timeout_sec=5,
        status_message="running post tool use hook",
        source_path=PurePosixPath("/tmp/hooks.json"),
        source=HookSource.USER,
        display_order=0,
        started_at=1_700_000_000,
    )


def _run_result(
    exit_code: int | None,
    stdout: str,
    stderr: str = "",
    error: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        started_at=1_700_000_000,
        completed_at=1_700_000_001,
        duration_ms=12,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        error=error,
    )


def _request(tool_use_id: str = "tool-call-456") -> PostToolUseRequest:
    return PostToolUseRequest(
        session_id="thread-1",
        turn_id="turn-1",
        subagent=None,
        cwd=Path("/tmp"),
        transcript_path=None,
        model="gpt-test",
        permission_mode="default",
        tool_name="Bash",
        matcher_aliases=[],
        run_id_suffix=None,
        tool_use_id=tool_use_id,
        tool_input={"command": "echo hello"},
        tool_response={"ok": True},
    )


def test_command_input_uses_request_tool_name_and_subagent_fields() -> None:
    # Rust crate/module/test: codex-hooks/src/events/post_tool_use.rs
    # tests::command_input_uses_request_tool_name.
    request = _request("call-apply-patch")
    request.tool_name = "apply_patch"
    request.subagent = SubagentHookContext("agent-1", "reviewer")
    request.transcript_path = Path("/tmp/transcript.jsonl")

    payload = json.loads(post_tool_use_command_input_json(request))

    assert payload["tool_name"] == "apply_patch"
    assert payload["tool_input"] == {"command": "echo hello"}
    assert payload["tool_response"] == {"ok": True}
    assert payload["tool_use_id"] == "call-apply-patch"
    assert payload["hook_event_name"] == "PostToolUse"
    assert payload["agent_id"] == "agent-1"
    assert payload["agent_type"] == "reviewer"
    assert payload["transcript_path"] == str(Path("/tmp/transcript.jsonl"))


def test_block_decision_stops_normal_processing() -> None:
    # Rust test: block_decision_stops_normal_processing.
    parsed = parse_post_tool_use_completed(
        _handler(),
        _run_result(0, '{"decision":"block","reason":"bash output looked sketchy"}'),
        "turn-1",
    )

    assert parsed.data == PostToolUseHandlerData(
        should_stop=False,
        stop_reason=None,
        additional_contexts_for_model=[],
        feedback_messages_for_model=["bash output looked sketchy"],
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "bash output looked sketchy"),
    )


def test_additional_context_is_recorded() -> None:
    # Rust test: additional_context_is_recorded.
    parsed = parse_post_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"Remember the bash cleanup note."}}',
        ),
        "turn-1",
    )

    assert parsed.data == PostToolUseHandlerData(
        should_stop=False,
        stop_reason=None,
        additional_contexts_for_model=["Remember the bash cleanup note."],
        feedback_messages_for_model=[],
    )
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "Remember the bash cleanup note."),
    )


def test_unsupported_updated_mcp_tool_output_fails_open() -> None:
    # Rust test: unsupported_updated_mcp_tool_output_fails_open.
    parsed = parse_post_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PostToolUse","updatedMCPToolOutput":{"ok":true}}}',
        ),
        "turn-1",
    )

    assert parsed.data == PostToolUseHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "PostToolUse hook returned unsupported updatedMCPToolOutput",
        ),
    )


def test_exit_two_surfaces_feedback_to_model_without_blocking() -> None:
    # Rust test: exit_two_surfaces_feedback_to_model_without_blocking.
    parsed = parse_post_tool_use_completed(
        _handler(),
        _run_result(2, "", "post hook says pause"),
        "turn-1",
    )

    assert parsed.data == PostToolUseHandlerData(
        should_stop=False,
        stop_reason=None,
        additional_contexts_for_model=[],
        feedback_messages_for_model=["post hook says pause"],
    )
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "post hook says pause"),
    )


def test_continue_false_stops_with_reason() -> None:
    # Rust test: continue_false_stops_with_reason.
    parsed = parse_post_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"continue":false,"stopReason":"halt after bash output","reason":"post-tool hook says stop"}',
        ),
        "turn-1",
    )

    assert parsed.data == PostToolUseHandlerData(
        should_stop=True,
        stop_reason="halt after bash output",
        additional_contexts_for_model=[],
        feedback_messages_for_model=["post-tool hook says stop"],
    )
    assert parsed.completed.run.status == HookRunStatus.STOPPED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.STOP, "halt after bash output"),
    )


def test_plain_stdout_is_ignored_for_post_tool_use() -> None:
    # Rust test: plain_stdout_is_ignored_for_post_tool_use.
    parsed = parse_post_tool_use_completed(
        _handler(),
        _run_result(0, "plain text only"),
        "turn-1",
    )

    assert parsed.data == PostToolUseHandlerData()
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == ()


def test_preview_and_completed_run_ids_include_tool_use_id() -> None:
    # Rust test: preview_and_completed_run_ids_include_tool_use_id.
    run = hook_run_for_tool_use(_running_summary(_handler()), "tool-call-456")
    assert run.id == "post-tool-use:0:/tmp/hooks.json:tool-call-456"

    parsed = parse_post_tool_use_completed(
        _handler(),
        _run_result(0, ""),
        "turn-1",
    )
    completed = hook_completed_for_tool_use(parsed.completed, "tool-call-456")
    assert completed.run.id == run.id


def test_serialization_failure_run_ids_include_tool_use_id() -> None:
    # Rust test: serialization_failure_run_ids_include_tool_use_id.
    completed = serialization_failure_hook_events_for_tool_use(
        [_handler()],
        "turn-1",
        "serialize failed",
        "tool-call-456",
    )

    assert len(completed) == 1
    assert completed[0].run.id == "post-tool-use:0:/tmp/hooks.json:tool-call-456"
    assert completed[0].run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "serialize failed"),
    )


def test_post_tool_use_source_contract_failure_edges() -> None:
    # Rust source contracts from output_parser.rs and parse_completed.
    cases = [
        (
            '{"suppressOutput":true}',
            "PostToolUse hook returned unsupported suppressOutput",
        ),
        (
            '{"decision":"block"}',
            "PostToolUse hook returned decision:block without a non-empty reason",
        ),
        (
            '{"decision":"block","reason":"   "}',
            "PostToolUse hook returned decision:block without a non-empty reason",
        ),
        (
            '{"reason":"lonely"}',
            "PostToolUse hook returned reason without decision",
        ),
        (
            '{"decision":',
            "hook returned invalid post-tool-use JSON output",
        ),
    ]
    for stdout, message in cases:
        parsed = parse_post_tool_use_completed(_handler(), _run_result(0, stdout), "turn-1")
        assert parsed.data == PostToolUseHandlerData()
        assert parsed.completed.run.status == HookRunStatus.FAILED
        assert parsed.completed.run.entries == (
            HookOutputEntry(HookOutputEntryKind.ERROR, message),
        )

    missing_stderr = parse_post_tool_use_completed(_handler(), _run_result(2, "", ""), "turn-1")
    assert missing_stderr.completed.run.status == HookRunStatus.FAILED
    assert missing_stderr.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "PostToolUse hook exited with code 2 but did not write feedback to stderr",
        ),
    )

    errored = parse_post_tool_use_completed(
        _handler(),
        _run_result(0, "", error="spawn failed"),
        "turn-1",
    )
    assert errored.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "spawn failed"),
    )

    no_status = parse_post_tool_use_completed(_handler(), _run_result(None, "", ""), "turn-1")
    assert no_status.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"),
    )


def test_feedback_messages_join_in_order() -> None:
    # Rust source contract: PostToolUse::run joins feedback chunks with blank lines.
    assert (
        post_tool_use_feedback_message(
            [
                PostToolUseHandlerData(feedback_messages_for_model=["first"]),
                PostToolUseHandlerData(feedback_messages_for_model=["second", "third"]),
            ]
        )
        == "first\n\nsecond\n\nthird"
    )
    assert post_tool_use_feedback_message([PostToolUseHandlerData()]) is None
