# codex-api src/api_bridge.rs status

Rust crate: `codex-api`

Rust module: `src/api_bridge.rs`

Python package/module: `pycodex/codex_api/api_bridge.py`

Status: `complete`

Implemented Rust-derived behavior:

- `ApiError` to protocol `CodexErr` mapping for context-window, quota,
  usage-not-included, retryable, stream, server-overloaded, API status,
  invalid-request, cyber-policy, transport, and rate-limit variants.
- HTTP transport mapping for 503 overloaded/slow-down JSON bodies, 400
  cyber-policy bodies including websocket-wrapped errors, invalid image bodies,
  unknown bad requests, 500 internal server errors, 429 usage limit,
  usage-not-included, and retry-limit fallbacks.
- Usage-limit metadata projection from body and headers, including plan type,
  reset timestamp, active-limit-specific rate-limit snapshot, promo message,
  and rate-limit reached type.
- Unexpected response metadata extraction for URL, cf-ray, request ids,
  identity authorization errors, and base64 `x-error-json` identity codes.
- Source-branch coverage for direct API status errors, rate-limit-as-stream,
  `slow_down` 503 bodies, retry-limit transport fallback, timeout/network/build
  transport variants, 500 internal server errors, request-id precedence, invalid
  `x-error-json` ignoring, and usage-limit plan/reset timestamp projection.

Validation:

- `python -m pytest tests/test_codex_api_api_bridge_rs.py -q --tb=short`
  passed on 2026-06-21 with `21 passed, 8 subtests passed`.
- `python -m py_compile pycodex/codex_api/api_bridge.py pycodex/codex_api/__init__.py tests/test_codex_api_api_bridge_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `231 passed, 49 subtests passed`.
