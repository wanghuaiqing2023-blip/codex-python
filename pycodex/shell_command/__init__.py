"""Command parsing and safety utilities shared across the Python port."""

from .parse_command import (
    extract_bash_command,
    extract_shell_command,
    parse_command,
    parse_command_impl,
    parse_shell_lc_plain_commands,
    parse_shell_lc_single_command_prefix,
    shlex_join,
)
from .powershell import (
    UTF8_OUTPUT_PREFIX,
    extract_powershell_command,
    parse_powershell_command_into_plain_commands,
    prefix_powershell_script_with_utf8,
    try_find_powershell_executable_blocking,
    try_find_pwsh_executable_blocking,
)
from .shell_detect import detect_shell_type
from .command_safety import (
    command_might_be_dangerous,
    executable_name_lookup_key,
    find_git_subcommand,
    is_dangerous_powershell_words,
    is_known_safe_command,
    is_safe_git_command,
    is_safe_powershell_words,
)

__all__ = [
    "UTF8_OUTPUT_PREFIX",
    "extract_bash_command",
    "extract_powershell_command",
    "extract_shell_command",
    "parse_command",
    "parse_command_impl",
    "parse_powershell_command_into_plain_commands",
    "parse_shell_lc_plain_commands",
    "parse_shell_lc_single_command_prefix",
    "prefix_powershell_script_with_utf8",
    "shlex_join",
    "try_find_powershell_executable_blocking",
    "try_find_pwsh_executable_blocking",
    "detect_shell_type",
    "command_might_be_dangerous",
    "executable_name_lookup_key",
    "find_git_subcommand",
    "is_dangerous_powershell_words",
    "is_known_safe_command",
    "is_safe_git_command",
    "is_safe_powershell_words",
]
