# `codex-model-provider/src/provider.rs` alignment status

Rust crate: `codex-model-provider`

Rust module: `src/provider.rs`

Python module: `pycodex/model_provider/provider.py`

Status: `complete`

Covered behavior:

- Default provider capabilities and approval-review preferred model.
- Configured provider runtime base URL.
- Command-backed provider auth manager construction.
- Amazon Bedrock provider dispatch without retaining the OpenAI auth manager.
- OpenAI account state for unauthenticated, API-key, ChatGPT-like, missing
  ChatGPT account detail, and refresh-failure cases.
- Custom non-OpenAI provider account state.
- Amazon Bedrock account state.
- Model-manager selection between configured static catalogs and
  OpenAI-compatible endpoint-backed managers.

Evidence:

- Rust source: `codex/codex-rs/model-provider/src/provider.rs`.
- Rust tests:
  - `configured_provider_uses_default_capabilities`
  - `configured_provider_uses_default_approval_review_preferred_model`
  - `configured_provider_runtime_base_url_uses_configured_base_url`
  - `create_model_provider_builds_command_auth_manager_without_base_manager`
  - `create_model_provider_does_not_use_openai_auth_manager_for_amazon_bedrock_provider`
  - `openai_provider_returns_unauthenticated_openai_account_state`
  - `openai_provider_returns_api_key_account_state`
  - `custom_non_openai_provider_returns_no_account_state`
  - `amazon_bedrock_provider_returns_bedrock_account_state`
  - selected model-manager contracts from the remaining Rust async tests
- Python tests: `tests/test_model_provider_provider_rs.py`.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_provider_rs -v`
  passed on 2026-06-20 with `12 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/provider.py tests/test_model_provider_provider_rs.py`
  passed on 2026-06-20.
