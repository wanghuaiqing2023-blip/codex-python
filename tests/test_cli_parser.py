import unittest
import io
import os
import tempfile
from pathlib import Path

from pycodex.cli.features import (
    FeatureCliError,
    FeatureToggles,
    FeaturesSubcommand,
    format_features_list,
    parse_features_args,
    run_features_command,
    under_development_feature_warning,
)
from pycodex.cli.parser import CliParseError, main, parse_args, reject_remote_mode_for_subcommand
from pycodex.core import Feature, Features
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

    def test_exec_cli_rejects_root_remote_like_upstream_noninteractive_dispatch(self):
        parsed = parse_args(["--remote", "ws://127.0.0.1:1234", "exec", "prompt"])

        with self.assertRaisesRegex(CliParseError, "only supported for interactive TUI commands"):
            parsed.exec_cli()

    def test_main_rejects_remote_auth_token_env_for_noninteractive_subcommand(self):
        stderr = io.StringIO()

        code = main(["--remote-auth-token-env", "CODEX_REMOTE_AUTH_TOKEN", "exec", "prompt"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex exec`", stderr.getvalue())

    def test_remote_mode_rejection_messages_match_upstream(self):
        with self.assertRaisesRegex(CliParseError, "`--remote ws://localhost:4500`"):
            reject_remote_mode_for_subcommand("ws://localhost:4500", None, "remote-control")
        with self.assertRaisesRegex(CliParseError, "`--remote-auth-token-env`"):
            reject_remote_mode_for_subcommand(None, "CODEX_REMOTE_AUTH_TOKEN", "exec")

    def test_feature_toggles_known_features_generate_overrides(self):
        toggles = FeatureToggles(
            enable=("web_search_request",),
            disable=("unified_exec",),
        )

        self.assertEqual(
            toggles.to_overrides(),
            [
                "features.web_search_request=true",
                "features.unified_exec=false",
            ],
        )

    def test_feature_toggles_accept_removed_and_legacy_flags(self):
        self.assertEqual(
            FeatureToggles(enable=("use_linux_sandbox_bwrap",)).to_overrides(),
            ["features.use_linux_sandbox_bwrap=true"],
        )
        self.assertEqual(
            FeatureToggles(enable=("image_detail_original",)).to_overrides(),
            ["features.image_detail_original=true"],
        )

    def test_feature_toggles_unknown_feature_errors(self):
        with self.assertRaisesRegex(FeatureCliError, "Unknown feature flag: does_not_exist"):
            FeatureToggles(enable=("does_not_exist",)).to_overrides()

    def test_root_feature_toggles_are_folded_after_config_overrides(self):
        parsed = parse_args(
            [
                "-c",
                "features.unified_exec=true",
                "--disable",
                "unified_exec",
                "--enable",
                "web_search_request",
            ]
        )

        self.assertEqual(
            parsed.config_overrides_with_feature_toggles(),
            (
                "features.unified_exec=true",
                "features.web_search_request=true",
                "features.unified_exec=false",
            ),
        )
        parsed_overrides = parsed.parsed_config_overrides()
        self.assertEqual(parsed_overrides[-2].path, "features.web_search_request")
        self.assertIs(parsed_overrides[-2].value, True)
        self.assertEqual(parsed_overrides[-1].path, "features.unified_exec")
        self.assertIs(parsed_overrides[-1].value, False)

    def test_exec_inherits_feature_toggle_overrides(self):
        parsed = parse_args(["--enable", "web_search_request", "exec", "prompt"])

        self.assertEqual(parsed.exec_cli().config_overrides, ("features.web_search_request=true",))

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

    def test_features_enable_and_disable_parse_feature_name(self):
        enabled = parse_args(["features", "enable", "unified_exec"]).features_cli()
        disabled = parse_args(["features", "disable", "shell_tool"]).features_cli()

        self.assertIs(enabled.subcommand, FeaturesSubcommand.ENABLE)
        self.assertEqual(enabled.args.feature, "unified_exec")
        self.assertIs(disabled.subcommand, FeaturesSubcommand.DISABLE)
        self.assertEqual(disabled.args.feature, "shell_tool")

    def test_features_list_parses_without_extra_args(self):
        listed = parse_features_args(["list"])

        self.assertIs(listed.subcommand, FeaturesSubcommand.LIST)
        self.assertIsNone(listed.args)

    def test_features_subcommands_reject_bad_shape(self):
        for args, pattern in (
            (["features"], "features requires a subcommand"),
            (["features", "list", "extra"], "does not accept extra"),
            (["features", "enable"], "requires exactly one feature"),
            (["features", "enable", "does_not_exist"], "Unknown feature flag"),
        ):
            with self.subTest(args=args):
                with self.assertRaisesRegex(CliParseError, pattern):
                    parse_args(args).features_cli()

    def test_main_validates_unknown_feature_toggles_before_dispatch(self):
        stderr = io.StringIO()

        code = main(["--strict-config", "--enable", "does_not_exist"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Unknown feature flag: does_not_exist", stderr.getvalue())

    def test_features_list_command_reads_config_and_root_overrides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "config.toml").write_text("[features]\nshell_tool = false\n", encoding="utf-8")
            stdout = io.StringIO()

            code = run_features_command(
                parse_features_args(["list"]),
                raw_config_overrides=("features.network_proxy=true",),
                codex_home=home,
                stdout=stdout,
            )

            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertTrue(any(line.startswith("network_proxy") and line.endswith("true") for line in output.splitlines()))
            self.assertTrue(any(line.startswith("shell_tool") and line.endswith("false") for line in output.splitlines()))

    def test_features_enable_command_writes_config_and_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            stdout = io.StringIO()
            stderr = io.StringIO()

            code = run_features_command(
                parse_features_args(["enable", "code_mode"]),
                codex_home=home,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertIn("Enabled feature `code_mode` in config.toml.", stdout.getvalue())
            self.assertIn("Under-development features enabled: code_mode", stderr.getvalue())
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "[features]\ncode_mode = true\n")

    def test_features_disable_command_clears_default_false_and_sets_default_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "config.toml").write_text("[features]\nnetwork_proxy = true\n", encoding="utf-8")
            stdout = io.StringIO()

            code = run_features_command(
                parse_features_args(["disable", "network_proxy"]),
                codex_home=home,
                stdout=stdout,
            )

            self.assertEqual(code, 0)
            self.assertIn("Disabled feature `network_proxy` in config.toml.", stdout.getvalue())
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "[features]\n")

            run_features_command(parse_features_args(["disable", "shell_tool"]), codex_home=home, stdout=io.StringIO())
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "[features]\nshell_tool = false\n")

    def test_main_features_enable_uses_codex_home(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                code = main(["features", "enable", "network_proxy"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

            self.assertEqual(code, 0)
            self.assertIn("Enabled feature `network_proxy` in config.toml.", stdout.getvalue())
            self.assertEqual(
                (Path(tmpdir) / "config.toml").read_text(encoding="utf-8"),
                "[features]\nnetwork_proxy = true\n",
            )

    def test_format_features_list_matches_upstream_columns(self):
        features = Features.with_defaults()
        features.enable(Feature.CODE_MODE)

        output = format_features_list(features)
        lines = output.splitlines()

        self.assertEqual(lines, sorted(lines))
        self.assertTrue(any(line.startswith("code_mode") and line.endswith("true") for line in lines))
        self.assertTrue(any("under development" in line for line in lines))

    def test_under_development_feature_warning_matches_cli_text(self):
        warning = under_development_feature_warning("C:/tmp/codex-home", "code_mode")

        self.assertIsNotNone(warning)
        self.assertIn("Under-development features enabled: code_mode", warning)
        self.assertIn("config.toml", warning)
        self.assertIsNone(under_development_feature_warning("C:/tmp/codex-home", "personality"))

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
