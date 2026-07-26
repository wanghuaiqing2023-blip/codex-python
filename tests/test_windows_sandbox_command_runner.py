from __future__ import annotations

from pathlib import Path


def test_cwd_junction_name_is_stable_and_rooted_under_sandbox(tmp_path: Path) -> None:
    # Rust source: bin/command_runner/win/cwd_junction.rs.
    from pycodex.windows_sandbox.bin.command_runner.win.cwd_junction import (
        junction_name_for_path,
        junction_root_for_userprofile,
    )

    requested = tmp_path / "workspace"
    assert junction_name_for_path(requested) == junction_name_for_path(requested)
    assert (
        junction_root_for_userprofile(tmp_path)
        == tmp_path / ".codex" / ".sandbox" / "cwd"
    )


def test_command_runner_effective_cwd_uses_junction_when_acl_mutex_exists(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # Rust source: bin/command_runner/win.rs::effective_cwd.
    import pycodex.windows_sandbox.bin.command_runner.win as runner

    requested = tmp_path / "workspace"
    junction = tmp_path / "junction"
    monkeypatch.setattr(runner, "read_acl_mutex_exists", lambda: True)
    monkeypatch.setattr(runner, "create_cwd_junction", lambda *_args: junction)

    assert runner.effective_cwd(requested, tmp_path / "logs") == junction


def test_command_runner_binary_delegates_to_windows_main(monkeypatch) -> None:
    # Rust source: bin/command_runner/main.rs::main.
    import pycodex.windows_sandbox.bin.command_runner.__main__ as binary

    monkeypatch.setattr(binary, "windows_main", lambda _argv=None: 7)
    assert binary.main(["--test"]) == 7
