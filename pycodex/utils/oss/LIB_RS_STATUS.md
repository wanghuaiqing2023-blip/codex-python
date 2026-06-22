# codex-utils-oss src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/oss/src/lib.rs`

Python coordinate: `pycodex/utils/oss/__init__.py`

Status: `complete`

Behavior contract:

- `get_default_model_for_oss_provider` returns LM Studio and Ollama default OSS model names, and `None` for unknown providers.
- `ensure_oss_provider_ready` skips unknown providers.
- LM Studio readiness delegates to a backend `ensure_oss_ready` call.
- Ollama readiness delegates to backend `ensure_responses_supported` before backend `ensure_oss_ready`.
- `ensure_oss_ready` failures are surfaced as `OSError("OSS setup failed: ...")`.

Evidence:

- `tests/test_utils_oss.py` maps the three Rust unit tests and covers the async readiness branches.
- `python -m pytest tests/test_utils_oss.py -q` passed.
- `python -m py_compile pycodex/utils/oss/__init__.py tests/test_utils_oss.py` passed.
