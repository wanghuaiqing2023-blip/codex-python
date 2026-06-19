# codex-exec src/cli.rs status

Status: complete_candidate

Rust owner: `codex-exec`
Rust module: `codex/codex-rs/exec/src/cli.rs`
Python module: `pycodex/exec/cli.py`
Python tests: `tests/test_exec_cli.py`

## Behavior Contract

Rust `src/cli.rs` owns the non-interactive `codex exec` command-line shape:

- root prompt parsing with optional stdin sentinel handled by later run logic
- global strict/config/isolation/session flags
- shared CLI options marked global for selected subcommands
- hidden `--full-auto` compatibility warning and conflict with dangerous bypass
- output schema, JSONL, color, last-message file, model/profile/sandbox/options
- `resume` subcommand positional reinterpretation when `--last` is used
- `resume` image/prompt flags
- `review` target selection, conflict rules, and commit title requirement

## Python Mapping

`pycodex.exec.cli` mirrors the Rust module as a lightweight standard-library
parser. It owns `ExecCli`, `ResumeArgs`, `ReviewArgs`, `Color`,
`ExecCliParseError`, and `parse_exec_args`, and keeps downstream runtime,
stdin prompt expansion, config bootstrapping, and review request construction
in sibling `pycodex.exec` modules.

## Evidence

- Rust source inspected: `codex/codex-rs/exec/src/cli.rs`.
- Rust tests inspected: `codex/codex-rs/exec/src/cli_tests.rs`.
- Python coverage inspected: `tests/test_exec_cli.py`.
- The four Rust local tests are mirrored by Python coverage:
  `test_resume_parses_prompt_after_global_flags`,
  `test_resume_accepts_output_flags_after_subcommand`,
  `test_parses_config_isolation_flags`, and
  `test_removed_full_auto_flag_reports_migration_path`.
- Additional Python coverage records shared-option, review-conflict, profile,
  sandbox, dangerous-bypass, root config override, and resume image behavior.
- Validation deferred by current crate automation rule until `codex-exec`
  functional module code is complete.
