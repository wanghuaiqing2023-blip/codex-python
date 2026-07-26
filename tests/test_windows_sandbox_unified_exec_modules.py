from __future__ import annotations

import os
from pathlib import Path

from pycodex.protocol import PermissionProfile
from pycodex.windows_sandbox import elevated_impl
from pycodex.windows_sandbox.elevated_impl import stub as elevated_stub
from pycodex.windows_sandbox.elevated_impl import windows_impl as elevated_windows
from pycodex.windows_sandbox import unified_exec
from pycodex.windows_sandbox.unified_exec.backends import elevated, legacy


def test_unified_exec_parent_delegates_legacy_backend(monkeypatch, tmp_path: Path) -> None:
    observed: list[object] = []
    monkeypatch.setattr(
        legacy,
        "spawn_windows_sandbox_session_legacy",
        lambda *args, **kwargs: observed.append((args, kwargs)) or "legacy",
    )

    result = unified_exec.spawn_windows_sandbox_session_legacy(
        PermissionProfile.read_only(),
        tmp_path,
        tmp_path / "home",
        ["cmd.exe"],
        tmp_path,
        {},
        None,
        (),
        (),
        False,
        False,
        False,
    )

    assert result == "legacy"
    assert len(observed) == 1


def test_unified_exec_parent_delegates_elevated_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed: list[object] = []
    monkeypatch.setattr(
        elevated,
        "spawn_windows_sandbox_session_elevated_for_permission_profile",
        lambda *args, **kwargs: observed.append((args, kwargs)) or "elevated",
    )

    result = unified_exec.spawn_windows_sandbox_session_elevated_for_permission_profile(
        PermissionProfile.read_only(),
        tmp_path,
        tmp_path / "home",
        ["cmd.exe"],
        tmp_path,
        {},
        None,
        None,
        False,
        None,
        (),
        (),
        False,
        False,
        False,
    )

    assert result == "elevated"
    assert len(observed) == 1


def test_elevated_impl_parent_selects_cfg_branch() -> None:
    expected = (
        elevated_windows.run_windows_sandbox_capture_for_permission_profile
        if os.name == "nt"
        else elevated_stub.run_windows_sandbox_capture_for_permission_profile
    )
    assert (
        elevated_impl.run_windows_sandbox_capture_for_permission_profile
        is expected
    )


def test_elevated_stub_rejects_non_windows_capture(tmp_path: Path) -> None:
    request = elevated_impl.ElevatedSandboxProfileCaptureRequest(
        PermissionProfile.read_only(),
        tmp_path,
        tmp_path / "home",
        ("cmd.exe",),
        tmp_path,
        {},
    )

    try:
        elevated_stub.run_windows_sandbox_capture_for_permission_profile(request)
    except OSError as exc:
        assert "only available on Windows" in str(exc)
    else:
        raise AssertionError("non-Windows stub must reject capture")
