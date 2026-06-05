# Core exec API-key default

## Source graph slice

- Graph node `function:codex-rs/exec/src/lib.rs#run_main:232` identifies the non-interactive `codex exec` entrypoint.
- Rust source confirms `run_main` builds `InProcessClientStartArgs` with `session_source: SessionSource::Exec`, `enable_codex_api_key_env: true`, and then calls `run_exec_session`.
- This makes the in-process core/app-server route the normal exec path, not an extension-only or experimental branch.

## Python port

- Updated `pycodex.exec.local_runtime.local_core_exec_enabled` so the core exec facade is enabled by default when `OPENAI_API_KEY` or `CODEX_API_KEY` is available.
- Kept explicit compatibility behavior:
  - `PYCODEX_EXEC_CORE=1` still forces core exec.
  - `PYCODEX_EXEC_CORE=0` disables core exec.
  - `PYCODEX_EXEC_LOCAL_HTTP=1` preserves the older local HTTP compatibility runner unless core is explicitly forced.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_runtime_uses_env_provider_and_model`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_api_key_defaults_to_core_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_core_env_uses_in_memory_core_http_sampling tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_default_uses_core_http_sampling tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_runtime_prints_summary_and_final_message`
- `python -m unittest tests.test_exec_core_runtime`

## Known gap

- The Python core facade still reuses some `local_http`-named helpers for provider/auth construction and rollout persistence. Those names should be untangled as follow-up cleanup once the default core path is stable.
