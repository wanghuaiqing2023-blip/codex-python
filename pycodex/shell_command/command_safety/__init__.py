"""Rust-aligned command-safety module and public re-exports."""

from .is_dangerous_command import (
    command_might_be_dangerous,
    executable_name_lookup_key,
    find_git_subcommand,
    is_dangerous_powershell_words,
)
from .is_safe_command import (
    is_known_safe_command,
    is_safe_git_command,
    is_safe_powershell_words,
    is_safe_to_call_with_exec,
)
from .powershell_parser import try_parse_powershell_ast_commands

__all__ = [
    "command_might_be_dangerous",
    "executable_name_lookup_key",
    "find_git_subcommand",
    "is_dangerous_powershell_words",
    "is_known_safe_command",
    "is_safe_git_command",
    "is_safe_powershell_words",
    "is_safe_to_call_with_exec",
    "try_parse_powershell_ast_commands",
]
