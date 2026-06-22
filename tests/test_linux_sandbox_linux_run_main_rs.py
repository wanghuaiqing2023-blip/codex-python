import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pycodex.linux_sandbox import CODEX_LINUX_SANDBOX_ARG0
from pycodex.linux_sandbox import bwrap
from pycodex.linux_sandbox import linux_run_main as subject
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    PermissionProfile,
)


def profile_arg(profile: PermissionProfile) -> str:
    return json.dumps(profile.to_mapping(), separators=(",", ":"))


class LinuxRunMainRsTests(unittest.TestCase):
    # Rust source: codex/codex-rs/linux-sandbox/src/linux_run_main.rs
    # Tests: codex/codex-rs/linux-sandbox/src/linux_run_main_tests.rs

    def test_parse_args_accepts_hidden_runtime_flags_and_trailing_command(self):
        profile = PermissionProfile.read_only()
        command = subject.parse_args(
            [
                "--sandbox-policy-cwd",
                "/repo",
                "--command-cwd",
                "/repo/link",
                "--permission-profile",
                profile_arg(profile),
                "--use-legacy-landlock",
                "--allow-network-for-proxy",
                "--no-proc",
                "--",
                "bash",
                "-lc",
                "echo ok",
            ]
        )

        self.assertEqual(Path("/repo"), command.sandbox_policy_cwd)
        self.assertEqual(Path("/repo/link"), command.command_cwd)
        self.assertEqual(profile, command.permission_profile)
        self.assertTrue(command.use_legacy_landlock)
        self.assertTrue(command.allow_network_for_proxy)
        self.assertTrue(command.no_proc)
        self.assertEqual(("bash", "-lc", "echo ok"), command.command)

    def test_missing_command_is_rejected_after_parse(self):
        with self.assertRaisesRegex(ValueError, "No command specified"):
            subject.plan_linux_run_main(
                [
                    "--sandbox-policy-cwd",
                    "/repo",
                    "--permission-profile",
                    profile_arg(PermissionProfile.read_only()),
                    "--",
                ]
            )

    def test_missing_permission_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing permission profile configuration"):
            subject.plan_linux_run_main(["--sandbox-policy-cwd", "/repo", "--", "true"])

    def test_invalid_permission_profile_json_has_rust_error_prefix(self):
        with self.assertRaisesRegex(ValueError, "invalid permission profile JSON"):
            subject.parse_permission_profile("{not-json")

    def test_inner_stage_and_legacy_landlock_are_incompatible(self):
        with self.assertRaisesRegex(ValueError, "incompatible"):
            subject.ensure_inner_stage_mode_is_valid(True, True)

    def test_detects_proc_mount_failures(self):
        self.assertTrue(
            subject.is_proc_mount_failure("bwrap: Can't mount proc on /newroot/proc: Invalid argument")
        )
        self.assertTrue(
            subject.is_proc_mount_failure("bwrap: Can't mount proc on /newroot/proc: Operation not permitted")
        )
        self.assertTrue(
            subject.is_proc_mount_failure("bwrap: Can't mount proc on /newroot/proc: Permission denied")
        )
        self.assertFalse(
            subject.is_proc_mount_failure("bwrap: Can't bind mount /dev/null: Operation not permitted")
        )

    def test_proxy_only_network_mode_takes_precedence_over_full_network(self):
        self.assertIs(
            subject.bwrap_network_mode(NetworkSandboxPolicy.ENABLED, True),
            bwrap.BwrapNetworkMode.PROXY_ONLY,
        )
        self.assertIs(
            subject.bwrap_network_mode(NetworkSandboxPolicy.ENABLED, False),
            bwrap.BwrapNetworkMode.FULL_ACCESS,
        )
        self.assertIs(
            subject.bwrap_network_mode(NetworkSandboxPolicy.RESTRICTED, False),
            bwrap.BwrapNetworkMode.ISOLATED,
        )

    def test_apply_inner_command_argv0_inserts_before_command_separator(self):
        argv = ["bwrap", "--ro-bind", "/", "/", "--", "/bin/true"]
        subject.apply_inner_command_argv0_for_launcher(
            argv,
            supports_argv0=True,
            argv0_fallback_command="/tmp/fallback/codex-linux-sandbox",
        )

        self.assertEqual(
            ["bwrap", "--ro-bind", "/", "/", "--argv0", CODEX_LINUX_SANDBOX_ARG0, "--", "/bin/true"],
            argv,
        )

    def test_apply_inner_command_argv0_rewrites_only_helper_command(self):
        nested_current_exe = "/tmp/current-exe"
        argv = [
            "bwrap",
            "--",
            "/tmp/helper-symlink",
            "--sandbox-policy-cwd",
            "/tmp/cwd",
            "--",
            nested_current_exe,
            "--codex-run-as-apply-patch",
            "patch",
        ]

        subject.apply_inner_command_argv0_for_launcher(
            argv,
            supports_argv0=False,
            argv0_fallback_command="/tmp/argv0-fallback-helper",
        )

        self.assertEqual(
            [
                "bwrap",
                "--",
                "/tmp/argv0-fallback-helper",
                "--sandbox-policy-cwd",
                "/tmp/cwd",
                "--",
                nested_current_exe,
                "--codex-run-as-apply-patch",
                "patch",
            ],
            argv,
        )

    def test_build_inner_seccomp_command_serializes_permission_profile(self):
        profile = PermissionProfile.read_only()
        inner = subject.build_inner_seccomp_command(
            sandbox_policy_cwd="/repo",
            command_cwd="/repo/link",
            permission_profile=profile,
            allow_network_for_proxy=True,
            proxy_route_spec='{"routes":[]}',
            command=("python", "-V"),
            current_exe="/opt/codex/codex-linux-sandbox",
        )

        self.assertEqual("/opt/codex/codex-linux-sandbox", inner[0])
        self.assertIn("--apply-seccomp-then-exec", inner)
        self.assertIn("--allow-network-for-proxy", inner)
        self.assertIn("--proxy-route-spec", inner)
        separator = inner.index("--")
        self.assertEqual(("python", "-V"), inner[separator + 1 :])
        profile_json = inner[inner.index("--permission-profile") + 1]
        self.assertEqual(profile, PermissionProfile.from_mapping(json.loads(profile_json)))

    def test_legacy_landlock_rejects_direct_runtime_enforcement_policy(self):
        with TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            docs = cwd / "docs"
            docs.mkdir()
            policy = FileSystemSandboxPolicy.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.WRITE,
                    ),
                    FileSystemSandboxEntry(FileSystemPath.explicit_path(docs), FileSystemAccessMode.READ),
                )
            )
            profile = PermissionProfile.from_runtime_permissions(policy, NetworkSandboxPolicy.RESTRICTED)

            with self.assertRaisesRegex(ValueError, "direct runtime enforcement"):
                subject.plan_linux_run_main(
                    [
                        "--sandbox-policy-cwd",
                        str(cwd),
                        "--permission-profile",
                        profile_arg(profile),
                        "--use-legacy-landlock",
                        "--",
                        "true",
                    ]
                )

    def test_bwrap_outer_plan_builds_inner_stage_and_inserts_argv0(self):
        plan = subject.plan_linux_run_main(
            [
                "--sandbox-policy-cwd",
                "/repo",
                "--command-cwd",
                "/repo/link",
                "--permission-profile",
                profile_arg(PermissionProfile.read_only()),
                "--no-proc",
                "--",
                "true",
            ],
            current_exe_resolver=lambda: "/opt/codex/codex-linux-sandbox",
            bwrap_supports_argv0=True,
        )

        self.assertIs(subject.LinuxRunStage.BWRAP_OUTER, plan.stage)
        self.assertIsNotNone(plan.bwrap_args)
        self.assertIn("--apply-seccomp-then-exec", plan.inner_command)
        self.assertIn("--argv0", plan.bwrap_args.args)
        argv0_index = plan.bwrap_args.args.index("--argv0")
        self.assertEqual(CODEX_LINUX_SANDBOX_ARG0, plan.bwrap_args.args[argv0_index + 1])

    def test_bwrap_outer_plan_threads_managed_proxy_route_spec_into_inner_stage(self):
        # Rust integration source:
        # linux-sandbox/tests/suite/managed_proxy.rs
        # managed_proxy_mode_routes_through_bridge_and_blocks_direct_egress.
        proxy_spec = '{"routes":[{"env_key":"HTTP_PROXY","uds_path":"/tmp/proxy-route-0.sock"}]}'
        plan = subject.plan_linux_run_main(
            [
                "--sandbox-policy-cwd",
                "/repo",
                "--permission-profile",
                profile_arg(PermissionProfile.disabled()),
                "--allow-network-for-proxy",
                "--",
                "true",
            ],
            current_exe_resolver=lambda: "/opt/codex/codex-linux-sandbox",
            proxy_route_preparer=lambda: proxy_spec,
            bwrap_supports_argv0=True,
        )

        self.assertIs(subject.LinuxRunStage.BWRAP_OUTER, plan.stage)
        self.assertEqual(proxy_spec, plan.proxy_route_spec)
        self.assertIn("--allow-network-for-proxy", plan.inner_command)
        self.assertIn("--proxy-route-spec", plan.inner_command)
        self.assertEqual(proxy_spec, plan.inner_command[plan.inner_command.index("--proxy-route-spec") + 1])
        self.assertIsNotNone(plan.bwrap_args)
        self.assertIn("--unshare-net", plan.bwrap_args.args)

    def test_run_main_delegates_bwrap_stage_to_injected_runner(self):
        seen = {}

        def runner(args: bwrap.BwrapArgs) -> str:
            seen["args"] = args
            return "ran-bwrap"

        result = subject.run_main(
            [
                "--sandbox-policy-cwd",
                "/repo",
                "--permission-profile",
                profile_arg(PermissionProfile.read_only()),
                "--",
                "true",
            ],
            bwrap_runner=runner,
        )

        self.assertEqual("ran-bwrap", result)
        self.assertIsInstance(seen["args"], bwrap.BwrapArgs)

    def test_run_main_delegates_full_disk_stage_to_injected_exec(self):
        seen = {}

        def exec_runner(command: tuple[str, ...]) -> str:
            seen["command"] = command
            return "ran-exec"

        result = subject.run_main(
            [
                "--sandbox-policy-cwd",
                "/repo",
                "--permission-profile",
                profile_arg(PermissionProfile.disabled()),
                "--",
                "true",
            ],
            exec_runner=exec_runner,
        )

        self.assertEqual("ran-exec", result)
        self.assertEqual(("true",), seen["command"])

    def test_managed_proxy_mode_fails_closed_without_proxy_env(self):
        # Rust integration source:
        # linux-sandbox/tests/suite/managed_proxy.rs
        # managed_proxy_mode_fails_closed_without_proxy_env.
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "managed proxy mode requires proxy environment variables"):
                subject.plan_linux_run_main(
                    [
                        "--sandbox-policy-cwd",
                        "/repo",
                        "--permission-profile",
                        profile_arg(PermissionProfile.disabled()),
                        "--allow-network-for-proxy",
                        "--",
                        "true",
                    ]
                )

    def test_managed_proxy_mode_fails_closed_without_loopback_endpoint(self):
        # Rust source: linux-sandbox/src/proxy_routing.rs
        # prepare_host_proxy_route_spec() parseable loopback preflight.
        with patch.dict(os.environ, {"HTTP_PROXY": "http://example.com:3128"}, clear=True):
            with self.assertRaisesRegex(ValueError, "managed proxy mode requires parseable loopback proxy endpoints"):
                subject.plan_linux_run_main(
                    [
                        "--sandbox-policy-cwd",
                        "/repo",
                        "--permission-profile",
                        profile_arg(PermissionProfile.disabled()),
                        "--allow-network-for-proxy",
                        "--",
                        "true",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
