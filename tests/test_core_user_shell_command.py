from __future__ import annotations

import unittest
from datetime import timedelta

from pycodex.core.user_shell_command import (
    env_for_user_shell_command,
    format_exec_output_for_model,
    format_exec_output_str,
    format_user_shell_command_record,
    user_shell_command_record_item,
)
from pycodex.core.tools.runtimes import (
    PROXY_ACTIVE_ENV_KEY,
    PROXY_ENV_KEYS,
    PROXY_GIT_SSH_COMMAND_ENV_KEY,
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

    def test_format_exec_output_for_model_reports_total_lines_when_truncated(self) -> None:
        # Rust source: codex-rs/core/src/tools/mod.rs
        # Behavior anchor: format_exec_output_for_model compares the original
        # content line count with the truncated output line count and includes
        # `Total output lines` when truncation removed lines.
        exec_output = ExecToolCallOutput(
            exit_code=1,
            aggregated_output=StreamOutput.new("line\n" * 100),
            duration=timedelta(milliseconds=1250),
        )

        formatted = format_exec_output_for_model(exec_output, TruncationPolicyConfig.bytes(16))

        self.assertTrue(formatted.startswith("Exit code: 1\nWall time: 1.3 seconds\n"))
        self.assertIn("Total output lines: 100\n", formatted)
        self.assertIn("\nOutput:\n", formatted)
        self.assertIn("truncated", formatted)

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

    def test_user_shell_env_removes_managed_proxy_when_active(self) -> None:
        # Rust source: codex-rs/core/src/tasks/user_shell.rs
        # Rust test: user_shell_commands_do_not_inherit_managed_network_proxy.
        env = {key: "managed" for key in PROXY_ENV_KEYS}
        env["CUSTOM"] = "kept"

        cleaned = env_for_user_shell_command(env, target_os="linux")

        self.assertEqual(cleaned, {"CUSTOM": "kept"})
        self.assertIn(PROXY_ACTIVE_ENV_KEY, env)

    def test_user_shell_env_keeps_user_proxy_without_active_marker(self) -> None:
        env = {
            "CUSTOM": "kept",
            "HTTP_PROXY": "http://user.proxy",
            PROXY_GIT_SSH_COMMAND_ENV_KEY: "ssh -i user-key",
        }

        self.assertEqual(env_for_user_shell_command(env, target_os="darwin"), env)

    def test_user_shell_env_removes_codex_git_ssh_proxy_only_on_macos(self) -> None:
        env = {
            PROXY_ACTIVE_ENV_KEY: "1",
            PROXY_GIT_SSH_COMMAND_ENV_KEY: "codex-proxy-git-ssh --proxy",
            "CUSTOM": "kept",
        }

        self.assertEqual(env_for_user_shell_command(env, target_os="darwin"), {"CUSTOM": "kept"})
        self.assertEqual(
            env_for_user_shell_command(env, target_os="linux"),
            {
                PROXY_GIT_SSH_COMMAND_ENV_KEY: "codex-proxy-git-ssh --proxy",
                "CUSTOM": "kept",
            },
        )

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

    def test_user_shell_env_rejects_invalid_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "env must be a mapping"):
            env_for_user_shell_command([])  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "env keys and values must be strings"):
            env_for_user_shell_command({"A": 1})  # type: ignore[dict-item]
        with self.assertRaisesRegex(TypeError, "target_os must be a string or None"):
            env_for_user_shell_command({PROXY_ACTIVE_ENV_KEY: "1"}, target_os=object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
