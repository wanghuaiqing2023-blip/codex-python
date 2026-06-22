# `codex-model-provider/src/lib.rs` alignment status

Rust crate: `codex-model-provider`

Rust module: `src/lib.rs`

Python module: `pycodex/model_provider/__init__.py`

Status: `complete`

Covered behavior:

- Public reexports for `auth_provider_from_auth`,
  `unauthenticated_auth_provider`, `BearerAuthProvider`,
  `CoreAuthProvider`, `ProviderAccount`, `ModelProvider`,
  `ProviderAccountError`, `ProviderAccountResult`, `ProviderAccountState`,
  `ProviderCapabilities`, `SharedModelProvider`, and
  `create_model_provider`.
- `CoreAuthProvider` aliases `BearerAuthProvider`.

Evidence:

- Rust source: `codex/codex-rs/model-provider/src/lib.rs`.
- Python tests: `tests/test_model_provider_lib_rs.py`.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_lib_rs -v`
  is included in the crate-focused validation and passed on 2026-06-20 with
  `2 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/__init__.py tests/test_model_provider_lib_rs.py`
  is included in the crate syntax validation and passed on 2026-06-20.
