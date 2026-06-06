# pycodex.shell_command Test Alignment

Updated: 2026-06-06

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
| `tests/test_shell_command_parse_command.py` | parse/display/bash/powershell command parsing coverage | First Rust-source comment batch added for selected `parse_command.rs` and `bash.rs` anchors |
| `tests/test_shell_command_safety.py` | safe/dangerous command classification coverage | First Rust-source comment batch added for selected safe/dangerous/Windows safety anchors |

## Completed Source Comment Batch

The first small batch of Rust-source comments has been added to
`tests/test_shell_command_parse_command.py`. This does not make the whole
`parse_command.rs` contract complete; it only anchors the already-present
Python tests to their Rust source evidence.

Completed anchors:

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.parse_command` | `parse_command.rs::tests::git_status_is_unknown` | `test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_shlex_join_and_unknown_commands` |
| `shell.parse_command` | `parse_command.rs::tests::supports_git_grep_and_ls_files` | `test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_supports_git_grep_and_ls_files` |
| `shell.parse_command` | `parse_command.rs::tests::keeps_mutating_xargs_pipeline` | `test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_collapses_mutating_xargs_pipeline_to_unknown` |
| `shell.bash_lc_parsing` | `bash.rs::tests::parse_shell_lc_single_command_prefix_supports_heredoc` | `test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_bash_single_command_prefix_supports_heredoc` |

## Completed Source Comment Batch: command safety

The first small batch of Rust-source comments has also been added to
`tests/test_shell_command_safety.py`. A few missing assertions already present
in the Rust inline tests were added at the same time.

Completed anchors:

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.command_safety` | `is_safe_command.rs::tests::known_safe_examples` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_known_safe_exec_examples` |
| `shell.command_safety` | `is_safe_command.rs::tests::cargo_check_is_not_safe` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_unsafe_exec_examples` |
| `shell.command_safety` | `is_safe_command.rs::tests::unknown_or_partial` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_unsafe_exec_examples` |
| `shell.command_safety` | `is_safe_command.rs::tests::base64_output_options_are_unsafe` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_unsafe_exec_examples` |
| `shell.command_safety` | `is_safe_command.rs::tests::ripgrep_rules` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_unsafe_exec_examples` |
| `shell.command_safety` | selected `is_safe_command.rs` git safety tests | `test_shell_command_safety.py::ShellCommandSafetyTests.test_git_global_and_subcommand_safety_rules` |
| `shell.command_safety` | `is_safe_command.rs::tests::bash_lc_safe_examples`; `is_safe_command.rs::tests::bash_lc_safe_examples_with_operators`; `is_safe_command.rs::tests::bash_lc_unsafe_examples` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_bash_lc_safe_and_unsafe_sequences` |
| `shell.dangerous_command` | `is_dangerous_command.rs::tests::rm_rf_is_dangerous`; `is_dangerous_command.rs::tests::rm_f_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_dangerous_command_detection` |
| `shell.powershell_safety` | selected `windows_dangerous_commands.rs` URL/force-delete tests | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_dangerous_heuristics_are_platform_independent` |
| `shell.powershell_safety` | selected `windows_safe_commands.rs` safelist/rejection tests | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_safelist_matches_platform_cfg` |

## 2026-06-06 Additional Batch: PowerShell read-only safelist

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_safe_commands.rs::tests::allows_read_only_pipelines_and_git_usage` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_read_only_pipelines_and_git_usage_follow_platform_cfg` |

## 2026-06-06 Additional Batch: PowerShell git global overrides

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_safe_commands.rs::tests::rejects_git_global_override_options` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_rejects_git_global_override_options` |

## 2026-06-06 Additional Batch: PowerShell git subcommand side effects

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_safe_commands.rs::tests::rejects_git_subcommand_options_with_side_effects` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_rejects_git_subcommand_options_with_side_effects` |

## 2026-06-06 Additional Batch: PowerShell constant and dynamic arguments

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_safe_commands.rs::tests::accepts_constant_expression_arguments` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_constant_arguments_and_dynamic_rejection_follow_platform_cfg` |
| `shell.powershell_safety` | `windows_safe_commands.rs::tests::rejects_dynamic_arguments` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_constant_arguments_and_dynamic_rejection_follow_platform_cfg` |

## 2026-06-06 Additional Batch: Windows URL launch danger

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::powershell_start_process_url_with_trailing_semicolon_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_dangerous_heuristics_are_platform_independent` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::cmd_start_with_url_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_dangerous_heuristics_are_platform_independent` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::explorer_with_directory_is_not_flagged` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_dangerous_heuristics_are_platform_independent` |

## 2026-06-06 Additional Batch: CMD start URL variants

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::cmd_start_url_single_string_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_cmd_start_url_string_variants_are_dangerous` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::cmd_start_quoted_url_single_string_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_cmd_start_url_string_variants_are_dangerous` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::cmd_start_title_then_url_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_cmd_start_url_string_variants_are_dangerous` |

## 2026-06-06 Additional Batch: Windows force-delete danger

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | selected `windows_dangerous_commands.rs` PowerShell force-delete tests | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_force_delete_heuristics_are_platform_independent` |
| `shell.powershell_safety` | selected `windows_dangerous_commands.rs` CMD force-delete tests | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_force_delete_heuristics_are_platform_independent` |

## 2026-06-06 Additional Batch: PowerShell rm alias force-delete

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::powershell_rm_alias_force_is_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_rm_alias_force_and_benign_force_segment` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs::tests::powershell_benign_force_separate_command_is_not_dangerous` | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_rm_alias_force_and_benign_force_segment` |

## 2026-06-06 Additional Batch: Windows chained delete danger

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | selected `windows_dangerous_commands.rs` CMD chained/no-space delete tests | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_chained_delete_heuristics_are_platform_independent` |
| `shell.powershell_safety` | selected `windows_dangerous_commands.rs` PowerShell chained/comma delete tests | `test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_chained_delete_heuristics_are_platform_independent` |

## Next Migration Targets

Continue with Rust tests that are already represented in Python and add source
comments or missing assertions in small batches.

Suggested next batch:

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.parse_command` | remaining `parse_command.rs` display-summary tests | `tests/test_shell_command_parse_command.py` |
| `shell.bash_lc_parsing` | remaining `bash.rs` parser acceptance/rejection tests | `tests/test_shell_command_parse_command.py` |
| `shell.powershell_safety` | broader `windows_safe_commands.rs` and `windows_dangerous_commands.rs` coverage | `tests/test_shell_command_safety.py` |

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
