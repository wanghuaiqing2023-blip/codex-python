# codex-api/src/endpoint/images.rs status

Rust module: `codex/codex-rs/codex-api/src/endpoint/images.rs`

Python module: `pycodex/codex_api/endpoint/images.py`

Status: `complete`

Ported contract:

- `ImagesClient` owns an injected transport, provider, auth provider, and
  optional telemetry placeholder matching the Rust client shape.
- `generate` posts typed `ImageGenerationRequest` JSON to
  `images/generations`.
- `edit` posts typed `ImageEditRequest` JSON to `images/edits`.
- Endpoint requests apply extra headers/auth through the shared session-shaped
  request boundary.
- `with_telemetry` returns a new client with request telemetry configured while
  preserving the existing transport/provider/auth boundaries.
- Image endpoint responses decode through `ImageResponse`.
- Image response decode failures map to `ApiError.stream(...)` with the
  operation name in the message.

Intentional adaptation:

- Rust routes through async `EndpointSession`. Python keeps the same
  request/auth/transport boundaries dependency-light and reuses the endpoint
  helper functions introduced for `src/endpoint/models.rs`.

Validation:

- `tests/test_codex_api_endpoint_images_rs.py`
- Focused validation command:
  `python -m pytest tests/test_codex_api_endpoint_images_rs.py -q --tb=short`
  (`5 passed`) on 2026-06-21.
- Crate focused validation command:
  `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` (`219 passed, 47 subtests passed`) on
  2026-06-21.
- Syntax validation:
  `python -m py_compile tests\test_codex_api_endpoint_images_rs.py pycodex\codex_api\endpoint\images.py`
  passed on 2026-06-21.
- Focused validation command:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_api_auth_rs tests.test_codex_api_error_rs tests.test_codex_api_rate_limits_rs tests.test_codex_api_common_rs tests.test_codex_api_provider_rs tests.test_codex_api_requests_headers_rs tests.test_codex_api_requests_responses_rs tests.test_codex_api_telemetry_rs tests.test_codex_api_files_rs tests.test_codex_api_images_rs tests.test_codex_api_search_rs tests.test_codex_api_endpoint_models_rs tests.test_codex_api_endpoint_images_rs -v`
  (`64 tests`).
- Syntax validation:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/codex_api/__init__.py pycodex/codex_api/auth.py pycodex/codex_api/common.py pycodex/codex_api/error.py pycodex/codex_api/files.py pycodex/codex_api/images.py pycodex/codex_api/provider.py pycodex/codex_api/rate_limits.py pycodex/codex_api/search.py pycodex/codex_api/telemetry.py pycodex/codex_api/endpoint/__init__.py pycodex/codex_api/endpoint/images.py pycodex/codex_api/endpoint/models.py pycodex/codex_api/requests/__init__.py pycodex/codex_api/requests/headers.py pycodex/codex_api/requests/responses.py tests/test_codex_api_auth_rs.py tests/test_codex_api_common_rs.py tests/test_codex_api_endpoint_images_rs.py tests/test_codex_api_endpoint_models_rs.py tests/test_codex_api_error_rs.py tests/test_codex_api_files_rs.py tests/test_codex_api_images_rs.py tests/test_codex_api_provider_rs.py tests/test_codex_api_rate_limits_rs.py tests/test_codex_api_requests_headers_rs.py tests/test_codex_api_requests_responses_rs.py tests/test_codex_api_search_rs.py tests/test_codex_api_telemetry_rs.py`
  passed on 2026-06-20.
