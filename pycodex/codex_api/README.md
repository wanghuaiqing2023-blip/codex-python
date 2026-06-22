# pycodex.codex_api

Python porting target for Rust `codex-api`.

Rust coordinate:

- Crate: `codex-api`
- Rust path: `codex/codex-rs/codex-api`
- Python package: `pycodex/codex_api`

Status: `complete`

Implemented module contracts:

- `src/lib.rs` crate-root public facade over the mapped module contracts,
  including endpoint clients, shared request/response data, search shapes,
  telemetry/auth/provider/error helpers, `codex-client` transport aliases, and
  realtime protocol facade names.
- `src/api_bridge.rs` `ApiError` to protocol `CodexErr` mapping, HTTP
  transport status/body/header classification, cyber-policy fallback handling,
  usage-limit metadata projection, retry-limit request tracking, and identity
  authorization error extraction, including direct API status errors,
  `slow_down` overloaded bodies, transport fallback variants, request-id
  precedence, invalid `x-error-json` ignoring, and usage-limit reset/plan
  projection.
- `src/auth.rs` auth error mapping, header-only auth provider default behavior,
  Rust `HeaderMap`-style case-insensitive auth header replacement,
  shared-provider surface, and auth header telemetry.
- `src/common.rs` shared request/response payload dataclasses, websocket
  metadata helpers, text controls, memory/compaction payload wire shapes,
  memory summarize required-field decoding, responses websocket request
  conversion including empty client metadata preservation, and lightweight
  response stream boundary.
- `src/error.rs` API error variants, user-facing display strings, transparent
  transport wrapping across transport variants, retryable delay storage, and
  rate-limit error conversion.
- `src/endpoint/compact.rs` compact endpoint path, POST body/timeout request
  shaping including arbitrary `serde_json::Value` body preservation,
  telemetry-bearing client cloning, typed response-item output decoding, and
  compaction input serialization.
- `src/endpoint/images.rs` image generation/edit endpoint request posting,
  extra-header/auth application, telemetry-bearing client cloning, typed image
  response decoding, and image decode-error mapping.
- `src/endpoint/memories.rs` memory summarize endpoint path, typed/raw POST
  body construction including arbitrary `serde_json::Value` preservation,
  telemetry-bearing client cloning, output decoding, and trace-summary alias
  handling.
- `src/endpoint/models.rs` models endpoint request construction,
  `client_version` query appending, auth/header application, `ETag` extraction,
  telemetry-bearing client cloning, and `ModelsResponse` decode/error mapping.
- `src/endpoint/realtime_call.rs` WebRTC realtime call POST request shaping,
  SDP body handling, backend/API session body variants, extra-header/auth
  application, telemetry-bearing client cloning, Location call-id parsing, and
  reuse of realtime websocket session JSON construction.
- `src/endpoint/realtime_websocket/{protocol,methods_common,methods_v1,methods_v2}.rs`
  pure realtime outbound-message/session helper slice: event parser/session
  config surface, V1 quicksilver and V2 realtime/transcription session JSON,
  conversation item/function-output message shapes, normalized V1 session mode,
  websocket intent, and Rust `Option::None` omission for absent session `id`
  and `model`.
- `src/endpoint/realtime_websocket/{protocol,protocol_common,protocol_v1,protocol_v2}.rs`
  pure realtime websocket event parser slice: V1/V2 dispatch, session update,
  audio, transcript, item, handoff/noop, error, speech-started, and response
  lifecycle event parsing, including Rust numeric conversion boundaries for
  audio frame fields.
- `src/endpoint/realtime_websocket/methods.rs` websocket URL/config helper
  slice: scheme conversion, realtime path normalization, intent/model/query
  construction, WebRTC sideband `call_id`, and default websocket config
  facade.
- `src/endpoint/realtime_websocket/methods.rs` active transcript helper slice:
  transcript delta/done accumulation, handoff transcript injection, handoff
  de-duplication, and new input/output entry boundaries.
- `src/endpoint/realtime_websocket/methods.rs` dependency-light websocket
  read/write facade slice: writer send helpers, idempotent close,
  send/close/read error mapping, ignored frame handling, binary error events,
  close termination, and active transcript updates during event parsing.
- `src/endpoint/realtime_websocket/methods.rs` standard-library connect/session
  projection: realtime websocket client URL/header/session-id setup, WebRTC
  sideband `call_id` joins, connector error mapping, stream adaptation, and
  immediate `session.update` send after connect. Header merge and
  `x-session-id` replacement preserve Rust `HeaderMap` case-insensitive
  behavior, session id values are validated like Rust `HeaderValue`, sideband
  retry sleeps use the shared Rust `codex-client` backoff schedule, and a
  local standard-library `ws://` mock server validates concrete websocket
  handshake/frame exchange against Rust's realtime mock-server e2e contract.
- `src/endpoint/responses.rs` responses HTTP stream request shaping, session
  and subagent headers, Azure stored-request item-id attachment, compression
  projection, event-stream accept header insertion, and SSE handoff boundary.
- `src/endpoint/responses_websocket.rs` wrapped websocket error parsing,
  websocket HTTP-error projection including Rust `u16` status parsing and
  invalid-type rejection, `StatusCode::from_u16` validity,
  connection-limit retryable mapping, JSON header scalar conversion with
  invalid name/value filtering, request header merge precedence, and
  websocket config projection.
- `src/endpoint/responses_websocket.rs` dependency-light websocket
  stream/send facade: request serialization, telemetry callback shape,
  send idle-timeout boundary mapping, reusable connection metadata prelude,
  `response.processed` send behavior, wrapped-error priority, rate-limit events, server-model de-dupe,
  model-verification events, completed termination, and binary/close/EOF/
  timeout/read-error stream errors.
- `src/endpoint/responses_websocket.rs` standard-library connect/probe
  projection: client URL/header/auth construction, websocket upgrade
  handshake, successful 101 metadata and turn-state capture from
  case-insensitive response headers, 101 upgrade/connection/accept validation,
  non-101 HTTP error mapping, strict UTF-8 body projection for non-101 HTTP
  errors including valid-body preservation and invalid-body clearing,
  close-frame probe reporting, and dependency-light frame send/read behavior
  including Ping/Pong pump filtering. An optional live-only
  smoke check exists for a real non-local `wss://` endpoint through
  `PYCODEX_LIVE_RESPONSES_WS_URL`; it is skipped unless real credentials are
  supplied and is not a crate-completion requirement. `codex-cli` doctor websocket
  diagnostics now consume this module's
  `ResponsesWebsocketClient.probe_handshake(...)` path, matching the Rust
  cross-crate call boundary.
- `src/endpoint/search.rs` search endpoint request posting, extra-header/auth
  application, telemetry-bearing client cloning, typed search response
  decoding, and search decode-error mapping.
- `src/endpoint/session.rs` shared endpoint session request construction,
  configure/auth/transport ordering, request telemetry retry wrapping, and
  transport-error to API-error mapping for execute/stream helpers.
- `src/files.rs` OpenAI file URI construction, file upload preflight checks,
  upload/finalize request sequencing through an injectable transport boundary,
  retry-finalize handling, file-upload error display variants, and
  finalization response optional string decode behavior.
- `src/images.rs` image generation/edit request wire shapes, image response
  payload decoding, lowercase image enums, Rust `u64` non-negative `created`
  decoding, required `b64_json` image data, and serde optional-field behavior.
- `src/provider.rs` retry policy conversion, provider URL/request/websocket
  helpers, stream idle timeout surface, and Azure responses provider detection.
- `src/rate_limits.rs` default/per-limit/all-limit header parsing,
  `codex.rate_limits` event parsing with strict JSON bool credit fields,
  credits and promo/protocol-enum reached-type helpers, and rate-limit
  snapshot dataclasses.
- `src/requests/headers.rs` session/thread header construction, subagent
  header mapping, guarded header insertion, and `HeaderValue::from_str`-style
  value validation.
- `src/requests/responses.rs` public compression enum surface and response
  input item id reattachment/replacement for serialized request payloads.
- `src/search.rs` search request/input/command/settings wire shapes, lowercase
  enum values, untagged input serialization, Rust `u64` non-negative operation
  limit validation, and encrypted-output response decoding.
- `src/sse/responses.rs` pure Responses SSE event helpers: model header
  extraction, model verification metadata decoding, response event mapping,
  token usage projection, retry-after parsing, failed/incomplete response error
  classification, completed parse-error mapping, response stream header prelude
  events, SSE data parsing, missing-completed stream errors, completed-event
  termination, and endpoint handoff through a dependency-light iterable facade.
- `src/telemetry.rs` public SSE/WebSocket telemetry traits, response/status
  helpers, request telemetry retry wrapper call semantics, and absent-telemetry
  retry behavior.

Latest focused validation:

- `python -m pytest tests/test_codex_api_lib_rs.py -q --tb=short` passed with
  `2 passed`.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api*_rs.py -q --tb=short` passed with
  `250 passed, 1 skipped, 79 subtests passed`.
- Optional live responses websocket smoke check
  `python -m pytest tests/test_codex_api_endpoint_responses_websocket_live_rs.py -q --tb=short -rs`
  skipped without `PYCODEX_LIVE_RESPONSES_WS_URL`; this is intentional and is
  not a local simulation.

The crate is considered complete for the active dependency-light Python port:
module-scoped behavior contracts are covered by Rust-derived tests, and
external live endpoint verification is treated as optional smoke coverage.
Do not reclassify `codex-api` as partial solely because the optional live
responses websocket smoke check has not been run against real credentials.
