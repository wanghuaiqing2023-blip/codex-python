# codex-ollama src/lib.rs status

Status: `complete`

Rust module: `codex/codex-rs/ollama/src/lib.rs`

Python module: `pycodex/ollama/__init__.py`

Behavior covered:

- Crate-root re-export surface for `OllamaClient`, `CliProgressReporter`,
  `PullEvent`, `PullProgressReporter`, and `TuiProgressReporter`.
- `DEFAULT_OSS_MODEL = "gpt-oss:20b"`.
- `ensure_oss_ready` chooses `config.model` or the default, constructs an
  `OllamaClient`, fetches local models, pulls when the selected model is
  missing, and treats model-listing errors as nonfatal.
- `min_responses_version` and `supports_responses` mirror the Rust cutoff:
  dev `0.0.0` or `>= 0.13.4`.
- `ensure_responses_supported` constructs an `OllamaClient`, treats missing or
  unparsable versions as OK, accepts supported versions, and reports the exact
  too-old version error.

Prepared tests:

- `tests/test_ollama_lib_rs.py`

Validation:

- `python -m pytest tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py tests/test_ollama_lib_rs.py -q`
  (`27 passed`)
- `python -m py_compile pycodex/ollama/__init__.py pycodex/ollama/url.py pycodex/ollama/pull.py pycodex/ollama/parser.py pycodex/ollama/client.py tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py tests/test_ollama_lib_rs.py`
  (passed)
