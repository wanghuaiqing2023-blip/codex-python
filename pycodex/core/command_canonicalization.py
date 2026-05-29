"""Command argv canonicalization for approval-cache matching.

Ported from ``codex/codex-rs/core/src/command_canonicalization.rs``.
"""

from __future__ import annotations

from collections.abc import Sequence

from pycodex.shell_command import extract_bash_command, extract_powershell_command, parse_shell_lc_plain_commands

CANONICAL_BASH_SCRIPT_PREFIX = "__codex_shell_script__"
CANONICAL_POWERSHELL_SCRIPT_PREFIX = "__codex_powershell_script__"


def canonicalize_command_for_approval(command: Sequence[str]) -> list[str]:
    """Canonicalize command argv for stable approval-cache matching."""

    if isinstance(command, str):
        raise TypeError("command must be a sequence of strings")
    command = tuple(command)
    if any(not isinstance(token, str) for token in command):
        raise TypeError("command tokens must be strings")

    plain_commands = parse_shell_lc_plain_commands(command)
    if plain_commands is not None and len(plain_commands) == 1:
        return list(plain_commands[0])

    bash = extract_bash_command(command)
    if bash is not None:
        shell_mode = command[1] if len(command) > 1 else ""
        return [CANONICAL_BASH_SCRIPT_PREFIX, shell_mode, bash[1]]

    powershell = extract_powershell_command(command)
    if powershell is not None:
        return [CANONICAL_POWERSHELL_SCRIPT_PREFIX, powershell[1]]

    return list(command)


__all__ = [
    "CANONICAL_BASH_SCRIPT_PREFIX",
    "CANONICAL_POWERSHELL_SCRIPT_PREFIX",
    "canonicalize_command_for_approval",
]
