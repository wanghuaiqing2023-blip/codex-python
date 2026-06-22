# codex-ollama test alignment

Rust crate: `codex-ollama`

Python package: `pycodex/ollama`

Status: `complete`

Module mapping:

- `codex/codex-rs/ollama/src/url.rs` ->
  `pycodex/ollama/url.py` (`complete`)
- `codex/codex-rs/ollama/src/parser.rs` ->
  `pycodex/ollama/parser.py` (`complete`)
- `codex/codex-rs/ollama/src/client.rs` ->
  `pycodex/ollama/client.py` (`complete`)
- `codex/codex-rs/ollama/src/pull.rs` ->
  `pycodex/ollama/pull.py` (`complete`)
- `codex/codex-rs/ollama/src/lib.rs` ->
  `pycodex/ollama/__init__.py` (`complete`)

Rust behavior prepared in `tests/test_ollama_url_rs.py`:

- `base_url_to_host_root` Rust unit-test cases
- trailing slash trimming before `/v1` removal
- `is_openai_compatible_base_url` terminal `/v1` detection

Rust behavior prepared in `tests/test_ollama_parser_rs.py`:

- status and success event ordering
- chunk progress event construction from `digest`, `total`, and `completed`
- Rust `JsonValue::as_u64` filtering for progress fields
- empty-string digest fallback

Rust behavior prepared in `tests/test_ollama_pull_rs.py`:

- status rendering, padding, and `pulling manifest` suppression
- chunk progress aggregation, header rendering, percentage, and speed text
- zero-total progress, error, and success event handling
- TUI reporter delegation

Rust behavior prepared in `tests/test_ollama_client_rs.py`:

- provider lookup, host-root normalization, and probe path selection
- model listing and version parsing
- connection-error hint projection
- pull stream request shape, parser event yielding, stream error handling, and
  terminal success handling
- reporter-driven pull success/error/unexpected-end behavior

Rust behavior prepared in `tests/test_ollama_lib_rs.py`:

- crate-root re-exports and `DEFAULT_OSS_MODEL`
- `supports_responses` dev-zero/cutoff behavior
- `ensure_oss_ready` default/explicit model orchestration, pull decision, and
  warning-only model-listing failures
- `ensure_responses_supported` accepted versions, missing-version OK behavior,
  and too-old error text

Remaining module: none.

Validation:

- `python -m pytest tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py tests/test_ollama_lib_rs.py -q`
  (`27 passed`)
- `python -m py_compile pycodex/ollama/__init__.py pycodex/ollama/url.py pycodex/ollama/pull.py pycodex/ollama/parser.py pycodex/ollama/client.py tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py tests/test_ollama_lib_rs.py`
  (passed)
