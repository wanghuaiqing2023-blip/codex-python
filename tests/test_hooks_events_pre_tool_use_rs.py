"""Rust-derived tests for ``codex-hooks/src/events/pre_tool_use.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/events/pre_tool_use.rs``

Rust tests mirrored include command input serialization, permission decision
handling, legacy decision handling, updated input ordering, stdout parsing,
exit-code blocking, and tool-use run id decoration.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from pathlib import PurePosixPath
from types import SimpleNamespace

from pycodex.hooks import PreToolUseHandlerData
from pycodex.hooks import PreToolUseRequest
from pycodex.hooks import SubagentHookContext
from pycodex.hooks import _running_summary
from pycodex.hooks import hook_completed_for_tool_use
from pycodex.hooks import hook_run_for_tool_use
from pycodex.hooks import latest_pre_tool_use_updated_input
from pycodex.hooks import parse_pre_tool_use_completed
from pycodex.hooks import pre_tool_use_command_input_json
from pycodex.hooks import serialization_failure_hook_events_for_tool_use
from pycodex.protocol import HookEventName
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookSource


def _handler() -> SimpleNamespace:
    return SimpleNamespace(
        event_name=HookEventName.PRE_TOOL_USE,
        matcher="^Bash$",
        command="echo hook",
        timeout_sec=5,
        status_message=None,
        source_path=PurePosixPath("/tmp/hooks.json"),
        source=HookSource.USER,
        display_order=0,
        started_at=1,
    )


def _run_result(
    exit_code: int | None,
    stdout: str,
    stderr: str = "",
    error: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        started_at=1,
        completed_at=2,
        duration_ms=1,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        error=error,
    )


def _request(tool_use_id: str = "tool-call-123") -> PreToolUseRequest:
    return PreToolUseRequest(
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
    )


def test_command_input_uses_request_tool_name_and_subagent_fields() -> None:
    # Rust crate/module/test: codex-hooks/src/events/pre_tool_use.rs
    # tests::command_input_uses_request_tool_name.
    request = _request()
    request.tool_name = "apply_patch"
    request.subagent = SubagentHookContext("agent-1", "reviewer")
    request.transcript_path = Path("/tmp/transcript.jsonl")

    payload = json.loads(pre_tool_use_command_input_json(request))

    assert payload["tool_name"] == "apply_patch"
    assert payload["tool_input"] == {"command": "echo hello"}
    assert payload["tool_use_id"] == "tool-call-123"
    assert payload["hook_event_name"] == "PreToolUse"
    assert payload["agent_id"] == "agent-1"
    assert payload["agent_type"] == "reviewer"
    assert payload["transcript_path"] == str(Path("/tmp/transcript.jsonl"))


def test_permission_decision_deny_blocks_processing() -> None:
    # Rust test: permission_decision_deny_blocks_processing.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"do not run that"}}',
        ),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData(
        should_block=True,
        block_reason="do not run that",
        additional_contexts_for_model=[],
        updated_input=None,
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "do not run that"),
    )


def test_permission_decision_allow_can_update_input() -> None:
    # Rust test: permission_decision_allow_can_update_input.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"echo rewritten"}}}',
        ),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData(
        should_block=False,
        block_reason=None,
        additional_contexts_for_model=[],
        updated_input={"command": "echo rewritten"},
    )
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == ()


def test_last_completed_updated_input_wins() -> None:
    # Rust test: last_completed_updated_input_wins.
    later_configured = parse_pre_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"echo configured later"}}}',
        ),
        "turn-1",
    )
    earlier_configured = parse_pre_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"echo finished later"}}}',
        ),
        "turn-1",
    )

    assert latest_pre_tool_use_updated_input(
        [
            replace(later_configured, completion_order=0),
            replace(earlier_configured, completion_order=1),
        ]
    ) == {"command": "echo finished later"}


def test_permission_decision_allow_without_updated_input_fails_open() -> None:
    # Rust test: permission_decision_allow_without_updated_input_fails_open.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}',
        ),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "PreToolUse hook returned unsupported permissionDecision:allow",
        ),
    )


def test_deprecated_block_decision_blocks_processing() -> None:
    # Rust test: deprecated_block_decision_blocks_processing.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(0, '{"decision":"block","reason":"do not run that"}'),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData(
        should_block=True,
        block_reason="do not run that",
        additional_contexts_for_model=[],
        updated_input=None,
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "do not run that"),
    )


def test_deprecated_block_decision_with_additional_context_blocks_processing() -> None:
    # Rust test: deprecated_block_decision_with_additional_context_blocks_processing.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"decision":"block","reason":"do not run that","hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"remember this"}}',
        ),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData(
        should_block=True,
        block_reason="do not run that",
        additional_contexts_for_model=["remember this"],
        updated_input=None,
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "remember this"),
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "do not run that"),
    )


def test_unsupported_permission_decision_fails_open() -> None:
    # Rust test: unsupported_permission_decision_fails_open.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"please confirm"}}',
        ),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "PreToolUse hook returned unsupported permissionDecision:ask",
        ),
    )


def test_deprecated_approve_decision_fails_open() -> None:
    # Rust test: deprecated_approve_decision_fails_open.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(0, '{"decision":"approve"}'),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "PreToolUse hook returned unsupported decision:approve",
        ),
    )


def test_additional_context_is_recorded() -> None:
    # Rust test: additional_context_is_recorded.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"do not run that","additionalContext":"nope"}}',
        ),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData(
        should_block=True,
        block_reason="do not run that",
        additional_contexts_for_model=["nope"],
        updated_input=None,
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "nope"),
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "do not run that"),
    )


def test_plain_stdout_is_ignored() -> None:
    # Rust test: plain_stdout_is_ignored.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(0, "hook ran successfully\n"),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData()
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == ()


def test_invalid_json_like_stdout_fails_instead_of_becoming_noop() -> None:
    # Rust test: invalid_json_like_stdout_fails_instead_of_becoming_noop.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(0, '{"decision":\n'),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "hook returned invalid pre-tool-use JSON output",
        ),
    )


def test_exit_code_two_blocks_processing() -> None:
    # Rust test: exit_code_two_blocks_processing.
    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(2, "", "blocked by policy\n"),
        "turn-1",
    )

    assert parsed.data == PreToolUseHandlerData(
        should_block=True,
        block_reason="blocked by policy",
        additional_contexts_for_model=[],
        updated_input=None,
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "blocked by policy"),
    )


def test_preview_and_completed_run_ids_include_tool_use_id() -> None:
    # Rust test: preview_and_completed_run_ids_include_tool_use_id.
    run = hook_run_for_tool_use(_running_summary(_handler()), "tool-call-123")
    assert run.id == "pre-tool-use:0:/tmp/hooks.json:tool-call-123"

    parsed = parse_pre_tool_use_completed(
        _handler(),
        _run_result(0, ""),
        "turn-1",
    )
    completed = hook_completed_for_tool_use(parsed.completed, "tool-call-123")
    assert completed.run.id == run.id


def test_serialization_failure_run_ids_include_tool_use_id() -> None:
    # Rust test: serialization_failure_run_ids_include_tool_use_id.
    completed = serialization_failure_hook_events_for_tool_use(
        [_handler()],
        "turn-1",
        "serialize failed",
        "tool-call-123",
    )

    assert len(completed) == 1
    assert completed[0].run.id == "pre-tool-use:0:/tmp/hooks.json:tool-call-123"
    assert completed[0].run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "serialize failed"),
    )


def test_pre_tool_use_source_contract_failure_edges() -> None:
    # Rust source contracts from output_parser.rs and parse_completed.
    cases = [
        (
            '{"continue":false}',
            "PreToolUse hook returned unsupported continue:false",
        ),
        (
            '{"stopReason":"later"}',
            "PreToolUse hook returned unsupported stopReason",
        ),
        (
            '{"suppressOutput":true}',
            "PreToolUse hook returned unsupported suppressOutput",
        ),
        (
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{}}}',
            "PreToolUse hook returned updatedInput without permissionDecision:allow",
        ),
        (
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny"}}',
            "PreToolUse hook returned permissionDecision:deny without a non-empty permissionDecisionReason",
        ),
        (
            '{"reason":"lonely"}',
            "PreToolUse hook returned reason without decision",
        ),
    ]
    for stdout, message in cases:
        parsed = parse_pre_tool_use_completed(_handler(), _run_result(0, stdout), "turn-1")
        assert parsed.data == PreToolUseHandlerData()
        assert parsed.completed.run.status == HookRunStatus.FAILED
        assert parsed.completed.run.entries == (
            HookOutputEntry(HookOutputEntryKind.ERROR, message),
        )

    missing_stderr = parse_pre_tool_use_completed(_handler(), _run_result(2, "", ""), "turn-1")
    assert missing_stderr.completed.run.status == HookRunStatus.FAILED
    assert missing_stderr.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "PreToolUse hook exited with code 2 but did not write a blocking reason to stderr",
        ),
    )

    errored = parse_pre_tool_use_completed(
        _handler(),
        _run_result(0, "", error="spawn failed"),
        "turn-1",
    )
    assert errored.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "spawn failed"),
    )
