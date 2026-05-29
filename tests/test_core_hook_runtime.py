import unittest

from pycodex.core import (
    HookRequestContext,
    HookRuntimeOutcome,
    HookToolName,
    PermissionRequestRequest,
    PostCompactHookOutcome,
    PostCompactRequest,
    PostToolUseHookOutcome,
    PostToolUseRequest,
    PreCompactHookOutcome,
    PreCompactRequest,
    PreToolUseRequest,
    PreToolUseHookResult,
    SessionStartRequest,
    SessionStartTarget,
    StopRequest,
    StopTarget,
    UserPromptSubmitRequest,
    additional_context_messages,
    blocked_pre_tool_use_message,
    build_permission_request_request,
    build_post_compact_request,
    build_post_tool_use_request,
    build_pre_compact_request,
    build_pre_tool_use_request,
    build_session_start_request,
    build_stop_request,
    build_user_prompt_submit_request,
    compaction_trigger_label,
    hook_permission_mode,
    post_compact_outcome_from_hook,
    post_tool_use_replacement_text,
    pre_compact_outcome_from_hook,
    pre_tool_use_result_from_outcome,
)


class HookRuntimeTests(unittest.TestCase):
    def context(self) -> HookRequestContext:
        return HookRequestContext(
            session_id="session-1",
            turn_id="turn-1",
            subagent={"agent_id": "agent-1", "agent_type": "explorer"},
            cwd="/workspace",
            transcript_path="/tmp/transcript.jsonl",
            model="gpt-5",
            permission_mode="default",
        )

    def test_build_pre_tool_use_request_matches_rust_shape(self) -> None:
        request = build_pre_tool_use_request(
            self.context(),
            tool_use_id="call-1",
            tool_name=HookToolName.apply_patch(),
            tool_input={"command": "*** Begin Patch"},
        )

        self.assertEqual(
            request,
            PreToolUseRequest(
                session_id="session-1",
                turn_id="turn-1",
                subagent={"agent_id": "agent-1", "agent_type": "explorer"},
                cwd="/workspace",
                transcript_path="/tmp/transcript.jsonl",
                model="gpt-5",
                permission_mode="default",
                tool_name="apply_patch",
                matcher_aliases=("Write", "Edit"),
                tool_use_id="call-1",
                tool_input={"command": "*** Begin Patch"},
            ),
        )

    def test_build_session_start_request_supports_root_and_subagent_targets(self) -> None:
        root = build_session_start_request(
            self.context(),
            target=SessionStartTarget.session_start("startup"),
        )
        subagent = build_session_start_request(
            self.context(),
            target=SessionStartTarget.subagent_start(
                turn_id="turn-1",
                agent_id="agent-1",
                agent_type="explorer",
            ),
        )

        self.assertEqual(
            root,
            SessionStartRequest(
                session_id="session-1",
                cwd="/workspace",
                transcript_path="/tmp/transcript.jsonl",
                model="gpt-5",
                permission_mode="default",
                target=SessionStartTarget.session_start("startup"),
            ),
        )
        self.assertEqual(subagent.target.type, "subagent_start")
        self.assertEqual(subagent.target.agent_type, "explorer")

    def test_build_user_prompt_submit_request_matches_rust_shape(self) -> None:
        request = build_user_prompt_submit_request(self.context(), prompt="hello codex")

        self.assertEqual(
            request,
            UserPromptSubmitRequest(
                session_id="session-1",
                turn_id="turn-1",
                subagent={"agent_id": "agent-1", "agent_type": "explorer"},
                cwd="/workspace",
                transcript_path="/tmp/transcript.jsonl",
                model="gpt-5",
                permission_mode="default",
                prompt="hello codex",
            ),
        )

    def test_build_stop_request_supports_root_and_subagent_targets(self) -> None:
        root = build_stop_request(
            self.context(),
            stop_hook_active=True,
            last_assistant_message="done",
            target=StopTarget.stop(),
        )
        subagent = build_stop_request(
            self.context(),
            stop_hook_active=False,
            last_assistant_message=None,
            target=StopTarget.subagent_stop(
                agent_id="agent-1",
                agent_type="explorer",
                agent_transcript_path="/tmp/agent.jsonl",
            ),
            transcript_path="/tmp/parent.jsonl",
        )

        self.assertEqual(
            root,
            StopRequest(
                session_id="session-1",
                turn_id="turn-1",
                cwd="/workspace",
                transcript_path="/tmp/transcript.jsonl",
                model="gpt-5",
                permission_mode="default",
                stop_hook_active=True,
                last_assistant_message="done",
                target=StopTarget.stop(),
            ),
        )
        self.assertEqual(subagent.transcript_path, "/tmp/parent.jsonl")
        self.assertEqual(subagent.target.agent_transcript_path, "/tmp/agent.jsonl")

    def test_build_compact_requests_use_trigger_label_without_permission_mode(self) -> None:
        pre = build_pre_compact_request(self.context(), trigger="manual")
        post = build_post_compact_request(self.context(), trigger="AUTO")

        self.assertEqual(
            pre,
            PreCompactRequest(
                session_id="session-1",
                turn_id="turn-1",
                subagent={"agent_id": "agent-1", "agent_type": "explorer"},
                cwd="/workspace",
                transcript_path="/tmp/transcript.jsonl",
                model="gpt-5",
                trigger="manual",
            ),
        )
        self.assertEqual(
            post,
            PostCompactRequest(
                session_id="session-1",
                turn_id="turn-1",
                subagent={"agent_id": "agent-1", "agent_type": "explorer"},
                cwd="/workspace",
                transcript_path="/tmp/transcript.jsonl",
                model="gpt-5",
                trigger="auto",
            ),
        )
        self.assertEqual(compaction_trigger_label("manual"), "manual")
        with self.assertRaises(ValueError):
            compaction_trigger_label("background")

    def test_build_post_tool_use_request_accepts_hook_name_or_raw_parts(self) -> None:
        request = build_post_tool_use_request(
            self.context(),
            tool_use_id="call-2",
            tool_name=HookToolName.bash(),
            tool_input={"command": "pwd"},
            tool_response="ok",
        )
        raw = build_post_tool_use_request(
            self.context(),
            tool_use_id="call-3",
            tool_name="mcp__server__tool",
            matcher_aliases=["alias"],
            tool_input={"x": 1},
            tool_response={"ok": True},
        )

        self.assertEqual(request.tool_name, "Bash")
        self.assertEqual(request.matcher_aliases, ())
        self.assertIsInstance(request, PostToolUseRequest)
        self.assertEqual(raw.matcher_aliases, ("alias",))
        self.assertEqual(raw.tool_response, {"ok": True})

    def test_build_permission_request_request_matches_tool_aliases(self) -> None:
        request = build_permission_request_request(
            self.context(),
            run_id_suffix="shell-approval",
            tool_name=HookToolName.bash(),
            tool_input={"command": "curl example.com"},
        )

        self.assertEqual(
            request,
            PermissionRequestRequest(
                session_id="session-1",
                turn_id="turn-1",
                subagent={"agent_id": "agent-1", "agent_type": "explorer"},
                cwd="/workspace",
                transcript_path="/tmp/transcript.jsonl",
                model="gpt-5",
                permission_mode="default",
                tool_name="Bash",
                matcher_aliases=(),
                run_id_suffix="shell-approval",
                tool_input={"command": "curl example.com"},
            ),
        )

    def test_hook_permission_mode_maps_never_to_bypass(self) -> None:
        self.assertEqual(hook_permission_mode("never"), "bypassPermissions")
        self.assertEqual(hook_permission_mode("on-request"), "default")

    def test_pre_tool_use_continue_and_updated_input(self) -> None:
        result = pre_tool_use_result_from_outcome(
            {"should_block": False, "updated_input": {"command": "pwd"}},
            tool_name=HookToolName.bash(),
            tool_input={"command": "ls"},
        )

        self.assertEqual(result, PreToolUseHookResult.continue_({"command": "pwd"}))

    def test_pre_tool_use_block_without_reason_continues_like_rust(self) -> None:
        result = pre_tool_use_result_from_outcome(
            {"should_block": True, "block_reason": None, "updated_input": {"ignored": True}},
            tool_name=HookToolName.new("view_image"),
            tool_input={"path": "x.png"},
        )

        self.assertEqual(result, PreToolUseHookResult.continue_(None))

    def test_pre_tool_use_block_message_mentions_command_for_shell_like_tools(self) -> None:
        self.assertEqual(
            blocked_pre_tool_use_message(
                tool_name=HookToolName.bash(),
                tool_input={"command": "rm -rf /tmp/x"},
                reason="dangerous",
            ),
            "Command blocked by PreToolUse hook: dangerous. Command: rm -rf /tmp/x",
        )
        self.assertEqual(
            blocked_pre_tool_use_message(
                tool_name=HookToolName.apply_patch(),
                tool_input={"command": "*** Begin Patch"},
                reason="blocked",
            ),
            "Command blocked by PreToolUse hook: blocked. Command: *** Begin Patch",
        )

    def test_pre_tool_use_block_message_mentions_tool_for_other_tools(self) -> None:
        result = pre_tool_use_result_from_outcome(
            {"should_block": True, "block_reason": "no images"},
            tool_name=HookToolName.new("view_image"),
            tool_input={"path": "x.png"},
        )

        self.assertEqual(
            result,
            PreToolUseHookResult.blocked(
                "Tool call blocked by PreToolUse hook: no images. Tool: view_image"
            ),
        )

    def test_post_tool_use_replacement_text_matches_stop_feedback_priority(self) -> None:
        self.assertEqual(
            post_tool_use_replacement_text(
                PostToolUseHookOutcome(should_stop=True, feedback_message="feedback", stop_reason="stop")
            ),
            "feedback",
        )
        self.assertEqual(
            post_tool_use_replacement_text(
                PostToolUseHookOutcome(should_stop=True, stop_reason="stop")
            ),
            "stop",
        )
        self.assertEqual(
            post_tool_use_replacement_text(PostToolUseHookOutcome(should_stop=True)),
            "PostToolUse hook stopped execution",
        )
        self.assertEqual(
            post_tool_use_replacement_text(PostToolUseHookOutcome(feedback_message="note")),
            "note",
        )
        self.assertIsNone(post_tool_use_replacement_text(PostToolUseHookOutcome()))

    def test_compact_hook_outcomes_match_stop_flag(self) -> None:
        self.assertEqual(pre_compact_outcome_from_hook(False), PreCompactHookOutcome.continue_())
        self.assertEqual(
            pre_compact_outcome_from_hook(True, "too soon"),
            PreCompactHookOutcome.stopped("too soon"),
        )
        self.assertEqual(post_compact_outcome_from_hook(False), PostCompactHookOutcome.continue_())
        self.assertEqual(post_compact_outcome_from_hook(True), PostCompactHookOutcome.stopped())

    def test_additional_context_messages_are_developer_messages_in_order(self) -> None:
        messages = additional_context_messages(["first tide note", "second tide note"])

        self.assertEqual([message.role for message in messages], ["developer", "developer"])
        self.assertEqual(
            [message.content[0].text for message in messages],
            ["first tide note", "second tide note"],
        )

    def test_hook_runtime_outcome_normalizes_contexts(self) -> None:
        outcome = HookRuntimeOutcome(should_stop=False, additional_contexts=["a", "b"])

        self.assertEqual(outcome.additional_contexts, ("a", "b"))


if __name__ == "__main__":
    unittest.main()
