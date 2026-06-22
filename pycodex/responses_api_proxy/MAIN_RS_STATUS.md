# `codex-responses-api-proxy/src/main.rs` alignment status

Rust crate: `codex-responses-api-proxy`

Rust module: `src/main.rs`

Python modules:

- `pycodex/responses_api_proxy/__init__.py`
- `pycodex/responses_api_proxy/__main__.py`

Status: `complete`

Implemented behavior:

- Package `main(argv, stdin, stdout, stderr)` and `run_main(args, ...)`
  provide a crate-owned entrypoint for the proxy command.
- Iterable argv input is parsed into `ResponsesApiProxyArgs`, matching Rust's
  binary command handoff.
- `ResponsesApiProxyArgs` dataclass values are converted to CLI arguments,
  including `--port`, `--server-info`, `--http-shutdown`, `--upstream-url`, and
  `--dump-dir`.
- The Rust default upstream URL is omitted from generated argv unless the
  caller overrides it, preserving clap's default behavior.
- `python -m pycodex.responses_api_proxy` exits through this package
  entrypoint.

Native boundary:

- Rust's `#[ctor::ctor]` `codex_process_hardening::pre_main_hardening()` call
  is a native binary hardening side effect. The Python port records it as a
  runtime boundary rather than duplicating OS hardening here.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_responses_api_proxy_main_rs tests.test_responses_api_proxy_lib_rs tests.test_responses_api_proxy_read_api_key_rs tests.test_responses_api_proxy_dump_rs -v`
  passed on 2026-06-20 with `21 tests`.
- Combined focused validation with selected CLI integration smoke tests passed
  on 2026-06-20 with `27 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/responses_api_proxy/__init__.py pycodex/responses_api_proxy/__main__.py tests/test_responses_api_proxy_main_rs.py`
  passed on 2026-06-20.
