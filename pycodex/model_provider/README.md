# pycodex.model_provider

Python porting target for Rust `codex-model-provider`.

Rust coordinate:

- Crate: `codex-model-provider`
- Rust path: `codex/codex-rs/model-provider`
- Python package: `pycodex/model_provider`

Status: `complete`

Implemented module contracts:

- `src/bearer_auth_provider.rs` bearer token/account/FedRAMP header injection
  behavior.
- `src/auth.rs` provider-scoped bearer auth selection, first-party auth
  conversion, unauthenticated provider, command-auth manager selection, and
  agent-identity request header behavior.
- `src/models_endpoint.rs` command-auth reporting and OpenAI-compatible
  `/models` endpoint URL/query construction.
- `src/provider.rs` configured provider facade behavior, account state,
  provider dispatch, and model-manager selection.
- `src/amazon_bedrock/*` Bedrock static catalog, Mantle endpoint/auth
  selection, SigV4 header filtering, and provider facade behavior.
- `src/lib.rs` public crate facade reexports.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_bearer_auth_provider_rs tests.test_model_provider_auth_rs tests.test_model_provider_models_endpoint_rs tests.test_model_provider_provider_rs tests.test_model_provider_amazon_bedrock_catalog_rs tests.test_model_provider_amazon_bedrock_mantle_rs tests.test_model_provider_amazon_bedrock_auth_rs tests.test_model_provider_amazon_bedrock_mod_rs tests.test_model_provider_lib_rs -v`
  passed on 2026-06-20 with `58 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile` over the package modules and Rust-derived
  tests passed on 2026-06-20.
