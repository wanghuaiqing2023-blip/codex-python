import unittest

from pathlib import Path
from tempfile import TemporaryDirectory

from pycodex.cli import (
    DebugSandboxConfigBuilderResult,
    DebugSandboxPidTracker,
    ManagedRequirementsMode,
    WINDOWS_STDIN_FORWARD_CHUNK_SIZE,
    build_debug_sandbox_config_load_plan,
    build_debug_sandbox_backend_args_plan,
    build_debug_sandbox_backend_args_from_plan,
    build_debug_sandbox_landlock_backend_args_from_plan,
    build_debug_sandbox_seatbelt_backend_args_from_plan,
    build_debug_sandbox_child_spawn_plan,
    build_debug_sandbox_default_run_flow_handlers,
    build_debug_sandbox_config_with_loader_overrides_from_plan,
    build_debug_sandbox_deferred_native_boundaries,
    load_debug_sandbox_config_with_default_builder,
    build_debug_sandbox_platform_implementation_decisions,
    build_debug_sandbox_entrypoint_plan,
    build_debug_sandbox_denial_logger_plan,
    build_debug_sandbox_execution_plan,
    build_debug_sandbox_exit_status_plan,
    build_debug_sandbox_network_plan,
    build_debug_sandbox_network_env_application_plan,
    build_debug_sandbox_run_flow_plan,
    build_debug_sandbox_run_flow_handler_wiring,
    build_debug_sandbox_windows_session_plan,
    build_debug_sandbox_windows_session_plan_from_config,
    cli_overrides_use_legacy_sandbox_mode,
    collect_debug_sandbox_descendant_pids,
    collect_debug_sandbox_seatbelt_denials,
    config_uses_permission_profiles,
    debug_sandbox_child_arg0,
    debug_sandbox_child_env,
    debug_sandbox_child_spawn_plan_from_execution_plan,
    debug_sandbox_list_child_pids,
    debug_sandbox_pid_is_alive,
    debug_sandbox_seatbelt_env,
    debug_sandbox_subprocess_argv,
    execute_debug_sandbox_run_flow_plan,
    finish_debug_sandbox_denial_logger_plan,
    format_debug_sandbox_denial_summary,
    format_debug_sandbox_network_proxy_error,
    loader_overrides_with_managed_requirements_mode,
    parse_debug_sandbox_seatbelt_denial_message,
    raise_debug_sandbox_child_run_exit_status,
    raise_debug_sandbox_exit_status,
    run_debug_sandbox_backend_args_plan_with_exit_status,
    run_debug_sandbox_config_load_plan,
    run_debug_sandbox_child_spawn_plan,
    run_debug_sandbox_child_spawn_plan_with_exit_status,
    run_debug_sandbox_execution_plan_with_denial_logging,
    run_debug_sandbox_execution_plan_with_exit_status,
    run_debug_sandbox_entrypoint_plan_with_exit_status,
    run_debug_sandbox_windows_session_plan,
    run_debug_sandbox_windows_session_control_flow,
    run_debug_sandbox_windows_session_io_bridge,
    run_debug_sandbox_windows_session_with_stdio_bridge,
    sandbox_unavailable_error,
    should_default_legacy_config_to_read_only,
    start_debug_sandbox_network_proxy_plan,
    with_permissions_profile_override,
    windows_output_forward_bytes,
    windows_stdin_forward_chunks,
)
from pycodex.core.spawn import CODEX_SANDBOX_ENV_VAR, CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR


class CliDebugSandboxTests(unittest.TestCase):
    class LayerStack:
        def __init__(self, values: dict[str, object]) -> None:
            self._values = values

        def effective_config(self) -> dict[str, object]:
            return self._values

    class Config:
        def __init__(self, values: dict[str, object]) -> None:
            self.config_layer_stack = CliDebugSandboxTests.LayerStack(values)

    def test_managed_requirements_mode_matches_rust_profile_invocation(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs ManagedRequirementsMode::for_profile_invocation.
        self.assertIs(
            ManagedRequirementsMode.for_profile_invocation(
                permissions_profile=":workspace",
                include_managed_config=False,
            ),
            ManagedRequirementsMode.IGNORE,
        )
        self.assertIs(
            ManagedRequirementsMode.for_profile_invocation(
                permissions_profile=":workspace",
                include_managed_config=True,
            ),
            ManagedRequirementsMode.INCLUDE,
        )

    def test_pid_tracker_new_rejects_non_positive_root_like_rust(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox/pid_tracker.rs PidTracker::new.
        self.assertIsNone(DebugSandboxPidTracker.new(0))
        self.assertIsNone(DebugSandboxPidTracker.new(-1))
        self.assertIsNotNone(DebugSandboxPidTracker.new(123))

    def test_pid_tracker_collects_recursive_descendants_like_rust(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox/pid_tracker.rs track_descendants/add_pid_watch.
        children = {
            10: [11, 12],
            11: [13],
            12: [13, -1],
            13: [],
        }

        self.assertEqual(
            collect_debug_sandbox_descendant_pids(
                10,
                list_children=lambda pid: children.get(pid, []),
                is_alive=lambda pid: pid != 12,
            ),
            {10, 11, 12, 13},
        )
        self.assertEqual(
            collect_debug_sandbox_descendant_pids(0, list_children=lambda pid: [1]),
            set(),
        )

    def test_pid_tracker_child_listing_boundary_is_platform_guarded(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox/pid_tracker.rs list_child_pids is macOS native.
        self.assertFalse(debug_sandbox_pid_is_alive(0))
        self.assertEqual(debug_sandbox_list_child_pids(10, platform="win32"), [])

        class Result:
            returncode = 0
            stdout = "11\nnot-a-pid\n12\n"

        self.assertEqual(
            debug_sandbox_list_child_pids(
                10,
                platform="darwin",
                runner=lambda *args, **kwargs: Result(),
            ),
            [11, 12],
        )

    def test_cli_overrides_use_legacy_sandbox_mode_matches_rust_key_scan(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs cli_overrides_use_legacy_sandbox_mode.
        self.assertTrue(
            cli_overrides_use_legacy_sandbox_mode(
                [
                    ("model", "gpt-5"),
                    ("sandbox_mode", "workspace-write"),
                ]
            )
        )

    def test_permissions_profile_override_matches_rust_default_permissions_append(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs load_debug_sandbox_config_with_codex_home.
        base = [("model", "gpt-5")]

        self.assertEqual(
            with_permissions_profile_override(base, "limited-read-test"),
            [("model", "gpt-5"), ("default_permissions", "limited-read-test")],
        )
        self.assertEqual(with_permissions_profile_override(base, None), base)
        self.assertEqual(base, [("model", "gpt-5")])

    def test_config_uses_permission_profiles_matches_rust_effective_config_probe(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs config_uses_permission_profiles.
        self.assertTrue(
            config_uses_permission_profiles(self.Config({"default_permissions": ":workspace"}))
        )
        self.assertFalse(config_uses_permission_profiles(self.Config({"sandbox_mode": "read-only"})))

    def test_legacy_config_read_only_default_decision_matches_rust_branch(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs load_debug_sandbox_config_with_codex_home.
        self.assertTrue(should_default_legacy_config_to_read_only(self.Config({}), []))
        self.assertFalse(
            should_default_legacy_config_to_read_only(
                self.Config({"default_permissions": ":workspace"}),
                [],
            )
        )
        self.assertFalse(
            should_default_legacy_config_to_read_only(
                self.Config({}),
                [("sandbox_mode", "workspace-write")],
            )
        )

    def test_loader_overrides_managed_requirements_mode_matches_rust_builder(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs build_debug_sandbox_config_with_loader_overrides.
        base = {"user_config_profile": "work"}

        self.assertEqual(
            loader_overrides_with_managed_requirements_mode(
                base,
                ManagedRequirementsMode.IGNORE,
            ),
            {
                "user_config_profile": "work",
                "ignore_managed_requirements": True,
            },
        )
        self.assertEqual(
            loader_overrides_with_managed_requirements_mode(
                base,
                ManagedRequirementsMode.INCLUDE,
            ),
            {"user_config_profile": "work"},
        )
        self.assertEqual(base, {"user_config_profile": "work"})

    def test_sandbox_unavailable_errors_match_rust_platform_guards(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_* sandbox guards.
        self.assertEqual(
            sandbox_unavailable_error("seatbelt", platform="linux"),
            "Seatbelt sandbox is only available on macOS",
        )
        self.assertEqual(
            sandbox_unavailable_error("windows", platform="linux"),
            "Windows sandbox is only available on Windows",
        )
        self.assertIsNone(sandbox_unavailable_error("seatbelt", platform="darwin"))
        self.assertIsNone(sandbox_unavailable_error("windows", platform="win32"))
        self.assertIsNone(sandbox_unavailable_error("landlock", platform="linux"))

    def test_child_env_marks_disabled_network_like_rust_spawn_helper(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs spawn_debug_sandbox_child.
        base = {"PATH": "/bin", CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR: "proxy"}

        self.assertEqual(
            debug_sandbox_child_env({"PATH": "/bin"}, network_sandbox_enabled=False),
            {"PATH": "/bin", CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR: "1"},
        )
        self.assertEqual(
            debug_sandbox_child_env(base, network_sandbox_enabled=True),
            base,
        )
        self.assertEqual(base[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "proxy")

    def test_seatbelt_child_env_marks_sandbox_like_rust_spawn_helper(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs Seatbelt spawn apply_env.
        base = {"PATH": "/bin", CODEX_SANDBOX_ENV_VAR: "landlock"}

        self.assertEqual(
            debug_sandbox_seatbelt_env({"PATH": "/bin"}),
            {"PATH": "/bin", CODEX_SANDBOX_ENV_VAR: "seatbelt"},
        )
        self.assertEqual(
            debug_sandbox_seatbelt_env(base),
            {"PATH": "/bin", CODEX_SANDBOX_ENV_VAR: "seatbelt"},
        )
        self.assertEqual(base[CODEX_SANDBOX_ENV_VAR], "landlock")

    def test_child_arg0_matches_rust_unix_spawn_selection(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs spawn_debug_sandbox_child.
        program = Path("/usr/bin/codex-linux-sandbox")

        self.assertEqual(
            debug_sandbox_child_arg0(program, arg0="codex-linux-sandbox", is_unix=True),
            "codex-linux-sandbox",
        )
        self.assertEqual(
            debug_sandbox_child_arg0(program, arg0=None, is_unix=True),
            "/usr/bin/codex-linux-sandbox",
        )
        self.assertIsNone(debug_sandbox_child_arg0(program, arg0="ignored", is_unix=False))

    def test_windows_stdin_forward_chunks_match_rust_forwarder_size(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs windows_stdio_bridge::spawn_input_forwarder.
        data = b"a" * WINDOWS_STDIN_FORWARD_CHUNK_SIZE + b"tail"

        self.assertEqual(
            windows_stdin_forward_chunks(data),
            [b"a" * WINDOWS_STDIN_FORWARD_CHUNK_SIZE, b"tail"],
        )
        self.assertEqual(windows_stdin_forward_chunks(b""), [])
        with self.assertRaisesRegex(TypeError, "data must be bytes"):
            windows_stdin_forward_chunks("not-bytes")  # type: ignore[arg-type]

    def test_windows_output_forward_bytes_match_rust_forwarder_order(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs windows_stdio_bridge::spawn_output_forwarder.
        self.assertEqual(windows_output_forward_bytes([b"alpha", b"beta"]), b"alphabeta")
        self.assertEqual(windows_output_forward_bytes([]), b"")
        with self.assertRaisesRegex(TypeError, "chunks must contain bytes"):
            windows_output_forward_bytes([b"alpha", "beta"])  # type: ignore[list-item]
        self.assertFalse(
            cli_overrides_use_legacy_sandbox_mode(
                [
                    ("default_permissions", ":workspace"),
                    ("sandbox.mode", "read-only"),
                ]
            )
        )
        self.assertIs(
            ManagedRequirementsMode.for_profile_invocation(
                permissions_profile=None,
                include_managed_config=False,
            ),
            ManagedRequirementsMode.INCLUDE,
        )

    def test_execution_plan_uses_cwd_for_permission_profile_cwd(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_sandbox.
        plan = build_debug_sandbox_execution_plan(
            ["echo", "hello"],
            cwd="/tmp/project",
            permissions_profile=":workspace",
            include_managed_config=False,
            base_env={"PATH": "/bin"},
            platform="linux",
        )

        self.assertEqual(plan.cwd, Path("/tmp/project"))
        self.assertEqual(plan.permission_profile_cwd, Path("/tmp/project"))
        self.assertEqual(plan.command, ("echo", "hello"))
        self.assertIs(plan.managed_requirements_mode, ManagedRequirementsMode.IGNORE)

    def test_execution_plan_applies_network_env_before_disabled_marker(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs spawn_debug_sandbox_child apply_env ordering.
        plan = build_debug_sandbox_execution_plan(
            ["echo"],
            sandbox_type="seatbelt",
            network_sandbox_enabled=False,
            network_env={
                "HTTPS_PROXY": "http://127.0.0.1:1234",
                CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR: "proxy",
            },
            base_env={"PATH": "/bin", CODEX_SANDBOX_ENV_VAR: "old"},
            platform="darwin",
        )

        self.assertEqual(plan.env[CODEX_SANDBOX_ENV_VAR], "seatbelt")
        self.assertEqual(plan.env["HTTPS_PROXY"], "http://127.0.0.1:1234")
        self.assertEqual(plan.env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "1")

    def test_execution_plan_records_backend_program_args_and_arg0(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_sandbox backend spawn inputs.
        landlock = build_debug_sandbox_execution_plan(
            ["echo", "hello"],
            sandbox_type="landlock",
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
            backend_args=["--sandbox", "echo", "hello"],
            base_env={"PATH": "/bin"},
            platform="linux",
        )
        seatbelt = build_debug_sandbox_execution_plan(
            ["echo", "hello"],
            sandbox_type="seatbelt",
            backend_args=["-p", "(version 1)", "echo", "hello"],
            base_env={"PATH": "/bin"},
            platform="darwin",
        )
        windows = build_debug_sandbox_execution_plan(
            ["cmd", "/c", "echo hi"],
            sandbox_type="windows",
            base_env={"PATH": "C:/Windows"},
            platform="win32",
        )

        self.assertEqual(landlock.backend_program, Path("/opt/codex-linux-sandbox"))
        self.assertEqual(landlock.backend_args, ("--sandbox", "echo", "hello"))
        self.assertEqual(landlock.child_arg0, "codex-linux-sandbox")
        self.assertEqual(seatbelt.backend_program, Path("/usr/bin/sandbox-exec"))
        self.assertEqual(seatbelt.backend_args, ("-p", "(version 1)", "echo", "hello"))
        self.assertIsNone(seatbelt.child_arg0)
        self.assertIsNone(windows.backend_program)
        self.assertEqual(windows.backend_args, ("cmd", "/c", "echo hi"))
        self.assertIsNone(windows.child_arg0)

    def test_config_load_plan_matches_rust_loader_decisions(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs load_debug_sandbox_config_with_codex_home.
        plan = build_debug_sandbox_config_load_plan(
            [("model", "gpt-5")],
            permissions_profile=":workspace",
            cwd="/tmp/work",
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
            codex_home="/tmp/codex-home",
            managed_requirements_mode=ManagedRequirementsMode.IGNORE,
            loader_overrides={"user_config_profile": "work"},
            strict_config=True,
            config_uses_permission_profile=False,
        )
        with_legacy = build_debug_sandbox_config_load_plan(
            [("sandbox_mode", "workspace-write")],
            config_uses_permission_profile=False,
        )
        with_profile_config = build_debug_sandbox_config_load_plan(
            [],
            config_uses_permission_profile=True,
        )

        self.assertEqual(plan.cli_overrides, (("model", "gpt-5"), ("default_permissions", ":workspace")))
        self.assertEqual(plan.harness_cwd, Path("/tmp/work"))
        self.assertEqual(plan.codex_linux_sandbox_exe, Path("/opt/codex-linux-sandbox"))
        self.assertEqual(plan.codex_home, Path("/tmp/codex-home"))
        self.assertEqual(plan.fallback_cwd, Path("/tmp/codex-home"))
        self.assertEqual(
            plan.loader_overrides,
            {"user_config_profile": "work", "ignore_managed_requirements": True},
        )
        self.assertTrue(plan.strict_config)
        self.assertFalse(plan.uses_legacy_sandbox_mode_override)
        self.assertTrue(plan.should_retry_with_read_only)
        self.assertTrue(with_legacy.uses_legacy_sandbox_mode_override)
        self.assertFalse(with_legacy.should_retry_with_read_only)
        self.assertFalse(with_profile_config.should_retry_with_read_only)

    def test_config_load_runner_matches_rust_read_only_retry(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs load_debug_sandbox_config_with_codex_home.
        calls = []

        def loader(plan, cli_overrides, sandbox_mode):
            calls.append((cli_overrides, sandbox_mode, plan.loader_overrides))
            return {"sandbox_mode": sandbox_mode or "ambient"}

        retry_plan = build_debug_sandbox_config_load_plan(
            [("model", "gpt-5")],
            managed_requirements_mode=ManagedRequirementsMode.IGNORE,
            loader_overrides={"user_config_profile": "work"},
            config_uses_permission_profile=False,
        )
        no_retry_plan = build_debug_sandbox_config_load_plan(
            [("model", "gpt-5")],
            config_uses_permission_profile=True,
        )

        retried = run_debug_sandbox_config_load_plan(retry_plan, loader)
        stable = run_debug_sandbox_config_load_plan(no_retry_plan, loader)

        self.assertEqual(retried.config, {"sandbox_mode": "read-only"})
        self.assertTrue(retried.retried_with_read_only)
        self.assertEqual(
            retried.attempts,
            (
                ((("model", "gpt-5"),), None),
                ((("model", "gpt-5"),), "read-only"),
            ),
        )
        self.assertEqual(stable.config, {"sandbox_mode": "ambient"})
        self.assertFalse(stable.retried_with_read_only)
        self.assertEqual(calls[0][2], {"user_config_profile": "work", "ignore_managed_requirements": True})
        self.assertEqual(calls[-1][1], None)

    def test_config_builder_adapter_matches_rust_builder_call_order(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs build_debug_sandbox_config_with_loader_overrides.
        calls = []

        class FakeBuilder:
            def cli_overrides(self, value):
                calls.append(("cli_overrides", value))
                return self

            def harness_overrides(self, value):
                calls.append(("harness_overrides", value))
                return self

            def strict_config(self, value):
                calls.append(("strict_config", value))
                return self

            def loader_overrides(self, value):
                calls.append(("loader_overrides", value))
                return self

            def codex_home(self, value):
                calls.append(("codex_home", value))
                return self

            def fallback_cwd(self, value):
                calls.append(("fallback_cwd", value))
                return self

            def build(self):
                calls.append(("build", None))
                return {"built": True, "calls": tuple(calls)}

        plan = build_debug_sandbox_config_load_plan(
            [("model", "gpt-5")],
            cwd="/workspace",
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
            codex_home="/tmp/codex-home",
            managed_requirements_mode=ManagedRequirementsMode.IGNORE,
            loader_overrides={"user_config_profile": "work"},
            strict_config=True,
        )

        result = run_debug_sandbox_config_load_plan(
            plan,
            lambda current_plan, cli_overrides, sandbox_mode: build_debug_sandbox_config_with_loader_overrides_from_plan(
                current_plan,
                cli_overrides,
                sandbox_mode,
                FakeBuilder,
            ),
        )

        self.assertEqual(result.config["built"], True)
        self.assertEqual(
            result.attempts,
            (
                ((("model", "gpt-5"),), None),
                ((("model", "gpt-5"),), "read-only"),
            ),
        )
        self.assertEqual(calls[0], ("cli_overrides", (("model", "gpt-5"),)))
        self.assertEqual(
            calls[1],
            (
                "harness_overrides",
                {
                    "cwd": Path("/workspace"),
                    "codex_linux_sandbox_exe": Path("/opt/codex-linux-sandbox"),
                    "sandbox_mode": None,
                },
            ),
        )
        self.assertEqual(calls[2], ("strict_config", True))
        self.assertEqual(calls[3], ("loader_overrides", {"user_config_profile": "work", "ignore_managed_requirements": True}))
        self.assertEqual(calls[4], ("codex_home", Path("/tmp/codex-home")))
        self.assertEqual(calls[5], ("fallback_cwd", Path("/tmp/codex-home")))
        self.assertEqual(calls[6], ("build", None))
        self.assertIn(
            (
                "harness_overrides",
                {
                    "cwd": Path("/workspace"),
                    "codex_linux_sandbox_exe": Path("/opt/codex-linux-sandbox"),
                    "sandbox_mode": "read-only",
                },
            ),
            calls,
        )

    def test_default_config_builder_bridge_loads_python_config_layers(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs build_debug_sandbox_config_with_loader_overrides.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "home"
            cwd = root / "workspace"
            system_root = root / "system"
            codex_home.mkdir()
            cwd.mkdir()
            system_root.mkdir()
            (codex_home / "config.toml").write_text(
                'model = "from-user"\ndefault_permissions = ":workspace"\n',
                encoding="utf-8",
            )

            plan = build_debug_sandbox_config_load_plan(
                [("model", "from-cli")],
                cwd=cwd,
                codex_home=codex_home,
                codex_linux_sandbox_exe=root / "codex-linux-sandbox",
                loader_overrides={
                    "system_config_path": system_root / "config.toml",
                    "system_requirements_path": system_root / "requirements.toml",
                    "managed_config_path": system_root / "managed.toml",
                    "ignore_managed_requirements": True,
                },
                config_uses_permission_profile=True,
            )

            loaded = load_debug_sandbox_config_with_default_builder(plan)

        config = loaded.config
        self.assertIsInstance(config, DebugSandboxConfigBuilderResult)
        self.assertFalse(loaded.retried_with_read_only)
        self.assertEqual(config.effective_config["model"], "from-cli")
        self.assertEqual(config.effective_config["default_permissions"], ":workspace")
        self.assertEqual(config.effective_config["cwd"], cwd)
        self.assertEqual(config.effective_config["codex_linux_sandbox_exe"], root / "codex-linux-sandbox")
        self.assertEqual(config.cli_overrides, (("model", "from-cli"),))
        self.assertEqual(config.codex_home, codex_home)
        self.assertEqual(config.fallback_cwd, codex_home)
        self.assertTrue(config.loader_overrides["ignore_managed_requirements"])

    def test_platform_implementation_decisions_document_debug_sandbox_boundaries(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs delegates platform-heavy implementation details.
        decisions = {
            decision.concern: decision
            for decision in build_debug_sandbox_platform_implementation_decisions()
        }

        self.assertEqual(
            decisions["seatbelt_policy_generation"].owner,
            "codex-sandboxing/seatbelt",
        )
        self.assertEqual(decisions["seatbelt_policy_generation"].status, "delegated")
        self.assertEqual(
            decisions["landlock_permission_profile_serialization"].owner,
            "codex-protocol/codex-sandboxing",
        )
        self.assertEqual(
            decisions["windows_session_objects_and_forwarder_threads"].status,
            "adapter_boundary",
        )
        self.assertEqual(
            decisions["config_builder_implementation"].debug_sandbox_role,
            "call ConfigBuilder-shaped loader in Rust order",
        )

    def test_network_plan_matches_rust_proxy_lifetime_decision(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs managed network proxy planning.
        present = build_debug_sandbox_network_plan(
            network_spec_present=True,
            permission_profile=":workspace",
            managed_network_requirements_enabled=True,
            proxy_env={"HTTPS_PROXY": "http://127.0.0.1:7777"},
        )
        absent = build_debug_sandbox_network_plan(
            network_spec_present=False,
            permission_profile=":workspace",
            managed_network_requirements_enabled=True,
            proxy_env={"HTTPS_PROXY": "http://127.0.0.1:7777"},
        )

        self.assertTrue(present.should_start_proxy)
        self.assertEqual(present.permission_profile, ":workspace")
        self.assertTrue(present.managed_network_requirements_enabled)
        self.assertEqual(present.audit_metadata, {})
        self.assertEqual(present.proxy_env, {"HTTPS_PROXY": "http://127.0.0.1:7777"})
        self.assertEqual(present.lifetime, "child_process")
        self.assertFalse(absent.should_start_proxy)
        self.assertIsNone(absent.permission_profile)
        self.assertFalse(absent.managed_network_requirements_enabled)
        self.assertEqual(absent.proxy_env, {})

    def test_network_proxy_error_format_matches_rust_context(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs managed network proxy startup error.
        self.assertEqual(
            format_debug_sandbox_network_proxy_error("bind failed"),
            "failed to start managed network proxy: bind failed",
        )

    def test_network_proxy_start_uses_planned_inputs(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs managed network proxy startup.
        calls = []

        def fake_starter(plan):
            calls.append(plan)
            return {"HTTPS_PROXY": "http://127.0.0.1:7777"}

        present = build_debug_sandbox_network_plan(
            network_spec_present=True,
            permission_profile=":workspace",
            managed_network_requirements_enabled=True,
            proxy_env={"HTTPS_PROXY": "http://fallback.invalid"},
        )
        absent = build_debug_sandbox_network_plan(network_spec_present=False)

        started = start_debug_sandbox_network_proxy_plan(present, starter=fake_starter)
        skipped = start_debug_sandbox_network_proxy_plan(absent, starter=fake_starter)

        self.assertTrue(started.started)
        self.assertEqual(started.proxy_env, {"HTTPS_PROXY": "http://127.0.0.1:7777"})
        self.assertEqual(started.lifetime, "child_process")
        self.assertEqual(calls, [present])
        self.assertFalse(skipped.started)
        self.assertEqual(skipped.proxy_env, {})

    def test_network_proxy_start_wraps_errors_like_rust_context(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs managed network proxy startup error.
        def failing_starter(plan):
            raise OSError("bind failed")

        present = build_debug_sandbox_network_plan(network_spec_present=True)

        with self.assertRaisesRegex(
            RuntimeError,
            "failed to start managed network proxy: bind failed",
        ):
            start_debug_sandbox_network_proxy_plan(present, starter=failing_starter)

    def test_subprocess_argv_prefers_backend_program_when_present(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs spawn_debug_sandbox_child program/args.
        backend = build_debug_sandbox_execution_plan(
            ["echo", "hello"],
            sandbox_type="landlock",
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
            backend_args=["--sandbox", "echo", "hello"],
            base_env={"PATH": "/bin"},
            platform="linux",
        )
        direct = build_debug_sandbox_execution_plan(
            ["cmd", "/c", "echo hi"],
            sandbox_type="windows",
            base_env={"PATH": "C:/Windows"},
            platform="win32",
        )

        self.assertEqual(
            debug_sandbox_subprocess_argv(backend),
            ("/opt/codex-linux-sandbox", "--sandbox", "echo", "hello"),
        )
        self.assertEqual(debug_sandbox_subprocess_argv(direct), ("cmd", "/c", "echo hi"))

    def test_execution_plan_converts_to_child_spawn_plan(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_sandbox to spawn_debug_sandbox_child.
        backend = build_debug_sandbox_execution_plan(
            ["echo", "hello"],
            cwd="/workspace",
            sandbox_type="landlock",
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
            backend_args=["--sandbox", "echo", "hello"],
            base_env={"PATH": "/bin"},
            network_sandbox_enabled=False,
            platform="linux",
        )
        direct = build_debug_sandbox_execution_plan(
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            sandbox_type="windows",
            base_env={"PATH": "C:/Windows"},
            platform="win32",
        )

        backend_spawn = debug_sandbox_child_spawn_plan_from_execution_plan(backend)
        direct_spawn = debug_sandbox_child_spawn_plan_from_execution_plan(
            direct,
            is_unix=False,
        )

        self.assertEqual(backend_spawn.program, Path("/opt/codex-linux-sandbox"))
        self.assertEqual(backend_spawn.args, ("--sandbox", "echo", "hello"))
        self.assertEqual(backend_spawn.arg0, "codex-linux-sandbox")
        self.assertEqual(backend_spawn.cwd, Path("/workspace"))
        self.assertEqual(backend_spawn.env["PATH"], "/bin")
        self.assertEqual(backend_spawn.env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "1")
        self.assertEqual(direct_spawn.program, Path("cmd"))
        self.assertEqual(direct_spawn.args, ("/c", "echo hi"))
        self.assertIsNone(direct_spawn.arg0)
        self.assertEqual(direct_spawn.cwd, Path("C:/work"))

    def test_execution_plan_runs_through_child_runner_and_exit_status(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_sandbox spawn/wait/exit flow.
        class Completed:
            returncode = 17

        calls: list[tuple[list[str], dict[str, object]]] = []

        def fake_runner(argv: list[str], **kwargs: object) -> Completed:
            calls.append((argv, kwargs))
            return Completed()

        plan = build_debug_sandbox_execution_plan(
            ["echo", "hello"],
            cwd="/workspace",
            sandbox_type="landlock",
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
            backend_args=["--sandbox", "echo", "hello"],
            base_env={"PATH": "/bin"},
            network_sandbox_enabled=False,
            platform="linux",
        )

        result = run_debug_sandbox_execution_plan_with_exit_status(
            plan,
            runner=fake_runner,
            platform="linux",
        )

        self.assertEqual(result.child.returncode, 17)
        self.assertEqual(
            result.child.argv,
            ("codex-linux-sandbox", "--sandbox", "echo", "hello"),
        )
        self.assertEqual(result.child.executable, "/opt/codex-linux-sandbox")
        self.assertEqual(result.exit_status.process_exit_code, 17)
        self.assertEqual(
            calls[0][0],
            ["codex-linux-sandbox", "--sandbox", "echo", "hello"],
        )
        self.assertEqual(calls[0][1]["executable"], "/opt/codex-linux-sandbox")
        self.assertEqual(calls[0][1]["cwd"], "/workspace")
        self.assertEqual(calls[0][1]["env"]["PATH"], "/bin")
        self.assertEqual(calls[0][1]["env"][CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "1")

    def test_backend_args_plan_matches_rust_builder_inputs(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs backend arg-builder inputs.
        landlock = build_debug_sandbox_backend_args_plan(
            ["echo", "hello"],
            sandbox_type="landlock",
            cwd="/workspace",
            permission_profile_cwd="/workspace",
            permission_profile=":workspace",
            use_legacy_landlock=True,
            managed_network_requirements_enabled=True,
        )
        seatbelt = build_debug_sandbox_backend_args_plan(
            ["echo", "hello"],
            sandbox_type="seatbelt",
            cwd="/workspace",
            permission_profile_cwd="/workspace",
            permission_profile=":workspace",
            use_legacy_landlock=True,
            managed_network_requirements_enabled=True,
            extra_allow_unix_sockets=["/tmp/codex.sock"],
        )

        self.assertEqual(landlock.command, ("echo", "hello"))
        self.assertEqual(landlock.cwd, Path("/workspace"))
        self.assertEqual(landlock.permission_profile_cwd, Path("/workspace"))
        self.assertEqual(landlock.permission_profile, ":workspace")
        self.assertTrue(landlock.use_legacy_landlock)
        self.assertTrue(landlock.allow_network_for_proxy)
        self.assertEqual(landlock.extra_allow_unix_sockets, ())
        self.assertFalse(landlock.enforce_managed_network)
        self.assertFalse(seatbelt.use_legacy_landlock)
        self.assertFalse(seatbelt.allow_network_for_proxy)
        self.assertEqual(seatbelt.extra_allow_unix_sockets, (Path("/tmp/codex.sock"),))
        self.assertFalse(seatbelt.enforce_managed_network)

    def test_backend_args_build_uses_injected_platform_builder(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs calls platform-specific backend arg builders.
        calls = []

        def fake_landlock_builder(plan):
            calls.append(plan)
            return ("--sandbox", *plan.command)

        landlock = build_debug_sandbox_backend_args_plan(
            ["echo", "hello"],
            sandbox_type="landlock",
            cwd="/workspace",
            permission_profile_cwd="/workspace",
            permission_profile=":workspace",
            managed_network_requirements_enabled=True,
        )
        built = build_debug_sandbox_backend_args_from_plan(
            landlock,
            builder=fake_landlock_builder,
        )
        fallback = build_debug_sandbox_backend_args_from_plan(landlock)

        self.assertEqual(calls, [landlock])
        self.assertEqual(built.sandbox_type, "landlock")
        self.assertEqual(built.args, ("--sandbox", "echo", "hello"))
        self.assertTrue(built.builder_invoked)
        self.assertEqual(fallback.args, ("echo", "hello"))
        self.assertFalse(fallback.builder_invoked)

    def test_seatbelt_backend_args_adapter_matches_rust_sandbox_exec_argv_shape(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs create_seatbelt_command_args call result.
        seatbelt = build_debug_sandbox_backend_args_plan(
            ["echo", "hello"],
            sandbox_type="seatbelt",
            cwd="/workspace",
            permission_profile_cwd="/workspace",
            permission_profile=":workspace",
            extra_allow_unix_sockets=["/tmp/codex.sock"],
        )

        built = build_debug_sandbox_seatbelt_backend_args_from_plan(
            seatbelt,
            policy="(version 1)",
            definitions={"READABLE_ROOT_0": "/workspace", "WRITABLE_ROOT_0": Path("/tmp")},
        )

        self.assertEqual(built.sandbox_type, "seatbelt")
        self.assertTrue(built.builder_invoked)
        self.assertEqual(built.adapter, "seatbelt")
        self.assertEqual(
            built.args,
            (
                "-p",
                "(version 1)",
                "-DREADABLE_ROOT_0=/workspace",
                "-DWRITABLE_ROOT_0=/tmp",
                "--",
                "echo",
                "hello",
            ),
        )
        with self.assertRaisesRegex(ValueError, "sandbox_type='seatbelt'"):
            build_debug_sandbox_seatbelt_backend_args_from_plan(
                build_debug_sandbox_backend_args_plan(
                    ["echo", "hello"],
                    sandbox_type="landlock",
                ),
                policy="(version 1)",
            )

    def test_landlock_backend_args_adapter_matches_rust_helper_argv_shape(self) -> None:
        # Rust parity: codex-sandboxing/src/landlock.rs create_linux_sandbox_command_args_for_permission_profile.
        landlock = build_debug_sandbox_backend_args_plan(
            ["/bin/true", "--flag"],
            sandbox_type="landlock",
            cwd="/tmp/link",
            permission_profile_cwd="/tmp",
            permission_profile=":read-only",
            use_legacy_landlock=True,
            managed_network_requirements_enabled=True,
        )

        built = build_debug_sandbox_landlock_backend_args_from_plan(
            landlock,
            permission_profile_json='{"preset":"read-only"}',
        )

        self.assertEqual(built.sandbox_type, "landlock")
        self.assertTrue(built.builder_invoked)
        self.assertEqual(built.adapter, "landlock")
        self.assertEqual(
            built.args,
            (
                "--sandbox-policy-cwd",
                "/tmp",
                "--command-cwd",
                "/tmp/link",
                "--permission-profile",
                '{"preset":"read-only"}',
                "--use-legacy-landlock",
                "--allow-network-for-proxy",
                "--",
                "/bin/true",
                "--flag",
            ),
        )
        with self.assertRaisesRegex(ValueError, "sandbox_type='landlock'"):
            build_debug_sandbox_landlock_backend_args_from_plan(
                build_debug_sandbox_backend_args_plan(
                    ["echo", "hello"],
                    sandbox_type="seatbelt",
                ),
                permission_profile_json="{}",
            )

    def test_backend_args_plan_runs_builder_output_through_child_runner(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs backend args are passed to spawn_debug_sandbox_child.
        builder_calls = []
        runner_calls = []

        class Completed:
            returncode = 29

        def fake_builder(plan):
            builder_calls.append(plan)
            return ("--sandbox", *plan.command)

        def fake_runner(argv, **kwargs):
            runner_calls.append((argv, kwargs))
            return Completed()

        landlock = build_debug_sandbox_backend_args_plan(
            ["echo", "hello"],
            sandbox_type="landlock",
            cwd="/workspace",
            permission_profile_cwd="/workspace",
            permission_profile=":workspace",
            managed_network_requirements_enabled=True,
        )

        result = run_debug_sandbox_backend_args_plan_with_exit_status(
            landlock,
            backend_program="/opt/codex-linux-sandbox",
            builder=fake_builder,
            runner=fake_runner,
            base_env={"PATH": "/bin"},
            network_sandbox_enabled=False,
            platform="linux",
        )

        self.assertEqual(builder_calls, [landlock])
        self.assertEqual(result.child.returncode, 29)
        self.assertEqual(result.exit_status.process_exit_code, 29)
        self.assertEqual(
            runner_calls[0][0],
            ["codex-linux-sandbox", "--sandbox", "echo", "hello"],
        )
        self.assertEqual(runner_calls[0][1]["executable"], "/opt/codex-linux-sandbox")
        self.assertEqual(runner_calls[0][1]["cwd"], "/workspace")
        self.assertEqual(runner_calls[0][1]["env"][CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "1")

    def test_windows_session_plan_matches_rust_spawn_inputs(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_windows_session.
        elevated = build_debug_sandbox_windows_session_plan(
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            permission_profile_cwd="C:/work",
            permission_profile=":workspace",
            codex_home="C:/codex",
            env={"PATH": "C:/Windows"},
            use_elevated=True,
            private_desktop=True,
        )
        legacy = build_debug_sandbox_windows_session_plan(
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            codex_home="C:/codex",
            use_elevated=False,
        )

        self.assertEqual(elevated.mode, "elevated")
        self.assertEqual(legacy.mode, "legacy")
        self.assertEqual(elevated.command, ("cmd", "/c", "echo hi"))
        self.assertEqual(elevated.cwd, Path("C:/work"))
        self.assertEqual(elevated.permission_profile_cwd, Path("C:/work"))
        self.assertEqual(elevated.permission_profile, ":workspace")
        self.assertEqual(elevated.codex_home, Path("C:/codex"))
        self.assertEqual(elevated.env, {"PATH": "C:/Windows"})
        self.assertIsNone(elevated.read_roots_override)
        self.assertFalse(elevated.read_roots_include_platform_defaults)
        self.assertIsNone(elevated.write_roots_override)
        self.assertEqual(elevated.deny_read_paths_override, ())
        self.assertEqual(elevated.deny_write_paths_override, ())
        self.assertFalse(elevated.tty)
        self.assertTrue(elevated.stdin_open)
        self.assertTrue(elevated.private_desktop)
        self.assertEqual(elevated.output_drain_timeout_seconds, 5)
        self.assertEqual(legacy.permission_profile_cwd, Path("C:/work"))
        self.assertEqual(legacy.env, {})

    def test_windows_session_plan_from_config_matches_rust_config_inputs(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_windows_session.
        class Permissions:
            windows_sandbox_private_desktop = True

            def effective_permission_profile(self):
                return ":workspace"

        class Config:
            permissions = Permissions()
            windows_sandbox_level = "Elevated"
            codex_home = Path("C:/codex")

        plan = build_debug_sandbox_windows_session_plan_from_config(
            Config(),
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            permission_profile_cwd="C:/profile",
            env={"PATH": "C:/Windows"},
        )

        self.assertEqual(plan.mode, "elevated")
        self.assertEqual(plan.permission_profile, ":workspace")
        self.assertEqual(plan.permission_profile_cwd, Path("C:/profile"))
        self.assertEqual(plan.codex_home, Path("C:/codex"))
        self.assertEqual(plan.cwd, Path("C:/work"))
        self.assertEqual(plan.env, {"PATH": "C:/Windows"})
        self.assertTrue(plan.private_desktop)
        self.assertFalse(plan.tty)
        self.assertTrue(plan.stdin_open)

    def test_windows_session_run_uses_spawner_and_wraps_errors(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_windows_session spawn result.
        calls = []

        class Spawned:
            exit_code = 23

        def spawner(plan):
            calls.append(plan)
            return Spawned()

        def failing_spawner(plan):
            raise OSError("access denied")

        plan = build_debug_sandbox_windows_session_plan(
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            codex_home="C:/codex",
            use_elevated=True,
        )

        success = run_debug_sandbox_windows_session_plan(plan, spawner=spawner)
        failure = run_debug_sandbox_windows_session_plan(plan, spawner=failing_spawner)

        self.assertEqual(calls, [plan])
        self.assertEqual(success.mode, "elevated")
        self.assertEqual(success.exit_code, 23)
        self.assertEqual(success.output_drain_timeout_seconds, 5)
        self.assertIsNone(success.error_message)
        self.assertEqual(failure.exit_code, 1)
        self.assertEqual(failure.error_message, "windows sandbox failed: access denied")

    def test_windows_session_control_flow_matches_rust_exit_and_ctrl_c_paths(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_windows_session control flow.
        plan = build_debug_sandbox_windows_session_plan(
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            codex_home="C:/codex",
            use_elevated=True,
        )

        normal = run_debug_sandbox_windows_session_control_flow(
            plan,
            exit_code=7,
            stdin_eof=True,
        )
        interrupted = run_debug_sandbox_windows_session_control_flow(
            plan,
            exit_code=None,
            ctrl_c=True,
        )

        self.assertEqual(normal.exit_code, 7)
        self.assertFalse(normal.requested_terminate)
        self.assertTrue(normal.closed_stdin_after_eof)
        self.assertTrue(normal.aborted_stdin_close_task)
        self.assertTrue(normal.waited_for_output_drain)
        self.assertEqual(normal.output_drain_timeout_seconds, 5)

        self.assertEqual(interrupted.exit_code, -1)
        self.assertTrue(interrupted.requested_terminate)
        self.assertFalse(interrupted.closed_stdin_after_eof)
        self.assertTrue(interrupted.aborted_stdin_close_task)
        self.assertTrue(interrupted.waited_for_output_drain)
        self.assertEqual(interrupted.output_drain_timeout_seconds, 5)

    def test_windows_session_io_bridge_forwards_stdio_and_control_hooks(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs Windows stdio bridge around session hooks.
        calls = []
        plan = build_debug_sandbox_windows_session_plan(
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            codex_home="C:/codex",
            use_elevated=True,
        )
        stdin = b"a" * WINDOWS_STDIN_FORWARD_CHUNK_SIZE + b"tail"

        result = run_debug_sandbox_windows_session_io_bridge(
            plan,
            stdin=stdin,
            stdout_chunks=(b"out", b"put"),
            stderr_chunks=(b"err", b"or"),
            exit_code=3,
            ctrl_c=True,
            write_stdin=lambda chunk: calls.append(("write", chunk)),
            close_stdin=lambda: calls.append(("close", None)),
            request_terminate=lambda: calls.append(("terminate", None)),
        )

        self.assertEqual(
            result.stdin_chunks,
            (b"a" * WINDOWS_STDIN_FORWARD_CHUNK_SIZE, b"tail"),
        )
        self.assertEqual(result.stdout, b"output")
        self.assertEqual(result.stderr, b"error")
        self.assertEqual(result.control.exit_code, 3)
        self.assertTrue(result.control.requested_terminate)
        self.assertTrue(result.control.closed_stdin_after_eof)
        self.assertEqual(
            result.actions,
            ("write_stdin", "write_stdin", "close_stdin", "request_terminate"),
        )
        self.assertEqual(
            calls,
            [
                ("write", b"a" * WINDOWS_STDIN_FORWARD_CHUNK_SIZE),
                ("write", b"tail"),
                ("close", None),
                ("terminate", None),
            ],
        )

    def test_windows_session_spawn_stdio_bridge_combines_spawn_and_forwarders(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_windows_session post-spawn bridge.
        calls = []

        class Spawned:
            stdin = b"abc"
            stdout_chunks = (b"out", b"put")
            stderr_chunks = (b"err",)
            exit_code = 42

        def spawner(plan):
            calls.append(("spawn", plan.mode))
            return Spawned()

        def failing_spawner(plan):
            raise OSError("denied")

        plan = build_debug_sandbox_windows_session_plan(
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            codex_home="C:/codex",
            use_elevated=True,
        )

        success = run_debug_sandbox_windows_session_with_stdio_bridge(
            plan,
            spawner=spawner,
            write_stdin=lambda chunk: calls.append(("stdin", chunk)),
            close_stdin=lambda: calls.append(("close", None)),
        )
        failure = run_debug_sandbox_windows_session_with_stdio_bridge(
            plan,
            spawner=failing_spawner,
        )

        self.assertEqual(success.run.mode, "elevated")
        self.assertEqual(success.run.exit_code, 42)
        self.assertIsNone(success.run.error_message)
        self.assertIsNotNone(success.io)
        assert success.io is not None
        self.assertEqual(success.io.stdin_chunks, (b"abc",))
        self.assertEqual(success.io.stdout, b"output")
        self.assertEqual(success.io.stderr, b"err")
        self.assertEqual(success.io.control.exit_code, 42)
        self.assertEqual(calls, [("spawn", "elevated"), ("stdin", b"abc"), ("close", None)])
        self.assertEqual(failure.run.exit_code, 1)
        self.assertEqual(failure.run.error_message, "windows sandbox failed: denied")
        self.assertIsNone(failure.io)

    def test_deferred_native_boundaries_record_remaining_platform_work(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs delegates native platform-heavy work.
        boundaries = {
            boundary.concern: boundary
            for boundary in build_debug_sandbox_deferred_native_boundaries()
        }

        self.assertEqual(
            boundaries["windows_session_objects"].upstream_owner,
            "codex-windows-sandbox",
        )
        self.assertEqual(
            boundaries["windows_background_forwarder_threads"].python_boundary,
            "run_debug_sandbox_windows_session_io_bridge",
        )
        self.assertIn(
            "sibling crates",
            boundaries["platform_policy_builders"].rationale,
        )

    def test_entrypoint_plan_matches_rust_public_entrypoint_forwarding(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_* entrypoints.
        seatbelt = build_debug_sandbox_entrypoint_plan(
            ["echo", "hello"],
            sandbox_type="seatbelt",
            cwd="/workspace",
            permissions_profile=":workspace",
            include_managed_config=False,
            config_overrides=(("model", "gpt-5"),),
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
            loader_overrides={"user_config_profile": "work"},
            log_denials=True,
            allow_unix_sockets=["/tmp/codex.sock"],
        )
        landlock = build_debug_sandbox_entrypoint_plan(
            ["echo", "hello"],
            sandbox_type="landlock",
            cwd="/workspace",
            permissions_profile=":workspace",
            include_managed_config=False,
            log_denials=True,
            allow_unix_sockets=["/tmp/codex.sock"],
        )
        windows = build_debug_sandbox_entrypoint_plan(
            ["cmd", "/c", "echo hi"],
            sandbox_type="windows",
            include_managed_config=True,
        )

        self.assertEqual(seatbelt.sandbox_type, "seatbelt")
        self.assertEqual(seatbelt.command, ("echo", "hello"))
        self.assertEqual(seatbelt.cwd, Path("/workspace"))
        self.assertEqual(seatbelt.permissions_profile, ":workspace")
        self.assertIs(seatbelt.managed_requirements_mode, ManagedRequirementsMode.IGNORE)
        self.assertEqual(seatbelt.config_overrides, (("model", "gpt-5"),))
        self.assertEqual(seatbelt.codex_linux_sandbox_exe, Path("/opt/codex-linux-sandbox"))
        self.assertEqual(seatbelt.loader_overrides, {"user_config_profile": "work"})
        self.assertTrue(seatbelt.log_denials)
        self.assertEqual(seatbelt.allow_unix_sockets, (Path("/tmp/codex.sock"),))
        self.assertFalse(landlock.log_denials)
        self.assertEqual(landlock.allow_unix_sockets, ())
        self.assertFalse(windows.log_denials)
        self.assertEqual(windows.allow_unix_sockets, ())
        self.assertIs(windows.managed_requirements_mode, ManagedRequirementsMode.INCLUDE)

    def test_entrypoint_plan_runs_through_shared_runner(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs public entrypoints feed run_command_under_sandbox.
        class Completed:
            returncode = 19

        calls: list[tuple[list[str], dict[str, object]]] = []

        def fake_runner(argv: list[str], **kwargs: object) -> Completed:
            calls.append((argv, kwargs))
            return Completed()

        plan = build_debug_sandbox_entrypoint_plan(
            ["echo", "hello"],
            sandbox_type="landlock",
            cwd="/workspace",
            permissions_profile=":workspace",
            include_managed_config=False,
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
        )

        result = run_debug_sandbox_entrypoint_plan_with_exit_status(
            plan,
            runner=fake_runner,
            platform="linux",
            backend_args=["--sandbox", "echo", "hello"],
            network_sandbox_enabled=False,
            base_env={"PATH": "/bin"},
        )

        self.assertEqual(result.child.returncode, 19)
        self.assertEqual(
            result.child.argv,
            ("codex-linux-sandbox", "--sandbox", "echo", "hello"),
        )
        self.assertEqual(result.child.executable, "/opt/codex-linux-sandbox")
        self.assertEqual(result.exit_status.process_exit_code, 19)
        self.assertEqual(calls[0][1]["cwd"], "/workspace")
        self.assertEqual(calls[0][1]["env"]["PATH"], "/bin")
        self.assertEqual(calls[0][1]["env"][CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "1")

    def test_child_spawn_plan_matches_rust_spawn_helper_ordering(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs spawn_debug_sandbox_child.
        plan = build_debug_sandbox_child_spawn_plan(
            "/opt/codex-linux-sandbox",
            ["--sandbox", "echo", "hello"],
            cwd="/workspace",
            env={"PATH": "/bin", CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR: "proxy"},
            env_updates={"HTTPS_PROXY": "http://127.0.0.1:7777"},
            arg0="codex-linux-sandbox",
            network_sandbox_enabled=False,
            is_unix=True,
        )
        non_unix = build_debug_sandbox_child_spawn_plan(
            "sandbox.exe",
            ["cmd", "/c", "echo hi"],
            cwd="C:/work",
            arg0="ignored",
            is_unix=False,
        )

        self.assertEqual(plan.program, Path("/opt/codex-linux-sandbox"))
        self.assertEqual(plan.args, ("--sandbox", "echo", "hello"))
        self.assertEqual(plan.arg0, "codex-linux-sandbox")
        self.assertEqual(plan.cwd, Path("/workspace"))
        self.assertEqual(plan.env["PATH"], "/bin")
        self.assertEqual(plan.env["HTTPS_PROXY"], "http://127.0.0.1:7777")
        self.assertEqual(plan.env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "1")
        self.assertTrue(plan.env_clear)
        self.assertEqual(plan.stdin, "inherit")
        self.assertEqual(plan.stdout, "inherit")
        self.assertEqual(plan.stderr, "inherit")
        self.assertTrue(plan.kill_on_drop)
        self.assertIsNone(non_unix.arg0)

    def test_child_spawn_runner_uses_plan_launch_inputs(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs spawn_debug_sandbox_child process launch inputs.
        class Completed:
            returncode = 23

        calls: list[tuple[list[str], dict[str, object]]] = []

        def fake_runner(argv: list[str], **kwargs: object) -> Completed:
            calls.append((argv, kwargs))
            return Completed()

        plan = build_debug_sandbox_child_spawn_plan(
            "/opt/codex-linux-sandbox",
            ["--sandbox", "echo", "hello"],
            cwd="/workspace",
            env={"PATH": "/bin"},
            arg0="codex-linux-sandbox",
        )

        result = run_debug_sandbox_child_spawn_plan(plan, runner=fake_runner)

        self.assertEqual(result.returncode, 23)
        self.assertEqual(
            result.argv,
            ("codex-linux-sandbox", "--sandbox", "echo", "hello"),
        )
        self.assertEqual(result.executable, "/opt/codex-linux-sandbox")
        self.assertEqual(result.cwd, Path("/workspace"))
        self.assertEqual(result.env, {"PATH": "/bin"})
        self.assertEqual(
            calls[0][0],
            ["codex-linux-sandbox", "--sandbox", "echo", "hello"],
        )
        self.assertEqual(calls[0][1]["executable"], "/opt/codex-linux-sandbox")
        self.assertEqual(calls[0][1]["cwd"], "/workspace")
        self.assertEqual(calls[0][1]["env"], {"PATH": "/bin"})
        self.assertIsNone(calls[0][1]["stdin"])
        self.assertIsNone(calls[0][1]["stdout"])
        self.assertIsNone(calls[0][1]["stderr"])
        self.assertFalse(calls[0][1]["check"])

    def test_child_spawn_runner_builds_exit_status_plan_after_wait(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs child.wait() followed by handle_exit_status.
        class Completed:
            returncode = 42

        def fake_runner(argv: list[str], **kwargs: object) -> Completed:
            return Completed()

        plan = build_debug_sandbox_child_spawn_plan(
            "/usr/bin/sandbox-exec",
            ["-p", "(version 1)", "echo", "hello"],
            cwd="/workspace",
            env={"PATH": "/bin"},
            arg0=None,
        )

        result = run_debug_sandbox_child_spawn_plan_with_exit_status(
            plan,
            runner=fake_runner,
            platform="linux",
        )

        self.assertEqual(result.child.returncode, 42)
        self.assertEqual(
            result.child.argv,
            ("/usr/bin/sandbox-exec", "-p", "(version 1)", "echo", "hello"),
        )
        self.assertEqual(result.child.executable, "/usr/bin/sandbox-exec")
        self.assertEqual(result.exit_status.child_exit_code, 42)
        self.assertEqual(result.exit_status.process_exit_code, 42)
        self.assertFalse(result.exit_status.used_signal_fallback)
        self.assertFalse(result.exit_status.used_generic_fallback)

    def test_child_run_exit_status_raise_matches_rust_handle_exit_status(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs child wait result is passed to handle_exit_status.
        class Completed:
            returncode = 42

        def fake_runner(argv: list[str], **kwargs: object) -> Completed:
            return Completed()

        plan = build_debug_sandbox_child_spawn_plan(
            "/usr/bin/sandbox-exec",
            ["-p", "(version 1)", "echo", "hello"],
            cwd="/workspace",
            env={"PATH": "/bin"},
        )
        result = run_debug_sandbox_child_spawn_plan_with_exit_status(
            plan,
            runner=fake_runner,
            platform="linux",
        )

        with self.assertRaises(SystemExit) as child_exit:
            raise_debug_sandbox_child_run_exit_status(result)

        self.assertEqual(child_exit.exception.code, 42)

    def test_network_env_application_plan_matches_rust_apply_env_order(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs network apply_env closures.
        seatbelt = build_debug_sandbox_network_env_application_plan(
            sandbox_type="seatbelt",
            base_env={"PATH": "/bin", CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR: "proxy"},
            proxy_env={
                "HTTPS_PROXY": "http://127.0.0.1:7777",
                CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR: "proxy",
            },
            network_present=True,
            network_sandbox_enabled=False,
        )
        landlock_without_proxy = build_debug_sandbox_network_env_application_plan(
            sandbox_type="landlock",
            base_env={"PATH": "/bin"},
            proxy_env={"HTTPS_PROXY": "http://127.0.0.1:7777"},
            network_present=False,
            network_sandbox_enabled=True,
        )

        self.assertTrue(seatbelt.applies_seatbelt_marker)
        self.assertEqual(seatbelt.env_after_apply[CODEX_SANDBOX_ENV_VAR], "seatbelt")
        self.assertEqual(seatbelt.env_after_apply["HTTPS_PROXY"], "http://127.0.0.1:7777")
        self.assertEqual(seatbelt.env_after_apply[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "proxy")
        self.assertEqual(seatbelt.final_env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "1")
        self.assertEqual(seatbelt.disabled_network_marker_value, "1")
        self.assertFalse(landlock_without_proxy.applies_seatbelt_marker)
        self.assertNotIn("HTTPS_PROXY", landlock_without_proxy.env_after_apply)
        self.assertNotIn(CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR, landlock_without_proxy.final_env)

    def test_denial_logger_plan_matches_rust_macos_lifecycle(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs DenialLogger lifecycle.
        enabled = build_debug_sandbox_denial_logger_plan(
            log_denials=True,
            platform="darwin",
        )
        disabled = build_debug_sandbox_denial_logger_plan(
            log_denials=True,
            platform="linux",
        )
        not_requested = build_debug_sandbox_denial_logger_plan(
            log_denials=False,
            platform="darwin",
        )

        self.assertTrue(enabled.enabled)
        self.assertTrue(enabled.create_before_spawn)
        self.assertTrue(enabled.attach_after_child_spawn)
        self.assertTrue(enabled.finish_after_child_wait)
        self.assertEqual(enabled.output_header, "\n=== Sandbox denials ===")
        self.assertEqual(enabled.empty_message, "None found.")
        self.assertEqual(enabled.denial_line_template, "({name}) {capability}")
        self.assertFalse(disabled.enabled)
        self.assertFalse(disabled.create_before_spawn)
        self.assertIsNone(disabled.output_header)
        self.assertFalse(not_requested.enabled)

    def test_denial_summary_format_matches_rust_output(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs DenialLogger finish output.
        self.assertEqual(
            format_debug_sandbox_denial_summary([]),
            ("", "=== Sandbox denials ===", "None found."),
        )
        self.assertEqual(
            format_debug_sandbox_denial_summary(
                [
                    ("process", "file-read-data"),
                    ("network", "outbound"),
                ]
            ),
            (
                "",
                "=== Sandbox denials ===",
                "(process) file-read-data",
                "(network) outbound",
            ),
        )

    def test_seatbelt_parse_message_matches_rust_regex(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox/seatbelt.rs parse_message.
        parsed = parse_debug_sandbox_seatbelt_denial_message(
            "Sandbox: processname(1234) deny(1) file-read-data /tmp/secret"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.pid, 1234)
        self.assertEqual(parsed.name, "processname")
        self.assertEqual(parsed.capability, "file-read-data /tmp/secret")
        self.assertIsNone(parse_debug_sandbox_seatbelt_denial_message("not sandbox"))
        self.assertIsNone(
            parse_debug_sandbox_seatbelt_denial_message(
                "Sandbox: processname(not-a-pid) deny(1) file-read-data"
            )
        )

    def test_seatbelt_collect_denials_filters_pid_and_deduplicates_like_rust(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox/seatbelt.rs DenialLogger::finish.
        lines = [
            '{"eventMessage":"Sandbox: proc(10) deny(1) file-read-data /tmp/a"}',
            '{"eventMessage":"Sandbox: proc(10) deny(1) file-read-data /tmp/a"}',
            '{"eventMessage":"Sandbox: other(11) deny(1) network-outbound"}',
            '{"eventMessage":"Sandbox: ignored(12) deny(1) file-write-data"}',
            '{"eventMessage":42}',
            'not json',
        ]

        self.assertEqual(
            collect_debug_sandbox_seatbelt_denials(lines, {10, 11}),
            (("proc", "file-read-data /tmp/a"), ("other", "network-outbound")),
        )
        self.assertEqual(collect_debug_sandbox_seatbelt_denials(lines, set()), ())

    def test_denial_logger_finish_collects_and_formats_output(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs DenialLogger finish after child wait.
        enabled = build_debug_sandbox_denial_logger_plan(
            log_denials=True,
            platform="darwin",
        )
        disabled = build_debug_sandbox_denial_logger_plan(
            log_denials=True,
            platform="linux",
        )
        calls = 0

        def collector() -> tuple[tuple[str, str], ...]:
            nonlocal calls
            calls += 1
            return (("process", "file-read-data"), ("network", "outbound"))

        collected = finish_debug_sandbox_denial_logger_plan(
            enabled,
            collector=collector,
        )
        skipped = finish_debug_sandbox_denial_logger_plan(
            disabled,
            collector=collector,
        )

        self.assertTrue(collected.enabled)
        self.assertEqual(
            collected.denials,
            (("process", "file-read-data"), ("network", "outbound")),
        )
        self.assertEqual(
            collected.output_lines,
            (
                "",
                "=== Sandbox denials ===",
                "(process) file-read-data",
                "(network) outbound",
            ),
        )
        self.assertFalse(skipped.enabled)
        self.assertEqual(skipped.denials, ())
        self.assertEqual(skipped.output_lines, ())
        self.assertEqual(calls, 1)

    def test_execution_with_denial_logging_finishes_after_child_wait(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs child wait precedes DenialLogger finish.
        class Completed:
            returncode = 5

        events: list[str] = []

        def fake_runner(argv: list[str], **kwargs: object) -> Completed:
            events.append("run_child")
            return Completed()

        def collector() -> tuple[tuple[str, str], ...]:
            events.append("finish_denials")
            return (("process", "file-read-data"),)

        plan = build_debug_sandbox_execution_plan(
            ["echo", "hello"],
            cwd="/workspace",
            sandbox_type="seatbelt",
            backend_args=["-p", "(version 1)", "echo", "hello"],
            base_env={"PATH": "/bin"},
            platform="darwin",
        )
        denial_logger = build_debug_sandbox_denial_logger_plan(
            log_denials=True,
            platform="darwin",
        )

        result = run_debug_sandbox_execution_plan_with_denial_logging(
            plan,
            denial_logger,
            runner=fake_runner,
            collector=collector,
            platform="darwin",
        )

        self.assertEqual(events, ["run_child", "finish_denials"])
        self.assertEqual(result.child_exit.exit_status.process_exit_code, 5)
        self.assertEqual(result.denial_log.denials, (("process", "file-read-data"),))
        self.assertEqual(
            result.denial_log.output_lines,
            ("", "=== Sandbox denials ===", "(process) file-read-data"),
        )

    def test_run_flow_plan_matches_rust_shared_sandbox_order(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_sandbox.
        landlock = build_debug_sandbox_run_flow_plan(
            sandbox_type="landlock",
            platform="linux",
        )
        windows = build_debug_sandbox_run_flow_plan(
            sandbox_type="windows",
            platform="win32",
        )
        windows_unavailable = build_debug_sandbox_run_flow_plan(
            sandbox_type="windows",
            platform="linux",
        )

        self.assertEqual(landlock.phases[0], "parse_config_overrides")
        self.assertLess(
            landlock.phases.index("maybe_create_denial_logger"),
            landlock.phases.index("maybe_start_network_proxy"),
        )
        self.assertLess(
            landlock.phases.index("spawn_debug_sandbox_child"),
            landlock.phases.index("maybe_attach_denial_logger"),
        )
        self.assertLess(
            landlock.phases.index("wait_child"),
            landlock.phases.index("handle_exit_status"),
        )
        self.assertFalse(landlock.strict_config)
        self.assertEqual(landlock.cwd_source, "config.cwd")
        self.assertEqual(landlock.permission_profile_cwd_source, "cwd")
        self.assertTrue(landlock.denial_logger_before_network_proxy)
        self.assertTrue(landlock.child_wait_before_exit_status)
        self.assertTrue(landlock.handles_exit_status)
        self.assertEqual(windows.phases[-1], "run_windows_session_and_exit")
        self.assertTrue(windows.windows_special_case_before_denial_logger)
        self.assertFalse(windows.handles_exit_status)
        self.assertEqual(windows_unavailable.phases[-1], "windows_unavailable_error")

    def test_run_flow_execution_uses_rust_phase_order_and_terminal_phase(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_sandbox phase execution.
        plan = build_debug_sandbox_run_flow_plan(
            sandbox_type="landlock",
            platform="linux",
        )
        events = []

        handlers = {
            phase: (lambda phase=phase: events.append(phase) or f"{phase}:ok")
            for phase in plan.phases
            if phase != "maybe_finish_denial_logger"
        }
        result = execute_debug_sandbox_run_flow_plan(plan, handlers)

        self.assertEqual(result.executed_phases, tuple(phase for phase in plan.phases if phase != "maybe_finish_denial_logger"))
        self.assertEqual(result.missing_handlers, ("maybe_finish_denial_logger",))
        self.assertEqual(result.terminal_phase, "handle_exit_status")
        self.assertEqual(events[-1], "handle_exit_status")
        self.assertEqual(result.outputs[0], ("parse_config_overrides", "parse_config_overrides:ok"))
        self.assertEqual(result.outputs[-1], ("handle_exit_status", "handle_exit_status:ok"))

        with self.assertRaisesRegex(KeyError, "maybe_finish_denial_logger"):
            execute_debug_sandbox_run_flow_plan(plan, handlers, require_handlers=True)

    def test_run_flow_handler_wiring_selects_planned_phase_handlers(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_sandbox phase handler wiring.
        plan = build_debug_sandbox_run_flow_plan(
            sandbox_type="windows",
            platform="win32",
        )
        events = []
        all_handlers = {
            "parse_config_overrides": lambda: events.append("parse") or "parsed",
            "load_debug_sandbox_config": lambda: events.append("load") or "loaded",
            "clone_config_cwd": lambda: events.append("cwd") or "cwd",
            "set_permission_profile_cwd_from_cwd": lambda: events.append("profile-cwd") or "profile-cwd",
            "create_shell_env": lambda: events.append("env") or "env",
            "run_windows_session_and_exit": lambda: events.append("windows") or 9,
            "handle_exit_status": lambda: events.append("unexpected") or 0,
        }

        wiring = build_debug_sandbox_run_flow_handler_wiring(plan, all_handlers)
        result = execute_debug_sandbox_run_flow_plan(plan, wiring.handlers)

        self.assertEqual(wiring.sandbox_type, "windows")
        self.assertEqual(wiring.missing_phases, ())
        self.assertEqual(wiring.terminal_phases, ("run_windows_session_and_exit",))
        self.assertNotIn("handle_exit_status", wiring.wired_phases)
        self.assertEqual(result.terminal_phase, "run_windows_session_and_exit")
        self.assertEqual(events, ["parse", "load", "cwd", "profile-cwd", "env", "windows"])
        self.assertEqual(result.outputs[-1], ("run_windows_session_and_exit", 9))

    def test_default_run_flow_handlers_wire_existing_helper_results(self) -> None:
        # Rust parity: codex-cli/src/debug_sandbox.rs run_command_under_sandbox phase handler hookups.
        plan = build_debug_sandbox_run_flow_plan(
            sandbox_type="landlock",
            platform="linux",
        )
        config_plan = build_debug_sandbox_config_load_plan(
            [("model", "gpt-5")],
            cwd="/workspace",
        )
        config_result = run_debug_sandbox_config_load_plan(
            config_plan,
            lambda _plan, _overrides, sandbox_mode: {
                "sandbox_mode": sandbox_mode or "ambient"
            },
        )
        execution_plan = build_debug_sandbox_execution_plan(
            ["echo", "hello"],
            cwd="/workspace",
            sandbox_type="landlock",
            codex_linux_sandbox_exe="/opt/codex-linux-sandbox",
            backend_args=["--sandbox", "echo", "hello"],
            platform="linux",
        )
        network_plan = build_debug_sandbox_network_plan(
            network_spec_present=True,
            managed_network_requirements_enabled=True,
            proxy_env={"HTTPS_PROXY": "http://127.0.0.1:7777"},
        )
        network_result = start_debug_sandbox_network_proxy_plan(network_plan)
        backend_result = build_debug_sandbox_landlock_backend_args_from_plan(
            build_debug_sandbox_backend_args_plan(
                ["echo", "hello"],
                sandbox_type="landlock",
                cwd="/workspace",
                permission_profile_cwd="/workspace",
            ),
            permission_profile_json="{}",
        )
        child_exit = run_debug_sandbox_child_spawn_plan_with_exit_status(
            debug_sandbox_child_spawn_plan_from_execution_plan(execution_plan),
            runner=lambda *args, **kwargs: type("Completed", (), {"returncode": 12})(),
            platform="linux",
        )
        denial_logger = build_debug_sandbox_denial_logger_plan(
            log_denials=False,
            platform="linux",
        )
        denial_log = finish_debug_sandbox_denial_logger_plan(denial_logger)

        wiring = build_debug_sandbox_default_run_flow_handlers(
            plan,
            config_plan=config_plan,
            config_result=config_result,
            execution_plan=execution_plan,
            network_plan=network_plan,
            network_proxy_result=network_result,
            backend_args_result=backend_result,
            child_exit=child_exit,
            denial_logger=denial_logger,
            denial_log=denial_log,
            exit_status=child_exit.exit_status,
        )
        result = execute_debug_sandbox_run_flow_plan(plan, wiring.handlers, require_handlers=True)

        self.assertEqual(wiring.missing_phases, ())
        self.assertEqual(result.terminal_phase, "handle_exit_status")
        self.assertEqual(result.outputs[0], ("parse_config_overrides", (("model", "gpt-5"),)))
        self.assertEqual(result.outputs[1], ("load_debug_sandbox_config", config_result))
        self.assertEqual(result.outputs[4][0], "create_shell_env")
        self.assertEqual(result.outputs[4][1]["PYCODEX_SANDBOX_MODE"], "workspace-write")
        self.assertEqual(result.outputs[6], ("compute_managed_network_requirements", True))
        self.assertEqual(result.outputs[8], ("build_backend_args", backend_result))
        self.assertEqual(result.outputs[-1], ("handle_exit_status", 12))

    def test_exit_status_plan_matches_rust_handle_exit_status(self) -> None:
        # Rust parity: codex-cli/src/exit_status.rs handle_exit_status as used by debug_sandbox.rs.
        explicit = build_debug_sandbox_exit_status_plan(
            exit_code=7,
            signal=9,
            platform="linux",
        )
        signaled = build_debug_sandbox_exit_status_plan(
            exit_code=None,
            signal=9,
            platform="linux",
        )
        unix_fallback = build_debug_sandbox_exit_status_plan(
            platform="linux",
        )
        windows_fallback = build_debug_sandbox_exit_status_plan(
            signal=9,
            platform="win32",
        )

        self.assertEqual(explicit.process_exit_code, 7)
        self.assertFalse(explicit.used_signal_fallback)
        self.assertFalse(explicit.used_generic_fallback)
        self.assertEqual(signaled.process_exit_code, 137)
        self.assertTrue(signaled.used_signal_fallback)
        self.assertFalse(signaled.used_generic_fallback)
        self.assertEqual(unix_fallback.process_exit_code, 1)
        self.assertTrue(unix_fallback.used_generic_fallback)
        self.assertEqual(windows_fallback.process_exit_code, 1)
        self.assertFalse(windows_fallback.used_signal_fallback)
        self.assertTrue(windows_fallback.used_generic_fallback)

    def test_raise_exit_status_matches_rust_process_exit(self) -> None:
        # Rust parity: codex-cli/src/exit_status.rs handle_exit_status exits with the planned code.
        explicit = build_debug_sandbox_exit_status_plan(
            exit_code=7,
            platform="linux",
        )
        signaled = build_debug_sandbox_exit_status_plan(
            signal=9,
            platform="linux",
        )

        with self.assertRaises(SystemExit) as explicit_exit:
            raise_debug_sandbox_exit_status(explicit)
        with self.assertRaises(SystemExit) as signaled_exit:
            raise_debug_sandbox_exit_status(signaled)

        self.assertEqual(explicit_exit.exception.code, 7)
        self.assertEqual(signaled_exit.exception.code, 137)


if __name__ == "__main__":
    unittest.main()
