"""Rust-derived tests for ``codex-hooks/src/events/permission_request.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/events/permission_request.rs``

Rust tests mirrored:
- ``permission_request_deny_overrides_earlier_allow``
- ``permission_request_returns_allow_when_no_handler_denies``
- ``permission_request_returns_none_when_no_handler_decides``
"""

from __future__ import annotations

import json
from pathlib import Path
from pathlib import PurePosixPath
from types import SimpleNamespace

from pycodex.hooks import PermissionRequestDecision
from pycodex.hooks import PermissionRequestHandlerData
from pycodex.hooks import PermissionRequestRequest
from pycodex.hooks import SubagentHookContext
from pycodex.hooks import _running_summary
from pycodex.hooks import hook_completed_for_tool_use
from pycodex.hooks import hook_run_for_tool_use
from pycodex.hooks import parse_permission_request_completed
from pycodex.hooks import permission_request_command_input_json
from pycodex.hooks import resolve_permission_request_decision
from pycodex.hooks import serialization_failure_hook_events_for_tool_use
from pycodex.protocol import HookEventName
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookSource


def _handler() -> SimpleNamespace:
    return SimpleNamespace(
        event_name=HookEventName.PERMISSION_REQUEST,
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


def _request(run_id_suffix: str = "tool-call-123") -> PermissionRequestRequest:
    return PermissionRequestRequest(
        session_id="thread-1",
        turn_id="turn-1",
        subagent=None,
        cwd=Path("/tmp"),
        transcript_path=None,
        model="gpt-test",
        permission_mode="default",
        tool_name="Bash",
        matcher_aliases=[],
        run_id_suffix=run_id_suffix,
        tool_input={"command": "echo hello"},
    )


def test_command_input_uses_request_tool_name_and_subagent_fields() -> None:
    # Rust crate/module/source contract: build_command_input.
    request = _request("call-apply-patch")
    request.tool_name = "apply_patch"
    request.subagent = SubagentHookContext("agent-1", "reviewer")
    request.transcript_path = Path("/tmp/transcript.jsonl")

    payload = json.loads(permission_request_command_input_json(request))

    assert payload["tool_name"] == "apply_patch"
    assert payload["tool_input"] == {"command": "echo hello"}
    assert payload["hook_event_name"] == "PermissionRequest"
    assert "run_id_suffix" not in payload
    assert payload["agent_id"] == "agent-1"
    assert payload["agent_type"] == "reviewer"
    assert payload["transcript_path"] == str(Path("/tmp/transcript.jsonl"))


def test_permission_request_deny_overrides_earlier_allow() -> None:
    # Rust test: permission_request_deny_overrides_earlier_allow.
    assert resolve_permission_request_decision(
        [
            PermissionRequestDecision.Allow(),
            PermissionRequestDecision.Deny("repo deny"),
        ]
    ) == PermissionRequestDecision.Deny("repo deny")


def test_permission_request_returns_allow_when_no_handler_denies() -> None:
    # Rust test: permission_request_returns_allow_when_no_handler_denies.
    assert resolve_permission_request_decision(
        [
            PermissionRequestDecision.Allow(),
            PermissionRequestDecision.Allow(),
        ]
    ) == PermissionRequestDecision.Allow()


def test_permission_request_returns_none_when_no_handler_decides() -> None:
    # Rust test: permission_request_returns_none_when_no_handler_decides.
    assert resolve_permission_request_decision([]) is None


def test_permission_request_allow_and_deny_parse_completed() -> None:
    # Rust source contract: parse_completed maps hook decisions to allow/deny.
    allowed = parse_permission_request_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}',
        ),
        "turn-1",
    )
    assert allowed.data == PermissionRequestHandlerData(PermissionRequestDecision.Allow())
    assert allowed.completed.run.status == HookRunStatus.COMPLETED
    assert allowed.completed.run.entries == ()

    denied = parse_permission_request_completed(
        _handler(),
        _run_result(
            0,
            '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny","message":"nope"}}}',
        ),
        "turn-1",
    )
    assert denied.data == PermissionRequestHandlerData(PermissionRequestDecision.Deny("nope"))
    assert denied.completed.run.status == HookRunStatus.BLOCKED
    assert denied.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "nope"),
    )


def test_permission_request_deny_defaults_message_and_system_message_warns() -> None:
    # Rust output_parser.rs contract: blank/missing denial message defaults.
    parsed = parse_permission_request_completed(
        _handler(),
        _run_result(
            0,
            '{"systemMessage":"heads up","hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny","message":"   "}}}',
        ),
        "turn-1",
    )

    assert parsed.data == PermissionRequestHandlerData(
        PermissionRequestDecision.Deny("PermissionRequest hook denied approval")
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.WARNING, "heads up"),
        HookOutputEntry(
            HookOutputEntryKind.FEEDBACK,
            "PermissionRequest hook denied approval",
        ),
    )


def test_reserved_permission_request_fields_fail_closed() -> None:
    # Rust output_parser.rs tests reject reserved decision fields.
    cases = [
        (
            '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow","updatedInput":{}}}}',
            "PermissionRequest hook returned unsupported updatedInput",
        ),
        (
            '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow","updatedPermissions":{}}}}',
            "PermissionRequest hook returned unsupported updatedPermissions",
        ),
        (
            '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow","interrupt":true}}}',
            "PermissionRequest hook returned unsupported interrupt:true",
        ),
    ]
    for stdout, message in cases:
        parsed = parse_permission_request_completed(_handler(), _run_result(0, stdout), "turn-1")
        assert parsed.data == PermissionRequestHandlerData()
        assert parsed.completed.run.status == HookRunStatus.FAILED
        assert parsed.completed.run.entries == (
            HookOutputEntry(HookOutputEntryKind.ERROR, message),
        )


def test_permission_request_universal_invalid_and_invalid_json() -> None:
    # Rust output_parser.rs contracts for unsupported universal fields.
    cases = [
        ('{"continue":false}', "PermissionRequest hook returned unsupported continue:false"),
        ('{"stopReason":"later"}', "PermissionRequest hook returned unsupported stopReason"),
        ('{"suppressOutput":true}', "PermissionRequest hook returned unsupported suppressOutput"),
        ('{"hookSpecificOutput":', "hook returned invalid permission-request JSON output"),
    ]
    for stdout, message in cases:
        parsed = parse_permission_request_completed(_handler(), _run_result(0, stdout), "turn-1")
        assert parsed.data == PermissionRequestHandlerData()
        assert parsed.completed.run.status == HookRunStatus.FAILED
        assert parsed.completed.run.entries == (
            HookOutputEntry(HookOutputEntryKind.ERROR, message),
        )


def test_exit_code_two_blocks_and_missing_stderr_fails() -> None:
    # Rust source contract: exit code 2 denies only with non-empty stderr.
    denied = parse_permission_request_completed(
        _handler(),
        _run_result(2, "", "blocked by policy\n"),
        "turn-1",
    )
    assert denied.data == PermissionRequestHandlerData(
        PermissionRequestDecision.Deny("blocked by policy")
    )
    assert denied.completed.run.status == HookRunStatus.BLOCKED
    assert denied.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "blocked by policy"),
    )

    failed = parse_permission_request_completed(_handler(), _run_result(2, "", ""), "turn-1")
    assert failed.data == PermissionRequestHandlerData()
    assert failed.completed.run.status == HookRunStatus.FAILED
    assert failed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "PermissionRequest hook exited with code 2 but did not write a denial reason to stderr",
        ),
    )


def test_permission_request_process_error_nonzero_and_missing_status() -> None:
    # Rust source contract: process error, other exit code, and no status fail.
    errored = parse_permission_request_completed(
        _handler(),
        _run_result(0, "", error="spawn failed"),
        "turn-1",
    )
    assert errored.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "spawn failed"),
    )

    nonzero = parse_permission_request_completed(_handler(), _run_result(7, "", ""), "turn-1")
    assert nonzero.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited with code 7"),
    )

    missing = parse_permission_request_completed(_handler(), _run_result(None, "", ""), "turn-1")
    assert missing.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"),
    )


def test_permission_request_run_ids_include_suffix() -> None:
    # Rust source contract: preview/completed/serialization failure ids append run_id_suffix.
    run = hook_run_for_tool_use(_running_summary(_handler()), "tool-call-123")
    assert run.id == "permission-request:0:/tmp/hooks.json:tool-call-123"

    parsed = parse_permission_request_completed(_handler(), _run_result(0, ""), "turn-1")
    completed = hook_completed_for_tool_use(parsed.completed, "tool-call-123")
    assert completed.run.id == run.id

    failed = serialization_failure_hook_events_for_tool_use(
        [_handler()],
        "turn-1",
        "serialize failed",
        "tool-call-123",
    )
    assert failed[0].run.id == run.id
    assert failed[0].run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "serialize failed"),
    )
