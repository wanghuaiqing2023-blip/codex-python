# `codex-responses-api-proxy/src/read_api_key.rs` alignment status

Rust crate: `codex-responses-api-proxy`

Rust module: `src/read_api_key.rs`

Python module: `pycodex/responses_api_proxy/__init__.py`

Status: `complete`

Implemented behavior:

- Fixed `1024` byte input buffer and `Bearer ` auth-header prefix.
- Incremental short-read handling until newline, EOF, or buffer capacity.
- CRLF/newline trimming.
- Empty input and full-buffer rejection with Rust-aligned messages.
- API-key byte validation for ASCII letters, digits, `-`, and `_`.
- IO error propagation through the injected reader boundary.

Runtime boundary:

- Unix `read(2)` stdin, zeroize optimization guarantees, heap leak lifetime, and
  `mlock(2)` memory locking remain native hardening boundaries. Python exposes
  the same validation and construction contract without claiming memory-locking
  semantics.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_responses_api_proxy_read_api_key_rs -v`
  passed on 2026-06-20 with `7 tests`.
- Included in combined focused validation with `tests.test_responses_api_proxy_dump_rs`:
  `9 tests` passed.
