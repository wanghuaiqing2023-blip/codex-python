# pycodex.codex_client

Python porting target for Rust `codex-client`.

Rust coordinate:

- Crate: `codex-client`
- Rust path: `codex/codex-rs/codex-client`
- Python package: `pycodex/codex_client`

Status: `complete`

Implemented module contracts:

- `src/chatgpt_cloudflare_cookies.rs` shared ChatGPT Cloudflare service-cookie
  allowlist behavior.
- `src/custom_ca.rs` custom CA environment selection, PEM normalization,
  certificate DER extraction, dependency-light builder/error boundaries, and
  rustls config stand-in behavior. Real reqwest/rustls TLS registration and
  local TLS handshake probes remain runtime validation debt.
- `src/chatgpt_hosts.rs` first-party ChatGPT host allowlist behavior.
- `src/error.rs` transport and stream error variant/display contract.
- `src/retry.rs` retry predicate, backoff, and retry-loop contract.
- `src/telemetry.rs` request telemetry interface contract.
- `src/sse.rs` minimal SSE data-frame forwarding and stream-error contract.
- `src/request.rs` request/body preparation behavior, including compact JSON
  serialization, raw body handling, compression conflict checks, valid zstd
  raw-frame byte production, and public response/body shape. Python uses a
  dependency-light standards-compliant Zstandard raw-block frame for the zstd
  branch rather than byte-identical native zstd level-3 output.
- `src/default_client.rs` default request builder/send facade behavior:
  builder creation, chained header/auth/timeout/body/json methods,
  HeaderMap-style replacement, stored builder errors, send-time trace-header
  injection, dependency-light W3C traceparent projection, debug success/failure
  events, default real local HTTP send through the standard-library transport,
  and async send facade. Full native reqwest/OpenTelemetry integration remains
  runtime debt.
- `src/transport.rs` request preparation, trace body formatting, status/error
  mapping, injected-sender response handling, dependency-light standard-library
  real HTTP dispatch, HTTPS custom-CA context selection, stream body error item
  mapping, async execute/stream facades, and Rust source-order edge cases for
  trace-before-build and body-read-before-status behavior. Native reqwest/Tokio
  runtime error text identity and generated TLS handshake probes remain
  dependency/runtime debt outside the accepted Python module contract.
- `src/lib.rs` crate-root facade re-export contract.

Tracked runtime debt:

- No unaudited module files remain. Remaining notes are native integration debt
  for full reqwest/Tokio/OpenTelemetry/rustls identity and generated TLS probes,
  while the dependency-light Python module contracts are complete.
