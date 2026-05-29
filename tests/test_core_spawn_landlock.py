import json
import unittest
from pathlib import Path

from pycodex.core.landlock import (
    CODEX_LINUX_SANDBOX_ARG0,
    allow_network_for_proxy,
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

    def test_allow_network_for_proxy_mirrors_boolean_input(self) -> None:
        self.assertTrue(allow_network_for_proxy(True))
        self.assertFalse(allow_network_for_proxy(False))


if __name__ == "__main__":
    unittest.main()
