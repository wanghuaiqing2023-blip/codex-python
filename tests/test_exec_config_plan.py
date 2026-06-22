import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from pycodex.exec import (
    DEFAULT_ANALYTICS_ENABLED,
    EXEC_DEFAULT_LOG_FILTER,
    EXEC_UNTRUSTED_DIRECTORY_MESSAGE,
    ExecConfigPlanError,
    NO_DEFAULT_OSS_PROVIDER_MESSAGE,
    build_exec_config_bootstrap_plan,
    build_exec_otel_provider,
    build_exec_run_main_plan,
    build_exec_runtime_request_sequence,
    build_exec_runtime_startup_plan,
    exec_session_config_from_bootstrap_plan,
    ensure_exec_trusted_directory,
    exec_trusted_directory_check,
    exec_harness_overrides_from_cli,
    exec_model_override,
    exec_model_provider_override,
    exec_sandbox_mode_from_cli,
    get_default_model_for_oss_provider,
    exec_session_startup_result_from_responses,
    initial_operation_request_from_startup_plan,
    next_initial_operation_request_from_startup_plan,
    parse_exec_args,
    RequestIdSequencer,
    resolve_exec_config_cwd,
    resolve_oss_provider,
    thread_bootstrap_result_from_response,
    thread_bootstrap_request_from_startup_plan,
)
from pycodex.arg0 import Arg0DispatchPaths
from pycodex.protocol import AskForApproval, GranularApprovalConfig, SandboxMode


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

    def test_exec_otel_defaults_match_upstream_exec_main(self):
        self.assertTrue(DEFAULT_ANALYTICS_ENABLED)
        self.assertEqual(EXEC_DEFAULT_LOG_FILTER, "error,opentelemetry_sdk=off,opentelemetry_otlp=off")

        provider = build_exec_otel_provider({"otel": {"metrics_exporter": "statsig"}, "codex_home": "/tmp/codex"}, "1.0")

        self.assertIsNotNone(provider)
        assert provider is not None
        self.assertEqual(provider.settings.metrics_exporter.kind, "statsig")

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

    def test_exec_harness_overrides_preserves_cli_approval_policy(self):
        cli = replace(parse_exec_args(["prompt"]), approval_policy=AskForApproval.ON_REQUEST)

        overrides = exec_harness_overrides_from_cli(cli)

        self.assertIs(overrides.approval_policy, AskForApproval.ON_REQUEST)
        self.assertEqual(overrides.to_mapping()["approvalPolicy"], "on-request")

    def test_exec_harness_overrides_serializes_granular_approval_policy(self):
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=False,
            request_permissions=True,
            mcp_elicitations=False,
        )
        cli = replace(parse_exec_args(["prompt"]), approval_policy=granular)

        overrides = exec_harness_overrides_from_cli(cli)

        self.assertEqual(overrides.approval_policy, granular)
        self.assertEqual(overrides.to_mapping()["approvalPolicy"], {"granular": granular.to_mapping()})

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

    def test_exec_session_config_from_bootstrap_plan_projects_runtime_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            extra = root / "extra"
            project.mkdir()
            extra.mkdir()
            cli = parse_exec_args(
                [
                    "--model",
                    "gpt-5.2-codex",
                    "--local-provider",
                    "openai",
                    "--sandbox",
                    "workspace-write",
                    "--ephemeral",
                    "-C",
                    "project",
                    "--add-dir",
                    str(extra),
                    "prompt",
                ]
            )
            plan = build_exec_config_bootstrap_plan(
                cli,
                config_toml={
                    "user_instructions": "project rules",
                    "project_doc_max_bytes": 0,
                },
                current_dir=root,
            )

        config = exec_session_config_from_bootstrap_plan(plan)

        self.assertEqual(config.model, "gpt-5.2-codex")
        self.assertEqual(config.model_provider_id, "openai")
        self.assertEqual(config.cwd, project.resolve())
        self.assertEqual(config.workspace_roots, (project.resolve(), extra))
        self.assertEqual(config.user_instructions, "project rules")
        self.assertIs(config.approval_policy, AskForApproval.NEVER)
        self.assertEqual(
            config.permission_profile.to_legacy_sandbox_policy(project.resolve()).type,
            SandboxMode.WORKSPACE_WRITE.value,
        )
        self.assertTrue(config.ephemeral)
        self.assertFalse(config.show_raw_agent_reasoning)
        self.assertTrue(config.allow_login_shell)
        self.assertFalse(config.exec_permission_approvals_enabled)
        self.assertFalse(config.request_permissions_tool_enabled)

    def test_exec_session_config_projects_shell_feature_flags_from_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cli = parse_exec_args(["prompt"])
            plan = build_exec_config_bootstrap_plan(
                cli,
                config_toml={
                    "allow_login_shell": False,
                    "features": {
                        "exec_permission_approvals": True,
                        "request_permissions_tool": True,
                    },
                },
                current_dir=root,
            )

        config = exec_session_config_from_bootstrap_plan(plan)

        self.assertFalse(config.allow_login_shell)
        self.assertTrue(config.exec_permission_approvals_enabled)
        self.assertTrue(config.request_permissions_tool_enabled)

    def test_exec_session_config_applies_cli_overrides_before_projecting_shell_features(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cli = parse_exec_args(
                [
                    "-c",
                    "allow_login_shell=true",
                    "-c",
                    "features.exec_permission_approvals=false",
                    "-c",
                    "features.request_permissions_tool=true",
                    "prompt",
                ]
            )
            plan = build_exec_config_bootstrap_plan(
                cli,
                config_toml={
                    "allow_login_shell": False,
                    "features": {
                        "exec_permission_approvals": True,
                        "request_permissions_tool": False,
                    },
                },
                current_dir=root,
            )

        config = exec_session_config_from_bootstrap_plan(plan)

        self.assertTrue(config.allow_login_shell)
        self.assertFalse(config.exec_permission_approvals_enabled)
        self.assertTrue(config.request_permissions_tool_enabled)

    def test_exec_session_config_projects_oss_raw_reasoning_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cli = parse_exec_args(["--oss", "--local-provider", "lmstudio", "prompt"])
            plan = build_exec_config_bootstrap_plan(cli, current_dir=root)

        config = exec_session_config_from_bootstrap_plan(plan)

        self.assertTrue(config.show_raw_agent_reasoning)

    def test_exec_session_config_preserves_multiple_add_dir_workspace_roots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            extra_one = root / "extra-one"
            extra_two = root / "extra-two"
            extra_three = root / "extra-three"
            project.mkdir()
            extra_one.mkdir()
            extra_two.mkdir()
            extra_three.mkdir()
            cli = parse_exec_args(
                [
                    "-C",
                    "project",
                    "--sandbox",
                    "workspace-write",
                    "--add-dir",
                    str(extra_one),
                    "--add-dir",
                    str(extra_two),
                    "--add-dir",
                    str(extra_three),
                    "prompt",
                ]
            )
            plan = build_exec_config_bootstrap_plan(cli, current_dir=root)

        config = exec_session_config_from_bootstrap_plan(plan)

        self.assertEqual(
            config.workspace_roots,
            (project.resolve(), extra_one, extra_two, extra_three),
        )
        legacy_sandbox = config.permission_profile.to_legacy_sandbox_policy(project.resolve())
        self.assertEqual(legacy_sandbox.type, SandboxMode.WORKSPACE_WRITE.value)
        self.assertEqual(legacy_sandbox.writable_roots, (extra_one, extra_two, extra_three))
        self.assertEqual(
            plan.harness_overrides.to_mapping()["additionalWritableRoots"],
            [str(extra_one), str(extra_two), str(extra_three)],
        )

    def test_build_exec_runtime_startup_plan_composes_config_session_and_run_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            (project / ".git").mkdir()
            cli = parse_exec_args(
                [
                    "--model",
                    "gpt-5.2-codex",
                    "-C",
                    "project",
                    "Summarize this concisely",
                ]
            )
            startup = build_exec_runtime_startup_plan(
                cli,
                config_toml={"model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )

        self.assertEqual(startup.bootstrap_plan.config_cwd, project.resolve())
        self.assertEqual(startup.session_config.model, "gpt-5.2-codex")
        self.assertEqual(startup.session_config.model_provider_id, "openai")
        self.assertEqual(startup.session_config.cwd, project.resolve())
        self.assertEqual(startup.run_plan.initial_operation.kind, "user_turn")
        self.assertEqual(startup.run_plan.prompt_summary, "Summarize this concisely")
        self.assertEqual(startup.to_mapping()["runPlan"]["initialOperation"], "user_turn")
        self.assertTrue(startup.trusted_directory_check.allowed)
        self.assertEqual(startup.trusted_directory_check.git_repo_root, project.resolve())

    def test_build_exec_run_main_plan_matches_in_process_startup_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cli = parse_exec_args(
                [
                    "--json",
                    "--ignore-user-config",
                    "--strict-config",
                    "-c",
                    "model='gpt-5.2-codex'",
                    "hello",
                ]
            )
            plan = build_exec_run_main_plan(
                cli,
                arg0_paths=Arg0DispatchPaths(codex_self_exe=root / "bin" / "codex"),
                config_toml={"user_instructions": "watch stdout"},
                current_dir=root,
                client_version="1.2.3",
            )

        self.assertEqual(plan.processor_kind, "json")
        self.assertEqual(plan.environment_manager_source, "env")
        self.assertEqual(plan.telemetry_service_name, "codex_exec")
        self.assertTrue(plan.analytics_enabled)
        self.assertEqual(plan.log_filter, EXEC_DEFAULT_LOG_FILTER)
        self.assertEqual(plan.in_process_start_args.client_name, "codex_exec")
        self.assertEqual(plan.in_process_start_args.client_version, "1.2.3")
        self.assertTrue(plan.in_process_start_args.strict_config)
        self.assertTrue(plan.in_process_start_args.enable_codex_api_key_env)
        self.assertTrue(plan.in_process_start_args.experimental_api)
        self.assertEqual(plan.in_process_start_args.channel_capacity, 1024)
        self.assertEqual(plan.in_process_start_args.session_source, "exec")
        self.assertEqual(plan.in_process_start_args.cli_overrides, [("model", "gpt-5.2-codex")])
        self.assertEqual(plan.startup.session_config.user_instructions, "watch stdout")
        self.assertEqual(plan.local_runtime_paths.codex_self_exe.as_path(), root / "bin" / "codex")
        self.assertEqual(plan.local_runtime_paths.codex_linux_sandbox_exe, None)

    def test_exec_trusted_directory_check_matches_upstream_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()

            with patch("pycodex.exec.config_plan.get_git_repo_root", return_value=None):
                blocked = exec_trusted_directory_check(parse_exec_args(["-C", "project", "prompt"]), project)
                skipped = exec_trusted_directory_check(parse_exec_args(["--skip-git-repo-check", "-C", "project", "prompt"]), project)
                yolo = exec_trusted_directory_check(
                    parse_exec_args(["--dangerously-bypass-approvals-and-sandbox", "-C", "project", "prompt"]),
                    project,
                )
            allowed = exec_trusted_directory_check(
                parse_exec_args(["-C", "project", "prompt"]),
                project,
                git_repo_root=project,
            )

        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.message, EXEC_UNTRUSTED_DIRECTORY_MESSAGE)
        self.assertTrue(skipped.allowed)
        self.assertTrue(skipped.skipped_by_flag)
        self.assertTrue(yolo.allowed)
        self.assertTrue(yolo.skipped_by_dangerous_bypass)
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.git_repo_root, project)

    def test_ensure_exec_trusted_directory_raises_upstream_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with patch("pycodex.exec.config_plan.get_git_repo_root", return_value=None):
                blocked = exec_trusted_directory_check(parse_exec_args(["-C", "project", "prompt"]), project)

        with self.assertRaisesRegex(ExecConfigPlanError, "--skip-git-repo-check"):
            ensure_exec_trusted_directory(blocked)

    def test_thread_bootstrap_request_from_startup_plan_uses_session_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            startup = build_exec_runtime_startup_plan(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )

        bootstrap = thread_bootstrap_request_from_startup_plan(startup, 7)

        self.assertEqual(bootstrap.action, "start")
        self.assertEqual(bootstrap.method, "thread/start")
        payload = bootstrap.request.to_mapping()
        self.assertEqual(payload["requestId"], 7)
        self.assertEqual(payload["params"]["model"], "gpt-config")
        self.assertEqual(payload["params"]["modelProvider"], "openai")
        self.assertEqual(payload["params"]["cwd"], str(project.resolve()))

    def test_initial_operation_request_from_startup_plan_uses_run_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            startup = build_exec_runtime_startup_plan(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )

        request = initial_operation_request_from_startup_plan(startup, 8, "thread-1")

        self.assertEqual(request.method, "turn/start")
        payload = request.request.to_mapping()
        self.assertEqual(payload["requestId"], 8)
        self.assertEqual(payload["params"]["threadId"], "thread-1")
        self.assertEqual(payload["params"]["input"][0]["type"], "text")
        self.assertEqual(payload["params"]["input"][0]["text"], "Summarize")

    def test_next_initial_operation_request_from_startup_plan_uses_bootstrap_thread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            startup = build_exec_runtime_startup_plan(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )
            response = {
                "thread": {
                    "sessionId": "11111111-1111-4111-8111-111111111111",
                    "id": "22222222-2222-4222-8222-222222222222",
                    "threadSource": "user",
                    "name": "Started",
                    "path": None,
                },
                "model": "gpt-config",
                "modelProvider": "openai",
                "serviceTier": None,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "activePermissionProfile": None,
                "cwd": str(project.resolve()),
                "reasoningEffort": None,
            }
            bootstrap = thread_bootstrap_result_from_response("start", response, startup.session_config)

        request = next_initial_operation_request_from_startup_plan(startup, RequestIdSequencer(9), bootstrap)

        payload = request.request.to_mapping()
        self.assertEqual(payload["requestId"], 9)
        self.assertEqual(payload["params"]["threadId"], "22222222-2222-4222-8222-222222222222")
        self.assertEqual(payload["params"]["input"][0]["text"], "Summarize")

    def test_exec_session_startup_result_from_responses_composes_loop_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            startup = build_exec_runtime_startup_plan(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )
            bootstrap = thread_bootstrap_result_from_response(
                "start",
                {
                    "thread": {
                        "sessionId": "11111111-1111-4111-8111-111111111111",
                        "id": "22222222-2222-4222-8222-222222222222",
                        "threadSource": "user",
                        "name": "Started",
                        "path": None,
                    },
                    "model": "gpt-config",
                    "modelProvider": "openai",
                    "serviceTier": None,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "activePermissionProfile": None,
                    "cwd": str(project.resolve()),
                    "reasoningEffort": None,
                },
                startup.session_config,
            )

        result = exec_session_startup_result_from_responses(
            startup,
            bootstrap,
            initial_operation_method="turn/start",
            initial_operation_response={"turn": {"id": "turn-1"}},
        )

        self.assertEqual(result.loop_state.thread_id, "22222222-2222-4222-8222-222222222222")
        self.assertEqual(result.loop_state.turn_id, "turn-1")
        self.assertFalse(result.loop_state.thread_ephemeral)

    def test_build_exec_runtime_request_sequence_allocates_startup_request_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            sequence = build_exec_runtime_request_sequence(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )
            bootstrap = thread_bootstrap_result_from_response(
                "start",
                {
                    "thread": {
                        "sessionId": "11111111-1111-4111-8111-111111111111",
                        "id": "22222222-2222-4222-8222-222222222222",
                        "threadSource": "user",
                        "name": "Started",
                        "path": None,
                    },
                    "model": "gpt-config",
                    "modelProvider": "openai",
                    "serviceTier": None,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "activePermissionProfile": None,
                    "cwd": str(project.resolve()),
                    "reasoningEffort": None,
                },
                sequence.startup.session_config,
            )

        bootstrap_payload = sequence.bootstrap_request.request.to_mapping()
        initial_payload = sequence.next_initial_operation_request(bootstrap).request.to_mapping()
        startup_result = sequence.startup_result_from_responses(
            bootstrap,
            initial_operation_method="turn/start",
            initial_operation_response={"turn": {"id": "turn-1"}},
        )

        self.assertEqual(bootstrap_payload["requestId"], 1)
        self.assertEqual(bootstrap_payload["method"], "thread/start")
        self.assertEqual(initial_payload["requestId"], 2)
        self.assertEqual(initial_payload["method"], "turn/start")
        self.assertEqual(startup_result.loop_state.turn_id, "turn-1")

    def test_request_sequence_trusted_bootstrap_request_enforces_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            with patch("pycodex.exec.config_plan.get_git_repo_root", return_value=None):
                blocked = build_exec_runtime_request_sequence(
                    parse_exec_args(["-C", "project", "Summarize"]),
                    config_toml={"model": "gpt-config", "model_provider": "openai"},
                    current_dir=root,
                    stdin_is_terminal=True,
                )
            allowed = build_exec_runtime_request_sequence(
                parse_exec_args(["--skip-git-repo-check", "-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )

        with self.assertRaisesRegex(ExecConfigPlanError, "--skip-git-repo-check"):
            blocked.trusted_bootstrap_request()
        self.assertEqual(allowed.trusted_bootstrap_request().method, "thread/start")

    def test_runtime_request_sequence_builds_startup_processor_actions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            sequence = build_exec_runtime_request_sequence(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )
            bootstrap = thread_bootstrap_result_from_response(
                "start",
                {
                    "thread": {
                        "sessionId": "11111111-1111-4111-8111-111111111111",
                        "id": "22222222-2222-4222-8222-222222222222",
                        "threadSource": "user",
                        "name": "Started",
                        "path": None,
                    },
                    "model": "gpt-config",
                    "modelProvider": "openai",
                    "serviceTier": None,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "activePermissionProfile": None,
                    "cwd": str(project.resolve()),
                    "reasoningEffort": None,
                },
                sequence.startup.session_config,
            )

        startup_result = sequence.startup_result_from_responses(
            bootstrap,
            initial_operation_method="turn/start",
            initial_operation_response={"turn": {"id": "turn-1"}},
        )
        actions = sequence.startup_processor_actions(startup_result, system_bwrap_warning="sandbox warning")
        json_actions = sequence.startup_processor_actions(startup_result, json_mode=True, system_bwrap_warning="sandbox warning")

        self.assertEqual(actions[0].kind, "print_config_summary")
        self.assertEqual(actions[1].kind, "process_warning")
        self.assertEqual(actions[1].warning, "sandbox warning")
        self.assertEqual(tuple(action.kind for action in json_actions), ("print_config_summary",))

    def test_runtime_request_sequence_exec_loop_step_uses_startup_loop_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            sequence = build_exec_runtime_request_sequence(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )
            bootstrap = thread_bootstrap_result_from_response(
                "start",
                {
                    "thread": {
                        "sessionId": "11111111-1111-4111-8111-111111111111",
                        "id": "22222222-2222-4222-8222-222222222222",
                        "threadSource": "user",
                        "name": "Started",
                        "path": None,
                    },
                    "model": "gpt-config",
                    "modelProvider": "openai",
                    "serviceTier": None,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "activePermissionProfile": None,
                    "cwd": str(project.resolve()),
                    "reasoningEffort": None,
                },
                sequence.startup.session_config,
            )
            startup_result = sequence.startup_result_from_responses(
                bootstrap,
                initial_operation_method="turn/start",
                initial_operation_response={"turn": {"id": "turn-1"}},
            )

        step = sequence.exec_loop_step(
            startup_result,
            {
                "type": "server_notification",
                "notification": {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "22222222-2222-4222-8222-222222222222",
                        "turn": {"id": "turn-1", "status": "completed", "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}]},
                    },
                },
            },
        )

        self.assertTrue(step.decision.notification.should_process)
        self.assertEqual(step.notification_to_process["method"], "turn/completed")
        self.assertFalse(step.state.error_seen)

    def test_runtime_request_sequence_exec_loop_actions_from_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            sequence = build_exec_runtime_request_sequence(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )
            bootstrap = thread_bootstrap_result_from_response(
                "start",
                {
                    "thread": {
                        "sessionId": "11111111-1111-4111-8111-111111111111",
                        "id": "22222222-2222-4222-8222-222222222222",
                        "threadSource": "user",
                        "name": "Started",
                        "path": None,
                    },
                    "model": "gpt-config",
                    "modelProvider": "openai",
                    "serviceTier": None,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "activePermissionProfile": None,
                    "cwd": str(project.resolve()),
                    "reasoningEffort": None,
                },
                sequence.startup.session_config,
            )
            startup_result = sequence.startup_result_from_responses(
                bootstrap,
                initial_operation_method="turn/start",
                initial_operation_response={"turn": {"id": "turn-1"}},
            )

        actions = sequence.exec_loop_actions(
            startup_result,
            {
                "type": "server_notification",
                "notification": {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "22222222-2222-4222-8222-222222222222",
                        "turn": {"id": "turn-1", "status": "completed", "items": []},
                    },
                },
            },
        )

        self.assertEqual(tuple(action.kind for action in actions), ("send_request",))
        self.assertEqual(actions[0].client_request.method, "thread/read")

    def test_runtime_request_sequence_exec_loop_actions_after_thread_read_backfill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            project.mkdir()
            sequence = build_exec_runtime_request_sequence(
                parse_exec_args(["-C", "project", "Summarize"]),
                config_toml={"model": "gpt-config", "model_provider": "openai"},
                current_dir=root,
                stdin_is_terminal=True,
            )
            bootstrap = thread_bootstrap_result_from_response(
                "start",
                {
                    "thread": {
                        "sessionId": "11111111-1111-4111-8111-111111111111",
                        "id": "22222222-2222-4222-8222-222222222222",
                        "threadSource": "user",
                        "name": "Started",
                        "path": None,
                    },
                    "model": "gpt-config",
                    "modelProvider": "openai",
                    "serviceTier": None,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "activePermissionProfile": None,
                    "cwd": str(project.resolve()),
                    "reasoningEffort": None,
                },
                sequence.startup.session_config,
            )
            startup_result = sequence.startup_result_from_responses(
                bootstrap,
                initial_operation_method="turn/start",
                initial_operation_response={"turn": {"id": "turn-1"}},
            )

        event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-4222-8222-222222222222",
                    "turn": {"id": "turn-1", "status": "completed", "items": []},
                },
            },
        }
        thread_read_response = {
            "thread": {
                "id": "22222222-2222-4222-8222-222222222222",
                "turns": [
                    {
                        "id": "turn-1",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                    }
                ],
            }
        }

        actions = sequence.exec_loop_actions_with_thread_read_response(
            startup_result,
            event,
            thread_read_response,
        )

        self.assertEqual(tuple(action.kind for action in actions), ("process_notification",))
        self.assertEqual(actions[0].notification["params"]["turn"]["items"][0]["text"], "done")

    def test_resolve_exec_config_cwd_rejects_missing_cd_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cli = parse_exec_args(["-C", "missing", "prompt"])
            with self.assertRaisesRegex(ExecConfigPlanError, "Failed to resolve -C/--cd path"):
                resolve_exec_config_cwd(cli, current_dir=tmpdir)


if __name__ == "__main__":
    unittest.main()


class ExecRuntimeRequestSequenceShutdownActionsTest(unittest.TestCase):
    def test_runtime_request_sequence_shutdown_actions_unsubscribes_and_breaks(self) -> None:
        from pycodex.exec import (
            ExecCli,
            build_exec_runtime_request_sequence,
            thread_bootstrap_result_from_response,
        )

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        bootstrap = thread_bootstrap_result_from_response(
            sequence.bootstrap_request.action,
            {
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            sequence.startup.session_config,
        )
        startup_result = sequence.startup_result_from_responses(
            bootstrap,
            initial_operation_method="thread/turn/start",
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )
        event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                    },
                },
            },
        }

        actions = sequence.exec_loop_shutdown_actions(startup_result, event)

        self.assertEqual(
            [action.kind for action in actions],
            ["process_notification", "send_request", "break"],
        )
        self.assertEqual(actions[1].client_request.method, "thread/unsubscribe")
        self.assertEqual(actions[1].client_request.request_id, 2)
        self.assertEqual(
            actions[1].client_request.params.to_mapping(),
            {"threadId": "22222222-2222-2222-2222-222222222222"},
        )


class ExecRuntimeRequestSequenceStartupClientRequestsTest(unittest.TestCase):
    def test_runtime_request_sequence_exposes_ordered_startup_client_requests(self) -> None:
        from pycodex.exec import (
            ExecCli,
            build_exec_runtime_request_sequence,
            thread_bootstrap_result_from_response,
        )

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        bootstrap = thread_bootstrap_result_from_response(
            sequence.bootstrap_request.action,
            {
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            sequence.startup.session_config,
        )

        first_request, second_request = sequence.startup_client_requests_from_bootstrap_result(bootstrap)

        self.assertEqual(first_request.method, "thread/start")
        self.assertEqual(first_request.request_id, 1)
        self.assertEqual(second_request.method, "turn/start")
        self.assertEqual(second_request.request_id, 2)
        self.assertEqual(
            second_request.params.to_mapping()["threadId"],
            "22222222-2222-2222-2222-222222222222",
        )
        self.assertEqual(
            second_request.params.to_mapping()["input"],
            [{"type": "text", "text": "hello", "text_elements": []}],
        )


class ExecRuntimeRequestSequenceStartupResponsesTest(unittest.TestCase):
    def test_runtime_request_sequence_builds_startup_actions_from_request_responses(self) -> None:
        from pycodex.exec import ExecCli, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        bootstrap_response = {
            "thread": {
                "id": "22222222-2222-2222-2222-222222222222",
                "sessionId": "33333333-3333-3333-3333-333333333333",
            },
            "model": "gpt-5",
            "modelProvider": "openai",
            "historyLogId": 0,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "sandbox": "read-only",
            "cwd": "C:/Users/27605/codex-python",
            "config": {"instructionSources": [], "startupWarnings": []},
        }
        bootstrap = sequence.bootstrap_result_from_response(bootstrap_response)
        initial_request = sequence.next_initial_operation_request(bootstrap)

        actions = sequence.startup_processor_actions_from_request_responses(
            bootstrap_response=bootstrap_response,
            initial_operation_request=initial_request,
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )

        self.assertEqual([action.kind for action in actions], ["print_config_summary"])
        action_mapping = actions[0].to_mapping()
        self.assertEqual(action_mapping["sessionConfigured"]["thread_id"], "22222222-2222-2222-2222-222222222222")
        self.assertEqual(action_mapping["sessionConfigured"]["model"], "gpt-5")
        self.assertEqual(action_mapping["sessionConfigured"]["model_provider_id"], "openai")
        self.assertEqual(action_mapping["prompt"], "hello")


class ExecRuntimeRequestSequenceInitialRequestPlanTest(unittest.TestCase):
    def test_runtime_request_sequence_builds_initial_request_plan_from_bootstrap_response(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeInitialRequestPlan, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        bootstrap_response = {
            "thread": {
                "id": "22222222-2222-2222-2222-222222222222",
                "sessionId": "33333333-3333-3333-3333-333333333333",
            },
            "model": "gpt-5",
            "modelProvider": "openai",
            "historyLogId": 0,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "sandbox": "read-only",
            "cwd": "C:/Users/27605/codex-python",
            "config": {"instructionSources": [], "startupWarnings": []},
        }

        plan = sequence.initial_request_plan_from_bootstrap_response(bootstrap_response)

        self.assertIsInstance(plan, ExecRuntimeInitialRequestPlan)
        self.assertEqual(plan.request.method, "turn/start")
        self.assertEqual(plan.request.request_id, 2)
        self.assertEqual(
            plan.request.params.to_mapping()["threadId"],
            "22222222-2222-2222-2222-222222222222",
        )

    def test_runtime_request_sequence_builds_initial_client_request_from_bootstrap_response(self) -> None:
        from pycodex.exec import ExecCli, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        bootstrap_response = {
            "thread": {
                "id": "22222222-2222-2222-2222-222222222222",
                "sessionId": "33333333-3333-3333-3333-333333333333",
            },
            "model": "gpt-5",
            "modelProvider": "openai",
            "historyLogId": 0,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "sandbox": "read-only",
            "cwd": "C:/Users/27605/codex-python",
            "config": {"instructionSources": [], "startupWarnings": []},
        }

        request = sequence.initial_client_request_from_bootstrap_response(bootstrap_response)

        self.assertEqual(request.method, "turn/start")
        self.assertEqual(request.request_id, 2)


class ExecRuntimeRequestSequenceStartupExchangeTest(unittest.TestCase):
    def test_runtime_request_sequence_builds_startup_exchange_from_responses(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeStartupExchange, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        bootstrap_response = {
            "thread": {
                "id": "22222222-2222-2222-2222-222222222222",
                "sessionId": "33333333-3333-3333-3333-333333333333",
            },
            "model": "gpt-5",
            "modelProvider": "openai",
            "historyLogId": 0,
            "approvalPolicy": "never",
            "approvalsReviewer": "user",
            "sandbox": "read-only",
            "cwd": "C:/Users/27605/codex-python",
            "config": {"instructionSources": [], "startupWarnings": []},
        }

        exchange = sequence.startup_exchange_from_responses(
            bootstrap_response=bootstrap_response,
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )

        self.assertIsInstance(exchange, ExecRuntimeStartupExchange)
        self.assertEqual(exchange.initial_request_plan.request.method, "turn/start")
        self.assertEqual(exchange.initial_request_plan.request.request_id, 2)
        self.assertEqual([action.kind for action in exchange.processor_actions], ["print_config_summary"])
        self.assertEqual(
            exchange.processor_actions[0].to_mapping()["sessionConfigured"]["thread_id"],
            "22222222-2222-2222-2222-222222222222",
        )
        self.assertEqual(exchange.processor_actions[0].to_mapping()["prompt"], "hello")


class ExecRuntimeRequestSequenceLoopExchangeTest(unittest.TestCase):
    def test_runtime_request_sequence_builds_loop_exchange_from_server_event(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventExchange, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        startup_exchange = sequence.startup_exchange_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )
        event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                    },
                },
            },
        }

        exchange = sequence.exec_loop_exchange(startup_exchange.startup_result, event)

        self.assertIsInstance(exchange, ExecRuntimeEventExchange)
        self.assertEqual(exchange.step.state.thread_id, "22222222-2222-2222-2222-222222222222")
        self.assertFalse(exchange.step.should_break)
        self.assertEqual([action.kind for action in exchange.actions], ["process_notification"])
        self.assertEqual(exchange.actions[0].to_mapping()["notification"]["method"], "turn/completed")


class ExecRuntimeRequestSequenceShutdownExchangeTest(unittest.TestCase):
    def test_runtime_request_sequence_shutdown_exchange_unsubscribes_and_breaks(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventExchange, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        startup_exchange = sequence.startup_exchange_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )
        event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                    },
                },
            },
        }

        exchange = sequence.exec_loop_shutdown_exchange(startup_exchange.startup_result, event)

        self.assertIsInstance(exchange, ExecRuntimeEventExchange)
        self.assertTrue(exchange.step.should_break)
        self.assertEqual(exchange.step.shutdown_request.method, "thread/unsubscribe")
        self.assertEqual(exchange.step.shutdown_request.request_id, 3)
        self.assertEqual(
            [action.kind for action in exchange.actions],
            ["process_notification", "send_request", "break"],
        )
        self.assertEqual(exchange.actions[1].client_request.request_id, 3)
        self.assertEqual(exchange.actions[1].client_request.method, "thread/unsubscribe")


class ExecRuntimeActionSummaryTest(unittest.TestCase):
    def test_runtime_action_summary_extracts_runner_work_from_shutdown_exchange(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeActionSummary, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        startup_exchange = sequence.startup_exchange_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )
        event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                    },
                },
            },
        }

        summary = sequence.exec_loop_shutdown_exchange(startup_exchange.startup_result, event).action_summary

        self.assertIsInstance(summary, ExecRuntimeActionSummary)
        self.assertTrue(summary.should_break)
        self.assertEqual(len(summary.notifications), 1)
        self.assertEqual(summary.notifications[0]["method"], "turn/completed")
        self.assertEqual(len(summary.client_requests), 1)
        self.assertEqual(summary.client_requests[0].method, "thread/unsubscribe")
        self.assertEqual(summary.client_requests[0].request_id, 3)
        self.assertEqual(summary.config_summaries, ())
        self.assertEqual(summary.warnings, ())

    def test_startup_exchange_action_summary_preserves_config_action(self) -> None:
        from pycodex.exec import ExecCli, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        startup_exchange = sequence.startup_exchange_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )

        summary = startup_exchange.action_summary

        self.assertFalse(summary.should_break)
        self.assertEqual(summary.client_requests, ())
        self.assertEqual(summary.notifications, ())
        self.assertEqual(len(summary.config_summaries), 1)
        self.assertEqual(summary.config_summaries[0]["prompt"], "hello")
        self.assertEqual(
            summary.config_summaries[0]["sessionConfigured"]["thread_id"],
            "22222222-2222-2222-2222-222222222222",
        )
        self.assertEqual([action.kind for action in summary.actions], ["print_config_summary"])


class ExecRuntimeActionSummaryServerRequestTest(unittest.TestCase):
    def test_runtime_action_summary_extracts_server_requests(self) -> None:
        from pycodex.exec import ExecLoopAction, exec_runtime_action_summary

        server_request = {"method": "tool/call", "params": {"id": "call-1"}}
        summary = exec_runtime_action_summary(
            (
                ExecLoopAction(kind="handle_server_request", server_request=server_request),
            )
        )

        self.assertEqual(summary.server_requests, (server_request,))
        self.assertEqual(summary.client_requests, ())
        self.assertEqual(summary.notifications, ())
        self.assertEqual(summary.config_summaries, ())
        self.assertFalse(summary.should_break)


class ExecRuntimeRunnerTranscriptTest(unittest.TestCase):
    def test_runtime_runner_transcript_aggregates_startup_and_shutdown_work(self) -> None:
        from pycodex.exec import (
            ExecCli,
            ExecRuntimeRunnerTranscript,
            build_exec_runtime_request_sequence,
            exec_runtime_runner_transcript,
        )

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        startup_exchange = sequence.startup_exchange_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )
        shutdown_exchange = sequence.exec_loop_shutdown_exchange(
            startup_exchange.startup_result,
            {
                "type": "server_notification",
                "notification": {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "22222222-2222-2222-2222-222222222222",
                        "turn": {
                            "id": "turn-1",
                            "status": "completed",
                            "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                        },
                    },
                },
            },
        )

        transcript = exec_runtime_runner_transcript(startup_exchange, (shutdown_exchange,))

        self.assertIsInstance(transcript, ExecRuntimeRunnerTranscript)
        self.assertEqual(len(transcript.action_summaries), 2)
        self.assertEqual(len(transcript.config_summaries), 1)
        self.assertEqual(transcript.config_summaries[0]["prompt"], "hello")
        self.assertEqual(len(transcript.notifications), 1)
        self.assertEqual(transcript.notifications[0]["method"], "turn/completed")
        self.assertEqual(len(transcript.client_requests), 1)
        self.assertEqual(transcript.client_requests[0].method, "thread/unsubscribe")
        self.assertEqual(transcript.client_requests[0].request_id, 3)
        self.assertTrue(transcript.should_break)
        self.assertEqual(transcript.server_requests, ())
        self.assertEqual(transcript.warnings, ())


class ExecRuntimeRequestSequenceRunnerTranscriptFromResponsesTest(unittest.TestCase):
    def test_runtime_request_sequence_builds_runner_transcript_from_responses_and_events(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        transcript = sequence.runner_transcript_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        self.assertEqual(transcript.startup_exchange.initial_request_plan.request.request_id, 2)
        self.assertEqual(len(transcript.event_exchanges), 1)
        self.assertEqual(len(transcript.config_summaries), 1)
        self.assertEqual(transcript.config_summaries[0]["prompt"], "hello")
        self.assertEqual(len(transcript.notifications), 1)
        self.assertEqual(transcript.notifications[0]["method"], "turn/completed")
        self.assertEqual(len(transcript.client_requests), 1)
        self.assertEqual(transcript.client_requests[0].method, "thread/unsubscribe")
        self.assertEqual(transcript.client_requests[0].request_id, 3)
        self.assertTrue(transcript.should_break)


class ExecRuntimeRunnerTranscriptAppendEventTest(unittest.TestCase):
    def test_runtime_request_sequence_appends_event_input_to_runner_transcript(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        transcript = sequence.runner_transcript_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )

        updated = sequence.append_event_input_to_runner_transcript(
            transcript,
            ExecRuntimeEventInput(
                event={
                    "type": "server_notification",
                    "notification": {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "22222222-2222-2222-2222-222222222222",
                            "turn": {
                                "id": "turn-1",
                                "status": "completed",
                                "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                            },
                        },
                    },
                },
                processor_status="initiate_shutdown",
            ),
        )

        self.assertEqual(transcript.event_exchanges, ())
        self.assertEqual(len(updated.event_exchanges), 1)
        self.assertEqual(len(updated.config_summaries), 1)
        self.assertEqual(len(updated.notifications), 1)
        self.assertEqual(updated.client_requests[0].method, "thread/unsubscribe")
        self.assertEqual(updated.client_requests[0].request_id, 3)
        self.assertTrue(updated.should_break)


class ExecRuntimeRunnerTranscriptAppendEventsUntilBreakTest(unittest.TestCase):
    def test_runtime_request_sequence_appends_event_inputs_until_break(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        transcript = sequence.runner_transcript_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )
        completed_event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                    },
                },
            },
        }
        late_event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-2",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-2", "text": "late"}],
                    },
                },
            },
        }

        updated = sequence.append_event_inputs_to_runner_transcript(
            transcript,
            (
                ExecRuntimeEventInput(event=completed_event, processor_status="initiate_shutdown"),
                ExecRuntimeEventInput(event=late_event),
            ),
        )

        self.assertEqual(len(updated.event_exchanges), 1)
        self.assertTrue(updated.should_break)
        self.assertEqual(len(updated.notifications), 1)
        self.assertEqual(updated.notifications[0]["params"]["turn"]["id"], "turn-1")
        self.assertEqual(updated.client_requests[0].method, "thread/unsubscribe")
        self.assertEqual(updated.client_requests[0].request_id, 3)


class ExecRuntimeRequestSequenceRunnerTranscriptFromResponsesBreakTest(unittest.TestCase):
    def test_runtime_request_sequence_runner_transcript_from_responses_stops_after_break(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        first_event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                    },
                },
            },
        }
        late_event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-2",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-2", "text": "late"}],
                    },
                },
            },
        }

        transcript = sequence.runner_transcript_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(event=first_event, processor_status="initiate_shutdown"),
                ExecRuntimeEventInput(event=late_event),
            ),
        )

        self.assertEqual(len(transcript.event_exchanges), 1)
        self.assertTrue(transcript.should_break)
        self.assertEqual(len(transcript.notifications), 1)
        self.assertEqual(transcript.notifications[0]["params"]["turn"]["id"], "turn-1")
        self.assertEqual(transcript.client_requests[0].method, "thread/unsubscribe")
        self.assertEqual(transcript.client_requests[0].request_id, 3)


class ExecRuntimeRunnerTranscriptStartupRequestsTest(unittest.TestCase):
    def test_runtime_runner_transcript_exposes_startup_and_all_client_requests(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        transcript = sequence.runner_transcript_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        self.assertEqual(len(transcript.bootstrap_client_requests), 1)
        self.assertEqual(transcript.bootstrap_client_requests[0].method, "thread/start")
        self.assertEqual(transcript.bootstrap_client_requests[0].request_id, 1)
        self.assertEqual(len(transcript.initial_client_requests), 1)
        self.assertEqual(transcript.initial_client_requests[0].method, "turn/start")
        self.assertEqual(transcript.initial_client_requests[0].request_id, 2)
        self.assertEqual(len(transcript.startup_client_requests), 2)
        self.assertEqual(len(transcript.client_requests), 1)
        self.assertEqual(transcript.client_requests[0].method, "thread/unsubscribe")
        self.assertEqual(transcript.client_requests[0].request_id, 3)
        self.assertEqual(
            [request.method for request in transcript.all_client_requests],
            ["thread/start", "turn/start", "thread/unsubscribe"],
        )
        self.assertEqual(
            [request.request_id for request in transcript.all_client_requests],
            [1, 2, 3],
        )


class ExecRuntimeRunnerTranscriptMappingTest(unittest.TestCase):
    def test_runtime_runner_transcript_to_mapping_preserves_request_order_and_break_state(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        transcript = sequence.runner_transcript_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        mapping = transcript.to_mapping()

        self.assertEqual(
            [request["method"] for request in mapping["allClientRequests"]],
            ["thread/start", "turn/start", "thread/unsubscribe"],
        )
        self.assertEqual(
            [request["requestId"] for request in mapping["allClientRequests"]],
            [1, 2, 3],
        )
        self.assertEqual(mapping["eventExchangeCount"], 1)
        self.assertTrue(mapping["shouldBreak"])
        self.assertEqual(mapping["notifications"][0]["method"], "turn/completed")
        self.assertEqual(mapping["configSummaries"][0]["prompt"], "hello")
        self.assertEqual(mapping["actionSummaries"][-1]["shouldBreak"], True)


class ExecRuntimeRunnerTranscriptAgentMessagesTest(unittest.TestCase):
    def test_runtime_runner_transcript_extracts_agent_messages_from_notifications(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        transcript = sequence.runner_transcript_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [
                                        {"type": "reasoning", "id": "r-1", "text": "hidden"},
                                        {"type": "agentMessage", "id": "msg-1", "text": "first"},
                                        {"type": "agentMessage", "id": "msg-2", "text": "final"},
                                    ],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        self.assertEqual(transcript.agent_messages, ("first", "final"))
        self.assertEqual(transcript.final_agent_message, "final")
        mapping = transcript.to_mapping()
        self.assertEqual(mapping["agentMessages"], ["first", "final"])
        self.assertEqual(mapping["finalAgentMessage"], "final")
        self.assertEqual(mapping["actionSummaries"][-1]["agentMessages"], ["first", "final"])


class ExecRuntimeRunnerResultTest(unittest.TestCase):
    def test_runtime_runner_result_from_responses_exposes_final_message_and_trace(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, ExecRuntimeRunnerResult, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        self.assertIsInstance(result, ExecRuntimeRunnerResult)
        self.assertTrue(result.completed)
        self.assertEqual(result.final_message, "final answer")
        self.assertEqual(result.request_count, 3)
        mapping = result.to_mapping()
        self.assertEqual(mapping["finalMessage"], "final answer")
        self.assertEqual(mapping["requestCount"], 3)
        self.assertEqual(
            [request["method"] for request in mapping["transcript"]["allClientRequests"]],
            ["thread/start", "turn/start", "thread/unsubscribe"],
        )


class ExecRuntimeRunnerResultFinalMessageOutputPlanTest(unittest.TestCase):
    def test_runner_result_final_message_output_plan_matches_terminal_rules(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, ExecRuntimeFinalMessageOutputPlan, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        redirected = result.final_message_output_plan(
            stdout_is_terminal=False,
            stderr_is_terminal=True,
            output_last_message=True,
        )
        tty = result.final_message_output_plan(
            stdout_is_terminal=True,
            stderr_is_terminal=True,
            final_message_rendered=False,
        )
        already_rendered = result.final_message_output_plan(
            stdout_is_terminal=True,
            stderr_is_terminal=True,
            final_message_rendered=True,
        )

        self.assertIsInstance(redirected, ExecRuntimeFinalMessageOutputPlan)
        self.assertEqual(redirected.stdout_text, "final answer")
        self.assertIsNone(redirected.tty_text)
        self.assertEqual(redirected.last_message_contents, "final answer")
        self.assertIsNone(redirected.last_message_path)
        self.assertFalse(redirected.should_write_last_message)
        self.assertIsNone(tty.stdout_text)
        self.assertEqual(tty.tty_text, "final answer")
        self.assertIsNone(already_rendered.stdout_text)
        self.assertIsNone(already_rendered.tty_text)
        self.assertEqual(redirected.to_mapping()["finalMessage"], "final answer")


class ExecRuntimeRunnerResultFinalMessageOutputPlanFromCliTest(unittest.TestCase):
    def test_runner_result_final_message_output_plan_from_cli_uses_last_message_file(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello", last_message_file="C:/tmp/last-message.txt"),
            current_dir="C:/Users/27605/codex-python",
        )
        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        plan = result.final_message_output_plan_from_cli(
            ExecCli(prompt="hello", last_message_file="C:/tmp/last-message.txt"),
            stdout_is_terminal=True,
            stderr_is_terminal=True,
            final_message_rendered=True,
        )

        self.assertIsNone(plan.stdout_text)
        self.assertIsNone(plan.tty_text)
        self.assertEqual(plan.last_message_path, "C:/tmp/last-message.txt")
        self.assertEqual(plan.last_message_contents, "final answer")
        self.assertTrue(plan.should_write_last_message)
        self.assertTrue(plan.to_mapping()["shouldWriteLastMessage"])


class ExecRuntimeFinalMessageOutputPlanApplyTest(unittest.TestCase):
    def test_apply_final_message_output_plan_writes_stdout_stderr_and_last_message(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from pycodex.exec import (
            ExecRuntimeFinalMessageOutputPlan,
            apply_exec_runtime_final_message_output_plan,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            last_message_path = Path(tmpdir) / "last-message.txt"
            stdout = io.StringIO()
            stderr = io.StringIO()
            plan = ExecRuntimeFinalMessageOutputPlan(
                final_message="final answer",
                stdout_text="stdout answer",
                tty_text="tty answer",
                last_message_contents="file answer",
                last_message_path=str(last_message_path),
            )

            apply_exec_runtime_final_message_output_plan(plan, stdout=stdout, stderr=stderr)

            self.assertEqual(stdout.getvalue(), "stdout answer\n")
            self.assertEqual(stderr.getvalue(), "tty answer\n")
            self.assertEqual(last_message_path.read_text(encoding="utf-8"), "file answer")


class ExecRuntimeRunnerResultApplyFinalMessageFromCliTest(unittest.TestCase):
    def test_runner_result_apply_final_message_output_from_cli_writes_outputs(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        with tempfile.TemporaryDirectory() as tmpdir:
            last_message_path = Path(tmpdir) / "last-message.txt"
            cli = ExecCli(prompt="hello", last_message_file=str(last_message_path))
            sequence = build_exec_runtime_request_sequence(
                cli,
                current_dir="C:/Users/27605/codex-python",
            )
            result = sequence.runner_result_from_responses(
                bootstrap_response={
                    "thread": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "sessionId": "33333333-3333-3333-3333-333333333333",
                    },
                    "model": "gpt-5",
                    "modelProvider": "openai",
                    "historyLogId": 0,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": "read-only",
                    "cwd": "C:/Users/27605/codex-python",
                    "config": {"instructionSources": [], "startupWarnings": []},
                },
                initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
                event_inputs=(
                    ExecRuntimeEventInput(
                        event={
                            "type": "server_notification",
                            "notification": {
                                "method": "turn/completed",
                                "params": {
                                    "threadId": "22222222-2222-2222-2222-222222222222",
                                    "turn": {
                                        "id": "turn-1",
                                        "status": "completed",
                                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                    },
                                },
                            },
                        },
                        processor_status="initiate_shutdown",
                    ),
                ),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            plan = result.apply_final_message_output_from_cli(
                cli,
                stdout_is_terminal=False,
                stderr_is_terminal=True,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(stdout.getvalue(), "final answer\n")
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(last_message_path.read_text(encoding="utf-8"), "final answer")
            self.assertEqual(plan.last_message_path, str(last_message_path))
            self.assertTrue(plan.should_write_last_message)


class ExecRuntimeRunnerTranscriptFinalMessageFallbackTest(unittest.TestCase):
    def test_runtime_runner_result_final_message_falls_back_to_plan_text(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "plan", "id": "plan-1", "text": "ship it"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        self.assertEqual(result.transcript.agent_messages, ())
        self.assertIsNone(result.transcript.final_agent_message)
        self.assertEqual(result.transcript.final_messages, ("ship it",))
        self.assertEqual(result.transcript.final_message, "ship it")
        self.assertEqual(result.final_message, "ship it")
        mapping = result.to_mapping()
        self.assertEqual(mapping["finalMessage"], "ship it")
        self.assertEqual(mapping["transcript"]["finalMessages"], ["ship it"])


class ExecRuntimeRunnerTranscriptFailedTurnClearsFinalMessageTest(unittest.TestCase):
    def test_runtime_runner_result_failed_turn_clears_stale_final_message(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        completed_event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "stale answer"}],
                    },
                },
            },
        }
        failed_event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/failed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "failed",
                        "items": [],
                    },
                },
            },
        }

        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(event=completed_event),
                ExecRuntimeEventInput(event=failed_event, processor_status="initiate_shutdown"),
            ),
        )

        self.assertEqual(result.transcript.agent_messages, ("stale answer",))
        self.assertEqual(result.transcript.final_messages, ())
        self.assertIsNone(result.transcript.final_message)
        self.assertIsNone(result.final_message)
        mapping = result.to_mapping()
        self.assertEqual(mapping["transcript"]["agentMessages"], ["stale answer"])
        self.assertEqual(mapping["transcript"]["finalMessages"], [])
        self.assertIsNone(mapping["finalMessage"])


class ExecRuntimeRunnerResultFailedFinalMessageOutputPlanTest(unittest.TestCase):
    def test_failed_runner_result_does_not_overwrite_last_message_file(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        with tempfile.TemporaryDirectory() as tmpdir:
            last_message_path = Path(tmpdir) / "last-message.txt"
            last_message_path.write_text("previous answer", encoding="utf-8")
            cli = ExecCli(prompt="hello", last_message_file=str(last_message_path))
            sequence = build_exec_runtime_request_sequence(
                cli,
                current_dir="C:/Users/27605/codex-python",
            )
            result = sequence.runner_result_from_responses(
                bootstrap_response={
                    "thread": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "sessionId": "33333333-3333-3333-3333-333333333333",
                    },
                    "model": "gpt-5",
                    "modelProvider": "openai",
                    "historyLogId": 0,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": "read-only",
                    "cwd": "C:/Users/27605/codex-python",
                    "config": {"instructionSources": [], "startupWarnings": []},
                },
                initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
                event_inputs=(
                    ExecRuntimeEventInput(
                        event={
                            "type": "server_notification",
                            "notification": {
                                "method": "turn/failed",
                                "params": {
                                    "threadId": "22222222-2222-2222-2222-222222222222",
                                    "turn": {"id": "turn-1", "status": "failed", "items": []},
                                },
                            },
                        },
                        processor_status="initiate_shutdown",
                    ),
                ),
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            plan = result.apply_final_message_output_from_cli(
                cli,
                stdout_is_terminal=False,
                stderr_is_terminal=True,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertIsNone(result.final_message)
            self.assertIsNone(plan.last_message_contents)
            self.assertFalse(plan.should_write_last_message)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(last_message_path.read_text(encoding="utf-8"), "previous answer")


class ExecRuntimeRunnerResultTurnStatusTest(unittest.TestCase):
    def test_runner_result_reports_completed_turn_status_as_success(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "done"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        self.assertEqual(result.transcript.turn_statuses, ("completed",))
        self.assertEqual(result.terminal_turn_status, "completed")
        self.assertTrue(result.succeeded)
        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.to_mapping()["terminalTurnStatus"], "completed")
        self.assertTrue(result.to_mapping()["succeeded"])
        self.assertEqual(result.to_mapping()["outcome"], "success")
        self.assertEqual(result.to_mapping()["exitCode"], 0)

    def test_runner_result_reports_failed_turn_status_as_not_success(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/failed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {"id": "turn-1", "status": "failed", "items": []},
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
        )

        self.assertEqual(result.transcript.turn_statuses, ("failed",))
        self.assertEqual(result.terminal_turn_status, "failed")
        self.assertFalse(result.succeeded)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.to_mapping()["transcript"]["turnStatuses"], ["failed"])
        self.assertEqual(result.to_mapping()["terminalTurnStatus"], "failed")
        self.assertFalse(result.to_mapping()["succeeded"])
        self.assertEqual(result.to_mapping()["outcome"], "failed")
        self.assertEqual(result.to_mapping()["exitCode"], 1)


class ExecRuntimeRunnerResultInterruptedTurnStatusTest(unittest.TestCase):
    def test_runner_result_reports_interrupted_turn_status_as_not_success_and_clears_final_message(self) -> None:
        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        completed_event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/completed",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "stale answer"}],
                    },
                },
            },
        }
        interrupted_event = {
            "type": "server_notification",
            "notification": {
                "method": "turn/interrupted",
                "params": {
                    "threadId": "22222222-2222-2222-2222-222222222222",
                    "turn": {"id": "turn-1", "status": "interrupted", "items": []},
                },
            },
        }

        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(event=completed_event),
                ExecRuntimeEventInput(event=interrupted_event, processor_status="initiate_shutdown"),
            ),
        )

        self.assertEqual(result.transcript.turn_statuses, ("completed", "interrupted"))
        self.assertEqual(result.terminal_turn_status, "interrupted")
        self.assertFalse(result.succeeded)
        self.assertEqual(result.outcome, "interrupted")
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.transcript.agent_messages, ("stale answer",))
        self.assertEqual(result.transcript.final_messages, ())
        self.assertIsNone(result.final_message)
        mapping = result.to_mapping()
        self.assertEqual(mapping["transcript"]["turnStatuses"], ["completed", "interrupted"])
        self.assertEqual(mapping["terminalTurnStatus"], "interrupted")
        self.assertFalse(mapping["succeeded"])
        self.assertEqual(mapping["outcome"], "interrupted")
        self.assertEqual(mapping["exitCode"], 1)
        self.assertIsNone(mapping["finalMessage"])


class ExecRuntimeRunnerResultOutcomeTest(unittest.TestCase):
    def test_runner_result_without_terminal_turn_status_is_incomplete(self) -> None:
        from pycodex.exec import ExecCli, build_exec_runtime_request_sequence

        sequence = build_exec_runtime_request_sequence(
            ExecCli(prompt="hello"),
            current_dir="C:/Users/27605/codex-python",
        )
        result = sequence.runner_result_from_responses(
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
        )

        self.assertIsNone(result.terminal_turn_status)
        self.assertFalse(result.succeeded)
        self.assertEqual(result.outcome, "incomplete")
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.to_mapping()["outcome"], "incomplete")


class ExecRuntimeCliCompletionTest(unittest.TestCase):
    def test_runner_result_apply_cli_completion_returns_exit_code_and_output_plan(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from pycodex.exec import ExecCli, ExecRuntimeCliCompletion, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        with tempfile.TemporaryDirectory() as tmpdir:
            last_message_path = Path(tmpdir) / "last-message.txt"
            cli = ExecCli(prompt="hello", last_message_file=str(last_message_path))
            sequence = build_exec_runtime_request_sequence(
                cli,
                current_dir="C:/Users/27605/codex-python",
            )
            result = sequence.runner_result_from_responses(
                bootstrap_response={
                    "thread": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "sessionId": "33333333-3333-3333-3333-333333333333",
                    },
                    "model": "gpt-5",
                    "modelProvider": "openai",
                    "historyLogId": 0,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": "read-only",
                    "cwd": "C:/Users/27605/codex-python",
                    "config": {"instructionSources": [], "startupWarnings": []},
                },
                initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
                event_inputs=(
                    ExecRuntimeEventInput(
                        event={
                            "type": "server_notification",
                            "notification": {
                                "method": "turn/completed",
                                "params": {
                                    "threadId": "22222222-2222-2222-2222-222222222222",
                                    "turn": {
                                        "id": "turn-1",
                                        "status": "completed",
                                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                    },
                                },
                            },
                        },
                        processor_status="initiate_shutdown",
                    ),
                ),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            completion = result.apply_cli_completion(
                cli,
                stdout_is_terminal=False,
                stderr_is_terminal=True,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertIsInstance(completion, ExecRuntimeCliCompletion)
            self.assertTrue(completion.completed)
            self.assertTrue(completion.ready_to_exit)
            self.assertTrue(completion.succeeded)
            self.assertEqual(completion.final_message, "final answer")
            self.assertEqual(completion.terminal_turn_status, "completed")
            self.assertEqual(completion.exit_code, 0)
            self.assertEqual(completion.outcome, "success")
            self.assertEqual(stdout.getvalue(), "final answer\n")
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(last_message_path.read_text(encoding="utf-8"), "final answer")
            mapping = completion.to_mapping()
            self.assertTrue(mapping["completed"])
            self.assertTrue(mapping["readyToExit"])
            self.assertTrue(mapping["succeeded"])
            self.assertEqual(mapping["finalMessage"], "final answer")
            self.assertEqual(mapping["terminalTurnStatus"], "completed")
            self.assertEqual(mapping["exitCode"], 0)
            self.assertEqual(mapping["outcome"], "success")
            self.assertEqual(mapping["outputPlan"]["lastMessagePath"], str(last_message_path))
            self.assertEqual(mapping["result"]["finalMessage"], "final answer")
            self.assertEqual(mapping["jsonPayload"]["outcome"], "success")
            self.assertEqual(mapping["jsonPayload"]["exitCode"], 0)
            self.assertEqual(mapping["jsonPayload"]["finalMessage"], "final answer")
            self.assertTrue(mapping["jsonPayload"]["succeeded"])
            self.assertTrue(mapping["jsonPayload"]["readyToExit"])


class ExecRuntimeRequestSequenceCliCompletionFromResponsesTest(unittest.TestCase):
    def test_sequence_cli_completion_from_responses_applies_output_and_returns_exit_code(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from pycodex.exec import ExecCli, ExecRuntimeCliCompletion, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        with tempfile.TemporaryDirectory() as tmpdir:
            last_message_path = Path(tmpdir) / "last-message.txt"
            cli = ExecCli(prompt="hello", last_message_file=str(last_message_path))
            sequence = build_exec_runtime_request_sequence(
                cli,
                current_dir="C:/Users/27605/codex-python",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            completion = sequence.cli_completion_from_responses(
                cli,
                bootstrap_response={
                    "thread": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "sessionId": "33333333-3333-3333-3333-333333333333",
                    },
                    "model": "gpt-5",
                    "modelProvider": "openai",
                    "historyLogId": 0,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": "read-only",
                    "cwd": "C:/Users/27605/codex-python",
                    "config": {"instructionSources": [], "startupWarnings": []},
                },
                initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
                event_inputs=(
                    ExecRuntimeEventInput(
                        event={
                            "type": "server_notification",
                            "notification": {
                                "method": "turn/completed",
                                "params": {
                                    "threadId": "22222222-2222-2222-2222-222222222222",
                                    "turn": {
                                        "id": "turn-1",
                                        "status": "completed",
                                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                    },
                                },
                            },
                        },
                        processor_status="initiate_shutdown",
                    ),
                ),
                stdout_is_terminal=False,
                stderr_is_terminal=True,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertIsInstance(completion, ExecRuntimeCliCompletion)
            self.assertEqual(completion.exit_code, 0)
            self.assertEqual(completion.outcome, "success")
            self.assertEqual(stdout.getvalue(), "final answer\n")
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(last_message_path.read_text(encoding="utf-8"), "final answer")
            self.assertEqual(completion.result.final_message, "final answer")
            self.assertEqual(completion.output_plan.last_message_path, str(last_message_path))


class ExecRuntimeCliCompletionFailurePropertiesTest(unittest.TestCase):
    def test_sequence_cli_completion_from_failed_response_exposes_failure_properties(self) -> None:
        import io
        import tempfile
        from pathlib import Path

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        with tempfile.TemporaryDirectory() as tmpdir:
            last_message_path = Path(tmpdir) / "last-message.txt"
            last_message_path.write_text("previous answer", encoding="utf-8")
            cli = ExecCli(prompt="hello", last_message_file=str(last_message_path))
            sequence = build_exec_runtime_request_sequence(
                cli,
                current_dir="C:/Users/27605/codex-python",
            )
            completion = sequence.cli_completion_from_responses(
                cli,
                bootstrap_response={
                    "thread": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "sessionId": "33333333-3333-3333-3333-333333333333",
                    },
                    "model": "gpt-5",
                    "modelProvider": "openai",
                    "historyLogId": 0,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": "read-only",
                    "cwd": "C:/Users/27605/codex-python",
                    "config": {"instructionSources": [], "startupWarnings": []},
                },
                initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
                event_inputs=(
                    ExecRuntimeEventInput(
                        event={
                            "type": "server_notification",
                            "notification": {
                                "method": "turn/failed",
                                "params": {
                                    "threadId": "22222222-2222-2222-2222-222222222222",
                                    "turn": {"id": "turn-1", "status": "failed", "items": []},
                                },
                            },
                        },
                        processor_status="initiate_shutdown",
                    ),
                ),
                stdout_is_terminal=False,
                stderr_is_terminal=True,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

            self.assertFalse(completion.succeeded)
            self.assertIsNone(completion.final_message)
            self.assertEqual(completion.terminal_turn_status, "failed")
            self.assertEqual(completion.outcome, "failed")
            self.assertEqual(completion.exit_code, 1)
            self.assertFalse(completion.output_plan.should_write_last_message)
            self.assertEqual(last_message_path.read_text(encoding="utf-8"), "previous answer")
            mapping = completion.to_mapping()
            self.assertFalse(mapping["succeeded"])
            self.assertIsNone(mapping["finalMessage"])
            self.assertEqual(mapping["terminalTurnStatus"], "failed")
            self.assertEqual(mapping["outcome"], "failed")
            self.assertEqual(mapping["exitCode"], 1)
            self.assertEqual(mapping["jsonPayload"]["outcome"], "failed")
            self.assertEqual(mapping["jsonPayload"]["exitCode"], 1)
            self.assertIsNone(mapping["jsonPayload"]["finalMessage"])
            self.assertFalse(mapping["jsonPayload"]["succeeded"])
            self.assertTrue(mapping["jsonPayload"]["readyToExit"])


class ExecRuntimeCliCompletionJsonPayloadTextTest(unittest.TestCase):
    def test_cli_completion_json_payload_text_is_compact_json(self) -> None:
        import json

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        cli = ExecCli(prompt="hello")
        sequence = build_exec_runtime_request_sequence(
            cli,
            current_dir="C:/Users/27605/codex-python",
        )
        completion = sequence.cli_completion_from_responses(
            cli,
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
            stdout_is_terminal=True,
            stderr_is_terminal=True,
            final_message_rendered=True,
        )

        payload_text = completion.json_payload_text()
        payload = json.loads(payload_text)

        self.assertNotIn("\n", payload_text)
        self.assertEqual(payload["outcome"], "success")
        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(payload["finalMessage"], "final answer")
        self.assertTrue(payload["succeeded"])
        self.assertTrue(payload["readyToExit"])
        self.assertEqual(payload["outputPlan"]["finalMessage"], "final answer")


class ExecRuntimeCliCompletionJsonPayloadApplyTest(unittest.TestCase):
    def test_cli_completion_apply_json_payload_output_writes_one_line_to_stdout(self) -> None:
        import io
        import json

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        cli = ExecCli(prompt="hello")
        sequence = build_exec_runtime_request_sequence(
            cli,
            current_dir="C:/Users/27605/codex-python",
        )
        completion = sequence.cli_completion_from_responses(
            cli,
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
            stdout_is_terminal=True,
            stderr_is_terminal=True,
            final_message_rendered=True,
        )
        stdout = io.StringIO()

        written = completion.apply_json_payload_output(stdout=stdout)

        self.assertEqual(stdout.getvalue(), written + "\n")
        payload = json.loads(written)
        self.assertEqual(payload["outcome"], "success")
        self.assertEqual(payload["finalMessage"], "final answer")
        self.assertEqual(payload["exitCode"], 0)


class ExecRuntimeRequestSequenceJsonCliCompletionFromResponsesTest(unittest.TestCase):
    def test_sequence_json_cli_completion_outputs_only_json_stdout_and_writes_last_message(self) -> None:
        import io
        import json
        import tempfile
        from pathlib import Path

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        with tempfile.TemporaryDirectory() as tmpdir:
            last_message_path = Path(tmpdir) / "last-message.txt"
            cli = ExecCli(prompt="hello", json=True, last_message_file=str(last_message_path))
            sequence = build_exec_runtime_request_sequence(
                cli,
                current_dir="C:/Users/27605/codex-python",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            completion = sequence.cli_json_completion_from_responses(
                cli,
                bootstrap_response={
                    "thread": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "sessionId": "33333333-3333-3333-3333-333333333333",
                    },
                    "model": "gpt-5",
                    "modelProvider": "openai",
                    "historyLogId": 0,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": "read-only",
                    "cwd": "C:/Users/27605/codex-python",
                    "config": {"instructionSources": [], "startupWarnings": []},
                },
                initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
                event_inputs=(
                    ExecRuntimeEventInput(
                        event={
                            "type": "server_notification",
                            "notification": {
                                "method": "turn/completed",
                                "params": {
                                    "threadId": "22222222-2222-2222-2222-222222222222",
                                    "turn": {
                                        "id": "turn-1",
                                        "status": "completed",
                                        "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                    },
                                },
                            },
                        },
                        processor_status="initiate_shutdown",
                    ),
                ),
                stdout=stdout,
                stderr=stderr,
            )

            stdout_lines = stdout.getvalue().splitlines()
            self.assertEqual(len(stdout_lines), 1)
            payload = json.loads(stdout_lines[0])
            self.assertEqual(payload["outcome"], "success")
            self.assertEqual(payload["finalMessage"], "final answer")
            self.assertEqual(payload["exitCode"], 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(last_message_path.read_text(encoding="utf-8"), "final answer")
            self.assertEqual(completion.final_message, "final answer")
            self.assertEqual(completion.output_plan.stdout_text, None)
            self.assertEqual(completion.output_plan.tty_text, None)
            self.assertTrue(completion.output_plan.should_write_last_message)


class ExecRuntimeRequestSequenceCompletionDispatchTest(unittest.TestCase):
    def test_sequence_completion_from_responses_uses_normal_output_when_json_false(self) -> None:
        import io

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        cli = ExecCli(prompt="hello", json=False)
        sequence = build_exec_runtime_request_sequence(
            cli,
            current_dir="C:/Users/27605/codex-python",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        completion = sequence.completion_from_responses(
            cli,
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
            stdout_is_terminal=False,
            stderr_is_terminal=True,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(completion.outcome, "success")
        self.assertEqual(stdout.getvalue(), "final answer\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_sequence_completion_from_responses_uses_json_output_when_json_true(self) -> None:
        import io
        import json

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        cli = ExecCli(prompt="hello", json=True)
        sequence = build_exec_runtime_request_sequence(
            cli,
            current_dir="C:/Users/27605/codex-python",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        completion = sequence.completion_from_responses(
            cli,
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            event_inputs=(
                ExecRuntimeEventInput(
                    event={
                        "type": "server_notification",
                        "notification": {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "22222222-2222-2222-2222-222222222222",
                                "turn": {
                                    "id": "turn-1",
                                    "status": "completed",
                                    "items": [{"type": "agentMessage", "id": "msg-1", "text": "final answer"}],
                                },
                            },
                        },
                    },
                    processor_status="initiate_shutdown",
                ),
            ),
            stdout_is_terminal=False,
            stderr_is_terminal=True,
            stdout=stdout,
            stderr=stderr,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(completion.outcome, "success")
        self.assertEqual(payload["finalMessage"], "final answer")
        self.assertEqual(stderr.getvalue(), "")


class ExecRuntimeRequestSequenceJsonCliCompletionFailedTest(unittest.TestCase):
    def test_sequence_json_completion_failed_turn_outputs_json_and_preserves_last_message_file(self) -> None:
        import io
        import json
        import tempfile
        from pathlib import Path

        from pycodex.exec import ExecCli, ExecRuntimeEventInput, build_exec_runtime_request_sequence

        with tempfile.TemporaryDirectory() as tmpdir:
            last_message_path = Path(tmpdir) / "last-message.txt"
            last_message_path.write_text("previous answer", encoding="utf-8")
            cli = ExecCli(prompt="hello", json=True, last_message_file=str(last_message_path))
            sequence = build_exec_runtime_request_sequence(
                cli,
                current_dir="C:/Users/27605/codex-python",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            completion = sequence.completion_from_responses(
                cli,
                bootstrap_response={
                    "thread": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "sessionId": "33333333-3333-3333-3333-333333333333",
                    },
                    "model": "gpt-5",
                    "modelProvider": "openai",
                    "historyLogId": 0,
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": "read-only",
                    "cwd": "C:/Users/27605/codex-python",
                    "config": {"instructionSources": [], "startupWarnings": []},
                },
                initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
                event_inputs=(
                    ExecRuntimeEventInput(
                        event={
                            "type": "server_notification",
                            "notification": {
                                "method": "turn/failed",
                                "params": {
                                    "threadId": "22222222-2222-2222-2222-222222222222",
                                    "turn": {"id": "turn-1", "status": "failed", "items": []},
                                },
                            },
                        },
                        processor_status="initiate_shutdown",
                    ),
                ),
                stdout_is_terminal=False,
                stderr_is_terminal=True,
                stdout=stdout,
                stderr=stderr,
            )

            stdout_lines = stdout.getvalue().splitlines()
            self.assertEqual(len(stdout_lines), 1)
            payload = json.loads(stdout_lines[0])
            self.assertEqual(payload["outcome"], "failed")
            self.assertEqual(payload["exitCode"], 1)
            self.assertIsNone(payload["finalMessage"])
            self.assertFalse(payload["succeeded"])
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(last_message_path.read_text(encoding="utf-8"), "previous answer")
            self.assertEqual(completion.exit_code, 1)
            self.assertEqual(completion.outcome, "failed")
            self.assertFalse(completion.output_plan.should_write_last_message)


class ExecRuntimeCliCompletionReadyToExitTest(unittest.TestCase):
    def test_cli_completion_without_break_is_not_ready_to_exit(self) -> None:
        import io

        from pycodex.exec import ExecCli, build_exec_runtime_request_sequence

        cli = ExecCli(prompt="hello")
        sequence = build_exec_runtime_request_sequence(
            cli,
            current_dir="C:/Users/27605/codex-python",
        )
        completion = sequence.completion_from_responses(
            cli,
            bootstrap_response={
                "thread": {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "sessionId": "33333333-3333-3333-3333-333333333333",
                },
                "model": "gpt-5",
                "modelProvider": "openai",
                "historyLogId": 0,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "cwd": "C:/Users/27605/codex-python",
                "config": {"instructionSources": [], "startupWarnings": []},
            },
            initial_operation_response={"turn": {"id": "turn-1", "status": "running"}},
            stdout_is_terminal=False,
            stderr_is_terminal=True,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        self.assertFalse(completion.completed)
        self.assertFalse(completion.ready_to_exit)
        self.assertFalse(completion.succeeded)
        self.assertEqual(completion.outcome, "incomplete")
        self.assertEqual(completion.exit_code, 1)
        mapping = completion.to_mapping()
        self.assertFalse(mapping["completed"])
        self.assertFalse(mapping["readyToExit"])
        self.assertEqual(mapping["outcome"], "incomplete")
