# codex-ollama src/client.rs status

Status: `complete`

Rust module: `codex/codex-rs/ollama/src/client.rs`

Python module: `pycodex/ollama/client.py`

Behavior covered:

- `OllamaClient.try_from_oss_provider` looks up the built-in `ollama` provider
  from `config.model_providers`.
- `OllamaClient.try_from_provider` requires `base_url`, derives
  `host_root`, records whether the provider is OpenAI-compatible, and probes
  the server.
- `probe_server` checks `/v1/models` for OpenAI-compatible providers and
  `/api/tags` otherwise, returning the Rust install/start hint on failure.
- `fetch_models` GETs `/api/tags`, returns an empty list for non-success
  status, and extracts `models[*].name`.
- `fetch_version` GETs `/api/version`, returns `None` for non-success,
  missing, or unparsable version values, and trims whitespace plus leading
  `v` before semantic-version parsing.
- `pull_model_stream` POSTs `/api/pull` with `{"model": model, "stream": true}`,
  parses newline-delimited JSON chunks, yields parser events, yields error
  events, and mirrors Rust's extra terminal `Success` yield for
  `status == "success"`.
- `pull_with_reporter` emits the initial pulling status, forwards stream
  events, returns on success, reports stream errors as `Pull failed: ...`, and
  reports unexpected stream end.

Implementation notes:

- The default implementation uses standard-library `urllib` behind
  `asyncio.to_thread`, matching the dependency-light project rule.
- Tests can inject `OllamaTransport` to exercise the real client contract
  without requiring a running Ollama daemon.

Prepared tests:

- `tests/test_ollama_client_rs.py`

Validation:

- `python -m py_compile pycodex/ollama/__init__.py pycodex/ollama/url.py pycodex/ollama/pull.py pycodex/ollama/parser.py pycodex/ollama/client.py tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py`
  (passed)
- Focused crate pytest passed:
  `python -m pytest tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py tests/test_ollama_lib_rs.py -q`
  (`27 passed`)
