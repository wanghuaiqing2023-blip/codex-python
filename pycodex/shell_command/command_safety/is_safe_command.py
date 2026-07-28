"""Rust-aligned owner for command_safety::is_safe_command."""

from __future__ import annotations

import os
from typing import Sequence

from pycodex.shell_command.bash import parse_shell_lc_plain_commands
from pycodex.shell_command.command_safety.is_dangerous_command import (
    executable_name_lookup_key,
    find_git_subcommand,
)


SAFE_EXEC_COMMANDS = {
    "cat",
    "cd",
    "cut",
    "echo",
    "expr",
    "false",
    "grep",
    "head",
    "id",
    "ls",
    "nl",
    "paste",
    "pwd",
    "rev",
    "seq",
    "stat",
    "tail",
    "tr",
    "true",
    "uname",
    "uniq",
    "wc",
    "which",
    "whoami",
}


UNSAFE_FIND_OPTIONS = {
    "-exec",
    "-execdir",
    "-ok",
    "-okdir",
    "-delete",
    "-fls",
    "-fprint",
    "-fprint0",
    "-fprintf",
}


UNSAFE_RIPGREP_OPTIONS_WITH_ARGS = {"--pre", "--hostname-bin"}


UNSAFE_RIPGREP_OPTIONS_WITHOUT_ARGS = {"--search-zip", "-z"}


def is_known_safe_command(command: Sequence[str]) -> bool:
    normalized = ["bash" if item == "zsh" else item for item in command]
    if is_safe_command_windows(normalized):
        return True
    if is_safe_to_call_with_exec(normalized):
        return True
    plain_commands = parse_shell_lc_plain_commands(normalized)
    if plain_commands and all(is_safe_to_call_with_exec(item) for item in plain_commands):
        return True
    return False


def is_safe_to_call_with_exec(command: Sequence[str]) -> bool:
    if not command:
        return False
    lookup = executable_name_lookup_key(command[0])
    if lookup is None:
        return False
    if os.name == "posix" and lookup in {"numfmt", "tac"}:
        return True
    if lookup in SAFE_EXEC_COMMANDS:
        return True
    if lookup == "base64":
        return not any(_is_unsafe_base64_arg(arg) for arg in command[1:])
    if lookup == "find":
        return not any(arg in UNSAFE_FIND_OPTIONS for arg in command)
    if lookup == "rg":
        return is_safe_ripgrep(command)
    if lookup == "git":
        return is_safe_git_command(command)
    if lookup == "sed":
        return len(command) <= 4 and len(command) >= 3 and command[1] == "-n" and _is_valid_sed_n_arg(command[2])
    return False


def _is_unsafe_base64_arg(arg: str) -> bool:
    return arg in {"-o", "--output"} or arg.startswith("--output=") or (arg.startswith("-o") and arg != "-o")


def is_safe_ripgrep(command: Sequence[str]) -> bool:
    return not any(_is_unsafe_ripgrep_arg(arg) for arg in command[1:])


def _is_unsafe_ripgrep_arg(arg: str) -> bool:
    arg_lc = arg.lower()
    if arg_lc in UNSAFE_RIPGREP_OPTIONS_WITHOUT_ARGS:
        return True
    return any(arg_lc == option or arg_lc.startswith(f"{option}=") for option in UNSAFE_RIPGREP_OPTIONS_WITH_ARGS)


def is_safe_git_command(command: Sequence[str]) -> bool:
    found = find_git_subcommand(command, ["status", "log", "diff", "show", "branch"])
    if found is None:
        return False
    subcommand_index, subcommand = found
    global_args = command[1:subcommand_index]
    if _git_has_unsafe_global_option(global_args):
        return False
    subcommand_args = command[subcommand_index + 1 :]
    if subcommand in {"status", "log", "diff", "show"}:
        return _git_subcommand_args_are_read_only(subcommand_args)
    if subcommand == "branch":
        return _git_subcommand_args_are_read_only(subcommand_args) and _git_branch_is_read_only(subcommand_args)
    return False


def _git_branch_is_read_only(branch_args: Sequence[str]) -> bool:
    if not branch_args:
        return True
    saw_read_only_flag = False
    for arg in branch_args:
        if arg in {"--list", "-l", "--show-current", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose"}:
            saw_read_only_flag = True
            continue
        if arg.startswith("--format="):
            saw_read_only_flag = True
            continue
        return False
    return saw_read_only_flag


def _git_has_unsafe_global_option(global_args: Sequence[str]) -> bool:
    return any(_git_matches_option_pattern(arg, UNSAFE_GIT_GLOBAL_OPTIONS) for arg in global_args)


def _git_subcommand_args_are_read_only(args: Sequence[str]) -> bool:
    return not any(_git_matches_option_pattern(arg, UNSAFE_GIT_SUBCOMMAND_OPTIONS) for arg in args)


def _git_matches_option_pattern(arg: str, patterns: Sequence[tuple[str, str]]) -> bool:
    for kind, option in patterns:
        if kind == "exact" and arg == option:
            return True
        if kind == "short_inline" and arg.startswith(option) and len(arg) > len(option):
            return True
        if kind == "prefix" and arg.startswith(option):
            return True
    return False


UNSAFE_GIT_GLOBAL_OPTIONS = (
    ("exact", "-C"),
    ("short_inline", "-C"),
    ("exact", "-c"),
    ("short_inline", "-c"),
    ("exact", "-p"),
    ("exact", "--config-env"),
    ("prefix", "--config-env="),
    ("exact", "--exec-path"),
    ("prefix", "--exec-path="),
    ("exact", "--git-dir"),
    ("prefix", "--git-dir="),
    ("exact", "--namespace"),
    ("prefix", "--namespace="),
    ("exact", "--paginate"),
    ("exact", "--super-prefix"),
    ("prefix", "--super-prefix="),
    ("exact", "--work-tree"),
    ("prefix", "--work-tree="),
)


UNSAFE_GIT_SUBCOMMAND_OPTIONS = (
    ("exact", "--output"),
    ("prefix", "--output="),
    ("exact", "--ext-diff"),
    ("exact", "--textconv"),
    ("exact", "--exec"),
    ("prefix", "--exec="),
)


def _is_valid_sed_n_arg(arg: str | None) -> bool:
    if arg is None or not arg.endswith("p"):
        return False
    core = arg[:-1]
    parts = core.split(",")
    if len(parts) == 1:
        return bool(parts[0]) and parts[0].isdigit()
    if len(parts) == 2:
        return bool(parts[0]) and bool(parts[1]) and parts[0].isdigit() and parts[1].isdigit()
    return False


def is_safe_powershell_words(command: Sequence[str]) -> bool:
    return _is_safe_powershell_words_windows(command)


from pycodex.shell_command.command_safety.windows_safe_commands import (
    is_safe_command_windows,
    is_safe_powershell_words as _is_safe_powershell_words_windows,
)
