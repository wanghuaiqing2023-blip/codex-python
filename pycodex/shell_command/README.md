# pycodex.shell_command

This package contains the Python counterpart for the Rust `codex-shell-command`
crate.

## Rust Counterpart

```text
Rust crate: codex-shell-command
Rust path: codex/codex-rs/shell-command
Cargo role: command parsing and shell command safety helpers
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/shell_command/__init__.py`; `pycodex/shell_command/command_safety.py`; `pycodex/shell_command/parse_command.py` | crate public surface and re-exports |
| `src/parse_command.rs` | `pycodex/shell_command/parse_command.py` | command token parsing and display summary behavior |
| `src/powershell.rs` | `pycodex/shell_command/parse_command.py`; `pycodex/shell_command/command_safety.py` | PowerShell command extraction and command parsing support |
| `src/bash.rs` | `pycodex/shell_command/parse_command.py` | shell command parsing support where represented in Python |
| `src/shell_detect.rs` | not yet assigned | shell detection behavior, pending review |
| `src/command_safety/is_safe_command.rs` | `pycodex/shell_command/command_safety.py` | known-safe command classification |
| `src/command_safety/is_dangerous_command.rs` | `pycodex/shell_command/command_safety.py` | dangerous command classification |
| `src/command_safety/windows_safe_commands.rs` | `pycodex/shell_command/command_safety.py` | Windows and PowerShell safe command classification |
| `src/command_safety/windows_dangerous_commands.rs` | `pycodex/shell_command/command_safety.py` | Windows and PowerShell dangerous command classification |
| `src/command_safety/powershell_parser.rs` | compatibility shim only | PowerShell AST subprocess parser; Python avoids the subprocess parser dependency |

## Alignment Unit

The regular acceptance unit is a module-scoped behavior contract.

For this package, the initial contracts are:

```text
shell.command_safety
shell.dangerous_command
shell.parse_command
shell.display_summary
shell.powershell_safety
shell.bash_lc_parsing
```

Function names such as `is_known_safe_command`, `is_dangerous_command`,
`parse_command`, and `summarize_main_tokens` are local anchors. They are useful
for comparison, but the package should be validated at the behavior-contract
level rather than by mechanically matching every Rust helper.

## Rust Test Sources

Primary Rust test sources should be collected from:

```text
codex/codex-rs/shell-command/src/lib.rs
codex/codex-rs/shell-command/src/parse_command.rs
codex/codex-rs/shell-command/src/powershell.rs
codex/codex-rs/shell-command/src/bash.rs
codex/codex-rs/shell-command/src/command_safety/is_safe_command.rs
codex/codex-rs/shell-command/src/command_safety/is_dangerous_command.rs
codex/codex-rs/shell-command/src/command_safety/windows_safe_commands.rs
codex/codex-rs/shell-command/src/command_safety/windows_dangerous_commands.rs
codex/codex-rs/shell-command/src/command_safety/powershell_parser.rs
```

See `TEST_ALIGNMENT.md` in this directory for the current local test-source
inventory.

If Rust tests are inline under `#[cfg(test)] mod tests`, Python parity tests
should record the original Rust test name in source comments.

## Python Test Source Comment Pattern

When tests are added or touched, prefer:

```python
# Source: rust_test_migrated
# Rust crate: codex-shell-command
# Rust module: src/parse_command.rs
# Rust test: tests::example_test_name
# Contract: shell.parse_command
```

If a test is inferred from Rust source rather than directly migrated:

```python
# Source: rust_source_inferred
# Rust crate: codex-shell-command
# Rust module: src/lib.rs
# Rust item: is_known_safe_command
# Contract: shell.command_safety
```

## Current Movement Status

No code movement is required for the first alignment pass because the current
Python package already exists and already carries the relevant implementation
files:

```text
pycodex/shell_command/command_safety.py
pycodex/shell_command/parse_command.py
```

The next useful work is to map Rust tests to Python parity tests for this
package before moving to a more coupled package.
