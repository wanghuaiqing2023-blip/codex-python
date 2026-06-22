from pathlib import PureWindowsPath

import pytest

from pycodex.core.shell import ShellType
from pycodex.shell_command import detect_shell_type


def test_detect_shell_type_exact_known_names() -> None:
    # Source: rust_source_inferred
    # Rust crate: codex-shell-command
    # Rust module: src/shell_detect.rs
    # Rust item: detect_shell_type
    # Contract: shell.shell_detect
    assert detect_shell_type("zsh") is ShellType.ZSH
    assert detect_shell_type("bash") is ShellType.BASH
    assert detect_shell_type("pwsh") is ShellType.POWERSHELL
    assert detect_shell_type("powershell") is ShellType.POWERSHELL
    assert detect_shell_type("sh") is ShellType.SH
    assert detect_shell_type("cmd") is ShellType.CMD


def test_detect_shell_type_recurses_through_file_stem() -> None:
    # Source: rust_source_inferred
    # Rust crate: codex-shell-command
    # Rust module: src/shell_detect.rs
    # Rust item: detect_shell_type
    # Contract: shell.shell_detect
    assert detect_shell_type("/usr/bin/bash") is ShellType.BASH
    assert detect_shell_type("/bin/zsh") is ShellType.ZSH
    assert detect_shell_type(PureWindowsPath(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")) is ShellType.POWERSHELL
    assert detect_shell_type(PureWindowsPath(r"C:\Windows\System32\cmd.exe")) is ShellType.CMD


def test_detect_shell_type_unknown_and_invalid_inputs() -> None:
    # Source: rust_source_inferred
    # Rust crate: codex-shell-command
    # Rust module: src/shell_detect.rs
    # Rust item: detect_shell_type
    # Contract: shell.shell_detect
    assert detect_shell_type("python") is None
    assert detect_shell_type("/usr/bin/not-a-shell") is None
    with pytest.raises(TypeError):
        detect_shell_type(123)  # type: ignore[arg-type]
