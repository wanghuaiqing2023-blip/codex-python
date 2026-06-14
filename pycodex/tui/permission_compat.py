"""Behavior port for Rust ``codex-tui::permission_compat``.

Upstream source: ``codex/codex-rs/tui/src/permission_compat.rs``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="permission_compat",
    source="codex/codex-rs/tui/src/permission_compat.rs",
)


def legacy_compatible_permission_profile(permission_profile: PermissionProfile, cwd: Path | str) -> PermissionProfile:
    """Project a canonical permission profile into a legacy-compatible shape.

    Rust keeps profiles that already bridge to the legacy sandbox policy.  For
    managed profiles that cannot bridge, it builds a workspace-write profile
    preserving extra writable roots, network policy, and tmp write exclusions.
    """

    cwd_path = Path(cwd)
    try:
        permission_profile.to_legacy_sandbox_policy(cwd_path)
        return permission_profile
    except Exception:
        pass

    file_system_policy = permission_profile.file_system_sandbox_policy()
    network_policy = permission_profile.network_sandbox_policy()
    cwd_abs = cwd_path if cwd_path.is_absolute() else None

    writable_roots = []
    for writable_root in file_system_policy.get_writable_roots_with_cwd(cwd_path):
        root = Path(getattr(writable_root, "root", writable_root))
        if cwd_abs is not None and root == cwd_abs:
            continue
        writable_roots.append(root)

    tmpdir = os.environ.get("TMPDIR")
    tmpdir_writable = bool(tmpdir) and file_system_policy.can_write_path_with_cwd(Path(tmpdir), cwd_path)

    slash_tmp = Path("/tmp")
    slash_tmp_writable = (
        slash_tmp.is_absolute()
        and slash_tmp.is_dir()
        and file_system_policy.can_write_path_with_cwd(slash_tmp, cwd_path)
    )

    return PermissionProfile.workspace_write(
        writable_roots,
        network=network_policy,
        exclude_tmpdir_env_var=not tmpdir_writable,
        exclude_slash_tmp=not slash_tmp_writable,
    )


def compatibility_profile_preserves_unbridgeable_write_roots() -> None:
    """Executable parity assertion for the Rust unit test of the same name."""

    from pycodex.protocol import (
        FileSystemAccessMode,
        FileSystemPath,
        FileSystemSandboxEntry,
        FileSystemSpecialPath,
        ManagedFileSystemPermissions,
    )

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


__all__ = [
    "RUST_MODULE",
    "compatibility_profile_preserves_unbridgeable_write_roots",
    "legacy_compatible_permission_profile",
]
