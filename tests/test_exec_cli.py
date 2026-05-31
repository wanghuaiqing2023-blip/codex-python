import unittest

from pycodex.exec import Color, ExecCliParseError, parse_exec_args
from pycodex.protocol import ProfileV2Name, SandboxMode


class ExecCliTests(unittest.TestCase):
    def test_exec_prompt_without_subcommand(self):
        cli = parse_exec_args(["summarize"])

        self.assertIsNone(cli.command)
        self.assertEqual(cli.prompt, "summarize")

    def test_root_config_overrides_are_prepended_before_exec_overrides(self):
        cli = parse_exec_args(["-c", "model='inner'", "summarize"], root_config_overrides=("sandbox='read-only'",))

        self.assertEqual(cli.config_overrides, ("sandbox='read-only'", "model='inner'"))

    def test_resume_parses_prompt_after_global_flags(self):
        prompt = "echo resume-with-global-flags-after-subcommand"
        cli = parse_exec_args(
            [
                "resume",
                "--last",
                "--json",
                "--model",
                "gpt-5.2-codex",
                "--config",
                "openai_base_url='http://localhost:1234/v1'",
                "--config",
                "reasoning_level='xhigh'",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                prompt,
            ]
        )

        self.assertTrue(cli.ephemeral)
        self.assertTrue(cli.ignore_user_config)
        self.assertTrue(cli.ignore_rules)
        self.assertTrue(cli.json)
        self.assertEqual(cli.model, "gpt-5.2-codex")
        self.assertEqual(
            cli.config_overrides,
            ("openai_base_url='http://localhost:1234/v1'", "reasoning_level='xhigh'"),
        )
        self.assertEqual(cli.command, "resume")
        self.assertIsNotNone(cli.resume)
        self.assertEqual(cli.resume.prompt, prompt)
        self.assertIsNone(cli.resume.session_id)

    def test_resume_accepts_output_flags_after_subcommand(self):
        prompt = "echo resume-with-output-file"
        cli = parse_exec_args(
            [
                "resume",
                "session-123",
                "-o",
                "/tmp/resume-output.md",
                "--output-schema",
                "/tmp/schema.json",
                prompt,
            ]
        )

        self.assertEqual(cli.last_message_file, "/tmp/resume-output.md")
        self.assertEqual(cli.output_schema, "/tmp/schema.json")
        self.assertIsNotNone(cli.resume)
        self.assertEqual(cli.resume.session_id, "session-123")
        self.assertEqual(cli.resume.prompt, prompt)

    def test_resume_collects_resume_images(self):
        cli = parse_exec_args(["resume", "--last", "--image", "a.png,b.png", "hello"])

        self.assertIsNotNone(cli.resume)
        self.assertEqual(cli.resume.images, ("a.png", "b.png"))
        self.assertEqual(cli.resume.prompt, "hello")

    def test_parses_config_isolation_flags(self):
        cli = parse_exec_args(["--ignore-user-config", "--ignore-rules", "summarize"])

        self.assertTrue(cli.ignore_user_config)
        self.assertTrue(cli.ignore_rules)

    def test_removed_full_auto_flag_reports_migration_path(self):
        cli = parse_exec_args(["--full-auto", "summarize"])

        self.assertEqual(
            cli.removed_full_auto_warning(),
            "warning: `--full-auto` is deprecated; use `--sandbox workspace-write` instead.",
        )
        self.assertIs(cli.effective_sandbox_mode(), SandboxMode.WORKSPACE_WRITE)

    def test_dangerous_bypass_projects_to_danger_full_access(self):
        cli = parse_exec_args(["--dangerously-bypass-approvals-and-sandbox", "summarize"])

        self.assertIs(cli.effective_sandbox_mode(), SandboxMode.DANGER_FULL_ACCESS)

    def test_full_auto_conflicts_with_dangerous_bypass_flag(self):
        with self.assertRaisesRegex(ExecCliParseError, "conflicts"):
            parse_exec_args(["--full-auto", "--dangerously-bypass-approvals-and-sandbox", "summarize"])

    def test_exec_shared_options_parse_before_subcommand(self):
        cli = parse_exec_args(
            [
                "-c",
                "model=gpt-5",
                "--image",
                "a.png",
                "--color",
                "always",
                "--profile",
                "work",
                "--sandbox",
                "workspace-write",
                "-C",
                "repo",
                "--add-dir",
                "extra",
                "summarize",
            ]
        )

        self.assertEqual(cli.config_overrides, ("model=gpt-5",))
        self.assertEqual(cli.images, ("a.png",))
        self.assertIs(cli.color, Color.ALWAYS)
        self.assertEqual(cli.profile, ProfileV2Name("work"))
        self.assertIs(cli.sandbox, SandboxMode.WORKSPACE_WRITE)
        self.assertEqual(cli.cwd, "repo")
        self.assertEqual(cli.add_dir, ("extra",))

    def test_exec_only_shared_option_is_rejected_after_subcommand(self):
        with self.assertRaisesRegex(ExecCliParseError, "Unknown review option"):
            parse_exec_args(["review", "--sandbox", "workspace-write"])

    def test_review_commit_title_requires_commit(self):
        with self.assertRaisesRegex(ExecCliParseError, "requires --commit"):
            parse_exec_args(["review", "--title", "Nice commit"])

    def test_review_targets_conflict(self):
        with self.assertRaisesRegex(ExecCliParseError, "mutually exclusive"):
            parse_exec_args(["review", "--base", "main", "custom prompt"])

    def test_review_commit_target(self):
        cli = parse_exec_args(["review", "--commit", "abc123", "--title", "Fix"])

        self.assertEqual(cli.command, "review")
        self.assertIsNotNone(cli.review)
        self.assertEqual(cli.review.commit, "abc123")
        self.assertEqual(cli.review.commit_title, "Fix")


if __name__ == "__main__":
    unittest.main()
