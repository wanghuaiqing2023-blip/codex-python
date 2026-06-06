import unittest
from datetime import timedelta
from pathlib import Path

from pycodex.core import (
    AppliedPatchChange,
    AppliedPatchDelta,
    AppliedPatchFileChange,
    ExecCommandInput,
    ToolEmitter,
    ToolEventCtx,
    ToolEventFailure,
    ToolEventStage,
    TurnDiffTracker,
    TurnDiffTrackerUpdate,
    apply_turn_diff_tracker_update,
    build_command_execution_begin_item,
    build_command_execution_end_item,
    build_command_execution_item_from_guardian_event,
    build_command_execution_item_mapping_from_guardian_event,
    build_exec_stage_events,
    build_patch_begin_item,
    build_patch_end_for_stage,
    command_actions_from_argv,
    command_execution_notification_from_event_msg,
    command_execution_status_from_guardian_status,
    exec_command_result_for_stage,
    file_change_notification_from_turn_item,
    guardian_auto_approval_review_notification,
    patch_status_for_failure,
    tracker_update_for_known_delta,
    turn_item_lifecycle_notification,
)
from pycodex.protocol import (
    EventMsg,
    ExecCommandOutputDeltaEvent,
    ExecCommandSource,
    ExecCommandStatus,
    ExecToolCallOutput,
    FileChange,
    GuardianAssessmentAction,
    GuardianAssessmentDecisionSource,
    GuardianAssessmentEvent,
    GuardianAssessmentStatus,
    GuardianCommandSource,
    GuardianRiskLevel,
    GuardianUserAuthorization,
    PatchApplyStatus,
    ParsedCommand,
    StreamOutput,
    TruncationPolicyConfig,
    TurnItem,
)


class _Turn:
    sub_id = "turn-1"
    truncation_policy = TruncationPolicyConfig.bytes(4096)


class ToolEventsTests(unittest.TestCase):
    def test_exec_begin_and_success_end_events_match_rust_shapes(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-1")
        exec_input = ExecCommandInput.new(
            ["echo", "hi"],
            Path("/tmp/project"),
            parsed_cmd=(ParsedCommand.unknown("echo hi"),),
            source=ExecCommandSource.USER_SHELL,
            process_id="pid-1",
        )
        output = ExecToolCallOutput(
            exit_code=0,
            stdout=StreamOutput.new("hi\n"),
            stderr=StreamOutput.new(""),
            aggregated_output=StreamOutput.new("hi\n"),
            duration=timedelta(seconds=1.25),
        )

        begin_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.begin(), timestamp_ms=10)[0]
        end_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.success(output), timestamp_ms=20)[0]

        self.assertEqual(begin_event.type, "exec_command_begin")
        self.assertEqual(begin_event.payload.call_id, "call-1")
        self.assertEqual(begin_event.payload.turn_id, "turn-1")
        self.assertEqual(begin_event.payload.command, ("echo", "hi"))
        self.assertEqual(begin_event.payload.process_id, "pid-1")
        self.assertEqual(end_event.type, "exec_command_end")
        self.assertEqual(end_event.payload.status, ExecCommandStatus.COMPLETED)
        self.assertEqual(end_event.payload.exit_code, 0)
        self.assertEqual(end_event.payload.stdout, "hi\n")
        self.assertEqual(end_event.payload.aggregated_output, "hi\n")

    def test_exec_command_events_build_command_execution_turn_items(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-1")
        exec_input = ExecCommandInput.new(
            ["python", "-m", "unittest"],
            Path("/tmp/project"),
            parsed_cmd=(ParsedCommand.unknown("python -m unittest"),),
            source=ExecCommandSource.USER_SHELL,
            process_id="pid-1",
        )
        output = ExecToolCallOutput(
            exit_code=1,
            stdout=StreamOutput.new(""),
            stderr=StreamOutput.new("FAILED\n"),
            aggregated_output=StreamOutput.new("FAILED\n"),
            duration=timedelta(seconds=1.25),
        )

        begin_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.begin(), timestamp_ms=10)[0]
        end_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.success(output), timestamp_ms=20)[0]
        begin_item = build_command_execution_begin_item(begin_event.payload)
        end_item = build_command_execution_end_item(end_event.payload)

        self.assertEqual(begin_item.type, "CommandExecution")
        self.assertEqual(begin_item.item.command, "python -m unittest")
        self.assertEqual(begin_item.item.source, "userShell")
        self.assertEqual(begin_item.item.status, "inProgress")
        self.assertEqual(begin_item.item.command_actions, ({"type": "unknown", "command": "python -m unittest"},))
        self.assertEqual(begin_item.item.aggregated_output, None)
        self.assertEqual(end_item.item.status, "failed")
        self.assertEqual(end_item.item.command_actions, ({"type": "unknown", "command": "python -m unittest"},))
        self.assertEqual(end_item.item.aggregated_output, "FAILED\n")
        self.assertEqual(end_item.item.exit_code, 1)
        self.assertEqual(end_item.item.duration_ms, 1250)

    def test_exec_command_events_map_to_command_execution_notifications(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-1")
        exec_input = ExecCommandInput.new(["echo", "hi"], Path("/tmp/project"))
        output = ExecToolCallOutput(
            exit_code=0,
            stdout=StreamOutput.new("hi\n"),
            stderr=StreamOutput.new(""),
            aggregated_output=StreamOutput.new("hi\n"),
        )

        begin_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.begin(), timestamp_ms=10)[0]
        end_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.success(output), timestamp_ms=20)[0]
        delta_event = EventMsg.with_payload(
            "exec_command_output_delta",
            ExecCommandOutputDeltaEvent("call-1", "stdout", b"hi\n"),
        )

        started = command_execution_notification_from_event_msg("thread-1", "turn-1", begin_event)
        completed = command_execution_notification_from_event_msg("thread-1", "turn-1", end_event)
        delta = command_execution_notification_from_event_msg("thread-1", "turn-1", delta_event)

        self.assertEqual(started["method"], "item/started")
        self.assertEqual(started["params"]["startedAtMs"], 10)
        self.assertEqual(started["params"]["item"]["type"], "commandExecution")
        self.assertEqual(started["params"]["item"]["status"], "inProgress")
        self.assertEqual(completed["method"], "item/completed")
        self.assertEqual(completed["params"]["completedAtMs"], 20)
        self.assertEqual(completed["params"]["item"]["aggregatedOutput"], "hi\n")
        self.assertEqual(completed["params"]["item"]["exitCode"], 0)
        self.assertEqual(delta["method"], "item/commandExecution/outputDelta")
        self.assertEqual(delta["params"]["itemId"], "call-1")
        self.assertEqual(delta["params"]["delta"], "hi\n")

    def test_turn_item_lifecycle_notification_supports_command_execution_items(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-1")
        exec_input = ExecCommandInput.new(["echo", "hi"], Path("/tmp/project"))
        output = ExecToolCallOutput(
            exit_code=0,
            stdout=StreamOutput.new("hi\n"),
            stderr=StreamOutput.new(""),
            aggregated_output=StreamOutput.new("hi\n"),
        )
        begin_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.begin(), timestamp_ms=10)[0]
        end_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.success(output), timestamp_ms=20)[0]

        started = turn_item_lifecycle_notification(
            "thread-1",
            "turn-1",
            build_command_execution_begin_item(begin_event.payload),
            timestamp_ms=10,
        )
        completed = turn_item_lifecycle_notification(
            "thread-1",
            "turn-1",
            build_command_execution_end_item(end_event.payload),
            timestamp_ms=20,
        )

        self.assertEqual(started["method"], "item/started")
        self.assertEqual(started["params"]["item"]["type"], "commandExecution")
        self.assertEqual(completed["method"], "item/completed")
        self.assertEqual(completed["params"]["item"]["status"], "completed")

    def test_guardian_command_assessment_builds_command_execution_item(self) -> None:
        assessment = GuardianAssessmentEvent(
            id="assessment-1",
            status=GuardianAssessmentStatus.DENIED,
            target_item_id="call-1",
            action=GuardianAssessmentAction.command_action(
                GuardianCommandSource.SHELL,
                "rm -rf tmp",
                Path("/repo"),
            ),
        )

        status = command_execution_status_from_guardian_status(assessment.status)
        item = build_command_execution_item_from_guardian_event(assessment, status)

        self.assertEqual(status, "declined")
        self.assertEqual(item.type, "CommandExecution")
        self.assertEqual(item.item.id, "call-1")
        self.assertEqual(item.item.command, "rm -rf tmp")
        self.assertEqual(item.item.cwd, Path("/repo"))
        self.assertEqual(item.item.source, "agent")
        self.assertEqual(item.item.status, "declined")
        self.assertEqual(item.item.command_actions, ({"type": "unknown", "command": "rm -rf tmp"},))

        item_mapping = build_command_execution_item_mapping_from_guardian_event(assessment)

        self.assertEqual(item_mapping["type"], "commandExecution")
        self.assertEqual(item_mapping["id"], "call-1")
        self.assertEqual(item_mapping["status"], "declined")
        self.assertEqual(item_mapping["aggregatedOutput"], None)

    def test_guardian_execve_assessment_parses_command_actions(self) -> None:
        assessment = GuardianAssessmentEvent(
            id="assessment-1",
            status=GuardianAssessmentStatus.DENIED,
            target_item_id="call-1",
            action=GuardianAssessmentAction.execve(
                GuardianCommandSource.UNIFIED_EXEC,
                "cat",
                ("cat", "README.md"),
                Path("/repo"),
            ),
        )

        item = build_command_execution_item_from_guardian_event(assessment, "declined")

        self.assertEqual(item.type, "CommandExecution")
        self.assertEqual(item.item.command, "cat README.md")
        self.assertEqual(
            item.item.command_actions,
            ({"type": "read", "command": "cat README.md", "name": "README.md", "path": str(Path("/repo") / "README.md")},),
        )

    def test_exec_command_actions_include_nullable_app_server_fields(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-1")
        exec_input = ExecCommandInput.new(
            ["rg", "needle"],
            Path("/repo"),
            parsed_cmd=(ParsedCommand.list_files("ls", None), ParsedCommand.search("rg needle", "needle", None)),
        )

        begin_event = build_exec_stage_events(ctx, exec_input, ToolEventStage.begin(), timestamp_ms=10)[0]
        item = build_command_execution_begin_item(begin_event.payload)

        self.assertEqual(
            item.item.command_actions,
            (
                {"type": "listFiles", "command": "ls", "path": None},
                {"type": "search", "command": "rg needle", "query": "needle", "path": None},
            ),
        )

    def test_tool_emitters_parse_command_actions_by_default(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-1")
        shell = ToolEmitter.shell(["bash", "-lc", "cat README.md"], Path("/repo"))
        unified = ToolEmitter.unified_exec(["bash", "-lc", "rg needle src"], Path("/repo"), process_id="45")

        shell_event = shell.emit(ctx, ToolEventStage.begin())[0]
        unified_event = unified.emit(ctx, ToolEventStage.begin())[0]
        shell_item = build_command_execution_begin_item(shell_event.payload)
        unified_item = build_command_execution_begin_item(unified_event.payload)

        self.assertEqual(
            shell_item.item.command_actions,
            ({"type": "read", "command": "cat README.md", "name": "README.md", "path": str(Path("/repo") / "README.md")},),
        )
        self.assertEqual(
            unified_item.item.command_actions,
            ({"type": "search", "command": "rg needle src", "query": "needle", "path": "src"},),
        )
        self.assertEqual(unified_event.payload.process_id, "45")

    def test_tool_emitters_preserve_explicit_parsed_commands(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-1")
        shell = ToolEmitter.shell(
            ["bash", "-lc", "cat README.md"],
            Path("/repo"),
            parsed_cmd=(ParsedCommand.unknown("custom"),),
        )

        event = shell.emit(ctx, ToolEventStage.begin())[0]
        item = build_command_execution_begin_item(event.payload)

        self.assertEqual(item.item.command_actions, ({"type": "unknown", "command": "custom"},))

    def test_command_actions_from_argv_uses_shell_command_parser(self) -> None:
        self.assertEqual(
            command_actions_from_argv(("bash", "-lc", "cat README.md"), Path("/repo")),
            ({"type": "read", "command": "cat README.md", "name": "README.md", "path": str(Path("/repo") / "README.md")},),
        )
        self.assertEqual(
            command_actions_from_argv(("bash", "-lc", "rg needle src"), Path("/repo")),
            ({"type": "search", "command": "rg needle src", "query": "needle", "path": "src"},),
        )

    def test_guardian_non_command_or_approved_assessment_does_not_build_command_execution_item(self) -> None:
        assessment = GuardianAssessmentEvent(
            id="assessment-1",
            status=GuardianAssessmentStatus.APPROVED,
            target_item_id="call-1",
            action=GuardianAssessmentAction.apply_patch(Path("/repo"), (Path("a.py"),)),
        )

        self.assertIsNone(command_execution_status_from_guardian_status(assessment.status))
        self.assertIsNone(build_command_execution_item_from_guardian_event(assessment, "inProgress"))
        self.assertIsNone(build_command_execution_item_mapping_from_guardian_event(assessment))

    def test_guardian_auto_approval_review_notifications_match_app_server_shape(self) -> None:
        started_assessment = GuardianAssessmentEvent(
            id="review-1",
            status=GuardianAssessmentStatus.IN_PROGRESS,
            target_item_id="call-1",
            turn_id="",
            started_at_ms=10,
            risk_level=GuardianRiskLevel.HIGH,
            user_authorization=GuardianUserAuthorization.LOW,
            rationale="risky",
            action=GuardianAssessmentAction.execve(
                GuardianCommandSource.UNIFIED_EXEC,
                "/bin/rm",
                ("/bin/rm", "-rf", "tmp"),
                Path("/repo"),
            ),
        )
        completed_assessment = GuardianAssessmentEvent(
            id="review-1",
            status=GuardianAssessmentStatus.DENIED,
            target_item_id="call-1",
            turn_id="turn-actual",
            started_at_ms=10,
            completed_at_ms=None,
            decision_source=GuardianAssessmentDecisionSource.AGENT,
            action=GuardianAssessmentAction.command_action(
                GuardianCommandSource.SHELL,
                "rm -rf tmp",
                Path("/repo"),
            ),
        )

        started = guardian_auto_approval_review_notification("thread-1", "turn-fallback", started_assessment)
        completed = guardian_auto_approval_review_notification("thread-1", "turn-fallback", completed_assessment)

        self.assertEqual(started["method"], "item/autoApprovalReview/started")
        self.assertEqual(started["params"]["turnId"], "turn-fallback")
        self.assertEqual(started["params"]["review"]["status"], "inProgress")
        self.assertEqual(started["params"]["review"]["riskLevel"], "high")
        self.assertEqual(started["params"]["review"]["userAuthorization"], "low")
        self.assertEqual(started["params"]["action"]["type"], "execve")
        self.assertEqual(started["params"]["action"]["source"], "unifiedExec")
        self.assertEqual(completed["method"], "item/autoApprovalReview/completed")
        self.assertEqual(completed["params"]["turnId"], "turn-actual")
        self.assertEqual(completed["params"]["completedAtMs"], 10)
        self.assertEqual(completed["params"]["decisionSource"], "agent")
        self.assertEqual(completed["params"]["review"]["status"], "denied")
        self.assertEqual(completed["params"]["action"]["type"], "command")

    def test_exec_failure_messages_are_failed_and_rejections_are_declined(self) -> None:
        policy = TruncationPolicyConfig.bytes(4096)

        failed = exec_command_result_for_stage(
            ToolEventStage.failure(ToolEventFailure.message_failure("boom")),
            policy,
        )
        declined = exec_command_result_for_stage(
            ToolEventStage.failure(ToolEventFailure.rejected("no")),
            policy,
        )

        self.assertEqual(failed.status, ExecCommandStatus.FAILED)
        self.assertEqual(failed.exit_code, -1)
        self.assertEqual(failed.stderr, "boom")
        self.assertEqual(declined.status, ExecCommandStatus.DECLINED)
        self.assertEqual(declined.stderr, "no")

    def test_exec_output_failure_emits_failed_end_event_with_output_metadata(self) -> None:
        # Rust source: codex-rs/core/src/tools/events.rs
        # Behavior anchor: ToolEventStage::Success and
        # ToolEventFailure::Output share the ExecCommandResult path; non-zero
        # output failures emit ExecCommandEnd with status Failed while preserving
        # stdout, stderr, aggregated_output, and formatted_output.
        ctx = ToolEventCtx.new(None, _Turn(), "call-output-failure")
        exec_input = ExecCommandInput.new(
            ["python", "-m", "pytest"],
            Path("/tmp/project"),
            source=ExecCommandSource.USER_SHELL,
        )
        output = ExecToolCallOutput(
            exit_code=1,
            stdout=StreamOutput.new(""),
            stderr=StreamOutput.new("FAILED\n"),
            aggregated_output=StreamOutput.new("FAILED\n"),
            duration=timedelta(milliseconds=1250),
        )

        (event,) = build_exec_stage_events(
            ctx,
            exec_input,
            ToolEventStage.failure(ToolEventFailure.output_failure(output)),
            timestamp_ms=30,
        )

        self.assertEqual(event.type, "exec_command_end")
        self.assertEqual(event.payload.status, ExecCommandStatus.FAILED)
        self.assertEqual(event.payload.exit_code, 1)
        self.assertEqual(event.payload.stderr, "FAILED\n")
        self.assertEqual(event.payload.aggregated_output, "FAILED\n")
        self.assertEqual(event.payload.formatted_output, "FAILED\n")

    def test_patch_begin_and_success_end_items_match_file_change_turn_items(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "patch-1")
        changes = {Path("a.txt"): FileChange.add("after")}
        output = ExecToolCallOutput(
            exit_code=0,
            stdout=StreamOutput.new("done"),
            stderr=StreamOutput.new(""),
            aggregated_output=StreamOutput.new("done"),
        )

        begin_item = build_patch_begin_item(ctx, changes, auto_approved=True)
        end_result = build_patch_end_for_stage(ctx, changes, ToolEventStage.success(output, AppliedPatchDelta.empty()))

        self.assertIsInstance(begin_item, TurnItem)
        self.assertEqual(begin_item.item.id, "patch-1")
        self.assertTrue(begin_item.item.auto_approved)
        self.assertEqual(end_result.completed_item.item.status, PatchApplyStatus.COMPLETED)
        self.assertEqual(end_result.completed_item.item.stdout, "done")
        self.assertIsNone(end_result.turn_diff_event)

    def test_patch_items_map_to_file_change_notifications(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "patch-1")
        changes = {Path("a.txt"): FileChange.add("after")}
        output = ExecToolCallOutput(
            exit_code=0,
            stdout=StreamOutput.new("done"),
            stderr=StreamOutput.new(""),
            aggregated_output=StreamOutput.new("done"),
        )

        begin_item = build_patch_begin_item(ctx, changes, auto_approved=True)
        end_result = build_patch_end_for_stage(ctx, changes, ToolEventStage.success(output, AppliedPatchDelta.empty()))
        started = file_change_notification_from_turn_item("thread-1", "turn-1", begin_item, timestamp_ms=10)
        completed = file_change_notification_from_turn_item("thread-1", "turn-1", end_result.completed_item, timestamp_ms=20)

        self.assertEqual(started["method"], "item/started")
        self.assertEqual(started["params"]["startedAtMs"], 10)
        self.assertEqual(started["params"]["item"]["type"], "fileChange")
        self.assertEqual(started["params"]["item"]["status"], "inProgress")
        self.assertEqual(completed["method"], "item/completed")
        self.assertEqual(completed["params"]["completedAtMs"], 20)
        self.assertEqual(completed["params"]["item"]["type"], "fileChange")
        self.assertEqual(completed["params"]["item"]["status"], "completed")
        self.assertEqual(
            turn_item_lifecycle_notification("thread-1", "turn-1", begin_item, timestamp_ms=10),
            started,
        )

    def test_patch_failure_statuses_and_tracker_updates_match_rust(self) -> None:
        # Rust parity: codex-core::tools::events
        # events.rs::tracker_update_for_known_delta and patch failure status arms.
        failed_output = ExecToolCallOutput(exit_code=1)
        non_empty_delta = AppliedPatchDelta.new(
            [AppliedPatchChange(Path("out.txt"), AppliedPatchFileChange.add("after\n"))],
            exact=True,
        )

        self.assertEqual(patch_status_for_failure(ToolEventFailure.output_failure(failed_output)), PatchApplyStatus.FAILED)
        self.assertEqual(patch_status_for_failure(ToolEventFailure.rejected("no")), PatchApplyStatus.DECLINED)
        self.assertEqual(tracker_update_for_known_delta(AppliedPatchDelta.empty()).type, "none")
        self.assertEqual(tracker_update_for_known_delta(non_empty_delta).type, "track")

    def test_apply_patch_emitter_emits_turn_diff_when_tracker_changes(self) -> None:
        # Rust parity: codex-core::tools::events
        # events.rs inline test rejected_apply_patch_tracks_committed_delta.
        ctx = ToolEventCtx.new(None, _Turn(), "patch-2", TurnDiffTracker())
        emitter = ToolEmitter.apply_patch({Path("out.txt"): FileChange.add("after\n")}, auto_approved=False)
        delta = AppliedPatchDelta.new(
            [AppliedPatchChange(Path("out.txt"), AppliedPatchFileChange.add("after\n"))],
            exact=True,
        )
        output = ExecToolCallOutput(exit_code=0)

        events = emitter.emit(ctx, ToolEventStage.success(output, delta))

        self.assertEqual(events[0].item.status, PatchApplyStatus.COMPLETED)
        self.assertEqual(events[1].type, "turn_diff")
        self.assertIn("out.txt", events[1].payload.unified_diff)

    def test_denied_apply_patch_with_committed_delta_emits_failed_item_and_turn_diff(self) -> None:
        # Rust parity: codex-core::tools::events
        # events.rs inline test denied_apply_patch_tracks_committed_delta.
        ctx = ToolEventCtx.new(None, _Turn(), "patch-denied", TurnDiffTracker())
        emitter = ToolEmitter.apply_patch({Path("out.txt"): FileChange.add("after\n")}, auto_approved=False)
        delta = AppliedPatchDelta.new(
            [AppliedPatchChange(Path("out.txt"), AppliedPatchFileChange.add("after\n"))],
            exact=True,
        )
        output = ExecToolCallOutput(
            exit_code=1,
            stdout=StreamOutput.new(""),
            stderr=StreamOutput.new("denied\n"),
            aggregated_output=StreamOutput.new("denied\n"),
        )

        result, events = emitter.finish(ctx, output, delta)

        self.assertIsInstance(result, FunctionCallError)
        self.assertEqual(events[0].item.status, PatchApplyStatus.FAILED)
        self.assertEqual(events[0].item.stderr, "denied\n")
        self.assertEqual(events[1].type, "turn_diff")
        self.assertIn("out.txt", events[1].payload.unified_diff)
        self.assertIn("+after", events[1].payload.unified_diff)

    def test_rejected_apply_patch_with_committed_delta_emits_declined_item_and_turn_diff(self) -> None:
        # Rust parity: codex-core::tools::events
        # events.rs inline test rejected_apply_patch_tracks_committed_delta.
        ctx = ToolEventCtx.new(None, _Turn(), "patch-3", TurnDiffTracker())
        emitter = ToolEmitter.apply_patch({Path("out.txt"): FileChange.add("after\n")}, auto_approved=False)
        delta = AppliedPatchDelta.new(
            [AppliedPatchChange(Path("out.txt"), AppliedPatchFileChange.add("after\n"))],
            exact=True,
        )

        events = emitter.emit(
            ctx,
            ToolEventStage.failure(ToolEventFailure.rejected("patch rejected by user", delta)),
        )

        self.assertEqual(events[0].item.status, PatchApplyStatus.DECLINED)
        self.assertEqual(events[0].item.stderr, "patch rejected by user")
        self.assertEqual(events[1].type, "turn_diff")
        self.assertIn("out.txt", events[1].payload.unified_diff)

    def test_turn_diff_tracker_invalidation_emits_empty_diff_when_previous_diff_existed(self) -> None:
        # Rust source: codex-rs/core/src/tools/events.rs
        # Behavior anchor: emit_patch_end records previous_diff, applies
        # TurnDiffTrackerUpdate::Invalidate, and emits TurnDiffEvent with
        # unified_diff.unwrap_or_default() when the previous diff existed.
        tracker = TurnDiffTracker()
        tracker.track_delta(
            AppliedPatchDelta.new(
                [AppliedPatchChange(Path("out.txt"), AppliedPatchFileChange.add("after\n"))],
                exact=True,
            )
        )

        event = apply_turn_diff_tracker_update(tracker, TurnDiffTrackerUpdate.invalidate())

        self.assertIsNotNone(event)
        self.assertEqual(event.type, "turn_diff")
        self.assertEqual(event.payload.unified_diff, "")

    def test_rejected_by_user_is_normalized_by_emitter_finish(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-3")
        shell = ToolEmitter.shell(["pwd"], Path("/tmp/project"))
        patch = ToolEmitter.apply_patch({}, auto_approved=False)

        shell_result, shell_events = shell.finish(ctx, ToolEventFailure.rejected("rejected by user"))
        patch_result, patch_events = patch.finish(ctx, ToolEventFailure.rejected("rejected by user"))

        self.assertEqual(shell_result.message, "exec command rejected by user")
        self.assertEqual(shell_events[0].payload.status, ExecCommandStatus.DECLINED)
        self.assertEqual(shell_events[0].payload.stderr, "exec command rejected by user")
        self.assertEqual(patch_result.message, "patch rejected by user")
        self.assertEqual(patch_events[0].item.status, PatchApplyStatus.DECLINED)
        self.assertEqual(patch_events[0].item.stderr, "patch rejected by user")

    def test_emitter_finish_returns_model_visible_exec_output_metadata(self) -> None:
        ctx = ToolEventCtx.new(None, _Turn(), "call-4")
        shell = ToolEmitter.shell(["python", "-m", "pytest"], Path("/tmp/project"))
        output = ExecToolCallOutput(
            exit_code=1,
            stdout=StreamOutput.new(""),
            stderr=StreamOutput.new("FAILED\n"),
            aggregated_output=StreamOutput.new("FAILED\n"),
            duration=timedelta(milliseconds=1250),
        )

        result, events = shell.finish(ctx, output)

        self.assertIsInstance(result, Exception)
        self.assertEqual(
            result.message,
            "Exit code: 1\n"
            "Wall time: 1.3 seconds\n"
            "Output:\n"
            "FAILED\n",
        )
        self.assertEqual(events[0].type, "exec_command_end")
        self.assertEqual(events[0].payload.formatted_output, "FAILED\n")

    def test_rejects_non_rust_variant_shapes(self) -> None:
        with self.assertRaises(TypeError):
            ToolEventCtx.new(None, _Turn(), "")
        with self.assertRaises(ValueError):
            ToolEventStage("begin", output=ExecToolCallOutput())
        with self.assertRaises(TypeError):
            ToolEventFailure.output_failure("bad")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            TurnDiffTrackerUpdate("invalidate", AppliedPatchDelta.empty())
        with self.assertRaises(TypeError):
            ExecCommandInput.new(["echo", 1], Path("/tmp"))  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
