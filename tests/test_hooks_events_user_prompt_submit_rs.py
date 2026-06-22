"""Rust-derived tests for ``codex-hooks/src/events/user_prompt_submit.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/events/user_prompt_submit.rs``

Rust tests mirrored:
- ``continue_false_preserves_context_for_later_turns``
- ``claude_block_decision_blocks_processing``
- ``claude_block_decision_requires_reason``
- ``exit_code_two_blocks_processing``
"""

from __future__ import annotations

from pathlib import PurePosixPath
from types import SimpleNamespace

from pycodex.hooks import ParsedUserPromptSubmitHandler
from pycodex.hooks import UserPromptSubmitHandlerData
from pycodex.hooks import parse_user_prompt_submit_completed
from pycodex.protocol import HookEventName
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookSource


def _handler() -> SimpleNamespace:
    return SimpleNamespace(
        event_name=HookEventName.USER_PROMPT_SUBMIT,
        matcher=None,
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


def test_continue_false_preserves_context_for_later_turns() -> None:
    # Rust crate/module/test: codex-hooks/src/events/user_prompt_submit.rs
    # tests::continue_false_preserves_context_for_later_turns.
    parsed = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(
            0,
            '{"continue":false,"stopReason":"pause","hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"do not inject"}}',
        ),
        "turn-1",
    )

    assert parsed == ParsedUserPromptSubmitHandler(
        completed=parsed.completed,
        data=UserPromptSubmitHandlerData(
            should_stop=True,
            stop_reason="pause",
            additional_contexts_for_model=["do not inject"],
        ),
    )
    assert parsed.completed.turn_id == "turn-1"
    assert parsed.completed.run.status == HookRunStatus.STOPPED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "do not inject"),
        HookOutputEntry(HookOutputEntryKind.STOP, "pause"),
    )


def test_claude_block_decision_blocks_processing() -> None:
    # Rust test: claude_block_decision_blocks_processing.
    parsed = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(
            0,
            '{"decision":"block","reason":"slow down","hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"do not inject"}}',
        ),
        "turn-1",
    )

    assert parsed.data == UserPromptSubmitHandlerData(
        should_stop=True,
        stop_reason="slow down",
        additional_contexts_for_model=["do not inject"],
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "do not inject"),
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "slow down"),
    )


def test_claude_block_decision_requires_reason() -> None:
    # Rust test: claude_block_decision_requires_reason.
    parsed = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(
            0,
            '{"decision":"block","hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"do not inject"}}',
        ),
        "turn-1",
    )

    assert parsed.data == UserPromptSubmitHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "UserPromptSubmit hook returned decision:block without a non-empty reason",
        ),
    )


def test_exit_code_two_blocks_processing() -> None:
    # Rust test: exit_code_two_blocks_processing.
    parsed = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(2, "", "blocked by policy\n"),
        "turn-1",
    )

    assert parsed.data == UserPromptSubmitHandlerData(
        should_stop=True,
        stop_reason="blocked by policy",
        additional_contexts_for_model=[],
    )
    assert parsed.completed.run.status == HookRunStatus.BLOCKED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.FEEDBACK, "blocked by policy"),
    )


def test_plain_stdout_becomes_model_context() -> None:
    # Rust source contract: parse_completed exit_code Some(0), non-JSON stdout branch.
    parsed = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(0, "remember this\n"),
        "turn-1",
    )

    assert parsed.data == UserPromptSubmitHandlerData(
        should_stop=False,
        stop_reason=None,
        additional_contexts_for_model=["remember this"],
    )
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "remember this"),
    )


def test_invalid_json_like_stdout_fails() -> None:
    # Rust source contract: output_parser::looks_like_json failure branch.
    parsed = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(0, '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit"'),
        "turn-1",
    )

    assert parsed.data == UserPromptSubmitHandlerData()
    assert parsed.completed.run.status == HookRunStatus.FAILED
    assert parsed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "hook returned invalid user prompt submit JSON output",
        ),
    )


def test_system_message_becomes_warning_and_exit_two_requires_stderr_reason() -> None:
    # Rust source contract: universal.system_message warning and exit code 2
    # without non-empty stderr is a failed run, not a block.
    parsed = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(
            0,
            '{"systemMessage":"heads up","hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"ctx"}}',
        ),
        "turn-1",
    )
    assert parsed.completed.run.status == HookRunStatus.COMPLETED
    assert parsed.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.WARNING, "heads up"),
        HookOutputEntry(HookOutputEntryKind.CONTEXT, "ctx"),
    )

    failed = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(2, "", "  \n"),
        "turn-1",
    )
    assert failed.data == UserPromptSubmitHandlerData()
    assert failed.completed.run.status == HookRunStatus.FAILED
    assert failed.completed.run.entries == (
        HookOutputEntry(
            HookOutputEntryKind.ERROR,
            "UserPromptSubmit hook exited with code 2 but did not write a blocking reason to stderr",
        ),
    )


def test_error_other_nonzero_and_missing_status_code_fail() -> None:
    # Rust source contract: CommandRunResult.error, other exit codes, and None
    # exit status map to failed HookOutputEntry::Error values.
    errored = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(0, "", error="spawn failed"),
        "turn-1",
    )
    assert errored.completed.run.status == HookRunStatus.FAILED
    assert errored.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "spawn failed"),
    )

    nonzero = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(7, "", ""),
        "turn-1",
    )
    assert nonzero.completed.run.status == HookRunStatus.FAILED
    assert nonzero.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited with code 7"),
    )

    missing = parse_user_prompt_submit_completed(
        _handler(),
        _run_result(None, "", ""),
        "turn-1",
    )
    assert missing.completed.run.status == HookRunStatus.FAILED
    assert missing.completed.run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"),
    )
