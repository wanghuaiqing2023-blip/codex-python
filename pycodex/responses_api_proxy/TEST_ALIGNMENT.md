# codex-responses-api-proxy test alignment

Rust crate: `codex-responses-api-proxy`

Python package: `pycodex/responses_api_proxy`

Status: `complete`

Module mapping:

- `codex/codex-rs/responses-api-proxy/src/read_api_key.rs` ->
  `pycodex/responses_api_proxy/__init__.py` (`complete`)
- `codex/codex-rs/responses-api-proxy/src/dump.rs` ->
  `pycodex/responses_api_proxy/__init__.py` (`complete`)
- `codex/codex-rs/responses-api-proxy/src/lib.rs` ->
  `pycodex/responses_api_proxy/__init__.py` (`complete`)
- `codex/codex-rs/responses-api-proxy/src/main.rs` ->
  `pycodex/responses_api_proxy/__init__.py` and
  `pycodex/responses_api_proxy/__main__.py` (`complete`)

Rust behavior covered in `tests/test_responses_api_proxy_read_api_key_rs.py`:

- Reads API keys with no newline.
- Reads API keys across short reads.
- Trims CRLF/newline suffixes.
- Rejects no input.
- Rejects keys that fill the fixed buffer without newline/EOF.
- Propagates IO errors from the reader boundary.
- Rejects invalid UTF-8 bytes and invalid key characters.

Rust behavior covered in `tests/test_responses_api_proxy_dump_rs.py`:

- Request dump JSON redacts authorization/cookie headers and preserves other
  headers/body.
- Response body tee streams bytes and writes response dump JSON with redacted
  headers.

Rust behavior covered in `tests/test_responses_api_proxy_lib_rs.py`:

- Default upstream URL and upstream host-header construction.
- Explicit upstream port preservation and upstream URL host validation.
- Exact `POST /v1/responses` allowlist and query rejection.
- Optional queryless `GET /shutdown` allowlist.
- Upstream request header replacement for `Authorization` and `Host`.
- Response header filtering for HTTP-server-managed headers only.
- Server-info `{port, pid}` JSON line writing.

Existing CLI integration coverage in `tests/test_cli_parser.py`:

- `responses-api-proxy` argument parsing and help.
- Local HTTP forwarding success/error behavior through CLI delegation to the
  package-owned runtime.
- Disallowed path and shutdown query rejection.
- Dump pair generation through the CLI runtime path.

Rust behavior covered in `tests/test_responses_api_proxy_main_rs.py`:

- Package `main(argv, ...)` delegates to the existing CLI runtime as
  `responses-api-proxy`.
- `ResponsesApiProxyArgs` values are converted to CLI arguments without
  changing the Rust default upstream URL unless explicitly overridden.
- Default `ResponsesApiProxyArgs` omits `--upstream-url`, preserving the Rust
  clap default.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_responses_api_proxy_main_rs tests.test_responses_api_proxy_lib_rs tests.test_responses_api_proxy_read_api_key_rs tests.test_responses_api_proxy_dump_rs -v`
  passed on 2026-06-20 with `21 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_responses_api_proxy_lib_rs tests.test_responses_api_proxy_read_api_key_rs tests.test_responses_api_proxy_dump_rs -v`
  passed on 2026-06-20 with `17 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/responses_api_proxy/__init__.py pycodex/cli/parser.py tests/test_responses_api_proxy_lib_rs.py tests/test_responses_api_proxy_read_api_key_rs.py tests/test_responses_api_proxy_dump_rs.py tests/test_cli_parser.py`
  passed on 2026-06-20.
- CLI smoke validation passed for selected `responses-api-proxy` tests:
  auth-header validation, too-long key rejection, local forwarding plus dump
  pair, upstream HTTP error mirroring, disallowed path 403, and shutdown query
  rejection. Combined focused validation passed with `27 tests` after moving
  the live proxy runtime into the package. The local HTTP smoke emits an existing
  ResourceWarning for unclosed test sockets but completes successfully.

Deferred:

- Native Rust `ctor` pre-main hardening remains documented as a binary/runtime
  side effect rather than reimplemented in Python.
