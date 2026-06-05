# pycodex.shell_command Test Alignment

Updated: 2026-06-05

This file records the local test-source map for the Python counterpart of the
Rust `codex-shell-command` crate.

It is not a test result report. It is a guide for where Python parity tests
should come from.

## Rule

Prefer Rust-derived Python parity tests before adding AI-inferred edge cases.

Python tests touching this package should eventually carry source comments:

```python
# Source: rust_test_migrated
# Rust crate: codex-shell-command
# Rust module: src/parse_command.rs
# Rust test: tests::git_status_is_unknown
# Contract: shell.parse_command
```

## Rust Test Inventory

| Rust source | Rust test count | Contract area | Python target |
|---|---:|---|---|
| `codex/codex-rs/shell-command/src/parse_command.rs` | 79 | `shell.parse_command`; `shell.display_summary` | `tests/test_shell_command_parse_command.py` |
| `codex/codex-rs/shell-command/src/bash.rs` | 29 | `shell.bash_lc_parsing`; `shell.parse_command` | `tests/test_shell_command_parse_command.py` |
| `codex/codex-rs/shell-command/src/powershell.rs` | 6 | `shell.powershell_parsing`; `shell.parse_command` | `tests/test_shell_command_parse_command.py` |
| `codex/codex-rs/shell-command/src/command_safety/is_safe_command.rs` | 19 | `shell.command_safety` | `tests/test_shell_command_safety.py` |
| `codex/codex-rs/shell-command/src/command_safety/is_dangerous_command.rs` | 3 | `shell.dangerous_command` | `tests/test_shell_command_safety.py` |
| `codex/codex-rs/shell-command/src/command_safety/windows_safe_commands.rs` | 10 | `shell.powershell_safety`; `shell.command_safety` | `tests/test_shell_command_safety.py` |
| `codex/codex-rs/shell-command/src/command_safety/windows_dangerous_commands.rs` | 39 | `shell.powershell_safety`; `shell.dangerous_command` | `tests/test_shell_command_safety.py` |
| `codex/codex-rs/shell-command/src/command_safety/powershell_parser.rs` | 2 | `shell.powershell_parser` | no direct Python target; compatibility shim only |

## Current Python Test Files

| Python test file | Current role | Source status |
|---|---|---|
| `tests/test_shell_command_parse_command.py` | parse/display/bash/powershell command parsing coverage | Rust-derived behavior appears present, but tests lack source comments |
| `tests/test_shell_command_safety.py` | safe/dangerous command classification coverage | Rust-derived behavior appears present, but tests lack source comments |

## First Migration Targets

Start with Rust tests that are already represented in Python and add source
comments or missing assertions in small batches.

Suggested first batch:

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.parse_command` | `parse_command.rs::tests::git_status_is_unknown` | `test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_shlex_join_and_unknown_commands` |
| `shell.parse_command` | `parse_command.rs::tests::supports_git_grep_and_ls_files` | `test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_supports_git_grep_and_ls_files` |
| `shell.parse_command` | `parse_command.rs::tests::keeps_mutating_xargs_pipeline` | `test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_collapses_mutating_xargs_pipeline_to_unknown` |
| `shell.bash_lc_parsing` | `bash.rs::tests::parse_shell_lc_single_command_prefix_supports_heredoc` | `test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_bash_single_command_prefix_supports_heredoc` |
| `shell.command_safety` | `is_safe_command.rs::tests::known_safe_examples` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_known_safe_exec_examples` |
| `shell.command_safety` | `is_safe_command.rs::tests::cargo_check_is_not_safe` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_unsafe_exec_examples` |
| `shell.dangerous_command` | `is_dangerous_command.rs::tests::rm_rf_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_dangerous_command_detection` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::powershell_start_process_url_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_dangerous_heuristics_are_platform_independent` |

## Known Gaps To Review

- Rust `parse_command.rs` has broad display-summary coverage that is only
  partially represented in Python tests.
- Rust `bash.rs` has many rejection tests for substitutions, unsupported
  operators, heredocs, herestrings, and parse-error positions. Python has only a
  small subset.
- Rust Windows safety tests are extensive. Python currently keeps platform
  behavior partly conditional on `os.name`, so parity must distinguish
  cross-platform heuristics from Windows-only behavior.
- Rust `powershell_parser.rs` uses a PowerShell AST subprocess parser. Python
  intentionally avoids this dependency; that area should be treated as a
  compatibility shim unless core behavior requires deeper parity.
