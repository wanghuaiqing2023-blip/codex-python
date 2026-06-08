import json
import unittest
from pathlib import Path

from pycodex.linux_sandbox import (
    CODEX_LINUX_SANDBOX_ARG0,
    allow_network_for_proxy,
    create_linux_sandbox_command_args,
    build_linux_sandbox_spawn_child_request,
    create_linux_sandbox_command_args_for_permission_profile,
    linux_sandbox_arg0,
)
from pycodex.core.spawn import (
    CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR,
    StdioPolicy,
    build_spawn_child_request,
)
from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile


class SpawnAndLandlockTests(unittest.TestCase):
    def test_spawn_request_applies_network_env_before_policy_marker(self) -> None:
        # Rust source: codex-rs/core/src/spawn.rs::spawn_child_async.
        class ManagedNetwork:
            def apply_to_env(self, env):
                env["MANAGED_NETWORK"] = "1"
                env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR] = "proxy"

        request = build_spawn_child_request(
            "/bin/echo",
            ["hello"],
            arg0=None,
            cwd="/tmp",
            network_sandbox_policy=NetworkSandboxPolicy.RESTRICTED,
            network=ManagedNetwork(),
            env={"A": "B"},
        )

        self.assertEqual(
            request.effective_env(),
            {
                "A": "B",
                "MANAGED_NETWORK": "1",
                CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR: "1",
            },
        )

    def test_spawn_request_effective_env_does_not_mutate_request_env(self) -> None:
        # Rust source: codex-rs/core/src/spawn.rs::spawn_child_async takes env by value before mutation.
        class ManagedNetwork:
            def apply_to_env(self, env):
                env["MANAGED_NETWORK"] = "1"

        request = build_spawn_child_request(
            "/bin/echo",
            ["hello"],
            arg0=None,
            cwd="/tmp",
            network_sandbox_policy=NetworkSandboxPolicy.ENABLED,
            network=ManagedNetwork(),
            env={"A": "B"},
        )

        self.assertEqual(request.effective_env(), {"A": "B", "MANAGED_NETWORK": "1"})
        self.assertEqual(request.env, {"A": "B"})

    def test_spawn_request_adds_network_disabled_env_for_restricted_policy(self) -> None:
        request = build_spawn_child_request(
            "/bin/echo",
            ["hello"],
            arg0=None,
            cwd="/tmp",
            network_sandbox_policy=NetworkSandboxPolicy.RESTRICTED,
            env={"A": "B"},
        )

        self.assertEqual(
            request.effective_env(),
            {"A": "B", CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR: "1"},
        )

    def test_spawn_request_preserves_env_for_enabled_network_policy(self) -> None:
        request = build_spawn_child_request(
            "/bin/echo",
            ["hello"],
            arg0=None,
            cwd="/tmp",
            network_sandbox_policy=NetworkSandboxPolicy.ENABLED,
            env={"A": "B"},
        )

        self.assertEqual(request.effective_env(), {"A": "B"})

    def test_create_linux_sandbox_command_args_for_permission_profile(self) -> None:
        # Rust test: codex-rs/sandboxing/src/landlock_tests.rs::permission_profile_flag_is_included.
        profile = PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED)

        args = create_linux_sandbox_command_args_for_permission_profile(
            ["bash", "-lc", "echo hi"],
            "/work",
            profile,
            "/sandbox",
            use_legacy_landlock=True,
            allow_network_for_proxy=True,
        )

        self.assertEqual(args[:6], ["--sandbox-policy-cwd", "/sandbox", "--command-cwd", "/work", "--permission-profile", json.dumps(profile.to_mapping(), separators=(",", ":"))])
        self.assertIn("--use-legacy-landlock", args)
        self.assertIn("--allow-network-for-proxy", args)
        self.assertEqual(args[-4:], ["--", "bash", "-lc", "echo hi"])

    def test_create_linux_sandbox_command_args_legacy_flag_matches_rust(self) -> None:
        # Rust test: codex-rs/sandboxing/src/landlock_tests.rs::legacy_landlock_flag_is_included_when_requested.
        default_bwrap = create_linux_sandbox_command_args(
            ["/bin/true"],
            "/tmp/link",
            "/tmp",
            use_legacy_landlock=False,
            allow_network_for_proxy=False,
        )
        legacy_landlock = create_linux_sandbox_command_args(
            ["/bin/true"],
            "/tmp/link",
            "/tmp",
            use_legacy_landlock=True,
            allow_network_for_proxy=False,
        )

        self.assertNotIn("--use-legacy-landlock", default_bwrap)
        self.assertIn("--use-legacy-landlock", legacy_landlock)
        self.assertEqual(default_bwrap, ["--sandbox-policy-cwd", "/tmp", "--command-cwd", "/tmp/link", "--", "/bin/true"])

    def test_create_linux_sandbox_command_args_proxy_flag_matches_rust(self) -> None:
        # Rust test: codex-rs/sandboxing/src/landlock_tests.rs::proxy_flag_is_included_when_requested.
        args = create_linux_sandbox_command_args(
            ["/bin/true"],
            "/tmp/link",
            "/tmp",
            use_legacy_landlock=True,
            allow_network_for_proxy=True,
        )

        self.assertIn("--allow-network-for-proxy", args)
        self.assertEqual(args[-2:], ["--", "/bin/true"])

    def test_linux_sandbox_arg0_matches_helper_basename_rule(self) -> None:
        self.assertEqual(linux_sandbox_arg0(Path("/opt/codex/codex-linux-sandbox")), "/opt/codex/codex-linux-sandbox")
        self.assertEqual(linux_sandbox_arg0(Path("/opt/codex/codex")), CODEX_LINUX_SANDBOX_ARG0)

    def test_build_linux_sandbox_spawn_child_request(self) -> None:
        request = build_linux_sandbox_spawn_child_request(
            "/opt/codex/codex",
            ["bash", "-lc", "echo hi"],
            "/work",
            PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED),
            "/sandbox",
            use_legacy_landlock=False,
            stdio_policy=StdioPolicy.INHERIT,
            env={"K": "V"},
        )

        self.assertEqual(request.program, Path("/opt/codex/codex"))
        self.assertEqual(request.arg0, CODEX_LINUX_SANDBOX_ARG0)
        self.assertEqual(request.cwd, Path("/work"))
        self.assertEqual(request.stdio_policy, StdioPolicy.INHERIT)
        self.assertIn("--permission-profile", request.args)
        self.assertEqual(request.effective_env()[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR], "1")

    def test_build_linux_sandbox_spawn_child_request_keeps_network_proxy(self) -> None:
        # Rust source: codex-rs/core/src/landlock.rs::spawn_command_under_linux_sandbox.
        class ManagedNetwork:
            def apply_to_env(self, env):
                env["MANAGED_NETWORK"] = "1"

        network = ManagedNetwork()
        request = build_linux_sandbox_spawn_child_request(
            "/opt/codex/codex",
            ["bash", "-lc", "echo hi"],
            "/work",
            PermissionProfile.external(NetworkSandboxPolicy.ENABLED),
            "/sandbox",
            use_legacy_landlock=False,
            stdio_policy=StdioPolicy.REDIRECT_FOR_SHELL_TOOL,
            env={"K": "V"},
            network=network,
        )

        self.assertIs(request.network, network)
        self.assertEqual(request.network_sandbox_policy, NetworkSandboxPolicy.ENABLED)
        self.assertEqual(request.effective_env(), {"K": "V", "MANAGED_NETWORK": "1"})

    def test_allow_network_for_proxy_mirrors_boolean_input(self) -> None:
        # Rust test: codex-rs/sandboxing/src/landlock_tests.rs::proxy_network_requires_managed_requirements.
        self.assertTrue(allow_network_for_proxy(True))
        self.assertFalse(allow_network_for_proxy(False))


if __name__ == "__main__":
    unittest.main()
