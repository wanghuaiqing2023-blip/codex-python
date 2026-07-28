from __future__ import annotations

import os
from pathlib import Path

from pycodex.rmcp_client.program_resolver import resolve


def test_program_resolver_uses_rust_module_owner() -> None:
    assert resolve.__module__ == "pycodex.rmcp_client.program_resolver"


def test_resolve_preserves_unknown_program(tmp_path: Path) -> None:
    assert resolve("missing-rmcp-program", {"PATH": str(tmp_path)}, tmp_path) == (
        "missing-rmcp-program"
    )


def test_windows_resolves_pathext_from_supplied_environment(tmp_path: Path) -> None:
    command = tmp_path / "test_mcp_server.cmd"
    command.write_text("@echo off\r\nexit /b 0\r\n", encoding="ascii")
    environment = {
        "PATH": str(tmp_path),
        "PATHEXT": ".COM;.EXE;.BAT;.CMD",
    }

    resolved = resolve("test_mcp_server", environment, tmp_path)
    if os.name == "nt":
        assert Path(resolved).resolve() == command.resolve()
    else:
        assert resolved == "test_mcp_server"


def test_windows_resolves_relative_path_against_supplied_cwd(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    command = scripts / "relative_server.cmd"
    command.write_text("@echo off\r\nexit /b 0\r\n", encoding="ascii")

    resolved = resolve(
        "relative_server",
        {"PATH": "scripts", "PATHEXT": ".CMD"},
        tmp_path,
    )
    if os.name == "nt":
        assert Path(resolved).resolve() == command.resolve()
    else:
        assert resolved == "relative_server"

