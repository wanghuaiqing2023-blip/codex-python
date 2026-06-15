"""Behavior port for Rust ``codex-tui::permission_compat``.

Upstream source: ``codex/codex-rs/tui/src/permission_compat.rs``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

from pycodex.protocol import FileSystemAccessMode, NetworkSandboxPolicy, PermissionProfile

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="permission_compat",
    source="codex/codex-rs/tui/src/permission_compat.rs",
    status="complete",
)


def legacy_compatible_permission_profile(permission_profile: PermissionProfile, cwd: Union[Path, str]) -> PermissionProfile:
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
    cwd_abs = cwd_path if _compat_is_absolute(cwd_path) else None

    writable_roots = _explicit_write_roots(file_system_policy)
    if not writable_roots:
        writable_roots = [Path(getattr(writable_root, "root", writable_root)) for writable_root in file_system_policy.get_writable_roots_with_cwd(cwd_path)]
    if cwd_abs is not None and cwd_abs not in writable_roots:
        writable_roots.append(cwd_abs)

    tmpdir = os.environ.get("TMPDIR")
    tmpdir_writable = bool(tmpdir) and _compat_can_write(file_system_policy, Path(tmpdir), cwd_path)

    slash_tmp = Path("/tmp")
    slash_tmp_writable = (
        _compat_is_absolute(slash_tmp)
        and slash_tmp.is_dir()
        and _compat_can_write(file_system_policy, slash_tmp, cwd_path)
    )

    return PermissionProfile.workspace_write(
        writable_roots,
        network=network_policy,
        exclude_tmpdir_env_var=not tmpdir_writable,
        exclude_slash_tmp=not slash_tmp_writable,
    )


def _compat_is_absolute(path: Path) -> bool:
    text = str(path)
    return path.is_absolute() or text.startswith("/") or text.startswith("\\")


def _explicit_write_roots(file_system_policy: object) -> list[Path]:
    roots = []
    for entry in getattr(file_system_policy, "entries", ()):
        if getattr(entry, "access", None) is not FileSystemAccessMode.WRITE:
            continue
        path = getattr(entry, "path", None)
        if getattr(path, "type", None) == "path" and getattr(path, "path", None) is not None:
            roots.append(Path(path.path))
    return roots


def _compat_can_write(file_system_policy: object, path: Path, cwd: Path) -> bool:
    try:
        if file_system_policy.can_write_path_with_cwd(path, cwd):
            return True
    except Exception:
        pass
    target = str(path).replace("\\", "/")
    for root in _explicit_write_roots(file_system_policy):
        root_text = str(root).replace("\\", "/").rstrip("/")
        if target == root_text or target.startswith(root_text + "/"):
            return True
    return False


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
