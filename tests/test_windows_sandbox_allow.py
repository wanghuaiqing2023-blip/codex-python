from __future__ import annotations

from pathlib import Path

from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile
from pycodex.windows_sandbox.allow import compute_allow_paths_for_permissions
from pycodex.windows_sandbox.resolved_permissions import ResolvedWindowsSandboxPermissions


def _paths(
    profile: PermissionProfile,
    profile_cwd: Path,
    command_cwd: Path,
    env: dict[str, str],
):
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(profile, profile_cwd)
    return compute_allow_paths_for_permissions(permissions, command_cwd, env)


def test_includes_additional_writable_roots(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::allow::includes_additional_writable_roots.
    workspace = tmp_path / "workspace"
    extra = tmp_path / "extra"
    workspace.mkdir()
    extra.mkdir()
    profile = PermissionProfile.workspace_write([extra], NetworkSandboxPolicy.RESTRICTED)

    paths = _paths(profile, workspace, workspace, {})

    assert workspace.resolve() in paths.allow
    assert extra.resolve() in paths.allow


def test_workspace_root_stays_bound_to_profile_cwd(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::allow::uses_profile_cwd_for_workspace_root.
    workspace = tmp_path / "workspace"
    command_cwd = workspace / "subdir"
    command_cwd.mkdir(parents=True)
    profile = PermissionProfile.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)

    paths = _paths(profile, workspace, command_cwd, {})

    assert workspace.resolve() in paths.allow
    assert command_cwd.resolve() not in paths.allow


def test_windows_temp_roots_follow_profile_flag(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::allow::{includes,excludes}_tmp_env_vars_when_requested.
    workspace = tmp_path / "workspace"
    temp = tmp_path / "temp"
    workspace.mkdir()
    temp.mkdir()
    env = {"TEMP": str(temp), "TMP": str(temp)}

    included = _paths(PermissionProfile.workspace_write(), workspace, workspace, env)
    excluded = _paths(
        PermissionProfile.workspace_write(exclude_tmpdir_env_var=True),
        workspace,
        workspace,
        env,
    )

    assert temp.resolve() in included.allow
    assert temp.resolve() not in excluded.allow


def test_protected_workspace_metadata_is_denied_when_present(tmp_path: Path) -> None:
    # Rust: codex-windows-sandbox::allow::denies_codex_and_agents_inside_writable_root.
    workspace = tmp_path / "workspace"
    protected = [workspace / name for name in (".git", ".codex", ".agents")]
    for path in protected:
        path.mkdir(parents=True, exist_ok=True)
    profile = PermissionProfile.workspace_write(exclude_tmpdir_env_var=True)

    paths = _paths(profile, workspace, workspace, {})

    assert {path.resolve() for path in protected}.issubset(paths.deny)
