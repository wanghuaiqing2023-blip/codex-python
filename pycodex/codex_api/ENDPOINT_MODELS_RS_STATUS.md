# codex-api/src/endpoint/models.rs status

Rust module: `codex/codex-rs/codex-api/src/endpoint/models.rs`

Python module: `pycodex/codex_api/endpoint/models.py`

Status: `complete`

Ported contract:

- `ModelsClient` owns an injected transport, provider, auth provider, and
  optional telemetry placeholder matching the Rust client shape.
- `ModelsClient.path()` returns `models`.
- `append_client_version_query` appends `client_version` with `?` or `&`
  depending on the request URL.
- `list_models` builds a GET request through `Provider`, merges extra headers,
  applies auth, executes the unary transport path, extracts `ETag`, decodes
  `ModelsResponse`, and returns `(models, etag)`.
- `with_telemetry` returns a new client with request telemetry configured while
  preserving the existing transport/provider/auth boundaries.
- Decode failures map to `ApiError.stream(...)` with the failed body included,
  matching the Rust `ApiError::Stream` branch shape.

Intentional adaptation:

- Rust uses async `HttpTransport` and `EndpointSession`. Python keeps the
  transport boundary injectable and awaits only auth providers that expose an
  awaitable `apply_auth`, avoiding a new HTTP dependency.

Validation:

- `tests/test_codex_api_endpoint_models_rs.py`
- Focused validation command:
  `python -m pytest tests/test_codex_api_endpoint_models_rs.py -q --tb=short`
  (`5 passed`) on 2026-06-21.
- Crate focused validation command:
  `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` (`222 passed, 47 subtests passed`) on
  2026-06-21.
- Syntax validation:
  `python -m py_compile tests\test_codex_api_endpoint_models_rs.py pycodex\codex_api\endpoint\models.py`
  passed on 2026-06-21.
- Focused validation command:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_api_auth_rs tests.test_codex_api_error_rs tests.test_codex_api_rate_limits_rs tests.test_codex_api_common_rs tests.test_codex_api_provider_rs tests.test_codex_api_requests_headers_rs tests.test_codex_api_requests_responses_rs tests.test_codex_api_telemetry_rs tests.test_codex_api_files_rs tests.test_codex_api_images_rs tests.test_codex_api_search_rs tests.test_codex_api_endpoint_models_rs -v`
  (`61 tests`).
- Syntax validation:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/codex_api/__init__.py pycodex/codex_api/auth.py pycodex/codex_api/common.py pycodex/codex_api/error.py pycodex/codex_api/files.py pycodex/codex_api/images.py pycodex/codex_api/provider.py pycodex/codex_api/rate_limits.py pycodex/codex_api/search.py pycodex/codex_api/telemetry.py pycodex/codex_api/endpoint/__init__.py pycodex/codex_api/endpoint/models.py pycodex/codex_api/requests/__init__.py pycodex/codex_api/requests/headers.py pycodex/codex_api/requests/responses.py tests/test_codex_api_auth_rs.py tests/test_codex_api_common_rs.py tests/test_codex_api_endpoint_models_rs.py tests/test_codex_api_error_rs.py tests/test_codex_api_files_rs.py tests/test_codex_api_images_rs.py tests/test_codex_api_provider_rs.py tests/test_codex_api_rate_limits_rs.py tests/test_codex_api_requests_headers_rs.py tests/test_codex_api_requests_responses_rs.py tests/test_codex_api_search_rs.py tests/test_codex_api_telemetry_rs.py`
  passed on 2026-06-20.
