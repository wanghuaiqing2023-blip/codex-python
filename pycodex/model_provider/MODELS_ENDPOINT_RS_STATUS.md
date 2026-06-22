# `codex-model-provider/src/models_endpoint.rs` alignment status

Rust crate: `codex-model-provider`

Rust module: `src/models_endpoint.rs`

Python module: `pycodex/model_provider/models_endpoint.py`

Status: `complete`

Covered behavior:

- `MODELS_ENDPOINT` uses the Rust endpoint shape `"/models"`.
- `OpenAiModelsEndpoint.has_command_auth()` reports command-backed provider
  auth without requiring cached auth.
- Providers without command-backed auth report `False`.
- OpenAI-compatible `/models` URL construction appends the endpoint once and
  preserves existing query parameters when appending `client_version`.

Evidence:

- Rust source: `codex/codex-rs/model-provider/src/models_endpoint.rs`.
- Rust tests:
  - `command_auth_provider_reports_command_auth_without_cached_auth`
  - `provider_without_command_auth_reports_no_command_auth`
- Python tests: `tests/test_model_provider_models_endpoint_rs.py`.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_models_endpoint_rs -v`
  passed on 2026-06-20 with `3 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/models_endpoint.py tests/test_model_provider_models_endpoint_rs.py`
  passed on 2026-06-20.
