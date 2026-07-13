from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    ManagedFileSystemPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
)
from pycodex.windows_sandbox import (
    ResolvedWindowsSandboxPermissions,
    WindowsSandboxPermissionError,
    WindowsSandboxTokenMode,
    token_mode_for_permission_profile,
)


def test_read_only_profile_uses_read_only_capability(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::resolved_permissions::
    # token_mode_for_profile_without_writable_roots_uses_readonly_capability.
    assert (
        token_mode_for_permission_profile(PermissionProfile.read_only(), tmp_path, {})
        is WindowsSandboxTokenMode.READ_ONLY_CAPABILITY
    )


def test_workspace_profile_uses_write_capabilities_and_windows_temp_roots(
    tmp_path: Path,
) -> None:
    # Rust: codex-windows-sandbox::resolved_permissions::
    # permission_profile_workspace_write_uses_windows_temp_env_vars.
    workspace = tmp_path / "workspace"
    temp = tmp_path / "temp"
    workspace.mkdir()
    temp.mkdir()
    profile = PermissionProfile.workspace_write()
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        profile,
        workspace,
    )

    roots = {
        root.root.resolve()
        for root in permissions.writable_roots_for_cwd(
            workspace,
            {"TEMP": str(temp), "TMP": str(temp)},
        )
    }

    assert workspace.resolve() in roots
    assert temp.resolve() in roots
    assert (
        token_mode_for_permission_profile(profile, workspace, {"TEMP": str(temp)})
        is WindowsSandboxTokenMode.WRITABLE_ROOTS_CAPABILITY
    )


def test_project_root_remains_bound_to_permission_profile_cwd(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::resolved_permissions::
    # permission_profile_workspace_root_stays_bound_to_profile_cwd.
    workspace = tmp_path / "workspace"
    command_cwd = workspace / "subdir"
    command_cwd.mkdir(parents=True)
    profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                    FileSystemAccessMode.WRITE,
                ),
            )
        ),
        NetworkSandboxPolicy.RESTRICTED,
    )
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        profile,
        workspace,
    )

    roots = permissions.writable_roots_for_cwd(command_cwd, {})

    assert [root.root.resolve() for root in roots] == [workspace.resolve()]


@pytest.mark.parametrize(
    "profile",
    [
        PermissionProfile.disabled(),
        PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED),
    ],
)
def test_non_managed_profiles_are_rejected(profile: PermissionProfile) -> None:
    # Rust: codex-windows-sandbox::resolved_permissions::permission_profile_rejects_disabled_profiles.
    with pytest.raises(WindowsSandboxPermissionError, match="only managed permission profiles"):
        ResolvedWindowsSandboxPermissions.try_from_permission_profile(profile)


def test_unrestricted_managed_profile_is_rejected() -> None:
    # Rust: codex-windows-sandbox::resolved_permissions::
    # permission_profile_rejects_unrestricted_managed_filesystem.
    profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.unrestricted(),
        NetworkSandboxPolicy.RESTRICTED,
    )
    with pytest.raises(WindowsSandboxPermissionError, match="only restricted managed filesystem"):
        ResolvedWindowsSandboxPermissions.try_from_permission_profile(profile)


def test_full_disk_write_profile_has_no_windows_token_mode(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::resolved_permissions::token_mode_rejects_full_disk_write_entries.
    profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.root()),
                    FileSystemAccessMode.WRITE,
                ),
            )
        ),
        NetworkSandboxPolicy.RESTRICTED,
    )
    with pytest.raises(WindowsSandboxPermissionError, match="full-disk filesystem writes"):
        token_mode_for_permission_profile(profile, tmp_path, {})
