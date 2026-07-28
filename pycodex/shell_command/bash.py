"""Bash command extraction and conservative word-only parsing."""

from __future__ import annotations

import re
import shlex
from typing import Sequence

from .shell_detect import ShellType, detect_shell_type

CONNECTORS = {"&&", "||", "|", ";"}


def extract_bash_command(command: Sequence[str]) -> tuple[str, str] | None:
    if len(command) != 3:
        return None
    shell, flag, script = command
    if flag not in {"-lc", "-c"} or detect_shell_type(shell) not in {
        ShellType.ZSH,
        ShellType.BASH,
        ShellType.SH,
    }:
        return None
    return shell, script


def parse_shell_lc_plain_commands(command: Sequence[str]) -> list[list[str]] | None:
    """Return word-only commands from a bash/zsh/sh wrapper.

    This mirrors ``bash::parse_shell_lc_plain_commands`` for callers that need a
    safety-oriented argv view. It is intentionally conservative with the
    standard library tokenizer: unsupported shell punctuation, redirection, and
    subshell-like tokens return ``None``.
    """

    extracted = extract_bash_command(command)
    if extracted is None:
        return None
    script = extracted[1]
    tree = try_parse_shell(script)
    return try_parse_word_only_commands_sequence(tree, script)


def _bash_plain_split(script: str) -> list[str] | None:
    lexer = shlex.shlex(script, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return None


def _shlex_split(value: str) -> list[str] | None:
    try:
        return shlex.split(value)
    except ValueError:
        return None


def _contains_unsupported_bash_plain_construct(script: str) -> bool:
    if "`" in script or ";;" in script:
        return True
    if _has_unquoted_single_ampersand(script):
        return True
    if _has_unquoted_dollar_expansion(script):
        return True
    if _has_unquoted_shell_grouping_or_redirection(script):
        return True
    tokens = _bash_plain_split(script)
    if tokens is None or not tokens:
        return True
    if tokens[0] in CONNECTORS or tokens[-1] in CONNECTORS:
        return True
    if tokens[0] == "env":
        tokens = tokens[1:]
        while tokens and _is_assignment_word(tokens[0]):
            tokens = tokens[1:]
        return not tokens
    return _is_assignment_word(tokens[0])


def _has_unquoted_shell_grouping_or_redirection(script: str) -> bool:
    in_single = False
    in_double = False
    escaped = False
    for char in script:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if not in_single and not in_double and char in "(){}<>":
            return True
    return False


def _has_unquoted_single_ampersand(script: str) -> bool:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(script):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "&" and not in_single and not in_double:
            previous_is_amp = index > 0 and script[index - 1] == "&"
            next_is_amp = index + 1 < len(script) and script[index + 1] == "&"
            if not previous_is_amp and not next_is_amp:
                return True
    return False


def _has_unquoted_dollar_expansion(script: str) -> bool:
    in_single = False
    escaped = False
    for index, char in enumerate(script):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'":
            in_single = not in_single
            continue
        if char == "$" and not in_single:
            next_char = script[index + 1] if index + 1 < len(script) else ""
            if next_char == "" or next_char.isspace():
                continue
            return True
    return False


def _is_assignment_word(token: str) -> bool:
    return re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token) is not None


def parse_shell_lc_single_command_prefix(command: Sequence[str]) -> list[str] | None:
    """Return the command words before a single heredoc redirect.

    Upstream uses tree-sitter to accept a single command with ``<<`` and reject
    other redirects, chained commands, substitutions, and assignment prefixes.
    This stdlib port keeps the same conservative surface for exec-policy
    matching.
    """

    extracted = extract_bash_command(command)
    if extracted is None:
        return None
    script = extracted[1]
    if "<<" not in script or "<<<" in script:
        return None

    prefix, rest = script.split("<<", 1)
    prefix = prefix.strip()
    if not prefix or any(marker in prefix for marker in (";", "|", "&", ">", "<", "$", "`", "(", ")", "{", "}")):
        return None

    newline_index = rest.find("\n")
    if newline_index < 0:
        return None
    heredoc_header = rest[:newline_index].strip()
    heredoc_body = rest[newline_index + 1 :]

    delimiter_tokens = _shlex_split(heredoc_header)
    if delimiter_tokens is None or len(delimiter_tokens) != 1:
        return None
    delimiter = delimiter_tokens[0]
    if not delimiter:
        return None

    lines = heredoc_body.splitlines()
    terminator_index = next((index for index, line in enumerate(lines) if line.strip() == delimiter), None)
    if terminator_index is None:
        return None
    if any(line.strip() for line in lines[terminator_index + 1 :]):
        return None

    words = _shlex_split(prefix)
    if words is None or not words:
        return None
    if "=" in words[0]:
        return None
    if _contains_unsupported_shell_token(words):
        return None
    return words


def try_parse_shell(shell_lc_arg: str) -> list[str] | None:
    return _bash_plain_split(shell_lc_arg)


def try_parse_word_only_commands_sequence(
    tree: list[str] | None,
    src: str,
) -> list[list[str]] | None:
    if tree is None or _contains_unsupported_bash_plain_construct(src):
        return None
    if _contains_unsupported_shell_token(tree) or _has_empty_connector_segment(tree):
        return None
    commands = _split_on_connectors(tree)
    return commands if commands and all(commands) else None


def _contains_unsupported_shell_token(tokens: Sequence[str]) -> bool:
    return any(token not in CONNECTORS and any(char in token for char in ("`", "\x00")) for token in tokens)


def _has_empty_connector_segment(tokens: Sequence[str]) -> bool:
    return bool(tokens) and (
        tokens[0] in CONNECTORS
        or tokens[-1] in CONNECTORS
        or any(left in CONNECTORS and right in CONNECTORS for left, right in zip(tokens, tokens[1:]))
    )


def _split_on_connectors(tokens: Sequence[str]) -> list[list[str]]:
    result: list[list[str]] = [[]]
    for token in tokens:
        if token in CONNECTORS:
            result.append([])
        else:
            result[-1].append(token)
    return result
