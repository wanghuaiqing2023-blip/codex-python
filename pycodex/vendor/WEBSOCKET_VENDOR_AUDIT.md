# WebSocket vendor audit

This audit records whether the Python port should keep its standard-library
WebSocket subset or vendor a mature protocol implementation.

## Rust behavior boundary

- Rust crate: `codex-api`
- Rust module: `endpoint::responses_websocket`
- Rust anchor: `ResponsesWebsocketClient::connect`,
  `connect_websocket`, `websocket_config`, and `WsStream`
- Rust source:
  `codex/codex-rs/codex-api/src/endpoint/responses_websocket.rs`
- Important runtime behavior:
  - Uses `tokio_tungstenite::connect_async_tls_with_config`.
  - Uses tungstenite `Message` handling for text, binary, close, ping, pong,
    and frame events.
  - Enables `permessage-deflate` through `WebSocketConfig`.
  - Uses the same custom-CA policy as HTTPS through the rustls connector.
  - Serializes stream use with a mutex while a response stream is active.

## Current Python state

- Python module: `pycodex.codex_api.endpoint.responses_websocket`
- Current transport: `_StdlibResponsesWebsocketStream`
- Supporting generic transport: `pycodex.exec.websocket.StdlibWebSocket`
- Implementation style: standard-library socket/TLS plus local handshake and
  frame encode/decode.

The current implementation is a useful subset for the active Responses
websocket path, but it is not a full RFC 6455/RFC 7692 implementation. Known
protocol gaps include:

- incomplete continuation-frame and fragmentation semantics;
- no real `permessage-deflate` negotiation or compression handling;
- limited RSV/control-frame validation;
- partial close-handshake behavior;
- limited protocol-level UTF-8 and close-code validation;
- TLS/proxy/runtime behavior that does not match Rust's tungstenite/rustls
  stack at the library level.

## Candidate packages

Candidate metadata was read from PyPI on 2026-06-25. The selected
`websockets==11.0.3` wheel was later extracted into `pycodex/vendor` and wired
behind `pycodex.codex_api.endpoint._websocket_client`.

| Package | Candidate pin | License | Requires Python | Runtime deps | Notes |
|---|---:|---|---|---|---|
| `websockets` | `11.0.3` | BSD-3-Clause | `>=3.7` | none | Sync client, TLS context support, default `permessage-deflate`, fragmentation support. |
| `wsproto` | `1.2.0` | MIT | `>=3.7.0` | `h11` | Strong sans-I/O protocol core, but we would still own socket/TLS/client glue. |
| `websocket-client` | `1.6.1` | Apache-2.0 | `>=3.7` | none | Simple blocking client, but no obvious bundled `permessage-deflate` implementation in the wheel. |

Latest package versions were not selected because current releases for these
libraries have moved beyond the repository's existing Python 3.7 compatibility
policy.

Downloaded wheel hashes:

| Package | Wheel | SHA256 |
|---|---|---|
| `websockets` | `websockets-11.0.3-py3-none-any.whl` | `6681ba9e7f8f3b19440921e99efbb40fc89f26cd71bf539e45d8c8a25c976dc6` |
| `wsproto` | `wsproto-1.2.0-py3-none-any.whl` | `b9acddd652b585d75b20477888c56642fdade28bdfd3579aa24a4d2c037dd736` |
| `websocket-client` | `websocket_client-1.6.1-py3-none-any.whl` | `f1f9f2ad5291f0225a49efad77abf9e700b6fef553900623060dad6e26503b9d` |

## Recommendation

If websocket remains only an optional optimization with reliable HTTP fallback,
the current standard-library subset can remain temporarily, guarded by focused
Rust-derived tests and live probes.

If websocket is treated as a product-critical path for TUI prewarm, streaming,
and first-token latency, use the vendored `websockets==11.0.3` client behind
the existing Python module boundary.

Recommended integration boundary:

```text
pycodex.codex_api.endpoint.responses_websocket
  -> pycodex.codex_api.endpoint._websocket_client
    -> pycodex.vendor._packages.websockets
```

The public Python behavior should stay at the Rust-aligned
`ResponsesWebsocketClient` / `ResponsesWebsocketConnection` boundary. Vendoring
should replace only handshake/frame/TLS transport internals, not the codex-api
event mapping or response stream API.

## Implementation record

Implemented:

1. Vendored `websockets==11.0.3` source and license into `pycodex/vendor`.
2. Added `pycodex.codex_api.endpoint._websocket_client`, a small compatibility
   wrapper exposing connect, send text, receive next message, close, and
   immediate close probe semantics.
3. Preserved custom CA behavior by passing the existing `ssl.SSLContext` from
   `_ssl_context_for_websocket`.
4. Kept HTTP fallback and websocket disable behavior at the core/client layer
   unchanged.

Validation should include:

- `tests/test_codex_api_endpoint_responses_websocket_rs.py`
- `tests/test_core_suite_client_websockets.py`
- `tests/test_core_http_transport.py`
- the live websocket probe test when credentials are available
