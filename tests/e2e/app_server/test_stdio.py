"""End-to-end coverage for the real app-server stdio command boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.e2e


def test_app_server_command_serves_initialize_over_stdio(tmp_path: Path) -> None:
    request = {
        "id": 1,
        "method": "initialize",
        "params": {
            "clientInfo": {
                "name": "pycodex-integration-test",
                "title": "PyCodex integration test",
                "version": "1.0.0",
            },
            "capabilities": {},
        },
    }
    env = os.environ.copy()
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    env["CODEX_HOME"] = str(codex_home)

    completed = subprocess.run(
        [sys.executable, "-m", "pycodex", "app-server"],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    messages = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    response = next(message for message in messages if message.get("id") == 1)
    assert response["result"]["codexHome"] == str(tmp_path / "codex-home")
    assert response["result"]["userAgent"]
