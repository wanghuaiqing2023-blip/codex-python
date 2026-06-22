# `codex-model-provider/src/bearer_auth_provider.rs` alignment status

Rust crate: `codex-model-provider`

Rust module: `src/bearer_auth_provider.rs`

Python module: `pycodex/model_provider/bearer_auth_provider.py`

Status: `complete`

Implemented behavior:

- `BearerAuthProvider.new(token)` stores only the bearer token.
- `BearerAuthProvider.for_test(token, account_id)` mirrors the Rust test
  helper shape.
- `add_auth_headers(...)` inserts `Authorization: Bearer <token>` when a valid
  token is present.
- `add_auth_headers(...)` inserts `ChatGPT-Account-ID` when a valid account id
  is present.
- FedRAMP accounts add `X-OpenAI-Fedramp: true`.
- Invalid header values containing carriage return, newline, or NUL are skipped
  to match Rust `HeaderValue::from_str(...).ok()` behavior.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_bearer_auth_provider_rs -v`
  passed on 2026-06-20 with `4 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/bearer_auth_provider.py tests/test_model_provider_bearer_auth_provider_rs.py`
  passed on 2026-06-20.
