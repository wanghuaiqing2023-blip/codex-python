"""Rust-derived tests for ``codex-hooks/src/events/compact.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/events/compact.rs``

Rust tests mirrored:
- ``pre_compact_input_includes_lifecycle_metadata``
- ``post_compact_input_includes_lifecycle_metadata``
- ``block_decision_is_not_supported_for_pre_compact``
- ``continue_false_stops_before_compaction``
- ``post_compact_continue_false_stops_after_compaction``
- ``pre_compact_ignores_plain_stdout``
- ``post_compact_ignores_plain_stdout``
"""

from __future__ import annotations

import json
from pathlib import Path
from pathlib import PurePosixPath
from types import SimpleNamespace

from pycodex.hooks import CompactHandlerData
from pycodex.hooks import PostCompactRequest
from pycodex.hooks import PreCompactRequest
from pycodex.hooks import SubagentHookContext
from pycodex.hooks import parse_post_compact_completed
from pycodex.hooks import parse_pre_compact_completed
from pycodex.hooks import post_compact_command_input_json
from pycodex.hooks import pre_compact_command_input_json
from pycodex.protocol import HookEventName
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookSource


def _handler(event_name: HookEventName) -> SimpleNamespace:
    return SimpleNamespace(
        event_name=event_name,
        matcher=None,
        command="python3 compact_hook.py",
        timeout_sec=5,
        status_message="running compact hook",
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


def _pre_request() -> PreCompactRequest:
    return PreCompactRequest(
        session_id="00000000-0000-4000-8000-000000000001",
        turn_id="turn-1",
        subagent=None,
        cwd=Path("/tmp"),
        transcript_path=None,
        model="gpt-test",
        trigger="manual",
    )


def _post_request() -> PostCompactRequest:
    return PostCompactRequest(
        session_id="00000000-0000-4000-8000-000000000002",
        turn_id="turn-1",
        subagent=None,
        cwd=Path("/tmp"),
        transcript_path=None,
        model="gpt-test",
        trigger="manual",
    )


def test_pre_compact_input_includes_lifecycle_metadata() -> None:
    # Rust test: pre_compact_input_includes_lifecycle_metadata.
    payload = json.loads(pre_compact_command_input_json(_pre_request()))

    assert payload == {
        "session_id": "00000000-0000-4000-8000-000000000001",
        "turn_id": "turn-1",
        "transcript_path": None,
        "cwd": str(Path("/tmp")),
        "hook_event_name": "PreCompact",
        "model": "gpt-test",
        "trigger": "manual",
    }


def test_post_compact_input_includes_lifecycle_metadata() -> None:
    # Rust test: post_compact_input_includes_lifecycle_metadata.
    payload = json.loads(post_compact_command_input_json(_post_request()))

    assert payload == {
        "session_id": "00000000-0000-4000-8000-000000000002",
        "turn_id": "turn-1",
        "transcript_path": None,
        "cwd": str(Path("/tmp")),
        "hook_event_name": "PostCompact",
        "model": "gpt-test",
        "trigger": "manual",
    }


def test_compact_command_input_includes_subagent_fields_when_present() -> None:
    # Rust source contract: SubagentCommandInputFields adds optional agent fields.
    request = _pre_request()
    request.subagent = SubagentHookContext("agent-1", "reviewer")
    request.transcript_path = Path("/tmp/transcript.jsonl")

    payload = json.loads(pre_compact_command_input_json(request))

    assert payload["agent_id"] == "agent-1"
    assert payload["agent_type"] == "reviewer"
    assert payload["transcript_path"] == str(Path("/tmp/transcript.jsonl"))


def test_block_decision_is_not_supported_for_pre_compact() -> None:
    # Rust test: block_decision_is_not_supported_for_pre_compact.
    parsed = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(0, '{"decision":"block","reason":"policy blocked compaction"}'),
        "turn-1",
    )

    assert parsed.data == CompactHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "hook returned invalid PreCompact hook JSON output",
        ),
    )


def test_continue_false_stops_before_compaction() -> None:
    # Rust test: continue_false_stops_before_compaction.
    parsed = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(0, '{"continue":false,"stopReason":"nope"}'),
        "turn-1",
    )

    assert parsed.data == CompactHandlerData(should_stop=True, stop_reason="nope")
    assert parsed.completed.run.status == HookRunStatus.STOPPED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.STOP, "nope"),
    )


def test_post_compact_continue_false_stops_after_compaction() -> None:
    # Rust test: post_compact_continue_false_stops_after_compaction.
    parsed = parse_post_compact_completed(
        _handler(HookEventName.POST_COMPACT),
        _run_result(0, '{"continue":false,"stopReason":"pause after compact"}'),
        "turn-1",
    )

    assert parsed.data == CompactHandlerData(
        should_stop=True,
        stop_reason="pause after compact",
    )
    assert parsed.completed.run.status == HookRunStatus.STOPPED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.STOP, "pause after compact"),
    )


def test_continue_false_without_reason_uses_event_default_message() -> None:
    # Rust source contract: parse_completed uses event-specific default stop text.
    pre = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(0, '{"continue":false}'),
        "turn-1",
    )
    post = parse_post_compact_completed(
        _handler(HookEventName.POST_COMPACT),
        _run_result(0, '{"continue":false}'),
        "turn-1",
    )

    assert pre.data == CompactHandlerData(should_stop=True, stop_reason=None)
    assert pre.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.STOP, "PreCompact hook stopped execution"),
    )
    assert post.data == CompactHandlerData(should_stop=True, stop_reason=None)
    assert post.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.STOP, "PostCompact hook stopped execution"),
    )


def test_system_message_warns_and_suppress_output_is_ignored() -> None:
    # Rust source contract: universal systemMessage is warning; suppressOutput is parsed but ignored.
    parsed = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(0, '{"systemMessage":"heads up","suppressOutput":true}'),
        "turn-1",
    )

    assert parsed.data == CompactHandlerData()
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.WARNING, "heads up"),
    )


def test_plain_stdout_is_ignored_for_pre_and_post_compact() -> None:
    # Rust tests: pre_compact_ignores_plain_stdout and post_compact_ignores_plain_stdout.
    pre = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(0, "checking compact policy\n"),
        "turn-1",
    )
    post = parse_post_compact_completed(
        _handler(HookEventName.POST_COMPACT),
        _run_result(0, "logged compact summary\n"),
        "turn-1",
    )

    assert pre.data == CompactHandlerData()
    assert pre.completed.run.status == HookRunStatus.COMPLETED
    assert pre.completed.run.entries == ()
    assert post.data == CompactHandlerData()
    assert post.completed.run.status == HookRunStatus.COMPLETED
    assert post.completed.run.entries == ()


def test_invalid_json_like_stdout_fails() -> None:
    # Rust source contract: JSON-looking stdout that does not match compact schema fails.
    cases = [
        (HookEventName.PRE_COMPACT, parse_pre_compact_completed, '{"hookSpecificOutput":{}}', "PreCompact"),
        (HookEventName.POST_COMPACT, parse_post_compact_completed, '{"stopReason":7}', "PostCompact"),
        (HookEventName.POST_COMPACT, parse_post_compact_completed, "[1,2,3]", "PostCompact"),
    ]

    for event_name, parse_completed, stdout, label in cases:
        parsed = parse_completed(_handler(event_name), _run_result(0, stdout), "turn-1")
        assert parsed.data == CompactHandlerData()
        assert parsed.completed.run.status == HookRunStatus.FAILED
        assert parsed.completed.run.entries == (
            HookOutputEntry(
                HookOutputEntryKind.ERROR,
                f"hook returned invalid {label} hook JSON output",
            ),
        )


def test_process_error_nonzero_and_missing_status_fail() -> None:
    # Rust source contract: error, nonzero exit, and missing status become failed hook events.
    errored = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(0, "", error="spawn failed"),
        "turn-1",
    )
    nonzero_stderr = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(7, "", "bad compact\n"),
        "turn-1",
    )
    nonzero_default = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(8, "", ""),
        "turn-1",
    )
    missing_status = parse_pre_compact_completed(
        _handler(HookEventName.PRE_COMPACT),
        _run_result(None, "", ""),
        "turn-1",
    )

    assert errored.completed.run.status == HookRunStatus.FAILED
    assert errored.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "spawn failed"),
    )
    assert nonzero_stderr.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "bad compact"),
    )
    assert nonzero_default.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited with code 8"),
    )
    assert missing_status.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "hook process terminated without an exit code",
        ),
    )
