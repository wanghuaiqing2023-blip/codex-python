"""PowerShell wrapper helpers aligned with Rust ``codex-shell-command``.

Rust counterpart: ``codex/codex-rs/shell-command/src/powershell.rs``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .command_safety import parse_powershell_script
from .parse_command import extract_powershell_command


UTF8_OUTPUT_PREFIX = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;\n"


def prefix_powershell_script_with_utf8(command: Sequence[str]) -> list[str]:
    extracted = extract_powershell_command(command)
    if extracted is None:
        return list(command)

    script = extracted[1]
    trimmed = script.lstrip()
    if not trimmed.startswith(UTF8_OUTPUT_PREFIX):
        script = f"{UTF8_OUTPUT_PREFIX}{script}"

    return list(command[:-1]) + [script]


def parse_powershell_command_into_plain_commands(command: Sequence[str]) -> list[list[str]] | None:
    extracted = extract_powershell_command(command)
    if extracted is None:
        return None
    executable, script = extracted
    commands = parse_powershell_script(executable, script)
    if commands is None or not commands or any(not item for item in commands):
        return None
    return commands


def try_find_powershell_executable_blocking() -> Path | None:
    return _try_find_powershellish_executable_in_path(["powershell.exe"])


def try_find_pwsh_executable_blocking() -> Path | None:
    ps_home = _try_find_pwsh_home()
    if ps_home is not None:
        candidate = ps_home / "pwsh.exe"
        if _is_powershellish_executable_available(candidate):
            return candidate
    return _try_find_powershellish_executable_in_path(["pwsh.exe"])


def _try_find_pwsh_home() -> Path | None:
    cmd = shutil.which("cmd")
    if cmd is None:
        return None
    try:
        result = subprocess.run(
            [cmd, "/C", "pwsh", "-NoProfile", "-Command", "$PSHOME"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    stdout = result.stdout.strip()
    return Path(stdout) if stdout else None


def _try_find_powershellish_executable_in_path(candidates: Sequence[str]) -> Path | None:
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved is None:
            continue
        path = Path(resolved).resolve()
        if _is_powershellish_executable_available(path):
            return path
    return None


def _is_powershellish_executable_available(powershell_or_pwsh_exe: Path) -> bool:
    try:
        result = subprocess.run(
            [str(powershell_or_pwsh_exe), "-NoLogo", "-NoProfile", "-Command", "Write-Output ok"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


__all__ = [
    "UTF8_OUTPUT_PREFIX",
    "extract_powershell_command",
    "parse_powershell_command_into_plain_commands",
    "prefix_powershell_script_with_utf8",
    "try_find_powershell_executable_blocking",
    "try_find_pwsh_executable_blocking",
]
