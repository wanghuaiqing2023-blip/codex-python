"""Rust-derived tests for ``codex-hooks/src/events/session_start.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/events/session_start.rs``

Rust tests mirrored:
- ``plain_stdout_becomes_model_context``
- ``continue_false_preserves_context_for_later_turns``
- ``invalid_json_like_stdout_fails_instead_of_becoming_model_context``
- ``subagent_start_plain_stdout_becomes_model_context``
- ``subagent_start_continue_false_is_ignored``
"""

from __future__ import annotations

from pathlib import PurePosixPath
from types import SimpleNamespace

from pycodex.hooks import ParsedSessionStartHandler
from pycodex.hooks import SessionStartHandlerData
from pycodex.hooks import SessionStartSource
from pycodex.hooks import StartHookTarget
from pycodex.hooks import parse_session_start_completed
from pycodex.protocol import HookEventName
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookSource


def _handler(event_name: HookEventName = HookEventName.SESSION_START) -> SimpleNamespace:
    return SimpleNamespace(
        event_name=event_name,
        matcher=None,
        command="echo hook",
        timeout_sec=600,
        status_message=None,
        source_path=PurePosixPath("/tmp/hooks.json"),
        source=HookSource.USER,
        display_order=0,
        started_at=1,
    )


def _run_result(exit_code: int | None, stdout: str, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        started_at=1,
        completed_at=2,
        duration_ms=1,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        error=None,
    )


def test_session_start_source_as_str_and_target_matcher_input() -> None:
    # Rust crate/module/source contract: codex-hooks/src/events/session_start.rs
    # SessionStartSource::as_str and StartHookTarget::matcher_input.
    assert SessionStartSource.STARTUP.as_str() == "startup"
    assert SessionStartSource.RESUME.as_str() == "resume"
    assert SessionStartSource.CLEAR.as_str() == "clear"
    assert SessionStartSource.COMPACT.as_str() == "compact"
    assert StartHookTarget.SessionStart(SessionStartSource.RESUME).matcher_input() == "resume"
    assert (
        StartHookTarget.SubagentStart("turn-1", "agent-1", "reviewer").matcher_input()
        == "reviewer"
    )


def test_plain_stdout_becomes_model_context() -> None:
    # Rust crate/module/test: codex-hooks/src/events/session_start.rs
    # tests::plain_stdout_becomes_model_context.
    parsed = parse_session_start_completed(
        _handler(),
        _run_result(0, "hello from hook\n"),
        None,
    )

    assert parsed == ParsedSessionStartHandler(
        completed=parsed.completed,
        data=SessionStartHandlerData(
            should_stop=False,
            stop_reason=None,
            additional_contexts_for_model=["hello from hook"],
        ),
    )
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "hello from hook"),
    )


def test_continue_false_preserves_context_for_later_turns() -> None:
    # Rust test: continue_false_preserves_context_for_later_turns.
    parsed = parse_session_start_completed(
        _handler(),
        _run_result(
            0,
            '{"continue":false,"stopReason":"pause","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"do not inject"}}',
        ),
        None,
    )

    assert parsed.data == SessionStartHandlerData(
        should_stop=True,
        stop_reason="pause",
        additional_contexts_for_model=["do not inject"],
    )
    assert parsed.completed.run.status == HookRunStatus.STOPPED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "do not inject"),
        HookOutputEntry(HookOutputEntryKind.STOP, "pause"),
    )


def test_invalid_json_like_stdout_fails_instead_of_becoming_model_context() -> None:
    # Rust test: invalid_json_like_stdout_fails_instead_of_becoming_model_context.
    parsed = parse_session_start_completed(
        _handler(),
        _run_result(0, '{"hookSpecificOutput":{"hookEventName":"SessionStart"'),
        None,
    )

    assert parsed.data == SessionStartHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "hook returned invalid session start JSON output",
        ),
    )


def test_subagent_start_plain_stdout_becomes_model_context() -> None:
    # Rust test: subagent_start_plain_stdout_becomes_model_context.
    parsed = parse_session_start_completed(
        _handler(HookEventName.SUBAGENT_START),
        _run_result(0, "hello from subagent hook\n"),
        "turn-1",
    )

    assert parsed.data == SessionStartHandlerData(
        should_stop=False,
        stop_reason=None,
        additional_contexts_for_model=["hello from subagent hook"],
    )
    assert parsed.completed.turn_id == "turn-1"
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "hello from subagent hook"),
    )


def test_subagent_start_continue_false_is_ignored() -> None:
    # Rust test: subagent_start_continue_false_is_ignored.
    parsed = parse_session_start_completed(
        _handler(HookEventName.SUBAGENT_START),
        _run_result(
            0,
            '{"continue":false,"stopReason":"skip child","hookSpecificOutput":{"hookEventName":"SubagentStart","additionalContext":"child context"}}',
        ),
        "turn-1",
    )

    assert parsed.data == SessionStartHandlerData(
        should_stop=False,
        stop_reason=None,
        additional_contexts_for_model=["child context"],
    )
    assert parsed.completed.turn_id == "turn-1"
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "child context"),
    )
