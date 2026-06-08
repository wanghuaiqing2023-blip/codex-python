import unittest
from pathlib import Path
from unittest.mock import patch

from pycodex.core import (
    get_platform_sandbox,
    permission_profile_policy_tag,
    permission_profile_sandbox_tag,
    should_require_platform_sandbox,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    ManagedFileSystemPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
    WindowsSandboxLevel,
)


class CoreSandboxTagsTests(unittest.TestCase):
    def expected_platform_tag(self, windows_sandbox_enabled: bool = False) -> str:
        sandbox = get_platform_sandbox(windows_sandbox_enabled)
        return "none" if sandbox is None else sandbox.as_metric_tag()

    def test_permission_profile_sandbox_tag_distinguishes_disabled_and_external(self) -> None:
        self.assertEqual(
            permission_profile_sandbox_tag(
                PermissionProfile.disabled(),
                WindowsSandboxLevel.DISABLED,
                enforce_managed_network=False,
            ),
            "none",
        )
        self.assertEqual(
            permission_profile_sandbox_tag(
                PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED),
                WindowsSandboxLevel.DISABLED,
                enforce_managed_network=False,
            ),
            "external",
        )

    def test_permission_profile_sandbox_tag_uses_platform_for_read_only(self) -> None:
        self.assertEqual(
            permission_profile_sandbox_tag(
                PermissionProfile.read_only(),
                WindowsSandboxLevel.DISABLED,
                enforce_managed_network=False,
            ),
            self.expected_platform_tag(False),
        )

    def test_unrestricted_managed_profile_with_enabled_network_is_untagged(self) -> None:
        profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.unrestricted(),
            NetworkSandboxPolicy.ENABLED,
        )

        self.assertEqual(
            permission_profile_sandbox_tag(
                profile,
                WindowsSandboxLevel.DISABLED,
                enforce_managed_network=False,
            ),
            "none",
        )

    def test_root_write_managed_profile_with_enabled_network_is_untagged(self) -> None:
        profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.WRITE,
                    ),
                )
            ),
            NetworkSandboxPolicy.ENABLED,
        )

        self.assertEqual(
            permission_profile_sandbox_tag(
                profile,
                WindowsSandboxLevel.DISABLED,
                enforce_managed_network=False,
            ),
            "none",
        )

    def test_root_write_with_deny_carveout_still_uses_platform_sandbox(self) -> None:
        # Rust source: codex-rs/sandboxing/src/policy_transforms.rs
        # Rust test: root_write_policy_with_carveouts_still_uses_platform_sandbox.
        blocked = Path.cwd() / "blocked"
        profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.WRITE,
                    ),
                    FileSystemSandboxEntry(
                        FileSystemPath.explicit_path(blocked),
                        FileSystemAccessMode.DENY,
                    ),
                )
            ),
            NetworkSandboxPolicy.ENABLED,
        )

        self.assertEqual(
            permission_profile_sandbox_tag(
                profile,
                WindowsSandboxLevel.DISABLED,
                enforce_managed_network=False,
            ),
            self.expected_platform_tag(False),
        )

    def test_managed_network_enforcement_tags_unrestricted_profiles_as_sandboxed(self) -> None:
        profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.unrestricted(),
            NetworkSandboxPolicy.ENABLED,
        )

        self.assertEqual(
            permission_profile_sandbox_tag(
                profile,
                WindowsSandboxLevel.DISABLED,
                enforce_managed_network=True,
            ),
            self.expected_platform_tag(False),
        )

    def test_windows_elevated_sandbox_tag_has_priority_on_windows(self) -> None:
        # Rust source: codex-rs/core/src/sandbox_tags.rs checks the Windows
        # Elevated level before falling back to get_platform_sandbox.
        with patch("pycodex.core.sandbox_tags.sys.platform", "win32"):
            self.assertEqual(
                permission_profile_sandbox_tag(
                    PermissionProfile.read_only(),
                    WindowsSandboxLevel.ELEVATED,
                    enforce_managed_network=False,
                ),
                "windows_elevated",
            )
            self.assertEqual(
                permission_profile_sandbox_tag(
                    PermissionProfile.read_only(),
                    WindowsSandboxLevel.RESTRICTED_TOKEN,
                    enforce_managed_network=False,
                ),
                "windows_sandbox",
            )
            self.assertEqual(
                permission_profile_sandbox_tag(
                    PermissionProfile.read_only(),
                    WindowsSandboxLevel.DISABLED,
                    enforce_managed_network=False,
                ),
                "none",
            )

    def test_should_require_platform_sandbox_matches_network_and_filesystem_rules(self) -> None:
        self.assertTrue(
            should_require_platform_sandbox(
                FileSystemSandboxPolicy.unrestricted(),
                NetworkSandboxPolicy.ENABLED,
                has_managed_network_requirements=True,
            )
        )
        self.assertTrue(
            should_require_platform_sandbox(
                FileSystemSandboxPolicy.default(),
                NetworkSandboxPolicy.RESTRICTED,
                has_managed_network_requirements=False,
            )
        )
        self.assertFalse(
            should_require_platform_sandbox(
                FileSystemSandboxPolicy.external_sandbox(),
                NetworkSandboxPolicy.RESTRICTED,
                has_managed_network_requirements=False,
            )
        )
        self.assertFalse(
            should_require_platform_sandbox(
                FileSystemSandboxPolicy.unrestricted(),
                NetworkSandboxPolicy.ENABLED,
                has_managed_network_requirements=False,
            )
        )

    def test_permission_profile_policy_tag_reports_closest_legacy_mode(self) -> None:
        cwd = Path.cwd()
        writable_root = cwd / "work"
        profile = PermissionProfile.from_runtime_permissions(
            FileSystemSandboxPolicy(
                kind=FileSystemSandboxKind.RESTRICTED,
                entries=(
                    FileSystemSandboxEntry(
                        FileSystemPath.explicit_path(writable_root),
                        FileSystemAccessMode.WRITE,
                    ),
                ),
            ),
            NetworkSandboxPolicy.RESTRICTED,
        )

        self.assertEqual(
            permission_profile_policy_tag(PermissionProfile.disabled(), cwd),
            "danger-full-access",
        )
        self.assertEqual(
            permission_profile_policy_tag(
                PermissionProfile.external(NetworkSandboxPolicy.ENABLED),
                cwd,
            ),
            "external-sandbox",
        )
        self.assertEqual(
            permission_profile_policy_tag(PermissionProfile.read_only(), cwd),
            "read-only",
        )
        self.assertEqual(
            permission_profile_policy_tag(profile, cwd),
            "workspace-write",
        )

    def test_rejects_non_rust_input_shapes(self) -> None:
        with self.assertRaises(TypeError):
            get_platform_sandbox(1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            should_require_platform_sandbox(
                "restricted",  # type: ignore[arg-type]
                NetworkSandboxPolicy.RESTRICTED,
                False,
            )
        with self.assertRaises(TypeError):
            should_require_platform_sandbox(
                FileSystemSandboxPolicy.default(),
                "restricted",  # type: ignore[arg-type]
                False,
            )
        with self.assertRaises(TypeError):
            should_require_platform_sandbox(
                FileSystemSandboxPolicy.default(),
                NetworkSandboxPolicy.RESTRICTED,
                1,  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            permission_profile_sandbox_tag(
                object(),  # type: ignore[arg-type]
                WindowsSandboxLevel.DISABLED,
                False,
            )
        with self.assertRaises(TypeError):
            permission_profile_sandbox_tag(
                PermissionProfile.read_only(),
                "disabled",  # type: ignore[arg-type]
                False,
            )
        with self.assertRaises(TypeError):
            permission_profile_sandbox_tag(
                PermissionProfile.read_only(),
                WindowsSandboxLevel.DISABLED,
                1,  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            permission_profile_policy_tag(object(), Path.cwd())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            permission_profile_policy_tag(PermissionProfile.read_only(), 1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
