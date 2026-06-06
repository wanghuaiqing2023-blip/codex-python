import unittest
from datetime import timedelta
from pathlib import Path

from pycodex.core.tools.events import (
    ExecCommandInput,
    ToolEmitter,
    ToolEventCtx,
    ToolEventFailure,
    ToolEventStage,
    build_exec_stage_events,
)
from pycodex.protocol import (
    ExecCommandSource,
    ExecCommandStatus,
    ExecToolCallOutput,
    StreamOutput,
    TruncationPolicyConfig,
)


class _Turn:
    sub_id = "turn-1"
    truncation_policy = TruncationPolicyConfig.bytes(4096)


class CoreToolEventsUnifiedExecContractTests(unittest.TestCase):
    def test_unified_exec_begin_event_preserves_source_and_process_id(self) -> None:
        # Rust source: codex-rs/core/src/tools/events.rs
        # Behavior anchor: ToolEmitter::unified_exec stores source and
        # process_id, then emit_exec_stage forwards both into
        # ExecCommandBeginEvent.
        ctx = ToolEventCtx.new(None, _Turn(), "call-unified")
        emitter = ToolEmitter.unified_exec(
            ["bash", "-lc", "echo hi"],
            Path("/repo"),
            source=ExecCommandSource.UNIFIED_EXEC_STARTUP,
            process_id="123",
        )

        event = emitter.emit(ctx, ToolEventStage.begin())[0]

        self.assertEqual(event.type, "exec_command_begin")
        self.assertEqual(event.payload.call_id, "call-unified")
        self.assertEqual(event.payload.turn_id, "turn-1")
        self.assertEqual(event.payload.command, ("bash", "-lc", "echo hi"))
        self.assertEqual(event.payload.cwd, Path("/repo"))
        self.assertEqual(event.payload.source, ExecCommandSource.UNIFIED_EXEC_STARTUP)
        self.assertEqual(event.payload.process_id, "123")
        self.assertIsNone(event.payload.interaction_input)

    def test_failure_output_stage_status_still_follows_exit_code_zero(self) -> None:
        # Rust source: codex-rs/core/src/tools/events.rs
        # Behavior anchor: emit_exec_stage handles Success(output) and
        # Failure(Output(output)) through the same ExecCommandResult path, so
        # status is derived from output.exit_code, not the outer stage kind.
        ctx = ToolEventCtx.new(None, _Turn(), "call-shell")
        exec_input = ExecCommandInput.new(
            ["bash", "-lc", "true"],
            Path("/repo"),
            source=ExecCommandSource.AGENT,
        )
        output = ExecToolCallOutput(
            exit_code=0,
            stdout=StreamOutput.new("ok\n"),
            stderr=StreamOutput.new(""),
            aggregated_output=StreamOutput.new("ok\n"),
            duration=timedelta(milliseconds=12),
        )

        event = build_exec_stage_events(
            ctx,
            exec_input,
            ToolEventStage.failure(ToolEventFailure.output_failure(output)),
            timestamp_ms=20,
        )[0]

        self.assertEqual(event.type, "exec_command_end")
        self.assertEqual(event.payload.status, ExecCommandStatus.COMPLETED)
        self.assertEqual(event.payload.exit_code, 0)
        self.assertEqual(event.payload.stdout, "ok\n")
        self.assertEqual(event.payload.stderr, "")
        self.assertEqual(event.payload.aggregated_output, "ok\n")

    def test_failure_output_stage_status_follows_nonzero_exit_code(self) -> None:
        # Rust source: codex-rs/core/src/tools/events.rs
        # Behavior anchor: emit_exec_stage maps output.exit_code != 0 to
        # ExecCommandStatus::Failed for both success and output-failure stages.
        ctx = ToolEventCtx.new(None, _Turn(), "call-shell")
        exec_input = ExecCommandInput.new(["bash", "-lc", "false"], Path("/repo"))
        output = ExecToolCallOutput(
            exit_code=9,
            stdout=StreamOutput.new(""),
            stderr=StreamOutput.new("failed\n"),
            aggregated_output=StreamOutput.new("failed\n"),
            duration=timedelta(milliseconds=12),
        )

        event = build_exec_stage_events(
            ctx,
            exec_input,
            ToolEventStage.failure(ToolEventFailure.output_failure(output)),
            timestamp_ms=20,
        )[0]

        self.assertEqual(event.payload.status, ExecCommandStatus.FAILED)
        self.assertEqual(event.payload.exit_code, 9)
        self.assertEqual(event.payload.stderr, "failed\n")


if __name__ == "__main__":
    unittest.main()
