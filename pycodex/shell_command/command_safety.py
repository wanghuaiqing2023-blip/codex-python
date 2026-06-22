"""Read-only and dangerous-command heuristics for shell commands.

Ported from:

- ``codex/codex-rs/shell-command/src/command_safety/is_safe_command.rs``
- ``codex/codex-rs/shell-command/src/command_safety/is_dangerous_command.rs``
- the standard-library-compatible portions of the Windows command safety files.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import PurePosixPath, PureWindowsPath
from typing import Iterable, Sequence
from urllib.parse import urlparse

from .parse_command import parse_shell_lc_plain_commands
from .powershell_parser import try_parse_powershell_ast_commands


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

SIDE_EFFECT_POWERSHELL_COMMANDS = {
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
    for word in words:
        inner = word.strip("()").lstrip("-").lower()
        if inner in SIDE_EFFECT_POWERSHELL_COMMANDS:
            return False
    command = words[0].strip("()").lstrip("-").lower()
    if command in SAFE_POWERSHELL_COMMANDS:
        return True
    if command == "git":
        return is_safe_git_command(words)
    if command == "rg":
        return is_safe_ripgrep(words)
    if command in SIDE_EFFECT_POWERSHELL_COMMANDS:
        return False
    return False


def is_dangerous_command_windows(command: Sequence[str]) -> bool:
    return is_dangerous_powershell(command) or is_dangerous_cmd(command) or is_direct_gui_launch(command)


def is_dangerous_powershell(command: Sequence[str]) -> bool:
    if not command or not _is_powershell_executable(command[0]):
        return False
    parsed = parse_powershell_invocation_for_danger(command[1:])
    return parsed is not None and is_dangerous_powershell_words(parsed)


def is_dangerous_powershell_words(words: Sequence[str]) -> bool:
    tokens_lc = [token.strip("'\"").lower() for token in words]
    if _is_dangerous_to_call_with_exec(tokens_lc):
        return True
    has_url = args_have_url(words)
    if has_url and any(token in {"start-process", "start", "saps", "invoke-item", "ii"} or "start-process" in token or "invoke-item" in token for token in tokens_lc):
        return True
    if has_url and any("shellexecute" in token or "shell.application" in token for token in tokens_lc):
        return True
    if tokens_lc:
        first = tokens_lc[0]
        if first == "rundll32" and any("url.dll,fileprotocolhandler" in token for token in tokens_lc) and has_url:
            return True
        if first == "mshta" and has_url:
            return True
        if _is_browser_executable(first) and has_url:
            return True
        if first in {"explorer", "explorer.exe"} and has_url:
            return True
    return has_force_delete_cmdlet(tokens_lc)


def parse_powershell_invocation_for_danger(args: Sequence[str]) -> list[str] | None:
    if not args:
        return None
    index = 0
    while index < len(args):
        arg = args[index]
        lower = arg.lower()
        if lower in {"-command", "/command", "-c"}:
            if index + 2 != len(args):
                return None
            return _danger_split(args[index + 1])
        if lower.startswith("-command:") or lower.startswith("/command:"):
            if index + 1 != len(args) or ":" not in arg:
                return None
            return _danger_split(arg.split(":", 1)[1])
        if lower in {"-nologo", "-noprofile", "-noninteractive", "-mta", "-sta"}:
            index += 1
            continue
        if lower.startswith("-"):
            index += 1
            continue
        return list(args[index:])
    return None


def _danger_split(script: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(script, posix=True, punctuation_chars=";&|{}[](),")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return [script]


def is_dangerous_cmd(command: Sequence[str]) -> bool:
    if not command:
        return False
    base = executable_basename(command[0])
    if base not in {"cmd", "cmd.exe"}:
        return False
    rest_iter = iter(command[1:])
    remaining: list[str] = []
    for arg in rest_iter:
        lower = arg.lower()
        if lower in {"/c", "/r", "-c"}:
            remaining = list(rest_iter)
            break
        if lower.startswith("/"):
            continue
        return False
    if not remaining:
        return False
    if len(remaining) == 1:
        cmd_tokens = _simple_split(remaining[0])
    else:
        cmd_tokens = remaining
    tokens = [part for token in cmd_tokens for part in split_embedded_cmd_operators(token)]
    separators = {"&", "&&", "|", "||"}
    segment: list[str] = []
    segments: list[list[str]] = []
    for token in tokens:
        if token in separators:
            if segment:
                segments.append(segment)
                segment = []
        else:
            segment.append(token)
    if segment:
        segments.append(segment)
    return any(_cmd_segment_is_dangerous(item) for item in segments)


def _cmd_segment_is_dangerous(segment: Sequence[str]) -> bool:
    if not segment:
        return False
    command = segment[0].lower()
    if command == "start" and args_have_url(segment):
        return True
    if command in {"del", "erase"} and has_force_flag_cmd(segment):
        return True
    if command in {"rd", "rmdir"} and has_recursive_flag_cmd(segment) and has_quiet_flag_cmd(segment):
        return True
    return False


def is_direct_gui_launch(command: Sequence[str]) -> bool:
    if not command:
        return False
    base = executable_basename(command[0])
    if base in {"explorer", "explorer.exe", "mshta", "mshta.exe"} and args_have_url(command[1:]):
        return True
    if base in {"rundll32", "rundll32.exe"} and any("url.dll,fileprotocolhandler" in token.lower() for token in command[1:]) and args_have_url(command[1:]):
        return True
    return bool(base and _is_browser_executable(base) and args_have_url(command[1:]))


def split_embedded_cmd_operators(token: str) -> list[str]:
    parts: list[str] = []
    start = 0
    index = 0
    while index < len(token):
        char = token[index]
        if char in {"&", "|"}:
            if index > start:
                parts.append(token[start:index])
            if index + 1 < len(token) and token[index + 1] == char:
                parts.append(token[index : index + 2])
                index += 2
            else:
                parts.append(char)
                index += 1
            start = index
            continue
        index += 1
    if start < len(token):
        parts.append(token[start:])
    return [part.strip() for part in parts if part.strip()]


def has_force_delete_cmdlet(tokens: Sequence[str]) -> bool:
    delete_cmdlets = {"remove-item", "ri", "rm", "del", "erase", "rd", "rmdir"}
    segment_separators = set(";|&\n\r\t")
    soft_separators = "{}()[],;"
    segments: list[list[str]] = [[]]
    for token in tokens:
        current = ""
        for char in token:
            if char in segment_separators:
                if current.strip():
                    segments[-1].append(current.strip())
                current = ""
                if segments[-1]:
                    segments.append([])
            else:
                current += char
        if current.strip():
            segments[-1].append(current.strip())

    for segment in segments:
        atoms: list[str] = []
        for token in segment:
            atoms.extend(part.strip() for part in re.split(f"[{re.escape(soft_separators)}]", token) if part.strip())
        has_delete = any(atom.lower() in delete_cmdlets for atom in atoms)
        has_force = any(atom.lower() == "-force" or atom.lower().startswith("-force:") for atom in atoms)
        if has_delete and has_force:
            return True
    return False


def has_force_flag_cmd(args: Sequence[str]) -> bool:
    return any(arg.lower() == "/f" for arg in args)


def has_recursive_flag_cmd(args: Sequence[str]) -> bool:
    return any(arg.lower() == "/s" for arg in args)


def has_quiet_flag_cmd(args: Sequence[str]) -> bool:
    return any(arg.lower() == "/q" for arg in args)


def args_have_url(args: Sequence[str]) -> bool:
    return any(looks_like_url(arg) for arg in args)


def looks_like_url(token: str) -> bool:
    start_candidates = [idx for idx in (token.find("https://"), token.find("http://")) if idx >= 0]
    urlish = token[min(start_candidates) :] if start_candidates else token
    candidate = re.sub(r"""^[ "'(\s]*""", "", urlish)
    candidate = re.sub(r"""[\s;)"']*$""", "", candidate)
    parsed = urlparse(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def executable_basename(exe: str) -> str | None:
    name = _basename(exe)
    return name.lower() if name is not None else None


def _is_powershell_executable(exe: str) -> bool:
    return executable_basename(exe) in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}


def _is_browser_executable(name: str) -> bool:
    return name in {"chrome", "chrome.exe", "msedge", "msedge.exe", "firefox", "firefox.exe", "iexplore", "iexplore.exe"}


def _simple_split(value: str) -> list[str]:
    try:
        return shlex.split(value)
    except ValueError:
        return [value]


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


__all__ = [
    "command_might_be_dangerous",
    "executable_name_lookup_key",
    "find_git_subcommand",
    "is_dangerous_powershell_words",
    "is_known_safe_command",
    "is_safe_git_command",
    "is_safe_powershell_words",
    "parse_powershell_command_into_plain_commands",
]
