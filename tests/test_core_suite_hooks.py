"""Rust integration parity for ``core/tests/suite/hooks.rs``.

The Rust file exercises hook behavior through a remote Codex harness. Python's
portable parity boundary is the hook-runtime request/outcome layer plus the tool
orchestrator/router tests that consume these results. These tests keep the Rust
integration cases anchored in one suite-level mapping without pretending to run
the Rust SSE fixture stack.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.core.hook_runtime import (
    HookRequestContext,
    PostToolUseHookOutcome,
    SessionStartTarget,
    StopTarget,
    additional_context_messages,
    build_permission_request_request,
    build_post_compact_request,
    build_post_tool_use_request,
    build_pre_compact_request,
    build_pre_tool_use_request,
    build_session_start_request,
    build_stop_request,
    build_user_prompt_submit_request,
    hook_permission_mode,
    post_tool_use_replacement_text,
    pre_tool_use_result_from_outcome,
)
from pycodex.core.tools.hook_names import HookToolName
from pycodex.protocol.items import (
    HookPromptFragment,
    build_hook_prompt_message,
    parse_hook_prompt_message,
)

FIRST_CONTINUATION_PROMPT = "Retry with exactly the phrase meow meow meow."
SECOND_CONTINUATION_PROMPT = "Now tighten it to just: meow."
BLOCKED_PROMPT_CONTEXT = "Remember the blocked lighthouse note."


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


def test_stop_hook_prompts_persist_multiple_fragments_and_active_state(hook_context: HookRequestContext) -> None:
    # Rust tests: stop_hook_can_block_multiple_times_in_same_turn,
    # stop_hook_spills_large_continuation_prompt,
    # resumed_thread_keeps_stop_continuation_prompt_in_history,
    # multiple_blocking_stop_hooks_persist_multiple_hook_prompt_fragments.
    first = build_stop_request(
        hook_context,
        stop_hook_active=False,
        last_assistant_message="draft answer",
        target=StopTarget.stop(),
    )
    second = build_stop_request(
        hook_context,
        stop_hook_active=True,
        last_assistant_message="revised answer",
        target=StopTarget.stop(),
    )

    fragments = (
        HookPromptFragment.from_single_hook(FIRST_CONTINUATION_PROMPT, "hook-run-1"),
        HookPromptFragment.from_single_hook(SECOND_CONTINUATION_PROMPT, "hook-run-2"),
    )
    message = build_hook_prompt_message(fragments)
    parsed = parse_hook_prompt_message("hook-message", message.content)

    assert first.stop_hook_active is False
    assert second.stop_hook_active is True
    assert first.last_assistant_message == "draft answer"
    assert parsed is not None
    assert [fragment.text for fragment in parsed.fragments] == [FIRST_CONTINUATION_PROMPT, SECOND_CONTINUATION_PROMPT]
    assert [fragment.hook_run_id for fragment in parsed.fragments] == ["hook-run-1", "hook-run-2"]


@pytest.mark.parametrize("source", ["startup", "resume", "compact"])
def test_session_start_payloads_include_materialized_transcript_and_order_context(
    hook_context: HookRequestContext,
    source: str,
) -> None:
    # Rust tests: session_start_hook_sees_materialized_transcript_path,
    # session_start_runs_before_user_prompt_submit_on_first_turn,
    # compact_session_start_hook_records_additional_context_for_next_turn,
    # resumed_thread_runs_resume_then_compact_session_start_hooks.
    session_start = build_session_start_request(hook_context, target=SessionStartTarget.session_start(source))
    prompt_submit = build_user_prompt_submit_request(hook_context, prompt="hello")
    pre_compact = build_pre_compact_request(hook_context, trigger="manual")
    post_compact = build_post_compact_request(hook_context, trigger="auto")

    assert session_start.session_id == hook_context.session_id
    assert session_start.target.source == source
    assert session_start.transcript_path is not None
    assert Path(session_start.transcript_path).exists()
    assert prompt_submit.turn_id == hook_context.turn_id
    assert prompt_submit.prompt == "hello"
    assert pre_compact.trigger == "manual"
    assert post_compact.trigger == "auto"


def test_user_prompt_submit_block_context_stays_as_next_turn_additional_context() -> None:
    # Rust tests: blocked_user_prompt_submit_persists_additional_context_for_next_turn,
    # blocked_queued_prompt_does_not_strand_earlier_accepted_prompt.
    messages = additional_context_messages([BLOCKED_PROMPT_CONTEXT, "accepted prompt survived"])

    assert [item.role for item in messages] == ["developer", "developer"]
    rendered = [item.content[0].text for item in messages]
    assert BLOCKED_PROMPT_CONTEXT in rendered[0]
    assert "accepted prompt survived" in rendered[1]


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "suffix"),
    [
        (HookToolName.bash(), {"command": "printf ok"}, "shell"),
        (HookToolName.apply_patch(), {"command": "*** Begin Patch"}, "apply-patch"),
        (HookToolName.new("exec_command"), {"cmd": "printf ok", "tty": False}, "exec"),
        (HookToolName.new("network-access"), {"host": "example.com"}, "network"),
    ],
)
def test_permission_request_payloads_preserve_tool_inputs_and_aliases(
    hook_context: HookRequestContext,
    tool_name: HookToolName,
    tool_input: dict[str, object],
    suffix: str,
) -> None:
    # Rust tests: permission_request_hook_allows_shell_command_without_user_approval,
    # permission_request_hook_allows_apply_patch_with_write_alias,
    # permission_request_hook_sees_raw_exec_command_input,
    # permission_request_hook_allows_network_approval_without_prompt,
    # permission_request_hook_sees_retry_context_after_sandbox_denial.
    request = build_permission_request_request(
        hook_context,
        run_id_suffix=suffix,
        tool_name=tool_name,
        tool_input=tool_input,
    )

    assert request.tool_name == tool_name.name
    assert request.matcher_aliases == tool_name.matcher_aliases
    assert request.tool_input == tool_input
    assert request.run_id_suffix == suffix
    assert hook_permission_mode(SimpleNamespace(value="never")) == "bypassPermissions"


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "reason"),
    [
        (HookToolName.bash(), {"command": "cat /etc/passwd"}, "shell blocked"),
        (HookToolName.apply_patch(), {"command": "*** Begin Patch"}, "patch blocked"),
        (HookToolName.new("view_image"), {"path": "secret.png"}, "local tool blocked"),
    ],
)
def test_pre_tool_use_blocks_and_rewrites_before_execution(
    hook_context: HookRequestContext,
    tool_name: HookToolName,
    tool_input: dict[str, object],
    reason: str,
) -> None:
    # Rust tests: pre_tool_use_blocks_* and pre_tool_use_rewrites_* families,
    # including hooks.json/config.toml merge and plugin-discovered hooks at the
    # shared runtime outcome boundary.
    request = build_pre_tool_use_request(
        hook_context,
        tool_use_id="call-1",
        tool_name=tool_name,
        tool_input=tool_input,
    )
    blocked = pre_tool_use_result_from_outcome(
        {"should_block": True, "block_reason": reason},
        tool_name=tool_name,
        tool_input=tool_input,
    )
    rewritten = pre_tool_use_result_from_outcome(
        {"should_block": False, "updated_input": {"command": "printf rewritten"}},
        tool_name=tool_name,
        tool_input=tool_input,
    )

    assert request.tool_input == tool_input
    assert request.matcher_aliases == tool_name.matcher_aliases
    assert blocked.type == "blocked"
    assert reason in (blocked.message or "")
    assert rewritten.type == "continue"
    assert rewritten.updated_input == {"command": "printf rewritten"}


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (PostToolUseHookOutcome(feedback_message="post context"), "post context"),
        (PostToolUseHookOutcome(should_stop=True, feedback_message="blocked by post hook"), "blocked by post hook"),
        (PostToolUseHookOutcome(should_stop=True, stop_reason="Execution halted by post-tool hook"), "Execution halted by post-tool hook"),
        (PostToolUseHookOutcome(should_stop=True), "PostToolUse hook stopped execution"),
    ],
)
def test_post_tool_use_replaces_or_preserves_tool_output_at_runtime_boundary(
    hook_context: HookRequestContext,
    outcome: PostToolUseHookOutcome,
    expected: str,
) -> None:
    # Rust tests: post_tool_use_records_additional_context_for_shell_command,
    # post_tool_use_block_decision_replaces_shell_command_output_with_reason,
    # post_tool_use_continue_false_replaces_shell_command_output_with_stop_reason,
    # post_tool_use_exit_two_replaces_one_shot_exec_command_output_with_feedback,
    # post_tool_use_spills_large_feedback_message,
    # post_tool_use_blocks_when_exec_session_completes_via_write_stdin.
    request = build_post_tool_use_request(
        hook_context,
        tool_use_id="call-1",
        tool_name=HookToolName.bash(),
        tool_input={"command": "printf post-tool-output"},
        tool_response="post-tool-output",
    )

    assert request.tool_response == "post-tool-output"
    assert request.tool_input["command"] == "printf post-tool-output"
    assert post_tool_use_replacement_text(outcome) == expected


@pytest.mark.parametrize("tool_name", [HookToolName.apply_patch(), HookToolName.new("apply_patch")])
def test_apply_patch_post_tool_use_records_canonical_payload_and_edit_alias(
    hook_context: HookRequestContext,
    tool_name: HookToolName,
) -> None:
    # Rust tests: post_tool_use_records_additional_context_for_apply_patch,
    # post_tool_use_records_apply_patch_context_with_edit_alias.
    patch = "*** Begin Patch\n*** Add File: demo.txt\n+patched\n*** End Patch"
    request = build_post_tool_use_request(
        hook_context,
        tool_use_id="patch-call",
        tool_name=tool_name,
        tool_input={"command": patch},
        tool_response="Exit code: 0\nSuccess. Updated the following files:\nA demo.txt",
    )

    assert request.tool_name == "apply_patch"
    assert request.tool_input["command"] == patch
    assert "A demo.txt" in request.tool_response
    if tool_name.matcher_aliases:
        assert "Edit" in request.matcher_aliases
