import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("bash", "extract_bash_command"),
        ("command_safety", "__all__"),
        ("command_safety.is_dangerous_command", "command_might_be_dangerous"),
        (
            "command_safety.is_dangerous_command.windows_dangerous_commands",
            "is_dangerous_command_windows",
        ),
        ("command_safety.is_safe_command", "is_known_safe_command"),
        ("command_safety.powershell_parser", "PowershellParseOutcome"),
        ("command_safety.windows_safe_commands", "is_safe_command_windows"),
        ("parse_command", "parse_command"),
        ("powershell", "extract_powershell_command"),
        ("shell_detect", "ShellType"),
    ],
)
def test_shell_command_item_has_rust_aligned_owner(
    module_name: str,
    symbol: str,
) -> None:
    """Rust source: codex-shell-command production module graph from src/lib.rs."""
    module = importlib.import_module(f"pycodex.shell_command.{module_name}")
    item = getattr(module, symbol)
    if callable(item):
        assert item.__module__ == module.__name__
