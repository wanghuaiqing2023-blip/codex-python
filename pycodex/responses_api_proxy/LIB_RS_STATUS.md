# `codex-responses-api-proxy/src/lib.rs` alignment status

Rust crate: `codex-responses-api-proxy`

Rust module: `src/lib.rs`

Python module: `pycodex/responses_api_proxy/__init__.py`

Status: `complete`

Implemented behavior:

- `Args`-equivalent configuration shape through `ResponsesApiProxyArgs`,
  including the Rust default upstream URL
  `https://api.openai.com/v1/responses`.
- Upstream URL parsing and `Host` header construction, including explicit
  upstream ports and missing-host errors.
- Exact proxy allowlist for `POST /v1/responses` without query strings.
- Optional shutdown allowlist for queryless `GET /shutdown`.
- Upstream request header projection that drops caller `Authorization` and
  `Host`, then injects the proxy auth header and upstream host header.
- Downstream response header filtering for headers managed by the HTTP server:
  `content-length`, `transfer-encoding`, `connection`, `trailer`, and
  `upgrade`.
- Server-info JSON payload and one-line file writing with `{port, pid}`.
- The existing CLI `responses-api-proxy` runtime now calls these package
  helpers for request allowlisting, shutdown allowlisting, upstream host/header
  construction, response header filtering, and server-info writing.
- The live blocking HTTP server runtime now lives in this package and covers
  listener creation, per-request handling, concrete upstream forwarding,
  response adaptation, dump generation, and shutdown handling. The CLI command
  delegates to this package-owned runtime.

Runtime boundary:

- Rust uses `reqwest` and `tiny_http` while the dependency-light Python port
  uses standard-library `urllib` and `http.server` adapters with matching
  request/response behavior covered by focused smoke tests.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_responses_api_proxy_lib_rs tests.test_responses_api_proxy_read_api_key_rs tests.test_responses_api_proxy_dump_rs -v`
  passed on 2026-06-20 with `17 tests`.
- Combined focused validation with selected CLI integration smoke tests passed
  on 2026-06-20 with `27 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/responses_api_proxy/__init__.py pycodex/cli/parser.py tests/test_responses_api_proxy_lib_rs.py tests/test_responses_api_proxy_read_api_key_rs.py tests/test_responses_api_proxy_dump_rs.py tests/test_cli_parser.py`
  passed on 2026-06-20.
