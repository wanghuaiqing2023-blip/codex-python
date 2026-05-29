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
    build_exec_stage_events,
    build_patch_begin_item,
    build_patch_end_for_stage,
    exec_command_result_for_stage,
    patch_status_for_failure,
    tracker_update_for_known_delta,
)
from pycodex.protocol import (
    ExecCommandSource,
    ExecCommandStatus,
    ExecToolCallOutput,
    FileChange,
    PatchApplyStatus,
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
            parsed_cmd=({"cmd": "echo"},),
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
        self.assertEqual(begin_item.payload.id, "patch-1")
        self.assertTrue(begin_item.payload.auto_approved)
        self.assertEqual(end_result.completed_item.payload.status, PatchApplyStatus.COMPLETED)
        self.assertEqual(end_result.completed_item.payload.stdout, "done")
        self.assertIsNone(end_result.turn_diff_event)

    def test_patch_failure_statuses_and_tracker_updates_match_rust(self) -> None:
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
        ctx = ToolEventCtx.new(None, _Turn(), "patch-2", TurnDiffTracker())
        emitter = ToolEmitter.apply_patch({Path("out.txt"): FileChange.add("after\n")}, auto_approved=False)
        delta = AppliedPatchDelta.new(
            [AppliedPatchChange(Path("out.txt"), AppliedPatchFileChange.add("after\n"))],
            exact=True,
        )
        output = ExecToolCallOutput(exit_code=0)

        events = emitter.emit(ctx, ToolEventStage.success(output, delta))

        self.assertEqual(events[0].payload.status, PatchApplyStatus.COMPLETED)
        self.assertEqual(events[1].type, "turn_diff")
        self.assertIn("out.txt", events[1].payload.unified_diff)

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
        self.assertEqual(patch_events[0].payload.status, PatchApplyStatus.DECLINED)
        self.assertEqual(patch_events[0].payload.stderr, "patch rejected by user")

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
