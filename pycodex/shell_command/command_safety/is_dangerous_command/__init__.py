"""Rust-aligned owner for command_safety::is_dangerous_command."""

from __future__ import annotations

import os
from pathlib import PurePosixPath, PureWindowsPath
from typing import Sequence

from pycodex.shell_command.bash import parse_shell_lc_plain_commands


def command_might_be_dangerous(command: Sequence[str]) -> bool:
    if is_dangerous_command_windows(command):
        return True
    if _is_dangerous_to_call_with_exec(command):
        return True
    plain_commands = parse_shell_lc_plain_commands(command)
    if plain_commands and any(_is_dangerous_to_call_with_exec(item) for item in plain_commands):
        return True
    return False


def _is_dangerous_to_call_with_exec(command: Sequence[str]) -> bool:
    if not command:
        return False
    if command[0] == "rm":
        return len(command) > 1 and command[1] in {"-f", "-rf"}
    if command[0] == "sudo":
        return _is_dangerous_to_call_with_exec(command[1:])
    return False


def is_git_global_option_with_value(arg: str) -> bool:
    return arg in {
        "-C",
        "-c",
        "--config-env",
        "--exec-path",
        "--git-dir",
        "--namespace",
        "--super-prefix",
        "--work-tree",
    }


def is_git_global_option_with_inline_value(arg: str) -> bool:
    return (
        arg.startswith("--config-env=")
        or arg.startswith("--exec-path=")
        or arg.startswith("--git-dir=")
        or arg.startswith("--namespace=")
        or arg.startswith("--super-prefix=")
        or arg.startswith("--work-tree=")
        or ((arg.startswith("-C") or arg.startswith("-c")) and len(arg) > 2)
    )


def find_git_subcommand(command: Sequence[str], subcommands: Sequence[str]) -> tuple[int, str] | None:
    if not command or executable_name_lookup_key(command[0]) != "git":
        return None
    skip_next = False
    for index, arg in enumerate(command[1:], start=1):
        if skip_next:
            skip_next = False
            continue
        if is_git_global_option_with_inline_value(arg):
            continue
        if is_git_global_option_with_value(arg):
            skip_next = True
            continue
        if arg == "--" or arg.startswith("-"):
            continue
        if arg in subcommands:
            return index, arg
        return None
    return None


def executable_name_lookup_key(raw: str) -> str | None:
    if not raw:
        return None
    name = _basename(raw)
    if name is None:
        return None
    if os.name == "nt":
        name = name.lower()
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name
    return name


def _basename(raw: str) -> str | None:
    raw = raw.rstrip("/\\")
    if not raw:
        return None
    if "\\" in raw:
        return PureWindowsPath(raw).name
    return PurePosixPath(raw).name


def is_dangerous_powershell_words(command: Sequence[str]) -> bool:
    return _is_dangerous_powershell_words_windows(command)


from .windows_dangerous_commands import (
    is_dangerous_command_windows,
    is_dangerous_powershell_words as _is_dangerous_powershell_words_windows,
)
