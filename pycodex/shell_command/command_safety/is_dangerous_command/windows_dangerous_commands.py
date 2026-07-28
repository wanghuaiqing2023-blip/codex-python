"""Rust-aligned owner for command_safety::is_dangerous_command::windows_dangerous_commands."""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath, PureWindowsPath
from typing import Sequence
from urllib.parse import urlparse


def is_dangerous_command_windows(command: Sequence[str]) -> bool:
    return is_dangerous_powershell(command) or is_dangerous_cmd(command) or is_direct_gui_launch(command)


def is_dangerous_powershell(command: Sequence[str]) -> bool:
    if not command or not _is_powershell_executable(command[0]):
        return False
    parsed = parse_powershell_invocation_for_danger(command[1:])
    return parsed is not None and is_dangerous_powershell_words(parsed)


def is_dangerous_powershell_words(words: Sequence[str]) -> bool:
    tokens_lc = [token.strip("'\"").lower() for token in words]
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
    raw = exe.rstrip("/\\")
    if not raw:
        return None
    name = PureWindowsPath(raw).name if "\\" in raw else PurePosixPath(raw).name
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
