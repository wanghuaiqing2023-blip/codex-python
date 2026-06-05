# Core exec bare prompt fallback

## Source graph slice

- Graph node `function:codex-rs/exec/src/lib.rs#run_main:232` remains the relevant non-interactive exec entrypoint.
- The Python CLI has a compatibility path where a bare prompt invocation can be converted into `exec` when an exec runtime is available.
- After making core exec the default API-key path, that compatibility entrypoint also needs to consider the core runtime, not only the older local HTTP switch.

## Python port

- Updated the top-level interactive prompt fallback in `pycodex.cli.parser.main`.
- A bare prompt now routes through `_run_noninteractive_exec` when either `local_http_exec_enabled()` or `core_exec_enabled()` is true.
- This keeps explicit `PYCODEX_EXEC_CORE=1` plus `PYCODEX_EXEC_LOCAL_HTTP=0` from falling back to the TUI when the caller expected the core exec path.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_uses_core_exec_when_core_only tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_uses_local_http_exec_when_available tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_is_interactive_path`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_api_key_defaults_to_core_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_core_env_uses_in_memory_core_http_sampling`

## Follow-up

- The standard `codex exec ...` path remains the primary porting target. Bare prompt fallback is a small compatibility bridge that now follows the same core/local runtime availability decision.
