# 2026-06-02: apply TASK_ID parser parity

## Upstream slice

- Graph/source lookup for the top-level CLI `apply` command points to `codex/codex-rs/cli/src/main.rs`, where `Subcommand::Apply(ApplyCommand)` is parsed as a normal top-level command.
- The Rust command uses a required task id positional argument for applying a Codex task diff.

## Python slice

- `_parse_apply_args` now raises `CliParseError("apply requires TASK_ID.")` when `codex apply` is invoked without a task id.
- Help flags still pass through unchanged, preserving `codex apply --help`.
- Existing support for `--` before a dash-prefixed task id is unchanged.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_requires_task_id tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_rejects_unknown_flag tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_accepts_dash_prefixed_task_id_via_end_marker tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_rejects_extra_after_end_marker tests.test_cli_parser.TopLevelCliParserTests.test_apply_alias_maps_to_canonical_name`
- `python -m unittest tests.test_exec_run tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_requires_task_id tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_rejects_unknown_flag tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_accepts_dash_prefixed_task_id_via_end_marker tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_rejects_extra_after_end_marker tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_prepares_noninteractive_plan tests.test_cli_parser.TopLevelCliParserTests.test_main_resume_with_exec_fallback_uses_noninteractive_resume_exec tests.test_cli_parser.TopLevelCliParserTests.test_main_fork_with_exec_fallback_uses_noninteractive_fork_exec`

Both targeted runs pass.

## Known gaps

- The remote cloud task/diff backend remains outside the core exec runtime target; this note only records parser-level parity for the top-level command shape.
