from io import StringIO
import unittest

from pycodex.cli import AppExitInfo, ExitReason, UpdateAction, format_exit_messages, handle_app_exit, run_update_action
from pycodex.protocol import TokenUsage


THREAD_ID = "123e4567-e89b-12d3-a456-426614174000"


class AppExitFormattingTests(unittest.TestCase):
    def test_skips_when_no_usage_or_resume_hint(self) -> None:
        self.assertEqual(format_exit_messages(AppExitInfo()), [])

    def test_includes_token_usage_when_non_zero(self) -> None:
        info = AppExitInfo(
            token_usage=TokenUsage(input_tokens=100, cached_input_tokens=20, output_tokens=30, total_tokens=130)
        )

        self.assertEqual(
            format_exit_messages(info),
            ["Token usage: total=110 input=80 (+ 20 cached) output=30"],
        )

    def test_includes_resume_hint_with_name_and_thread_id(self) -> None:
        info = AppExitInfo(thread_id=THREAD_ID, thread_name="my-thread")

        self.assertEqual(
            format_exit_messages(info),
            [f"To continue this session, run codex resume, then select my-thread ({THREAD_ID})"],
        )

    def test_includes_direct_resume_command_without_name(self) -> None:
        info = AppExitInfo(thread_id=THREAD_ID)

        self.assertEqual(
            format_exit_messages(info),
            [f"To continue this session, run codex resume {THREAD_ID}"],
        )

    def test_token_usage_precedes_resume_hint(self) -> None:
        info = AppExitInfo(
            token_usage=TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3),
            thread_id=THREAD_ID,
        )

        self.assertEqual(
            format_exit_messages(info),
            [
                "Token usage: total=3 input=1 output=2",
                f"To continue this session, run codex resume {THREAD_ID}",
            ],
        )

    def test_colorizes_only_resume_command(self) -> None:
        info = AppExitInfo(thread_id=THREAD_ID)

        self.assertEqual(
            format_exit_messages(info, color_enabled=True),
            [f"To continue this session, run \x1b[36mcodex resume {THREAD_ID}\x1b[39m"],
        )

    def test_handle_app_exit_fatal_prints_error_and_exits_one(self) -> None:
        stderr = StringIO()

        with self.assertRaises(SystemExit) as raised:
            handle_app_exit(AppExitInfo.fatal("boom"), stderr=stderr)

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(stderr.getvalue(), "ERROR: boom\n")

    def test_handle_app_exit_user_requested_prints_summary_lines(self) -> None:
        stdout = StringIO()
        info = AppExitInfo(
            token_usage=TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3),
            thread_id=THREAD_ID,
            exit_reason=ExitReason.user_requested(),
        )

        handle_app_exit(info, stdout=stdout, color_enabled=False)

        self.assertEqual(
            stdout.getvalue(),
            f"Token usage: total=3 input=1 output=2\nTo continue this session, run codex resume {THREAD_ID}\n",
        )

    def test_handle_app_exit_runs_update_action_after_summary(self) -> None:
        stdout = StringIO()
        calls = []

        handle_app_exit(
            AppExitInfo(thread_id=THREAD_ID, update_action="install"),
            stdout=stdout,
            run_update_action=calls.append,
        )

        self.assertEqual(stdout.getvalue(), f"To continue this session, run codex resume {THREAD_ID}\n")
        self.assertEqual(calls, ["install"])

    def test_run_update_action_prints_command_and_success_message(self) -> None:
        stdout = StringIO()
        calls = []

        run_update_action(
            UpdateAction.BREW_UPGRADE,
            stdout=stdout,
            runner=lambda command, args: calls.append((command, args)) or True,
        )

        self.assertEqual(calls, [("brew", ("upgrade", "--cask", "codex"))])
        self.assertEqual(
            stdout.getvalue(),
            "\nUpdating Codex via `brew upgrade --cask codex`...\n\n\U0001f389 Update ran successfully! Please restart Codex.\n",
        )

    def test_run_update_action_raises_on_failure_status(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "`npm install -g @openai/codex` failed with status 7"):
            run_update_action(UpdateAction.NPM_GLOBAL_LATEST, stdout=StringIO(), runner=lambda _command, _args: 7)

    def test_run_update_action_requires_explicit_runner(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "runner callback is required"):
            run_update_action(UpdateAction.NPM_GLOBAL_LATEST, stdout=StringIO())


if __name__ == "__main__":
    unittest.main()
