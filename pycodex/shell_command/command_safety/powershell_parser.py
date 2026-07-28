"""Conservative PowerShell parser compatibility surface.

Rust counterpart:
``codex/codex-rs/shell-command/src/command_safety/powershell_parser.rs``.

The Rust crate keeps a cached PowerShell subprocess and asks the real
PowerShell AST parser for argv-like commands. The Python port intentionally does
not spawn a long-lived parser process; instead it exposes the same semantic
boundary and returns commands only for the simple, word-only surface that the
standard library can parse conservatively.
"""

from __future__ import annotations

import base64
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class PowershellParseKind(str, Enum):
    COMMANDS = "commands"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True)
class PowershellParseOutcome:
    kind: PowershellParseKind
    commands: tuple[tuple[str, ...], ...] = ()

    @classmethod
    def commands_outcome(cls, commands: Sequence[Sequence[str]]) -> "PowershellParseOutcome":
        return cls(PowershellParseKind.COMMANDS, tuple(tuple(command) for command in commands))

    @classmethod
    def unsupported(cls) -> "PowershellParseOutcome":
        return cls(PowershellParseKind.UNSUPPORTED)

    @classmethod
    def failed(cls) -> "PowershellParseOutcome":
        return cls(PowershellParseKind.FAILED)


@dataclass(frozen=True)
class PowershellParserResponse:
    id: int
    status: str
    commands: tuple[tuple[str, ...], ...] | None = None

    def into_outcome(self) -> PowershellParseOutcome:
        if self.status == "ok":
            commands = self.commands
            if commands and all(command and all(word for word in command) for command in commands):
                return PowershellParseOutcome.commands_outcome(commands)
            return PowershellParseOutcome.unsupported()
        if self.status == "unsupported":
            return PowershellParseOutcome.unsupported()
        return PowershellParseOutcome.failed()


def encode_powershell_base64(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def parse_with_powershell_ast(executable: str, script: str) -> PowershellParseOutcome:
    del executable
    commands = _parse_simple_powershell_script(script)
    if commands is None:
        return PowershellParseOutcome.unsupported()
    return PowershellParseOutcome.commands_outcome(commands)


def try_parse_powershell_ast_commands(executable: str, script: str) -> list[list[str]] | None:
    outcome = parse_with_powershell_ast(executable, script)
    if outcome.kind != PowershellParseKind.COMMANDS:
        return None
    return [list(command) for command in outcome.commands]


def _parse_simple_powershell_script(script: str) -> list[list[str]] | None:
    if _powershell_script_has_unsupported_construct(script):
        return None
    tokens = _powershell_split(script)
    if tokens is None:
        return None
    commands = _split_powershell_commands(tokens)
    return commands or None


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


__all__ = [
    "PowershellParseKind",
    "PowershellParseOutcome",
    "PowershellParserResponse",
    "encode_powershell_base64",
    "parse_with_powershell_ast",
    "try_parse_powershell_ast_commands",
]
