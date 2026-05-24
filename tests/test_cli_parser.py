import unittest

from pycodex.cli.parser import CliParseError, parse_args
from pycodex.protocol import AskForApproval, ProfileV2Name, SandboxMode


class TopLevelCliParserTests(unittest.TestCase):
    def test_no_args_defaults_to_interactive_mode(self):
        parsed = parse_args([])

        self.assertTrue(parsed.is_interactive)
        self.assertIsNone(parsed.command)
        self.assertIsNone(parsed.prompt)

    def test_single_positional_without_subcommand_is_prompt(self):
        parsed = parse_args(["fix the failing tests"])

        self.assertTrue(parsed.is_interactive)
        self.assertEqual(parsed.prompt, "fix the failing tests")

    def test_exec_command_and_visible_alias_map_to_canonical_name(self):
        parsed = parse_args(["exec", "hello"])
        alias = parse_args(["e", "hello"])

        self.assertEqual(parsed.command, "exec")
        self.assertEqual(alias.command, "exec")
        self.assertEqual(parsed.command_args, ("hello",))
        self.assertEqual(alias.command_args, ("hello",))
        self.assertEqual(parsed.exec_cli().prompt, "hello")

    def test_apply_alias_maps_to_canonical_name(self):
        parsed = parse_args(["a", "--check"])

        self.assertEqual(parsed.command, "apply")
        self.assertEqual(parsed.command_args, ("--check",))

    def test_hyphenated_commands_match_upstream_clap_names(self):
        for name in ("mcp-server", "app-server", "remote-control", "exec-server"):
            with self.subTest(name=name):
                self.assertEqual(parse_args([name]).command, name)

    def test_cloud_tasks_alias_matches_cloud_command(self):
        parsed = parse_args(["cloud-tasks", "list"])

        self.assertEqual(parsed.command, "cloud")
        self.assertEqual(parsed.command_args, ("list",))

    def test_root_options_are_collected_before_subcommand(self):
        parsed = parse_args(
            [
                "-c",
                "model=gpt-5",
                "--enable",
                "unified_exec",
                "--disable=old_flow",
                "--remote",
                "ws://127.0.0.1:1234",
                "--strict-config",
                "exec",
                "prompt",
            ]
        )

        self.assertEqual(parsed.command, "exec")
        self.assertEqual(parsed.config_overrides, ("model=gpt-5",))
        self.assertEqual(parsed.enable, ("unified_exec",))
        self.assertEqual(parsed.disable, ("old_flow",))
        self.assertEqual(parsed.remote, "ws://127.0.0.1:1234")
        self.assertTrue(parsed.strict_config)
        self.assertEqual(parsed.command_args, ("prompt",))

    def test_exec_inherits_root_shared_options_like_upstream_main(self):
        parsed = parse_args(
            [
                "--image",
                "root.png",
                "--model",
                "gpt-5.2",
                "--sandbox",
                "workspace-write",
                "--add-dir",
                "root-extra",
                "exec",
                "--image",
                "exec.png",
                "--add-dir",
                "exec-extra",
                "summarize",
            ]
        )
        exec_cli = parsed.exec_cli()

        self.assertEqual(exec_cli.images, ("root.png", "exec.png"))
        self.assertEqual(exec_cli.model, "gpt-5.2")
        self.assertIs(exec_cli.sandbox, SandboxMode.WORKSPACE_WRITE)
        self.assertEqual(exec_cli.add_dir, ("root-extra", "exec-extra"))

    def test_root_config_overrides_parse_with_shared_config_logic(self):
        parsed = parse_args(["-c", "use_legacy_landlock=true", "-c", "model=gpt-5"])
        overrides = parsed.parsed_config_overrides()

        self.assertEqual(overrides[0].path, "features.use_legacy_landlock")
        self.assertIs(overrides[0].value, True)
        self.assertEqual(overrides[1].path, "model")
        self.assertEqual(overrides[1].value, "gpt-5")

    def test_config_option_preserves_empty_raw_value_for_later_parse_error(self):
        parsed = parse_args(["--config="])

        self.assertEqual(parsed.config_overrides, ("",))

    def test_shared_interactive_options_are_collected(self):
        parsed = parse_args(
            [
                "--image",
                "a.png,b.png",
                "-m",
                "gpt-5",
                "--oss",
                "--sandbox",
                "workspace-write",
                "--ask-for-approval",
                "untrusted",
                "--profile",
                "work",
                "-C",
                "work",
                "--add-dir",
                "extra",
                "hello",
            ]
        )

        self.assertEqual(parsed.prompt, "hello")
        self.assertEqual(parsed.root_options["images"], ("a.png", "b.png"))
        self.assertEqual(parsed.root_options["model"], "gpt-5")
        self.assertTrue(parsed.root_options["oss"])
        self.assertIs(parsed.root_options["sandbox"], SandboxMode.WORKSPACE_WRITE)
        self.assertIs(parsed.root_options["approval_policy"], AskForApproval.UNLESS_TRUSTED)
        self.assertEqual(parsed.root_options["profile"], ProfileV2Name("work"))
        self.assertEqual(parsed.root_options["cwd"], "work")
        self.assertEqual(parsed.root_options["add_dir"], ("extra",))

    def test_invalid_typed_shared_options_error(self):
        for args, pattern in (
            (["--sandbox", "workspace_write"], "invalid SandboxMode"),
            (["--ask-for-approval", "sometimes"], "invalid AskForApproval"),
            (["--profile", "../work"], "invalid --profile"),
        ):
            with self.subTest(args=args):
                with self.assertRaisesRegex(CliParseError, pattern):
                    parse_args(args)

    def test_extra_interactive_positionals_error_like_optional_prompt(self):
        with self.assertRaisesRegex(CliParseError, "Unexpected extra argument"):
            parse_args(["first", "second"])

    def test_unknown_root_option_errors(self):
        with self.assertRaisesRegex(CliParseError, "Unknown option"):
            parse_args(["--definitely-not-a-codex-option"])

    def test_help_text_hides_hidden_commands(self):
        with self.assertRaises(CliParseError) as ctx:
            parse_args(["--help"])

        help_text = str(ctx.exception)
        self.assertIn("exec", help_text)
        self.assertIn("app-server", help_text)
        self.assertNotIn("responses-api-proxy", help_text)
        self.assertNotIn("stdio-to-uds", help_text)


if __name__ == "__main__":
    unittest.main()
