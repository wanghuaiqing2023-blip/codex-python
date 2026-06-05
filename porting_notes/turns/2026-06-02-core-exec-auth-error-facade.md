# Core exec auth error facade

## Source graph slice

- Graph node `function:codex-rs/exec/src/lib.rs#run_main:232` identifies the normal non-interactive `codex exec` entrypoint.
- Rust source shows `run_main` building `InProcessClientStartArgs` and entering `run_exec_session`, with `enable_codex_api_key_env: true`.
- That makes credential handling part of the default core exec path, so Python's core facade should not leak compatibility-only local HTTP switch names in user-facing errors.

## Python port

- Added a `build_default_core_exec_runtime` wrapper in `pycodex.exec.core_runtime`.
- The wrapper still delegates to the existing provider/auth construction while the core path is being untangled.
- It rewrites the old `PYCODEX_EXEC_LOCAL_HTTP=1` missing-key message to `OPENAI_API_KEY or CODEX_API_KEY is required for core exec runtime`.

## Validation

- `python -m unittest tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_build_default_core_exec_runtime_rewrites_auth_error tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_build_default_core_exec_runtime_delegates_success tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_core_runtime_facade_exports_core_helpers`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_core_missing_api_key_prints_core_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_missing_api_key_prints_human_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_core_env_uses_in_memory_core_http_sampling`

## Follow-up

- Continue replacing core facade imports that are direct aliases to `local_http`-named helpers with core-facing wrappers when they affect user-facing behavior.
