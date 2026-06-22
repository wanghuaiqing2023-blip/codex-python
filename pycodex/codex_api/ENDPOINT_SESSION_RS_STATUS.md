# codex-api/src/endpoint/session.rs status

Rust module: `codex/codex-rs/codex-api/src/endpoint/session.rs`

Python module: `pycodex/codex_api/endpoint/session.py`

Status: `complete`

Implemented behavior:

- `EndpointSession.new(...)` stores transport, provider, and shared auth.
- `with_request_telemetry(...)` returns a session copy with request telemetry.
- `provider()` exposes the provider reference used by endpoint clients.
- Request construction starts from `Provider.build_request(...)`, extends
  provider headers with extra headers, and attaches an optional JSON body.
- `execute(...)` delegates to `execute_with(...)` with a no-op configure hook.
- `execute_with(...)` rebuilds a request for each retry attempt, invokes the
  configure hook before auth, applies auth, delegates to `transport.execute`,
  and maps terminal `TransportError` values to `ApiError::Transport`.
- `stream_with(...)` mirrors the same flow for `transport.stream`.

Adaptation note:

- Rust configure hooks receive `&mut Request`. Python's existing
  `codex_client.Request` is frozen at top level but carries mutable header
  dictionaries; this module preserves configure ordering and header mutation.
  Broader top-level request mutation should be revisited when endpoint clients
  migrate onto the shared session helper.

Validation:

- `python -m pytest tests/test_codex_api_endpoint_session_rs.py -q --tb=short`
  passed on 2026-06-20 with `5 passed`.
- `python -m py_compile pycodex/codex_api/endpoint/session.py tests/test_codex_api_endpoint_session_rs.py`
  passed on 2026-06-20.
