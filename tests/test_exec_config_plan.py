import tempfile
import unittest
from pathlib import Path

from pycodex.exec import (
    ExecConfigPlanError,
    NO_DEFAULT_OSS_PROVIDER_MESSAGE,
    build_exec_config_bootstrap_plan,
    exec_harness_overrides_from_cli,
    exec_model_override,
    exec_model_provider_override,
    exec_sandbox_mode_from_cli,
    get_default_model_for_oss_provider,
    parse_exec_args,
    resolve_exec_config_cwd,
    resolve_oss_provider,
)
from pycodex.protocol import AskForApproval, SandboxMode


class ExecConfigPlanTests(unittest.TestCase):
    def test_sandbox_mode_precedence_matches_exec_run_main(self):
        self.assertIs(exec_sandbox_mode_from_cli(parse_exec_args(["--sandbox", "read-only", "prompt"])), SandboxMode.READ_ONLY)
        self.assertIs(exec_sandbox_mode_from_cli(parse_exec_args(["--full-auto", "prompt"])), SandboxMode.WORKSPACE_WRITE)
        self.assertIs(
            exec_sandbox_mode_from_cli(parse_exec_args(["--dangerously-bypass-approvals-and-sandbox", "prompt"])),
            SandboxMode.DANGER_FULL_ACCESS,
        )

    def test_oss_provider_resolution_matches_cli_then_config_order(self):
        self.assertEqual(resolve_oss_provider("lmstudio", {"oss_provider": "ollama"}), "lmstudio")
        self.assertEqual(resolve_oss_provider(None, {"oss_provider": "ollama"}), "ollama")
        self.assertIsNone(resolve_oss_provider(None, {}))

    def test_oss_default_models_match_upstream_util(self):
        self.assertEqual(get_default_model_for_oss_provider("lmstudio"), "openai/gpt-oss-20b")
        self.assertEqual(get_default_model_for_oss_provider("ollama"), "gpt-oss:20b")
        self.assertIsNone(get_default_model_for_oss_provider("custom"))

    def test_exec_model_and_provider_overrides_follow_oss_rules(self):
        explicit = parse_exec_args(["--oss", "--local-provider", "lmstudio", "prompt"])
        self.assertEqual(exec_model_provider_override(explicit, {"oss_provider": "ollama"}), "lmstudio")
        self.assertEqual(exec_model_override(explicit, "lmstudio"), "openai/gpt-oss-20b")

        configured = parse_exec_args(["--oss", "prompt"])
        self.assertEqual(exec_model_provider_override(configured, {"oss_provider": "ollama"}), "ollama")
        self.assertEqual(exec_model_override(configured, "ollama"), "gpt-oss:20b")

        model_wins = parse_exec_args(["--oss", "--local-provider", "lmstudio", "--model", "custom-model", "prompt"])
        self.assertEqual(exec_model_override(model_wins, "lmstudio"), "custom-model")

    def test_exec_oss_requires_provider_like_upstream(self):
        with self.assertRaisesRegex(ExecConfigPlanError, "No default OSS provider configured"):
            exec_model_provider_override(parse_exec_args(["--oss", "prompt"]), {})
        self.assertEqual(str(NO_DEFAULT_OSS_PROVIDER_MESSAGE), NO_DEFAULT_OSS_PROVIDER_MESSAGE)

    def test_exec_model_and_provider_can_come_from_config_toml(self):
        cli = parse_exec_args(["prompt"])

        self.assertEqual(exec_model_provider_override(cli, {"model_provider": "local-openai"}), "local-openai")
        self.assertEqual(exec_model_override(cli, config_toml={"model": "gpt-config"}), "gpt-config")

    def test_harness_overrides_mapping_matches_upstream_config_overrides_slice(self):
        cli = parse_exec_args(
            [
                "--oss",
                "--local-provider",
                "lmstudio",
                "--ephemeral",
                "--dangerously-bypass-hook-trust",
                "--add-dir",
                "extra",
                "--sandbox",
                "workspace-write",
                "prompt",
            ]
        )

        overrides = exec_harness_overrides_from_cli(cli)

        self.assertEqual(
            overrides.to_mapping(),
            {
                "model": "openai/gpt-oss-20b",
                "approvalPolicy": "never",
                "sandboxMode": "workspace-write",
                "modelProvider": "lmstudio",
                "showRawAgentReasoning": True,
                "ephemeral": True,
                "bypassHookTrust": True,
                "additionalWritableRoots": ["extra"],
            },
        )
        self.assertIs(overrides.approval_policy, AskForApproval.NEVER)

    def test_build_exec_config_bootstrap_plan_resolves_cwd_and_cli_overrides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            extra = root / "extra"
            extra.mkdir()
            cli = parse_exec_args(
                [
                    "--strict-config",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "-C",
                    "project",
                    "--add-dir",
                    str(extra),
                    "-c",
                    "model='gpt-5.2'",
                    "prompt",
                ]
            )

            plan = build_exec_config_bootstrap_plan(cli, current_dir=root)

        self.assertEqual(plan.config_cwd, project.resolve())
        self.assertTrue(plan.strict_config)
        self.assertTrue(plan.ignore_user_config)
        self.assertTrue(plan.ignore_rules)
        self.assertEqual([(override.path, override.value) for override in plan.cli_overrides], [("model", "gpt-5.2")])
        self.assertEqual(plan.harness_overrides.additional_writable_roots, (extra,))
        self.assertEqual(plan.harness_overrides.to_mapping()["cwd"], "project")

    def test_build_exec_config_bootstrap_plan_uses_config_model_and_provider(self):
        cli = parse_exec_args(["prompt"])

        plan = build_exec_config_bootstrap_plan(
            cli,
            config_toml={"model": "gpt-config", "model_provider": "local-openai"},
            current_dir=Path.cwd(),
        )

        self.assertEqual(plan.harness_overrides.model, "gpt-config")
        self.assertEqual(plan.harness_overrides.model_provider, "local-openai")

    def test_resolve_exec_config_cwd_rejects_missing_cd_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cli = parse_exec_args(["-C", "missing", "prompt"])
            with self.assertRaisesRegex(ExecConfigPlanError, "Failed to resolve -C/--cd path"):
                resolve_exec_config_cwd(cli, current_dir=tmpdir)


if __name__ == "__main__":
    unittest.main()
