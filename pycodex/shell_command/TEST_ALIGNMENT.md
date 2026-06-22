# pycodex.shell_command Test Alignment

Updated: 2026-06-15

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
| `codex/codex-rs/shell-command/src/command_safety/powershell_parser.rs` | 2 | `shell.powershell_parser` | `tests/test_shell_command_safety.py` |
| `codex/codex-rs/shell-command/src/shell_detect.rs` | 0 | `shell.shell_detect` | `tests/test_shell_command_shell_detect.py` |

## Current Python Test Files

| Python test file | Current role | Source status |
|---|---|---|
| `tests/test_shell_command_parse_command.py` | parse/display/bash/powershell command parsing coverage | Rust-source comments cover selected `parse_command.rs` anchors plus `bash.rs` plain-command and heredoc-prefix behavior |
| `tests/test_shell_command_safety.py` | safe/dangerous command classification coverage | First Rust-source comment batch added for selected safe/dangerous/Windows safety anchors |
| `tests/test_shell_command_shell_detect.py` | shell type detection coverage | Rust-source inferred coverage for `shell_detect.rs` |

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

## 2026-06-15 Module alignment: shell_detect

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.shell_detect` | `shell_detect.rs::detect_shell_type` | `tests/test_shell_command_shell_detect.py` |

## 2026-06-15 Module alignment: bash

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.bash_lc_parsing` | `bash.rs::tests::plain_commands_*`; `bash.rs::tests::accepts_*`; `bash.rs::tests::rejects_*` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_bash_plain_commands_*` |
| `shell.bash_lc_parsing` | `bash.rs::tests::parse_shell_lc_single_command_prefix_supports_heredoc`; selected heredoc rejection behavior | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_bash_single_command_prefix_*` |

## 2026-06-15 Module alignment: powershell

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_parsing` | `powershell.rs::tests::extracts_basic_powershell_command`; `powershell.rs::tests::extracts_lowercase_flags`; `powershell.rs::tests::extracts_full_path_powershell_command`; `powershell.rs::tests::extracts_with_noprofile_and_alias` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_powershell_wrapper_extracts_script` |
| `shell.powershell_parsing` | `powershell.rs::prefix_powershell_script_with_utf8` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_powershell_utf8_prefix_is_added_once` |
| `shell.powershell_parsing` | `powershell.rs::tests::parses_plain_powershell_commands`; `powershell.rs::tests::parses_multiple_plain_powershell_commands` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_powershell_plain_commands_parse_simple_ast_surface` |

## 2026-06-15 Module alignment: powershell_parser

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_parser` | `powershell_parser.rs::tests::parser_process_handles_multiple_requests` | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_powershell_parser_handles_simple_command_requests` |
| `shell.powershell_parser` | `powershell_parser.rs::tests::parser_process_rejects_stop_parsing_forms` | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_powershell_parser_rejects_stop_parsing_forms` |
| `shell.powershell_parser` | `powershell_parser.rs::encode_powershell_base64`; `PowershellParserResponse::into_outcome` | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_powershell_parser_encoding_and_response_validation` |

## 2026-06-15 Module alignment: windows_safe_commands

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_safe_commands.rs::tests::recognizes_safe_powershell_wrappers`; `windows_safe_commands.rs::tests::accepts_full_path_powershell_invocations` | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_wrapper_forms_follow_platform_cfg` |
| `shell.powershell_safety` | `windows_safe_commands.rs::tests::recognizes_safe_powershell_wrappers`; `windows_safe_commands.rs::tests::rejects_powershell_commands_with_side_effects` | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_wrapper_rejections` |

## 2026-06-15 Module alignment: windows_dangerous_commands

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.powershell_safety` | `windows_dangerous_commands.rs` URL launch tests for PowerShell, CMD, browsers, Explorer, mshta, and rundll32 | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_dangerous_heuristics_are_platform_independent` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs` CMD start URL string variants | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_cmd_start_url_string_variants_are_dangerous` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs` PowerShell/CMD force-delete and benign path tests | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_force_delete_heuristics_are_platform_independent` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs` PowerShell rm alias and benign force-separate-command tests | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_powershell_rm_alias_force_and_benign_force_segment` |
| `shell.powershell_safety` | `windows_dangerous_commands.rs` chained/no-space CMD delete and PowerShell chained/comma delete tests | `tests/test_shell_command_safety.py::ShellCommandSafetyTests.test_windows_chained_delete_heuristics_are_platform_independent` |

## 2026-06-15 Module alignment: parse_command display-summary read variants

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.display_summary` | `parse_command.rs::tests::supports_cat`; `parse_command.rs::tests::zsh_lc_supports_cat`; `parse_command.rs::tests::supports_bat`; `parse_command.rs::tests::supports_batcat`; `parse_command.rs::tests::supports_less`; `parse_command.rs::tests::supports_more` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_read_file_viewer_variants` |
| `shell.display_summary` | `parse_command.rs::tests::supports_head_n`; `parse_command.rs::tests::supports_head_file_only`; `parse_command.rs::tests::supports_tail_n_plus`; `parse_command.rs::tests::supports_tail_n_last_lines`; `parse_command.rs::tests::supports_tail_file_only` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_head_tail_variants` |

## 2026-06-15 Module alignment: parse_command display-summary list variants

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.display_summary` | `parse_command.rs::tests::supports_ls_with_pipe`; `parse_command.rs::tests::supports_eza_exa_tree_du` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_list_file_viewer_variants` |
| `shell.display_summary` | `parse_command.rs::tests::supports_rg_files_with_path_and_pipe`; `parse_command.rs::tests::supports_rg_files_then_head` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_rg_files_pipeline_variants` |

## 2026-06-15 Module alignment: parse_command display-summary search variants

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.display_summary` | `parse_command.rs::tests::rg_files_with_matches_flags_are_search`; `parse_command.rs::tests::rg_with_equals_style_flags` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_rg_search_variants` |
| `shell.display_summary` | `parse_command.rs::tests::supports_ag_ack_pt_rga`; `parse_command.rs::tests::ag_ack_pt_files_with_matches_flags_are_search` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_ag_ack_pt_search_variants` |
| `shell.display_summary` | `parse_command.rs::tests::supports_grep_recursive_current_dir`; `parse_command.rs::tests::supports_grep_query_with_slashes_not_shortened`; `parse_command.rs::tests::supports_grep_weird_backtick_in_query` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_grep_search_variants` |

## 2026-06-15 Module alignment: parse_command display-summary formatting/read pipelines

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.display_summary` | `parse_command.rs::tests::cat_with_double_dash_and_sed_ranges`; `parse_command.rs::tests::bin_bash_lc_sed`; `parse_command.rs::tests::bin_zsh_lc_sed` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_sed_and_double_dash_read_variants` |
| `shell.display_summary` | `parse_command.rs::tests::drop_trailing_nl_in_pipeline` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_drops_trailing_nl_pipeline_stage` |

## 2026-06-15 Module alignment: parse_command display-summary finder/path/cd variants

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.display_summary` | `parse_command.rs::tests::ls_with_time_style_and_path`; `parse_command.rs::tests::fd_file_finder_variants`; `parse_command.rs::tests::find_basic_name_filter`; `parse_command.rs::tests::find_type_only_path`; `parse_command.rs::tests::supports_cd_and_rg_files` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_finder_path_and_cd_variants` |

## 2026-06-15 Module alignment: parse_command display-summary miscellaneous variants

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.display_summary` | `parse_command.rs::tests::supports_python_walks_files`; `parse_command.rs::tests::supports_python3_walks_files`; `parse_command.rs::tests::python_without_file_walk_is_unknown`; `parse_command.rs::tests::supports_awk_with_file` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_python_and_awk_misc_variants` |
| `shell.display_summary` | `parse_command.rs::tests::filters_out_printf`; `parse_command.rs::tests::drops_yes_in_pipelines`; `parse_command.rs::tests::preserves_rg_with_spaces`; `parse_command.rs::tests::strips_true_in_sequence`; `parse_command.rs::tests::strips_true_inside_bash_lc` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_small_command_filtering_variants` |
| `shell.display_summary` | `parse_command.rs::tests::head_with_no_space`; `parse_command.rs::tests::tail_with_no_space`; `parse_command.rs::tests::bash_dash_c_pipeline_parsing`; `parse_command.rs::tests::ls_with_glob` | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_misc_shell_syntax_variants` |

## 2026-06-15 Module alignment: parse_command final residual audit

| Contract | Rust source/test | Python target |
|---|---|---|
| `shell.display_summary` | `parse_command.rs` cd-context tests (`cd_then_cat_is_single_read`, `cd_with_double_dash_then_cat_is_read`, `cd_with_multiple_operands_uses_last`, `bash_cd_then_bar_is_same_as_bar`, `bash_cd_then_cat_is_read`) | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_cd_context_residual_variants` |
| `shell.display_summary` | `parse_command.rs` unknown/complex-pipeline tests (`supports_npm_run_build_is_unknown`, `handles_complex_bash_command_head`, `handles_complex_bash_command`, `collapses_pipeline_with_helper_when_later_stage_is_unknown`) | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_unknown_and_complex_pipeline_residual_variants` |
| `shell.display_summary` | `parse_command.rs` residual search tests (`supports_grep_recursive_specific_file`, `supports_egrep_and_fgrep`, `grep_files_with_matches_flags_are_search`, `grep_with_query_and_path`, `supports_single_string_script_with_cd_and_pipe`) | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_search_residual_variants` |
| `shell.display_summary` | `parse_command.rs` small-formatting helper tests (`small_formatting_always_true_commands`, `awk_behavior`, `head_behavior`, `tail_behavior`, `sed_behavior`, `empty_tokens_is_not_small`) | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_small_formatting_residual_variants` |
| `shell.display_summary` | `parse_command.rs` residual read tests (`supports_nl_then_sed_reading`, `supports_sed_n`, `supports_sed_n_then_nl_as_search`, `shorten_path_on_windows`) | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_read_residual_variants` |
| `shell.display_summary` | `parse_command.rs` PowerShell wrapper stripping tests (`powershell_command_is_stripped`, `pwsh_with_noprofile_and_c_alias_is_stripped`, `powershell_with_path_is_stripped`) | `tests/test_shell_command_parse_command.py::ShellCommandParseCommandTests.test_display_summary_powershell_wrapper_residual_variants` |

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

No known remaining `codex-shell-command` module-scoped migration target is open.
Future work should only be added when upstream Rust changes introduce new tests
or behavior contracts.

## Known Gaps To Review

- Rust `parse_command.rs` broad display-summary coverage is now represented by
  read/viewer/range, list-files, search, formatting/read pipeline,
  finder/path/cd, miscellaneous, and final residual-audit Python parity tests.
- Rust `bash.rs` plain-command parsing and single-heredoc-prefix behavior are
  now represented by focused Python parity tests. Remaining crate gaps should be
  tracked through the higher-level `parse_command.rs` display-summary behavior
  and PowerShell AST compatibility surface, not by reopening already-covered
  Bash word-only parsing.
- Rust `powershell.rs` is now represented by a dedicated
  `pycodex/shell_command/powershell.py` module. Full PowerShell AST subprocess
  parity remains scoped to `powershell_parser.rs`, not this wrapper module.
- Rust `powershell_parser.rs` is now represented by
  `pycodex/shell_command/powershell_parser.py`. Python intentionally keeps the
  no-subprocess compatibility design, so the aligned behavior boundary is
  simple command extraction, unsupported handling, UTF-16LE base64 encoding, and
  response outcome validation.
- Rust `windows_safe_commands.rs` safe wrapper recognition, read-only pipeline,
  git rejection, constant/dynamic argument, full-path wrapper, and opaque-flag
  rejection behavior is now represented in Python parity tests.
- Rust `windows_dangerous_commands.rs` URL launch, force delete, CMD chaining,
  PowerShell chaining, aliases, and benign counterexamples are now represented
  in Python parity tests.
- Rust Windows safety tests are extensive. Python currently keeps platform
  behavior partly conditional on `os.name`, so parity must distinguish
  cross-platform heuristics from Windows-only behavior.
