from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from pycodex.protocol import ManagedFileSystemPermissions, NetworkSandboxPolicy, PermissionProfile
from pycodex.windows_sandbox import (
    WindowsSandboxSpawnPrepError,
    run_windows_sandbox_capture,
    run_windows_sandbox_capture_with_filesystem_overrides,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires native Windows sandbox APIs")


def _read_only_with_network() -> PermissionProfile:
    read_only = PermissionProfile.read_only()
    assert read_only.file_system is not None
    return PermissionProfile.managed(read_only.file_system, NetworkSandboxPolicy.ENABLED)


def _workspace_with_network() -> PermissionProfile:
    workspace = PermissionProfile.workspace_write(
        network=NetworkSandboxPolicy.ENABLED,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    return workspace


def test_legacy_capture_read_only_reads_but_cannot_write(tmp_path: Path) -> None:
    # Rust owners: codex-windows-sandbox::windows_impl and spawn_prep read-only branch.
    workspace = Path.cwd()
    source = workspace / ".tmp" / f"readonly-source-{uuid.uuid4().hex}.txt"
    target = workspace / ".tmp" / f"readonly-target-{uuid.uuid4().hex}.txt"
    source.parent.mkdir(exist_ok=True)
    source.write_text("readable", encoding="utf-8")
    codex_home = tmp_path / "codex-home"
    profile = _read_only_with_network()

    try:
        read = run_windows_sandbox_capture(
            profile,
            workspace,
            codex_home,
            ["cmd.exe", "/d", "/c", f"type {source}"],
            workspace,
            dict(os.environ),
            10_000,
            True,
        )
        write = run_windows_sandbox_capture(
            profile,
            workspace,
            codex_home,
            ["cmd.exe", "/d", "/c", f"echo unsafe> {target}"],
            workspace,
            dict(os.environ),
            10_000,
            True,
        )

        assert read.exit_code == 0
        assert b"readable" in read.stdout
        assert write.exit_code != 0
        assert not target.exists()
    finally:
        source.unlink(missing_ok=True)
        target.unlink(missing_ok=True)


def test_legacy_capture_workspace_writes_repo_but_not_external_temp() -> None:
    # Real fixed-setup integration using this repository's persisted workspace capability SID.
    workspace = Path.cwd()
    codex_home = Path.home() / ".codex"
    allowed = workspace / ".tmp" / f"capture-{uuid.uuid4().hex}.txt"
    outside = Path(os.environ["TEMP"]) / f"capture-outside-{uuid.uuid4().hex}.txt"
    allowed.parent.mkdir(exist_ok=True)
    try:
        result_allowed = run_windows_sandbox_capture(
            _workspace_with_network(),
            workspace,
            codex_home,
            ["cmd.exe", "/d", "/c", f"echo allowed> {allowed}"],
            workspace,
            dict(os.environ),
            10_000,
            True,
        )
        result_denied = run_windows_sandbox_capture(
            _workspace_with_network(),
            workspace,
            codex_home,
            ["cmd.exe", "/d", "/c", f"echo denied> {outside}"],
            workspace,
            dict(os.environ),
            10_000,
            True,
        )

        assert result_allowed.exit_code == 0
        assert allowed.exists()
        assert result_denied.exit_code != 0
        assert not outside.exists()
    finally:
        allowed.unlink(missing_ok=True)
        outside.unlink(missing_ok=True)


def test_legacy_capture_rejects_deny_read_override(tmp_path: Path) -> None:
    with pytest.raises(WindowsSandboxSpawnPrepError, match="elevated Windows sandbox"):
        run_windows_sandbox_capture_with_filesystem_overrides(
            _read_only_with_network(),
            tmp_path,
            tmp_path / "codex-home",
            ["cmd.exe", "/c", "echo ok"],
            tmp_path,
            dict(os.environ),
            10_000,
            [tmp_path / "secret"],
            [],
            False,
        )


def test_legacy_capture_rejects_restricted_read_profile(tmp_path: Path) -> None:
    profile = PermissionProfile.managed(
        ManagedFileSystemPermissions.restricted(()),
        NetworkSandboxPolicy.ENABLED,
    )
    with pytest.raises(WindowsSandboxSpawnPrepError, match="requires the elevated"):
        run_windows_sandbox_capture(
            profile,
            tmp_path,
            tmp_path / "codex-home",
            ["cmd.exe", "/c", "echo ok"],
            tmp_path,
            dict(os.environ),
            10_000,
            False,
        )
