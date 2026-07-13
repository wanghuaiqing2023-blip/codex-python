from __future__ import annotations

from pathlib import Path

from pycodex.windows_sandbox.env import (
    apply_no_network_to_env,
    ensure_non_interactive_pager,
    inherit_path_env,
    normalize_null_device_env,
)


def test_normalize_null_device_env_matches_windows_spelling() -> None:
    # Rust owner: codex-windows-sandbox::env::normalize_null_device_env.
    env = {"A": "/dev/null", "B": r"\\dev\\null", "C": "keep"}
    normalize_null_device_env(env)
    assert env == {"A": "NUL", "B": "NUL", "C": "keep"}


def test_pager_defaults_preserve_explicit_values() -> None:
    env = {"PAGER": "custom"}
    ensure_non_interactive_pager(env)
    assert env["GIT_PAGER"] == "more.com"
    assert env["PAGER"] == "custom"
    assert env["LESS"] == ""


def test_inherit_path_env_only_fills_missing(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "parent-path")
    monkeypatch.setenv("PATHEXT", ".EXE;.CMD")
    env = {"PATH": "explicit"}
    inherit_path_env(env)
    assert env["PATH"] == "explicit"
    assert env["PATHEXT"] == ".EXE;.CMD"


def test_apply_no_network_env_builds_deny_stubs(tmp_path: Path) -> None:
    # Rust owner: codex-windows-sandbox::env::apply_no_network_to_env.
    env = {"PATH": "C:\\Windows", "PATHEXT": ".COM;.EXE;.BAT;.CMD"}
    denybin = apply_no_network_to_env(env, denybin_dir=tmp_path / "denybin")

    assert env["SBX_NONET_ACTIVE"] == "1"
    assert env["HTTP_PROXY"] == "http://127.0.0.1:9"
    assert env["PATH"].split(";", 1)[0] == str(denybin)
    assert env["PATHEXT"].startswith(".BAT;.CMD")
    assert (denybin / "ssh.bat").read_bytes() == b"@echo off\r\nexit /b 1\r\n"
    assert (denybin / "scp.cmd").exists()
    assert not (denybin / "curl.cmd").exists()
