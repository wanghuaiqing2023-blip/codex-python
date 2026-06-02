from __future__ import annotations

import unittest
from datetime import timedelta

from pycodex.core.user_shell_command import (
    format_exec_output_for_model,
    format_exec_output_str,
    format_user_shell_command_record,
    user_shell_command_record_item,
)
from pycodex.protocol import (
    ContentItem,
    ExecToolCallOutput,
    ResponseItem,
    StreamOutput,
    TruncationPolicyConfig,
)


class UserShellCommandTests(unittest.TestCase):
    def test_formats_basic_record(self) -> None:
        exec_output = ExecToolCallOutput(
            exit_code=0,
            stdout=StreamOutput.new("hi"),
            stderr=StreamOutput.new(""),
            aggregated_output=StreamOutput.new("hi"),
            duration=timedelta(seconds=1),
            timed_out=False,
        )

        item = user_shell_command_record_item(
            "echo hi",
            exec_output,
            TruncationPolicyConfig.bytes(1024),
        )

        expected_text = (
            "<user_shell_command>\n"
            "<command>\n"
            "echo hi\n"
            "</command>\n"
            "<result>\n"
            "Exit code: 0\n"
            "Duration: 1.0000 seconds\n"
            "Output:\n"
            "hi\n"
            "</result>\n"
            "</user_shell_command>"
        )
        self.assertEqual(item, ResponseItem.message("user", (ContentItem.input_text(expected_text),)))

    def test_uses_aggregated_output_over_streams(self) -> None:
        exec_output = ExecToolCallOutput(
            exit_code=42,
            stdout=StreamOutput.new("stdout-only"),
            stderr=StreamOutput.new("stderr-only"),
            aggregated_output=StreamOutput.new("combined output wins"),
            duration=timedelta(milliseconds=120),
            timed_out=False,
        )

        self.assertEqual(
            format_user_shell_command_record(
                "false",
                exec_output,
                TruncationPolicyConfig.bytes(1024),
            ),
            "<user_shell_command>\n"
            "<command>\n"
            "false\n"
            "</command>\n"
            "<result>\n"
            "Exit code: 42\n"
            "Duration: 0.1200 seconds\n"
            "Output:\n"
            "combined output wins\n"
            "</result>\n"
            "</user_shell_command>",
        )

    def test_timeout_prefix_matches_exec_output_formatting(self) -> None:
        exec_output = ExecToolCallOutput(
            exit_code=124,
            aggregated_output=StreamOutput.new("partial output"),
            duration=timedelta(milliseconds=2500),
            timed_out=True,
        )

        self.assertEqual(
            format_exec_output_str(exec_output, TruncationPolicyConfig.bytes(1024)),
            "command timed out after 2500 milliseconds\npartial output",
        )

    def test_format_exec_output_for_model_includes_exit_code_wall_time_and_timeout(self) -> None:
        exec_output = ExecToolCallOutput(
            exit_code=124,
            aggregated_output=StreamOutput.new("partial output"),
            duration=timedelta(milliseconds=1250),
            timed_out=True,
        )

        self.assertEqual(
            format_exec_output_for_model(exec_output, TruncationPolicyConfig.bytes(1024)),
            "Exit code: 124\n"
            "Wall time: 1.3 seconds\n"
            "Output:\n"
            "command timed out after 1250 milliseconds\npartial output",
        )

    def test_output_is_truncated_before_record_rendering(self) -> None:
        exec_output = ExecToolCallOutput(
            exit_code=0,
            aggregated_output=StreamOutput.new("line\n" * 100),
            duration=timedelta(milliseconds=1),
            timed_out=False,
        )

        record = format_user_shell_command_record(
            "yes line",
            exec_output,
            TruncationPolicyConfig.bytes(16),
        )

        self.assertIn("Total output lines: 100", record)
        self.assertIn("chars truncated", record)
        self.assertIn("<user_shell_command>", record)
        self.assertIn("</user_shell_command>", record)

    def test_rejects_non_string_command(self) -> None:
        exec_output = ExecToolCallOutput(
            exit_code=0,
            aggregated_output=StreamOutput.new("hi"),
            duration=timedelta(milliseconds=1),
            timed_out=False,
        )

        with self.assertRaisesRegex(TypeError, "command must be a str"):
            user_shell_command_record_item(  # type: ignore[arg-type]
                123,
                exec_output,
                TruncationPolicyConfig.bytes(1024),
            )

    def test_rejects_non_exec_output(self) -> None:
        with self.assertRaisesRegex(TypeError, "exec_output must be an ExecToolCallOutput"):
            format_exec_output_str(  # type: ignore[arg-type]
                object(),
                TruncationPolicyConfig.bytes(1024),
            )

    def test_rejects_non_truncation_policy(self) -> None:
        exec_output = ExecToolCallOutput(
            exit_code=0,
            aggregated_output=StreamOutput.new("hi"),
            duration=timedelta(milliseconds=1),
            timed_out=False,
        )

        with self.assertRaisesRegex(TypeError, "truncation_policy must be a TruncationPolicyConfig"):
            format_user_shell_command_record(  # type: ignore[arg-type]
                "echo hi",
                exec_output,
                object(),
            )


if __name__ == "__main__":
    unittest.main()
