# http_transport

This package is a Python-specific stdlib HTTP/SSE transport adapter for the
core sampling path.

It intentionally does not map to one single Rust source file. The equivalent
Rust behavior is distributed across several modules:

- `codex-rs/core/src/client.rs`: model client setup, Responses API requests,
  response headers, turn-state headers, and stream construction.
- `codex-rs/core/src/client_common.rs`: shared `ResponseEvent` stream shape.
- `codex-rs/core/src/responses_retry.rs`: retry and reconnect decisions for
  response streams.
- `codex-rs/core/src/session/turn.rs`: turn-scoped sampling loop integration.
- `codex-rs/protocol/src/protocol.rs`: protocol payloads such as rate limits,
  model verification events, and stream/error data shapes.

Why this exists as one Python package:

- PyCodex avoids complex third-party HTTP/SSE dependencies.
- The Python implementation uses the standard library (`urllib`) and local SSE
  parsing helpers.
- Keeping this adapter together makes the transport boundary explicit while
  preserving the public import path `pycodex.core.http_transport`.

Porting rule:

- Treat this package as a compatibility adapter, not as an unported root-level
  leftover.
- When debugging request construction, headers, SSE parsing, retry behavior, or
  HTTP error mapping, compare this package against the Rust modules listed
  above by behavior slice.
- Do not force this package into `session/`, `tools/`, or `client/` unless the
  implementation is deliberately split by behavior in a future refactor.
