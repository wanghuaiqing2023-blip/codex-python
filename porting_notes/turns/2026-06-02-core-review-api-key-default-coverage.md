# Core review API-key default coverage

## Source graph slice

- Graph node `function:codex-rs/exec/src/lib.rs#run_main:232` covers both `codex exec` and the `review` subcommand handled through the exec runtime.
- Rust `run_exec_session` builds the initial review operation and then uses the same in-process exec/session path as ordinary user turns.

## Python port

- Added CLI coverage that top-level `codex review --uncommitted` defaults to `run_core_exec_command` when an API key is available and no explicit compatibility runtime is requested.
- The test protects the default core route from regressing back to the older local HTTP review runner.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_review_api_key_defaults_to_core_review_runner tests.test_cli_parser.TopLevelCliParserTests.test_main_review_core_env_uses_core_review_runner tests.test_cli_parser.TopLevelCliParserTests.test_main_review_local_http_runtime_prints_summary_and_final_message`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_api_key_defaults_to_core_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_uses_core_exec_when_core_only`

## Follow-up

- This is coverage for the already-wired default route. Deeper review-mode parity still depends on the core review prompt/output rendering path and should stay tied to the exec runtime slice.
