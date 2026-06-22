# lmstudio/src/client.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/lmstudio/src/client.rs`

Python target:

- `pycodex/lmstudio/client.py`

Implemented public API:

- `LMStudioClient.try_from_provider`
- `LMStudioClient.load_model`
- `LMStudioClient.fetch_models`
- `LMStudioClient.find_lms`
- `LMStudioClient.find_lms_with_home_dir`
- `LMStudioClient.download_model`
- `LMStudioClient.from_host_root`

Notes:

- The Python port uses standard-library `urllib` and runs blocking HTTP/process
  work through `asyncio.to_thread`.
- Rust `reqwest` error wrappers are mirrored as Python `OSError`/`ValueError`
  messages at the public boundary.
- `download_model` preserves the `lms get --yes <model>` command shape; tests
  inject `subprocess.run` instead of invoking a real LM Studio install.

Validation:

- `python -m pytest tests/test_lmstudio_client_rs.py -q`
- `python -m py_compile pycodex/lmstudio/client.py pycodex/lmstudio/__init__.py tests/test_lmstudio_client_rs.py`
