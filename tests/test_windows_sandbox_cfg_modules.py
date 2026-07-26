from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest


def test_windows_and_stub_modules_own_cfg_branch_items() -> None:
    from pycodex.windows_sandbox import stub, windows_impl

    assert (
        windows_impl.CaptureResult.__module__
        == "pycodex.windows_sandbox.windows_impl"
    )
    assert (
        windows_impl.run_windows_sandbox_capture.__module__
        == "pycodex.windows_sandbox.windows_impl"
    )
    assert (
        stub.CaptureResult.__module__
        == "pycodex.windows_sandbox.stub"
    )
    assert (
        stub.run_windows_sandbox_capture.__module__
        == "pycodex.windows_sandbox.stub"
    )


def test_crate_root_reexports_active_cfg_branch() -> None:
    import pycodex.windows_sandbox as sandbox
    from pycodex.windows_sandbox import stub, windows_impl

    active = windows_impl if os.name == "nt" else stub
    assert sandbox.CaptureResult is active.CaptureResult
    assert (
        sandbox.run_windows_sandbox_capture
        is active.run_windows_sandbox_capture
    )
    assert (
        sandbox.run_windows_sandbox_legacy_preflight
        is active.run_windows_sandbox_legacy_preflight
    )


def test_crate_root_does_not_define_cfg_branch_implementations() -> None:
    import pycodex.windows_sandbox as sandbox

    source = inspect.getsource(sandbox)
    assert "class CaptureResult" not in source
    assert "def run_windows_sandbox_capture(" not in source
    assert "def run_windows_sandbox_legacy_preflight(" not in source


def test_non_windows_stub_rejects_capture_and_preflight(tmp_path: Path) -> None:
    from pycodex.protocol import PermissionProfile
    from pycodex.windows_sandbox import stub

    with pytest.raises(OSError, match="only available on Windows"):
        stub.run_windows_sandbox_capture(
            PermissionProfile.read_only(),
            tmp_path,
            tmp_path,
            ["cmd.exe"],
            tmp_path,
            {},
            None,
            False,
        )
    with pytest.raises(OSError, match="only available on Windows"):
        stub.run_windows_sandbox_legacy_preflight(
            PermissionProfile.read_only(),
            tmp_path,
            tmp_path,
            tmp_path,
            {},
        )
