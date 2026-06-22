# codex-lmstudio test alignment

Rust crate: `codex-lmstudio`

Python package: `pycodex/lmstudio`

Status: `complete`

Certified modules:

- `codex/codex-rs/lmstudio/src/client.rs` -> `pycodex/lmstudio/client.py`
- `codex/codex-rs/lmstudio/src/lib.rs` -> `pycodex/lmstudio/__init__.py`

Rust behavior covered by `tests/test_lmstudio_client_rs.py`:

- `fetch_models` GETs `/models`, extracts `data[*].id`, rejects missing `data`,
  and reports non-success status as `Failed to fetch models: <status>`.
- `check_server` treats successful `/models` status as ready, reports
  non-success status with the LM Studio install/start hint, and reports
  connection failures with the same Rust hint.
- `load_model` POSTs `/responses` with `model`, empty `input`, and
  `max_output_tokens = 1`, and reports non-success status.
- `find_lms` prefers `lms` on `PATH`; `find_lms_with_home_dir` checks the Rust
  fallback path under `.lmstudio/bin`.
- `from_host_root` stores the raw base URL.
- `try_from_provider` looks up the built-in `lmstudio` provider, requires a
  `base_url`, checks the server, and returns a client.
- `download_model` executes `lms get --yes <model>` and reports non-zero exits.

Rust behavior covered by `tests/test_lmstudio_lib_rs.py`:

- crate-root `DEFAULT_OSS_MODEL` matches Rust's default OSS model.
- `LMStudioClient` is re-exported at the crate root.
- `ensure_oss_ready` uses the default model when `config.model` is absent.
- existing models skip download and still schedule background loading.
- missing models are downloaded before background loading.
- model-listing failures are nonfatal.
- download failures propagate.
- background load failures are swallowed after logging.

Remaining module: none.

Validation:

- `python -m pytest tests/test_lmstudio_lib_rs.py tests/test_lmstudio_client_rs.py -q` (`20 passed`)
- `python -m py_compile pycodex/lmstudio/__init__.py pycodex/lmstudio/client.py tests/test_lmstudio_lib_rs.py tests/test_lmstudio_client_rs.py` (passed)
