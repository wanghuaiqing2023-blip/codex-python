"""Rust-derived tests for ``codex-hooks/src/events/stop.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/events/stop.rs``

Rust tests mirrored:
- ``block_decision_with_reason_sets_continuation_prompt``
- ``block_decision_without_reason_is_invalid``
- ``continue_false_overrides_block_decision``
- ``exit_code_two_uses_stderr_feedback_only``
- ``exit_code_two_without_stderr_does_not_block``
- ``block_decision_with_blank_reason_fails_instead_of_blocking``
- ``invalid_stdout_fails_instead_of_silently_nooping``
- ``aggregate_results_concatenates_blocking_reasons_in_declaration_order``
"""

from __future__ import annotations

from pathlib import PurePosixPath
from types import SimpleNamespace

from pycodex.hooks import ParsedStopHandler
from pycodex.hooks import StopHandlerData
from pycodex.hooks import StopHookTarget
from pycodex.hooks import aggregate_stop_results
from pycodex.hooks import parse_stop_completed
from pycodex.protocol import HookEventName
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookPromptFragment
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookSource


def _handler(event_name: HookEventName = HookEventName.STOP) -> SimpleNamespace:
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


def test_stop_target_matcher_input() -> None:
    # Rust crate/module/source contract: codex-hooks/src/events/stop.rs
    # StopHookTarget::event_name and StopHookTarget::matcher_input.
    assert StopHookTarget.Stop().event_name == HookEventName.STOP
    assert StopHookTarget.Stop().matcher_input() is None
    target = StopHookTarget.SubagentStop("agent-1", "reviewer", None)
    assert target.event_name == HookEventName.SUBAGENT_STOP
    assert target.matcher_input() == "reviewer"


def test_block_decision_with_reason_sets_continuation_prompt() -> None:
    # Rust test: block_decision_with_reason_sets_continuation_prompt.
    parsed = parse_stop_completed(
        _handler(),
        _run_result(0, '{"decision":"block","reason":"retry with tests"}'),
        "turn-1",
    )

    assert parsed == ParsedStopHandler(
        completed=parsed.completed,
        data=StopHandlerData(
            should_stop=False,
            stop_reason=None,
            should_block=True,
            block_reason="retry with tests",
            continuation_fragments=[
                HookPromptFragment(
                    text="retry with tests",
                    hook_run_id=parsed.completed.run.id,
                )
            ],
        ),
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "retry with tests"),
    )


def test_block_decision_without_reason_is_invalid() -> None:
    # Rust test: block_decision_without_reason_is_invalid.
    parsed = parse_stop_completed(
        _handler(),
        _run_result(0, '{"decision":"block"}'),
        "turn-1",
    )

    assert parsed.data == StopHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "Stop hook returned decision:block without a non-empty reason",
        ),
    )


def test_continue_false_overrides_block_decision() -> None:
    # Rust test: continue_false_overrides_block_decision.
    parsed = parse_stop_completed(
        _handler(),
        _run_result(
            0,
            '{"continue":false,"stopReason":"done","decision":"block","reason":"keep going"}',
        ),
        "turn-1",
    )

    assert parsed.data == StopHandlerData(
        should_stop=True,
        stop_reason="done",
        should_block=False,
        block_reason=None,
        continuation_fragments=[],
    )
    assert parsed.completed.run.status == HookRunStatus.STOPPED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.STOP, "done"),
    )


def test_exit_code_two_uses_stderr_feedback_only() -> None:
    # Rust test: exit_code_two_uses_stderr_feedback_only.
    parsed = parse_stop_completed(
        _handler(),
        _run_result(2, "ignored stdout", "retry with tests"),
        "turn-1",
    )

    assert parsed.data == StopHandlerData(
        should_stop=False,
        stop_reason=None,
        should_block=True,
        block_reason="retry with tests",
        continuation_fragments=[
            HookPromptFragment(
                text="retry with tests",
                hook_run_id=parsed.completed.run.id,
            )
        ],
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "retry with tests"),
    )


def test_exit_code_two_without_stderr_does_not_block() -> None:
    # Rust test: exit_code_two_without_stderr_does_not_block.
    parsed = parse_stop_completed(
        _handler(),
        _run_result(2, "", "   "),
        None,
    )

    assert parsed.data == StopHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "Stop hook exited with code 2 but did not write a continuation prompt to stderr",
        ),
    )


def test_block_decision_with_blank_reason_fails_instead_of_blocking() -> None:
    # Rust test: block_decision_with_blank_reason_fails_instead_of_blocking.
    parsed = parse_stop_completed(
        _handler(),
        _run_result(0, '{"decision":"block","reason":"   "}'),
        "turn-1",
    )

    assert parsed.data == StopHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "Stop hook returned decision:block without a non-empty reason",
        ),
    )


def test_invalid_stdout_fails_instead_of_silently_nooping() -> None:
    # Rust test: invalid_stdout_fails_instead_of_silently_nooping.
    parsed = parse_stop_completed(
        _handler(),
        _run_result(0, "not json"),
        "turn-1",
    )

    assert parsed.data == StopHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "hook returned invalid stop hook JSON output",
        ),
    )


def test_subagent_stop_error_texts_follow_rust_event_name() -> None:
    # Rust source contract: parse_completed branches choose Stop vs
    # SubagentStop user-visible error strings from handler.event_name.
    invalid = parse_stop_completed(
        _handler(HookEventName.SUBAGENT_STOP),
        _run_result(0, "not json"),
        "turn-1",
    )
    assert invalid.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "hook returned invalid subagent stop hook JSON output",
        ),
    )

    missing = parse_stop_completed(
        _handler(HookEventName.SUBAGENT_STOP),
        _run_result(2, "", ""),
        "turn-1",
    )
    assert missing.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "SubagentStop hook exited with code 2 but did not write a continuation prompt to stderr",
        ),
    )


def test_process_error_other_nonzero_and_missing_status_fail() -> None:
    # Rust source contract: CommandRunResult.error, other exit codes, and None
    # exit status map to failed HookOutputEntry::Error values.
    errored = parse_stop_completed(
        _handler(),
        _run_result(0, "", error="spawn failed"),
        "turn-1",
    )
    assert errored.completed.run.status == HookRunStatus.FAILED
    assert errored.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "spawn failed"),
    )

    nonzero = parse_stop_completed(
        _handler(),
        _run_result(7, "", ""),
        "turn-1",
    )
    assert nonzero.completed.run.status == HookRunStatus.FAILED
    assert nonzero.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited with code 7"),
    )

    missing = parse_stop_completed(
        _handler(),
        _run_result(None, "", ""),
        "turn-1",
    )
    assert missing.completed.run.status == HookRunStatus.FAILED
    assert missing.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"),
    )


def test_aggregate_results_concatenates_blocking_reasons_in_declaration_order() -> None:
    # Rust test: aggregate_results_concatenates_blocking_reasons_in_declaration_order.
    aggregate = aggregate_stop_results(
        [
            StopHandlerData(
                should_stop=False,
                stop_reason=None,
                should_block=True,
                block_reason="first",
                continuation_fragments=[
                    HookPromptFragment.from_single_hook("first", "run-1")
                ],
            ),
            StopHandlerData(
                should_stop=False,
                stop_reason=None,
                should_block=True,
                block_reason="second",
                continuation_fragments=[
                    HookPromptFragment.from_single_hook("second", "run-2")
                ],
            ),
        ]
    )

    assert aggregate == StopHandlerData(
        should_stop=False,
        stop_reason=None,
        should_block=True,
        block_reason="first\n\nsecond",
        continuation_fragments=[
            HookPromptFragment.from_single_hook("first", "run-1"),
            HookPromptFragment.from_single_hook("second", "run-2"),
        ],
    )


def test_aggregate_stop_takes_precedence_over_block() -> None:
    # Rust source contract: aggregate_results sets should_block only when no
    # handler requested stop, and drops continuation fragments in that case.
    aggregate = aggregate_stop_results(
        [
            StopHandlerData(
                should_stop=False,
                stop_reason=None,
                should_block=True,
                block_reason="retry",
                continuation_fragments=[
                    HookPromptFragment.from_single_hook("retry", "run-1")
                ],
            ),
            StopHandlerData(
                should_stop=True,
                stop_reason="done",
                should_block=False,
                block_reason=None,
                continuation_fragments=[],
            ),
        ]
    )

    assert aggregate == StopHandlerData(
        should_stop=True,
        stop_reason="done",
        should_block=False,
        block_reason=None,
        continuation_fragments=[],
    )
