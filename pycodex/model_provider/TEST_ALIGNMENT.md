# codex-model-provider test alignment

Rust crate: `codex-model-provider`

Python package: `pycodex/model_provider`

Status: `complete`

Module mapping:

- `codex/codex-rs/model-provider/src/bearer_auth_provider.rs` ->
  `pycodex/model_provider/bearer_auth_provider.py` (`complete`)
- `codex/codex-rs/model-provider/src/auth.rs` ->
  `pycodex/model_provider/auth.py` (`complete`)
- `codex/codex-rs/model-provider/src/models_endpoint.rs` ->
  `pycodex/model_provider/models_endpoint.py` (`complete`)
- `codex/codex-rs/model-provider/src/provider.rs` ->
  `pycodex/model_provider/provider.py` (`complete`)
- `codex/codex-rs/model-provider/src/amazon_bedrock/catalog.rs` ->
  `pycodex/model_provider/amazon_bedrock/catalog.py` (`complete`)
- `codex/codex-rs/model-provider/src/amazon_bedrock/mantle.rs` ->
  `pycodex/model_provider/amazon_bedrock/mantle.py` (`complete`)
- `codex/codex-rs/model-provider/src/amazon_bedrock/auth.rs` ->
  `pycodex/model_provider/amazon_bedrock/auth.py` (`complete`)
- `codex/codex-rs/model-provider/src/amazon_bedrock/mod.rs` ->
  `pycodex/model_provider/amazon_bedrock/__init__.py` (`complete`)
- `codex/codex-rs/model-provider/src/lib.rs` ->
  `pycodex/model_provider/__init__.py` (`complete`)

Rust behavior covered in `tests/test_model_provider_bearer_auth_provider_rs.py`:

- `bearer_auth_provider_reports_when_auth_header_will_attach`
- `bearer_auth_provider_adds_auth_headers`
- `bearer_auth_provider_adds_fedramp_routing_header_for_fedramp_accounts`
- invalid header value rejection behavior from `HeaderValue::from_str`

Rust behavior covered in `tests/test_model_provider_auth_rs.py`:

- `unauthenticated_auth_provider_adds_no_headers`
- `bearer_auth_for_provider()` API-key before experimental-token selection
- `resolve_provider_auth()` provider bearer precedence and fallback behavior
- `auth_provider_from_auth()` bearer-like auth mapping
- `AgentIdentityAuthProvider.add_auth_headers()` AgentAssertion generation,
  signing-error tolerance, account/FedRAMP routing headers, and invalid header
  value skipping
- `auth_manager_for_provider()` external bearer manager selection for
  command-backed provider auth

Rust behavior covered in `tests/test_model_provider_models_endpoint_rs.py`:

- `command_auth_provider_reports_command_auth_without_cached_auth`
- `provider_without_command_auth_reports_no_command_auth`
- `MODELS_ENDPOINT` shape and OpenAI-compatible `/models` URL/client-version
  query construction

Rust behavior covered in `tests/test_model_provider_provider_rs.py`:

- default capabilities and approval-review preferred model
- configured runtime base URL
- command-auth manager construction
- Amazon Bedrock provider dispatch without retaining OpenAI auth manager
- OpenAI, API-key, ChatGPT-like, missing-detail, refresh-failure, custom
  non-OpenAI, and Amazon Bedrock account states
- static-catalog versus OpenAI endpoint model-manager selection

Rust behavior covered in `tests/test_model_provider_amazon_bedrock_catalog_rs.py`:

- `catalog_uses_mantle_model_ids_as_slugs`
- `gpt_5_4_cmb_advertises_only_bedrock_supported_reasoning_levels`
- GPT-5.4 CMB, GPT OSS, and reasoning-preset static metadata from
  `catalog.rs`

Rust behavior covered in `tests/test_model_provider_amazon_bedrock_mantle_rs.py`:

- `base_url_uses_region_endpoint`
- `base_url_rejects_unsupported_region`
- `aws_auth_config_uses_profile_and_mantle_service`
- `aws_auth_config_uses_configured_region`
- region trimming and runtime region resolution

Rust behavior covered in `tests/test_model_provider_amazon_bedrock_auth_rs.py`:

- `bedrock_bearer_auth_uses_configured_region_and_header`
- `bedrock_bearer_auth_rejects_missing_configured_region`
- `bedrock_mantle_sigv4_strips_headers_not_preserved_by_mantle`
- bearer-token env handling, auth-method selection, provider auth mapping,
  SigV4 pre-sign header stripping, and retryable/build auth-error mapping

Rust behavior covered in `tests/test_model_provider_amazon_bedrock_mod_rs.py`:

- `api_provider_for_bedrock_bearer_token_uses_configured_region_endpoint`
- `capabilities_disable_unsupported_hosted_tools`
- `approval_review_preferred_model_uses_bedrock_gpt_5_4`
- Bedrock no-OpenAI-auth, account-state, runtime URL, and static
  model-manager behavior

Rust behavior covered in `tests/test_model_provider_lib_rs.py`:

- `src/lib.rs` public reexports and `CoreAuthProvider` aliasing

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_bearer_auth_provider_rs -v`
  passed on 2026-06-20 with `4 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/bearer_auth_provider.py tests/test_model_provider_bearer_auth_provider_rs.py`
  passed on 2026-06-20.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_auth_rs -v`
  passed on 2026-06-20 with `9 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/auth.py tests/test_model_provider_auth_rs.py`
  passed on 2026-06-20.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_models_endpoint_rs -v`
  passed on 2026-06-20 with `3 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/models_endpoint.py tests/test_model_provider_models_endpoint_rs.py`
  passed on 2026-06-20.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_provider_rs -v`
  passed on 2026-06-20 with `12 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/provider.py tests/test_model_provider_provider_rs.py`
  passed on 2026-06-20.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_amazon_bedrock_catalog_rs tests.test_model_provider_amazon_bedrock_mantle_rs tests.test_model_provider_amazon_bedrock_auth_rs tests.test_model_provider_amazon_bedrock_mod_rs -v`
  passed on 2026-06-20 with `28 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_bearer_auth_provider_rs tests.test_model_provider_auth_rs tests.test_model_provider_models_endpoint_rs tests.test_model_provider_provider_rs tests.test_model_provider_amazon_bedrock_catalog_rs tests.test_model_provider_amazon_bedrock_mantle_rs tests.test_model_provider_amazon_bedrock_auth_rs tests.test_model_provider_amazon_bedrock_mod_rs tests.test_model_provider_lib_rs -v`
  passed on 2026-06-20 with `58 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile` over the package modules and Rust-derived
  tests passed on 2026-06-20.
