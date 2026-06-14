from pathlib import Path

from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    ManagedFileSystemPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
)
from pycodex.tui.permission_compat import legacy_compatible_permission_profile


def test_legacy_compatible_permission_profile_preserves_bridgeable_profile():
    # Rust: codex-tui, permission_compat.rs, early return when legacy projection succeeds.
    profile = PermissionProfile.workspace_write((Path("/workspace/project"),))

    assert legacy_compatible_permission_profile(profile, Path("/workspace/project")) == profile


def test_compatibility_profile_preserves_unbridgeable_write_roots():
    # Rust: codex-tui, permission_compat.rs, compatibility_profile_preserves_unbridgeable_write_roots.
    cwd = Path("/workspace/project")
    extra_root = Path("/workspace/extra")
    permission_profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.root()),
                    FileSystemAccessMode.READ,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(extra_root),
                    FileSystemAccessMode.WRITE,
                ),
            )
        ),
        NetworkSandboxPolicy.RESTRICTED,
    )

    compatibility_profile = legacy_compatible_permission_profile(permission_profile, cwd)
    policy = compatibility_profile.to_legacy_sandbox_policy(cwd)
    roots = [root.root for root in policy.get_writable_roots_with_cwd(cwd)]

    assert roots == [extra_root, cwd]


def test_legacy_compatible_permission_profile_preserves_network_policy_when_rebuilt():
    cwd = Path("/workspace/project")
    extra_root = Path("/workspace/extra")
    permission_profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.root()),
                    FileSystemAccessMode.READ,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(extra_root),
                    FileSystemAccessMode.WRITE,
                ),
            )
        ),
        NetworkSandboxPolicy.ENABLED,
    )

    compatibility_profile = legacy_compatible_permission_profile(permission_profile, cwd)

    assert compatibility_profile.network_sandbox_policy() is NetworkSandboxPolicy.ENABLED


def test_legacy_compatible_permission_profile_sets_tmpdir_exclusion_from_write_access(monkeypatch):
    # Rust: permission_compat.rs fallback rebuild computes exclude_tmpdir_env_var from TMPDIR writability.
    cwd = Path("/workspace/project")
    extra_root = Path("/workspace/extra")
    tmp_root = Path("/workspace/tmp")
    monkeypatch.setenv("TMPDIR", str(tmp_root))

    writable_tmp_profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.root()),
                    FileSystemAccessMode.READ,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(extra_root),
                    FileSystemAccessMode.WRITE,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(tmp_root),
                    FileSystemAccessMode.WRITE,
                ),
            )
        ),
        NetworkSandboxPolicy.RESTRICTED,
    )
    writable_tmp_policy = legacy_compatible_permission_profile(
        writable_tmp_profile,
        cwd,
    ).to_legacy_sandbox_policy(cwd)
    assert writable_tmp_policy.exclude_tmpdir_env_var is False

    blocked_tmp_profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.root()),
                    FileSystemAccessMode.READ,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(extra_root),
                    FileSystemAccessMode.WRITE,
                ),
            )
        ),
        NetworkSandboxPolicy.RESTRICTED,
    )
    blocked_tmp_policy = legacy_compatible_permission_profile(
        blocked_tmp_profile,
        cwd,
    ).to_legacy_sandbox_policy(cwd)
    assert blocked_tmp_policy.exclude_tmpdir_env_var is True


def test_legacy_compatible_permission_profile_sets_slash_tmp_exclusion_from_write_access(monkeypatch):
    # Rust: permission_compat.rs fallback rebuild checks absolute existing /tmp writability separately.
    cwd = Path("/workspace/project")
    extra_root = Path("/workspace/extra")
    slash_tmp = Path("/tmp")
    monkeypatch.setenv("TMPDIR", "")
    monkeypatch.setattr(Path, "is_dir", lambda self: self == slash_tmp)

    writable_slash_tmp_profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.root()),
                    FileSystemAccessMode.READ,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(extra_root),
                    FileSystemAccessMode.WRITE,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(slash_tmp),
                    FileSystemAccessMode.WRITE,
                ),
            )
        ),
        NetworkSandboxPolicy.RESTRICTED,
    )
    writable_slash_tmp_policy = legacy_compatible_permission_profile(
        writable_slash_tmp_profile,
        cwd,
    ).to_legacy_sandbox_policy(cwd)
    assert writable_slash_tmp_policy.exclude_slash_tmp is False

    blocked_slash_tmp_profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.root()),
                    FileSystemAccessMode.READ,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(extra_root),
                    FileSystemAccessMode.WRITE,
                ),
            )
        ),
        NetworkSandboxPolicy.RESTRICTED,
    )
    blocked_slash_tmp_policy = legacy_compatible_permission_profile(
        blocked_slash_tmp_profile,
        cwd,
    ).to_legacy_sandbox_policy(cwd)
    assert blocked_slash_tmp_policy.exclude_slash_tmp is True
