"""Subprocess builder derived from ``test_codex_exec.rs``."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

__test__ = False


@dataclass(frozen=True)
class TestCodexExecBuilder:
    cwd: Path
    home: Path

    def command(self, *args: str, env: Mapping[str, str] | None = None) -> tuple[list[str], dict[str, str]]:
        command_env = os.environ.copy()
        command_env["CODEX_HOME"] = str(self.home)
        command_env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(Path(__file__).resolve().parents[3]), command_env.get("PYTHONPATH", "")])
        )
        if env:
            command_env.update(env)
        return [sys.executable, "-B", "-m", "pycodex", *args], command_env

    def run(
        self,
        *args: str,
        env: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> subprocess.CompletedProcess[str]:
        command, command_env = self.command(*args, env=env)
        return subprocess.run(
            command,
            cwd=self.cwd,
            env=command_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def cmd_with_server(self, server_url: str, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run(*args, env={"OPENAI_BASE_URL": server_url})

    def cwd_path(self) -> Path:
        return self.cwd

    def home_path(self) -> Path:
        return self.home


def test_codex_exec(
    *,
    cwd: str | Path | None = None,
    home: str | Path | None = None,
) -> TestCodexExecBuilder:
    resolved_cwd = Path(cwd or Path.cwd()).resolve()
    resolved_home = Path(home or tempfile.mkdtemp(prefix="pycodex-core-test-home-")).resolve()
    resolved_home.mkdir(parents=True, exist_ok=True)
    return TestCodexExecBuilder(resolved_cwd, resolved_home)


test_codex_exec.__test__ = False


__all__ = ["TestCodexExecBuilder", "test_codex_exec"]
