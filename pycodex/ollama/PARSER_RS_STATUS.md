# codex-ollama src/parser.rs status

Status: `complete`

Rust module: `codex/codex-rs/ollama/src/parser.rs`

Python module: `pycodex/ollama/parser.py`

Behavior covered:

- `pull_events_from_value` emits a `Status` event when `status` is a string.
- A `status == "success"` update emits `Status("success")` followed by
  `Success`.
- `total` and `completed` are accepted only when they match Rust
  `JsonValue::as_u64` semantics.
- A progress event is emitted when either `total` or `completed` is present.
- Missing or non-string `digest` values default to the empty string.

Dependency note:

- `pycodex/ollama/pull.py` provides the `PullEvent` value interface required
  by this parser module; Rust `src/pull.rs` reporter behavior is also mapped
  in the same module.

Prepared tests:

- `tests/test_ollama_parser_rs.py`

Validation:

- `python -m py_compile pycodex/ollama/__init__.py pycodex/ollama/url.py pycodex/ollama/pull.py pycodex/ollama/parser.py tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py`
  (passed)
- Focused crate pytest passed:
  `python -m pytest tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py tests/test_ollama_lib_rs.py -q`
  (`27 passed`)
