import unittest

from pycodex.core.unified_exec import UnifiedExecError
from pycodex.protocol import ExecToolCallOutput, StreamOutput


class CoreUnifiedExecErrorsTests(unittest.TestCase):
    def test_create_process_error_matches_rust_display_and_data(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/errors.rs
        # Behavior anchor: UnifiedExecError::CreateProcess display and
        # UnifiedExecError::create_process constructor.
        error = UnifiedExecError.create_process("no pty")

        self.assertEqual(error.kind, UnifiedExecError.CREATE_PROCESS)
        self.assertEqual(error.message, "no pty")
        self.assertEqual(str(error), "Failed to create unified exec process: no pty")

    def test_process_failed_error_matches_rust_display_and_data(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/errors.rs
        # Behavior anchor: UnifiedExecError::ProcessFailed display and
        # UnifiedExecError::process_failed constructor.
        error = UnifiedExecError.process_failed("lost watcher")

        self.assertEqual(error.kind, UnifiedExecError.PROCESS_FAILED)
        self.assertEqual(error.message, "lost watcher")
        self.assertEqual(str(error), "Unified exec process failed: lost watcher")

    def test_unknown_process_error_matches_rust_display_and_data(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/errors.rs
        # Behavior anchor: UnifiedExecError::UnknownProcessId display.
        error = UnifiedExecError.unknown_process_id(42)

        self.assertEqual(error.kind, UnifiedExecError.UNKNOWN_PROCESS_ID)
        self.assertEqual(error.process_id, 42)
        self.assertEqual(str(error), "Unknown process id 42")

    def test_write_to_stdin_error_matches_rust_display(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/errors.rs
        # Behavior anchor: UnifiedExecError::WriteToStdin display.
        error = UnifiedExecError.write_to_stdin()

        self.assertEqual(error.kind, UnifiedExecError.WRITE_TO_STDIN)
        self.assertEqual(str(error), "failed to write to stdin")

    def test_stdin_closed_error_matches_rust_display(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/errors.rs
        # Behavior anchor: UnifiedExecError::StdinClosed display.
        error = UnifiedExecError.stdin_closed()

        self.assertEqual(error.kind, UnifiedExecError.STDIN_CLOSED)
        self.assertEqual(
            str(error),
            "stdin is closed for this session; rerun exec_command with tty=true to keep stdin open",
        )

    def test_missing_command_line_error_matches_rust_display(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/errors.rs
        # Behavior anchor: UnifiedExecError::MissingCommandLine display.
        error = UnifiedExecError.missing_command_line()

        self.assertEqual(error.kind, UnifiedExecError.MISSING_COMMAND_LINE)
        self.assertEqual(str(error), "missing command line for unified exec request")

    def test_sandbox_denied_error_matches_rust_display_and_payload(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/errors.rs
        # Behavior anchor: UnifiedExecError::SandboxDenied display and
        # UnifiedExecError::sandbox_denied constructor.
        output = ExecToolCallOutput(aggregated_output=StreamOutput.new("sandbox said no"))

        error = UnifiedExecError.sandbox_denied("operation not permitted", output)

        self.assertEqual(error.kind, UnifiedExecError.SANDBOX_DENIED)
        self.assertEqual(error.message, "operation not permitted")
        self.assertIs(error.output, output)
        self.assertEqual(str(error), "Command denied by sandbox: operation not permitted")


if __name__ == "__main__":
    unittest.main()
