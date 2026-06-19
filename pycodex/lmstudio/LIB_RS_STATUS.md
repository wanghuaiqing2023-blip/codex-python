# lmstudio/src/lib.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/lmstudio/src/lib.rs`

Python target:

- `pycodex/lmstudio/__init__.py`

Implemented public API:

- `DEFAULT_OSS_MODEL`
- `LMStudioClient` crate-root re-export
- `ensure_oss_ready`

Behavior:

- Uses `config.model` when present and `DEFAULT_OSS_MODEL` otherwise.
- Constructs the real `LMStudioClient` through `try_from_provider`.
- Fetches locally available models; if the selected model is absent, awaits
  `download_model` and propagates its errors.
- Treats `fetch_models` failures as nonfatal, matching Rust's warning-only
  branch.
- Schedules `load_model` as background work and logs/ignores load failures.

Validation:

- `python -m pytest tests/test_lmstudio_lib_rs.py tests/test_lmstudio_client_rs.py -q`
- `python -m py_compile pycodex/lmstudio/__init__.py pycodex/lmstudio/client.py tests/test_lmstudio_lib_rs.py tests/test_lmstudio_client_rs.py`
