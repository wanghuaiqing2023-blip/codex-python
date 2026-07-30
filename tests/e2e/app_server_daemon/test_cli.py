from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


pytestmark = pytest.mark.e2e


def test_app_server_daemon_cli_uses_real_platform_gate(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("the fixed Rust baseline supports daemon lifecycle only on Unix")

    env = os.environ.copy()
    env["CODEX_HOME"] = str(tmp_path / "codex-home")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pycodex",
            "app-server",
            "daemon",
            "start",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert (
        "codex app-server daemon lifecycle is only supported on Unix platforms"
        in result.stderr
    )
    assert not (Path(env["CODEX_HOME"]) / "app-server-state.json").exists()
