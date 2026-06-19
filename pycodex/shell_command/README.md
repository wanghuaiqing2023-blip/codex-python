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
| `src/powershell.rs` | `pycodex/shell_command/powershell.py`; `pycodex/shell_command/parse_command.py`; `pycodex/shell_command/command_safety.py` | PowerShell command extraction, UTF-8 output prefixing, executable discovery helpers, and conservative plain-command parsing |
| `src/bash.rs` | `pycodex/shell_command/parse_command.py` | Bash `-lc` word-only parsing, conservative rejection boundaries, and single heredoc-prefix support |
| `src/shell_detect.rs` | `pycodex/shell_command/shell_detect.py` | shell detection by exact name and recursive file stem |
| `src/command_safety/is_safe_command.rs` | `pycodex/shell_command/command_safety.py` | known-safe command classification |
| `src/command_safety/is_dangerous_command.rs` | `pycodex/shell_command/command_safety.py` | dangerous command classification |
| `src/command_safety/windows_safe_commands.rs` | `pycodex/shell_command/command_safety.py` | Windows and PowerShell safe command classification |
| `src/command_safety/windows_dangerous_commands.rs` | `pycodex/shell_command/command_safety.py` | Windows and PowerShell dangerous command classification |
| `src/command_safety/powershell_parser.rs` | `pycodex/shell_command/powershell_parser.py` | PowerShell AST parser semantic boundary; Python uses a conservative compatibility shim instead of a subprocess parser |

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
shell.shell_detect
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

No code movement is required because the current Python package already carries
the relevant implementation files:

```text
pycodex/shell_command/command_safety.py
pycodex/shell_command/parse_command.py
pycodex/shell_command/powershell.py
pycodex/shell_command/powershell_parser.py
pycodex/shell_command/shell_detect.py
```

`codex-shell-command` is strict complete as of 2026-06-15. The Rust module
surfaces listed above are covered by Rust-derived Python parity tests, including
the final `parse_command.rs` residual display-summary audit. Focused validation
passed with `84 passed, 144 subtests passed` across shell-command related tests.
