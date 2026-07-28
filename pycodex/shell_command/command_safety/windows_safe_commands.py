"""Rust-aligned owner for command_safety::windows_safe_commands."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Sequence

from .powershell_parser import try_parse_powershell_ast_commands


SAFE_POWERSHELL_COMMANDS = {
    "echo",
    "write-output",
    "write-host",
    "dir",
    "ls",
    "get-childitem",
    "gci",
    "cat",
    "type",
    "gc",
    "get-content",
    "select-string",
    "sls",
    "findstr",
    "measure-object",
    "measure",
    "get-location",
    "gl",
    "pwd",
    "test-path",
    "tp",
    "resolve-path",
    "rvpa",
    "select-object",
    "select",
    "get-item",
}


def is_safe_command_windows(command: Sequence[str]) -> bool:
    commands = try_parse_powershell_command_sequence(command)
    if commands is None:
        return False
    return all(is_safe_powershell_words(item) for item in commands)


def try_parse_powershell_command_sequence(command: Sequence[str]) -> list[list[str]] | None:
    if not command:
        return None
    exe, rest = command[0], list(command[1:])
    if not _is_powershell_executable(exe):
        return None
    return parse_powershell_invocation(exe, rest)


def _is_powershell_executable(exe: str) -> bool:
    executable_name = Path(exe).name.lower()
    return executable_name in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}


def parse_powershell_command_into_plain_commands(command: Sequence[str]) -> list[list[str]] | None:
    commands = try_parse_powershell_command_sequence(command)
    if commands is None or not commands or any(not item for item in commands):
        return None
    return commands


def parse_powershell_invocation(executable: str, args: Sequence[str]) -> list[list[str]] | None:
    if not args:
        return None
    index = 0
    while index < len(args):
        arg = args[index]
        lower = arg.lower()
        if lower in {"-command", "/command", "-c"}:
            if index + 2 != len(args):
                return None
            return parse_powershell_script(executable, args[index + 1])
        if lower.startswith("-command:") or lower.startswith("/command:"):
            if index + 1 != len(args) or ":" not in arg:
                return None
            return parse_powershell_script(executable, arg.split(":", 1)[1])
        if lower in {"-nologo", "-noprofile", "-noninteractive", "-mta", "-sta"}:
            index += 1
            continue
        if lower in {"-encodedcommand", "-ec", "-file", "/file", "-windowstyle", "-executionpolicy", "-workingdirectory"}:
            return None
        if lower.startswith("-"):
            return None
        return parse_powershell_script(executable, join_arguments_as_script(args[index:]))
    return None


def parse_powershell_script(executable: str, script: str) -> list[list[str]] | None:
    return try_parse_powershell_ast_commands(executable, script)


def _powershell_script_has_unsupported_construct(script: str) -> bool:
    return any(marker in script for marker in (">", "<", "$(", "@(", "--%")) or _powershell_script_has_dynamic_argument(script)


def _powershell_script_has_dynamic_argument(script: str) -> bool:
    in_single_quote = False
    in_double_quote = False
    index = 0
    while index < len(script):
        char = script[index]
        if char == "`":
            index += 2
            continue
        if char == "'" and not in_double_quote:
            if in_single_quote and index + 1 < len(script) and script[index + 1] == "'":
                index += 2
                continue
            in_single_quote = not in_single_quote
            index += 1
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            index += 1
            continue
        if char == "$" and not in_single_quote:
            next_char = script[index + 1] if index + 1 < len(script) else ""
            if next_char == "{" or next_char == "_" or next_char.isalpha():
                return True
        index += 1
    return False


def _powershell_split(script: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(script, posix=True, punctuation_chars="|;&(){}[],")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return None


def _split_powershell_commands(tokens: Sequence[str]) -> list[list[str]]:
    commands: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in {"|", ";"}:
            if current:
                commands.append(current)
                current = []
            continue
        if token in {"&", "&&", "||", ">", ">>", "2>", "2>>"}:
            return []
        if token in {"(", ")", "{", "}", "[", "]", ","}:
            continue
        current.append(token)
    if current:
        commands.append(current)
    return commands


def join_arguments_as_script(args: Sequence[str]) -> str:
    if not args:
        return ""
    return " ".join([args[0], *[quote_argument(arg) for arg in args[1:]]]).strip()


def quote_argument(arg: str) -> str:
    if arg == "":
        return "''"
    if all(not char.isspace() for char in arg):
        return arg
    return "'" + arg.replace("'", "''") + "'"


def is_safe_powershell_words(command: Sequence[str]) -> bool:
    if os.name != "nt":
        return False
    return _is_safe_powershell_words_any_platform(command)


def _is_safe_powershell_words_any_platform(words: Sequence[str]) -> bool:
    if not words:
        return False
    side_effect_commands = {
        "set-content",
        "add-content",
        "out-file",
        "new-item",
        "remove-item",
        "move-item",
        "copy-item",
        "rename-item",
        "start-process",
        "stop-process",
    }
    for word in words:
        inner = word.strip("()").lstrip("-").lower()
        if inner in side_effect_commands:
            return False
    command = words[0].strip("()").lstrip("-").lower()
    if command in SAFE_POWERSHELL_COMMANDS:
        return True
    if command == "git":
        return is_safe_git_command(words)
    if command == "rg":
        return is_safe_ripgrep(words)
    if command in side_effect_commands:
        return False
    return False


def is_safe_ripgrep(words: Sequence[str]) -> bool:
    options_with_args = {"--pre", "--hostname-bin"}
    options_without_args = {"--search-zip", "-z"}
    for arg in words[1:]:
        arg_lc = arg.lower()
        if arg_lc in options_without_args:
            return False
        if any(arg_lc == option or arg_lc.startswith(f"{option}=") for option in options_with_args):
            return False
    return True


from .is_safe_command import is_known_safe_command, is_safe_git_command
