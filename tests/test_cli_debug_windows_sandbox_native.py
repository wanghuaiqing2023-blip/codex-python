from __future__ import annotations

import os
import io
import sys
from pathlib import Path

import pytest

from pycodex.cli.debug_sandbox import (
    build_debug_sandbox_windows_session_plan,
    run_debug_sandbox_windows_session_plan,
    run_debug_sandbox_windows_product_session,
)
from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires native Windows sandbox APIs")


def _read_only_with_network() -> PermissionProfile:
    profile = PermissionProfile.read_only()
    assert profile.file_system is not None
    return PermissionProfile.managed(profile.file_system, NetworkSandboxPolicy.ENABLED)


def test_default_debug_windows_spawner_uses_native_capture(tmp_path: Path) -> None:
    # Rust owner: codex-cli::debug_sandbox Windows session branch.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    plan = build_debug_sandbox_windows_session_plan(
        ["cmd.exe", "/d", "/c", "echo debug-native"],
        cwd=Path.cwd(),
        permission_profile_cwd=Path.cwd(),
        permission_profile=_read_only_with_network(),
        codex_home=codex_home,
        env=dict(os.environ),
        private_desktop=True,
    )

    result = run_debug_sandbox_windows_session_plan(plan)

    assert result.exit_code == 0
    assert result.error_message is None


def test_debug_windows_product_session_round_trips_live_stdio(tmp_path: Path) -> None:
    # Fixed Rust owner: codex-cli::debug_sandbox::
    # run_command_under_windows_session. Product execution must use the native
    # Popen session and forward stdin/stdout/stderr instead of capture replay.
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    plan = build_debug_sandbox_windows_session_plan(
        [
            sys.executable,
            "-c",
            (
                "import sys; line=sys.stdin.readline().strip(); "
                "print('OUT:'+line, flush=True); "
                "print('ERR:'+line, file=sys.stderr, flush=True)"
            ),
        ],
        cwd=Path.cwd(),
        permission_profile_cwd=Path.cwd(),
        permission_profile=_read_only_with_network(),
        codex_home=codex_home,
        env=dict(os.environ),
        private_desktop=True,
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run_debug_sandbox_windows_product_session(
        plan,
        stdin=io.BytesIO(b"native-stdio\n"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result.exit_code == 0
    assert result.error_message is None
    assert stdout.getvalue().splitlines() == ["OUT:native-stdio"]
    assert stderr.getvalue().splitlines() == ["ERR:native-stdio"]


def test_default_debug_windows_elevated_path_uses_native_capture(tmp_path: Path, monkeypatch) -> None:
    from pycodex.windows_sandbox import elevated
    from pycodex.windows_sandbox.process import ProcessCaptureResult

    observed: dict[str, object] = {}

    def fake_capture(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return ProcessCaptureResult(0, b"ok", b"")

    monkeypatch.setattr(elevated, "run_elevated_capture", fake_capture)
    plan = build_debug_sandbox_windows_session_plan(
        ["cmd.exe", "/c", "echo elevated-native"],
        cwd=Path.cwd(),
        permission_profile_cwd=Path.cwd(),
        permission_profile=_read_only_with_network(),
        codex_home=tmp_path,
        use_elevated=True,
    )

    result = run_debug_sandbox_windows_session_plan(plan)

    assert result.exit_code == 0
    assert result.error_message is None
    assert observed["kwargs"]["proxy_enforced"] is False
