# `codex-model-provider/src/amazon_bedrock/*` alignment status

Rust crate: `codex-model-provider`

Rust modules:

- `src/amazon_bedrock/catalog.rs`
- `src/amazon_bedrock/mantle.rs`
- `src/amazon_bedrock/auth.rs`
- `src/amazon_bedrock/mod.rs`

Python package: `pycodex/model_provider/amazon_bedrock`

Status: `complete`

Covered behavior:

- Static Bedrock model catalog ordering and model metadata for GPT-5.4 CMB and
  GPT OSS Bedrock models.
- Bedrock-specific reasoning effort presets and descriptions.
- Mantle region endpoint construction, supported-region validation, auth config
  profile/region/service construction, and runtime region resolution.
- Bedrock bearer-token auth env lookup, configured-region requirement,
  provider-auth mapping, AWS context loader fallback, SigV4 provider creation,
  retryable/build auth error distinction, and removal of snake_case headers not
  preserved by the Mantle front door.
- `AmazonBedrockModelProvider` capabilities, approval-review model,
  no-OpenAI-auth behavior, app-visible account state, runtime/api provider base
  URL, and static model-manager behavior.

Evidence:

- Rust sources:
  - `codex/codex-rs/model-provider/src/amazon_bedrock/catalog.rs`
  - `codex/codex-rs/model-provider/src/amazon_bedrock/mantle.rs`
  - `codex/codex-rs/model-provider/src/amazon_bedrock/auth.rs`
  - `codex/codex-rs/model-provider/src/amazon_bedrock/mod.rs`
- Python tests:
  - `tests/test_model_provider_amazon_bedrock_catalog_rs.py`
  - `tests/test_model_provider_amazon_bedrock_mantle_rs.py`
  - `tests/test_model_provider_amazon_bedrock_auth_rs.py`
  - `tests/test_model_provider_amazon_bedrock_mod_rs.py`

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_amazon_bedrock_catalog_rs tests.test_model_provider_amazon_bedrock_mantle_rs tests.test_model_provider_amazon_bedrock_auth_rs tests.test_model_provider_amazon_bedrock_mod_rs -v`
  passed on 2026-06-20 with `28 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/amazon_bedrock/catalog.py pycodex/model_provider/amazon_bedrock/mantle.py pycodex/model_provider/amazon_bedrock/auth.py pycodex/model_provider/amazon_bedrock/__init__.py tests/test_model_provider_amazon_bedrock_catalog_rs.py tests/test_model_provider_amazon_bedrock_mantle_rs.py tests/test_model_provider_amazon_bedrock_auth_rs.py tests/test_model_provider_amazon_bedrock_mod_rs.py`
  passed on 2026-06-20.
