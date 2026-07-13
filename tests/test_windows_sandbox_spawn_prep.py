from __future__ import annotations

import os
from pathlib import Path

from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile
from pycodex.windows_sandbox import (
    SpawnPrepOptions,
    legacy_session_capability_roots,
    prepare_legacy_spawn_context,
    root_capability_sids,
)


def _workspace_with_network() -> PermissionProfile:
    profile = PermissionProfile.workspace_write(network=NetworkSandboxPolicy.ENABLED)
    return profile


def test_prepare_context_normalizes_environment_and_preserves_profile_cwd(tmp_path: Path) -> None:
    # Rust owner: codex-windows-sandbox::spawn_prep::prepare_legacy_spawn_context.
    workspace = tmp_path / "workspace"
    command_cwd = workspace / "subdir"
    command_cwd.mkdir(parents=True)
    env = {"NULL_DEVICE": "/dev/null"}

    context = prepare_legacy_spawn_context(
        _workspace_with_network(),
        workspace,
        tmp_path / "codex-home",
        command_cwd,
        env,
        ["cmd.exe", "/c", "echo ok"],
        SpawnPrepOptions(inherit_path=True),
    )

    assert context.current_dir == command_cwd
    assert context.uses_write_capabilities
    assert env["NULL_DEVICE"] == "NUL"
    assert env["GIT_PAGER"] == "more.com"
    assert env["PATH"] == os.environ["PATH"]
    roots = legacy_session_capability_roots(context.permissions, command_cwd, env, tmp_path / "codex-home")
    assert workspace.resolve() in roots
    assert command_cwd.resolve() not in roots


def test_root_capability_sids_are_stable_and_root_scoped(tmp_path: Path) -> None:
    # Rust owner: codex-windows-sandbox::spawn_prep::root_capability_sids.
    workspace = tmp_path / "workspace"
    extra = tmp_path / "extra"
    workspace.mkdir()
    extra.mkdir()
    codex_home = tmp_path / "codex-home"

    first = root_capability_sids(codex_home, workspace, [workspace, extra, workspace])
    first_values = {item.root: item.sid_str for item in first}
    for item in first:
        item.close()
    second = root_capability_sids(codex_home, workspace, [extra, workspace])
    second_values = {item.root: item.sid_str for item in second}
    for item in second:
        item.close()

    assert first_values == second_values
    assert len(set(first_values.values())) == 2
