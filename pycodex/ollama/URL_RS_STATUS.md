# codex-ollama src/url.rs Status

Rust source:

- `codex/codex-rs/ollama/src/url.rs`

Python mapping:

- `pycodex/ollama/url.py`

Status: `complete`

Implemented behavior:

- `is_openai_compatible_base_url(...)` trims trailing slashes and checks for a
  terminal `/v1` path.
- `base_url_to_host_root(...)` trims trailing slashes and removes a terminal
  `/v1` segment for OpenAI-compatible Ollama provider URLs.

Validation:

- `python -m py_compile pycodex/ollama/__init__.py pycodex/ollama/url.py tests/test_ollama_url_rs.py`
  passed on 2026-06-19.
- Focused crate pytest passed:
  `python -m pytest tests/test_ollama_url_rs.py tests/test_ollama_parser_rs.py tests/test_ollama_pull_rs.py tests/test_ollama_client_rs.py tests/test_ollama_lib_rs.py -q`
  (`27 passed`)
