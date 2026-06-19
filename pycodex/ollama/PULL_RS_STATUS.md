# codex-ollama src/pull.rs status

Status: `complete`

Rust module: `codex/codex-rs/ollama/src/pull.rs`

Python module: `pycodex/ollama/pull.py`

Behavior covered:

- Pull event value variants: status, chunk progress, success, and error.
- `PullProgressReporter` observer protocol.
- `CliProgressReporter` default/new state.
- Status rendering to stderr-style writer, including case-insensitive
  `pulling manifest` suppression and line-padding cleanup.
- Chunk progress aggregation by digest, first-header rendering, byte progress,
  percentage, speed calculation, and line-padding cleanup.
- Error events are intentionally ignored by the reporter.
- Success events write a newline.
- `TuiProgressReporter` delegates to `CliProgressReporter`.

Prepared tests:

- `tests/test_ollama_pull_rs.py`

Validation:

- `python -m py_compile pycodex/ollama/__init__.py pycodex/ollama/url.py pycodex/ollama/pull.py pycodex/ollama/parser.py tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py`
  (passed)
- Focused crate pytest passed:
  `python -m pytest tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py tests/test_ollama_lib_rs.py -q`
  (`27 passed`)
