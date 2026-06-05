# Resume last model-provider default

## Source slice

- Graph entrypoint: `function:codex-rs/exec/src/lib.rs#run_exec_session:564`.
- Graph-selected dependency: `function:codex-rs/exec/src/lib.rs#resolve_resume_thread_id:1335`.
- Rust source check: `resume_lookup_model_providers` returns `Some(vec![config.model_provider_id.clone()])` for `resume --last`, and `Config.model_provider_id` is an effective provider string.

## Python port

- `ExecSessionConfig.model_provider_id` is optional in the Python compatibility layer, so the previous `resume --last` request could serialize `modelProviders: [None]` when built from a minimal config.
- `pycodex.exec.session.resume_lookup_model_providers` now defaults missing provider IDs to `"openai"` for `resume --last`, matching the effective default used by the Python exec config/runtime paths and preserving the Rust request shape.
- Added a focused test that asserts `thread/list` for `resume --last` never emits a null provider.

## Validation

- `python -m unittest tests.test_exec_session.ExecSessionRequestBuilderTests.test_resume_thread_list_request_matches_upstream_last_lookup_shape tests.test_exec_session.ExecSessionRequestBuilderTests.test_resume_search_request_omits_model_provider_filter_without_last tests.test_exec_session.ExecSessionRequestBuilderTests.test_resume_last_defaults_missing_model_provider_like_exec_config tests.test_exec_session.ExecSessionRequestBuilderTests.test_resume_thread_id_lookup_step_matches_upstream_branches`
- `python -m unittest tests.test_exec_session`
